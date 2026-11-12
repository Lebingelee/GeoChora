"""Provider-free configuration checks for the four formal v2.1.1 tasks."""

import importlib

import pytest
import yaml

from task_env.environment.configuration import resolve_task_env_config
from task_env.registry import ENV_REGISTRY


@pytest.mark.parametrize(('uid', 'profile'), [
    ('pick-cube-p16-reference-v1', 'r3_continuous_v1'),
    ('pick-cube-p16-reference-v1', 'panda-direct-effort-v1'),
    ('nut-assembly-outcome-reference-v1', 'r3_continuous_v1'),
    ('pendulum-v1', 'direct_joint_effort_v1'),
    ('two-wheel-balance-v1', 'direct_joint_effort_v1'),
])
def test_formal_tasks_construct_from_common_request(uid, profile, monkeypatch):
    from task_env import make_env
    from task_env.environment import reference_binding

    requests = []
    request_type = reference_binding.TaskBuildRequest

    def record(*args):
        request = request_type(*args)
        requests.append(request)
        return request

    monkeypatch.setattr(reference_binding, 'TaskBuildRequest', record)
    env = make_env(uid, config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    try:
        assert len(requests) == 1
        request = requests[0]
        assert (request.provider, request.backend, request.horizon) == ('mujoco', 'cpu', 8)
        assert request.binding.robot.uid == env.robot.uid
        assert request.sampled_reset is None
    finally:
        env.close()


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
    ('nut-assembly-outcome-reference-v1', 'r3_continuous_v1'),
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


@pytest.mark.parametrize(('robot', 'profile'), [
    ('panda-v1', 'r1_split'),
    ('panda-arm-hand-v1', 'r3_continuous_v1'),
])
def test_controller_profile_must_be_declared_by_selected_robot(robot, profile):
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='does not declare Controller profile') as error:
        resolve_task_env_config(ENV_REGISTRY.get('pick-cube-p16-reference-v1'), {
            'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
            'robot': {'uid': robot}, 'controller': {'profile_id': profile},
        })
    assert error.value.phase == 'static_config'


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


@pytest.mark.parametrize('uid', ['nut-assembly-outcome-reference-v1', 'pendulum-v1', 'two-wheel-balance-v1'])
def test_task_rejects_an_undeclared_reset_profile(uid):
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='unsupported task reset profile'):
        resolve_task_env_config(ENV_REGISTRY.get(uid), {
            'execution': {'physics_provider': 'mujoco', 'reset_profile': 'pickcube-state-only-switch-v1'},
        })


@pytest.mark.parametrize('controller', [
    {'profile_id': 'r1'},
    {'profile_id': 'r3_continuous_v1', 'gravity_compensation': True},
])
def test_pickcube_reset_profile_requires_its_declared_controller(controller):
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='reset profile requires PickCube R3'):
        resolve_task_env_config(ENV_REGISTRY.get('pick-cube-p16-reference-v1'), {
            'execution': {'physics_provider': 'mujoco', 'reset_profile': 'pickcube-state-only-switch-v1',
                          'deployment': 'in_process'},
            'controller': controller,
        })


@pytest.mark.parametrize('uid,robot', [
    ('pendulum-v1', None),
    ('two-wheel-balance-v1', None),
    ('pick-cube-p16-reference-v1', 'panda-arm-hand-v1'),
])
def test_gravity_compensation_requires_robot_capability(uid, robot):
    importlib.import_module('task_env.tasks')
    config = {'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
              'controller': {'gravity_compensation': True}}
    if robot:
        config['robot'] = {'uid': robot}
        config['controller']['profile_id'] = 'r1'
    with pytest.raises(ValueError, match='selected Robot does not declare'):
        resolve_task_env_config(ENV_REGISTRY.get(uid), config)


@pytest.mark.parametrize('uid', ['pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'])
def test_panda_declares_gravity_compensation_for_formal_tabletop_tasks(uid):
    importlib.import_module('task_env.tasks')
    resolved = resolve_task_env_config(ENV_REGISTRY.get(uid), {
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'gravity_compensation': True},
    })
    assert resolved.gravity_compensation is True


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


@pytest.mark.parametrize('uid', ['pickcube-physical-candidate-v1', 'pickcube-isaac-physical-candidate-v1'])
def test_formal_registry_rejects_retired_physical_diagnostic_uids(uid):
    importlib.import_module('task_env.tasks')
    with pytest.raises(KeyError):
        ENV_REGISTRY.get(uid)


@pytest.mark.parametrize(('task_uid', 'robot_uid'), [
    ('pick-cube-p16-reference-v1', 'panda-v1'),
    ('nut-assembly-outcome-reference-v1', 'panda-v1'),
    ('pendulum-v1', 'pendulum-v1'),
    ('two-wheel-balance-v1', 'two-wheel-balance-v1'),
])
def test_formal_tasks_resolve_robot_through_shared_registry(task_uid, robot_uid):
    from task_env import make_agent
    from task_env.environment.protocols import RobotComponent
    importlib.import_module('task_env.tasks')
    robot = make_agent(robot_uid)
    assert isinstance(robot, RobotComponent) and robot.uid == robot_uid
    config = resolve_task_env_config(ENV_REGISTRY.get(task_uid), {'robot': {'uid': robot_uid}})
    assert config.robot_uid == robot_uid
    assert resolve_task_env_config(ENV_REGISTRY.get(task_uid), config) == config


def test_robot_choice_rejects_a_different_task_subject():
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='does not admit'):
        resolve_task_env_config(ENV_REGISTRY.get('pendulum-v1'), {'robot': {'uid': 'panda-v1'}})


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_formal_configuration_rejects_diagnostic_source_workspace(uid):
    importlib.import_module('task_env.tasks')
    with pytest.raises(KeyError, match='source_workspace'):
        resolve_task_env_config(ENV_REGISTRY.get(uid), {'execution': {'source_workspace': '/tmp/old-source'}})


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_formal_construction_rejects_old_component_resolved_config(uid):
    from task_env.environment.configuration import resolve_env_config
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(uid)
    old = resolve_env_config(task_uid=uid, scene_uid='tabletop-v1')
    with pytest.raises(TypeError, match='mapping or YAML'):
        task.from_resolved_config(old)


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_make_env_resolves_public_config_once(uid, monkeypatch):
    import sys
    import task_env.environment.configuration as configuration
    from task_env import make_env

    calls = []
    resolve = configuration.resolve_task_env_config
    def counted(task, value):
        calls.append((task.uid, value))
        return resolve(task, value)
    monkeypatch.setattr(configuration, 'resolve_task_env_config', counted)
    config = {'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                            'physics_device': 'cpu', 'deployment': 'in_process',
                            'interpreter': sys.executable}, 'episode': {'horizon': 8}}
    env = make_env(uid, config=config)
    try:
        assert calls == [(uid, config)]
        assert env.resolved_public_config.task_uid == uid
    finally:
        env.close()


def test_formal_constructor_revalidates_supplied_resolved_config():
    from dataclasses import replace
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get('pendulum-v1')
    resolved = resolve_task_env_config(task, {'execution': {'physics_provider': 'mujoco'}})
    forged_runtime = replace(resolved.environment.runtime, physics_dt=0.123)
    forged = replace(resolved, environment=replace(resolved.environment, runtime=forged_runtime))
    with pytest.raises(ValueError, match='unsupported overrides'):
        task.from_resolved_config(forged)


@pytest.mark.parametrize(('uid', 'robot_uid'), [
    ('pick-cube-p16-reference-v1', 'panda-v1'),
    ('nut-assembly-outcome-reference-v1', 'panda-v1'),
    ('pendulum-v1', 'pendulum-v1'),
    ('two-wheel-balance-v1', 'two-wheel-balance-v1'),
])
def test_default_robot_is_resolved_once_and_matches_explicit_selection(uid, robot_uid):
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(uid)
    default = resolve_task_env_config(task, {})
    explicit = resolve_task_env_config(task, {'robot': {'uid': robot_uid}})
    assert default.robot_uid == robot_uid
    assert default == explicit
    assert resolve_task_env_config(task, default) == default


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_formal_controller_profile_cannot_be_null(uid):
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='unsupported selected controller profile'):
        resolve_task_env_config(ENV_REGISTRY.get(uid), {'controller': {'profile_id': None}})


def test_solution_diagnostic_alias_is_not_a_controller_profile():
    importlib.import_module('task_env.tasks')
    with pytest.raises(ValueError, match='unsupported selected controller profile'):
        resolve_task_env_config(ENV_REGISTRY.get('pick-cube-p16-reference-v1'), {
            'controller': {'profile_id': 'r3_continuous_v1_pose_path_x20'},
        })


def test_resolved_controller_profile_has_one_owner():
    from dataclasses import asdict, replace
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    resolved = resolve_task_env_config(task, {'controller': {'profile_id': 'r1'}})
    assert 'controller_profile' not in asdict(resolved)
    assert asdict(resolved)['environment']['control']['profile_id'] == 'r1'
    changed = replace(resolved, environment=replace(
        resolved.environment, control=replace(resolved.environment.control, profile_id='r3_continuous_v1')))
    assert changed.controller_profile == 'r3_continuous_v1'
    assert resolve_task_env_config(task, changed) == changed


def test_execution_selection_has_one_owner():
    from dataclasses import asdict, replace
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get('pendulum-v1')
    resolved = resolve_task_env_config(task, {'execution': {'physics_provider': 'mujoco'}})
    data = asdict(resolved)
    assert not {'physics_provider', 'physics_device', 'render_default'} & data.keys()
    assert resolved.physics_provider == resolved.execution_spec_v2.physics_provider == 'mujoco'
    assert resolved.physics_device == resolved.execution_spec_v2.physics_device == 'cpu'
    assert resolved.render_default == resolved.execution_spec_v2.render_default
    with pytest.raises(TypeError, match='must be ExecutionSpecV2'):
        replace(resolved, execution_spec_v2=None)


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_formal_class_does_not_enter_component_construction(uid):
    from task_env.environment.configuration import resolve_env_config
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(uid)
    old = resolve_env_config(task_uid=uid, scene_uid='tabletop-v1')
    with pytest.raises(TypeError, match='through make_env'):
        task(config=old, build_runtime=False)
    with pytest.raises(TypeError, match='through make_env'):
        task()


@pytest.mark.parametrize('uid', ['pendulum-v1', 'two-wheel-balance-v1'])
def test_legacy_parallel_factory_is_not_advertised_for_formal_tasks(uid):
    from task_env.vectorization.registry import PARALLEL_ENV_REGISTRY

    importlib.import_module('task_env.tasks')
    assert not PARALLEL_ENV_REGISTRY.contains(uid)


@pytest.mark.parametrize('uid', ['pendulum-v1', 'two-wheel-balance-v1'])
@pytest.mark.parametrize('profile', ['direct_joint_effort_v1', 'velocity_damped_joint_effort_v1'])
def test_formal_effort_action_space_comes_from_compiled_controller(uid, profile):
    from dataclasses import replace
    import sys
    from task_env import make_env

    env = make_env(uid, config={
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                      'deployment': 'in_process', 'interpreter': sys.executable},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    try:
        physical = env.value['physical_execution']
        assert env.binding.action_space_factory.__self__ is physical
        assert env.action_space == physical.action_space()
        invalid = replace(env.binding.external_action_contract, high=env.binding.external_action_contract.high / 2)
        with pytest.raises(ValueError, match='bounds or units'):
            replace(env.binding, external_action_contract=invalid).bind_compiled_control(env.value)
    finally:
        env.close()


@pytest.mark.parametrize(('uid', 'robot_type'), [
    ('pendulum-v1', 'PendulumEntity'),
    ('two-wheel-balance-v1', 'TwoWheelBalanceEntity'),
])
def test_formal_effort_task_consumes_selected_robot_action_declaration(uid, robot_type, monkeypatch):
    from dataclasses import replace
    import sys
    from task_env import make_env
    from task_env import robots

    cls = getattr(robots, robot_type)
    declared = replace(cls.action_contract, schema_id='robot-declared-effort-action-v1')
    monkeypatch.setattr(cls, 'action_contract', declared)
    env = make_env(uid, config={
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                      'deployment': 'in_process', 'interpreter': sys.executable},
        'episode': {'horizon': 8},
    })
    try:
        assert env.binding.external_action_contract is env.binding.robot.action_contract is declared
        assert env.binding.action_schema['schema_id'] == declared.schema_id
        assert env.binding.action_space_factory.__self__ is env.value['physical_execution']
    finally:
        env.close()

@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_all_formal_tasks_resolve_defaults_from_one_task_configuration(uid, monkeypatch):
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(uid)
    source = task.selected_task_configuration()
    default_config = task.selected_default_config
    default_controller = task.selected_default_controller_profile
    calls = []

    def configured(source_config):
        calls.append(('environment', source_config))
        return default_config(source_config)

    def controller(source_config):
        calls.append(('controller', source_config))
        return default_controller(source_config)

    monkeypatch.setattr(task, 'selected_task_configuration', staticmethod(lambda: source))
    monkeypatch.setattr(task, 'selected_default_config', configured)
    monkeypatch.setattr(task, 'selected_default_controller_profile', controller)
    resolved = resolve_task_env_config(task, {'execution': {'physics_provider': 'mujoco'}})
    assert calls == [('environment', source), ('controller', source)]
    assert resolved.environment.control.profile_id == default_controller(source)


@pytest.mark.parametrize('uid', ['pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'])
def test_tabletop_execution_defaults_preserve_class_yaml_caller_precedence(uid, monkeypatch):
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(uid)
    data = dict(task.selected_task_configuration())
    data['execution'] = {'physics_provider': 'mujoco'}
    monkeypatch.setattr(task, 'selected_task_configuration', staticmethod(lambda: data))
    monkeypatch.setattr(task, 'selected_execution_defaults', {'physics_provider': 'geophys'})
    assert resolve_task_env_config(task, None).physics_provider == 'mujoco'
    assert resolve_task_env_config(task, {'execution': {'physics_provider': 'geophys'}}).physics_provider == 'geophys'


def test_panda_effort_configuration_does_not_load_candidate_builders():
    import subprocess
    import sys

    script = '''
import sys
from task_env.environment.configuration import resolve_task_env_config
from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
resolved = resolve_task_env_config(PickCubeReferenceEnv, {
    'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
    'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
})
assert resolved.controller_profile == 'panda-joint-effort-reference-v1'
assert 'task_env.tasks.pick_cube.physical_candidate' not in sys.modules
assert 'task_env.tasks.pick_cube.physical_isaac_candidate' not in sys.modules
'''
    subprocess.run([sys.executable, '-c', script], check=True)


def test_effort_reset_selection_rejects_provider_without_its_source_capability():
    import sys
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    with pytest.raises(ValueError, match='reset selection requires an isolated MuJoCo'):
        resolve_task_env_config(PickCubeReferenceEnv, {
            'execution': {'physics_provider': 'geophys', 'deployment': 'in_process',
                          'interpreter': sys.executable},
            'controller': {'profile_id': 'panda-joint-effort-reference-v1',
                           'parameters': {'reset_selection': True}},
        })
