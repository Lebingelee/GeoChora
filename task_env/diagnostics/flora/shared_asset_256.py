"""Verify that many Go2 instances share one Flora model table."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from task_env.tasks.go2_walk.flora_assets import build_go2_flora_bundle
from task_env.render.flora.runtime import FloraRuntimeConfig
from task_env.render.flora.scene import FloraScene


LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT = Path("temp_outputs/task_env/flora/go2_shared_256")


def _compiled_go2_body_order() -> tuple[str, ...]:
    """Use the public compiled model order for the live transform smoke."""

    from scene import import_scene_source
    from task_env.tasks.go2_walk.assets import Go2WalkSceneComposer

    source, _ = Go2WalkSceneComposer().build_scene_source(
        None,
        [SimpleNamespace(uid="go2-v1")],
    )
    model = import_scene_source(source).build_rigid_scene_model()
    return tuple(str(item.object_key) for item in model.objects)


def _write_ppm(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width, _channels = rgba.shape
    with path.open("wb") as stream:
        stream.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        stream.write(np.ascontiguousarray(rgba[:, :, :3]).tobytes(order="C"))


def run(
    output_dir: str | Path = DEFAULT_OUTPUT,
    *,
    instances: int = 256,
    flora_root: str | Path | None = None,
    force: bool = False,
) -> dict[str, object]:
    if int(instances) < 1:
        raise ValueError("instances must be positive")
    body_order = _compiled_go2_body_order()
    bundle = build_go2_flora_bundle(
        output_dir=output_dir,
        instance_count=instances,
        body_order=body_order,
        force=force,
    )
    payload = json.loads(bundle.scene_path.read_text(encoding="utf-8"))
    models = tuple(payload.get("models", ()))
    roots = tuple(payload.get("graph", ()))
    if len(models) != len(bundle.model_paths):
        raise AssertionError("SceneFile model table differs from generated model paths")
    if len(roots) != int(instances):
        raise AssertionError(
            f"expected {instances} graph roots, found {len(roots)}"
        )
    model_refs = [
        int(node["model"])
        for root in roots
        for body in root.get("children", ())
        for node in body.get("children", ())
        if "model" in node
    ]
    if not model_refs or min(model_refs) < 0 or max(model_refs) >= len(models):
        raise AssertionError("SceneFile contains an invalid shared model reference")
    report = {
        "schema": "task_env.flora_shared_asset_smoke.v1",
        "instance_count": int(instances),
        "graph_root_count": len(roots),
        "unique_models": len(models),
        "visual_model_references": len(model_refs),
        "model_table_shared": len(models) == len(bundle.model_paths),
        "scene_path": str(bundle.scene_path),
    }
    if flora_root is not None:
        config = FloraRuntimeConfig.resolve(runtime_root=flora_root)
        with FloraScene(
            bundle.scene_path,
            runtime_config=config,
            body_node_names=bundle.body_node_names,
            width=64,
            height=64,
        ) as scene:
            from scene import import_scene_source
            from task_env.tasks.go2_walk.assets import Go2WalkSceneComposer

            model_source, _ = Go2WalkSceneComposer().build_scene_source(
                None,
                [SimpleNamespace(uid="go2-v1")],
            )
            model = import_scene_source(model_source).build_rigid_scene_model()
            base_positions = np.asarray(model.positions, dtype=np.float32)
            base_orientations = np.asarray(model.orientations, dtype=np.float32)
            positions = np.concatenate(
                [
                    base_positions
                    + np.asarray(
                        (
                            (instance % 16) - 7.5,
                            (instance // 16) - 7.5,
                            0.0,
                        ),
                        dtype=np.float32,
                    )
                    for instance in range(int(instances))
                ],
                axis=0,
            )
            orientations = np.tile(base_orientations, (int(instances), 1))
            scene.update_body_poses(positions, orientations)
            scene.set_camera((0.0, -28.0, 20.0), (0.0, 0.0, 0.4))
            frame = scene.render_rgba8()
            frame_path = Path(output_dir) / "go2_shared_256_frame.ppm"
            _write_ppm(frame_path, frame)
            if not np.any(frame[:, :, :3]):
                raise AssertionError("Flora 256-instance pose-update frame is black")
            native_stats = scene.scene_stats()
        report["native_scene_stats"] = native_stats
        report["pose_update_batch"] = {
            "body_count": int(positions.shape[0]),
            "transport": "direct_host_pose_to_native_batch_update",
            "frame_path": str(frame_path),
        }
        if native_stats.get("unique_meshes") != len(models):
            raise AssertionError(
                "Flora native scene did not preserve the shared unique mesh count"
            )
        if native_stats.get("mesh_instances") != len(model_refs):
            raise AssertionError(
                "Flora native scene mesh instance count differs from SceneFile references"
            )
    LOGGER.info("Flora shared asset smoke passed: %s", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--instances", type=int, default=256)
    parser.add_argument("--flora-root")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(
        args.output_dir,
        instances=args.instances,
        flora_root=args.flora_root,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
