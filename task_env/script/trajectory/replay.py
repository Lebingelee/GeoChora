"""Replay a Panda trajectory through the public TaskEnv action boundary."""

from __future__ import annotations

import argparse
from pathlib import Path

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import BACKEND_CHOICES, get_logger, stage14_output, write_json
else:
    from .._bootstrap import BACKEND_CHOICES, get_logger, stage14_output, write_json


def main(argv=None) -> None:
    from task_env.trajectory import replay_and_verify_collection, replay_and_verify_universal_action

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="cpu")
    parser.add_argument("--require-exact", action="store_true")
    parser.add_argument('--selected-reexecute', action='store_true', help='Same-source selected expert comparison; --output must be a fresh H5 path')
    parser.add_argument('--historical', action='store_true',
                        help='Explicit recovery-only legacy H5 replay; never selected-route acceptance')
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.selected_reexecute:
        if args.historical or args.output is None or args.require_exact:
            parser.error('selected comparison requires fresh --output and excludes historical flags')
        from task_env.trajectory.reference_replay import reexecute_selected
        import json
        print(json.dumps(reexecute_selected(args.trajectory, output=args.output)))
        return
    if not args.historical:
        parser.error('legacy H5 replay requires --historical; selected H5 validation uses canonical.streaming.validate_streaming, not D0 reconstruction')
    logger = get_logger("task-env-stage14-trajectory-replay")
    backend = None if args.backend == "auto" else args.backend
    import h5py

    with h5py.File(args.trajectory, "r") as root:
        grouped = str(root.attrs.get("container_type", "")) == "trajectory_collection"
    report = (
        replay_and_verify_collection(args.trajectory, backend=backend, require_exact=args.require_exact)
        if grouped
        else replay_and_verify_universal_action(
            args.trajectory, backend=backend, require_exact=args.require_exact
        )
    )
    output = args.output or stage14_output("trajectories", "replay.json")
    write_json(output, {"trajectory": str(args.trajectory), "report": report})
    logger.success("Stage 14 trajectory replay completed", trajectory=str(args.trajectory), output=str(output))


if __name__ == "__main__":
    main()
