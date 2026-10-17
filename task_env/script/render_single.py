"""Retired historical single-task rendering entry point."""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    print(
        "task_env.script.render_single is retired: it depended on historical task IDs. "
        "The supported current Pendulum route is documented in "
        "examples/rendering/pendulum_single_rgb.py; the bounded batch route is "
        "examples/rendering/pendulum_parallel_rgb.py. No selected manipulation "
        "task × renderer route is declared by this command. See "
        "docs/module/task_env/p2_0_s4_5_b_source_recovery.json for source recovery.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
