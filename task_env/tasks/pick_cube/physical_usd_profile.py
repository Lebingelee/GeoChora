"""Source-bound F06 PickCube direct-effort declaration, without native I/O."""
from __future__ import annotations

from ...artifacts import FrameReference, JointReference
from ...artifacts.logical_assembly import (
    LogicalAssemblyV1, LogicalAssemblyScenePinV1, LogicalAssemblyEntityMemberV1,
    LogicalAssemblyNestedMemberV1, LogicalAssemblySubcomponentReferenceV1,
)
from ...artifacts.state import StateFieldRequirement, StateRequirements
from ...controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
from ...controllers.canonical.physical_commands import PhysicalControlBindingV1, PhysicalJointChannelV1
from ...controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
from ...runtime.sessions.physical_control import PhysicalControlExecutionV1, compile_physical_control_binding, _rotate


def build_f06_direct_effort_execution(scene, artifact, source):
    """Declare seven arm channels and the source-constrained mimic pair.

    The two finger contributions are half of a common leader effort. Native
    build admission must independently verify the F06 drive and mimic witness;
    these declared limits bound this contribution, not the total drive force.
    """
    from ...runtime.sessions.source import UsdRuntimeSourceV1
    if type(source) is not UsdRuntimeSourceV1:
        raise TypeError('F06 physical profile requires its exact USD RuntimeSource')
    source.validate()
    if (source.source_closure_digest != 'dc2a87a74963e0ec10f3cf98b3e33cc87226350dde78aeddbc88244a0fbdafc6'
            or source.task_artifact.identity_hash != artifact.identity_hash
            or source.scene_definition.identity_hash != scene.identity_hash):
        raise ValueError('F06 physical profile requires the frozen source and Artifact')
    entity, owner = 'panda-v1', 'panda-direct-effort'
    native_drive = ('disabled' if artifact.artifact_id == 'pickcube-f06-physical-effort-no-drive-v1' else 'position')
    names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
    definitions = {j.joint_id: j for a in scene.articulations or () if a.entity_id == entity for j in a.joints}
    if any(name not in definitions or source.joints.get(f'{entity}/{name}') != name for name in names):
        raise ValueError('F06 physical profile requires nine exact named joints')
    instance = next(x for x in scene.entities if x.entity_id == entity)
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id, scene.schema_version, scene.identity_hash)
    refs = tuple(LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref',
        (name,), 'joint', JointReference(entity, name)) for name in names)
    child = LogicalAssemblyV1('logical-assembly-v1', 'f06-panda-direct-effort-components', 'v1', pin, refs)
    logical = LogicalAssemblyV1('logical-assembly-v1', 'f06-panda-direct-effort-assembly', 'v1', pin, (
        LogicalAssemblyEntityMemberV1('entity_member', ('owner',), entity, instance.asset_id, instance.asset_version),
        LogicalAssemblyNestedMemberV1('nested_assembly', ('robot',), child.assembly_id,
                                     child.revision, child.logical_content_sha256)))
    channels = []
    for i, name in enumerate(names):
        joint = definitions[name]
        arm = i < 7
        coefficient = 1.0 if arm else 0.5
        native_range = (-250., 250.) if arm else (-5., 5.)
        channels.append(PhysicalJointChannelV1('physical-joint-channel-v1', ('robot', name), (owner,),
            entity, name, 'dof0', joint.kind, _rotate(joint.pose_parent_from_joint.quaternion_wxyz, joint.axis),
            joint.parent_frame, 1, 'N*m' if arm else 'N', tuple(coefficient*x for x in native_range),
            name if arm else 'finger_joint1', f'f06-arm-{i+1}' if arm else 'f06-mimic-pair',
            coefficient, native_range, native_drive))
    binding = PhysicalControlBindingV1('physical-control-binding-v1', scene.identity_hash,
        artifact.identity_hash, source.source_id, source.source_closure_digest,
        logical.logical_content_sha256, tuple(channels), ())
    compiled = compile_physical_control_binding(scene, logical, {(child.assembly_id, child.revision): child}, binding)
    keys = tuple(f'{entity}/{name}' for name in names)
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1',
        'f06-direct-effort-zero-bias-v1', 'geochora', 'v1', 'stdlib', source.source_id,
        source.source_closure_digest, keys, ('rad',)*7 + ('m',)*2, 'joint_bias',
        ('N*m',)*7 + ('N',)*2, 'joint-axis', 'evaluation_boundary', artifact.timebase.control_dt,
        0., 'pure_no_physics_step', owner, 'none', 'required')
    zero = (0.,)*9
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement, zero, zero, zero)
    action_names = tuple(f'arm-effort-{i}' for i in range(1, 8)) + ('finger-pair-effort',)
    matrix = tuple(tuple((1. if i == j else 0.) if i < 7 else (0.5 if j == 7 else 0.)
                         for j in range(8)) for i in range(9))
    profile = LinearEffortProfileV1('linear-effort-profile-v1', owner, action_names, keys, matrix, requirement)
    controller = LinearEffortControllerV1(profile, binding, model)
    fields = tuple(StateFieldRequirement('state-field-requirement-v1', field, 'joint', entity, name,
        'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
        for name in names for field in ('joint_position', 'joint_velocity'))
    requirements = StateRequirements('state-requirements-v1', 'controller', owner, fields)
    from ...runtime.sessions.source import position_joint_bindings_from_artifact, position_frame_bindings_from_artifact
    joint_bindings = position_joint_bindings_from_artifact(scene, artifact, source)
    frame_bindings = position_frame_bindings_from_artifact(artifact, source)
    result = PhysicalControlExecutionV1(compiled, (controller,), scene, joint_bindings, frame_bindings, requirements, 1)
    result.validate_source(scene=scene, artifact_sha256=artifact.identity_hash, source_id=source.source_id,
                           source_closure_sha256=source.source_closure_digest, source=source)
    return result
