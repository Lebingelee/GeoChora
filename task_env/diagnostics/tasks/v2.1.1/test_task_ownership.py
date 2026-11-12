"""Common native interval identity and clock validation used by formal Tasks."""
from types import SimpleNamespace

import pytest

from task_env.controllers.canonical.feedback import validate_native_interval_boundaries


def _boundary(step, time_s):
    return {'control_step': step, 'simulation_time_s': time_s, 'identity_hash': f'boundary-{step}',
            'episode_id': 'episode', 'reset_sample_id': 'reset', 'provider_materialization_id': 'source'}


def test_native_interval_common_contract_checks_identity_and_measured_time():
    before, after = _boundary(3, .03), _boundary(4, .04)
    kwargs = {'episode_id': 'episode', 'reset_sample_id': 'reset',
              'provider_materialization_id': 'source', 'interval_s': .01}
    assert validate_native_interval_boundaries(before, after, **kwargs) == (.03, .04)
    for mutated in ({**after, 'episode_id': 'other'}, {**after, 'identity_hash': ''},
                    {**after, 'control_step': 5}):
        with pytest.raises(ValueError, match='boundary identity'):
            validate_native_interval_boundaries(before, mutated, **kwargs)
    for time_s in (.05, float('nan'), float('inf')):
        with pytest.raises(ValueError, match='control interval'):
            validate_native_interval_boundaries(before, {**after, 'simulation_time_s': time_s}, **kwargs)


def test_shared_guard_dwell_gap_restore_and_priority_without_task_import():
    from task_env.planners.completion import GuardedTransitionEvaluator, TransitionGuardSpec
    from copy import deepcopy

    def make():
        return GuardedTransitionEvaluator(source_stage='source', guards=(
            TransitionGuardSpec('primary', 'source', 'done', ('primary',), 0),
            TransitionGuardSpec('backup', 'source', 'done', ('backup',), 1)),
            required_duration_s=.1, start_time_s=0, deadline_s=1, sample_period_s=.002,
            allow_early_alternative=True)
    def sample(index):
        return {'sample_time_s': index * .002, 'sample_duration_s': .002,
                'conditions': {'primary': True, 'backup': True}, 'values': {'index': index}}
    current = make()
    for index in range(10):
        current.observe(sample(index))
    assert current.observe(sample(11)).outcome == 'RECOVERY_REQUIRED'
    for index in range(12, 36):
        current.observe(sample(index))
    restored = make()
    restored.restore_state(deepcopy(current.to_mapping()))
    for index in range(36, 61):
        left, right = current.observe(sample(index)), restored.observe(sample(index))
    assert left.to_mapping() == right.to_mapping()
    assert left.outcome == 'AUTHORIZED' and left.selected_guard_id == 'primary'
    assert left.evidence['native_sample_count'] == 50


def test_nut_guard_keeps_actuator_and_two_millisecond_policy_at_task_boundary():
    from task_env.controllers.canonical.feedback import (CanonicalControlFeedback,
        CanonicalGripperFeedback, NativeControlFeedbackSampleV1)
    from task_env.environment.types import ActuatorForceMeasurementV1
    from task_env.tasks.nut_assembly.solution import _validate_nut_native_force_contract

    def sample(*, actuator, evaluation, sample_time):
        feedback = CanonicalControlFeedback('canonical-control-feedback-v0', 0, evaluation,
            CanonicalGripperFeedback('gripper', .04, 2.0))
        measurement = ActuatorForceMeasurementV1('task-env-actuator-force-sample-v1',
            1, 1, 1, 1, 1, 'native_step_pre_integration', True, episode_id='episode',
            reset_sample_id='reset', evaluation_control_step=0,
            evaluation_simulation_time_s=evaluation, actuator_id=actuator,
            actuator_ctrl=0.1, signed_force_N=-2., native_sample_time_s=sample_time)
        return NativeControlFeedbackSampleV1('native-control-feedback-sample-v1', 'provider',
            'materialization', 'source', None, 'episode', 'reset', feedback, measurement)

    _validate_nut_native_force_contract(sample(actuator='actuator8', evaluation=.002, sample_time=0.))
    other_robot = sample(actuator='other-gripper', evaluation=.002, sample_time=0.)
    with pytest.raises(ValueError, match='actuator8'):
        _validate_nut_native_force_contract(other_robot)
    wrong_clock = sample(actuator='actuator8', evaluation=.005, sample_time=.004)
    with pytest.raises(ValueError, match='2 ms'):
        _validate_nut_native_force_contract(wrong_clock)


def test_nut_solution_factory_releases_its_temporary_source(monkeypatch):
    from task_env.tasks.nut_assembly import specialization
    from task_env.runtime.sessions import source as source_api
    token = object()
    source = object()
    closed = []
    monkeypatch.setattr(specialization, 'build_reference',
                        lambda *, provider: {'source': source, 'solution': token})
    monkeypatch.setattr(source_api, 'source_resource_receipt',
                        lambda actual: SimpleNamespace(close=lambda: closed.append(actual)))
    assert specialization.build_outcome_solution(provider='mujoco') is token
    assert closed == [source]


def test_nut_solution_factory_real_source_is_closed(monkeypatch):
    from task_env.tasks.nut_assembly import specialization
    from task_env.runtime.sessions.source import source_resource_receipt
    original = specialization.build_reference
    leases = []
    def build(**kwargs):
        value = original(**kwargs)
        leases.append(source_resource_receipt(value['source']))
        return value
    monkeypatch.setattr(specialization, 'build_reference', build)
    solution = specialization.build_outcome_solution(provider='mujoco')
    assert solution.identity and len(leases) == 1 and not leases[0].snapshot_root.exists()
