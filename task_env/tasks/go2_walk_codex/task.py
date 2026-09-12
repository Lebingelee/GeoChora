"""Independent Go2 Codex environment with the active C2b reward variant."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
from typing import Any

import numpy as np

from ...registry import register_env
from ...vectorization.registry import register_parallel_env
from ..go2_walk.task import (
    GO2_POLICY_DT,
    Go2WalkTaskDefinition,
    _base_roll_pitch,
    _torch_quat_rotate_inverse,
)
from ..go2_walk_deploy.task import (
    GO2_DEPLOY_HEIGHT_ENV_ID,
    GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION,
    _height_moving_tracking_multiplier_device,
    _height_moving_tracking_multiplier_host,
    Go2WalkDeployHeightEnv,
    Go2WalkDeployHeightTaskDefinition,
)
from .reward import (
    C2B_REWARD_VARIANT,
    c2a_tracking_terms_device,
    c2a_tracking_terms_host,
    c2b_stability_terms_device,
    c2b_stability_terms_host,
)
from .diagnostics import scalar_diagnostics
from .sampler import Go2WalkCodexResetSampler


GO2_CODEX_ENV_ID = "go2-walk-codex"


class Go2WalkCodexTaskDefinition(Go2WalkDeployHeightTaskDefinition):
    """C2b task definition: axis-wise tracking with weak stability shaping."""

    def _reward(
        self,
        lin,
        ang,
        gravity,
        torque,
        action,
        previous,
        qpos,
        qvel,
        commands,
        previous_vel,
        contact_ground,
        contact_body,
        contact_geom=None,
        *,
        base_height=None,
        roll=None,
        pitch=None,
        foot_positions=None,
    ):
        """Replace C0 planar tracking and add C2b stability shaping on host."""

        base_reward, base_terms = super()._reward(
            lin,
            ang,
            gravity,
            torque,
            action,
            previous,
            qpos,
            qvel,
            commands,
            previous_vel,
            contact_ground,
            contact_body,
            contact_geom,
            base_height=base_height,
            roll=roll,
            pitch=pitch,
            foot_positions=foot_positions,
        )
        del base_reward
        command_value = np.asarray(commands, dtype=np.float32)
        lin_value = np.asarray(lin, dtype=np.float32)
        command_magnitude = np.linalg.norm(command_value[..., :2], axis=-1)
        tracking_multiplier = _height_moving_tracking_multiplier_host(
            command_magnitude
        )
        terms = dict(base_terms)
        terms.pop("tracking_lin_vel", None)
        terms.update(
            c2a_tracking_terms_host(
                lin=lin_value,
                commands=command_value,
                tracking_multiplier=tracking_multiplier,
                dt=GO2_POLICY_DT,
            )
        )
        projected_gravity = (
            np.asarray(gravity, dtype=np.float32)
            if gravity is not None
            else np.zeros_like(lin_value, dtype=np.float32)
        )
        if gravity is None:
            projected_gravity[..., 2] = -1.0
        if roll is None or pitch is None:
            roll, pitch = _base_roll_pitch(qpos, None, self.base_body_id)
        terms.update(
            c2b_stability_terms_host(
                lin=lin_value,
                projected_gravity=projected_gravity,
                base_height=base_height,
                roll=roll,
                pitch=pitch,
                dt=GO2_POLICY_DT,
            )
        )
        total = np.sum(np.stack(tuple(terms.values()), axis=0), axis=0)
        return np.asarray(total, dtype=np.float32), terms

    def evaluate(self, *, state, action, elapsed_steps, previous_state=None):
        """Add C2b scalar diagnostics to the inherited host evaluation."""

        result = super().evaluate(
            state=state,
            action=action,
            elapsed_steps=elapsed_steps,
            previous_state=previous_state,
        )
        qpos = np.asarray(state.qpos, dtype=np.float32)
        qvel = np.asarray(state.qvel, dtype=np.float32)
        if self._commands is None:
            commands = np.zeros(self.command_dim, dtype=np.float32)
        else:
            commands = np.asarray(self._commands, dtype=np.float32)
        diagnostics = scalar_diagnostics(
            qpos=qpos,
            qvel=qvel,
            commands=commands,
            body_xquat=state.body_xquat,
            body_xpos=state.body_xpos,
        )
        metrics = dict(result.metrics)
        if state.is_batch:
            metrics.update(diagnostics)
        else:
            metrics.update({name: float(value[0]) for name, value in diagnostics.items()})
        return replace(result, metrics=metrics)

    def evaluate_device(self, *, state, action, elapsed_steps=None, previous_state=None):
        """Apply the same C2b algebra after the inherited device path."""

        import torch

        result = super().evaluate_device(
            state=state,
            action=action,
            elapsed_steps=elapsed_steps,
            previous_state=previous_state,
        )
        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        body_xquat = state.arrays.get("body_xquat")
        if body_xquat is not None and body_xquat.shape[1] > self.base_body_id:
            root_quat = body_xquat[:, self.base_body_id]
        else:
            root_quat = qpos[:, 3:7]
        lin = _torch_quat_rotate_inverse(root_quat, qvel[:, :3])
        commands = self._device_update_heading_command(
            qpos=qpos,
            root_quat=root_quat,
            batch_size=int(state.num_envs),
        )
        command_magnitude = torch.linalg.vector_norm(commands[..., :2], dim=-1)
        tracking_multiplier = _height_moving_tracking_multiplier_device(
            command_magnitude
        )
        terms = dict(result["reward_terms"])
        terms.pop("tracking_lin_vel", None)
        terms.update(
            c2a_tracking_terms_device(
                lin=lin,
                commands=commands,
                tracking_multiplier=tracking_multiplier,
                dt=torch.as_tensor(GO2_POLICY_DT, dtype=qpos.dtype, device=qpos.device),
            )
        )
        result["reward_terms"] = terms
        result["reward"] = torch.stack(tuple(terms.values()), dim=0).sum(dim=0)

        world_gravity = torch.zeros_like(qvel[:, :3])
        world_gravity[:, 2] = -1.0
        projected = _torch_quat_rotate_inverse(root_quat, world_gravity)
        base_height = result["metrics"]["base_height"]
        if self.command_dim >= 4:
            height_target = commands[..., 3]
        else:
            height_target = torch.full_like(base_height, 0.34)
        roll = result["metrics"]["roll"]
        pitch = result["metrics"]["pitch"]
        terms.update(
            c2b_stability_terms_device(
                lin=lin,
                projected_gravity=projected,
                base_height=base_height,
                roll=roll,
                pitch=pitch,
                dt=torch.as_tensor(
                    GO2_POLICY_DT, dtype=qpos.dtype, device=qpos.device
                ),
            )
        )
        result["reward_terms"] = terms
        result["reward"] = torch.stack(tuple(terms.values()), dim=0).sum(dim=0)
        metrics = dict(result["metrics"])
        metrics.update(
            {
                "command_velocity_x": commands[..., 0],
                "forward_velocity": lin[..., 0],
                "velocity_error_x": commands[..., 0] - lin[..., 0],
                "command_velocity_y": commands[..., 1],
                "lateral_velocity": lin[..., 1],
                "velocity_error_y": commands[..., 1] - lin[..., 1],
                "abs_vz": torch.abs(lin[..., 2]),
                "base_height_error": base_height - height_target,
                "projected_gravity_x": projected[..., 0],
                "projected_gravity_y": projected[..., 1],
                "projected_gravity_xy_norm": torch.linalg.vector_norm(
                    projected[..., :2], dim=-1
                ),
                "roll_abs": torch.abs(roll),
                "pitch_abs": torch.abs(pitch),
            }
        )
        result["metrics"] = metrics
        return result


@register_parallel_env()
@register_env()
class Go2WalkCodexEnv(Go2WalkDeployHeightEnv):
    """Independent registry entry for the active C2b reward experiment."""

    uid = GO2_CODEX_ENV_ID
    task_uid = GO2_CODEX_ENV_ID

    @classmethod
    def default_config_path(cls) -> Path:
        del cls
        return Path(__file__).with_name("default.yaml")

    @classmethod
    def default_config(cls):
        config = super().default_config()
        return replace(
            config,
            task=replace(config.task, task_uid=cls.task_uid),
            observation=replace(
                config.observation,
                schema_version=GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION,
            ),
        )

    def placement_notes(self) -> tuple[str, ...]:
        return (
            "Codex C2b preserves the deploy-height 46D actor and 49D privileged critic contract.",
            "The sampler remains the C0 nominal pose with small root/joint velocity perturbations.",
            "C2b replaces combined planar tracking with weighted x/y terms and weak stability shaping.",
            "Canonical Go2 asset, ground/contact, physics, action, observation, and command schedules are inherited.",
        )

    def reference_profile(self) -> dict[str, Any]:
        profile = super().reference_profile()
        profile.update(
            {
                "profile_id": "task-env-go2-walk-codex-c2b-reference-v1",
                "source_environment": GO2_DEPLOY_HEIGHT_ENV_ID,
                "reward_variant": C2B_REWARD_VARIANT.as_dict(),
                "sampler": {
                    "profile": "go2_walk_codex_stage2_narrow_reset_v1",
                    "root_linear_velocity_range": [-0.10, 0.10],
                    "root_angular_velocity_range": [-0.10, 0.10],
                    "joint_velocity_range": [-0.05, 0.05],
                    "joint_pose": "genesis_nominal",
                    "root_height_range": [0.30, 0.40],
                    "deployment_eval_height": 0.34,
                },
            }
        )
        return profile

    def create_reset_sampler(self):
        return Go2WalkCodexResetSampler()

    def create_task_definition(self, compiled_scene):
        base = super().create_task_definition(compiled_scene)
        values = {field.name: getattr(base, field.name) for field in fields(Go2WalkTaskDefinition)}
        return Go2WalkCodexTaskDefinition(**values)


__all__ = ["GO2_CODEX_ENV_ID", "Go2WalkCodexEnv", "Go2WalkCodexTaskDefinition"]
