"""Framework-owned task-definition and state-view contracts.

Task definitions describe semantics.  They do not own the scalar or batch
episode lifecycle.  ``TaskStateView`` is the common value-facing boundary used
by both runtime paths; scalar and batch implementations differ only in the
leading batch dimension of their arrays.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, ClassVar, Protocol, Sequence, runtime_checkable

import numpy as np

from ..artifacts.contracts import Timebase
from ..artifacts.state import (
    NativeIntervalEvidence,
    StateBoundaryIdentity,
    StateSampleClock,
)
from .types import AppliedControl, RuntimeSnapshot, TaskEvaluation


@runtime_checkable
class TaskStateView(Protocol):
    """Named runtime state consumed by task semantics.

    Scalar views expose arrays such as ``qpos.shape == (N,)``; batch views
    expose ``qpos.shape == (B, N)``.  The task definition may use NumPy
    broadcasting to implement both paths without constructing ``B`` scalar
    ``RuntimeSnapshot`` objects.
    """

    qpos: np.ndarray
    qvel: np.ndarray
    qacc: np.ndarray | None
    ctrl: np.ndarray | None
    body_xpos: np.ndarray | None
    body_xquat: np.ndarray | None
    site_xpos: np.ndarray | None
    site_xquat: np.ndarray | None

    @property
    def batch_size(self) -> int:
        ...

    @property
    def is_batch(self) -> bool:
        ...

    def get(self, name: str) -> np.ndarray:
        ...


@dataclass(frozen=True)
class TaskBatchEvaluation:
    """Batch-valued semantic result owned by the task-definition contract."""

    reward: np.ndarray
    success: np.ndarray
    failure: np.ndarray
    truncated: np.ndarray
    metrics: Mapping[str, np.ndarray] = field(default_factory=dict)
    reward_terms: Mapping[str, np.ndarray] = field(default_factory=dict)


def _freeze_action_value(value: Any, *, path: str = "requested_action") -> Any:
    """Copy a task-specific action value into an immutable context payload."""

    if isinstance(value, np.ndarray):
        array = np.asarray(value).copy()
        if array.dtype.kind not in "biufSU":
            raise TypeError(f"{path} contains an unsupported array dtype {array.dtype}")
        if array.dtype.kind in "f" and not np.isfinite(array).all():
            raise ValueError(f"{path} must contain only finite values")
        array.setflags(write=False)
        return array
    if isinstance(value, np.generic):
        return _freeze_action_value(value.item(), path=path)
    if isinstance(value, Mapping):
        frozen = {}
        for raw_name, child in value.items():
            if (
                not isinstance(raw_name, str)
                or not raw_name.strip()
                or raw_name != raw_name.strip()
            ):
                raise ValueError(
                    f"{path} mapping keys must be trimmed nonempty strings"
                )
            if raw_name in frozen:
                raise ValueError(f"{path} contains duplicate normalized keys")
            frozen[raw_name] = _freeze_action_value(
                child, path=f"{path}.{raw_name}"
            )
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(
            _freeze_action_value(child, path=f"{path}[{index}]")
            for index, child in enumerate(value)
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite values")
        return float(value)
    raise TypeError(f"{path} contains unsupported value {type(value).__name__}")


@dataclass(frozen=True)
class TaskEvaluationContextV1:
    """Read-only inputs for one explicit task predicate read.

    ``timebase`` is the declared evaluation cadence. ``native_interval`` is
    optional measured evidence for one interval; the two are kept separate so
    expected time is never reported as observed time. This value does not own
    or commit task memory.
    """

    state: RuntimeSnapshot | TaskStateView
    requested_action: Any = None
    action_schema_id: str | None = None
    applied_control: AppliedControl | None = None
    elapsed_steps: int | np.ndarray = 0
    previous_state: RuntimeSnapshot | TaskStateView | None = None
    timebase: Timebase | None = None
    native_interval: NativeIntervalEvidence | None = None
    boundary_identity: StateBoundaryIdentity | None = None
    sample_clock: StateSampleClock | None = None
    schema_version: str = "task-evaluation-context-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "task-evaluation-context-v1":
            raise ValueError("unsupported TaskEvaluationContext schema")
        view = as_task_state_view(self.state)
        object.__setattr__(self, "state", view)
        if self.previous_state is not None:
            previous = as_task_state_view(self.previous_state)
            if previous.is_batch != view.is_batch or (
                previous.is_batch and previous.batch_size != view.batch_size
            ):
                raise ValueError("previous and current task state cardinality must match")
            object.__setattr__(self, "previous_state", previous)

        if view.is_batch:
            steps = np.asarray(self.elapsed_steps)
            if steps.shape != (view.batch_size,) or steps.dtype.kind not in "iu":
                raise ValueError("batch elapsed_steps must be an integer array shaped (B,)")
            if np.any(steps < 0):
                raise ValueError("elapsed_steps cannot be negative")
            steps = steps.astype(np.int64, copy=True)
            steps.setflags(write=False)
            object.__setattr__(self, "elapsed_steps", steps)
        else:
            if isinstance(self.elapsed_steps, (bool, np.bool_)) or not isinstance(
                self.elapsed_steps, (int, np.integer)
            ):
                raise TypeError("scalar elapsed_steps must be an integer")
            if int(self.elapsed_steps) < 0:
                raise ValueError("elapsed_steps cannot be negative")
            object.__setattr__(self, "elapsed_steps", int(self.elapsed_steps))

        action = _freeze_action_value(self.requested_action)
        object.__setattr__(self, "requested_action", action)
        if action is not None and not isinstance(self.action_schema_id, str):
            raise ValueError("requested_action requires a stable action_schema_id")
        if self.action_schema_id is not None:
            if (
                not isinstance(self.action_schema_id, str)
                or not self.action_schema_id.strip()
                or self.action_schema_id != self.action_schema_id.strip()
            ):
                raise ValueError("action_schema_id must be a stable nonempty token")
        if self.applied_control is not None and not isinstance(
            self.applied_control, AppliedControl
        ):
            raise TypeError("applied_control must use the existing AppliedControl contract")

        if self.timebase is not None:
            if not isinstance(self.timebase, Timebase):
                raise TypeError("timebase must use the existing Timebase contract")
            self.timebase.validate()
        if self.native_interval is not None:
            if not isinstance(self.native_interval, NativeIntervalEvidence):
                raise TypeError(
                    "native_interval must use the existing NativeIntervalEvidence contract"
                )
            self.native_interval.validate()
            if self.timebase is not None and (
                self.native_interval.physics_dt != self.timebase.physics_dt
                or self.native_interval.control_substeps
                != self.timebase.control_substeps
            ):
                raise ValueError("measured interval disagrees with the declared Timebase")

        boundary = self.boundary_identity
        clock = self.sample_clock
        if self.native_interval is not None:
            interval_boundary = self.native_interval.boundary_after
            interval_clock = self.native_interval.evaluation_end
            if boundary is None:
                boundary = interval_boundary
                object.__setattr__(self, "boundary_identity", boundary)
            elif boundary != interval_boundary:
                raise ValueError("context boundary disagrees with native interval end")
            if clock is None:
                clock = interval_clock
                object.__setattr__(self, "sample_clock", clock)
            elif clock != interval_clock:
                raise ValueError("context sample clock disagrees with native interval end")
        if (boundary is None) != (clock is None):
            raise ValueError("boundary_identity and sample_clock must be supplied together")
        if boundary is not None:
            if not isinstance(boundary, StateBoundaryIdentity):
                raise TypeError("boundary_identity must use StateBoundaryIdentity")
            if not isinstance(clock, StateSampleClock):
                raise TypeError("sample_clock must use StateSampleClock")
            boundary.validate()
            clock.validate()
            if clock.clock_domain != "evaluation_boundary":
                raise ValueError("task evaluation context requires an evaluation-boundary clock")
            if clock.sample_index != boundary.control_step:
                raise ValueError("context sample clock and boundary control step disagree")

    @property
    def declared_control_interval_s(self) -> float | None:
        """Authored cadence, if supplied; not a measurement."""

        return None if self.timebase is None else float(self.timebase.control_dt)

    @property
    def measured_control_interval_s(self) -> float | None:
        """Measured boundary duration, available only with native evidence."""

        if self.native_interval is None:
            return None
        return float(
            self.native_interval.evaluation_end.simulation_time_s
            - self.native_interval.evaluation_start.simulation_time_s
        )


@dataclass(frozen=True)
class TaskPredicateResultV1:
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
    def available(cls, value: bool | np.ndarray) -> "TaskPredicateResultV1":
        return cls("available", value=value)

    @classmethod
    def unavailable(cls, reason: str) -> "TaskPredicateResultV1":
        return cls("unavailable", reason=reason)

    @classmethod
    def no_evaluator(cls) -> "TaskPredicateResultV1":
        return cls("no_evaluator")


@dataclass(frozen=True)
class TaskPredicateEvaluationV1:
    """Explicit result set from the current read-only predicate evaluator."""

    evaluator_status: str
    predicates: Mapping[str, TaskPredicateResultV1] = field(default_factory=dict)
    schema_version: str = "task-predicate-evaluation-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "task-predicate-evaluation-v1":
            raise ValueError("unsupported TaskPredicateEvaluation schema")
        if self.evaluator_status not in {"available", "no_evaluator"}:
            raise ValueError(f"unsupported predicate evaluator status: {self.evaluator_status!r}")
        if not isinstance(self.predicates, Mapping):
            raise TypeError("predicate results must be a mapping")
        values = {}
        for raw_name, result in self.predicates.items():
            if (
                not isinstance(raw_name, str)
                or not raw_name.strip()
                or raw_name != raw_name.strip()
                or raw_name in values
            ):
                raise ValueError("predicate names must be nonempty and unique")
            name = raw_name
            if not isinstance(result, TaskPredicateResultV1):
                raise TypeError("predicate mappings must contain TaskPredicateResultV1 values")
            if result.status == "no_evaluator":
                raise ValueError("no_evaluator belongs to the evaluation envelope")
            values[name] = result
        if self.evaluator_status == "no_evaluator" and values:
            raise ValueError("no_evaluator cannot include predicate results")
        object.__setattr__(self, "predicates", MappingProxyType(values))

    @classmethod
    def no_evaluator(cls) -> "TaskPredicateEvaluationV1":
        return cls("no_evaluator")

    @classmethod
    def available(
        cls, predicates: Mapping[str, TaskPredicateResultV1]
    ) -> "TaskPredicateEvaluationV1":
        return cls("available", predicates=predicates)

    def resolve(self, name: str) -> TaskPredicateResultV1:
        """Resolve a predicate without conflating absence with ``False``."""

        if not isinstance(name, str):
            raise TypeError("predicate name must be a string")
        key = name.strip()
        if not key or key != name:
            raise ValueError("predicate name cannot be empty")
        if self.evaluator_status == "no_evaluator":
            return TaskPredicateResultV1.no_evaluator()
        return self.predicates.get(
            key, TaskPredicateResultV1.unavailable("predicate_not_produced")
        )


@dataclass(frozen=True)
class TemporalPredicateRuleV1:
    """Bounded temporal rule declaration owned by one TaskDefinition."""

    output_name: str
    kind: str
    source_predicates: tuple[str, ...]
    required_samples: int | None = None
    schema_version: str = "temporal-predicate-rule-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "temporal-predicate-rule-v1":
            raise ValueError("unsupported TemporalPredicateRule schema")
        if (
            not isinstance(self.output_name, str)
            or not self.output_name.strip()
            or self.output_name != self.output_name.strip()
        ):
            raise ValueError("temporal predicate output_name must be a stable token")
        if self.kind not in {"rising_edge", "dwell", "sequence"}:
            raise ValueError(f"unsupported temporal predicate rule: {self.kind!r}")
        if not isinstance(self.source_predicates, (tuple, list)):
            raise TypeError("temporal source_predicates must be a tuple or list")
        names = tuple(self.source_predicates)
        if (
            not names
            or any(
                not isinstance(name, str)
                or not name.strip()
                or name != name.strip()
                for name in names
            )
        ):
            raise ValueError("temporal source predicate names must be nonempty tokens")
        if self.kind == "rising_edge" and len(names) != 1:
            raise ValueError("rising_edge requires exactly one source predicate")
        if self.kind == "dwell":
            if len(names) != 1:
                raise ValueError("dwell requires exactly one source predicate")
            if (
                isinstance(self.required_samples, bool)
                or not isinstance(self.required_samples, int)
                or self.required_samples < 1
            ):
                raise ValueError("dwell required_samples must be a positive integer")
        elif self.required_samples is not None:
            raise ValueError("required_samples only applies to dwell rules")
        if self.kind == "sequence" and len(names) < 2:
            raise ValueError("sequence requires at least two source predicates")
        object.__setattr__(self, "source_predicates", names)


class ScalarTaskStateView:
    """Adapter that gives the legacy ``RuntimeSnapshot`` a common view API."""

    def __init__(self, snapshot: RuntimeSnapshot) -> None:
        self._snapshot = snapshot

    @property
    def qpos(self) -> np.ndarray:
        return self._snapshot.qpos

    @property
    def qvel(self) -> np.ndarray:
        return self._snapshot.qvel

    @property
    def qacc(self) -> np.ndarray | None:
        return self._snapshot.qacc

    @property
    def ctrl(self) -> np.ndarray | None:
        return self._snapshot.ctrl

    @property
    def body_xpos(self) -> np.ndarray | None:
        return self._snapshot.body_xpos

    @property
    def body_xquat(self) -> np.ndarray | None:
        return self._snapshot.body_xquat

    @property
    def site_xpos(self) -> np.ndarray | None:
        return self._snapshot.site_xpos

    @property
    def site_xquat(self) -> np.ndarray | None:
        return self._snapshot.site_xquat

    @property
    def batch_size(self) -> int:
        return 1

    @property
    def is_batch(self) -> bool:
        return False

    def get(self, name: str) -> np.ndarray:
        value = getattr(self._snapshot, str(name), None)
        if value is None:
            raise KeyError(f"unknown or unavailable scalar task state field: {name}")
        return value


class BatchTaskStateView:
    """Adapter for named batch runtime state values."""

    def __init__(self, state: Any) -> None:
        self._state = state
        arrays = getattr(state, "arrays", None)
        if arrays is None:
            raise TypeError("batch state must expose named arrays")
        if not arrays:
            raise ValueError("batch state must contain at least one named array")
        self._arrays = {str(name): np.asarray(value) for name, value in arrays.items()}
        sizes = {int(value.shape[0]) for value in self._arrays.values()}
        if len(sizes) != 1:
            raise ValueError("batch state arrays must share their leading dimension")

    def _field(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"unknown or unavailable batch task state field: {name}") from exc

    @property
    def qpos(self) -> np.ndarray:
        return self._field("qpos")

    @property
    def qvel(self) -> np.ndarray:
        return self._field("qvel")

    @property
    def qacc(self) -> np.ndarray | None:
        return self._arrays.get("qacc")

    @property
    def ctrl(self) -> np.ndarray | None:
        return self._arrays.get("ctrl")

    @property
    def body_xpos(self) -> np.ndarray | None:
        return self._arrays.get("body_xpos")

    @property
    def body_xquat(self) -> np.ndarray | None:
        return self._arrays.get("body_xquat")

    @property
    def site_xpos(self) -> np.ndarray | None:
        return self._arrays.get("site_xpos")

    @property
    def site_xquat(self) -> np.ndarray | None:
        return self._arrays.get("site_xquat")

    @property
    def batch_size(self) -> int:
        return int(next(iter(self._arrays.values())).shape[0])

    @property
    def is_batch(self) -> bool:
        return True

    def get(self, name: str) -> np.ndarray:
        return self._field(str(name))


def as_task_state_view(state: RuntimeSnapshot | TaskStateView) -> TaskStateView:
    """Normalize a scalar runtime snapshot without copying batch state."""

    if isinstance(state, RuntimeSnapshot):
        return ScalarTaskStateView(state)
    if hasattr(state, "arrays") and hasattr(state, "num_envs"):
        return BatchTaskStateView(state)
    if not isinstance(state, TaskStateView):
        raise TypeError("task state must implement TaskStateView")
    return state


class TaskDefinitionBase:
    """Default bindings shared by task definitions.

    A task definition may specialize the native action adapter or observation
    builder after compiled references are available.  The environment class
    itself does not need task-specific binding hooks.  A unified task
    definition sets ``uses_unified_state_view = True`` and implements one
    ``reset`` plus one ``evaluate`` method that consume ``TaskStateView``;
    those methods are called for both scalar and batch execution.
    """

    uses_unified_state_view = False

    # device 状态声明属于 task consumer；runtime field plan 保留既有基础/接触字段，
    # 只追加这里显式声明的字段。
    device_state_required_fields: ClassVar[tuple[str, ...]] = ()
    device_state_optional_fields: ClassVar[tuple[str, ...]] = ()

    def on_reset_sample(
        self,
        *,
        parameters: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        seeds: Sequence[int | None] | None,
        reset_mask: np.ndarray,
    ) -> None:
        """Optional hook for task-local reset semantics.

        The framework still owns physical state sampling and lifecycle.  A
        task may consume the sampler's named parameters (for example command
        samples) without adding a fourth environment factory or changing the
        common reset signature.
        """

        del parameters, seeds, reset_mask

    def evaluate_predicates(
        self, context: TaskEvaluationContextV1
    ) -> TaskPredicateEvaluationV1:
        """Read current predicates without advancing task lifecycle memory.

        Implementations of this optional API must be pure: repeated calls for
        the same context cannot mutate task state. Temporal memory and its
        once-per-boundary commit are owned by a separate lifecycle operation.
        """

        if not isinstance(context, TaskEvaluationContextV1):
            raise TypeError("predicate evaluation requires TaskEvaluationContextV1")
        return TaskPredicateEvaluationV1.no_evaluator()

    def temporal_predicate_rules(self) -> tuple[TemporalPredicateRuleV1, ...]:
        """Declare bounded temporal outputs; mutable progress stays in lifecycle."""

        return ()

    def create_action_adapter(self, compiled_scene: Any):
        del compiled_scene
        return None

    def create_observation_builder(
        self,
        compiled_scene: Any,
        *,
        observation_config: Any,
        render_config: Any,
    ):
        from ..observations import StateObservationBuilder

        return StateObservationBuilder(
            references=compiled_scene.references,
            config=observation_config,
            render_config=render_config,
        )

    def build_observation(
        self,
        state: TaskStateView,
        *,
        sensor_observation: Any | None = None,
    ) -> Any:
        """Build a semantic observation from a scalar or batch state view.

        Existing scalar task definitions keep their observation builder.  A
        batch-capable task should override this method once with NumPy-native
        logic; the framework then uses it for both scalar and batch paths.
        """

        del state, sensor_observation
        raise NotImplementedError(
            f"{type(self).__name__} must provide build_observation() for the "
            "framework lifecycle"
        )

__all__ = [
    "BatchTaskStateView",
    "ScalarTaskStateView",
    "TaskBatchEvaluation",
    "TaskDefinitionBase",
    "TaskEvaluationContextV1",
    "TaskPredicateEvaluationV1",
    "TaskPredicateResultV1",
    "TemporalPredicateRuleV1",
    "TaskStateView",
    "as_task_state_view",
]
