"""Shared execution loop for task-owned public solutions."""

from __future__ import annotations

from typing import Any


def _completion_fields(solution: Any, info: dict[str, Any], *, terminated: bool,
                      truncated: bool) -> dict[str, Any]:
    """Report task outcome and expert lifecycle without conflating them."""

    metrics = dict(info.get("task_metrics", {}))
    report_fn = getattr(solution, "outcome_report", None)
    outcome = report_fn() if callable(report_fn) else {}
    task_success = bool(metrics.get("task_success", info.get("is_success", False)))
    solution_done = bool(solution.done)
    solution_failed = bool(solution.failed)
    planned = outcome.get("planned_trajectory_completed", info.get("planned_trajectory_completed"))
    outcome_complete = outcome.get("outcome_complete", info.get("outcome_complete"))
    override = outcome.get("unapproved_override_used", info.get("unapproved_override_used"))
    strict_lifecycle = outcome.get(
        "original_expert_lifecycle_status", info.get("original_expert_lifecycle_status")
    )
    expert_complete = outcome.get("expert_complete", info.get("expert_complete"))
    if expert_complete is None and isinstance(strict_lifecycle, dict):
        expert_complete = strict_lifecycle.get("expert_complete")
    if expert_complete is None:
        expert_complete = solution_done and not solution_failed
    if outcome_complete is None:
        success = task_success and solution_done and not solution_failed
    else:
        success = bool(task_success and solution_done and not solution_failed
                       and planned is True and outcome_complete is True and override is False)
    if terminated or truncated:
        success = False
    return {
        "success": success,
        "task_success": task_success,
        "expert_complete": bool(expert_complete),
        "solution_done": solution_done,
        "solution_failed": solution_failed,
        "planned_trajectory_completed": planned,
        "outcome_complete": outcome_complete,
        "unapproved_override_used": override,
        "original_expert_lifecycle_status": strict_lifecycle,
        "readiness_warnings": info.get("readiness_warnings", outcome.get("readiness_warnings", [])),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
    }

def rollout_solution(
    env: Any,
    *,
    horizon: int,
    seed: int,
) -> dict[str, Any]:
    """Run a selected task-owned solution through its public expert boundary.

    Task-owned readiness and guarded progression remain authoritative. This
    helper admits only the selected public reference environment interface.
    """

    if not callable(getattr(env, "step_expert", None)):
        raise TypeError("planning workflow requires a selected task-owned step_expert() route")
    observation, info = env.reset(seed=seed)
    solution = env.solution
    transitions = 0
    stages: list[str] = []
    reward_sum = 0.0
    terminated = truncated = False
    while transitions < horizon and not solution.done and not solution.failed:
        stages.append(solution.stage)
        observation, reward, terminated, truncated, info = env.step_expert()
        reward_sum += float(reward)
        transitions += 1
        if terminated or truncated:
            break
    completion = _completion_fields(solution, info, terminated=terminated, truncated=truncated)
    return {
        "observation": observation,
        "info": info,
        "transitions": transitions,
        "reward_sum": reward_sum,
        "stages": stages,
        **completion,
        "failure_reason": solution.failure_reason,
        "task_metrics": dict(info.get("task_metrics", {})),
    }


def run_solution(
    *,
    env_id: str,
    requested_backend: str,
    horizon: int,
    seed: int,
    summary_name: str,
    provider: str = 'geophys',
) -> dict[str, Any]:
    from task_env import make_env
    if requested_backend not in {'cpu', 'auto'}:
        raise ValueError('selected reference planning requires CPU')
    if env_id not in {'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'}:
        raise ValueError('planning commands admit only the selected public reference UIDs')
    env = make_env(env_id, config={'provider': provider, 'backend': 'cpu', 'horizon': horizon})
    try:
        result = rollout_solution(env, horizon=horizon, seed=seed)
        if not result['success']:
            reason = result['failure_reason'] or 'task_outcome_or_expert_incomplete'
            raise RuntimeError('selected reference expert did not complete: ' + str(reason))
        import json
        print(json.dumps({k:v for k,v in result.items() if k not in {'observation','info'}}, default=str))
        return result
    finally:
        env.close()
