"""TaskEnv adapter for GeoPhys' internal rasterizer."""

from ..base.backend import SceneSourceBackend, _backend_registration


class RasterizerRenderBackend(SceneSourceBackend):
    name = _backend_registration("rasterizer").descriptor.name
    capabilities = _backend_registration("rasterizer").descriptor.capabilities

    @property
    def source_backend_name(self) -> str:
        return self.name


__all__ = ["RasterizerRenderBackend"]
