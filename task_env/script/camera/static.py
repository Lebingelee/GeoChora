"""Retired historical PickCube camera-observation example."""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    print(
        "task_env.script.camera.static is retired because it constructed the historical "
        "pick-cube-v1 task. CameraSpec remains available to Task Artifacts whose "
        "observation contract declares cameras; selected reference task camera "
        "acceptance is not established. See "
        "docs/module/task_env/p2_0_s4_5_b_source_recovery.json for source recovery.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
