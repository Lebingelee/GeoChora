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


@pytest.mark.parametrize(('uid', 'profile'), [
    ('pick-cube-p16-reference-v1', 'r3_continuous_v1'),
    ('nut-assembly-outcome-reference-v1', None),
    ('pendulum-v1', 'direct_joint_effort_v1'),
    ('two-wheel-balance-v1', 'direct_joint_effort_v1'),
])
def test_canonical_controller_profile_round_trips_through_yaml_and_resolved(uid, profile, tmp_path):
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(uid)
    values = {'execution': {'physics_provider': 'mujoco'}, 'controller': {'profile_id': profile}}
    yaml_path = tmp_path / 'config.yaml'
    yaml_path.write_text(yaml.safe_dump(values), encoding='utf-8')
    resolved = resolve_task_env_config(task, values)
    assert resolved == resolve_task_env_config(task, yaml_path)
    assert resolved == resolve_task_env_config(task, resolved)
    assert resolved.controller_profile == profile
    assert resolved.environment.control.profile_id == profile


@pytest.mark.parametrize('values', [
    {'controller_profile': 'r3_continuous_v1'},
    {'task': {'controller_profile': 'r3_continuous_v1'}},
    {'control': {'profile_id': 'r3_continuous_v1'}},
])
def test_retired_controller_selector_inputs_are_rejected(values):
    importlib.import_module('task_env.tasks')
    with pytest.raises((KeyError, ValueError), match='unsupported'):
        resolve_task_env_config(ENV_REGISTRY.get('pick-cube-p16-reference-v1'), values)


def test_reset_switch_preserves_canonical_controller_profile():
    from task_env.environment.reset_switch import prepare_switch_reset
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    current = resolve_task_env_config(task, {
        'execution': {'physics_provider': 'mujoco', 'reset_profile': 'pickcube-state-only-switch-v1'},
        'controller': {'profile_id': 'r3_continuous_v1'},
    })
    candidate = prepare_switch_reset(task, current, 17, None, {'physics_provider': 'geophys'})
    assert candidate.config.controller_profile == current.controller_profile
    assert candidate.config.physics_provider == 'geophys'
    assert candidate.task_seed == candidate.provider_seed == 17
