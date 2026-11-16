"""Run the guarded NutAssembly Outcome V1 Solution through public actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from examples._common import RunTimeout, bounded_process, bootstrap_imports, identity_summary, run_caller_solution


ENV_ID = "nut-assembly-outcome-reference-v1"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True)
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--horizon", type=int, default=6000)
    parser.add_argument("--time-limit-s", type=int, default=420)
    parser.add_argument(
        "--address-space-limit-mb", "--memory-limit-mb", dest="memory_limit_mb",
        type=int, default=8192,
        help="Linux per-process RLIMIT_AS virtual address-space cap; not RSS or process-tree memory",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.horizon <= 6000:
        parser.error("--horizon must be in [1, 6000]")

    bootstrap_imports()
    env = None
    report = {"status": "ERROR", "env_id": ENV_ID, "provider": args.provider,
              "capability_intersection": "selected NutAssembly Outcome V1, caller-owned Solution, scalar CPU",
              "close_attempted": False, "close_succeeded": False}
    try:
        with bounded_process(args.memory_limit_mb, args.time_limit_s) as budget:
            from task_env import make_env
            from task_env.tasks.nut_assembly.task import build_outcome_solution

            env = make_env(ENV_ID, config={"execution": {"physics_provider": args.provider, "physics_backend": "cpu"}, "episode": {"horizon": args.horizon}})
            solution = build_outcome_solution(provider=args.provider)
            obs, info = env.reset(seed=args.seed)
            solution.reset(obs, info, env.metadata)
            episode = run_caller_solution(env, solution, obs, info, horizon=args.horizon)
            report.update(episode=episode, identity=identity_summary(env, provider=args.provider), resource_budget=budget)
            report["status"] = episode["status"]
    except RunTimeout as exc:
        report.update(status="TIMEOUT", timeout=str(exc))
        if env is not None:
            report["identity"] = identity_summary(env, provider=args.provider)
    except Exception as exc:
        report.update(status="ERROR", error=f"{type(exc).__name__}: {exc}")
        if env is not None:
            report["identity"] = identity_summary(env, provider=args.provider)
    finally:
        if env is not None:
            report["close_attempted"] = True
            try:
                env.close()
                report["close_succeeded"] = True
            except Exception as exc:
                report["close_error"] = f"{type(exc).__name__}: {exc}"
                report["status"] = "ERROR"
    print(json.dumps(report, sort_keys=True, default=str))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
