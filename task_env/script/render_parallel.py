"""Manually exercise P2-S18b parallel selected-world rendering.

Example::

    PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_parallel \
        --env-id pendulum-v1 --num-env 4 --parallel-render-num 4 \
        --mode human --backend cuda --render-backend rasterizer
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", choices=("pendulum-v1",), default="pendulum-v1")
    parser.add_argument("--num-env", type=int, default=4)
    parser.add_argument("--parallel-render-num", type=int, default=None)
    parser.add_argument("--mode", choices=("human", "rgb_array"), default="human")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument(
        "--render-backend",
        choices=("rasterizer", "raytracer"),
        default="rasterizer",
    )
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--columns", type=int, default=2)
    parser.add_argument("--cell-width", type=float, default=4.0)
    parser.add_argument("--cell-depth", type=float, default=4.0)
    parser.add_argument("--padding", type=float, default=0.5)
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument("--sleep", type=float, default=0.02)
    args = parser.parse_args()
    if (
        args.num_env < 1
        or args.width < 1
        or args.height < 1
        or args.columns < 1
        or args.steps < 1
        or args.cell_width <= 0.0
        or args.cell_depth <= 0.0
        or args.padding < 0.0
        or args.sleep < 0.0
    ):
        parser.error("num-env, width, height, columns, and steps must be positive")
    render_num = args.num_env if args.parallel_render_num is None else args.parallel_render_num
    if render_num < 1 or render_num > args.num_env:
        parser.error("parallel-render-num must satisfy 1 <= parallel-render-num <= num-env")

    from task_env.vectorization.parallel import make_homogeneous_env

    logger = get_logger("task-env-p2-s18b-parallel-render-cli")
    env = make_homogeneous_env(
        args.env_id,
        {
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
        args.num_env,
        args.backend,
        execution="local",
    )
    try:
        env.reset(seed=args.seed)
        env.set_parallel_render_num(render_num)
        env.set_parallel_render_layout(
            cell_width=args.cell_width,
            cell_depth=args.cell_depth,
            columns=args.columns,
            padding=args.padding,
        )
        for step_index in range(args.steps):
            frame = env.render(mode=args.mode)
            if args.mode == "rgb_array" and step_index == 0:
                logger.check_or_raise(
                    isinstance(frame, np.ndarray)
                    and frame.shape == (args.height, args.width, 3)
                    and frame.dtype == np.dtype("float32")
                    and np.isfinite(frame).all(),
                    "parallel RGB render must produce a finite HWC float32 frame",
                    shape=None if frame is None else frame.shape,
                )
            _, reward, terminated, truncated, _ = env.step(
                {"torque": np.zeros((args.num_env, 1), dtype=np.float32)}
            )
            if step_index == 0 or (step_index + 1) % 50 == 0:
                logger.info(
                    "Parallel render rollout step",
                    event="task_env.parallel_render.step",
                    step=step_index + 1,
                    mode=args.mode,
                    parallel_render_num=render_num,
                    mean_reward=float(np.mean(reward)),
                    terminated=int(np.count_nonzero(terminated)),
                    truncated=int(np.count_nonzero(truncated)),
                )
            if np.any(np.logical_or(terminated, truncated)):
                env.reset(seed=args.seed + step_index + 1)
            if args.sleep:
                time.sleep(args.sleep)
    finally:
        env.close()
    logger.success(
        "P2-S18b manual parallel render completed",
        env_id=args.env_id,
        mode=args.mode,
        backend=args.backend,
        render_backend=args.render_backend,
        num_env=args.num_env,
        parallel_render_num=render_num,
        steps=args.steps,
    )


if __name__ == "__main__":
    main()
