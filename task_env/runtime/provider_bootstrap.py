"""GeoPhys provider bootstrap owned by the TaskEnv runtime boundary."""

from __future__ import annotations

from typing import Any


def init_task_env_backend(arch: str = "cpu", **kwargs: Any) -> None:
    """Initialize the selected GeoPhys/Taichi backend lazily."""

    from geophys.test_runtime import init_test_backend

    init_test_backend(arch, **kwargs)


__all__ = ["init_task_env_backend"]
