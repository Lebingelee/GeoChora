"""Shared TaskEnv render dispatch and request-processing tools."""

from .backend_registry import (
    available_render_backends,
    create_render_backend,
    normalize_render_backend,
)
from .processing import RenderBuildRequest, RenderProcessor, build_task_visualizer


def __getattr__(name: str):
    # Camera interaction uses Taichi; request/registry imports must stay inert.
    if name in {"CameraPoseSink", "InteractiveCameraController"}:
        from importlib import import_module

        value = getattr(import_module(".camera", __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(name)

__all__ = [
    "available_render_backends",
    "create_render_backend",
    "normalize_render_backend",
    "RenderBuildRequest",
    "RenderProcessor",
    "build_task_visualizer",
    "CameraPoseSink",
    "InteractiveCameraController",
]
