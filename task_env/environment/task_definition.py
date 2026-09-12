"""Framework-owned task-definition and state-view contracts.

Task definitions describe semantics.  They do not own the scalar or batch
episode lifecycle.  ``TaskStateView`` is the common value-facing boundary used
by both runtime paths; scalar and batch implementations differ only in the
leading batch dimension of their arrays.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, Sequence, runtime_checkable

import numpy as np

from .types import RuntimeSnapshot, TaskEvaluation


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
    "TaskStateView",
    "as_task_state_view",
]
