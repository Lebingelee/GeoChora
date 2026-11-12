"""Pendulum Robot subject and source declarations."""

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

@register_agent("pendulum-v1")
@dataclass(frozen=True)
class PendulumEntity(RobotComponent):
    """Stable scene names used by the Pendulum task and adapter."""

    observer_source_family = 'inline-articulation-v1'
    uid: str = "pendulum-v1"
    joint_name: str = "pendulum_hinge"
    actuator_name: str = "pendulum_torque"
    assembly_id = 'pendulum-source-assembly'
    source_xml = PENDULUM_MJCF_XML
    source_base_dir = Path(__file__).resolve().parent
    controller_profiles = ('direct_joint_effort_v1', 'velocity_damped_joint_effort_v1')
    action_contract = PENDULUM_ACTION_CONTRACT

    @classmethod
    def physical_controller_kinds(cls):
        return {profile: 'joint-effort' for profile in cls.controller_profiles}

    def scene_definition(self, *, source_revision=None):
        origin = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
        source_hash = hashlib.sha256(self.source_xml.encode()).hexdigest()
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

    def source_recipe(self):
        """Declare the inline source and its Controller-owned hinge writer."""
        from .source_recipe import RobotSourceRecipeV1, RobotSourceReferenceV1
        revision = hashlib.sha256(self.source_xml.encode()).hexdigest()
        return RobotSourceRecipeV1(self.uid, 'reference-task-source', (
            RobotSourceReferenceV1(f'{self.uid}/inline', 'inline://task-env/pendulum',
                                   revision, (self.uid,)),), (), (self.joint_name,),
            self.controller_profiles, ((self.uid, self.actuator_name, 'pendulum-direct-effort'),))

    def physical_subject_declaration(self, *, source_id, source_closure_sha256):
        """Describe the task-owned hinge before constructing a control binding."""
        from ..artifacts import FrameReference
        from ..runtime.sessions.physical_control import ControlledSubjectV1, SubjectJointDeclarationV1
        writer, component_path = 'pendulum-direct-effort', ('hinge',)
        subject = ControlledSubjectV1(self.uid, self.uid, source_id, source_closure_sha256,
            'references_existing', 'fixed', FrameReference(self.uid, 'pendulum_anchor'), None,
            (component_path,), (writer,),
            supported_controller_profiles=self.controller_profiles)
        joint = SubjectJointDeclarationV1(component_path, self.joint_name, (writer,),
            self.actuator_name, self.actuator_name, 1.,
            (-PENDULUM_TORQUE_LIMIT_NM, PENDULUM_TORQUE_LIMIT_NM), 'disabled')
        return subject, (joint,)



__all__ = [
    "PENDULUM_ACTION_CONTRACT",
    "PENDULUM_ACTION_SCHEMA_ID",
    "PENDULUM_ACTION_SCHEMA_VERSION",
    "PENDULUM_TORQUE_LIMIT_NM",
    "PendulumEntity",
]
