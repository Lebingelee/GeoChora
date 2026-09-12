"""TaskEnv adapter for GeoPhys' internal raytracer."""

from typing import Mapping

from ..base.backend import SceneSourceBackend
from ..base.contracts import RenderBackendBuildError, RenderBackendCapabilities
from .scene import build_raytracer_visualizer


class RaytracerRenderBackend(SceneSourceBackend):
    name = "raytracer"
    capabilities = RenderBackendCapabilities(
        supports_parallel=True,
        supports_asset_instancing=True,
        supports_shared_asset_table=True,
        supports_gpu_geometry_instancing=True,
        supports_batch_transform_update=True,
        transform_transport="device_world_major",
        output_transport="geophys_framebuffer",
    )

    @property
    def source_backend_name(self) -> str:
        return self.name

    def create_visualizer(
        self,
        source: object,
        *,
        request,
        visualizer_kwargs: Mapping[str, object] | None = None,
    ) -> object:
        kwargs = dict(request.visualizer_kwargs())
        if visualizer_kwargs:
            kwargs.update(dict(visualizer_kwargs))
        try:
            return build_raytracer_visualizer(
                source,
                visualizer_kwargs=kwargs,
            )
        except Exception as exc:
            if isinstance(exc, RenderBackendBuildError):
                raise
            raise RenderBackendBuildError(
                f"failed to build TaskEnv RayTracer backend: {exc}"
            ) from exc


__all__ = ["RaytracerRenderBackend"]
