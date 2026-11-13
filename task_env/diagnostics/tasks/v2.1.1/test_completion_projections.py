"""The ordinary callers and Harness preserve the same episode facts."""
from types import SimpleNamespace

import pytest

from examples._common import episode_result
from task_env.script.agent.completion_facts import capture_episode_facts
from task_env.script.trajectory.planning._common import _completion_fields
from task_env.script.trajectory.record import _completion_result


@pytest.mark.parametrize('change', [
    {}, {'task_success': False}, {'task_failure': True}, {'done': False},
    {'failed': True}, {'terminated': True}, {'truncated': True},
    {'planned': False}, {'outcome': False}, {'override': True},
    {'expert': False}, {'expert_failed': True}, {'execution_status': 'failed'},
])
def test_completion_fields_agree_and_preserve_outcome_separately(change):
    lifecycle = {'expert_complete': change.get('expert', True),
                 'expert_failed': change.get('expert_failed', False)}
    outcome = {'planned_trajectory_completed': change.get('planned', True),
               'outcome_complete': change.get('outcome', True),
               'unapproved_override_used': change.get('override', False),
               'original_expert_lifecycle_status': lifecycle,
               'execution_lifecycle_status': change.get('execution_status')}
    solution = SimpleNamespace(done=change.get('done', True), failed=change.get('failed', False),
                               failure_reason=None, outcome_report=lambda: outcome)
    env = SimpleNamespace(solution=solution)
    info = {'task_metrics': {'task_success': change.get('task_success', True)},
            'task_failure': change.get('task_failure', False)}
    flags = {'terminated': change.get('terminated', False), 'truncated': change.get('truncated', False)}
    example = episode_result(env, info=info, transitions=1, **flags)
    planning = _completion_fields(solution, info, **flags)
    recording = _completion_result(env, info, **flags)
    harness = capture_episode_facts(env, info, transitions=1, **flags)
    for name in ('task_success', 'task_failure', 'solution_done', 'solution_failed',
                 'expert_complete', 'planned_trajectory_completed', 'outcome_complete',
                 'unapproved_override_used', 'original_expert_lifecycle_status',
                 'execution_lifecycle_status', 'terminated', 'truncated',
                 'completion_basis', 'completion_eligible'):
        assert example[name] == planning[name] == recording[name] == harness[name], name
    assert (example['status'] == 'PASS') == planning['success'] == (recording['status'] == 'PASS')
    if change.get('expert') is False or change.get('expert_failed'):
        assert example['policy_complete'] is True
        assert example['completion_eligible'] is False


def test_facts_are_preserved_when_task_fails_before_outcome_policy():
    solution = SimpleNamespace(done=False, failed=False, failure_reason=None,
        outcome_report=lambda: {'planned_trajectory_completed': True, 'outcome_complete': True,
                                'unapproved_override_used': False})
    result = _completion_result(SimpleNamespace(solution=solution), {'is_success': False}, truncated=True)
    assert result['status'] == 'FAIL'
    assert result['planned_trajectory_completed'] is True and result['outcome_complete'] is True
    assert result['failure_reason'] == 'environment_truncated_or_horizon_reached'


def test_recording_example_reports_timeout_and_close_failure_together(tmp_path, monkeypatch, capsys):
    from contextlib import nullcontext
    import json
    import task_env
    from examples.recording import record_expert

    class Env:
        metadata = {}

        def reset(self, *, seed):
            raise record_expert.RunTimeout('synthetic timeout')

        def close(self):
            raise OSError('synthetic close failure')

    monkeypatch.setattr(record_expert, 'bootstrap_imports', lambda: None)
    monkeypatch.setattr(record_expert, 'bounded_process', lambda *args: nullcontext({}))
    monkeypatch.setattr(task_env, 'make_env', lambda *args, **kwargs: Env())
    code = record_expert.main(['--env-id', 'pick-cube-p16-reference-v1', '--provider', 'mujoco',
                               '--output', str(tmp_path / 'absent.h5')])
    report = json.loads(capsys.readouterr().out)
    assert code == 1 and report['status'] == 'ERROR'
    assert report['error']['type'] == 'TIMEOUT'
    assert report['close_attempted'] is True and report['close_succeeded'] is False
    assert report['close_error']['type'] == 'OSError'
    assert report['recording']['status'] == 'NOT_WRITTEN'


def test_record_cli_keeps_execution_and_close_errors(tmp_path, monkeypatch, capsys):
    import json
    import task_env
    from task_env.script.trajectory import record

    class Env:
        def reset(self, *, seed):
            raise TimeoutError('reset timed out')

        def close(self):
            raise OSError('close failed')

    monkeypatch.setattr(task_env, 'make_env', lambda *args, **kwargs: Env())
    code = record.main(['--provider', 'mujoco', '--output', str(tmp_path / 'absent.h5')])
    report = json.loads(capsys.readouterr().out)
    assert code == 1 and report['status'] == 'INVALID'
    assert report['error']['type'] == 'TimeoutError'
    assert report['close_attempted'] and not report['close_succeeded']
    assert report['close_error']['type'] == 'OSError'


def test_planning_horizon_is_reported_as_truncation():
    from task_env.script.trajectory.planning._common import rollout_solution

    class Solution:
        done = failed = False
        failure_reason = None
        stage = 'approach'

        def reset(self, *args):
            pass

        def act(self, *args):
            return 0

        def observe(self, *args):
            pass

    class Env:
        metadata = {}

        def reset(self, **kwargs):
            return None, {'is_success': False}

        def step(self, action):
            return None, 0., False, False, {'is_success': False}

    result = rollout_solution(Env(), horizon=1, seed=31, solution=Solution())
    assert result['truncated'] is True and not result['success']
    assert result['failure_reason'] == 'environment_truncated_or_horizon_reached'


def test_planning_reports_execution_and_close_failures(monkeypatch, capsys):
    import json
    import task_env
    import task_env.tasks.pick_cube as pick_cube
    from task_env.script.trajectory.planning import _common

    class Env:
        def close(self):
            raise OSError('close failed')

    failure = TimeoutError('execution timed out')
    monkeypatch.setattr(task_env, 'make_env', lambda *args, **kwargs: Env())
    monkeypatch.setattr(pick_cube, 'build_readiness_solution', lambda **kwargs: object())
    monkeypatch.setattr(_common, 'rollout_solution', lambda *args, **kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(TimeoutError) as caught:
        _common.run_solution(env_id='pick-cube-p16-reference-v1', requested_backend='cpu',
                             horizon=1, seed=31, summary_name='fake', provider='mujoco')
    assert caught.value is failure
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'ERROR' and report['error']['type'] == 'TimeoutError'
    assert report['close_attempted'] and not report['close_succeeded']
    assert report['close_error']['type'] == 'OSError'
