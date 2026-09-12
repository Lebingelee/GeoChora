"""Framework-owned task semantic lifecycle shared by scalar and batch paths.

The runtime implementations deliberately remain separate: scalar execution
uses ``RuntimeSnapshot`` and the single solver boundary, while batch
execution uses named ``BatchState`` arrays and ``SceneBatchRuntime``.  This
adapter owns the part that must not diverge between those paths: task
definition dispatch, state-view normalization, evaluation validation,
observation fallback, and episode outcome calculation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from .task_definition import (
    TaskBatchEvaluation,
    TaskDefinitionBase,
    TaskStateView,
    as_task_state_view,
)
from .types import (
    AppliedControl,
    ControlCommand,
    RuntimeSnapshot,
    StageUnavailableError,
    TaskEvaluation,
)


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
    ) -> tuple[bool, bool]:
        effective_horizon = self.horizon if horizon is None else int(horizon)
        effective_ignore_done = (
            self.ignore_done if ignore_done is None else bool(ignore_done)
        )
        if effective_ignore_done:
            return False, False
        terminated = bool(evaluation.success or evaluation.failure)
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
    ) -> None:
        super().__init__(
            task_definition=task_definition,
            horizon=horizon,
            ignore_done=ignore_done,
        )
        if int(control_substeps) < 1:
            raise ValueError("scalar task lifecycle control_substeps must be positive")
        self.runtime = runtime
        self.control_substeps = int(control_substeps)
        self._sample_reset_state = sample_reset_state
        self._snapshot_request = snapshot_request
        self._reset_components = reset_components
        self._convert_action = convert_action
        self._observation_fallback = observation_fallback
        self._episode_limits_provider = episode_limits
        self._last_snapshot: RuntimeSnapshot | None = None
        self._last_evaluation: TaskEvaluation | None = None
        self._elapsed_steps = 0
        self._episode_finished = False

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

    def reset(
        self,
        *,
        seed: int | None,
        options: Mapping[str, Any] | None,
        rng: np.random.Generator,
    ) -> SingleTaskResetResult:
        del options
        reset_state, reset_parameters = self._sample_reset_state(seed, rng)
        if not isinstance(reset_parameters, Mapping):
            raise TypeError("episode reset sampler must return a mapping of parameters")
        on_reset_sample = getattr(self.task_definition, "on_reset_sample", None)
        if callable(on_reset_sample):
            on_reset_sample(
                parameters=reset_parameters,
                seeds=(None if seed is None else (int(seed),)),
                reset_mask=np.ones(1, dtype=np.bool_),
            )
        from ..runtime.contracts import build_world_randomization_batch

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
            apply_randomization(
                payload=world_randomization,
                mask=np.ones(1, dtype=np.bool_),
            )
        self.runtime.apply_reset_state(reset_state)
        self._elapsed_steps = 0
        self._episode_finished = False
        snapshot = self.runtime.read_snapshot(self._snapshot_request())
        self._last_snapshot = snapshot
        self._reset_components(snapshot)
        evaluation = self.reset_task(
            state=snapshot,
            reset_mask=np.ones(1, dtype=np.bool_),
            legacy_snapshot=snapshot,
        )
        evaluation = self.coerce_scalar_evaluation(evaluation)
        self._last_evaluation = evaluation
        observation = self.build_observation(
            snapshot,
            fallback=lambda: self._observation_fallback(snapshot),
        )
        return SingleTaskResetResult(
            snapshot=snapshot,
            evaluation=evaluation,
            observation=observation,
            reset_parameters=dict(reset_parameters),
        )

    def step(self, action: Any) -> SingleTaskStepResult:
        if self._episode_finished:
            raise RuntimeError("reset() must be called before stepping after episode end")
        if self._last_snapshot is None:
            raise RuntimeError("reset() must be called before step()")
        previous_snapshot = self._last_snapshot
        command = self._convert_action(action, previous_snapshot)
        applied = self.runtime.apply_control(command)
        self.runtime.step(substeps=self.control_substeps)
        self._elapsed_steps += 1
        snapshot = self.runtime.read_snapshot(self._snapshot_request())
        evaluation = self.evaluate_task(
            state=snapshot,
            action=command.external_action,
            elapsed_steps=self._elapsed_steps,
            previous_state=previous_snapshot,
            legacy_previous_snapshot=previous_snapshot,
            legacy_current_snapshot=snapshot,
        )
        evaluation = self.coerce_scalar_evaluation(evaluation)
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
        )
        self._last_snapshot = snapshot
        self._last_evaluation = evaluation
        self._episode_finished = bool(terminated or truncated)
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
        )

    def close(self) -> None:
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
