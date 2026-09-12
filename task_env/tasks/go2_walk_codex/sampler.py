"""Second-stage narrow reset sampler for the independent Codex task."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..go2_walk_deploy.task import (
    GO2_DEPLOY_HEIGHT_DEFAULT,
    GO2_DEPLOY_HEIGHT_MAX,
    GO2_DEPLOY_HEIGHT_MIN,
    GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION,
    GO2_DEPLOY_HEIGHT_VX_MAX,
    GO2_DEPLOY_HEIGHT_VX_MIN,
    GO2_DEPLOY_HEIGHT_VY_MAX,
    GO2_DEPLOY_HEIGHT_VY_MIN,
    GO2_DEPLOY_HEIGHT_YAW_COMMAND_LIMIT,
    Go2WalkDeployResetSampler,
    _clip_height_deploy_command,
)
from ...environment.types import EpisodePhysicsState


CODEX_ROOT_LINEAR_VELOCITY_RANGE = (-0.10, 0.10)
CODEX_ROOT_ANGULAR_VELOCITY_RANGE = (-0.10, 0.10)
CODEX_JOINT_VELOCITY_RANGE = (-0.05, 0.05)


class Go2WalkCodexResetSampler(Go2WalkDeployResetSampler):
    """Nominal Go2 pose with small reset velocity perturbations.

    The deploy-height sampler's wide joint-pose/root-velocity diagnostic is
    intentionally not called here.  Scene, asset, command, and height
    contracts remain inherited from the deploy-height task.
    """

    def sample_episode_state(
        self,
        *,
        compiled_scene: object,
        initial_state: EpisodePhysicsState,
        rng: np.random.Generator,
        seed: int | None,
    ) -> tuple[EpisodePhysicsState, dict[str, Any]]:
        state, parameters = super().sample_episode_state(
            compiled_scene=compiled_scene,
            initial_state=initial_state,
            rng=rng,
            seed=seed,
        )

        qpos = np.asarray(state.qpos, dtype=np.float32).copy()
        qvel = np.asarray(state.qvel, dtype=np.float32).copy()
        root_height = float(rng.uniform(GO2_DEPLOY_HEIGHT_MIN, GO2_DEPLOY_HEIGHT_MAX))
        qpos[2] = np.float32(root_height)
        qvel[:3] = rng.uniform(
            CODEX_ROOT_LINEAR_VELOCITY_RANGE[0],
            CODEX_ROOT_LINEAR_VELOCITY_RANGE[1],
            size=3,
        ).astype(np.float32)
        qvel[3:6] = rng.uniform(
            CODEX_ROOT_ANGULAR_VELOCITY_RANGE[0],
            CODEX_ROOT_ANGULAR_VELOCITY_RANGE[1],
            size=3,
        ).astype(np.float32)
        qvel[6:] = rng.uniform(
            CODEX_JOINT_VELOCITY_RANGE[0],
            CODEX_JOINT_VELOCITY_RANGE[1],
            size=qvel[6:].shape,
        ).astype(np.float32)
        state = EpisodePhysicsState(
            qpos=qpos,
            qvel=qvel,
            qacc=np.asarray(state.qacc, dtype=np.float32).copy(),
            ctrl=np.asarray(state.ctrl, dtype=np.float32).copy(),
            act=np.asarray(state.act, dtype=np.float32).copy(),
        )

        target_height = float(rng.uniform(GO2_DEPLOY_HEIGHT_MIN, GO2_DEPLOY_HEIGHT_MAX))
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
        command = _clip_height_deploy_command(command)

        parameters = dict(parameters)
        parameters.update(
            {
                "profile": "go2_walk_codex_stage2_narrow_reset_v1",
                "initialization_profile": "nominal_joint_pose_small_velocity_v1",
                "root_position": [0.0, 0.0, root_height],
                "root_velocity_range": [
                    CODEX_ROOT_LINEAR_VELOCITY_RANGE,
                    CODEX_ROOT_ANGULAR_VELOCITY_RANGE,
                ],
                "joint_velocity_range": CODEX_JOINT_VELOCITY_RANGE,
                "joint_random_scale": [1.0, 1.0],
                "hip_initial_range": [0.0, 0.0],
                "command": np.concatenate(
                    (command[:3], np.asarray((target_height,), dtype=np.float32))
                ).tolist(),
                "target_height": target_height,
                "observation_schema": GO2_DEPLOY_HEIGHT_OBS_SCHEMA_VERSION,
                "sampler_stage": "second_stage_small_joint_root_velocity_randomization",
                "height_default": GO2_DEPLOY_HEIGHT_DEFAULT,
            }
        )
        return state, parameters


__all__ = [
    "CODEX_JOINT_VELOCITY_RANGE",
    "CODEX_ROOT_ANGULAR_VELOCITY_RANGE",
    "CODEX_ROOT_LINEAR_VELOCITY_RANGE",
    "Go2WalkCodexResetSampler",
]
