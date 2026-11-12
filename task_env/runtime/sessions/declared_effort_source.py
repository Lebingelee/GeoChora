"""Compile a declared fixed Robot subject into an effort Runtime source."""
from __future__ import annotations

from dataclasses import replace

from ...artifacts import ExecutionSpecV1, RendererSelectionV1
from ...assembly.compiler import compile_reference_source
from ...assembly.source import TaskSceneSource
from .source import project_mjcf_scene_source


def declared_effort_scene(robot, *, provider, source_delivery_manifest):
    revision = None
    delivery = None
    if provider == 'isaacsim':
        if source_delivery_manifest is None:
            raise ValueError('Isaac effort source requires source_delivery_manifest')
        from .isaac_g05 import ensure_g05_isaac_app_open, load_g05_isaac_delivery
        ensure_g05_isaac_app_open()
        delivery = load_g05_isaac_delivery(source_delivery_manifest)
        revision = delivery.delivery.asset_definition.source_revision
    return robot.scene_definition(source_revision=revision), delivery


def compile_declared_effort_source(*, robot, scene, artifact, task_source, composition,
                                   config, provider, source_delivery, seed):
    """Map Robot topology and declared transmissions to the chosen source adapter."""
    xml = robot.source_xml
    source_id = f'scene-definition-v3:{scene.identity_hash}'
    scene_source = TaskSceneSource(xml, robot.source_base_dir, source_id)
    _, _, closure = project_mjcf_scene_source(scene_source, scene)
    subject, declarations = robot.physical_subject_declaration(
        source_id=source_id, source_closure_sha256=closure)
    from .source_scene_import import validate_declared_effort_transmissions
    validate_declared_effort_transmissions(xml, declarations)

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
        source = build_g05_isaac_runtime_source(
            delivery=source_delivery, artifact=artifact, scene=scene,
            task_source_identity_sha256=task_source.identity_hash, joints=joints,
            articulation=articulation, body_names=body_names,
            frames={}, free_joints={}, joint_targets=joints)
        execution_spec = ExecutionSpecV1(
            'execution-spec-v1', 'isaacsim', 'cuda', G05_ISAAC_EFFORT_PROFILE,
            seed, 'best_effort',
            RendererSelectionV1('renderer-selection-v1', 'none', 'cpu', 'none', None),
            physics_device='cuda:0', camera_overrides=())
        closure = source.source_closure_digest
    else:
        source = compile_reference_source(
            artifact=artifact, scene_source=scene_source,
            composition=composition, config=config, joints=joints, bodies=body_names,
            frames={}, free_joints={}, joint_targets={}, open_actuators=(), agents=(robot,),
            scene_definition=scene, source_closure_digest=closure,
            torque_actuators=torque_actuators,
            actuator_units={item.native_actuator: 'N*m' for item in declarations})
        execution_spec = None
    # The source adapter may replace the provisional MJCF identity with a USD
    # identity. Preserve the exact transmission declaration checked above.
    subject = replace(subject, source_id=source.source_id,
                      source_closure_sha256=source.source_closure_digest)
    return source, execution_spec, closure, subject, declarations
