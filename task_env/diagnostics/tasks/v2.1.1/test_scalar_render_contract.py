"""Public rendering/configuration regressions; no native renderer is started."""
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.mark.parametrize('uid', ['pendulum-v1', 'pick-cube-p16-reference-v1'])
@pytest.mark.parametrize('scope', ['scalar', 'device_batch'])
def test_render_overlay_survives_resolved_roundtrip(uid, scope, tmp_path):
    import task_env.tasks
    from task_env.registry import ENV_REGISTRY
    from task_env.environment.configuration import resolve_task_env_config

    env_type = ENV_REGISTRY.get(uid)
    config = {'execution': {'physics_provider': 'geophys'},
              'render': {'backend': 'rasterizer', 'width': 72, 'height': 48}}
    resolved = resolve_task_env_config(env_type, config, execution_scope=scope)
    assert (resolved.environment.render.width, resolved.environment.render.height) == (72, 48)
    assert resolve_task_env_config(env_type, resolved, execution_scope=scope) == resolved
    import yaml
    path = tmp_path / 'caller.yaml'
    path.write_text(yaml.safe_dump(config))
    assert resolve_task_env_config(env_type, path, execution_scope=scope) == resolved


def test_scalar_rejects_metadata_only_sensor_configuration():
    from task_env.tasks.pendulum import PendulumEnv
    from task_env.environment.configuration import resolve_task_env_config

    with pytest.raises(ValueError, match='observations are not implemented'):
        resolve_task_env_config(PendulumEnv, {'render': {
            'camera_obs': True, 'cameras': [{'name': 'base'}]}})


def test_rgb_export_is_owned_uint8_without_mutating_sensor_frame():
    from task_env.render.providers.single import TaskEnvRenderProvider
    from task_env.render.base.contracts import RenderMode

    source = np.array([[[-.1, .5, 1.1]]], dtype=np.float32)
    original = source.copy()
    capture = SimpleNamespace(rgb=source,
        metadata=SimpleNamespace(to_mapping=lambda: {}),
        capture_identity=SimpleNamespace(to_mapping=lambda: {}))
    provider = TaskEnvRenderProvider(render_source=None,
        config=SimpleNamespace(width=1, height=1), frame_capture=lambda: capture)
    try:
        frame = provider.render(mode=RenderMode.RGB_ARRAY, snapshot=None)
        np.testing.assert_array_equal(frame, [[[0, 128, 255]]])
        assert frame.dtype == np.uint8 and frame.flags.c_contiguous
        frame[:] = 0
        np.testing.assert_array_equal(source, original)
    finally:
        provider.close()


def test_selected_interval_presents_only_after_publication():
    from task_env.environment.lifecycle import EpisodeExecutionState

    events = []
    env = SimpleNamespace(render_mode='human', state=object(), obs=object(),
                          render=lambda: events.append('render'))
    def publish(*_):
        events.append('publish')
        return 'transition'
    state = EpisodeExecutionState()
    result = state.execute_selected_interval(env, apply_control=lambda: None,
        advance=lambda _: None, evaluate=lambda _: None, publish=publish,
        on_failure=lambda *_: pytest.fail('unexpected interval failure'))
    assert result == 'transition' and events == ['publish', 'render']


def test_no_render_mode_does_not_allocate_ui_provider():
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.environment.lifecycle import EpisodeExecutionState

    env = SimpleNamespace(render_mode=None,
                          _episode_execution_state=lambda: EpisodeExecutionState())
    assert SelectedReferenceEnv.render(env) is None


def test_observer_projects_state_without_a_position_controller_publication():
    from task_env.environment.reference_env import SelectedReferenceEnv

    expected = object()
    env = SimpleNamespace(_published_position_typed_state=None, _execution_fault=None,
        session=object(), state=object(), _task_rgb_state_binding=object(),
        _publish_task_rgb_typed_state=lambda _: expected)
    assert SelectedReferenceEnv._observer_publication(env) is expected


def test_remote_rgb_roundtrip_preserves_camera_and_rejects_corrupt_bytes():
    from dataclasses import replace
    from task_env.diagnostics.phase1.camera.fixtures import camera
    from task_env.diagnostics.phase1.camera.checks import state
    from task_env.observations.canonical_camera import resolve_camera
    from task_env.observations.canonical_camera.images import CanonicalCameraObservation
    from task_env.runtime.sessions.transport import _encode, _decode

    metadata = resolve_camera(replace(camera('world'), depth=False), state())
    pixels = np.linspace(0, 1, metadata.camera.height * metadata.camera.width * 3,
                         dtype=np.float32).reshape(metadata.camera.height, metadata.camera.width, 3)
    encoded = _encode(CanonicalCameraObservation(pixels, None, metadata))
    decoded = _decode(encoded)
    np.testing.assert_array_equal(decoded.rgb, pixels)
    assert decoded.metadata == metadata and not np.shares_memory(decoded.rgb, pixels)
    encoded['value']['rgb'] = ''
    with pytest.raises(ValueError, match='bytes differ'):
        _decode(encoded)


def test_closed_device_window_is_not_reopened_by_automatic_presentation():
    from task_env.render.rasterizer.device import DeviceBatchRasterSource

    destroyed = []
    source = DeviceBatchRasterSource(runtime=None, source=None)
    source._visualizer = SimpleNamespace(close=lambda: None)
    source._window = SimpleNamespace(running=False, destroy=lambda: destroyed.append(True))
    source.present_parallel(frame=None, world_ids=(), world_transforms=())
    source.present_parallel(frame=None, world_ids=(), world_transforms=())
    assert destroyed == [True] and source._window is None
    source.close()
