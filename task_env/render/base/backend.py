"""TaskEnv render backend abstraction.

The physics/runtime layers expose a ``src.visualization`` scene source.  This
module is the TaskEnv-owned boundary that selects one backend implementation
without making callers know how that source is instantiated.  Backend
implementations remain deliberately thin: scene lowering, snapshot ownership,
and renderer kernels continue to belong to ``src.visualization``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

from .contracts import (
    RenderBackendCapabilities,
    RenderBackendBuildError,
)

if TYPE_CHECKING:
    from ..tools.processing import RenderBuildRequest


@dataclass(frozen=True)
class RenderBackendDescriptor:
    """Public metadata for one TaskEnv backend implementation."""

    name: str
    capabilities: RenderBackendCapabilities
    implementation: str

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "capabilities": {
                "supports_human": self.capabilities.supports_human,
                "supports_rgb_array": self.capabilities.supports_rgb_array,
                "supports_parallel": self.capabilities.supports_parallel,
                "supports_asset_instancing": (
                    self.capabilities.supports_asset_instancing
                ),
                "supports_shared_asset_table": (
                    self.capabilities.supports_shared_asset_table
                ),
                "supports_gpu_geometry_instancing": (
                    self.capabilities.supports_gpu_geometry_instancing
                ),
                "supports_batch_transform_update": (
                    self.capabilities.supports_batch_transform_update
                ),
                "transform_transport": self.capabilities.transform_transport,
                "output_transport": self.capabilities.output_transport,
            },
            "implementation": self.implementation,
        }


class RenderBackend(ABC):
    """Backend instance contract consumed by the common render processor."""

    name: str
    capabilities: RenderBackendCapabilities

    @property
    def descriptor(self) -> RenderBackendDescriptor:
        return RenderBackendDescriptor(
            name=self.name,
            capabilities=self.capabilities,
            implementation=f"{type(self).__module__}.{type(self).__qualname__}",
        )

    @abstractmethod
    def create_visualizer(
        self,
        source: object,
        *,
        request: "RenderBuildRequest",
        visualizer_kwargs: Mapping[str, object] | None = None,
    ) -> object:
        """Instantiate the backend visualizer for one prepared source."""


class SceneSourceBackend(RenderBackend):
    """Adapter for the common ``SceneVisualizationSource`` factory contract."""

    @property
    @abstractmethod
    def source_backend_name(self) -> str:
        """Name passed to ``SceneVisualizationSource.build_visualizer``."""

    def create_visualizer(
        self,
        source: object,
        *,
        request: "RenderBuildRequest",
        visualizer_kwargs: Mapping[str, object] | None = None,
    ) -> object:
        build_visualizer = getattr(source, "build_visualizer", None)
        if not callable(build_visualizer):
            raise RenderBackendBuildError(
                f"render source does not expose build_visualizer() for backend "
                f"{self.name!r}"
            )

        kwargs = dict(request.visualizer_kwargs())
        if visualizer_kwargs:
            kwargs.update(dict(visualizer_kwargs))
        kwargs["backend"] = self.source_backend_name
        try:
            return build_visualizer(**kwargs)
        except Exception as exc:
            raise RenderBackendBuildError(
                f"failed to build TaskEnv render backend {self.name!r}: {exc}"
            ) from exc


class LegacyReferenceRenderBackend(SceneSourceBackend):
    """Compatibility adapter for the existing MuJoCo reference renderer."""

    name = "mujoco_reference"
    capabilities = RenderBackendCapabilities(
        supports_parallel=False,
        supports_asset_instancing=False,
        output_transport="external_reference",
    )

    @property
    def source_backend_name(self) -> str:
        return self.name


__all__ = [
    "RenderBackend",
    "RenderBackendDescriptor",
    "SceneSourceBackend",
    "LegacyReferenceRenderBackend",
]
