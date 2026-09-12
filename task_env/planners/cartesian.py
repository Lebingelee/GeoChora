"""Cartesian pose waypoint planner for TaskEnv action adapters."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..utils.rotation import (
    normalize_quat_wxyz,
    quat_angle_wxyz,
    slerp_quat_wxyz,
)


def _as_pose(pose: np.ndarray) -> np.ndarray:
    value = np.asarray(pose, dtype=np.float64).reshape(7).copy()
    if not np.isfinite(value).all():
        raise ValueError("pose must contain only finite values")
    value[3:7] = normalize_quat_wxyz(value[3:7])
    return value


@dataclass(frozen=True)
class CartesianPosePlannerConfig:
    """Per-control-tick velocity and acceleration limits for 8D pose actions."""

    max_translation_per_step: float = 0.012
    max_translation_acceleration_per_step: float = 0.004
    max_rotation_per_step: float = 0.12
    max_rotation_acceleration_per_step: float = 0.04
    settle_steps: int = 16
    max_steps: int = 200

    def __post_init__(self) -> None:
        if self.max_translation_per_step <= 0.0:
            raise ValueError("max_translation_per_step must be positive")
        if self.max_translation_acceleration_per_step <= 0.0:
            raise ValueError("max_translation_acceleration_per_step must be positive")
        if self.max_rotation_per_step <= 0.0:
            raise ValueError("max_rotation_per_step must be positive")
        if self.max_rotation_acceleration_per_step <= 0.0:
            raise ValueError("max_rotation_acceleration_per_step must be positive")
        if self.settle_steps < 0:
            raise ValueError("settle_steps cannot be negative")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least one")


class CartesianPosePlanner:
    """Generate public 8D Cartesian pose actions for one-step controllers.

    The planner does not call IK, mutate the environment, or advance physics. It
    only expands a pose goal into waypoint actions that can be passed to
    ``env.step`` one by one.
    """

    def __init__(self, config: CartesianPosePlannerConfig | None = None) -> None:
        self.config = config or CartesianPosePlannerConfig()

    def plan_to_pose(
        self,
        *,
        current_pose: np.ndarray,
        goal_pose: np.ndarray,
        steps: int | None = None,
        gripper: float = 1.0,
        max_translation_per_step: float | None = None,
        max_rotation_per_step: float | None = None,
        settle_steps: int | None = None,
    ) -> np.ndarray:
        start = _as_pose(current_pose)
        goal = _as_pose(goal_pose)
        count = self._resolve_step_count(
            start,
            goal,
            steps=steps,
            max_translation_per_step=max_translation_per_step,
            max_rotation_per_step=max_rotation_per_step,
        )
        gripper_value = np.float32(np.clip(float(gripper), -1.0, 1.0))
        actions = np.zeros((count, 8), dtype=np.float32)
        for index in range(count):
            fraction = self._smooth_fraction(index + 1, count)
            actions[index, :3] = (
                (1.0 - fraction) * start[:3] + fraction * goal[:3]
            ).astype(np.float32)
            actions[index, 3:7] = slerp_quat_wxyz(
                start[3:7],
                goal[3:7],
                fraction,
            ).astype(np.float32)
            actions[index, 7] = gripper_value
        return self._append_settle(actions, steps=settle_steps)

    def plan_translation_only(
        self,
        *,
        current_pose: np.ndarray,
        target_position: np.ndarray,
        steps: int | None = None,
        gripper: float = 1.0,
        max_translation_per_step: float | None = None,
        settle_steps: int | None = None,
    ) -> np.ndarray:
        start = _as_pose(current_pose)
        goal = start.copy()
        goal[:3] = np.asarray(target_position, dtype=np.float64).reshape(3)
        count = self._resolve_step_count(
            start,
            goal,
            steps=steps,
            max_translation_per_step=max_translation_per_step,
            max_rotation_per_step=None,
        )
        gripper_value = np.float32(np.clip(float(gripper), -1.0, 1.0))
        actions = np.zeros((count, 8), dtype=np.float32)
        for index in range(count):
            fraction = self._smooth_fraction(index + 1, count)
            actions[index, :3] = (
                (1.0 - fraction) * start[:3] + fraction * goal[:3]
            ).astype(np.float32)
            actions[index, 3:7] = start[3:7].astype(np.float32)
            actions[index, 7] = gripper_value
        return self._append_settle(actions, steps=settle_steps)

    def hold_pose(
        self,
        *,
        pose: np.ndarray,
        steps: int,
        gripper: float,
    ) -> np.ndarray:
        if steps < 1:
            raise ValueError("steps must be at least one")
        target = _as_pose(pose)
        action = np.zeros(8, dtype=np.float32)
        action[:7] = target.astype(np.float32)
        action[7] = np.float32(np.clip(float(gripper), -1.0, 1.0))
        return np.repeat(action[None, :], int(steps), axis=0)

    def hold_current_pose(
        self,
        *,
        current_pose: np.ndarray,
        steps: int,
        gripper: float,
    ) -> np.ndarray:
        return self.hold_pose(pose=current_pose, steps=steps, gripper=gripper)

    def plan_gripper_transition(
        self,
        *,
        pose: np.ndarray,
        start_gripper: float,
        goal_gripper: float,
        steps: int,
        settle_steps: int | None = None,
    ) -> np.ndarray:
        """Change only the public gripper scalar with a smooth profile.

        Keeping the pose columns identical makes this stitch exactly continuous
        with a preceding Cartesian stage whose final pose is ``pose``.
        """
        if steps < 1:
            raise ValueError("steps must be at least one")
        target = _as_pose(pose)
        start = float(np.clip(start_gripper, -1.0, 1.0))
        goal = float(np.clip(goal_gripper, -1.0, 1.0))
        actions = np.zeros((int(steps), 8), dtype=np.float32)
        actions[:, :7] = target.astype(np.float32)
        for index in range(int(steps)):
            fraction = self._smooth_fraction(index + 1, int(steps))
            actions[index, 7] = np.float32((1.0 - fraction) * start + fraction * goal)
        return self._append_settle(actions, steps=settle_steps)

    def _resolve_step_count(
        self,
        start: np.ndarray,
        goal: np.ndarray,
        *,
        steps: int | None,
        max_translation_per_step: float | None,
        max_rotation_per_step: float | None,
    ) -> int:
        requested_count = 1
        if steps is not None:
            if int(steps) < 1:
                raise ValueError("steps must be at least one")
            requested_count = int(steps)
        translation_step = (
            self.config.max_translation_per_step
            if max_translation_per_step is None
            else float(max_translation_per_step)
        )
        rotation_step = (
            self.config.max_rotation_per_step
            if max_rotation_per_step is None
            else float(max_rotation_per_step)
        )
        if translation_step <= 0.0:
            raise ValueError("max_translation_per_step must be positive")
        if rotation_step <= 0.0:
            raise ValueError("max_rotation_per_step must be positive")
        distance = float(np.linalg.norm(goal[:3] - start[:3]))
        angle = quat_angle_wxyz(start[3:7], goal[3:7])
        # Cubic smoothstep s(u)=3u²-2u³ has zero endpoint velocity.  Its
        # largest discrete velocity and acceleration are conservatively bounded
        # by 1.5*distance/N and 6*distance/N², respectively.
        translation_velocity_count = int(math.ceil(1.5 * distance / translation_step))
        rotation_velocity_count = int(math.ceil(1.5 * angle / rotation_step))
        translation_acceleration_count = int(
            math.ceil(
                math.sqrt(
                    6.0 * distance
                    / float(self.config.max_translation_acceleration_per_step)
                )
            )
        )
        rotation_acceleration_count = int(
            math.ceil(
                math.sqrt(
                    6.0
                    * angle
                    / float(self.config.max_rotation_acceleration_per_step)
                )
            )
        )
        count = max(
            requested_count,
            1,
            translation_velocity_count,
            rotation_velocity_count,
            translation_acceleration_count,
            rotation_acceleration_count,
        )
        if count > int(self.config.max_steps):
            raise ValueError(
                f"trajectory needs {count} steps, exceeding max_steps={self.config.max_steps}"
            )
        return count

    @staticmethod
    def _smooth_fraction(step: int, count: int) -> float:
        """Cubic time scaling with zero initial and terminal velocity."""
        u = float(step) / float(count)
        return u * u * (3.0 - 2.0 * u)

    def _append_settle(self, actions: np.ndarray, *, steps: int | None) -> np.ndarray:
        settle_count = self.config.settle_steps if steps is None else int(steps)
        if settle_count < 0:
            raise ValueError("settle_steps cannot be negative")
        if settle_count == 0:
            return actions
        final_action = np.asarray(actions[-1], dtype=np.float32)
        settle_actions = np.repeat(final_action[None, :], settle_count, axis=0)
        return np.concatenate([actions, settle_actions], axis=0)


# The implementation is reference-neutral: it expands an already world-frame
# absolute pose target.  Stage 10 exposes that meaning under the new name while
# retaining the old names until the legacy controller removal in Stage 10f.
AbsolutePosePlanner = CartesianPosePlanner
AbsolutePosePlannerConfig = CartesianPosePlannerConfig


__all__ = [
    "AbsolutePosePlanner",
    "AbsolutePosePlannerConfig",
    "CartesianPosePlanner",
    "CartesianPosePlannerConfig",
]
