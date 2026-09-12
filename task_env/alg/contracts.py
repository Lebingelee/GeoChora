"""Framework-neutral learner contracts.

These contracts describe ordering and shape at the learner boundary.  They do
not contain task names and do not import a learner library.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import gymnasium as gym
import numpy as np
from gymnasium.spaces.utils import flatten, flatten_space, unflatten

from ..utils.tree import tree_index, tree_stack


@dataclass(frozen=True)
class LearnerTensorContract:
    """Deterministic raw-tree to policy-tensor mapping."""

    observation_space: gym.spaces.Space
    action_space: gym.spaces.Space
    observation_group: str = "policy"
    dtype: str = "float32"
    normalization: str = "none"
    schema_id: str = "task-env-learner-contract-v1"

    def __post_init__(self) -> None:
        if not str(self.observation_group).strip():
            raise ValueError("observation_group cannot be empty")
        if self.dtype not in {"float32", "float64"}:
            raise ValueError("learner tensor dtype must be float32 or float64")
        if self.normalization not in {"none", "declared_external"}:
            raise ValueError("unsupported learner normalization policy")
        if not str(self.schema_id).strip():
            raise ValueError("learner contract schema_id cannot be empty")

    @classmethod
    def from_spaces(
        cls,
        observation_space: gym.spaces.Space,
        action_space: gym.spaces.Space,
        **kwargs: Any,
    ) -> "LearnerTensorContract":
        return cls(
            observation_space=observation_space,
            action_space=action_space,
            **kwargs,
        )

    @property
    def observation_dim(self) -> int:
        return int(np.prod(flatten_space(self.observation_space).shape, dtype=np.int64))

    @property
    def action_dim(self) -> int:
        return int(np.prod(flatten_space(self.action_space).shape, dtype=np.int64))

    def flatten_observation(self, value: Any, batch_size: int) -> np.ndarray:
        rows = [flatten(self.observation_space, tree_index(value, index)) for index in range(batch_size)]
        result = np.stack(rows, axis=0)
        return result.astype(np.float64 if self.dtype == "float64" else np.float32, copy=False)

    def flatten_action(self, value: Any, batch_size: int) -> np.ndarray:
        rows = [flatten(self.action_space, tree_index(value, index)) for index in range(batch_size)]
        result = np.stack(rows, axis=0)
        return result.astype(np.float64 if self.dtype == "float64" else np.float32, copy=False)

    def validate_flat_action(self, value: Any, batch_size: int) -> np.ndarray:
        result = np.asarray(value, dtype=np.float32)
        expected = (int(batch_size), self.action_dim)
        if result.shape != expected:
            raise ValueError(f"learner action must have shape {expected}, got {result.shape}")
        if not np.isfinite(result).all():
            raise ValueError("learner action must be finite")
        return result

    def unflatten_action(self, value: Any, batch_size: int) -> Any:
        array = self.validate_flat_action(value, batch_size)
        width = self.action_dim
        return tree_stack(
            [
                unflatten(self.action_space, array[index].reshape(width))
                for index in range(int(batch_size))
            ]
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "observation_group": self.observation_group,
            "observation_dim": self.observation_dim,
            "action_dim": self.action_dim,
            "dtype": self.dtype,
            "normalization": self.normalization,
            "observation_space": repr(self.observation_space),
            "action_space": repr(self.action_space),
        }


__all__ = ["LearnerTensorContract"]
