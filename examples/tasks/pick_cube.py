"""Run and record the selected built-in PickCube expert through public make_env."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from examples._common import (
    RunTimeout, bounded_process, bootstrap_imports, identity_summary,
    load_recording_summary, run_expert,
)


ENV_ID = "pick-cube-p16-reference-v1"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True,
                        help="real CPU provider; Isaac uses the versioned Harness native-worker route")
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--horizon", type=int, default=1000)
    parser.add_argument("--controller-profile", choices=("r1", "r3_continuous_v1"),
                        default="r3_continuous_v1")
    parser.add_argument("--recording", type=Path,
                        help="canonical H5 output; default workspace/examples/pick_cube/<provider>-<seed>.h5")
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
    recording = (args.recording.expanduser().resolve() if args.recording else
                 (_REPOSITORY_ROOT / "workspace/examples/pick_cube" / f"{args.provider}-{args.seed}.h5").resolve())
    report = {"status": "ERROR", "runtime_valid": False, "task_outcome": "UNRESOLVED",
              "env_id": ENV_ID, "provider": args.provider, "backend": "cpu", "device": "cpu",
              "controller_profile": args.controller_profile, "seed": args.seed,
              "horizon": args.horizon, "recording_path": str(recording),
              "capability_intersection": (
                  f"selected PickCube P1.6, scalar CPU, existing task-owned "
                  f"{args.controller_profile}/ReadinessSolution"
              )}
    construction_succeeded = reset_succeeded = finalize_succeeded = close_succeeded = False
    episode = None
    try:
        with bounded_process(args.memory_limit_mb, args.time_limit_s) as budget:
            from task_env import make_env

            env = make_env(ENV_ID, config={
                "provider": args.provider, "backend": "cpu", "horizon": args.horizon,
                "controller_profile": args.controller_profile,
            })
            construction_succeeded = True
            _, reset_info = env.reset(seed=args.seed)
            reset_succeeded = True
            recording.parent.mkdir(parents=True, exist_ok=True)
            env.start_recording(recording)
            episode = run_expert(env, seed=args.seed, horizon=args.horizon,
                                 already_reset=True, initial_info=reset_info)
            reason = episode.get("failure_reason") or (
                "task_success" if episode.get("task_success") else "task_or_expert_incomplete"
            )
            if episode.get("truncated") and episode.get("transitions") == args.horizon:
                reason = "horizon_reached"
            report["recording_finalize"] = env.finish_recording(reason)
            finalize_succeeded = True
            report.update(episode=episode, identity=identity_summary(env, provider=args.provider),
                          controller_identity=env.controller.identity,
                          solution_identity=env.solution.identity,
                          provider_materialization_id=env.session.provider_materialization_id,
                          resource_budget=budget)
    except RunTimeout as exc:
        report.update(status="INVALID", error_type="TIMEOUT", timeout=str(exc))
        if env is not None:
            report["identity"] = identity_summary(env, provider=args.provider)
    except Exception as exc:
        report.update(status="INVALID", error=f"{type(exc).__name__}: {exc}")
        if env is not None:
            report["identity"] = identity_summary(env, provider=args.provider)
    finally:
        if env is not None:
            try:
                env.close()
                close_succeeded = True
            except Exception as exc:
                report["close_error"] = f"{type(exc).__name__}: {exc}"
    recording_summary = None
    if recording.is_file():
        try:
            recording_summary = load_recording_summary(recording)
            from task_env.trajectory.canonical.h5 import load
            trajectory = load(recording)
            report["planned_action_count"] = sum(item.planned_action for item in trajectory.transitions)
            report["recording"] = {
                "path": str(recording),
                "sha256": __import__("hashlib").sha256(recording.read_bytes()).hexdigest(),
                "bytes": recording.stat().st_size,
                **recording_summary,
            }
        except Exception as exc:
            report["readback_error"] = f"{type(exc).__name__}: {exc}"
    runtime_valid = bool(
        construction_succeeded and reset_succeeded and finalize_succeeded and close_succeeded
        and recording_summary and recording_summary.get("t_plus_one_valid")
        and report.get("planned_action_count", 0) > 0
        and not report.get("error") and not report.get("close_error")
    )
    report["runtime_valid"] = runtime_valid
    report["task_outcome"] = (
        "SOLVED" if episode and episode.get("task_success") and episode.get("expert_complete")
        else "TASK_OR_EXPERT_FAILURE_REPORTED" if runtime_valid
        else "UNRESOLVED_RUNTIME_FAILURE"
    )
    report["status"] = "RUNTIME_VALID" if runtime_valid else report.get("status", "INVALID")
    print(json.dumps(report, sort_keys=True, default=str))
    return 0 if runtime_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
