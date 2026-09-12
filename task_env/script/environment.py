"""Compatibility entry point for :mod:`task_env.script.env.single_inline`."""

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from task_env.script.env.single_inline import main
else:
    from .env.single_inline import main


if __name__ == "__main__":
    main()


__all__ = ["main"]
