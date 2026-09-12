"""Controller-level immutable contracts for TaskEnv action adapters.

These contracts describe resolved controller targets and actuator commands.  They
do not own a solver, upload ``ctrl``, or advance simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from ..environment import ControlCommand, RuntimeSnapshot


def _readonly_vector(value: np.ndarray, *, name: str, size: int) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32).reshape(-1).copy()
    if array.shape != (size,):
        raise ValueError(f"{name} must have shape {(size,)}, got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class JointTarget:
    """Resolved joint-space position target for one control tick.

    ``provenance`` records how the public action was interpreted; the stored
    value is always an absolute joint target, never a torque or acceleration.
    """

    positions: np.ndarray
    provenance: str = "absolute"

    def __post_init__(self) -> None:
        positions = np.asarray(self.positions, dtype=np.float32).reshape(-1).copy()
        if positions.size == 0:
            raise ValueError("joint target cannot be empty")
        if not np.isfinite(positions).all():
            raise ValueError("joint target positions must be finite")
        provenance = str(self.provenance).strip()
        if provenance not in {
            "absolute",
            "delta_from_achieved",
            "delta_from_target",
            "ik_solution",
        }:
            raise ValueError(f"unsupported joint target provenance: {provenance}")
        positions.setflags(write=False)
        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "provenance", provenance)


@dataclass(frozen=True)
class PoseTarget:
    """Resolved world-frame EE pose target for one control tick."""

    position: np.ndarray
    quaternion_wxyz: np.ndarray
    provenance: str = "absolute"

    def __post_init__(self) -> None:
        position = _readonly_vector(self.position, name="position", size=3)
        quaternion = _readonly_vector(
            self.quaternion_wxyz,
            name="quaternion_wxyz",
            size=4,
        )
        norm = float(np.linalg.norm(quaternion))
        if norm <= 1.0e-8:
            raise ValueError("quaternion_wxyz norm must be positive")
        quaternion = (quaternion / np.float32(norm)).astype(np.float32, copy=False)
        quaternion.setflags(write=False)
        provenance = str(self.provenance).strip()
        if provenance not in {
            "absolute",
            "delta_from_achieved",
            "delta_from_target",
        }:
            raise ValueError(f"unsupported pose target provenance: {provenance}")
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "quaternion_wxyz", quaternion)
        object.__setattr__(self, "provenance", provenance)


@dataclass(frozen=True)
class ActuatorCommand:
    """One tick of actuator ``ctrl`` values plus its resolved controller target.

    The current TaskEnv runtime accepts only ``ctrl`` commands.  ``control_mode``
    therefore declares the actuator interpretation required by the selected
    backend, rather than changing solver semantics by itself.
    """

    actuator_ctrl: np.ndarray
    control_mode: str
    joint_target: JointTarget | None = None
    pose_target: PoseTarget | None = None

    def __post_init__(self) -> None:
        ctrl = np.asarray(self.actuator_ctrl, dtype=np.float32).reshape(-1).copy()
        if not np.isfinite(ctrl).all():
            raise ValueError("actuator_ctrl must contain only finite values")
        control_mode = str(self.control_mode).strip()
        if control_mode not in {"position", "velocity", "torque", "direct"}:
            raise ValueError(f"unsupported actuator control mode: {control_mode}")
        ctrl.setflags(write=False)
        object.__setattr__(self, "actuator_ctrl", ctrl)
        object.__setattr__(self, "control_mode", control_mode)


class Controller(Protocol):
    """Public one-control-tick controller contract.

    ``convert`` returns the existing RuntimeBoundary command type so controller
    migration does not alter the frozen ``env.step(action)`` boundary.
    """

    @property
    def action_space(self) -> Any: ...

    def reset(self, snapshot: RuntimeSnapshot) -> None: ...

    def convert(
        self,
        action: np.ndarray,
        snapshot: RuntimeSnapshot,
    ) -> ControlCommand: ...


__all__ = ["ActuatorCommand", "Controller", "JointTarget", "PoseTarget"]
