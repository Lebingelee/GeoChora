"""Record one selected task-owned expert route to canonical H5 and verify it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from examples._common import (
    RunTimeout,
    bounded_process,
    bootstrap_imports,
    identity_summary,
    load_recording_summary,
    run_expert,
)


ENV_IDS = ("pick-cube-p16-reference-v1", "nut-assembly-outcome-reference-v1")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", choices=ENV_IDS, required=True)
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--horizon", type=int, default=6000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--time-limit-s", type=int, default=420)
    parser.add_argument(
        "--address-space-limit-mb", "--memory-limit-mb", dest="memory_limit_mb",
        type=int, default=8192,
        help="Linux per-process RLIMIT_AS virtual address-space cap; not RSS or process-tree memory",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.horizon <= 6000:
        parser.error("--horizon must be in [1, 6000]")
    seed = 31 if args.env_id == ENV_IDS[0] else 19
    if args.seed is not None:
        seed = args.seed
    if args.env_id == ENV_IDS[1] and seed != 19:
        parser.error("the selected NutAssembly NA-S0 recipe requires seed 19")

    bootstrap_imports()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    env = None
    recording_started = False
    episode = None
    identity = None
    budget = None
    verification = None
    recording = None
    error = None
    status = "ERROR"
    try:
        with bounded_process(args.memory_limit_mb, args.time_limit_s) as budget:
            from task_env import make_env

            env = make_env(args.env_id, config={"provider": args.provider, "backend": "cpu", "horizon": args.horizon})
            _, reset_info = env.reset(seed=seed)
            # Recording begins with the measured reset boundary, before the first expert action.
            env.start_recording(output)
            recording_started = True
            episode = run_expert(env, seed=seed, horizon=args.horizon, already_reset=True,
                                 initial_info=reset_info)
            identity = identity_summary(env, provider=args.provider)
            status = episode["status"]
    except RunTimeout as exc:
        error = {"type": "TIMEOUT", "message": str(exc)}
        status = "TIMEOUT"
        if env is not None:
            identity = identity_summary(env, provider=args.provider)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        status = "ERROR"
        if env is not None:
            identity = identity_summary(env, provider=args.provider)
    finally:
        if env is not None:
            if recording_started:
                try:
                    verification = env.finish_recording(
                        (episode or {}).get("failure_reason") or status.lower()
                    )
                except Exception as exc:
                    error = {"type": type(exc).__name__, "message": f"recording finalization failed: {exc}"}
                    status = "ERROR"
            env.close()

    if output.exists():
        try:
            recording = load_recording_summary(output)
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": f"recording validation failed: {exc}"}
            status = "ERROR"
    else:
        recording = {"status": "NOT_WRITTEN", "path": str(output)}

    roundtrip = bool((verification or {}).get("byte_exact", (verification or {}).get("logical_mapping_exact", False)))
    counts_valid = bool(recording and recording.get("t_plus_one_valid"))
    if status == "PASS" and (not roundtrip or not counts_valid):
        status = "ERROR"
        error = {"type": "RecordingValidationError", "message": "roundtrip or T+1 boundary validation failed"}
    report = {
        "status": status,
        "env_id": args.env_id,
        "provider": args.provider,
        "backend": "cpu",
        "seed": seed,
        "capability_intersection": "selected task-owned expert, scalar CPU; H5 storage check is not D0 replay",
        "episode": episode,
        "identity": identity,
        "recording": recording,
        "verification": verification,
        "roundtrip": "PASS" if roundtrip else "FAIL_OR_NOT_FINALIZED",
        "resource_budget": budget,
        "output": str(output),
        "error": error,
    }
    print(json.dumps(report, sort_keys=True, default=str))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
