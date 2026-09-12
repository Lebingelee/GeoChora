"""Current RSL-RL 5.x runner facade."""

from __future__ import annotations

from typing import Any

from .nan_check import install_runner_nan_check


def build_runner(
    env: Any,
    train_cfg: dict[str, Any],
    *,
    log_dir: str | None = None,
    device: str = "cuda:0",
) -> Any:
    """Construct the installed current RSL-RL runner."""

    try:
        from rsl_rl.runners import OnPolicyRunner
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "RSL-RL could not be imported in this learner environment; "
            "verify the installed rsl_rl version, Python compatibility, and "
            "its optional dependencies before running training. "
            f"original error: {type(exc).__name__}: {exc}"
        ) from exc
    runner = OnPolicyRunner(env, train_cfg, log_dir=log_dir, device=str(device))
    install_runner_nan_check(
        runner,
        rollout_steps=int(train_cfg["num_steps_per_env"]),
    )
    return runner


def train(
    env: Any,
    train_cfg: dict[str, Any],
    *,
    iterations: int,
    log_dir: str | None = None,
    device: str = "cuda:0",
    init_at_random_ep_len: bool = False,
) -> Any:
    if int(iterations) < 1:
        raise ValueError("iterations must be positive")
    runner = build_runner(env, train_cfg, log_dir=log_dir, device=device)
    runner.learn(
        num_learning_iterations=int(iterations),
        init_at_random_ep_len=bool(init_at_random_ep_len),
    )
    return runner


__all__ = ["build_runner", "train"]
