"""Shared TaskEnv render contracts and backend base classes."""

from .backend import (
    LegacyReferenceRenderBackend,
    RenderBackend,
    RenderBackendDescriptor,
    SceneSourceBackend,
)
from .contracts import (
    RenderBackendBuildError,
    RenderBackendCapabilities,
    RenderBackendName,
    RenderMode,
    RenderUnavailableError,
    UiRenderProvider,
    normalize_render_mode,
)

__all__ = [
    "RenderBackend",
    "RenderBackendDescriptor",
    "SceneSourceBackend",
    "LegacyReferenceRenderBackend",
    "RenderBackendBuildError",
    "RenderBackendCapabilities",
    "RenderBackendName",
    "RenderMode",
    "RenderUnavailableError",
    "UiRenderProvider",
    "normalize_render_mode",
]
