"""Create a TaskEnv with a readable inline public config and step it."""

from __future__ import annotations

import argparse

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import BACKEND_CHOICES
    from task_env.script.env._common import inline_config, run_single
else:
    from .._bootstrap import BACKEND_CHOICES
    from ._common import inline_config, run_single


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", default="pick-cube-v1")
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto")
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--seed", type=int, default=31)
    args = parser.parse_args()
    if args.steps < 1 or args.horizon < args.steps:
        parser.error("--steps and --horizon must be positive, with horizon >= steps")
    config_backend = "cuda" if args.backend == "auto" else args.backend
    run_single(
        env_id=args.env_id,
        requested_backend=args.backend,
        config=inline_config(args.env_id, config_backend, args.horizon),
        steps=args.steps,
        seed=args.seed,
        summary_name="single_inline",
    )


if __name__ == "__main__":
    main()
