"""Small tree utilities shared by TaskEnv vector and SB3 wrappers.

These helpers operate only on public Gymnasium spaces and NumPy values.  They
must remain free of Taichi imports so they are safe in the SB3 learner process.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import gymnasium as gym
import numpy as np


def tree_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): tree_copy(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(tree_copy(item) for item in value)
    if isinstance(value, list):
        return [tree_copy(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.copy()
    return value


def tree_index(value: Any, index: int) -> Any:
    """Extract one vector slot while preserving its tree structure."""

    if isinstance(value, Mapping):
        return {str(key): tree_index(item, index) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(tree_index(item, index) for item in value)
    if isinstance(value, list):
        return [tree_index(item, index) for item in value]
    return np.asarray(value)[int(index)].copy()


def tree_stack(values: list[Any]) -> Any:
    """Stack same-shaped per-slot trees along their leading batch axis."""

    if not values:
        raise ValueError("cannot stack an empty tree sequence")
    first = values[0]
    if isinstance(first, Mapping):
        keys = tuple(first.keys())
        if any(tuple(value.keys()) != keys for value in values):
            raise ValueError("tree mapping keys changed across vector slots")
        return {key: tree_stack([value[key] for value in values]) for key in keys}
    if isinstance(first, tuple):
        width = len(first)
        if any(not isinstance(value, tuple) or len(value) != width for value in values):
            raise ValueError("tree tuple structure changed across vector slots")
        return tuple(tree_stack([value[index] for value in values]) for index in range(width))
    if isinstance(first, list):
        width = len(first)
        if any(not isinstance(value, list) or len(value) != width for value in values):
            raise ValueError("tree list structure changed across vector slots")
        return [tree_stack([value[index] for value in values]) for index in range(width)]
    return np.stack([np.asarray(value) for value in values], axis=0)


def tree_set_index(value: Any, index: int, replacement: Any) -> None:
    """Replace one vector slot in a mutable batched tree."""

    if isinstance(value, Mapping):
        if not isinstance(replacement, Mapping) or tuple(value.keys()) != tuple(replacement.keys()):
            raise ValueError("replacement tree does not match the batched tree")
        for key in value:
            tree_set_index(value[key], index, replacement[key])
        return
    if isinstance(value, tuple):
        if not isinstance(replacement, tuple) or len(value) != len(replacement):
            raise ValueError("replacement tuple does not match the batched tree")
        for current, item in zip(value, replacement):
            tree_set_index(current, index, item)
        return
    np.asarray(value)[int(index)] = replacement


def validate_batched_tree(value: Any, space: gym.spaces.Space, batch_size: int) -> None:
    """Validate a `(B, ...)` value against a single-environment Gym space."""

    if isinstance(space, gym.spaces.Dict):
        if not isinstance(value, Mapping) or tuple(value.keys()) != tuple(space.spaces.keys()):
            raise ValueError("batched value keys do not match Dict space")
        for key, child in space.spaces.items():
            validate_batched_tree(value[key], child, batch_size)
        return
    if isinstance(space, gym.spaces.Tuple):
        if not isinstance(value, (tuple, list)) or len(value) != len(space.spaces):
            raise ValueError("batched value tuple does not match Tuple space")
        for item, child in zip(value, space.spaces):
            validate_batched_tree(item, child, batch_size)
        return
    array = np.asarray(value)
    expected = (int(batch_size), *space.shape)
    if array.shape != expected:
        raise ValueError(f"batched value shape must be {expected}, got {array.shape}")
    if not np.issubdtype(array.dtype, np.number) or not np.isfinite(array).all():
        raise ValueError("batched Box values must be finite numeric arrays")
    if any(not space.contains(array[index]) for index in range(int(batch_size))):
        raise ValueError("batched Box value is outside its declared space")


__all__ = [
    "tree_copy",
    "tree_index",
    "tree_set_index",
    "tree_stack",
    "validate_batched_tree",
]
