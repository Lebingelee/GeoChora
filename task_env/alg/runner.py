"""Task-independent PPO runner selection for registered homogeneous TaskEnv."""

from __future__ import annotations

from typing import Any


_PPO_ENV_ALIASES = {
    "pendulum": "pendulum-v1",
    "go2_walk": "go2-walk-v1",
    "go2_walk_deploy": "go2-walk-deploy-v1",
    "go2_walk_deploy_height": "go2-walk-deploy-height-v1",
}


def canonical_ppo_env_id(env_id: str) -> str:
    """Normalize a documented task alias without adding task-specific routes."""

    value = str(env_id).strip()
    if not value:
        raise ValueError("env_id cannot be empty")
    return _PPO_ENV_ALIASES.get(value, value)


def train_registered_ppo(*, env_id: str, args: Any) -> dict[str, Any]:
    """Run current RSL PPO through a registered parallel environment."""

    canonical_id = canonical_ppo_env_id(env_id)
    from task_env import ENV_REGISTRY, PARALLEL_ENV_REGISTRY

    if canonical_id not in ENV_REGISTRY.uids():
        raise ValueError(f"unknown registered env-id: {canonical_id!r}")
    if canonical_id not in PARALLEL_ENV_REGISTRY.uids():
        raise ValueError(
            f"env-id {canonical_id!r} has no homogeneous parallel registration; "
            "register the task with @register_parallel_env() before RSL PPO"
        )
    from .rsl_rl.training import RslPpoOptions, train

    args.env_id = canonical_id
    options = RslPpoOptions.from_namespace(args)
    checkpoint = train(options)
    return {
        "env_id": options.env_id,
        "num_env": options.num_env,
        "iterations": options.iterations,
        "rollout_steps": options.rollout_steps,
        "checkpoint": str(checkpoint),
        "output_dir": str(options.output_dir),
    }


__all__ = ["canonical_ppo_env_id", "train_registered_ppo"]
