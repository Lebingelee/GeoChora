"""Panda-owned declaration of common position subjects and Controller binding."""
from __future__ import annotations

from dataclasses import replace


def compile_reference_position_source(robot, source, *, artifact, controller, entity_id, recipe):
    """Compile the source-owned Panda position subject and its native mapping."""
    from ..assembly.source_composition import PositionSubjectControlBindingV1
    from ..runtime.sessions.source_scene_import import declare_panda_scene

    if entity_id != robot.uid or not recipe.sources or any(
            item.entity_ids != (entity_id,) for item in recipe.sources):
        raise ValueError('Panda reference recipe does not identify the existing Task Robot')
    scene = declare_panda_scene(robot, entity_id=entity_id, scene_id='integrated-panda-position')
    joints = tuple(recipe.controlled_joints)
    plan, subject_identity, subjects = compile_panda_position_subjects(
        source_scene=scene, components=((entity_id, 'link0', joints, None),),
        site_entity=entity_id, site_name='nutassembly_ee_site',
        groups=((entity_id, 'arm'), (entity_id, 'gripper')),
        source_id=source.source_id, robot_closure_sha256=source.source_closure_digest,
        task_closure_sha256=source.source_closure_digest, artifact=artifact, controller=controller)
    if source.open_actuators != ('actuator8',):
        raise ValueError('integrated Panda source lacks its declared gripper actuator')
    return PositionSubjectControlBindingV1(plan, subject_identity,
        tuple((entity, actuator, actuator) for entity, actuator, _ in plan.resource_writers),
        tuple((f'{entity_id}/{name}', entity_id, name, name,
               f'actuator{i + 1}' if i < 7 else 'actuator8')
              for i, name in enumerate(joints)), subjects=subjects)


def compile_panda_position_subjects(*, source_scene, components, site_entity, site_name,
                                     groups, source_id, robot_closure_sha256,
                                     task_closure_sha256, artifact, controller, attachment=None):
    """Compile single-entity or nested Panda components through the same owners.

    Components are (entity, root_frame, joint_names, parent_entity) declarations.
    The source attachment is checked against the original robot source scene.
    """
    from ..artifacts import (FrameDefinition, FrameReference, LogicalAssemblyV1,
        LogicalAssemblyScenePinV1, LogicalAssemblyNestedMemberV1)
    from ..artifacts.logical_assembly_resolution import existing_entity_joint_members
    from ..artifacts.state import StateFieldRequirement, StateRequirements
    from ..environment.types import ActionModeSpec
    from ..runtime.sessions.control import (ControllerBindingV1, ControlGroupActionProjectionV1,
        compile_control_binding_plan, validate_position_control_subjects)
    from ..runtime.sessions.physical_control import ControlledSubjectV1

    scene = source_scene
    if not any(f.entity_id == site_entity and f.frame_id == site_name for f in scene.frames):
        scene = replace(scene, frames=(*scene.frames,
            FrameDefinition('frame-definition-v1', site_entity, site_name, 'runtime', None, None)))
    scene.validate()
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
                                    scene.schema_version, scene.identity_hash)
    leaves = []
    for entity_id, _root_name, names, _parent in components:
        members = existing_entity_joint_members(scene, entity_id,
                                                tuple(((name,), name) for name in names))
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
    declare = getattr(controller, 'position_binding_requirements', None)
    declarations = tuple(declare()) if callable(declare) else ()
    if declarations:
        bindings = []
        subject_writers = {}
        grants = []
        used_groups = []
        for index, (owner, group_indices, action_indices, action_mode, needs_site) in enumerate(declarations):
            if (not group_indices or len(set(group_indices)) != len(group_indices)
                    or any(type(i) is not int or not 0 <= i < len(groups) for i in group_indices)
                    or not action_indices or len(set(action_indices)) != len(action_indices)
                    or any(type(i) is not int or not 0 <= i < len(names) for i in action_indices)
                    or action_mode not in {'absolute_pose', 'absolute_joint'}
                    or type(needs_site) is not bool
                    or not isinstance(getattr(owner, 'writer_id', None), str)
                    or not isinstance(getattr(owner, 'identity', None), str)):
                raise ValueError('Controller position binding requirements are invalid')
            used_groups.extend(group_indices)
            owned_groups = tuple(groups[i] for i in group_indices)
            owned_entities = {entity for entity, _ in owned_groups}
            for entity in owned_entities:
                if entity in subject_writers and subject_writers[entity] != owner.writer_id:
                    raise ValueError('one position subject cannot have multiple declared writers')
                subject_writers[entity] = owner.writer_id
            components_for_owner = tuple(names[i] for i in action_indices)
            owner_action = ActionModeSpec(
                f'panda-split-position-{index}-v1', 'task-env-action-v2',
                action_mode,
                'world' if action_mode == 'absolute_pose' else None,
                'quaternion_wxyz' if action_mode == 'absolute_pose' else None,
                components_for_owner, (float('-inf'),)*len(components_for_owner),
                (float('inf'),)*len(components_for_owner),
                quaternion_convention='wxyz' if action_mode == 'absolute_pose' else None)
            owner_fields = tuple(field for field in fields if field.entity_id in owned_entities
                                 or (needs_site and field.field_name == 'frame_pose_world'))
            requirements = StateRequirements('state-requirements-v1', 'controller', owner.writer_id, owner_fields)
            bindings.append(ControllerBindingV1('controller-binding-v1', owner.writer_id, owner_action,
                'canonical-control-feedback', 'v1', requirements,
                tuple(ControlGroupActionProjectionV1('control-group-action-projection-v1',
                                                      entity, group, components_for_owner)
                      for entity, group in owned_groups),
                controller_identity=owner.identity))
            if needs_site and site_entity not in owned_entities:
                grants.append((owner.writer_id, site_entity, site_name))
        if sorted(used_groups) != list(range(len(groups))):
            raise ValueError('Controller position declarations must cover every group exactly once')
        bindings = tuple(bindings)
    else:
        grants = []
        requirements = StateRequirements('state-requirements-v1', 'controller', writer, fields)
        bindings = (ControllerBindingV1('controller-binding-v1', writer, action, 'canonical-control-feedback',
            'v1', requirements, tuple(ControlGroupActionProjectionV1('control-group-action-projection-v1',
                entity, group, names[:7] if index == 0 else names[7:])
                for index, (entity, group) in enumerate(groups)), controller_identity=controller.identity),)
        subject_writers = {entity: writer for entity, _, _, _ in components}
    plan = compile_control_binding_plan(scene, bindings, artifact_identity_hash=artifact.identity_hash,
        source_closure_digest=task_closure_sha256, logical_assembly=root, assembly_children=children,
        cross_entity_frame_grants=tuple(grants),
        feedback_attachment=attachment if grants else None,
        feedback_attachment_scene=source_scene if grants else None)
    subjects = tuple(ControlledSubjectV1(entity, entity, source_id, robot_closure_sha256,
        'references_existing', 'fixed' if parent is None else 'constrained', FrameReference(entity, root_frame),
        parent, tuple(paths[entity](name) for name in joint_names), (subject_writers[entity],),
        attachment_plan=None if parent is None else attachment)
        for entity, root_frame, joint_names, parent in components)
    subject_identity = validate_position_control_subjects(scene=scene, root=root, children=children,
        subjects=subjects, plan=plan, attachment_scene=source_scene if attachment is not None else None)
    return plan, subject_identity, subjects
