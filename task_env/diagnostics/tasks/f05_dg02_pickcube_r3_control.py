"""Freeze, run, and cold-compare the bounded PickCube R3 provider controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

import numpy as np


CORE = Path(__file__).resolve().parents[3]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))
MAINT = Path("/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001")
WINDOW = MAINT / "f05_diagnostic_goal02/window_002"
PACKAGE = MAINT / "sol_f05_dg02_002_pickcube_r3_001"
PROVIDER = MAINT / "f05_geophys_provider/GeoPhys"
PACKAGE_HEAD = "d808ba0228d7c9299e43e7ff89fe4d3687ea5f71"
PROVIDER_HEAD = "f4d3b3bb21882bac5ca007e657f5d6709a6189b8"
ARM_NAMES = tuple(f"panda-v1/joint{i}" for i in range(1, 8))
FINGER_NAMES = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any):
    if hasattr(value, "to_mapping"):
        return _jsonable(value.to_mapping())
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict
        return _jsonable(asdict(value))
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _tracked_paths() -> list[Path]:
    relative = (
        "task_env/tasks/pick_cube/task.py",
        "task_env/tasks/pick_cube/config.yaml",
        "task_env/tasks/reference_env.py",
        "task_env/objects/pick_cube.py",
        "task_env/controllers/canonical/__init__.py",
        "task_env/controllers/canonical/contracts.py",
        "task_env/controllers/canonical/controller.py",
        "task_env/controllers/canonical/feedback.py",
        "task_env/controllers/canonical/kinematics.py",
        "task_env/controllers/canonical/production_r2.py",
        "task_env/controllers/canonical/production_r3.py",
        "task_env/utils/rotation/__init__.py",
        "task_env/utils/rotation/core.py",
        "task_env/recorders/__init__.py",
        "task_env/recorders/h5.py",
        "task_env/runtime/sessions/api.py",
        "task_env/runtime/sessions/control.py",
        "task_env/runtime/sessions/geophys.py",
        "task_env/runtime/sessions/geophys_native_io.py",
        "task_env/runtime/sessions/mujoco.py",
        "task_env/runtime/sessions/source.py",
        "task_env/runtime/sessions/provenance.py",
        "task_env/diagnostics/tasks/c02b_r1_force_freshness_s2_probe.py",
        "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py",
        "task_env/diagnostics/tasks/f05_dg02_pickcube_r3_control.py",
    )
    return sorted((CORE / item).resolve(strict=True) for item in relative)


def _source_rows() -> dict:
    files = {
        "control_oracles": PACKAGE / "control_oracles.json",
        "original_physical_oracle": PACKAGE / "original_physical_oracle.json",
        "task_scene_recipe": PACKAGE / "accepted_task_scene_recipe.json",
        "package_prompt": PACKAGE / "luna_goal_prompt.md",
        "package_snapshot": PACKAGE / "input_snapshot.json",
        "package_manifest": PACKAGE / "package_manifest.json",
        "pickcube_task_config": CORE / "task_env/tasks/pick_cube/config.yaml",
        "pickcube_r3_profile_source": CORE / "task_env/tasks/nut_assembly/config.yaml",
        "panda_mjcf": CORE / "asset/external/mujoco_menagerie/franka_emika_panda/panda.xml",
    }
    return {key: {"path": str(path.resolve(strict=True)), "sha256": _sha(path)}
            for key, path in files.items()}


def freeze_plan(provider: str, run_dir: Path) -> tuple[dict, Path, Path]:
    if provider not in {"geophys", "mujoco"}:
        raise ValueError("PickCube R3 control provider must be geophys or mujoco")
    run_dir = run_dir.resolve()
    plan_path = run_dir.with_suffix(".plan.json")
    sidecar = plan_path.with_suffix(plan_path.suffix + ".sha256")
    if any(path.exists() for path in (run_dir, plan_path, sidecar)):
        raise FileExistsError("refusing to replace an existing PickCube R3 control plan/output")
    if run_dir.parent.resolve() != WINDOW.resolve():
        raise ValueError("PickCube R3 control outputs must stay in the frozen window directory")
    suffix = run_dir.name.rsplit("_", 1)[-1]
    if not suffix.isdigit():
        raise ValueError("PickCube R3 output directory must end with an attempt number")
    if (_git(CORE, "rev-parse", "HEAD"), _git(CORE, "branch", "--show-current"),
            _git(PROVIDER, "rev-parse", "HEAD"), _git(PROVIDER, "branch", "--show-current")) != (
            PACKAGE_HEAD, "develop-full", PROVIDER_HEAD, "codex/phase-ii-01-f05-geophys"):
        raise RuntimeError("Core/provider checkout differs from the frozen Goal inputs")
    if _git(PROVIDER, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("isolated GeoPhys checkout must remain clean")

    previous = json.loads((WINDOW / "core_s1_002.plan.json").read_text(encoding="utf-8"))
    budget = json.loads((PACKAGE / "execution_budget.json").read_text(encoding="utf-8"))
    control_oracles = json.loads((PACKAGE / "control_oracles.json").read_text(encoding="utf-8"))
    resource = budget["resource_envelope"]
    limit = budget["window_limits"]
    lock_path = Path(resource["shared_native_lock_path"]).resolve()
    import fcntl
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("shared native lock is occupied during plan freeze") from error
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    mem = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
               if line.startswith("MemAvailable:"))
    if mem < int(resource["start_native_mem_available_bytes_min"]):
        raise RuntimeError("native memory start gate is not satisfied")

    ledger = json.loads((WINDOW / "run_ledger.json").read_text(encoding="utf-8"))
    route_start_count = (ledger["new_window_totals"]["geophys_starts"] if provider == "geophys"
                         else ledger["new_window_totals"]["mujoco_starts"])
    route_steps = (ledger["new_window_totals"]["geophys_nonformal_attempted_steps"] if provider == "geophys"
                   else ledger["new_window_totals"]["mujoco_attempted_steps"])
    if provider == "geophys":
        if route_steps + 3000 > int(limit["nonformal_geophys_steps_max"]):
            raise RuntimeError("PickCube R3 comparison would exceed the GeoPhys nonformal window cap")
        if (ledger["new_window_totals"]["geophys_formal_attempted_steps"]
                + ledger["new_window_totals"]["geophys_nonformal_attempted_steps"] + 3000
                > int(limit["geophys_attempted_steps_max"])):
            raise RuntimeError("PickCube R3 comparison would exceed the GeoPhys window step cap")
    elif route_steps + 3000 > int(limit["secondary_mujoco_attempted_steps_max"]):
        raise RuntimeError("PickCube R3 comparison would exceed the MuJoCo window step cap")
    counter_path = run_dir / "step_counter.json"
    run_id = f"DG02_WINDOW002_PICKCUBE_R3_{provider.upper()}_{suffix}"
    output = {
        "run_dir": str(run_dir),
        "worker_script": str((CORE / "task_env/diagnostics/tasks/f05_dg02_pickcube_r3_control.py").resolve()),
        "worker_receipt": str(run_dir / "worker_receipt.json"),
        "episode_h5_paths": [str(run_dir / "episode_001.h5"), str(run_dir / "episode_002.h5")],
        "native_receipt": str(run_dir / "supervisor_receipt.json"),
        "step_counter": str(counter_path),
    }
    code = [{"path": str(path), "sha256": _sha(path)} for path in _tracked_paths()]
    source = _source_rows()
    # The exact R3 profile is loaded through the PickCube public constructor. This
    # frozen descriptor records the imported owner and the source config hash.
    source["controller_profile"] = {
        "method": "existing ProductionCanonicalPandaControllerR3 via PickCube public opt-in",
        "selection": "r3_continuous_v1",
        "profile_source_sha256": source["pickcube_r3_profile_source"]["sha256"],
    }
    runtime = dict(previous["runtime"])
    plan = {
        "schema_version": "f05-dg02-n1-public-consumer-plan-v1",
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "classification": f"diagnostic PickCube/MJCF/R3 unloaded {provider}/CPU provider control; not qualification",
        "provider": provider,
        "input_identity": {
            "core_branch": "develop-full", "core_input_head": PACKAGE_HEAD,
            "core_worktree": str(CORE.resolve()),
            "provider_branch": "codex/phase-ii-01-f05-geophys",
            "provider_gitlink": previous["input_identity"]["provider_gitlink"],
            "provider_input_head": PROVIDER_HEAD, "provider_worktree": str(PROVIDER.resolve()),
        },
        "source": source,
        "oracle": {
            "source_control_oracle_sha256": source["control_oracles"]["sha256"],
            "source_physical_oracle_sha256": source["original_physical_oracle"]["sha256"],
            "controller_profile": "r3_continuous_v1",
            "task_seed": 31,
            "episode_count": 2,
            "control_intervals_per_episode": 300,
            "control_substeps": 5,
            "physics_dt_s": 0.002,
            "control_dt_s": 0.01,
            "task_tcp_frame": "panda-v1/ee; physical site frame; no hand-origin relabeling",
            "provider_matching": "same seed, q0/dq0, reset TCP, action and gripper schedules are required by cold comparison",
            "planner": {
                "position_delta_world_m": [0.012, 0.0, 0.0],
                "rotation_delta_world_rotvec_rad": [0.0, 0.0, 0.08],
                "position_interpolation": "cubic_smoothstep_40_intervals_then_10_interval_endpoint_hold",
                "rotation_interpolation": "cubic_smoothstep_40_intervals_then_10_interval_endpoint_hold",
                "max_translation_speed_m_s": 0.06,
                "max_translation_acceleration_m_s2": 0.45,
                "max_rotation_speed_rad_s": 3.0,
                "max_rotation_acceleration_rad_s2": 27.0,
                "derived_peak_translation_speed_m_s": 0.045,
                "derived_peak_translation_acceleration_m_s2": 0.45,
                "derived_peak_rotation_speed_rad_s": 0.3,
                "derived_peak_rotation_acceleration_rad_s2": 3.0,
            },
            "phases": [
                {"start": 0, "stop": 50, "phase": "unloaded_home_hold", "measure_last": 10},
                {"start": 50, "stop": 100, "phase": "unloaded_point_and_hold", "move": [50, 90], "measure_last": 10},
                {"start": 100, "stop": 150, "phase": "unloaded_return_and_hold", "move": [100, 140], "measure_last": 10},
                {"start": 150, "stop": 200, "phase": "gripper_close_at_home", "gripper_opening_m": 0.02, "measure_last": 10},
                {"start": 200, "stop": 250, "phase": "gripper_open_at_home", "gripper_opening_m": 0.08, "measure_last": 10},
                {"start": 250, "stop": 300, "phase": "final_cartesian_hold", "measure_last": 10},
            ],
            "gripper_command_schedule": {"open_m": 0.08, "close_m": 0.02, "normalized_open": 1.0, "normalized_close": -0.5},
            "locked_joint_mode": "separate ablation; not mixed with this continuous Cartesian feedback route",
            "metrics": ["TCP position error RMSE/max/bias/jitter", "TCP quaternion angle error", "joint error/rate", "applied arm targets", "clipping", "canonical gripper force/opening", "raw adapter actuator sample when public"],
            "qualification": False,
        },
        "code": {"tracked_inputs": code},
        "runtime": runtime,
        "runtime_environment_sha256": hashlib.sha256(json.dumps(runtime, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        "limits": {
            "native_starts_before": route_start_count,
            "planned_native_starts": 1,
            "physics_steps_before": route_steps,
            "physics_steps_reserved": 3000,
            "physics_steps_completed_before": route_steps,
            "probe_physics_steps_before": 1675 + ledger["new_window_totals"]["geophys_nonformal_attempted_steps"],
            "probe_physics_steps_max": int(budget["original_goal_limits_unchanged"]["probe_physics_steps_cumulative_max"]),
            "global_physics_steps_max": int(budget["original_goal_limits_unchanged"]["goal_native_physics_steps_cumulative_max"]),
            "geophys_physics_steps_max": int(budget["original_goal_limits_unchanged"]["geophys_physics_steps_cumulative_max"]),
            "cumulative_geophys_wall_s_before": ledger["carry_in"]["geophys_wall_s_conservative"] + ledger["new_window_totals"]["native_wall_s"],
            "per_formal_worker_step_max": int(limit["per_formal_steps_max"]),
            "per_formal_worker_wall_s_max": int(limit["per_formal_wall_s_max"]),
            "per_probe_steps_max": int(limit["per_baseline_regression_worker_steps_max"]),
            "per_probe_worker_wall_s_max": int(limit["per_baseline_regression_worker_wall_s_max"]),
            "worker_wall_s_max": int(limit["per_baseline_regression_worker_wall_s_max"]),
            "native_log_bytes_max": int(budget["original_goal_limits_unchanged"]["native_log_bytes_max"]),
            "native_process_group_sampled_rss_bytes_max": int(resource["native_process_group_sampled_rss_bytes_max"]),
            "abort_mem_available_bytes_below": int(resource["abort_mem_available_bytes_below"]),
            "start_native_mem_available_bytes_min": int(resource["start_native_mem_available_bytes_min"]),
            "cpu_threads_max": int(resource["cpu_threads_max"]),
            "sample_interval_s": float(resource["sample_interval_s_max"]),
            "term_grace_s": int(resource["term_grace_s"]),
            "shared_native_lock_path": str(Path(resource["shared_native_lock_path"]).resolve()),
            "preflight_mem_available_bytes": mem,
        },
        "output": output,
    }
    return plan, plan_path, sidecar


def _verify(plan_path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("PickCube R3 plan hash mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-n1-public-consumer-plan-v1":
        raise ValueError("unsupported PickCube R3 plan schema")
    if plan.get("classification") != f"diagnostic PickCube/MJCF/R3 unloaded {plan['provider']}/CPU provider control; not qualification":
        raise ValueError("PickCube R3 classification changed")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"PickCube R3 tracked code changed after plan freeze: {path}")
    for row in plan["source"].values():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            path = Path(row["path"]).resolve(strict=True)
            if _sha(path) != row["sha256"]:
                raise ValueError(f"PickCube R3 source changed after plan freeze: {path}")
    identity = plan["input_identity"]
    for repo_key, head_key, branch_key in (
        ("core_worktree", "core_input_head", "core_branch"),
        ("provider_worktree", "provider_input_head", "provider_branch"),
    ):
        repo = Path(identity[repo_key]).resolve(strict=True)
        if (_git(repo, "rev-parse", "HEAD"), _git(repo, "branch", "--show-current")) != (
                identity[head_key], identity[branch_key]):
            raise ValueError(f"PickCube R3 {repo_key} changed after plan freeze")
    return plan, digest


def _finite(value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("PickCube R3 received a non-finite public state/control value")
    return result


def _pose(pose) -> dict:
    return {
        "position_m": [_finite(x) for x in pose.position],
        "quaternion_wxyz": [_finite(x) for x in pose.quaternion_wxyz],
    }


def _quat_mul(a, b):
    aw, ax, ay, az = map(float, a)
    bw, bx, by, bz = map(float, b)
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _target_at(base_pose: dict, plan: dict, interval: int) -> tuple[dict, str, float]:
    position = np.asarray(base_pose["position_m"], dtype=float)
    quaternion = tuple(base_pose["quaternion_wxyz"])
    position_delta = np.asarray(plan["oracle"]["planner"]["position_delta_world_m"], dtype=float)
    rotvec = np.asarray(plan["oracle"]["planner"]["rotation_delta_world_rotvec_rad"], dtype=float)
    angle = float(np.linalg.norm(rotvec))
    half = angle * 0.5
    delta_q = (math.cos(half), *(rotvec / angle * math.sin(half))) if angle else (1.0, 0.0, 0.0, 0.0)
    if 50 <= interval < 90:
        progress = (interval - 49) / 40.0
        phase = "unloaded_point_move"
    elif 90 <= interval < 100:
        progress, phase = 1.0, "unloaded_point_hold"
    elif 100 <= interval < 140:
        progress = 1.0 - (interval - 99) / 40.0
        phase = "unloaded_return_move"
    elif 140 <= interval < 150:
        progress, phase = 0.0, "unloaded_return_hold"
    elif interval < 50:
        progress, phase = 0.0, "unloaded_home_hold"
    elif interval < 100:
        progress, phase = 1.0, "unloaded_point_hold"
    elif interval < 150:
        progress, phase = 0.0, "unloaded_return_hold"
    elif interval < 200:
        progress, phase = 0.0, "gripper_close_at_home"
    elif interval < 250:
        progress, phase = 0.0, "gripper_open_at_home"
    else:
        progress, phase = 0.0, "final_cartesian_hold"
    blend = 3.0 * progress ** 2 - 2.0 * progress ** 3
    goal_position = position + blend * position_delta
    scaled_delta_q = (math.cos(half * blend), *(rotvec / angle * math.sin(half * blend))) if angle else delta_q
    goal_quaternion = _quat_mul(scaled_delta_q, quaternion)
    if 150 <= interval < 200:
        gripper = -0.5
    else:
        gripper = 1.0
    return ({"position_m": goal_position.tolist(), "quaternion_wxyz": list(goal_quaternion)}, phase, gripper)


def _state(env) -> dict:
    actual = env.state.pose_world["panda-v1/ee"]
    return {
        "control_step": int(env.state.control_step),
        "simulation_time_s": _finite(env.state.simulation_time),
        "joint_position_rad": {name: _finite(env.state.joint_position[name]) for name in (*ARM_NAMES, *FINGER_NAMES)},
        "joint_velocity_rad_s": {name: _finite(env.state.joint_velocity[name]) for name in (*ARM_NAMES, *FINGER_NAMES)},
        "tcp_pose_world": _pose(actual),
        "gripper_feedback": _jsonable(env.feedback.gripper),
    }


def _position_error(actual: dict, target: dict) -> dict:
    error = np.asarray(actual["position_m"]) - np.asarray(target["position_m"])
    q_actual = np.asarray(actual["quaternion_wxyz"], dtype=float)
    q_target = np.asarray(target["quaternion_wxyz"], dtype=float)
    dot = float(np.clip(abs(float(q_actual @ q_target)), 0.0, 1.0))
    return {"position_error_world_m": error.tolist(), "position_error_norm_m": float(np.linalg.norm(error)),
            "orientation_error_rad": 2.0 * math.acos(dot)}


def _inspect_mujoco_source_joint_types(source) -> list[dict]:
    """Report the exact compiled scalar-joint types used by the MuJoCo adapter."""
    import mujoco
    import xml.etree.ElementTree as ET

    root = ET.fromstring(source.scene_source.xml)
    for element in root.iter("freejoint"):
        element.tag = "joint"
        element.set("type", "free")
    for element in root.findall("keyframe"):
        root.remove(element)
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    allowed = {
        int(mujoco.mjtJoint.mjJNT_HINGE),
        int(mujoco.mjtJoint.mjJNT_SLIDE),
    }
    rows = []
    for semantic, native in source.joints.items():
        joint_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, native))
        if joint_id < 0:
            rows.append({"semantic": semantic, "native_name": native, "joint_id": None,
                         "joint_type": None, "accepted_scalar": False})
            continue
        joint_type = int(model.jnt_type[joint_id])
        rows.append({"semantic": semantic, "native_name": native, "joint_id": joint_id,
                     "joint_type": joint_type, "accepted_scalar": joint_type in allowed})
    del model
    return rows


def _mujoco_address_failure_details(error: BaseException) -> dict | None:
    """Capture the exact Core adapter binding that failed, without retaining model state."""
    traceback_node = error.__traceback__
    while traceback_node is not None:
        frame = traceback_node.tb_frame
        if frame.f_code.co_name == "_addresses" and Path(frame.f_code.co_filename).name == "mujoco.py":
            local = frame.f_locals
            session = local.get("self")
            name = local.get("name")
            joint_id = local.get("joint")
            if session is None or name is None or joint_id is None:
                return {"capture_status": "adapter_frame_missing_expected_locals"}
            model = session._model
            raw_type = model.jnt_type[int(joint_id)]
            allowed = tuple(local.get("allowed", ()))
            return {
                "capture_status": "captured",
                "native_name": str(name),
                "joint_id": int(joint_id),
                "joint_type_raw_repr": repr(raw_type),
                "joint_type_int": int(raw_type),
                "allowed_raw_repr": [repr(value) for value in allowed],
                "raw_membership_results": [bool(raw_type == value) for value in allowed],
                "free": bool(local.get("free")),
            }
        traceback_node = traceback_node.tb_next
    return None


def _record_attempt(counter_path: Path, plan: dict, *, completed: bool = False) -> None:
    counter = json.loads(counter_path.read_text(encoding="utf-8"))
    if counter.get("run_id") != plan["run_id"]:
        raise ValueError("PickCube R3 step counter belongs to another run")
    key = "completed_physics_steps" if completed else "attempted_physics_steps"
    value = int(counter[key]) + int(plan["oracle"]["control_substeps"])
    if value > int(plan["limits"]["physics_steps_reserved"]):
        raise RuntimeError("PickCube R3 exceeded its frozen native step reservation")
    counter[key] = value
    counter["physics_dt_s"] = float(plan["oracle"]["physics_dt_s"])
    counter["expected_native_steps_per_control_interval"] = int(plan["oracle"]["control_substeps"])
    _atomic_json(counter_path, counter)


def _run_episode(env, plan: dict, episode: int, counter: Path, actuator_law: dict) -> dict:
    from task_env.trajectory.canonical.h5 import load as load_canonical_h5

    _, reset_info = env.reset(seed=int(plan["oracle"]["task_seed"]))
    if env.state.control_step != 0 or abs(env.state.simulation_time) > 1e-12:
        raise ValueError("PickCube R3 reset did not return to control step/time zero")
    reset = _state(env)
    initial_pose = reset["tcp_pose_world"]
    h5_path = Path(plan["output"]["episode_h5_paths"][episode - 1]).resolve()
    env.start_recording(h5_path)
    transitions = []
    intervals = int(plan["oracle"]["control_intervals_per_episode"])
    dt = float(plan["oracle"]["control_dt_s"])
    substeps = int(plan["oracle"]["control_substeps"])
    for interval in range(intervals):
        before = _state(env)
        target, phase, gripper = _target_at(initial_pose, plan, interval)
        action = np.asarray((*target["position_m"], *target["quaternion_wxyz"], gripper), dtype=np.float64)
        _record_attempt(counter, plan)
        result = env.step(action)
        if type(result) is not tuple or len(result) != 5:
            raise TypeError("PickCube R3 SelectedReferenceEnv.step did not return its five-value API")
        obs, reward, terminated, truncated, info = result
        after = _state(env)
        if after["control_step"] != before["control_step"] + 1:
            raise ValueError("PickCube R3 did not advance exactly one control interval")
        if abs(after["simulation_time_s"] - before["simulation_time_s"] - dt) > 1e-9:
            raise ValueError("PickCube R3 clock differs from the frozen 100 Hz / 5×2 ms oracle")
        if bool(terminated) or bool(truncated):
            raise RuntimeError("PickCube R3 unexpectedly terminated/truncated before the planned stop")
        _record_attempt(counter, plan, completed=True)
        acknowledgement = info.get("control_application_v1")
        if not isinstance(acknowledgement, dict):
            raise ValueError("PickCube R3 public control application acknowledgement is missing")
        arm_target = acknowledgement["target"]["arm_position"]
        applied_arm = acknowledgement["applied"]["arm_servo_position"]
        joint_error = {name: _finite(after["joint_position_rad"][name] - arm_target[name])
                       for name in ARM_NAMES}
        raw_measurement = getattr(env.session, "actuator_force_measurement", None)
        raw_measurement_mapping = _jsonable(raw_measurement)
        if isinstance(raw_measurement_mapping, dict):
            raw_measurement_mapping["source_actuator_force_range_N"] = list(actuator_law["source_forcerange"])
        diagnostics = getattr(env.controller, "last_arm_diagnostics", {})
        transitions.append({
            "interval": interval,
            "phase": phase,
            "requested_tcp_pose_world": target,
            "requested_gripper_normalized": gripper,
            "requested_gripper_opening_m": 0.5 * (gripper + 1.0) * 0.08,
            "before": before,
            "after": after,
            "tcp_tracking_error": _position_error(after["tcp_pose_world"], target),
            "joint_target_rad": {name: _finite(arm_target[name]) for name in ARM_NAMES},
            "applied_arm_servo_target_rad": {name: _finite(applied_arm[name]) for name in ARM_NAMES},
            "joint_target_error_rad": joint_error,
            "canonical_control_application": acknowledgement,
            "controller_arm_diagnostics": _jsonable(diagnostics),
            "provider_actuator_force_measurement": raw_measurement_mapping,
            "task_metrics": _jsonable(info.get("task_metrics", {})),
            "reward": _finite(reward),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
        })
    if len(transitions) != intervals:
        raise ValueError("PickCube R3 transition count differs from its frozen plan")
    stop_reason = f"dg02_pickcube_r3_{plan['provider']}_episode_{episode}"
    recording = env.finish_recording(stop_reason)
    if Path(env.recording_path).resolve() != h5_path:
        raise ValueError("PickCube R3 H5 path differs from the frozen output")
    with h5_path.open("rb") as stream:
        os.fsync(stream.fileno())
    cold = load_canonical_h5(h5_path)
    if (len(cold.transitions), len(cold.boundaries)) != (intervals, intervals + 1):
        raise ValueError("PickCube R3 in-process canonical H5 reader rejected T/T+1")
    return {
        "episode": episode,
        "reset": reset,
        "reset_info": _jsonable(reset_info),
        "sample_id": env.sample.sample_id,
        "task_seed": int(env.sample.task_seed),
        "task_artifact_identity_sha256": env.artifact.identity_hash,
        "source_id": env.value["source"].scene_source.source_id,
        "source_xml_sha256": env.value["resolved_configuration"]["source_xml_sha256"],
        "source_closure_sha256": env.value["source"].source_closure_digest,
        "controller_class": type(env.controller).__name__,
        "controller_identity_sha256": env.controller.identity,
        "controller_profile": _jsonable(env.value["resolved_configuration"].get("resolved_controller_profile")),
        "controller_profile_source_sha256": env.value["resolved_configuration"]["source_sha256"].get("task_env/tasks/nut_assembly/config.yaml"),
        "source_actuator8_law": actuator_law,
        "provider": env.provider,
        "backend": env.backend,
        "timebase": env.artifact.timebase.to_mapping(),
        "transition_count": len(cold.transitions),
        "observation_count": len(cold.boundaries),
        "h5_path": str(h5_path),
        "h5_bytes": h5_path.stat().st_size,
        "h5_sha256": _sha(h5_path),
        "recording_receipt": recording,
        "in_process_h5_readback": {"transition_count": len(cold.transitions), "observation_count": len(cold.boundaries),
                                   "schema_version": cold.schema_version, "identity_hash": cold.identity_hash},
        "transitions": transitions,
    }


def run(plan_path: Path, sidecar: Path, receipt_path: Path, counter_path: Path) -> dict:
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv
    from task_env.controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
    from task_env.diagnostics.tasks.c02b_r1_force_freshness_s2_probe import _actuator_law

    plan, digest = _verify(plan_path.resolve(strict=True), sidecar.resolve(strict=True))
    if receipt_path.resolve() != Path(plan["output"]["worker_receipt"]).resolve():
        raise ValueError("PickCube R3 worker receipt path differs from the frozen plan")
    run_dir = Path(plan["output"]["run_dir"]).resolve(strict=True)
    if counter_path.resolve() != run_dir / "step_counter.json":
        raise ValueError("PickCube R3 step counter differs from the frozen plan")
    env = PickCubeReferenceEnv.from_reference_config({
        "provider": plan["provider"], "backend": "cpu", "horizon": 301,
        "controller_profile": "r3_continuous_v1",
    })
    episodes = []
    source_joint_diagnostics = []
    address_failure_details = None
    failure = None
    try:
        if not isinstance(env.controller, ProductionCanonicalPandaControllerR3):
            raise TypeError("PickCube public opt-in did not construct Production R3")
        if env.value["resolved_configuration"].get("controller_profile") != "r3_continuous_v1":
            raise ValueError("PickCube resolved configuration does not identify R3 continuous")
        if plan["provider"] == "mujoco":
            source_joint_diagnostics = _inspect_mujoco_source_joint_types(env.value["source"])
        actuator_law = _actuator_law(env.value["source"].scene_source.xml)
        for index in (1, 2):
            episodes.append(_run_episode(env, plan, index, counter_path, actuator_law))
    except BaseException as error:
        failure = error
        if plan["provider"] == "mujoco":
            address_failure_details = _mujoco_address_failure_details(error)
    finally:
        try:
            env.close()
        except BaseException as close_error:
            if failure is None:
                failure = close_error
            elif callable(getattr(failure, "add_note", None)):
                failure.add_note(f"PickCube R3 env.close also failed: {close_error!r}")
    counter = json.loads(counter_path.read_text(encoding="utf-8"))
    receipt = {
        "schema_version": "f05-dg02-pickcube-r3-control-receipt-v1",
        "run_id": plan["run_id"],
        "plan_sha256": digest,
        "classification": plan["classification"],
        "provider": plan["provider"],
        "oracle": plan["oracle"],
        "native_starts": 1,
        "physics_steps_attempted": counter["attempted_physics_steps"],
        "physics_steps_completed": counter["completed_physics_steps"],
        "source_actuator8_law": episodes[0]["source_actuator8_law"] if episodes else None,
        "source_joint_diagnostics": source_joint_diagnostics,
        "address_failure_details": address_failure_details,
        "episodes": episodes,
        "status": "PASS_PICKCUBE_R3_MATCHED_CONTROL" if failure is None else "FAIL_PICKCUBE_R3_CONTROL",
    }
    if failure is not None:
        receipt["failure"] = f"{type(failure).__name__}: {failure}"
        receipt["traceback"] = "".join(traceback.format_exception(failure))
    _atomic_json(receipt_path, receipt)
    if failure is not None:
        raise failure
    return receipt


def compare(geophys_path: Path, mujoco_path: Path, output: Path) -> dict:
    from task_env.trajectory.canonical.h5 import load as load_canonical_h5

    geo = json.loads(geophys_path.read_text(encoding="utf-8"))
    mujoco = json.loads(mujoco_path.read_text(encoding="utf-8"))
    if geo["provider"] != "geophys" or mujoco["provider"] != "mujoco":
        raise ValueError("PickCube R3 comparison requires one GeoPhys and one MuJoCo receipt")
    if geo["status"] != "PASS_PICKCUBE_R3_MATCHED_CONTROL" or mujoco["status"] != "PASS_PICKCUBE_R3_MATCHED_CONTROL":
        raise ValueError("PickCube R3 comparison refuses incomplete provider receipts")
    control_oracle = json.loads((PACKAGE / "control_oracles.json").read_text(encoding="utf-8"))
    initial_state_atol = float(control_oracle["normalization"]["numeric_f64_abs_tolerance"])
    rows = []
    strict_initial_state_match = True
    strict_target_trajectory_match = True
    for egeo, emj in zip(geo["episodes"], mujoco["episodes"], strict=True):
        if (egeo["transition_count"], emj["transition_count"]) != (300, 300):
            raise ValueError("PickCube R3 comparison requires all frozen 300-interval episodes")
        if (egeo["source_xml_sha256"] != emj["source_xml_sha256"]
                or egeo["controller_class"] != emj["controller_class"]
                or egeo["controller_profile"] != emj["controller_profile"]
                or egeo["timebase"] != emj["timebase"]):
            raise ValueError("PickCube R3 model/profile/timebase identities do not match")
        if (egeo["sample_id"] != emj["sample_id"]
                or egeo["task_seed"] != emj["task_seed"]
                or egeo["task_artifact_identity_sha256"] != emj["task_artifact_identity_sha256"]):
            raise ValueError("PickCube R3 providers did not consume the same reset sample and Task Artifact")
        q_geo = egeo["reset"]["joint_position_rad"]
        q_mj = emj["reset"]["joint_position_rad"]
        dq_geo = egeo["reset"]["joint_velocity_rad_s"]
        dq_mj = emj["reset"]["joint_velocity_rad_s"]
        state_checks = {}
        for name, group_geo, group_mj in (("joint_position", q_geo, q_mj),
                                           ("joint_velocity", dq_geo, dq_mj)):
            if group_geo.keys() != group_mj.keys():
                raise ValueError(f"PickCube R3 provider {name} semantic keys do not match")
            delta = np.asarray(list(group_geo.values()), dtype=float) - np.asarray(
                list(group_mj.values()), dtype=float)
            matched = bool(np.allclose(delta, 0.0, rtol=0.0, atol=initial_state_atol))
            state_checks[f"{name}_match_within_numeric_f64_atol"] = matched
            state_checks[f"{name}_max_abs_delta"] = float(np.max(np.abs(delta))) if delta.size else 0.0
        for name, field in (("tcp_position", "position_m"),
                            ("tcp_orientation", "quaternion_wxyz")):
            left = np.asarray(egeo["reset"]["tcp_pose_world"][field], dtype=float)
            right = np.asarray(emj["reset"]["tcp_pose_world"][field], dtype=float)
            delta = left - right
            matched = bool(np.allclose(delta, 0.0, rtol=0.0, atol=initial_state_atol))
            state_checks[f"{name}_match_within_numeric_f64_atol"] = matched
            state_checks[f"{name}_max_abs_delta"] = float(np.max(np.abs(delta))) if delta.size else 0.0
        state_checks["sample_identity_match"] = True
        state_checks["atol"] = initial_state_atol
        episode_state_match = all(
            value for key, value in state_checks.items()
            if key.endswith("_match_within_numeric_f64_atol")
        )
        state_checks["strict_realized_initial_state_match"] = episode_state_match
        strict_initial_state_match = strict_initial_state_match and episode_state_match
        target_geo = np.asarray([x["requested_tcp_pose_world"]["position_m"] + x["requested_tcp_pose_world"]["quaternion_wxyz"] for x in egeo["transitions"]])
        target_mj = np.asarray([x["requested_tcp_pose_world"]["position_m"] + x["requested_tcp_pose_world"]["quaternion_wxyz"] for x in emj["transitions"]])
        target_delta = target_geo - target_mj
        target_match = bool(np.allclose(target_delta, 0.0, rtol=0.0, atol=initial_state_atol))
        strict_target_trajectory_match = strict_target_trajectory_match and target_match
        state_checks["requested_tcp_trajectory_match_within_numeric_f64_atol"] = target_match
        state_checks["requested_tcp_trajectory_max_abs_delta"] = float(np.max(np.abs(target_delta)))
        grip_geo = np.asarray([x["requested_gripper_normalized"] for x in egeo["transitions"]])
        grip_mj = np.asarray([x["requested_gripper_normalized"] for x in emj["transitions"]])
        if not np.array_equal(grip_geo, grip_mj):
            raise ValueError("PickCube R3 providers did not receive an identical gripper schedule")
        for episode in (egeo, emj):
            h5_path = Path(episode["h5_path"]).resolve(strict=True)
            if _sha(h5_path) != episode["h5_sha256"]:
                raise ValueError("PickCube R3 H5 artifact hash differs from the worker receipt")
            trajectory = load_canonical_h5(h5_path)
            if (len(trajectory.transitions), len(trajectory.boundaries)) != (300, 301):
                raise ValueError("independent PickCube R3 H5 cold reader rejected T/T+1")
        def stats(episode):
            error = np.asarray([x["tcp_tracking_error"]["position_error_world_m"] for x in episode["transitions"]], dtype=float)
            norms = np.linalg.norm(error, axis=1)
            angular = np.asarray([x["tcp_tracking_error"]["orientation_error_rad"] for x in episode["transitions"]])
            joint_error = np.asarray([[x["joint_target_error_rad"][name] for name in ARM_NAMES]
                                      for x in episode["transitions"]], dtype=float)
            raw_samples = [x["provider_actuator_force_measurement"] for x in episode["transitions"]
                           if isinstance(x["provider_actuator_force_measurement"], dict)]
            raw_saturated = 0
            for sample in raw_samples:
                limits = sample.get("source_actuator_force_range_N")
                measured_force = sample.get("signed_force_N")
                if limits is not None and measured_force is not None:
                    raw_saturated += int(float(measured_force) <= float(limits[0]) + 1e-6
                                         or float(measured_force) >= float(limits[1]) - 1e-6)
            raw_controls = [abs(float(sample["actuator_ctrl"])) for sample in raw_samples
                            if sample.get("actuator_ctrl") is not None]
            phase_stats = {}
            for phase in ("unloaded_home_hold", "unloaded_point_and_hold", "unloaded_return_and_hold",
                          "gripper_close_at_home", "gripper_open_at_home", "final_cartesian_hold"):
                phase_spec = next(x for x in geo["oracle"]["phases"] if x["phase"] == phase)
                selected = [i for i, row in enumerate(episode["transitions"])
                            if int(row["interval"]) >= int(phase_spec["stop"]) - int(phase_spec["measure_last"])
                            and int(row["interval"]) < int(phase_spec["stop"])]
                phase_norm = norms[selected]
                phase_angle = angular[selected]
                phase_joint = joint_error[selected]
                phase_stats[phase] = {
                    "sample_count": len(selected),
                    "tcp_position_error_rmse_m": float(np.sqrt(np.mean(phase_norm ** 2))),
                    "tcp_position_error_max_m": float(np.max(phase_norm)),
                    "tcp_orientation_error_rmse_rad": float(np.sqrt(np.mean(phase_angle ** 2))),
                    "tcp_orientation_error_max_rad": float(np.max(phase_angle)),
                    "joint_target_error_rmse_rad_by_joint": np.sqrt(np.mean(phase_joint ** 2, axis=0)).tolist(),
                    "joint_target_error_max_abs_rad_by_joint": np.max(np.abs(phase_joint), axis=0).tolist(),
                    "clipped_intervals": int(sum(bool(episode["transitions"][i]["canonical_control_application"]["applied"]["clipped"]) for i in selected)),
                }
            return {"tcp_position_error_rmse_m": float(np.sqrt(np.mean(norms ** 2))),
                    "tcp_position_error_max_m": float(np.max(norms)),
                    "tcp_position_error_bias_world_m": np.mean(error, axis=0).tolist(),
                    "tcp_position_error_jitter_rms_m": float(np.sqrt(np.mean((norms - np.mean(norms)) ** 2))),
                    "tcp_orientation_error_rmse_rad": float(np.sqrt(np.mean(angular ** 2))),
                    "tcp_orientation_error_max_rad": float(np.max(angular)),
                    "clipped_intervals": int(sum(bool(x["canonical_control_application"]["applied"]["clipped"]) for x in episode["transitions"])),
                    "raw_actuator_force_samples": len(raw_samples),
                    "raw_actuator_force_saturated_samples": int(raw_saturated),
                    "raw_actuator_ctrl_abs_max": float(max(raw_controls)) if raw_controls else None,
                    "last10_of_each50_interval_phase": phase_stats}
        rows.append({"episode": egeo["episode"], "realized_initial_state_comparison": state_checks,
                     "geophys": stats(egeo), "mujoco": stats(emj)})
    result = {
        "schema_version": "f05-dg02-pickcube-r3-control-comparison-v1",
        "status": ("PASS_STRICT_REALIZED_STATE_AND_TARGET_MATCH"
                   if strict_initial_state_match and strict_target_trajectory_match
                   else "PARTIAL_REALIZED_STATE_OR_TARGET_MISMATCH"),
        "classification": "diagnostic matched R3 reset-sample/control-schedule comparison; realized initial-state threshold is reported without relaxation; not trajectory equivalence or qualification",
        "geophys_receipt_sha256": _sha(geophys_path),
        "mujoco_receipt_sha256": _sha(mujoco_path),
        "matched_control_intervals": 2 * 300,
        "matched_physics_steps_per_provider": 3000,
        "initial_state_match_atol": initial_state_atol,
        "same_reset_sample_artifact_and_seed": True,
        "strict_realized_initial_state_match": strict_initial_state_match,
        "requested_tcp_trajectory_identical": strict_target_trajectory_match,
        "requested_tcp_trajectory_match_within_numeric_f64_atol": strict_target_trajectory_match,
        "source_xml_identical": True,
        "controller_method": "ProductionCanonicalPandaControllerR3 / r3_continuous_v1",
        "episodes": rows,
        "limits": "Original control oracles unchanged; this is diagnostic comparison evidence only.",
    }
    _atomic_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-plan", action="store_true")
    parser.add_argument("--provider", choices=("geophys", "mujoco"))
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-sha256", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--counter", type=Path)
    parser.add_argument("--compare-geophys", type=Path)
    parser.add_argument("--compare-mujoco", type=Path)
    parser.add_argument("--comparison-output", type=Path)
    args = parser.parse_args()
    if args.freeze_plan:
        if not args.provider or not args.run_dir:
            parser.error("--freeze-plan requires --provider and --run-dir")
        plan, plan_path, sidecar = freeze_plan(args.provider, args.run_dir)
        _atomic_json(plan_path, plan)
        digest = _sha(plan_path)
        sidecar.write_text(digest + "\n", encoding="ascii")
        print(json.dumps({"status": "FROZEN_PICKCUBE_R3_CONTROL_PLAN", "plan_path": str(plan_path), "plan_sha256": digest, "run_id": plan["run_id"], "physics_steps_reserved": plan["limits"]["physics_steps_reserved"]}, indent=2))
        return 0
    if args.compare_geophys or args.compare_mujoco or args.comparison_output:
        if not (args.compare_geophys and args.compare_mujoco and args.comparison_output):
            parser.error("comparison requires both provider receipts and --comparison-output")
        print(json.dumps(compare(args.compare_geophys, args.compare_mujoco, args.comparison_output), indent=2, allow_nan=False))
        return 0
    if not (args.plan and args.plan_sha256 and args.receipt and args.counter):
        parser.error("worker mode requires --plan, --plan-sha256, --receipt, and --counter")
    print(json.dumps(run(args.plan, args.plan_sha256, args.receipt, args.counter), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
