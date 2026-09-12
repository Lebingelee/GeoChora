"""Pendulum native torque action adapter.

This is deliberately not an ``AgentComponent``: the task has no robot
controller.  Its native action is already the runtime-facing canonical
``universal_action``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from gymnasium.spaces import Box, Dict

from ..environment import ControlCommand, ExternalActionContract, RuntimeSnapshot


PENDULUM_ACTION_SCHEMA_ID = "task-env.pendulum.torque.v1"
PENDULUM_ACTION_SCHEMA_VERSION = "task-env-action-v1"
PENDULUM_TORQUE_LIMIT_NM = 2.0


PENDULUM_ACTION_CONTRACT = ExternalActionContract(
    mode="direct_torque",
    dimension=1,
    components=("torque",),
    low=-PENDULUM_TORQUE_LIMIT_NM,
    high=PENDULUM_TORQUE_LIMIT_NM,
    controller_backend="direct_actuator_torque",
    actuator_control_mode="torque",
    schema_id=PENDULUM_ACTION_SCHEMA_ID,
    schema_version=PENDULUM_ACTION_SCHEMA_VERSION,
    unit="N*m",
    actuator_interpretation="pendulum_hinge_torque",
    task_family="pendulum",
)


@dataclass(frozen=True)
class PendulumEntity:
    """Stable scene names used by the Pendulum task and adapter."""

    uid: str = "pendulum-v1"
    joint_name: str = "pendulum_hinge"
    actuator_name: str = "pendulum_torque"


class PendulumTorqueActionAdapter:
    """Convert the one-dimensional native action into one actuator command."""

    action_contract = PENDULUM_ACTION_CONTRACT

    def __init__(self, *, actuator_id: int, actuator_count: int) -> None:
        if actuator_id < 0 or actuator_id >= actuator_count:
            raise ValueError("Pendulum actuator id is outside the compiled actuator range")
        self._actuator_id = int(actuator_id)
        self._actuator_count = int(actuator_count)
        self._torque_space = Box(
            low=np.asarray([PENDULUM_ACTION_CONTRACT.low], dtype=np.float32),
            high=np.asarray([PENDULUM_ACTION_CONTRACT.high], dtype=np.float32),
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
                raise ValueError("Pendulum action tree must contain only torque")
            action = action["torque"]
        value = np.asarray(action, dtype=np.float32)
        if value.shape != (1,):
            raise ValueError(f"Pendulum action shape must be (1,), got {value.shape}")
        if not np.isfinite(value).all():
            raise ValueError("Pendulum action must contain only finite values")
        if not self._torque_space.contains(value):
            raise ValueError(
                "Pendulum torque action is outside the declared native bounds"
            )

        ctrl = (
            np.zeros(self._actuator_count, dtype=np.float32)
            if snapshot.ctrl is None
            else np.asarray(snapshot.ctrl, dtype=np.float32).copy()
        )
        if ctrl.shape != (self._actuator_count,):
            raise ValueError("Pendulum snapshot ctrl shape does not match compiled actuators")
        torque = np.asarray(value, dtype=np.float32).copy()
        ctrl[self._actuator_id] = torque[0]
        return ControlCommand(
            actuator_ctrl=ctrl,
            external_action=torque,
            requested_action=torque,
            controller_target=torque,
            # No controller is present: the native action is already the
            # runtime-facing canonical universal action.
            universal_action=torque,
            mode="direct_torque",
        )

    def convert_batch(self, action: np.ndarray, state) -> np.ndarray:
        """Convert the native tree-normalized action for all slots at once."""

        del state
        if isinstance(action, Mapping):
            if tuple(action.keys()) != ("torque",):
                raise ValueError("Pendulum batch action tree must contain only torque")
            action = action["torque"]
        value = np.asarray(action, dtype=np.float32)
        if value.ndim != 2 or value.shape[1:] != (1,):
            raise ValueError("Pendulum batch action must have shape (B, 1)")
        if not np.isfinite(value).all() or np.any(
            value < PENDULUM_ACTION_CONTRACT.low
        ) or np.any(value > PENDULUM_ACTION_CONTRACT.high):
            raise ValueError("Pendulum batch torque is outside the declared bounds")
        control = np.zeros((value.shape[0], self._actuator_count), dtype=np.float32)
        control[:, self._actuator_id] = value[:, 0]
        return control


__all__ = [
    "PENDULUM_ACTION_CONTRACT",
    "PENDULUM_ACTION_SCHEMA_ID",
    "PENDULUM_ACTION_SCHEMA_VERSION",
    "PENDULUM_TORQUE_LIMIT_NM",
    "PendulumEntity",
    "PendulumTorqueActionAdapter",
]
