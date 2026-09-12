"""通用的 device 字段所有权与生命周期计划。

该计划刻意保持 task-agnostic，只描述具备 device 能力的 batch task 之间稳定的
runtime 命名字段和 transition 所有权；task 的 observation/reward 代数仍归
task definition 管理。本模块不导入 Torch、Taichi、learner 或 task UID。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .admission import (
    RuntimePortAdmission,
    admit_runtime_port,
    resolve_device_transfer_mode,
)
from .contracts import DeviceBatchState


DEVICE_FIELD_PLAN_VERSION = "task-env-device-field-plan-v1"

_BASE_STATE_FIELDS = (
    "qpos",
    "qvel",
    "qacc",
    "ctrl",
    "act",
    "body_xpos",
    "body_xquat",
    "site_xpos",
    "site_xquat",
)
_CONTACT_STATE_FIELDS = (
    "ground_contact_active",
    "body_contact_active",
    "ground_contact_count",
    "body_contact_count",
    "ground_contact_geom",
)


@dataclass(frozen=True)
class DeviceFieldSpec:
    """一个命名 device 字段的所有权与生命周期信息。"""

    name: str
    role: str
    owner: str
    dtype: str | None = None
    device: str | None = None
    reset_policy: str = "persistent"
    producer: str = ""
    consumer: str = ""
    readback_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "owner": self.owner,
            "dtype": self.dtype,
            "device": self.device,
            "reset_policy": self.reset_policy,
            "producer": self.producer,
            "consumer": self.consumer,
            "readback_name": self.readback_name,
        }


@dataclass(frozen=True)
class DeviceFieldPlan:
    """可选 device transition 路径的不可变公共描述。"""

    available: bool
    num_envs: int
    backend: str
    execution: str
    device: str | None
    transfer_mode: str
    state_readback_fields: tuple[str, ...]
    fields: tuple[DeviceFieldSpec, ...]
    action_leaf_layout: tuple[str, ...] = ()
    observation_leaf_layout: tuple[str, ...] = ()
    terminal_policy: str = "terminal_mask_only"
    reset_policy: str = "masked_reset_sampler"
    reasons: tuple[str, ...] = ()
    version: str = DEVICE_FIELD_PLAN_VERSION

    def __post_init__(self) -> None:
        if int(self.num_envs) < 1:
            raise ValueError("DeviceFieldPlan num_envs must be positive")
        if not str(self.backend).strip():
            raise ValueError("DeviceFieldPlan backend cannot be empty")
        if not str(self.execution).strip():
            raise ValueError("DeviceFieldPlan execution cannot be empty")
        names = tuple(str(name) for name in self.state_readback_fields)
        if len(names) != len(set(names)):
            raise ValueError("DeviceFieldPlan state fields must be unique")
        object.__setattr__(self, "state_readback_fields", names)
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "action_leaf_layout", tuple(self.action_leaf_layout))
        object.__setattr__(self, "observation_leaf_layout", tuple(self.observation_leaf_layout))
        object.__setattr__(self, "reasons", tuple(str(reason) for reason in self.reasons))

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    def as_dict(self) -> dict[str, Any]:
        """返回不暴露 device 对象、可安全写入 JSON/YAML 的 provenance。"""

        return {
            "version": self.version,
            "available": bool(self.available),
            "num_envs": int(self.num_envs),
            "backend": str(self.backend),
            "execution": str(self.execution),
            "device": self.device,
            "transfer_mode": self.transfer_mode,
            "state_readback_fields": list(self.state_readback_fields),
            "fields": [field.as_dict() for field in self.fields],
            "action_leaf_layout": list(self.action_leaf_layout),
            "observation_leaf_layout": list(self.observation_leaf_layout),
            "terminal_policy": self.terminal_policy,
            "reset_policy": self.reset_policy,
            "reasons": list(self.reasons),
        }


def _schema_leaf_names(value: Any) -> tuple[str, ...]:
    """只读取声明的叶子名称，不推断 task 语义。"""

    if not isinstance(value, Mapping):
        return ()
    for key in ("fields", "leaves"):
        entries = value.get(key)
        if isinstance(entries, (list, tuple)):
            names: list[str] = []
            for entry in entries:
                if isinstance(entry, Mapping):
                    name = entry.get("name")
                else:
                    name = entry
                if name is not None:
                    names.append(str(name))
            return tuple(names)
    return ()


def _declared_device_fields(
    task_definition: object,
    attribute: str,
) -> tuple[str, ...]:
    """规范化一个由 task consumer 所有的不可变字段声明。"""

    value = getattr(task_definition, attribute, ())
    if value is None:
        return ()
    if not isinstance(value, tuple):
        raise TypeError(f"{attribute} must be an immutable tuple of field names")
    names = tuple(str(name).strip() for name in value)
    if any(not name for name in names):
        raise ValueError(f"{attribute} cannot contain empty field names")
    if len(names) != len(set(names)):
        raise ValueError(f"{attribute} cannot contain duplicate field names")
    return names


def _probe_device_field(
    reader: object,
    name: str,
    *,
    num_envs: int,
    device: str,
) -> None:
    """通过 runtime 既有的 read API 探测一个命名字段。"""

    result = reader((name,))
    if not isinstance(result, DeviceBatchState):
        raise TypeError(
            "runtime.read_device_state() must return DeviceBatchState"
        )
    arrays = result.arrays
    if name not in arrays:
        raise ValueError(
            f"runtime.read_device_state() did not return requested field {name!r}"
        )
    if int(result.num_envs) != int(num_envs):
        raise ValueError(
            f"runtime device field {name!r} returned num_envs={result.num_envs}, "
            f"expected {num_envs}"
        )
    if str(result.device) != str(device):
        raise ValueError(
            f"runtime device field {name!r} returned device={result.device!r}, "
            f"expected {device!r}"
        )


def build_device_field_plan(
    *,
    runtime: object,
    action_adapter: object | None,
    task_definition: object,
    metadata: Mapping[str, Any] | None,
    num_envs: int,
    backend: str,
) -> DeviceFieldPlan:
    """在 lifecycle 构造期只生成一次通用计划。

    ``resource_summary()["device_transition"]`` 是 device capability 的
    authoritative source；方法存在性和 named-field probe 只用于验证该
    summary 的声明是否真实。没有 device 实现的 task 仍然是有效的
    host/NumPy task，并获得带稳定原因的 unavailable 计划。
    """

    runtime_methods = {
        "runtime.read_device_state": getattr(runtime, "read_device_state", None),
        "runtime.step_device": getattr(runtime, "step_device", None),
        "runtime.reset_device": getattr(runtime, "reset_device", None),
    }
    metadata_value = dict(metadata or {})
    task_methods = {
        "task.build_device_observation": getattr(task_definition, "build_device_observation", None),
        "task.evaluate_device": getattr(task_definition, "evaluate_device", None),
    }
    adapter_method = getattr(action_adapter, "convert_device_batch", None)
    missing = [name for name, method in runtime_methods.items() if not callable(method)]
    missing.extend(name for name, method in task_methods.items() if not callable(method))
    if not callable(adapter_method):
        missing.append("action_adapter.convert_device_batch")

    summary: Mapping[str, Any] = {}
    cached_summary = metadata_value.get("runtime_resource_summary")
    if isinstance(cached_summary, Mapping):
        summary = cached_summary
    else:
        try:
            candidate = getattr(runtime, "resource_summary")()
            if isinstance(candidate, Mapping):
                summary = candidate
        except Exception as exc:  # 诊断构造不能吞掉 capability 原因
            missing.append(f"runtime.resource_summary:{type(exc).__name__}")

    execution = str(metadata_value.get("execution", "local")).strip().lower()
    requested_transfer_mode = str(
        metadata_value.get("transfer_mode", "device")
    ).strip().lower()
    admission = admit_runtime_port(
        runtime=runtime,
        summary=summary,
        execution=execution,
        requested_transfer_mode=requested_transfer_mode,
    )
    if not admission.device_available:
        missing.extend(admission.device_reasons)
    transfer_mode = admission.transfer_mode
    transition_available = (
        admission.device_available and transfer_mode == "device"
    )
    device_value = admission.device

    try:
        task_required_fields = _declared_device_fields(
            task_definition, "device_state_required_fields"
        )
    except (TypeError, ValueError) as exc:
        task_required_fields = ()
        missing.append(f"task.device_state_required_fields: {exc}")
    try:
        task_optional_fields = _declared_device_fields(
            task_definition, "device_state_optional_fields"
        )
    except (TypeError, ValueError) as exc:
        task_optional_fields = ()
        missing.append(f"task.device_state_optional_fields: {exc}")

    required_state_fields: list[str] = []
    for name in _BASE_STATE_FIELDS + (
        _CONTACT_STATE_FIELDS if bool(summary.get("contact_enabled", False)) else ()
    ) + task_required_fields:
        if name not in required_state_fields:
            required_state_fields.append(name)
    optional_state_fields = tuple(
        name for name in task_optional_fields if name not in required_state_fields
    )
    supported_optional_fields: list[str] = []
    reader = runtime_methods["runtime.read_device_state"]
    can_probe = transition_available and callable(reader)
    if can_probe:
        for name in required_state_fields:
            try:
                _probe_device_field(
                    reader,
                    name,
                    num_envs=int(num_envs),
                    device=str(device_value),
                )
            except Exception as exc:
                missing.append(
                    f"runtime required device field {name!r}: "
                    f"{type(exc).__name__}: {exc}"
                )
        for name in optional_state_fields:
            try:
                _probe_device_field(
                    reader,
                    name,
                    num_envs=int(num_envs),
                    device=str(device_value),
                )
            except KeyError:
                continue
            except Exception as exc:
                missing.append(
                    f"runtime optional device field {name!r} probe failed: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                supported_optional_fields.append(name)
    state_fields = tuple(required_state_fields + supported_optional_fields)

    fields = [
        DeviceFieldSpec(
            name=name,
            role="state",
            owner="runtime",
            device=device_value,
            reset_policy="masked_persistent",
            producer="runtime.step_device",
            consumer="task.build_device_observation|task.evaluate_device",
            readback_name=name,
        )
        for name in state_fields
    ]
    fields.extend(
        (
            DeviceFieldSpec(
                name="external_action",
                role="action",
                owner="lifecycle",
                dtype="float32",
                device=device_value,
                reset_policy="not_reset",
                producer="learner",
                consumer="action_adapter.convert_device_batch",
            ),
            DeviceFieldSpec(
                name="control",
                role="control",
                owner="runtime",
                dtype="float32",
                device=device_value,
                reset_policy="persistent",
                producer="action_adapter.convert_device_batch",
                consumer="runtime.step_device",
            ),
            DeviceFieldSpec(
                name="reward",
                role="transition",
                owner="task",
                device=device_value,
                reset_policy="not_reset",
                producer="task.evaluate_device",
                consumer="learner",
            ),
            DeviceFieldSpec(
                name="terminated",
                role="terminal",
                owner="task",
                dtype="bool",
                device=device_value,
                reset_policy="terminal_branch",
                producer="task.evaluate_device",
                consumer="lifecycle",
            ),
            DeviceFieldSpec(
                name="truncated",
                role="terminal",
                owner="lifecycle",
                dtype="bool",
                device=device_value,
                reset_policy="terminal_branch",
                producer="task.evaluate_device|horizon",
                consumer="learner|reset_sampler",
            ),
        )
    )
    if execution not in {"local", "remote"}:
        missing.append(f"unsupported execution provenance: {execution}")
    if transfer_mode not in {"device", "host_numpy"}:
        missing.append(f"unsupported transfer mode: {transfer_mode}")
    if transfer_mode != "device":
        missing.append(
            f"device transition intentionally unavailable for transfer_mode={transfer_mode}"
        )
    if execution == "remote" and transfer_mode == "device":
        missing.append("remote execution requires an explicit host_numpy transfer boundary")
    action_layout = _schema_leaf_names(metadata_value.get("action_schema"))
    observation_layout = _schema_leaf_names(metadata_value.get("observation_schema"))
    return DeviceFieldPlan(
        available=not missing,
        num_envs=int(num_envs),
        backend=str(backend),
        execution=execution,
        device=device_value,
        transfer_mode=transfer_mode,
        state_readback_fields=state_fields,
        fields=tuple(fields),
        action_leaf_layout=action_layout,
        observation_leaf_layout=observation_layout,
        reasons=tuple(dict.fromkeys(str(reason) for reason in missing)),
    )


__all__ = [
    "DEVICE_FIELD_PLAN_VERSION",
    "DeviceFieldPlan",
    "DeviceFieldSpec",
    "RuntimePortAdmission",
    "admit_runtime_port",
    "build_device_field_plan",
    "resolve_device_transfer_mode",
]
