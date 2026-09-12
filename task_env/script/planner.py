"""Compatibility entry point for the PickCube planning example."""

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from task_env.script.trajectory.planning.pick_cube import main
else:
    from .trajectory.planning.pick_cube import main


if __name__ == "__main__":
    main()


__all__ = ["main"]
