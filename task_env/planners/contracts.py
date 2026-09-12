"""Public task expert contracts used by task-owned solutions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

import numpy as np


@dataclass(frozen=True)
class ExpertAction:
    """One public action proposed by a task expert."""

    action: np.ndarray
    stage: str
    done: bool = False
    failed: bool = False
    diagnostics: Mapping[str, float | int | bool | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        action = np.asarray(self.action, dtype=np.float32).reshape(-1).copy()
        action.setflags(write=False)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "stage", str(self.stage))
        object.__setattr__(self, "done", bool(self.done))
        object.__setattr__(self, "failed", bool(self.failed))
        object.__setattr__(
            self,
            "diagnostics",
            {str(name): value for name, value in self.diagnostics.items()},
        )


class TaskExpertSolver(Protocol):
    """External task policy that only consumes public env observations and info."""

    @property
    def stage(self) -> str: ...

    @property
    def done(self) -> bool: ...

    @property
    def failed(self) -> bool: ...

    def reset(self, observation, info: Mapping[str, object]) -> None: ...

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction: ...

    def observe(
        self,
        observation,
        reward: float,
        terminated: bool,
        truncated: bool,
        info: Mapping[str, object],
    ) -> None: ...
