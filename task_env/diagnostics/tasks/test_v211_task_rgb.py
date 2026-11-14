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


def test_selected_reset_captures_task_rgb_after_reset_transaction_returns(monkeypatch):
    from task_env.environment.reference_env import SelectedReferenceEnv

    events = []

    class ResetState:
        stopped = True

        def require_open(self, _message):
            return None

        def execute_reset(self, **operations):
            assert 'after_commit' not in operations
            self.stopped = False
            events.append('execute_reset_return')
            return {'observation': 'published'}, {'info': 'published'}

    lifecycle = ResetState()
    env = object.__new__(SelectedReferenceEnv)
    from types import SimpleNamespace
    env.binding = SimpleNamespace(task_reset_sampler=None)
    env._task_rgb_config = object()
    env._defer_task_rgb_capture = False
    env._reset_failure_receipt = 'prior'
    env.state = 'published-state'

    def after_commit(state, result):
        assert state == env.state
        assert lifecycle.stopped is False
        assert env._defer_task_rgb_capture is False
        assert env._reset_failure_receipt is None
        events.append('task_rgb_capture')
        return {'task_rgb': 'captured'}, {'task_rgb_v1': 'receipt'}

    operations = {
        'after_commit': after_commit,
        'on_failure': lambda phase, error: events.append(('cleanup', phase, error)),
    }
    monkeypatch.setattr(env, '_episode_execution_state', lambda: lifecycle, raising=False)
    monkeypatch.setattr(env, '_has_component_assembly', lambda: False, raising=False)
    monkeypatch.setattr(env, '_prepare_reference_reset', lambda **_kwargs: operations, raising=False)

    result = SelectedReferenceEnv.reset(env)

    assert result == ({'task_rgb': 'captured'}, {'task_rgb_v1': 'receipt'})
    assert events == ['execute_reset_return', 'task_rgb_capture']


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
            env.position_profile = False
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


def test_component_task_rgb_config_is_fixed_and_preserves_physics():
    from task_env.environment.config import CameraSpec
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.tasks.pendulum import PendulumEnv

    config = PendulumEnv.default_config()
    camera = CameraSpec('pendulum-task', width=8, height=6)
    resolved, task_rgb = SelectedReferenceEnv._prepare_component_task_rgb(
        config, camera, 'geophys'
    )
    assert resolved.runtime == config.runtime
    assert resolved.render.backend == 'rasterizer'
    assert resolved.render.camera_obs is True
    assert resolved.render.cameras == (camera,)
    assert task_rgb[:2] == (camera, 'geophys')
    with pytest.raises(ValueError, match='GeoPhys renderer only'):
        SelectedReferenceEnv._prepare_component_task_rgb(config, camera, 'mujoco')


def test_component_task_rgb_uses_owned_frame_from_same_snapshot():
    from types import SimpleNamespace
    from task_env.environment.gym_compat import Box, Dict
    from task_env.environment import CameraRendererReadbackV1
    from task_env.environment.config import CameraSpec
    from task_env.environment.reference_env import SelectedReferenceEnv

    camera = CameraSpec('task', width=4, height=3)
    source = np.full((3, 4, 3), 0.25, dtype=np.float32)
    env = object.__new__(SelectedReferenceEnv)
    env._component_task_rgb = (camera, 'geophys', 'generation-a')
    env._last_sensor_snapshot = None
    env._last_sensor_observation = None
    env._last_camera_metadata = {}
    snapshot = object()
    calls = []
    realized = CameraRendererReadbackV1(
        camera_id='task', binding_id='binding-a', position=(0., 0., 0.),
        forward=(1., 0., 0.), up=(0., 0., 1.), fov_degrees=float(np.degrees(camera.fov_y)),
        near=camera.near, far=camera.far, width=camera.width, height=camera.height,
    )
    observation = SimpleNamespace(
        rgb={'task': source},
        camera_metadata={'task': SimpleNamespace(synchronized=True, renderer_readback=realized)},
    )
    env._sensor_provider = SimpleNamespace(
        capture=lambda actual: calls.append(actual) or observation
    )
    env.observation_space = Dict({
        'state': Box(-1.0, 1.0, shape=(2,), dtype=np.float32),
        'task_rgb': Box(0.0, 1.0, shape=(3, 4, 3), dtype=np.float32),
    })
    state = np.array((0.0, 1.0), dtype=np.float32)
    actual = env._augment_component_task_rgb(snapshot, {'state': state})
    assert calls == [snapshot]
    assert actual['task_rgb'].dtype == np.float32
    assert actual['task_rgb'].flags.owndata
    assert not np.shares_memory(actual['task_rgb'], source)
    assert env._augment_component_task_rgb(snapshot, {'state': state})['task_rgb'].shape == (3, 4, 3)
    assert calls == [snapshot]


def test_geophys_selected_camera_light_contract_is_source_driven():
    from types import SimpleNamespace
    from task_env.runtime.sessions.geophys import _observer_mjcf_light_declaration

    def light(light_id, light_type, kind=None):
        payload = {} if kind is None else {'mjcf_kind': kind}
        return SimpleNamespace(
            light_id=light_id, light_type=light_type, runtime_payload=payload
        )

    tracking = light('mjcf:light:key', 'spot', 'world_trackcom')
    headlight = light('mjcf:headlight', 'directional', 'headlight')
    ambient = light('mjcf:headlight:ambient', 'ambient')
    no_lights = _observer_mjcf_light_declaration(None)
    assert no_lights[:3] == (None, None, 'no-authored-mjcf-lights')
    declared = _observer_mjcf_light_declaration(
        SimpleNamespace(records=(ambient, headlight, tracking))
    )
    assert declared == (tracking, headlight, 'supported-authored-mjcf-lights', 3)
    assert _observer_mjcf_light_declaration(
        SimpleNamespace(records=(ambient, headlight))
    )[:2] == (None, headlight)
    with pytest.raises(RuntimeError, match='ambiguous or unsupported'):
        _observer_mjcf_light_declaration(
            SimpleNamespace(records=(ambient, headlight, tracking, tracking))
        )
    with pytest.raises(RuntimeError, match='ambiguous or unsupported'):
        _observer_mjcf_light_declaration(
            SimpleNamespace(records=(ambient, headlight, light('unknown', 'mjcf_unsupported')))
        )
    with pytest.raises(RuntimeError, match='ambiguous or unsupported'):
        _observer_mjcf_light_declaration(
            SimpleNamespace(records=(light('mjcf:headlight:ambient', 'directional'), headlight))
        )
    with pytest.raises(RuntimeError, match='ambiguous or unsupported'):
        _observer_mjcf_light_declaration(SimpleNamespace(records=(ambient,)))


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
    env._reset_reconstruction = None
    env.resolved_public_config = SimpleNamespace(reset_profile='pickcube-state-only-switch-v1')
    candidate = SimpleNamespace(config=SimpleNamespace(physics_provider='isaacsim',
        environment=SimpleNamespace(runtime=SimpleNamespace(backend='cuda'))))
    monkeypatch.setattr(reset_switch, 'prepare_switch_reset', lambda *args: candidate)
    monkeypatch.setattr(SelectedReferenceEnv, 'selected_binding',
                        lambda *args: pytest.fail('candidate build must not start'), raising=False)
    with pytest.raises(ValueError, match='incompatible with the fixed task RGB renderer'):
        env._prepare_reference_reset(options={'execution': {'physics_provider': 'isaacsim'}})
