"""Freeze one bounded, source-bound DG04 Core N2 execution plan."""

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
MAINT = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
PACKAGE = MAINT / "sol_f05_diagnostic04_004"
WINDOW = MAINT / "f05_diagnostic04/window_004"
DELIVERY = MAINT / "f05_diagnostic04/window_002/isaac_usd_v4/delivery_manifest.json"
ISAAC_ROOT = CORE / "workspace/environments/isaacsim-6.2.0"
ISAAC_PYTHON = ISAAC_ROOT / "bin/python"
GEOPHYS = MAINT / "f05_geophys_provider/GeoPhys"
PROTECTED_DOC = CORE / "docs/maintenance/20261030_runtime_route_diagnostic_handoff.md"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _row(path: Path) -> dict:
    resolved = path.resolve(strict=True)
    return {"path": str(resolved), "sha256": _sha(resolved)}


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


def _tracked_inputs(paths: list[Path]) -> list[dict]:
    rows = [_row(path) for path in paths]
    unique = {row["path"]: row for row in rows}
    return [unique[path] for path in sorted(unique)]


def _schedule(contract: dict, model) -> dict:
    physical = contract["physical_acceptance"]
    home_all = physical["home_joint_position_rad"]
    arm_order = [f"joint{index}" for index in range(1, 8)]
    home = {name: float(home_all[name]) for name in arm_order}
    rows = []
    for phase in contract["schedule"]:
        target = {
            name: home[name] + float(phase["arm_offsets_rad"][index])
            for index, name in enumerate(arm_order)
        }
        pose = model.pose([target[name] for name in arm_order])
        rows.append({
            "start": int(phase["start"]),
            "stop": int(phase["stop"]),
            "phase": str(phase["phase"]),
            "arm_offsets_rad": [float(value) for value in phase["arm_offsets_rad"]],
            "arm_target_position_rad": target,
            "opening_m": float(phase["opening_m"]),
            "source_fk_hand_pose_world": {
                "position_m": [float(value) for value in pose.position],
                "quaternion_wxyz": [float(value) for value in pose.quaternion_wxyz],
            },
        })
    return {
        "episode_count": int(contract["timebase"]["episodes_per_env"]),
        "control_intervals_per_episode": int(contract["timebase"]["control_intervals_per_episode"]),
        "control_substeps": int(contract["timebase"]["physics_steps_per_interval"]),
        "physics_dt_s": float(contract["timebase"]["physics_dt_s"]),
        "outer_control_dt_s": float(contract["timebase"]["physics_steps_per_interval"])
        * float(contract["timebase"]["physics_dt_s"]),
        "reset_physics_steps_expected": int(contract["timebase"]["reset_physics_steps_expected"]),
        "native_observation_rows_per_episode": int(contract["timebase"]["native_observation_rows_per_episode"]),
        "formal_totals": dict(contract["formal_totals"]),
        "home_joint_position_rad": home,
        "finger_home_position_m": {
            name: float(home_all[name]) for name in ("finger_joint1", "finger_joint2")
        },
        "joint_order": arm_order + ["finger_joint1", "finger_joint2"],
        "schedule": rows,
        "tracking": dict(contract["tracking"]),
        "physical_acceptance": dict(contract["physical_acceptance"]),
        "gripper_native_adaptation": dict(contract["gripper_native_adaptation"]),
        "gripper_opening_range_m": 0.08,
        "raw_task_readout": {
            "raw_predicate": "raw_lift_height_predicate",
            "lifecycle_field": "lifecycle_terminated",
            "claim_boundary": "record each independently; the formal F05 diagnostic does not claim Pick/Lift completion or lifecycle-valid success",
        },
        "recording": "two Generic H5 v3 episodes, each T=300 and T+1=301",
        "qualification_granted": False,
    }


def build_plan(output_root: Path) -> tuple[dict, Path, Path, Path]:
    output_root = output_root.resolve()
    if not output_root.is_dir():
        raise FileNotFoundError(f"explicit DG04 N2 output root does not exist: {output_root}")
    progress = _json(WINDOW / "goal_progress.json")
    snapshot = _json(PACKAGE / "input_snapshot.json")
    contract = _json(PACKAGE / "acceptance_contract.json")
    if contract["schema_version"] != "f05-native-adaptation-acceptance-v1":
        raise ValueError("DG04 acceptance contract schema changed")
    branch, head = _git(CORE, "branch", "--show-current"), _git(CORE, "rev-parse", "HEAD")
    if branch != "develop-full":
        raise RuntimeError(f"DG04 formal N2 requires the frozen develop-full branch, found {branch}")
    dirty = _git(CORE, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    protected_line = "?? docs/maintenance/20261030_runtime_route_diagnostic_handoff.md"
    if sorted(dirty) != [protected_line]:
        raise RuntimeError(f"unexpected dirty paths at DG04 N2 plan freeze: {dirty!r}")
    if _sha(PROTECTED_DOC) != snapshot["unrelated_untracked"]["sha256"]:
        raise RuntimeError("protected unrelated handoff document changed")
    if _git(GEOPHYS, "rev-parse", "HEAD") != snapshot["provider_candidate"]["head"]:
        raise RuntimeError("read-only provider candidate HEAD changed")
    if _git(GEOPHYS, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("read-only provider candidate has dirty paths")
    lock_path = MAINT / "shared_native_execution.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("shared native execution lock is occupied before plan freeze") from exc
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    from task_env.controllers.canonical.kinematics import PandaKinematics, PANDA_HAND_ORIGIN_TCP_V1
    from task_env.tasks.position_candidate.builder import build_f05_dg04_isaac_native_candidate

    input_v1, candidate = build_f05_dg04_isaac_native_candidate(str(DELIVERY.resolve(strict=True)), horizon=300)
    input_v1.validate()
    candidate_row = {
        "schema_version": input_v1.schema_version,
        "provider": candidate.env.provider,
        "backend": candidate.env.backend,
        "horizon": int(candidate.env.horizon),
        "task_seed": int(input_v1.reset_plan.reset_sample.task_seed),
        "reset_sample_id": input_v1.reset_plan.reset_sample.sample_id,
        "source_id": input_v1.runtime_source.source_id,
        "source_closure_sha256": input_v1.runtime_source.source_closure_digest,
        "task_artifact_identity_sha256": input_v1.artifact.identity_hash,
        "execution_identity_sha256": input_v1.execution.identity_hash,
        "reset_plan_identity_sha256": input_v1.reset_plan.identity_hash,
        "scene_identity_sha256": candidate.scene.identity_hash,
        "control_binding_plan_identity_sha256": candidate.controller_binding_plan.identity_hash,
        "controller_identity_sha256": candidate.env.controller.identity,
        "task_source_identity_sha256": input_v1.task_source.identity_hash,
        "kinematics_source_sha256": input_v1.kinematics_source_sha256,
        "task_scene_recipe_sha256": input_v1.task_scene_recipe_sha256,
        "physics_profile": input_v1.execution.physics_profile,
    }
    if candidate_row["provider"] != "isaacsim" or candidate_row["backend"] != "cuda" or candidate_row["horizon"] != 300:
        raise ValueError("rebuilt DG04 formal candidate does not bind the required Isaac CUDA horizon")
    xml_path = CORE / "asset/external/mujoco_menagerie/franka_emika_panda/panda.xml"
    if _sha(xml_path) != snapshot["historical_source_entry_sha256"]:
        raise ValueError("Menagerie source MJCF bytes differ from the frozen source entry")
    model = PandaKinematics(input_v1.kinematics_source_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
    oracle = _schedule(contract, model)
    if (oracle["episode_count"] != 2 or oracle["control_intervals_per_episode"] != 300
            or oracle["control_substeps"] != 5 or oracle["formal_totals"] != {
                "physics_steps": 3000, "boundary_observation_rows": 602, "transitions": 600,
            }):
        raise ValueError("DG04 current formal schedule differs from its frozen acceptance totals")

    suffix = 1
    while True:
        tag = f"{suffix:03d}"
        run_dir = output_root / f"n2_formal_{tag}"
        plan_path = output_root / f"n2_formal_{tag}.plan.json"
        sidecar_path = output_root / f"n2_formal_{tag}.plan.json.sha256"
        static_path = output_root / f"candidate_static_{tag}.json"
        receipt_path = output_root / f"n2_formal_{tag}.plan_receipt.json"
        if not any(path.exists() for path in (run_dir, plan_path, sidecar_path, static_path, receipt_path)):
            break
        suffix += 1
    run_id = f"F05_DG04_CORE_N2_FORMAL_{tag}"
    worker = CORE / "task_env/diagnostics/tasks/f05_dg04_core_n2_probe.py"
    reader = CORE / "task_env/diagnostics/tasks/f05_dg04_core_n2_cold_reader.py"
    planner = Path(__file__).resolve()
    supervisor = WINDOW / "run_n2_supervisor.py"
    # The supervisor is written before plan construction so its bytes are frozen too.
    code_paths = [
        planner, worker, reader, supervisor,
        CORE / "task_env/diagnostics/tasks/f05_dg04_native_mimic_core_n1.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_probe.py",
        CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py",
        CORE / "task_env/recorders/recorder.py", CORE / "task_env/recorders/h5.py",
        CORE / "task_env/runtime/sessions/api.py", CORE / "task_env/runtime/sessions/control.py",
        CORE / "task_env/runtime/sessions/leaf_control.py", CORE / "task_env/runtime/sessions/native_io.py",
        CORE / "task_env/runtime/sessions/isaac_native_io.py", CORE / "task_env/tasks/reference_env.py",
        CORE / "task_env/tasks/position_candidate/builder.py", CORE / "task_env/tasks/position_candidate/source.py",
        CORE / "task_env/controllers/canonical/position_profile.py",
        CORE / "task_env/controllers/canonical/kinematics.py",
    ]
    code_rows = _tracked_inputs(code_paths)
    source_rows = {
        "package_manifest": _row(PACKAGE / "package_manifest.json"),
        "input_snapshot": _row(PACKAGE / "input_snapshot.json"),
        "execution_policy": _row(PACKAGE / "execution_policy.json"),
        "acceptance_contract": _row(PACKAGE / "acceptance_contract.json"),
        "luna_prompt": _row(PACKAGE / "luna_goal_prompt.md"),
        "delivery_manifest": _row(DELIVERY),
        "source_mjcf": _row(xml_path),
        "task_scene_recipe": _row(Path(snapshot["original_acceptance_inputs"][2]["path"])),
        "dg01_control_oracle": _row(Path(snapshot["original_acceptance_inputs"][0]["path"])),
        "dg01_original_physical_oracle": _row(Path(snapshot["original_acceptance_inputs"][1]["path"])),
        "candidate_static_receipt": None,
    }
    candidate_static = {
        "schema_version": "f05-dg04-candidate-static-receipt-v1",
        "status": "PASS_ZERO_STEP_SOURCE_BOUND_CANDIDATE_REBUILD",
        "candidate": candidate_row,
        "solver_initialized": False,
        "solver_constructed": False,
        "physics_steps": 0,
        "claim_limit": "candidate identity only; no native physics or Core N2 evidence",
    }
    _atomic_json(static_path, candidate_static)
    source_rows["candidate_static_receipt"] = _row(static_path)
    package_sha = source_rows["package_manifest"]["sha256"]
    if _sha(PACKAGE / "luna_goal_prompt.md") != "8aa89f2ef37674b821df248923e72e60fe50c7c643c275f1222c08bca6488800":
        raise ValueError("frozen DG04 prompt hash changed")

    runtime = {
        "python": str(ISAAC_PYTHON.resolve(strict=True)),
        "python_sha256": _sha(ISAAC_PYTHON),
        "isaac_root": str(ISAAC_ROOT.resolve(strict=True)),
        "isaac_version": "6.2.0.0",
        "core_site_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages",
        "working_directory": str(CORE.resolve()),
        "inherit_pythonpath": False,
        "renderer": "none",
        "backend": "GPU PhysX",
        "device": "cuda:0",
        "cpu_affinity_max_cores": 4,
    }
    mem_available = next(
        int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    gpu_query = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()[0].strip()
    gpu_free_bytes = int(gpu_query) * 1024**2
    limits = {
        "physics_steps_reserved": 3000,
        "worker_wall_s_max": 1800,
        "supervisor_wall_s_max": 1860,
        "sample_period_s": 0.1,
        "max_sample_gap_s": 0.25,
        "max_process_group_rss_bytes": 10 * 1024**3,
        "start_mem_available_bytes_min": 6 * 1024**3,
        "abort_mem_available_bytes_below": 1 * 1024**3,
        "start_gpu_free_bytes_min": 5120 * 1024**2,
        "abort_gpu_free_bytes_below": 256 * 1024**2,
        "start_disk_free_bytes_min": 10 * 1024**3,
        "abort_disk_free_bytes_below": 8 * 1024**3,
        "max_log_bytes": 128 * 1024**2,
        "termination_grace_s": 5,
        "cpu_affinity_max_cores": 4,
        "shared_native_lock_path": str((MAINT / "shared_native_execution.lock").resolve()),
        "preflight_mem_available_bytes": mem_available,
        "preflight_gpu_free_bytes": gpu_free_bytes,
        "shared_lock_available_at_freeze": True,
        "native_workers_max": 1,
    }
    output = {
        "run_dir": str(run_dir.resolve()),
        "episode_h5_paths": [str((run_dir / f"episode_{index:03d}.h5").resolve()) for index in (1, 2)],
        "step_counter": str((run_dir / "step_counter.json").resolve()),
        "worker_progress": str((run_dir / "worker_progress.json").resolve()),
        "worker_receipt": str((run_dir / "worker_receipt.json").resolve()),
        "supervisor_receipt": str((run_dir / "supervisor_receipt.json").resolve()),
        "worker_log": str((run_dir / "worker.log").resolve()),
        "supervisor_script": str(supervisor.resolve(strict=True)),
        "worker_script": str(worker.resolve(strict=True)),
        "reader_script": str(reader.resolve(strict=True)),
        "candidate_static_receipt": str(static_path.resolve(strict=True)),
    }
    plan = {
        "schema_version": "f05-dg04-core-n2-plan-v1",
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "package_id": "F05_DG04_WINDOW004_NATIVE_ADAPTATION_CORE_CLOSURE",
        "package_manifest_sha256": package_sha,
        "classification": (
            "actual Core SelectedReferenceEnv PositionServoV1; source-bound Isaac 6.2 GPU PhysX native adaptation; "
            "bounded diagnostic, not qualification"
        ),
        "hypothesis": (
            "One exact DG04 candidate can execute two 300-interval nonterminal episodes through the production Core "
            "RuntimeSession and Isaac native adapter, persist T/T+1 Generic H5 records, and satisfy the unchanged "
            "tracking, source-FK, gripper, free-body and contact gates on independent cold read."
        ),
        "input_identity": {
            "core_branch": branch,
            "core_input_head": head,
            "core_worktree": str(CORE.resolve()),
            "expected_git_status_lines": sorted(dirty),
            "provider_candidate_path": str(GEOPHYS.resolve()),
            "provider_candidate_head": snapshot["provider_candidate"]["head"],
            "provider_candidate_gitlink": snapshot["provider_gitlinks"]["GeoPhys"],
            "source_asset_gitlink": snapshot["provider_gitlinks"]["asset/external/mujoco_menagerie"],
        },
        "candidate": candidate_row,
        "source": source_rows,
        "oracle": oracle,
        "code": {"tracked_inputs": code_rows},
        "runtime": runtime,
        "limits": limits,
        "method": {
            "entry": "build_f05_dg04_isaac_native_candidate -> SelectedReferenceEnv.reset -> Core RuntimeSession -> structured Position request -> existing Generic H5 v3 Recorder -> separate H5 cold reader",
            "episode_lifecycle": "same SelectedReferenceEnv instance reset twice; 300 accepted control intervals per episode; only the explicit final horizon boundary truncates",
            "native_step_accounting": "formal counter charges five exact Isaac physics advances before every Core step and completes them only after transition return; app bootstrap is separate",
            "physical_contact_evidence": "read raw public PhysX RigidPrim.get_raw_contact_data substep witnesses persisted in native_interval_advance_receipts_v1; retain source paths, signed scalar, magnitude, normals, separation and support normal force; do not relabel as GeoPhys impulse",
            "qualification": False,
        },
        "source_delivery_identity_sha256": candidate_row["source_closure_sha256"],
        "exit_policy": "Any worker error, unplanned lifecycle stop, resource breach, lost process-group control, incomplete T/T+1, or nonzero exit is retained with exact attempted/completed counters; release the native lock only after the process group is gone.",
        "output": output,
    }
    plan_path = output_root / f"n2_formal_{tag}.plan.json"
    sidecar_path = output_root / f"n2_formal_{tag}.plan.json.sha256"
    if plan_path.exists() or sidecar_path.exists() or receipt_path.exists():
        raise FileExistsError("refusing to replace an existing frozen DG04 plan")
    _atomic_json(plan_path, plan)
    plan_sha = _sha(plan_path)
    sidecar_path.write_text(f"{plan_sha}  {plan_path.name}\n", encoding="ascii")
    plan_receipt = {
        "schema_version": "f05-dg04-core-n2-plan-receipt-v1",
        "status": "FROZEN_READY_FOR_SUPERVISED_NATIVE_RUN",
        "run_id": run_id,
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": plan_sha,
        "sidecar_path": str(sidecar_path.resolve()),
        "candidate_static_receipt": source_rows["candidate_static_receipt"],
        "current_core_head": head,
        "package_input_snapshot_sha256": source_rows["input_snapshot"]["sha256"],
        "acceptance_contract_sha256": source_rows["acceptance_contract"]["sha256"],
        "formal_totals": oracle["formal_totals"],
        "resource_gates": {key: limits[key] for key in (
            "preflight_mem_available_bytes", "preflight_gpu_free_bytes",
            "start_mem_available_bytes_min", "start_gpu_free_bytes_min",
            "max_process_group_rss_bytes", "worker_wall_s_max", "supervisor_wall_s_max",
        )},
    }
    _atomic_json(receipt_path, plan_receipt)
    return plan, plan_path, sidecar_path, receipt_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    _, plan_path, sidecar_path, receipt_path = build_plan(args.output_root)
    print(json.dumps({"plan": str(plan_path), "sidecar": str(sidecar_path),
                      "receipt": str(receipt_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
