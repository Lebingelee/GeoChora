"""TaskEnv adapter for GeoPhys' internal rasterizer."""

from ..base.backend import SceneSourceBackend
from ..base.contracts import RenderBackendCapabilities


class RasterizerRenderBackend(SceneSourceBackend):
    name = "rasterizer"
    capabilities = RenderBackendCapabilities(
        supports_parallel=True,
        supports_asset_instancing=False,
        supports_shared_asset_table=False,
        supports_gpu_geometry_instancing=False,
        supports_batch_transform_update=False,
        transform_transport="device_world_major",
        output_transport="geophys_framebuffer",
    )

    @property
    def source_backend_name(self) -> str:
        return self.name


__all__ = ["RasterizerRenderBackend"]
