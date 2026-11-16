"""Fake camera routing, source identity, clock and state isolation checks."""
from types import SimpleNamespace
import pytest
from task_env.diagnostics.tasks.physical_contract_fixtures import _case
from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.render.camera.source import DynamicCameraRenderSourceV2


def _env(renderer):
    compiled, _, _, _ = _case()
    artifact = SimpleNamespace(identity_hash='a' * 64, legacy_frame_bindings={})
    source = SimpleNamespace(
        scene_definition=compiled.scene, source_id='source-a',
        source_closure_digest='b' * 64, task_artifact_hash=artifact.identity_hash,
        joints={'arm/drive': 'drive'}, bodies={}, frames={}, free_joints={},
    )
    env = object.__new__(SelectedReferenceEnv)
    env.artifact = artifact
    env.value = {'source': source}
    env._task_rgb_config = (object(), renderer)
    return env, source


@pytest.mark.parametrize('renderer', ('isaacsim', 'geophys'))
def test_borrowed_camera_state_does_not_require_mujoco_source(monkeypatch, renderer):
    env, source = _env(renderer)
    def unexpected(*args, **kwargs):
        raise AssertionError('borrowed camera must not construct a MuJoCo visual source')
    monkeypatch.setattr(DynamicCameraRenderSourceV2, 'from_runtime_source', unexpected)
    binding = env._prepare_task_rgb_state_binding()
    assert binding[0] is source
    assert 'arm/drive' in binding[3]
    assert binding[-1] is None


def test_mujoco_renderer_still_requires_its_source_adapter(monkeypatch):
    env, source = _env('mujoco')
    calls = []
    projection = SimpleNamespace(
        validate_binding_provenance=lambda: calls.append('validated'),
    )
    def construct(actual_source, **kwargs):
        calls.append(actual_source)
        return projection
    monkeypatch.setattr(DynamicCameraRenderSourceV2, 'from_runtime_source', construct)
    assert env._prepare_task_rgb_state_binding()[-1] is projection
    assert calls == [source, 'validated']


def test_task_rgb_rejects_foreign_artifact_before_renderer_selection():
    env, source = _env('isaacsim')
    source.task_artifact_hash = 'f' * 64
    with pytest.raises(ValueError, match='Artifact'):
        env._prepare_task_rgb_state_binding()


def test_task_rgb_clock_mapping_records_epoch_without_rewriting_timeline():
    from task_env.runtime.sessions.isaac_native_io import _task_render_clock_mapping

    receipt = _task_render_clock_mapping(provider_time_s=0.036, episode_time_s=0.0)

    assert receipt['schema_version'] == 'isaac-task-render-clock-observation-v1'
    assert receipt['episode_time_s'] == 0.0
    assert receipt['provider_time_s'] == pytest.approx(0.036)
    assert receipt['provider_epoch_offset_s'] == pytest.approx(0.036)
    assert receipt['timeline_mutated'] is False
    assert receipt['physics_step_requested'] is False
    with pytest.raises(ValueError, match='finite'):
        _task_render_clock_mapping(provider_time_s=float('nan'), episode_time_s=0.0)


def test_task_rgb_state_projection_preserves_controller_publication(monkeypatch):
    from task_env import artifacts

    class Publication:
        def __init__(self, boundary):
            self.view = SimpleNamespace(
                boundary=boundary,
                sample_clock=SimpleNamespace(simulation_time_s=0.0),
                validate_against_scene=lambda _scene: None,
                validate_requirements=lambda _requirements: None,
            )
            self.lifetime = SimpleNamespace(may_be_retained=True)

    monkeypatch.setattr(artifacts, 'CanonicalStatePublicationV1', Publication)
    env, source = _env('isaacsim')
    scene = source.scene_definition
    boundary = SimpleNamespace(control_step=0)
    publication = Publication(boundary)
    env.artifact.timebase = SimpleNamespace(
        control_dt=0.01, physics_dt=0.002, control_substeps=5,
    )
    env.session = SimpleNamespace(
        state_boundary_identity=lambda: boundary,
        snapshot_v1=lambda **_kwargs: publication,
    )
    env.state = SimpleNamespace(control_step=0, simulation_time=0.0)
    env._task_rgb_state_binding = (
        source, env.artifact.identity_hash, scene, {}, {}, object(), None,
    )
    controller_publication = object()
    env.typed_state = controller_publication

    assert env._publish_task_rgb_typed_state(env.state) is publication
    assert env._task_rgb_typed_state is publication
    assert env.typed_state is controller_publication

    with pytest.raises(ValueError, match='stale or differs from Runtime readback'):
        env._publish_task_rgb_typed_state(
            SimpleNamespace(control_step=1, simulation_time=0.0),
        )
    assert env.typed_state is controller_publication
    assert env._task_rgb_typed_state is None


def test_observation_captures_the_camera_projection_not_controller_state():
    import numpy as np

    env = object.__new__(SelectedReferenceEnv)
    env.mixed_control_profile = False
    env.binding = SimpleNamespace(
        observation_projection=lambda _env, state: ({'state': state}, {}, 'evaluation'),
    )
    env._task_rgb_config = (object(), 'isaacsim')
    camera_view = object()
    camera_publication = SimpleNamespace(view=camera_view)
    env._publish_task_rgb_typed_state = lambda _state: camera_publication
    env.typed_state = object()
    frame = np.zeros((2, 2, 3), dtype=np.float32)
    captured = []
    env._task_rgb_consumer = SimpleNamespace(
        capture=lambda state: captured.append(state) or (frame, {'capture': 'receipt'}),
    )
    env._selected_execution_context = lambda: (None, None)

    observation, info, evaluation = env.observation(object())

    assert captured == [camera_view]
    assert observation['task_rgb'] is frame
    assert info['task_rgb_v1'] == {'capture': 'receipt'}
    assert evaluation == 'evaluation'
