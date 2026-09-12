"""Capture one fixed-seed PickCube camera frame with current or legacy lighting.

Run each mode in a separate process.  This is intentional: some CPU Taichi
setups abort during renderer teardown after the output has been written.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ._bootstrap import configure_imports

configure_imports()

from task_env import CameraSpec, make_env
from task_env.utils.rotation import look_at_quat_wxyz as _look_at_quat


_LEGACY_AMBIENT = (0.30, 0.34, 0.42)
_LEGACY_DIRECTION = (0.48, 0.32, 0.82)
_LEGACY_LIGHT_COLOR = (1.0, 0.95, 0.85)


def _config(backend: str) -> dict[str, object]:
    base_position = np.asarray((0.8, 0.0, 0.8), dtype=np.float64)
    return {
        "runtime": {"backend": backend, "broadphase": "n2", "prewarm": False,
                    "physics_dt": 1.0 / 600.0, "control_substeps": 20},
        "robot": {"controller": {"kind": "absolute_pose", "reference": "world",
                                   "rotation_representation": "quaternion_wxyz"}},
        "episode": {"horizon": 1},
        "render": {"camera_obs": True, "backend": "raytracer", "cameras": (
            CameraSpec("base_camera", 224, 224, frame="world", position=tuple(base_position),
                       quaternion_wxyz=_look_at_quat(base_position, np.asarray((0.0, 0.0, -0.2)))),
            CameraSpec("hand_camera", 224, 224, frame="site", parent="nutassembly_ee_site",
                       position=(0.08, 0.0, -0.03),
                       quaternion_wxyz=(0.70710678, 0.0, -0.70710678, 0.0)),
        )},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("current", "legacy"), required=True)
    parser.add_argument("--backend", choices=("cpu", "vulkan", "cuda"), default="cpu")
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    env = make_env("pick-cube-v1", config=_config(args.backend))
    try:
        visualizer = env._sensor_provider._visualizer
        if args.mode == "legacy":
            visualizer.set_ambient_light(_LEGACY_AMBIENT)
            visualizer.add_light(direction=_LEGACY_DIRECTION, color=_LEGACY_LIGHT_COLOR)
        observation, _ = env.reset(seed=args.seed)
        images = {name: np.asarray(image, dtype=np.float32) for name, image in observation["rgb"].items()}
        np.savez_compressed(args.output, **images)
        summary = {
            "mode": args.mode,
            "seed": args.seed,
            "images": {name: {"shape": list(image.shape), "mean": float(image.mean()),
                              "std": float(image.std()), "min": float(image.min()),
                              "max": float(image.max())} for name, image in images.items()},
        }
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
