"""Framework-owned task semantic lifecycle shared by scalar and batch paths.

The runtime implementations deliberately remain separate: scalar execution
uses ``RuntimeSnapshot`` and the single solver boundary, while batch
execution uses named ``BatchState`` arrays and ``SceneBatchRuntime``.  This
adapter owns the part that must not diverge between those paths: task
definition dispatch, state-view normalization, evaluation validation,
observation fallback, and episode outcome calculation.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any
from uuid import uuid4

import numpy as np

from .task_definition import (
    TaskBatchEvaluation,
    TaskDefinitionBase,
    EpisodeTerminationPolicyV1,
    TaskEvaluationContextV1,
    TaskPredicateEvaluationV1,
    TaskPredicateResultV1,
    TaskStateView,
    TemporalPredicateRuleV1,
    as_task_state_view,
)
from .types import (
    AppliedControl,
    ControlCommand,
    ExecutionFaultV1,
    RuntimeSnapshot,
    StageUnavailableError,
    TaskEvaluation,
    attach_execution_fault,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..trajectory.canonical.episode import EpisodeEndV1


@dataclass
class _TemporalRuleMemory:
    dwell_count: int = 0
    sequence_index: int = 0
    previous_values: dict[str, bool | None] | None = None

    def __post_init__(self) -> None:
        if self.previous_values is None:
            self.previous_values = {}

    def clear(self) -> None:
        self.dwell_count = 0
        self.sequence_index = 0
        self.previous_values = {}


class _TemporalPredicateCommitState:
    """Lifecycle-owned bounded memory for explicit evaluation-boundary commits."""

    def __init__(self, rules: tuple[TemporalPredicateRuleV1, ...]) -> None:
        if any(not isinstance(rule, TemporalPredicateRuleV1) for rule in rules):
            raise TypeError("TaskDefinition temporal rules must be TemporalPredicateRuleV1")
        if len({rule.output_name for rule in rules}) != len(rules):
            raise ValueError("temporal predicate output names must be unique")
        self.rules = tuple(rules)
        self.reset()

    def reset(self) -> None:
        self._memory = self._fresh_memory()
        self._owner_identity = None
        self._last_control_step = None
        self._last_simulation_time_s = None
        self._last_boundary_id = None
        self._last_input_digest = None
        self._last_result = None

    def _fresh_memory(self) -> dict[str, _TemporalRuleMemory]:
        return {rule.output_name: _TemporalRuleMemory() for rule in self.rules}

    @staticmethod
    def _owner(boundary) -> tuple[str, ...]:
        return (
            boundary.episode_id,
            boundary.reset_sample_id,
            boundary.scene_identity_hash,
            boundary.scene_instance_id,
            boundary.provider_materialization_id,
        )

    @staticmethod
    def _stable_value(value):
        if isinstance(value, np.ndarray):
            return _TemporalPredicateCommitState._stable_value(value.tolist())
        if isinstance(value, np.generic):
            return _TemporalPredicateCommitState._stable_value(value.item())
        if isinstance(value, Mapping):
            return {
                str(name): _TemporalPredicateCommitState._stable_value(child)
                for name, child in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, (tuple, list)):
            return [_TemporalPredicateCommitState._stable_value(child) for child in value]
        if isinstance(value, float) and not np.isfinite(value):
            return {"nonfinite": repr(value)}
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        raise TypeError(f"unsupported commit fingerprint value: {type(value).__name__}")

    @classmethod
    def _input_digest(
        cls,
        context: TaskEvaluationContextV1,
        evaluation: TaskPredicateEvaluationV1,
    ) -> str:
        def encode_result(result):
            return {
                "status": result.status,
                "value": cls._stable_value(result.value),
                "reason": result.reason,
            }

        def encode_state(state):
            if state is None:
                return None
            names = (
                "qpos",
                "qvel",
                "qacc",
                "ctrl",
                "actuator_force",
                "body_xpos",
                "body_xquat",
                "site_xpos",
                "site_xquat",
                "site_jacp",
                "site_jacr",
                "contact_summary",
                "simulation_time",
            )
            values = {}
            getter = getattr(state, "get", None)
            for name in names:
                value = getattr(state, name, None)
                if value is None and callable(getter):
                    try:
                        value = getter(name)
                    except KeyError:
                        continue
                if value is None:
                    continue
                if name == "contact_summary":
                    pair_counts = getattr(value, "pair_counts", None)
                    if pair_counts is None and isinstance(value, Mapping):
                        pair_counts = value
                    if not isinstance(pair_counts, Mapping):
                        raise TypeError(
                            "contact_summary must expose stable pair_counts"
                        )
                    value = {"pair_counts": pair_counts}
                values[name] = cls._stable_value(value)
            return values

        applied = context.applied_control
        payload = {
            "boundary_id": context.boundary_identity.boundary_id,
            "sample_clock": context.sample_clock.to_mapping(),
            "current_state": encode_state(context.state),
            "previous_state": encode_state(context.previous_state),
            "requested_action": cls._stable_value(context.requested_action),
            "action_schema_id": context.action_schema_id,
            "applied_control": None
            if applied is None
            else {
                "requested_ctrl": cls._stable_value(applied.requested_ctrl),
                "applied_ctrl": cls._stable_value(applied.applied_ctrl),
                "clipped": bool(applied.clipped),
            },
            "elapsed_steps": cls._stable_value(context.elapsed_steps),
            "timebase": None if context.timebase is None else context.timebase.to_mapping(),
            "native_interval": None
            if context.native_interval is None
            else context.native_interval.to_mapping(),
            "evaluator_status": evaluation.evaluator_status,
            "predicates": {
                name: encode_result(result)
                for name, result in sorted(evaluation.predicates.items())
            },
        }
        payload = cls._stable_value(payload)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def commit(
        self,
        context: TaskEvaluationContextV1,
        evaluation: TaskPredicateEvaluationV1,
    ) -> TaskPredicateEvaluationV1:
        boundary = context.boundary_identity
        clock = context.sample_clock
        if boundary is None or clock is None:
            raise ValueError(
                "temporal predicate commit requires a typed state boundary and sample clock"
            )
        if context.state.is_batch:
            raise StageUnavailableError(
                "temporal predicate commits currently require a scalar evaluation boundary"
            )

        control_step = int(boundary.control_step)
        boundary_id = boundary.boundary_id
        input_digest = self._input_digest(context, evaluation)
        owner = self._owner(boundary)
        if self._owner_identity is not None and owner != self._owner_identity:
            raise ValueError("temporal predicate identity changed without lifecycle reset")
        gap = False
        if self._last_control_step is not None:
            if control_step == self._last_control_step:
                if (
                    boundary_id == self._last_boundary_id
                    and input_digest == self._last_input_digest
                ):
                    return self._last_result
                raise ValueError("evaluation boundary was already committed with different input")
            if control_step < self._last_control_step:
                raise ValueError("temporal predicate boundaries must be committed in order")
            if clock.simulation_time_s <= self._last_simulation_time_s:
                raise ValueError("temporal predicate evaluation clock must move forward")
            if control_step > self._last_control_step + 1:
                gap = True

        next_memory = copy.deepcopy(self._memory)
        if gap:
            for memory in next_memory.values():
                memory.clear()
        if evaluation.evaluator_status == "no_evaluator":
            for memory in next_memory.values():
                memory.clear()
            result = evaluation
        else:
            collisions = set(evaluation.predicates) & {
                rule.output_name for rule in self.rules
            }
            if collisions:
                raise ValueError(
                    "temporal output collides with read-only predicate: "
                    + ", ".join(sorted(collisions))
                )
            outputs = {}
            for rule in self.rules:
                outputs[rule.output_name] = self._commit_rule(
                    rule, next_memory[rule.output_name], evaluation
                )
            merged = dict(evaluation.predicates)
            for name, output in outputs.items():
                merged[name] = output
            result = TaskPredicateEvaluationV1.available(merged)

        self._memory = next_memory
        self._owner_identity = owner
        self._last_control_step = control_step
        self._last_simulation_time_s = float(clock.simulation_time_s)
        self._last_boundary_id = boundary_id
        self._last_input_digest = input_digest
        self._last_result = result
        return result

    @staticmethod
    def _commit_rule(
        rule: TemporalPredicateRuleV1,
        memory: _TemporalRuleMemory,
        evaluation: TaskPredicateEvaluationV1,
    ) -> TaskPredicateResultV1:
        values = {
            name: evaluation.resolve(name) for name in set(rule.source_predicates)
        }
        if rule.kind == "rising_edge":
            name = rule.source_predicates[0]
            source = values[name]
            if source.status != "available":
                memory.previous_values[name] = None
                return TaskPredicateResultV1.unavailable(source.reason or "source_unavailable")
            current = bool(source.value)
            previous = memory.previous_values.get(name)
            memory.previous_values[name] = current
            if current and previous is None:
                return TaskPredicateResultV1.unavailable("edge_baseline_unavailable")
            return TaskPredicateResultV1.available(current and previous is False)

        if rule.kind == "dwell":
            name = rule.source_predicates[0]
            source = values[name]
            if source.status != "available":
                memory.dwell_count = 0
                return TaskPredicateResultV1.unavailable(source.reason or "source_unavailable")
            if bool(source.value):
                memory.dwell_count += 1
            else:
                memory.dwell_count = 0
            return TaskPredicateResultV1.available(
                memory.dwell_count >= int(rule.required_samples)
            )

        statuses = [values[name] for name in rule.source_predicates]
        missing = next((value for value in statuses if value.status != "available"), None)
        if missing is not None:
            memory.sequence_index = 0
            memory.previous_values.clear()
            return TaskPredicateResultV1.unavailable(
                missing.reason or "sequence_source_unavailable"
            )

        edges = []
        unknown_baseline = False
        for name in dict.fromkeys(rule.source_predicates):
            current = bool(values[name].value)
            previous = memory.previous_values.get(name)
            if current and previous is None:
                unknown_baseline = True
            elif current and previous is False:
                edges.append(name)
            memory.previous_values[name] = current
        if unknown_baseline:
            memory.sequence_index = 0
            return TaskPredicateResultV1.unavailable("sequence_baseline_unavailable")
        if len(edges) > 1:
            memory.sequence_index = 0
            return TaskPredicateResultV1.available(False)
        if edges:
            edge = edges[0]
            expected = rule.source_predicates[memory.sequence_index]
            if edge == expected:
                memory.sequence_index += 1
            else:
                memory.sequence_index = 1 if edge == rule.source_predicates[0] else 0
            if memory.sequence_index == len(rule.source_predicates):
                memory.sequence_index = 0
                return TaskPredicateResultV1.available(True)
        return TaskPredicateResultV1.available(False)


class TaskLifecycleAdapter:
    """Normalize task semantics for both scalar and batch runtime adapters.

    This class intentionally does not own a solver, Taichi field, controller,
    or vector wrapper.  Runtime-specific adapters call ``reset_task`` and
    ``evaluate_task`` after they have produced their public state view.
    """

    def __init__(
        self,
        *,
        task_definition: TaskDefinitionBase | None,
        horizon: int,
        ignore_done: bool,
    ) -> None:
        if int(horizon) < 1:
            raise ValueError("task lifecycle horizon must be positive")
        self.task_definition = task_definition
        self.horizon = int(horizon)
        self.ignore_done = bool(ignore_done)
        rules_method = getattr(task_definition, "temporal_predicate_rules", None)
        rules = tuple(rules_method()) if callable(rules_method) else ()
        self._temporal_predicate_state = _TemporalPredicateCommitState(rules)

    def reset_task(
        self,
        *,
        state: RuntimeSnapshot | TaskStateView,
        reset_mask: np.ndarray | None = None,
        legacy_snapshot: RuntimeSnapshot | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation:
        """Evaluate task reset semantics from a scalar or batch state view."""

        view = as_task_state_view(state)
        definition = self.task_definition
        self._temporal_predicate_state.reset()
        if definition is None:
            return self.placeholder_evaluation(batch_size=view.batch_size if view.is_batch else None)

        reset = getattr(definition, "reset", None)
        if not callable(reset):
            raise StageUnavailableError(
                f"task definition {type(definition).__name__} has no reset semantic"
            )
        if getattr(definition, "uses_unified_state_view", False):
            mask = self._normalize_task_reset_mask(reset_mask, view)
            evaluation = reset(state=view, reset_mask=mask)
        else:
            if view.is_batch:
                raise StageUnavailableError(
                    f"task definition {type(definition).__name__} has no unified batch reset semantic"
                )
            if legacy_snapshot is None:
                if isinstance(state, RuntimeSnapshot):
                    legacy_snapshot = state
                else:
                    raise TypeError(
                        "legacy scalar task reset requires a RuntimeSnapshot"
                    )
            evaluation = reset(legacy_snapshot)
        return self.normalize_evaluation(evaluation, view)

    def evaluate_task(
        self,
        *,
        state: RuntimeSnapshot | TaskStateView,
        action: Any,
        elapsed_steps: int | np.ndarray,
        previous_state: RuntimeSnapshot | TaskStateView | None = None,
        legacy_previous_snapshot: RuntimeSnapshot | None = None,
        legacy_current_snapshot: RuntimeSnapshot | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation:
        """Evaluate one task transition through the unified semantic boundary."""

        view = as_task_state_view(state)
        definition = self.task_definition
        if definition is None:
            return self.placeholder_evaluation(batch_size=view.batch_size if view.is_batch else None)

        evaluate = getattr(definition, "evaluate", None)
        if not callable(evaluate):
            raise StageUnavailableError(
                f"task definition {type(definition).__name__} has no step semantic"
            )
        if getattr(definition, "uses_unified_state_view", False):
            previous_view = (
                None if previous_state is None else as_task_state_view(previous_state)
            )
            evaluation = evaluate(
                state=view,
                action=action,
                elapsed_steps=elapsed_steps,
                previous_state=previous_view,
            )
        else:
            if view.is_batch:
                raise StageUnavailableError(
                    f"task definition {type(definition).__name__} has no unified batch step semantic"
                )
            if legacy_previous_snapshot is None and isinstance(previous_state, RuntimeSnapshot):
                legacy_previous_snapshot = previous_state
            if legacy_current_snapshot is None and isinstance(state, RuntimeSnapshot):
                legacy_current_snapshot = state
            if legacy_previous_snapshot is None or legacy_current_snapshot is None:
                raise TypeError(
                    "legacy scalar task evaluation requires previous/current RuntimeSnapshot"
                )
            evaluation = evaluate(
                legacy_previous_snapshot,
                action,
                legacy_current_snapshot,
            )
        return self.normalize_evaluation(evaluation, view)

    def evaluate_predicates(
        self, context: TaskEvaluationContextV1
    ) -> TaskPredicateEvaluationV1:
        """Explicitly read task predicates without invoking reward evaluation.

        This method is intentionally not called by ``step`` or observation
        construction. Callers may inspect a result repeatedly; committing any
        temporal state remains a distinct lifecycle action.
        """

        if not isinstance(context, TaskEvaluationContextV1):
            raise TypeError("predicate evaluation requires TaskEvaluationContextV1")
        definition = self.task_definition
        evaluate = getattr(definition, "evaluate_predicates", None)
        if not callable(evaluate):
            return TaskPredicateEvaluationV1.no_evaluator()
        result = evaluate(context)
        if not isinstance(result, TaskPredicateEvaluationV1):
            raise TypeError(
                "task predicate evaluator must return TaskPredicateEvaluationV1"
            )
        if context.state.is_batch:
            for name, predicate in result.predicates.items():
                if predicate.status == "available":
                    if not isinstance(predicate.value, np.ndarray):
                        raise ValueError(
                            f"batch predicate {name!r} must return one bool per environment"
                        )
                    if predicate.value.shape != (context.state.batch_size,):
                        raise ValueError(
                            f"batch predicate {name!r} has the wrong leading dimension"
                        )
        elif any(
            predicate.status == "available"
            and isinstance(predicate.value, np.ndarray)
            for predicate in result.predicates.values()
        ):
            raise ValueError("scalar predicate evaluation cannot return batch values")
        return result

    def commit_temporal_predicates(
        self, context: TaskEvaluationContextV1
    ) -> TaskPredicateEvaluationV1:
        """Commit one task predicate sample at its explicit state boundary.

        Repeated reads remain pure; only this explicit method advances the
        lifecycle-owned temporal memory. Exact duplicate commits are idempotent,
        while conflicting or out-of-order commits fail closed.
        """

        if not isinstance(context, TaskEvaluationContextV1):
            raise TypeError("temporal commit requires TaskEvaluationContextV1")
        if context.boundary_identity is None or context.sample_clock is None:
            raise ValueError(
                "temporal predicate commit requires a typed state boundary and sample clock"
            )
        if self._temporal_predicate_state.rules and context.state.is_batch:
            raise StageUnavailableError(
                "temporal predicate commits currently require a scalar evaluation boundary"
            )
        evaluation = self.evaluate_predicates(context)
        if not self._temporal_predicate_state.rules:
            return evaluation
        return self._temporal_predicate_state.commit(context, evaluation)

    def build_observation(
        self,
        state: RuntimeSnapshot | TaskStateView,
        *,
        fallback: Callable[[], Any] | None = None,
    ) -> Any:
        """Use the task semantic observation builder, or the scalar fallback."""

        view = as_task_state_view(state)
        definition = self.task_definition
        builder = getattr(definition, "build_observation", None)
        if (
            callable(builder)
            and type(definition).build_observation is not TaskDefinitionBase.build_observation
        ):
            return builder(view)
        if fallback is None:
            raise StageUnavailableError(
                f"task definition {type(definition).__name__ if definition is not None else 'None'} "
                "has no observation builder"
            )
        return fallback()

    def normalize_evaluation(
        self,
        evaluation: Any,
        state: RuntimeSnapshot | TaskStateView,
    ) -> TaskEvaluation | TaskBatchEvaluation:
        """Validate and normalize a task result against the state cardinality."""

        view = as_task_state_view(state)
        if view.is_batch:
            if not isinstance(evaluation, TaskBatchEvaluation):
                raise TypeError(
                    "batch task semantics must return TaskBatchEvaluation"
                )
            self.validate_batch_evaluation(evaluation, view.batch_size)
            return evaluation
        return self.coerce_scalar_evaluation(evaluation)

    @staticmethod
    def placeholder_evaluation(
        *, batch_size: int | None = None
    ) -> TaskEvaluation | TaskBatchEvaluation:
        if batch_size is None:
            return TaskEvaluation(
                reward=0.0,
                success=False,
                failure=False,
                metrics={},
                reward_terms={},
            )
        zeros = np.zeros(int(batch_size), dtype=np.float32)
        false = np.zeros(int(batch_size), dtype=np.bool_)
        return TaskBatchEvaluation(
            reward=zeros,
            success=false,
            failure=false,
            truncated=false,
        )

    @staticmethod
    def coerce_scalar_evaluation(evaluation: Any) -> TaskEvaluation:
        if isinstance(evaluation, TaskEvaluation):
            return evaluation
        if isinstance(evaluation, TaskBatchEvaluation):
            arrays = {
                "reward": np.asarray(evaluation.reward),
                "success": np.asarray(evaluation.success),
                "failure": np.asarray(evaluation.failure),
                "truncated": np.asarray(evaluation.truncated),
            }
            if any(value.shape != (1,) for value in arrays.values()):
                raise ValueError(
                    "scalar TaskEnv received a batch evaluation with a non-singleton shape"
                )

            def _scalar_metric(value: Any) -> Any:
                array = np.asarray(value)
                if array.shape != (1,):
                    raise ValueError(
                        "scalar TaskEnv received a non-singleton task metric"
                    )
                return array[0].item()

            return TaskEvaluation(
                reward=float(arrays["reward"][0]),
                success=bool(arrays["success"][0]),
                failure=bool(arrays["failure"][0]),
                metrics={
                    name: _scalar_metric(values)
                    for name, values in evaluation.metrics.items()
                },
                reward_terms={
                    name: float(_scalar_metric(values))
                    for name, values in evaluation.reward_terms.items()
                },
            )
        raise TypeError(
            f"task definition returned unsupported evaluation type {type(evaluation).__name__}"
        )

    @staticmethod
    def validate_batch_evaluation(
        evaluation: TaskBatchEvaluation,
        batch_size: int,
    ) -> None:
        arrays = {
            "reward": evaluation.reward,
            "success": evaluation.success,
            "failure": evaluation.failure,
            "truncated": evaluation.truncated,
        }
        expected = (int(batch_size),)
        for name, value in arrays.items():
            if np.asarray(value).shape != expected:
                raise ValueError(
                    f"batch evaluation {name} must have shape {expected}"
                )
        for name, value in evaluation.metrics.items():
            if np.asarray(value).shape != expected:
                raise ValueError(
                    f"batch evaluation metric {name} must have shape {expected}"
                )
        for name, value in evaluation.reward_terms.items():
            if np.asarray(value).shape != expected:
                raise ValueError(
                    f"batch reward term {name} must have shape {expected}"
                )

    def resolve_scalar_done(
        self,
        evaluation: TaskEvaluation,
        elapsed_steps: int,
        *,
        horizon: int | None = None,
        ignore_done: bool | None = None,
        policy: EpisodeTerminationPolicyV1 | None = None,
    ) -> tuple[bool, bool]:
        effective_horizon = self.horizon if horizon is None else int(horizon)
        effective_ignore_done = (
            self.ignore_done if ignore_done is None else bool(ignore_done)
        )
        if effective_ignore_done:
            return False, False
        effective_policy = policy or EpisodeTerminationPolicyV1()
        if not isinstance(effective_policy, EpisodeTerminationPolicyV1):
            raise TypeError("scalar termination policy must be EpisodeTerminationPolicyV1")
        terminated = bool(
            (evaluation.success and effective_policy.terminate_on_success)
            or (evaluation.failure and effective_policy.terminate_on_failure)
        )
        truncated = bool(
            getattr(evaluation, "truncated", False)
            or int(elapsed_steps) >= effective_horizon
        )
        return terminated, truncated

    def resolve_batch_done(
        self,
        evaluation: TaskBatchEvaluation,
        elapsed_steps: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        size = int(np.asarray(evaluation.reward).shape[0])
        self.validate_batch_evaluation(evaluation, size)
        truncated = np.asarray(evaluation.truncated, dtype=np.bool_).copy()
        terminated = np.logical_or(evaluation.success, evaluation.failure)
        if not self.ignore_done:
            truncated |= np.asarray(elapsed_steps, dtype=np.int32) >= self.horizon
        else:
            terminated = np.zeros(size, dtype=np.bool_)
            truncated = np.zeros(size, dtype=np.bool_)
        return terminated.astype(np.bool_, copy=False), truncated.astype(
            np.bool_, copy=False
        )

    @staticmethod
    def _normalize_task_reset_mask(
        reset_mask: np.ndarray | None,
        state: TaskStateView,
    ) -> np.ndarray:
        if state.is_batch:
            if reset_mask is None:
                return np.ones(state.batch_size, dtype=np.bool_)
            value = np.asarray(reset_mask, dtype=np.bool_)
            if value.shape != (state.batch_size,):
                raise ValueError("reset mask must have shape (B,)")
            return value
        return np.ones(1, dtype=np.bool_)


@dataclass(frozen=True)
class SingleTaskResetResult:
    """Framework result returned by one scalar episode reset."""

    snapshot: RuntimeSnapshot
    evaluation: TaskEvaluation
    observation: Any
    reset_parameters: Mapping[str, Any]
    previous_episode_end: EpisodeEndV1 | None = None


@dataclass(frozen=True)
class SingleTaskStepResult:
    """Framework result returned by one scalar environment step."""

    previous_snapshot: RuntimeSnapshot
    snapshot: RuntimeSnapshot
    evaluation: TaskEvaluation
    observation: Any
    command: ControlCommand
    applied: AppliedControl
    terminated: bool
    truncated: bool
    elapsed_steps: int
    episode_end: EpisodeEndV1 | None = None


class SingleTaskLifecycleAdapter(TaskLifecycleAdapter):
    """Own scalar runtime reset/step around the shared task semantic adapter."""

    def __init__(
        self,
        *,
        runtime: Any,
        task_definition: TaskDefinitionBase | None,
        control_substeps: int,
        horizon: int,
        ignore_done: bool,
        sample_reset_state: Callable[
            [int | None, np.random.Generator], tuple[Any, Mapping[str, Any]]
        ],
        snapshot_request: Callable[[], Any],
        reset_components: Callable[[RuntimeSnapshot], None],
        convert_action: Callable[[Any, RuntimeSnapshot], ControlCommand],
        observation_fallback: Callable[[RuntimeSnapshot], Any],
        episode_limits: Callable[[], tuple[int, bool]] | None = None,
        expected_control_dt_s: float | None = None,
        termination_policy: EpisodeTerminationPolicyV1 | None = None,
    ) -> None:
        super().__init__(
            task_definition=task_definition,
            horizon=horizon,
            ignore_done=ignore_done,
        )
        if int(control_substeps) < 1:
            raise ValueError("scalar task lifecycle control_substeps must be positive")
        if expected_control_dt_s is not None and (
            not math.isfinite(float(expected_control_dt_s))
            or float(expected_control_dt_s) <= 0.0
        ):
            raise ValueError("expected_control_dt_s must be finite and positive")
        self.runtime = runtime
        self.control_substeps = int(control_substeps)
        self.expected_control_dt_s = (
            None if expected_control_dt_s is None else float(expected_control_dt_s)
        )
        self._sample_reset_state = sample_reset_state
        self._snapshot_request = snapshot_request
        self._reset_components = reset_components
        self._convert_action = convert_action
        self._observation_fallback = observation_fallback
        self._episode_limits_provider = episode_limits
        if termination_policy is None:
            policy_factory = getattr(task_definition, "termination_policy", None)
            termination_policy = policy_factory() if callable(policy_factory) else EpisodeTerminationPolicyV1()
        if not isinstance(termination_policy, EpisodeTerminationPolicyV1):
            raise TypeError("termination_policy must be EpisodeTerminationPolicyV1")
        self.termination_policy = termination_policy
        self._last_snapshot: RuntimeSnapshot | None = None
        self._boundary_snapshot: RuntimeSnapshot | None = None
        self._last_evaluation: TaskEvaluation | None = None
        self._elapsed_steps = 0
        self._episode_finished = False
        self._execution_fault: ExecutionFaultV1 | None = None
        self._episode_id: str | None = None
        self._episode_boundary = 0
        self._episode_end: EpisodeEndV1 | None = None
        self._closed = False

    @property
    def last_snapshot(self) -> RuntimeSnapshot | None:
        return self._last_snapshot

    @property
    def elapsed_steps(self) -> int:
        return int(self._elapsed_steps)

    @property
    def episode_finished(self) -> bool:
        return bool(self._episode_finished)

    @property
    def last_evaluation(self) -> TaskEvaluation | None:
        return self._last_evaluation

    @property
    def execution_fault(self) -> ExecutionFaultV1 | None:
        return self._execution_fault

    @property
    def episode_id(self) -> str | None:
        return self._episode_id

    @property
    def episode_end(self) -> EpisodeEndV1 | None:
        return self._episode_end

    def _latch_fault(
        self,
        phase: str,
        error: BaseException,
        *,
        before_snapshot: Any = None,
        after_snapshot: Any = None,
        control_step_before: int | None = None,
        control_step_after: int | None = None,
        interval_attempted: bool = False,
        interval_completed: bool = False,
        readback_error: str | None = None,
        transition_status: str = "not_assessed",
    ) -> ExecutionFaultV1:
        fault = ExecutionFaultV1.from_exception(
            phase,
            error,
            control_step_before=control_step_before,
            control_step_after=control_step_after,
            simulation_time_before_s=getattr(before_snapshot, "simulation_time", None),
            simulation_time_after_s=getattr(after_snapshot, "simulation_time", None),
            expected_control_dt_s=self.expected_control_dt_s,
            interval_attempted=interval_attempted,
            interval_completed=interval_completed,
            transition_status=transition_status,
            readback_error=readback_error,
        )
        self._execution_fault = fault
        attach_execution_fault(error, fault)
        return fault

    def _read_fault_snapshot(self) -> tuple[RuntimeSnapshot | None, str | None]:
        try:
            return self.runtime.read_snapshot(self._snapshot_request()), None
        except BaseException as error:
            return None, f"{type(error).__name__}: {error}"

    def reset(
        self,
        *,
        seed: int | None,
        options: Mapping[str, Any] | None,
        rng: np.random.Generator,
    ) -> SingleTaskResetResult:
        if self._closed:
            raise RuntimeError("scalar task lifecycle is closed")
        del options
        previous_episode_end = self._episode_end
        if self._episode_id is not None and self._boundary_snapshot is not None and previous_episode_end is None:
            previous_episode_end = self.stop("reset")
        # A failed reset must never let Stop re-use the preceding episode's
        # identity or re-stamp its boundary as a new episode.
        self._episode_id = None
        self._boundary_snapshot = None
        self._episode_end = None
        self._episode_boundary = 0
        before_snapshot = self._last_snapshot
        before_elapsed_steps = self._elapsed_steps
        phase = "reset_sampling"
        reset_state_applied = False
        snapshot: RuntimeSnapshot | None = None
        try:
            reset_state, reset_parameters = self._sample_reset_state(seed, rng)
            if not isinstance(reset_parameters, Mapping):
                raise TypeError("episode reset sampler must return a mapping of parameters")
            on_reset_sample = getattr(self.task_definition, "on_reset_sample", None)
            if callable(on_reset_sample):
                phase = "reset_task_sample"
                on_reset_sample(
                    parameters=reset_parameters,
                    seeds=(None if seed is None else (int(seed),)),
                    reset_mask=np.ones(1, dtype=np.bool_),
                )
            from ..runtime.contracts import build_world_randomization_batch

            phase = "reset_randomization_prepare"
            world_randomization = build_world_randomization_batch(
                (reset_parameters,),
                reset_mask=np.ones(1, dtype=np.bool_),
            )
            if world_randomization is not None:
                apply_randomization = getattr(self.runtime, "apply_world_randomization", None)
                if not callable(apply_randomization):
                    raise StageUnavailableError(
                        "reset sampler requested world randomization but scalar runtime "
                        "does not expose apply_world_randomization()"
                    )
                phase = "reset_randomization_apply"
                apply_randomization(
                    payload=world_randomization,
                    mask=np.ones(1, dtype=np.bool_),
                )
            phase = "reset_state_apply"
            self.runtime.apply_reset_state(reset_state)
            reset_state_applied = True
            phase = "reset_readback"
            snapshot = self.runtime.read_snapshot(self._snapshot_request())
            phase = "reset_components"
            self._reset_components(snapshot)
            phase = "reset_task_evaluation"
            evaluation = self.reset_task(
                state=snapshot,
                reset_mask=np.ones(1, dtype=np.bool_),
                legacy_snapshot=snapshot,
            )
            evaluation = self.coerce_scalar_evaluation(evaluation)
            phase = "reset_observation"
            observation = self.build_observation(
                snapshot,
                fallback=lambda: self._observation_fallback(snapshot),
            )
            self._last_snapshot = snapshot
            self._boundary_snapshot = snapshot
            self._last_evaluation = evaluation
            self._elapsed_steps = 0
            self._episode_boundary = 0
            self._episode_id = uuid4().hex
            self._episode_end = None
            self._episode_finished = False
            self._execution_fault = None
            return SingleTaskResetResult(
                snapshot=snapshot,
                evaluation=evaluation,
                observation=observation,
                reset_parameters=dict(reset_parameters),
                previous_episode_end=previous_episode_end,
            )
        except BaseException as error:
            readback_error = None
            if reset_state_applied and snapshot is None:
                snapshot, readback_error = self._read_fault_snapshot()
            self._last_snapshot = snapshot
            self._last_evaluation = None
            self._latch_fault(
                phase,
                error,
                before_snapshot=before_snapshot,
                after_snapshot=snapshot,
                control_step_before=before_elapsed_steps,
                control_step_after=None,
                readback_error=readback_error,
            )
            raise

    def step(self, action: Any) -> SingleTaskStepResult:
        if self._closed:
            raise RuntimeError("scalar task lifecycle is closed")
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                "scalar task lifecycle is faulted; reset() is required "
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if self._episode_finished:
            raise RuntimeError("reset() must be called before stepping after episode end")
        if self._last_snapshot is None:
            raise RuntimeError("reset() must be called before step()")
        previous_snapshot = self._last_snapshot
        command = self._convert_action(action, previous_snapshot)
        phase = "control_application"
        interval_attempted = False
        interval_completed = False
        snapshot: RuntimeSnapshot | None = None
        before_elapsed_steps = self._elapsed_steps
        try:
            applied = self.runtime.apply_control(command)
            phase = "physics_step"
            interval_attempted = True
            self.runtime.step(substeps=self.control_substeps)
            interval_completed = True
            self._elapsed_steps += 1
            phase = "snapshot_readback"
            snapshot = self.runtime.read_snapshot(self._snapshot_request())
            phase = "task_evaluation"
            evaluation = self.evaluate_task(
                state=snapshot,
                action=command.external_action,
                elapsed_steps=self._elapsed_steps,
                previous_state=previous_snapshot,
                legacy_previous_snapshot=previous_snapshot,
                legacy_current_snapshot=snapshot,
            )
            evaluation = self.coerce_scalar_evaluation(evaluation)
            phase = "observation"
            observation = self.build_observation(
                snapshot,
                fallback=lambda: self._observation_fallback(snapshot),
            )
            horizon, ignore_done = self._get_episode_limits()
            terminated, truncated = self.resolve_scalar_done(
                evaluation,
                self._elapsed_steps,
                horizon=horizon,
                ignore_done=ignore_done,
                policy=self.termination_policy,
            )
            self._last_snapshot = snapshot
            self._last_evaluation = evaluation
            self._boundary_snapshot = snapshot
            self._episode_boundary = self._elapsed_steps
            self._episode_finished = bool(terminated or truncated)
            episode_end = None
            if self._episode_finished:
                if terminated:
                    end_reason = "task_terminal"
                    outcome_terminated, outcome_truncated = True, False
                    bootstrap_allowed = False
                elif bool(getattr(evaluation, "truncated", False)):
                    end_reason = "task_truncated"
                    outcome_terminated, outcome_truncated = False, True
                    bootstrap_allowed = True
                else:
                    end_reason = "horizon_reached"
                    outcome_terminated, outcome_truncated = False, True
                    bootstrap_allowed = self.termination_policy.bootstrap_on_horizon
                episode_end = self._finish_episode(
                    end_reason,
                    terminated=outcome_terminated,
                    truncated=outcome_truncated,
                    bootstrap_allowed=bootstrap_allowed,
                    task_success=bool(evaluation.success),
                )
            return SingleTaskStepResult(
                previous_snapshot=previous_snapshot,
                snapshot=snapshot,
                evaluation=evaluation,
                observation=observation,
                command=command,
                applied=applied,
                terminated=terminated,
                truncated=truncated,
                elapsed_steps=self._elapsed_steps,
                episode_end=episode_end,
            )
        except BaseException as error:
            readback_error = None
            if interval_attempted and snapshot is None:
                snapshot, readback_error = self._read_fault_snapshot()
            if snapshot is not None:
                self._last_snapshot = snapshot
            self._latch_fault(
                phase,
                error,
                before_snapshot=previous_snapshot,
                after_snapshot=snapshot,
                control_step_before=before_elapsed_steps,
                control_step_after=self._elapsed_steps,
                interval_attempted=interval_attempted,
                interval_completed=interval_completed,
                readback_error=readback_error,
            )
            raise

    def revoke_unpublished_step(self, result: SingleTaskStepResult) -> None:
        """Restore the public finalizer boundary when an outer Env facade fails.

        Physics may have advanced, and the fault receipt retains that clock.
        The failed facade call returned no transition, so Stop must remain at
        the preceding published boundary and must not manufacture one.
        """

        if not isinstance(result, SingleTaskStepResult):
            raise TypeError("result must be SingleTaskStepResult")
        if self._boundary_snapshot is not result.snapshot:
            raise RuntimeError("cannot revoke a step that is not the current lifecycle boundary")
        self._boundary_snapshot = result.previous_snapshot
        self._episode_boundary = max(0, int(result.elapsed_steps) - 1)
        if result.episode_end is not None and self._episode_end is result.episode_end:
            self._episode_end = None
        self._episode_finished = False

    def _finish_episode(
        self,
        end_reason: str,
        *,
        terminated: bool,
        truncated: bool,
        bootstrap_allowed: bool,
        task_success: bool | None,
        payload: Mapping[str, object] | None = None,
    ) -> EpisodeEndV1:
        from ..trajectory.canonical.episode import make_episode_end_v1

        if self._episode_end is not None:
            return self._episode_end
        if self._episode_id is None or self._boundary_snapshot is None:
            raise RuntimeError("episode end requires a successfully reset lifecycle")
        details = {
            "control_step": self._episode_boundary,
            "simulation_time_s": float(self._boundary_snapshot.simulation_time),
            "termination_policy": self.termination_policy.to_mapping(),
        }
        details.update(dict(payload or {}))
        result = make_episode_end_v1(
            episode_id=self._episode_id,
            final_boundary=self._episode_boundary,
            end_reason=end_reason,
            terminated=terminated,
            truncated=truncated,
            bootstrap_allowed=bootstrap_allowed,
            source="task_env.lifecycle",
            payload=details,
            task_success=task_success,
        )
        self._episode_end = result
        self._episode_finished = True
        return result

    def stop(self, reason: str = "external_stop") -> EpisodeEndV1:
        """End at the last published boundary without a Controller or Runtime step."""

        if self._closed:
            raise RuntimeError("cannot stop a closed scalar task lifecycle")
        if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
            raise ValueError("Stop reason must be a trimmed non-empty string")
        if self._episode_end is not None:
            return self._episode_end
        if self._last_snapshot is None or self._episode_id is None:
            raise RuntimeError("reset() must complete before Stop")
        if self._execution_fault is not None:
            return self._finish_episode(
                "execution_fault",
                terminated=False,
                truncated=True,
                bootstrap_allowed=False,
                task_success=None,
                payload={"fault": self._execution_fault.to_mapping()},
            )
        is_terminated = self.termination_policy.external_stop_terminated
        return self._finish_episode(
            "external_stop",
            terminated=is_terminated,
            truncated=not is_terminated,
            bootstrap_allowed=(
                self.termination_policy.bootstrap_on_external_stop and not is_terminated
            ),
            task_success=(
                None if self._last_evaluation is None else bool(self._last_evaluation.success)
            ),
            payload={"requested_reason": reason},
        )

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._boundary_snapshot is not None and self._episode_end is None:
                # Record the lifecycle end while its final public boundary is
                # still available. Runtime teardown remains guaranteed if
                # event construction or a task policy rejects the Stop.
                self.stop("environment_close")
        finally:
            self._closed = True
            self._temporal_predicate_state.reset()
            self.runtime.close()

    def _get_episode_limits(self) -> tuple[int, bool]:
        if self._episode_limits_provider is None:
            return self.horizon, self.ignore_done
        horizon, ignore_done = self._episode_limits_provider()
        return int(horizon), bool(ignore_done)


__all__ = [
    "SingleTaskLifecycleAdapter",
    "SingleTaskResetResult",
    "SingleTaskStepResult",
    "TaskLifecycleAdapter",
]
