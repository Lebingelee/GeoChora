"""UI rendering contract, deliberately separate from observation sensors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np


class RenderMode(str, Enum):
    """Stable modes accepted by the future :meth:`BaseTaskEnv.render` API."""

    HUMAN = "human"
    RGB_ARRAY = "rgb_array"


class RenderBackendName(str, Enum):
    """Backend names owned by the TaskEnv render boundary."""

    RAYTRACER = "raytracer"
    RASTERIZER = "rasterizer"
    FLORA = "flora"


@dataclass(frozen=True)
class RenderBackendCapabilities:
    """Stable capability description exposed before a renderer is created."""

    supports_human: bool = True
    supports_rgb_array: bool = True
    supports_parallel: bool = True
    # ``supports_asset_instancing`` is retained as a compatibility field for
    # existing callers.  New code should use the explicit capabilities below.
    supports_asset_instancing: bool = False
    supports_shared_asset_table: bool = False
    supports_gpu_geometry_instancing: bool = False
    supports_batch_transform_update: bool = False
    transform_transport: str = "unknown"
    output_transport: str = "geophys_framebuffer"


class RenderUnavailableError(RuntimeError):
    """Raised when an environment has no configured UI rendering backend."""


class RenderBackendBuildError(RuntimeError):
    """Raised when a selected backend cannot build its visualizer."""


def normalize_render_mode(mode: RenderMode | str) -> RenderMode:
    """Validate one public UI render mode without accepting sensor aliases."""

    try:
        return RenderMode(mode)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RenderMode)
        raise ValueError(f"unsupported UI render mode {mode!r}; expected one of: {allowed}") from exc


class UiRenderProvider(Protocol):
    """TaskEnv UI backend; it is separate from camera observation capture."""

    def render(self, *, mode: RenderMode, snapshot: object) -> np.ndarray | None:
        """Present a frame or return an RGB frame according to ``mode``."""

    def close(self) -> None:
        """Release window and visualizer resources; the operation is idempotent."""


__all__ = [
    "RenderMode",
    "RenderBackendName",
    "RenderBackendCapabilities",
    "RenderUnavailableError",
    "RenderBackendBuildError",
    "UiRenderProvider",
    "normalize_render_mode",
]
