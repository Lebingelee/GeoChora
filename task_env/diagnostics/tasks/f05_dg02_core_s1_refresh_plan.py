"""Freeze a new DG02 Core S1 plan against the current Core/provider source pair."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


CORE = Path(__file__).resolve().parents[3]
MAINT = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
WINDOW = MAINT / "f05_diagnostic_goal02/window_002"
PROVIDER = MAINT / "f05_geophys_provider/GeoPhys"
LOCK = MAINT / "shared_native_execution.lock"
PREVIOUS_PLAN = WINDOW / "core_s1_002.plan.json"
LEDGER = WINDOW / "run_ledger.json"
BASE_PROGRESS = WINDOW.parent / "window_001/goal_progress.json"
PROVIDER_COMMIT = "a9e4c4850bd225f5929e74831ac282b18ff517ce"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _row(path: Path) -> dict[str, str]:
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": _sha(path)}


def build(suffix: str) -> tuple[dict, Path]:
    if not suffix.isdigit() or len(suffix) != 3:
        raise ValueError("S1 refresh suffix must contain three digits")
    previous_plan_path = PREVIOUS_PLAN.resolve(strict=True)
    previous_sidecar = previous_plan_path.with_suffix(previous_plan_path.suffix + ".sha256")
    previous_hash = _sha(previous_plan_path)
    if previous_sidecar.read_text(encoding="ascii").split()[0] != previous_hash:
        raise ValueError("prior S1 plan sidecar hash mismatch")
    previous = json.loads(previous_plan_path.read_text(encoding="utf-8"))
    previous_run = Path(previous["output"]["run_dir"]).resolve(strict=True)
    prior_worker = previous_run / "worker_receipt.json"
    prior_supervisor = previous_run / "supervisor_receipt.json"
    worker_receipt, supervisor_receipt = json.loads(prior_worker.read_text()), json.loads(prior_supervisor.read_text())
    if (worker_receipt.get("status") != "PASS_CORE_S1_SELECTED_REFERENCE_RUNTIME_RECORDER_H5"
            or worker_receipt.get("physics_steps_attempted") != 80
            or worker_receipt.get("physics_steps_completed") != 80
            or supervisor_receipt.get("exit_code") != 0
            or not supervisor_receipt.get("process_group_gone_before_release")
            or not supervisor_receipt.get("lock_released_after_process_group_exit")):
        raise ValueError("prior window-002 S1 evidence is not a clean 80-step pass")

    core_branch, core_head = _git(CORE, "branch", "--show-current"), _git(CORE, "rev-parse", "HEAD")
    provider_branch, provider_head = _git(PROVIDER, "branch", "--show-current"), _git(PROVIDER, "rev-parse", "HEAD")
    if core_branch != "develop-full" or provider_branch != "codex/phase-ii-01-f05-geophys":
        raise RuntimeError("S1 Core/provider branch identity differs from the frozen owner map")
    if provider_head != PROVIDER_COMMIT or _git(PROVIDER, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("S1 requires the clean committed USD joint-passive provider repair")

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    base_progress = json.loads(BASE_PROGRESS.read_text(encoding="utf-8"))
    lock_path = LOCK.resolve(strict=True)
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("shared native lock is occupied before S1 freeze") from error
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    available = next(
        int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    if available < 6 * 1024**3:
        raise RuntimeError("S1 MemAvailable preflight is below the frozen 6 GiB floor")

    run_id = f"DG02_WINDOW002_CORE_SELECTED_REFERENCE_S1_{suffix}"
    run_dir = WINDOW / f"core_s1_{suffix}"
    plan_path = WINDOW / f"core_s1_{suffix}.plan.json"
    if run_dir.exists() or plan_path.exists() or plan_path.with_suffix(plan_path.suffix + ".sha256").exists():
        raise FileExistsError("S1 output already exists; preserve it and allocate a new suffix")

    plan = json.loads(json.dumps(previous))
    plan["run_id"] = run_id
    plan["created_utc"] = datetime.now(timezone.utc).isoformat()
    plan["hypothesis"] = (
        "The committed USD source-joint passive adapter feeds the original authored damping/armature "
        "through Core SelectedReferenceEnv to the current GeoPhys provider while the existing S1 "
        "schedule, public observation, and Generic H5 behavior remain intact. This remains bounded S1 evidence."
    )
    plan["input_identity"].update({
        "core_branch": core_branch,
        "core_input_head": core_head,
        "provider_branch": provider_branch,
        "provider_input_head": provider_head,
    })
    source = plan["source"]
    source["prior_window002_s1_plan"] = _row(previous_plan_path)
    source["prior_window002_s1_worker_receipt"] = _row(prior_worker)
    source["prior_window002_s1_supervisor_receipt"] = _row(prior_supervisor)
    candidate_dir = WINDOW / "core_candidate_static_004"
    for name, path in {
        "core_candidate_plan": WINDOW / "core_candidate_static_004.plan.json",
        "core_candidate_plan_sidecar": WINDOW / "core_candidate_static_004.plan.json.sha256",
        "core_candidate_receipt": candidate_dir / "core_source_receipt.json",
        "core_candidate_worker_receipt": candidate_dir / "worker_receipt.json",
        "core_candidate_supervisor_receipt": candidate_dir / "supervisor_receipt.json",
    }.items():
        source[name] = _row(path)
    source["provider_joint_passive_repair"] = {
        "commit": PROVIDER_COMMIT,
        "provider_branch": provider_branch,
        "provider_head": provider_head,
    }
    plan["output"].update({
        "run_dir": str(run_dir.resolve()),
        "episode_h5_paths": [str((run_dir / f"episode_{index:03d}.h5").resolve()) for index in (1, 2)],
        "native_receipt": str((run_dir / "supervisor_receipt.json").resolve()),
        "worker_receipt": str((run_dir / "worker_receipt.json").resolve()),
        "step_counter": str((run_dir / "step_counter.json").resolve()),
    })

    totals, carry = ledger["new_window_totals"], ledger["carry_in"]
    limits = plan["limits"]
    limits.update({
        "native_starts_before": int(base_progress["native"]["geophys_starts"]) + int(totals["geophys_starts"]),
        "physics_steps_before": int(carry["geophys_attempted_steps"]) + int(totals["geophys_completed_steps"]),
        "physics_steps_completed_before": int(carry["geophys_completed_steps"]) + int(totals["geophys_completed_steps"]),
        "probe_physics_steps_before": int(carry["nonformal_probe_attempted_steps_upper_bound"]) + int(totals["geophys_nonformal_attempted_steps"]),
        "cumulative_geophys_wall_s_before": float(carry["geophys_wall_s_conservative"]) + float(totals["native_wall_s"]) + float(totals["provider_free_wall_s"]),
        "physics_steps_reserved": 80,
        "planned_native_starts": 1,
        "shared_native_lock_available_at_freeze": True,
        "preflight_mem_available_bytes": available,
    })

    code_paths = {Path(row["path"]).resolve(strict=True) for row in plan["code"]["tracked_inputs"]}
    code_paths.update({
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_s1_refresh_plan.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_plan.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_worker.py",
        PROVIDER / "src/scene/_rigid_usd_joint.py",
        PROVIDER / "src/scene/usd_scene_ir.py",
        PROVIDER / "test/verification/scene/test_usd_joint_lowering.py",
    })
    plan["code"]["tracked_inputs"] = [_row(path) for path in sorted(code_paths, key=str)]
    plan["runtime_environment_sha256"] = hashlib.sha256(json.dumps(
        plan["runtime"], sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    plan["limits"]["shared_native_lock_path"] = str(lock_path)
    plan["limits"]["start_native_mem_available_bytes_min"] = 6 * 1024**3
    return plan, plan_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suffix", required=True)
    args = parser.parse_args()
    plan, path = build(args.suffix)
    raw = (json.dumps(plan, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")
    print(json.dumps({"run_id": plan["run_id"], "plan_path": str(path),
                      "plan_sha256": hashlib.sha256(raw).hexdigest(),
                      "physics_steps_reserved": plan["limits"]["physics_steps_reserved"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
