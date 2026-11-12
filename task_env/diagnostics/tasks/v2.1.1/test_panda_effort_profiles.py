"""Formal PickCube effort profiles share the Controller composition contract."""

import pytest


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
    ('panda-joint-mass-effort-v1', 'MassMatrixEffortControllerV1', 8),
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
        value = binding.build('mujoco')
        execution = value['physical_execution']
        assert type(execution.controllers[0]).__name__ == controller_type
        assert [subject.subject_id for subject in execution.subjects] == ['panda-v1']
        assert execution.action_space().shape == (dimension,)
        assert execution.compiled.binding.source_closure_sha256 == value['source'].source_closure_digest
        if profile.startswith('panda-r3'):
            assert any(field.field_name == 'frame_pose_world' for field in execution.requirements.requirements)
    finally:
        binding.close_task_resources()


def test_panda_subject_rejects_incomplete_native_transmission_declaration():
    from task_env.robots.panda import PandaAgent

    with pytest.raises(ValueError, match='nine named transmission channels'):
        PandaAgent.physical_subject_declaration(
            entity_id='panda-v1', source_id='test-source', source_closure_sha256='a' * 64,
            native_ranges=((-5., 5.),) * 8, native_drive='disabled',
            native_actuators=('joint1',), transmission_ids=('drive1',))


def test_formal_effort_scene_and_execution_use_same_robot(monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.robots.panda import PandaAgent
    from task_env.runtime.sessions import source_scene_import
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    used = []
    declare = source_scene_import.declare_panda_scene
    build = PandaAgent.build_direct_effort_execution

    def capture_declaration(robot, *args, **kwargs):
        used.append(('scene', robot))
        return declare(robot, *args, **kwargs)

    def capture_execution(robot, *args, **kwargs):
        used.append(('execution', robot))
        return build(robot, *args, **kwargs)

    monkeypatch.setattr(source_scene_import, 'declare_panda_scene', capture_declaration)
    monkeypatch.setattr(PandaAgent, 'build_direct_effort_execution', capture_execution)
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
        execution = task_binding.build('mujoco')['physical_execution']
        profile = execution.controllers[0].profile
        with pytest.raises(ValueError, match='writer binding'):
            LinearEffortControllerV1.zero_bias(execution.compiled.binding, writer_id='foreign',
                channel_keys=profile.channel_keys, action_names=profile.action_names,
                action_to_effort=profile.action_to_effort, cadence_s=.01, model_id='foreign')
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
        value = binding.build('mujoco')
        assert value['source'].config.control.profile_id == config.controller_profile
        assert value['source'].config.episode.horizon == 8
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize('profile', ['r3_continuous_v1', 'panda-direct-effort-v1'])
def test_pickcube_position_and_effort_consume_the_same_lift(profile):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                      'deployment': 'in_process', 'interpreter': __import__('sys').executable},
        'controller': {'profile_id': profile}, 'task': {'lift_height_m': .17},
        'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    value = None
    try:
        value = binding.build_seeded('mujoco', 'cpu', 42, 8)
        assert value['artifact'].semantics.parameters_si['lift_height'] == .17
        assert binding.task_definition_factory(value['artifact']).semantics.parameters_si['lift_height'] == .17
    finally:
        if binding.close_task_resources is not None:
            binding.close_task_resources()
        elif value is not None:
            value['source'].execution_source_receipt.close()


@pytest.mark.parametrize('provider', ['mujoco', 'geophys'])
@pytest.mark.parametrize('profile', ['panda-direct-effort-v1', 'panda-joint-effort-reference-v1',
    'panda-r3-effort-reference-v1', 'panda-joint-mass-effort-v1', 'panda-r3-mass-effort-v1'])
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
        value = binding.build(provider)
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


def test_switchable_r3_solution_uses_physical_state_and_control(tmp_path):
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
        env.step_with_solution(solution)
        assert env.state.control_step == before + 1
        assert env.controller is env._physical_reset_selection.current.execution.controllers[0]
        assert env.session._last_control_submission['status'] == 'acknowledged'
        receipt = env.finish_recording('external_stop')
        assert receipt['transition_count'] == 1
        assert receipt['observation_count'] == 2
    finally:
        env.close()
