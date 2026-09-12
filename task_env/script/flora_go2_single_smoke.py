"""Build and render one asset-backed Go2 scene with Flora."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

from ._bootstrap import get_logger


def _write_ppm(path: Path, rgba: bytes, width: int, height: int) -> None:
    image = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        stream.write(np.ascontiguousarray(image[:, :, :3]).tobytes())


def _import_native(module_dir: Path):
    sys.path.insert(0, str(module_dir.resolve()))
    import FloraRenderPyNative as renderer

    return renderer


def main() -> int:
    logger = get_logger("task-env-flora-go2-single-smoke")
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Render one MJCF-authored Go2 asset graph through Flora."
    )
    parser.add_argument(
        "--flora-root", type=Path, default=Path("/home/zyf/lly_project/Flora")
    )
    parser.add_argument("--module-dir", type=Path, default=None)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("temp_outputs/task_env/flora_go2_single")
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from task_env.tasks.go2_walk.flora_assets import build_go2_flora_bundle

    module_dir = args.module_dir or args.flora_root / "bin" / "linux-x64"
    bundle = build_go2_flora_bundle(
        output_dir=repo_root / args.output_dir,
        force=args.force,
    )
    logger.info(
        "Go2 Flora asset bundle prepared",
        event="render.flora.go2_bundle_ready",
        scene=str(bundle.scene_path),
        unique_models=len(bundle.model_paths),
        body_nodes=len(bundle.body_node_names),
        visual_nodes=bundle.visual_node_count,
    )

    renderer = _import_native(module_dir)
    renderer.init(str(args.flora_root.resolve()), "vulkan", -1, False, False)
    output_path = repo_root / args.output_dir / "go2_single_frame.ppm"
    try:
        scene = renderer.create_scene()
        scene.load_scene(str(bundle.scene_path))
        scene.set_ambient((0.16, 0.18, 0.22), (0.025, 0.03, 0.04))
        scene.set_default_light((-0.4, -1.0, -0.6), (1.0, 1.0, 1.0), 2.5)
        scene.set_camera(
            (1.35, 0.95, 0.95), (0.0, 0.0, 0.25), (0.0, 0.0, 1.0),
            45.0, args.width, args.height, 0.05, 20.0,
        )
        stats = scene.get_scene_stats()
        logger.info(
            "Flora Go2 scene loaded",
            event="render.flora.go2_scene_loaded",
            node_handles=scene.node_handle_count,
            stats=stats,
        )
        logger.check_or_raise(
            scene.node_handle_count >= len(bundle.body_node_names),
            "Flora did not expose all Go2 body graph nodes",
            expected_body_nodes=len(bundle.body_node_names),
            node_handles=scene.node_handle_count,
        )

        handles = scene.get_node_handles([bundle.body_node_names[0]])
        before = bytes(scene.render_frame())
        image = np.frombuffer(before, dtype=np.uint8)
        logger.check_or_raise(
            image.size == args.width * args.height * 4,
            "Flora returned an unexpected RGBA frame size",
            byte_count=int(image.size),
        )
        visible_pixels = int(np.count_nonzero(image.reshape(-1, 4)[:, :3].max(axis=1)))
        logger.check_or_raise(
            visible_pixels > 100,
            "Go2 asset frame contains no visible RGB pixels",
            visible_pixels=visible_pixels,
        )

        scene.update_node_transforms_batch(
            handles,
            [[
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.445, 1.0,
            ]],
        )
        after = bytes(scene.render_frame())
        logger.check_or_raise(
            before != after,
            "Flora body transform update did not change the rendered frame",
        )
        _write_ppm(output_path, after, scene.width, scene.height)
    finally:
        renderer.destroy()

    logger.success(
        "Flora Go2 single-asset smoke completed",
        output=str(output_path),
        scene=str(bundle.scene_path),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
