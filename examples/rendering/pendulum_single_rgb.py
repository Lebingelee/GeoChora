"""Render one current Pendulum frame through the scalar public TaskEnv API.

This exercises Pendulum / GeoPhys CPU / scalar TaskEnv / GeoPhys rasterizer.
It does not exercise Flora or Physics x Renderer interoperability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from examples._common import RunTimeout, bootstrap_imports, bounded_process


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--height", type=int, default=24)
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument("--time-limit-s", type=int, default=120)
    parser.add_argument(
        "--address-space-limit-mb",
        type=int,
        default=8192,
        help="Linux per-process RLIMIT_AS cap; not RSS or process-tree memory",
    )
    args = parser.parse_args(argv)
    if args.width < 1 or args.height < 1:
        parser.error("width and height must be positive")

    bootstrap_imports()
    result = {
        "status": "ERROR",
        "qualification": "NOT_ASSESSED",
        "capability_intersection": "Pendulum / GeoPhys CPU / scalar TaskEnv / rasterizer RGB",
        "provider": "geophys",
        "backend": "cpu",
        "width": args.width,
        "height": args.height,
    }
    env = None
    try:
        with bounded_process(args.address_space_limit_mb, args.time_limit_s) as budget:
            from task_env import make_env

            env = make_env(
                "pendulum-v1",
                config={
                    "runtime": {"backend": "cpu", "broadphase": "n2", "prewarm": False},
                    "render": {"backend": "rasterizer", "width": args.width, "height": args.height},
                    "episode": {"horizon": 2},
                },
                render_mode="rgb_array",
            )
            observation, info = env.reset(seed=args.seed)
            frame = env.render()
            if (
                not isinstance(frame, np.ndarray)
                or frame.shape != (args.height, args.width, 3)
                or frame.dtype != np.dtype("float32")
                or not np.isfinite(frame).all()
            ):
                raise RuntimeError("scalar rasterizer did not return a finite HWC float32 frame")
            observation, reward, terminated, truncated, info = env.step(
                {"torque": np.zeros(1, dtype=np.float32)}
            )
            result.update(
                status="PASS_BOUNDED_RENDER_SMOKE_NOT_QUALIFICATION",
                frame_shape=list(frame.shape),
                frame_dtype=str(frame.dtype),
                task_success=bool(info.get("task_success", False)),
                expert_complete=None,
                reward=float(reward),
                terminated=bool(terminated),
                truncated=bool(truncated),
                reset_observation_valid=env.observation_space.contains(observation),
                resource_budget=budget,
            )
    except RunTimeout as exc:
        result.update(status="TIMEOUT", error=str(exc))
    except Exception as exc:
        result.update(status="ERROR", error=f"{type(exc).__name__}: {exc}")
    finally:
        if env is not None:
            env.close()
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS_BOUNDED_RENDER_SMOKE_NOT_QUALIFICATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
