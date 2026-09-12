"""TaskEnv 跨组件共享的无运行时数据契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import OrderedDict
from collections.abc import Mapping as MappingABC
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np


class StageUnavailableError(RuntimeError):
    """当前 Stage 尚未提供可执行能力。"""


def _unique_names(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(str(value).strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} cannot contain empty names")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} cannot contain duplicate names")
    return normalized


def _readonly_array(
    value: np.ndarray,
    *,
    name: str,
    ndim: int | None = None,
    dtype: np.dtype | type | None = np.float32,
) -> np.ndarray:
    array = np.asarray(value, dtype=dtype).copy()
    if ndim is not None and array.ndim != ndim:
        raise ValueError(f"{name} must have ndim={ndim}")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class AssetManifest:
    """组件资产声明；构造时不访问磁盘。"""

    owner_uid: str
    asset_kind: str
    mjcf_sources: tuple[Path, ...] = ()
    asset_roots: tuple[Path, ...] = ()
    asset_version: str = "stage0"

    def __post_init__(self) -> None:
        if not self.owner_uid.strip():
            raise ValueError("owner_uid cannot be empty")
        if not self.asset_kind.strip():
            raise ValueError("asset_kind cannot be empty")
        object.__setattr__(
            self,
            "mjcf_sources",
            tuple(Path(path) for path in self.mjcf_sources),
        )
        object.__setattr__(
            self,
            "asset_roots",
            tuple(Path(path) for path in self.asset_roots),
        )


@dataclass(frozen=True)
class ReferenceSpec:
    """组件在场景编译后必须解析的稳定名称。"""

    body_names: tuple[str, ...] = ()
    joint_names: tuple[str, ...] = ()
    site_names: tuple[str, ...] = ()
    geom_names: tuple[str, ...] = ()
    actuator_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "body_names",
            "joint_names",
            "site_names",
            "geom_names",
            "actuator_names",
        ):
            object.__setattr__(
                self,
                field_name,
                _unique_names(getattr(self, field_name), field_name=field_name),
            )


@dataclass(frozen=True)
class InitialStateSpec:
    """Stage 0 的命名初态描述，不包含 solver 地址。"""

    joint_positions: tuple[tuple[str, float], ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskCompositionSpec:
    """具体任务对 Scene、Agent 和 Object 的轻量组合声明。"""

    task_uid: str
    scene_uid: str
    agent_uids: tuple[str, ...] = ()
    object_uids: tuple[str, ...] = ()
    placement_notes: tuple[str, ...] = ()
    success_definition: str = ""

    def __post_init__(self) -> None:
        if not self.task_uid.strip():
            raise ValueError("task_uid cannot be empty")
        if not self.scene_uid.strip():
            raise ValueError("scene_uid cannot be empty")
        object.__setattr__(
            self,
            "agent_uids",
            _unique_names(self.agent_uids, field_name="agent_uids"),
        )
        object.__setattr__(
            self,
            "object_uids",
            _unique_names(self.object_uids, field_name="object_uids"),
        )


@dataclass(frozen=True)
class ExternalActionContract:
    """Versioned scalar/vector action contract for non-controller environments.

    The historical ``no_op`` values remain unchanged for empty environments.
    Non-robot tasks use the same neutral contract with their native action
    interpretation; their canonical runtime-facing action is a task-family
    schema-specific ``universal_action``, not Panda's fixed eight-dimensional layout.
    """

    mode: str = "no_op"
    dimension: int = 0
    components: tuple[str, ...] = ()
    low: float = -1.0
    high: float = 1.0
    controller_backend: str = "dls_ik_position_target"
    actuator_control_mode: str = "position"
    gripper_convention: str = "none"
    gripper_close_value: float = 0.0
    gripper_open_value: float = 0.0
    schema_id: str = "task-env.no-op.v1"
    schema_version: str = "task-env-action-v1"
    unit: str = "none"
    actuator_interpretation: str = "none"
    task_family: str = "empty"

    def __post_init__(self) -> None:
        if self.dimension != len(self.components):
            raise ValueError("action dimension must match component count")
        if self.low >= self.high:
            raise ValueError("action bounds must be strictly increasing")
        if not self.low <= self.gripper_close_value <= self.high:
            raise ValueError("gripper_close_value must lie inside action bounds")
        if not self.low <= self.gripper_open_value <= self.high:
            raise ValueError("gripper_open_value must lie inside action bounds")
        for name in (
            "mode",
            "schema_id",
            "schema_version",
            "unit",
            "actuator_interpretation",
            "task_family",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} cannot be empty")

    @classmethod
    def for_mode(cls, mode: str) -> "ExternalActionContract":
        normalized = str(mode).strip()
        if normalized == "no_op":
            return cls()
        raise ValueError(f"unsupported external action mode: {mode!r}")


@dataclass(frozen=True)
class ActionModeSpec:
    """Versioned public schema for a Stage 10 controller action.

    It captures interpretation rather than implementation.  In particular,
    delta translations are physical metres; no hidden normalization factor is
    permitted by this schema.
    """

    schema_id: str
    schema_version: str
    controller_kind: str
    reference: str | None
    rotation_representation: str | None
    components: tuple[str, ...]
    low: tuple[float, ...]
    high: tuple[float, ...]
    translation_unit: str | None = None
    max_translation_delta_m: float | None = None
    max_rotation_delta_rad: float | None = None
    max_absolute_rotvec_angle_rad: float | None = None
    joint_order: tuple[str, ...] = ()
    gripper_convention: str = "normalized_signed_scalar"
    quaternion_convention: str | None = None
    reference_identity: str | None = None
    backend_provenance: str = "unresolved"

    def __post_init__(self) -> None:
        if not self.schema_id.strip():
            raise ValueError("ActionModeSpec schema_id cannot be empty")
        if self.schema_version != "task-env-action-v2":
            raise ValueError("unsupported ActionModeSpec schema_version")
        allowed_references = {
            "absolute_joint": {None},
            "absolute_pose": {"world", "base"},
            "delta_pose": {"world", "base", "ee"},
        }
        if self.controller_kind not in allowed_references:
            raise ValueError("unsupported ActionModeSpec controller_kind")
        if self.reference not in allowed_references[self.controller_kind]:
            raise ValueError("ActionModeSpec reference is invalid for controller_kind")
        if self.controller_kind == "absolute_joint":
            if self.rotation_representation is not None or self.translation_unit is not None:
                raise ValueError("absolute_joint cannot declare pose representation")
        elif self.rotation_representation not in {"quaternion_wxyz", "rotvec"}:
            raise ValueError("pose ActionModeSpec requires a rotation representation")
        if self.rotation_representation == "quaternion_wxyz":
            if self.quaternion_convention != "wxyz":
                raise ValueError("quaternion ActionModeSpec requires wxyz convention")
        elif self.quaternion_convention is not None:
            raise ValueError("rotvec ActionModeSpec cannot declare quaternion convention")
        components = _unique_names(self.components, field_name="action components")
        low = tuple(float(value) for value in self.low)
        high = tuple(float(value) for value in self.high)
        if len(components) != len(low) or len(components) != len(high):
            raise ValueError("action components and bounds must have equal lengths")
        if any(lower > upper for lower, upper in zip(low, high, strict=True)):
            raise ValueError("action lower bound cannot exceed upper bound")
        if self.controller_kind == "delta_pose":
            if self.translation_unit != "meters":
                raise ValueError("delta_pose translations must use physical meters")
            if self.max_translation_delta_m is None or self.max_translation_delta_m <= 0.0:
                raise ValueError("delta_pose requires max_translation_delta_m")
            if self.max_rotation_delta_rad is None or self.max_rotation_delta_rad <= 0.0:
                raise ValueError("delta_pose requires max_rotation_delta_rad")
        if self.rotation_representation == "rotvec":
            if (
                self.controller_kind == "absolute_pose"
                and (
                    self.max_absolute_rotvec_angle_rad is None
                    or self.max_absolute_rotvec_angle_rad <= 0.0
                )
            ):
                raise ValueError("absolute_pose rotvec requires max_absolute_rotvec_angle_rad")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "low", low)
        object.__setattr__(self, "high", high)
        object.__setattr__(self, "joint_order", _unique_names(self.joint_order, field_name="joint_order"))

    @property
    def dimension(self) -> int:
        return len(self.components)

    @classmethod
    def from_controller_config(
        cls,
        controller,
        *,
        joint_order: tuple[str, ...] = (
            "joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7"
        ),
    ) -> "ActionModeSpec":
        """Build the frozen public schema without constructing a runtime controller."""

        kind = controller.kind
        if kind == "absolute_joint":
            components = (*joint_order, "gripper")
            return cls(
                schema_id="task-env.absolute_joint.v1",
                schema_version="task-env-action-v2",
                controller_kind=kind,
                reference=None,
                rotation_representation=None,
                components=components,
                low=(*(-float("inf") for _ in joint_order), -1.0),
                high=(*(float("inf") for _ in joint_order), 1.0),
                joint_order=joint_order,
                backend_provenance="absolute_joint_position_servo",
            )
        rotation = controller.rotation_representation
        if kind == "delta_pose":
            rotation_components = (
                ("dqw", "dqx", "dqy", "dqz")
                if rotation == "quaternion_wxyz"
                else ("drx", "dry", "drz")
            )
        else:
            rotation_components = (
                ("qw", "qx", "qy", "qz")
                if rotation == "quaternion_wxyz"
                else ("rx", "ry", "rz")
            )
        prefixes = ("x", "y", "z") if kind == "absolute_pose" else ("dx", "dy", "dz")
        components = (*prefixes, *rotation_components, "gripper")
        if kind == "absolute_pose":
            rotation_bound = (
                float("inf")
                if rotation == "quaternion_wxyz"
                else controller.max_absolute_rotvec_angle_rad
            )
            return cls(
                schema_id=f"task-env.absolute_pose.{rotation}.v1",
                schema_version="task-env-action-v2",
                controller_kind=kind,
                reference=controller.reference,
                rotation_representation=rotation,
                components=components,
                low=(
                    *(-float("inf") for _ in range(3)),
                    *(-rotation_bound for _ in rotation_components),
                    -1.0,
                ),
                high=(
                    *(float("inf") for _ in range(3)),
                    *(rotation_bound for _ in rotation_components),
                    1.0,
                ),
                quaternion_convention=("wxyz" if rotation == "quaternion_wxyz" else None),
                max_absolute_rotvec_angle_rad=(
                    controller.max_absolute_rotvec_angle_rad
                    if rotation == "rotvec"
                    else None
                ),
                backend_provenance="dls_ik_pose_target",
            )
        rotation_limit = (
            1.0 if rotation == "quaternion_wxyz" else controller.max_rotation_delta_rad
        )
        return cls(
            schema_id=f"task-env.delta_pose.{rotation}.v1",
            schema_version="task-env-action-v2",
            controller_kind=kind,
            reference=controller.reference,
            rotation_representation=rotation,
            components=components,
            low=(
                *(-controller.max_translation_delta_m for _ in range(3)),
                *(-rotation_limit for _ in rotation_components),
                -1.0,
            ),
            high=(
                *(controller.max_translation_delta_m for _ in range(3)),
                *(rotation_limit for _ in rotation_components),
                1.0,
            ),
            translation_unit="meters",
            max_translation_delta_m=controller.max_translation_delta_m,
            max_rotation_delta_rad=controller.max_rotation_delta_rad,
            quaternion_convention=("wxyz" if rotation == "quaternion_wxyz" else None),
            backend_provenance="dls_ik_pose_target",
        )


@dataclass(frozen=True)
class EpisodePhysicsState:
    """一次 episode reset 所需的基础物理状态。"""

    qpos: np.ndarray
    qvel: np.ndarray
    qacc: np.ndarray
    ctrl: np.ndarray
    act: np.ndarray

    def __post_init__(self) -> None:
        for name in ("qpos", "qvel", "qacc", "ctrl", "act"):
            object.__setattr__(
                self,
                name,
                _readonly_array(getattr(self, name), name=name, ndim=1),
            )


@dataclass(frozen=True)
class PhysicsStateSnapshot:
    """RuntimeBoundary 的完整恢复快照容器。"""

    arrays: Mapping[str, np.ndarray]

    def __post_init__(self) -> None:
        frozen = {
            str(name): _readonly_array(value, name=str(name), dtype=None)
            for name, value in self.arrays.items()
        }
        object.__setattr__(self, "arrays", MappingProxyType(frozen))


@dataclass(frozen=True)
class SnapshotRequest:
    """一次公共 CPU 快照需要 materialize 的字段集合。"""

    qacc: bool = True
    ctrl: bool = True
    actuator_force: bool = False
    body_pose: bool = True
    site_pose: bool = True
    site_jacobians: bool = False
    contact_summary: bool = False
    simulation_time: bool = False


@dataclass(frozen=True)
class ContactSummary:
    """任务层可消费的稳定接触摘要占位契约。"""

    pair_counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pair_counts",
            MappingProxyType(
                {str(name): int(count) for name, count in self.pair_counts.items()}
            ),
        )


@dataclass(frozen=True)
class TaskEvaluation:
    """TaskDefinition 对一个 step/reset 的单次任务语义评估。"""

    reward: float
    success: bool
    failure: bool = False
    metrics: Mapping[str, float | bool] = field(default_factory=dict)
    reward_terms: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reward", float(self.reward))
        object.__setattr__(self, "success", bool(self.success))
        object.__setattr__(self, "failure", bool(self.failure))
        object.__setattr__(
            self,
            "metrics",
            MappingProxyType(
                {
                    str(name): (
                        bool(value) if isinstance(value, bool) else float(value)
                    )
                    for name, value in self.metrics.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "reward_terms",
            MappingProxyType(
                {str(name): float(value) for name, value in self.reward_terms.items()}
            ),
        )


@dataclass(frozen=True)
class RuntimeSnapshot:
    """一个 control step 只生成一次的公共 CPU 快照。"""

    qpos: np.ndarray
    qvel: np.ndarray
    qacc: np.ndarray | None = None
    ctrl: np.ndarray | None = None
    actuator_force: np.ndarray | None = None
    body_xpos: np.ndarray | None = None
    body_xquat: np.ndarray | None = None
    site_xpos: np.ndarray | None = None
    site_xquat: np.ndarray | None = None
    site_jacp: np.ndarray | None = None
    site_jacr: np.ndarray | None = None
    contact_summary: ContactSummary | None = None
    simulation_time: float | None = None

    def __post_init__(self) -> None:
        for name in (
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
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    _readonly_array(value, name=name),
                )


@dataclass(frozen=True)
class CameraPose:
    """相机在当前 snapshot 下的 world pose 与 visualizer 写入参数。"""

    position: np.ndarray
    quaternion_wxyz: np.ndarray
    look_at: np.ndarray
    up: np.ndarray

    def __post_init__(self) -> None:
        for name, ndim in (
            ("position", 1),
            ("quaternion_wxyz", 1),
            ("look_at", 1),
            ("up", 1),
        ):
            object.__setattr__(
                self,
                name,
                _readonly_array(getattr(self, name), name=name, ndim=ndim),
            )
        if self.position.shape != (3,):
            raise ValueError("camera position must have shape (3,)")
        if self.quaternion_wxyz.shape != (4,):
            raise ValueError("camera quaternion_wxyz must have shape (4,)")
        if self.look_at.shape != (3,):
            raise ValueError("camera look_at must have shape (3,)")
        if self.up.shape != (3,):
            raise ValueError("camera up must have shape (3,)")


@dataclass(frozen=True)
class CameraMetadata:
    """单个相机在 observation / recorder 中共享的稳定元数据。"""

    name: str
    width: int
    height: int
    rgb: bool
    depth: bool
    frame: str
    parent: str | None
    fov_y: float
    near: float
    far: float
    pose: CameraPose
    intrinsic: np.ndarray
    extrinsic: np.ndarray

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("camera metadata name cannot be empty")
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(
            self,
            "intrinsic",
            _readonly_array(self.intrinsic, name="intrinsic", ndim=2),
        )
        object.__setattr__(
            self,
            "extrinsic",
            _readonly_array(self.extrinsic, name="extrinsic", ndim=2),
        )
        if self.intrinsic.shape != (3, 3):
            raise ValueError("camera intrinsic must have shape (3, 3)")
        if self.extrinsic.shape != (4, 4):
            raise ValueError("camera extrinsic must have shape (4, 4)")


@dataclass(frozen=True)
class SensorObservation:
    """相机传感器输出的视觉快照；允许图像分支为空。"""

    rgb: Mapping[str, np.ndarray] = field(default_factory=dict)
    depth: Mapping[str, np.ndarray] = field(default_factory=dict)
    camera_metadata: Mapping[str, CameraMetadata] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rgb",
            MappingProxyType(
                {
                    str(name): _readonly_array(value, name=f"rgb.{name}", ndim=3)
                    for name, value in self.rgb.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "depth",
            MappingProxyType(
                {
                    str(name): _readonly_array(value, name=f"depth.{name}", ndim=2)
                    for name, value in self.depth.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "camera_metadata",
            MappingProxyType(dict(self.camera_metadata)),
        )


@dataclass(frozen=True)
class ObservationFieldSpec:
    """一个观测字段的稳定 schema 描述。"""

    name: str
    shape: tuple[int, ...]
    dtype: str = "float32"
    semantic: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("observation field name cannot be empty")
        if any(int(dim) < 0 for dim in self.shape):
            raise ValueError("observation field shape dimensions cannot be negative")
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "shape", tuple(int(dim) for dim in self.shape))
        object.__setattr__(self, "dtype", str(np.dtype(self.dtype)))
        object.__setattr__(self, "semantic", str(self.semantic))


@dataclass(frozen=True)
class ObservationSchema:
    """ObservationBuilder 输出的版本化字段顺序。"""

    version: str
    fields: tuple[ObservationFieldSpec, ...]
    quaternion_convention: str = "wxyz"
    groups: tuple[str, ...] = ("state", "privileged_state")

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("observation schema version cannot be empty")
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("observation schema cannot contain duplicate fields")
        groups = _unique_names(self.groups, field_name="observation groups")
        object.__setattr__(self, "version", str(self.version))
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "quaternion_convention", str(self.quaternion_convention))
        object.__setattr__(self, "groups", groups)

    @property
    def field_names(self) -> tuple[str, ...]:
        """顶层 observation 字段顺序。"""

        return self.groups

    @property
    def leaf_field_names(self) -> tuple[str, ...]:
        """完整叶子字段路径顺序，如 ``state.qpos``。"""

        return tuple(field.name for field in self.fields)

    def validate(self, observation: Mapping[str, Any]) -> None:
        """检查字段集合、顺序、shape 与 dtype。"""

        if tuple(observation.keys()) != self.field_names:
            raise ValueError("observation keys do not match schema order")
        expected_tree: dict[str, OrderedDict[str, Any]] = {
            group: OrderedDict() for group in self.groups
        }
        for field in self.fields:
            parts = tuple(part for part in field.name.split(".") if part)
            if len(parts) < 2:
                raise ValueError(
                    f"observation field {field.name} must use group.leaf naming"
                )
            group = parts[0]
            if group not in expected_tree:
                raise ValueError(
                    f"observation field {field.name} uses unknown group {group}"
                )
            cursor = expected_tree[group]
            for key in parts[1:-1]:
                cursor = cursor.setdefault(key, OrderedDict())
            cursor[parts[-1]] = field

        def _validate_tree(expected: OrderedDict[str, Any], value: Any, path: str) -> None:
            if not isinstance(value, MappingABC):
                raise ValueError(f"observation group {path} must be a mapping")
            if tuple(value.keys()) != tuple(expected.keys()):
                raise ValueError(f"observation group {path} keys do not match schema order")
            for key, child in expected.items():
                if isinstance(child, OrderedDict):
                    _validate_tree(child, value[key], f"{path}.{key}")

        for group, expected in expected_tree.items():
            value = observation[group]
            _validate_tree(expected, value, group)
        for field in self.fields:
            parts = tuple(field.name.split("."))
            value = observation[parts[0]]
            for key in parts[1:]:
                value = value[key]
            array = np.asarray(value)
            if array.shape != field.shape:
                raise ValueError(
                    f"observation field {field.name} has shape {array.shape}, "
                    f"expected {field.shape}"
                )
            if np.dtype(array.dtype) != np.dtype(field.dtype):
                raise ValueError(
                    f"observation field {field.name} has dtype {array.dtype}, "
                    f"expected {field.dtype}"
                )


def _freeze_observation_value(value: Any, *, name: str) -> Any:
    if isinstance(value, MappingABC):
        return freeze_observation(tuple(value.items()))
    # ObservationSchema, not the generic freezer, owns leaf dtypes.  In
    # particular CameraSpec may deliberately expose uint8 RGB leaves.
    return _readonly_array(np.asarray(value), name=name, dtype=None)


def freeze_observation(values: Sequence[tuple[str, Any]]) -> OrderedDict[str, Any]:
    """按给定顺序冻结 observation 树中的数组。"""

    frozen: OrderedDict[str, Any] = OrderedDict()
    for name, value in values:
        if name in frozen:
            raise ValueError(f"duplicate observation field: {name}")
        frozen[str(name)] = _freeze_observation_value(value, name=str(name))
    return frozen


@dataclass(frozen=True)
class ControlCommand:
    """ActionAdapter 将来输出的控制命令。"""

    actuator_ctrl: np.ndarray
    external_action: np.ndarray
    requested_action: np.ndarray
    controller_target: np.ndarray
    universal_action: np.ndarray
    mode: str
    action_clipped: bool = False

    def __post_init__(self) -> None:
        for name in (
            "actuator_ctrl",
            "external_action",
            "requested_action",
            "controller_target",
            "universal_action",
        ):
            object.__setattr__(
                self,
                name,
                _readonly_array(getattr(self, name), name=name, ndim=1),
            )


@dataclass(frozen=True)
class AppliedControl:
    """RuntimeBoundary 实际应用的控制结果。"""

    requested_ctrl: np.ndarray
    applied_ctrl: np.ndarray
    clipped: bool

    def __post_init__(self) -> None:
        for name in ("requested_ctrl", "applied_ctrl"):
            object.__setattr__(
                self,
                name,
                _readonly_array(getattr(self, name), name=name, ndim=1),
            )
