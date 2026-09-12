"""Panda gripper component owned by the robot layer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..environment import ActionConfig, RuntimeSnapshot
from ..assembly import AgentReferences


@dataclass(frozen=True)
class GripperTarget:
    """One-tick Panda gripper request: opening in metres and force in N."""

    opening_m: float = 0.0
    force_N: float = 5.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.opening_m) or self.opening_m < 0.0:
            raise ValueError("gripper opening_m must be finite and non-negative")
        if not np.isfinite(self.force_N) or self.force_N < 0.0:
            raise ValueError("gripper force_N must be finite and non-negative")


class PandaGripperController:
    """Force-limited Panda tendon-position controller.

    Closing error is bounded by ``force_limit_N / stiffness`` at every public
    control tick.  When bound to a TaskEnv runtime, the same value is written
    to the task-owned actuator ``forcerange`` as its physical hard cap.
    """

    def __init__(
        self,
        *,
        references: AgentReferences,
        config: ActionConfig,
        force_limit_N: float | None = None,
    ) -> None:
        self.references = references
        self.config = config
        initial_force = (
            config.gripper_default_force_N
            if force_limit_N is None
            else force_limit_N
        )
        self._force_N = self._validated_force_limit_N(initial_force)
        self._force_limit_writer = None

    @staticmethod
    def _validated_force_limit_N(force_limit_N: float) -> float:
        value = float(force_limit_N)
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError("gripper force_limit_N must be finite and positive")
        return value

    @property
    def force_limit_N(self) -> float:
        """Return the active physical actuator force limit in Newtons."""

        return float(self._force_N)

    @property
    def force_N(self) -> float:
        """Compatibility alias for :attr:`force_limit_N`."""

        return self.force_limit_N

    @property
    def force_limit_is_physical(self) -> bool:
        """Whether the active limit is connected to TaskEnv's runtime contract."""

        return self._force_limit_writer is not None

    def set_force_limit_N(self, force_limit_N: float) -> None:
        """Temporarily set the physical gripper actuator limit in Newtons.

        When the controller belongs to a live TaskEnv, this also updates the
        task-owned actuator ``forcerange`` through the public runtime boundary.
        """

        self._force_N = self._validated_force_limit_N(force_limit_N)
        if self._force_limit_writer is not None:
            self._force_limit_writer(
                self.references.gripper_actuator_ids,
                self.force_limit_N,
            )

    def set_force(self, force: float) -> None:
        """Compatibility alias for :meth:`set_force_limit_N`."""

        self.set_force_limit_N(force)

    def bind_force_limit(self, runtime_boundary) -> None:
        """Bind the public TaskEnv actuator force-limit operation."""

        writer = getattr(runtime_boundary, "set_actuator_force_limits", None)
        if not callable(writer):
            raise ValueError("runtime boundary does not expose actuator force limits")
        self._force_limit_writer = writer
        self._force_limit_writer(
            self.references.gripper_actuator_ids,
            self.force_limit_N,
        )

    def move_gripper_m(
        self,
        value: float = 0.0,
        force: float | None = None,
    ) -> GripperTarget:
        """Request a target opening and the selected force in Newtons."""

        if force is not None:
            # The legacy argument remains usable, but now changes the one
            # authoritative force-limit state rather than a per-target shadow.
            self.set_force_limit_N(force)
        return GripperTarget(opening_m=float(value), force_N=self.force_limit_N)

    def normalized_target(self, command: float) -> GripperTarget:
        alpha = 0.5 * (float(np.clip(command, -1.0, 1.0)) + 1.0)
        return self.move_gripper_m(
            value=alpha * self.config.gripper_opening_range_m,
        )

    def ctrl_for_target(
        self,
        *,
        snapshot: RuntimeSnapshot,
        target: GripperTarget,
    ) -> float:
        if snapshot.qpos is None:
            raise ValueError("Panda gripper control requires snapshot qpos")
        qpos_ids = self.references.gripper_qpos_ids
        if qpos_ids.size == 0:
            raise ValueError("Panda gripper control requires gripper qpos ids")
        current_opening = float(np.sum(snapshot.qpos[qpos_ids], dtype=np.float64))
        requested_opening = float(
            np.clip(target.opening_m, 0.0, self.config.gripper_opening_range_m)
        )
        opening_error = requested_opening - current_opening
        if abs(opening_error) > 1.0e-12:
            max_motion = float(target.force_N) / self.config.gripper_position_stiffness_N_per_m
            requested_opening = current_opening + np.clip(
                opening_error,
                -max_motion,
                max_motion,
            )
        alpha = requested_opening / self.config.gripper_opening_range_m
        return float(
            (1.0 - alpha) * self.config.gripper_close_ctrl
            + alpha * self.config.gripper_open_ctrl
        )


class ExperimentalPandaGripperController(PandaGripperController):
    """实验用的速率受限 Panda 位置夹爪控制器。

    与 :class:`PandaGripperController` 隔离：该类只在配置显式选择时创建。它
    维护独立的 ``commanded_opening_m``，不会把接触时的 finger qpos 波动当作下一
    帧的位置命令。接近阶段使用固定开口速率；检测到 actuator closing force 后，
    用一次 opening 采样建立保持目标，随后仅在保持力不足时以测得的 actuator
    force 小步闭合；不会因位置顺应或较高接触力反向打开。
    ``set_force_limit_N`` 经 TaskEnv 公开 runtime boundary 映射到 actuator 的
    真实 ``forcerange``，而不再承担位置步长语义。
    """

    def __init__(
        self,
        *,
        references: AgentReferences,
        config: ActionConfig,
        force_limit_N: float,
        max_opening_step_m: float,
        force_deadband_N: float = 1.0,
        force_adjust_step_m: float = 1.0e-4,
    ) -> None:
        super().__init__(
            references=references,
            config=config,
            force_limit_N=force_limit_N,
        )
        step = float(max_opening_step_m)
        if not np.isfinite(step) or step <= 0.0:
            raise ValueError("max_opening_step_m must be finite and positive")
        if not np.isfinite(force_deadband_N) or force_deadband_N < 0.0:
            raise ValueError("force_deadband_N must be finite and non-negative")
        if not np.isfinite(force_adjust_step_m) or force_adjust_step_m <= 0.0:
            raise ValueError("force_adjust_step_m must be finite and positive")
        self.max_opening_step_m = step
        self.force_deadband_N = float(force_deadband_N)
        self.force_adjust_step_m = float(force_adjust_step_m)
        self._commanded_opening_m: float | None = None
        self._force_mode_active = False
        self._force_mode_initialized = False

    @property
    def force_mode_active(self) -> bool:
        """Whether this close cycle is regulating measured actuator force."""

        return bool(self._force_mode_active)

    @property
    def commanded_opening_m(self) -> float | None:
        """Return the persistent opening target used for the next actuator ctrl."""

        return self._commanded_opening_m

    @property
    def effective_hold_force_N(self) -> float:
        """Return the contact setpoint, equal to the physical force limit."""

        return self.force_limit_N

    def set_opening_step_m(self, opening_step_m: float) -> None:
        """Temporarily set the persistent opening change bound per control tick."""

        value = float(opening_step_m)
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError("gripper opening_step_m must be finite and positive")
        self.max_opening_step_m = value

    def set_force_deadband_N(self, force_deadband_N: float) -> None:
        """Temporarily set the one-sided force-regulation deadband."""

        value = float(force_deadband_N)
        if not np.isfinite(value) or value < 0.0:
            raise ValueError("gripper force_deadband_N must be finite and non-negative")
        self.force_deadband_N = value

    def set_force_adjust_step_m(self, force_adjust_step_m: float) -> None:
        """Temporarily set the closing correction used when force is insufficient."""

        value = float(force_adjust_step_m)
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError("gripper force_adjust_step_m must be finite and positive")
        self.force_adjust_step_m = value

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        """Seed the persistent command once per environment reset."""

        if snapshot.qpos is None:
            raise ValueError("experimental Panda gripper reset requires snapshot qpos")
        qpos_ids = self.references.gripper_qpos_ids
        if qpos_ids.size == 0:
            raise ValueError("experimental Panda gripper reset requires gripper qpos ids")
        opening = float(np.sum(snapshot.qpos[qpos_ids], dtype=np.float64))
        self._commanded_opening_m = float(
            np.clip(opening, 0.0, self.config.gripper_opening_range_m)
        )
        self._force_mode_active = False
        self._force_mode_initialized = False

    def ctrl_for_target(
        self,
        *,
        snapshot: RuntimeSnapshot,
        target: GripperTarget,
    ) -> float:
        if self._commanded_opening_m is None:
            self.reset(snapshot)
        requested_opening = float(
            np.clip(target.opening_m, 0.0, self.config.gripper_opening_range_m)
        )
        if self._commanded_opening_m is None:
            raise RuntimeError("experimental Panda gripper command was not initialized")
        opening_delta = requested_opening - self._commanded_opening_m
        if opening_delta > 1.0e-12:
            # An explicit opening command starts a fresh close cycle.
            self._force_mode_active = False
            self._force_mode_initialized = False
        closing = opening_delta < -1.0e-12
        if snapshot.actuator_force is None:
            raise ValueError("experimental Panda gripper requires actuator-force snapshot")
        actuator_ids = self.references.gripper_actuator_ids
        if actuator_ids.size != 1:
            raise ValueError("experimental Panda gripper requires one actuator")
        actuator_force = float(snapshot.actuator_force[int(actuator_ids[0])])
        hold_force = self.effective_hold_force_N
        activation_force = max(0.5, 0.1 * hold_force)
        if closing and not self._force_mode_active and actuator_force <= -activation_force:
            self._force_mode_active = True
        if closing and self._force_mode_active:
            if not self._force_mode_initialized:
                # 只在进入接触保持模式的首帧读取实际 opening。后续不再追随
                # finger qpos；否则物体的缓慢顺应会被放大为持续增大的位置命令。
                actual_opening = float(
                    np.sum(snapshot.qpos[self.references.gripper_qpos_ids], dtype=np.float64)
                )
                self._commanded_opening_m = float(
                    np.clip(
                        actual_opening
                        - hold_force / self.config.gripper_position_stiffness_N_per_m,
                        0.0,
                        self.config.gripper_opening_range_m,
                    )
                )
                self._force_mode_initialized = True
            force_error = actuator_force + hold_force
            if force_error > self.force_deadband_N:
                self._commanded_opening_m = float(
                    max(0.0, self._commanded_opening_m - self.force_adjust_step_m)
                )
        elif not self._force_mode_active:
            delta = float(
                np.clip(
                    opening_delta,
                    -self.max_opening_step_m,
                    self.max_opening_step_m,
                )
            )
            self._commanded_opening_m = float(
                np.clip(
                    self._commanded_opening_m + delta,
                    0.0,
                    self.config.gripper_opening_range_m,
                )
            )
        alpha = self._commanded_opening_m / self.config.gripper_opening_range_m
        return float(
            (1.0 - alpha) * self.config.gripper_close_ctrl
            + alpha * self.config.gripper_open_ctrl
        )


__all__ = [
    "ExperimentalPandaGripperController",
    "GripperTarget",
    "PandaGripperController",
]
