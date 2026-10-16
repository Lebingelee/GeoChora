"""Pure result-gating tests for the selected trajectory recording CLI."""
from types import SimpleNamespace

import pytest

from task_env.script.trajectory.record import _completion_result, main


def _env(*, task_kind='pick_cube', done=True, failed=False, task_success=True,
         planned=True, outcome=True, override=False, reason=None):
    solution = SimpleNamespace(
        done=done,
        failed=failed,
        failure_reason=reason,
        outcome_report=lambda: {
            'planned_trajectory_completed': planned,
            'outcome_complete': outcome,
            'unapproved_override_used': override,
            # The outcome CLI must keep strict lifecycle status independent.
            'original_expert_lifecycle_status': {'expert_complete': False, 'expert_failed': True},
        },
    )
    return SimpleNamespace(
        task_kind=task_kind,
        solution=solution,
        info={'is_success': task_success, 'task_metrics': {'task_success': task_success}},
    )


def test_pickcube_requires_successful_expert_and_task_outcome():
    assert _completion_result(_env())['status'] == 'PASS'
    assert _completion_result(_env(done=False))['failure_reason'] == 'selected_policy_incomplete'
    assert _completion_result(_env(failed=True, reason='controller_failure'))['failure_reason'] == 'controller_failure'
    assert _completion_result(_env(task_success=False))['failure_reason'] == 'task_success_false'


@pytest.mark.parametrize(('flag', 'reason'), [
    ('terminated', 'environment_terminated'),
    ('truncated', 'environment_truncated_or_horizon_reached'),
])
def test_terminal_or_horizon_stop_is_not_recorded_as_success(flag, reason):
    assert _completion_result(_env(), **{flag: True})['failure_reason'] == reason


def test_nutassembly_outcome_can_succeed_while_original_strict_expert_failed():
    result = _completion_result(_env(task_kind='nut_assembly'))
    assert result['status'] == 'PASS'
    assert result['planned_trajectory_completed'] and result['outcome_complete']


@pytest.mark.parametrize(('kwargs', 'reason'), [
    ({'planned': False}, 'planned_trajectory_incomplete'),
    ({'outcome': False}, 'outcome_incomplete'),
    ({'override': True}, 'unapproved_override_used_or_unreported'),
])
def test_nutassembly_requires_full_approved_outcome(kwargs, reason):
    assert _completion_result(_env(task_kind='nut_assembly', **kwargs))['failure_reason'] == reason


@pytest.mark.parametrize(('failed', 'success', 'terminated', 'truncated', 'expected', 'reason'), [
    (False, True, False, False, 0, 'selected_policy_completed'),
    (True, False, False, False, 1, 'controller_failure'),
    (False, True, True, False, 1, 'environment_terminated'),
    (False, True, False, True, 1, 'environment_truncated_or_horizon_reached'),
])
def test_record_cli_exit_code_reflects_completion_and_finalizes(failed, success, terminated, truncated, expected, reason, monkeypatch, tmp_path, capsys):
    import task_env

    calls = {}
    env = _env(done=not failed, failed=failed, task_success=success, reason='controller_failure' if failed else None)
    env.reset = lambda seed: None
    env.start_recording = lambda path: None
    env._stopped = not (terminated or truncated)
    def stop_with_flag():
        env._stopped = True
        return None, 0.0, terminated, truncated, env.info
    env.step_expert = stop_with_flag
    env.finish_recording = lambda stop_reason: calls.setdefault('stop_reason', stop_reason) or {'roundtrip': True}
    env.close = lambda: calls.setdefault('closed', True)
    monkeypatch.setattr(task_env, 'make_env', lambda uid, config: env)
    code = main(['--env-id', 'pick-cube-p16-reference-v1', '--provider', 'mujoco',
                 '--output', str(tmp_path / 'episode.h5')])
    output = capsys.readouterr().out
    assert code == expected
    assert calls['stop_reason'] == reason
    assert calls['closed']
    assert ('"status": "PASS"' in output) is (expected == 0)
