"""Load and render one asset-backed Go2 Flora SceneFile."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from task_env.tasks.go2_walk.flora_assets import build_go2_flora_bundle
from task_env.render.flora.runtime import FloraRuntimeConfig
from task_env.render.flora.scene import FloraScene


LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT = Path("temp_outputs/task_env/flora/go2_single")


def _write_ppm(path: Path, rgba) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width, _channels = rgba.shape
    with path.open("wb") as stream:
        stream.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        stream.write(rgba[:, :, :3].tobytes(order="C"))


def run(
    flora_root: str | Path,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    width: int = 640,
    height: int = 480,
    force: bool = False,
) -> dict[str, object]:
    bundle = build_go2_flora_bundle(
        output_dir=output_dir,
        instance_count=1,
        force=force,
    )
    config = FloraRuntimeConfig.resolve(runtime_root=flora_root)
    output_path = Path(output_dir) / "go2_single_frame.ppm"
    with FloraScene(
        bundle.scene_path,
        runtime_config=config,
        body_node_names=bundle.body_node_names,
        width=width,
        height=height,
    ) as scene:
        scene.set_camera((1.7, -1.7, 1.0), (0.0, 0.0, 0.35))
        frame = scene.render_rgba8()
        _write_ppm(output_path, frame)
        report = {
            "schema": "task_env.flora_single_scene_smoke.v1",
            "scene_path": str(bundle.scene_path),
            "frame_path": str(output_path),
            "resolution": [int(width), int(height)],
            "scene_stats": scene.scene_stats(),
        }
    LOGGER.info("Flora single scene smoke passed: %s", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flora-root", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(
        args.flora_root,
        output_dir=args.output_dir,
        width=args.width,
        height=args.height,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
