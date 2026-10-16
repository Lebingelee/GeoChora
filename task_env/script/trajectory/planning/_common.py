"""Shared execution loop for task-owned public solutions."""

from __future__ import annotations

from typing import Any

from ..._bootstrap import get_logger, with_backend_fallback
from .._task_plans import _build_plan


def rollout_solution(
    env: Any,
    solution: Any,
    *,
    horizon: int,
    seed: int,
) -> dict[str, Any]:
    """Run one task-owned solution through the public ``env.step`` boundary.

    The planning example and the historical Stage 8--10 smoke tests must
    exercise the same task route.  This helper deliberately owns no recorder
    lifecycle: callers that wrap ``env`` can end recording after a solution
    reaches its task-owned success endpoint.
    """

    if hasattr(env, 'step_expert'):
        observation, info = env.reset(seed=seed)
        stages = []
        reward_sum = 0.
        while not env.solution.done and not env.solution.failed and not env._stopped:
            stages.append(env.solution.stage)
            observation, reward, terminated, truncated, info = env.step_expert()
            reward_sum += reward
        return {'observation': observation, 'info': info, 'transitions': env.state.control_step,
            'reward_sum': reward_sum, 'stages': stages,
            'success': bool(env.solution.done and not env.solution.failed and info.get('is_success')),
            'failure_reason': env.solution.failure_reason, 'task_metrics': dict(info['task_metrics'])}
    # Explicit legacy environment objects remain usable by historical tests only.
    observation, info = env.reset(seed=seed)
    solution.reset(observation, info, env.metadata)
    transitions = 0
    stages: list[str] = []
    reward_sum = 0.0
    while not solution.done and not solution.failed:
        proposal = solution.act(observation, info)
        stages.append(proposal.stage)
        observation, reward, terminated, truncated, info = env.step(proposal.action)
        reward_sum += float(reward)
        solution.observe(observation, reward, terminated, truncated, info)
        transitions += 1
        if transitions > horizon:
            raise RuntimeError("task solution exceeded the script horizon")
    return {
        "observation": observation,
        "info": info,
        "transitions": transitions,
        "reward_sum": reward_sum,
        "stages": stages,
        "success": bool(solution.done and not solution.failed and info.get("is_success", False)),
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
    config, _ = _build_plan(env_id, 'cpu', horizon)
    config['provider'] = provider
    env = make_env(env_id, config=config)
    try:
        result = rollout_solution(env, env.solution, horizon=horizon, seed=seed)
        if not result['success']:
            raise RuntimeError('selected reference expert did not complete: ' + str(result['failure_reason']))
        import json
        print(json.dumps({k:v for k,v in result.items() if k not in {'observation','info'}}, default=str))
        return result
    finally:
        env.close()
