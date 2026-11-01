"""Focused F06 PickCube-to-Isaac canonical projection checks."""

from task_env.tasks.pick_cube.isaac import compile_pickcube_isaac_task_artifact
from task_env.tasks.pick_cube.task import _configuration, build_artifact


def test_pickcube_isaac_projection_preserves_task_semantics_and_binds_runtime_frames():
    legacy = build_artifact()
    task_source, scene, artifact = compile_pickcube_isaac_task_artifact(
        _configuration(), legacy,
    )

    assert artifact.source_artifact_identity_hash == legacy.identity_hash
    assert task_source.task_id == legacy.task_id == "pick-cube-v1"
    assert scene.scene_id == "tabletop-v1"
    assert {entity.entity_id for entity in scene.entities} == {
        "panda-v1", "cube-v1", "tabletop-v1",
    }
    assert artifact.legacy_frame_bindings["panda-v1/base"].frame_id == "link0"
    assert artifact.legacy_frame_bindings["panda-v1/ee"].frame_id == "ee"
    assert artifact.legacy_frame_bindings["cube-v1"].frame_id == "cube"
    frame = next(
        item for item in scene.frames
        if (item.entity_id, item.frame_id) == ("tabletop-v1", "top")
    )
    assert frame.frame_kind == "runtime"

    floating = [
        joint
        for articulation in scene.articulations
        if articulation.entity_id == "cube-v1"
        for joint in articulation.joints
        if joint.kind == "floating"
    ]
    assert len(floating) == 1
    assert floating[0].joint_id == "cube_freejoint"
    assert len(artifact.legacy_joint_bindings) == 9
    artifact.validate_scene(scene)


def test_f06_pickcube_tcp_is_the_task_ee_site_offset():
    from task_env.controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1

    assert PANDA_PICKCUBE_EE_TCP_V1.to_mapping() == {
        'schema_version': 'panda-tcp-profile-v1',
        'tcp_id': 'panda-v1/pickcube-ee-offset-v1',
        'hand_frame_id': 'hand',
        'position_m': [0.0, 0.0, 0.0584],
        'quaternion_wxyz': [1.0, 0.0, 0.0, 0.0],
    }


def test_f06_external_binding_constructs_only_the_solution_free_source_once():
    from unittest.mock import patch

    from task_env.tasks.pick_cube.task import make_reference_binding

    manifest = '/frozen/f06/delivery_manifest.json'
    binding = make_reference_binding(
        controller_profile='r3_continuous_v1',
        source_delivery_manifest=manifest,
    )
    with patch('task_env.tasks.pick_cube.task.build_isaac_reference',
               return_value={'construction': 'external'}) as build:
        result = binding.build_external('isaacsim')

    assert result == {'construction': 'external'}
    build.assert_called_once_with(
        delivery_manifest=manifest,
        include_solution=False,
        controller_profile='r3_continuous_v1',
    )


def test_position_reset_uses_artifact_frame_alias_for_single_segment_semantics():
    from types import SimpleNamespace

    from task_env.artifacts import FrameReference
    from task_env.tasks.reference_env import _position_frame_bindings_from_artifact

    artifact = SimpleNamespace(legacy_frame_bindings={
        'panda-v1/base': FrameReference('panda-v1', 'link0'),
        'panda-v1/ee': FrameReference('panda-v1', 'ee'),
        'cube-v1': FrameReference('cube-v1', 'cube'),
    })
    source = SimpleNamespace(
        bodies={'panda-v1/base': '/F06Scene/panda/link0', 'cube-v1': '/F06Scene/cube_v1'},
        frames={'panda-v1/ee': '/F06Scene/panda/hand/ee'},
    )

    assert _position_frame_bindings_from_artifact(artifact, source) == {
        'panda-v1/base': FrameReference('panda-v1', 'link0'),
        'panda-v1/ee': FrameReference('panda-v1', 'ee'),
        'cube-v1': FrameReference('cube-v1', 'cube'),
    }
