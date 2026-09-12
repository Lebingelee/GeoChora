"""公共 batch runtime contract。

该模块只包含 NumPy value object 和纯 Python Protocol。具体 Taichi runtime
可以替换，但上层 task/vector/recorder 不需要知道 field、kernel 或 readback
布局。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


def _is_boolean_device_mask(value: Any) -> bool:
    dtype = getattr(value, "dtype", None)
    return dtype is not None and str(dtype) in {"bool", "bool_", "torch.bool"}


def validate_device_reset_selection(
    selection: "DeviceResetSelection",
    *,
    mask: Any | None = None,
    num_envs: int | None = None,
    device: str | None = None,
    require_data_pointer: bool = False,
) -> None:
    """Defensively validate a selection without importing a device library."""

    if not isinstance(selection, DeviceResetSelection):
        raise TypeError("reset selection must be DeviceResetSelection")
    expected_num_envs = selection.num_envs if num_envs is None else int(num_envs)
    expected_device = selection.device if device is None else str(device)
    if selection.num_envs != expected_num_envs or expected_num_envs < 1:
        raise ValueError("reset selection num_envs does not match runtime")
    if selection.device != expected_device:
        raise ValueError("reset selection device does not match runtime")
    if tuple(getattr(selection.device_mask, "shape", ())) != (expected_num_envs,):
        raise ValueError("reset selection device_mask shape does not match runtime")
    if not _is_boolean_device_mask(selection.device_mask):
        raise ValueError("reset selection device_mask must have boolean dtype")
    if str(getattr(selection.device_mask, "device", "")) != expected_device:
        raise ValueError("reset selection device_mask device does not match runtime")

    if mask is not None:
        if tuple(getattr(mask, "shape", ())) != (expected_num_envs,):
            raise ValueError("reset selection actual mask shape does not match runtime")
        if not _is_boolean_device_mask(mask):
            raise ValueError("reset selection actual mask must have boolean dtype")
        if str(getattr(mask, "device", "")) != expected_device:
            raise ValueError("reset selection actual mask device does not match runtime")
        if selection.device_mask is not mask:
            raise ValueError("reset selection device_mask identity is stale")
        selection_pointer = getattr(selection.device_mask, "data_ptr", None)
        mask_pointer = getattr(mask, "data_ptr", None)
        if require_data_pointer and (
            not callable(selection_pointer) or not callable(mask_pointer)
        ):
            raise ValueError("reset selection device_mask data pointer is unavailable")
        if callable(selection_pointer) and callable(mask_pointer) and (
            int(selection_pointer()) != int(mask_pointer())
        ):
            raise ValueError("reset selection device_mask data pointer is stale")

    host_mask = selection.host_mask
    selected_slots = selection.selected_slots
    if (
        not isinstance(host_mask, np.ndarray)
        or host_mask.shape != (expected_num_envs,)
        or host_mask.dtype != np.bool_
    ):
        raise ValueError("reset selection host_mask must be a bool array of shape (B,)")
    if host_mask.flags.writeable:
        raise ValueError("reset selection host_mask must be read-only")
    if (
        not isinstance(selected_slots, np.ndarray)
        or selected_slots.ndim != 1
        or not np.issubdtype(selected_slots.dtype, np.integer)
    ):
        raise ValueError("reset selection selected_slots must have integer dtype")
    if selected_slots.flags.writeable:
        raise ValueError("reset selection selected_slots must be read-only")
    if not isinstance(selection.selected_count, (int, np.integer)):
        raise ValueError("reset selection selected_count must be an integer")
    selected_count = int(selection.selected_count)
    if selected_count < 0 or selected_count > expected_num_envs:
        raise ValueError("reset selection selected_count is out of range")
    if selected_slots.size != selected_count:
        raise ValueError("reset selection selected_count does not match selected_slots")
    if selected_slots.size:
        if int(selected_slots[0]) < 0 or int(selected_slots[-1]) >= expected_num_envs:
            raise ValueError("reset selection selected_slots are out of range")
        if selected_slots.size > 1 and not bool(np.all(np.diff(selected_slots) > 0)):
            raise ValueError("reset selection selected_slots must be strictly ascending")
    if (
        int(np.count_nonzero(host_mask)) != selected_count
        or (selected_count and not bool(np.all(host_mask[selected_slots])))
    ):
        raise ValueError(
            "reset selection host_mask flatnonzero differs from selected_slots"
        )


def _readonly_batch_array(value: Any, *, name: str) -> np.ndarray:
    array = np.asarray(value).copy()
    if array.ndim < 1:
        raise ValueError(f"batch value {name} must have a leading batch dimension")
    if not np.isfinite(array).all():
        raise ValueError(f"batch value {name} must be finite")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class BatchState:
    """命名的 host snapshot。

    构造时会复制 NumPy 数组并将其设为只读；调用方获得的是 value
    semantics，不是 runtime-owned storage 的 view。
    """

    arrays: Mapping[str, np.ndarray]

    def __post_init__(self) -> None:
        frozen = {
            str(name): _readonly_batch_array(value, name=str(name))
            for name, value in self.arrays.items()
        }
        if not frozen:
            raise ValueError("BatchState must contain at least one named array")
        batch_sizes = {array.shape[0] for array in frozen.values()}
        if len(batch_sizes) != 1:
            raise ValueError("all BatchState arrays must share the batch dimension")
        object.__setattr__(self, "arrays", frozen)

    @property
    def num_envs(self) -> int:
        return next(iter(self.arrays.values())).shape[0]

    def get(self, name: str) -> np.ndarray:
        try:
            return self.arrays[str(name)]
        except KeyError as exc:
            raise KeyError(f"unknown batch state field: {name}") from exc


@dataclass(frozen=True)
class BatchDiagnostics:
    """命名的 runtime diagnostics；不携带未命名列式 readback。"""

    arrays: Mapping[str, np.ndarray] | None = None

    def __post_init__(self) -> None:
        values = dict(self.arrays or {})
        frozen = {
            str(name): _readonly_batch_array(value, name=str(name))
            for name, value in values.items()
        }
        batch_sizes = {array.shape[0] for array in frozen.values()}
        if len(batch_sizes) > 1:
            raise ValueError("all BatchDiagnostics arrays must share the batch dimension")
        object.__setattr__(self, "arrays", frozen)

    def get(self, name: str) -> np.ndarray:
        try:
            return self.arrays[str(name)]
        except KeyError as exc:
            raise KeyError(f"unknown batch diagnostic: {name}") from exc


@dataclass(frozen=True)
class BatchResetResult:
    """runtime.reset() 的公开结果。"""

    state: BatchState
    diagnostics: BatchDiagnostics = BatchDiagnostics()


@dataclass(frozen=True)
class BatchStepResult:
    """runtime.step() 的公开结果。"""

    state: BatchState
    diagnostics: BatchDiagnostics = BatchDiagnostics()


def _readonly_randomization_array(
    value: Any,
    *,
    name: str,
    dtype: np.dtype | type,
    ndim: int,
) -> np.ndarray:
    """Normalize a selected-world randomization array at the public boundary."""

    array = np.asarray(value, dtype=dtype)
    if array.ndim != int(ndim):
        raise ValueError(
            f"world randomization field {name!r} must have {ndim} dimensions, "
            f"got shape {array.shape}"
        )
    if not np.isfinite(array).all():
        raise ValueError(f"world randomization field {name!r} must be finite")
    result = np.ascontiguousarray(array).copy()
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class WorldRandomizationBatch:
    """Selected-world domain-randomization payload.

    This value object is deliberately task-agnostic.  A task reset sampler
    may produce it through the namespaced ``parameters["world_randomization"]``
    mapping, while a runtime only consumes fixed-shape arrays and the selected
    world indices.  The optional fields are independent capabilities: a
    runtime may support friction, push scheduling, mass, or a subset thereof.
    """

    schema_id: str
    world_indices: np.ndarray
    friction_mu: np.ndarray | None = None
    push_event_steps: np.ndarray | None = None
    push_velocity_xy: np.ndarray | None = None
    base_mass_delta_kg: np.ndarray | None = None
    lifetime: str = "episode"
    reference_profile: str = ""
    inertia_policy: str = "reference_mass_only"
    push_on_reset_boundary: bool = False

    def __post_init__(self) -> None:
        schema = str(self.schema_id).strip()
        if not schema:
            raise ValueError("world randomization schema_id cannot be empty")
        indices = np.asarray(self.world_indices, dtype=np.int64).reshape(-1)
        if indices.size and (np.any(indices < 0) or np.any(np.diff(indices) <= 0)):
            raise ValueError("world randomization world_indices must be sorted and unique")
        indices = np.ascontiguousarray(indices).copy()
        indices.setflags(write=False)
        object.__setattr__(self, "schema_id", schema)
        object.__setattr__(self, "world_indices", indices)
        lifetime = str(self.lifetime).strip().lower()
        if lifetime not in {"construction", "episode"}:
            raise ValueError("world randomization lifetime must be construction or episode")
        object.__setattr__(self, "lifetime", lifetime)
        profile = str(self.reference_profile).strip()
        object.__setattr__(self, "reference_profile", profile)
        policy = str(self.inertia_policy).strip().lower()
        if policy not in {"reference_mass_only", "scale_inertia_with_mass"}:
            raise ValueError(
                "world randomization inertia_policy must be reference_mass_only "
                "or scale_inertia_with_mass"
            )
        object.__setattr__(self, "inertia_policy", policy)
        object.__setattr__(self, "push_on_reset_boundary", bool(self.push_on_reset_boundary))

        count = int(indices.size)
        normalized: dict[str, np.ndarray | None] = {}
        if self.friction_mu is not None:
            normalized["friction_mu"] = _readonly_randomization_array(
                self.friction_mu, name="friction_mu", dtype=np.float32, ndim=1
            )
        else:
            normalized["friction_mu"] = None
        if self.base_mass_delta_kg is not None:
            normalized["base_mass_delta_kg"] = _readonly_randomization_array(
                self.base_mass_delta_kg,
                name="base_mass_delta_kg",
                dtype=np.float32,
                ndim=1,
            )
        else:
            normalized["base_mass_delta_kg"] = None
        if self.push_event_steps is not None:
            normalized["push_event_steps"] = _readonly_randomization_array(
                self.push_event_steps,
                name="push_event_steps",
                dtype=np.int32,
                ndim=2,
            )
            if normalized["push_event_steps"].shape[0] != count:
                raise ValueError("push_event_steps leading dimension must match world_indices")
        else:
            normalized["push_event_steps"] = None
        if self.push_velocity_xy is not None:
            normalized["push_velocity_xy"] = _readonly_randomization_array(
                self.push_velocity_xy,
                name="push_velocity_xy",
                dtype=np.float32,
                ndim=3,
            )
            if normalized["push_velocity_xy"].shape[0] != count:
                raise ValueError("push_velocity_xy leading dimension must match world_indices")
            if normalized["push_velocity_xy"].shape[2] != 2:
                raise ValueError("push_velocity_xy must have trailing shape (K, 2)")
            if normalized["push_event_steps"] is None or tuple(normalized["push_velocity_xy"].shape[:2]) != tuple(normalized["push_event_steps"].shape):
                raise ValueError("push event steps and velocity schedule shapes must match")
        else:
            normalized["push_velocity_xy"] = None
        for name in ("friction_mu", "base_mass_delta_kg"):
            value = normalized[name]
            if value is not None and value.shape != (count,):
                raise ValueError(f"{name} leading shape must be ({count},)")
        for name, value in normalized.items():
            object.__setattr__(self, name, value)

    @property
    def selected_count(self) -> int:
        return int(self.world_indices.size)

    @property
    def event_capacity(self) -> int:
        return 0 if self.push_event_steps is None else int(self.push_event_steps.shape[1])

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-friendly provenance without exposing writable arrays."""

        return {
            "schema_id": self.schema_id,
            "world_indices": self.world_indices.tolist(),
            "friction_mu": None if self.friction_mu is None else self.friction_mu.tolist(),
            "push_event_steps": None if self.push_event_steps is None else self.push_event_steps.tolist(),
            "push_velocity_xy": None if self.push_velocity_xy is None else self.push_velocity_xy.tolist(),
            "base_mass_delta_kg": None if self.base_mass_delta_kg is None else self.base_mass_delta_kg.tolist(),
            "lifetime": self.lifetime,
            "reference_profile": self.reference_profile,
            "inertia_policy": self.inertia_policy,
            "push_on_reset_boundary": self.push_on_reset_boundary,
        }


def build_world_randomization_batch(
    parameters: Sequence[Mapping[str, Any]],
    *,
    reset_mask: np.ndarray,
) -> WorldRandomizationBatch | None:
    """Extract a namespaced payload from full or selected reset parameters."""

    mask = np.asarray(reset_mask, dtype=np.bool_)
    if mask.ndim != 1:
        raise ValueError("world randomization reset_mask must be one-dimensional")
    selected = np.flatnonzero(mask).astype(np.int64, copy=False)
    entries = list(parameters)
    if len(entries) == mask.size:
        selected_entries = [entries[int(index)] for index in selected]
    elif len(entries) == selected.size:
        selected_entries = entries
    else:
        raise ValueError(
            "reset parameters must contain either one entry per world or one entry per selected world"
        )
    payloads = []
    for entry in selected_entries:
        if not isinstance(entry, Mapping):
            raise TypeError("reset parameters must be mappings")
        value = entry.get("world_randomization")
        if value is None:
            payloads.append(None)
        elif isinstance(value, Mapping):
            payloads.append(value)
        else:
            raise TypeError("parameters['world_randomization'] must be a mapping")
    if not payloads or all(value is None for value in payloads):
        return None
    if any(value is None for value in payloads):
        raise ValueError("world_randomization must be present for every selected world")
    first = payloads[0]
    schema_id = str(first.get("schema_id", "task-env-world-randomization-v1"))
    lifetime = str(first.get("lifetime", "episode"))
    reference_profile = str(first.get("reference_profile", ""))
    inertia_policy = str(first.get("inertia_policy", "reference_mass_only"))
    push_on_reset = bool(first.get("push_on_reset_boundary", False))

    def _same(name: str, default: Any = None) -> list[Any]:
        values = []
        for value in payloads:
            current = value.get(name, default)
            values.append(current)
        return values

    friction_values = _same("friction_mu")
    mass_values = _same("base_mass_delta_kg")
    event_values = _same("push_event_steps")
    velocity_values = _same("push_velocity_xy")
    for value in payloads[1:]:
        if str(value.get("schema_id", schema_id)) != schema_id:
            raise ValueError("world randomization schema_id must be consistent across selected worlds")
        for key, expected in (
            ("lifetime", lifetime),
            ("reference_profile", reference_profile),
            ("inertia_policy", inertia_policy),
        ):
            if str(value.get(key, expected)) != expected:
                raise ValueError(f"world randomization {key} must be consistent across selected worlds")
        if bool(value.get("push_on_reset_boundary", push_on_reset)) != push_on_reset:
            raise ValueError("world randomization push_on_reset_boundary must be consistent")

    def _vector(values: list[Any], name: str) -> np.ndarray | None:
        if all(item is None for item in values):
            return None
        if any(item is None for item in values):
            raise ValueError(f"world randomization {name} must be present for every selected world")
        return np.asarray(values, dtype=np.float32)

    friction = _vector(friction_values, "friction_mu")
    mass = _vector(mass_values, "base_mass_delta_kg")
    if all(item is None for item in event_values) and all(item is None for item in velocity_values):
        event_steps = event_velocity = None
    elif any(item is None for item in (*event_values, *velocity_values)):
        raise ValueError("push event steps and velocity schedule must be present together")
    else:
        event_steps = np.asarray(event_values, dtype=np.int32)
        event_velocity = np.asarray(velocity_values, dtype=np.float32)
    return WorldRandomizationBatch(
        schema_id=schema_id,
        world_indices=selected,
        friction_mu=friction,
        push_event_steps=event_steps,
        push_velocity_xy=event_velocity,
        base_mass_delta_kg=mass,
        lifetime=lifetime,
        reference_profile=reference_profile,
        inertia_policy=inertia_policy,
        push_on_reset_boundary=push_on_reset,
    )



class BatchRuntimeProtocol(Protocol):
    """task-owned batch adapter 可依赖的最小 runtime 边界。"""

    num_envs: int

    def reset(
        self,
        *,
        state: Mapping[str, np.ndarray],
        mask: np.ndarray,
    ) -> BatchResetResult:
        ...

    def step(self, action: np.ndarray) -> BatchStepResult:
        ...

    def resource_summary(self) -> dict[str, Any]:
        ...

    def close(self) -> None:
        ...


class WorldRandomizationRuntimeProtocol(Protocol):
    """Optional reset-boundary capability for fixed-shape world parameters."""

    def apply_world_randomization(
        self,
        *,
        payload: WorldRandomizationBatch,
        mask: np.ndarray,
    ) -> None:
        ...


@dataclass(frozen=True)
class DeviceBatchState:
    """Opaque device-resident named state exposed at the learner boundary.

    Values are intentionally typed as ``Any`` so importing TaskEnv does not
    import Torch, TensorDict, Taichi, or a particular device array library.
    Implementations must expose named arrays/tensors with a leading batch
    dimension and must not return positional readback rows。冻结容器不代表底层
    arrays 不可变：它们可以是 runtime 所有的 reference/view，调用方不拥有其
    生命周期；后续 runtime step 或 reset 可能更新同一底层存储。
    """

    arrays: Mapping[str, Any]
    device: str
    num_envs: int

    def __post_init__(self) -> None:
        if int(self.num_envs) < 1:
            raise ValueError("DeviceBatchState num_envs must be positive")
        normalized = {str(name): value for name, value in self.arrays.items()}
        if not normalized:
            raise ValueError("DeviceBatchState must contain named values")
        for name, value in normalized.items():
            shape = getattr(value, "shape", None)
            if shape is None or len(tuple(shape)) < 1:
                raise ValueError(f"device state {name!r} must expose a leading batch dimension")
            if int(shape[0]) != int(self.num_envs):
                raise ValueError(
                    f"device state {name!r} batch dimension {shape[0]} does not match "
                    f"num_envs={self.num_envs}"
                )
        object.__setattr__(self, "arrays", normalized)
        object.__setattr__(self, "device", str(self.device))


@dataclass(frozen=True)
class DeviceBatchTransition:
    """Named learner transition returned by an optional device bridge.

    The values may be Torch tensors or another device-array implementation;
    this value object intentionally carries no learner import.  ``infos`` is
    optional evidence/metrics and is not used as a physics state channel.
    """

    observation: Any
    reward: Any
    terminated: Any
    truncated: Any
    device: str
    infos: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "device", str(self.device))


@dataclass(frozen=True)
class DeviceResetSelection:
    """One validated device/host view of an autoreset mask.

    The device mask remains opaque so this dependency-safe contract does not
    import Torch.  Host arrays are owned immutable copies, making the value
    safe to pass through runtime and task reset hooks without recomputation.
    """

    device_mask: Any
    host_mask: np.ndarray
    selected_slots: np.ndarray
    selected_count: int
    num_envs: int
    device: str

    def __post_init__(self) -> None:
        num_envs = int(self.num_envs)
        selected_count = int(self.selected_count)
        device = str(self.device)
        if num_envs < 1:
            raise ValueError("DeviceResetSelection num_envs must be positive")
        if selected_count < 0 or selected_count > num_envs:
            raise ValueError("DeviceResetSelection selected_count is out of range")
        shape = getattr(self.device_mask, "shape", None)
        if shape is None or tuple(shape) != (num_envs,):
            raise ValueError(
                f"DeviceResetSelection device_mask must have shape ({num_envs},)"
            )
        if not _is_boolean_device_mask(self.device_mask):
            raise ValueError("DeviceResetSelection device_mask must have boolean dtype")
        mask_device = getattr(self.device_mask, "device", None)
        if mask_device is None or str(mask_device) != device:
            raise ValueError(
                "DeviceResetSelection device does not match device_mask device"
            )

        host_mask = np.asarray(self.host_mask)
        if host_mask.dtype != np.bool_ or host_mask.shape != (num_envs,):
            raise ValueError(
                f"DeviceResetSelection host_mask must be bool shape ({num_envs},)"
            )
        selected_slots = np.asarray(self.selected_slots)
        if selected_slots.ndim != 1 or not np.issubdtype(
            selected_slots.dtype, np.integer
        ):
            raise ValueError("DeviceResetSelection selected_slots must be a 1-D integer array")
        if selected_slots.size != selected_count:
            raise ValueError(
                "DeviceResetSelection selected_count does not match selected_slots"
            )
        host_mask = host_mask.astype(np.bool_, copy=True)
        selected_slots = selected_slots.astype(np.int64, copy=True)
        host_mask.setflags(write=False)
        selected_slots.setflags(write=False)
        object.__setattr__(self, "host_mask", host_mask)
        object.__setattr__(self, "selected_slots", selected_slots)
        object.__setattr__(self, "selected_count", selected_count)
        object.__setattr__(self, "num_envs", num_envs)
        object.__setattr__(self, "device", device)
        validate_device_reset_selection(self)


@dataclass(frozen=True)
class DeviceBatchResetResult:
    """Device-resident autoreset result returned by the task lifecycle."""

    state: DeviceBatchState
    observation: Any
    device: str
    infos: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "device", str(self.device))


class DeviceBatchRuntimeProtocol(Protocol):
    """Optional additive device path parallel to ``BatchRuntimeProtocol``."""

    num_envs: int

    def read_device_state(self, names: tuple[str, ...]) -> DeviceBatchState:
        """返回命名状态 tensor，不暴露内部字段；返回值可以是 runtime-owned view。

        调用方不得超出 runtime 文档规定的生命周期持有或修改这些 view。
        """
        ...

    def step_device(self, control: Any) -> DeviceBatchState:
        """Apply one public control tick on the runtime's device."""
        ...

    def reset_device(
        self,
        state: Mapping[str, Any],
        mask: Any,
        *,
        selection: DeviceResetSelection | None = None,
    ) -> DeviceBatchState:
        """在 runtime device 上执行 masked reset。

        如果提供 ``selection``，adapter 必须转发创建该 selection 时使用的原始
        mask 对象；调用前不得 clone、重新创建或转换该 mask。
        """
        ...


__all__ = [
    "BatchDiagnostics",
    "BatchResetResult",
    "BatchRuntimeProtocol",
    "BatchState",
    "BatchStepResult",
    "DeviceBatchRuntimeProtocol",
    "DeviceBatchResetResult",
    "DeviceBatchState",
    "DeviceBatchTransition",
    "DeviceResetSelection",
    "WorldRandomizationBatch",
    "WorldRandomizationRuntimeProtocol",
    "build_world_randomization_batch",
    "validate_device_reset_selection",
]
