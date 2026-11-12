"""Provider-free contract checks for fixed task RGB observation ownership."""
from dataclasses import replace

import numpy as np
import pytest

from task_env.artifacts import RendererSelectionV1
from task_env.artifacts.state import CanonicalStateViewV1, StateBoundaryIdentity, StateSampleClock
from task_env.observations.canonical_camera import CameraGeometry, CanonicalCameraObservation, resolve_camera
from task_env.observations.canonical_camera.contracts import IDENTITY
from task_env.observations.capture import TaskRgbObservationConsumerV1
from task_env.render.camera.source import CameraCaptureIdentityV1


def _state(step, episode='episode-a'):
    boundary = StateBoundaryIdentity('state-boundary-identity-v1', episode, 'reset-' + 'a' * 64,
                                     'b' * 64, 'scene-a', 'materialization-a', step, step)
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', step, step * .01)
    return CanonicalStateViewV1('canonical-state-v1', 'SI_right_handed_z_up_wxyz', boundary, clock, (), ())


def _camera(name='task'):
    return CameraGeometry('camera-observation-v0', 'c' * 64, name, 'world', IDENTITY, IDENTITY,
                          4, 3, 1., .01, 10., True, False)


def _selection():
    return RendererSelectionV1('renderer-selection-v1', 'mujoco', 'native-opengl',
                               'v211_mujoco_cpu_native_rgb_v1', None)


def test_camera_spec_lowering_preserves_pose_and_artifact_link():
    from task_env.environment.config import CameraSpec
    spec = CameraSpec(name='rotated', quaternion_wxyz=(2., 0., 0., 2.),
                      position=(1., 2., 3.), width=8, height=6, depth=False)
    geometry = CameraGeometry.from_camera_spec(spec, task_artifact_hash='c' * 64)
    np.testing.assert_allclose(geometry.T_parent_from_mount,
        [[0., -1., 0., 1.], [1., 0., 0., 2.], [0., 0., 1., 3.], [0., 0., 0., 1.]], atol=1e-15)
    assert geometry.task_artifact_hash == 'c' * 64
    assert (geometry.width, geometry.height, geometry.depth) == (8, 6, False)


def test_camera_spec_capture_metadata_uses_published_boundary_for_reset_and_step():
    from types import SimpleNamespace
    from task_env.environment.config import CameraSpec
    from task_env.environment.reference_env import SelectedReferenceEnv
    camera, selection = _camera(), _selection()
    env = object.__new__(SelectedReferenceEnv)
    env._task_camera_spec = CameraSpec(name='task', width=4, height=3, depth=False)
    env._task_rgb_config = camera, 'mujoco'
    env._task_rgb_consumer = TaskRgbObservationConsumerV1(camera, selection,
        lambda _state: _Session(camera, selection), color_space='test')
    env.session = SimpleNamespace(task_camera_binding=lambda view: {
        'native': {'episode_id': view.boundary.episode_id, 'fov_y': 1.}})
    for step in (0, 1):
        view = _state(step)
        env._publish_task_rgb_typed_state = lambda _state: SimpleNamespace(view=view)
        image, receipt = env._capture_task_rgb_boundary(
            SimpleNamespace(control_step=step, simulation_time=step * .01))
        assert image.shape == (3, 4, 3)
        assert receipt['requested_camera']['name'] == 'task'
        assert receipt['realized_camera']['episode_id'] == view.boundary.episode_id
        assert receipt['observation_boundary']['control_step'] == step
        assert receipt['render_backend'] == 'native-opengl'


def _capture(camera, selection, state):
    identity = CameraCaptureIdentityV1('camera-capture-identity-v1', camera.task_artifact_hash,
        camera.camera_id, camera.identity_hash, 'd' * 64, 'e' * 64, selection, 'f' * 64,
        state.boundary, state.sample_clock, ('rgb',), 'post_control_step')
    return CanonicalCameraObservation(np.full((3, 4, 3), .25, dtype=np.float32), None,
                                      resolve_camera(camera, state), identity)


class _Session:
    def __init__(self, camera, selection):
        self.camera, self.selection, self.closed = camera, selection, 0
        self.override = None

    def capture(self, state):
        return self.override if self.override is not None else _capture(self.camera, self.selection, state)

    def close(self):
        self.closed += 1


def test_task_rgb_produces_owned_contiguous_reset_and_step_frames():
    camera, selection = _camera(), _selection()
    session = _Session(camera, selection)
    consumer = TaskRgbObservationConsumerV1(camera, selection, lambda state: session, color_space='test')
    first, initial = consumer.capture(_state(0))
    second, step = consumer.capture(_state(1))
    assert first.flags.owndata and second.flags.owndata and not np.shares_memory(first, second)
    assert initial['capture_identity']['capture_phase'] == 'reset_initial'
    assert step['capture_identity']['capture_phase'] == 'post_control_step'
    assert initial['renderer_generation'] == step['renderer_generation']
    with pytest.raises(ValueError, match='next boundary'):
        consumer.capture(_state(1))
    consumer.close()
    consumer.close()
    assert session.closed == 1
    with pytest.raises(RuntimeError, match='closed'):
        consumer.capture(_state(2))


@pytest.mark.parametrize('mutation', ['camera', 'renderer', 'state', 'phase'])
def test_task_rgb_rejects_foreign_or_stale_capture(mutation):
    camera, selection = _camera(), _selection()
    session = _Session(camera, selection)
    consumer = TaskRgbObservationConsumerV1(camera, selection, lambda state: session, color_space='test')
    if mutation == 'phase':
        current = _capture(camera, selection, _state(0))
        session.override = replace(current, capture_identity=replace(current.capture_identity, capture_phase='reset_initial'))
        with pytest.raises(ValueError, match='requested camera'):
            consumer.capture(_state(0))
        consumer.close()
        return
    consumer.capture(_state(0))
    current = _capture(camera, selection, _state(1))
    if mutation == 'camera':
        current = _capture(_camera('other-camera'), selection, _state(1))
    elif mutation == 'renderer':
        current = _capture(camera, replace(selection, profile='other-profile'), _state(1))
    elif mutation == 'state':
        current = _capture(camera, selection, _state(1, episode='other-episode'))
    session.override = current
    with pytest.raises(ValueError):
        consumer.capture(_state(1))
    consumer.close()


def test_task_rgb_rejects_wrong_episode_before_calling_renderer():
    camera, selection = _camera(), _selection()
    session = _Session(camera, selection)
    consumer = TaskRgbObservationConsumerV1(camera, selection, lambda state: session, color_space='test')
    consumer.capture(_state(0))
    with pytest.raises(ValueError, match='same episode'):
        consumer.capture(_state(1, episode='other'))
    consumer.close()


def test_environment_closes_rgb_and_visual_resources_once():
    from types import SimpleNamespace
    from task_env.environment.reference_env import SelectedReferenceEnv

    closed = []
    class Resource:
        close_status = {'closed': True}
        def __init__(self, name): self.name = name
        def close(self): closed.append(self.name)

    env = object.__new__(SelectedReferenceEnv)
    env._task_rgb_consumer = Resource('rgb')
    env._visual_state_session = Resource('visual')
    env._close_camera_consumer()
    env._close_camera_consumer()
    assert closed == ['rgb', 'visual']
    assert env._visual_binding_last_close == {'closed': True}
