"""Retired Phase I Stage 11 collection entry point.

Historical Stage 11 source collection and replay are available from the exact
recovery ref recorded in ``docs/module/task_env/p2_0_s4_5_a_source_recovery.json``.
For this entry point, that is the S4 base commit ``0ff2d846a36c7014d2b40a530f52d99e64266ff9``;
use immutable ``v1.0.0`` only for entries whose manifest says so. Current
examples use selected task-owned UIDs via ``task_env.make_env`` and
``task_env.script.trajectory.record``.
"""

import sys


def main(argv=None) -> int:
    del argv
    print(
        "Stage 11 Phase I collection is retired from active develop; "
        "restore the exact recovery ref from the S4.5-A manifest in a separate checkout.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
