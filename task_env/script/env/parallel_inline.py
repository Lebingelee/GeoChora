"""Drive a remote homogeneous Pendulum batch with bounded random actions."""

from __future__ import annotations

import argparse

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import BACKEND_CHOICES
    from task_env.script.env._common import run_parallel
else:
    from .._bootstrap import BACKEND_CHOICES
    from ._common import run_parallel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", default="pendulum-v1")
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto")
    parser.add_argument("--num-env", type=int, default=4)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--seed", type=int, default=73)
    args = parser.parse_args()
    if args.num_env < 1 or args.steps < 1:
        parser.error("--num-env and --steps must be positive")
    run_parallel(
        env_id=args.env_id,
        requested_backend=args.backend,
        env_config={"base_seed": args.seed},
        num_env=args.num_env,
        steps=args.steps,
        seed=args.seed,
        summary_name="parallel_inline",
    )


if __name__ == "__main__":
    main()
