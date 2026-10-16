"""Run the guarded selected NutAssembly solution through ``step_expert()``."""

from __future__ import annotations

import argparse

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from task_env.script._bootstrap import BACKEND_CHOICES
    from task_env.script.trajectory.planning._common import run_solution
else:
    from ..._bootstrap import BACKEND_CHOICES
    from ._common import run_solution


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto")
    parser.add_argument('--provider', choices=('geophys','mujoco'), default='geophys')
    parser.add_argument("--horizon", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=19)
    args = parser.parse_args()
    if args.horizon < 1:
        parser.error("--horizon must be positive")
    run_solution(
        env_id='nut-assembly-outcome-reference-v1',
        requested_backend=args.backend,
        provider=args.provider,
        horizon=args.horizon,
        seed=args.seed,
        summary_name="nut_assembly",
    )


if __name__ == "__main__":
    main()
