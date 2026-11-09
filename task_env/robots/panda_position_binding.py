"""Panda-owned declaration of common position subjects and Controller binding."""
from __future__ import annotations

from dataclasses import replace


def compile_panda_position_subjects(*, source_scene, components, site_entity, site_name,
                                     groups, source_id, robot_closure_sha256,
                                     task_closure_sha256, artifact, controller, attachment=None):
    """Compile single-entity or nested Panda components through the same owners.

    Components are (entity, root_frame, joint_names, parent_entity) declarations.
    The source attachment is checked against the original robot source scene.
    """
    from ..artifacts import (FrameDefinition, FrameReference, JointReference, LogicalAssemblyV1,
        LogicalAssemblyScenePinV1, LogicalAssemblyEntityMemberV1, LogicalAssemblyNestedMemberV1,
        LogicalAssemblySubcomponentReferenceV1)
    from ..artifacts.state import StateFieldRequirement, StateRequirements
    from ..environment.types import ActionModeSpec
    from ..runtime.sessions.control import (ControllerBindingV1, ControlGroupActionProjectionV1,
        compile_control_binding_plan, validate_position_control_subjects)
    from ..runtime.sessions.physical_control import ControlledSubjectV1
    from ..controllers.canonical.split_panda_position import (
        ARM_WRITER, HAND_WRITER, SplitPandaPositionControllerV1,
    )

    scene = source_scene
    if not any(f.entity_id == site_entity and f.frame_id == site_name for f in scene.frames):
        scene = replace(scene, frames=(*scene.frames,
            FrameDefinition('frame-definition-v1', site_entity, site_name, 'runtime', None, None)))
    scene.validate()
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
                                    scene.schema_version, scene.identity_hash)
    entities = {item.entity_id: item for item in scene.entities}
    leaves = []
    for entity_id, _root_name, names, _parent in components:
        entity = entities[entity_id]
        members = (LogicalAssemblyEntityMemberV1('entity_member', ('owner',), entity_id,
                   entity.asset_id, entity.asset_version),) + tuple(
            LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref', (name,),
                                                    'joint', JointReference(entity_id, name)) for name in names)
        leaves.append(LogicalAssemblyV1('logical-assembly-v1', entity_id + '-position-owner',
                                         'v1', pin, members))
    def edge(path, child):
        return LogicalAssemblyNestedMemberV1('nested_assembly', (path,), child.assembly_id,
                                              child.revision, child.logical_content_sha256)
    if len(components) == 1:
        root, children = leaves[0], {}
        paths = {components[0][0]: lambda name: (name,)}
    else:
        branch = LogicalAssemblyV1('logical-assembly-v1', 'panda-position-components', 'v1', pin,
            tuple(edge(f'component-{i}', leaf) for i, leaf in enumerate(leaves)))
        root = LogicalAssemblyV1('logical-assembly-v1', 'panda-position-robot', 'v1', pin,
                                  (edge('robot', branch),))
        children = {(item.assembly_id, item.revision): item for item in (*leaves, branch)}
        paths = {item[0]: (lambda name, i=i: ('robot', f'component-{i}', name))
                 for i, item in enumerate(components)}
    names = ('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz', 'gripper')
    action = ActionModeSpec('selected-reference-absolute-pose-v1', 'task-env-action-v2',
        'absolute_pose', 'world', 'quaternion_wxyz', names, (float('-inf'),)*8,
        (float('inf'),)*8, quaternion_convention='wxyz')
    writer = 'panda-position-controller'
    fields = tuple(StateFieldRequirement('state-field-requirement-v1', 'joint_position', 'joint',
        entity, joint, 'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
        for entity, _, joints, _ in components for joint in joints)
    fields += (StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world', 'frame', site_entity,
        site_name, 'required', 'evaluation_boundary', 'meter+quaternion_wxyz', 'frame_pose_query'),
        StateFieldRequirement('state-field-requirement-v1', 'actuator_force', 'actuator', groups[1][0],
        'actuator8', 'required', 'evaluation_boundary', 'provider-native-actuator-output', 'actuator_force_query'))
    split = type(controller) is SplitPandaPositionControllerV1
    if split:
        if len(components) != 2 or len(groups) != 2 or groups[0][0] == groups[1][0]:
            raise ValueError('split Position Controllers require distinct arm and hand subjects')
        bindings = []
        for index, (entity, group) in enumerate(groups):
            owner = controller.arm if index == 0 else controller.hand
            components_for_owner = names[:7] if index == 0 else names[7:]
            owner_action = ActionModeSpec(
                f'panda-split-position-{index}-v1', 'task-env-action-v2',
                'absolute_pose' if index == 0 else 'absolute_joint',
                'world' if index == 0 else None, 'quaternion_wxyz' if index == 0 else None,
                components_for_owner, (float('-inf'),)*len(components_for_owner),
                (float('inf'),)*len(components_for_owner),
                quaternion_convention='wxyz' if index == 0 else None)
            owner_fields = tuple(field for field in fields if field.entity_id == entity
                                 or (index == 0 and field.field_name == 'frame_pose_world'))
            requirements = StateRequirements('state-requirements-v1', 'controller', owner.writer_id, owner_fields)
            bindings.append(ControllerBindingV1('controller-binding-v1', owner.writer_id, owner_action,
                'canonical-control-feedback', 'v1', requirements,
                (ControlGroupActionProjectionV1('control-group-action-projection-v1',
                                                 entity, group, components_for_owner),),
                controller_identity=owner.identity))
        bindings = tuple(bindings)
        subject_writers = {groups[0][0]: ARM_WRITER, groups[1][0]: HAND_WRITER}
    else:
        requirements = StateRequirements('state-requirements-v1', 'controller', writer, fields)
        bindings = (ControllerBindingV1('controller-binding-v1', writer, action, 'canonical-control-feedback',
            'v1', requirements, tuple(ControlGroupActionProjectionV1('control-group-action-projection-v1',
                entity, group, names[:7] if index == 0 else names[7:])
                for index, (entity, group) in enumerate(groups)), controller_identity=controller.identity),)
        subject_writers = {entity: writer for entity, _, _, _ in components}
    plan = compile_control_binding_plan(scene, bindings, artifact_identity_hash=artifact.identity_hash,
        source_closure_digest=task_closure_sha256, logical_assembly=root, assembly_children=children,
        cross_entity_frame_grants=((ARM_WRITER, site_entity, site_name),) if split else (),
        feedback_attachment=attachment if split else None,
        feedback_attachment_scene=source_scene if split else None)
    subjects = tuple(ControlledSubjectV1(entity, entity, source_id, robot_closure_sha256,
        'references_existing', 'fixed' if parent is None else 'constrained', FrameReference(entity, root_frame),
        parent, tuple(paths[entity](name) for name in joint_names), (subject_writers[entity],),
        attachment_plan=None if parent is None else attachment)
        for entity, root_frame, joint_names, parent in components)
    subject_identity = validate_position_control_subjects(scene=scene, root=root, children=children,
        subjects=subjects, plan=plan, attachment_scene=source_scene if attachment is not None else None)
    return plan, subject_identity
