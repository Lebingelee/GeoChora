"""Capture and validate a site-bound camera across reset and one step."""

from __future__ import annotations

import argparse

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import BACKEND_CHOICES
    from task_env.script.camera._common import run_camera
else:
    from .._bootstrap import BACKEND_CHOICES
    from ._common import run_camera


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto")
    args = parser.parse_args()
    run_camera(requested_backend=args.backend, bound=True)


if __name__ == "__main__":
    main()
