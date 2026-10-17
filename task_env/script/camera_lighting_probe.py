"""Retired historical PickCube lighting probe."""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    print(
        "task_env.script.camera_lighting_probe is retired: it used the historical "
        "pick-cube-v1 task and accessed renderer internals. Use only the public "
        "Renderer/Camera contracts on a separately supported task-provider route. "
        "No Physics × Flora capability is implied. See "
        "docs/module/task_env/p2_0_s4_5_b_source_recovery.json for source recovery.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
