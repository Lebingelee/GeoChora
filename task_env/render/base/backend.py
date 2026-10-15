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
    RenderBackendName,
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


@dataclass(frozen=True)
class _BackendRegistration:
    descriptor: RenderBackendDescriptor
    aliases: tuple[str, ...] = ()
    listed: bool = True


# One metadata authority, shared by discovery and the concrete adapter classes.
# Implementation paths are strings so neither discovery nor validation imports
# a renderer. Order is the historical available_render_backends() order.
_BACKEND_REGISTRATIONS = (
    _BackendRegistration(RenderBackendDescriptor(
        name=RenderBackendName.RAYTRACER.value,
        capabilities=RenderBackendCapabilities(
            supports_parallel=True,
            supports_asset_instancing=True,
            supports_shared_asset_table=True,
            supports_gpu_geometry_instancing=True,
            supports_batch_transform_update=True,
            transform_transport="device_world_major",
            output_transport="geophys_framebuffer",
        ),
        implementation="task_env.render.raytracer.backend.RaytracerRenderBackend",
    )),
    _BackendRegistration(RenderBackendDescriptor(
        name=RenderBackendName.RASTERIZER.value,
        capabilities=RenderBackendCapabilities(
            supports_parallel=True,
            supports_asset_instancing=False,
            supports_shared_asset_table=False,
            supports_gpu_geometry_instancing=False,
            supports_batch_transform_update=False,
            transform_transport="device_world_major",
            output_transport="geophys_framebuffer",
        ),
        implementation="task_env.render.rasterizer.backend.RasterizerRenderBackend",
    )),
    _BackendRegistration(RenderBackendDescriptor(
        name=RenderBackendName.FLORA.value,
        capabilities=RenderBackendCapabilities(
            supports_parallel=True,
            supports_asset_instancing=True,
            output_transport="external_host_rgba8",
        ),
        implementation="task_env.render.flora.backend.FloraRenderBackend",
    )),
    _BackendRegistration(
        RenderBackendDescriptor(
            name="mujoco_reference",
            capabilities=RenderBackendCapabilities(
                supports_parallel=False,
                supports_asset_instancing=False,
                output_transport="external_reference",
            ),
            implementation="task_env.render.base.backend.LegacyReferenceRenderBackend",
        ),
        aliases=("mujoco", "external_mujoco"),
        listed=False,
    ),
)


def _backend_registration(name: str) -> _BackendRegistration:
    for registration in _BACKEND_REGISTRATIONS:
        if name == registration.descriptor.name or name in registration.aliases:
            return registration
    raise KeyError(name)


class LegacyReferenceRenderBackend(SceneSourceBackend):
    """Compatibility adapter for the existing MuJoCo reference renderer."""

    name = _backend_registration("mujoco_reference").descriptor.name
    capabilities = _backend_registration("mujoco_reference").descriptor.capabilities

    @property
    def source_backend_name(self) -> str:
        return self.name


__all__ = [
    "RenderBackend",
    "RenderBackendDescriptor",
    "SceneSourceBackend",
    "LegacyReferenceRenderBackend",
]
