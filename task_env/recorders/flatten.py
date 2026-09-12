"""Task-agnostic Gym tree codec used by the transition wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gymnasium.spaces import Dict, Space
from gymnasium.spaces.utils import flatten, flatten_space, unflatten

from .contracts import RecorderConfig


def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.split(".") if part)


class TreeCodec:
    """Replace selected observation subtrees with reversible flat Box spaces."""

    def __init__(self, observation_space: Space, action_space: Space, config: RecorderConfig) -> None:
        self._source_observation_space = observation_space
        self._source_action_space = action_space
        self._selected = tuple(_path_parts(path) for path in config.flatten_observation_paths)
        for path in self._selected:
            if self._space_at(observation_space, path) is None:
                raise ValueError(f"flatten observation path does not exist: {'.'.join(path)}")
        for index, path in enumerate(self._selected):
            if any(path[: len(other)] == other or other[: len(path)] == path for other in self._selected[:index]):
                raise ValueError("flatten observation paths cannot overlap")
        self.observation_space = self._rewrite_space(observation_space, ())
        self.action_space = flatten_space(action_space) if config.flatten_action else action_space
        self._flatten_action = config.flatten_action

    @staticmethod
    def _space_at(space: Space, path: tuple[str, ...]) -> Space | None:
        cursor = space
        for part in path:
            if not isinstance(cursor, Dict) or part not in cursor.spaces:
                return None
            cursor = cursor.spaces[part]
        return cursor

    def _is_selected(self, prefix: tuple[str, ...]) -> bool:
        return prefix in self._selected

    def _rewrite_space(self, space: Space, prefix: tuple[str, ...]) -> Space:
        if self._is_selected(prefix):
            return flatten_space(space)
        if not isinstance(space, Dict):
            return space
        return Dict({name: self._rewrite_space(child, prefix + (name,)) for name, child in space.spaces.items()})

    def encode_obs(self, observation: Any) -> Any:
        return self._encode_obs(self._source_observation_space, observation, ())

    def _encode_obs(self, space: Space, value: Any, prefix: tuple[str, ...]) -> Any:
        if self._is_selected(prefix):
            return flatten(space, value)
        if not isinstance(space, Dict):
            return value
        if not isinstance(value, Mapping):
            raise ValueError(f"observation at {'.'.join(prefix)} must be a mapping")
        return {name: self._encode_obs(child, value[name], prefix + (name,)) for name, child in space.spaces.items()}

    def decode_action(self, action: Any) -> Any:
        if not self.action_space.contains(action):
            raise ValueError("policy action does not belong to wrapper action_space")
        return unflatten(self._source_action_space, action) if self._flatten_action else action


__all__ = ["TreeCodec"]
