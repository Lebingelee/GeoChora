"""Absolute-world-pose reference solution for NutAssemblySquare.

The solution is an external TaskEnv client: it consumes reset/step outputs
only.  In particular, geometry used for grasp-relative transport is read from
the recorded public ``privileged_state`` observation, never from an environment
or MuJoCo runtime object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from ...planners import AbsolutePosePlanner, AbsolutePosePlannerConfig, ExpertAction
from ...utils.rotation import (
    normalize_quat_wxyz,
    quat_multiply_wxyz,
    rotate_vector_wxyz,
)
from .assets import NUT_CONTACT_MARGIN, NUT_HALF_HEIGHT, PEG_HALF_HEIGHT, TABLE_TOP_Z


@dataclass(frozen=True)
class NutAssemblySolutionConfig:
    """30 Hz absolute-pose trajectory limits validated by the smoke test."""

    action_budget: int = 500
    close_steps: int = 10
    close_settle_steps: int = 15
    release_steps: int = 10
    release_settle_steps: int = 20
    planner: AbsolutePosePlannerConfig = field(
        default_factory=lambda: AbsolutePosePlannerConfig(
            max_translation_per_step=0.004,
            max_translation_acceleration_per_step=0.001,
            max_rotation_per_step=0.10,
            max_rotation_acceleration_per_step=0.03,
            settle_steps=8,
            max_steps=160,
        )
    )


def _square_yaw_correction(quaternion_wxyz: np.ndarray) -> float:
    w, x, y, z = normalize_quat_wxyz(quaternion_wxyz)
    yaw = float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))
    period = 0.5 * np.pi
    return -float((yaw + 0.5 * period) % period - 0.5 * period)


class NutAssemblySolution:
    """Plan the verified pick, peg-hover, peg-through-hole, table-seat, and release path."""

    _STAGES = (
        "approach_nut", "descend_to_handle", "close_gripper", "lift_nut",
        "raise_for_transport", "move_above_square_peg", "align_nut_yaw",
        "descend_to_peg_top", "lower_nut_to_table", "open_gripper",
    )

    def __init__(self, *, config: NutAssemblySolutionConfig | None = None) -> None:
        self.config = config or NutAssemblySolutionConfig()
        self._planner = AbsolutePosePlanner(self.config.planner)
        self._stage_index = 0
        self._actions = np.empty((0, 8), dtype=np.float32)
        self._action_index = 0
        self._actions_emitted = 0
        self._done = False
        self._failed = False
        self._failure_reason: str | None = None
        self._metadata: Mapping[str, object] | None = None

    @property
    def stage(self) -> str: return self._STAGES[min(self._stage_index, len(self._STAGES) - 1)]
    @property
    def done(self) -> bool: return self._done
    @property
    def failed(self) -> bool: return self._failed
    @property
    def failure_reason(self) -> str | None: return self._failure_reason

    def reset(self, observation, info: Mapping[str, object], metadata: Mapping[str, object]) -> None:
        schema = metadata.get("action_schema", {})
        if (schema.get("controller_kind"), schema.get("reference"), schema.get("rotation_representation")) != (
            "absolute_pose", "world", "quaternion_wxyz"
        ):
            raise ValueError("NutAssemblySolution requires absolute_pose(reference='world') with quaternion_wxyz")
        self._stage_index, self._action_index, self._actions_emitted = 0, 0, 0
        self._done, self._failed, self._failure_reason = bool(info.get("is_success", False)), False, None
        self._metadata = metadata
        if not self._done: self._plan_stage(observation)

    def act(self, observation=None, info: Mapping[str, object] | None = None) -> ExpertAction:
        del observation, info
        if self._done or self._failed: raise RuntimeError("cannot act after solution completion")
        action = self._actions[self._action_index]
        result = ExpertAction(action=action, stage=self.stage, diagnostics={"stage_index": self._stage_index, "stage_step": self._action_index, "actions_emitted": self._actions_emitted})
        self._action_index += 1
        self._actions_emitted += 1
        return result

    next_action = act

    def observe(self, observation, reward: float, terminated: bool, truncated: bool, info: Mapping[str, object]) -> None:
        del reward
        if bool(info.get("is_success", False)):
            self._done = True
            return
        if terminated or truncated:
            self._failed, self._failure_reason = True, "environment_terminated"
            return
        if self._action_index < len(self._actions): return
        if self._stage_index == len(self._STAGES) - 1:
            self._failed, self._failure_reason = True, "release_completed_without_task_success"
            return
        self._stage_index += 1
        self._action_index = 0
        self._plan_stage(observation)

    @staticmethod
    def _ee_pose(observation) -> np.ndarray:
        return np.asarray(observation["state"]["ee_pose"], dtype=np.float64).reshape(7)

    @staticmethod
    def _body_pose(observation, name: str) -> np.ndarray:
        return np.asarray(observation["privileged_state"][f"{name}_body_pose"][0], dtype=np.float64).reshape(7)

    @staticmethod
    def _pose(position: np.ndarray, orientation: np.ndarray) -> np.ndarray:
        return np.concatenate((position, orientation)).astype(np.float32)

    def _set_actions(self, actions: np.ndarray) -> None:
        self._actions = np.asarray(actions, dtype=np.float32)
        if self._actions.ndim != 2 or self._actions.shape[0] < 1 or self._actions.shape[1] != 8:
            raise ValueError("NutAssemblySolution must emit non-empty universal 8D actions")
        if self._actions_emitted + len(self._actions) > self.config.action_budget:
            self._failed, self._failure_reason = True, "solution_action_budget_exceeded"

    def _plan_stage(self, observation) -> None:
        ee = self._ee_pose(observation)
        nut = self._body_pose(observation, "square_nut_v1")
        peg = self._body_pose(observation, "square_peg_v1")
        orientation = ee[3:]
        handle = nut[:3] + rotate_vector_wxyz(nut[3:], np.array([0.054, 0.0, 0.0]))
        stage = self.stage
        if stage == "approach_nut":
            actions = self._planner.plan_to_pose(current_pose=ee, goal_pose=self._pose(handle + [-.02, 0, .12], orientation), gripper=1.0)
        elif stage == "descend_to_handle":
            actions = self._planner.plan_to_pose(current_pose=ee, goal_pose=self._pose(handle + [-.02, 0, .045], orientation), gripper=1.0)
        elif stage == "close_gripper":
            actions = self._planner.plan_gripper_transition(pose=ee, start_gripper=1.0, goal_gripper=-1.0, steps=self.config.close_steps, settle_steps=self.config.close_settle_steps)
        elif stage == "lift_nut":
            actions = self._planner.plan_to_pose(current_pose=ee, goal_pose=self._pose(handle + [-.02, 0, .15], orientation), gripper=-1.0)
        else:
            nut_to_ee = nut[:3] - ee[:3]
            hover_nut = peg[:3] + np.array([0.0, 0.0, PEG_HALF_HEIGHT + .08])
            if stage == "raise_for_transport":
                target = ee[:3].copy(); target[2] = (hover_nut - nut_to_ee)[2]
                actions = self._planner.plan_translation_only(current_pose=ee, target_position=target, gripper=-1.0)
            elif stage == "move_above_square_peg":
                actions = self._planner.plan_translation_only(current_pose=ee, target_position=hover_nut - nut_to_ee, gripper=-1.0)
            elif stage == "align_nut_yaw":
                correction = _square_yaw_correction(nut[3:])
                qz = np.array([np.cos(.5 * correction), 0.0, 0.0, np.sin(.5 * correction)])
                actions = self._planner.plan_to_pose(current_pose=ee, goal_pose=self._pose(ee[:3], quat_multiply_wxyz(qz, ee[3:])), gripper=-1.0)
            elif stage == "descend_to_peg_top":
                nut_at_peg_top = peg[:3] + np.array([0.0, 0.0, PEG_HALF_HEIGHT + NUT_HALF_HEIGHT + NUT_CONTACT_MARGIN])
                actions = self._planner.plan_translation_only(current_pose=ee, target_position=nut_at_peg_top - nut_to_ee, gripper=-1.0)
            elif stage == "lower_nut_to_table":
                nut_on_table = np.array([peg[0], peg[1], TABLE_TOP_Z + NUT_HALF_HEIGHT + NUT_CONTACT_MARGIN])
                actions = self._planner.plan_translation_only(current_pose=ee, target_position=nut_on_table - nut_to_ee, gripper=-1.0)
            else:  # open_gripper
                actions = self._planner.plan_gripper_transition(pose=ee, start_gripper=-1.0, goal_gripper=1.0, steps=self.config.release_steps, settle_steps=self.config.release_settle_steps)
        self._set_actions(actions)


__all__ = ["NutAssemblySolution", "NutAssemblySolutionConfig"]
