"""SB3 learner-side wrappers for structured TaskEnv spaces.

The wrapped vector environment keeps its raw observation/action tree.  This
wrapper is the only boundary that converts a structured tree to the flat Box
contract expected by ``PPO("MlpPolicy")``.  It is intentionally independent
of Taichi and of the reporter transport.
"""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium.spaces.utils import flatten, flatten_space, unflatten
from stable_baselines3.common.vec_env import VecEnv, VecEnvWrapper

from .tree import tree_index, tree_stack, tree_copy


def _flatten_batch(value: Any, space: gym.spaces.Space, batch_size: int) -> np.ndarray:
    if isinstance(space, (gym.spaces.Dict, gym.spaces.Tuple)):
        rows = [flatten(space, tree_index(value, index)) for index in range(batch_size)]
        return np.stack(rows, axis=0).astype(np.float32, copy=False)
    array = np.asarray(value, dtype=space.dtype)
    expected = (batch_size, *space.shape)
    if array.shape != expected:
        raise ValueError(f"vector value must have shape {expected}, got {array.shape}")
    return array.reshape((batch_size, -1)).astype(np.float32, copy=False)


def _unflatten_batch(value: np.ndarray, space: gym.spaces.Space, batch_size: int) -> Any:
    array = np.asarray(value, dtype=np.float32)
    expected = (batch_size, int(np.prod(flatten_space(space).shape, dtype=np.int64)))
    if array.shape != expected:
        raise ValueError(f"flat vector value must have shape {expected}, got {array.shape}")
    if isinstance(space, (gym.spaces.Dict, gym.spaces.Tuple)):
        return tree_stack([unflatten(space, array[index]) for index in range(batch_size)])
    return array.reshape((batch_size, *space.shape)).astype(space.dtype, copy=False)


class SB3FlattenVecWrapper(VecEnvWrapper):
    """Flatten structured observation/action trees only at the SB3 boundary."""

    def __init__(self, venv: VecEnv) -> None:
        self.raw_observation_space = venv.observation_space
        self.raw_action_space = venv.action_space
        super().__init__(
            venv,
            observation_space=flatten_space(self.raw_observation_space),
            action_space=flatten_space(self.raw_action_space),
        )
        self.metadata = dict(getattr(venv, "metadata", {}))
        self.metadata.update(
            {
                "sb3_wrapper": "flatten-v1",
                "raw_observation_space": str(self.raw_observation_space),
                "raw_action_space": str(self.raw_action_space),
            }
        )

    def reset(self) -> np.ndarray:
        observation = self.venv.reset()
        return _flatten_batch(observation, self.raw_observation_space, self.num_envs)

    def step_async(self, actions: np.ndarray) -> None:
        self.venv.step_async(
            _unflatten_batch(actions, self.raw_action_space, self.num_envs)
        )

    def step_wait(self):
        observation, rewards, dones, infos = self.venv.step_wait()
        for info in infos:
            terminal_observation = info.get("terminal_observation")
            if terminal_observation is not None:
                info["terminal_observation"] = flatten(
                    self.raw_observation_space,
                    terminal_observation,
                ).astype(np.float32, copy=False)
        return (
            _flatten_batch(observation, self.raw_observation_space, self.num_envs),
            rewards,
            dones,
            infos,
        )


__all__ = ["SB3FlattenVecWrapper"]
