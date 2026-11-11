"""Provider-free configuration checks for the four formal v2.1.1 tasks."""

import importlib

import pytest
import yaml

from task_env.environment.configuration import resolve_task_env_config
from task_env.registry import ENV_REGISTRY


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_formal_mapping_and_yaml_share_execution_and_episode_semantics(uid, tmp_path):
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(uid)
    values = {'execution': {'physics_provider': 'mujoco'},
              'episode': {'horizon': 8, 'seed': 31, 'ignore_done': True}}
    path = tmp_path / 'task.yaml'
    path.write_text(yaml.safe_dump(values), encoding='utf-8')
    mapping = resolve_task_env_config(task, values)
    assert mapping == resolve_task_env_config(task, path)
    assert mapping == resolve_task_env_config(task, mapping)
    assert mapping.physics_provider == 'mujoco'
    assert mapping.environment.episode.horizon == 8
    assert mapping.environment.episode.seed == 31
    assert mapping.environment.episode.ignore_done is True
    assert mapping.environment.control.profile_id == mapping.controller_profile


@pytest.mark.parametrize('uid', ['pendulum-v1', 'two-wheel-balance-v1'])
def test_unavailable_damped_controller_route_rejects_before_construction(uid):
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='not admitted'):
        resolve_task_env_config(ENV_REGISTRY.get(uid), {
            'execution': {'physics_provider': 'geophys'},
            'controller': {'profile_id': 'velocity_damped_joint_effort_v1'},
        })
