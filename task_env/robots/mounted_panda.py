"""Declarations for a Panda arm already mounted in a task-owned MJCF source.

Only the seven named torque motors are exposed as canonical effort channels.
The task's independent gripper position actuators remain source-owned.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import xml.etree.ElementTree as ET

from ..artifacts import (ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityInstance, FrameDefinition, FrameReference,
    JointDefinition, PoseWorld, RobotInstance, SceneDefinition)
from ..environment.protocols import RobotComponent
from .source_recipe import RobotSourceRecipeV1, RobotSourceReferenceV1


@dataclass(frozen=True)
class MountedPandaArm(RobotComponent):
    """A reference to an existing named arm; it never imports a second robot."""
    source_id: str
    source_closure_sha256: str
    uid: str = 'panda-v1'
    assembly_id = 'mounted-panda-arm-effort'
    controller_profiles = ('direct_joint_effort_v1', 'source_osc_pose_v1')
    writer_id = 'mounted-panda-arm-effort'

    @property
    def state_joint_names(self):
        return tuple(f'robot0_joint{i}' for i in range(1, 8))

    def source_recipe(self):
        return RobotSourceRecipeV1(self.uid, 'reference-task-source', (
            RobotSourceReferenceV1(self.source_id, 'task-source://mounted-panda',
                                   self.source_closure_sha256, (self.uid,)),), (),
            self.state_joint_names, self.controller_profiles,
            tuple((self.uid, f'robot0_torq_j{i}', self.writer_id) for i in range(1, 8)))

    def physical_subject_declaration(self, *, source_xml):
        from ..runtime.sessions.physical_control import ControlledSubjectV1, SubjectJointDeclarationV1
        root = ET.fromstring(source_xml)
        named_bodies = [node for node in root.iter('body') if node.get('name')]
        bodies = {node.get('name'): node for node in named_bodies}
        if len(bodies) != len(named_bodies):
            raise ValueError('mounted Panda source contains duplicate body names')
        parents = {child: parent for parent in root.iter() for child in parent}
        base = bodies.get('robot0_base')
        link0 = bodies.get('robot0_link0')
        if (base is None or parents.get(base) is not root.find('worldbody')
                or base.find('joint') is not None or base.find('freejoint') is not None
                or link0 is None or parents.get(link0) is not base
                or link0.find('joint') is not None or link0.find('freejoint') is not None):
            raise ValueError('mounted Panda root must be a fixed world child')
        paths, declarations = [], []
        for i, name in enumerate(self.state_joint_names, 1):
            body = bodies.get(f'robot0_link{i}')
            parent = bodies.get(f'robot0_link{i-1}')
            joints = [] if body is None else body.findall(f"joint[@name='{name}']")
            motors = root.findall(f"./actuator/motor[@name='robot0_torq_j{i}']")
            joint = joints[0] if len(joints) == 1 else None
            motor = motors[0] if len(motors) == 1 else None
            if (body is None or parent is None or parents.get(body) is not parent or joint is None
                    or joint.get('type', 'hinge') != 'hinge'
                    or motor is None or motor.get('joint') != name
                    or motor.get('ctrllimited') != 'true'):
                raise ValueError('mounted Panda arm joint or motor mapping differs from source')
            axis = tuple(float(v) for v in joint.get('axis', '0 0 1').split())
            limits = tuple(float(v) for v in motor.get('ctrlrange', '').split())
            gear = tuple(float(v) for v in motor.get('gear', '1').split())
            if (len(axis) != 3 or not all(math.isfinite(v) for v in axis)
                    or abs(sum(v*v for v in axis) - 1) > 1e-9
                    or len(limits) != 2 or not all(math.isfinite(v) for v in limits)
                    or not limits[0] < 0 < limits[1] or gear != (1.,)):
                raise ValueError('mounted Panda motor axis, gear or range differs from declaration')
            path = ('arm', name)
            paths.append(path)
            declarations.append(SubjectJointDeclarationV1(path, name, (self.writer_id,),
                f'robot0_torq_j{i}', f'robot0_torq_j{i}', 1., limits, 'disabled'))
        subject = ControlledSubjectV1(self.uid, self.uid, self.source_id, self.source_closure_sha256,
            'references_existing', 'fixed', FrameReference(self.uid, 'robot0_base'), None,
            tuple(paths), (self.writer_id,), supported_controller_profiles=self.controller_profiles)
        return subject, tuple(declarations)

    def scene_definition(self, *, source_xml, scene_id):
        """Project named arm links from the existing task source into a typed Scene."""
        subject, declarations = self.physical_subject_declaration(source_xml=source_xml)
        del subject
        root = ET.fromstring(source_xml)
        bodies = {node.get('name'): node for node in root.iter('body') if node.get('name')}
        subtree = bodies['robot0_base']
        nodes = tuple(subtree.iter('body'))
        names = tuple(node.get('name') for node in nodes)
        if any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError('mounted Panda bodies require unique names')
        parents = {child: parent for parent in subtree.iter() for child in parent}
        origin = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
        frames = [FrameDefinition('frame-definition-v1', self.uid, name, 'runtime', None, None)
                  for name in names]
        def body_pose(body):
            position = tuple(float(v) for v in body.get('pos', '0 0 0').split())
            quat = tuple(float(v) for v in body.get('quat', '1 0 0 0').split())
            if len(position) != 3 or len(quat) != 4 or not all(math.isfinite(v) for v in (*position, *quat)):
                raise ValueError('mounted Panda body pose is invalid')
            norm = math.sqrt(sum(v*v for v in quat))
            if norm == 0:
                raise ValueError('mounted Panda body quaternion is zero')
            return PoseWorld(position, tuple(v / norm for v in quat))

        joints = []
        for body in nodes[1:]:
            name = body.get('name')
            parent = parents[body]
            declared = body.findall('joint')
            if len(declared) > 1 or body.find('freejoint') is not None:
                raise ValueError('mounted Panda requires at most one scalar joint per body')
            if declared:
                joint = declared[0]
                kind = {'hinge': ('revolute', 'radian', 'radian_per_second'),
                        'slide': ('prismatic', 'meter', 'meter_per_second')}.get(joint.get('type', 'hinge'))
                axis = tuple(float(v) for v in joint.get('axis', '0 0 1').split())
                if (kind is None or not joint.get('name')
                        or tuple(float(v) for v in joint.get('pos', '0 0 0').split()) != (0., 0., 0.)):
                    raise ValueError('mounted Panda joint declaration is unsupported')
                joint_id = joint.get('name')
                joint_kind, position_unit, velocity_unit = kind
                sizes = (1, 1)
            else:
                joint_id, joint_kind, axis = name + '_fixed', 'fixed', None
                position_unit, velocity_unit, sizes = 'none', 'none', (0, 0)
            joints.append(JointDefinition('joint-definition-v1', joint_id,
                FrameReference(self.uid, parent.get('name')), FrameReference(self.uid, name),
                body_pose(body), origin, joint_kind, axis, position_unit, velocity_unit, *sizes))
        for site in subtree.iter('site'):
            if site.get('name'):
                frames.append(FrameDefinition('frame-definition-v1', self.uid, site.get('name'), 'runtime', None, None))
        asset = AssetDefinition('asset-definition-v1', 'mounted-panda-task-source', 'v1',
            'task-source://mounted-panda', source_revision=hashlib.sha256(source_xml.encode()).hexdigest(),
            source_content_sha256=self.source_closure_sha256)
        entity = EntityInstance('entity-instance-v1', self.uid, asset.asset_id, asset.asset_version)
        articulation = ArticulationDefinition('articulation-definition-v1', self.uid, names[0], names, tuple(joints))
        actuators = [ActuatorResourceDefinition('actuator-resource-v1', self.uid, d.native_actuator)
                     for d in declarations]
        groups = [ControlGroup('control-group-v1', self.uid, 'arm',
                  tuple(ActuatorReference(self.uid, d.native_actuator) for d in declarations))]
        finger_names = tuple(f'gripper0_gripper_finger_joint{i}' for i in (1, 2))
        finger_drives = tuple(root.findall(f"./actuator/position[@name='{name}']") for name in finger_names)
        if any(finger_drives):
            if any(len(drive) != 1 or drive[0].get('joint') != f'gripper0_finger_joint{i}'
                   for i, drive in enumerate(finger_drives, 1)):
                raise ValueError('mounted Panda position drives differ from finger source joints')
            actuators.extend(ActuatorResourceDefinition('actuator-resource-v1', self.uid, name)
                             for name in finger_names)
            groups.append(ControlGroup('control-group-v1', self.uid, 'gripper',
                tuple(ActuatorReference(self.uid, name) for name in finger_names)))
        scene = SceneDefinition('scene-definition-v3', scene_id, (asset,), (entity,), tuple(frames),
            (articulation,), (RobotInstance('robot-instance-v1', self.uid, (FrameReference(self.uid, names[0]),)),),
            tuple(actuators), tuple(groups))
        scene.validate()
        return scene
