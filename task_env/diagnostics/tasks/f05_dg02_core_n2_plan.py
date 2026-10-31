"""Freeze the actual-Core DG02 N2 run after source and resource preflight."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


CORE = Path(__file__).resolve().parents[3]
PROVIDER = Path(
    "/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_geophys_provider/GeoPhys"
)
MAINT = Path("/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001")
PACKAGE = MAINT / "sol_f05_dg02_001"
WINDOW = MAINT / "f05_diagnostic_goal02/window_001"
OUT = WINDOW / "host_g5_001"
PROGRESS = WINDOW / "goal_progress.json"
BUDGET_PATH = PACKAGE / "execution_budget.json"
ORACLES_PATH = PACKAGE / "control_oracles.json"
PHYSICAL_PATH = PACKAGE / "original_physical_oracle.json"
OLD_S1_PLAN = WINDOW / "host_g3_001/core_s1_007.plan.json"
OLD_CANDIDATE_PLAN = WINDOW / "host_g3_001/core_candidate_010/plan.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _row(path: Path) -> dict:
    resolved = path.resolve(strict=True)
    return {"path": str(resolved), "sha256": _sha(resolved)}


def _tracked_inputs(*rows: dict) -> list[dict]:
    all_paths = {Path(row["path"]).resolve(strict=True) for row in rows}
    all_paths.update({
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_plan.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_s1_probe.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_source_receipt.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py",
    })
    return [
        {"path": str(path.resolve(strict=True)), "sha256": _sha(path.resolve(strict=True))}
        for path in sorted(all_paths, key=str)
    ]


def _head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _branch(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _assert_lock_free(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("shared native lock is already occupied") from error
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def _model_pose_mapping(pose) -> dict:
    return {
        "position_m": [float(value) for value in pose.position],
        "quaternion_wxyz": [float(value) for value in pose.quaternion_wxyz],
    }


def _build_formal_oracle(candidate, physical: dict, control: dict, action_config: dict) -> dict:
    home_all = physical["physical_acceptance"]["home_joint_position_rad"]
    arm_order = [f"joint{index}" for index in range(1, 8)]
    home = {name: float(home_all[name]) for name in arm_order}
    schedule = []
    for phase in control["schedule"]:
        target = {
            name: home[name] + float(phase["arm_offsets_rad"][index])
            for index, name in enumerate(arm_order)
        }
        pose = candidate.env.controller.model.pose([target[name] for name in arm_order])
        schedule.append({
            "start": int(phase["start"]),
            "stop": int(phase["stop"]),
            "phase": str(phase["phase"]),
            "arm_offsets_rad": [float(value) for value in phase["arm_offsets_rad"]],
            "arm_target_position_rad": target,
            "opening_m": float(phase["opening_m"]),
            "source_fk_method": "PandaPositionServoProfileV1.model.pose(source MJCF Menagerie kinematics)",
            "source_fk_hand_pose_world": _model_pose_mapping(pose),
        })
    runtime_source = candidate.env.value["source"]
    source_bodies = dict(runtime_source.bodies)
    contact_body_roles = {}
    for role, prim_name in (("free_cube", "free_cube"), ("support", "support")):
        matches = [
            {"semantic_id": str(semantic), "usd_prim_path": str(path)}
            for semantic, path in source_bodies.items()
            if str(path).rstrip("/").rsplit("/", 1)[-1] == prim_name
        ]
        if len(matches) != 1:
            raise RuntimeError(f"formal N2 source must bind exactly one {role} body, found {matches}")
        contact_body_roles[role] = matches[0]
    return {
        "control_intervals_per_episode": int(control["control_intervals_per_episode"]),
        "episode_count": int(control["episodes_per_env"]),
        "control_substeps": int(control["physics_steps_per_interval"]),
        "physics_dt_s": float(control["physics_dt_s"]),
        "outer_control_dt_s": 0.01,
        "horizon": 300,
        "home_joint_position_rad": home,
        "finger_joint_home_position_m": {
            "finger_joint1": float(home_all["finger_joint1"]),
            "finger_joint2": float(home_all["finger_joint2"]),
        },
        "joint_order": arm_order + ["finger_joint1", "finger_joint2"],
        "schedule": schedule,
        "tracking": control["tracking"],
        "original_physical_acceptance": physical["physical_acceptance"],
        "controller_action_config": action_config,
        "required_public_model_counts": {
            "n_actuators": 8, "n_dof": 15, "n_equalities": 1,
            "n_qpos": 16, "n_tendons": 1,
        },
        "reset_physics_steps_expected": int(control["reset_physics_steps_expected"]),
        "recording": "two Generic H5 v3 files, each T=300 and T+1=301",
        "expected_episode_end": {
            "end_reason": "horizon_reached",
            "terminated": False,
            "truncated": True,
            "bootstrap_allowed": True,
            "policy": "observe and retain the single planned final-horizon truncation; any earlier termination/truncation is a failure",
        },
        "task_readout": control["Task_predicate"],
        "contact_body_roles": contact_body_roles,
        "contact_observation": {
            "schema_version": "f05-dg02-public-contact-observation-v1",
            "sample_at_each_control_boundary": True,
            "expected_reset_episode_index": "one-based provider contact-observation episode",
            "required_pair": "free_cube/support from the exact source body map above",
            "minimum_contact_samples": 1,
            "required_impulse_evidence": "known solved manifold with finite, nonnegative normal impulse and a nonzero cumulative impulse",
        },
        "not_a_trajectory_equivalence_claim": True,
        "qualification_granted": False,
    }


def build_plan() -> tuple[dict, dict]:
    attempt_index = 1
    while True:
        attempt_tag = f"{attempt_index:03d}"
        run_dir = OUT / f"n2_formal_{attempt_tag}"
        candidate_dir = OUT / f"core_candidate_{10 + attempt_index:03d}"
        plan_path = OUT / f"n2_formal_{attempt_tag}.plan.json"
        if not any(path.exists() for path in (run_dir, candidate_dir, plan_path)):
            break
        attempt_index += 1
    run_id = f"DG02_G5_FORMAL_ACTUAL_CORE_SELECTED_REFERENCE_N2_{attempt_tag}"
    core_head, provider_head = _head(CORE), _head(PROVIDER)
    core_branch, provider_branch = _branch(CORE), _branch(PROVIDER)
    if core_branch != "develop-full" or provider_branch != "codex/phase-ii-01-f05-geophys":
        raise RuntimeError("N2 checkout branch differs from the frozen Core/provider owner map")
    provider_status = subprocess.run(
        ["git", "-C", str(PROVIDER), "status", "--porcelain=v1", "--untracked-files=all"],
        check=True, capture_output=True, text=True,
    ).stdout
    if provider_status.strip():
        raise RuntimeError("provider checkout is not clean at N2 freeze")
    if not CORE.joinpath("docs/maintenance/20261030_runtime_route_diagnostic_handoff.md").is_file():
        raise RuntimeError("protected maintenance handoff document is missing")

    progress = _json(PROGRESS)
    budget = _json(BUDGET_PATH)
    control = _json(ORACLES_PATH)
    physical = _json(PHYSICAL_PATH)
    old_s1 = _json(OLD_S1_PLAN)
    candidate_plan = _json(OLD_CANDIDATE_PLAN)
    candidate_plan_path = candidate_dir / "plan.json"
    candidate_sidecar_path = candidate_dir / "plan.sha256"
    candidate_receipt_path = candidate_dir / "core_source_receipt.json"
    candidate_admission_path = candidate_dir / "static_admission_receipt.json"

    # Freeze a current static admission plan against the already accepted USD source.
    candidate_plan["run_id"] = "DG02_G5_CORE_SOURCE_BOUND_CANDIDATE_ADMISSION_011"
    candidate_plan["created_utc"] = datetime.now(timezone.utc).isoformat()
    candidate_plan["input_identity"].update({
        "core_branch": core_branch,
        "core_input_head": core_head,
        "core_worktree": str(CORE.resolve()),
        "provider_branch": provider_branch,
        "provider_input_head": provider_head,
        "provider_worktree": str(PROVIDER.resolve()),
    })
    candidate_plan["code"]["tracked_inputs"] = _tracked_inputs(*candidate_plan["code"]["tracked_inputs"])
    candidate_plan["output"] = {
        "run_dir": str(candidate_dir.resolve()),
        "candidate_receipt": str(candidate_receipt_path.resolve()),
        "native_operations_forbidden": True,
    }
    _atomic_json(candidate_plan_path, candidate_plan)
    candidate_plan_hash = _sha(candidate_plan_path)
    candidate_sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_sidecar_path.write_text(candidate_plan_hash + "\n", encoding="ascii")

    from task_env.diagnostics.tasks.f05_dg02_core_source_receipt import build_candidate_receipt

    static_receipt, candidate = build_candidate_receipt(candidate_plan, include_candidate=True)
    static_receipt["plan_path"] = str(candidate_plan_path.resolve())
    static_receipt["plan_sha256"] = candidate_plan_hash
    if (static_receipt["checks"]["solver_initialized"]
            or static_receipt["checks"]["solver_constructed"]
            or static_receipt["checks"]["physics_steps"] != 0):
        raise RuntimeError("static Core candidate admission unexpectedly initialized or stepped a solver")
    if static_receipt["public_model_counts"] != {
            "n_qpos": 16, "n_dof": 15, "n_actuators": 8, "n_tendons": 1,
            "n_equalities": 1, "n_geoms": static_receipt["public_model_counts"]["n_geoms"]}:
        raise RuntimeError("source-bound static candidate changed required 9DOF/8-actuator model counts")
    _atomic_json(candidate_receipt_path, static_receipt)
    candidate_static_receipt = {
        "schema_version": "f05-dg02-static-candidate-admission-v1",
        "run_id": candidate_plan["run_id"],
        "candidate_plan_sha256": candidate_plan_hash,
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
    _atomic_json(candidate_admission_path, candidate_static_receipt)

    original_source = dict(old_s1["source"])
    prior_candidate_supervisor = original_source.pop("core_candidate_supervisor_receipt", None)
    original_source.update({
        "core_candidate_plan": _row(candidate_plan_path),
        "core_candidate_plan_sidecar": _row(candidate_sidecar_path),
        "core_candidate_receipt": _row(candidate_receipt_path),
        "candidate_static_admission_receipt": _row(candidate_admission_path),
    })
    if prior_candidate_supervisor is not None:
        original_source["prior_core_candidate_010_supervisor_receipt"] = prior_candidate_supervisor

    runtime = dict(old_s1["runtime"])
    runtime_hash = hashlib.sha256(json.dumps(
        runtime, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    code_rows = _tracked_inputs(
        *old_s1["code"]["tracked_inputs"],
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_plan.py"), "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_plan.py")},
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py"), "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py")},
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py"), "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py")},
    )
    schedule_oracle = _build_formal_oracle(
        candidate, physical, control, static_receipt["action_config"],
    )
    budget_limits = budget["resource_envelope"]
    lock_path = Path(budget_limits["shared_native_lock_path"]).resolve()
    _assert_lock_free(lock_path)
    mem_available = int(next(
        int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    ))
    if mem_available < int(budget_limits["start_native_mem_available_bytes_min"]):
        raise RuntimeError("formal N2 frozen native start MemAvailable gate is not satisfied")
    if run_dir.exists() or candidate_dir.joinpath("worker_receipt.json").exists():
        raise FileExistsError("formal N2 output appeared during plan generation")

    limits = {
        "native_starts_before": int(progress["native"]["geophys_starts"]),
        "planned_native_starts": 1,
        "physics_steps_before": int(progress["native"]["geophys_steps"]),
        "physics_steps_reserved": 3000,
        "physics_steps_completed_before": int(progress["native"]["geophys_steps_completed"]),
        "global_physics_steps_max": int(budget["goal_native_physics_steps_cumulative_max"]),
        "geophys_physics_steps_max": int(budget["geophys_physics_steps_cumulative_max"]),
        "probe_physics_steps_max": int(budget["probe_physics_steps_cumulative_max"]),
        "per_probe_steps_max": int(budget["per_probe_steps_max"]),
        "per_formal_worker_step_max": int(budget["per_formal_worker_steps_max"]),
        "per_formal_worker_wall_s_max": int(budget["per_formal_worker_wall_s_max"]),
        "worker_wall_s_max": int(budget["per_formal_worker_wall_s_max"]),
        "cumulative_geophys_wall_s_before": float(progress["native"]["geophys_wall_s"]),
        "geophys_native_wall_s_max": int(budget["geophys_native_wall_s_cumulative_max"]),
        "global_native_wall_s_max": int(budget["goal_native_wall_s_cumulative_max"]),
        "native_process_group_sampled_rss_bytes_max": int(budget_limits["native_process_group_sampled_rss_bytes_max"]),
        "start_native_mem_available_bytes_min": int(budget_limits["start_native_mem_available_bytes_min"]),
        "abort_mem_available_bytes_below": int(budget_limits["abort_mem_available_bytes_below"]),
        "cpu_threads_max": int(budget_limits["cpu_threads_max"]),
        "sample_interval_s": float(budget_limits["sample_interval_s_max"]),
        "term_grace_s": int(budget_limits["term_grace_s"]),
        "native_log_bytes_max": int(budget["native_log_bytes_max"]),
        "shared_native_lock_path": str(lock_path),
        "shared_native_lock_available_at_freeze": True,
        "preflight_mem_available_bytes": mem_available,
        "heavy_concurrency_max": int(budget_limits["heavy_concurrency_max"]),
        "evidence_bytes_max": int(budget["evidence_bytes_max"]),
        "dependency_mutations": int(budget["dependency_mutations"]),
        "asset_download_bytes_max": int(budget["asset_download_bytes_max"]),
    }
    output = {
        "run_dir": str(run_dir.resolve()),
        "episode_h5_paths": [str((run_dir / f"episode_{index:03d}.h5").resolve()) for index in (1, 2)],
        "native_receipt": str((run_dir / "supervisor_receipt.json").resolve()),
        "step_counter": str((run_dir / "step_counter.json").resolve()),
        "worker_receipt": str((run_dir / "worker_receipt.json").resolve()),
        "worker_script": str((CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py").resolve()),
        "independent_reader_script": str((CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py").resolve()),
    }
    plan = {
        "schema_version": "f05-dg02-core-n2-plan-v1",
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": (
            "actual Core SelectedReferenceEnv PositionServoV1; source-bound GeoPhys/USD; "
            "formal bounded diagnostic, not qualification"
        ),
        "hypothesis": (
            "The exact frozen Menagerie Panda source/USD public model can drive the declared six-phase "
            "100Hz position schedule through Core SelectedReferenceEnv, reset twice on one Env, preserve "
            "its public tendon/equality and native drive, produce 301 typed/H5 boundaries per episode, "
            "and satisfy the unchanged bounded physical/control gates."
        ),
        "input_identity": {
            "core_branch": core_branch,
            "core_input_head": core_head,
            "core_worktree": str(CORE.resolve()),
            "provider_branch": provider_branch,
            "provider_gitlink": old_s1["input_identity"]["provider_gitlink"],
            "provider_input_head": provider_head,
            "provider_worktree": str(PROVIDER.resolve()),
        },
        "source": original_source,
        "oracle": schedule_oracle,
        "code": {"tracked_inputs": code_rows},
        "runtime": runtime,
        "runtime_environment_sha256": runtime_hash,
        "limits": limits,
        "method": {
            "entry": "build_versioned_position_candidate -> SelectedReferenceEnv.reset -> RuntimeSession.materialize -> structured Position request -> Generic H5 v3 -> independent process cold reader",
            "episode_lifecycle": "one actual Candidate Env object, two reset episodes, 300 accepted control intervals each; the planned final horizon truncation is recorded as such",
            "native_step_accounting": "charge 5 physics steps before every Core control interval; increment completed only after the public transition returns",
            "physical_oracle": "recompute named arm tracking, source FK, gripper symmetry/opening, free-cube drop/settle and raw Task metrics from typed public boundary states",
            "nonterminal_task_semantics": "raw lift predicate and Task success field are recorded separately; no grasp/lift success or Qualification is claimed",
        },
        "exit_policy": (
            "Preserve frozen plan, exact counters, every output/receipt/log and partial H5 on failure. "
            "Do not suppress early termination, unexpected truncation, Core fault, cleanup error, or a missed gate. "
            "The only expected truncation is the actual horizon-reached final boundary of each episode."
        ),
        "output": output,
    }
    return plan, candidate_static_receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--static-receipt", type=Path)
    args = parser.parse_args()
    plan, candidate_receipt = build_plan()
    attempt_tag = plan["run_id"].rsplit("_", 1)[-1]
    plan_path = args.plan or (OUT / f"n2_formal_{attempt_tag}.plan.json")
    sidecar_path = args.sidecar or Path(str(plan_path) + ".sha256")
    static_receipt_path = args.static_receipt or (OUT / f"candidate_plan_build_{attempt_tag}_receipt.json")
    existing = [path for path in (plan_path, sidecar_path, static_receipt_path) if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to replace frozen N2 plan outputs: {existing}")
    _atomic_json(plan_path, plan)
    plan_hash = _sha(plan_path)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(plan_hash + "\n", encoding="ascii")
    candidate_receipt.update({"formal_plan_path": str(plan_path.resolve()), "formal_plan_sha256": plan_hash})
    _atomic_json(static_receipt_path, candidate_receipt)
    print(json.dumps({
        "run_id": plan["run_id"],
        "formal_plan_path": str(plan_path.resolve()),
        "formal_plan_sha256": plan_hash,
        "native_start_reserved": plan["limits"]["planned_native_starts"],
        "physics_steps_reserved": plan["limits"]["physics_steps_reserved"],
        "candidate_static_receipt_sha256": plan["source"]["core_candidate_receipt"]["sha256"],
        "public_model_counts": candidate_receipt["public_model_counts"],
        "status": "FROZEN_READY_FOR_ZERO_STEP_PRECHECK",
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
