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
