"""TaskEnv adapter for GeoPhys' internal raytracer."""

from typing import Mapping

from ..base.backend import SceneSourceBackend, _backend_registration
from ..base.contracts import RenderBackendBuildError


class RaytracerRenderBackend(SceneSourceBackend):
    name = _backend_registration("raytracer").descriptor.name
    capabilities = _backend_registration("raytracer").descriptor.capabilities

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
        from .scene import build_raytracer_visualizer

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
