"""Freeze a CPU-supervised DG02 Core USD candidate build without stepping."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone


CORE = Path(__file__).resolve().parents[3]
MAINT = Path("/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001")
WINDOW = MAINT / "f05_diagnostic_goal02/window_002"
PROVIDER = MAINT / "f05_geophys_provider/GeoPhys"
BASE_CANDIDATE = MAINT / "f05_diagnostic_goal02/window_001/host_g3_001/core_candidate_010/plan.json"
BASE_SUPERVISOR_PLAN = MAINT / "f05_diagnostic_goal02/window_001/host_g3_001/core_s1_007.plan.json"
BUDGET_PATH = MAINT / "sol_f05_dg02_002_pickcube_r3_001/execution_budget.json"
PACKAGE_HEAD = "d808ba0228d7c9299e43e7ff89fe4d3687ea5f71"
PACKAGE_PROVIDER_HEAD = "f4d3b3bb21882bac5ca007e657f5d6709a6189b8"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _tracked_paths(candidate: dict) -> list[Path]:
    paths = {Path(row["path"]).resolve(strict=True)
             for row in candidate["code"]["tracked_inputs"]}
    paths.update({
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_plan.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_worker.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_source_receipt.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py",
        CORE / "task_env/controllers/canonical/__init__.py",
        CORE / "task_env/controllers/canonical/contracts.py",
        CORE / "task_env/controllers/canonical/controller.py",
        CORE / "task_env/controllers/canonical/position_profile.py",
        CORE / "task_env/controllers/canonical/production_r2.py",
        CORE / "task_env/controllers/canonical/production_r3.py",
        CORE / "task_env/controllers/canonical/kinematics.py",
        CORE / "task_env/tasks/pick_cube/task.py",
        CORE / "task_env/tasks/nut_assembly/config.yaml",
        CORE / "task_env/tasks/position_candidate/builder.py",
        CORE / "task_env/tasks/position_candidate/source.py",
        CORE / "task_env/tasks/reference_env.py",
        CORE / "task_env/runtime/sessions/api.py",
        CORE / "task_env/runtime/sessions/control.py",
        CORE / "task_env/runtime/sessions/geophys_source.py",
        CORE / "task_env/runtime/sessions/source.py",
    })
    return sorted((path.resolve(strict=True) for path in paths), key=str)


def build_plan(output_dir: Path) -> tuple[dict, Path, Path]:
    output_dir = output_dir.resolve()
    suffix = output_dir.name.rsplit("_", 1)[-1]
    if not suffix.isdigit():
        raise ValueError("supervised candidate output directory must end in a numeric attempt suffix")
    run_id = f"DG02_WINDOW002_CORE_CANDIDATE_STATIC_{suffix}"
    plan_path = output_dir.with_suffix(".plan.json")
    sidecar_path = output_dir.with_suffix(".plan.json.sha256")
    receipt_path = output_dir / "core_source_receipt.json"
    worker_receipt_path = output_dir / "worker_receipt.json"
    supervisor_receipt_path = output_dir / "supervisor_receipt.json"
    if any(path.exists() for path in (
        output_dir, plan_path, sidecar_path, receipt_path,
        worker_receipt_path, supervisor_receipt_path,
    )):
        raise FileExistsError("refusing to replace an existing supervised candidate output")

    core_head, provider_head = _git(CORE, "rev-parse", "HEAD"), _git(PROVIDER, "rev-parse", "HEAD")
    core_branch, provider_branch = _git(CORE, "branch", "--show-current"), _git(PROVIDER, "branch", "--show-current")
    if (core_head, core_branch, provider_head, provider_branch) != (
        PACKAGE_HEAD, "develop-full", PACKAGE_PROVIDER_HEAD,
        "codex/phase-ii-01-f05-geophys",
    ):
        raise RuntimeError("Core/provider checkout differs from the frozen package input")
    if _git(PROVIDER, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("isolated GeoPhys provider checkout is not clean")

    candidate = _json(BASE_CANDIDATE)
    supervisor_base = _json(BASE_SUPERVISOR_PLAN)
    budget = _json(BUDGET_PATH)
    window_limits = budget["window_limits"]
    resource = budget["resource_envelope"]
    lock_path = Path(resource["shared_native_lock_path"]).resolve()
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("shared native lock is occupied during candidate freeze") from error
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    if available < int(resource["start_native_mem_available_bytes_min"]):
        raise RuntimeError("native MemAvailable start gate is not satisfied")

    tracked = _tracked_paths(candidate)
    candidate.update({
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "supervised source-bound Core USD/Position candidate build; zero solver steps; not qualification",
        "input_identity": {
            **candidate["input_identity"],
            "core_branch": core_branch,
            "core_input_head": core_head,
            "core_worktree": str(CORE.resolve()),
            "provider_branch": provider_branch,
            "provider_input_head": provider_head,
            "provider_worktree": str(PROVIDER.resolve()),
        },
        "code": {"tracked_inputs": [
            {"path": str(path), "sha256": _sha(path)} for path in tracked
        ]},
        "limits": {
            "native_starts_before": 0,
            "planned_native_starts": 1,
            "physics_steps_before": 0,
            "physics_steps_reserved": 0,
            "physics_steps_completed_before": 0,
            "worker_wall_s_max": int(window_limits["modelcompile_wall_s_max"]),
            "native_process_group_sampled_rss_bytes_max": int(resource["native_process_group_sampled_rss_bytes_max"]),
            "start_native_mem_available_bytes_min": int(resource["start_native_mem_available_bytes_min"]),
            "abort_mem_available_bytes_below": int(resource["abort_mem_available_bytes_below"]),
            "cpu_threads_max": int(resource["cpu_threads_max"]),
            "sample_interval_s": float(resource["sample_interval_s_max"]),
            "term_grace_s": int(resource["term_grace_s"]),
            "native_log_bytes_max": int(window_limits["native_log_bytes_max"]),
            "shared_native_lock_path": str(lock_path),
            "preflight_mem_available_bytes": available,
        },
        "output": {
            "run_dir": str(output_dir),
            "worker_script": str((CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_worker.py").resolve()),
            "worker_receipt": str(worker_receipt_path),
            "candidate_receipt": str(receipt_path),
        },
        "schema_version": "f05-dg02-n1-public-consumer-plan-v1",
    })
    candidate["source"]["candidate_horizon"] = 12
    candidate["source"]["candidate_static_horizon"] = 12
    candidate["runtime"] = dict(supervisor_base["runtime"])
    candidate["runtime"]["pythonpath"] = list(dict.fromkeys([
        str(CORE.resolve()), *candidate["runtime"]["pythonpath"],
    ]))
    candidate["runtime_environment_sha256"] = hashlib.sha256(json.dumps(
        candidate["runtime"], sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    return candidate, plan_path, sidecar_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    plan, plan_path, sidecar_path = build_plan(args.output_dir)
    _atomic_json(plan_path, plan)
    plan_hash = _sha(plan_path)
    sidecar_path.write_text(plan_hash + "\n", encoding="ascii")
    print(json.dumps({
        "plan_path": str(plan_path),
        "plan_sha256": plan_hash,
        "run_id": plan["run_id"],
        "native_start_reserved": plan["limits"]["planned_native_starts"],
        "physics_steps_reserved": plan["limits"]["physics_steps_reserved"],
        "status": "FROZEN_READY_FOR_SUPERVISED_STATIC_CANDIDATE_BUILD",
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
