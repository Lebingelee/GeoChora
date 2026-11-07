"""Provider-free checks for observer frame ownership and invalidation."""
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.render.base.contracts import RenderMode
from task_env.render.providers.single import TaskEnvRenderProvider


class _Mapping:
    def __init__(self, value):
        self.value = value

    def to_mapping(self):
        return self.value


def test_rgb_render_returns_independent_copy_and_invalidates_on_capture_failure():
    native = np.full((2, 3, 3), 0.25, dtype=np.float32)
    state = {'fail': False}

    def capture():
        if state['fail']:
            raise RuntimeError('readback failed')
        return SimpleNamespace(rgb=native, metadata=_Mapping({'camera': 'observer'}),
                               capture_identity=_Mapping({'boundary': 7}))

    provider = TaskEnvRenderProvider(render_source=None,
        config=SimpleNamespace(width=3, height=2), frame_capture=capture)
    frame = provider.render(mode=RenderMode.RGB_ARRAY, snapshot=None)
    assert frame.flags.owndata and not np.shares_memory(frame, native)
    native[:] = 0.75
    assert np.all(frame == 0.25)
    assert provider.last_frame_receipt['capture_identity'] == {'boundary': 7}
    state['fail'] = True
    with pytest.raises(RuntimeError, match='readback failed'):
        provider.render(mode=RenderMode.RGB_ARRAY, snapshot=None)
    assert provider.last_frame_receipt is None
    provider.close()
    provider.close()
    with pytest.raises(RuntimeError, match='closed'):
        provider.render(mode=RenderMode.RGB_ARRAY, snapshot=None)


def test_isaac_observer_request_rejects_unrelated_routes_and_modalities():
    from dataclasses import replace
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.observations.canonical_camera.contracts import IDENTITY
    from task_env.render.base.contracts import ObserverRenderRequestV1

    camera = CameraGeometry('camera-observation-v0', 'a' * 64, 'observer', 'world',
                            IDENTITY, IDENTITY, 320, 240, 1.0, .01, 10.0, True, False)
    artifact = SimpleNamespace(identity_hash='a' * 64)
    request = ObserverRenderRequestV1(camera, 'rgb_array', 'isaacsim', 'rtx')
    request.validate(artifact=artifact, physics_provider='isaacsim', physics_backend='cuda')
    with pytest.raises(ValueError, match='physics route'):
        request.validate(artifact=artifact, physics_provider='geophys', physics_backend='cpu')
    with pytest.raises(ValueError, match='RGB contract'):
        replace(request, camera=replace(camera, depth=True)).validate(
            artifact=artifact, physics_provider='isaacsim', physics_backend='cuda')
    geo = ObserverRenderRequestV1(camera, 'rgb_array', 'geophys', 'rasterizer')
    geo.validate(artifact=artifact, physics_provider='geophys', physics_backend='cpu')
    with pytest.raises(ValueError, match='physics route'):
        geo.validate(artifact=artifact, physics_provider='geophys', physics_backend='cuda')


def test_usd_observer_rejects_stale_boundary_before_native_capture(monkeypatch):
    from task_env.runtime.sessions.native_io import UsdCoreRuntimeSession

    session = object.__new__(UsdCoreRuntimeSession)
    observed = []
    session._native_io = SimpleNamespace(capture_observer=lambda *args: observed.append(args))
    monkeypatch.setattr(session, '_require_reset', lambda: None)
    monkeypatch.setattr(session, '_assert_native_identity', lambda: None)
    monkeypatch.setattr(session, 'state_boundary_identity', lambda: 'current')
    with pytest.raises(ValueError, match='current state boundary'):
        session.capture_observer(object(), SimpleNamespace(boundary='old'))
    assert observed == []


def test_failed_present_does_not_publish_capture_receipt():
    frame = SimpleNamespace(rgb=np.ones((2, 3, 3), dtype=np.float32),
                            metadata=_Mapping({'camera': 'observer'}),
                            capture_identity=_Mapping({'boundary': 1}))
    def fail_present():
        raise RuntimeError('presentation failed')
    provider = TaskEnvRenderProvider(render_source=None,
        config=SimpleNamespace(width=3, height=2), frame_capture=lambda: frame,
        frame_presenter=fail_present)
    with pytest.raises(RuntimeError, match='presentation failed'):
        provider.render(mode=RenderMode.HUMAN, snapshot=None)
    assert provider.last_frame_receipt is None
    provider.close()


def test_usd_observer_rejects_changed_native_state(monkeypatch):
    from task_env.runtime.sessions.native_io import UsdCoreRuntimeSession
    session = object.__new__(UsdCoreRuntimeSession)
    readbacks = iter(('before', 'after'))
    session._native_io = SimpleNamespace(read_state=lambda: next(readbacks),
                                         capture_observer=lambda *_args: object())
    monkeypatch.setattr(session, '_require_reset', lambda: None)
    monkeypatch.setattr(session, '_assert_native_identity', lambda: None)
    monkeypatch.setattr(session, 'state_boundary_identity', lambda: 'current')
    with pytest.raises(RuntimeError, match='physics state or boundary changed'):
        session.capture_observer(object(), SimpleNamespace(boundary='current'))


def test_mujoco_rgb_rejects_unverified_framebuffer_encoding(monkeypatch):
    """An sRGB-enabled or unavailable framebuffer cannot claim the linear profile."""
    import ctypes
    import ctypes.util
    from task_env.render.camera.mujoco import MuJoCoDynamicCameraSession

    class Function:
        def __init__(self, function):
            self.function = function
        def __call__(self, *args):
            return self.function(*args)

    def library(*, encoding=0x2601, enabled=False, error=0):
        def integer(_name, output):
            ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = 1
        def attachment(_target, _attachment, _name, output):
            ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = encoding
        return SimpleNamespace(glIsEnabled=Function(lambda _name: enabled),
            glGetIntegerv=Function(integer), glGetFramebufferAttachmentParameteriv=Function(attachment),
            glGetError=Function(lambda: error))

    monkeypatch.setattr(ctypes.util, 'find_library', lambda _name: 'GL')
    monkeypatch.setattr(ctypes, 'CDLL', lambda _name: library())
    MuJoCoDynamicCameraSession._verify_linear_framebuffer()
    monkeypatch.setattr(ctypes, 'CDLL', lambda _name: library(enabled=True))
    with pytest.raises(RuntimeError, match='linear-encoded'):
        MuJoCoDynamicCameraSession._verify_linear_framebuffer()
    monkeypatch.setattr(ctypes, 'CDLL', lambda _name: library(encoding=0x8C40))
    with pytest.raises(RuntimeError, match='linear-encoded'):
        MuJoCoDynamicCameraSession._verify_linear_framebuffer()
    monkeypatch.setattr(ctypes.util, 'find_library', lambda _name: None)
    with pytest.raises(RuntimeError, match='cannot be checked'):
        MuJoCoDynamicCameraSession._verify_linear_framebuffer()


def test_mujoco_encoding_failure_faults_and_closes_renderer(monkeypatch):
    from task_env.render.camera.api import V211_RGB_PROFILE
    from task_env.render.camera.mujoco import MuJoCoDynamicCameraSession
    from task_env.render.camera.mujoco import CameraSessionValues

    session = object.__new__(MuJoCoDynamicCameraSession)
    session._manifest = SimpleNamespace(render_profile=V211_RGB_PROFILE)
    session._source = SimpleNamespace(schema_version='camera-dynamic-source-v2')
    session._last_projection = session._last_sync = object()
    closed = []
    monkeypatch.setattr(session, '_require_trustworthy', lambda: None)
    monkeypatch.setattr(CameraSessionValues, 'capture', lambda *_args: object())
    monkeypatch.setattr(session, '_verify_linear_framebuffer',
                        lambda: (_ for _ in ()).throw(RuntimeError('encoding unavailable')))
    monkeypatch.setattr(session, 'close', lambda: closed.append(True))
    with pytest.raises(RuntimeError, match='encoding unavailable'):
        session.capture(object())
    assert session._faulted and session._last_projection is None and session._last_sync is None
    assert closed == [True]


def test_isaac_observer_clock_regression_invalidates_runtime():
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1
    native = object.__new__(IsaacSimNativeRuntimeIOV1)
    native._episode_origin_step = 18
    native._episode_origin_time = .036
    native._counter = lambda: (0, 0.0)
    with pytest.raises(RuntimeError, match='changed the physics clock'):
        native._check_observer_clock((18, .036), playing=False, operation='observer rendering')
    assert native._observer_runtime_invalid
    assert native._episode_origin_step is None and native._episode_origin_time is None
    native._closed = False
    with pytest.raises(RuntimeError, match='rebuild required'):
        native.write_reset(None, ())


def test_isaac_owner_rejects_stopped_app_before_rebuild():
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1
    owner = IsaacSimAppOwnerV1()
    owner._app = SimpleNamespace(is_running=lambda: False)
    with pytest.raises(RuntimeError, match='new worker is required'):
        owner.open()


def test_isaac_clock_failure_invalidates_shared_app_owner():
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1, IsaacSimNativeRuntimeIOV1
    owner = IsaacSimAppOwnerV1()
    owner._app = SimpleNamespace(is_running=lambda: True)
    native = object.__new__(IsaacSimNativeRuntimeIOV1)
    native._app_owner = owner
    native._episode_origin_step, native._episode_origin_time = 18, .036
    native._counter = lambda: (0, 0.0)
    with pytest.raises(RuntimeError, match='changed the physics clock'):
        native._check_observer_clock((18, .036), playing=False, operation='capture')
    with pytest.raises(RuntimeError, match='new worker is required'):
        owner.open()


def test_isaac_viewport_rejects_stale_camera_and_wrong_projection():
    import math
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1
    width, height, fov, near, far = 320, 240, math.pi / 3, .01, 10.
    world = np.eye(4)
    world[:3, 3] = [.6, -1.1, .85]
    contract = (world, width, height, fov, near, far)
    focal = 1. / math.tan(fov / 2.)
    projection = [0.] * 16
    projection[0], projection[5] = focal * height / width, focal
    projection[10], projection[14] = near / (far-near), near*far / (far-near)
    correct = {'view': np.linalg.inv(world).T.reshape(-1).tolist(),
               'projection': projection, 'resolution': (width, height)}
    matches = IsaacSimNativeRuntimeIOV1._viewport_frame_matches_observer
    assert matches(correct, contract)
    assert not matches({**correct, 'view': np.eye(4).reshape(-1).tolist()}, contract)
    assert not matches({**correct, 'resolution': (1280, 720)}, contract)
    wrong_projection = projection.copy()
    wrong_projection[14] = .02
    assert not matches({**correct, 'projection': wrong_projection}, contract)
    assert not matches({'resolution': (width, height)}, contract)


def test_gamma22_output_converts_to_srgb_transfer_and_rejects_invalid():
    from task_env.render.camera.color import gamma22_to_srgb

    linear = np.array([0., .0031308, .18, .5, 1.], dtype=np.float32)
    native = np.repeat(np.power(linear, 1. / 2.2)[:, None, None], 3, axis=2)
    expected = np.array([0., .040449936, .4613561, .73535698, 1.], dtype=np.float32)
    converted = gamma22_to_srgb(native)
    np.testing.assert_allclose(converted[:, 0, 0], expected, rtol=0, atol=2e-6)
    assert converted.dtype == np.float32 and converted.flags.c_contiguous
    with pytest.raises(ValueError, match='finite HWC float32'):
        gamma22_to_srgb(np.full((1, 1, 3), np.nan, dtype=np.float32))
    with pytest.raises(ValueError, match='finite HWC float32'):
        gamma22_to_srgb(np.full((1, 1, 3), 1.01, dtype=np.float32))


def _fake_mjcf_render_source(visualizer):
    track = SimpleNamespace(light_id='mjcf:light:top', light_type='spot', direction=(0., 0., 1.),
                            runtime_payload={'mjcf_kind': 'world_trackcom', 'authored_position': (0., 0., 2.)})
    head = SimpleNamespace(light_type='directional', runtime_payload={'mjcf_kind': 'headlight'})
    desc = SimpleNamespace(mjcf_light_table=SimpleNamespace(records=(track, head)))
    return SimpleNamespace(read_render_scene=lambda **_kw: desc, build_visualizer=lambda **_kw: visualizer)


def test_geophys_observer_propagates_camera_and_invalidates_on_state_change(monkeypatch):
    from task_env.diagnostics.tasks.test_v211_render_binding import _values
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.observations.canonical_camera.contracts import IDENTITY
    from task_env.runtime.sessions.geophys import _GeoPhysSession

    source, state = _values()
    camera = CameraGeometry('camera-observation-v0', source.task_artifact_hash, 'observer', 'world',
                            IDENTITY, IDENTITY, 3, 2, 1., .1, 10., True, False)
    calls = []
    class Visualizer:
        closed = False
        def set_camera_pose(self, *value): calls.append(('pose', value))
        def set_fov(self, value): calls.append(('fov', value))
        def set_clip_interval(self, near, far): calls.append(('clip', (near, far)))
        def update_mjcf_light_pose(self, light_id, **value): calls.append(('light', light_id, value))
        def read_resources(self): return {'material_features': {'missing_required': [], 'unsupported_authored': []},
                                          'light_features': {'uses_default_sun': False, 'unsupported': []},
                                          'lighting': {'unshadowed_casting_lights': []}}
        def read_frame(self, *, synchronized):
            assert synchronized
            return np.full((2, 3, 3), .5, dtype=np.float32)
        def close(self): self.closed = True

    visualizer = Visualizer()
    session = object.__new__(_GeoPhysSession)
    session._observer_render_request = object()
    session._observer_render_source = _fake_mjcf_render_source(visualizer)
    session._observer_visualizer = None
    session._observer_fault = False
    session._source = SimpleNamespace(source_closure_digest='b' * 64)
    session._observer_execution_identity = 'd' * 64
    session._observer_com_bodies = [{'name': 'a', 'mass_kg': 1., 'com_body_m': [0., 0., 0.]}]
    session._observer_com_ids = {'a': 0}
    session._observer_rest_com = np.zeros(3)
    session._boundary = SimpleNamespace(read_snapshot=lambda _request: SimpleNamespace(
        body_xpos=[[1., 0., 0.]], body_xquat=[[1., 0., 0., 0.]]))
    monkeypatch.setattr(session, '_require_reset', lambda: None)
    monkeypatch.setattr(session, 'state_boundary_identity', lambda: state.boundary)
    monkeypatch.setattr(session, '_snapshot_with_native_free_joints', lambda: ('unchanged',))
    result = session.capture_observer(camera, state)
    assert result.capture_identity.state_boundary == state.boundary
    assert result.rgb.shape == (2, 3, 3) and result.rgb.flags.owndata
    assert ('clip', (.1, 10.)) in calls
    assert calls[0][0] == 'pose' and ('fov', camera.fov_y * 180 / np.pi) in calls
    assert np.allclose(calls[1][2]['position'], [1., 0., 2.])

    samples = iter(('before', 'after'))
    monkeypatch.setattr(session, '_snapshot_with_native_free_joints', lambda: next(samples))
    with pytest.raises(RuntimeError, match='physics state or boundary changed'):
        session.capture_observer(camera, state)
    assert visualizer.closed and session._observer_fault
    with pytest.raises(RuntimeError, match='requires a new runtime'):
        session.capture_observer(camera, state)


def test_geophys_observer_rejects_degraded_materials_before_capture(monkeypatch):
    from task_env.diagnostics.tasks.test_v211_render_binding import _values
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.observations.canonical_camera.contracts import IDENTITY
    from task_env.runtime.sessions.geophys import _GeoPhysSession

    source, state = _values()
    camera = CameraGeometry('camera-observation-v0', source.task_artifact_hash, 'observer', 'world',
                            IDENTITY, IDENTITY, 3, 2, 1., .1, 10., True, False)
    closed = []
    visualizer = SimpleNamespace(
        read_resources=lambda: {'material_features': {'missing_required': ['alpha_blending']}},
        close=lambda: closed.append(True))
    session = object.__new__(_GeoPhysSession)
    session._observer_render_request = object()
    session._observer_render_source = _fake_mjcf_render_source(visualizer)
    session._observer_visualizer = None
    session._observer_fault = False
    monkeypatch.setattr(session, '_require_reset', lambda: None)
    monkeypatch.setattr(session, 'state_boundary_identity', lambda: state.boundary)
    monkeypatch.setattr(session, '_snapshot_with_native_free_joints', lambda: ('unchanged',))
    with pytest.raises(RuntimeError, match='alpha_blending'):
        session.capture_observer(camera, state)
    assert closed == [True] and session._observer_fault


def test_geophys_observer_rejects_default_light_before_capture(monkeypatch):
    from task_env.diagnostics.tasks.test_v211_render_binding import _values
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.observations.canonical_camera.contracts import IDENTITY
    from task_env.runtime.sessions.geophys import _GeoPhysSession

    source, state = _values()
    camera = CameraGeometry('camera-observation-v0', source.task_artifact_hash, 'observer', 'world',
                            IDENTITY, IDENTITY, 3, 2, 1., .1, 10., True, False)
    closed = []
    visualizer = SimpleNamespace(
        read_resources=lambda: {'material_features': {'missing_required': [], 'unsupported_authored': []},
                                'light_features': {'uses_default_sun': True, 'unsupported': []}},
        close=lambda: closed.append(True))
    session = object.__new__(_GeoPhysSession)
    session._observer_render_request = object()
    session._observer_render_source = _fake_mjcf_render_source(visualizer)
    session._observer_visualizer = None
    session._observer_fault = False
    monkeypatch.setattr(session, '_require_reset', lambda: None)
    monkeypatch.setattr(session, 'state_boundary_identity', lambda: state.boundary)
    monkeypatch.setattr(session, '_snapshot_with_native_free_joints', lambda: ('unchanged',))
    with pytest.raises(RuntimeError, match='cannot preserve authored lighting'):
        session.capture_observer(camera, state)
    assert closed == [True] and session._observer_fault


def test_geophys_close_releases_all_resources_after_pending_interval_failure():
    from task_env.runtime.sessions.geophys import _GeoPhysSession

    events = []
    def fail_interval():
        events.append('interval')
        raise RuntimeError('interval cleanup failed')
    session = object.__new__(_GeoPhysSession)
    session._closed = False
    session._physical_port = SimpleNamespace(pending=object(), finish_interval=fail_interval)
    session._observer_visualizer = SimpleNamespace(close=lambda: events.append('visualizer'))
    session._boundary = SimpleNamespace(close=lambda: events.append('boundary'))
    session._source = SimpleNamespace(
        execution_source_receipt=SimpleNamespace(close=lambda: events.append('source')),
        scene_source=SimpleNamespace(source_id='scene'), source_closure_digest='a' * 64)
    session._provider_materialization_id = 'provider'
    session._episode_id = 'episode'
    session._reset_sample_id = 'reset'
    session._control_step = session._native_steps = 0
    session._observer_fault = False
    session._observer_material_report = {}
    with pytest.raises(RuntimeError, match='interval cleanup failed'):
        session.close()
    assert events == ['interval', 'visualizer', 'boundary', 'source']
    assert session._closed and session._last_close_receipt['boundary_close_completed']
    assert not session._last_close_receipt['cleanup_completed']
    with pytest.raises(RuntimeError, match='no current admitted material report'):
        session.observer_render_facts()
    session.close()
    assert len(events) == 4


def test_geophys_missing_observer_source_keeps_primary_error_on_close_failure(monkeypatch):
    import task_env.runtime.sessions.geophys as module

    def fail_close():
        raise RuntimeError('boundary close failed')
    runtime = SimpleNamespace(render_source=None, boundary=SimpleNamespace(close=fail_close))
    monkeypatch.setattr(module._GeoPhysSession, '_initialize_values', lambda *_args: None)
    monkeypatch.setattr(module, 'bootstrap_task_runtime', lambda **_kwargs: runtime)
    monkeypatch.setattr(module, 'GeoPhysSourceComposer', lambda *_args, **_kwargs: object())
    source = SimpleNamespace(config=None, composition=None, scene=None, agents=None, objects=None,
                             scene_source=None, scene_definition=None, execution_source_receipt=None)
    with pytest.raises(RuntimeError, match='observer source could not be materialized') as error:
        module._GeoPhysSession(None, source, observer_render_request=object())
    assert any('boundary close failed' in note for note in error.value.__notes__)


def test_geophys_observer_rejects_unshadowed_authored_light(monkeypatch):
    from task_env.diagnostics.tasks.test_v211_render_binding import _values
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.observations.canonical_camera.contracts import IDENTITY
    from task_env.runtime.sessions.geophys import _GeoPhysSession

    source, state = _values()
    camera = CameraGeometry('camera-observation-v0', source.task_artifact_hash, 'observer', 'world',
                            IDENTITY, IDENTITY, 3, 2, 1., .1, 10., True, False)
    closed = []
    visualizer = SimpleNamespace(
        read_resources=lambda: {'material_features': {'missing_required': [], 'unsupported_authored': []},
                                'light_features': {'uses_default_sun': False, 'unsupported': []},
                                'lighting': {'unshadowed_casting_lights': ['mjcf:light:top']}},
        close=lambda: closed.append(True))
    session = object.__new__(_GeoPhysSession)
    session._observer_render_request = object()
    session._observer_render_source = _fake_mjcf_render_source(visualizer)
    session._observer_visualizer = None
    session._observer_fault = False
    monkeypatch.setattr(session, '_require_reset', lambda: None)
    monkeypatch.setattr(session, 'state_boundary_identity', lambda: state.boundary)
    monkeypatch.setattr(session, '_snapshot_with_native_free_joints', lambda: ('unchanged',))
    with pytest.raises(RuntimeError, match='cannot preserve authored shadows'):
        session.capture_observer(camera, state)
    assert closed == [True] and session._observer_fault


def test_isaac_observer_color_admission_fails_closed():
    from task_env.runtime.sessions.isaac_native_io import (
        _ISAAC_62_OBSERVER_COLOR_SETTINGS, _ISAAC_62_OBSERVER_OCIO_SHA256,
        _validate_isaac_observer_color_settings,
    )
    values = dict(_ISAAC_62_OBSERVER_COLOR_SETTINGS)
    result = _validate_isaac_observer_color_settings(values, _ISAAC_62_OBSERVER_OCIO_SHA256)
    assert result['ocio_sha256'] == _ISAAC_62_OBSERVER_OCIO_SHA256
    values['/rtx/post/tonemap/enableSrgbToGamma'] = False
    with pytest.raises(RuntimeError, match='color settings are not qualified'):
        _validate_isaac_observer_color_settings(values, _ISAAC_62_OBSERVER_OCIO_SHA256)
    values = dict(_ISAAC_62_OBSERVER_COLOR_SETTINGS)
    values['/rtx/post/tonemap/colorMode'] = False
    with pytest.raises(RuntimeError, match='color settings are not qualified'):
        _validate_isaac_observer_color_settings(values, _ISAAC_62_OBSERVER_OCIO_SHA256)
    values = dict(_ISAAC_62_OBSERVER_COLOR_SETTINGS)
    values['/rtx/post/tonemap/ocio/view'] = 'unqualified-view'
    with pytest.raises(RuntimeError, match='color settings are not qualified'):
        _validate_isaac_observer_color_settings(values, _ISAAC_62_OBSERVER_OCIO_SHA256)
    with pytest.raises(RuntimeError, match='OCIO configuration is not qualified'):
        _validate_isaac_observer_color_settings(_ISAAC_62_OBSERVER_COLOR_SETTINGS, '0' * 64)
