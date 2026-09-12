"""Joint-space smooth action planner for absolute-joint controllers."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class JointPositionPlannerConfig:
    """Discrete joint and gripper velocity/acceleration limits."""

    max_joint_delta_per_step: float = 0.03
    max_joint_acceleration_per_step: float = 0.008
    max_gripper_delta_per_step: float = 0.08
    max_gripper_acceleration_per_step: float = 0.02
    settle_steps: int = 48
    max_steps: int = 400

    def __post_init__(self) -> None:
        for name in (
            "max_joint_delta_per_step",
            "max_joint_acceleration_per_step",
            "max_gripper_delta_per_step",
            "max_gripper_acceleration_per_step",
        ):
            if float(getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.settle_steps < 0:
            raise ValueError("settle_steps cannot be negative")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least one")


class JointPositionPlanner:
    """Generate continuous 8D public absolute-joint action sequences."""

    def __init__(self, config: JointPositionPlannerConfig | None = None) -> None:
        self.config = config or JointPositionPlannerConfig()

    def plan_to_joint_positions(
        self,
        *,
        current_positions: np.ndarray,
        target_positions: np.ndarray,
        gripper: float,
        steps: int | None = None,
        settle_steps: int | None = None,
    ) -> np.ndarray:
        start = self._joint_vector(current_positions, name="current_positions")
        target = self._joint_vector(target_positions, name="target_positions")
        count = self._resolve_joint_count(target - start, steps=steps)
        actions = np.empty((count, 8), dtype=np.float32)
        for index in range(count):
            fraction = self._smooth_fraction(index + 1, count)
            actions[index, :7] = ((1.0 - fraction) * start + fraction * target).astype(
                np.float32
            )
            actions[index, 7] = np.float32(np.clip(gripper, -1.0, 1.0))
        return self._append_settle(actions, steps=settle_steps)

    def plan_gripper_transition(
        self,
        *,
        joint_positions: np.ndarray,
        start_gripper: float,
        target_gripper: float,
        steps: int | None = None,
        settle_steps: int | None = None,
    ) -> np.ndarray:
        joint_target = self._joint_vector(joint_positions, name="joint_positions")
        start = float(np.clip(start_gripper, -1.0, 1.0))
        target = float(np.clip(target_gripper, -1.0, 1.0))
        count = self._resolve_gripper_count(target - start, steps=steps)
        actions = np.empty((count, 8), dtype=np.float32)
        actions[:, :7] = joint_target.astype(np.float32)
        for index in range(count):
            fraction = self._smooth_fraction(index + 1, count)
            actions[index, 7] = np.float32((1.0 - fraction) * start + fraction * target)
        return self._append_settle(actions, steps=settle_steps)

    @staticmethod
    def _joint_vector(value: np.ndarray, *, name: str) -> np.ndarray:
        vector = np.asarray(value, dtype=np.float64).reshape(-1).copy()
        if vector.shape != (7,) or not np.isfinite(vector).all():
            raise ValueError(f"{name} must be a finite vector with shape (7,)")
        return vector

    def _resolve_joint_count(self, delta: np.ndarray, *, steps: int | None) -> int:
        distance = float(np.max(np.abs(delta)))
        return self._resolve_count(
            distance,
            velocity_limit=self.config.max_joint_delta_per_step,
            acceleration_limit=self.config.max_joint_acceleration_per_step,
            steps=steps,
        )

    def _resolve_gripper_count(self, delta: float, *, steps: int | None) -> int:
        return self._resolve_count(
            abs(float(delta)),
            velocity_limit=self.config.max_gripper_delta_per_step,
            acceleration_limit=self.config.max_gripper_acceleration_per_step,
            steps=steps,
        )

    def _resolve_count(
        self,
        distance: float,
        *,
        velocity_limit: float,
        acceleration_limit: float,
        steps: int | None,
    ) -> int:
        requested = 1 if steps is None else int(steps)
        if requested < 1:
            raise ValueError("steps must be at least one")
        count = max(
            requested,
            1,
            int(math.ceil(1.5 * distance / velocity_limit)),
            int(math.ceil(math.sqrt(6.0 * distance / acceleration_limit))),
        )
        if count > self.config.max_steps:
            raise ValueError(
                f"trajectory needs {count} steps, exceeding max_steps={self.config.max_steps}"
            )
        return count

    @staticmethod
    def _smooth_fraction(step: int, count: int) -> float:
        u = float(step) / float(count)
        return u * u * (3.0 - 2.0 * u)

    def _append_settle(self, actions: np.ndarray, *, steps: int | None) -> np.ndarray:
        settle_count = self.config.settle_steps if steps is None else int(steps)
        if settle_count < 0:
            raise ValueError("settle_steps cannot be negative")
        if settle_count == 0:
            return actions
        return np.concatenate(
            [actions, np.repeat(actions[-1:, :], settle_count, axis=0)],
            axis=0,
        )


__all__ = ["JointPositionPlanner", "JointPositionPlannerConfig"]
