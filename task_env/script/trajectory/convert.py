"""Convert a Panda/controller H5 trajectory using the public offline API."""

from __future__ import annotations

import argparse
from pathlib import Path

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import get_logger, write_json
else:
    from .._bootstrap import get_logger, write_json


def main() -> None:
    from task_env.trajectory.processing import inspect_trajectory, transcode_actions, validate_trajectory

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-mode", choices=("absolute_joint", "absolute_pose", "delta_pose"), required=True)
    parser.add_argument("--target-reference", choices=("world", "base", "ee"))
    parser.add_argument("--mode", choices=("strict", "interpolation"), default="strict")
    args = parser.parse_args()
    logger = get_logger("task-env-stage14-trajectory-convert")
    before = inspect_trajectory(args.input)
    validate_trajectory(args.input)
    output = transcode_actions(
        args.input,
        args.output,
        target_mode=args.target_mode,
        target_reference=args.target_reference,
        mode=args.mode,
    )
    after = inspect_trajectory(output)
    summary = {
        "input": str(args.input),
        "output": str(output),
        "target_mode": args.target_mode,
        "target_reference": args.target_reference,
        "mode": args.mode,
        "input_inspection": before,
        "output_inspection": after,
    }
    write_json(output.with_suffix(".json"), summary)
    logger.success("Stage 14 Panda trajectory conversion completed", output=str(output))


if __name__ == "__main__":
    main()
