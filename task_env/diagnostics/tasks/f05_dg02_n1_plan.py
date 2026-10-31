"""Freeze a source-bound, bounded public GeoPhys USD tendon/actuator probe."""

from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


CORE = Path("/home/lly/Program_Files/Geochora")
WINDOW = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal02/window_001"
PROVIDER = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_geophys_provider/GeoPhys"
PREVIOUS = WINDOW / "host_g2_001/n0_model_compile_004/plan.json"
PACKAGE = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_dg02_001"
LOCK = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock"
RUN_DIR = WINDOW / "host_g2_001/n1_public_consumer_002"
WORKER = CORE / "task_env/diagnostics/tasks/f05_dg02_n1_public_consumer_probe.py"
SUPERVISOR = CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py"
BUILDER = Path(__file__).resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str, cwd: Path = CORE) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def tracked_input(path: Path) -> dict[str, str]:
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": sha(path)}


def build() -> Path:
    if RUN_DIR.exists():
        raise FileExistsError(f"probe output already exists: {RUN_DIR}")
    previous = json.loads(PREVIOUS.read_text())
    if previous["schema_version"] != "f05-dg02-n0-model-compile-plan-v1":
        raise ValueError("expected the completed N0_004 plan")
    if git("rev-parse", "HEAD") != "589f0640c71a87ec9c7142b9c4fccb2853190ffd" or git("branch", "--show-current") != "develop-full":
        raise RuntimeError("Core branch/HEAD differs from the frozen DG02 input")
    if git("-C", str(PROVIDER), "rev-parse", "HEAD") != "41f8b517c5f92cd6e59907394dc42714b78702a7" or git("-C", str(PROVIDER), "branch", "--show-current") != "codex/phase-ii-01-f05-geophys":
        raise RuntimeError("provider branch/HEAD differs from the frozen DG02 input")

    lock_stream = LOCK.open("a+")
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("shared native lock is occupied") from exc
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
    finally:
        lock_stream.close()
    mem_available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    if mem_available < 6 * 1024**3:
        raise RuntimeError(f"native resource gate failed: MemAvailable={mem_available}")

    code_paths = {row["path"] for row in previous["code"]["tracked_inputs"]}
    code_paths.update(str(path.resolve()) for path in (
        BUILDER,
        WORKER,
        SUPERVISOR,
        PROVIDER / "src/geometry/articulation_data.py",
        PROVIDER / "src/solvers/materialization.py",
        PROVIDER / "src/solvers/rigid/config.py",
        PROVIDER / "src/solvers/rigid/state/host_io.py",
        PROVIDER / "src/solvers/rigid/execution/solver_mixin.py",
        PROVIDER / "src/solvers/rigid/articulation/generalized_dynamics.py",
        PROVIDER / "src/solvers/rigid/equality/field_allocation.py",
    ))
    code = [tracked_input(Path(path)) for path in sorted(code_paths)]

    stage = previous["source"]["usd_stage"]
    source = dict(previous["source"])
    source["mjcf_source"] = {
        "path": str(CORE / "asset/external/mujoco_menagerie/franka_emika_panda/panda.xml"),
        "sha256": previous["source"]["source_mjcf_sha256"],
    }
    source["parent_model_compile_plan"] = {
        "path": str(PREVIOUS.resolve()),
        "sha256": sha(PREVIOUS),
    }
    parent_receipt = WINDOW / "host_g2_001/n0_model_compile_004/process/worker_receipt.json"
    source["parent_model_compile_receipt"] = {
        "path": str(parent_receipt.resolve()),
        "sha256": sha(parent_receipt),
    }
    limits = {
        "native_starts_before": 5,
        "physics_steps_before": 0,
        "physics_steps_reserved": 2,
        "per_probe_steps_max": 500,
        "worker_wall_s_max": 900,
        "sample_interval_s": 0.25,
        "start_native_mem_available_bytes_min": 6442450944,
        "abort_mem_available_bytes_below": 1073741824,
        "native_process_group_sampled_rss_bytes_max": 4294967296,
        "native_log_bytes_max": 134217728,
        "cpu_threads_max": 4,
        "term_grace_s": 5,
        "shared_native_lock_path": str(LOCK),
        "preflight_mem_available_bytes": mem_available,
        "shared_native_lock_available_at_freeze": True,
        "global_physics_steps_max": 72000,
        "geophys_physics_steps_max": 66000,
        "probe_physics_steps_max": 18000,
        "cumulative_geophys_wall_s_before": 10.444709028,
    }
    plan = {
        "schema_version": "f05-dg02-n1-public-consumer-plan-v1",
        "run_id": "DG02_N1_USD_TENDON_ACTUATOR_EQUALITY_002",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "source-bound GeoPhys/USD CPU public-consumer probe; diagnostic, not qualification",
        "hypothesis": "The public GeoPhys USD lowering and RigidSolver consume the source fixed-tendon Jacobian, actuator ctrl/force limits and affine bias, and active compliant finger-joint equality for this exact derived USD. A two-step asymmetric diagnostic should read L=0.02 m, Ldot=0.05 m/s and actuator force 1.5 N before integration; the tendon generalized force should be J^T f=(0.75,0.75) N. A second out-of-range diagnostic state L=1.05 should exercise the -100 N scalar force cap. Equality response is recorded separately and is not called equivalent without source-law comparison.",
        "method": [
            "Import the exact new USD through GeoPhys SceneSource.usd_path(format=usd), lower through SolverSceneDesc/ArticulationConfig and ImportedScene.build_rigid_scene_model.",
            "Initialize only the public GeoPhys CPU runtime and materialize the resulting RigidSceneModel through materialize_rigid.",
            "Resolve source joint names to model joint/qpos/dof addresses; write public qpos/qvel/ctrl state; call exactly two public solver.step() operations with event-fsynced step accounting.",
            "Read only public host diagnostics for tendon length/rate, actuator force, generalized actuator force, constraint force, qpos/qvel and actuator sample status."
        ],
        "source": source,
        "input_identity": previous["input_identity"],
        "runtime": previous["runtime"],
        "code": {"tracked_inputs": code},
        "oracle": {
            "source_revision": "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7",
            "source_joint_names": previous["oracle"]["source_joint_names"],
            "source_actuator_names": previous["oracle"]["actuator_names"],
            "source_tendon": "split",
            "source_equality": "finger_joint1_finger_joint2",
            "test_state_1": {"finger_joint1_q": 0.01, "finger_joint2_q": 0.03, "finger_joint1_dq": 0.02, "finger_joint2_dq": 0.08, "actuator8_requested_ctrl": 300.0, "ctrl_clips_to": 255.0, "expected_tendon_length": 0.02, "expected_tendon_velocity": 0.05, "expected_actuator_force": 1.5, "expected_each_finger_generalized_force": 0.75},
            "test_state_2": {"finger_joint1_q": 1.05, "finger_joint2_q": 1.05, "finger_joint1_dq": 0.0, "finger_joint2_dq": 0.0, "actuator8_requested_ctrl": 255.0, "raw_expected_actuator_force": -101.0, "expected_clipped_actuator_force": -100.0, "expected_each_finger_generalized_force": -50.0, "purpose": "force-law diagnostic outside articulated limit range; not a task trajectory"},
            "epsilon": {"length_m": 0.00005, "velocity_m_s": 0.0001, "force_n": 0.05, "generalized_force_n": 0.08},
            "model_counts": {"actuators": 8, "tendons": 1, "equalities": 1, "scalar_dof": 15}
        },
        "limits": limits,
        "exit_policy": "Record failures with exact started/attempted steps; no retries in this frozen run. Any retry gets a new plan and cumulative counters. A passing N1 probe is local diagnostic evidence only; it does not establish Core route admission or qualification.",
        "output": {"run_dir": str(RUN_DIR.resolve()), "native_receipt": str((RUN_DIR / "supervisor_receipt.json").resolve()), "worker_receipt": str((RUN_DIR / "worker_receipt.json").resolve())}
    }
    path = RUN_DIR.with_suffix(".plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(plan, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(raw)
    (path.with_suffix(path.suffix + ".sha256")).write_text(hashlib.sha256(raw).hexdigest() + "  " + path.name + "\n")
    return path


if __name__ == "__main__":
    print(build())
