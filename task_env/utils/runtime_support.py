"""TaskEnv-owned runtime helpers for diagnostics and integration fixtures.

This module replaces the historical dependency on ``test/_support/bootstrap.py``
for code shipped under ``task_env`` while keeping backend initialization
delegated to the TaskEnv runtime provider boundary.
"""

from __future__ import annotations

from typing import Any


def get_task_env_logger(
    layer: str,
    module: str | None = None,
    instance: str | None = None,
):
    """Return the standard structured logger used by TaskEnv tools."""

    from utils.logger import get_component_logger

    return get_component_logger(layer, module=module, instance=instance)


def init_task_env_backend(arch: str = "cpu", **kwargs: Any) -> None:
    """Compatibility wrapper for the runtime-owned backend initializer."""

    from task_env.runtime.provider_bootstrap import init_task_env_backend as _init

    _init(arch, **kwargs)


__all__ = ["get_task_env_logger", "init_task_env_backend"]
