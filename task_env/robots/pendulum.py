"""Pendulum subject declaration and retained legacy component action adapter.

The scalar selected route binds the source-owned subject to a shared physical
Controller.  The component adapter remains for the existing parallel route.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from ..environment.gym_compat import Box, Dict

from ..environment import ControlCommand, ExternalActionContract, RuntimeSnapshot
from ..environment.protocols import DefaultCanonicalControllerMixin


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
class PendulumEntity(DefaultCanonicalControllerMixin):
    """Stable scene names used by the Pendulum task and adapter."""

    uid: str = "pendulum-v1"
    joint_name: str = "pendulum_hinge"
    actuator_name: str = "pendulum_torque"

    def physical_subject_declaration(self, *, source_id, source_closure_sha256,
                                     entity_id, root_frame, controller_writer,
                                     component_path):
        """Describe the task-owned hinge before constructing a control binding."""
        from ..artifacts import FrameReference
        from ..runtime.sessions.physical_control import ControlledSubjectV1, SubjectJointDeclarationV1
        subject = ControlledSubjectV1(self.uid, entity_id, source_id, source_closure_sha256,
            'references_existing', 'fixed', FrameReference(entity_id, root_frame), None,
            (component_path,), (controller_writer,),
            supported_controller_profiles=('direct_joint_effort_v1',
                                            'velocity_damped_joint_effort_v1'))
        joint = SubjectJointDeclarationV1(component_path, self.joint_name, (controller_writer,),
            self.actuator_name, self.actuator_name, 1., (-2., 2.), 'disabled')
        return subject, (joint,)

    def controlled_subject(self, *, binding, entity_id, root_frame, controller_writer):
        """Declare the source-owned hinge without constructing a second body."""
        from ..artifacts import FrameReference
        from ..runtime.sessions.physical_control import ControlledSubjectV1
        channels = tuple(c for c in binding.channels if c.entity_id == entity_id)
        if (len(channels) != 1 or channels[0].joint_id != self.joint_name
                or channels[0].native_actuator != self.actuator_name
                or channels[0].unit != 'N*m' or channels[0].effort_range != (-2., 2.)):
            raise ValueError('Pendulum subject requires its declared hinge torque channel')
        return ControlledSubjectV1(self.uid, entity_id, binding.source_id,
            binding.source_closure_sha256, 'references_existing', 'fixed',
            FrameReference(entity_id, root_frame), None,
            (channels[0].component_path,), (controller_writer,),
            supported_controller_profiles=('direct_joint_effort_v1',
                                            'velocity_damped_joint_effort_v1'))


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
