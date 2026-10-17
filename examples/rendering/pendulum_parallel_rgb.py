"""Render a single Pendulum batch frame through the existing GeoPhys route.

The bounded example uses the current local merged-scene batch runtime and
GeoPhys rasterizer. It does not exercise Flora or renderer interoperability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from examples._common import RunTimeout, bootstrap_imports, bounded_process


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=48)
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
        "capability_intersection": "Pendulum / GeoPhys CPU / merged_scene batch / rasterizer RGB",
        "width": args.width,
        "height": args.height,
        "steps": 1,
    }
    try:
        with bounded_process(args.address_space_limit_mb, args.time_limit_s) as budget:
            from task_env.script.render_parallel import main as render_parallel

            render_result = render_parallel(
                [
                    "--env-id", "pendulum-v1",
                    "--num-env", "1",
                    "--parallel-render-num", "1",
                    "--mode", "rgb_array",
                    "--backend", "cpu",
                    "--render-backend", "rasterizer",
                    "--width", str(args.width),
                    "--height", str(args.height),
                    "--columns", "1",
                    "--steps", "1",
                    "--seed", "73",
                    "--sleep", "0",
                ]
            )
            if render_result not in (None, 0):
                raise RuntimeError(f"the existing parallel-render CLI returned {render_result}")
            result.update(status="PASS_BOUNDED_RENDER_SMOKE_NOT_QUALIFICATION", resource_budget=budget)
    except RunTimeout as exc:
        result.update(status="TIMEOUT", error=str(exc))
    except SystemExit as exc:
        result.update(status="ERROR", error=f"parallel-render CLI exited with code {exc.code}")
    except Exception as exc:
        result.update(status="ERROR", error=f"{type(exc).__name__}: {exc}")
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS_BOUNDED_RENDER_SMOKE_NOT_QUALIFICATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
