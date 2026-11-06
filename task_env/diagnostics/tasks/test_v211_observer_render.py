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
