"""Immutable in-memory transition trajectory with the Stage 9 length invariant."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

import numpy as np


def copy_tree(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): copy_tree(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [copy_tree(item) for item in value]
    if isinstance(value, np.ndarray):
        return np.asarray(value).copy()
    if isinstance(value, np.generic):
        return value.item()
    return value


def tree_nbytes(value: Any) -> int:
    if isinstance(value, dict):
        return sum(tree_nbytes(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return sum(tree_nbytes(item) for item in value)
    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    return 0


@dataclass(frozen=True)
class FrozenTrajectory:
    observations: tuple[Any, ...]
    actions: tuple[np.ndarray, ...]
    universal_actions: tuple[np.ndarray, ...]
    rewards: tuple[float, ...]
    successes: tuple[bool, ...]
    terminated: tuple[bool, ...]
    truncated: tuple[bool, ...]
    infos: tuple[dict[str, Any], ...]
    reset_info: dict[str, Any]
    record_metadata: dict[str, Any]
    stop_reason: str

    @property
    def transition_count(self) -> int:
        return len(self.actions)

    def validate(self) -> None:
        count = self.transition_count
        if len(self.observations) != count + 1:
            raise ValueError("trajectory must contain T+1 observations")
        for name in ("universal_actions", "rewards", "successes", "terminated", "truncated", "infos"):
            if len(getattr(self, name)) != count:
                raise ValueError(f"trajectory {name} must contain T values")


__all__ = ["FrozenTrajectory", "copy_tree", "tree_nbytes"]
