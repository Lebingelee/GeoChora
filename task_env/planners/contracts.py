"""Public task expert contracts used by task-owned solutions."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Mapping, Protocol

import numpy as np
from ..controllers.canonical.execution import ArmTargetExecutionRequestV1


@dataclass(frozen=True)
class ExpertAction:
    """One public action proposed by a task expert."""

    action: np.ndarray
    stage: str
    done: bool = False
    failed: bool = False
    diagnostics: Mapping[str, float | int | bool | str] = field(default_factory=dict)
    control_request: ArmTargetExecutionRequestV1 | None = None
    request_boundary: Mapping[str, object] | None = None
    solution_identity: str | None = None

    def __post_init__(self) -> None:
        action = np.asarray(self.action, dtype=np.float32).reshape(-1).copy()
        action.setflags(write=False)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "stage", str(self.stage))
        if self.request_boundary is not None:
            object.__setattr__(self, "request_boundary", deepcopy(dict(self.request_boundary)))
        if self.solution_identity is not None and (
                type(self.solution_identity) is not str or not self.solution_identity):
            raise ValueError("solution_identity must be a nonempty string when supplied")
        object.__setattr__(self, "done", bool(self.done))
        object.__setattr__(self, "failed", bool(self.failed))
        if self.control_request is not None:
            if not isinstance(self.control_request, ArmTargetExecutionRequestV1):
                raise TypeError("control_request must be ArmTargetExecutionRequestV1")
            self.control_request.validate()
        object.__setattr__(
            self,
            "diagnostics",
            {str(name): value for name, value in self.diagnostics.items()},
        )


def validate_caller_solution_action(
    action: ExpertAction, *, boundary, solution_identity, control_request_mode: str,
    state_boundary=None,
) -> None:
    """Admit an external Solution proposal against the last published boundary.

    Position proposals also bind the typed state boundary; other routes either
    require or forbid the versioned control request specified by their binding.
    This check does not mutate the Solution, environment, or controller.
    """
    if control_request_mode not in {'position', 'required', 'forbidden'}:
        raise ValueError('invalid Solution control request mode')
    if control_request_mode == 'position':
        if action.control_request is not None:
            raise ValueError('Position Solution action does not admit a native control request')
        boundary = boundary()
        if (action.request_boundary is None or action.request_boundary != boundary
                or boundary != state_boundary()):
            raise ValueError('Solution action boundary is stale or mismatched')
    elif control_request_mode == 'required':
        if action.request_boundary != boundary:
            raise ValueError('Solution action boundary is stale or mismatched')
        if action.control_request is None:
            raise ValueError('Solution action requires its versioned control request')
    else:
        if action.control_request is not None:
            raise ValueError('this Solution action route does not admit a control request')
        if action.request_boundary != boundary:
            raise ValueError('Solution action boundary is stale or mismatched')
    if action.solution_identity != solution_identity:
        raise ValueError('Solution action identity differs from the selected task')


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
