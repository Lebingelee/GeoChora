"""Private Go2 deployment-contract task (45-d actor observation).

The deployment task is a separate registered environment rather than a mode
branch in ``go2_walk``.  Its observation is exactly the real-robot layout:
angular velocity, projected gravity, command, joint position error, joint
velocity, and previous action.  Training uses the Unitree uniform noise
vector; deployment/evaluation should use the independent MuJoCo evaluator,
which is deterministic.
"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from gymnasium.spaces import Box, Dict

from ...environment import (
    EpisodePhysicsState,
    ObservationFieldSpec,
    ObservationSchema,
    RuntimeSnapshot,
    TaskStateView,
    as_task_state_view,
    freeze_observation,
)
from ...environment.configuration import resolve_env_config
from ...registry import register_env
from ...robots.go2 import GO2_DEFAULT_JOINT_ANGLES
from ...vectorization.registry import register_parallel_env
from ..base import BaseTaskEnv
from .assets import GO2_SCENE_UID, Go2WalkSceneComposer, canonical_xml_digest
from ..go2_walk.task import (
    GO2_ACTION_CONTRACT,
    GO2_CONTROL_SUBSTEPS,
    GO2_COMMAND_OBS_SCALE,
    GO2_HORIZON,
    GO2_HEIGHT_COMMAND_MAX,
    GO2_HEIGHT_COMMAND_MIN,
    GO2_TERMINATION_ANGLE,
    GO2_OBS_SCHEMA_VERSION,
    GO2_PHYSICS_DT,
    GO2_POLICY_DT,
    Go2ObservationBuilder,
    Go2WalkEnv,
    Go2WalkResetSampler,
    Go2WalkTaskDefinition,
    _base_kinematics,
    _torch_quat_rotate_inverse,
)


GO2_DEPLOY_ENV_ID = "go2-walk-deploy-v1"
GO2_DEPLOY_OBS_SCHEMA_VERSION = "task-env-go2-walk-deploy-observation-v1"
GO2_DEPLOY_OBSERVATION_DIM = 45
GO2_DEPLOY_HEIGHT_ENV_ID = "go2-walk-deploy-height-v1"
GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION = "task-env-go2-walk-deploy-height-observation-v1"
GO2_DEPLOY_HEIGHT_OBSERVATION_DIM = 46
GO2_DEPLOY_ROOT_HEIGHT = 0.34
GO2_DEPLOY_HEIGHT_DEFAULT = 0.34
GO2_DEPLOY_HEIGHT_MIN = GO2_HEIGHT_COMMAND_MIN
GO2_DEPLOY_HEIGHT_MAX = GO2_HEIGHT_COMMAND_MAX
GO2_DEPLOY_HEIGHT_PENALTY_MAX = 0.1
GO2_DEPLOY_HEIGHT_REWARD_SCALE = 0.00
GO2_DEPLOY_HEIGHT_VX_MIN = -0.7
GO2_DEPLOY_HEIGHT_VX_MAX = 0.7
GO2_DEPLOY_HEIGHT_VY_MIN = -0.7
GO2_DEPLOY_HEIGHT_VY_MAX = 0.7
# Kept as a compatibility/export bound for callers that only understand one
# symmetric linear limit.  Sampling and clipping use the per-axis ranges.
GO2_DEPLOY_HEIGHT_LINEAR_COMMAND_LIMIT = max(
    abs(GO2_DEPLOY_HEIGHT_VX_MIN), abs(GO2_DEPLOY_HEIGHT_VX_MAX),
    abs(GO2_DEPLOY_HEIGHT_VY_MIN), abs(GO2_DEPLOY_HEIGHT_VY_MAX),
)
GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT = 1.0
# Controlled initialization variant used by the height-domain diagnostic.
# The ordinary Go2 walk sampler remains Genesis-deterministic; only the
# height-domain experiment opts into the historical randomized reset.
GO2_HEIGHT_RESET_ROOT_VELOCITY_MIN = -0.5
GO2_HEIGHT_RESET_ROOT_VELOCITY_MAX = 0.5
GO2_HEIGHT_RESET_JOINT_SCALE_MIN = 0.5
GO2_HEIGHT_RESET_JOINT_SCALE_MAX = 1.5
GO2_HEIGHT_RESET_HIP_MIN = -0.1
GO2_HEIGHT_RESET_HIP_MAX = 0.1
GO2_HEIGHT_TERMINATION_GRACE_STEPS = 10
GO2_HEIGHT_MOVING_COMMAND_THRESHOLD = 0.1
GO2_HEIGHT_MOVING_COMMAND_MAX = 0.5
GO2_HEIGHT_MOVING_TRACKING_MULTIPLIER = 2.0
GO2_HEIGHT_FEET_AIR_TIME_SCALE = 0.10
GO2_HEIGHT_FOOT_CLEARANCE_SCALE = 0.05
GO2_HEIGHT_FOOT_CLEARANCE_TARGET = 0.08
GO2_HEIGHT_EFFECTIVE_SWING_SCALE = 0.10
GO2_HEIGHT_EFFECTIVE_SWING_MAX = 0.25
GO2_HEIGHT_HIP_POS_SCALE = -1.0
# Local 12-DOF order is FL, FR, RL, RR for the hip joints at 0, 3, 6, 9.
GO2_HEIGHT_HIP_INDICES = np.asarray((0, 3, 6, 9), dtype=np.int32)
GO2_HEIGHT_HIP_DEFAULT_POS = np.asarray(
    (0.1, -0.1, 0.1, -0.1), dtype=np.float32
)
# The requested Unitree/legged_gym reward contract for the active 46D task.
# Keep this table as the single source of truth for both host and device paths.
GO2_HEIGHT_REWARD_SCALES = {
    "tracking_lin_vel": 1.0,
    "tracking_ang_vel": 0.5,
    "lin_vel_z": -2.0,
    "ang_vel_xy": -0.05,
    "orientation": -0.2,
    "torques": -0.0002,
    "dof_acc": -2.5e-7,
    "base_height": -0.8,
    "hip_pos": GO2_HEIGHT_HIP_POS_SCALE,
    "feet_air_time": 1.0,
    "collision": -1.0,
    "action_rate": -0.01,
    "stand_still": -0.2,
    "dof_pos_limits": -10.0,
    "feet_slip": -0.1,
    "termination": -0.0,
    "dof_vel": -0.0,
    "feet_stumble": -0.0,
}
# Backup of the pre-alignment 46D height-deploy reward.  It remains exported
# for checkpoint/diagnostic metadata, but is no longer used by the active
# reward methods below.
GO2_HEIGHT_GENESIS_REWARD_SCALES = {
    "tracking_lin_vel": 1.0,
    "tracking_ang_vel": 0.2,
    "lin_vel_z": -1.0,
    "base_height": -50.0,
    "action_rate": -0.003,
    "similar_to_default": -0.05,
}
# Height-deploy-only attitude shaping.  Roll is the primary stabilization
# signal; pitch is deliberately weaker so forward/backward motion is not
# over-constrained.  Both terms are squared angles multiplied by policy_dt.
GO2_DEPLOY_ROLL_ORIENTATION_WEIGHT = 1.0
GO2_DEPLOY_PITCH_ORIENTATION_WEIGHT = 0.5
GO2_DEPLOY_NOISE_SCALE = np.concatenate(
    (
        np.full(3, 0.2 * 0.25, dtype=np.float32),
        np.full(3, 0.05, dtype=np.float32),
        np.zeros(3, dtype=np.float32),
        np.full(12, 0.01, dtype=np.float32),
        np.full(12, 1.5 * 0.05, dtype=np.float32),
        np.zeros(12, dtype=np.float32),
    )
)
GO2_DEPLOY_HEIGHT_NOISE_SCALE = np.concatenate(
     (
        np.full(3, 0.2 * 0.25, dtype=np.float32),
        np.full(3, 0.05, dtype=np.float32),
        np.zeros(4, dtype=np.float32),
        np.full(12, 0.01, dtype=np.float32),
        np.full(12, 1.5 * 0.05, dtype=np.float32),
        np.zeros(12, dtype=np.float32),
    )
)


def _uniform_noise(
    values: np.ndarray, rng: np.random.Generator, scale: np.ndarray = GO2_DEPLOY_NOISE_SCALE
) -> np.ndarray:
    value = np.asarray(values, dtype=np.float32)
    noise = (2.0 * rng.random(value.shape, dtype=np.float32) - 1.0) * np.asarray(scale, dtype=np.float32)
    return (value + noise).astype(np.float32, copy=False)


def _clip_height_deploy_command(command: np.ndarray) -> np.ndarray:
    """限制 46D height-deploy 任务的前三个运动 command。"""

    value = np.asarray(command, dtype=np.float32).copy()
    if value.shape[-1] < 3:
        raise ValueError("Go2 height-deploy command must contain x/y/yaw values")
    value[..., :2] = np.clip(
        value[..., :2],
        np.asarray((GO2_DEPLOY_HEIGHT_VX_MIN, GO2_DEPLOY_HEIGHT_VY_MIN), dtype=np.float32),
        np.asarray((GO2_DEPLOY_HEIGHT_VX_MAX, GO2_DEPLOY_HEIGHT_VY_MAX), dtype=np.float32),
    )
    value[..., 2] = np.clip(
        value[..., 2],
        -GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
        GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
    )
    return value


def _height_moving_tracking_multiplier_host(command_magnitude: np.ndarray) -> np.ndarray:
    """Return a continuous quadratic velocity-tracking emphasis on host."""

    magnitude = np.asarray(command_magnitude, dtype=np.float32)
    span = np.float32(
        GO2_HEIGHT_MOVING_COMMAND_MAX - GO2_HEIGHT_MOVING_COMMAND_THRESHOLD
    )
    normalized = np.clip(
        (magnitude - np.float32(GO2_HEIGHT_MOVING_COMMAND_THRESHOLD)) / span,
        0.0,
        1.0,
    )
    return (
        np.float32(1.0)
        + (np.float32(GO2_HEIGHT_MOVING_TRACKING_MULTIPLIER) - np.float32(1.0))
        * np.square(normalized)
    ).astype(np.float32, copy=False)


def _height_moving_tracking_multiplier_device(command_magnitude):
    """Device twin of :func:`_height_moving_tracking_multiplier_host`."""

    import torch

    span = torch.as_tensor(
        GO2_HEIGHT_MOVING_COMMAND_MAX - GO2_HEIGHT_MOVING_COMMAND_THRESHOLD,
        dtype=command_magnitude.dtype,
        device=command_magnitude.device,
    )
    normalized = torch.clamp(
        (command_magnitude - GO2_HEIGHT_MOVING_COMMAND_THRESHOLD) / span,
        min=0.0,
        max=1.0,
    )
    return 1.0 + (
        GO2_HEIGHT_MOVING_TRACKING_MULTIPLIER - 1.0
    ) * normalized.square()


class Go2DeployObservationBuilder(Go2ObservationBuilder):
    """Sensor-only builder shared by the 45D and 46D deploy contracts."""

    def __init__(self, *, joint_qpos_ids, joint_dof_ids, base_body_id, command_dim=3,
                 schema_version=GO2_DEPLOY_OBS_SCHEMA_VERSION, noise_scale=GO2_DEPLOY_NOISE_SCALE):
        super().__init__(
            joint_qpos_ids=joint_qpos_ids,
            joint_dof_ids=joint_dof_ids,
            base_body_id=base_body_id,
        )
        self.command_dim = int(command_dim)
        self.observation_dim = 42 + self.command_dim
        self.noise_scale = np.asarray(noise_scale, dtype=np.float32)
        if self.noise_scale.shape != (self.observation_dim,):
            raise ValueError("Go2 deploy noise scale must match observation dimension")
        self.observation_space = Dict({"state": Dict({"proprioception": Box(
            low=-100.0, high=100.0, shape=(self.observation_dim,), dtype=np.float32
        )})})
        self._schema = ObservationSchema(
            version=schema_version,
            fields=(ObservationFieldSpec(
                name="state.proprioception", shape=(self.observation_dim,), dtype="float32",
                semantic=(f"base_ang_vel(3), projected_gravity(3), commands({self.command_dim}), "
                          "dof_pos_error(12), dof_vel(12), actions(12); deployable Go2 ordering"),
            ),),
            groups=("state",),
        )
        self._noise_rng = np.random.default_rng(0)

    def _build(self, view: TaskStateView, command: np.ndarray, actions: np.ndarray) -> Any:
        qpos = np.asarray(view.qpos, dtype=np.float32)
        qvel = np.asarray(view.qvel, dtype=np.float32)
        _, _, base_ang, projected = _base_kinematics(qpos, qvel, view.body_xpos, self._base_body_id)
        dof_pos = qpos[..., self._qpos_ids] - GO2_DEFAULT_JOINT_ANGLES
        dof_vel = qvel[..., self._dof_ids]
        command_value = np.asarray(command, dtype=np.float32)
        scaled_command = command_value[..., :3] * GO2_COMMAND_OBS_SCALE
        if self.command_dim == 4:
            scaled_command = np.concatenate((scaled_command, command_value[..., 3:4]), axis=-1)
        parts = (base_ang * 0.25, projected, scaled_command, dof_pos, dof_vel * 0.05, np.asarray(actions, dtype=np.float32))
        if qpos.ndim == 1:
            values = _uniform_noise(np.concatenate(parts), self._noise_rng, self.noise_scale)
            if values.shape != (self.observation_dim,):
                raise ValueError(f"Go2 deploy scalar observation must have shape ({self.observation_dim},)")
            return freeze_observation((("state", {"proprioception": values}),))
        values = np.concatenate(parts, axis=1)
        values = _uniform_noise(values, self._noise_rng, self.noise_scale)
        return {"state": {"proprioception": values}}


class Go2WalkDeployTaskDefinition(Go2WalkTaskDefinition):
    """Shared Go2 reward/actuation with an independent deploy observation path."""

    # Deployment training receives an explicit yaw-rate command in channel 2;
    # it does not maintain Unitree's hidden target-heading state.
    heading_command_enabled = False
    height_command_enabled = True
    height_target_default = GO2_DEPLOY_HEIGHT_DEFAULT
    height_reward_scale = GO2_DEPLOY_HEIGHT_REWARD_SCALE
    height_error_tolerance = GO2_DEPLOY_HEIGHT_PENALTY_MAX
    observation_schema_version = GO2_DEPLOY_OBS_SCHEMA_VERSION
    observation_noise_scale = GO2_DEPLOY_NOISE_SCALE

    def __post_init__(self) -> None:
        super().__post_init__()
        self._deploy_noise_rng = np.random.default_rng(0)
        self._deploy_noise_level = 1.0

    def observation_noise_curriculum_spec(self) -> dict[str, Any]:
        """Return a task capability; policy iteration never enters the task."""

        return {
            "schema": "task-env-observation-noise-curriculum-v1",
            "enabled": True,
            "initial_level": 0.0,
            "final_level": 1.0,
            "peak_fraction": 0.50,
        }

    @property
    def observation_noise_level(self) -> float:
        return float(self._deploy_noise_level)

    def set_observation_noise_level(self, level: float) -> None:
        self._deploy_noise_level = float(np.clip(level, 0.0, 1.0))

    def create_observation_builder(self, compiled_scene, **_kwargs):
        del compiled_scene
        return Go2DeployObservationBuilder(
            joint_qpos_ids=self.joint_qpos_ids,
            joint_dof_ids=self.joint_dof_ids,
            base_body_id=self.base_body_id,
            command_dim=self.command_dim,
            schema_version=self.observation_schema_version,
            noise_scale=self.observation_noise_scale,
        )

    def create_observation_builder_from_state(self, view, actions, commands):
        qpos = np.asarray(view.qpos, dtype=np.float32)
        qvel = np.asarray(view.qvel, dtype=np.float32)
        _, _, base_ang, projected = _base_kinematics(qpos, qvel, view.body_xpos, self.base_body_id)
        dof_pos = qpos[..., self.joint_qpos_ids] - GO2_DEFAULT_JOINT_ANGLES
        dof_vel = qvel[..., self.joint_dof_ids]
        command_value = np.asarray(commands, dtype=np.float32)
        scaled_command = command_value[..., :3] * GO2_COMMAND_OBS_SCALE
        if self.command_dim == 4:
            scaled_command = np.concatenate((scaled_command, command_value[..., 3:4]), axis=-1)
        parts = (base_ang * 0.25, projected, scaled_command, dof_pos, dof_vel * 0.05, np.asarray(actions, dtype=np.float32))
        if qpos.ndim == 1:
            values = _uniform_noise(
                np.concatenate(parts), self._deploy_noise_rng,
                self._deploy_noise_level * self.observation_noise_scale,
            )
            return freeze_observation((("state", {"proprioception": values}),))
        values = _uniform_noise(
            np.concatenate(parts, axis=1), self._deploy_noise_rng,
            self._deploy_noise_level * self.observation_noise_scale,
        )
        return {"state": {"proprioception": values}}

    def build_device_observation(self, state):
        import torch

        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        batch_size = int(state.num_envs)
        constants = self._device_constants(qpos=qpos)
        if "deploy_noise_scale" not in constants:
            constants["deploy_noise_scale"] = torch.as_tensor(
                self.observation_noise_scale, dtype=qpos.dtype, device=qpos.device
            )
        if "body_xquat" in state.arrays and state.arrays["body_xquat"].shape[1] > self.base_body_id:
            root_quat = state.arrays["body_xquat"][:, self.base_body_id]
        else:
            root_quat = qpos[:, 3:7]
        gravity = torch.zeros_like(qvel[:, :3])
        gravity[:, 2] = -1.0
        base_ang = _torch_quat_rotate_inverse(root_quat, qvel[:, 3:6])
        projected = _torch_quat_rotate_inverse(root_quat, gravity)
        qpos_ids = constants["qpos_ids"]
        dof_ids = constants["dof_ids"]
        commands = self._device_command_tensor(batch_size=batch_size, device=qpos.device, dtype=qpos.dtype)
        actions = self._device_action_tensor(batch_size=batch_size, device=qpos.device, dtype=qpos.dtype)
        command_value = commands[..., :3] * constants["command_scale"]
        if self.command_dim == 4:
            command_value = torch.cat((command_value, commands[..., 3:4]), dim=1)
        values = torch.cat(
            (
                base_ang * 0.25,
                projected,
                command_value,
                qpos.index_select(-1, qpos_ids) - constants["default_angles"],
                qvel.index_select(-1, dof_ids) * 0.05,
                actions,
            ),
            dim=1,
        )
        values = values + (2.0 * torch.rand_like(values) - 1.0) * constants["deploy_noise_scale"] * self._deploy_noise_level
        expected_dim = 42 + self.command_dim
        if tuple(values.shape) != (batch_size, expected_dim):
            raise ValueError(f"Go2 deploy device observation must have shape ({batch_size}, {expected_dim})")
        return values


class Go2WalkDeployResetSampler(Go2WalkResetSampler):
    heading_command_enabled = False

    def sample_episode_state(self, *, compiled_scene, initial_state, rng, seed):
        state, parameters = super().sample_episode_state(
            compiled_scene=compiled_scene,
            initial_state=initial_state,
            rng=rng,
            seed=seed,
        )
        deploy_qpos = np.asarray(state.qpos, dtype=np.float32).copy()
        deploy_qpos[:7] = np.asarray((0.0, 0.0, GO2_DEPLOY_ROOT_HEIGHT, 1.0, 0.0, 0.0, 0.0), dtype=np.float32)
        state = EpisodePhysicsState(
            qpos=deploy_qpos,
            qvel=np.asarray(state.qvel, dtype=np.float32).copy(),
            qacc=np.asarray(state.qacc, dtype=np.float32).copy(),
            ctrl=np.asarray(state.ctrl, dtype=np.float32).copy(),
            act=np.asarray(state.act, dtype=np.float32).copy(),
        )
        parameters = dict(parameters)
        parameters["profile"] = "unitree_rl_gym_go2_deploy_reset_v1"
        parameters["root_position"] = [0.0, 0.0, GO2_DEPLOY_ROOT_HEIGHT]
        parameters["observation_schema"] = GO2_DEPLOY_OBS_SCHEMA_VERSION
        parameters["observation_noise_scale"] = GO2_DEPLOY_NOISE_SCALE.tolist()
        parameters["target_height"] = GO2_DEPLOY_HEIGHT_DEFAULT
        return state, parameters


class Go2WalkDeployHeightResetSampler(Go2WalkDeployResetSampler):
    """Reset sampler for the versioned 46D height-command contract."""

    def sample_episode_state(self, *, compiled_scene, initial_state, rng, seed):
        state, parameters = super().sample_episode_state(
            compiled_scene=compiled_scene, initial_state=initial_state, rng=rng, seed=seed
        )
        # Height-domain training randomizes the reset/root target in the same
        # narrow range as the fourth command.  The deployment evaluator keeps
        # its explicit test-time root height at GO2_DEPLOY_ROOT_HEIGHT.
        root_height = float(rng.uniform(GO2_DEPLOY_HEIGHT_MIN, GO2_DEPLOY_HEIGHT_MAX))
        height_qpos = np.asarray(state.qpos, dtype=np.float32).copy()
        height_qpos[2] = np.float32(root_height)
        state = EpisodePhysicsState(
            qpos=height_qpos,
            qvel=np.asarray(state.qvel, dtype=np.float32).copy(),
            qacc=np.asarray(state.qacc, dtype=np.float32).copy(),
            ctrl=np.asarray(state.ctrl, dtype=np.float32).copy(),
            act=np.asarray(state.act, dtype=np.float32).copy(),
        )
        target_height = float(rng.uniform(GO2_DEPLOY_HEIGHT_MIN, GO2_DEPLOY_HEIGHT_MAX))
        parameters = dict(parameters)
        command = np.asarray(
            (
                rng.uniform(GO2_DEPLOY_HEIGHT_VX_MIN, GO2_DEPLOY_HEIGHT_VX_MAX),
                rng.uniform(GO2_DEPLOY_HEIGHT_VY_MIN, GO2_DEPLOY_HEIGHT_VY_MAX),
                rng.uniform(-GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT, GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT),
            ),
            dtype=np.float32,
        )
        if float(np.linalg.norm(command[:2])) <= 0.2:
            command[:2] = 0.0
        command = _clip_height_deploy_command(command)
        parameters["command"] = np.concatenate(
            (command[:3], np.asarray((target_height,), dtype=np.float32))
        ).tolist()
        parameters["root_position"] = [0.0, 0.0, root_height]
        parameters["target_height"] = target_height
        parameters["observation_schema"] = GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION
        parameters["profile"] = "unitree_rl_gym_go2_deploy_height_reset_v1"
        parameters["observation_noise_scale"] = GO2_DEPLOY_HEIGHT_NOISE_SCALE.tolist()

        # Controlled initialization diagnostic: restore the historical
        # height-domain reset variation without changing the ordinary
        # go2-walk sampler.  Hips are sampled in +/-0.1 rad first, then every
        # joint is multiplied by an independent U[0.5, 1.5] scale.  The six
        # root generalized velocities use U[-0.5, 0.5]; joint velocities stay
        # zero.  This is intentionally the only reset difference for the
        # GeoPhys initialization experiment.
        randomized_qpos = np.asarray(state.qpos, dtype=np.float32).copy()
        randomized_qvel = np.asarray(state.qvel, dtype=np.float32).copy()
        refs = compiled_scene.references.agents["go2-v1"]
        joint_pose = np.asarray(GO2_DEFAULT_JOINT_ANGLES, dtype=np.float32).copy()
        joint_pose[0::3] = rng.uniform(
            GO2_HEIGHT_RESET_HIP_MIN,
            GO2_HEIGHT_RESET_HIP_MAX,
            size=4,
        ).astype(np.float32)
        joint_scale = rng.uniform(
            GO2_HEIGHT_RESET_JOINT_SCALE_MIN,
            GO2_HEIGHT_RESET_JOINT_SCALE_MAX,
            size=joint_pose.shape,
        ).astype(np.float32)
        for qpos_id, value in zip(refs.arm_qpos_ids, joint_pose * joint_scale, strict=True):
            randomized_qpos[int(qpos_id)] = np.float32(value)
        randomized_qvel[:6] = rng.uniform(
            GO2_HEIGHT_RESET_ROOT_VELOCITY_MIN,
            GO2_HEIGHT_RESET_ROOT_VELOCITY_MAX,
            size=6,
        ).astype(np.float32)
        randomized_qvel[6:] = 0.0
        state = EpisodePhysicsState(
            qpos=randomized_qpos,
            qvel=randomized_qvel,
            qacc=np.asarray(state.qacc, dtype=np.float32).copy(),
            ctrl=np.asarray(state.ctrl, dtype=np.float32).copy(),
            act=np.asarray(state.act, dtype=np.float32).copy(),
        )
        parameters["initialization_profile"] = (
            "height_randomized_joint_pose_and_root_velocity_v1"
        )
        parameters["root_velocity_range"] = [
            GO2_HEIGHT_RESET_ROOT_VELOCITY_MIN,
            GO2_HEIGHT_RESET_ROOT_VELOCITY_MAX,
        ]
        parameters["joint_random_scale"] = [
            GO2_HEIGHT_RESET_JOINT_SCALE_MIN,
            GO2_HEIGHT_RESET_JOINT_SCALE_MAX,
        ]
        parameters["hip_initial_range"] = [
            GO2_HEIGHT_RESET_HIP_MIN,
            GO2_HEIGHT_RESET_HIP_MAX,
        ]
        return state, parameters


@register_parallel_env()
@register_env()
class Go2WalkDeployEnv(BaseTaskEnv):
    uid = GO2_DEPLOY_ENV_ID
    task_uid = GO2_DEPLOY_ENV_ID
    scene_uid = GO2_SCENE_UID
    agent_uids = ("go2-v1",)
    object_uids: tuple[str, ...] = ()
    success_definition = "go2_walk_no_terminal_success_v1"

    @classmethod
    def default_config_path(cls) -> Path:
        """Share one package YAML with both the 45D and 46D registrations."""

        del cls
        return Path(__file__).with_name("default.yaml")

    @classmethod
    def default_config(cls):
        return resolve_env_config(
            task_uid=cls.task_uid,
            scene_uid=cls.scene_uid,
            agent_uids=cls.agent_uids,
            runtime={
                "physics_dt": GO2_PHYSICS_DT,
                "control_substeps": GO2_CONTROL_SUBSTEPS,
                "batch_physics_layout": "static_template",
                "static_template": {
                    "profile": "articulated_fused_ground_contact_v1",
                    "kinematics_backend": "taichi",
                    "contact_precision": "f32",
                    "cuda_graph": True,
                    "contact": {
                        "response_backend": "active_slot_cholesky_f32_v1",
                    },
                },
                "enable_ground_contact": True,
                "enable_domain_boundary_contact": False,
            },
            action={"rsl_action_profile": "unitree_go2_reference"},
            observation={"schema_version": GO2_DEPLOY_OBS_SCHEMA_VERSION, "include_privileged_state": False},
            episode={"horizon": GO2_HORIZON},
            success_definition=cls.success_definition,
        )

    def placement_notes(self) -> tuple[str, ...]:
        return ("Deployment Go2 uses the 45-value real-robot actor layout, z=0.34 reset, and the Unitree training noise vector.", "Use the deterministic MuJoCo deployment evaluator for sensor-only rollout.")

    def reference_profile(self) -> dict[str, Any]:
        return {
            "profile_id": "task-env-go2-walk-deploy-reference-v1",
            "source": "temp_outputs/unitree_rl_gym + article deployment contract",
            "canonical_xml_sha256": canonical_xml_digest(),
            "observation_schema": GO2_DEPLOY_OBS_SCHEMA_VERSION,
            "observation_dim": 45,
            "command_observation_scale": GO2_COMMAND_OBS_SCALE.tolist(),
            "root_height": GO2_DEPLOY_ROOT_HEIGHT,
            "observation_noise": True,
            "action_schema": GO2_ACTION_CONTRACT.schema_id,
            "action_dim": 12,
            "physics": {
                "physics_dt": GO2_PHYSICS_DT,
                "control_substeps": GO2_CONTROL_SUBSTEPS,
                "policy_dt": GO2_POLICY_DT,
            },
        }

    def create_scene_composer(self):
        return Go2WalkSceneComposer()

    def create_reset_sampler(self):
        return Go2WalkDeployResetSampler()

    def create_task_definition(self, compiled_scene):
        base = Go2WalkEnv.create_task_definition(self, compiled_scene)
        values = {field.name: getattr(base, field.name) for field in fields(Go2WalkTaskDefinition)}
        return Go2WalkDeployTaskDefinition(**values)


class Go2WalkDeployHeightTaskDefinition(Go2WalkDeployTaskDefinition):
    """46D deploy task: the fourth command is a bounded height target."""

    command_dim = 4
    # height gait reward 优先使用足部 geometry；provider 不提供 geom_xpos 时，
    # 任务已有 body_xpos fallback。
    device_state_optional_fields: ClassVar[tuple[str, ...]] = ("geom_xpos",)
    roll_orientation_weight = GO2_DEPLOY_ROLL_ORIENTATION_WEIGHT
    pitch_orientation_weight = GO2_DEPLOY_PITCH_ORIENTATION_WEIGHT
    termination_grace_steps = GO2_HEIGHT_TERMINATION_GRACE_STEPS
    observation_schema_version = GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION
    observation_noise_scale = GO2_DEPLOY_HEIGHT_NOISE_SCALE

    @staticmethod
    def _sample_command(rng: np.random.Generator) -> np.ndarray:
        """Sample the first three commands under the height-task limits."""

        command = np.asarray(
            (
                rng.uniform(GO2_DEPLOY_HEIGHT_VX_MIN, GO2_DEPLOY_HEIGHT_VX_MAX),
                rng.uniform(GO2_DEPLOY_HEIGHT_VY_MIN, GO2_DEPLOY_HEIGHT_VY_MAX),
                rng.uniform(
                    -GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
                    GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
                ),
            ),
            dtype=np.float32,
        )
        if float(np.linalg.norm(command[:2])) <= 0.2:
            command[:2] = 0.0
        return command

    def _sample_task_command(self, rng: np.random.Generator) -> np.ndarray:
        command = self._sample_command(rng)
        return np.concatenate(
            (
                command,
                np.asarray(
                    (rng.uniform(GO2_DEPLOY_HEIGHT_MIN, GO2_DEPLOY_HEIGHT_MAX),),
                    dtype=np.float32,
                ),
            )
        )

    @staticmethod
    def _heading_yaw_command(root_quat, target_heading):
        """Keep heading-derived yaw within the 46D command contract."""

        import torch

        command = Go2WalkTaskDefinition._heading_yaw_command(root_quat, target_heading)
        return torch.clamp(
            command,
            -GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
            GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
        )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._height_swing_start_positions = None
        self._device_height_swing_start_positions = None
        self._last_foot_positions = None
        self._device_last_foot_positions = None

    def _host_foot_positions(self, view) -> np.ndarray:
        """Return four foot positions, preferring named foot geoms."""

        try:
            geom_xpos = np.asarray(view.get("geom_xpos"), dtype=np.float32)
        except KeyError:
            geom_xpos = None
        if geom_xpos is not None and geom_xpos.shape[-2] > int(np.max(self.foot_geom_ids)):
            return np.asarray(geom_xpos[..., self.foot_geom_ids, :], dtype=np.float32)
        if view.body_xpos is None:
            raise ValueError("height-deploy gait reward requires foot positions")
        body_xpos = np.asarray(view.body_xpos, dtype=np.float32)
        return np.asarray(body_xpos[..., self.foot_body_ids, :], dtype=np.float32)

    def _reward_foot_positions(self, view):
        return self._host_foot_positions(view)

    def _device_foot_positions(self, state, constants):
        geom_xpos = state.arrays.get("geom_xpos")
        geom_ids = constants["foot_geom_ids"]
        # Geometry ids are compiled scene constants.  Resolve their maximum
        # on the host once per task object; never synchronize a CUDA tensor in
        # this policy-tick helper just to check a static index.
        if (
            geom_xpos is not None
            and len(self.foot_geom_ids)
            and int(np.max(self.foot_geom_ids)) < geom_xpos.shape[1]
        ):
            return geom_xpos.index_select(1, geom_ids)
        body_xpos = state.arrays.get("body_xpos")
        if body_xpos is None:
            raise ValueError("height-deploy device gait reward requires foot positions")
        return body_xpos.index_select(1, constants["foot_body_ids"])

    @staticmethod
    def _command_active(commands) -> Any:
        import torch

        if torch.is_tensor(commands):
            return torch.linalg.vector_norm(
                commands[..., :2], dim=-1
            ) > GO2_HEIGHT_MOVING_COMMAND_THRESHOLD
        return np.linalg.norm(np.asarray(commands)[..., :2], axis=-1) > (
            GO2_HEIGHT_MOVING_COMMAND_THRESHOLD
        )

    @staticmethod
    def _foot_contact_host(
        task,
        contact_ground,
        contact_body,
        contact_geom,
        shape,
    ) -> np.ndarray:
        contact_matrix = task._contact_matrix(
            contact_ground,
            contact_body,
            body_ids=np.concatenate((task.foot_body_ids, task.penalized_body_ids)),
            shape=shape,
        )
        geom_matrix = task._geom_contact_matrix(
            contact_geom,
            geom_ids=task.foot_geom_ids,
            shape=shape,
        )
        return (
            geom_matrix
            if geom_matrix is not None
            else contact_matrix[..., task.foot_body_ids]
        )

    def _gait_terms_host(
        self,
        *,
        commands,
        feet_contact,
        foot_positions,
    ) -> dict[str, np.ndarray]:
        """Compute height-task gait shaping and update host-side gait state."""

        contacts = np.asarray(feet_contact, dtype=np.bool_)
        positions = np.asarray(foot_positions, dtype=np.float32)
        if self._height_swing_start_positions is None or self._height_swing_start_positions.shape != positions.shape:
            self._height_swing_start_positions = positions.copy()
        swing_start = self._height_swing_start_positions
        if swing_start is None or swing_start.shape != positions.shape:
            swing_start = positions.copy()
            self._height_swing_start_positions = swing_start
        previous_contacts = (
            np.zeros_like(contacts)
            if self._last_contacts is None or self._last_contacts.shape != contacts.shape
            else self._last_contacts
        )
        air_time = (
            np.zeros_like(positions[..., 0], dtype=np.float32)
            if self._feet_air_time is None or self._feet_air_time.shape != contacts.shape
            else self._feet_air_time
        )
        command_active = self._command_active(commands)
        contact_filt = np.logical_or(contacts, previous_contacts)
        first_contact = np.logical_and(air_time > 0.0, contact_filt)
        air_time += np.float32(GO2_POLICY_DT)
        air_reward = np.sum((air_time - np.float32(0.5)) * first_contact, axis=-1)
        air_reward *= command_active

        takeoff = np.logical_and(previous_contacts, np.logical_not(contacts))
        swing_start[takeoff] = positions[takeoff]
        landing = np.logical_and(
            np.logical_and(np.logical_not(previous_contacts), contacts),
            air_time > np.float32(GO2_POLICY_DT * 1.5),
        )
        stride = np.linalg.norm(positions[..., :2] - swing_start[..., :2], axis=-1)
        effective_swing = np.sum(
            np.minimum(stride, np.float32(GO2_HEIGHT_EFFECTIVE_SWING_MAX)) * landing,
            axis=-1,
        ) * command_active
        clearance_deficit = np.maximum(
            np.float32(GO2_HEIGHT_FOOT_CLEARANCE_TARGET) - positions[..., 2],
            0.0,
        )
        clearance_penalty = np.sum(clearance_deficit * np.logical_not(contacts), axis=-1)
        clearance_penalty *= command_active
        self._feet_air_time = air_time * np.logical_not(contact_filt)
        self._last_contacts = contacts.copy()
        return {
            "feet_air_time": np.asarray(
                GO2_HEIGHT_FEET_AIR_TIME_SCALE * air_reward * GO2_POLICY_DT,
                dtype=np.float32,
            ),
            "foot_clearance": np.asarray(
                -GO2_HEIGHT_FOOT_CLEARANCE_SCALE * clearance_penalty * GO2_POLICY_DT,
                dtype=np.float32,
            ),
            "effective_swing": np.asarray(
                GO2_HEIGHT_EFFECTIVE_SWING_SCALE * effective_swing * GO2_POLICY_DT,
                dtype=np.float32,
            ),
        }

    def _device_foot_contacts(self, state, constants):
        import torch

        batch_size = int(state.num_envs)
        contact_matrix = self._device_contact_matrix(state, batch_size=batch_size)
        geom_contact = self._device_geom_contact(
            state,
            constants["foot_geom_ids"],
            batch_size=batch_size,
        )
        if geom_contact is not None:
            return geom_contact
        foot_ids = constants["foot_body_ids"]
        valid = foot_ids[foot_ids < contact_matrix.shape[-1]]
        result = torch.zeros(
            (batch_size, len(self.foot_body_ids)),
            dtype=torch.bool,
            device=state.device,
        )
        if valid.numel():
            result[..., : valid.numel()] = contact_matrix.index_select(-1, valid)
        return result

    def _gait_terms_device(self, *, commands, feet_contact, foot_positions):
        import torch

        contacts = feet_contact.to(torch.bool)
        positions = foot_positions
        batch_size = int(positions.shape[0])
        expected = (batch_size, len(self.foot_body_ids), 3)
        if tuple(positions.shape) != expected:
            raise ValueError(
                "height-deploy device foot positions must have shape "
                f"{expected}, got {tuple(positions.shape)}"
            )
        if (
            self._device_height_swing_start_positions is None
            or tuple(self._device_height_swing_start_positions.shape) != expected
            or self._device_height_swing_start_positions.device != positions.device
            or self._device_height_swing_start_positions.dtype != positions.dtype
        ):
            self._device_height_swing_start_positions = torch.empty_like(positions)
            self._device_height_swing_start_positions.copy_(positions.detach())
        swing_start = self._device_height_swing_start_positions
        if swing_start is None or tuple(swing_start.shape) != expected:
            self._device_height_swing_start_positions = torch.empty_like(positions)
            self._device_height_swing_start_positions.copy_(positions.detach())
            swing_start = self._device_height_swing_start_positions
        previous_contacts = (
            torch.zeros_like(contacts)
            if self._device_last_contacts is None
            or tuple(self._device_last_contacts.shape) != contacts.shape
            else self._device_last_contacts
        )
        if (
            self._device_feet_air_time is None
            or tuple(self._device_feet_air_time.shape) != contacts.shape
            or self._device_feet_air_time.device != positions.device
            or self._device_feet_air_time.dtype != positions.dtype
        ):
            self._device_feet_air_time = torch.zeros(
                contacts.shape,
                dtype=positions.dtype,
                device=positions.device,
            )
        air_time = self._device_feet_air_time
        command_active = self._command_active(commands)
        contact_filt = torch.logical_or(contacts, previous_contacts)
        first_contact = torch.logical_and(air_time > 0.0, contact_filt)
        air_time.add_(GO2_POLICY_DT)
        air_reward = torch.sum((air_time - 0.5) * first_contact, dim=-1)
        air_reward = air_reward * command_active

        takeoff = torch.logical_and(previous_contacts, torch.logical_not(contacts))
        swing_start[takeoff] = positions[takeoff].detach()
        landing = torch.logical_and(
            torch.logical_and(torch.logical_not(previous_contacts), contacts),
            air_time > GO2_POLICY_DT * 1.5,
        )
        stride = torch.linalg.vector_norm(
            positions[..., :2] - swing_start[..., :2], dim=-1
        )
        effective_swing = torch.sum(
            torch.minimum(
                stride,
                torch.as_tensor(
                    GO2_HEIGHT_EFFECTIVE_SWING_MAX,
                    dtype=positions.dtype,
                    device=positions.device,
                ),
            ) * landing,
            dim=-1,
        ) * command_active
        clearance_deficit = torch.relu(
            torch.as_tensor(
                GO2_HEIGHT_FOOT_CLEARANCE_TARGET,
                dtype=positions.dtype,
                device=positions.device,
            )
            - positions[..., 2]
        )
        clearance_penalty = torch.sum(
            clearance_deficit * torch.logical_not(contacts), dim=-1
        ) * command_active
        self._device_feet_air_time.mul_(torch.logical_not(contact_filt))
        if self._device_last_contacts is None or tuple(self._device_last_contacts.shape) != contacts.shape:
            self._device_last_contacts = torch.zeros_like(contacts)
        self._device_last_contacts.copy_(contacts)
        dt = torch.as_tensor(GO2_POLICY_DT, dtype=positions.dtype, device=positions.device)
        return {
            "feet_air_time": GO2_HEIGHT_FEET_AIR_TIME_SCALE * air_reward * dt,
            "foot_clearance": -GO2_HEIGHT_FOOT_CLEARANCE_SCALE * clearance_penalty * dt,
            "effective_swing": GO2_HEIGHT_EFFECTIVE_SWING_SCALE * effective_swing * dt,
        }

    def reset_device(
        self,
        *,
        state,
        reset_mask,
        selection=None,
    ) -> None:
        """Reset specialized foot-position history for selected worlds."""

        import torch

        super().reset_device(state=state, reset_mask=reset_mask, selection=selection)
        qpos = state.arrays["qpos"]
        positions = self._device_foot_positions(
            state, self._device_constants(qpos=qpos)
        )
        mask = reset_mask.to(device=positions.device, dtype=torch.bool)
        expected = tuple(positions.shape)
        if (
            self._device_height_swing_start_positions is None
            or tuple(self._device_height_swing_start_positions.shape) != expected
            or self._device_height_swing_start_positions.device != positions.device
            or self._device_height_swing_start_positions.dtype != positions.dtype
        ):
            self._device_height_swing_start_positions = torch.empty_like(positions)
            self._device_height_swing_start_positions.copy_(positions.detach())
        else:
            self._device_height_swing_start_positions[mask].copy_(positions[mask].detach())
        if (
            self._device_last_foot_positions is None
            or tuple(self._device_last_foot_positions.shape) != expected
            or self._device_last_foot_positions.device != positions.device
            or self._device_last_foot_positions.dtype != positions.dtype
        ):
            self._device_last_foot_positions = torch.empty_like(positions)
            self._device_last_foot_positions.copy_(positions.detach())
        else:
            self._device_last_foot_positions[mask].copy_(positions[mask].detach())

    def reset(
        self,
        snapshot=None,
        *,
        state=None,
        reset_mask=None,
    ):
        """Reset host-side specialized foot-position history per slot."""

        result = super().reset(snapshot, state=state, reset_mask=reset_mask)
        if state is None:
            self._height_swing_start_positions = None
            self._last_foot_positions = None
            return result
        view = as_task_state_view(state)
        positions = self._host_foot_positions(view)
        if view.is_batch:
            mask = (
                np.ones(view.batch_size, dtype=np.bool_)
                if reset_mask is None
                else np.asarray(reset_mask, dtype=np.bool_)
            )
            if mask.shape != (view.batch_size,):
                raise ValueError("height-deploy reset_mask must have shape (B,)")
            if (
                self._height_swing_start_positions is None
                or self._height_swing_start_positions.shape != positions.shape
            ):
                self._height_swing_start_positions = positions.copy()
            else:
                self._height_swing_start_positions[mask] = positions[mask]
            if (
                self._last_foot_positions is None
                or self._last_foot_positions.shape != positions.shape
            ):
                self._last_foot_positions = positions.copy()
            else:
                self._last_foot_positions[mask] = positions[mask]
        else:
            self._height_swing_start_positions = positions.copy()
            self._last_foot_positions = positions.copy()
        return result

    def _update_heading_commands(self, qpos: np.ndarray, body_xquat: np.ndarray | None) -> None:
        super()._update_heading_commands(qpos, body_xquat)
        if self._commands is not None:
            self._commands[...] = _clip_height_deploy_command(self._commands)

    def privileged_observation_manifest(self) -> dict[str, Any]:
        """Declare simulator-only velocity information for the PPO critic.

        The actor remains the deployable 46D sensor contract.  This field is
        intentionally exposed through the learner profile as a critic input
        only and is never part of ``build_observation``.
        """

        return {
            "schema": "task-env-go2-height-deploy-critic-privileged-v1",
            "source": "base_lin_vel_body",
            "shape": [3],
            "scale": 2.0,
            "deployable": False,
        }

    def build_privileged_observation(self, state) -> np.ndarray:
        """Return scaled body-frame base linear velocity for the critic."""

        view = as_task_state_view(state)
        _, base_lin, _, _ = _base_kinematics(
            np.asarray(view.qpos, dtype=np.float32),
            np.asarray(view.qvel, dtype=np.float32),
            view.body_xpos,
            self.base_body_id,
        )
        value = np.asarray(base_lin * np.float32(2.0), dtype=np.float32)
        if value.ndim != 2 or value.shape[1:] != (3,):
            raise ValueError(
                "height-deploy privileged observation must have shape (B, 3)"
            )
        return value

    def build_device_privileged_observation(self, state):
        """Device-native twin of :meth:`build_privileged_observation`."""

        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        body_xquat = state.arrays.get("body_xquat")
        if body_xquat is not None and body_xquat.shape[1] > self.base_body_id:
            root_quat = body_xquat[:, self.base_body_id]
        else:
            root_quat = qpos[:, 3:7]
        value = _torch_quat_rotate_inverse(root_quat, qvel[:, :3]) * 2.0
        if tuple(value.shape) != (int(state.num_envs), 3):
            raise ValueError(
                "height-deploy device privileged observation must have shape (B, 3)"
            )
        return value

    def on_reset_sample(self, *, parameters, seeds, reset_mask: np.ndarray) -> None:
        super().on_reset_sample(
            parameters=parameters,
            seeds=seeds,
            reset_mask=reset_mask,
        )
        if self._commands is not None:
            self._commands[...] = _clip_height_deploy_command(self._commands)
            # 父类已上传 reset 行；重建缓存以保证裁剪后的 host command 生效。
            self._device_commands = None

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
        """Evaluate the height-deploy Unitree/Genesis reward on the host path.

        This is intentionally a task-local reward definition.  Every enabled
        term is multiplied by one policy ``dt`` and the final sum is clipped
        at zero, matching the requested Unitree reward contract.  The public
        host state does not expose rigid-body velocities, so ``feet_slip`` uses
        a reset-safe finite difference of task-owned foot positions.
        """

        del roll, pitch
        if base_height is None:
            raise ValueError("height-deploy reward requires base_height")
        lin = np.asarray(lin, dtype=np.float32)
        ang = np.asarray(ang, dtype=np.float32)
        gravity = (
            np.zeros_like(lin, dtype=np.float32)
            if gravity is None
            else np.asarray(gravity, dtype=np.float32)
        )
        torque = (
            np.zeros_like(qvel[..., self.joint_dof_ids], dtype=np.float32)
            if torque is None
            else np.asarray(torque, dtype=np.float32)
        )
        action = np.asarray(action, dtype=np.float32)
        previous = np.asarray(previous, dtype=np.float32)
        qpos = np.asarray(qpos, dtype=np.float32)
        qvel = np.asarray(qvel, dtype=np.float32)
        commands = _clip_height_deploy_command(np.asarray(commands, dtype=np.float32))
        base_height = np.asarray(base_height, dtype=np.float32)
        dof_pos = qpos[..., self.joint_qpos_ids]
        dof_vel = qvel[..., self.joint_dof_ids]
        previous_vel = (
            dof_vel
            if previous_vel is None
            else np.asarray(previous_vel, dtype=np.float32)
        )
        default = np.asarray(GO2_DEFAULT_JOINT_ANGLES, dtype=np.float32)
        dt = np.float32(GO2_POLICY_DT)
        shape = action.shape[:-1]

        contact_matrix = self._contact_matrix(
            contact_ground,
            contact_body,
            body_ids=np.concatenate((self.foot_body_ids, self.penalized_body_ids)),
            shape=shape,
        )
        feet_geom_contact = self._geom_contact_matrix(
            contact_geom,
            geom_ids=self.foot_geom_ids,
            shape=shape,
        )
        feet_contact = (
            feet_geom_contact
            if feet_geom_contact is not None
            else contact_matrix[..., self.foot_body_ids]
        )
        previous_contacts = (
            np.zeros_like(feet_contact, dtype=np.bool_)
            if self._last_contacts is None
            or self._last_contacts.shape != feet_contact.shape
            else self._last_contacts
        )
        if self._feet_air_time is None or self._feet_air_time.shape != feet_contact.shape:
            self._feet_air_time = np.zeros_like(feet_contact, dtype=np.float32)
        contact_filt = np.logical_or(feet_contact, previous_contacts)
        first_contact = np.logical_and(self._feet_air_time > 0.0, contact_filt)
        self._feet_air_time += dt
        feet_air_time = np.sum(
            (self._feet_air_time - np.float32(0.25)) * first_contact,
            axis=-1,
        )
        feet_air_time *= np.linalg.norm(commands[..., :2], axis=-1) > 0.1
        self._feet_air_time *= np.logical_not(contact_filt)
        self._last_contacts = np.asarray(feet_contact, dtype=np.bool_).copy()

        penalized_geom_contact = self._geom_contact_matrix(
            contact_geom,
            geom_ids=self.penalized_geom_ids,
            shape=shape,
        )
        collision_source = (
            penalized_geom_contact
            if penalized_geom_contact is not None
            else contact_matrix[..., self.penalized_body_ids]
        )
        collision = np.sum(np.asarray(collision_source, dtype=np.float32), axis=-1)

        # The host state has no rigid-body velocity array.  Use the current and
        # previous policy-tick foot positions as the documented approximation;
        # reset() seeds this cache so reset jumps are never treated as slip.
        if foot_positions is None:
            foot_slip = np.zeros(shape, dtype=np.float32)
        else:
            current_foot_positions = np.asarray(foot_positions, dtype=np.float32)
            previous_foot_positions = getattr(self, "_last_foot_positions", None)
            if (
                previous_foot_positions is None
                or previous_foot_positions.shape != current_foot_positions.shape
            ):
                foot_velocity = np.zeros_like(current_foot_positions)
            else:
                foot_velocity = (
                    current_foot_positions - previous_foot_positions
                ) / dt
            self._last_foot_positions = current_foot_positions.copy()
            slip_sq = np.minimum(
                np.sum(np.square(foot_velocity[..., :2]), axis=-1),
                np.float32(1.0),
            )
            foot_slip = np.sum(slip_sq * feet_contact, axis=-1)
        command_active = np.linalg.norm(commands[..., :2], axis=-1) < 0.1
        terms = {
            "tracking_lin_vel": np.exp(
                -np.sum((commands[..., :2] - lin[..., :2]) ** 2, axis=-1) / 0.25
            ) * np.float32(GO2_HEIGHT_REWARD_SCALES["tracking_lin_vel"]) * dt,
            "tracking_ang_vel": np.exp(
                -((commands[..., 2] - ang[..., 2]) ** 2) / 0.25
            ) * np.float32(GO2_HEIGHT_REWARD_SCALES["tracking_ang_vel"]) * dt,
            "lin_vel_z": np.square(lin[..., 2])
            * np.float32(GO2_HEIGHT_REWARD_SCALES["lin_vel_z"])
            * dt,
            "ang_vel_xy": np.sum(np.square(ang[..., :2]), axis=-1)
            * np.float32(GO2_HEIGHT_REWARD_SCALES["ang_vel_xy"])
            * dt,
            "orientation": np.sum(np.square(gravity[..., :2]), axis=-1)
            * np.float32(GO2_HEIGHT_REWARD_SCALES["orientation"])
            * dt,
            "torques": np.sum(np.square(torque), axis=-1)
            * np.float32(GO2_HEIGHT_REWARD_SCALES["torques"])
            * dt,
            "dof_acc": np.sum(np.square((previous_vel - dof_vel) / dt), axis=-1)
            * np.float32(GO2_HEIGHT_REWARD_SCALES["dof_acc"])
            * dt,
            "base_height": np.square(base_height - np.float32(0.34))
            * np.float32(GO2_HEIGHT_REWARD_SCALES["base_height"])
            * dt,
            "feet_air_time": feet_air_time
            * np.float32(GO2_HEIGHT_REWARD_SCALES["feet_air_time"])
            * dt,
            "collision": collision
            * np.float32(GO2_HEIGHT_REWARD_SCALES["collision"])
            * dt,
            "action_rate": np.sum(np.square(previous - action), axis=-1)
            * np.float32(GO2_HEIGHT_REWARD_SCALES["action_rate"])
            * dt,
            "stand_still": np.sum(np.abs(dof_pos - default), axis=-1)
            * command_active.astype(np.float32)
            * np.float32(GO2_HEIGHT_REWARD_SCALES["stand_still"])
            * dt,
            "dof_pos_limits": self._dof_pos_limit_penalty(dof_pos)
            * np.float32(GO2_HEIGHT_REWARD_SCALES["dof_pos_limits"])
            * dt,
            "feet_slip": foot_slip
            * np.float32(GO2_HEIGHT_REWARD_SCALES["feet_slip"])
            * dt,
            "termination": np.zeros(shape, dtype=np.float32),
            "dof_vel": np.zeros(shape, dtype=np.float32),
            "feet_stumble": np.zeros(shape, dtype=np.float32),
        }
        total = np.sum(np.stack(tuple(terms.values()), axis=0), axis=0)
        return np.clip(np.asarray(total, dtype=np.float32), a_min=0.0, a_max=None), terms

    def evaluate_device(self, *, state, action, elapsed_steps=None, previous_state=None):
        """Evaluate the 46D Unitree/Genesis reward without device readback.

        The projected gravity vector is used for ``orientation``; this keeps
        the body level without penalizing the world gravity vector itself.
        Linear motion is considered active only when the command magnitude is
        greater than ``0.1``.  The host and device paths intentionally keep
        ``feet_slip`` at zero until direct foot velocities are part of the
        public device-state contract.
        """

        import torch

        del elapsed_steps, previous_state
        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        action = action if hasattr(action, "device") else torch.as_tensor(action, device=state.device)
        batch_size = int(state.num_envs)
        constants = self._device_constants(qpos=qpos)
        if (
            self._device_command_steps is None
            or self._device_command_steps.shape != (batch_size,)
        ):
            self._device_command_steps = np.zeros(batch_size, dtype=np.int32)
        self._device_command_steps += 1
        self._maybe_resample_commands(self._device_command_steps, batch_size)

        body_xquat = state.arrays.get("body_xquat")
        if body_xquat is not None and body_xquat.shape[1] > self.base_body_id:
            root_quat = body_xquat[:, self.base_body_id]
        else:
            root_quat = qpos[:, 3:7]
        world_gravity = torch.zeros_like(qvel[:, :3])
        world_gravity[:, 2] = -1.0
        lin = _torch_quat_rotate_inverse(root_quat, qvel[:, :3])
        ang = _torch_quat_rotate_inverse(root_quat, qvel[:, 3:6])
        projected_gravity = _torch_quat_rotate_inverse(root_quat, world_gravity)
        commands = self._device_update_heading_command(
            qpos=qpos, root_quat=root_quat, batch_size=batch_size
        )
        commands[..., :2].clamp_(
            -GO2_DEPLOY_HEIGHT_LINEAR_COMMAND_LIMIT,
            GO2_DEPLOY_HEIGHT_LINEAR_COMMAND_LIMIT,
        )
        commands[..., 2].clamp_(
            -GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
            GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
        )
        body_xpos = state.arrays.get("body_xpos")
        if body_xpos is not None and body_xpos.shape[1] > self.base_body_id:
            base_height = body_xpos[:, self.base_body_id, 2]
        else:
            base_height = qpos[:, 2]
        dof_pos = qpos.index_select(-1, constants["qpos_ids"])
        dof_vel = qvel.index_select(-1, constants["dof_ids"])
        default = constants["default_angles"]
        target = default + torch.as_tensor(0.25, dtype=qpos.dtype, device=qpos.device) * action
        torque = constants["kp"] * (target - dof_pos) - constants["kd"] * dof_vel
        ctrl_limits = constants["ctrl_limits"]
        torque = torch.clamp(torque, ctrl_limits[:, 0], ctrl_limits[:, 1])
        previous = self._device_action_tensor(
            batch_size=batch_size, device=qpos.device, dtype=qpos.dtype
        )
        if (
            self._device_last_dof_vel is None
            or tuple(self._device_last_dof_vel.shape) != tuple(dof_vel.shape)
            or self._device_last_dof_vel.device != dof_vel.device
            or self._device_last_dof_vel.dtype != dof_vel.dtype
        ):
            host_previous_vel = np.asarray(
                getattr(self, "_last_dof_vel", np.zeros((batch_size, 12), dtype=np.float32)),
                dtype=np.float32,
            )
            if host_previous_vel.shape == (batch_size, 12):
                previous_vel = torch.as_tensor(
                    host_previous_vel, dtype=qpos.dtype, device=qpos.device
                )
            else:
                previous_vel = dof_vel.detach().clone()
        else:
            previous_vel = self._device_last_dof_vel
        dt = torch.as_tensor(GO2_POLICY_DT, dtype=qpos.dtype, device=qpos.device)
        command_magnitude = torch.linalg.vector_norm(commands[..., :2], dim=-1)
        moving = command_magnitude > 0.1
        standing = ~moving

        terms = {
            "tracking_lin_vel": torch.exp(
                -torch.sum((commands[..., :2] - lin[..., :2]) ** 2, dim=-1) / 0.25
            ) * GO2_HEIGHT_REWARD_SCALES["tracking_lin_vel"] * dt,
            "tracking_ang_vel": torch.exp(
                -((commands[..., 2] - ang[..., 2]) ** 2) / 0.25
            ) * GO2_HEIGHT_REWARD_SCALES["tracking_ang_vel"] * dt,
            "lin_vel_z": lin[..., 2].square() * GO2_HEIGHT_REWARD_SCALES["lin_vel_z"] * dt,
            "ang_vel_xy": torch.sum(ang[..., :2].square(), dim=-1)
            * GO2_HEIGHT_REWARD_SCALES["ang_vel_xy"] * dt,
            "orientation": torch.sum(projected_gravity[..., :2].square(), dim=-1)
            * GO2_HEIGHT_REWARD_SCALES["orientation"] * dt,
            "torques": torch.sum(torque.square(), dim=-1)
            * GO2_HEIGHT_REWARD_SCALES["torques"] * dt,
            "dof_acc": torch.sum(((previous_vel - dof_vel) / dt).square(), dim=-1)
            * GO2_HEIGHT_REWARD_SCALES["dof_acc"] * dt,
            "base_height": (base_height - 0.34).square()
            * GO2_HEIGHT_REWARD_SCALES["base_height"] * dt,
            "action_rate": torch.sum((previous - action).square(), dim=-1)
            * GO2_HEIGHT_REWARD_SCALES["action_rate"] * dt,
            "stand_still": torch.sum(torch.abs(dof_pos - default), dim=-1)
            * standing.to(qpos.dtype)
            * GO2_HEIGHT_REWARD_SCALES["stand_still"] * dt,
            "dof_pos_limits": self._device_dof_limit_penalty(
                dof_pos, constants=constants
            ) * GO2_HEIGHT_REWARD_SCALES["dof_pos_limits"] * dt,
            "termination": torch.zeros(
                (batch_size,), dtype=qpos.dtype, device=qpos.device
            ),
            "dof_vel": torch.zeros(
                (batch_size,), dtype=qpos.dtype, device=qpos.device
            ),
            "feet_stumble": torch.zeros(
                (batch_size,), dtype=qpos.dtype, device=qpos.device
            ),
        }

        contact_matrix = self._device_contact_matrix(state, batch_size=batch_size)
        feet_contact = self._device_foot_contacts(state, constants)
        previous_contacts = (
            torch.zeros_like(feet_contact)
            if self._device_last_contacts is None
            or tuple(self._device_last_contacts.shape) != tuple(feet_contact.shape)
            else self._device_last_contacts
        )
        if (
            self._device_feet_air_time is None
            or tuple(self._device_feet_air_time.shape) != tuple(feet_contact.shape)
            or self._device_feet_air_time.device != qpos.device
            or self._device_feet_air_time.dtype != qpos.dtype
        ):
            self._device_feet_air_time = torch.zeros(
                tuple(feet_contact.shape), dtype=qpos.dtype, device=qpos.device
            )
        contact_filt = torch.logical_or(feet_contact, previous_contacts)
        first_contact = torch.logical_and(
            self._device_feet_air_time > 0.0, contact_filt
        )
        self._device_feet_air_time.add_(dt)
        air_time_reward = torch.sum(
            (self._device_feet_air_time - 0.25) * first_contact, dim=-1
        ) * moving.to(qpos.dtype)
        self._device_feet_air_time.mul_(~contact_filt)
        if (
            self._device_last_contacts is None
            or tuple(self._device_last_contacts.shape) != tuple(feet_contact.shape)
        ):
            self._device_last_contacts = torch.zeros_like(feet_contact)
        self._device_last_contacts.copy_(feet_contact)
        terms["feet_air_time"] = (
            air_time_reward * GO2_HEIGHT_REWARD_SCALES["feet_air_time"] * dt
        )

        penalized_geom_contact = self._device_geom_contact(
            state, constants["penalized_geom_ids"], batch_size=batch_size
        )
        if penalized_geom_contact is not None:
            collision_source = penalized_geom_contact
        else:
            penalized_ids = constants["penalized_body_ids"]
            valid_penalized = penalized_ids[penalized_ids < contact_matrix.shape[-1]]
            collision_source = (
                contact_matrix.index_select(-1, valid_penalized)
                if valid_penalized.numel()
                else torch.zeros(
                    (batch_size, 0), dtype=torch.bool, device=qpos.device
                )
            )
        collision = collision_source.to(qpos.dtype).sum(dim=-1)
        terms["collision"] = collision * GO2_HEIGHT_REWARD_SCALES["collision"] * dt
        # Direct foot velocities are not currently part of the device-state
        # contract.  Keep this term exactly zero rather than differentiating
        # positions and introducing a reset/latency-dependent approximation.
        terms["feet_slip"] = torch.zeros(
            (batch_size,), dtype=qpos.dtype, device=qpos.device
        )
        reward = torch.clamp(torch.stack(tuple(terms.values()), dim=0).sum(dim=0), min=0.0)

        w, x, y, z = [root_quat[..., index] for index in range(4)]
        roll = torch.atan2(
            2.0 * (w * x + y * z),
            1.0 - 2.0 * (x * x + y * y),
        )
        pitch = torch.asin(torch.clamp(2.0 * (w * y - z * x), -1.0, 1.0))
        fall = (torch.abs(roll) > GO2_TERMINATION_ANGLE) | (
            torch.abs(pitch) > GO2_TERMINATION_ANGLE
        )
        base_contact = self._device_body_contact(
            state, constants["base_body_ids"], batch_size=batch_size
        )
        if (
            self._device_last_actions is None
            or tuple(self._device_last_actions.shape) != tuple(action.shape)
            or self._device_last_actions.device != action.device
            or self._device_last_actions.dtype != action.dtype
        ):
            self._device_last_actions = torch.empty_like(action)
        self._device_last_actions.copy_(action.detach())
        current_dof_vel = dof_vel.detach()
        if (
            self._device_last_dof_vel is None
            or tuple(self._device_last_dof_vel.shape) != tuple(current_dof_vel.shape)
            or self._device_last_dof_vel.device != current_dof_vel.device
            or self._device_last_dof_vel.dtype != current_dof_vel.dtype
        ):
            self._device_last_dof_vel = torch.empty_like(current_dof_vel)
        self._device_last_dof_vel.copy_(current_dof_vel)
        if self._device_elapsed is None or tuple(self._device_elapsed.shape) != (batch_size,):
            self._device_elapsed = torch.zeros((batch_size,), dtype=torch.int32, device=qpos.device)
        elif self._device_elapsed.device != qpos.device:
            self._device_elapsed = torch.zeros((batch_size,), dtype=torch.int32, device=qpos.device)
        self._device_elapsed.add_(1)
        return {
            "reward": reward,
            "terminated": fall | base_contact,
            "truncated": self._device_elapsed >= GO2_HORIZON,
            "infos": None,
            "metrics": {
                "base_height": base_height,
                "roll": roll,
                "pitch": pitch,
                "fall": fall,
                "base_contact": base_contact,
            },
            "reward_terms": terms,
        }

    # The active 46D contract follows the requested Unitree/legged_gym reward
    # table.  The older six-term implementation remains above as a backup
    # reference, but this later definition is the Python class implementation
    # used by both the host and device lifecycle routes.
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
        del roll, pitch
        if base_height is None:
            raise ValueError("height-deploy reward requires base_height")
        lin = np.asarray(lin, dtype=np.float32)
        ang = np.asarray(ang, dtype=np.float32)
        gravity = (
            np.zeros_like(lin, dtype=np.float32)
            if gravity is None
            else np.asarray(gravity, dtype=np.float32)
        )
        torque = (
            np.zeros_like(np.asarray(qvel)[..., self.joint_dof_ids], dtype=np.float32)
            if torque is None
            else np.asarray(torque, dtype=np.float32)
        )
        action = np.asarray(action, dtype=np.float32)
        previous = np.asarray(previous, dtype=np.float32)
        qpos = np.asarray(qpos, dtype=np.float32)
        qvel = np.asarray(qvel, dtype=np.float32)
        commands = _clip_height_deploy_command(np.asarray(commands, dtype=np.float32))
        base_height = np.asarray(base_height, dtype=np.float32)
        dof_pos = qpos[..., self.joint_qpos_ids]
        dof_vel = qvel[..., self.joint_dof_ids]
        previous_vel = dof_vel if previous_vel is None else np.asarray(previous_vel, dtype=np.float32)
        default = np.asarray(GO2_DEFAULT_JOINT_ANGLES, dtype=np.float32)
        dt = np.float32(GO2_POLICY_DT)
        hip_position_error = (
            dof_pos[..., GO2_HEIGHT_HIP_INDICES] - GO2_HEIGHT_HIP_DEFAULT_POS
        )
        command_magnitude = np.linalg.norm(commands[..., :2], axis=-1)
        shape = action.shape[:-1]

        contact_matrix = self._contact_matrix(
            contact_ground,
            contact_body,
            body_ids=np.concatenate((self.foot_body_ids, self.penalized_body_ids)),
            shape=shape,
        )
        feet_geom_contact = self._geom_contact_matrix(
            contact_geom,
            geom_ids=self.foot_geom_ids,
            shape=shape,
        )
        feet_contact = (
            feet_geom_contact
            if feet_geom_contact is not None
            else contact_matrix[..., self.foot_body_ids]
        )
        previous_contacts = (
            np.zeros_like(feet_contact, dtype=np.bool_)
            if self._last_contacts is None
            or self._last_contacts.shape != feet_contact.shape
            else self._last_contacts
        )
        if self._feet_air_time is None or self._feet_air_time.shape != feet_contact.shape:
            self._feet_air_time = np.zeros_like(feet_contact, dtype=np.float32)
        contact_filt = np.logical_or(feet_contact, previous_contacts)
        first_contact = np.logical_and(self._feet_air_time > 0.0, contact_filt)
        self._feet_air_time += dt
        feet_air_time = np.sum(
            (self._feet_air_time - np.float32(0.25)) * first_contact,
            axis=-1,
        )
        feet_air_time *= command_magnitude > np.float32(0.1)
        self._feet_air_time *= np.logical_not(contact_filt)
        self._last_contacts = np.asarray(feet_contact, dtype=np.bool_).copy()

        penalized_geom_contact = self._geom_contact_matrix(
            contact_geom,
            geom_ids=self.penalized_geom_ids,
            shape=shape,
        )
        collision_source = (
            penalized_geom_contact
            if penalized_geom_contact is not None
            else contact_matrix[..., self.penalized_body_ids]
        )
        collision = np.sum(np.asarray(collision_source, dtype=np.float32), axis=-1)

        # The public host state does not expose rigid_body_states/foot velocity.
        # Use a reset-safe finite difference of foot positions at the public
        # task boundary; this is the available equivalent of rigid-body foot
        # velocity without adding a host readback to the policy path.
        foot_slip = np.zeros(shape, dtype=np.float32)
        if foot_positions is not None:
            current_foot_positions = np.asarray(foot_positions, dtype=np.float32)
            previous_foot_positions = getattr(self, "_last_foot_positions", None)
            if (
                previous_foot_positions is None
                or previous_foot_positions.shape != current_foot_positions.shape
            ):
                foot_velocity = np.zeros_like(current_foot_positions)
            else:
                foot_velocity = (current_foot_positions - previous_foot_positions) / dt
            self._last_foot_positions = current_foot_positions.copy()
            slip_sq = np.minimum(
                np.sum(np.square(foot_velocity[..., :2]), axis=-1),
                np.float32(1.0),
            )
            foot_slip = np.sum(slip_sq * feet_contact, axis=-1)

        command_still = (command_magnitude < np.float32(0.1)).astype(np.float32)
        terms = {
            "tracking_lin_vel": np.exp(
                -np.sum((commands[..., :2] - lin[..., :2]) ** 2, axis=-1) / 0.25
            ) * np.float32(GO2_HEIGHT_REWARD_SCALES["tracking_lin_vel"]) * dt,
            "tracking_ang_vel": np.exp(
                -((commands[..., 2] - ang[..., 2]) ** 2) / 0.25
            ) * np.float32(GO2_HEIGHT_REWARD_SCALES["tracking_ang_vel"]) * dt,
            "lin_vel_z": np.square(lin[..., 2]) * np.float32(GO2_HEIGHT_REWARD_SCALES["lin_vel_z"]) * dt,
            "ang_vel_xy": np.sum(np.square(ang[..., :2]), axis=-1) * np.float32(GO2_HEIGHT_REWARD_SCALES["ang_vel_xy"]) * dt,
            "orientation": np.sum(np.square(gravity[..., :2]), axis=-1) * np.float32(GO2_HEIGHT_REWARD_SCALES["orientation"]) * dt,
            "torques": np.sum(np.square(torque), axis=-1) * np.float32(GO2_HEIGHT_REWARD_SCALES["torques"]) * dt,
            "dof_acc": np.sum(np.square((previous_vel - dof_vel) / dt), axis=-1) * np.float32(GO2_HEIGHT_REWARD_SCALES["dof_acc"]) * dt,
            "base_height": np.square(base_height - np.float32(GO2_DEPLOY_HEIGHT_DEFAULT)) * np.float32(GO2_HEIGHT_REWARD_SCALES["base_height"]) * dt,
            "hip_pos": np.sum(np.square(hip_position_error), axis=-1) * np.float32(GO2_HEIGHT_REWARD_SCALES["hip_pos"]) * dt,
            "feet_air_time": feet_air_time * np.float32(GO2_HEIGHT_REWARD_SCALES["feet_air_time"]) * dt,
            "collision": collision * np.float32(GO2_HEIGHT_REWARD_SCALES["collision"]) * dt,
            "action_rate": np.sum(np.square(previous - action), axis=-1) * np.float32(GO2_HEIGHT_REWARD_SCALES["action_rate"]) * dt,
            "stand_still": np.sum(np.abs(dof_pos - default), axis=-1) * command_still * np.float32(GO2_HEIGHT_REWARD_SCALES["stand_still"]) * dt,
            "dof_pos_limits": self._dof_pos_limit_penalty(dof_pos) * np.float32(GO2_HEIGHT_REWARD_SCALES["dof_pos_limits"]) * dt,
            "feet_slip": foot_slip * np.float32(GO2_HEIGHT_REWARD_SCALES["feet_slip"]) * dt,
            "termination": np.zeros(shape, dtype=np.float32) * np.float32(GO2_HEIGHT_REWARD_SCALES["termination"]) * dt,
            "dof_vel": np.sum(np.square(dof_vel), axis=-1) * np.float32(GO2_HEIGHT_REWARD_SCALES["dof_vel"]) * dt,
            "feet_stumble": np.zeros(shape, dtype=np.float32) * np.float32(GO2_HEIGHT_REWARD_SCALES["feet_stumble"]) * dt,
        }
        total = np.sum(np.stack(tuple(terms.values()), axis=0), axis=0)
        return np.maximum(np.asarray(total, dtype=np.float32), 0.0), terms

    def evaluate_device(self, *, state, action, elapsed_steps=None, previous_state=None):
        """Device-native counterpart of the requested 18-term reward."""

        import torch

        del previous_state
        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        action = action if torch.is_tensor(action) else torch.as_tensor(action, device=state.device)
        batch_size = int(state.num_envs)
        constants = self._device_constants(qpos=qpos)
        if self._device_command_steps is None or self._device_command_steps.shape != (batch_size,):
            self._device_command_steps = np.zeros(batch_size, dtype=np.int32)
        self._device_command_steps += 1
        self._maybe_resample_commands(self._device_command_steps, batch_size)

        body_xquat = state.arrays.get("body_xquat")
        if body_xquat is not None and body_xquat.shape[1] > self.base_body_id:
            root_quat = body_xquat[:, self.base_body_id]
        else:
            root_quat = qpos[:, 3:7]
        lin = _torch_quat_rotate_inverse(root_quat, qvel[:, :3])
        ang = _torch_quat_rotate_inverse(root_quat, qvel[:, 3:6])
        commands = self._device_update_heading_command(
            qpos=qpos, root_quat=root_quat, batch_size=batch_size
        )
        linear_low = torch.as_tensor(
            (GO2_DEPLOY_HEIGHT_VX_MIN, GO2_DEPLOY_HEIGHT_VY_MIN),
            dtype=qpos.dtype,
            device=qpos.device,
        )
        linear_high = torch.as_tensor(
            (GO2_DEPLOY_HEIGHT_VX_MAX, GO2_DEPLOY_HEIGHT_VY_MAX),
            dtype=qpos.dtype,
            device=qpos.device,
        )
        commands[..., :2].clamp_(linear_low, linear_high)
        commands[..., 2].clamp_(
            -GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
            GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
        )
        if self.command_dim >= 4:
            commands[..., 3].clamp_(GO2_DEPLOY_HEIGHT_MIN, GO2_DEPLOY_HEIGHT_MAX)
        body_xpos = state.arrays.get("body_xpos")
        base_height = (
            body_xpos[:, self.base_body_id, 2]
            if body_xpos is not None and body_xpos.shape[1] > self.base_body_id
            else qpos[:, 2]
        )
        dof_pos = qpos.index_select(-1, constants["qpos_ids"])
        dof_vel = qvel.index_select(-1, constants["dof_ids"])
        if "height_hip_indices" not in constants:
            constants["height_hip_indices"] = torch.as_tensor(
                GO2_HEIGHT_HIP_INDICES, dtype=torch.long, device=qpos.device
            )
            constants["height_hip_default_pos"] = torch.as_tensor(
                GO2_HEIGHT_HIP_DEFAULT_POS, dtype=qpos.dtype, device=qpos.device
            )
        hip_position_error = (
            dof_pos.index_select(-1, constants["height_hip_indices"])
            - constants["height_hip_default_pos"]
        )
        target = constants["default_angles"] + torch.as_tensor(0.25, dtype=qpos.dtype, device=qpos.device) * action
        torque = constants["kp"] * (target - dof_pos) - constants["kd"] * dof_vel
        torque = torch.clamp(torque, constants["ctrl_limits"][:, 0], constants["ctrl_limits"][:, 1])
        previous = self._device_action_tensor(
            batch_size=batch_size, device=qpos.device, dtype=qpos.dtype
        )
        if (
            self._device_last_dof_vel is None
            or tuple(self._device_last_dof_vel.shape) != tuple(dof_vel.shape)
        ):
            host_previous_vel = np.asarray(
                getattr(self, "_last_dof_vel", np.zeros((batch_size, 12), dtype=np.float32)),
                dtype=np.float32,
            )
            if host_previous_vel.shape == (batch_size, 12):
                previous_vel = torch.as_tensor(
                    host_previous_vel, dtype=qpos.dtype, device=qpos.device
                )
            else:
                previous_vel = dof_vel.detach().clone()
        else:
            previous_vel = self._device_last_dof_vel
        dt = torch.as_tensor(GO2_POLICY_DT, dtype=qpos.dtype, device=qpos.device)
        command_magnitude = torch.linalg.vector_norm(commands[..., :2], dim=-1)
        world_gravity = torch.zeros_like(qvel[:, :3])
        world_gravity[:, 2] = -1.0
        projected_gravity = _torch_quat_rotate_inverse(root_quat, world_gravity)
        terms = {
            "tracking_lin_vel": torch.exp(
                -torch.sum((commands[..., :2] - lin[..., :2]).square(), dim=-1) / 0.25
            )
            * GO2_HEIGHT_REWARD_SCALES["tracking_lin_vel"]
            * dt,
            "tracking_ang_vel": torch.exp(
                -((commands[..., 2] - ang[..., 2]).square()) / 0.25
            ) * GO2_HEIGHT_REWARD_SCALES["tracking_ang_vel"] * dt,
            "lin_vel_z": lin[..., 2].square() * GO2_HEIGHT_REWARD_SCALES["lin_vel_z"] * dt,
            "ang_vel_xy": torch.sum(ang[..., :2].square(), dim=-1) * GO2_HEIGHT_REWARD_SCALES["ang_vel_xy"] * dt,
            "orientation": torch.sum(projected_gravity[..., :2].square(), dim=-1) * GO2_HEIGHT_REWARD_SCALES["orientation"] * dt,
            "torques": torch.sum(torque.square(), dim=-1) * GO2_HEIGHT_REWARD_SCALES["torques"] * dt,
            "dof_acc": torch.sum(((previous_vel - dof_vel) / dt).square(), dim=-1) * GO2_HEIGHT_REWARD_SCALES["dof_acc"] * dt,
            "base_height": (base_height - GO2_DEPLOY_HEIGHT_DEFAULT).square() * GO2_HEIGHT_REWARD_SCALES["base_height"] * dt,
            "hip_pos": torch.sum(hip_position_error.square(), dim=-1) * GO2_HEIGHT_REWARD_SCALES["hip_pos"] * dt,
            "action_rate": torch.sum((previous - action).square(), dim=-1) * GO2_HEIGHT_REWARD_SCALES["action_rate"] * dt,
            "stand_still": torch.sum(torch.abs(dof_pos - constants["default_angles"]), dim=-1) * (command_magnitude < 0.1).to(qpos.dtype) * GO2_HEIGHT_REWARD_SCALES["stand_still"] * dt,
            "dof_pos_limits": self._device_dof_limit_penalty(dof_pos, constants=constants) * GO2_HEIGHT_REWARD_SCALES["dof_pos_limits"] * dt,
            "dof_vel": torch.sum(dof_vel.square(), dim=-1) * GO2_HEIGHT_REWARD_SCALES["dof_vel"] * dt,
        }
        contact_matrix = self._device_contact_matrix(state, batch_size=batch_size)
        feet_contact = self._device_foot_contacts(state, constants)
        previous_contacts = (
            torch.zeros_like(feet_contact)
            if self._device_last_contacts is None
            or tuple(self._device_last_contacts.shape) != tuple(feet_contact.shape)
            else self._device_last_contacts
        )
        if self._device_feet_air_time is None or tuple(self._device_feet_air_time.shape) != tuple(feet_contact.shape):
            self._device_feet_air_time = torch.zeros(tuple(feet_contact.shape), dtype=qpos.dtype, device=qpos.device)
        contact_filt = torch.logical_or(feet_contact, previous_contacts)
        first_contact = torch.logical_and(self._device_feet_air_time > 0.0, contact_filt)
        self._device_feet_air_time.add_(dt)
        air_time_reward = torch.sum((self._device_feet_air_time - 0.25) * first_contact, dim=-1)
        air_time_reward = air_time_reward * (command_magnitude > 0.1).to(qpos.dtype)
        self._device_feet_air_time.mul_(~contact_filt)
        if self._device_last_contacts is None or tuple(self._device_last_contacts.shape) != tuple(feet_contact.shape):
            self._device_last_contacts = torch.zeros_like(feet_contact)
        self._device_last_contacts.copy_(feet_contact)
        terms["feet_air_time"] = air_time_reward * GO2_HEIGHT_REWARD_SCALES["feet_air_time"] * dt

        penalized_geom_contact = self._device_geom_contact(state, constants["penalized_geom_ids"], batch_size=batch_size)
        if penalized_geom_contact is not None:
            collision_source = penalized_geom_contact
        else:
            penalized_ids = constants["penalized_body_ids"]
            valid_penalized = penalized_ids[penalized_ids < contact_matrix.shape[-1]]
            collision_source = (
                contact_matrix.index_select(-1, valid_penalized)
                if valid_penalized.numel()
                else torch.zeros((batch_size, 0), dtype=torch.bool, device=qpos.device)
            )
        collision = collision_source.to(qpos.dtype).sum(dim=-1)
        terms["collision"] = collision * GO2_HEIGHT_REWARD_SCALES["collision"] * dt

        foot_positions = self._device_foot_positions(state, constants)
        direct_body_velocity = state.arrays.get("body_xvel")
        if direct_body_velocity is not None and direct_body_velocity.shape[1] > int(np.max(self.foot_body_ids)):
            foot_velocity = direct_body_velocity.index_select(1, constants["foot_body_ids"])
        else:
            previous_foot_positions = getattr(self, "_device_last_foot_positions", None)
            if previous_foot_positions is None or tuple(previous_foot_positions.shape) != tuple(foot_positions.shape):
                foot_velocity = torch.zeros_like(foot_positions)
            else:
                foot_velocity = (foot_positions - previous_foot_positions) / dt
        if getattr(self, "_device_last_foot_positions", None) is None or tuple(self._device_last_foot_positions.shape) != tuple(foot_positions.shape):
            self._device_last_foot_positions = torch.empty_like(foot_positions)
        self._device_last_foot_positions.copy_(foot_positions.detach())
        slip_sq = torch.clamp(torch.sum(foot_velocity[..., :2].square(), dim=-1), max=1.0)
        foot_slip = torch.sum(slip_sq * feet_contact, dim=-1)
        terms["feet_slip"] = foot_slip * GO2_HEIGHT_REWARD_SCALES["feet_slip"] * dt
        terms["termination"] = torch.zeros((batch_size,), dtype=qpos.dtype, device=qpos.device) * GO2_HEIGHT_REWARD_SCALES["termination"] * dt
        terms["feet_stumble"] = torch.zeros((batch_size,), dtype=qpos.dtype, device=qpos.device) * GO2_HEIGHT_REWARD_SCALES["feet_stumble"] * dt
        reward = torch.clamp(torch.stack(tuple(terms.values()), dim=0).sum(dim=0), min=0.0)
        w, x, y, z = [root_quat[..., index] for index in range(4)]
        roll = torch.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
        pitch = torch.asin(torch.clamp(2.0 * (w * y - z * x), -1.0, 1.0))
        raw_fall = (torch.abs(roll) > GO2_TERMINATION_ANGLE) | (
            torch.abs(pitch) > GO2_TERMINATION_ANGLE
        )
        if elapsed_steps is not None:
            episode_age = elapsed_steps.to(
                device=qpos.device, dtype=torch.int32
            ) if torch.is_tensor(elapsed_steps) else torch.as_tensor(
                elapsed_steps, device=qpos.device, dtype=torch.int32
            )
        elif self._device_elapsed is None:
            episode_age = torch.ones(
                batch_size, dtype=torch.int32, device=qpos.device
            )
        else:
            episode_age = self._device_elapsed + 1
        fall = raw_fall & (
            episode_age >= int(self.termination_grace_steps)
        )
        base_contact = self._device_body_contact(
            state, constants["base_body_ids"], batch_size=batch_size
        )
        if self._device_last_actions is None or tuple(self._device_last_actions.shape) != tuple(action.shape):
            self._device_last_actions = torch.empty_like(action)
        self._device_last_actions.copy_(action.detach())
        current_dof_vel = dof_vel.detach()
        if (
            self._device_last_dof_vel is None
            or tuple(self._device_last_dof_vel.shape) != tuple(current_dof_vel.shape)
            or self._device_last_dof_vel.device != current_dof_vel.device
            or self._device_last_dof_vel.dtype != current_dof_vel.dtype
        ):
            self._device_last_dof_vel = torch.empty_like(current_dof_vel)
        self._device_last_dof_vel.copy_(current_dof_vel)
        if self._device_elapsed is None or tuple(self._device_elapsed.shape) != (batch_size,):
            self._device_elapsed = torch.zeros((batch_size,), dtype=torch.int32, device=qpos.device)
        elif self._device_elapsed.device != qpos.device:
            self._device_elapsed = torch.zeros((batch_size,), dtype=torch.int32, device=qpos.device)
        self._device_elapsed.add_(1)
        return {
            "reward": reward,
            "terminated": fall | base_contact,
            "truncated": self._device_elapsed >= GO2_HORIZON,
            "infos": None,
            "metrics": {
                "base_height": base_height,
                "roll": roll,
                "pitch": pitch,
                "fall": fall,
                "base_contact": base_contact,
            },
            "reward_terms": terms,
        }


@register_parallel_env()
@register_env()
class Go2WalkDeployHeightEnv(Go2WalkDeployEnv):
    uid = GO2_DEPLOY_HEIGHT_ENV_ID
    task_uid = GO2_DEPLOY_HEIGHT_ENV_ID

    @classmethod
    def default_config(cls):
        config = super().default_config()
        return replace(
            config,
            task=replace(config.task, task_uid=cls.task_uid),
            action=replace(config.action, rsl_action_profile="unitree_go2_debug"),
            observation=replace(
                config.observation,
                schema_version=GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION,
            ),
        )

    def placement_notes(self) -> tuple[str, ...]:
        return (
            "Go2 height training uses a 46-value actor layout with a 0.30-0.40 m height command/root reset range.",
            "The deployment evaluator keeps the fourth command and base-height target fixed at 0.34 m unless explicitly overridden.",
            "The legacy 45-value environment remains registered unchanged for checkpoint compatibility.",
        )

    def reference_profile(self) -> dict[str, Any]:
        profile = super().reference_profile()
        profile.update({
            "profile_id": "task-env-go2-walk-deploy-height-reference-v1",
            "observation_schema": GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION,
            "observation_dim": GO2_DEPLOY_HEIGHT_OBSERVATION_DIM,
            "height_command": {
                "index": 9, "min": GO2_DEPLOY_HEIGHT_MIN,
                "max": GO2_DEPLOY_HEIGHT_MAX, "default": GO2_DEPLOY_HEIGHT_DEFAULT,
                "reward_target": 0.34,
                "reward_uses_command": False,
                "base_height_scale": GO2_HEIGHT_REWARD_SCALES["base_height"],
                "policy_dt_scaled": True,
                "feet_air_time_command_threshold": 0.1,
                "termination_angle": float(GO2_TERMINATION_ANGLE),
                "termination_grace_steps": GO2_HEIGHT_TERMINATION_GRACE_STEPS,
                "termination_grace_seconds": (
                    GO2_HEIGHT_TERMINATION_GRACE_STEPS * GO2_POLICY_DT
                ),
                "base_contact_immediate": True,
            },
            "initialization": {
                "profile": "height_randomized_joint_pose_and_root_velocity_v1",
                "root_velocity_range": [
                    GO2_HEIGHT_RESET_ROOT_VELOCITY_MIN,
                    GO2_HEIGHT_RESET_ROOT_VELOCITY_MAX,
                ],
                "joint_scale_range": [
                    GO2_HEIGHT_RESET_JOINT_SCALE_MIN,
                    GO2_HEIGHT_RESET_JOINT_SCALE_MAX,
                ],
                "hip_initial_range": [
                    GO2_HEIGHT_RESET_HIP_MIN,
                    GO2_HEIGHT_RESET_HIP_MAX,
                ],
            },
            "reward_terms": {
                **GO2_HEIGHT_REWARD_SCALES,
                "policy_dt": GO2_POLICY_DT,
                "base_height_target": GO2_DEPLOY_HEIGHT_DEFAULT,
                "feet_air_time_threshold": 0.25,
                "nonnegative_clip": True,
                "contract": "unitree-legged-gym-eighteen-term-v1",
            },
        })
        return profile

    def create_reset_sampler(self):
        return Go2WalkDeployHeightResetSampler()

    def create_task_definition(self, compiled_scene):
        base = Go2WalkEnv.create_task_definition(self, compiled_scene)
        values = {field.name: getattr(base, field.name) for field in fields(Go2WalkTaskDefinition)}
        return Go2WalkDeployHeightTaskDefinition(**values)


__all__ = [
    "GO2_DEPLOY_ENV_ID",
    "GO2_DEPLOY_HEIGHT_ENV_ID",
    "GO2_DEPLOY_NOISE_SCALE",
    "GO2_DEPLOY_HEIGHT_NOISE_SCALE",
    "GO2_DEPLOY_OBS_SCHEMA_VERSION",
    "GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION",
    "GO2_DEPLOY_OBSERVATION_DIM",
    "GO2_DEPLOY_HEIGHT_OBSERVATION_DIM",
    "GO2_DEPLOY_ROOT_HEIGHT",
    "GO2_DEPLOY_HEIGHT_DEFAULT",
    "GO2_DEPLOY_HEIGHT_MIN",
    "GO2_DEPLOY_HEIGHT_MAX",
    "GO2_DEPLOY_HEIGHT_REWARD_SCALE",
    "GO2_HEIGHT_REWARD_SCALES",
    "GO2_HEIGHT_HIP_POS_SCALE",
    "GO2_HEIGHT_HIP_INDICES",
    "GO2_HEIGHT_HIP_DEFAULT_POS",
    "GO2_HEIGHT_GENESIS_REWARD_SCALES",
    "GO2_DEPLOY_HEIGHT_LINEAR_COMMAND_LIMIT",
    "GO2_HEIGHT_RESET_ROOT_VELOCITY_MIN",
    "GO2_HEIGHT_RESET_ROOT_VELOCITY_MAX",
    "GO2_HEIGHT_RESET_JOINT_SCALE_MIN",
    "GO2_HEIGHT_RESET_JOINT_SCALE_MAX",
    "GO2_HEIGHT_RESET_HIP_MIN",
    "GO2_HEIGHT_RESET_HIP_MAX",
    "GO2_HEIGHT_TERMINATION_GRACE_STEPS",
    "GO2_HEIGHT_MOVING_COMMAND_THRESHOLD",
    "GO2_HEIGHT_MOVING_COMMAND_MAX",
    "GO2_HEIGHT_MOVING_TRACKING_MULTIPLIER",
    "GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT",
    "GO2_DEPLOY_ROLL_ORIENTATION_WEIGHT",
    "GO2_DEPLOY_PITCH_ORIENTATION_WEIGHT",
    "Go2WalkDeployHeightEnv",
    "Go2WalkDeployHeightResetSampler",
    "Go2WalkDeployHeightTaskDefinition",
    "Go2WalkDeployEnv",
    "Go2WalkDeployResetSampler",
    "Go2WalkDeployTaskDefinition",
]
