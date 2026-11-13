"""Pure/fake checks for parent-bound task cameras; no SDK or asset reads."""
from dataclasses import replace
from types import SimpleNamespace
import sys

import numpy as np
import pytest

from task_env.artifacts import FrameReference, PoseWorld, TypedFrameStateValue
from task_env.artifacts.state import CanonicalStateViewV1, StateBoundaryIdentity, StateSampleClock
from task_env.environment.config import CameraSpec
from task_env.observations.canonical_camera import CameraGeometry, resolve_camera


def _state(step, *, duplicate=False):
    frames = (TypedFrameStateValue('typed-frame-state-v1', FrameReference('robot-a', 'ee'),
                                  PoseWorld((float(step), 0., 0.), (1., 0., 0., 0.))),)
    if duplicate:
        frames += (replace(frames[0], frame=FrameReference('robot-b', 'ee')),)
    return CanonicalStateViewV1('canonical-state-v1', 'SI_right_handed_z_up_wxyz',
        StateBoundaryIdentity('state-boundary-identity-v1', 'episode-a', 'reset-'+'a'*64, 'b'*64,
                             'scene-a', 'materialization-a', step, step),
        StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', step, step*.01),
        (), frames)


def _camera():
    return CameraGeometry.from_camera_spec(CameraSpec('wrist', frame='body', parent='robot-a/ee',
        position=(.1, .2, .3), width=8, height=6), task_artifact_hash='c'*64)


def test_mounted_declaration_tracks_qualified_parent_and_preserves_identity():
    camera = _camera()
    a, b = resolve_camera(camera, _state(0, duplicate=True)), resolve_camera(camera, _state(2, duplicate=True))
    assert camera.parent_frame == 'robot-a/ee'
    np.testing.assert_allclose(np.asarray(b.T_world_from_camera)[:3, 3] - np.asarray(a.T_world_from_camera)[:3, 3], [2., 0., 0.])
    assert a.camera.identity_hash == b.camera.identity_hash
    assert (a.capture_control_step, b.capture_control_step) == (0, 2)


def test_unknown_and_ambiguous_parent_reject_without_substituting_world():
    with pytest.raises(ValueError, match='exactly one'):
        resolve_camera(replace(_camera(), parent_frame='missing/ee'), _state(0))
    with pytest.raises(ValueError, match='exactly one'):
        resolve_camera(replace(_camera(), parent_frame='ee'), _state(0, duplicate=True))


def test_renderer_capability_rejects_unimplemented_mounts_before_native_setup():
    from task_env.render.camera.task_rgb import prepare_task_rgb_adapter
    from task_env.render.base.contracts import task_rgb_capability
    assert task_rgb_capability('isaacsim', 'cuda', 'isaacsim').frame_mounts
    with pytest.raises(ValueError, match='does not admit frame-mounted'):
        prepare_task_rgb_adapter(camera=_camera(), renderer='mujoco', provider='mujoco',
                                 backend='cpu', artifact=object(), observer=None)


def test_native_mount_updates_only_owned_camera_without_advancing_physics(monkeypatch):
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1
    writes = []
    operation = SimpleNamespace(Set=lambda value: writes.append(value))
    prim = SimpleNamespace(IsA=lambda cls: cls == 'camera')
    stage = SimpleNamespace(GetPrimAtPath=lambda path: prim if path == '/owned-camera' else None)
    geom = SimpleNamespace(Camera='camera',
                           Xformable=lambda p: SimpleNamespace(MakeMatrixXform=lambda: operation))
    monkeypatch.setitem(sys.modules, 'pxr', SimpleNamespace(
        Gf=SimpleNamespace(Matrix4d=lambda *v: np.asarray(v).reshape(4, 4)), UsdGeom=geom))
    io = object.__new__(IsaacSimNativeRuntimeIOV1)
    io._stage, io._task_camera_path = stage, '/owned-camera'
    camera = _camera()
    for step in (0, 1):
        io._sync_task_camera_mount(camera, _state(step))
    assert len(writes) == 2
    np.testing.assert_allclose(writes[1].T[:3, 3] - writes[0].T[:3, 3], [1., 0., 0.])
    assert not hasattr(io, '_manager')  # Updating camera has no simulation owner.


def test_native_mount_rejects_missing_owned_camera(monkeypatch):
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1
    geom = SimpleNamespace(Camera='camera')
    monkeypatch.setitem(sys.modules, 'pxr', SimpleNamespace(Gf=object(), UsdGeom=geom))
    io = object.__new__(IsaacSimNativeRuntimeIOV1)
    io._stage = SimpleNamespace(GetPrimAtPath=lambda p: None)
    io._task_camera_path = '/owned-camera'
    with pytest.raises(RuntimeError, match='prim is unavailable'):
        io._sync_task_camera_mount(_camera(), _state(0))
