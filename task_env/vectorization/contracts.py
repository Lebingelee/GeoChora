"""纯 Python contracts for task-owned homogeneous batch adapters."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import gymnasium as gym
import numpy as np

from ..environment.task_definition import TaskBatchEvaluation


@dataclass(frozen=True)
class BatchResetSample:
    """Task-owned reset sample consumed by the generic batch lifecycle."""

    state: Mapping[str, np.ndarray]
    seeds: Sequence[int | None]
    parameters: Sequence[Mapping[str, Any]]


# Backward-compatible vectorization name.  The semantic result belongs to the
# framework task-definition contract, not to the vector wrapper.
BatchTaskEvaluation = TaskBatchEvaluation


class BatchResetSamplerProtocol(Protocol):
    """Optional batch reset hook owned by the task's reset sampler."""

    def sample_batch(
        self,
        *,
        num_envs: int,
        rng: np.random.Generator,
        seeds: Sequence[int | None] | None,
    ) -> BatchResetSample:
        ...


@dataclass(frozen=True)
class BatchTaskResetResult:
    observation: Any
    infos: list[dict[str, Any]]


@dataclass(frozen=True)
class BatchTaskStepResult:
    observation: Any
    reward: np.ndarray
    terminated: np.ndarray
    truncated: np.ndarray
    infos: list[dict[str, Any]]


class ParallelTaskSpecProtocol(Protocol):
    """Task-owned semantics and runtime construction boundary."""

    uid: str
    num_envs: int
    single_action_space: gym.spaces.Space
    single_observation_space: gym.spaces.Space
    metadata: dict[str, Any]
    parallel_render_provider: object | None

    def reset(self, *, seed=None, options=None, mask=None) -> BatchTaskResetResult:
        ...

    def step(self, actions: Any) -> BatchTaskStepResult:
        ...

    def resource_summary(self) -> dict[str, Any]:
        ...

    def close(self) -> None:
        ...


__all__ = [
    "BatchResetSample",
    "BatchResetSamplerProtocol",
    "BatchTaskEvaluation",
    "BatchTaskResetResult",
    "BatchTaskStepResult",
    "ParallelTaskSpecProtocol",
]
