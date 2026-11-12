"""Formal PickCube effort profiles share the Controller composition contract."""

import pytest


def test_reference_effort_options_are_resolved_by_controller_capability():
    from task_env.controllers.canonical.dynamic_mass_effort import validate_reset_effort_parameters
    from task_env.controllers.canonical.r3_effort import resolve_panda_effort_options, panda_reset_action_schema

    assert resolve_panda_effort_options('panda-direct-effort-v1', None, {}) == (
        'direct', 'position', False, 'dynamic')
    assert resolve_panda_effort_options('panda-joint-effort-reference-v1', None,
        {'reset_selection': True, 'action_space_policy': 'fixed_semantic'}) == (
            'joint', 'disabled', True, 'fixed_semantic')
    assert panda_reset_action_schema('joint')['controller_kind'] == 'absolute_joint'
    with pytest.raises(ValueError, match='isolated native drive'):
        resolve_panda_effort_options('panda-joint-effort-reference-v1', 'position', {})
    with pytest.raises(ValueError, match='requires reset selection'):
        resolve_panda_effort_options('panda-direct-effort-v1', None,
                                     {'action_space_policy': 'fixed_semantic'})
    for invalid in ({'kp': True}, {'kp': float('inf')}, {'unexpected': 1.}):
        with pytest.raises(ValueError, match='physical controller parameters'):
            validate_reset_effort_parameters(invalid)

from task_env.runtime.sessions.source import source_resource_receipt


def test_panda_declares_shared_immutable_effort_profiles():
    from task_env.controllers.canonical.r3_effort import PANDA_EFFORT_PROFILE_KINDS
    from task_env.robots.panda import PandaAgent
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    profiles = PandaAgent.effort_controller_profiles()
    assert profiles is PANDA_EFFORT_PROFILE_KINDS is PickCubeReferenceEnv.panda_effort_profiles
    assert profiles['panda-joint-effort-reference-v1'] == 'joint'
    with pytest.raises(TypeError):
        profiles['panda-joint-effort-reference-v1'] = 'direct'


@pytest.mark.parametrize('profile,controller_type,dimension', [
    ('panda-joint-effort-reference-v1', 'ConstrainedPairEffortControllerV1', 8),
    ('panda-r3-effort-reference-v1', 'R3ReferenceEffortControllerV1', 8),
    ('panda-joint-mass-effort-v1', 'DynamicMassEffortControllerV1', 8),
    ('panda-r3-mass-effort-v1', 'R3ReferenceEffortControllerV1', 8),
])
def test_formal_panda_effort_profile_source_contract(profile, controller_type, dimension):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'episode': {'horizon': 8}, 'controller': {'profile_id': profile},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        execution = value['physical_execution']
        assert type(execution.controllers[0]).__name__ == controller_type
        assert [subject.subject_id for subject in execution.subjects] == ['panda-v1']
        assert execution.action_space().shape == (dimension,)
        assert execution.compiled.binding.source_closure_sha256 == value['source'].source_closure_digest
        if profile.startswith('panda-r3'):
            assert any(field.field_name == 'frame_pose_world' for field in execution.requirements.requirements)
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize('profile', ['panda-joint-mass-effort-v1', 'panda-r3-mass-effort-v1'])
def test_source_dynamics_profile_does_not_construct_unused_pd_servo(profile, monkeypatch):
    from task_env.controllers.canonical.effort_servo import JointReferenceEffortControllerV1
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    def unexpected_servo(*args, **kwargs):
        pytest.fail('source dynamics constructed an unused affine PD servo')
    monkeypatch.setattr(JointReferenceEffortControllerV1, '__init__', unexpected_servo)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        assert binding.build_for_request('mujoco', 'cpu', 31, 8)['physical_execution'].requires_source_dynamics
    finally:
        binding.close_task_resources()


def test_panda_subject_rejects_incomplete_native_transmission_declaration():
    from task_env.robots.panda import PandaAgent

    with pytest.raises(ValueError, match='nine named transmission channels'):
        PandaAgent.physical_subject_declaration(
            entity_id='panda-v1', source_id='test-source', source_closure_sha256='a' * 64,
            native_ranges=((-5., 5.),) * 8, native_drive='disabled',
            native_actuators=('joint1',), transmission_ids=('drive1',))


@pytest.mark.parametrize(('drive', 'limit'), [('position', 10.), ('disabled', -1.), ('disabled', float('nan'))])
def test_panda_rejects_invalid_gripper_force_override(drive, limit):
    from task_env.robots.panda import PandaAgent
    from task_env.runtime.sessions.source_composition_adapters import build_panda_direct_effort_execution

    with pytest.raises(ValueError, match='positive limit and isolated drives'):
        build_panda_direct_effort_execution(PandaAgent(), None, None, None, entity_id='panda-v1',
            native_drive=drive, native_ranges=((-5., 5.),) * 8, gripper_force_limit_N=limit)


def test_formal_effort_scene_and_execution_use_same_robot(monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.robots.panda import PandaAgent
    from task_env.runtime.sessions import source_composition_adapters, source_scene_import
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    used = []
    declare = source_scene_import.declare_panda_scene
    build = source_composition_adapters.build_panda_direct_effort_execution

    def capture_declaration(robot, *args, **kwargs):
        used.append(('scene', robot))
        return declare(robot, *args, **kwargs)

    def capture_execution(robot, *args, **kwargs):
        used.append(('execution', robot))
        return build(robot, *args, **kwargs)

    monkeypatch.setattr(source_scene_import, 'declare_panda_scene', capture_declaration)
    monkeypatch.setattr(source_composition_adapters, 'build_panda_direct_effort_execution', capture_execution)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-direct-effort-v1'}, 'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        assert [kind for kind, _ in used] == ['scene', 'execution']
        assert used[0][1] is used[1][1]
    finally:
        binding.close_task_resources()


def test_panda_effort_controller_rejects_foreign_writer():
    from task_env.controllers.canonical.physical_controller import LinearEffortControllerV1
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-direct-effort-v1'}, 'episode': {'horizon': 8},
    })
    task_binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        execution = task_binding.build_for_request('mujoco', 'cpu', 31, 8)['physical_execution']
        profile = execution.controllers[0].profile
        with pytest.raises(ValueError, match='writer binding'):
            LinearEffortControllerV1.zero_bias(execution.compiled.binding, writer_id='foreign',
                channel_keys=profile.channel_keys, action_names=profile.action_names,
                action_to_effort=profile.action_to_effort, cadence_s=.01, model_id='foreign')
    finally:
        task_binding.close_task_resources()


@pytest.mark.parametrize('profile', ['panda-direct-effort-v1', 'panda-joint-effort-reference-v1',
                                    'panda-r3-effort-reference-v1', 'panda-joint-mass-effort-v1',
                                    'panda-r3-mass-effort-v1'])
def test_effort_retains_formal_task_identity(profile):
    from dataclasses import replace
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv, build_artifact
    from task_env.runtime.sessions.control import bind_selected_controller

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        assert value['artifact'].artifact_id == build_artifact().artifact_id
        selected = bind_selected_controller(value, binding=binding, provider='mujoco', backend='cpu')
        assert selected.physical_execution is value['physical_execution']
        match, = selected.selection_matches
        assert match.selection_profile_id == profile
        assert match.controller_identities == (value['controller'].identity,)
        assert match.subject_ids == ('panda-v1',)
        assert len(match.channel_keys) == len(match.resource_keys) == 9
        if profile in {'panda-direct-effort-v1', 'panda-joint-effort-reference-v1',
                       'panda-r3-effort-reference-v1'}:
            assert match.model_requirement_sha256 is not None
        if profile == 'panda-direct-effort-v1':
            from task_env.controllers.canonical.physical_controller import LinearEffortControllerV1
            controller = value['controller']
            alternate = LinearEffortControllerV1(
                replace(controller.profile, selection_profile_id='foreign-profile'),
                controller.binding, controller.model)
            assert alternate.identity != controller.identity
        if profile == 'panda-joint-effort-reference-v1':
            from task_env.controllers.canonical.effort_servo import JointReferenceEffortControllerV1
            servo = value['controller'].servo
            alternate = JointReferenceEffortControllerV1(servo.profile, servo.binding, servo._linear.model,
                                                          selection_profile_id='foreign-profile')
            assert alternate.identity != servo.identity
        with pytest.raises(ValueError, match='physical selection differs'):
            replace(selected.physical_execution, selection_profile_id='foreign-profile')
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize('profile', ['panda-joint-mass-effort-v1', 'panda-r3-mass-effort-v1'])
def test_mass_controller_requires_matching_source_dynamics(profile):
    from types import SimpleNamespace
    from task_env.environment.types import StageUnavailableError
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        execution = value['physical_execution']
        assert execution.requires_source_dynamics
        execution.preflight(provider='mujoco', backend='cpu', artifact=value['artifact'], source=value['source'])
        with pytest.raises(StageUnavailableError, match='source dynamics'):
            execution.preflight(provider='geophys', backend='cpu', artifact=value['artifact'], source=value['source'])
        foreign = SimpleNamespace(source_closure_sha256='f' * 64, evaluate=lambda *args: None)
        with pytest.raises(ValueError, match='selected source'):
            execution.controllers[0].bind_model(foreign)
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize(('profile', 'expected'), [
    ('panda-direct-effort-v1', 'position'),
    ('panda-joint-effort-reference-v1', 'disabled'),
])
def test_adapter_drive_mode_follows_bound_channels(profile, expected):
    from dataclasses import replace
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions.physical_control import uniform_native_drive_mode
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    task_binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        binding = task_binding.build_for_request('mujoco', 'cpu', 31, 8)['physical_execution'].compiled.binding
        assert uniform_native_drive_mode(binding) == expected
        opposite = 'disabled' if expected == 'position' else 'position'
        mixed = replace(binding, channels=(replace(binding.channels[0], native_drive=opposite),
                                           *binding.channels[1:]))
        with pytest.raises(ValueError, match='one supported native drive'):
            uniform_native_drive_mode(mixed)
    finally:
        task_binding.close_task_resources()


def test_effort_uses_resolved_task_configuration_without_loading_it_again(monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube import specialization

    config = resolve_task_env_config(specialization.PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'episode': {'horizon': 8},
    })
    def unexpected_reload():
        pytest.fail('effort construction reloaded the Task configuration')
    monkeypatch.setattr(specialization, '_configuration', unexpected_reload)
    binding = specialization.PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        assert value['source'].config.control.profile_id == config.controller_profile
        assert value['source'].config.episode.horizon == 8
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize('profile', ['panda-direct-effort-v1', 'panda-joint-effort-reference-v1'])
def test_effort_without_solution_does_not_prepare_solution_readiness(profile, monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.solution import PickCubeReadinessConfig

    config = resolve_task_env_config(specialization.PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    def unexpected(*args, **kwargs):
        pytest.fail('effort construction prepared unused Solution data')
    monkeypatch.setattr(specialization, '_r3_dynamic_profile', unexpected)
    monkeypatch.setattr(PickCubeReadinessConfig, 'from_source', unexpected)
    binding = specialization.PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        assert value['controller'] is value['physical_execution'].controllers[0]
        assert 'solution_factory' not in value
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize('profile', ['r3_continuous_v1', 'panda-direct-effort-v1'])
def test_pickcube_position_and_effort_consume_the_same_lift(profile):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv, build_artifact

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                      'deployment': 'in_process', 'interpreter': __import__('sys').executable},
        'controller': {'profile_id': profile}, 'task': {'lift_height_m': .17},
        'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    value = None
    try:
        value = binding.build_for_request('mujoco', 'cpu', 42, 8)
        assert value['artifact'].semantics.parameters_si['lift_height'] == .17
        assert binding.task_definition_factory(value['artifact']).semantics.parameters_si['lift_height'] == .17
        assert value['artifact'].initialization.joint_position == build_artifact(lift_height_m=.17).initialization.joint_position
    finally:
        if binding.close_task_resources is not None:
            binding.close_task_resources()
        elif value is not None:
            source_resource_receipt(value['source']).close()


@pytest.mark.parametrize('provider', ['mujoco', 'geophys'])
@pytest.mark.parametrize('profile', ['panda-direct-effort-v1', 'panda-joint-effort-reference-v1',
    'panda-r3-effort-reference-v1'])
def test_fixed_effort_does_not_construct_position_controller(provider, profile, monkeypatch):
    import sys
    from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    def reject_position(*args, **kwargs):
        raise AssertionError('fixed effort must not construct a Position Controller')

    monkeypatch.setattr(PandaPositionServoProfileV1, 'from_source', reject_position)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': provider, 'deployment': 'in_process',
                      'interpreter': sys.executable},
        'controller': {'profile_id': profile},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request(provider, 'cpu', 31, 8)
        assert value['controller'] is value['physical_execution'].controllers[0]
        assert binding.physical_observation_binding is None
        assert binding.physical_sequence_v2_observation is True
    finally:
        binding.close_task_resources()


def test_switchable_effort_recording_uses_physical_owner_metadata(monkeypatch, tmp_path):
    import sys
    from task_env import make_env
    from task_env.environment.reference_env import SelectedReferenceEnv

    def reject_position_metadata(_env):
        raise AssertionError('physical recording must not use Position metadata')

    monkeypatch.setattr(SelectedReferenceEnv, '_position_record_metadata', reject_position_metadata)
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process',
                      'interpreter': sys.executable},
        'episode': {'horizon': 8},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1',
                       'parameters': {'reset_selection': True}},
    })
    try:
        env.reset(seed=31)
        env.start_recording(tmp_path / 'episode.h5')
        metadata = env.recorder._record_metadata
        profile = metadata['env_metadata']['reference_profile']
        execution = env._physical_reset_selection.current.execution
        assert profile['physical_binding_sha256'] == execution.compiled.binding.identity_hash
        assert profile['scene_identity_hash'] == execution.scene.identity_hash
        assert profile['source_closure_digest'] == env.value['source'].source_closure_digest
        assert 'position_control_binding_provenance' not in metadata['resolved_config']
    finally:
        env.close()


@pytest.mark.parametrize('switchable', [False, True])
def test_effort_reset_rebuilds_plan_for_requested_seed(switchable):
    import sys
    import numpy as np
    from task_env import make_env

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process',
                      'interpreter': sys.executable},
        'episode': {'horizon': 8, 'seed': 31},
        'controller': {'profile_id': ('panda-r3-effort-reference-v1' if switchable
                                     else 'panda-joint-effort-reference-v1'),
                       'parameters': {'reset_selection': switchable}},
    })
    try:
        q = env.artifact.initialization.joint_position
        action = (np.asarray([.4, 0., .4, 1., 0., 0., 0., 1.], dtype=np.float32)
                  if switchable else np.asarray(
                      [q[f'panda-v1/joint{i}'] + (.002 if i == 1 else 0.)
                       for i in range(1, 8)] + [.04], dtype=np.float32))
        env.reset(seed=37)
        first = env.sample
        assert first.task_seed == 37
        if switchable:
            from task_env.environment.types import StageUnavailableError
            controller, boundary = env.controller, env.session.state_boundary_identity()
            with pytest.raises(StageUnavailableError, match='only supported at reset'):
                env.switch_position_controller(object())
            assert env.controller is controller
            assert env.session.state_boundary_identity() == boundary
        env.step(env.bind_physical_action(action) if switchable else action)
        env.reset(seed=42)
        assert env.sample.task_seed == 42
        env.step(env.bind_physical_action(action) if switchable else action)
        env.reset(seed=37)
        assert env.sample == first
        if switchable:
            solution = env.value['solution_factory']()
            env.reset_for_solution(solution, seed=43)
            assert env.sample.task_seed == 43
    finally:
        env.close()


@pytest.mark.parametrize('parameters', [{'kp': 0.}, {'kd': float('nan')}, {'unknown': 1.}])
def test_invalid_reset_controller_gains_fail_before_materialization(parameters):
    from task_env import make_env

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1',
                       'parameters': {'reset_selection': True}},
    })
    try:
        with pytest.raises(ValueError, match='unsupported or invalid physical controller parameters'):
            env.reset(seed=31, options={'controller': {'kind': 'joint', 'parameters': parameters}})
        assert env.session is None
        assert env._physical_reset_selection.committed is None
    finally:
        env.close()


def test_reset_switch_matches_the_candidate_controller_before_materialization():
    from task_env import make_env

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1',
                       'parameters': {'reset_selection': True}},
        'episode': {'horizon': 8},
    })
    try:
        env.reset(seed=31)
        first = env.controller.identity
        env.reset(seed=31, options={'controller': 'r3-pose'})
        match, = env._controller_selection_matches
        assert match.selection_profile_id == 'panda-r3-effort-reference-v1'
        assert match.controller_identities == (env.controller.identity,)
        assert env.controller.identity != first
        assert env.value['physical_execution'] is env._physical_reset_selection.current.execution
    finally:
        env.close()


def test_switchable_r3_solution_uses_physical_state_and_control(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import sys
    from task_env import make_env
    from task_env.artifacts.state import CanonicalStatePublicationV2

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process',
                      'interpreter': sys.executable},
        'episode': {'horizon': 8},
        'controller': {'profile_id': 'panda-r3-effort-reference-v1',
                       'parameters': {'reset_selection': True}},
    })
    try:
        solution = env.value['solution_factory']()
        _, info = env.reset_for_solution(solution, seed=31)
        assert isinstance(env.typed_state, CanonicalStatePublicationV2)
        assert not env.position_profile
        assert 'pickcube_position_execution_info_v1' in info
        env.start_recording(tmp_path / 'solution.h5')
        before = env.state.control_step
        original_scope = env._selected_com_wrench_scope
        scoped = []

        @contextmanager
        def capture_scope(requests):
            scoped.append(requests)
            with original_scope(requests):
                yield

        monkeypatch.setattr(env, '_selected_com_wrench_scope', capture_scope)
        env.step_with_solution(solution)
        assert scoped == [None]
        assert env.state.control_step == before + 1
        assert env.controller is env._physical_reset_selection.current.execution.controllers[0]
        assert env.session._last_control_submission['status'] == 'acknowledged'
        receipt = env.finish_recording('external_stop')
        assert receipt['transition_count'] == 1
        assert receipt['observation_count'] == 2
    finally:
        env.close()


def test_switchable_r3_expert_uses_the_selected_controller_submission():
    from task_env import make_env

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-r3-effort-reference-v1',
                       'parameters': {'reset_selection': True}},
        'episode': {'horizon': 8},
    })
    try:
        env.reset(seed=31)
        before = env.state.control_step
        env.step_expert()
        assert env.state.control_step == before + 1
        assert env.controller is env._physical_reset_selection.current.execution.controllers[0]
        assert env.session._last_control_submission['status'] == 'acknowledged'
    finally:
        env.close()


def test_stale_switchable_action_rejects_without_fault_or_dispatch():
    import numpy as np
    from task_env import make_env

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1',
                       'parameters': {'reset_selection': True}},
        'episode': {'horizon': 8},
    })
    try:
        env.reset(seed=31)
        q = env.artifact.initialization.joint_position
        values = np.asarray([q[f'panda-v1/joint{i}'] for i in range(1, 8)] + [.04], dtype=np.float32)
        action = env.bind_physical_action(values)
        boundary = env.session.state_boundary_identity()
        dispatch = getattr(env.session, '_control_lifecycle_dispatch', None)
        with pytest.raises(ValueError, match='requires the R3 pose'):
            env.step_expert()
        assert env.solution is None
        with pytest.raises(ValueError, match='stale or foreign'):
            env.step({**action, 'generation': action['generation'] + 1})
        assert env._execution_fault is None
        assert env.session.state_boundary_identity() == boundary
        assert getattr(env.session, '_control_lifecycle_dispatch', None) is dispatch
        env.step(action)
        assert env.session._last_control_submission['status'] == 'acknowledged'
    finally:
        env.close()


def test_malformed_expert_proposal_faults_after_solution_act(monkeypatch):
    from task_env import make_env

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'r3_continuous_v1'},
        'episode': {'horizon': 8},
    })
    try:
        env.reset(seed=31)
        solution = env.prepare_expert()
        calls = []
        def invalid_action(*_args):
            calls.append('mutated')
            return object()
        monkeypatch.setattr(solution, 'act', invalid_action)
        boundary = env.session.state_boundary_identity()
        with pytest.raises(TypeError, match='expert Solution act'):
            env.step_expert()
        assert calls == ['mutated']
        assert env._execution_fault.phase == 'expert_proposal'
        assert env.session.state_boundary_identity() == boundary
        with pytest.raises(RuntimeError, match='faulted'):
            env.step_expert()
    finally:
        env.close()


@pytest.mark.parametrize(('profile', 'requires_kinematics'), [
    ('panda-joint-effort-reference-v1', False),
    ('panda-r3-effort-reference-v1', True),
    ('panda-r3-mass-effort-v1', True),
])
def test_effort_controller_constructs_only_its_required_source_model(profile, requires_kinematics, monkeypatch):
    from task_env.controllers.canonical.kinematics import PandaKinematics
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions.source import project_scene_definition_v3_to_mjcf
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    original = PandaKinematics.__init__
    used_sources = []
    def capture(self, source_xml, *args, **kwargs):
        used_sources.append(source_xml)
        original(self, source_xml, *args, **kwargs)
    monkeypatch.setattr(PandaKinematics, '__init__', capture)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        source = binding.build_for_request('mujoco', 'cpu', 31, 8)['source']
        expected = project_scene_definition_v3_to_mjcf(source.scene_source.xml, source.scene_definition)
        assert used_sources == ([expected] if requires_kinematics else [])
    finally:
        binding.close_task_resources()


def test_task_force_uses_the_same_declaration_for_position_and_effort(monkeypatch):
    from types import SimpleNamespace
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube import specialization

    def config(profile):
        return resolve_task_env_config(specialization.PickCubeReferenceEnv, {
            'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
            'controller': {'profile_id': profile}, 'task': {'cube_force_z_N': 1.5},
        })

    position = specialization.PickCubeReferenceEnv.selected_binding(config('r1'))
    def unexpected_position_binding(*_args, **_kwargs):
        pytest.fail('effort construction must not construct a Position task binding')
    monkeypatch.setattr(specialization, 'make_reference_binding', unexpected_position_binding)
    effort = specialization.PickCubeReferenceEnv.selected_binding(config('panda-direct-effort-v1'))
    try:
        assert position.task_definition_factory == effort.task_definition_factory
        assert position.task_state_projection is effort.task_state_projection
        assert position.object_poses == effort.object_poses
        env = SimpleNamespace(artifact=SimpleNamespace(timebase=SimpleNamespace(control_substeps=5)))
        left, = position.task_com_wrench_factory(env)
        right, = effort.task_com_wrench_factory(env)
        left.validate()
        right.validate()
        assert left == right
        assert (left.force_world_N, left.start_substep, left.end_substep) == ((0., 0., 1.5), 0, 5)
    finally:
        effort.close_task_resources()
