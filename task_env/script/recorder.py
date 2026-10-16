"""Compatibility command for selected task-owned expert recording only."""


def main(argv=None) -> int:
    if __package__ in (None, ""):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from task_env.script.trajectory.record import main as record_main
    else:
        from .trajectory.record import main as record_main

    return record_main(argv)


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
