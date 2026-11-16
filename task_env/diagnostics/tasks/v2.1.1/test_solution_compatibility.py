"""Compatibility Solution entry points share proposal handling and fault rules."""
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.planners.contracts import ExpertAction


def test_pickcube_position_and_physical_readiness_share_measured_boundary():
    from task_env.tasks.pick_cube.task import physical_execution_info, position_execution_info

    state = SimpleNamespace(joint_position={'panda-v1/finger_joint1': .02,
                                            'panda-v1/finger_joint2': .02},
        joint_velocity={'panda-v1/finger_joint1': .002, 'panda-v1/finger_joint2': -.002},
        control_step=3, simulation_time=.03)
    env = SimpleNamespace(state=state, _last_physical_opening_target=.07)
    transition = (None, SimpleNamespace(target=SimpleNamespace(gripper=SimpleNamespace(opening_m=.07))))
    assert position_execution_info(state, transition) == physical_execution_info(env)
    assert not physical_execution_info(env).close_ready
    env._last_physical_opening_target = None
    assert position_execution_info(state, None) == physical_execution_info(env)
    assert not physical_execution_info(env).close_ready  # No full close request yet.
    env._last_physical_opening_target = 0.
    assert physical_execution_info(env).close_ready
    env._last_physical_opening_target = None

    state.joint_position = {'panda-v1/finger_joint1': .041, 'panda-v1/finger_joint2': .041}
    assert physical_execution_info(env).target_opening_m == .08
    with pytest.raises(ValueError, match='invalid PickCube Position'):
        position_execution_info(state, None)
    state.joint_position = {'panda-v1/finger_joint1': -2e-7, 'panda-v1/finger_joint2': 0.}
    assert position_execution_info(state, None).measured_opening_m == 0.
    assert physical_execution_info(env).measured_opening_m == 0.


@pytest.mark.parametrize('backend', ['cpu', 'cuda'])
@pytest.mark.parametrize('profile', ['r1', 'r3_continuous_v1'])
def test_external_pickcube_solution_matches_source_without_constructing_one(backend, profile, monkeypatch):
    from dataclasses import replace
    from task_env.tasks.pick_cube import specialization
    from task_env.runtime.sessions.source import source_resource_receipt

    config = specialization._environment_config()
    config = replace(config, runtime=replace(config.runtime, backend=backend))
    built = specialization.make_reference_binding(controller_profile=profile, resolved_config=config
        ).build_for_request('mujoco', backend, 31, 8)
    try:
        expected_identity = built['solution_identity']
        expected_readiness = built['readiness']
    finally:
        source_resource_receipt(built['source']).close()

    def unexpected_source(*args, **kwargs):
        pytest.fail('external Solution must not construct a RuntimeSource')
    from task_env.assembly import panda_box
    monkeypatch.setattr(panda_box, 'compile_panda_box_task', unexpected_source)
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


@pytest.mark.parametrize('include_report', [False, True])
def test_solution_observation_commits_once_and_preserves_report_policy(include_report):
    from types import SimpleNamespace
    from task_env.environment.reference_env import SelectedReferenceEnv

    events = []
    class Solution:
        done, failed, failure_reason = True, False, None
        def observe(self, observation, reward, terminated, truncated, info, **kwargs):
            events.append(('observe', observation, reward, terminated, truncated, info, kwargs))
        def outcome_report(self):
            events.append(('report',))
            return {'selected_policy_execution_complete': 'overridden', 'task_report': 7}
    env = object.__new__(SelectedReferenceEnv)
    env.info = {'existing': 1}
    projected = {'input': 2}
    env._observe_selected_solution(Solution(), 'observation', 1.5, False, True,
                                   projected, {'sample': 4}, report=include_report)
    assert events[0] == ('observe', 'observation', 1.5, False, True, projected, {'sample': 4})
    assert len(events) == (2 if include_report else 1)
    assert env.info['selected_policy_execution_complete'] is True
    assert env.info['selected_policy_execution_failed'] is False
    assert ('task_report' in env.info) is include_report


def test_solution_observation_failure_does_not_publish_completion():
    from task_env.environment.reference_env import SelectedReferenceEnv

    class FailedSolution:
        def observe(self, *_args, **_kwargs):
            raise RuntimeError('observe failed')
    env = object.__new__(SelectedReferenceEnv)
    env.info = {'existing': 1}
    with pytest.raises(RuntimeError, match='observe failed'):
        env._observe_selected_solution(FailedSolution(), None, 0., False, False, {}, {}, report=True)
    assert env.info == {'existing': 1}
