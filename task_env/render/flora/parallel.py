"""Flora parallel visualizer for one shared asset table and selected worlds.

The physics-side parallel source still owns selection and snapshot publication.
This module only consumes that snapshot provider at the render boundary.  One
Flora SceneFile contains one model table and ``render_num`` graph instances;
per-frame work is a single host readback followed by one native transform batch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from .assets import (
    FloraSceneBundle,
    build_scene_file_from_assemblies,
    build_scene_file_from_render_scene,
)
from .runtime import FloraRuntimeConfig
from .scene import FloraScene
from ..tools.camera import InteractiveCameraController


_DEFAULT_OUTPUT_ROOT = Path("temp_outputs/task_env/flora")


def _provider_body_count(source: object) -> int:
    reader = getattr(source, "read_rigid_render_transform_provider", None)
    if not callable(reader):
        raise RuntimeError(
            "Flora parallel source must expose a rigid render transform provider"
        )
    provider = reader()
    if provider is None:
        raise RuntimeError(
            "Flora parallel source published no rigid render transform provider"
        )
    return int(provider.schema.body_count)


class FloraParallelVisualizer:
    """Render selected snapshot worlds with one shared Flora model table."""

    backend_name = "flora"

    def __init__(
        self,
        source: object,
        *,
        compiled_scene: object,
        render_num: int,
        width: int,
        height: int,
        output_dir: str | Path | None = None,
        force_scene_build: bool = False,
        runtime_config: FloraRuntimeConfig | None = None,
    ) -> None:
        self.source = source
        self.compiled_scene = compiled_scene
        self.render_num = int(render_num)
        self.width = int(width)
        self.height = int(height)
        if self.render_num < 1:
            raise ValueError("Flora parallel render_num must be positive")
        if self.width < 1 or self.height < 1:
            raise ValueError("Flora parallel resolution must be positive")

        expected_body_count = _provider_body_count(source)
        root = (
            Path(output_dir).expanduser().resolve()
            if output_dir is not None
            else _DEFAULT_OUTPUT_ROOT.resolve()
        )
        root.mkdir(parents=True, exist_ok=True)
        scene_path = root / f"go2_parallel_{self.render_num}.scene.json"
        self._bundle = self._build_bundle(
            source,
            compiled_scene=compiled_scene,
            scene_path=scene_path,
            instance_count=self.render_num,
            force=force_scene_build,
        )
        if len(self._bundle.body_node_names) != expected_body_count:
            raise RuntimeError(
                "Flora SceneFile body nodes do not match the published snapshot "
                f"provider: nodes={len(self._bundle.body_node_names)}, "
                f"provider_body_count={expected_body_count}. "
                "The asset/body order must be lowered from the same logical scene."
            )

        self._runtime_config = runtime_config or FloraRuntimeConfig.resolve()
        self._scene = FloraScene(
            self._bundle.scene_path,
            runtime_config=self._runtime_config,
            body_node_names=self._bundle.body_node_names,
            width=self.width,
            height=self.height,
        )
        self._closed = False
        self._last_rgba8: np.ndarray | None = None
        self._last_transform_count = 0
        self._camera_far = 1000.0
        self._last_camera_pose = (
            (2.6, -1.8, 2.2),
            (0.5, 0.5, 0.5),
            (0.0, 0.0, 1.0),
        )
        self._initial_camera_pose = self._last_camera_pose
        self.set_camera_pose(*self._initial_camera_pose)
        self._camera_controller = InteractiveCameraController(
            position=self._last_camera_pose[0],
            look_at=self._last_camera_pose[1],
            up=self._last_camera_pose[2],
            pose_sink=self._apply_interactive_camera_pose,
            pan_speed_per_norm=0.5,
            wheel_dolly_step=0.08,
        )

    @staticmethod
    def _build_bundle(
        source: object,
        *,
        compiled_scene: object,
        scene_path: Path,
        instance_count: int,
        force: bool,
    ) -> FloraSceneBundle:
        assembly_reader = getattr(source, "read_render_assemblies", None)
        assemblies = tuple(assembly_reader() or ()) if callable(assembly_reader) else ()
        if assemblies:
            return build_scene_file_from_assemblies(
                assemblies=assemblies,
                output_path=scene_path,
                instance_count=int(instance_count),
                force=force,
                include_checker_floor=True,
                floor_half_extent=256.0,
                floor_tile_size=2.0,
            )
        imported_scene = getattr(compiled_scene, "imported_scene", None)
        render_scene_builder = getattr(imported_scene, "build_render_scene_desc", None)
        if not callable(render_scene_builder):
            raise RuntimeError(
                "Flora parallel rendering requires a compiled public "
                "RenderSceneDesc or RenderAssemblyDesc input"
            )
        render_scene = render_scene_builder(
            scene_model=getattr(compiled_scene, "scene_model", None)
        )
        scene_model = getattr(compiled_scene, "scene_model", None)
        scene_objects = tuple(getattr(scene_model, "objects", ()) or ())
        body_names = {
            int(getattr(item, "object_id", index)): str(
                getattr(item, "object_key", "")
            )
            for index, item in enumerate(scene_objects)
            if str(getattr(item, "object_key", ""))
        }
        if not body_names:
            raise RuntimeError(
                "Flora render-scene lowering requires the compiled scene model "
                "to expose ordered object_key values"
            )
        return build_scene_file_from_render_scene(
            render_scene=render_scene,
            body_names=body_names,
            output_path=scene_path,
            instance_count=int(instance_count),
            force=force,
            include_checker_floor=True,
            floor_half_extent=256.0,
            floor_tile_size=2.0,
        )

    @property
    def bundle(self) -> FloraSceneBundle:
        return self._bundle

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Flora parallel visualizer is closed")

    def set_camera_pose(self, position, look_at, up) -> None:
        self._require_open()
        pose = (
            tuple(float(value) for value in position),
            tuple(float(value) for value in look_at),
            tuple(float(value) for value in up),
        )
        if any(len(component) != 3 for component in pose):
            raise ValueError("Flora camera pose components must be 3-vectors")
        controller = getattr(self, "_camera_controller", None)
        if controller is not None:
            controller.sync_pose(*pose)
        self._write_camera_pose(*pose)

    def _write_camera_pose(self, position, look_at, up) -> None:
        """Write a pose without synchronizing the input controller."""

        pose = (
            tuple(float(value) for value in position),
            tuple(float(value) for value in look_at),
            tuple(float(value) for value in up),
        )
        self._last_camera_pose = pose
        self._scene.set_camera(
            pose[0],
            pose[1],
            up=pose[2],
            far=float(self._camera_far),
        )

    def _apply_interactive_camera_pose(self, position, look_at, up) -> None:
        self._write_camera_pose(position, look_at, up)

    def set_parallel_camera_domain(
        self,
        world_transforms: Sequence[Sequence[float]],
    ) -> None:
        """Fit the fixed camera to the selected grid without changing assets."""

        self._require_open()
        offsets = np.asarray(
            [
                (float(transform[3]), float(transform[7]), float(transform[11]))
                for transform in world_transforms
            ],
            dtype=np.float32,
        )
        if offsets.size == 0:
            return
        lower = np.min(offsets, axis=0)
        upper = np.max(offsets, axis=0)
        center = 0.5 * (lower + upper) + np.asarray((0.0, 0.0, 0.4), dtype=np.float32)
        extent = upper - lower + np.asarray((1.5, 1.5, 1.0), dtype=np.float32)
        distance = max(float(np.max(extent)) * 1.6, 2.5)
        # The default 1000-unit far plane is insufficient for the 4-column,
        # 256-world layout (its grid span is roughly 570 units).  Keep the
        # camera contract stable while fitting the selected-world domain.
        self._camera_far = max(1000.0, distance * 4.0 + 10.0)
        self._initial_camera_pose = (
            (
                float(center[0]),
                float(center[1] - distance),
                float(center[2] + 0.65 * distance),
            ),
            tuple(float(value) for value in center),
            (0.0, 0.0, 1.0),
        )
        self.set_camera_pose(*self._initial_camera_pose)
        controller = getattr(self, "_camera_controller", None)
        if controller is not None:
            # Match the existing Rasterizer/Orbit controller's scale to the
            # selected-world camera distance.  A fixed 0.5 world-unit pan is
            # imperceptible once 256 worlds are fit into one view.
            controller.set_motion_scale(
                pan_speed_per_norm=max(float(distance) * 1.732, 0.5),
                wheel_dolly_step=max(float(distance) * 0.08, 0.05),
            )

    def read_frame(
        self,
        *,
        width: int,
        height: int,
        synchronized: bool = False,
    ) -> np.ndarray:
        del synchronized
        self._require_open()
        if (int(width), int(height)) != (self.width, self.height):
            raise ValueError(
                "Flora parallel frame resolution cannot change after SceneFile load: "
                f"requested={(int(width), int(height))}, configured={(self.width, self.height)}"
            )
        reader = getattr(self.source, "read_rigid_render_transform_provider", None)
        provider = reader() if callable(reader) else None
        if provider is None:
            raise RuntimeError("Flora parallel source lost its rigid transform provider")
        count = int(provider.schema.body_count)
        if count != len(self._bundle.body_node_names):
            raise RuntimeError(
                "Flora provider body count changed after SceneFile construction: "
                f"provider={count}, nodes={len(self._bundle.body_node_names)}"
            )
        # The explicit host readback is intentionally confined to this render
        # boundary.  Flora then receives one native batch update for all body
        # nodes across all selected worlds.
        self._scene.update_from_provider(provider)
        self._last_transform_count = count
        rgba8 = self._scene.render_rgba8()
        self._last_rgba8 = rgba8
        return np.ascontiguousarray(rgba8[:, :, :3], dtype=np.float32) / 255.0

    def _synchronize_taichi_runtime(self) -> None:
        """Compatibility hook for the common headed presenter."""

    def _present_rendered_frame(self, canvas) -> None:
        self._require_open()
        if self._last_rgba8 is None:
            raise RuntimeError("Flora parallel visualizer has no rendered frame")
        from visualization.flora.rgba_output import display_frame_from_rgba8

        canvas.submit_frame(display_frame_from_rgba8(self._last_rgba8))

    def _mark_displayed_snapshot(self) -> None:
        return None

    def _process_camera_input(self, window) -> bool:
        controller = getattr(self, "_camera_controller", None)
        if controller is None:
            return False
        return bool(controller.update(window))

    def read_resources(self) -> dict[str, object]:
        stats = self._scene.scene_stats()
        return {
            "backend": self.backend_name,
            "asset_mode": "one_logical_asset_table",
            "asset_transport": "shared_scene_file_model_table",
            "instance_transport": "scene_graph_instances",
            "transform_transport": "host_batch_explicit_readback",
            "output_transport": "external_host_rgba8",
            "render_world_count": int(self.render_num),
            "body_transform_count": int(self._last_transform_count),
            "scene_path": str(self._bundle.scene_path),
            "model_paths": [str(path) for path in self._bundle.model_paths],
            "scene_stats": stats,
        }

    def describe(self) -> dict[str, object]:
        return {
            "kind": "parallel_asset_visualizer",
            "backend": self.backend_name,
            "render_world_count": int(self.render_num),
            "unique_model_count": len(self._bundle.model_paths),
            "body_node_count": len(self._bundle.body_node_names),
            "transform_transport": "host_batch_explicit_readback",
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._scene.close()


__all__ = ["FloraParallelVisualizer"]
