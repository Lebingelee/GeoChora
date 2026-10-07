"""Pilot-first, final-checkpoint Flow rollout gate for long-training variants."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


PILOT_SEEDS = (1000, 1010)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pilot_gate_passes(reports) -> bool:
    by_seed = {int(row["seed"]): row for row in reports if row.get("task_success") is not None}
    return all(seed in by_seed and bool(by_seed[seed]["task_success"]) for seed in PILOT_SEEDS)


def run_episode(root: Path, seed: int) -> dict:
    output_dir = root / "rollout" / f"seed{seed}"
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite rollout evidence for seed {seed}: {output_dir}")
    output_dir.mkdir(parents=True)
    command = [sys.executable, "-m", "task_env.diagnostics.phase1.policy_search.flow100_rollout",
               "--seed", str(seed), "--output", str(output_dir / "report.json"),
               "--variant-root", str(root)]
    (output_dir / "command.txt").write_text(" ".join(command) + "\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = "GeoPhys/src:."
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with (output_dir / "stdout.log").open("w") as stdout, (output_dir / "stderr.log").open("w") as stderr:
        proc = subprocess.run(command, cwd=Path.cwd(), env=env, stdout=stdout, stderr=stderr, text=True)
    report_path = output_dir / "report.json"
    result = {"seed": seed, "returncode": int(proc.returncode), "report_path": str(report_path)}
    if report_path.is_file():
        report = json.loads(report_path.read_text())
        result.update({"task_success": bool(report["task_success"]),
                       "max_cube_lift_m": float(report["max_cube_lift_m"]),
                       "control_frames": int(report["control_frames"]),
                       "checkpoint_sha256": report["checkpoint_sha256"],
                       "checkpoint_role": report["checkpoint_role"]})
    else:
        result.update({"task_success": None, "execution_error": f"rollout exited {proc.returncode} without a report"})
    return result


def run(root: Path) -> dict:
    root = Path(root)
    spec_path = root / "rollout_spec.yaml"
    lock_path = root / "rollout_spec_lock.json"
    lock = json.loads(lock_path.read_text())
    if sha256(spec_path) != lock["sha256"]:
        raise ValueError("rollout specification lock mismatch")
    spec = yaml.safe_load(spec_path.read_text())
    cohort = tuple(map(int, spec["cohort_seeds"]))
    pilot = tuple(map(int, spec["pilot_seeds"]))
    if pilot != PILOT_SEEDS or cohort[:len(pilot)] != pilot:
        raise ValueError("pilot-first seed order differs from the frozen 1000/1010 contract")
    if spec.get("checkpoint_role") != "final" or lock.get("checkpoint_role") != "final":
        raise ValueError("long-training pilot must evaluate the predeclared final checkpoint")
    destination = root / "rollout" / "pilot_gate_report.json"
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite pilot gate Evidence: {destination}")

    rows = []
    for seed in pilot:
        print(f"starting frozen pilot seed={seed}", flush=True)
        rows.append(run_episode(root, seed))
        print(f"completed frozen pilot seed={seed} success={rows[-1].get('task_success')}", flush=True)

    gate = pilot_gate_passes(rows)
    full_cohort_started = False
    if gate:
        full_cohort_started = True
        for seed in cohort[len(pilot):]:
            print(f"starting gated cohort seed={seed}", flush=True)
            rows.append(run_episode(root, seed))
            print(f"completed gated cohort seed={seed} success={rows[-1].get('task_success')}", flush=True)

    completed = [row for row in rows if row.get("task_success") is not None]
    result = {
        "schema": "p1_6-flow-long-training-pilot-gate-v0",
        "variant": spec["variant"],
        "rollout_spec_sha256": lock["sha256"],
        "checkpoint_role": spec["checkpoint_role"],
        "checkpoint_sha256": spec["checkpoint_sha256"],
        "pilot_seeds": list(pilot),
        "pilot_results": rows[:len(pilot)],
        "pilot_success_count": sum(bool(row.get("task_success")) for row in rows[:len(pilot)]),
        "pilot_gate_pass": gate,
        "full_cohort_started": full_cohort_started,
        "cohort_seeds": list(cohort),
        "episodes": rows,
        "completed_successes": sum(bool(row.get("task_success")) for row in completed),
        "completed_episode_count": len(completed),
        "full_cohort_complete": full_cohort_started and len(completed) == len(cohort),
        "scope": {"diagnostic_only": True, "provider_qualification_claim": False},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.variant_root), sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
