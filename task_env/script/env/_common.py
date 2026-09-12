"""Shared orchestration for the environment examples."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .._bootstrap import (
    check_observation,
    deep_merge,
    get_logger,
    json_compatible,
    load_yaml_mapping,
    pick_cube_config,
    resolved_config_summary,
    stage14_output,
    with_backend_fallback,
    write_json,
)


def _observation_leaf_shapes(value: Any, path: str = "") -> dict[str, dict[str, Any]]:
    """Describe a public observation tree without assuming a flat ``Box``."""

    if isinstance(value, Mapping):
        result: dict[str, dict[str, Any]] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            result.update(_observation_leaf_shapes(child, child_path))
        return result
    if isinstance(value, (tuple, list)):
        result = {}
        for index, child in enumerate(value):
            result.update(_observation_leaf_shapes(child, f"{path}[{index}]"))
        return result
    array = np.asarray(value)
    return {
        path or "<root>": {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
        }
    }


def inline_config(env_id: str, backend: str, horizon: int) -> dict[str, Any]:
    if env_id == "pick-cube-v1":
        return pick_cube_config(backend=backend, horizon=horizon)
    return {
        "runtime": {"backend": backend, "broadphase": "n2", "prewarm": False},
        "episode": {"horizon": horizon},
    }


def public_config(
    env_id: str,
    backend: str,
    horizon: int,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve inline example defaults followed by the user YAML mapping."""

    values = deep_merge(inline_config(env_id, backend, horizon), load_yaml_mapping(config_path))
    runtime = dict(values.get("runtime", {}))
    runtime["backend"] = backend
    values["runtime"] = runtime
    return values


def run_single(
    *,
    env_id: str,
    requested_backend: str,
    config: Mapping[str, Any],
    steps: int,
    seed: int,
    summary_name: str,
) -> dict[str, Any]:
    from task_env import make_env

    logger = get_logger(f"task-env-stage14-{summary_name}")

    def create(backend: str):
        values = deep_merge(config, {"runtime": {"backend": backend}})
        return make_env(env_id, config=values)

    backend, env = with_backend_fallback(
        requested_backend,
        create,
        logger=logger,
        operation=f"single:{env_id}",
    )
    rows: list[dict[str, Any]] = []
    try:
        observation, info = env.reset(seed=seed)
        check_observation(observation, env.observation_space)
        for step_index in range(steps):
            # Stage 13 exposes structured action spaces (for example,
            # ``{"torque": Box(...)}``) on the public boundary.  Keep the
            # sampled tree intact instead of assuming every space is a Box.
            action = env.action_space.sample()
            if not env.action_space.contains(action):
                raise ValueError("sampled action is outside the advertised action_space")
            observation, reward, terminated, truncated, info = env.step(action)
            check_observation(observation, env.observation_space)
            if not np.isfinite(float(reward)):
                raise ValueError("TaskEnv reward is not finite")
            rows.append(
                {
                    "step": step_index + 1,
                    "reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                }
            )
            if terminated or truncated:
                break
        summary = {
            "env_id": env_id,
            "backend": backend,
            "seed": seed,
            "steps_requested": steps,
            "steps_completed": len(rows),
            "rows": rows,
            "resolved": resolved_config_summary(env),
            "final_info": json_compatible(info),
        }
        output = stage14_output("env", summary_name, "summary.json")
        write_json(output, summary)
        logger.success(
            "Stage 14 single environment example completed",
            env_id=env_id,
            backend=backend,
            steps_completed=len(rows),
            output=str(output),
        )
        return summary
    finally:
        env.close()


def run_parallel(
    *,
    env_id: str,
    requested_backend: str,
    env_config: Mapping[str, Any],
    num_env: int,
    steps: int,
    seed: int,
    summary_name: str,
) -> dict[str, Any]:
    # Use the lazy top-level factory shown in the public API.  The concrete
    # registry, runtime and IPC implementation stay below this example layer.
    from task_env import make_parallel_env

    logger = get_logger(f"task-env-stage14-{summary_name}")
    from task_env.utils import tree_stack

    def create(backend: str):
        return make_parallel_env(
            uid=env_id,
            env_config=dict(env_config),
            num_env=num_env,
            backend=backend,
            execution="remote",
        )

    backend, env = with_backend_fallback(
        requested_backend,
        create,
        logger=logger,
        operation=f"parallel:{env_id}",
    )
    rows: list[dict[str, Any]] = []
    try:
        observation = env.reset()
        check_observation(observation, env.observation_space, batch=num_env)
        for step_index in range(steps):
            sample = env.action_space.sample()
            actions = tree_stack([sample for _ in range(num_env)])
            env.step_async(actions)
            observation, reward, done, infos = env.step_wait()
            check_observation(observation, env.observation_space, batch=num_env)
            reward = np.asarray(reward)
            done = np.asarray(done)
            if reward.shape != (num_env,) or done.shape != (num_env,) or len(infos) != num_env:
                raise ValueError("parallel step must return B-shaped reward/done/info values")
            if not np.isfinite(reward).all():
                raise ValueError("parallel rewards must be finite")
            rows.append(
                {
                    "step": step_index + 1,
                    "reward_mean": float(reward.mean()),
                    "done_count": int(done.sum()),
                }
            )
        summary = {
            "env_id": env_id,
            "backend": backend,
            "num_env": num_env,
            "seed": seed,
            "steps_requested": steps,
            "steps_completed": len(rows),
            "rows": rows,
            "observation_leaves": _observation_leaf_shapes(observation),
        }
        output = stage14_output("env", summary_name, "summary.json")
        write_json(output, summary)
        logger.success(
            "Stage 14 parallel environment example completed",
            env_id=env_id,
            backend=backend,
            num_env=num_env,
            steps_completed=len(rows),
            output=str(output),
        )
        return summary
    finally:
        env.close()
