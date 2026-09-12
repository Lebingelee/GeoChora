"""User-facing Go2 MuJoCo sim-to-sim probe with optional passive viewer.

The independent oracle implementation lives under ``task_env.diagnostics``;
this small entry point is the only MuJoCo visualization command exposed in
``script/rl``.  It never imports GeoPhys task code, so the trace remains an
independent sim-to-sim reference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from task_env.diagnostics.go2.mujoco_oracle import Go2MujocoOracle, XML_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--action", type=float, nargs=12, default=[0.0] * 12)
    parser.add_argument("--platform-box", action="store_true")
    parser.add_argument("--viewer", action="store_true", help="open mujoco.viewer.launch_passive")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if int(args.steps) < 1:
        parser.error("--steps must be positive")

    oracle = Go2MujocoOracle(platform_box=bool(args.platform_box))
    oracle.reset()
    action = np.asarray(args.action, dtype=np.float32)
    rows = []
    if args.viewer:
        try:
            import mujoco.viewer
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("--viewer requires the mujoco viewer dependencies") from exc
        with mujoco.viewer.launch_passive(oracle.model, oracle.data) as viewer:
            for _ in range(int(args.steps)):
                rows.append(oracle.step(action))
                viewer.sync()
    else:
        rows = [oracle.step(action) for _ in range(int(args.steps))]

    payload = {
        "schema": "task-env-go2-mujoco-sim2sim-v1",
        "source": str(XML_PATH),
        "steps": rows,
        "platform_box": bool(args.platform_box),
        "viewer": bool(args.viewer),
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
