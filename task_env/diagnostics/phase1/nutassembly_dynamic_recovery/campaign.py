"""Run ordered all-rate T0/G0/T1 candidate gates and preserve each iteration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from ..nutassembly_nominal.common import RATE_NAMES


ROOT = Path("workspace/qualification/phase1/p1_8_nutassembly_dynamic_recovery")
PROFILE_PATH = Path("task_env/tasks/nut_assembly/profiles/nutassembly-nominal-v2.json")
PROVIDERS = ("geophys", "mujoco")
PROBES = ("T0", "G0", "T1")


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _append(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")


def _summary(probe, report):
    if report is None:
        return {"probe": probe, "pass": False, "failure_boundary": "worker_report_missing"}
    if probe == "T0":
        return {
            "probe": probe,
            "pass": bool(report.get("pass")),
            "failure_boundary": report.get("failure_boundary"),
            "error_summary": report.get("error_summary"),
            "endpoint_count": len(report.get("endpoints", [])),
            "endpoint_pass_count": sum(bool(row.get("pass")) for row in report.get("endpoints", [])),
            "report_path": report.get("_path"),
        }
    return {
        "probe": probe,
        "pass": bool(report.get("pass")),
        "failure_boundary": report.get("failure_boundary"),
        "authorization_branch": (report.get("close_authorization") or {}).get("authorization_branch"),
        "authorization_time_s": (report.get("close_authorization") or {}).get("authorization_time_s"),
        "verify_lift_pass": report.get("verify_lift_pass"),
        "max_capture_position_drift_m": report.get("max_capture_position_drift_m"),
        "max_capture_rotation_drift_rad": report.get("max_capture_rotation_drift_rad"),
        "endpoint_count": len(report.get("endpoints", [])),
        "report_path": report.get("_path"),
    }


def _run_cell(probe, rate, provider, iteration, attempt, profile_path, dynamic_profile_path, root):
    rate_label = rate.lower().replace("na-", "")
    category = {"T0": "unloaded", "G0": "gripper", "T1": "loaded"}[probe]
    report_path = root / "tracking" / category / provider / rate_label / f"candidate-{iteration:02d}" / "report.json"
    if int(attempt) > 1:
        report_path = report_path.parent / f"attempt-{int(attempt):02d}" / "report.json"
    command = [
        sys.executable,
        "-m", "task_env.diagnostics.phase1.nutassembly_dynamic_recovery.tracking_worker",
        "--root", str(root), "--probe", probe, "--rate", rate, "--provider", provider,
        "--candidate", str(iteration), "--profile-path", str(profile_path),
        "--dynamic-profile", str(dynamic_profile_path), "--attempt", str(attempt),
    ]
    environment = os.environ.copy()
    module_root = Path(__file__).resolve().parents[4]
    provider_paths = [str(module_root / "GeoPhys"), str(module_root / "GeoPhys" / "src")]
    existing_paths = [value for value in environment.get("PYTHONPATH", "").split(os.pathsep) if value]
    environment["PYTHONPATH"] = os.pathsep.join(provider_paths + existing_paths)
    environment.setdefault("GEOPHYS_TAICHI_BACKEND", "taichi_forge")
    environment["PYTHONUNBUFFERED"] = "1"
    process = subprocess.run(command, cwd=module_root, env=environment,
                             capture_output=True, text=True, check=False)
    if process.stdout:
        print(process.stdout.rstrip(), flush=True)
    if process.stderr:
        print(process.stderr.rstrip(), file=sys.stderr, flush=True)
    report = None
    if report_path.exists():
        report = json.loads(report_path.read_text())
        report["_path"] = str(report_path)
    elif process.returncode != 0:
        report = {"pass": False, "failure_boundary": "worker_start_or_context", "error": process.stderr[-5000:]}
    return report


def run_candidate(iteration, profile_path=PROFILE_PATH, dynamic_profile_path=None, root=ROOT, attempt=1):
    if not 1 <= int(iteration) <= 12:
        raise ValueError("R4 candidate iteration must be between 1 and 12")
    root = Path(root)
    profile_path = Path(profile_path)
    dynamic_profile_path = Path(dynamic_profile_path or
                                root / "optimization" / "candidate_profiles" / f"candidate-{iteration:02d}.yaml")
    candidate = yaml.safe_load(dynamic_profile_path.read_text())
    if candidate.get("candidate_id") != f"R4-C{iteration:02d}":
        raise ValueError("candidate file ID does not match the requested iteration")
    log = root / "optimization" / "optimization_log.jsonl"
    snapshot = {
        "controller_profile": candidate["controller"],
        "gripper_dynamic_profile": candidate["gripper"],
        "planner_profile": candidate["planner"],
        "candidate_profile_path": str(dynamic_profile_path),
        "candidate_profile_sha256": hashlib.sha256(dynamic_profile_path.read_bytes()).hexdigest(),
        "reason_for_change": candidate.get("reason", "candidate hypothesis not supplied"),
        "T0_result": None,
        "G0_result": None,
        "T1_result": None,
        "full_task_result": None,
    }
    _append(log, {"event": "candidate_begin", "iteration": iteration,
                  "attempt": int(attempt), "recorded_at_utc": _utc(), **snapshot})
    results = {}
    for probe in PROBES:
        cells = {}
        for rate in RATE_NAMES:
            for provider in PROVIDERS:
                key = f"{provider}/{rate}"
                print(f"[{candidate['candidate_id']}] {probe} {key} starting", flush=True)
                report = _run_cell(probe, rate, provider, iteration, attempt, profile_path,
                                   dynamic_profile_path, root)
                cells[key] = _summary(probe, report)
        gate_pass = bool(len(cells) == len(RATE_NAMES) * len(PROVIDERS)
                         and all(cell.get("pass") for cell in cells.values()))
        results[probe] = {"gate": "PASS" if gate_pass else "FAIL", "cells": cells}
        field = f"{probe}_result"
        snapshot[field] = results[probe]
        _append(log, {"event": "candidate_probe_complete", "iteration": iteration,
                      "attempt": int(attempt), "probe": probe, "recorded_at_utc": _utc(), **snapshot})
        if not gate_pass:
            break
    snapshot.update(results)
    snapshot["candidate_decision"] = "T0_G0_T1_PASS" if all(
        results.get(probe, {}).get("gate") == "PASS" for probe in PROBES
    ) else "PROBE_GATE_FAILED_OR_NOT_RUN"
    _append(log, {"event": "candidate_complete", "iteration": iteration,
                  "attempt": int(attempt), "recorded_at_utc": _utc(), **snapshot})
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--profile-path", type=Path, default=PROFILE_PATH)
    parser.add_argument("--dynamic-profile", type=Path)
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    result = run_candidate(args.iteration, args.profile_path, args.dynamic_profile, args.root, args.attempt)
    print(json.dumps({"iteration": args.iteration, "candidate_decision": result["candidate_decision"],
                      "attempt": args.attempt,
                      "gates": {key: (result.get(key + "_result") or {}).get("gate", "NOT_RUN")
                                for key in PROBES}}, indent=2), flush=True)
    return 0 if result["candidate_decision"] == "T0_G0_T1_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
