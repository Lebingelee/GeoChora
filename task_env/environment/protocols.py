"""TaskEnv 组件、RuntimeBoundary 与 ActionAdapter 协议。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Protocol

import numpy as np

from .task_definition import TaskBatchEvaluation, TaskStateView
from .types import (
    AppliedControl,
    AssetManifest,
    ControlCommand,
    EpisodePhysicsState,
    InitialStateSpec,
    PhysicsStateSnapshot,
    ReferenceSpec,
    SensorObservation,
    RuntimeSnapshot,
    SnapshotRequest,
    TaskCompositionSpec,
    TaskEvaluation,
)


class AgentComponent(ABC):
    """机器人组件的纯描述基类。"""

    uid: ClassVar[str]

    @abstractmethod
    def asset_manifest(self) -> AssetManifest:
        """返回机器人资产声明。"""

    @abstractmethod
    def reference_spec(self) -> ReferenceSpec:
        """返回机器人稳定名称需求。"""

    @abstractmethod
    def initial_state_spec(self) -> InitialStateSpec:
        """返回机器人命名初态。"""

    @abstractmethod
    def supported_controller_kinds(self) -> tuple[str, ...]:
        """Return public controller kinds supported by this robot."""


class TaskObjectComponent(ABC):
    """任务物体的纯描述基类。"""

    uid: ClassVar[str]

    @abstractmethod
    def asset_manifest(self) -> AssetManifest:
        """返回物体资产声明。"""

    @abstractmethod
    def reference_spec(self) -> ReferenceSpec:
        """返回物体稳定名称需求。"""


class SceneBuilderComponent(ABC):
    """可复用环境背景的纯描述基类。"""

    uid: ClassVar[str]

    @abstractmethod
    def asset_manifest(self) -> AssetManifest:
        """返回背景资产声明。"""

    @abstractmethod
    def reference_spec(self) -> ReferenceSpec:
        """返回背景稳定名称需求。"""


class TaskEnvironmentComponent(ABC):
    """可注册 TaskEnv 的最小类型边界。"""

    uid: ClassVar[str]

    @property
    @abstractmethod
    def composition_spec(self) -> TaskCompositionSpec:
        """返回纯组件组合描述。"""


class RuntimeBoundary(Protocol):
    """TaskEnv 与 GeoPhys runtime 之间唯一允许的物理边界。"""

    def apply_reset_state(self, state: EpisodePhysicsState) -> None: ...

    def apply_control(self, command: ControlCommand) -> AppliedControl: ...

    def set_actuator_force_limits(self, actuator_ids, limit_N: float) -> None: ...

    def step(self, *, substeps: int) -> None: ...

    def read_snapshot(self, request: SnapshotRequest) -> RuntimeSnapshot: ...

    def snapshot_state(self) -> PhysicsStateSnapshot: ...

    def restore_state(self, state: PhysicsStateSnapshot) -> None: ...

    def prewarm(self, profile: str = "interactive") -> None: ...


class ActionAdapter(Protocol):
    """外部 action 到控制命令的纯 CPU 转换边界。"""

    @property
    def action_space(self) -> Any: ...

    def reset(self, snapshot: RuntimeSnapshot) -> None: ...

    def convert(
        self,
        action: np.ndarray,
        snapshot: RuntimeSnapshot,
    ) -> ControlCommand: ...


class SensorProvider(Protocol):
    """可选相机传感器边界；只消费同一次 runtime snapshot。"""

    def reset(self) -> None: ...

    def capture(self, snapshot: RuntimeSnapshot) -> SensorObservation: ...

    def close(self) -> None: ...


class TaskDefinition(Protocol):
    """任务语义边界；同时消费 scalar/batch ``TaskStateView``。"""

    uses_unified_state_view: bool
    device_state_required_fields: tuple[str, ...]
    device_state_optional_fields: tuple[str, ...]

    def reset(
        self,
        *,
        state: TaskStateView,
        reset_mask: np.ndarray | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation: ...

    def evaluate(
        self,
        *,
        state: TaskStateView,
        action: Any,
        elapsed_steps: int | np.ndarray,
        previous_state: TaskStateView | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation: ...
