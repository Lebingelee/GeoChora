"""Compatibility Solution entry points share proposal handling and fault rules."""
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.planners.contracts import ExpertAction


@pytest.mark.parametrize('backend', ['cpu', 'cuda'])
@pytest.mark.parametrize('profile', ['r1', 'r3_continuous_v1'])
def test_external_pickcube_solution_matches_source_without_constructing_one(backend, profile, monkeypatch):
    from task_env.tasks.pick_cube import specialization
    from task_env.runtime.sessions.source import source_resource_receipt

    built = specialization.build_reference(backend=backend, controller_profile=profile)
    try:
        expected_identity = built['solution_identity']
        expected_readiness = built['readiness']
    finally:
        source_resource_receipt(built['source']).close()

    def unexpected_source(*args, **kwargs):
        pytest.fail('external Solution must not construct a RuntimeSource')
    monkeypatch.setattr(specialization, 'compile_panda_box_task', unexpected_source)
    solution = specialization.build_readiness_solution(backend=backend, controller_profile=profile)
    assert solution.identity == expected_identity
    assert solution.readiness_config == expected_readiness


def test_external_pickcube_solution_keeps_robot_and_backend_admission():
    from task_env.tasks.pick_cube.specialization import build_readiness_solution

    with pytest.raises(ValueError, match='Panda does not declare this Controller profile'):
        build_readiness_solution(controller_profile='r1_split')
    with pytest.raises(ValueError, match='backend must be cpu or cuda'):
        build_readiness_solution(backend='unsupported')


@pytest.mark.parametrize('phase', ['proposal', 'physical_external_solution_proposal'])
def test_solution_proposal_is_projected_once_and_remains_caller_owned(phase):
    boundary = {'episode': 'episode-1'}
    proposal = ExpertAction(np.array([0.2]), 'move', request_boundary=boundary,
                            solution_identity='solution-1')
    calls = []
    solution = SimpleNamespace(act=lambda obs, info: calls.append(('act', obs)) or proposal)
    env = SimpleNamespace(obs={'state': 1}, info={'state_boundary_identity': boundary},
        typed_state=SimpleNamespace(view=SimpleNamespace(boundary=SimpleNamespace(to_mapping=lambda: boundary))),
        value={'solution_identity': 'solution-1'}, position_profile=True,
        bind_physical_action=lambda action: calls.append(('bind', action)) or 'bound')
    action, returned = SelectedReferenceEnv._prepare_solution_action(
        env, solution, public_observation=True, physical=True,
        proposal_phase=phase, action_phase='action', abort_on_error=False,
        strict_proposal_type=True, action_projector=env.bind_physical_action)
    assert action == 'bound' and returned is proposal
    assert [item[0] for item in calls] == ['act', 'bind']


@pytest.mark.parametrize('strict', [False, True])
def test_proposal_subclass_policy_is_explicit_and_independent_of_error_phase(strict):
    class DerivedAction(ExpertAction):
        pass

    proposal = DerivedAction(np.array([0.2]), 'move')
    faults = []
    env = SimpleNamespace(position_profile=False, state=object(),
        binding=SimpleNamespace(abort_solution_on_runtime_error=False),
        _latch_fault=lambda phase, error, **kwargs: faults.append(phase))
    solution = SimpleNamespace(act=lambda: proposal)
    kwargs = dict(public_observation=False, physical=False,
        proposal_phase='physical_external_solution_proposal', action_phase='action',
        abort_on_error=False, strict_proposal_type=strict)
    if strict:
        with pytest.raises(TypeError, match='ExpertAction'):
            SelectedReferenceEnv._prepare_solution_action(env, solution, **kwargs)
        assert faults == ['physical_external_solution_proposal']
    else:
        _, returned = SelectedReferenceEnv._prepare_solution_action(env, solution, **kwargs)
        assert returned is proposal and faults == []


def test_bad_solution_proposal_faults_after_act_and_preserves_abort_error():
    calls = []
    def abort(reason):
        calls.append(reason)
        raise RuntimeError('abort failed')
    solution = SimpleNamespace(act=lambda: calls.append('act') or object(), abort=abort)
    env = SimpleNamespace(binding=SimpleNamespace(abort_solution_on_runtime_error=True), state=object(),
                          _latch_fault=lambda phase, error, **kwargs: calls.append(phase))
    with pytest.raises(TypeError, match='ExpertAction') as raised:
        SelectedReferenceEnv._prepare_solution_action(env, solution, public_observation=False,
            physical=False, proposal_phase='expert_proposal', action_phase='expert_action_validation',
            abort_on_error=True)
    assert calls == ['act', 'expert_proposal', 'runtime_error']
    assert any('abort failed' in note for note in raised.value.__notes__)


def test_nut_solution_accepts_public_schema_but_still_rejects_nonfinite_info():
    from task_env.environment.types import ObservationSchema
    from task_env.tasks.nut_assembly.solution import NutAssemblyOutcomeSolutionV1

    solution = object.__new__(NutAssemblyOutcomeSolutionV1)
    pose = np.array([0., 0., 0., 1., 0., 0., 0.])
    observation = {'state': {'ee_pose': pose}, 'privileged_state': {
        'square_nut_v1_body_pose': [pose], 'square_peg_v1_body_pose': [pose]}}
    info = {'observation_schema': ObservationSchema('test-v1', ()), 'is_success': False,
        'task_metrics': {'inserted_on_peg': False, 'released_nut': False, 'task_success': False}}
    assert solution._validate(observation, info) is False
    with pytest.raises(ValueError, match='nonfinite'):
        solution._validate(observation, {**info, 'simulation_time_s': float('nan')})
