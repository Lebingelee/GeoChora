"""TaskEnv-specific Flora SceneFile and transform-update wrapper.

The wrapper consumes a prepared SceneFile and talks to the installed Linux
Flora backend.  It deliberately does not mirror ``src/visualization/flora``;
the source package remains the owner of the common visualization contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .assets import FloraSceneBundle, build_scene_file_from_assemblies
from .runtime import FloraRuntimeConfig, load_flora_backend
from .transforms import (
    geophys_to_flora_matrix,
    geophys_to_flora_points,
    pose_matrix,
    read_rigid_provider_arrays,
)


class FloraScene:
    """A loaded Flora SceneFile with shared meshes and mutable body nodes."""

    def __init__(
        self,
        scene_path: str | Path,
        *,
        runtime_config: FloraRuntimeConfig,
        body_node_names: Sequence[str] = (),
        width: int = 640,
        height: int = 480,
    ) -> None:
        self.scene_path = Path(scene_path).expanduser().resolve()
        if not self.scene_path.is_file():
            raise FileNotFoundError(f"Flora SceneFile does not exist: {self.scene_path}")
        self.runtime_config = runtime_config
        self.width = int(width)
        self.height = int(height)
        if self.width < 1 or self.height < 1:
            raise ValueError("Flora scene resolution must be positive")
        self._closed = False
        self._backend_module = load_flora_backend(runtime_config)
        renderer_type = getattr(self._backend_module, "FloraRenderer", None)
        if renderer_type is None:
            raise RuntimeError("installed Flora backend does not expose FloraRenderer")
        self._renderer = renderer_type(
            module_dir=runtime_config.module_dir,
            runtime_dir=runtime_config.runtime_root,
            backend=runtime_config.backend,
            device_index=runtime_config.device_index,
            enable_debug=runtime_config.enable_debug,
            enable_external_interop=runtime_config.enable_external_interop,
            rendered_envs_idx=[0],
        )
        native_scene = getattr(self._renderer, "_scene", None)
        if native_scene is None or not callable(getattr(native_scene, "load_scene", None)):
            self.close()
            raise RuntimeError(
                "installed Flora backend does not expose the SceneFile load/update API"
            )
        self._native_scene = native_scene
        self._native_scene.load_scene(str(self.scene_path))
        # ``FloraRenderer`` reapplies its default environment after its own
        # internal GLB build, but the direct SceneFile API does not.  Restore
        # the public renderer lighting contract after ``load_scene`` so asset
        # frames are not silently black.
        set_ambient = getattr(self._renderer, "set_ambient", None)
        if callable(set_ambient):
            set_ambient((0.03, 0.04, 0.06), (0.01, 0.01, 0.01))
        set_default_light = getattr(self._renderer, "set_default_light", None)
        if callable(set_default_light):
            set_default_light(
                direction=(-0.4, -1.0, -0.6),
                color=(1.0, 1.0, 1.0),
                irradiance=2.0,
            )
        self._body_node_names = tuple(str(name) for name in body_node_names)
        self._body_handles: tuple[int, ...] = ()
        if self._body_node_names:
            self._body_handles = tuple(
                int(value)
                for value in self._native_scene.get_node_handles(
                    list(self._body_node_names)
                )
            )

    @property
    def body_node_names(self) -> tuple[str, ...]:
        return self._body_node_names

    @property
    def body_handles(self) -> tuple[int, ...]:
        return self._body_handles

    @property
    def closed(self) -> bool:
        return bool(self._closed)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Flora scene is closed")

    def set_camera(
        self,
        position: object,
        look_at: object,
        *,
        up: object = (0.0, 0.0, 1.0),
        fov_degrees: float = 45.0,
        near: float = 0.1,
        far: float = 1000.0,
    ) -> None:
        self._require_open()
        position_flora = tuple(float(value) for value in geophys_to_flora_points(position))
        look_at_flora = tuple(float(value) for value in geophys_to_flora_points(look_at))
        up_flora = tuple(float(value) for value in geophys_to_flora_points(up))
        self._native_scene.set_camera(
            position_flora,
            look_at_flora,
            up_flora,
            float(fov_degrees),
            int(self.width),
            int(self.height),
            float(near),
            float(far),
        )

    def update_node_matrices(
        self,
        node_names: Sequence[str],
        matrices: Sequence[object],
    ) -> None:
        self._require_open()
        names = tuple(str(name) for name in node_names)
        if len(names) != len(matrices):
            raise ValueError("node_names and matrices must have equal lengths")
        if not names:
            return
        handles = (
            self._body_handles
            if names == self._body_node_names and len(self._body_handles) == len(names)
            else tuple(
                int(value)
                for value in self._native_scene.get_node_handles(list(names))
            )
        )
        converted = []
        for matrix in matrices:
            value = np.asarray(matrix, dtype=np.float32)
            if value.shape != (4, 4) or not np.isfinite(value).all():
                raise ValueError("Flora node matrices must be finite 4x4 arrays")
            converted_matrix = geophys_to_flora_matrix(value)
            converted.append(converted_matrix.reshape(-1).tolist())
        self._native_scene.update_node_transforms_batch(
            [int(handle) for handle in handles],
            converted,
        )

    def update_body_poses(
        self,
        positions: object,
        orientations_wxyz: object,
        *,
        node_names: Sequence[str] | None = None,
    ) -> None:
        names = self._body_node_names if node_names is None else tuple(node_names)
        position_array = np.asarray(positions, dtype=np.float32).reshape(-1, 3)
        orientation_array = np.asarray(orientations_wxyz, dtype=np.float32).reshape(-1, 4)
        if len(names) != position_array.shape[0] or position_array.shape[0] != orientation_array.shape[0]:
            raise ValueError(
                "Flora body pose count does not match body node count: "
                f"nodes={len(names)}, positions={position_array.shape}, orientations={orientation_array.shape}"
            )
        matrices = [
            pose_matrix(position, orientation)
            for position, orientation in zip(position_array, orientation_array, strict=True)
        ]
        self.update_node_matrices(names, matrices)

    def update_from_provider(
        self,
        provider: object,
        *,
        node_names: Sequence[str] | None = None,
    ) -> None:
        positions, orientations = read_rigid_provider_arrays(provider)
        self.update_body_poses(positions, orientations, node_names=node_names)

    def render_rgba8(self) -> np.ndarray:
        self._require_open()
        rgba = self._native_scene.render_frame()
        image = np.frombuffer(rgba, dtype=np.uint8)
        expected = self.width * self.height * 4
        if image.size != expected:
            raise RuntimeError(
                f"Flora returned {image.size} bytes, expected {expected}"
            )
        return np.ascontiguousarray(image.reshape(self.height, self.width, 4))

    def scene_stats(self) -> dict[str, object]:
        self._require_open()
        reader = getattr(self._native_scene, "get_scene_stats", None)
        if not callable(reader):
            return {"available": False}
        raw = reader()
        if isinstance(raw, Mapping):
            return {str(key): value for key, value in raw.items()}
        fields = (
            "mesh_instances",
            "unique_meshes",
            "unique_geometries",
            "unique_materials",
            "opaque_materials",
            "alpha_tested_materials",
            "alpha_blended_materials",
            "transmissive_materials",
            "unknown_materials",
            "unique_vertices",
            "unique_indices",
            "shadow_instances",
        )
        return {
            "available": True,
            **{
                field: getattr(raw, field)
                for field in fields
                if hasattr(raw, field)
            },
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        renderer = getattr(self, "_renderer", None)
        destroy = getattr(renderer, "destroy", None)
        if callable(destroy):
            destroy()
        self._native_scene = None

    def __enter__(self) -> "FloraScene":
        self._require_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def build_flora_scene_from_source(
    source: object,
    *,
    output_path: str | Path,
    runtime_config: FloraRuntimeConfig,
    instance_count: int | None = None,
    width: int = 640,
    height: int = 480,
    force: bool = False,
) -> tuple[FloraScene, FloraSceneBundle]:
    """Build a shared SceneFile from ``SceneVisualizationSource`` assemblies."""

    reader = getattr(source, "read_render_assemblies", None)
    if not callable(reader):
        raise ValueError("Flora source must expose read_render_assemblies()")
    assemblies = tuple(reader() or ())
    if not assemblies:
        raise ValueError("Flora source published no RenderAssemblyDesc entries")
    if instance_count is None:
        provider_reader = getattr(source, "read_rigid_render_transform_provider", None)
        provider = provider_reader() if callable(provider_reader) else None
        instance_count = int(provider.schema.world_count) if provider is not None else 1
    bundle = build_scene_file_from_assemblies(
        assemblies=assemblies,
        output_path=output_path,
        instance_count=int(instance_count),
        force=force,
    )
    scene = FloraScene(
        bundle.scene_path,
        runtime_config=runtime_config,
        body_node_names=bundle.body_node_names,
        width=width,
        height=height,
    )
    return scene, bundle


__all__ = ["FloraScene", "build_flora_scene_from_source"]
