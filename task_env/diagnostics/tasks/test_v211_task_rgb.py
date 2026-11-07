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


def test_public_factory_adds_camera_to_an_independently_named_selected_task(monkeypatch):
    from types import SimpleNamespace
    from task_env.environment.gym_compat import Box, Dict
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env import registry

    class OtherTask(SelectedReferenceEnv):
        uid = 'independent-task-with-different-names-v1'

        @classmethod
        def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
            assert not kwargs and render_mode is None
            env = object.__new__(cls)
            env.position_profile = True
            env.provider, env.backend = 'mujoco', 'cpu'
            env.artifact = SimpleNamespace(identity_hash='c' * 64)
            env.observation_space = Dict({'different-state': Box(-1., 1., shape=(3,), dtype=np.float32)})
            env.metadata = {}
            return env

    monkeypatch.setattr(registry.ENV_REGISTRY, 'get', lambda uid: OtherTask)
    camera = _camera('independent-camera')
    env = registry.make_env(OtherTask.uid, task_rgb_camera=camera, task_renderer='mujoco')
    assert set(env.observation_space.spaces) == {'different-state', 'task_rgb'}
    assert env.metadata['task_rgb_v1']['camera']['camera_id'] == 'independent-camera'
    assert env._task_rgb_config[0] is not camera


def test_isaac_color_defaults_do_not_override_incompatible_settings(monkeypatch, tmp_path):
    import hashlib
    import sys
    from types import SimpleNamespace
    from task_env.runtime.sessions import isaac_native_io as native

    class Settings:
        def __init__(self):
            self.values, self.writes = {}, []
        def get(self, key):
            return self.values.get(key)
        def set(self, key, value):
            self.writes.append((key, value))
            self.values[key] = value

    sdk_root = tmp_path / 'sdk'
    ocio = sdk_root / 'kit/rendering-data/runtime/ov-0.1.0.ocio'
    ocio.parent.mkdir(parents=True)
    ocio.write_bytes(b'qualified test configuration')
    monkeypatch.setattr(native, '_ISAAC_62_OBSERVER_OCIO_SHA256', hashlib.sha256(ocio.read_bytes()).hexdigest())
    settings = Settings()
    monkeypatch.setitem(sys.modules, 'carb', SimpleNamespace(settings=SimpleNamespace(get_settings=lambda: settings)))
    monkeypatch.setitem(sys.modules, 'isaacsim', SimpleNamespace(__file__=str(sdk_root / '__init__.py')))
    setup = native.configure_isaac_task_rgb_color_defaults()
    assert setup['qualified']['ocio_sha256'] == hashlib.sha256(ocio.read_bytes()).hexdigest()
    assert settings.get('/rtx/post/tonemap/op') == 6
    settings.values['/rtx/post/tonemap/op'] = 5
    settings.writes.clear()
    with pytest.raises(RuntimeError, match='incompatible App setting'):
        native.configure_isaac_task_rgb_color_defaults()
    assert settings.writes == []


def test_task_rgb_and_observer_keep_distinct_identity_and_existing_request(monkeypatch):
    from types import SimpleNamespace
    from task_env.environment.gym_compat import Box, Dict
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.render.base.contracts import ObserverRenderRequestV1

    monkeypatch.setattr(ObserverRenderRequestV1, 'validate', lambda self, **kwargs: None)
    env = object.__new__(SelectedReferenceEnv)
    env.position_profile = True
    env.provider, env.backend = 'geophys', 'cpu'
    env.artifact = SimpleNamespace(identity_hash='c' * 64)
    env.observation_space = Dict({'state': Box(-1., 1., shape=(3,), dtype=np.float32)})
    env.metadata = {}
    env._selected_observer_camera = _camera('observer')
    existing_request = object()
    env._observer_render_request = existing_request
    env._configure_task_rgb(_camera('task'), 'geophys')
    assert env._observer_render_request is existing_request
    with pytest.raises(ValueError, match='distinct identities'):
        env._configure_selected_observer('rgb_array', _camera('task'))
    with pytest.raises(ValueError, match='distinct identities'):
        env.set_observer_camera(_camera('task'))

    other = object.__new__(SelectedReferenceEnv)
    other.position_profile = True
    other.provider, other.backend = 'geophys', 'cpu'
    other.artifact = env.artifact
    other.observation_space = Dict({'state': Box(-1., 1., shape=(3,), dtype=np.float32)})
    other.metadata = {}
    other._selected_observer_camera = _camera('task')
    with pytest.raises(ValueError, match='distinct identities'):
        other._configure_task_rgb(_camera('task'), 'geophys')


def test_incompatible_reset_pair_rejected_before_candidate_build(monkeypatch):
    from types import SimpleNamespace
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.environment import reset_switch

    env = object.__new__(SelectedReferenceEnv)
    env._episode_execution_state = lambda: SimpleNamespace(require_open=lambda message: None, fault=None)
    env._task_rgb_config = (_camera(), 'mujoco')
    env.binding = SimpleNamespace(physical_control_profile=None)
    env.recorder = None
    env.resolved_public_config = SimpleNamespace(reset_profile='pickcube-state-only-switch-v1')
    candidate = SimpleNamespace(config=SimpleNamespace(physics_provider='isaacsim',
        environment=SimpleNamespace(runtime=SimpleNamespace(backend='cuda'))))
    monkeypatch.setattr(reset_switch, 'prepare_switch_reset', lambda *args: candidate)
    monkeypatch.setattr(SelectedReferenceEnv, 'selected_binding',
                        lambda *args: pytest.fail('candidate build must not start'), raising=False)
    with pytest.raises(ValueError, match='incompatible with the fixed task RGB renderer'):
        env._prepare_reference_reset(options={'execution': {'physics_provider': 'isaacsim'}})
