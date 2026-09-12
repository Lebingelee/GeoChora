"""Generic SB3 runner facade over the existing TaskEnv adapter."""

from __future__ import annotations

from typing import Any


def build_ppo(
    vector_env: Any,
    *,
    policy: str = "MlpPolicy",
    device: str = "cuda",
    **kwargs: Any,
) -> Any:
    try:
        from stable_baselines3 import PPO
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
        raise RuntimeError("SB3 is not available in this learner environment") from exc
    return PPO(policy, vector_env, device=str(device), **kwargs)


def train(
    vector_env: Any,
    *,
    total_timesteps: int,
    device: str = "cuda",
    **kwargs: Any,
) -> Any:
    if int(total_timesteps) < 1:
        raise ValueError("total_timesteps must be positive")
    model = build_ppo(vector_env, device=device, **kwargs)
    model.learn(total_timesteps=int(total_timesteps))
    return model


__all__ = ["build_ppo", "train"]
