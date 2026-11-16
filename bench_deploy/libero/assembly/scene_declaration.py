"""Project the benchmark's existing MJCF bodies into the common Scene contract.

This is a declaration only: no source subtree is imported twice and no native
model, runtime, reset, or stepping is created here.
"""
from __future__ import annotations

from dataclasses import replace
import math
import xml.etree.ElementTree as ET

from task_env.artifacts import (ArticulationDefinition, AssetDefinition, EntityInstance,
    FrameDefinition, FrameReference, JointDefinition, PoseWorld, SceneDefinition)


def _body_pose(body):
    position = tuple(float(v) for v in body.get('pos', '0 0 0').split())
    quat = tuple(float(v) for v in body.get('quat', '1 0 0 0').split())
    if len(position) != 3 or len(quat) != 4 or not all(math.isfinite(v) for v in (*position, *quat)):
        raise ValueError('LIBERO source body pose is invalid')
    norm = math.sqrt(sum(v*v for v in quat))
    if norm == 0:
        raise ValueError('LIBERO source body quaternion is zero')
    return PoseWorld(position, tuple(v / norm for v in quat))


def compose_libero_scene(*, robot, legacy_artifact, source):
    """Extend the Robot Scene with the source-authored task bodies and joints."""
    xml = source.scene_source.xml
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    if world is None:
        raise ValueError('LIBERO source has no worldbody')
    robot_scene = robot.scene_definition(source_xml=xml, scene_id=source.config.scene.scene_uid)
    assets, entities = list(robot_scene.assets), list(robot_scene.entities)
    frames, articulations = list(robot_scene.frames), list(robot_scene.articulations)
    frame_map = {'panda-v1/ee': FrameReference('panda-v1', source.frames['panda-v1/ee'])}
    frame_map.update({key: FrameReference('panda-v1', native) for key, native in source.bodies.items()
                      if key.startswith('panda-v1/')})
    native_to_joint = {native: semantic for semantic, native in source.joints.items()}
    native_to_free = {native: semantic for semantic, native in source.free_joints.items()}
    legacy_joint_map = {}
    definitions = {}
    for joint in robot_scene.articulations[0].joints:
        if joint.joint_id in native_to_joint:
            legacy_joint_map[native_to_joint[joint.joint_id]] = (robot.uid, joint.joint_id)
            definitions[native_to_joint[joint.joint_id]] = joint
    zero = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
    for entity in legacy_artifact.world.entities:
        entity_id = entity.semantic_id
        if entity_id == robot.uid:
            continue
        native_root = source.bodies.get(entity_id)
        roots = world.findall(f"body[@name='{native_root}']") if native_root else []
        if len(roots) != 1:
            raise ValueError(f'LIBERO task entity {entity_id!r} has no unique world source body')
        subtree = roots[0]
        nodes = tuple(subtree.iter('body'))
        names = tuple(node.get('name') for node in nodes)
        if any(not name for name in names) or len(names) != len(set(names)):
            raise ValueError('LIBERO task body names must be present and unique')
        parents = {child: parent for parent in subtree.iter() for child in parent}
        body_names = ('world', *names)
        frames.extend(FrameDefinition('frame-definition-v1', entity_id, name, 'runtime', None, None)
                      for name in body_names)
        task_joints = []
        for body in nodes:
            parent_name = 'world' if body is subtree else parents[body].get('name')
            joint_nodes = body.findall('joint') + body.findall('freejoint')
            if len(joint_nodes) > 1:
                raise ValueError('LIBERO source body has more than one joint')
            if joint_nodes:
                node = joint_nodes[0]
                kind_name = 'free' if node.tag == 'freejoint' else node.get('type', 'hinge')
                values = {'hinge': ('revolute', 'radian', 'radian_per_second', 1, 1),
                          'slide': ('prismatic', 'meter', 'meter_per_second', 1, 1),
                          'free': ('floating', 'xyz_meter_quaternion_wxyz',
                            'linear_xyz_meter_per_second_angular_xyz_radian_per_second', 7, 6)}.get(kind_name)
                if values is None or not node.get('name'):
                    raise ValueError('LIBERO source joint is unsupported or unnamed')
                kind, pos_unit, vel_unit, pos_size, vel_size = values
                axis = None if kind == 'floating' else tuple(float(v) for v in node.get('axis', '0 0 1').split())
                if kind != 'floating' and tuple(float(v) for v in node.get('pos', '0 0 0').split()) != (0., 0., 0.):
                    raise ValueError('LIBERO scalar joint offset is unsupported')
                joint_id = node.get('name')
            else:
                joint_id, kind, axis, pos_unit, vel_unit, pos_size, vel_size = (
                    body.get('name') + '_fixed', 'fixed', None, 'none', 'none', 0, 0)
            item = JointDefinition('joint-definition-v1', joint_id,
                FrameReference(entity_id, parent_name), FrameReference(entity_id, body.get('name')),
                _body_pose(body), zero, kind, axis, pos_unit, vel_unit, pos_size, vel_size)
            task_joints.append(item)
            if joint_id in native_to_joint:
                semantic = native_to_joint[joint_id]
                legacy_joint_map[semantic] = (entity_id, joint_id)
                definitions[semantic] = item
            if joint_id in native_to_free:
                definitions[native_to_free[joint_id]] = item
        asset = AssetDefinition('asset-definition-v1', 'libero-' + entity_id, 'v1',
            entity.asset_reference, source_revision='task-source', source_content_sha256=source.source_closure_digest)
        assets.append(asset)
        entities.append(EntityInstance('entity-instance-v1', entity_id, asset.asset_id, asset.asset_version))
        articulations.append(ArticulationDefinition('articulation-definition-v1', entity_id, 'world',
                                                    body_names, tuple(task_joints)))
        frame_map[entity_id] = FrameReference(entity_id, native_root)
    scene = SceneDefinition('scene-definition-v3', robot_scene.scene_id, tuple(assets), tuple(entities),
        tuple(frames), tuple(articulations), robot_scene.robots, robot_scene.actuator_resources,
        robot_scene.control_groups)
    scene.validate()
    if set(definitions) != set(source.joints) | set(source.free_joints):
        raise ValueError('LIBERO Scene does not cover the complete source joint mapping')
    if set(frame_map) != set(source.bodies) | set(source.frames):
        raise ValueError('LIBERO Scene does not cover the complete source frame mapping')
    return scene, frame_map, legacy_joint_map, definitions


def bind_libero_default_source(*, source, legacy_artifact, initial_poses,
                               controller_profile='direct_joint_effort_v1'):
    """Bind the mounted task source to its declared effort Controller.

    The caller retains ownership of the original source snapshot and must close
    it on success or failure.  This function does not construct a Runtime.
    """
    from task_env.artifacts import ActionIntent, JointReference
    from task_env.environment.task_source import TaskSourceV1, compile_task_artifact_v1
    from task_env.robots.mounted_panda import MountedPandaArm
    from task_env.runtime.sessions.source import bind_reference_scene_source
    from task_env.runtime.sessions.source_composition_adapters import (
        prepare_robot_source_intent, validate_effort_robot_intent,
    )
    from task_env.runtime.sessions.physical_control import build_declared_effort_execution

    robot = MountedPandaArm(source.source_id, source.source_closure_digest)
    scene, frames, joints, definitions = compose_libero_scene(
        robot=robot, legacy_artifact=legacy_artifact, source=source)
    task_roots = tuple((key, native) for key, native in source.bodies.items()
                       if not key.startswith(robot.uid + '/'))
    profile = controller_profile
    if profile not in robot.controller_profiles:
        raise ValueError('mounted Panda does not declare this Controller profile')
    intent, _ = prepare_robot_source_intent(source, robot=robot, controller_profile=profile,
        existing_robot_entity=robot.uid, task_body_names=task_roots, task_site_transfers=())
    remap = {key: (f'{robot.uid}/{native}' if key in source.torque_actuators else key)
             for key, native in source.joints.items()}
    if set(initial_poses) != set(source.free_joints):
        raise ValueError('LIBERO initialization must cover the source free joints')
    entities = tuple(replace(entity, joints=tuple(remap.get(name, name) for name in entity.joints))
                     for entity in legacy_artifact.world.entities)
    legacy = replace(legacy_artifact,
        world=replace(legacy_artifact.world, entities=entities,
            action=(ActionIntent('direct_joint_effort', None, 'none', 'joint_effort')
                    if profile == 'direct_joint_effort_v1' else
                    ActionIntent('absolute_pose', 'world', 'quaternion_wxyz', 'arm_joint_effort'))),
        initialization=replace(legacy_artifact.initialization,
            poses_world=dict(initial_poses),
            joint_position={remap.get(name, name): value for name, value in
                            legacy_artifact.initialization.joint_position.items()}),
        semantics=replace(legacy_artifact.semantics,
            required_joints=tuple(remap.get(name, name) for name in
                                  legacy_artifact.semantics.required_joints)))
    task_source = TaskSourceV1(legacy.task_id, legacy.artifact_version, scene.scene_id, (), None)
    artifact = compile_task_artifact_v1(task_source, scene, legacy,
        frame_bindings={'panda-v1/ee': frames['panda-v1/ee']},
        joint_bindings={remap.get(key, key): JointReference(*pair) for key, pair in joints.items()})
    artifact = replace(artifact, legacy_frame_bindings={**artifact.legacy_frame_bindings, **frames})
    artifact.validate_scene(scene)
    source = replace(source, mixed_actuator_plan=None,
        joints={remap[key]: native for key, native in source.joints.items()},
        torque_actuators={remap[key]: native for key, native in source.torque_actuators.items()},
        joint_targets=dict(source.position_actuators))
    bound, _, _ = bind_reference_scene_source(source, artifact=artifact, scene=scene,
                                               bodies=dict(source.bodies), frames=dict(source.frames))
    bound = replace(bound, source_composition_intent=intent)
    robot = MountedPandaArm(bound.source_id, bound.source_closure_digest)
    subject, declarations = robot.physical_subject_declaration(source_xml=bound.scene_source.xml)
    joint_bindings = {remap[key] if key in remap else key: definition
                      for key, definition in definitions.items()}
    def selected_controller(binding, writer):
        if profile == 'direct_joint_effort_v1':
            return robot.default_controller.bind(subject, binding, writer_id=writer,
                                                 units=('N*m',) * len(declarations))
        from task_env.controllers.canonical.operational_space_effort import OperationalSpaceEffortControllerV1
        return OperationalSpaceEffortControllerV1(binding, tcp_frame=frames['panda-v1/ee'],
                                                   cadence_s=artifact.timebase.control_dt)

    execution = build_declared_effort_execution(scene=scene, artifact=artifact, source=bound,
        subject=subject, declarations=declarations, assembly_id=robot.assembly_id,
        controller_factory=selected_controller,
        state_joint_names=robot.state_joint_names, joint_bindings=joint_bindings, frame_bindings=frames)
    if profile == 'source_osc_pose_v1':
        from task_env.artifacts.state import StateFieldRequirement
        tcp = frames['panda-v1/ee']
        requirement = StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world',
            'frame', tcp.entity_id, tcp.frame_id, 'required', 'evaluation_boundary',
            'meter+quaternion_wxyz', 'frame_pose_query')
        execution = replace(execution, requirements=replace(execution.requirements,
            requirements=(*execution.requirements.requirements, requirement)))
    execution = replace(execution, selection_profile_id=profile)
    validate_effort_robot_intent(intent, bound, execution, controller_profile=profile)
    return task_source, artifact, bound, robot, execution, intent, remap
