"""Standalone predicate values; legacy schema identity is preserved.

TaskEnv retains its own runtime type. Validation consumes observations and
exports status/value/reason mappings without importing an environment.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class PredicateResult:
    """One typed predicate value or an explicit unavailability state."""

    status: str
    value: bool | np.ndarray | None = None
    reason: str | None = None
    schema_version: str = "task-predicate-result-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "task-predicate-result-v1":
            raise ValueError("unsupported TaskPredicateResult schema")
        if self.status not in {"available", "unavailable", "no_evaluator"}:
            raise ValueError(f"unsupported task predicate status: {self.status!r}")
        if self.status == "available":
            if isinstance(self.value, np.ndarray):
                values = np.asarray(self.value)
                if values.dtype.kind != "b" or values.ndim != 1:
                    raise TypeError("batch predicate values must be a one-dimensional bool array")
                values = values.copy()
                values.setflags(write=False)
                object.__setattr__(self, "value", values)
            elif not isinstance(self.value, (bool, np.bool_)):
                raise TypeError("available predicate values must be boolean")
            else:
                object.__setattr__(self, "value", bool(self.value))
            if self.reason is not None:
                raise ValueError("available predicate results cannot carry an unavailable reason")
        else:
            if self.value is not None:
                raise ValueError("unavailable predicate results cannot carry a value")
            if self.status == "unavailable" and (
                not isinstance(self.reason, str) or not self.reason.strip()
            ):
                raise ValueError("unavailable predicate results require a reason")
            if self.status == "no_evaluator" and self.reason is not None:
                raise ValueError("no_evaluator is an evaluator status, not a missing-data reason")

    @classmethod
    def available(cls, value: bool | np.ndarray) -> "PredicateResult":
        return cls("available", value=value)

    @classmethod
    def unavailable(cls, reason: str) -> "PredicateResult":
        return cls("unavailable", reason=reason)

    @classmethod
    def no_evaluator(cls) -> "PredicateResult":
        return cls("no_evaluator")
