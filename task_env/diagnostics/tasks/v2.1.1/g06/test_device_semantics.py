"""CPU tensor oracles for device lifecycle and shared Pendulum semantics."""
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import pytest
import torch


def test_geophys_site_pose_composition_uses_each_world_and_source_rotation():
    from task_env.runtime.providers.geophys.device_batch import _compose_site_poses

    half = 2 ** -0.5
    position = torch.tensor([[[1., 2., 3.]], [[-2., 1., 4.]]])
    rotation = torch.tensor([[[half, 0., 0., half]], [[half, 0., 0., -half]]])
    local_position = torch.tensor([[1., 0., 0.]])
    local_rotation = torch.tensor([[half, half, 0., 0.]])
    actual_position, actual_rotation = _compose_site_poses(position, rotation, local_position, local_rotation)
    torch.testing.assert_close(actual_position, torch.tensor([[[1., 3., 3.]], [[-2., 0., 4.]]]), atol=2e-7, rtol=0)
    torch.testing.assert_close(actual_rotation, torch.tensor([[[.5, .5, .5, .5]], [[.5, .5, -.5, -.5]]]),
                               atol=2e-7, rtol=0)


def test_device_coupled_transmission_rejects_unrepresentable_effort_per_world():
    from task_env.runtime.transport.device_batch_session import _coupled_effort_groups, _validate_coupled_efforts

    channels = (SimpleNamespace(entity_id='rig', transmission_id='coupled', sign=1, transmission_coefficient=.5),
                SimpleNamespace(entity_id='rig', transmission_id='single', sign=1, transmission_coefficient=1.),
                SimpleNamespace(entity_id='rig', transmission_id='coupled', sign=-1, transmission_coefficient=.25))
    groups = _coupled_effort_groups(channels)
    values = torch.tensor([[1., 3., -.5], [-2., 0., 1.], [0., -1., 0.]])
    _validate_coupled_efforts(values, groups)
    values[1, 2] = .8
    with pytest.raises(ValueError, match='coupled transmission'):
        _validate_coupled_efforts(values, groups)


def test_implicitfast_equivalence_rejects_unqualified_velocity_effects():
    import xml.etree.ElementTree as ET
    from task_env.runtime.providers.geophys.device_batch import _validate_implicitfast_smooth_equivalence

    data = {'jnt_type': [0], 'jnt_child_body': [0], 'body_parentid': [-1],
            'body_ipos': [[0., 0., 0.]], 'tendon_damping': [0.],
            'jnt_frictionloss': [0.], 'jnt_stiffness': [0.],
            'body_linear_damping': [0.], 'body_angular_damping': [0.]}
    model = SimpleNamespace(joint_data=data, objects=[SimpleNamespace(body_inertia=[1., 1., 1.])])
    _validate_implicitfast_smooth_equivalence(model, ET.fromstring('<option/>'))
    for changed in ({'tendon_damping': [1.]}, {'body_ipos': [[.1, 0., 0.]]},
                    {'body_parentid': [-1, 0]}):
        with pytest.raises(ValueError, match='implicitfast equivalence'):
            _validate_implicitfast_smooth_equivalence(SimpleNamespace(joint_data={**data, **changed},
                objects=model.objects), ET.fromstring('<option/>'))
    with pytest.raises(ValueError, match='isotropic'):
        _validate_implicitfast_smooth_equivalence(SimpleNamespace(joint_data=data,
            objects=[SimpleNamespace(body_inertia=[1., 2., 3.])]), ET.fromstring('<option/>'))
    with pytest.raises(ValueError, match='fluid'):
        _validate_implicitfast_smooth_equivalence(model, ET.fromstring('<option viscosity="1"/>'))


def test_geophys_close_attempts_every_owner_and_retries_only_failures():
    from task_env.runtime.providers.geophys.device_batch import GeoPhysNativeBatch

    calls = []

    class Resource:
        def __init__(self, name, failures):
            self.name, self.failures = name, failures

        def close(self):
            calls.append(self.name)
            if self.failures:
                self.failures -= 1
                raise RuntimeError(self.name)

    adapter = GeoPhysNativeBatch.__new__(GeoPhysNativeBatch)
    adapter._closed = False
    adapter._publisher = Resource('publisher', 1)
    adapter._runtime = Resource('runtime', 2)
    with pytest.raises(RuntimeError, match='publisher') as first:
        adapter.close()
    assert calls == ['publisher', 'runtime']
    assert any('runtime' in note for note in first.value.__notes__)
    assert not adapter._closed
    with pytest.raises(RuntimeError, match='runtime'):
        adapter.close()
    assert calls == ['publisher', 'runtime', 'publisher', 'runtime']
    assert adapter._publisher is None
    adapter.close()
    adapter.close()
    assert calls == ['publisher', 'runtime', 'publisher', 'runtime', 'runtime']
    assert adapter._closed and adapter._runtime is None

from task_env.runtime.contracts import DeviceBatchState, DeviceBatchTransition
from task_env.tasks.pendulum import PendulumTaskDefinition, PendulumTaskSemantics
from task_env.vectorization.homogeneous import HomogeneousVectorTaskEnv


def test_scalar_device_view_preserves_terminal_camera_and_unbatches_actions():
    class Spec:
        uid, num_envs, metadata, parallel_render_provider = 'fake', 1, {}, None
        single_action_space = gym.spaces.Dict({'torque': gym.spaces.Box(-1., 1., (1,), dtype=np.float32)})
        single_observation_space = gym.spaces.Dict({'cameras': gym.spaces.Dict({
            'base': gym.spaces.Dict({'rgb': gym.spaces.Box(0, 255, (2, 2, 3), dtype=np.uint8)})})})

        def __init__(self):
            self.image = torch.ones((1, 2, 2, 3), dtype=torch.uint8)
            self.episode = torch.ones(1, dtype=torch.int64)
            self.steps = torch.zeros(1, dtype=torch.int32)
            self.last_action = None

        @property
        def device_episode_ids(self):
            return self.episode.clone()

        @property
        def device_episode_steps(self):
            return self.steps.clone()

        def reset_sampled_device(self, *, seed=None, mask=None, selection=None):
            if mask is not None:
                self.image[mask] = 3
                self.episode[mask] += 1
                self.steps[mask] = 0
            return SimpleNamespace(observation={'cameras': {'base': {'rgb': self.image}}},
                                   infos={'episode_id': self.episode.clone()})

        def step_device(self, action):
            self.last_action = action['torque'].clone()
            self.image.fill_(2)
            self.steps += 1
            return DeviceBatchTransition({'cameras': {'base': {'rgb': self.image}}},
                torch.tensor([1.]), torch.tensor([False]), torch.tensor([True]), 'cpu')

        def prepare_device_reset_selection(self, mask):
            return SimpleNamespace(selected_count=int(mask.sum()))

        def close(self):
            pass

    spec = Spec()
    env = HomogeneousVectorTaskEnv(spec, execution_mode='device', scalar_device=True)
    from task_env.recorders import VectorTransitionRecorder
    assert env.metadata['execution'] == 'device_scalar_worker'
    with pytest.raises(ValueError, match='requires batched device observations'):
        VectorTransitionRecorder(env)
    initial, info = env.reset(seed=73)
    assert initial['cameras']['base']['rgb'].shape == (2, 2, 3)
    assert info['episode_id'].shape == ()
    assert env.observation_space['cameras']['base']['rgb'].shape == (2, 2, 3)
    observation, reward, terminated, truncated, info = env.step({'torque': torch.tensor([.5])})
    assert spec.last_action.shape == (1, 1)
    assert reward.shape == terminated.shape == truncated.shape == ()
    assert bool(truncated) and not bool(terminated) and bool(info['_final_observation'])
    assert torch.all(info['final_observation']['cameras']['base']['rgb'] == 2)
    assert torch.all(observation['cameras']['base']['rgb'] == 3)
    spec.image.fill_(7)
    assert torch.all(info['final_observation']['cameras']['base']['rgb'] == 2)
    with pytest.raises(ValueError, match='does not accept a batch mask'):
        env.reset(mask=torch.tensor([True]))
    env.close()


def test_independent_readback_accepts_native_partial_line_prefix(tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    path = Path(__file__).with_name('readback.py')
    spec = importlib.util.spec_from_file_location('g06_readback_receipt_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / 'supervisor.json').write_text(json.dumps(
        {'exit_code': 0, 'violation': None, 'forced_retirement': False}))
    (tmp_path / 'stdout.log').write_text('[native] unfinished line {"scope": "fixture", "value": 2}\n')
    _, receipt = module._receipt(tmp_path)
    assert receipt == {'scope': 'fixture', 'value': 2}


def test_x11_window_probe_accepts_dynamic_fps_title_without_counting_decorations(monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).with_name('runner.py')
    spec = importlib.util.spec_from_file_location('g06_window_probe_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree = (' 0x11 "GeoChora  0.887568 FPS": ("mutter-x11-frames" "mutter-x11-frames")\n'
            ' 0x22 "GeoChora  0.887568 FPS": ("GeoChora" "GeoChora")\n')
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *args, **kwargs: tree)
    windows, entries = module._x11_geochora_windows()
    assert windows == {'0x22'} and len(entries) == 2


def test_pendulum_device_evaluation_matches_shared_batch_semantics_and_masked_reset():
    task = PendulumTaskDefinition(qpos_id=0, qvel_id=0)
    state = DeviceBatchState({'qpos': torch.tensor([[1.], [.05], [-2.]]),
                              'qvel': torch.tensor([[.2], [.1], [-.3]])}, 'cpu', 3)
    action = {'torque': torch.tensor([[1.], [-.5], [1.5]])}
    task.reset_device(state=state, reset_mask=torch.ones(3, dtype=torch.bool))
    semantics = PendulumTaskSemantics()
    window = np.zeros(3, dtype=np.int32)
    for step in range(1, 6):
        actual = task.evaluate_device(state=state, action=action,
                                      elapsed_steps=torch.full((3,), step), previous_state=None)
        expected, success, truncated, window, _, _ = semantics.evaluate_arrays(
            theta=np.array([1., .05, -2.], dtype=np.float32),
            theta_dot=np.array([.2, .1, -.3], dtype=np.float32),
            torque=np.array([1., -.5, 1.5], dtype=np.float32),
            upright_steps=window, elapsed_steps=np.full(3, step, dtype=np.int32))
        np.testing.assert_allclose(actual['reward'].numpy(), expected, rtol=1e-6, atol=1e-6)
        assert actual['terminated'].tolist() == success.tolist()
        assert actual['truncated'].tolist() == truncated.tolist()
    assert actual['terminated'].tolist() == [False, True, False]
    task.reset_device(state=state, reset_mask=torch.tensor([False, True, False]))
    assert not task.evaluate_device(state=state, action=action,
                                    elapsed_steps=torch.ones(3))['terminated'].any()
    expected_obs = semantics.observation(np.array([1., .05, -2.], dtype=np.float32),
                                         np.array([.2, .1, -.3], dtype=np.float32))
    np.testing.assert_allclose(task.build_device_observation(state)['state']['proprioception'].numpy(),
                               expected_obs, atol=3e-7)


def test_device_autoreset_retains_owned_terminal_row_and_resets_once():
    class Spec:
        uid = 'fake'
        num_envs = 2
        metadata = {}
        parallel_render_provider = None
        single_action_space = gym.spaces.Box(-1., 1., shape=(1,), dtype=np.float32)
        single_observation_space = gym.spaces.Dict({'state': gym.spaces.Box(-10., 10., shape=(1,), dtype=np.float32)})

        def __init__(self):
            self.values = torch.tensor([[1.], [2.]])
            self.episodes = torch.ones(2, dtype=torch.int64)
            self.steps = torch.zeros(2, dtype=torch.int32)
            self.reset_calls = 0

        @property
        def device_episode_ids(self):
            return self.episodes.clone()

        @property
        def device_episode_steps(self):
            return self.steps.clone()

        def reset_sampled_device(self, *, seed=None, mask=None, selection=None):
            if mask is not None:
                self.reset_calls += 1
                self.values[mask] = 9.
                self.episodes[mask] += 1
                self.steps[mask] = 0
            return SimpleNamespace(observation={'state': self.values}, infos={'episode_id': self.episodes.clone()})

        def step_device(self, action):
            self.steps += 1
            return DeviceBatchTransition({'state': self.values}, torch.tensor([0., 1.]),
                torch.tensor([False, False]), torch.tensor([False, True]), 'cpu')

        def prepare_device_reset_selection(self, mask):
            return SimpleNamespace(selected_count=int(mask.sum()))

        def close(self):
            pass

    spec = Spec()
    env = HomogeneousVectorTaskEnv(spec, execution_mode='device')
    env.reset()
    observation, reward, terminated, truncated, infos = env.step(torch.zeros((2, 1)))
    assert spec.reset_calls == 1
    assert observation['state'][:, 0].tolist() == [1., 9.]
    assert infos['final_observation']['state'][:, 0].tolist() == [0., 2.]
    assert infos['_final_observation'].tolist() == [False, True]
    assert infos['final_episode_id'].tolist() == [1, 1]
    assert infos['episode_id'].tolist() == [1, 2]
    assert truncated.tolist() == [False, True]
    assert reward.tolist() == [0., 1.] and not terminated.any()
    spec.values[1] = -3.
    assert infos['final_observation']['state'][:, 0].tolist() == [0., 2.]
    env.close()


def test_device_reset_streams_are_seeded_per_row_and_advance_only_when_selected():
    from task_env.vectorization.task_definition import BatchTaskLifecycleAdapter

    class Runtime:
        num_envs = 3

        def __init__(self):
            self.q = torch.zeros((3, 1))
            self.v = torch.zeros((3, 1))

        def resource_summary(self):
            return {'device_transition': {'available': True, 'field_device': 'cpu',
                    'transport': 'cuda_ipc', 'state_readback_fields': ['qpos', 'qvel'],
                    'state_shapes': {'qpos': (1,), 'qvel': (1,)}}}

        def reset_device(self, state, mask, *, selection=None):
            self.q = torch.where(mask[:, None], state['qpos'], self.q)
            self.v = torch.where(mask[:, None], state['qvel'], self.v)
            return DeviceBatchState({'qpos': self.q, 'qvel': self.v}, 'cpu', 3)

        def read_device_state(self, names):
            return DeviceBatchState({name: {'qpos': self.q, 'qvel': self.v}[name] for name in names}, 'cpu', 3)

        def step_device(self, control):
            raise AssertionError('not used in this reset test')

        def close(self):
            pass

    class Controller:
        def convert_device_batch(self, action, state):
            raise AssertionError('not used in this reset test')

    def adapter():
        runtime = Runtime()
        task = PendulumTaskDefinition(qpos_id=0, qvel_id=0)
        return BatchTaskLifecycleAdapter(uid='pendulum-v1', num_envs=3, backend='cpu', base_seed=73,
            runtime=runtime, reset_sampler=None, compiled_scene=None, initial_state=None,
            task_definition=task, action_adapter=Controller(),
            single_action_space=gym.spaces.Dict({'torque': gym.spaces.Box(-2., 2., shape=(1,), dtype=np.float32)}),
            single_observation_space=task.device_observation_space(),
            metadata={'execution': 'device_worker', 'transfer_mode': 'device',
                      'runtime_resource_summary': runtime.resource_summary()}, horizon=200, ignore_done=False)

    first, second = adapter(), adapter()
    initial = first.reset_sampled_device(seed=73).state.arrays['qpos'].clone()
    other_initial = second.reset_sampled_device(seed=73).state.arrays['qpos'].clone()
    assert torch.equal(initial, other_initial)
    first.reset_sampled_device(mask=torch.tensor([False, True, False]))
    selected = torch.tensor([True, False, True])
    first_result = first.reset_sampled_device(mask=selected).state.arrays['qpos']
    second_result = second.reset_sampled_device(mask=selected).state.arrays['qpos']
    assert torch.equal(first_result[selected], second_result[selected])
    before = first_result.clone()
    episodes = first.device_episode_ids
    first.reset_sampled_device(mask=torch.zeros(3, dtype=torch.bool))
    assert torch.equal(before, first.runtime.q)
    assert torch.equal(episodes, first.device_episode_ids)
    repeated = first.reset_sampled_device(seed=73).state.arrays['qpos']
    assert torch.equal(repeated, initial)

    rng_before = first._device_rng_state.clone()
    episode_before = first.device_episode_ids
    state_before = first.runtime.q.clone()
    with pytest.raises(ValueError, match='seed'):
        first.reset_sampled_device(seed=[1, -1, 3])
    original_sampler = first.task_definition.sample_device_reset
    first.task_definition.sample_device_reset = lambda *args: (_ for _ in ()).throw(ValueError('sampler rejected'))
    with pytest.raises(ValueError, match='sampler rejected'):
        first.reset_sampled_device(seed=101)
    first.task_definition.sample_device_reset = original_sampler
    assert torch.equal(first._device_rng_state, rng_before)
    assert torch.equal(first.device_episode_ids, episode_before)
    assert torch.equal(first.runtime.q, state_before)

    post_reset_failure = adapter()
    post_reset_failure.reset_sampled_device(seed=73)
    def fail_observation(state):
        raise RuntimeError('camera capture failed')
    post_reset_failure._device_observation_builder = fail_observation
    with pytest.raises(RuntimeError, match='camera capture failed') as failed:
        post_reset_failure.reset_sampled_device(mask=torch.tensor([False, True, False]))
    with pytest.raises(RuntimeError, match='faulted') as latched:
        post_reset_failure.reset_sampled_device()
    assert latched.value.__cause__ is failed.value
    post_reset_failure.close()

    def reject_input(action, state):
        raise ValueError('invalid action')

    first._device_action_converter = reject_input
    with pytest.raises(ValueError, match='invalid action'):
        first.step_device({})
    first._device_action_converter = lambda action, state: object()
    with pytest.raises(AssertionError, match='not used in this reset test'):
        first.step_device({})
    with pytest.raises(RuntimeError, match='faulted') as fault:
        first.step_device({})
    assert isinstance(fault.value.__cause__, AssertionError)
    first.close()
    second.close()


def test_device_profile_resolution_is_sdk_free_and_scalar_route_stays_rejected():
    import subprocess
    import sys

    code = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in {"mujoco", "mujoco_warp", "warp", "taichi", "torch"}:
        raise AssertionError("SDK imported during configuration")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from task_env.registry import ENV_REGISTRY
from task_env.environment.configuration import resolve_task_env_config
task = ENV_REGISTRY.get("pendulum-v1")
request = {"execution": {"physics_provider": "mujoco_warp", "interpreter": "/tmp/profile-python"}}
resolved = resolve_task_env_config(task, request, execution_scope="device_batch")
assert (resolved.physics_provider, resolved.physics_device) == ("mujoco_warp", "cuda:0")
assert resolved.execution_spec_v2.batch_layout == "native_batch"
assert resolved.execution_spec_v2.deployment == "isolated_worker"
try:
    resolve_task_env_config(task, request)
except ValueError:
    pass
else:
    raise AssertionError("scalar construction admitted the batch-only route")
'''
    subprocess.run([sys.executable, '-c', code], check=True)


def test_device_camera_render_config_roundtrips_without_changing_scalar_admission():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY

    task = ENV_REGISTRY.get('pendulum-v1')
    request = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': '/tmp/profile-python'},
               'render': {'backend': 'rasterizer', 'camera_obs': True,
                          'cameras': [{'name': 'base', 'width': 2, 'height': 3, 'rgb_dtype': 'uint8'}]}}
    resolved = resolve_task_env_config(task, request, execution_scope='device_batch')
    assert resolved.environment.render.cameras[0].name == 'base'
    assert resolve_task_env_config(task, resolved, execution_scope='device_batch') == resolved
    with pytest.raises(ValueError):
        resolve_task_env_config(task, request)


def test_device_scope_overrides_scalar_task_yaml_defaults_but_respects_explicit_request():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY

    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    execution = {'physics_provider': 'mujoco_warp', 'interpreter': '/tmp/profile-python'}
    request = {'execution': execution, 'controller': {'profile_id': 'r1'}}
    resolved = resolve_task_env_config(task, request, execution_scope='device_batch')
    assert (resolved.environment.runtime.backend, resolved.physics_device) == ('cuda', 'cuda:0')
    assert resolve_task_env_config(task, resolved, execution_scope='device_batch') == resolved

    with pytest.raises(ValueError, match='unsupported selected physics'):
        resolve_task_env_config(task, {**request, 'execution': {**execution, 'physics_backend': 'cpu'}},
                                execution_scope='device_batch')


def test_geophys_contact_mode_is_explicit_source_independent_and_roundtrips():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY

    task = ENV_REGISTRY.get('pendulum-v1')
    execution = {'physics_provider': 'geophys', 'interpreter': '/tmp/profile-python'}
    default = resolve_task_env_config(task, {'execution': execution}, execution_scope='device_batch')
    assert default.geophys_contact_mode == 'provider_default'
    for mode in ('provider_default', 'discrete', 'continuous'):
        resolved = resolve_task_env_config(task, {'execution': {**execution, 'geophys_contact_mode': mode}},
                                           execution_scope='device_batch')
        assert resolved.geophys_contact_mode == mode
        assert resolved.environment == default.environment
        assert resolved.execution_spec_v2 == default.execution_spec_v2
        assert resolve_task_env_config(task, resolved, execution_scope='device_batch') == resolved
        if mode != 'provider_default':
            assert mode in resolved.requested_execution_json
    with pytest.raises(ValueError, match='contact_mode'):
        resolve_task_env_config(task, {'execution': {**execution, 'geophys_contact_mode': 'automatic'}},
                                execution_scope='device_batch')
    with pytest.raises(ValueError, match='requires the GeoPhys provider'):
        resolve_task_env_config(task, {'execution': {**execution, 'physics_provider': 'mujoco_warp',
                                                       'geophys_contact_mode': 'discrete'}},
                                execution_scope='device_batch')


def test_pickcube_device_source_uses_declared_effort_transmissions():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.sessions.source import close_source_and_task_resources

    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    request = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': '/tmp/profile-python'},
               'controller': {'profile_id': 'panda-direct-effort-v1'},
               'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 20}}
    config = resolve_task_env_config(task, request, execution_scope='device_batch')
    binding = task._build_selected_binding(config)
    built = binding.build_for_request(config.physics_provider, config.environment.runtime.backend, 31, 20)
    try:
        execution = built['physical_execution']
        execution.validate_source(scene=built['source'].scene_definition,
            artifact_sha256=built['artifact'].identity_hash, source_id=built['source'].source_id,
            source_closure_sha256=built['source'].source_closure_digest, source=built['source'])
        channels = execution.compiled.binding.channels
        pair = [channel for channel in channels if channel.native_actuator in built['source'].open_actuators]
        assert len(pair) == 2
        assert pair[0].transmission_id == pair[1].transmission_id
        assert [channel.transmission_coefficient for channel in pair] == [.5, .5]
        assert all(channel.native_drive == 'disabled' for channel in channels)
        assert 'cube-v1' in built['source'].free_joints
        space = built['controller'].device_action_space().spaces['effort']
        assert space.shape == (len(built['controller'].profile.action_names),)
        # The last input is total tendon effort; each finger receives one half.
        assert float(space.low[-1]) == -5.0
        assert float(space.high[-1]) == 5.0
        assert all(float(value) == 250.0 for value in space.high[:-1])
    finally:
        close_source_and_task_resources(built['source'], binding)

    with pytest.raises(ValueError, match='isolated native drives'):
        resolve_task_env_config(task, {**request, 'robot': {'native_drive': 'position'}},
                                execution_scope='device_batch')


@pytest.mark.skipif(not torch.cuda.is_available(), reason='CUDA device required')
def test_pickcube_device_linear_effort_respects_tendon_and_row_identity():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.contracts import DeviceStateIdentity
    from task_env.runtime.sessions.source import close_source_and_task_resources

    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    config = resolve_task_env_config(task, {
        'execution': {'physics_provider': 'mujoco_warp', 'interpreter': '/tmp/profile-python'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 20},
    }, execution_scope='device_batch')
    binding = task._build_selected_binding(config)
    built = binding.build_for_request(config.physics_provider, config.environment.runtime.backend, 31, 20)
    controller = built['controller']
    try:
        physical = controller.binding
        identity = DeviceStateIdentity(physical.source_id, physical.source_closure_sha256,
            physical.artifact_sha256, 'fixture', 0, 0, 0, 0., .01)
        state = DeviceBatchState({'qpos': torch.zeros((3, 1), device='cuda')}, 'cuda:0', 3,
            identity, 'owned_snapshot', torch.tensor([1, 2, 3], device='cuda', dtype=torch.int64),
            torch.tensor([0, 4, 7], device='cuda', dtype=torch.int32))
        action = torch.tensor([[1., -2., 3., -4., 5., -6., 7., 4.],
                               [-1., 2., -3., 4., -5., 6., -7., -4.],
                               [0., 0., 0., 0., 0., 0., 0., 0.]], device='cuda')
        expected = torch.tensor([[1., -2., 3., -4., 5., -6., 7., 2., 2.],
                                 [-1., 2., -3., 4., -5., 6., -7., -2., -2.],
                                 [0., 0., 0., 0., 0., 0., 0., 0., 0.]], device='cuda')
        command = controller.convert_device_batch({'effort': action}, state)
        torch.testing.assert_close(command.values, expected, rtol=0, atol=0)
        assert torch.equal(command.episode_ids, state.episode_ids)
        assert torch.equal(command.episode_steps, state.episode_steps)
        with pytest.raises(ValueError, match='exceeds'):
            controller.convert_device_batch({'effort': action + 251.}, state)
        with pytest.raises(ValueError, match='action tree'):
            controller.convert_device_batch({'other': action}, state)
    finally:
        controller.close_device()
        close_source_and_task_resources(built['source'], binding)


def test_device_camera_observation_preserves_terminal_and_reset_frames():
    from task_env.environment.config import CameraSpec
    from task_env.render.providers.parallel import ParallelRenderProvider
    from task_env.vectorization.task_definition import BatchTaskLifecycleAdapter

    class Runtime:
        num_envs = 3
        def __init__(self):
            self.q = torch.zeros(3, 1)
            self.steps = self.resets = 0
        def resource_summary(self):
            return {'device_transition': {'available': True, 'field_device': 'cpu',
                    'transport': 'cuda_ipc', 'state_readback_fields': ['qpos'],
                    'state_shapes': {'qpos': (1,)}}}
        def read_device_state(self, fields):
            return DeviceBatchState({'qpos': self.q.clone()}, 'cpu', 3)
        def reset_device(self, values, mask, *, selection=None):
            self.resets += 1
            self.q = torch.where(mask[:, None], values['qpos'], self.q)
            return self.read_device_state(('qpos',))
        def step_device(self, control):
            self.steps += 1
            self.q += torch.tensor([[1.], [2.], [3.]])
            return self.read_device_state(('qpos',))
        def close(self):
            pass

    class Task:
        device_state_required_fields = ('qpos',)
        def device_reset_spec(self):
            return {'random': {'sample': (1,)}, 'state_fields': ('qpos',)}
        def sample_device_reset(self, uniforms, template):
            return {'qpos': torch.full_like(template['qpos'], 10.)}
        def build_device_observation(self, state):
            return {'state': state.arrays['qpos'].clone()}
        def evaluate_device(self, **kwargs):
            return {'reward': torch.zeros(3), 'terminated': torch.tensor([False, True, False]),
                    'truncated': torch.zeros(3, dtype=torch.bool)}
        def reset_device(self, **kwargs):
            pass

    class Controller:
        def convert_device_batch(self, action, state):
            return action

    class Source:
        window_closes = captures = 0
        failure = None
        closed = False
        def render_parallel(self, **kwargs):
            raise AssertionError('camera capture must not render an observer frame')
        def capture_cameras(self, *, state, world_ids, world_transforms, width, height):
            self.captures += 1
            if self.failure is not None:
                raise self.failure
            assert world_ids == (0, 1, 2)
            pixels = state.arrays['qpos'].to(torch.uint8).reshape(3, 1, 1, 1)
            return {'base': {'rgb': pixels.expand(3, 2, 2, 3).clone()}}
        def close_window(self):
            self.window_closes += 1
        def close(self):
            self.closed = True

    runtime, source = Runtime(), Source()
    adapter = BatchTaskLifecycleAdapter(uid='fixture', num_envs=3, backend='cpu', base_seed=9,
        runtime=runtime, reset_sampler=None, compiled_scene=None, initial_state=None,
        task_definition=Task(), action_adapter=Controller(),
        single_action_space=gym.spaces.Box(-1., 1., (1,), dtype=np.float32),
        single_observation_space=gym.spaces.Dict({'state': gym.spaces.Box(0., 100., (1,), dtype=np.float32)}),
        metadata={'execution': 'device_worker', 'transfer_mode': 'device',
                  'runtime_resource_summary': runtime.resource_summary()}, horizon=20, ignore_done=False)
    adapter.parallel_render_provider = ParallelRenderProvider(num_envs=3, render_source=source)
    adapter.configure_device_cameras((CameraSpec(name='base', width=2, height=2, rgb_dtype='uint8'),))
    env = HomogeneousVectorTaskEnv(adapter, execution_mode='device')
    assert env.single_observation_space['cameras']['base']['rgb'].shape == (2, 2, 3)
    assert env.observation_space['cameras']['base']['rgb'].shape == (3, 2, 2, 3)
    observation, _ = env.reset()
    assert observation['cameras']['base']['rgb'][:, 0, 0, 0].tolist() == [10, 10, 10]
    observation, _, terminated, _, info = env.step(torch.zeros(3, 1))
    assert terminated.tolist() == [False, True, False]
    assert observation['cameras']['base']['rgb'][:, 0, 0, 0].tolist() == [11, 10, 13]
    terminal = info['final_observation']['cameras']['base']['rgb']
    assert terminal[:, 0, 0, 0].tolist() == [0, 12, 0]
    assert runtime.steps == 1 and runtime.resets == 2 and source.captures == 3
    env.close_render()
    assert source.window_closes == 1
    env.step(torch.zeros(3, 1))
    assert terminal[:, 0, 0, 0].tolist() == [0, 12, 0]
    assert runtime.steps == 2 and source.captures == 5
    failure = RuntimeError('camera capture failed after physics')
    source.failure = failure
    with pytest.raises(RuntimeError, match='camera capture failed after physics') as caught:
        env.step(torch.zeros(3, 1))
    assert caught.value is failure and runtime.steps == 3
    with pytest.raises(RuntimeError, match='faulted') as latched:
        env.reset()
    assert latched.value.__cause__ is failure
    env.close()
    assert source.closed


def test_unimplemented_task_and_missing_interpreter_fail_before_native_start(tmp_path, monkeypatch):
    from task_env import make_parallel_env
    from task_env.environment.types import StageUnavailableError
    from task_env.runtime.transport import worker

    interpreter = str(tmp_path / 'missing-python')
    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': interpreter}}
    original = worker.RuntimeWorker
    monkeypatch.setattr(worker, 'RuntimeWorker', lambda *a, **k: pytest.fail('worker started for unsupported task'))
    with pytest.raises(StageUnavailableError, match='device semantics'):
        make_parallel_env('two-wheel-balance-v1', env_config=config, num_env=3, execution='device')
    monkeypatch.setattr(worker, 'RuntimeWorker', original)
    with pytest.raises(FileNotFoundError):
        make_parallel_env('pendulum-v1', env_config=config, num_env=3, execution='device')


@pytest.mark.parametrize('terminated,truncated', [
    ([False, True, False], [False, False, False]),
    ([True, False, True], [False, False, True]),
    ([True, True, True], [False, False, False]),
    ([False, False, False], [False, False, False]),
])
def test_device_final_columns_preserve_rows_metrics_and_old_boundary(terminated, truncated):
    """Same-step results retain full B rows and task evidence across a reset."""
    class Spec:
        uid = 'device-fixture'
        num_envs = 3
        metadata = {}
        parallel_render_provider = None
        single_action_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)
        single_observation_space = gym.spaces.Dict({'state': gym.spaces.Box(-100., 100., (1,), dtype=np.float32)})

        def __init__(self):
            self.values = torch.tensor([[11.], [22.], [33.]])
            self.metrics = torch.tensor([1., 2., 3.])
            self.episodes = torch.ones(3, dtype=torch.int64)
            self.steps = torch.tensor([4, 5, 6], dtype=torch.int32)
            self.resets = 0

        @property
        def device_episode_ids(self):
            return self.episodes.clone()

        @property
        def device_episode_steps(self):
            return self.steps.clone()

        def reset_sampled_device(self, *, seed=None, mask=None, selection=None):
            if mask is not None:
                self.resets += 1
                self.values[mask] = -1.
                self.metrics[mask] = -9.
                self.episodes[mask] += 1
                self.steps[mask] = 0
            state = SimpleNamespace(identity='new-boundary')
            return SimpleNamespace(state=state, observation={'state': self.values},
                                   infos={'episode_id': self.episodes.clone()})

        def step_device(self, action):
            return DeviceBatchTransition({'state': self.values}, torch.tensor([.1, .2, .3]),
                torch.tensor(terminated), torch.tensor(truncated), 'cpu',
                infos={'metrics': {'score': self.metrics}, 'reward_terms': {'cost': self.metrics}},
                boundary='old-boundary')

        def prepare_device_reset_selection(self, mask):
            return SimpleNamespace(selected_count=int(mask.sum()))

        def close(self):
            pass

    spec = Spec()
    env = HomogeneousVectorTaskEnv(spec, execution_mode='device')
    env.reset()
    obs, _, term, trunc, info = env.step(None)
    done = torch.tensor(terminated) | torch.tensor(truncated)
    assert term.tolist() == terminated and trunc.tolist() == truncated
    assert info['_final_observation'].tolist() == done.tolist()
    assert info['_final_observation'] is info['final_mask']
    assert info['final_observation']['state'].shape == (3, 1)
    torch.testing.assert_close(info['final_observation']['state'][done], torch.tensor([[11.], [22.], [33.]])[done])
    assert info['final_info']['env_id'].tolist() == [0, 1, 2]
    assert info['final_info']['episode_id'].tolist() == [1, 1, 1]
    assert info['final_info']['episode_step'].tolist() == [4, 5, 6]
    assert info['final_info']['boundary'] == 'old-boundary'
    assert info['metrics']['score'].tolist() == [1., 2., 3.]
    assert info['final_info']['task']['reward_terms']['cost'].tolist() == [1., 2., 3.]
    assert spec.resets == int(done.any())
    if done.any():
        assert info['reset_info']['boundary'] == 'new-boundary'
        assert torch.equal(info['reset_info']['episode_id'][done], torch.tensor([2] * int(done.sum())))
        assert torch.all(obs['state'][done] == -1.)
    spec.values.fill_(0.)
    torch.testing.assert_close(info['final_observation']['state'][done], torch.tensor([[11.], [22.], [33.]])[done])
    env.close()


@pytest.mark.parametrize('algorithm', [None, 'pcg64-v0'])
def test_device_reset_sampling_accepts_task_declared_domains_and_other_state_fields(algorithm):
    """The common sampler does not assume Pendulum's two random values or qpos/qvel."""
    from task_env.vectorization.task_definition import BatchTaskLifecycleAdapter

    class Runtime:
        num_envs = 3
        def __init__(self):
            self.value = torch.zeros((3, 3))
        def resource_summary(self):
            return {'device_transition': {'available': True, 'field_device': 'cpu',
                'transport': 'cuda_ipc', 'state_readback_fields': ['position'],
                'state_shapes': {'position': (3,)}}}
        def reset_device(self, state, mask, *, selection=None):
            self.value = torch.where(mask[:, None], state['position'], self.value)
            return DeviceBatchState({'position': self.value}, 'cpu', 3)
        def read_device_state(self, names):
            return DeviceBatchState({name: self.value for name in names}, 'cpu', 3)
        def step_device(self, action):
            raise AssertionError('not part of reset')
        def close(self):
            pass

    class Task:
        device_state_required_fields = ('position',)
        device_random_algorithm = algorithm
        def device_reset_spec(self):
            return {'random': {'point': (3,), 'offset': ()}, 'state_fields': ('position',)}
        def sample_device_reset(self, uniforms, template):
            return {'position': uniforms['point'] + uniforms['offset'][:, None]}
        def build_device_observation(self, state):
            return {'position': state.arrays['position'].clone()}
        def evaluate_device(self, **kwargs):
            raise AssertionError('not part of reset')
        def reset_device(self, **kwargs):
            pass

    class Controller:
        def convert_device_batch(self, action, state):
            raise AssertionError('not part of reset')

    def build():
        runtime = Runtime()
        return BatchTaskLifecycleAdapter(uid='fixture', num_envs=3, backend='cpu', base_seed=9,
            runtime=runtime, reset_sampler=None, compiled_scene=None, initial_state=None,
            task_definition=Task(), action_adapter=Controller(),
            single_action_space=gym.spaces.Box(-1., 1., (1,), dtype=np.float32),
            single_observation_space=gym.spaces.Dict({'position': gym.spaces.Box(0., 2., (3,), dtype=np.float32)}),
            metadata={'execution': 'device_worker', 'transfer_mode': 'device',
                      'runtime_resource_summary': runtime.resource_summary()}, horizon=20, ignore_done=False)

    first, second = build(), build()
    initial = first.reset_sampled_device(seed=19).state.arrays['position'].clone()
    second.reset_sampled_device(seed=19)
    if algorithm == 'pcg64-v0':
        for row in range(3):
            rng = np.random.Generator(np.random.PCG64(19 + row))
            expected = rng.random(3).astype(np.float32) + np.float32(rng.random())
            np.testing.assert_array_equal(initial[row].numpy(), expected)
    first.reset_sampled_device(mask=torch.tensor([False, True, False]))
    select = torch.tensor([True, False, True])
    a = first.reset_sampled_device(mask=select).state.arrays['position']
    b = second.reset_sampled_device(mask=select).state.arrays['position']
    assert a.shape == (3, 3)
    assert torch.equal(a[select], b[select])
    assert not torch.equal(a[0], a[2])
    first.close()
    second.close()


def test_ipc_cleanup_continues_after_failure_and_retries_remaining_mapping():
    from task_env.runtime.transport.cuda_ipc import CudaIpcConnection

    class Driver:
        def __init__(self):
            self.closed = []
            self.events = []
            self.fail = True
        def cuIpcCloseMemHandle(self, pointer):
            self.closed.append(pointer)
            if pointer == 10 and self.fail:
                return (1,)
            return (0,)
        def cuEventDestroy(self, event):
            self.events.append(event)
            return (0,)

    connection = object.__new__(CudaIpcConnection)
    connection._cu = Driver()
    connection._buffers = {'failed': (10, (1,), 'float32'), 'other': (20, (1,), 'float32')}
    connection._ready, connection._written = 30, 40
    connection.synchronize = lambda: None
    with pytest.raises(RuntimeError, match='CUDA driver IPC operation failed'):
        connection.close()
    assert connection._cu.closed == [10, 20]
    assert connection._cu.events == [30, 40]
    assert list(connection._buffers) == ['failed']
    connection._cu.fail = False
    connection.close()
    assert not connection._buffers
    connection.close()


def test_ipc_partial_construction_preserves_original_error_and_cleans_import(monkeypatch):
    from cuda.bindings import driver as cu
    from task_env.runtime.transport import cuda_ipc

    failure = RuntimeError('second mapping failed')
    closed = []
    calls = iter(((0, 123), (1,)))
    monkeypatch.setattr(torch.cuda, 'init', lambda: None)
    monkeypatch.setattr(torch.cuda, 'current_device', lambda: 0)
    monkeypatch.setattr(torch.cuda, 'current_stream', lambda *_: SimpleNamespace(synchronize=lambda: None))
    monkeypatch.setattr(cuda_ipc, '_decode_handle', lambda *_: object())

    def open_mapping(*_):
        result = next(calls)
        if result[0]:
            raise failure
        return result

    monkeypatch.setattr(cu, 'cuIpcOpenMemHandle', open_mapping)
    monkeypatch.setattr(cu, 'cuIpcCloseMemHandle', lambda pointer: (closed.append(pointer) or (0,)))
    description = {'device': 'cuda:0', 'buffers': {
        'first': {'handle': '', 'shape': [1], 'dtype': 'float32'},
        'second': {'handle': '', 'shape': [1], 'dtype': 'float32'}}, 'ready': ''}
    with pytest.raises(RuntimeError, match='second mapping failed') as caught:
        cuda_ipc.CudaIpcConnection(description)
    assert caught.value is failure
    assert closed == [123]


def test_ipc_publisher_partial_construction_synchronizes_and_preserves_error(monkeypatch):
    import contextlib
    import sys
    from task_env.runtime.transport.cuda_ipc import CudaIpcPublisher

    failure = RuntimeError('second allocation failed')
    events = []
    device = SimpleNamespace(is_cuda=True, is_ipc_supported=True)
    def allocate(*args, **kwargs):
        events.append('allocate')
        if events.count('allocate') == 2:
            raise failure
        return object()
    warp = SimpleNamespace(init=lambda: None, get_device=lambda _: device,
                           ScopedMempool=lambda *_: contextlib.nullcontext(),
                           zeros=allocate, float32=object(),
                           synchronize_device=lambda value: events.append(('synchronize', value)))
    monkeypatch.setitem(sys.modules, 'warp', warp)
    with pytest.raises(RuntimeError, match='second allocation failed') as caught:
        CudaIpcPublisher({'first': (1,), 'second': (1,)})
    assert caught.value is failure
    assert events == ['allocate', 'allocate', ('synchronize', device)]


def test_worker_startup_and_abrupt_exit_retire_all_owned_resources(monkeypatch, tmp_path):
    from task_env.runtime.transport import worker

    class Stream:
        closed = False
        def close(self):
            self.closed = True

    class Process:
        returncode = 73
        def __init__(self):
            self.stdin, self.stdout = Stream(), Stream()
        def poll(self):
            return self.returncode

    process = Process()
    failure = ConnectionError('startup connection closed')
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: process)
    monkeypatch.setattr(worker, '_send', lambda *a, **k: None)
    monkeypatch.setattr(worker, '_receive', lambda *a, **k: (_ for _ in ()).throw(failure))
    temporary = tmp_path / 'worker'
    temporary.mkdir()
    monkeypatch.setattr(worker.tempfile, 'TemporaryDirectory',
                        lambda **_: SimpleNamespace(name=str(temporary), cleanup=lambda: temporary.rmdir()))
    with pytest.raises(ConnectionError, match='startup connection closed') as caught:
        worker.RuntimeWorker('interpreter', {})
    assert caught.value is failure
    assert process.stdin.closed and process.stdout.closed and not temporary.exists()
    assert any('exited with code 73' in note for note in failure.__notes__)

    process = Process()
    runtime = worker.RuntimeWorker.__new__(worker.RuntimeWorker)
    runtime._process, runtime._temporary_directory = process, None
    with pytest.raises(RuntimeError, match='exited with code 73'):
        runtime.close()
    assert runtime.closed and process.stdin.closed and process.stdout.closed
    runtime.close()


def test_closed_remote_session_retries_failed_ipc_cleanup():
    from task_env.runtime.sessions.transport import RemoteSession

    class Connection:
        calls = 0
        def close(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError('mapping still open')

    connection = Connection()
    session = RemoteSession.__new__(RemoteSession)
    session._closed, session._device_pose_ipc = True, connection
    with pytest.raises(RuntimeError, match='mapping still open'):
        session.close()
    session.close()
    session.close()
    assert connection.calls == 2 and session._device_pose_ipc is None


def test_remote_cleanup_continues_after_socket_failure():
    from task_env.runtime.sessions.transport import RemoteSession

    events = []
    failure = RuntimeError('socket close failed')
    def fail_socket():
        events.append('socket')
        raise failure
    connection = SimpleNamespace(release_imports=lambda: events.append('unmap'),
                                 close=lambda: events.append('ipc'))
    process = SimpleNamespace(wait=lambda timeout: events.append('wait'), returncode=0)
    session = RemoteSession.__new__(RemoteSession)
    session._closed, session._device_pose_ipc = False, connection
    session._sock, session._process = SimpleNamespace(close=fail_socket), process
    session._call = lambda _: events.append('request')
    with pytest.raises(RuntimeError, match='socket close failed') as caught:
        session.close()
    assert caught.value is failure
    assert events == ['unmap', 'request', 'socket', 'wait', 'ipc']
    session.close()


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_camera_binding_failure_preserves_original_error_while_closing_visualizer(cleanup_fails):
    from task_env.environment.config import CameraSpec
    from task_env.render.rasterizer.device import DeviceBatchRasterSource

    failure = ValueError('camera binding failed')
    cleanup_failure = RuntimeError('renderer close failed')

    class SceneSource:
        def compute_default_camera(self):
            return (0, 0, 1), (0, 0, 0), (0, 1, 0)

    class Visualizer:
        def __init__(self):
            self.closed = 0
        def set_camera_pose(self, *args):
            pass
        def bind_task_camera(self, **kwargs):
            raise failure
        def close(self):
            self.closed += 1
            if cleanup_fails and self.closed == 1:
                raise cleanup_failure

    visualizer = Visualizer()
    source = DeviceBatchRasterSource(runtime=None, source=None,
                                     cameras=(CameraSpec(name='base', rgb_dtype='uint8'),))
    source._visualizer = visualizer
    with pytest.raises(ValueError, match='camera binding failed') as caught:
        source._configure_visualizer(SceneSource())
    assert caught.value is failure
    assert visualizer.closed == 1
    if cleanup_fails:
        assert any('renderer close failed' in note for note in failure.__notes__)
        assert source._visualizer is visualizer
        source.close()
        assert visualizer.closed == 2
    assert source._visualizer is None


def test_device_camera_capture_failure_propagates_and_renderer_can_close():
    from task_env.environment.config import CameraSpec
    from task_env.render.rasterizer.device import DeviceBatchRasterSource

    failure = RuntimeError('camera frame failed')
    state = DeviceBatchState({'body_position': torch.zeros(3, 1, 3),
                              'body_orientation': torch.zeros(3, 1, 4)}, 'cpu', 3)

    class Runtime:
        reads = 0
        def read_device_state(self, fields):
            self.reads += 1
            return state

    class Visualizer:
        closed = False
        def update_task_camera_pose_from_device(self, **kwargs):
            pass
        def write_task_camera_rgb8(self, frame, *, camera_id):
            raise failure
        def close(self):
            self.closed = True

    class Sensor:
        spec = CameraSpec(name='base', rgb_dtype='uint8')
        def resolve_device_pose(self, state, *, world_offsets):
            return torch.zeros(3, 3, 3)

    runtime, visualizer = Runtime(), Visualizer()
    source = DeviceBatchRasterSource(runtime=runtime, source=None, cameras=(Sensor.spec,))
    source._visualizer = visualizer
    source._camera_sensors = (Sensor(),)
    source._world_ids, source._world_transforms = (0, 1, 2), ((), (), ())
    source._translation = torch.zeros(3, 3)
    source._publish_pose = lambda state, world_ids: None
    with pytest.raises(RuntimeError, match='camera frame failed') as caught:
        source.capture_cameras(state=state, world_ids=(0, 1, 2),
                               world_transforms=((), (), ()), width=2, height=2)
    assert caught.value is failure and runtime.reads == 1
    source.close()
    assert visualizer.closed


def test_device_render_cleanup_attempts_all_owners_and_retries():
    from task_env.render.rasterizer.device import DeviceBatchRasterSource
    from task_env.render.providers.parallel import ParallelRenderProvider

    class Window:
        calls = 0
        def destroy(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError('window cleanup failed')

    class Visualizer:
        calls = 0
        def close(self):
            self.calls += 1

    source = DeviceBatchRasterSource(runtime=None, source=None)
    window, visualizer = Window(), Visualizer()
    source._window, source._visualizer = window, visualizer
    provider = ParallelRenderProvider(num_envs=1, render_source=source)
    with pytest.raises(RuntimeError, match='window cleanup failed'):
        provider.close()
    assert window.calls == 1 and visualizer.calls == 1
    provider.close()
    provider.close()
    assert window.calls == 2 and visualizer.calls == 1


def test_device_env_retries_close_after_partial_cleanup():
    class Spec:
        uid = 'close-fixture'
        num_envs = 1
        metadata = {}
        parallel_render_provider = None
        single_action_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)
        single_observation_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)
        def __init__(self):
            self.calls = 0
        def close(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError('resource release failed')

    spec = Spec()
    env = HomogeneousVectorTaskEnv(spec, execution_mode='device')
    with pytest.raises(RuntimeError, match='resource release failed'):
        env.close()
    with pytest.raises(RuntimeError, match='closed'):
        env.reset()
    env.close()
    env.close()
    assert spec.calls == 2


def test_device_vector_recorder_keeps_staggered_terminal_rows_and_boundary_contexts(tmp_path):
    import h5py
    from task_env.recorders import VectorTransitionRecorder, inspect_trajectory_h5
    from task_env.runtime.contracts import DeviceStateIdentity

    def boundary(revision):
        return DeviceStateIdentity('source', 'a' * 64, 'b' * 64, 'native-1', 7,
                                   revision, revision * 25, revision * .05, .05)

    class Env:
        num_envs = 3
        metadata = {'execution': 'device_worker', 'action_schema': {'components': ['torque']}}
        single_action_space = gym.spaces.Dict({'torque': gym.spaces.Box(-2., 2., (1,), dtype=np.float32)})
        action_space = gym.vector.utils.batch_space(single_action_space, 3)
        single_observation_space = gym.spaces.Dict({'state': gym.spaces.Box(-100., 100., (1,), dtype=np.float32)})
        observation_space = gym.vector.utils.batch_space(single_observation_space, 3)
        render_mode = None

        def __init__(self):
            self.episode = torch.ones(3, dtype=torch.int64)
            self.clock = torch.zeros(3, dtype=torch.int32)
            self.tick = 0
        def get_record_metadata(self):
            return {'env_metadata': self.metadata, 'resolved_config': {}, 'universal_action_schema': {}}
        def obs(self, values):
            frame = torch.tensor(values, dtype=torch.uint8)[:, None, None, None].expand(3, 2, 2, 3).clone()
            return {'state': {'value': torch.tensor(values, dtype=torch.float32)[:, None]},
                    'cameras': {'base': {'rgb': frame}}}
        def reset(self, **kwargs):
            return self.obs([10, 20, 30]), {'env_id': torch.arange(3), 'episode_id': self.episode.clone(),
                                           'episode_step': self.clock.clone(), 'boundary': boundary(0)}
        def step(self, actions):
            self.tick += 1
            self.clock += 1
            done = torch.tensor([False, True, False] if self.tick == 1 else [True, False, True])
            old = {'env_id': torch.arange(3), 'episode_id': self.episode.clone(),
                   'episode_step': self.clock.clone(), 'boundary': boundary(self.tick)}
            final = self.obs([11 * self.tick, 22 * self.tick, 33 * self.tick])
            self.episode[done] += 1
            self.clock[done] = 0
            obs = self.obs([101 if done[0] else 11 * self.tick,
                            102 if done[1] else 22 * self.tick,
                            103 if done[2] else 33 * self.tick])
            reset_info = {'env_id': torch.arange(3), 'episode_id': self.episode.clone(),
                          'episode_step': self.clock.clone(), 'boundary': boundary(self.tick + 10)}
            info = {'episode_id': self.episode.clone(), 'episode_step': self.clock.clone(),
                    'boundary': boundary(self.tick + 10), 'final_info': old, 'reset_info': reset_info,
                    'final_observation': final, '_final_observation': done,
                    'metrics': {'score': torch.tensor([1., 2., 3.])}, 'reward_terms': {}}
            return obs, torch.tensor([.1, .2, .3]), done, torch.zeros(3, dtype=torch.bool), info
        def close(self):
            pass

    env = Env()
    recorder = VectorTransitionRecorder(env, path=tmp_path, env_ids=(0, 1))
    initial, _ = recorder.reset()
    action = {'torque': torch.zeros((3, 1))}
    first, _, first_term, _, _ = recorder.step(action)
    second, _, second_term, _, _ = recorder.step(action)
    assert first_term.tolist() == [False, True, False]
    assert second_term.tolist() == [True, False, True]
    paths = recorder.saved_paths
    assert len(paths) == 2
    row1, row0 = paths
    one = inspect_trajectory_h5(row1)
    zero = inspect_trajectory_h5(row0)
    assert [c['env_id'] for c in one['boundary_contexts']] == [1, 1]
    assert [c['episode_id'] for c in one['boundary_contexts']] == [1, 1]
    assert [c['episode_step'] for c in zero['boundary_contexts']] == [0, 1, 2]
    assert zero['boundary_contexts'][-1]['generation'] == 7
    with h5py.File(row1) as h5:
        np.testing.assert_array_equal(h5['obs/state/value'][:, 0], [20., 22.])
        assert h5['obs/cameras/base/rgb'][1, 0, 0, 0] == 22
    with h5py.File(row0) as h5:
        np.testing.assert_array_equal(h5['obs/state/value'][:, 0], [10., 11., 22.])
        assert h5['obs/cameras/base/rgb'][2, 0, 0, 0] == 22
    assert first['state']['value'][1].item() == 102
    assert second['state']['value'][0].item() == 101
    recorder.close()

    disabled = VectorTransitionRecorder(Env(), path=tmp_path, record=False, env_ids=(0, 1))
    disabled._device_row = lambda *args: pytest.fail('disabled recording copied device data')
    disabled.reset()
    disabled.step(action)
    disabled.close()


def test_device_recorder_retries_failed_row_and_preserves_first_close_error(monkeypatch, tmp_path):
    from task_env.recorders import VectorTransitionRecorder, inspect_trajectory_h5
    from task_env.recorders.recorder import TransitionRecorder
    from task_env.runtime.contracts import DeviceStateIdentity

    class Env:
        num_envs = 2
        metadata = {'execution': 'device_worker', 'action_schema': {'components': ['torque']}}
        single_action_space = gym.spaces.Dict({'torque': gym.spaces.Box(-2., 2., (1,), dtype=np.float32)})
        action_space = gym.vector.utils.batch_space(single_action_space, 2)
        observation_space = gym.vector.utils.batch_space(gym.spaces.Dict({
            'state': gym.spaces.Box(-100., 100., (1,), dtype=np.float32)}), 2)
        render_mode = None
        steps = 0
        close_calls = 0

        def get_record_metadata(self):
            return {'env_metadata': self.metadata, 'resolved_config': {}, 'universal_action_schema': {}}

        def info(self):
            boundary = DeviceStateIdentity('source', 'a' * 64, 'b' * 64, 'native-1', 1,
                                           self.steps, self.steps * 25, self.steps * .05, .05)
            return {'env_id': torch.arange(2), 'episode_id': torch.ones(2, dtype=torch.int64),
                    'episode_step': torch.full((2,), self.steps), 'boundary': boundary,
                    'metrics': {}, 'reward_terms': {}}

        def reset(self):
            return {'state': torch.zeros((2, 1))}, self.info()

        def step(self, actions):
            self.steps += 1
            return ({'state': torch.ones((2, 1))}, torch.zeros(2), torch.zeros(2, dtype=torch.bool),
                    torch.zeros(2, dtype=torch.bool), self.info())

        def close(self):
            self.close_calls += 1
            if self.close_calls == 1:
                raise RuntimeError('environment close failed')

    failure = OSError('row zero save failed')
    save = TransitionRecorder.save_h5
    attempts = []

    def save_with_failure(recorder, *, path, name):
        attempts.append(name)
        if 'slot_000' in name and attempts.count(name) == 1:
            raise failure
        return save(recorder, path=path, name=name)

    monkeypatch.setattr(TransitionRecorder, 'save_h5', save_with_failure)
    env = Env()
    recorder = VectorTransitionRecorder(env, path=tmp_path)
    recorder.reset()
    action = {'torque': torch.zeros((2, 1))}
    recorder.step(action)
    with pytest.raises(OSError, match='row zero save failed') as caught:
        recorder.close()
    assert caught.value is failure
    assert any('environment close failed' in note for note in failure.__notes__)
    assert len(recorder.saved_paths) == 1 and 'slot_001' in recorder.saved_paths[0].name
    with pytest.raises(RuntimeError, match='device recording is faulted') as fault:
        recorder.step(action)
    assert fault.value.__cause__ is failure and env.steps == 1
    recorder.close()
    recorder.close()
    assert len(recorder.saved_paths) == 2
    assert all(inspect_trajectory_h5(path)['transition_count'] == 1 for path in recorder.saved_paths)

    class TerminalEnv(Env):
        def step(self, actions):
            observation, reward, terminated, truncated, info = super().step(actions)
            terminated[0] = True
            info['final_info'] = dict(info)
            info['reset_info'] = dict(info)
            info['final_observation'] = observation
            return observation, reward, terminated, truncated, info

        def close(self):
            self.close_calls += 1

    attempts.clear()
    step_output = tmp_path / 'step'
    step_output.mkdir()
    env = TerminalEnv()
    recorder = VectorTransitionRecorder(env, path=step_output)
    recorder.reset()
    with pytest.raises(OSError, match='row zero save failed') as step_error:
        recorder.step(action)
    assert step_error.value is failure and env.steps == 1
    with pytest.raises(RuntimeError, match='device recording is faulted'):
        recorder.reset()
    with pytest.raises(RuntimeError, match='device recording is faulted'):
        recorder.step(action)
    with pytest.raises(RuntimeError, match='device recording is faulted'):
        recorder.start_record()
    assert env.steps == 1
    recorder.end_record()
    assert len(recorder.saved_paths) == 2
    assert all(inspect_trajectory_h5(path)['transition_count'] == 1 for path in recorder.saved_paths)
    recorder.close()

    class ResetEnv(Env):
        reset_calls = 0
        def reset(self):
            self.reset_calls += 1
            return {'state': torch.full((2, 1), 10. * self.reset_calls)}, self.info()
        def close(self):
            self.close_calls += 1

    attempts.clear()
    reset_output = tmp_path / 'reset'
    reset_output.mkdir()
    env = ResetEnv()
    recorder = VectorTransitionRecorder(env, path=reset_output)
    recorder.reset()
    recorder.step(action)
    with pytest.raises(OSError, match='row zero save failed') as reset_error:
        recorder.reset()
    assert reset_error.value is failure and env.reset_calls == 2
    with pytest.raises(RuntimeError, match='device recording is faulted'):
        recorder.reset()
    with pytest.raises(RuntimeError, match='device recording is faulted'):
        recorder.step(action)
    assert env.reset_calls == 2 and env.steps == 1
    recorder.end_record()
    assert len(recorder.saved_paths) == 2
    monkeypatch.setattr(TransitionRecorder, 'save_h5', save)
    recorder.start_record()
    recorder.step(action)
    recorder.close()
    import h5py
    resumed = [path for path in recorder.saved_paths if 'episode_000001' in path.name]
    assert len(resumed) == 2
    for path in resumed:
        with h5py.File(path) as h5:
            np.testing.assert_array_equal(h5['obs/state'][:, 0], [20., 1.])


def test_camera_sensor_device_pose_composes_wxyz_parent_and_one_grid_offset():
    from task_env.assembly.references import SceneNameTable, TaskReferences
    from task_env.environment.config import CameraSpec
    from task_env.observations.camera import CameraSensor

    references = TaskReferences(SceneNameTable(bodies={'robot/hand': 0}, joints={}, sites={}, geoms={}, actuators={}), {}, {})
    sensor = CameraSensor(spec=CameraSpec(name='hand', frame='body', parent='robot/hand',
        position=(1., 0., 0.), quaternion_wxyz=(1., 0., 0., 0.)), references=references)
    q = 2 ** -.5
    state = DeviceBatchState({'body_position': torch.tensor([[[1., 2., 3.]], [[4., 5., 6.]]]),
        'body_orientation': torch.tensor([[[q, 0., 0., q]], [[1., 0., 0., 0.]]])}, 'cpu', 2)
    pose = sensor.resolve_device_pose(state, world_offsets=torch.tensor([[10., 0., 0.], [0., 5., 0.]]))
    torch.testing.assert_close(pose[0], torch.tensor([[11., 3., 3.], [11., 4., 3.], [0., 0., 1.]]), atol=2e-6, rtol=0.)
    torch.testing.assert_close(pose[1], torch.tensor([[5., 10., 6.], [6., 10., 6.], [0., 0., 1.]]), atol=2e-6, rtol=0.)


def test_pick_cube_device_semantics_match_scalar_threshold_oracle():
    from task_env.tasks.pick_cube.task import (
        PickCubeTaskDefinition, _DeviceTaskBinding, _evaluate_values, semantic_definition,
    )

    semantics = semantic_definition()
    p = semantics.parameters_si
    # Values on both sides of the reach, opening, and lift boundaries. The
    # scalar evaluator sees the actual float32 inputs, not separately rounded
    # literals, so this also checks the threshold classifications.
    z = p['rest_height']
    cube = torch.tensor([[.4, .1, z], [.4, .1, z + p['lift_height'] - .002],
                         [.4, .1, z + p['lift_height'] + .002], [.4, .1, z]], dtype=torch.float32)
    eef = cube.clone()
    eef[:, 0] += torch.tensor([p['reach_distance'] - .002, p['reach_distance'] + .002,
                               .01, .01])
    openings = torch.tensor([p['gripper_closed_opening'] - .002,
                             p['gripper_closed_opening'] - .002,
                             p['gripper_closed_opening'] + .002, .0])

    class View:
        def frame_pose(self, state, name):
            assert name == 'panda-v1/ee'
            return torch.cat((eef, torch.zeros((4, 4))), dim=1)
        def joint_positions(self, state, names):
            return torch.stack((openings / 2, openings / 2), dim=1)

    binding = _DeviceTaskBinding(View(), (), 0, 0, (0.,) * 7, ((0., 1.), (0., 1.)), True)
    definition = PickCubeTaskDefinition(semantics, binding)
    state = SimpleNamespace(arrays={'body_position': cube[:, None, :]})
    actual = definition.evaluate_device(state=state, action=None, elapsed_steps=None)
    for row in range(4):
        expected = _evaluate_values(tuple(map(float, cube[row])), tuple(map(float, eef[row])),
                                    float(openings[row]), semantics)
        assert actual['reward'][row].item() == pytest.approx(expected.reward, abs=2e-6)
        assert bool(actual['terminated'][row]) == expected.success
        for key in ('reached_cube', 'grasped_cube', 'lifted_cube', 'task_success'):
            assert bool(actual['metrics'][key][row]) == expected.metrics[key]
        for key, value in expected.reward_terms.items():
            assert actual['reward_terms'][key][row].item() == pytest.approx(value, abs=2e-6)


def test_panda_canonical_scalar_and_device_observation_declarations_match():
    from task_env.robots.panda import PandaAgent

    robot = PandaAgent()
    env = SimpleNamespace(position_profile=False, dual_entity_position=False)
    scalar = robot.reference_observation_spaces(env, include_robot_state=True)
    device = robot.device_reference_observation_space().spaces
    assert set(scalar) == set(device) == {'ee_pose', 'joint_position', 'hand_pose'}
    for name in scalar:
        assert scalar[name].shape == device[name].shape
        assert scalar[name].dtype == device[name].dtype
    # The old Position profile is an explicit compatibility declaration.
    legacy = robot.reference_observation_spaces(
        SimpleNamespace(position_profile=True, dual_entity_position=False))
    assert legacy['boundary_identity_sha256'].shape == (32,)


def test_isaac_source_damping_is_explicit_and_rejects_unknown_passives():
    from task_env.robots.pendulum import PENDULUM_MJCF_XML
    from task_env.runtime.providers.isaac.batch import _declared_single_joint_damping

    source = SimpleNamespace(joints={'pendulum-v1/pendulum_hinge': 'pendulum_hinge'},
                             scene_source=SimpleNamespace(xml=PENDULUM_MJCF_XML))
    assert _declared_single_joint_damping(source) == .05
    source.scene_source.xml = PENDULUM_MJCF_XML.replace('damping="0.05"', 'damping="0.05" frictionloss="1"')
    with pytest.raises(ValueError, match='other passive'):
        _declared_single_joint_damping(source)
    source.scene_source.xml = PENDULUM_MJCF_XML.replace('<worldbody>', '<default/><worldbody>')
    with pytest.raises(ValueError, match='default inheritance'):
        _declared_single_joint_damping(source)


def test_device_session_close_retries_worker_after_partial_cleanup():
    from task_env.runtime.transport.device_batch_session import DevicePhysicalBatchSession

    class Worker:
        closed = False
        calls = 0
        def close(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError('worker close failed')
            self.closed = True

    class IPC:
        releases = 0
        closed = False
        def release_imports(self):
            self.releases += 1
        def close(self):
            self.closed = True

    session = object.__new__(DevicePhysicalBatchSession)
    session._closed = False
    session._worker, session._ipc = Worker(), IPC()
    session._last_state = session._device_limits = None
    worker, ipc = session._worker, session._ipc
    with pytest.raises(RuntimeError, match='worker close failed'):
        session.close()
    assert session._worker is worker and session._ipc is ipc and not ipc.closed
    session.close()
    assert worker.closed and ipc.closed and session._worker is None and session._ipc is None
    session.close()


def test_isaac_articulation_reads_inherited_passive_terms_and_joint_equality():
    from types import SimpleNamespace
    from task_env.runtime.providers.isaac.batch import _declared_articulation_dynamics

    xml = b'''<mujoco><default><joint damping="1" armature=".1"/></default>
      <worldbody><body><joint name="one" type="hinge"/><geom type="sphere" size=".1" mass="1"/>
      <body pos="0 0 .2"><joint name="two" type="hinge"/>
      <geom type="sphere" size=".1" mass="1"/></body></body></worldbody>
      <equality><joint joint1="one" joint2="two" polycoef="0 1 0 0 0"/></equality></mujoco>'''
    delivery = SimpleNamespace(source_entry_file='robot.xml')
    loaded = SimpleNamespace(delivery=delivery, source_input_bytes={'robot.xml': xml})
    source = SimpleNamespace(joints={'robot/one': 'one', 'robot/two': 'two'},
                             scene_source=SimpleNamespace(loaded_delivery=loaded))
    dynamics, equalities = _declared_articulation_dynamics(source)
    assert dynamics == {'one': {'damping': 1., 'armature': .1},
                        'two': {'damping': 1., 'armature': .1}}
    assert equalities == [('one', 'two')]
    loaded.source_input_bytes = {'robot.xml': xml.replace(b'armature=".1"', b'armature=".1" frictionloss=".2"')}
    with pytest.raises(ValueError, match='friction loss'):
        _declared_articulation_dynamics(source)


def test_free_body_velocity_mapping_matches_mujoco_with_rotated_offset_com():
    import mujoco
    import numpy as np
    import torch
    from task_env.runtime.providers.isaac.articulation_layout import _rotate

    model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody><body><freejoint/>
      <geom type="box" size=".1 .1 .1" pos=".2 0 0" mass="1"/>
      </body></worldbody></mujoco>''')
    data = mujoco.MjData(model)
    data.qpos[3:7] = [2**-.5, 2**-.5, 0., 0.]
    data.qvel[:] = [.3, -.1, .2, 0., 0., 1.]
    mujoco.mj_forward(model, data)
    reference = np.zeros(6)
    mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, 1, reference, 0)
    quat = torch.as_tensor(data.qpos[3:7], dtype=torch.float64).unsqueeze(0)
    angular = _rotate(quat, torch.as_tensor(data.qvel[3:6], dtype=torch.float64).unsqueeze(0))
    offset = _rotate(quat, torch.as_tensor(model.body_ipos[1], dtype=torch.float64).unsqueeze(0))
    origin_velocity = torch.as_tensor(data.qvel[:3], dtype=torch.float64).unsqueeze(0)
    com_velocity = origin_velocity + torch.linalg.cross(angular, offset)
    np.testing.assert_allclose(angular.numpy()[0], reference[:3], atol=1e-12)
    np.testing.assert_allclose(com_velocity.numpy()[0], reference[3:], atol=1e-12)


def test_panda_device_action_component_names_are_transmission_independent():
    from types import SimpleNamespace
    from task_env.robots.panda import PandaAgent

    arms = tuple(f'arm-effort-{index}' for index in range(1, 8))
    def controller(key, finger):
        return SimpleNamespace(profile=SimpleNamespace(action_key=key, action_names=arms + (finger,)))
    assert PandaAgent.device_effort_action_components(controller(None, 'finger-pair-effort')) == arms + ('finger-pair-effort',)
    assert PandaAgent.device_effort_action_components(controller('effort', 'finger-tendon-effort')) == arms + ('finger-pair-effort',)
    with pytest.raises(ValueError, match='declared effort'):
        PandaAgent.device_effort_action_components(controller('other', 'finger-pair-effort'))


def test_isaac_collision_capacity_covers_overlapping_clones():
    from task_env.runtime.providers.isaac.batch import _aggregate_pair_capacity

    shapes = 16 * 28
    capacity = _aggregate_pair_capacity(shapes, 1024)
    assert capacity >= shapes * (shapes - 1)
    assert capacity & (capacity - 1) == 0
    assert _aggregate_pair_capacity(1, 4096) >= 4096
    with pytest.raises(ValueError, match='integer range'):
        _aggregate_pair_capacity(100_000, 1024)
