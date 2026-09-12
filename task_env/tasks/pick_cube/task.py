"""PickCube registration, reset sampling, reward and success semantics."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from ...environment import EpisodePhysicsState, RuntimeSnapshot, TaskEvaluation
from ...environment.task_definition import TaskDefinitionBase
from ...assembly import TaskReferences
from ...registry import register_env
from ..base import BaseTaskEnv
from .assets import CUBE_CONTACT_MARGIN, CUBE_HALF_SIZE, TABLE_TOP_Z


@dataclass(frozen=True)
class PickCubeVariantSpec:
    """Stable identifiers and profiles for the registered PickCube variant."""

    env_id: str
    task_uid: str
    variant: str
    scene_uid: str
    agent_uids: tuple[str, ...]
    object_uids: tuple[str, ...]
    success_definition: str
    scene_profile: str
    sensor_profile: str
    reset_profile: str
    expert_profile: str
    reward_profile: str
    language_templates: tuple[str, ...] = ()


PICK_CUBE_SPEC = PickCubeVariantSpec(
    env_id="pick-cube-v1",
    task_uid="pick-cube-v1",
    variant="default",
    scene_uid="tabletop-v1",
    agent_uids=("panda-v1",),
    object_uids=("cube-v1",),
    success_definition="cube_lifted_v1",
    scene_profile="tabletop_panda_cube_v1",
    sensor_profile="state_privileged_optional_base_hand_camera_v1",
    reset_profile="uniform_table_center_xy_v1",
    expert_profile="cartesian_pose_primitive_sequence_v1",
    reward_profile="cube_lift_height_10cm_v2",
    language_templates=("pick up the cube",),
)

PICK_CUBE_ENV_ID = PICK_CUBE_SPEC.env_id
PICK_CUBE_TASK_UID = PICK_CUBE_SPEC.task_uid
PICK_CUBE_VARIANT = PICK_CUBE_SPEC.variant
PICK_CUBE_SUCCESS_DEFINITION = PICK_CUBE_SPEC.success_definition
PICK_CUBE_SCENE_UID = PICK_CUBE_SPEC.scene_uid
PICK_CUBE_AGENT_UIDS = PICK_CUBE_SPEC.agent_uids
PICK_CUBE_OBJECT_UIDS = PICK_CUBE_SPEC.object_uids
PICK_CUBE_EXPERT_PROFILE = PICK_CUBE_SPEC.expert_profile
PICK_CUBE_RESET_PROFILE = PICK_CUBE_SPEC.reset_profile
PICK_CUBE_SENSOR_PROFILE = PICK_CUBE_SPEC.sensor_profile


_PANDA_UID = "panda-v1"
_CUBE_UID = "cube-v1"
_LIFT_HEIGHT = 0.100
_REACH_DISTANCE = 0.090
# ``grasped_cube`` is a diagnostic/reward heuristic.  The task's authoritative
# success contract is only the 10 cm measured cube lift below.
_GRIPPER_CLOSED_OPENING = 0.045


def _distance(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64)))


@dataclass(frozen=True)
class PickCubeTaskDefinition(TaskDefinitionBase):
    """Versioned PickCube lift evaluation."""

    references: TaskReferences
    success_definition: str = PICK_CUBE_SUCCESS_DEFINITION

    def __post_init__(self) -> None:
        if self.success_definition != PICK_CUBE_SUCCESS_DEFINITION:
            raise ValueError(
                "PickCubeTaskDefinition only implements "
                f"{PICK_CUBE_SUCCESS_DEFINITION!r}, got {self.success_definition!r}"
            )
        if _PANDA_UID not in self.references.agents:
            raise KeyError("PickCubeTaskDefinition requires panda-v1 references")
        if _CUBE_UID not in self.references.objects:
            raise KeyError("PickCubeTaskDefinition requires cube-v1 references")

    def reset(self, snapshot: RuntimeSnapshot) -> TaskEvaluation:
        return self._evaluate(snapshot)

    def evaluate(
        self,
        previous_snapshot: RuntimeSnapshot,
        action: np.ndarray,
        current_snapshot: RuntimeSnapshot,
    ) -> TaskEvaluation:
        del previous_snapshot, action
        return self._evaluate(current_snapshot)

    def _evaluate(self, snapshot: RuntimeSnapshot) -> TaskEvaluation:
        panda = self.references.agents[_PANDA_UID]
        cube_ref = self.references.objects[_CUBE_UID]
        if snapshot.site_xpos is None:
            raise ValueError("PickCube evaluation requires site_xpos")
        if snapshot.body_xpos is None:
            raise ValueError("PickCube evaluation requires body_xpos")

        cube_pos = np.asarray(snapshot.body_xpos[int(cube_ref.body_ids[0])], dtype=np.float64)
        eef_pos = np.asarray(snapshot.site_xpos[int(panda.eef_site_id)], dtype=np.float64)
        gripper_qpos = np.asarray(snapshot.qpos[panda.gripper_qpos_ids], dtype=np.float64)
        gripper_opening = float(np.sum(gripper_qpos))
        cube_lift = float(cube_pos[2] - (TABLE_TOP_Z + CUBE_HALF_SIZE))
        eef_to_cube_dist = _distance(eef_pos, cube_pos)

        reached_cube = eef_to_cube_dist <= _REACH_DISTANCE
        gripper_closed = gripper_opening <= _GRIPPER_CLOSED_OPENING
        grasped_cube = bool(reached_cube and gripper_closed)
        lifted_cube = bool(cube_lift >= _LIFT_HEIGHT)
        task_success = bool(lifted_cube)

        reach_reward = 0.10 * float(1.0 - math.tanh(10.0 * eef_to_cube_dist))
        lift_reward = min(0.40, max(0.0, cube_lift / _LIFT_HEIGHT) * 0.40)
        reward_terms = {
            "reach": reach_reward,
            "grasp": 0.25 if grasped_cube else 0.0,
            "lift": lift_reward,
            "success": 1.0 if task_success else 0.0,
        }
        metrics = {
            "reached_cube": bool(reached_cube),
            "grasped_cube": bool(grasped_cube),
            "lifted_cube": bool(lifted_cube),
            "task_success": bool(task_success),
            "cube_x": float(cube_pos[0]),
            "cube_y": float(cube_pos[1]),
            "cube_z": float(cube_pos[2]),
            "cube_lift": float(cube_lift),
            "eef_to_cube_dist": float(eef_to_cube_dist),
            "gripper_opening": float(gripper_opening),
            "success_definition": self.success_definition == PICK_CUBE_SUCCESS_DEFINITION,
        }
        return TaskEvaluation(
            reward=sum(reward_terms.values()),
            success=task_success,
            failure=False,
            metrics=metrics,
            reward_terms=reward_terms,
        )


@register_env()
class PickCubeEnv(BaseTaskEnv):
    """Registered PickCube environment and task-owned runtime factories."""

    variant_spec = PICK_CUBE_SPEC
    uid = PICK_CUBE_ENV_ID
    task_uid = PICK_CUBE_TASK_UID
    scene_uid = PICK_CUBE_SCENE_UID
    agent_uids = PICK_CUBE_AGENT_UIDS
    object_uids = PICK_CUBE_OBJECT_UIDS
    success_definition = PICK_CUBE_SUCCESS_DEFINITION
    sensor_profile = PICK_CUBE_SENSOR_PROFILE
    reset_profile = PICK_CUBE_RESET_PROFILE

    def placement_notes(self) -> tuple[str, ...]:
        return (
            "Panda base pose follows the current tabletop reference scene.",
            "Cube reset position is sampled uniformly in a 20 cm square around the table center.",
            "PickCube uses a task-specific composition adapter.",
        )

    def create_scene_composer(self):
        from .assets import PickCubeSceneComposer

        return PickCubeSceneComposer()

    def create_reset_sampler(self):
        return PickCubeResetSampler()

    def create_task_definition(self, compiled_scene):
        return PickCubeTaskDefinition(
            references=compiled_scene.references,
            success_definition=self.config.task.success_definition,
        )


class PickCubeResetSampler:
    """Sample replayable PickCube positions at the public reset boundary."""

    table_center_xy = np.asarray((0.5545, 0.0), dtype=np.float32)
    half_extent_m = 0.10

    def sample_episode_state(
        self,
        *,
        compiled_scene: object,
        initial_state: EpisodePhysicsState,
        rng: np.random.Generator,
        seed: int | None,
    ) -> tuple[EpisodePhysicsState, dict[str, Any]]:
        cube_ref = compiled_scene.references.objects["cube-v1"]
        qpos_ids = np.asarray(cube_ref.qpos_ids, dtype=np.int32).reshape(-1)
        if qpos_ids.size != 1:
            raise ValueError("PickCube reset requires a freejoint cube pose")
        qpos = np.asarray(initial_state.qpos, dtype=np.float32).copy()
        cube_qpos_adr = int(qpos_ids[0])
        if qpos.size < cube_qpos_adr + 7:
            raise ValueError("PickCube cube freejoint exceeds the reset qpos state")
        xy = self.table_center_xy + rng.uniform(
            low=-self.half_extent_m,
            high=self.half_extent_m,
            size=2,
        ).astype(np.float32)
        cube_position = np.asarray(
            (xy[0], xy[1], TABLE_TOP_Z + CUBE_HALF_SIZE + CUBE_CONTACT_MARGIN),
            dtype=np.float32,
        )
        qpos[cube_qpos_adr : cube_qpos_adr + 3] = cube_position
        qpos[cube_qpos_adr + 3 : cube_qpos_adr + 7] = np.asarray(
            (1.0, 0.0, 0.0, 0.0), dtype=np.float32
        )
        state = EpisodePhysicsState(
            qpos=qpos,
            qvel=np.asarray(initial_state.qvel, dtype=np.float32),
            qacc=np.asarray(initial_state.qacc, dtype=np.float32),
            ctrl=np.asarray(initial_state.ctrl, dtype=np.float32),
            act=np.asarray(initial_state.act, dtype=np.float32),
        )
        return state, {
            "profile": PICK_CUBE_RESET_PROFILE,
            "seed": seed,
            "cube_position_world_m": cube_position.tolist(),
            "cube_quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
            "xy_half_extent_m": float(self.half_extent_m),
            "table_center_xy_m": self.table_center_xy.tolist(),
        }


__all__ = [
    "PICK_CUBE_AGENT_UIDS", "PICK_CUBE_ENV_ID", "PICK_CUBE_EXPERT_PROFILE",
    "PICK_CUBE_OBJECT_UIDS", "PICK_CUBE_RESET_PROFILE", "PICK_CUBE_SCENE_UID",
    "PICK_CUBE_SENSOR_PROFILE", "PICK_CUBE_SPEC", "PICK_CUBE_SUCCESS_DEFINITION",
    "PICK_CUBE_TASK_UID", "PICK_CUBE_VARIANT", "PickCubeEnv", "PickCubeResetSampler",
    "PickCubeTaskDefinition", "PickCubeVariantSpec",
]
