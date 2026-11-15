"""CPU tensor oracles for device lifecycle and shared Pendulum semantics."""
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import pytest
import torch

from task_env.runtime.contracts import DeviceBatchState, DeviceBatchTransition
from task_env.tasks.pendulum import PendulumTaskDefinition, PendulumTaskSemantics
from task_env.vectorization.homogeneous import HomogeneousVectorTaskEnv


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
    assert infos['final_observation']['state'][:, 0].tolist() == [2.]
    assert infos['final_episode_id'].tolist() == [1]
    assert infos['episode_id'].tolist() == [1, 2]
    assert truncated.tolist() == [False, True]
    assert reward.tolist() == [0., 1.] and not terminated.any()
    spec.values[1] = -3.
    assert infos['final_observation']['state'][:, 0].tolist() == [2.]
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
