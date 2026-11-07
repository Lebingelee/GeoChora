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


def test_task_camera_declaration_and_readback_guard():
    from dataclasses import replace
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.observations.canonical_camera.contracts import IDENTITY

    camera = CameraGeometry('camera-observation-v0', 'a' * 64, 'task', 'world',
                            IDENTITY, IDENTITY, 320, 240, 1.0, .01, 10., True, False)
    env = object.__new__(SelectedReferenceEnv)
    env.artifact = SimpleNamespace(identity_hash='a' * 64)
    env.provider = 'isaacsim'
    env._execution_fault = None
    env._published_position_typed_state = SimpleNamespace(view='publication')
    calls = []
    env.session = SimpleNamespace(task_camera_binding=lambda *args: calls.append(args) or 'read')
    assert env.task_camera_binding() == 'read'
    assert calls == [('publication',)]
    from task_env.tasks.pick_cube.physical_isaac_candidate import PickCubeIsaacPhysicalCandidateEnv
    with pytest.raises(ValueError, match='world mounts'):
        PickCubeIsaacPhysicalCandidateEnv.from_reference_config(
            {}, render_mode='human', task_camera=replace(camera, parent_frame='hand'))
    with pytest.raises(ValueError, match='observer-enabled'):
        PickCubeIsaacPhysicalCandidateEnv.from_reference_config({}, task_camera=camera)
    with pytest.raises(ValueError, match='distinct identities'):
        PickCubeIsaacPhysicalCandidateEnv.from_reference_config(
            {}, render_mode='human', observer_camera=camera, task_camera=camera)
    env._declared_task_camera = camera
    env._selected_observer_camera = replace(camera, camera_id='observer')
    with pytest.raises(ValueError, match='distinct identities'):
        env.set_observer_camera(camera)
    env._published_position_typed_state = None
    with pytest.raises(RuntimeError, match='published state'):
        env.task_camera_binding()


def test_usd_task_camera_operations_reject_stale_or_changed_state(monkeypatch):
    from task_env.runtime.sessions.native_io import UsdCoreRuntimeSession
    session = object.__new__(UsdCoreRuntimeSession)
    states = iter(('before', 'after'))
    calls = []
    session._native_io = SimpleNamespace(read_state=lambda: next(states),
        bind_task_camera=lambda *args: calls.append(args) or 'bound')
    monkeypatch.setattr(session, '_require_reset', lambda: None)
    monkeypatch.setattr(session, '_assert_native_identity', lambda: None)
    monkeypatch.setattr(session, 'state_boundary_identity', lambda: 'current')
    with pytest.raises(ValueError, match='current state boundary'):
        session.bind_task_camera('camera', SimpleNamespace(boundary='old'))
    assert calls == []
    with pytest.raises(RuntimeError, match='physics state'):
        session.bind_task_camera('camera', SimpleNamespace(boundary='current'))


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


def test_observer_window_close_keeps_capture_live_without_reopening(monkeypatch):
    import sys

    class FakeWindow:
        instances = []

        def __init__(self):
            self.close_callback = None
            self.destroyed = False
            self.close_during_update = False
            self.instances.append(self)

        def title(self, _value):
            pass

        def protocol(self, _name, callback):
            self.close_callback = callback

        def update_idletasks(self):
            pass

        def update(self):
            if self.close_during_update:
                self.close_callback()

        def winfo_id(self):
            return 731

        def destroy(self):
            self.destroyed = True

    class FakeLabel:
        def __init__(self, _window, **_kwargs):
            pass

        def pack(self):
            pass

        def configure(self, **_kwargs):
            pass

    fake_tk = SimpleNamespace(
        Tk=FakeWindow,
        Label=FakeLabel,
        PhotoImage=lambda **_kwargs: object(),
    )
    monkeypatch.setitem(sys.modules, 'tkinter', fake_tk)
    captures = []

    def capture():
        boundary = len(captures) + 1
        frame = SimpleNamespace(
            rgb=np.full((2, 3, 3), boundary / 10, dtype=np.float32),
            metadata=_Mapping({'observer': 'camera-a'}),
            capture_identity=_Mapping({'boundary': boundary}),
        )
        captures.append(frame)
        return frame

    provider = TaskEnvRenderProvider(
        render_source=None, config=SimpleNamespace(width=3, height=2),
        frame_capture=capture,
    )
    assert provider.render(mode=RenderMode.HUMAN, snapshot=None) is None
    first = provider.last_frame_receipt
    assert first['capture_identity'] == {'boundary': 1}
    assert first['presentation']['status'] == 'presented'
    assert first['presentation']['window_id'] == 731

    FakeWindow.instances[0].close_callback()
    assert FakeWindow.instances[0].destroyed
    assert provider.render(mode=RenderMode.HUMAN, snapshot=None) is None
    second = provider.last_frame_receipt
    assert second['capture_identity'] == {'boundary': 2}
    assert second['presentation']['status'] == 'display_closed_capture_only'
    assert second['presentation']['window_id'] is None
    assert len(FakeWindow.instances) == 1
    assert len(captures) == 2
    provider.close()
    provider.close()


def test_isaac_observer_uses_headless_camera_enabled_app_profile():
    from task_env.runtime.sessions.isaac_native_io import (
        IsaacSimAppOwnerV1,
        V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1,
    )

    owner = IsaacSimAppOwnerV1(
        launch_profile_id=V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1,
    )
    assert owner.launch_profile_receipt() == {
        'profile_id': 'v211-headless-camera-v1',
        'simulation_app_config': {
            'headless': True,
            'enable_cameras': True,
            'limit_cpu_threads': 4,
            'fast_shutdown': False,
            'multi_gpu': False,
            'max_gpu_count': 1,
        },
    }


def test_selected_observer_render_latches_typed_fault_and_rejects_reuse():
    from task_env.environment.lifecycle import EpisodeExecutionState
    from task_env.environment.reference_env import SelectedReferenceEnv

    env = object.__new__(SelectedReferenceEnv)
    env._episode_state = EpisodeExecutionState()
    env._selected_observer_camera = object()
    env.render_mode = 'rgb_array'
    env._published_position_state = SimpleNamespace(
        control_step=7, simulation_time=0.014,
    )
    env.artifact = SimpleNamespace(timebase=SimpleNamespace(control_dt=0.002))
    original = RuntimeError('native observer owner failed')
    calls = []

    def fail(**_kwargs):
        calls.append(True)
        raise original

    env._ui_render_provider = SimpleNamespace(render=fail)
    with pytest.raises(RuntimeError, match='native observer owner failed') as caught:
        env.render()
    assert caught.value is original
    assert env.execution_fault.phase == 'observer_render'
    assert env.execution_fault.exception_type == 'RuntimeError'
    assert env.execution_fault.control_step_before == 7
    assert env.execution_fault.simulation_time_before_s == pytest.approx(0.014)
    assert original.execution_fault is env.execution_fault
    assert env._episode_execution_state().stopped

    with pytest.raises(RuntimeError, match='selected execution is faulted'):
        env.render()
    with pytest.raises(RuntimeError, match='selected execution is faulted'):
        env.step(np.zeros(0, dtype=np.float32))
    assert len(calls) == 1


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


def test_isaac_session_owner_close_retains_first_error_and_attempts_all_cleanup():
    from task_env.runtime.sessions.api import close_session_and_runtime_owner

    events = []
    first_error = LookupError('observer failure')

    class Session:
        close_receipt = {'session_closed': False}

        def close(self):
            events.append('session')
            raise RuntimeError('session close failed')

        def close_runtime_owner(self):
            events.append('owner')
            raise ValueError('owner close failed')

    error, receipt = close_session_and_runtime_owner(
        Session(), first_error=first_error,
        session_error_label='session cleanup', owner_error_label='owner cleanup',
        capture_close_receipt=True,
    )
    assert error is first_error
    assert receipt == {'session_closed': False}
    assert events == ['session', 'owner']
    assert len(first_error.__notes__) == 2
    assert 'session cleanup also failed: RuntimeError: session close failed' in first_error.__notes__[0]
    assert 'owner cleanup also failed: ValueError: owner close failed' in first_error.__notes__[1]


def test_runtime_construction_rollback_closes_only_half_built_session(monkeypatch):
    import task_env.runtime as runtime_module
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions.api import close_session_and_runtime_owner
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1

    class FakeApp:
        def __init__(self):
            self.close_calls = 0

        def is_running(self):
            return self.close_calls == 0

        def close(self):
            self.close_calls += 1

    owner = IsaacSimAppOwnerV1()
    owner._app = FakeApp()
    owner.retain_process_lifetime()  # half-built session
    owner.retain_process_lifetime()  # live sibling session
    events = []

    class HalfBuiltSession:
        def close(self):
            events.append('half-built-session')
            raise RuntimeError('partial session cleanup failed')

        def close_runtime_owner(self):
            events.append('shared-owner-close-request')
            owner.close()

    class SiblingSession:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

        def is_live(self):
            return owner.open().is_running()

    sibling = SiblingSession()
    primary = RuntimeError('task binding failed after runtime materialization')
    assembly = SimpleNamespace(boundary=HalfBuiltSession(), compiled_scene=object())
    monkeypatch.setattr(runtime_module, 'bootstrap_task_runtime', lambda **_kwargs: assembly)

    env = object.__new__(SelectedReferenceEnv)
    env.config = SimpleNamespace(
        render=SimpleNamespace(camera_obs=False),
        agents=SimpleNamespace(agent_uids=()),
    )
    env._composition_spec = object()
    env.scene = object()
    env.agents = ()
    env.objects = ()
    env.render_mode = None
    env.create_reset_sampler = lambda: object()
    env.create_scene_composer = lambda: object()
    env.create_task_definition = lambda _scene: (_ for _ in ()).throw(primary)

    def rollback_close():
        error, _receipt = close_session_and_runtime_owner(
            assembly.boundary, session_error_label='half-built session close',
            owner_error_label='shared App owner close',
        )
        if error is not None:
            raise error

    env.close = rollback_close
    with pytest.raises(RuntimeError, match='task binding failed after runtime materialization') as caught:
        env._build_runtime_with_rollback()

    assert caught.value is primary
    assert primary.execution_fault.phase == 'runtime_construction'
    assert any('construction rollback also failed' in note for note in primary.__notes__)
    assert any('partial session cleanup failed' in note for note in primary.__notes__)
    assert events == ['half-built-session', 'shared-owner-close-request']
    assert sibling.close_calls == 0 and sibling.is_live()
    assert owner._close_requested and not owner._close_attempted
    assert owner.app is owner.open() and owner.app.is_running()
    assert owner.app.close_calls == 0

    owner.release_process_lifetime()
    assert owner.app.close_calls == 0
    owner.release_process_lifetime()
    assert owner.app.close_calls == 1
    assert owner.close_receipt()['close_completed']
