"""Pendulum subject declaration and retained legacy component action adapter.

The scalar selected route binds the source-owned subject to a shared physical
Controller.  The component adapter remains for the existing parallel route.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib

from ..artifacts import (ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityInstance, FrameDefinition, FrameReference,
    JointDefinition, PoseWorld, RobotInstance, SceneDefinition)

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


PENDULUM_MJCF_XML = """
<mujoco model="task_env_pendulum">
  <compiler angle="radian"/>
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="pendulum_anchor" pos="0 0 0">
      <geom name="pendulum_anchor_geom" type="cylinder" size="0.08 0.03"
            mass="0" rgba="0.30 0.30 0.34 1"/>
      <body name="pendulum_link" pos="0 0 0">
        <joint name="pendulum_hinge" type="hinge" axis="0 1 0"
               damping="0.05"/>
        <inertial pos="0 0 0.25" mass="1.0"
                  diaginertia="0.05 0.05 0.05"/>
        <geom name="pendulum_link_geom" type="capsule"
              fromto="0 0 0 0 0 0.50" size="0.04"
              density="1000" rgba="0.16 0.46 0.82 1"/>
      </body>
    </body>
  </worldbody>
  <contact>
    <exclude body1="pendulum_anchor" body2="pendulum_link"/>
  </contact>
  <actuator>
    <motor name="pendulum_torque" joint="pendulum_hinge"
           gear="1" ctrllimited="true" ctrlrange="-2 2"/>
  </actuator>
</mujoco>
""".strip()

@dataclass(frozen=True)
class PendulumEntity(DefaultCanonicalControllerMixin):
    """Stable scene names used by the Pendulum task and adapter."""

    uid: str = "pendulum-v1"
    joint_name: str = "pendulum_hinge"
    actuator_name: str = "pendulum_torque"
    assembly_id = 'pendulum-source-assembly'

    def scene_definition(self, *, source_revision=None):
        origin = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
        source_hash = hashlib.sha256(PENDULUM_MJCF_XML.encode()).hexdigest()
        asset = AssetDefinition('asset-definition-v1', 'pendulum-inline', 'v1',
                                'inline://task-env/pendulum', source_revision=source_revision,
                                source_content_sha256=source_hash)
        entity = EntityInstance('entity-instance-v1', self.uid, asset.asset_id, asset.asset_version)
        frames = tuple(FrameDefinition('frame-definition-v1', self.uid, name, 'runtime', None, None)
                       for name in ('pendulum_anchor', 'pendulum_link'))
        root, link = (FrameReference(self.uid, name) for name in ('pendulum_anchor', 'pendulum_link'))
        joint = JointDefinition('joint-definition-v1', self.joint_name, root, link,
                                origin, origin, 'revolute', (0., 1., 0.),
                                'radian', 'radian_per_second', 1, 1)
        articulation = ArticulationDefinition('articulation-definition-v1', self.uid, 'pendulum_anchor',
            ('pendulum_anchor', 'pendulum_link'), (joint,))
        actuator = ActuatorResourceDefinition('actuator-resource-v1', self.uid, self.actuator_name)
        group = ControlGroup('control-group-v1', self.uid, 'hinge-drive',
                             (ActuatorReference(self.uid, self.actuator_name),))
        return SceneDefinition('scene-definition-v3', 'pendulum-inline-scene-v1', (asset,), (entity,),
            frames, (articulation,), (RobotInstance('robot-instance-v1', self.uid, (root,)),),
            (actuator,), (group,))

    @property
    def state_joint_names(self):
        return (self.joint_name,)

    def physical_subject_declaration(self, *, source_id, source_closure_sha256):
        """Describe the task-owned hinge before constructing a control binding."""
        from ..artifacts import FrameReference
        from ..runtime.sessions.physical_control import ControlledSubjectV1, SubjectJointDeclarationV1
        writer, component_path = 'pendulum-direct-effort', ('hinge',)
        subject = ControlledSubjectV1(self.uid, self.uid, source_id, source_closure_sha256,
            'references_existing', 'fixed', FrameReference(self.uid, 'pendulum_anchor'), None,
            (component_path,), (writer,),
            supported_controller_profiles=('direct_joint_effort_v1',
                                            'velocity_damped_joint_effort_v1'))
        joint = SubjectJointDeclarationV1(component_path, self.joint_name, (writer,),
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
