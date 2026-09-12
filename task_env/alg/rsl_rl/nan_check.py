"""One-materialization NaN validation for the current RSL-RL runner."""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from importlib import import_module
from typing import Any


def _copy_stacked_nan_flags_to_host(stacked_flags: Any) -> list[bool]:
    """Perform the single device-to-host copy for one device group."""

    return stacked_flags.to(device="cpu").tolist()


def _materialize_nan_flags(flags: tuple[Any, ...]) -> tuple[bool, ...]:
    """Materialize one device-local group of scalar flags together."""

    import torch

    host_flags = _copy_stacked_nan_flags_to_host(torch.stack(flags))
    return tuple(bool(flag) for flag in host_flags)


def _environment_fields(obs: Any, rewards: Any, dones: Any) -> list[tuple[Any, ...]]:
    fields = [
        (
            ("observation", key),
            tensor,
            f"The observation group '{key}' returned by the environment contains "
            "NaN values. This usually indicates a bug in the environment's step() "
            "or reset() function.",
        )
        for key, tensor in obs.items()
    ]
    fields.extend(
        (
            (
                ("rewards",),
                rewards,
                "The rewards returned by the environment contain NaN values. This "
                "usually indicates a bug in the environment's reward computation.",
            ),
            (
                ("dones",),
                dones,
                "The dones returned by the environment contain NaN values. This "
                "usually indicates a bug in the environment's termination logic.",
            ),
        )
    )
    return fields


def _field_layout(fields: list[tuple[Any, ...]]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (identity, tuple(tensor.shape), tensor.device)
        for identity, tensor, _ in fields
    )


def _device_nan_flags(
    fields: list[tuple[Any, ...]],
) -> dict[Any, list[tuple[int, Any]]]:
    import torch

    device_groups: dict[Any, list[tuple[int, Any]]] = {}
    for index, (_, tensor, _) in enumerate(fields):
        device_groups.setdefault(tensor.device, []).append(
            (index, torch.isnan(tensor).any())
        )
    return device_groups


def check_nan(obs: Any, rewards: Any, dones: Any) -> None:
    """Immediately raise the upstream error using one transfer per device."""

    fields = _environment_fields(obs, rewards, dones)
    device_groups = _device_nan_flags(fields)

    nan_flags = [False] * len(fields)
    for group in device_groups.values():
        materialized = _materialize_nan_flags(tuple(flag for _, flag in group))
        for (index, _), is_nan in zip(group, materialized, strict=True):
            nan_flags[index] = is_nan

    for is_nan, (_, _, message) in zip(nan_flags, fields, strict=True):
        if is_nan:
            raise ValueError(message)


class RolloutNanChecker:
    """Defer host materialization until one complete RSL rollout boundary."""

    def __init__(self, *, rollout_steps: int) -> None:
        self.rollout_steps = int(rollout_steps)
        if self.rollout_steps < 1:
            raise ValueError("rollout_steps must be positive")
        self._clear()

    def _clear(self) -> None:
        self._tick_count = 0
        self._layout: tuple[tuple[Any, ...], ...] | None = None
        self._messages: tuple[str, ...] = ()
        self._device_groups: dict[Any, list[tuple[int, Any]]] = {}

    def __call__(self, obs: Any, rewards: Any, dones: Any) -> None:
        try:
            fields = _environment_fields(obs, rewards, dones)
            layout = _field_layout(fields)
            if self._layout is None:
                self._layout = layout
                self._messages = tuple(message for _, _, message in fields)
            elif layout != self._layout:
                raise RuntimeError(
                    "RSL-RL NaN checker field layout changed during a rollout"
                )

            field_count = len(fields)
            flat_offset = self._tick_count * field_count
            for device, group in _device_nan_flags(fields).items():
                destination = self._device_groups.setdefault(device, [])
                destination.extend(
                    (flat_offset + field_index, flag)
                    for field_index, flag in group
                )
            self._tick_count += 1
        except Exception:
            self._clear()
            raise

        if self._tick_count < self.rollout_steps:
            return

        try:
            nan_flags = [False] * (self.rollout_steps * len(self._messages))
            for group in self._device_groups.values():
                materialized = _materialize_nan_flags(
                    tuple(flag for _, flag in group)
                )
                for (flat_index, _), is_nan in zip(
                    group,
                    materialized,
                    strict=True,
                ):
                    nan_flags[flat_index] = is_nan

            field_count = len(self._messages)
            for flat_index, is_nan in enumerate(nan_flags):
                if is_nan:
                    raise ValueError(self._messages[flat_index % field_count])
        finally:
            self._clear()


_ACTIVE_ROLLOUT_NAN_CHECKER: ContextVar[RolloutNanChecker | None] = ContextVar(
    "task_env_active_rollout_nan_checker",
    default=None,
)


def dispatch_check_nan(obs: Any, rewards: Any, dones: Any) -> None:
    """Dispatch to the active runner checker, or fail safe immediately."""

    checker = _ACTIVE_ROLLOUT_NAN_CHECKER.get()
    if checker is None:
        return check_nan(obs, rewards, dones)
    return checker(obs, rewards, dones)


def install_runner_nan_check(
    runner: Any,
    *,
    rollout_steps: int,
) -> Any:
    """Bind a runner-local checker activation around its existing learn method."""

    steps = int(rollout_steps)
    if steps < 1:
        raise ValueError("rollout_steps must be positive")
    runner_module = import_module(type(runner).__module__)
    current = getattr(runner_module, "check_nan", None)
    if current is not dispatch_check_nan and not callable(current):
        raise RuntimeError(
            "installed RSL-RL OnPolicyRunner does not expose a module-level "
            "check_nan hook"
        )
    runner_module.check_nan = dispatch_check_nan

    steps_attribute = "_task_env_nan_check_rollout_steps"
    wrapper_attribute = "_task_env_nan_check_wrapped_learn"
    setattr(runner, steps_attribute, steps)
    existing_wrapper = getattr(runner, wrapper_attribute, None)
    if existing_wrapper is not None:
        runner.learn = existing_wrapper
        return dispatch_check_nan

    original_learn = runner.learn

    @wraps(original_learn)
    def learn_with_nan_check(*args: Any, **kwargs: Any) -> Any:
        checker = RolloutNanChecker(
            rollout_steps=int(getattr(runner, steps_attribute))
        )
        token = _ACTIVE_ROLLOUT_NAN_CHECKER.set(checker)
        try:
            return original_learn(*args, **kwargs)
        finally:
            checker._clear()
            _ACTIVE_ROLLOUT_NAN_CHECKER.reset(token)

    setattr(runner, wrapper_attribute, learn_with_nan_check)
    runner.learn = learn_with_nan_check
    return dispatch_check_nan


__all__ = [
    "RolloutNanChecker",
    "check_nan",
    "dispatch_check_nan",
    "install_runner_nan_check",
]
