"""Freeze the bounded 100-interval DG02 Core tracking diagnostic."""

from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


CORE = Path(__file__).resolve().parents[3]
MAINT = Path("/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001")
WINDOW = MAINT / "f05_diagnostic_goal02/window_001"
HOST = WINDOW / "host_g5_001"
PROVIDER = MAINT / "f05_geophys_provider/GeoPhys"
BASE_PLAN = HOST / "n2_formal_019.plan.json"
OLD_CANDIDATE = HOST / "core_candidate_029/plan.json"
PROGRESS = WINDOW / "goal_progress.json"
PACKAGE = MAINT / "sol_f05_dg02_001"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _head(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


def _branch(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "branch", "--show-current"], check=True,
                          capture_output=True, text=True).stdout.strip()


def build_plan(output_dir: Path) -> tuple[dict, Path, Path]:
    output_dir = output_dir.resolve()
    plan_path = output_dir.with_name(output_dir.name + ".plan.json")
    sidecar = output_dir.with_name(output_dir.name + ".plan.json.sha256")
    candidate_dir = output_dir.with_name(output_dir.name + "_candidate_static")
    paths = (output_dir, plan_path, sidecar, candidate_dir)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"tracking-probe output already exists: {[str(p) for p in paths if p.exists()]}")

    from task_env.diagnostics.tasks.f05_dg02_core_n2_plan import (
        _build_formal_oracle,
        _row,
        _tracked_inputs,
    )
    from task_env.diagnostics.tasks.f05_dg02_core_source_receipt import build_candidate_receipt

    base = _json(BASE_PLAN)
    candidate = _json(OLD_CANDIDATE)
    core_head, provider_head = _head(CORE), _head(PROVIDER)
    core_branch, provider_branch = _branch(CORE), _branch(PROVIDER)
    if core_branch != "develop-full" or provider_branch != "codex/phase-ii-01-f05-geophys":
        raise RuntimeError("tracking-probe checkout branches differ from the frozen owner map")
    if _json(PROGRESS)["native"]["geophys_steps"] + 500 > 18000:
        raise RuntimeError("500-step probe does not fit the frozen cumulative probe budget")
    if _json(PROGRESS)["native"]["geophys_steps"] + 500 > 66000:
        raise RuntimeError("500-step probe does not fit the frozen GeoPhys total budget")
    lock_path = Path(base["limits"]["shared_native_lock_path"]).resolve()
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("shared native lock is occupied during probe freeze") from error
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    mem_available = next(
        int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    budget = _json(PACKAGE / "execution_budget.json")
    resource = budget["resource_envelope"]
    if mem_available < int(resource["start_native_mem_available_bytes_min"]):
        raise RuntimeError("tracking-probe native memory start gate is not satisfied")

    for runtime_path in base["runtime"]["pythonpath"]:
        resolved = str(Path(runtime_path).resolve(strict=True))
        if resolved not in sys.path:
            sys.path.insert(0, resolved)

    candidate["run_id"] = "DG02_G5_CORE_TRACKING_PROBE_CANDIDATE_ADMISSION_001"
    candidate["created_utc"] = datetime.now(timezone.utc).isoformat()
    candidate["input_identity"].update({
        "core_branch": core_branch,
        "core_input_head": core_head,
        "core_worktree": str(CORE.resolve()),
        "provider_branch": provider_branch,
        "provider_input_head": provider_head,
        "provider_worktree": str(PROVIDER.resolve()),
    })
    candidate["source"]["candidate_horizon"] = 100
    candidate["code"]["tracked_inputs"] = _tracked_inputs(
        *candidate["code"]["tracked_inputs"],
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_tracking_probe_plan.py"),
         "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_tracking_probe_plan.py")},
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py"),
         "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py")},
    )
    candidate_receipt_path = candidate_dir / "core_source_receipt.json"
    candidate["output"] = {
        "run_dir": str(candidate_dir.resolve()),
        "candidate_receipt": str(candidate_receipt_path.resolve()),
        "native_operations_forbidden": True,
    }
    candidate_path = candidate_dir / "plan.json"
    candidate_sidecar = candidate_dir / "plan.sha256"
    _atomic_json(candidate_path, candidate)
    candidate_hash = _sha(candidate_path)
    candidate_sidecar.write_text(candidate_hash + "\n", encoding="ascii")
    static_receipt, built_candidate = build_candidate_receipt(candidate, include_candidate=True)
    static_receipt.update({"plan_path": str(candidate_path.resolve()), "plan_sha256": candidate_hash})
    if (static_receipt["checks"]["solver_initialized"]
            or static_receipt["checks"]["solver_constructed"]
            or static_receipt["checks"]["physics_steps"] != 0):
        raise RuntimeError("static tracking candidate unexpectedly initialized or stepped a solver")
    _atomic_json(candidate_receipt_path, static_receipt)
    candidate_admission = {
        "schema_version": "f05-dg02-static-candidate-admission-v1",
        "run_id": candidate["run_id"],
        "candidate_plan_sha256": candidate_hash,
        "candidate_receipt_path": str(candidate_receipt_path.resolve()),
        "candidate_receipt_sha256": _sha(candidate_receipt_path),
        "solver_initialized": False,
        "solver_constructed": False,
        "physics_steps": 0,
        "public_model_counts": static_receipt["public_model_counts"],
        "provider_head": provider_head,
        "core_head": core_head,
        "status": "PASS_STATIC_SOURCE_BOUND_CANDIDATE_ADMISSION",
    }
    admission_path = candidate_dir / "static_admission_receipt.json"
    _atomic_json(admission_path, candidate_admission)

    from task_env.diagnostics.tasks.f05_dg02_core_n2_plan import (
        _build_formal_oracle,
        _tracked_inputs,
    )
    physical = _json(PACKAGE / "original_physical_oracle.json")
    control = _json(PACKAGE / "control_oracles.json")
    oracle = _build_formal_oracle(built_candidate, physical, control, static_receipt["action_config"])
    oracle.update({
        "episode_count": 1,
        "control_intervals_per_episode": 100,
        "horizon": 100,
        "schedule": [row for row in oracle["schedule"] if int(row["stop"]) <= 100],
    })
    if [row["phase"] for row in oracle["schedule"]] != ["unloaded_home_hold", "unloaded_point"]:
        raise RuntimeError("tracking probe schedule is not the exact first two frozen phases")

    progress = _json(PROGRESS)
    run_dir = output_dir
    tracked_inputs = _tracked_inputs(
        *base["code"]["tracked_inputs"],
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_tracking_probe_plan.py"),
         "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_tracking_probe_plan.py")},
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_tracking_probe_reader.py"),
         "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_tracking_probe_reader.py")},
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py"),
         "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py")},
    )
    plan = dict(base)
    plan.update({
        "run_id": "DG02_G5_CORE_TRACKING_PROBE_001",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": (
            "actual Core SelectedReferenceEnv PositionServoV1; source-bound GeoPhys/USD; "
            "bounded tracking probe, not a formal cell or qualification"
        ),
        "hypothesis": (
            "With the unchanged DG01 ActionConfig, source, and tracking thresholds, the existing "
            "achieved-state DLS method avoids accumulated unachieved joint-target windup through "
            "the actual Core Position route for the frozen home-hold and point-hold phases."
        ),
        "input_identity": {
            **base["input_identity"],
            "core_branch": core_branch,
            "core_input_head": core_head,
            "provider_branch": provider_branch,
            "provider_input_head": provider_head,
        },
        "source": {
            **base["source"],
            "candidate_horizon": 100,
            "core_candidate_plan": _row(candidate_path),
            "core_candidate_plan_sidecar": _row(candidate_sidecar),
            "core_candidate_receipt": _row(candidate_receipt_path),
            "candidate_static_admission_receipt": _row(admission_path),
        },
        "oracle": oracle,
        "code": {"tracked_inputs": tracked_inputs},
        "limits": {
            **base["limits"],
            "native_starts_before": int(progress["native"]["geophys_starts"]),
            "planned_native_starts": 1,
            "physics_steps_before": int(progress["native"]["geophys_steps"]),
            "physics_steps_reserved": 500,
            "physics_steps_completed_before": int(progress["native"]["geophys_steps_completed"]),
            "per_probe_steps_max": int(budget["per_probe_steps_max"]),
            "worker_wall_s_max": int(budget["per_probe_worker_wall_s_max"]),
            "probe_physics_steps_max": int(budget["probe_physics_steps_cumulative_max"]),
            "cumulative_geophys_wall_s_before": float(progress["native"]["geophys_wall_s"]),
            "preflight_mem_available_bytes": mem_available,
            "shared_native_lock_available_at_freeze": True,
        },
        "method": {
            **base["method"],
            "entry": "build_versioned_position_candidate -> SelectedReferenceEnv.reset -> RuntimeSession.materialize -> structured Position request -> Generic H5 v3 -> independent tracking-probe cold reader",
            "episode_lifecycle": "one actual Candidate Env object, one 100-interval episode spanning the exact frozen home and point phases; the planned final horizon truncation is recorded",
            "native_step_accounting": "charge 5 physics steps before every Core control interval; increment completed only after the public transition returns; 500 total",
        },
        "output": {
            "run_dir": str(run_dir),
            "episode_h5_paths": [str((run_dir / "episode_001.h5").resolve())],
            "native_receipt": str((run_dir / "supervisor_receipt.json").resolve()),
            "step_counter": str((run_dir / "step_counter.json").resolve()),
            "worker_receipt": str((run_dir / "worker_receipt.json").resolve()),
            "tracking_probe_reader_receipt": str((run_dir / "tracking_probe_reader_receipt.json").resolve()),
            "worker_script": str((CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py").resolve()),
            "independent_reader_script": str((CORE / "task_env/diagnostics/tasks/f05_dg02_core_tracking_probe_reader.py").resolve()),
        },
    })
    if int(plan["limits"]["physics_steps_before"]) + 500 > int(plan["limits"]["probe_physics_steps_max"]):
        raise RuntimeError("tracking probe exceeds frozen cumulative probe limit")
    if int(plan["limits"]["cumulative_geophys_wall_s_before"]) + int(plan["limits"]["worker_wall_s_max"]) > int(plan["limits"]["geophys_native_wall_s_max"]):
        raise RuntimeError("tracking probe cannot fit the frozen cumulative GeoPhys wall budget")
    _atomic_json(plan_path, plan)
    sidecar.write_text(_sha(plan_path) + "\n", encoding="ascii")
    return plan, plan_path, sidecar


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else HOST / "controller_tracking_probe_001"
    plan, path, sidecar = build_plan(target)
    print(json.dumps({"run_id": plan["run_id"], "plan": str(path), "plan_sha256": _sha(path),
                      "sidecar": str(sidecar), "steps_reserved": plan["limits"]["physics_steps_reserved"],
                      "candidate_receipt_sha256": plan["source"]["core_candidate_receipt"]["sha256"],
                      "status": "FROZEN_TRACKING_PROBE_READY"}, indent=2, sort_keys=True))
