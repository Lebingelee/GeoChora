"""Fresh-process learner imports and model-side data/space contracts."""
import importlib

import gymnasium as gym
import h5py
import numpy as np


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
