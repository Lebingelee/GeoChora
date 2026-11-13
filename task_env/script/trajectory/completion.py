"""Project task and Solution facts for ordinary trajectory callers.

The selected outcome policy and the stricter original expert lifecycle are
separate facts. Harness execution/cleanup validity remains owned by Harness.
"""
from collections.abc import Mapping


def completion_facts(solution, info, *, terminated=False, truncated=False):
    info = dict(info or {})
    metrics = dict(info.get('task_metrics', {}))
    report = getattr(solution, 'outcome_report', None)
    outcome = report() if callable(report) else {}
    if not isinstance(outcome, Mapping):
        raise TypeError('solution outcome_report must return a mapping')
    task_success = bool(metrics.get('task_success', info.get('is_success', False)))
    task_failure = bool(info.get('task_failure', False))
    done, failed = bool(solution.done), bool(solution.failed)
    planned = outcome.get('planned_trajectory_completed', info.get('planned_trajectory_completed'))
    outcome_complete = outcome.get('outcome_complete', info.get('outcome_complete'))
    override = outcome.get('unapproved_override_used', info.get('unapproved_override_used'))
    lifecycle = outcome.get('original_expert_lifecycle_status', info.get('original_expert_lifecycle_status'))
    expert = outcome.get('expert_complete', info.get('expert_complete'))
    if expert is None and isinstance(lifecycle, Mapping):
        expert = lifecycle.get('expert_complete')
    if expert is None:
        expert = done and not failed
    basis = ('selected_expert_completion' if outcome_complete is None
             else 'outcome_policy_and_full_planned_route')
    reason = None
    if terminated:
        reason = 'environment_terminated'
    elif truncated:
        reason = 'environment_truncated_or_horizon_reached'
    elif failed:
        reason = getattr(solution, 'failure_reason', None) or 'selected_policy_failed'
    elif not done:
        reason = 'selected_policy_incomplete'
    elif task_failure:
        reason = 'task_failure'
    elif not task_success:
        reason = 'task_success_false'
    elif outcome_complete is not None:
        if planned is not True:
            reason = 'planned_trajectory_incomplete'
        elif outcome_complete is not True:
            reason = 'outcome_incomplete'
        elif override is not False:
            reason = 'unapproved_override_used_or_unreported'
    policy_complete = reason is None
    completion_eligible = bool(policy_complete and expert
        and not (isinstance(lifecycle, Mapping) and lifecycle.get('expert_failed') is True)
        and outcome.get('execution_lifecycle_status') != 'failed')
    return {
        'task_success': task_success, 'task_failure': task_failure,
        'solution_done': done, 'solution_failed': failed, 'expert_complete': bool(expert),
        'planned_trajectory_completed': planned, 'outcome_complete': outcome_complete,
        'unapproved_override_used': override, 'original_expert_lifecycle_status': lifecycle,
        'execution_lifecycle_status': outcome.get('execution_lifecycle_status'),
        'readiness_warnings': outcome.get('readiness_warnings', info.get('readiness_warnings', [])),
        'terminated': bool(terminated), 'truncated': bool(truncated),
        'completion_basis': basis, 'policy_complete': policy_complete,
        'completion_eligible': completion_eligible, 'failure_reason': reason,
    }
