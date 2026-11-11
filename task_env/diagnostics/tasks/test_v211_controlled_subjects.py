"""Provider-free tests for source-bound subjects on the production control owner."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.artifacts.state import StateRequirements
from task_env.artifacts import FrameReference
from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.runtime.sessions.physical_control import (
    ControlledSubjectV1, PhysicalControlExecutionV1, validate_controlled_subjects,
)


def test_isaac_binding_compiles_once_in_shared_construction_and_rebuilds_on_reset(monkeypatch):
    from task_env.tasks.pick_cube import physical_isaac_candidate as candidate
    from task_env.tasks.pick_cube import physical_usd_profile, specialization
    builds = []
    def build_reference(**kwargs):
        value = {'source': SimpleNamespace(scene_definition=object()),
                 'artifact': object(), 'controller': object(),
                 'reset_plan': SimpleNamespace(reset_sample=object())}
        builds.append((kwargs, value))
        return value
    controller = SimpleNamespace(identity='physical-controller', action_shape=(8,))
    physical = SimpleNamespace(controllers=(controller,), action_space=lambda: 'space')
    monkeypatch.setattr(specialization, 'build_isaac_reference', build_reference)
    monkeypatch.setattr(physical_usd_profile, 'build_f06_direct_effort_execution',
                        lambda *_args: physical)
    binding = candidate.make_isaac_physical_binding(delivery_manifest='/source.json',
        seed=47, horizon=8, drive_mode='coexist', control_kind='direct')
    assert builds == [] and binding.action_schema is None
    policy = binding.reset_reconstruction_strategy('isaacsim', 'cuda', 8)
    initial = policy.initial(seed=47)
    assert len(builds) == 1 and initial['source'] is builds[0][1]['source']
    assert initial['physical_execution'] is physical
    rebuilt = policy.build_reset(initial, 47, None)
    assert len(builds) == 2 and rebuilt['source'] is builds[1][1]['source']
    assert rebuilt['source'] is not initial['source']
    with pytest.raises(ValueError, match='frozen execution'):
        policy.initial(seed=48)
    assert len(builds) == 2


def test_compiled_physical_contract_reuses_actual_controller_and_preserves_extensions():
    from task_env import make_env
    env = make_env('pick-cube-p16-reference-v1', config={
        'provider': 'mujoco', 'controller': {'profile_id': 'panda-direct-effort-v1'}})
    try:
        execution = env.value['physical_execution']
        assert env.binding.action_space_factory.__self__ is execution
        assert env.binding.action_schema == execution.action_schema()
        deferred = replace(env.binding, action_schema=None, action_space_factory=None)
        resolved = deferred.bind_compiled_control(env.value)
        assert resolved.action_schema == env.binding.action_schema
        assert resolved.action_space_factory.__self__ is execution
        with pytest.raises(ValueError, match='requires its execution'):
            deferred.bind_compiled_control({})
        extended = replace(env.binding, action_schema={**env.binding.action_schema,
            'position_physical_action': 'position-physical-action-v1'})
        bound = extended.bind_compiled_control(env.value)
        assert bound.action_schema['position_physical_action'] == 'position-physical-action-v1'
        assert bound.action_space_factory.__self__ is execution
        assert env.metadata['action_schema'] == execution.action_schema()
    finally:
        env.close()


def test_solution_info_payload_preserves_typed_gym_schema_and_nonfinite_rejection():
    from types import MappingProxyType
    from task_env.environment import ObservationSchema, ObservationFieldSpec
    from task_env.environment.metadata import task_info_for_solution
    from task_env.tasks.nut_assembly.solution import NutAssemblyOutcomeSolutionV1
    schema = ObservationSchema('task-state-v1', (
        ObservationFieldSpec('state.angle', (1,), 'float32'),))
    info = {'observation_schema': schema,
            'task_metrics': MappingProxyType({'height_m': .3}),
            'reward_terms': MappingProxyType({'reach': .1})}
    payload = task_info_for_solution(info)
    assert info['observation_schema'] is schema
    assert isinstance(info['task_metrics'], MappingProxyType)
    assert payload['observation_schema']['version'] == schema.version
    assert payload['task_metrics'] == {'height_m': .3}
    assert NutAssemblyOutcomeSolutionV1._finite(payload)
    invalid = {**info, 'task_metrics': MappingProxyType({'height_m': float('nan')})}
    assert not NutAssemblyOutcomeSolutionV1._finite(task_info_for_solution(invalid))


def test_admitted_legacy_interval_binds_declared_snapshot_and_rejects_wrong_closure():
    from task_env import make_env
    from task_env.runtime.sessions.legacy_native_feedback_binding import install_admitted_binding
    env = make_env('nut-assembly-outcome-reference-v1', config={'provider': 'mujoco'})
    try:
        source = env.value['source']
        session = SimpleNamespace(_source=source, _artifact=env.artifact,
                                  provider_materialization_id='test-materialization')
        install_admitted_binding(session, source=source, artifact=env.artifact, controller=env.controller)
        bound = session._legacy_native_feedback_binding
        assert bound.source_closure_sha256 == source.source_closure_digest
        assert bound._source is source and bound._controller is env.controller
        bound.validate_live(session)
        bad_source = SimpleNamespace(**{**vars(source), 'source_closure_digest': 'f' * 64})
        bad_session = SimpleNamespace(_source=bad_source, _artifact=env.artifact,
                                      provider_materialization_id='test-materialization')
        with pytest.raises(ValueError, match='admitted source receipt'):
            install_admitted_binding(bad_session, source=bad_source,
                                     artifact=env.artifact, controller=env.controller)
    finally:
        env.close()


@pytest.mark.parametrize('uid,config', [
    ('pick-cube-p16-reference-v1', {'controller': {'profile_id': 'r1'}}),
    ('pick-cube-p16-reference-v1', {'controller': {'profile_id': 'r3_continuous_v1'},
                                  'task': {'lift_height_m': .08}}),
    ('nut-assembly-outcome-reference-v1', {'task': {'lift_height_m': .07}})])
def test_formal_task_definition_owns_evaluation_with_exact_reward_oracle(uid, config):
    from task_env import make_env
    from task_env.artifacts import CanonicalStateView, PoseWorld
    from task_env.environment import CanonicalTaskStateView, TaskDefinitionBase, as_task_state_view
    from task_env.tasks.pick_cube import task as pick
    from task_env.tasks.nut_assembly import task as nut
    env = make_env(uid, config={'provider': 'mujoco', **config})
    try:
        definition = env._task_definition
        assert isinstance(definition, TaskDefinitionBase)
        assert env._task_lifecycle.task_definition is definition
        assert definition.semantics is env.artifact.semantics
        module = pick if uid.startswith('pick-cube') else nut
        joints = dict(env.artifact.initialization.joint_position)
        poses = {name: env.artifact.initialization.poses_world.get(
            name, PoseWorld((.51, .02, .43), (1., 0., 0., 0.)))
            for name in env.artifact.semantics.required_poses}
        def forbidden_legacy_evaluator(*_args):
            raise AssertionError('formal observation bypassed TaskDefinition lifecycle')
        env.binding = replace(env.binding, evaluate=forbidden_legacy_evaluator)
        for index in range(7):
            joints['panda-v1/finger_joint1'] = .003 + index * .005
            joints['panda-v1/finger_joint2'] = .004 + index * .004
            state = CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz',
                index, index * env.artifact.timebase.control_dt, dict(joints),
                {name: 0. for name in joints}, poses)
            view = as_task_state_view(state)
            assert isinstance(view, CanonicalTaskStateView) and view.canonical_state is state
            assert as_task_state_view(view) is view and not hasattr(view, 'qpos')
            expected = module.evaluate(state, env.artifact.semantics,
                lift_height_m=config.get('task', {}).get('lift_height_m'))
            _obs, _info, actual = env.observation(state)
            assert actual.reward.hex() == expected.reward.hex()
            assert actual.success == expected.success and actual.failure == expected.failure
            assert dict(actual.metrics) == dict(expected.metrics)
            assert dict(actual.reward_terms) == dict(expected.reward_terms)
        metadata = env.get_record_metadata()
        assert 'universal_action_schema' not in metadata
    finally:
        env.close()


@pytest.mark.parametrize('early_failure', [False, True])
def test_common_construction_compiles_once_with_declared_seed_and_cleans_failure(early_failure):
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.environment.reference_binding import ReferenceTaskBinding
    calls = []
    receipt = SimpleNamespace(close=lambda: calls.append('source-close'))
    value = {'execution_spec_v1': None, 'source': SimpleNamespace(execution_source_receipt=receipt)}
    def compile_seeded(provider, backend, seed, horizon):
        calls.append((provider, backend, seed, horizon))
        return value
    class DeclaredEnv(SelectedReferenceEnv):
        def _initialize_selected_value(self, **kwargs):
            calls.append(self.value)
            raise RuntimeError('constructor rejected declaration')
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    binding = replace(PickCubeReferenceEnv.binding, build=lambda _: value, build_seeded=compile_seeded,
        close_task_resources=lambda: calls.append('task-close'))
    horizon = 0 if early_failure else 8
    with pytest.raises(ValueError if early_failure else RuntimeError,
                       match='horizon' if early_failure else 'constructor rejected'):
        DeclaredEnv.from_task_binding(binding, provider='mujoco', backend='cpu', horizon=horizon, seed=47)
    expected = [('mujoco', 'cpu', 47, horizon)] + ([] if early_failure else [value])
    assert calls == [*expected, 'source-close', 'task-close']


@pytest.mark.parametrize('kind', ['direct', 'joint', 'r3-pose', 'joint-mass', 'r3-mass-pose'])
def test_legacy_isaac_input_translates_to_formal_owner(monkeypatch, kind):
    from task_env.tasks.pick_cube.physical_isaac_candidate import PickCubeIsaacPhysicalCandidateEnv
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    from task_env.tasks.pick_cube.physical_candidate import PICKCUBE_PHYSICAL_PROFILES
    captured = []
    monkeypatch.setattr(PickCubeReferenceEnv, 'from_reference_config',
        classmethod(lambda cls, config, **kwargs: captured.append((cls, config, kwargs)) or 'formal-env'))
    assert PickCubeIsaacPhysicalCandidateEnv.from_reference_config({
        'delivery_manifest': '/explicit/source.json', 'control_kind': kind,
        'drive_mode': 'effort-only', 'seed': 47}) == 'formal-env'
    cls, config, kwargs = captured.pop()
    assert cls is PickCubeReferenceEnv and kwargs == {'render_mode': None}
    assert PICKCUBE_PHYSICAL_PROFILES[config['controller']['profile_id']] == kind
    assert config['episode'] == {'seed': 47, 'horizon': 8}
    assert config['robot']['native_drive'] == 'disabled'
    assert config['execution']['source_delivery_manifest'] == '/explicit/source.json'


@pytest.mark.parametrize('already_open', [False, True])
def test_isaac_preparation_preserves_existing_app_and_primary_failure(monkeypatch, already_open):
    from task_env.runtime.sessions import isaac_native_io as native
    calls = []
    def close():
        calls.append('close')
        raise OSError('close failed')
    owner = SimpleNamespace(app=object() if already_open else None,
        open=lambda **kwargs: calls.append(('open', kwargs)), close=close)
    monkeypatch.setattr(native, '_process_app_owner', lambda **kwargs: owner)
    with pytest.raises(RuntimeError, match='source failed') as error:
        with native.prepare_isaac_source(rendering=True):
            calls.append('source')
            raise RuntimeError('source failed')
    assert calls[:2] == [('open', {'f06_compatibility': True}), 'source']
    assert ('close' in calls) is not already_open
    if not already_open:
        assert 'close failed' in error.value.__notes__[0]


@pytest.mark.parametrize('seed', [None, True])
def test_legacy_isaac_preserves_strict_frozen_seed_rejection(seed):
    from task_env.tasks.pick_cube.physical_isaac_candidate import PickCubeIsaacPhysicalCandidateEnv
    with pytest.raises(ValueError, match='frozen seed'):
        PickCubeIsaacPhysicalCandidateEnv.from_reference_config({
            'delivery_manifest': '/explicit/source.json', 'seed': seed})


@pytest.mark.parametrize('profile', [
    'panda-direct-effort-v1', 'panda-joint-effort-reference-v1', 'panda-r3-effort-reference-v1',
    'panda-joint-mass-effort-v1', 'panda-r3-mass-effort-v1'])
def test_isaac_physical_configuration_roundtrip_and_source_limits(profile):
    import sys
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    config = {'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
        'physics_device': 'cuda:0', 'source_delivery_manifest': '/explicit/source.json',
        'deployment': 'in_process', 'interpreter': sys.executable},
        'controller': {'profile_id': profile}, 'episode': {'seed': 47, 'horizon': 8}}
    resolved = resolve_task_env_config(PickCubeReferenceEnv, config)
    assert resolved == resolve_task_env_config(PickCubeReferenceEnv, resolved)
    assert resolved.environment.episode.seed == 47
    assert resolved.controller_profile == profile
    for invalid in ({'episode': {'horizon': 1001}},
                    {'controller': {'profile_id': profile, 'parameters': {'reset_selection': True}}},
                    {'execution': {**config['execution'], 'source_workspace': '/unused'}}):
        with pytest.raises(ValueError, match='Isaac physical'):
            resolve_task_env_config(PickCubeReferenceEnv, {**config, **invalid})


@pytest.mark.parametrize('uid', ['pendulum-v1', 'two-wheel-balance-v1'])
def test_formal_task_config_uses_shared_construction_and_owned_definition(monkeypatch, tmp_path, uid):
    import yaml
    from task_env import make_env
    from task_env.registry import ENV_REGISTRY
    from task_env.environment.lifecycle import TaskLifecycleAdapter
    from task_env.environment.configuration import resolve_task_env_config
    import task_env.tasks

    task = ENV_REGISTRY.get(uid)
    def forbidden_legacy_factory(*args, **kwargs):
        raise AssertionError('formal caller re-entered legacy environment construction')
    monkeypatch.setattr(task, 'from_reference_config', forbidden_legacy_factory)
    values = {'runtime': {'backend': 'cpu'}, 'episode': {'horizon': 8},
              'controller': {'profile_id': 'velocity_damped_joint_effort_v1'}}
    path = tmp_path / 'task.yaml'
    path.write_text(yaml.safe_dump(values))
    first = make_env(uid, config=values, provider='mujoco', backend='cpu')
    second = make_env(uid, config=path, provider='mujoco', backend='cpu')
    try:
        assert first.config == second.config == resolve_task_env_config(task, values)
        assert isinstance(first._task_lifecycle, TaskLifecycleAdapter)
        assert first._task_lifecycle.task_definition is first._task_definition
        assert first._task_definition is not second._task_definition
        assert first.controller.profile_id == second.controller.profile_id == 'velocity_damped_joint_effort_v1'
        assert first.session is None and second.session is None
        assert first.get_record_metadata()['universal_action_schema']['components'] == first.binding.action_schema['components']
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize('uid', ['pendulum-v1', 'two-wheel-balance-v1'])
def test_invalid_task_camera_rejects_before_source_or_isaac_owner(monkeypatch, uid):
    from task_env import make_env
    from task_env.registry import ENV_REGISTRY
    from task_env.environment.config import CameraSpec
    import task_env.tasks

    def forbidden_binding(*args, **kwargs):
        raise AssertionError('invalid camera reached task/source construction')
    monkeypatch.setattr(ENV_REGISTRY.get(uid), 'selected_binding', forbidden_binding)
    with pytest.raises(ValueError, match='finite world CameraSpec'):
        make_env(uid, config={'runtime': {'backend': 'cuda'}}, provider='isaacsim', backend='cuda',
            source_delivery_manifest='never-read.json',
            task_rgb_camera=CameraSpec(name='task', quaternion_wxyz=(0., 0., 0., 0.), depth=False),
            task_renderer='isaacsim')


def test_physical_task_rejects_foreign_resolved_identity_before_binding(monkeypatch):
    from task_env.tasks.pendulum import PendulumEnv
    from task_env.tasks.two_wheel_balance import TwoWheelBalanceEnv
    def forbidden_binding(*args, **kwargs):
        raise AssertionError('foreign Task identity reached source construction')
    monkeypatch.setattr(PendulumEnv, 'selected_binding', forbidden_binding)
    with pytest.raises(ValueError, match='declared Task identity'):
        PendulumEnv.from_resolved_config(TwoWheelBalanceEnv.default_config(), provider='mujoco')


def test_legacy_class_binding_preserves_scalar_factory_input(monkeypatch):
    from task_env import make_env
    from task_env.registry import ENV_REGISTRY
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    class LegacyTask(SelectedReferenceEnv):
        uid = 'legacy-class-binding-example'
        binding = PickCubeReferenceEnv.binding
    monkeypatch.setattr(ENV_REGISTRY, 'get', lambda _uid: LegacyTask)
    env = make_env(LegacyTask.uid, config={'provider': 'mujoco', 'backend': 'cpu', 'horizon': 8})
    try:
        assert not env._has_component_assembly()
        assert (env.provider, env.backend, env.horizon) == ('mujoco', 'cpu', 8)
        assert env.binding is LegacyTask.binding
        assert env.session is None
    finally:
        env.close()


@pytest.mark.parametrize('profile', [
    'panda-direct-effort-v1', 'panda-joint-effort-reference-v1', 'panda-r3-effort-reference-v1',
    'panda-joint-mass-effort-v1', 'panda-r3-mass-effort-v1',
])
def test_formal_physical_profiles_own_source_and_preserve_compiled_control(tmp_path, profile):
    import yaml
    from task_env import make_env
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    config = {'provider': 'mujoco', 'controller': {'profile_id': profile},
              'episode': {'seed': 31, 'horizon': 8}}
    path = tmp_path / 'physical.yaml'
    path.write_text(yaml.safe_dump(config))
    resolved = resolve_task_env_config(PickCubeReferenceEnv, config)
    assert resolved == resolve_task_env_config(PickCubeReferenceEnv, path)
    assert resolved == resolve_task_env_config(PickCubeReferenceEnv, resolved)
    env = make_env(PickCubeReferenceEnv.uid, config=path)
    root = env.value['source'].scene_source.base_dir
    try:
        execution = env.value['physical_execution']
        assert env.robot.subjects is execution.subjects
        assert env.robot.controllers is execution.controllers
        assert env.binding.physical_control_profile(env) is execution
        assert env.resolved_public_config == resolved
        assert env.resolved_public_config.source_workspace is None
        assert env.session is None and root.is_dir()
        if profile in {'panda-r3-effort-reference-v1', 'panda-r3-mass-effort-v1'}:
            assert not callable(getattr(execution.controllers[0], 'bind_model', None))
        from task_env.runtime.sessions.api import assess_selected_request
        arguments = dict(selection=resolved.execution_spec_v2, artifact=env.artifact,
            source=env.value['source'], value=env.value, dependency_status='available',
            request_identity='a' * 64)
        assessment = assess_selected_request(binding=env.binding, **arguments)
        assert assessment.decision != 'rejected', assessment.to_mapping()
        refused = assess_selected_request(binding=replace(env.binding, physical_control_profile=None), **arguments)
        assert refused.decision == 'rejected'
    finally:
        env.close()
    assert not root.exists()


def test_legacy_physical_uid_uses_formal_factory_and_preserves_caller_copy(tmp_path):
    from task_env import make_env
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    root = tmp_path / 'explicit-source'
    env = make_env('pickcube-physical-candidate-v1', config={'source_workspace': root})
    try:
        assert type(env) is PickCubeReferenceEnv
        assert env.uid == PickCubeReferenceEnv.uid
        assert env.value['source'].scene_source.base_dir == root / 'source-snapshot'
        assert env.resolved_public_config.source_workspace == str(root)
    finally:
        env.close()
    assert (root / 'source-snapshot').is_dir()


def test_formal_physical_construction_failure_releases_owned_source(monkeypatch):
    from task_env import make_env
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import mujoco_composition
    paths = []
    original = mujoco_composition.bind_reference_scene_source
    def capture_source(*args, **kwargs):
        value = original(*args, **kwargs)
        paths.append(value[0].scene_source.base_dir)
        return value
    def fail_initialization(*args, **kwargs):
        raise RuntimeError('injected declaration initialization failure')
    monkeypatch.setattr(mujoco_composition, 'bind_reference_scene_source', capture_source)
    monkeypatch.setattr(SelectedReferenceEnv, '_initialize_selected_value', fail_initialization)
    with pytest.raises(RuntimeError, match='declaration initialization failure'):
        make_env('pick-cube-p16-reference-v1', config={
            'provider': 'mujoco', 'controller': {'profile_id': 'panda-direct-effort-v1'}})
    assert paths and all(not path.exists() for path in paths)


def test_dynamic_r3_composition_keeps_its_source_model_binding():
    from task_env import make_env
    env = make_env('pick-cube-p16-reference-v1', config={'provider': 'mujoco',
        'controller': {'profile_id': 'panda-r3-effort-reference-v1',
                       'parameters': {'reset_selection': True}}})
    try:
        candidate = env._physical_reset_selection.prepare('r3-pose')
        controller = candidate.execution.controllers[0]
        assert callable(controller.bind_model)
        assert controller.bind_model == controller.servo.bind_model
        with pytest.raises(ValueError, match='missing or differs'):
            controller.bind_model(SimpleNamespace(source_closure_sha256='foreign', evaluate=lambda: None))
    finally:
        env.close()


def test_undeclared_subclass_does_not_infer_component_construction_from_factory_override(monkeypatch):
    from task_env import make_env
    from task_env.registry import ENV_REGISTRY
    from task_env.environment.reference_env import SelectedReferenceEnv
    class Extension(SelectedReferenceEnv):
        uid = 'explicit-component-configuration-test'
    def forbidden_bootstrap(*args, **kwargs):
        raise AssertionError('pure configuration unexpectedly bootstrapped a Runtime')
    monkeypatch.setattr(SelectedReferenceEnv, '_build_runtime_with_rollback', forbidden_bootstrap)
    with pytest.raises(TypeError, match='explicit task binding'):
        Extension()
    monkeypatch.setattr(ENV_REGISTRY, 'get', lambda _uid: Extension)
    env = make_env(Extension.uid, build_runtime=False)
    try:
        assert env._has_component_assembly()
        assert env._runtime is None
    finally:
        env.close()


def test_physical_config_rejects_unconsumed_task_parameters_before_binding(monkeypatch):
    from task_env import make_env
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    def forbidden_binding(*args, **kwargs):
        raise AssertionError('unsupported Task parameter reached source construction')
    monkeypatch.setattr(PickCubeReferenceEnv, 'selected_binding', forbidden_binding)
    with pytest.raises(ValueError, match='unsupported override') as failure:
        make_env(PickCubeReferenceEnv.uid, config={'provider': 'mujoco',
            'controller': {'profile_id': 'panda-direct-effort-v1'}, 'task': {'lift_height_m': .05}})
    assert failure.value.receipt['phase'] == 'static_config'


@pytest.mark.parametrize('uid, config, options, subject_count, controller_count', [
    ('pendulum-v1', {}, {'provider': 'mujoco'}, 1, 1),
    ('two-wheel-balance-v1', {}, {'provider': 'mujoco'}, 1, 1),
    ('pick-cube-p16-reference-v1', {'provider': 'mujoco'}, {}, 1, 1),
    ('pick-cube-p16-reference-v1', {'provider': 'mujoco', 'robot': {'uid': 'panda-arm-hand-v1'},
                                 'task': {'controller_profile': 'r1_split'}}, {}, 2, 2),
])
def test_robot_view_reuses_admitted_subjects_and_controller_owners(
        uid, config, options, subject_count, controller_count):
    from task_env import make_env
    env = make_env(uid, config=config, **options)
    try:
        robot = env.robot
        physical = env._selected_controller_binding.physical_execution
        if physical is not None:
            assert robot.subjects is physical.subjects
            assert robot.controllers is physical.controllers
        else:
            binding = env.value['source'].position_subject_binding
            assert robot.subjects is binding.subjects
            identities = {item.controller_identity for item in binding.plan.controller_bindings}
            assert identities == {item.identity for item in robot.controllers}
            with pytest.raises(ValueError, match='retained position subjects'):
                replace(binding, subjects=(replace(binding.subjects[0], source_id='foreign'),
                                           *binding.subjects[1:]))
        assert len(robot.subjects) == subject_count and len(robot.controllers) == controller_count
        assert robot.controller is env.controller
        assert robot.root_frames == tuple(subject.root_frame for subject in robot.subjects)
        assert robot.gripper is None and robot.ee is None
        assert env.session is None
    finally:
        env.close()


def _fixture():
    plan, context, effort, _ = _case()
    subject = ControlledSubjectV1('subject-a', 'arm', 'source-a', 'b'*64, 'references_existing',
                                  'fixed', FrameReference('arm', 'base'), None,
                                  (('robot', 'arm-drive-joint'),), ('controller-a',))
    controller = SimpleNamespace(binding=plan.binding, identity='control-a', writer_id='controller-a',
        action_shape=(1,), compute=lambda action, view, ctx: PhysicalCommandBatchV1(
            'physical-command-batch-v1', ctx, (effort('effect-a', float(action[0])),), (), ()))
    req = StateRequirements('state-requirements-v1', 'controller', 'subject-a', ())
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {}, req, 1, (subject,))
    return execution, subject, context


def test_subject_controls_actual_named_batch_and_rejects_bad_declarations():
    execution, subject, context = _fixture()
    assert subject.identity_hash != replace(subject, root_mode='free').identity_hash
    with pytest.raises(ValueError, match='unit differs'):
        replace(execution.compiled.binding.channels[0], unit='N')
    batch = execution.controller_batch([1.25], object(), context)
    assert batch.joint_efforts[0].target_key == ('arm', 'drive', 'dof0')
    assert batch.joint_efforts[0].value == 1.25
    assert batch.joint_efforts[0].context == context
    with pytest.raises(ValueError, match='missing, duplicated or foreign'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, channel_paths=(('robot', 'absent'),)),), execution.controllers)
    with pytest.raises(ValueError, match='missing or foreign'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, source_id='other-source'),), execution.controllers)
    with pytest.raises(ValueError, match='missing or foreign'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, source_closure_sha256='c'*64),), execution.controllers)
    with pytest.raises(ValueError, match='root Frame is missing'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, root_frame=FrameReference('arm', 'absent')),), execution.controllers)
    with pytest.raises(ValueError, match='writer is missing'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, controller_writers=('foreign',)),), execution.controllers)
    with pytest.raises(ValueError, match='duplicate subject or entity'):
        validate_controlled_subjects(execution.compiled,
            (subject, replace(subject, subject_id='another')), execution.controllers)
    with pytest.raises(ValueError, match='parent is missing'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, root_mode='constrained', parent_subject_id='absent'),), execution.controllers)


def test_subject_default_effort_controller_is_bound_and_preserves_direct_identity():
    from task_env.controllers.canonical.physical_controller import DirectJointEffortControllerV1
    execution, subject, _ = _fixture()
    binding = execution.compiled.binding
    channel = binding.channels[0]
    controller = subject.default_effort_controller(binding, writer_id='controller-a', units=(channel.unit,))
    previous = DirectJointEffortControllerV1(binding, controller_id='controller-a',
                                            channel_keys=(f'{channel.entity_id}/{channel.joint_id}',))
    assert controller.identity == previous.identity
    with pytest.raises(ValueError, match='writer'):
        subject.default_effort_controller(binding, writer_id='foreign', units=(channel.unit,))
    with pytest.raises(ValueError, match='unit'):
        subject.default_effort_controller(binding, writer_id='controller-a', units=('wrong-unit',))
    with pytest.raises(ValueError, match='one explicit unit'):
        subject.default_effort_controller(binding, writer_id='controller-a', units=())
    with pytest.raises(ValueError, match='missing or ambiguous'):
        replace(subject, channel_paths=(('absent',),)).default_effort_controller(
            binding, writer_id='controller-a', units=(channel.unit,))
    with pytest.raises(ValueError, match='source'):
        replace(subject, source_id='foreign').default_effort_controller(
            binding, writer_id='controller-a', units=(channel.unit,))


def test_default_effort_checks_original_precision_before_float32_rounding():
    execution, subject, context = _fixture()
    binding = execution.compiled.binding
    channel = binding.channels[0]
    controller = subject.default_effort_controller(binding, writer_id='controller-a', units=(channel.unit,))
    with pytest.raises(ValueError, match='declared bounds'):
        controller.compute([channel.effort_range[1] + 1e-9], object(), context)
    other = replace(channel, joint_id='other', component_path=('robot', 'other'),
                    native_actuator='other', transmission_id='other')
    expanded = replace(binding, channels=(channel, other))
    expanded_subject = replace(subject, channel_paths=(*subject.channel_paths, ('robot', 'other')))
    expanded_controller = expanded_subject.default_effort_controller(
        expanded, writer_id='controller-a', units=(channel.unit, other.unit))
    with pytest.raises(ValueError, match='shape or finite'):
        expanded_controller.compute([True, 0.0], object(), context)


@pytest.mark.parametrize('version', [1, 2])
def test_typed_initial_state_uses_session_boundary_and_clock(version):
    from task_env.artifacts.state import (CanonicalStateViewV1, CanonicalStateViewV2,
        CanonicalStatePublicationV1, CanonicalStatePublicationV2, StateViewLifetime)
    from task_env.environment.reference_binding import validate_initial_state_publication
    _, _, context = _fixture()
    view_type = CanonicalStateViewV1 if version == 1 else CanonicalStateViewV2
    publication_type = CanonicalStatePublicationV1 if version == 1 else CanonicalStatePublicationV2
    view = view_type(f'canonical-state-v{version}', 'SI_right_handed_z_up_wxyz',
                     context.boundary, context.clock, (), (), ())
    lifetime = StateViewLifetime('state-view-lifetime-v1', 'material-a', context.boundary, 0,
                                 'owned_snapshot', 'retained')
    publication = publication_type(f'canonical-state-publication-v{version}', view, lifetime)
    session = SimpleNamespace(state_boundary_identity=lambda: context.boundary)
    state = SimpleNamespace(control_step=0, simulation_time=context.clock.simulation_time_s)
    assert validate_initial_state_publication(session, publication, state) is publication
    with pytest.raises(ValueError, match='boundary or clock'):
        validate_initial_state_publication(session, publication,
            SimpleNamespace(control_step=0, simulation_time=state.simulation_time + .1))
    with pytest.raises(ValueError, match='boundary or clock'):
        validate_initial_state_publication(SimpleNamespace(state_boundary_identity=lambda: None), publication, state)


def test_physical_execution_owns_controller_initialization_and_preflights_model():
    from task_env.artifacts.state import CanonicalStateViewV2, CanonicalStatePublicationV2, StateViewLifetime
    from task_env.environment.types import StageUnavailableError
    execution, _, context = _fixture()
    calls = []
    controller = execution.controllers[0]
    controller.bind_model = lambda model: calls.append(('model', model))
    controller.reset_from_realized_state = lambda view: calls.append(('reset', view))
    view = CanonicalStateViewV2('canonical-state-v2', 'SI_right_handed_z_up_wxyz',
                                context.boundary, context.clock, (), (), (), ())
    publication = CanonicalStatePublicationV2('canonical-state-publication-v2', view,
        StateViewLifetime('state-view-lifetime-v1', 'material-a', context.boundary, 0,
                          'owned_snapshot', 'retained'))
    with pytest.raises(StageUnavailableError, match='source dynamics model'):
        execution.initialize_controllers(SimpleNamespace(), publication)
    assert not calls
    execution.initialize_controllers(SimpleNamespace(physical_source_dynamics_model=lambda: 'source-model'), publication)
    assert calls == [('model', 'source-model'), ('reset', view)]


def test_foreign_controller_output_is_rejected_before_submission():
    execution, subject, context = _fixture()
    original = execution.controllers[0]
    wrong = replace(original.compute([1.0], None, context).joint_efforts[0], joint_id='other')
    bad = SimpleNamespace(binding=original.binding, identity=original.identity, writer_id=original.writer_id,
        action_shape=(1,), compute=lambda action, view, ctx: PhysicalCommandBatchV1(
            'physical-command-batch-v1', ctx, (wrong,), (), ()))
    changed = replace(execution, controllers=(bad,))
    with pytest.raises(ValueError, match='outside its subject'):
        changed.controller_batch([1.0], object(), context)


def test_nonposition_reference_close_releases_owned_camera_and_propagates_error():
    from task_env.environment.reference_env import SelectedReferenceEnv
    class Camera:
        calls = 0
        def close(self):
            self.calls += 1
    env = object.__new__(SelectedReferenceEnv)
    env.mixed_control_profile = False
    env.position_profile = False
    env._ui_render_provider = None
    env._camera_consumer = None
    camera = Camera()
    env._task_rgb_consumer = camera
    env.session = None
    env.value = {'source': SimpleNamespace(execution_source_receipt=None)}
    env.binding = SimpleNamespace(close_task_resources=None)
    env._close_reference_resources()
    env._close_reference_resources()
    assert camera.calls == 1
    assert env._task_rgb_consumer is None
    class FailedCamera:
        def close(self):
            raise RuntimeError('camera close failed')
    env._task_rgb_consumer = FailedCamera()
    with pytest.raises(RuntimeError, match='camera close failed'):
        env._close_reference_resources()
    assert env._task_rgb_consumer is None


def test_flat_and_nested_use_same_physical_resolver_and_subject_admission():
    from task_env.artifacts import JointReference
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _assembly, _entity_member, _sub,
    )
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding
    nested, _, _, _ = _case()
    scene = _scene_v3()
    root = _assembly(scene, 'single-subject', (
        _entity_member('arm', path=('owner',)),
        _sub(('hinge',), JointReference('arm', 'drive'), 'joint'),
    ))
    channel = replace(nested.binding.channels[0], component_path=('hinge',))
    binding = replace(nested.binding, logical_assembly_sha256=root.logical_content_sha256,
                      channels=(channel,))
    flat = compile_physical_control_binding(scene, root, {}, binding)
    controller = SimpleNamespace(writer_id='controller-a')
    subject = ControlledSubjectV1('generic-one', 'arm', 'source-a', 'b'*64, 'owns_source', 'fixed',
                                  FrameReference('arm', 'base'), None, (('hinge',),), ('controller-a',))
    validate_controlled_subjects(flat, (subject,), (controller,))
    # The same subject semantics use the nested resolver, without task-name dispatch.
    nested_subject = replace(subject, channel_paths=(('robot', 'arm-drive-joint'),))
    validate_controlled_subjects(nested, (nested_subject,), (controller,))
    with pytest.raises(ValueError, match='source-owning subject needs'):
        empty_owner_root = _assembly(scene, 'referenced-only', (
            _sub(('hinge',), JointReference('arm', 'drive'), 'joint'),))
        no_owner_binding = replace(binding, logical_assembly_sha256=empty_owner_root.logical_content_sha256)
        no_owner = compile_physical_control_binding(scene, empty_owner_root, {}, no_owner_binding)
        validate_controlled_subjects(no_owner, (subject,), (controller,))


def test_legacy_closure_relocation_preserves_receipt_and_rejects_other_changes(monkeypatch, tmp_path):
    import task_env.assembly.assets as assets
    import task_env.utils._paths as paths
    from task_env.tasks.pick_cube.physical_candidate import _accept_original_panda_closure
    root = tmp_path / 'menagerie'
    monkeypatch.setattr(paths, 'MUJOCO_MENAGERIE_ROOT', root)
    current = str((root / 'franka_emika_panda' / 'assets').resolve()).encode()
    old = b'/home/lly/.codex/worktrees/v210-integration/Geochora/asset/external/mujoco_menagerie/franka_emika_panda/assets'
    original = {'canonical-source.xml': b'<compiler meshdir="' + current + b'"/>', 'assets/mesh.stl': b'original'}
    expected_bytes = {'canonical-source.xml': b'<compiler meshdir="' + old + b'"/>', 'assets/mesh.stl': b'original'}
    expected = '02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d'
    monkeypatch.setattr(assets, '_source_closure_digest', lambda values: expected if values == expected_bytes else 'different')
    class Receipt:
        source_closure_digest = 'actual'
        closure_files = original
        def validate_snapshot(self):
            self.checked = True
    receipt = Receipt()
    assert _accept_original_panda_closure(receipt, 'actual')
    assert receipt.checked and receipt.closure_files == original
    assert not _accept_original_panda_closure(receipt, 'foreign')
    receipt.closure_files = dict(original, **{'assets/mesh.stl': b'modified'})
    assert not _accept_original_panda_closure(receipt, 'actual')
    receipt.closure_files = dict(original, **{'canonical-source.xml': original['canonical-source.xml'] + current})
    assert not _accept_original_panda_closure(receipt, 'actual')


def test_third_subject_can_bind_and_submit_without_public_task_dispatch():
    from task_env.artifacts import SceneDefinition, JointReference
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _assembly, _entity_member, _sub,
    )
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding
    old, context, effort, _ = _case()
    def rename(value):
        if isinstance(value, str):
            return {'arm':'rotor','drive':'spin'}.get(value, value)
        if isinstance(value, list): return [rename(x) for x in value]
        if isinstance(value, dict): return {k:rename(v) for k,v in value.items()}
        return value
    scene = SceneDefinition.from_mapping(rename(_scene_v3().to_mapping()))
    root = _assembly(scene, 'rotor-assembly', (
        _entity_member('rotor', path=('owner',)),
        _sub(('spin',), JointReference('rotor', 'spin'), 'joint'),
    ))
    channel = replace(old.binding.channels[0], component_path=('spin',), entity_id='rotor',
                      joint_id='spin', axis_frame=FrameReference('rotor', 'base'))
    binding = replace(old.binding, scene_sha256=scene.identity_hash,
                      logical_assembly_sha256=root.logical_content_sha256, channels=(channel,))
    plan = compile_physical_control_binding(scene, root, {}, binding)
    subject = ControlledSubjectV1('rotor-subject','rotor','source-a','b'*64,'owns_source',
                                  'fixed',FrameReference('rotor','base'),None,(('spin',),),('controller-a',))
    joint = replace(effort('effect-a',1.0), entity_id='rotor', joint_id='spin',
                    axis_frame=FrameReference('rotor','base'))
    controller = SimpleNamespace(binding=binding, identity='rotor-controller', writer_id='controller-a',
        action_shape=(1,), compute=lambda action, view, ctx: PhysicalCommandBatchV1(
            'physical-command-batch-v1',ctx,(replace(joint,context=ctx,value=float(action[0])),),(),()))
    req = StateRequirements('state-requirements-v1','controller','rotor-subject',())
    execution = PhysicalControlExecutionV1(plan,(controller,),scene,{}, {},req,1,(subject,))
    actual = execution.controller_batch([1.5],None,context)
    assert actual.joint_efforts[0].target_key == ('rotor','spin','dof0')
    assert actual.joint_efforts[0].value == 1.5


def test_two_subject_controllers_combine_once_and_reject_parent_cycle():
    from task_env.artifacts import FixedAttachmentPlanV1, JointReference, PoseWorld
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _assembly, _entity_member, _sub,
    )
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding
    old, context, effort, _ = _case(); scene = _scene_v3()
    root = _assembly(scene,'two-subjects',(
        _entity_member('arm',path=('arm-owner',)), _entity_member('hand',path=('hand-owner',)),
        _sub(('arm-joint',),JointReference('arm','drive'),'joint'),
        _sub(('hand-joint',),JointReference('hand','drive'),'joint'),))
    a=replace(old.binding.channels[0],component_path=('arm-joint',))
    b=replace(a,component_path=('hand-joint',),entity_id='hand',axis_frame=FrameReference('hand','base'),
              native_actuator='native-b',transmission_id='direct-b',owner_ids=('controller-b',))
    binding=replace(old.binding,scene_sha256=scene.identity_hash,
                    logical_assembly_sha256=root.logical_content_sha256,channels=(a,b))
    plan=compile_physical_control_binding(scene,root,{},binding)
    first=ControlledSubjectV1('first','arm','source-a','b'*64,'owns_source','fixed',
                              FrameReference('arm','base'),None,(('arm-joint',),),('controller-a',))
    identity=PoseWorld((0.,0.,0.),(1.,0.,0.,0.))
    attachment=FixedAttachmentPlanV1('fixed-attachment-plan-v1',root.assembly_id,root.revision,
        root.logical_content_sha256,root.scene_pin,'arm','hand','robot/shared','v1','robot/shared','v1',
        'c'*64,'d'*64,'e'*64,'b'*64,FrameReference('arm','base'),FrameReference('hand','base'),
        FrameReference('arm','tool'),FrameReference('hand','base'),'mount-site','hand-body',
        identity,identity,'hand-ns','fixed_child_root_under_parent_mount_no_free_joint',
        'source_preserved',.04,(),{'arm/base':'arm-body','hand/base':'hand-body'},
        {'arm/tool':'mount-site'},{'arm/drive':'joint-a'},{'arm/drive':'actuator-a'}, {})
    second=ControlledSubjectV1('second','hand','source-a','b'*64,'references_existing','constrained',
                               FrameReference('hand','base'),'first',(('hand-joint',),),('controller-b',),
                               attachment_plan=attachment)
    def controller(identity,writer,entity):
        joint=effort(identity,1.0)
        joint=replace(joint,entity_id=entity,axis_frame=FrameReference(entity,'base'),
                      contribution=replace(joint.contribution,owner_id=writer))
        return SimpleNamespace(binding=binding,identity=identity,writer_id=writer,action_shape=(1,),
            compute=lambda action,view,ctx: PhysicalCommandBatchV1('physical-command-batch-v1',ctx,
                (replace(joint,context=ctx,value=float(action[0])),),(),()))
    ca,cb=controller('input-a','controller-a','arm'),controller('input-b','controller-b','hand')
    requirements=StateRequirements('state-requirements-v1','controller','both',())
    execution=PhysicalControlExecutionV1(plan,(ca,cb),scene,{}, {},requirements,1,(first,second))
    batch=execution.controller_batch({'input-a':[1.0],'input-b':[2.0]},None,context)
    assert [(v.entity_id,v.value) for v in batch.joint_efforts] == [('arm',1.0),('hand',2.0)]
    with pytest.raises(ValueError,match='parent cycle'):
        validate_controlled_subjects(plan,(replace(first,root_mode='constrained',parent_subject_id='second'),second),(ca,cb))
    with pytest.raises(ValueError,match='source-bound attachment'):
        validate_controlled_subjects(plan,(first,replace(second,attachment_plan=None)),(ca,cb))


def test_two_controllers_conflict_is_rejected_after_subject_dispatch():
    from task_env.diagnostics.tasks.test_v211_physical_control_contract import _joint_receipt
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding, prepare_physical_command_batch
    old, context, effort, assessment = _case()
    channel=replace(old.binding.channels[0],owner_ids=('controller-a','controller-b'))
    binding=replace(old.binding,channels=(channel,))
    plan=compile_physical_control_binding(old.scene,old.root,old.children,binding)
    subject=ControlledSubjectV1('subject','arm','source-a','b'*64,'references_existing','fixed',
        FrameReference('arm','base'),None,(('robot','arm-drive-joint'),),('controller-a','controller-b'))
    def make_controller(identity, writer, composition):
        item=effort(identity,1.0,composition)
        item=replace(item,contribution=replace(item.contribution,owner_id=writer))
        return SimpleNamespace(binding=binding,identity=identity,writer_id=writer,action_shape=(1,),
            compute=lambda action,view,ctx: PhysicalCommandBatchV1('physical-command-batch-v1',ctx,
                (replace(item,context=ctx),),(),()))
    ca=make_controller('a','controller-a','exclusive');cb=make_controller('b','controller-b','sum')
    req=StateRequirements('state-requirements-v1','controller','subject',())
    execution=PhysicalControlExecutionV1(plan,(ca,cb),plan.scene,{}, {},req,1,(subject,))
    batch=execution.controller_batch({'a':[1.],'b':[1.]},None,context)
    prior=assessment('joint_effort','sum')
    admit=replace(prior,request_identity=binding.identity_hash,
        rows=tuple(replace(row,object_ref=f'binding:{binding.identity_hash}') for row in prior.rows))
    with pytest.raises(ValueError,match='declared sum'):
        prepare_physical_command_batch(plan,batch,expected_context=context,
            assessment=admit,joint_build_receipt=_joint_receipt(plan,context))


def test_task_subject_declarations_preserve_hinge_and_wheel_order():
    from task_env.robots.pendulum import PendulumEntity
    from task_env.robots.two_wheel_balance import TwoWheelBalanceEntity
    plan, _, _, _ = _case(); template=plan.binding.channels[0]
    hinge=replace(template,joint_id='pendulum_hinge',native_actuator='pendulum_torque',
                  effort_range=(-2.,2.),native_range=(-2.,2.))
    pendulum=replace(plan.binding,channels=(hinge,))
    declaration=PendulumEntity().controlled_subject(binding=pendulum,entity_id='arm',
        root_frame='base',controller_writer='controller-a')
    assert declaration.channel_paths == (hinge.component_path,)
    left=replace(template,component_path=('left',),joint_id='left_wheel_hinge',
                 native_actuator='left_wheel_torque',transmission_id='left-drive',
                 effort_range=(-1.5,1.5),native_range=(-1.5,1.5))
    right=replace(left,component_path=('right',),joint_id='right_wheel_hinge',
                  native_actuator='right_wheel_torque',transmission_id='right-drive')
    wheel=replace(plan.binding,channels=(left,right))
    declaration=TwoWheelBalanceEntity().controlled_subject(binding=wheel,entity_id='arm',
        root_frame='base',controller_writer='controller-a')
    assert declaration.channel_paths == (('left',),('right',))
    with pytest.raises(ValueError,match='ordered left/right'):
        TwoWheelBalanceEntity().controlled_subject(binding=replace(wheel,channels=(right,left)),
            entity_id='arm',root_frame='base',controller_writer='controller-a')


def test_usd_task_rgb_state_binding_does_not_require_mujoco_source(monkeypatch):
    """Synthetic USD routing is not an Isaac SDK or RGB success."""
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import source as source_module
    from task_env.runtime.sessions.source import UsdRuntimeSourceV1
    source=object.__new__(UsdRuntimeSourceV1)
    object.__setattr__(source,'scene_definition',object())
    object.__setattr__(source,'scene_source',SimpleNamespace(source_closure_sha256='0'*64))
    object.__setattr__(source,'task_artifact',SimpleNamespace(identity_hash='1'*64))
    env=SimpleNamespace(_task_rgb_config=(object(),'isaacsim'),value={'source':source},
                        artifact=SimpleNamespace(identity_hash='1'*64))
    monkeypatch.setattr(source_module,'position_joint_bindings_from_artifact',lambda *_:{})
    monkeypatch.setattr(source_module,'position_frame_bindings_from_artifact',lambda *_:{})
    binding = SelectedReferenceEnv._prepare_task_rgb_state_binding(env)
    assert binding[0] is source and binding[-1] is None


def test_component_resolver_delegates_existing_panda_layout_to_subject():
    import numpy as np
    from task_env.robots.panda import PandaAgent
    from task_env.environment import ReferenceSpec
    from task_env.assembly.references import resolve_task_references
    panda=PandaAgent(); spec=panda.reference_spec()
    item=lambda name:SimpleNamespace(name=name)
    links=[SimpleNamespace(name=name,joints=[],sites=[]) for name in spec.body_names]
    links[0].joints=[item(name) for name in spec.joint_names]
    links[0].sites=[item(name) for name in spec.site_names]
    loader=SimpleNamespace(links=links,actuators=[item(name) for name in spec.actuator_names])
    model=SimpleNamespace(joint_data={'jnt_qposadr':np.arange(len(spec.joint_names)),
        'jnt_dofadr':np.arange(len(spec.joint_names)),
        'actuator_ctrlrange':np.zeros((len(spec.actuator_names),2)), 'geom_names':()})
    scene=SimpleNamespace(uid='empty-scene',reference_spec=lambda:ReferenceSpec())
    refs=resolve_task_references(loader_result=loader,scene_model=model,scene=scene,agents=(panda,),objects=())
    result=refs.agents[panda.uid]
    assert result.arm_joint_ids.tolist()==list(range(7))
    assert result.gripper_joint_ids.tolist()==[7,8]
    assert result.arm_actuator_ids.tolist()==list(range(7))
    assert result.gripper_actuator_ids.tolist()==[7]
    assert result.base_body_name=='link0' and result.eef_site_name=='nutassembly_ee_site'


def test_subject_root_mode_is_rechecked_against_runtime_source():
    execution, subject, _ = _fixture()
    execution=replace(execution,joint_bindings={'arm/drive':object()})
    source=SimpleNamespace(joints={'arm/drive':'hinge'},free_joints={},bodies={},frames={})
    execution.validate_source(scene=execution.scene,artifact_sha256='a'*64,
        source_id='source-a',source_closure_sha256='b'*64,source=source)
    source.joints={};source.free_joints={'arm/drive':'free'}
    with pytest.raises(ValueError,match='root mode differs'):
        execution.validate_source(scene=execution.scene,artifact_sha256='a'*64,
            source_id='source-a',source_closure_sha256='b'*64,source=source)
