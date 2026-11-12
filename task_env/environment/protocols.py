"""TaskEnv 组件、RuntimeBoundary 与 ActionAdapter 协议。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from functools import cached_property
from typing import Any, ClassVar, Protocol

import numpy as np

from .task_definition import CanonicalTaskStateView, TaskBatchEvaluation, TaskStateView
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


class DefaultCanonicalControllerMixin:
    """Give each subject its own stable, initially unbound Controller."""

    @cached_property
    def default_controller(self):
        # Lazy import keeps the foundational component contract independent of
        # Controller package initialization.
        from ..controllers.canonical.default_identity import DefaultCanonicalController
        return DefaultCanonicalController()


class RobotComponent(DefaultCanonicalControllerMixin, ABC):
    """Shared Robot identity; concrete capabilities are declared by each Robot."""

    uid: ClassVar[str]
    component_controller_kinds: ClassVar[tuple[str, ...]] = ()
    controller_profiles: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def declared_controller_profiles(cls):
        """Return the Controller profiles this Robot can bind."""
        return tuple(cls.controller_profiles)

    def artifact_entity(self, scene):
        """Project this Robot's declared Scene identity into a Task Artifact."""
        from ..artifacts import EntityDefinition

        entities = tuple(item for item in scene.entities if item.entity_id == self.uid)
        articulations = tuple(item for item in scene.articulations if item.entity_id == self.uid)
        if len(entities) != 1 or len(articulations) != 1:
            raise ValueError('Task requires one declared Robot entity and articulation')
        entity, articulation = entities[0], articulations[0]
        assets = tuple(item for item in scene.assets
                       if (item.asset_id, item.asset_version) == (entity.asset_id, entity.asset_version))
        if len(assets) != 1:
            raise ValueError('Robot entity must resolve to exactly one Scene asset')
        names = tuple(self.state_joint_names)
        if names != tuple(joint.joint_id for joint in articulation.joints):
            raise ValueError('Robot state joints differ from its Scene articulation')
        return EntityDefinition(self.uid, 'embodiment', assets[0].source_reference,
            tuple(f'{self.uid}/{name}' for name in articulation.link_frame_ids),
            tuple(f'{self.uid}/{name}' for name in names), 'source_owned', 'source_owned', {})


class AgentComponent(RobotComponent):
    """Legacy source-component capabilities for Robots that provide them."""

    def single_mjcf_source(self):
        """Resolve an explicitly declared single-file Robot source."""
        manifest = self.asset_manifest()
        if manifest.owner_uid != self.uid or len(manifest.mjcf_sources) != 1:
            raise ValueError('Robot must declare one MJCF source under its own identity')
        source = manifest.mjcf_sources[0].resolve()
        if not any(source.is_relative_to(root.resolve()) for root in manifest.asset_roots):
            raise ValueError('Robot MJCF source is outside its declared asset roots')
        return source

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

    def apply_reset_state(
        self,
        state: EpisodePhysicsState,
        *,
        static_world_child_poses: Mapping[int, tuple[np.ndarray, np.ndarray]] | None = None,
    ) -> None: ...

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
    """任务语义边界；消费声明的索引数组或具名 canonical state view。"""

    uses_unified_state_view: bool
    device_state_required_fields: tuple[str, ...]
    device_state_optional_fields: tuple[str, ...]

    def reset(
        self,
        *,
        state: TaskStateView | CanonicalTaskStateView,
        reset_mask: np.ndarray | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation: ...

    def evaluate(
        self,
        *,
        state: TaskStateView | CanonicalTaskStateView,
        action: Any,
        elapsed_steps: int | np.ndarray,
        previous_state: TaskStateView | CanonicalTaskStateView | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation: ...
