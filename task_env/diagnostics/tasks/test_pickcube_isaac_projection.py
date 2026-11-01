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


def test_f06_reset_materializes_the_exact_rebuilt_runtime_input_artifact():
    from dataclasses import dataclass
    from types import SimpleNamespace
    from unittest.mock import patch

    from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
    from task_env.runtime.sessions.control import ControlBindingPlanV1
    from task_env.runtime.sessions.api import F06_PICKCUBE_ISAAC_PROFILE
    from task_env.tasks.reference_env import SelectedReferenceEnv

    @dataclass(frozen=True)
    class Artifact:
        identity_hash: str

    initial_artifact = Artifact('a' * 64)
    rebuilt_artifact = Artifact('a' * 64)
    assert rebuilt_artifact == initial_artifact
    assert rebuilt_artifact is not initial_artifact

    reset_plan = SimpleNamespace(reset_sample=SimpleNamespace(task_seed=31))
    execution = ExecutionSpecV1(
        schema_version='execution-spec-v1',
        physics_provider='isaacsim',
        physics_backend='cuda',
        physics_profile=F06_PICKCUBE_ISAAC_PROFILE,
        provider_seed=31,
        determinism_mode='best_effort',
        render_default=RendererSelectionV1(
            'renderer-selection-v1', 'none', 'none', 'none',
        ),
        physics_device='cuda:0',
    )
    runtime_input = SimpleNamespace(artifact=rebuilt_artifact, reset_plan=reset_plan)
    source = SimpleNamespace(
        scene_definition=SimpleNamespace(articulations=()),
        free_joints={}, bodies={}, frames={},
    )
    plan = ControlBindingPlanV1(
        'control-binding-plan-v1', 'b' * 64, (), (),
    )
    rebuilt_value = {
        'artifact': rebuilt_artifact,
        'source': source,
        'reset_plan': reset_plan,
        'execution_spec_v1': execution,
        'f06_pickcube_isaac_input': runtime_input,
        'controller_binding_plan': plan,
        'solution': None,
    }

    env = object.__new__(SelectedReferenceEnv)
    env._closed = False
    env._stopped = False
    env.position_profile = True
    env.leaf_position_profile = False
    env.fixed_attachment_leaf_position_profile = False
    env.position_profiles = (object(),)
    env.position_plan = plan
    env.provider, env.backend, env.horizon = 'isaacsim', 'cuda', 1000
    env.artifact = initial_artifact
    env.value = {'artifact': initial_artifact, 'reset_plan': reset_plan}
    env.binding = SimpleNamespace(
        reset_seed=lambda seed: seed,
        build_seeded=lambda *_args: rebuilt_value,
    )
    env._diagnostic_profile = None
    env._position_episode_end = None
    env.session = None
    env.recorder = None
    env._declared_execution_spec_v1 = execution
    env._close_camera_consumer = lambda: None
    env._bind_selected_controller = lambda _value: None
    env._latch_fault = lambda _phase, _error: None

    class StopAtMaterialization(Exception):
        pass

    observed = {}

    def capture_materialization(artifact, *_args, **_kwargs):
        observed['artifact'] = artifact
        raise StopAtMaterialization

    with patch('task_env.tasks.reference_env.materialize_control', capture_materialization):
        try:
            env.reset(seed=31)
        except StopAtMaterialization:
            pass
        else:
            raise AssertionError('the reset did not reach the materialization boundary')

    assert observed['artifact'] is rebuilt_artifact
    assert observed['artifact'] is runtime_input.artifact
