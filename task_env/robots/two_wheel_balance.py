"""Native torque adapter for the Stage 12b two-wheel balance task."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from gymnasium.spaces import Box, Dict

from ..environment import ControlCommand, ExternalActionContract, RuntimeSnapshot


TWO_WHEEL_ACTION_SCHEMA_ID = "task-env.two-wheel-balance.wheel-torque.v1"
TWO_WHEEL_ACTION_SCHEMA_VERSION = "task-env-action-v1"
TWO_WHEEL_TORQUE_LIMIT_NM = 1.5


TWO_WHEEL_ACTION_CONTRACT = ExternalActionContract(
    mode="direct_wheel_torque",
    dimension=2,
    components=("left_wheel_torque", "right_wheel_torque"),
    low=-TWO_WHEEL_TORQUE_LIMIT_NM,
    high=TWO_WHEEL_TORQUE_LIMIT_NM,
    controller_backend="direct_actuator_torque",
    actuator_control_mode="torque",
    schema_id=TWO_WHEEL_ACTION_SCHEMA_ID,
    schema_version=TWO_WHEEL_ACTION_SCHEMA_VERSION,
    unit="N*m",
    actuator_interpretation="left_right_wheel_hinge_torque",
    task_family="two_wheel_balance",
)


@dataclass(frozen=True)
class TwoWheelBalanceEntity:
    """Stable body/joint/actuator names for the two-wheel topology."""

    uid: str = "two-wheel-balance-v1"
    chassis_joint_name: str = "chassis_pitch"
    left_wheel_joint_name: str = "left_wheel_hinge"
    right_wheel_joint_name: str = "right_wheel_hinge"
    left_actuator_name: str = "left_wheel_torque"
    right_actuator_name: str = "right_wheel_torque"


class TwoWheelTorqueActionAdapter:
    """Resolve left/right native torques into their matching actuators."""

    action_contract = TWO_WHEEL_ACTION_CONTRACT

    def __init__(self, *, actuator_ids: tuple[int, int], actuator_count: int) -> None:
        if len(actuator_ids) != 2:
            raise ValueError("Two-wheel action adapter requires two actuator ids")
        if any(index < 0 or index >= actuator_count for index in actuator_ids):
            raise ValueError("Two-wheel actuator id is outside the compiled actuator range")
        if actuator_ids[0] == actuator_ids[1]:
            raise ValueError("Two-wheel left/right actuators must be distinct")
        self._actuator_ids = tuple(int(index) for index in actuator_ids)
        self._actuator_count = int(actuator_count)
        self._torque_space = Box(
            low=np.full(2, -TWO_WHEEL_TORQUE_LIMIT_NM, dtype=np.float32),
            high=np.full(2, TWO_WHEEL_TORQUE_LIMIT_NM, dtype=np.float32),
            dtype=np.float32,
        )
        # Public action tree; H5 writes this leaf as ``action/torque``.
        self.action_space = Dict({"torque": self._torque_space})

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        del snapshot

    def convert(
        self,
        action: np.ndarray,
        snapshot: RuntimeSnapshot,
    ) -> ControlCommand:
        if isinstance(action, Mapping):
            if tuple(action.keys()) != ("torque",):
                raise ValueError("Two-wheel action tree must contain only torque")
            action = action["torque"]
        value = np.asarray(action, dtype=np.float32)
        if value.shape != (2,):
            raise ValueError(f"Two-wheel action shape must be (2,), got {value.shape}")
        if not np.isfinite(value).all():
            raise ValueError("Two-wheel action must contain only finite values")
        if not self._torque_space.contains(value):
            raise ValueError("Two-wheel torque action is outside the declared native bounds")

        del snapshot
        ctrl = np.zeros(self._actuator_count, dtype=np.float32)
        if ctrl.shape != (self._actuator_count,):
            raise ValueError("Two-wheel snapshot ctrl shape does not match compiled actuators")
        universal = value.copy()
        ctrl[self._actuator_ids[0]] = universal[0]
        ctrl[self._actuator_ids[1]] = universal[1]
        return ControlCommand(
            actuator_ctrl=ctrl,
            external_action=universal,
            requested_action=universal,
            controller_target=universal,
            # No controller is present: the native action is already the
            # runtime-facing canonical universal action.
            universal_action=universal,
            mode="direct_wheel_torque",
        )

    def convert_batch(self, action, state) -> np.ndarray:
        """Convert the public torque tree for all slots in one host pass."""

        del state
        if isinstance(action, Mapping):
            if tuple(action.keys()) != ("torque",):
                raise ValueError("Two-wheel batch action tree must contain only torque")
            action = action["torque"]
        value = np.asarray(action, dtype=np.float32)
        expected = (value.shape[0], 2) if value.ndim == 2 else None
        if expected is None or value.shape != expected:
            raise ValueError("Two-wheel batch action must have shape (B, 2)")
        if not np.isfinite(value).all() or np.any(
            value < -TWO_WHEEL_TORQUE_LIMIT_NM
        ) or np.any(value > TWO_WHEEL_TORQUE_LIMIT_NM):
            raise ValueError("Two-wheel batch torque is outside the declared bounds")
        control = np.zeros((value.shape[0], self._actuator_count), dtype=np.float32)
        control[:, self._actuator_ids[0]] = value[:, 0]
        control[:, self._actuator_ids[1]] = value[:, 1]
        return control


__all__ = [
    "TWO_WHEEL_ACTION_CONTRACT",
    "TWO_WHEEL_ACTION_SCHEMA_ID",
    "TWO_WHEEL_ACTION_SCHEMA_VERSION",
    "TWO_WHEEL_TORQUE_LIMIT_NM",
    "TwoWheelBalanceEntity",
    "TwoWheelTorqueActionAdapter",
]
