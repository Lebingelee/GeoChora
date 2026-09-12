"""Manually exercise P2-S17a single-environment rendering.

Examples::

    PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_single \
        --env-id pendulum-v1 --mode human --render-backend rasterizer
    PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_single \
        --env-id pick-cube-v1 --mode rgb_array --render-backend rasterizer
"""

from __future__ import annotations

import argparse
import time

import numpy as np

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from task_env.script._bootstrap import get_logger
else:
    from ._bootstrap import get_logger


def _action(env_id: str) -> object:
    if env_id == "pendulum-v1":
        return {"torque": np.zeros(1, dtype=np.float32)}
    if env_id == "pick-cube-v1":
        return np.asarray(
            [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            dtype=np.float32,
        )
    raise ValueError(f"unsupported manual render task: {env_id!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-id",
        choices=("pendulum-v1", "pick-cube-v1"),
        default="pendulum-v1",
    )
    parser.add_argument("--mode", choices=("human", "rgb_array"), default="human")
    parser.add_argument("--backend", choices=("cpu", "cuda", "vulkan"), default="cpu")
    parser.add_argument(
        "--render-backend",
        choices=("rasterizer", "raytracer", "mujoco_reference"),
        default="rasterizer",
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument("--sleep", type=float, default=0.02)
    args = parser.parse_args()
    if args.width < 1 or args.height < 1 or args.steps < 1 or args.sleep < 0.0:
        parser.error("width, height, and steps must be positive; sleep must be non-negative")

    from task_env import make_env

    logger = get_logger("task-env-p2-s17a-render-cli")
    env = make_env(
        args.env_id,
        config={
            "runtime": {
                "backend": args.backend,
                "broadphase": "n2",
                "prewarm": False,
            },
            "render": {
                "backend": args.render_backend,
                "width": args.width,
                "height": args.height,
            },
            "episode": {"horizon": max(args.steps + 1, 2)},
        },
        render_mode=args.mode,
    )
    try:
        env.reset(seed=args.seed)
        for step_index in range(args.steps):
            frame = env.render()
            if args.mode == "rgb_array" and step_index == 0:
                logger.check_or_raise(
                    isinstance(frame, np.ndarray)
                    and frame.shape == (args.height, args.width, 3)
                    and frame.dtype == np.dtype("float32")
                    and np.isfinite(frame).all(),
                    "manual RGB render must produce a finite HWC float32 frame",
                    env_id=args.env_id,
                    shape=None if frame is None else frame.shape,
                )
                logger.info(
                    "TaskEnv RGB frame received",
                    event="task_env.render.rgb_frame",
                    env_id=args.env_id,
                    shape=frame.shape,
                    mean=float(frame.mean()),
                )
            _, reward, terminated, truncated, _ = env.step(_action(args.env_id))
            if step_index == 0 or (step_index + 1) % 50 == 0:
                logger.info(
                    "TaskEnv render rollout step",
                    event="task_env.render.step",
                    env_id=args.env_id,
                    mode=args.mode,
                    step=step_index + 1,
                    reward=float(reward),
                    terminated=bool(terminated),
                    truncated=bool(truncated),
                )
            if terminated or truncated:
                env.reset(seed=args.seed + step_index + 1)
            if args.sleep:
                time.sleep(args.sleep)
    finally:
        env.close()
    logger.success(
        "P2-S17a manual single-environment render completed",
        env_id=args.env_id,
        mode=args.mode,
        backend=args.backend,
        render_backend=args.render_backend,
        steps=args.steps,
    )


if __name__ == "__main__":
    main()
