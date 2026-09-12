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
) -> dict[str, Any]:
    from task_env import make_env

    logger = get_logger(f"task-env-stage14-planning-{summary_name}")

    def create(backend: str):
        config, solution = _build_plan(
            env_id,
            backend,
            horizon,
            camera_obs=False,
            force_limit_N=30.0,
            camera_size=32,
        )
        return make_env(env_id, config=config), solution

    backend, pair = with_backend_fallback(
        requested_backend,
        create,
        logger=logger,
        operation=f"planning:{env_id}",
    )
    env, solution = pair
    try:
        result = rollout_solution(env, solution, horizon=horizon, seed=seed)
        success = bool(result["success"])
        logger.check_or_raise(
            success,
            "task-owned public solution must finish successfully",
            env_id=env_id,
            failure_reason=result["failure_reason"],
            metrics=result["task_metrics"],
        )
        summary = {
            "env_id": env_id,
            "backend": backend,
            "seed": seed,
            "transitions": result["transitions"],
            "stage": solution.stage,
            "success": success,
            "failure_reason": result["failure_reason"],
            "task_metrics": result["task_metrics"],
            "stages": result["stages"],
        }
        logger.success(
            "Stage 14 task planning example completed",
            env_id=env_id,
            backend=backend,
            transitions=result["transitions"],
            metrics=summary["task_metrics"],
        )
        return summary
    finally:
        env.close()
