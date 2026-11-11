"""Source-declared Panda direct effort profile for the existing candidate task.

The profile is a pre-native declaration. Its XML transmission assumptions must
be checked against a session's native build before any physical batch is sent.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ...artifacts import FrameReference, JointReference
from ...artifacts.logical_assembly import (
    LogicalAssemblyV1, LogicalAssemblyScenePinV1, LogicalAssemblyEntityMemberV1,
    LogicalAssemblyNestedMemberV1, LogicalAssemblySubcomponentReferenceV1,
)
from ...artifacts.state import StateFieldRequirement, StateRequirements
from ...controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
from ...controllers.canonical.physical_commands import PhysicalBodyBindingV1
from ...controllers.canonical.physical_controller import (
    LinearEffortProfileV1, LinearEffortControllerV1, WrenchControlProfileV1, WrenchControllerV1,
)
from ...runtime.sessions.physical_control import (
    PhysicalControlExecutionV1, compile_declared_subject_binding,
)

PANDA_DIRECT_EFFORT_PROFILE = 'panda-direct-effort-v1'
PANDA_EFFORT_WRENCH_PROFILE = 'panda-direct-effort-wrench-v1'
PANDA_EFFORT_OBJECT_WRENCH_PROFILE = 'panda-direct-effort-object-wrench-v1'
PANDA_SPLIT_EFFORT_PROFILE = 'panda-split-direct-effort-v1'
PANDA_FIXED_FRAME_POINT_WRENCH_PROFILE = 'panda-fixed-frame-point-wrench-v1'


def build_panda_direct_effort_execution(scene, artifact, source, *, wrench_target=None, split=False,
                                        fixed_frame_point=False, entity_id='panda-main', native_drive='position',
                                        gripper_force_limit=None):
    """Build named 7+2 commands from eight direct-effort inputs; no native I/O."""
    if native_drive not in {'position', 'disabled'}:
        raise ValueError('Panda effort profile requires a declared native drive mode')
    from ...assembly.assets import _source_closure_digest
    from ...runtime.sessions.source import project_scene_definition_v3_to_mjcf, source_asset_bytes

    projected = project_scene_definition_v3_to_mjcf(source.scene_source.xml, scene)
    closure = _source_closure_digest({'scene.xml': projected.encode('utf-8'),
                                      **source_asset_bytes(source.scene_source.base_dir, projected)})
    if closure != source.source_closure_digest:
        raise ValueError('physical profile source closure differs from its actual bytes')
    from ...robots.panda import PandaAgent
    names = PandaAgent.physical_joint_names()
    owner, entity = 'panda-direct-effort', entity_id
    definitions = {j.joint_id: j for a in scene.articulations or ()
                   if a.entity_id == entity for j in a.joints}
    if any(name not in definitions or source.joints.get(f'{entity}/{name}') != name for name in names):
        raise ValueError('Panda effort profile requires the exact nine named source joints')
    root_xml = ET.fromstring(source.scene_source.xml)
    from ...runtime.sessions.mujoco_composition import panda_effort_source_limits
    limits = panda_effort_source_limits(root_xml)
    if gripper_force_limit is not None:
        if (getattr(artifact, 'artifact_id', None) != 'pickcube-mjcf-physical-effort-task-v1'
                or native_drive != 'disabled' or float(gripper_force_limit) != 10.
                or limits[7] != (-5., 5.)):
            raise ValueError('task gripper force override requires its exact source and isolated fixture')
        # The selected PickCube R3 task uses a 10 N runtime gripper force cap;
        # this changes no authored MJCF bytes and preserves the 1:2 pair map.
        limits[7] = (-10., 10.)
    subject, declarations = PandaAgent.physical_subject_declaration(
        entity_id=entity, source_id=source.source_id,
        source_closure_sha256=source.source_closure_digest, native_ranges=tuple(limits),
        native_drive=native_drive, split=split)
    instance = next(x for x in scene.entities if x.entity_id == subject.entity_id)
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
                                     scene.schema_version, scene.identity_hash)
    refs = tuple(LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref',
        item.component_path[1:], 'joint', JointReference(subject.entity_id, item.joint_id))
        for item in declarations)
    child = LogicalAssemblyV1('logical-assembly-v1', 'panda-direct-effort-components', 'v1', pin, refs)
    logical = LogicalAssemblyV1('logical-assembly-v1', 'panda-direct-effort-assembly', 'v1', pin, (
        LogicalAssemblyEntityMemberV1('entity_member', ('owner',), entity, instance.asset_id, instance.asset_version),
        LogicalAssemblyNestedMemberV1('nested_assembly', ('robot',), child.assembly_id,
                                      child.revision, child.logical_content_sha256)))
    bodies = ()
    if wrench_target is not None:
        targets = {'hand': (entity, 'hand'), 'object': ('square-peg-instance', 'peg1'),
                   'probe': ('probe', 'probe_body')}
        if wrench_target not in targets:
            raise ValueError('unknown physical wrench target')
        body_entity, body_name = targets[wrench_target]
        if (root_xml.find(f".//body[@name='{body_name}']") is None
                or source.bodies.get(f'{body_entity}/{body_name}') != body_name):
            raise ValueError('wrench profile requires the declared source body')
        bodies = (PhysicalBodyBindingV1('physical-body-binding-v1', body_entity, body_name,
                  FrameReference(body_entity, body_name), body_name, ('candidate-body-wrench',)),)
    compiled = compile_declared_subject_binding(scene, artifact.identity_hash, source.source_id,
        source.source_closure_digest, logical, {(child.assembly_id, child.revision): child},
        (subject,), declarations, bodies)
    binding = compiled.binding
    groups = tuple((writer, tuple(item.joint_id for item in declarations if writer in item.owner_ids))
                   for writer in subject.controller_writers)
    controllers = ()
    for writer, group_names in groups:
        keys = tuple(f'{entity}/{name}' for name in group_names)
        kinds = tuple(definitions[name].kind for name in group_names)
        requirement = ControllerModelRequirementV1('controller-model-requirement-v1',
            'direct-effort-zero-bias-v1', 'geochora', 'v1', 'stdlib', source.source_id,
            source.source_closure_digest, keys,
            tuple('rad' if kind == 'revolute' else 'm' for kind in kinds), 'joint_bias',
            tuple('N*m' if kind == 'revolute' else 'N' for kind in kinds),
            'joint-axis', 'evaluation_boundary', artifact.timebase.control_dt,
            0., 'pure_no_physics_step', writer, 'none', 'required')
        # Direct effort deliberately adds zero: this is not a Panda dynamics model.
        zero = (0.,) * len(group_names)
        model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement, zero, zero, zero)
        action_names = (tuple(f'arm-effort-{i}' for i in range(1, 8))
                        if split and writer == 'panda-arm-effort' else
                        ('finger-tendon-effort',) if split else
                        tuple(f'arm-effort-{i}' for i in range(1, 8)) + ('finger-tendon-effort',))
        matrix = tuple(tuple((1. if names.index(name) == j else 0.) if names.index(name) < 7
                             else (0.5 if j == len(action_names)-1 else 0.)
                             for j in range(len(action_names))) for name in group_names)
        profile = LinearEffortProfileV1('linear-effort-profile-v1', writer, action_names, keys, matrix, requirement)
        controllers += (LinearEffortControllerV1(profile, binding, model),)
    if wrench_target is not None:
        frame = FrameReference(body_entity, body_name)
        expression_frame = FrameReference('square-peg-instance', 'peg1') if fixed_frame_point else frame
        if fixed_frame_point and (wrench_target not in {'hand', 'probe'}
                                  or source.bodies.get('square-peg-instance/peg1') != 'peg1'):
            raise ValueError('fixed-frame point wrench requires the source-bound peg and hand')
        if fixed_frame_point:
            peg = root_xml.find("./worldbody/body[@name='peg1']")
            if (peg is None or peg.find('joint') is not None or peg.find('freejoint') is not None
                    or peg.get('mocap', 'false').lower() not in {'false', '0'}):
                raise ValueError('fixed-frame point wrench requires a fixed world child')
        point_frame = expression_frame if wrench_target == 'probe' else frame
        # The fixed peg origin is (0.58, 0.045, 0.522) in this versioned
        # Scene; native preflight must verify its world pose before use.
        point = (-0.57, -0.045, 0.478) if wrench_target == 'probe' else (0.01, 0., 0.)
        wrench_profile = WrenchControlProfileV1('wrench-control-profile-v1', 'candidate-body-wrench',
            body_entity, body_name, expression_frame, point, point_frame,
            point if fixed_frame_point else (0., 0., 0.), point_frame, 'exclusive')
        controllers += (WrenchControllerV1(wrench_profile, binding),)
    fields = tuple(StateFieldRequirement('state-field-requirement-v1', field, 'joint', entity, name,
        'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
        for name in names for field in ('joint_position', 'joint_velocity'))
    if wrench_target is not None:
        fields += (StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world', 'frame',
            body_entity, body_name, 'required', 'evaluation_boundary', 'meter+quaternion_wxyz', 'frame_pose_query'),)
    if fixed_frame_point:
        fields += (StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world', 'frame',
            'square-peg-instance', 'peg1', 'required', 'evaluation_boundary',
            'meter+quaternion_wxyz', 'frame_pose_query'),)
    requirements = StateRequirements('state-requirements-v1', 'controller', owner, fields)
    definitions_by_native = {j.joint_id: j for a in scene.articulations or ()
                             for j in a.joints if j.kind != 'fixed'}
    joint_bindings = {semantic: definitions_by_native[native]
                      for semantic, native in (*source.joints.items(), *source.free_joints.items())}
    frame_bindings = {name: (artifact.legacy_frame_bindings[name]
                             if name in artifact.legacy_frame_bindings
                             else FrameReference(*name.split('/', 1)))
                      for name in (*source.bodies, *source.frames)}
    execution = PhysicalControlExecutionV1(compiled, controllers, scene, joint_bindings,
                                            frame_bindings, requirements, 1, (subject,))
    execution.validate_source(scene=scene, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    return execution
