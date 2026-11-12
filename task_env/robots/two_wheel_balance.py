"""Two-wheel Robot subject and source declarations."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from ..artifacts import (ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityInstance, FrameDefinition, FrameReference,
    JointDefinition, PoseWorld, RobotInstance, SceneDefinition)

from ..environment import ExternalActionContract
from ..environment.protocols import RobotComponent
from ..registry import register_agent


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


TWO_WHEEL_BALANCE_MJCF_XML = """
<mujoco model="task_env_two_wheel_balance">
  <compiler angle="radian"/>
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="balance_anchor" pos="0 0 0">
      <geom name="balance_anchor_geom" type="cylinder" size="0.06 0.02"
            mass="0" rgba="0.28 0.28 0.32 1"/>
      <body name="balance_chassis" pos="0 0 0">
        <joint name="chassis_pitch" type="hinge" axis="0 1 0"
               damping="0.04"/>
        <inertial pos="0 0 0.45" mass="2.0"
                  diaginertia="0.20 0.20 0.20"/>
        <geom name="balance_chassis_geom" type="box" pos="0 0 0.45"
              size="0.18 0.10 0.45" mass="0"
              rgba="0.20 0.48 0.78 1"/>
        <body name="left_wheel" pos="-0.22 0 0">
          <joint name="left_wheel_hinge" type="hinge" axis="0 1 0"
                 damping="0.01"/>
          <inertial pos="0 0 0" mass="0.25"
                    diaginertia="0.01 0.01 0.01"/>
          <geom name="left_wheel_geom" type="cylinder" size="0.12 0.045"
                mass="0" rgba="0.08 0.08 0.10 1"/>
        </body>
        <body name="right_wheel" pos="0.22 0 0">
          <joint name="right_wheel_hinge" type="hinge" axis="0 1 0"
                 damping="0.01"/>
          <inertial pos="0 0 0" mass="0.25"
                    diaginertia="0.01 0.01 0.01"/>
          <geom name="right_wheel_geom" type="cylinder" size="0.12 0.045"
                mass="0" rgba="0.08 0.08 0.10 1"/>
        </body>
      </body>
    </body>
  </worldbody>
  <contact>
    <exclude body1="balance_anchor" body2="balance_chassis"/>
    <exclude body1="balance_chassis" body2="left_wheel"/>
    <exclude body1="balance_chassis" body2="right_wheel"/>
    <exclude body1="left_wheel" body2="right_wheel"/>
  </contact>
  <actuator>
    <motor name="left_wheel_torque" joint="left_wheel_hinge"
           gear="1" ctrllimited="true" ctrlrange="-1.5 1.5"/>
    <motor name="right_wheel_torque" joint="right_wheel_hinge"
           gear="1" ctrllimited="true" ctrlrange="-1.5 1.5"/>
  </actuator>
</mujoco>
""".strip()

@register_agent("two-wheel-balance-v1")
@dataclass(frozen=True)
class TwoWheelBalanceEntity(RobotComponent):
    """Stable body/joint/actuator names for the two-wheel topology."""

    uid: str = "two-wheel-balance-v1"
    chassis_joint_name: str = "chassis_pitch"
    left_wheel_joint_name: str = "left_wheel_hinge"
    right_wheel_joint_name: str = "right_wheel_hinge"
    left_actuator_name: str = "left_wheel_torque"
    right_actuator_name: str = "right_wheel_torque"
    assembly_id = 'two-wheel-source-assembly'
    source_xml = TWO_WHEEL_BALANCE_MJCF_XML
    source_base_dir = Path(__file__).resolve().parent

    frame_names = ('balance_anchor', 'balance_chassis', 'left_wheel', 'right_wheel')

    @property
    def actuator_names(self):
        return (self.left_actuator_name, self.right_actuator_name)

    def scene_definition(self, *, source_revision=None):
        identity = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
        asset = AssetDefinition('asset-definition-v1', 'two-wheel-inline', 'v1',
            'inline://task-env/two-wheel-balance', source_revision=source_revision,
            source_content_sha256=hashlib.sha256(TWO_WHEEL_BALANCE_MJCF_XML.encode()).hexdigest())
        entity = EntityInstance('entity-instance-v1', self.uid, asset.asset_id, asset.asset_version)
        frames = tuple(FrameDefinition('frame-definition-v1', self.uid, name, 'runtime', None, None)
                       for name in self.frame_names)
        refs = tuple(FrameReference(self.uid, name) for name in self.frame_names)
        offsets = (identity, PoseWorld((-.22, 0., 0.), (1., 0., 0., 0.)),
                   PoseWorld((.22, 0., 0.), (1., 0., 0., 0.)))
        joints = tuple(JointDefinition('joint-definition-v1', name, refs[parent], refs[child],
            offset, identity, 'revolute', (0., 1., 0.), 'radian', 'radian_per_second', 1, 1)
            for name, parent, child, offset in zip(self.state_joint_names, (0, 1, 1), (1, 2, 3), offsets, strict=True))
        articulation = ArticulationDefinition('articulation-definition-v1', self.uid, self.frame_names[0], self.frame_names, joints)
        actuators = tuple(ActuatorResourceDefinition('actuator-resource-v1', self.uid, a) for a in self.actuator_names)
        group = ControlGroup('control-group-v1', self.uid, 'wheel-drive',
            tuple(ActuatorReference(self.uid, a) for a in self.actuator_names))
        return SceneDefinition('scene-definition-v3', 'two-wheel-inline-scene-v1', (asset,),
            (entity,), frames, (articulation,), (RobotInstance('robot-instance-v1', self.uid, (refs[0],)),), actuators, (group,))

    @property
    def state_joint_names(self):
        return (self.chassis_joint_name, self.left_wheel_joint_name, self.right_wheel_joint_name)

    def physical_subject_declaration(self, *, source_id, source_closure_sha256):
        """Describe ordered wheel joints before constructing a control binding."""
        from ..artifacts import FrameReference
        from ..runtime.sessions.physical_control import ControlledSubjectV1, SubjectJointDeclarationV1
        writer, component_paths = 'two-wheel-direct-effort', (('left',), ('right',))
        subject = ControlledSubjectV1(self.uid, self.uid, source_id, source_closure_sha256,
            'references_existing', 'fixed', FrameReference(self.uid, 'balance_anchor'), None,
            component_paths, (writer,),
            supported_controller_profiles=('direct_joint_effort_v1',
                                            'velocity_damped_joint_effort_v1'))
        joints = tuple(SubjectJointDeclarationV1(path, name, (writer,), actuator,
            actuator, 1., (-1.5, 1.5), 'disabled') for path, name, actuator in zip(
                component_paths, (self.left_wheel_joint_name, self.right_wheel_joint_name),
                (self.left_actuator_name, self.right_actuator_name), strict=True))
        return subject, joints



__all__ = [
    "TWO_WHEEL_ACTION_CONTRACT",
    "TWO_WHEEL_ACTION_SCHEMA_ID",
    "TWO_WHEEL_ACTION_SCHEMA_VERSION",
    "TWO_WHEEL_TORQUE_LIMIT_NM",
    "TwoWheelBalanceEntity",
]
