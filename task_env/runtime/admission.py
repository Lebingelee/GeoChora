"""Runtime Port admission facts, separate from device field planning.

This module owns the host/device/randomization eligibility decision.  It does
not inspect provider-private state or construct a field plan; the latter
remains in :mod:`task_env.runtime.device_plan`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import operator
from typing import Any


@dataclass(frozen=True)
class RuntimePortAdmission:
    """一次 runtime port admission 的不可变结果。"""

    host_available: bool
    device_available: bool
    randomization_available: bool
    transfer_mode: str
    device: str | None = None
    host_reasons: tuple[str, ...] = ()
    device_reasons: tuple[str, ...] = ()
    randomization_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "transfer_mode", str(self.transfer_mode))
        object.__setattr__(
            self, "device", None if self.device is None else str(self.device)
        )
        object.__setattr__(
            self,
            "host_reasons",
            tuple(str(item) for item in self.host_reasons),
        )
        object.__setattr__(
            self,
            "device_reasons",
            tuple(str(item) for item in self.device_reasons),
        )
        object.__setattr__(
            self,
            "randomization_reasons",
            tuple(str(item) for item in self.randomization_reasons),
        )

    @property
    def reasons(self) -> tuple[str, ...]:
        """返回按 host/device/randomization 分组去重后的原因。"""

        return tuple(
            dict.fromkeys(
                (
                    *self.host_reasons,
                    *self.device_reasons,
                    *self.randomization_reasons,
                )
            )
        )


def _device_transition_report(
    summary: Mapping[str, Any] | None,
) -> tuple[bool, str | None, str | None]:
    """读取 runtime summary 中唯一的 device-transition capability 事实。"""

    if not isinstance(summary, Mapping):
        return False, None, "runtime.resource_summary() did not return a mapping"
    transition = summary.get("device_transition")
    if not isinstance(transition, Mapping):
        return False, None, "runtime.resource_summary.device_transition is unavailable"
    available = transition.get("available", False)
    raw_device = transition.get("field_device")
    device = None if raw_device is None else str(raw_device).strip() or None
    if not isinstance(available, bool):
        return False, device, "runtime.device_transition.available must be a boolean"
    if not available:
        return (
            False,
            device,
            str(transition.get("reason") or "runtime.device_transition is unavailable"),
        )
    if device is None:
        return False, None, "runtime.device_transition.field_device is unavailable"
    return True, device, None


def admit_runtime_port(
    *,
    runtime: object,
    summary: Mapping[str, Any] | None = None,
    execution: str = "local",
    requested_transfer_mode: str = "host_numpy",
    randomization_required: bool = False,
) -> RuntimePortAdmission:
    """集中验证 TaskEnv runtime port 的 host/device/随机化 admission。"""

    host_reasons: list[str] = []
    for name in ("reset", "step", "resource_summary", "close"):
        if not callable(getattr(runtime, name, None)):
            host_reasons.append(f"runtime.{name} is not callable")
    try:
        raw_num_envs = getattr(runtime, "num_envs")
    except AttributeError:
        host_reasons.append("runtime.num_envs is missing")
    else:
        try:
            num_envs = operator.index(raw_num_envs)
        except (TypeError, ValueError, OverflowError):
            num_envs = None
        if isinstance(raw_num_envs, bool) or num_envs is None or num_envs < 1:
            host_reasons.append("runtime.num_envs must be a positive integer")

    summary_supplied = summary is not None
    resolved_summary: Mapping[str, Any] | None = (
        summary if isinstance(summary, Mapping) else None
    )
    if summary_supplied and not isinstance(summary, Mapping):
        host_reasons.append("runtime.resource_summary must return a mapping")
    elif resolved_summary is None:
        summary_getter = getattr(runtime, "resource_summary", None)
        if callable(summary_getter):
            try:
                candidate = summary_getter()
            except Exception as exc:
                host_reasons.append(
                    f"runtime.resource_summary failed: {type(exc).__name__}: {exc}"
                )
            else:
                if isinstance(candidate, Mapping):
                    resolved_summary = candidate
                else:
                    host_reasons.append("runtime.resource_summary must return a mapping")
        else:
            host_reasons.append("runtime.resource_summary is not callable")

    device_available, device, transition_reason = _device_transition_report(
        resolved_summary
    )
    device_reasons: list[str] = []
    if transition_reason is not None:
        device_reasons.append(str(transition_reason))
    execution_value = str(execution).strip().lower()
    if execution_value != "local":
        device_available = False
        device_reasons.append(
            f"device transition requires local execution, got {execution_value}"
        )
    for name in ("read_device_state", "step_device", "reset_device"):
        if not callable(getattr(runtime, name, None)):
            device_available = False
            device_reasons.append(f"runtime.{name} is not callable")
    if not device_available and not device_reasons:
        device_reasons.append("runtime device transition is unavailable")

    randomization_reasons: list[str] = []
    randomization_available = True
    if randomization_required and not callable(
        getattr(runtime, "apply_world_randomization", None)
    ):
        randomization_available = False
        randomization_reasons.append(
            "runtime.apply_world_randomization is not callable for a non-empty payload"
        )

    requested_value = str(requested_transfer_mode).strip().lower()
    resolved_transfer_mode = (
        "device"
        if requested_value == "device" and device_available
        else "host_numpy"
        if requested_value == "device"
        else requested_value
    )
    return RuntimePortAdmission(
        host_available=not host_reasons,
        device_available=bool(device_available),
        randomization_available=randomization_available,
        transfer_mode=resolved_transfer_mode,
        device=device,
        host_reasons=tuple(dict.fromkeys(host_reasons)),
        device_reasons=tuple(dict.fromkeys(device_reasons)),
        randomization_reasons=tuple(dict.fromkeys(randomization_reasons)),
    )


def resolve_device_transfer_mode(
    *,
    runtime: object,
    summary: Mapping[str, Any] | None,
    execution: str,
    requested: str,
) -> str:
    """依据既有 runtime summary 解析 transfer mode。"""

    return admit_runtime_port(
        runtime=runtime,
        summary=summary,
        execution=execution,
        requested_transfer_mode=requested,
    ).transfer_mode


__all__ = [
    "RuntimePortAdmission",
    "admit_runtime_port",
    "resolve_device_transfer_mode",
]
