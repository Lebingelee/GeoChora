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
        CORE / "task_env/controllers/canonical/controller.py",
        CORE / "task_env/controllers/canonical/position_profile.py",
        CORE / "task_env/tasks/position_candidate/builder.py",
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


def _build_formal_oracle(model, source_bodies: dict, physical: dict, control: dict,
                         action_config: dict, controller_method: dict,
                         controller_identity: str) -> dict:
    home_all = physical["physical_acceptance"]["home_joint_position_rad"]
    arm_order = [f"joint{index}" for index in range(1, 8)]
    home = {name: float(home_all[name]) for name in arm_order}
    schedule = []
    for phase in control["schedule"]:
        target = {
            name: home[name] + float(phase["arm_offsets_rad"][index])
            for index, name in enumerate(arm_order)
        }
        pose = model.pose([target[name] for name in arm_order])
        schedule.append({
            "start": int(phase["start"]),
            "stop": int(phase["stop"]),
            "phase": str(phase["phase"]),
            "arm_offsets_rad": [float(value) for value in phase["arm_offsets_rad"]],
            "arm_target_position_rad": target,
            "opening_m": float(phase["opening_m"]),
            "source_fk_method": "PandaKinematics(source MJCF Menagerie bytes; PositionServoV1 owner)",
            "source_fk_hand_pose_world": _model_pose_mapping(pose),
        })
    contact_body_roles = {}
    for role, prim_name in (("free_cube", "free_cube"), ("support", "support")):
        matches = [
            {"semantic_id": str(semantic), "usd_prim_path": str(path)}
            for semantic, path in source_bodies.items()
            if str(path).rstrip("/").rsplit("/", 1)[-1] == prim_name
        ]
        paths = sorted({row["usd_prim_path"] for row in matches})
        if len(paths) != 1 or not matches:
            raise RuntimeError(f"formal N2 source must bind exactly one {role} prim, found {matches}")
        contact_body_roles[role] = {
            "semantic_ids": sorted({row["semantic_id"] for row in matches}),
            "usd_prim_path": paths[0],
        }
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
        "controller_method": {
            "controller_identity_sha256": controller_identity,
            "arm_tracking_method": controller_method["arm_tracking_method"],
            "arm_tracking_profile": controller_method["arm_tracking_profile"],
            "arm_reference_identity_sha256": controller_method["arm_reference_identity"],
            "nullspace_reference_gain": controller_method["nullspace_reference_gain"],
            "reference_source": "reset_typed_arm_joint_position",
            "projector": "svd_right_nullspace_v1",
            "pose_target_method": controller_method["pose_target_method"],
            "arm_target_limit_source": controller_method["arm_target_limit_source"],
        },
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


def _verified_supervised_candidate(*, plan_path: Path, sidecar_path: Path,
                                   receipt_path: Path, worker_path: Path,
                                   supervisor_path: Path, core_head: str,
                                   provider_head: str) -> tuple[dict, dict, dict, dict, dict]:
    plan_path = plan_path.resolve(strict=True)
    sidecar_path = sidecar_path.resolve(strict=True)
    receipt_path = receipt_path.resolve(strict=True)
    worker_path = worker_path.resolve(strict=True)
    supervisor_path = supervisor_path.resolve(strict=True)
    plan_hash = _sha(plan_path)
    if sidecar_path.read_text(encoding="ascii").split()[0] != plan_hash:
        raise ValueError("supervised static candidate plan SHA-256 mismatch")
    plan = _json(plan_path)
    if plan.get("schema_version") != "f05-dg02-n1-public-consumer-plan-v1":
        raise ValueError("unsupported supervised static candidate plan")
    identity = plan["input_identity"]
    if (identity.get("core_input_head") != core_head
            or identity.get("core_branch") != "develop-full"
            or identity.get("provider_input_head") != provider_head
            or identity.get("provider_branch") != "codex/phase-ii-01-f05-geophys"):
        raise ValueError("supervised static candidate was not frozen for the current Core/provider identity")
    if plan["output"].get("candidate_receipt") != str(receipt_path):
        raise ValueError("supervised candidate plan points at a different candidate receipt")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"supervised static candidate input changed: {path}")
    receipt = _json(receipt_path)
    worker = _json(worker_path)
    supervisor = _json(supervisor_path)
    if (worker.get("status") != "PASS_SUPERVISED_STATIC_CORE_CANDIDATE"
            or worker.get("run_id") != plan.get("run_id")
            or worker.get("plan_sha256") != plan_hash
            or worker.get("candidate_receipt_sha256") != _sha(receipt_path)
            or supervisor.get("run_id") != plan.get("run_id")
            or supervisor.get("plan_sha256") != plan_hash
            or supervisor.get("worker_receipt_sha256") != _sha(worker_path)
            or supervisor.get("exit_code") != 0
            or supervisor.get("lock_released_after_process_group_exit") is not True
            or supervisor.get("process_group_gone_before_release") is not True
            or supervisor.get("physics_steps_attempted") != 0
            or supervisor.get("physics_steps_completed") != 0):
        raise ValueError("supervised static candidate receipts do not prove a clean zero-step pass")
    if (receipt.get("run_id") != plan.get("run_id")
            or receipt.get("plan_sha256") != plan_hash
            or receipt.get("checks", {}).get("solver_initialized") is not False
            or receipt.get("checks", {}).get("solver_constructed") is not False
            or receipt.get("checks", {}).get("physics_steps") != 0
            or receipt.get("public_model_counts") != worker.get("public_model_counts")):
        raise ValueError("supervised candidate receipt does not match its plan/worker")
    expected_counts = {"n_qpos": 16, "n_dof": 15, "n_actuators": 8,
                       "n_tendons": 1, "n_equalities": 1}
    actual_counts = receipt.get("public_model_counts", {})
    if any(actual_counts.get(key) != value for key, value in expected_counts.items()):
        raise ValueError("supervised static candidate changed the required source-bound model counts")
    counter_path = Path(supervisor["step_counter_path"]).resolve(strict=True)
    counter = _json(counter_path)
    if (counter.get("attempted_physics_steps") != 0
            or counter.get("completed_physics_steps") != 0):
        raise ValueError("supervised static candidate step counter is not zero")
    candidate_method = worker.get("candidate_controller_method", {})
    if (candidate_method.get("arm_tracking_method") != "production_r3_continuous_v1"
            or not isinstance(candidate_method.get("arm_tracking_profile"), dict)
            or len(str(worker.get("candidate_controller_identity_sha256", ""))) != 64
            or len(str(candidate_method.get("arm_reference_identity", ""))) != 64):
        raise ValueError("supervised static candidate is not bound to the DG02 Production R3 arm method")
    return plan, receipt, worker, supervisor, counter


def build_plan(*, output_root: Path, progress_path: Path,
               candidate_plan_path: Path, candidate_sidecar_path: Path,
               candidate_receipt_path: Path, candidate_worker_path: Path,
               candidate_supervisor_path: Path) -> tuple[dict, dict]:
    output_root = output_root.resolve()
    progress_path = progress_path.resolve(strict=True)
    attempt_index = 1
    while True:
        attempt_tag = f"{attempt_index:03d}"
        run_dir = output_root / f"n2_formal_{attempt_tag}"
        plan_path = output_root / f"n2_formal_{attempt_tag}.plan.json"
        candidate_admission_path = output_root / f"candidate_static_admission_{attempt_tag}.json"
        if not any(path.exists() for path in (run_dir, plan_path, candidate_admission_path)):
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

    progress = _json(progress_path)
    budget = _json(BUDGET_PATH)
    control = _json(ORACLES_PATH)
    physical = _json(PHYSICAL_PATH)
    old_s1 = _json(OLD_S1_PLAN)
    (candidate_plan, static_receipt, candidate_worker, candidate_supervisor,
     _candidate_counter) = _verified_supervised_candidate(
        plan_path=candidate_plan_path,
        sidecar_path=candidate_sidecar_path,
        receipt_path=candidate_receipt_path,
        worker_path=candidate_worker_path,
        supervisor_path=candidate_supervisor_path,
        core_head=core_head,
        provider_head=provider_head,
    )
    if not CORE.joinpath("docs/maintenance/20261030_runtime_route_diagnostic_handoff.md").is_file():
        raise RuntimeError("protected maintenance handoff document is missing")

    candidate_plan_hash = _sha(candidate_plan_path.resolve(strict=True))
    candidate_static_receipt = {
        "schema_version": "f05-dg02-static-candidate-admission-v1",
        "run_id": candidate_plan["run_id"],
        "candidate_plan_sha256": candidate_plan_hash,
        "candidate_plan_path": str(candidate_plan_path.resolve()),
        "candidate_plan_sidecar_path": str(candidate_sidecar_path.resolve()),
        "candidate_receipt_path": str(candidate_receipt_path.resolve()),
        "candidate_receipt_sha256": _sha(candidate_receipt_path.resolve()),
        "candidate_worker_receipt_path": str(candidate_worker_path.resolve()),
        "candidate_worker_receipt_sha256": _sha(candidate_worker_path.resolve()),
        "candidate_supervisor_receipt_path": str(candidate_supervisor_path.resolve()),
        "candidate_supervisor_receipt_sha256": _sha(candidate_supervisor_path.resolve()),
        "step_counter_path": str(Path(candidate_supervisor["step_counter_path"]).resolve()),
        "step_counter_sha256": _sha(Path(candidate_supervisor["step_counter_path"]).resolve()),
        "solver_initialized": False,
        "solver_constructed": False,
        "physics_steps": 0,
        "public_model_counts": static_receipt["public_model_counts"],
        "controller_identity_sha256": candidate_worker["candidate_controller_identity_sha256"],
        "controller_method": candidate_worker["candidate_controller_method"],
        "provider_head": provider_head,
        "core_head": core_head,
        "status": "PASS_STATIC_SOURCE_BOUND_CANDIDATE_ADMISSION",
    }
    _atomic_json(candidate_admission_path, candidate_static_receipt)

    original_source = dict(old_s1["source"])
    prior_candidate_supervisor = original_source.pop("core_candidate_supervisor_receipt", None)
    original_source.update({
        "core_candidate_plan": _row(candidate_plan_path.resolve(strict=True)),
        "core_candidate_plan_sidecar": _row(candidate_sidecar_path.resolve(strict=True)),
        "core_candidate_receipt": _row(candidate_receipt_path.resolve(strict=True)),
        "core_candidate_worker_receipt": _row(candidate_worker_path.resolve(strict=True)),
        "core_candidate_supervisor_receipt": _row(candidate_supervisor_path.resolve(strict=True)),
        "core_candidate_step_counter": _row(Path(candidate_supervisor["step_counter_path"]).resolve(strict=True)),
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
        {"path": str(CORE / "task_env/controllers/canonical/kinematics.py"), "sha256": _sha(CORE / "task_env/controllers/canonical/kinematics.py")},
        {"path": str(CORE / "task_env/tasks/nut_assembly/config.yaml"), "sha256": _sha(CORE / "task_env/tasks/nut_assembly/config.yaml")},
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_plan.py"), "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_plan.py")},
        {"path": str(CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_worker.py"), "sha256": _sha(CORE / "task_env/diagnostics/tasks/f05_dg02_core_candidate_supervised_worker.py")},
    )
    source_xml_path = Path(old_s1["source"]["mjcf_source"]["path"]).resolve(strict=True)
    if _sha(source_xml_path) != old_s1["source"]["mjcf_source"]["sha256"]:
        raise ValueError("formal N2 source MJCF changed before oracle construction")
    from task_env.controllers.canonical.kinematics import PandaKinematics, PANDA_HAND_ORIGIN_TCP_V1
    from task_env.tasks.position_candidate.builder import _f05_dg02_usd_source_bindings
    source_bodies, _source_joints = _f05_dg02_usd_source_bindings()
    model = PandaKinematics(
        source_xml_path.read_text(encoding="utf-8"),
        tcp_profile=PANDA_HAND_ORIGIN_TCP_V1,
    )
    schedule_oracle = _build_formal_oracle(
        model, source_bodies, physical, control, static_receipt["action_config"],
        candidate_worker["candidate_controller_method"],
        candidate_worker["candidate_controller_identity_sha256"],
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
    if run_dir.exists():
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
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--candidate-plan", type=Path, required=True)
    parser.add_argument("--candidate-plan-sha256", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--candidate-worker", type=Path, required=True)
    parser.add_argument("--candidate-supervisor", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--static-receipt", type=Path, required=True)
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    plan_path = args.plan.resolve()
    sidecar_path = args.sidecar.resolve()
    static_receipt_path = args.static_receipt.resolve()
    if any(output_root not in path.parents for path in (plan_path, sidecar_path, static_receipt_path)):
        raise ValueError("all formal plan outputs must be contained under the explicit output root")
    plan, candidate_receipt = build_plan(
        output_root=args.output_root,
        progress_path=args.progress,
        candidate_plan_path=args.candidate_plan,
        candidate_sidecar_path=args.candidate_plan_sha256,
        candidate_receipt_path=args.candidate_receipt,
        candidate_worker_path=args.candidate_worker,
        candidate_supervisor_path=args.candidate_supervisor,
    )
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
