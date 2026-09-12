"""Compatibility exports for the Stage 14 trajectory scripts.

The implementation lives in ``task_env.script.trajectory``.  Stage 11
imports the two public task-plan helpers from this module, so they remain
available without keeping a second recorder implementation here.
"""

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from task_env.script.trajectory._task_plans import (
        _build_plan,
        _nut_assembly_config,
        _pick_cube_config,
    )
else:
    from .trajectory._task_plans import (
        _build_plan,
        _nut_assembly_config,
        _pick_cube_config,
    )

from task_env.utils.rotation import look_at_quat_wxyz as _look_at_quat


def main() -> None:
    if __package__ in (None, ""):
        from task_env.script.trajectory.record import main as record_main
    else:
        from .trajectory.record import main as record_main

    record_main()


__all__ = [
    "_build_plan",
    "_look_at_quat",
    "_nut_assembly_config",
    "_pick_cube_config",
    "main",
]


if __name__ == "__main__":
    main()
