"""Shared execution loop for task-owned public solutions."""

from __future__ import annotations

from typing import Any


def _completion_fields(solution: Any, info: dict[str, Any], *, terminated: bool,
                      truncated: bool) -> dict[str, Any]:
    """Report task outcome and expert lifecycle without conflating them."""

    from task_env.script.trajectory.completion import completion_facts

    facts = completion_facts(solution, info, terminated=terminated, truncated=truncated)
    return {**facts, "success": facts["policy_complete"]}


def rollout_solution(
    env: Any,
    *,
    horizon: int,
    seed: int,
    solution: Any = None,
) -> dict[str, Any]:
    """Run a selected task-owned solution through its public expert boundary.

    Task-owned readiness and guarded progression remain authoritative. This
    helper admits only the selected public reference environment interface.
    """

    if solution is None:
        raise TypeError("planning workflow requires a caller-owned Solution")
    observation, info = env.reset(seed=seed)
    solution.reset(observation, info, env.metadata)
    transitions = 0
    stages: list[str] = []
    reward_sum = 0.0
    terminated = truncated = False
    while transitions < horizon and not solution.done and not solution.failed:
        stages.append(solution.stage)
        action = solution.act(observation, info)
        observation, reward, terminated, truncated, info = env.step(action)
        solution.observe(observation, reward, terminated, truncated, info)
        reward_sum += float(reward)
        transitions += 1
        if terminated or truncated:
            break
    if transitions >= horizon and not solution.done and not solution.failed:
        truncated = True
    completion = _completion_fields(solution, info, terminated=terminated, truncated=truncated)
    return {
        "observation": observation,
        "info": info,
        "transitions": transitions,
        "reward_sum": reward_sum,
        "stages": stages,
        **completion,
        "failure_reason": solution.failure_reason or completion["failure_reason"],
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
    import json
    env = None
    result = None
    error = close_error = None
    close_attempted = close_succeeded = False
    try:
        env = make_env(env_id, config={'execution': {'physics_provider': provider, 'physics_backend': 'cpu'}, 'episode': {'horizon': horizon}})
        is_pickcube = env_id == 'pick-cube-p16-reference-v1'
        if is_pickcube:
            from task_env.tasks.pick_cube import build_readiness_solution
            solution = build_readiness_solution(backend='cpu', controller_profile='r3_continuous_v1')
        else:
            from task_env.tasks.nut_assembly.task import build_outcome_solution
            solution = build_outcome_solution(provider=provider)
        result = rollout_solution(env, horizon=horizon, seed=seed, solution=solution)
        if not result['success']:
            reason = result['failure_reason'] or 'task_outcome_or_expert_incomplete'
            raise RuntimeError('selected reference expert did not complete: ' + str(reason))
    except Exception as exc:
        error = exc
    finally:
        if env is not None:
            close_attempted = True
            try:
                env.close()
                close_succeeded = True
            except Exception as exc:
                close_error = exc
    summary = {} if result is None else {k: v for k, v in result.items() if k not in {'observation', 'info'}}
    summary.update(env_id=env_id, provider=provider, requested_backend=requested_backend,
                   backend='cpu', seed=seed, summary_name=summary_name,
                   status='ERROR' if error is not None or close_error is not None else 'PASS',
                   error=None if error is None else {'type': type(error).__name__, 'message': str(error)},
                   close_attempted=close_attempted, close_succeeded=close_succeeded,
                   close_error=None if close_error is None else
                   {'type': type(close_error).__name__, 'message': str(close_error)})
    print(json.dumps(summary, default=str))
    if error is not None:
        if close_error is not None:
            error.add_note(f'close also failed: {close_error!r}')
        raise error
    if close_error is not None:
        raise close_error
    return result
