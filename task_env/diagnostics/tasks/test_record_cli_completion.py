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
    )
    if task_kind == 'nut_assembly':
        solution.outcome_report = lambda: {
            'planned_trajectory_completed': planned,
            'outcome_complete': outcome,
            'unapproved_override_used': override,
            # The outcome CLI must keep strict lifecycle status independent.
            'original_expert_lifecycle_status': {'expert_complete': False, 'expert_failed': True},
        }
    return SimpleNamespace(
        task_kind=task_kind,
        solution=solution,
        info={'is_success': task_success, 'task_metrics': {'task_success': task_success}},
    )


def _result(env, **kwargs):
    return _completion_result(env, env.info, **kwargs)


def test_pickcube_requires_successful_expert_and_task_outcome():
    assert _result(_env())['status'] == 'PASS'
    assert _result(_env(done=False))['failure_reason'] == 'selected_policy_incomplete'
    assert _result(_env(failed=True, reason='controller_failure'))['failure_reason'] == 'controller_failure'
    assert _result(_env(task_success=False))['failure_reason'] == 'task_success_false'


@pytest.mark.parametrize(('flag', 'reason'), [
    ('terminated', 'environment_terminated'),
    ('truncated', 'environment_truncated_or_horizon_reached'),
])
def test_terminal_or_horizon_stop_is_not_recorded_as_success(flag, reason):
    assert _result(_env(), **{flag: True})['failure_reason'] == reason


def test_nutassembly_outcome_can_succeed_while_original_strict_expert_failed():
    result = _result(_env(task_kind='nut_assembly'))
    assert result['status'] == 'PASS'
    assert result['planned_trajectory_completed'] and result['outcome_complete']


@pytest.mark.parametrize(('kwargs', 'reason'), [
    ({'planned': False}, 'planned_trajectory_incomplete'),
    ({'outcome': False}, 'outcome_incomplete'),
    ({'override': True}, 'unapproved_override_used_or_unreported'),
])
def test_nutassembly_requires_full_approved_outcome(kwargs, reason):
    assert _result(_env(task_kind='nut_assembly', **kwargs))['failure_reason'] == reason


@pytest.mark.parametrize(('failed', 'success', 'terminated', 'truncated', 'expected', 'reason'), [
    (False, True, False, False, 0, 'selected_policy_completed'),
    (True, False, False, False, 1, 'controller_failure'),
    (False, True, True, False, 1, 'environment_terminated'),
    (False, True, False, True, 1, 'environment_truncated_or_horizon_reached'),
])
def test_record_cli_exit_code_reflects_completion_and_finalizes(failed, success, terminated, truncated, expected, reason, monkeypatch, tmp_path, capsys):
    import task_env

    calls = {}
    env = _env(done=False, failed=failed, task_success=success, reason='controller_failure' if failed else None)
    env.reset = lambda seed: (None, env.info)
    env.start_recording = lambda path: None
    def stop_with_flag():
        env.solution.done = True
        return None, 0.0, terminated, truncated, env.info
    env.step_expert = stop_with_flag
    def finish_recording(stop_reason):
        calls['stop_reason'] = stop_reason
        calls['finalized'] = True
        return {'roundtrip': True}
    env.finish_recording = finish_recording
    env.close = lambda: calls.setdefault('closed', True)
    monkeypatch.setattr(task_env, 'make_env', lambda uid, config: env)
    code = main(['--env-id', 'pick-cube-p16-reference-v1', '--provider', 'mujoco',
                 '--output', str(tmp_path / 'episode.h5')])
    output = capsys.readouterr().out
    assert code == expected
    assert calls['stop_reason'] == reason
    assert calls['finalized']
    assert calls['closed']
    assert ('"status": "PASS"' in output) is (expected == 0)


def test_failed_cli_run_finalizes_readable_h5_before_nonzero_exit(monkeypatch, tmp_path, capsys):
    """Exercise the CLI and real canonical recorder with one synthetic interval."""
    import task_env
    import task_env.runtime.sessions.provenance as provenance
    import task_env.tasks.reference_env as reference_env
    from task_env.diagnostics.tasks.test_selected_consumers import FakeSession
    from task_env.trajectory.canonical.h5 import load

    monkeypatch.setattr(reference_env, 'materialize_control', FakeSession)
    monkeypatch.setattr(provenance, 'provider_build_identity',
                        lambda provider: {'synthetic_provider': provider})
    real_make_env = task_env.make_env
    monkeypatch.setattr(task_env, 'make_env',
                        lambda uid, config: real_make_env(uid, config={**config, 'horizon': 1}))

    path = tmp_path / 'failed-episode.h5'
    code = main(['--env-id', 'pick-cube-p16-reference-v1', '--provider', 'mujoco',
                 '--horizon', '1', '--seed', '31', '--output', str(path)])
    output = capsys.readouterr().out

    assert code == 1
    assert '"status": "FAIL"' in output
    assert '"logical_mapping_exact": true' in output
    assert path.is_file()
    trajectory = load(path)
    assert trajectory.stop_reason == 'environment_truncated_or_horizon_reached'
    assert len(trajectory.transitions) == 1
    assert len(trajectory.boundaries) == 2
    assert trajectory.transitions[0].truncated is True
