"""Flora backend implementation for the TaskEnv render boundary."""

from pathlib import Path
from typing import Mapping

from ..base.backend import SceneSourceBackend
from ..base.contracts import RenderBackendBuildError, RenderBackendCapabilities


class FloraRenderBackend(SceneSourceBackend):
    """Adapter for the externally installed Flora visualizer contract.

    Importing this module is side-effect free.  Flora registration is
    requested only when a visualizer is actually constructed.  Parallel
    TaskEnv rendering uses the explicit SceneFile path in
    :class:`FloraParallelVisualizer`; the output remains host RGBA8 and the
    transform transport remains an explicit render-boundary readback.
    """

    name = "flora"
    capabilities = RenderBackendCapabilities(
        supports_parallel=True,
        supports_asset_instancing=True,
        output_transport="external_host_rgba8",
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
        try:
            from visualization.flora import register_flora_backend

            register_flora_backend()
        except Exception as exc:
            raise RenderBackendBuildError(
                "Flora backend registration is unavailable; install/configure "
                "the external Flora adapter before rendering"
            ) from exc
        return super().create_visualizer(
            source,
            request=request,
            visualizer_kwargs=visualizer_kwargs,
        )

    def create_asset_scene(
        self,
        source: object,
        *,
        runtime_root: str | Path,
        output_path: str | Path,
        instance_count: int | None = None,
        width: int = 640,
        height: int = 480,
        device_index: int = -1,
        enable_debug: bool = False,
        force: bool = False,
    ):
        """Create the TaskEnv SceneFile path without changing source/runtime code.

        This explicit method is the asset-backed entry point.  The legacy
        ``create_visualizer`` path remains intact until the TaskEnv provider
        gains native SceneFile frame presentation.
        """

        from .runtime import FloraRuntimeConfig
        from .scene import build_flora_scene_from_source

        config = FloraRuntimeConfig.resolve(
            runtime_root=runtime_root,
            device_index=device_index,
            enable_debug=enable_debug,
        )
        return build_flora_scene_from_source(
            source,
            output_path=output_path,
            runtime_config=config,
            instance_count=instance_count,
            width=width,
            height=height,
            force=force,
        )

    def create_parallel_visualizer(
        self,
        source: object,
        *,
        compiled_scene: object,
        render_num: int,
        width: int,
        height: int,
        output_dir: str | Path | None = None,
    ) -> object:
        """Create the SceneFile-backed selected-world Flora visualizer.

        This is intentionally a Flora-only extension of the common backend
        contract.  The parallel provider owns world selection/snapshots; the
        Flora backend owns asset lowering and native graph updates.
        """

        from .parallel import FloraParallelVisualizer

        return FloraParallelVisualizer(
            source,
            compiled_scene=compiled_scene,
            render_num=int(render_num),
            width=int(width),
            height=int(height),
            output_dir=output_dir,
        )


__all__ = ["FloraRenderBackend"]
