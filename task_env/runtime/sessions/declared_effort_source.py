"""Compile a declared fixed Robot subject into an effort Runtime source."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ...artifacts import ExecutionSpecV1, RendererSelectionV1
from ...assembly.assets import _source_closure_digest
from ...assembly.compiler import compile_reference_source
from ...assembly.source import TaskSceneSource
from .source import project_scene_definition_v3_to_mjcf, source_asset_bytes


def declared_effort_scene(robot, *, provider, source_delivery_manifest):
    revision = None
    if provider == 'isaacsim':
        if source_delivery_manifest is None:
            raise ValueError('Isaac effort source requires source_delivery_manifest')
        from .isaac_g05 import ensure_g05_isaac_app_open, load_g05_isaac_delivery
        ensure_g05_isaac_app_open()
        revision = load_g05_isaac_delivery(source_delivery_manifest).delivery.asset_definition.source_revision
    return robot.scene_definition(source_revision=revision)


def compile_declared_effort_source(*, robot, scene, artifact, task_source, composition,
                                   config, provider, source_delivery_manifest, seed, base_dir):
    """Map Robot topology and declared transmissions to the chosen source adapter."""
    xml = robot.source_xml
    source_id = f'scene-definition-v3:{scene.identity_hash}'
    projected = project_scene_definition_v3_to_mjcf(xml, scene)
    closure = _source_closure_digest({'scene.xml': projected.encode(),
                                      **source_asset_bytes(base_dir, projected)})
    subject, declarations = robot.physical_subject_declaration(
        source_id=source_id, source_closure_sha256=closure)
    root = ET.fromstring(xml)
    section = root.find('./actuator')
    motors = root.findall('./actuator/motor')
    if section is None or len(section) != len(declarations) or len(motors) != len(declarations):
        raise ValueError('source motor count differs from Robot transmission declaration')
    for motor, declaration in zip(motors, declarations, strict=True):
        try:
            limits = tuple(float(value) for value in motor.get('ctrlrange', '').split())
            gear = float(motor.get('gear', ''))
        except ValueError as exc:
            raise ValueError('source motor transmission is invalid') from exc
        if (motor.get('name') != declaration.native_actuator
                or motor.get('joint') != declaration.joint_id
                or gear != declaration.transmission_coefficient
                or motor.get('ctrllimited') != 'true'
                or limits != declaration.native_range):
            raise ValueError('source motor transmission differs from Robot declaration')

    articulations = tuple(a for a in scene.articulations if a.entity_id == subject.entity_id)
    if len(articulations) != 1:
        raise ValueError('declared effort source requires one subject articulation')
    articulation = articulations[0]
    joints = {f'{subject.entity_id}/{name}': name for name in robot.state_joint_names}
    frames = articulation.link_frame_ids
    body_names = {f'{subject.entity_id}/{name}': name for name in frames}
    torque_actuators = {f'{subject.entity_id}/{item.joint_id}': item.native_actuator
                        for item in declarations}
    if provider == 'isaacsim':
        from .isaac_g05 import G05_ISAAC_EFFORT_PROFILE, build_g05_isaac_runtime_source
        # USD export retains the declared articulation hierarchy under Geometry.
        paths = {articulation.root_frame_id: f'Geometry/{articulation.root_frame_id}'}
        remaining = list(articulation.joints)
        while remaining:
            ready = [joint for joint in remaining if joint.parent_frame.frame_id in paths]
            if not ready:
                raise ValueError('subject articulation cannot resolve USD body paths')
            for joint in ready:
                paths[joint.child_frame.frame_id] = paths[joint.parent_frame.frame_id] + '/' + joint.child_frame.frame_id
                remaining.remove(joint)
        bodies = {key: paths[name] for key, name in body_names.items()}
        source = build_g05_isaac_runtime_source(
            manifest_path=source_delivery_manifest, artifact=artifact, scene=scene,
            task_source_identity_sha256=task_source.identity_hash, joints=joints,
            bodies=bodies, frames={}, free_joints={}, joint_targets=joints)
        execution_spec = ExecutionSpecV1(
            'execution-spec-v1', 'isaacsim', 'cuda', G05_ISAAC_EFFORT_PROFILE,
            seed, 'best_effort',
            RendererSelectionV1('renderer-selection-v1', 'none', 'cpu', 'none', None),
            physics_device='cuda:0', camera_overrides=())
        closure = source.source_closure_digest
    else:
        source = compile_reference_source(
            artifact=artifact, scene_source=TaskSceneSource(xml, base_dir, source_id),
            composition=composition, config=config, joints=joints, bodies=body_names,
            frames={}, free_joints={}, joint_targets={}, open_actuators=(),
            scene_definition=scene, source_closure_digest=closure,
            torque_actuators=torque_actuators,
            actuator_units={item.native_actuator: 'N*m' for item in declarations})
        execution_spec = None
    return source, execution_spec, closure
