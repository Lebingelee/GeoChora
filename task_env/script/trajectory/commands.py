"""Dispatch selected-task recording and provider-independent H5 utilities."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _retired(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _merge(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Merge current TaskEnv trajectory collections offline.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from task_env.trajectory.processing import merge_trajectory_collections

    paths = sorted(args.input_dir.glob("*.h5"))
    if not paths:
        parser.error(f"no H5 files found in {args.input_dir}")
    merge_trajectory_collections(paths, args.output)
    print(f"merged {len(paths)} trajectory files into {args.output}")
    return 0


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and (arguments[0] == "--historical-grouped" or arguments[0] == "collect"):
        return _retired(
            "The grouped Stage 14/Phase I collector is retired. Use "
            "`python -m task_env.script.trajectory.record --env-id <selected-uid> "
            "--provider <geophys|mujoco> --output <fresh.h5>` for one selected expert route; "
            "restore the exact source ref listed for task_env.script.trajectory.commands "
            "in docs/module/task_env/p2_0_s4_5_a_source_recovery.json for historical grouped collection."
        )
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", nargs="?", choices=("record", "replay", "convert", "merge"))
        parser.print_help()
        return 0

    command, rest = arguments[0], arguments[1:]
    if command == "record":
        from .record import main as record_main

        return record_main(rest)
    if command == "replay":
        from .replay import main as replay_main

        return replay_main(rest)
    if command == "convert":
        from .convert import main as convert_main

        return convert_main(rest)
    if command == "merge":
        return _merge(rest)
    return _retired(f"Unknown trajectory command {command!r}; run with --help for supported routes.")
