"""在 Taichi 之前确定性预载可选设备栈，并记录可审计来源。"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import os
import sys
from threading import Lock
from types import ModuleType
from typing import Any


_SCHEMA = "task-env-device-stack-provenance-v1"
_TRITON_ACCEPTED_STATUS = "triton_preloaded_before_taichi"
_PRELOAD_LOCK = Lock()
_PROVENANCE: DeviceStackProvenance | None = None
_PRELOAD_FINGERPRINT: tuple[bool, bool, bool, bool] | None = None
_TRITON_MODULE: ModuleType | None = None
_TRITON_LANGUAGE_MODULE: ModuleType | None = None


@dataclass(frozen=True, slots=True)
class DeviceStackProvenance:
    """一次进程级预载尝试的不可变、JSON 兼容记录。"""

    schema: str
    torch_requested: bool
    torch_loaded: bool
    tensordict_requested: bool
    tensordict_loaded: bool
    triton_requested: bool
    triton_loaded: bool
    taichi_loaded_before_triton: bool
    status: str
    triton_version: str | None
    error: str | None
    triton_module_id: int | None
    triton_language_module_id: int | None

    def to_dict(self) -> dict[str, Any]:
        """返回不含模块对象的 JSON 兼容副本。"""

        return {
            "schema": self.schema,
            "torch_requested": self.torch_requested,
            "torch_loaded": self.torch_loaded,
            "tensordict_requested": self.tensordict_requested,
            "tensordict_loaded": self.tensordict_loaded,
            "triton_requested": self.triton_requested,
            "triton_loaded": self.triton_loaded,
            "taichi_loaded_before_triton": self.taichi_loaded_before_triton,
            "status": self.status,
            "triton_version": self.triton_version,
            "error": self.error,
            "triton_module_id": self.triton_module_id,
            "triton_language_module_id": self.triton_language_module_id,
        }


class DeviceStackPreloadConflictError(RuntimeError):
    """同一进程尝试以不同预载请求重复初始化设备栈。"""


def _load_optional(module_name: str) -> ModuleType | None:
    try:
        return import_module(module_name)
    except Exception:  # 可选依赖缺失或二进制加载失败均不得破坏 CPU 入口。
        return None


def _sanitized_error(error: Exception) -> str:
    """只保留异常类型，避免把本机路径或凭据写入来源记录。"""

    return type(error).__name__


def preload_device_stack(
    *,
    request_torch: bool = True,
    request_tensordict: bool = True,
    request_triton: bool = True,
) -> DeviceStackProvenance:
    """按 Torch、TensorDict、Triton 顺序执行一次进程级预载。"""

    global _PRELOAD_FINGERPRINT, _PROVENANCE
    global _TRITON_LANGUAGE_MODULE, _TRITON_MODULE

    disable_triton = os.environ.get("GEOPHYS_DISABLE_TRITON") == "1"
    fingerprint = (
        bool(request_torch),
        bool(request_tensordict),
        bool(request_triton),
        disable_triton,
    )

    with _PRELOAD_LOCK:
        if _PROVENANCE is not None:
            if fingerprint != _PRELOAD_FINGERPRINT:
                raise DeviceStackPreloadConflictError(
                    "device stack preload already completed with a different request"
                )
            return _PROVENANCE

        # 任何重依赖都有可能传递导入 Triton，因此必须先锁定 Taichi 状态。
        taichi_loaded = "taichi" in sys.modules
        if taichi_loaded:
            torch_module = None
            tensordict_module = None
        else:
            torch_module = _load_optional("torch") if request_torch else None
            tensordict_module = (
                _load_optional("tensordict") if request_tensordict else None
            )
        # Torch/TensorDict 也可能传递加载 Taichi；Triton import 紧前再快照。
        taichi_loaded = "taichi" in sys.modules
        triton_module: ModuleType | None = None
        triton_language_module: ModuleType | None = None
        triton_error: str | None = None

        if not request_triton:
            status = "triton_not_requested"
        elif disable_triton:
            status = "triton_disabled"
        elif taichi_loaded:
            status = "late_import_blocked"
        else:
            try:
                triton_module = import_module("triton")
                triton_language_module = import_module("triton.language")
            except Exception as error:  # 依赖缺失和平台加载失败都是可审计 fallback。
                status = "triton_unavailable"
                triton_error = _sanitized_error(error)
                triton_module = None
                triton_language_module = None
            else:
                status = _TRITON_ACCEPTED_STATUS

        triton_loaded = (
            status == _TRITON_ACCEPTED_STATUS
            and triton_module is not None
            and triton_language_module is not None
        )
        if triton_loaded:
            _TRITON_MODULE = triton_module
            _TRITON_LANGUAGE_MODULE = triton_language_module

        _PROVENANCE = DeviceStackProvenance(
            schema=_SCHEMA,
            torch_requested=bool(request_torch),
            torch_loaded=torch_module is not None,
            tensordict_requested=bool(request_tensordict),
            tensordict_loaded=tensordict_module is not None,
            triton_requested=bool(request_triton),
            triton_loaded=triton_loaded,
            taichi_loaded_before_triton=taichi_loaded,
            status=status,
            triton_version=(
                str(getattr(triton_module, "__version__", "unknown"))
                if triton_loaded
                else None
            ),
            error=triton_error,
            triton_module_id=id(triton_module) if triton_loaded else None,
            triton_language_module_id=(
                id(triton_language_module) if triton_loaded else None
            ),
        )
        _PRELOAD_FINGERPRINT = fingerprint
        return _PROVENANCE


def get_device_stack_provenance() -> DeviceStackProvenance | None:
    """返回已完成的预载记录；尚未预载时返回 ``None``。"""

    return _PROVENANCE


def get_preloaded_triton_modules() -> tuple[ModuleType | None, ModuleType | None]:
    """仅在模块身份仍匹配可信预载记录时返回 Triton 句柄。"""

    record = _PROVENANCE
    triton_module = _TRITON_MODULE
    language_module = _TRITON_LANGUAGE_MODULE
    if (
        os.environ.get("GEOPHYS_DISABLE_TRITON") == "1"
        or record is None
        or record.status != _TRITON_ACCEPTED_STATUS
        or not record.triton_loaded
        or triton_module is None
        or language_module is None
        or id(triton_module) != record.triton_module_id
        or id(language_module) != record.triton_language_module_id
        or sys.modules.get("triton") is not triton_module
        or sys.modules.get("triton.language") is not language_module
    ):
        return None, None
    return triton_module, language_module


__all__ = [
    "DeviceStackProvenance",
    "DeviceStackPreloadConflictError",
    "get_device_stack_provenance",
    "get_preloaded_triton_modules",
    "preload_device_stack",
]
