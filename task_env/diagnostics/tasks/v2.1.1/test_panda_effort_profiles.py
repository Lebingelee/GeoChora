"""Formal PickCube effort profiles share the Controller composition contract."""

import pytest


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
