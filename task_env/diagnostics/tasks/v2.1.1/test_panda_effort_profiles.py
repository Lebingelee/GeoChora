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
