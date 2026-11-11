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


@pytest.mark.parametrize('key', ['provider', 'backend', 'horizon', 'source_delivery_manifest'])
def test_retired_top_level_execution_inputs_are_rejected(key):
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='unsupported'):
        resolve_task_env_config(ENV_REGISTRY.get('pick-cube-p16-reference-v1'), {key: 'obsolete'})


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_environment_example_generates_formal_configuration(uid):
    from task_env.script.env._common import inline_config
    importlib.import_module('task_env.tasks')
    config = inline_config(uid, 'cpu', 8)
    resolved = resolve_task_env_config(ENV_REGISTRY.get(uid), config)
    assert resolved.physics_provider == 'geophys'
    assert resolved.environment.episode.horizon == 8


def test_builtin_harness_outputs_formal_controller_configuration(monkeypatch, tmp_path):
    from task_env.script.agent import catalog_query, harness_compiler
    from task_env.script.agent.builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1
    spec = BuiltinPickCubeExampleV1(
        'harness-builtin-pickcube-example-v1', 'pickcube-harness-example-v1',
        'pick-cube-p16-reference-v1', 'mujoco', 'cpu', 'cpu', 'r3_continuous_v1',
        (31, 32, 33), 8, .002, 5, None)
    scope = ExampleWorkingTreeScopeV1('harness-example-working-tree-scope-v1', ())
    repo = str(tmp_path.resolve())
    monkeypatch.setattr(catalog_query, 'core_context', lambda _: {'core_repo': repo, 'core_commit': 'test'})
    monkeypatch.setattr(harness_compiler, '_example_working_tree_context', lambda *_: {})
    monkeypatch.setattr('subprocess.check_output', lambda *args, **kwargs: '')
    catalog = {'schema_version': 'harness-catalog-v0', 'core_repo': repo, 'core_commit': 'test',
               'core_dirty': False, 'builtin_examples': {'pickcube-harness-example-v1': {'task_uid': spec.task_uid}},
               'env_uids': [spec.task_uid], 'providers': {'mujoco': {'available': True}}}
    config, _, _ = harness_compiler.resolve_builtin_pickcube_example(spec, catalog, working_tree_scope=scope)
    assert config['controller'] == {'profile_id': spec.controller_profile}
    importlib.import_module('task_env.tasks')
    assert resolve_task_env_config(ENV_REGISTRY.get(spec.task_uid), config).controller_profile == spec.controller_profile


def test_recorded_formal_configuration_reconstructs_controller_and_episode():
    from task_env.recorders.reference_provenance import recorded_execution_configuration
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    original = resolve_task_env_config(task, {
        'execution': {'physics_provider': 'mujoco'},
        'episode': {'horizon': 8, 'seed': 31, 'ignore_done': True},
        'controller': {'profile_id': 'r1_split'},
        'robot': {'uid': 'panda-arm-hand-v1'},
    })
    projected = recorded_execution_configuration(uid=task.uid, provider='mujoco', backend='cpu',
                                                  horizon=8, resolved=original)
    assert projected['controller']['profile_id'] == 'r1_split'
    assert 'controller_profile' not in projected['task']
    rebuilt = resolve_task_env_config(task, {k: v for k, v in projected.items() if k != 'env_id'})
    assert rebuilt.environment == original.environment
    assert rebuilt.controller_profile == original.controller_profile
    assert rebuilt.robot_uid == original.robot_uid
    assert rebuilt.execution_spec_v2 == original.execution_spec_v2


def test_recording_coordinator_serializes_typed_observation_schema():
    from task_env.environment.types import ObservationFieldSpec, ObservationSchema
    from task_env.recorders.reference_provenance import coordinator_receipt
    schema = ObservationSchema('test-observation-v1', (ObservationFieldSpec('state.joint', (1,)),))
    receipt = coordinator_receipt(step=0, time=0., artifact_hash='a' * 64,
        controller_identity='controller', solution_identity=None, provider='mujoco',
        execution_mode='external', task_outcome={'observation_schema': schema}, source_sha256='b' * 64)
    outcome = receipt['owners']['coordinator']['fields']['task_outcome']['value']
    assert outcome['observation_schema']['version'] == schema.version
    assert outcome['observation_schema']['fields'][0]['name'] == 'state.joint'
    assert len(receipt['integrity_hash']) == 64
