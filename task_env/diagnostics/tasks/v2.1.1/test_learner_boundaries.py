"""Fresh-process learner imports and model-side data/space contracts."""
import importlib

import gymnasium as gym
import h5py
import numpy as np
import pytest


def test_learner_imports_do_not_start_simulators():
    for name in ('task_env.alg.agent_factory', 'task_env.alg.agent_factory.env.wrappers',
                 'task_env.alg.rsl_rl.adapter', 'task_env.script.rl.pendulum_ppo'):
        assert importlib.import_module(name)


def test_model_transform_reads_raw_tree_and_preserves_declared_order(tmp_path):
    from task_env.alg.agent_factory.env.model_transform import ModelTransformSpec, read_raw_h5_observation

    path = tmp_path / 'observation.h5'
    with h5py.File(path, 'w') as handle:
        state = handle.create_group('state')
        state.create_dataset('position', data=np.array([[1., 2.]], dtype=np.float32))
        rgb = handle.create_group('rgb')
        rgb.create_dataset('camera', data=np.full((1, 2, 3, 3), 255, dtype=np.uint8))
    with h5py.File(path, 'r') as handle:
        raw = read_raw_h5_observation(handle, 0)
    spec = ModelTransformSpec.from_env_meta({
        'meta_keys': {'obs': {'state': {'position': {}}, 'rgb': {'camera': {}}}},
        'observation_group_order': ['state', 'rgb'],
        'observation_schema': {'groups': {'rgb': {'leaves': {
            'camera': {'layout': 'HWC', 'semantic': 'rgb'}}}}},
    })
    assert spec.group_order == ('state', 'rgb')
    assert tuple(spec.tensor('state', 'position', raw['state']['position']).shape) == (2,)
    image = spec.tensor('rgb', 'camera', raw['rgb']['camera'])
    assert tuple(image.shape) == (3, 2, 3) and float(image.max()) == 1.0


def test_learner_space_contract_reads_component_shapes():
    from task_env.alg.contracts import LearnerTensorContract

    observation = gym.spaces.Box(-1, 1, shape=(3,), dtype=np.float32)
    action = gym.spaces.Box(-1, 1, shape=(2,), dtype=np.float32)
    contract = LearnerTensorContract.from_spaces(observation, action)
    assert contract is not None


@pytest.mark.parametrize('transfer_mode', ['host_numpy', 'device'])
def test_rsl_rejects_coordinated_device_before_reset_or_conversion(transfer_mode):
    from task_env.alg.rsl_rl.adapter import TaskEnvRslVecAdapter
    from task_env.vectorization.homogeneous import HomogeneousVectorTaskEnv

    class DeviceSpec:
        num_envs = 2
        single_action_space = gym.spaces.Box(-1, 1, shape=(1,), dtype=np.float32)
        single_observation_space = gym.spaces.Box(-1, 1, shape=(1,), dtype=np.float32)
        metadata = {'execution': 'local'}

    with pytest.raises(ValueError, match='coordinated device same-step autoreset'):
        TaskEnvRslVecAdapter(HomogeneousVectorTaskEnv(DeviceSpec(), execution_mode='device'),
                             transfer_mode=transfer_mode)


def test_rsl_legacy_device_transition_preserves_masked_autoreset():
    """The legacy device boundary remains admitted; CPU tensors model its contract."""
    from types import SimpleNamespace
    import torch
    from task_env.alg.rsl_rl.adapter import TaskEnvRslVecAdapter

    class LegacyDeviceEnv:
        num_envs, horizon, backend = 2, 5, 'cpu'
        metadata = {'execution': 'local'}
        single_observation_space = gym.spaces.Box(-10, 10, shape=(2,), dtype=np.float32)
        single_action_space = gym.spaces.Box(-1, 1, shape=(1,), dtype=np.float32)

        def __init__(self):
            self.masks = []

        def resource_summary(self):
            return {'device_transition': {'available': True, 'field_device': 'cpu'}}

        def reset(self, *, seed=None, mask=None):
            self.masks.append(None if mask is None else mask.copy())
            return np.zeros((2, 2), dtype=np.float32), [{}, {}]

        def step(self, actions):
            raise AssertionError('device transition must not use host step')

        def read_device_state(self):
            return None

        def reset_device(self):
            raise AssertionError('legacy masked reset uses the host reset boundary')

        def step_device(self, actions):
            self.actions = actions.clone()
            return SimpleNamespace(observation=torch.ones((2, 2)), reward=torch.tensor([1., 2.]),
                terminated=torch.tensor([False, False]), truncated=torch.tensor([False, True]),
                infos=[{}, {}])

        def close(self):
            pass

    raw = LegacyDeviceEnv()
    adapter = TaskEnvRslVecAdapter(raw, device='cpu', transfer_mode='device')
    _, rewards, dones, extras = adapter.step(torch.tensor([[2.], [-2.]]))
    assert raw.actions.tolist() == [[1.], [-1.]]
    assert rewards.tolist() == [1., 2.] and dones.tolist() == [False, True]
    assert extras['time_outs'].tolist() == [False, True]
    assert raw.masks[-1].tolist() == [False, True]
    assert extras['infos'][1]['terminal_observation'].tolist() == [1., 1.]
    adapter.close()
