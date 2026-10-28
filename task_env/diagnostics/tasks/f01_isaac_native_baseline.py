"""Bounded Isaac Sim 6.2 Panda + free-body baseline for Phase II-01 F01.

The module itself is provider-free. Isaac imports are lazy and occur only in
``NativeDriver.open`` after the supervisor has reserved an App start and
acquired the shared native lock.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import traceback
from typing import Any, Callable


SCHEMA = "geochora-f01-isaac-native-baseline-v1"
RESULT_NAME = "native_result.json"
TRACE_NAME = "native_trace.jsonl"
DT = 1.0 / 120.0
ROUNDS = 2
STEPS_PER_ROUND = 240
MAX_PHYSICS_STEPS = 1200
MAX_SIMULATION_SECONDS = 10.0
ARM_JOINT = "panda_joint1"
ROBOT_PATH = "/World/robot"
GROUND_PATH = "/World/ground_plane"
CUBE_PATH = "/World/f01_cube"
CUBE_POSITION = (0.8, 0.0, 0.25)
CUBE_ORIENTATION_WXYZ = (1.0, 0.0, 0.0, 0.0)
CUBE_EDGE_M = 0.05
CUBE_MASS_KG = 0.08
ARM_TARGET_DELTA_RAD = 0.1
RESET_POSITION_TOLERANCE = 1e-4
RESET_VELOCITY_TOLERANCE = 1e-4
TIME_TOLERANCE = 1e-5


def default_plan() -> dict[str, Any]:
    """Return the package-frozen recipe. Callers cannot override physics gates."""
    return {
        "schema": "geochora-f01-isaac-native-plan-v1",
        "application": {
            "headless": True,
            "renderer": "MinimalRendering",
            "fast_shutdown": False,
            "limit_cpu_threads": 1,
            "disable_viewport_updates": True,
            "enable_crashreporter": False,
            "multi_gpu": False,
            "max_gpu_count": 1,
        },
        "robot": {
            "name": "franka",
            "prim_path": ROBOT_PATH,
            "asset_path": "/Isaac/Robots_Multiphysics/FrankaRobotics/FrankaPanda/franka/franka.usda",
            "variants": {"Gripper": "alternatefinger", "Mesh": "performance"},
            "selected_joint": ARM_JOINT,
            "target_delta_rad": ARM_TARGET_DELTA_RAD,
        },
        "scene": {
            "physics_engine": "PhysX",
            "physics_device": "cpu",
            "gpu_dynamics": False,
            "dt_seconds": DT,
            "stage_meters_per_unit": 1.0,
            "stage_up_axis": "Z",
            "ground_path": GROUND_PATH,
            "ground_visual_template": None,
            "cube_path": CUBE_PATH,
            "cube_edge_m": CUBE_EDGE_M,
            "cube_mass_kg": CUBE_MASS_KG,
            "cube_position_m": list(CUBE_POSITION),
            "cube_orientation_wxyz": list(CUBE_ORIENTATION_WXYZ),
            "rounds": ROUNDS,
            "steps_per_round": STEPS_PER_ROUND,
            "phase_steps": [60, 60, 60, 60],
        },
        "limits": {
            "max_physics_steps": MAX_PHYSICS_STEPS,
            "max_simulation_seconds": MAX_SIMULATION_SECONDS,
            "max_process_wall_seconds": 900,
            "max_asset_transfer_bytes": 2 * 1024**3,
            "reset_position_tolerance": RESET_POSITION_TOLERANCE,
            "reset_velocity_tolerance": RESET_VELOCITY_TOLERANCE,
            "time_tolerance": TIME_TOLERANCE,
            "min_selected_joint_motion_rad": 0.04,
            "max_final_home_error_rad": 0.05,
            "min_cube_drop_m": 0.05,
            "final_cube_center_z_m": [0.015, 0.04],
            "joint_limit_tolerance": 1e-4,
        },
    }


def _strict_json_value(value: Any, warnings: list[dict[str, str]] | None = None, path: str = "$") -> Any:
    """Convert NumPy/Warp-like values to strict JSON without emitting NaN/Infinity."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        if warnings is not None:
            warnings.append({"path": path, "value": repr(value), "reason": "non_finite_number"})
        return {"non_finite": repr(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _strict_json_value(v, warnings, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strict_json_value(v, warnings, f"{path}[{i}]") for i, v in enumerate(value)]
    if hasattr(value, "tolist"):
        return _strict_json_value(value.tolist(), warnings, path)
    if hasattr(value, "item"):
        return _strict_json_value(value.item(), warnings, path)
    if hasattr(value, "value") and isinstance(value.value, (str, int, float)):
        return _strict_json_value(value.value, warnings, path)
    raise TypeError(f"unsupported strict JSON value at {path}: {type(value).__name__}")


def _write_json_new(path: Path, value: Any) -> None:
    """Atomically create a JSON file and refuse to replace any existing evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    warnings: list[dict[str, str]] = []
    normalized = _strict_json_value(value, warnings)
    if warnings and isinstance(normalized, dict):
        normalized.setdefault("serialization_warnings", []).extend(warnings)
    payload = json.dumps(normalized, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _replace_json(path: Path, value: Any) -> None:
    """Atomically replace an owned progress snapshot (never a final receipt)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    payload = json.dumps(_strict_json_value(value), sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_installation() -> dict[str, Any]:
    """Metadata-only preflight; this function never imports Isaac or a provider."""
    expected = {
        "isaacsim": "6.2.0.0",
        "isaacsim-core": "6.2.0.0",
        "isaacsim-extscache-kit": "6.2.0.0",
        "torch": "2.11.0+cu128",
        "numpy": "2.3.1",
    }
    found: dict[str, str | None] = {}
    errors: list[str] = []
    for distribution, expected_version in expected.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        found[distribution] = actual
        if actual != expected_version:
            errors.append(f"{distribution}: expected {expected_version}, found {actual}")
    forbidden = [name for name in sys.modules if name.startswith(("omni", "pxr", "isaacsim", "mujoco", "torch"))]
    return {
        "schema": "f01-install-metadata-check-v1",
        "python": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "packages": found,
        "expected_packages_match": not errors,
        "errors": errors,
        "forbidden_imports_loaded": forbidden,
        "provider_free": not forbidden,
    }


class JsonlTrace:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.stream = self.path.open("x", encoding="utf-8", buffering=1)
        self.rows = 0

    def write(self, row: dict[str, Any]) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        value = _strict_json_value(row, warnings)
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.stream.write(payload + "\n")
        self.rows += 1
        if self.rows % 20 == 0:
            self.stream.flush()
            os.fsync(self.stream.fileno())
        return warnings

    def flush(self) -> None:
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self) -> None:
        if not self.stream.closed:
            self.flush()
            self.stream.close()


def _failure(exc: BaseException, stage: str) -> dict[str, str]:
    return {"stage": stage, "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}


def _finite_vector(values: Any, length: int) -> bool:
    return isinstance(values, list) and len(values) == length and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)) for v in values
    )


def _quat_rotation_error(q: list[float], expected: list[float]) -> float:
    if not _finite_vector(q, 4) or not _finite_vector(expected, 4):
        return math.inf
    qn = math.sqrt(sum(float(x) ** 2 for x in q))
    en = math.sqrt(sum(float(x) ** 2 for x in expected))
    if qn == 0 or en == 0:
        return math.inf
    dot = abs(sum((float(a) / qn) * (float(b) / en) for a, b in zip(q, expected)))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def _worker_reset_checks(state: dict[str, Any], home: dict[str, float], plan: dict[str, Any]) -> dict[str, Any]:
    tol = plan["limits"]["reset_position_tolerance"]
    vtol = plan["limits"]["reset_velocity_tolerance"]
    q = state.get("joint_positions", {})
    qd = state.get("joint_velocities", {})
    targets = state.get("position_targets", {})
    vtargets = state.get("velocity_targets", {})
    def error(mapping: Any, key: str, expected: float | None = None) -> float:
        if not isinstance(mapping, dict) or not _finite_vector([mapping.get(key)], 1):
            return math.inf
        value = float(mapping[key])
        return abs(value) if expected is None else abs(value - expected)

    joint_pos_err = max((error(q, k, v) for k, v in home.items()), default=math.inf)
    target_err = max((error(targets, k, v) for k, v in home.items()), default=math.inf)
    joint_vel_max = max((error(qd, k) for k in home), default=math.inf)
    vel_target_max = max((error(vtargets, k) for k in home), default=math.inf)
    cube_pos = state.get("cube_position_m")
    cube_quat = state.get("cube_orientation_wxyz")
    cube_lin = state.get("cube_linear_velocity_m_s")
    cube_ang = state.get("cube_angular_velocity_rad_s")
    cube_pos_err = math.inf if not _finite_vector(cube_pos, 3) else max(abs(float(a) - b) for a, b in zip(cube_pos, CUBE_POSITION))
    cube_lin_max = math.inf if not _finite_vector(cube_lin, 3) else max(abs(float(v)) for v in cube_lin)
    cube_ang_max = math.inf if not _finite_vector(cube_ang, 3) else max(abs(float(v)) for v in cube_ang)
    cube_rotation_err = _quat_rotation_error(cube_quat, list(CUBE_ORIENTATION_WXYZ))
    return {
        "joint_position_error_rad_or_m": joint_pos_err,
        "position_target_error_rad_or_m": target_err,
        "joint_velocity_max_rad_s_or_m_s": joint_vel_max,
        "velocity_target_max_rad_s_or_m_s": vel_target_max,
        "cube_position_error_m": cube_pos_err,
        "cube_rotation_error_rad": cube_rotation_err,
        "cube_linear_velocity_max_m_s": cube_lin_max,
        "cube_angular_velocity_max_rad_s": cube_ang_max,
        "joint_positions": joint_pos_err <= tol,
        "position_targets_cleared_to_home": target_err <= tol,
        "joint_velocities_zero": joint_vel_max <= vtol,
        "velocity_targets_zero": vel_target_max <= vtol,
        "cube_position": cube_pos_err <= 1e-5,
        "cube_orientation": cube_rotation_err <= 1e-4,
        "cube_velocity_zero": cube_lin_max <= 1e-6 and cube_ang_max <= 1e-6,
    }


def _worker_round_checks(rows: list[dict[str, Any]], reset_state: dict[str, Any], home: dict[str, float],
                         lower: dict[str, float], upper: dict[str, float], plan: dict[str, Any]) -> dict[str, Any]:
    limits = plan["limits"]
    dt = plan["scene"]["dt_seconds"]
    selected = plan["robot"]["selected_joint"]
    if len(rows) != STEPS_PER_ROUND:
        return {"step_count": False, "count": len(rows)}
    clock_ok = True
    step_indices_ok = True
    all_finite = True
    limits_ok = True
    targets_ok = True
    previous_index = reset_state.get("physics_index")
    previous_time = reset_state.get("simulation_time_s")
    selected_values = []
    for i, row in enumerate(rows, start=1):
        state = row["state"]
        index = state.get("physics_index")
        sim_time = state.get("simulation_time_s")
        if type(index) is not int or type(previous_index) is not int or index - previous_index != 1:
            step_indices_ok = False
        if not isinstance(sim_time, (int, float)) or not isinstance(previous_time, (int, float)):
            clock_ok = False
        elif abs((float(sim_time) - float(previous_time)) - dt) > limits["time_tolerance"]:
            clock_ok = False
        q = state.get("joint_positions", {})
        qd = state.get("joint_velocities", {})
        targets = state.get("position_targets", {})
        expected_target = home[selected] + _target_delta(i, home[selected], plan["robot"]["target_delta_rad"])
        if not _finite_vector([row.get("commanded_target_rad")], 1) or abs(float(row["commanded_target_rad"]) - expected_target) > 1e-8:
            targets_ok = False
        if (not isinstance(targets, dict) or set(targets) != set(home)
                or not _finite_vector([targets.get(selected)], 1)
                or abs(float(targets[selected]) - expected_target) > 1e-4
                or any(not _finite_vector([targets.get(name)], 1) or abs(float(targets[name]) - home[name]) > 1e-4
                       for name in home if name != selected)):
            targets_ok = False
        if not isinstance(q, dict) or set(q) != set(home) or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(float(v)) for v in q.values()):
            all_finite = False
        if not isinstance(qd, dict) or set(qd) != set(home) or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(float(v)) for v in qd.values()):
            all_finite = False
        for name, value in (q.items() if isinstance(q, dict) else []):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                continue
            if name in lower and (float(value) < lower[name] - limits["joint_limit_tolerance"]
                                  or float(value) > upper[name] + limits["joint_limit_tolerance"]):
                limits_ok = False
        selected_value = q.get(selected) if isinstance(q, dict) else None
        selected_values.append(float(selected_value) if isinstance(selected_value, (int, float)) and not isinstance(selected_value, bool) else math.nan)
        previous_index, previous_time = index, sim_time
    motion = max(selected_values) - min(selected_values) if selected_values and all(map(math.isfinite, selected_values)) else 0.0
    final_error = abs(selected_values[-1] - home[selected]) if selected_values and math.isfinite(selected_values[-1]) else math.inf
    start_cube_z = float(reset_state.get("cube_position_m", [math.nan] * 3)[2])
    end_cube = rows[-1]["state"].get("cube_position_m", [math.nan] * 3)
    end_z = float(end_cube[2]) if _finite_vector(end_cube, 3) else math.nan
    drop = start_cube_z - end_z
    quaternion = rows[-1]["state"].get("cube_orientation_wxyz")
    velocity = rows[-1]["state"].get("cube_linear_velocity_m_s")
    angular_velocity = rows[-1]["state"].get("cube_angular_velocity_rad_s")
    quat_norm = math.sqrt(sum(float(v) ** 2 for v in quaternion)) if _finite_vector(quaternion, 4) else math.nan
    return {
        "step_count": True,
        "physics_indices_contiguous": step_indices_ok,
        "clock_dt_consistent": clock_ok,
        "all_joint_state_finite": all_finite,
        "joint_limits": limits_ok,
        "commanded_targets_match_recipe": targets_ok,
        "selected_joint_motion_rad": motion,
        "selected_joint_motion": motion >= limits["min_selected_joint_motion_rad"],
        "final_home_error_rad": final_error,
        "final_home": final_error <= limits["max_final_home_error_rad"],
        "cube_drop_m": drop,
        "cube_dropped": math.isfinite(drop) and drop >= limits["min_cube_drop_m"],
        "final_cube_center_z_m": end_z,
        "cube_final_height": math.isfinite(end_z) and limits["final_cube_center_z_m"][0] <= end_z <= limits["final_cube_center_z_m"][1],
        "final_cube_pose_finite": _finite_vector(end_cube, 3) and _finite_vector(quaternion, 4),
        "final_cube_quaternion_unit": math.isfinite(quat_norm) and abs(quat_norm - 1.0) <= 1e-3,
        "final_cube_velocity_finite": _finite_vector(velocity, 3) and _finite_vector(angular_velocity, 3),
    }


def _target_delta(step: int, home: float, delta: float) -> float:
    if step <= 60:
        return delta * (step / 60.0)
    if step <= 120:
        return delta
    if step <= 180:
        return delta * (1.0 - (step - 120) / 60.0)
    return 0.0


def _initial_report(run_dir: Path, evidence_kind: str, run_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "evidence_kind": evidence_kind,
        "status": "INCOMPLETE",
        "pass": False,
        "stage": "preflight",
        "app_start_attempts": 0,
        "app_close_attempts": 0,
        "app_closed": False,
        "timeline_stop_attempts": 0,
        "callbacks_registered": 0,
        "callbacks_deregistered": 0,
        "physics_steps_at_start": None,
        "physics_steps_at_end": None,
        "total_physics_steps": 0,
        "simulation_time_start_s": None,
        "simulation_time_end_s": None,
        "total_simulation_time_s": 0.0,
        "bootstrap": [],
        "rounds": [],
        "asset_inventory": None,
        "scene_identity": None,
        "worker_error": None,
        "cleanup_errors": [],
        "serialization_warnings": [],
        "trace_rows": 0,
        "trace_sha256": None,
        "started_monotonic": time.monotonic(),
        "finished_monotonic": None,
    }


def run_worker(run_dir: Path, plan: dict[str, Any], *, driver_factory: Callable[..., Any],
               evidence_kind: str = "real_native", result_writer: Callable[[Path, Any], None] = _write_json_new) -> dict[str, Any]:
    """Run the shared worker lifecycle with an injected App/physics driver."""
    run_dir = Path(run_dir).resolve()
    result_path = run_dir / RESULT_NAME
    trace_path = run_dir / TRACE_NAME
    if not run_dir.is_dir():
        return {"exit_code": 2, "error": "run_directory_missing", "path": str(run_dir)}
    progress_path = run_dir / "progress.json"
    if result_path.exists() or trace_path.exists() or progress_path.exists():
        return {"exit_code": 2, "error": "existing_output_refused", "result": result_path.exists(),
                "trace": trace_path.exists(), "progress": progress_path.exists()}
    run_id = str(plan.get("run_id", run_dir.name))
    report = _initial_report(run_dir, evidence_kind, run_id)
    trace: JsonlTrace | None = None
    driver: Any = None
    stage_name = "trace_open"
    primary_error: BaseException | None = None

    def mark_stage(value: str) -> None:
        nonlocal stage_name
        stage_name = value
        report["stage"] = value

    try:
        mark_stage("trace_open")
        trace = JsonlTrace(trace_path)
        mark_stage("driver_construct")
        driver = driver_factory(plan, report)
        mark_stage("app_start")
        report["app_start_attempts"] = 1
        driver.open()
        mark_stage("scene_prepare")
        prepared = driver.prepare()
        report["asset_inventory"] = prepared.get("asset_inventory")
        report["scene_identity"] = prepared.get("scene_identity")
        report["bootstrap"] = prepared.get("bootstrap", [])
        report["physics_steps_at_start"] = prepared.get("physics_steps_at_start")
        report["simulation_time_start_s"] = prepared.get("simulation_time_start_s")
        home = {str(k): float(v) for k, v in prepared["home_positions"].items()}
        lower = {str(k): float(v) for k, v in prepared["joint_lower_limits"].items()}
        upper = {str(k): float(v) for k, v in prepared["joint_upper_limits"].items()}
        selected = plan["robot"]["selected_joint"]
        if selected not in home or abs(home[selected] - 0.012) > 1e-8:
            raise RuntimeError(f"configured Panda selected-joint home mismatch: {selected}={home.get(selected)}")
        if len(home) != 9 or "panda_finger_joint1" not in home or "panda_finger_joint2" not in home:
            raise RuntimeError(f"unexpected configured DOF inventory: {sorted(home)}")
        report["home_positions"] = home
        report["joint_lower_limits"] = lower
        report["joint_upper_limits"] = upper
        _write_progress(run_dir, report)
        total_baseline_index = int(prepared.get("physics_steps_at_start", 0))
        total_baseline_time = float(prepared.get("simulation_time_start_s", 0.0))
        for round_index in range(1, ROUNDS + 1):
            mark_stage(f"round_{round_index}_view_refresh" if round_index == 2 else "round_1_reset")
            if round_index == 2:
                refresh = driver.refresh_views()
                report["bootstrap"].append(refresh)
            mark_stage(f"round_{round_index}_reset")
            reset_state = driver.reset(home, plan)
            reset_checks = _worker_reset_checks(reset_state, home, plan)
            reset_row = {"event": "round_reset", "round": round_index, "state": reset_state, "checks": reset_checks}
            report["serialization_warnings"].extend(trace.write(reset_row))
            round_doc = {
                "round": round_index,
                "reset": reset_row,
                "steps": [],
                "checks": {},
                "expected_step_count": STEPS_PER_ROUND,
                "view_refresh": round_index == 2,
            }
            report["rounds"].append(round_doc)
            if not all(v is True for v in reset_checks.values() if isinstance(v, bool)):
                raise RuntimeError(f"round {round_index} pre-step reset checks failed: {reset_checks}")
            previous = reset_state
            for step_index in range(1, STEPS_PER_ROUND + 1):
                mark_stage(f"round_{round_index}_step_{step_index}")
                target = home[selected] + _target_delta(step_index, home[selected], float(plan["robot"]["target_delta_rad"]))
                driver.set_selected_joint_target(selected, target)
                driver.step()
                state = driver.read_state()
                step_row = {
                    "event": "physics_step",
                    "round": round_index,
                    "round_step": step_index,
                    "commanded_target_rad": target,
                    "state": state,
                }
                report["serialization_warnings"].extend(trace.write(step_row))
                round_doc["steps"].append(step_row)
                report["trace_rows"] = trace.rows
                report["total_physics_steps"] = int(state["physics_index"]) - total_baseline_index
                report["total_simulation_time_s"] = float(state["simulation_time_s"]) - total_baseline_time
                previous = state
                if report["total_physics_steps"] > MAX_PHYSICS_STEPS:
                    raise RuntimeError("physics step budget exceeded")
                if report["total_simulation_time_s"] > MAX_SIMULATION_SECONDS + TIME_TOLERANCE:
                    raise RuntimeError("simulation time budget exceeded")
                if step_index % 20 == 0:
                    _write_progress(run_dir, report)
            round_doc["checks"] = _worker_round_checks(round_doc["steps"], reset_state, home, lower, upper, plan)
            if not all(v is True for v in round_doc["checks"].values() if isinstance(v, bool)):
                raise RuntimeError(f"round {round_index} gates failed: {round_doc['checks']}")
    except BaseException as exc:
        primary_error = exc
        report["worker_error"] = _failure(exc, stage_name)
    finally:
        if driver is not None:
            try:
                mark_stage("native_stop_cleanup")
                driver.stop()
            except BaseException as exc:
                report["cleanup_errors"].append(_failure(exc, "native_stop_cleanup"))
            try:
                mark_stage("app_close")
                report["app_close_attempts"] = int(getattr(driver, "app_close_attempts", 0))
                driver.close()
                report["app_close_attempts"] = int(getattr(driver, "app_close_attempts", report["app_close_attempts"]))
                report["app_closed"] = bool(getattr(driver, "app_closed", True))
            except BaseException as exc:
                report["app_close_attempts"] = int(getattr(driver, "app_close_attempts", report["app_close_attempts"]))
                report["app_closed"] = False
                report["cleanup_errors"].append(_failure(exc, "app_close"))
            report["timeline_stop_attempts"] = int(getattr(driver, "timeline_stop_attempts", 0))
            report["callbacks_registered"] = int(getattr(driver, "callbacks_registered", 0))
            report["callbacks_deregistered"] = int(getattr(driver, "callbacks_deregistered", 0))
            try:
                counters = driver.final_counters()
                report["physics_steps_at_end"] = counters.get("physics_index")
                if report["physics_steps_at_start"] is not None and report["physics_steps_at_end"] is not None:
                    report["total_physics_steps"] = int(report["physics_steps_at_end"]) - int(report["physics_steps_at_start"])
                report["simulation_time_end_s"] = counters.get("simulation_time_s")
                if report["simulation_time_start_s"] is not None and report["simulation_time_end_s"] is not None:
                    report["total_simulation_time_s"] = float(report["simulation_time_end_s"]) - float(report["simulation_time_start_s"])
            except BaseException as exc:
                report["cleanup_errors"].append(_failure(exc, "final_counters"))
        if trace is not None:
            try:
                trace.close()
                report["trace_rows"] = trace.rows
                report["trace_sha256"] = _sha256(trace_path) if trace_path.exists() else None
            except BaseException as exc:
                report["cleanup_errors"].append(_failure(exc, "trace_close"))
        report["finished_monotonic"] = time.monotonic()
        report["worker_wall_seconds"] = report["finished_monotonic"] - report["started_monotonic"]
        report["pass"] = (
            primary_error is None
            and not report["cleanup_errors"]
            and report["app_closed"]
            and report["app_close_attempts"] == 1
            and report["timeline_stop_attempts"] == 1
            and report["app_start_attempts"] == 1
            and report["callbacks_registered"] == 1
            and report["callbacks_deregistered"] == 1
            and report["total_physics_steps"] <= MAX_PHYSICS_STEPS
            and report["total_simulation_time_s"] <= MAX_SIMULATION_SECONDS + TIME_TOLERANCE
            and report["trace_sha256"] is not None
            and len(report["rounds"]) == ROUNDS
            and all(all(v is True for v in r["checks"].values() if isinstance(v, bool)) for r in report["rounds"])
        )
        if report["pass"]:
            report["status"] = "PASS_SYNTHETIC_S1_ONLY" if evidence_kind == "synthetic_fixture" else "PASS_NATIVE_PENDING_READER"
        elif primary_error is not None:
            report["status"] = "FAILED_WORKER"
        else:
            report["status"] = "FAILED_CLEANUP_OR_GATE"
        report["exit_code"] = 0 if report["pass"] else 1
        report["receipt_write_attempted"] = True
        report["receipt_written"] = True
        try:
            result_writer(result_path, report)
        except BaseException as exc:
            report["receipt_written"] = False
            report["final_receipt_error"] = _failure(exc, "final_receipt_write")
            report["exit_code"] = 2
            report["status"] = "FINAL_RECEIPT_WRITE_FAILED"
    return {"exit_code": int(report["exit_code"]), "report": report, "result_path": str(result_path), "trace_path": str(trace_path)}


def _write_progress(run_dir: Path, report: dict[str, Any]) -> None:
    progress = {
        "schema": SCHEMA + ".progress",
        "run_id": report["run_id"],
        "stage": report["stage"],
        "status": report["status"],
        "trace_rows": report["trace_rows"],
        "total_physics_steps": report["total_physics_steps"],
        "total_simulation_time_s": report["total_simulation_time_s"],
        "worker_error": report["worker_error"],
    }
    _replace_json(run_dir / "progress.json", progress)


class FakeApp:
    """Small S1-only App stand-in; never used by the native supervisor."""
    def __init__(self, close_error: BaseException | None = None):
        self.close_error = close_error
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class FakeDriver:
    """Synthetic physics IO for S1; common worker/finalizer code remains real."""
    def __init__(self, plan: dict[str, Any], report: dict[str, Any], *, primary_error: str | None = None,
                 close_error: str | None = None, fail_before_step: bool = False,
                 fail_after_step: int | None = None, nan_state: bool = False):
        self.plan = plan
        self.report = report
        self.primary_error = primary_error
        self.fail_before_step = fail_before_step
        self.fail_after_step = fail_after_step
        self.nan_state = nan_state
        self.app = FakeApp(RuntimeError(close_error) if close_error else None)
        self.app_close_attempts = 0
        self.app_closed = False
        self.timeline_stop_attempts = 0
        self.callbacks_registered = 1
        self.callbacks_deregistered = 0
        self._index = 3
        self._time = self._index * DT
        self._home: dict[str, float] = {}
        self._q: dict[str, float] = {}
        self._qd: dict[str, float] = {}
        self._targets: dict[str, float] = {}
        self._vtargets: dict[str, float] = {}
        self._cube_position = list(CUBE_POSITION)
        self._cube_orientation = list(CUBE_ORIENTATION_WXYZ)
        self._cube_linear_velocity = [0.0, 0.0, 0.0]
        self._cube_angular_velocity = [0.0, 0.0, 0.0]
        self._started_at = 0
        self._stop_called = False
        self._worker_steps = 0

    def open(self) -> None:
        self._started_at = 1

    def prepare(self) -> dict[str, Any]:
        home = {
            "panda_joint1": 0.012, "panda_joint2": -0.568, "panda_joint3": 0.0,
            "panda_joint4": -2.811, "panda_joint5": 0.0, "panda_joint6": 3.037,
            "panda_joint7": 0.741, "panda_finger_joint1": 0.04, "panda_finger_joint2": 0.04,
        }
        self._home = dict(home)
        self.reset_state(home)
        return {
            "asset_inventory": {"kind": "synthetic_fixture", "assets": []},
            "scene_identity": {"kind": "synthetic_fixture", "backend": "fake_physics_io"},
            "home_positions": home,
            "joint_lower_limits": {k: -3.0 for k in home},
            "joint_upper_limits": {k: 3.2 for k in home},
            "physics_steps_at_start": self._index,
            "simulation_time_start_s": self._time,
            "bootstrap": [{"kind": "synthetic_bootstrap", "steps": self._index, "simulation_time_s": self._time}],
        }

    def reset_state(self, home: dict[str, float]) -> None:
        self._home = dict(home)
        self._q = dict(home)
        self._qd = {k: 0.0 for k in home}
        self._targets = dict(home)
        self._vtargets = {k: 0.0 for k in home}
        self._cube_position = list(CUBE_POSITION)
        self._cube_orientation = list(CUBE_ORIENTATION_WXYZ)
        self._cube_linear_velocity = [0.0, 0.0, 0.0]
        self._cube_angular_velocity = [0.0, 0.0, 0.0]

    def reset(self, home: dict[str, float], _plan: dict[str, Any]) -> dict[str, Any]:
        self.reset_state(home)
        return self.read_state()

    def refresh_views(self) -> dict[str, Any]:
        self._index += 1
        self._time += DT
        return {"kind": "synthetic_view_refresh", "physics_steps": 1, "physics_index": self._index, "simulation_time_s": self._time}

    def set_selected_joint_target(self, name: str, value: float) -> None:
        if self.fail_before_step:
            raise RuntimeError("injected ordinary API wiring error before first step")
        if self.primary_error in {"primary", "primary_and_cleanup"}:
            raise RuntimeError("injected primary worker error")
        self._targets[name] = float(value)

    def step(self) -> None:
        self._index += 1
        self._time += DT
        self._worker_steps += 1
        self._q["panda_joint1"] = self._targets["panda_joint1"]
        elapsed = (self._index - 3) * DT
        if elapsed >= 0.25:
            self._cube_position[2] = 0.025
            self._cube_linear_velocity = [0.0, 0.0, 0.0]
        if self.fail_after_step is not None and self._worker_steps >= self.fail_after_step:
            raise RuntimeError("injected worker failure after a measured physics step")

    def read_state(self) -> dict[str, Any]:
        state = {
            "physics_index": self._index,
            "simulation_time_s": self._time,
            "joint_positions": dict(self._q),
            "joint_velocities": dict(self._qd),
            "position_targets": dict(self._targets),
            "velocity_targets": dict(self._vtargets),
            "cube_position_m": list(self._cube_position),
            "cube_orientation_wxyz": list(self._cube_orientation),
            "cube_linear_velocity_m_s": list(self._cube_linear_velocity),
            "cube_angular_velocity_rad_s": list(self._cube_angular_velocity),
        }
        if self.nan_state:
            state["joint_positions"]["panda_joint1"] = math.nan
        return state

    def final_counters(self) -> dict[str, Any]:
        return {"physics_index": self._index, "simulation_time_s": self._time}

    def stop(self) -> None:
        if self._stop_called:
            return
        self._stop_called = True
        self.timeline_stop_attempts += 1
        self.callbacks_deregistered += self.callbacks_registered

    def close(self) -> None:
        self.app_close_attempts += 1
        self.app.close()
        self.app_closed = True


class NativeDriver:
    """Isaac 6.2 implementation of the task-local physics IO boundary."""
    def __init__(self, plan: dict[str, Any], report: dict[str, Any]):
        self.plan = plan
        self.report = report
        self.app = None
        self.app_utils = None
        self.SimulationManager = None
        self.SimulationEvent = None
        self.scenario = None
        self.articulation = None
        self.cube = None
        self.physics_scene = None
        self.stage = None
        self.dof_names: list[str] = []
        self.dof_index: dict[str, int] = {}
        self.home: dict[str, float] = {}
        self.lower: dict[str, float] = {}
        self.upper: dict[str, float] = {}
        self.callback_uid: int | None = None
        self.callbacks_registered = 0
        self.callbacks_deregistered = 0
        self.timeline_stop_attempts = 0
        self.app_close_attempts = 0
        self.app_closed = False
        self._asset_inventory: dict[str, Any] | None = None
        self._scene_identity: dict[str, Any] | None = None
        self._physics_start_index = 0
        self._time_start = 0.0
        self._selected_target = None
        self._prepare_done = False
        self._stop_called = False

    def open(self) -> None:
        from isaacsim.simulation_app import SimulationApp

        self.app = SimulationApp(dict(self.plan["application"]))
        from isaacsim.core.experimental.utils import app as app_utils
        from isaacsim.core.experimental.objects import Cube, GroundPlane
        from isaacsim.core.experimental.prims import Articulation, GeomPrim, RigidPrim
        from isaacsim.core.simulation_manager import SimulationEvent, SimulationManager
        from isaacsim.robot_motion.examples.manipulation import ManipulationScenario
        import omni.usd
        from pxr import UsdGeom

        self.app_utils = app_utils
        self.SimulationManager = SimulationManager
        self.SimulationEvent = SimulationEvent
        if not app_utils.enable_extension("isaacsim.robot_motion.examples"):
            raise RuntimeError("isaacsim.robot_motion.examples extension did not enable")
        app_utils.update_app(steps=1)
        self.stage = omni.usd.get_context().get_stage()
        if self.stage is None:
            raise RuntimeError("SimulationApp did not create a USD stage")
        UsdGeom.SetStageMetersPerUnit(self.stage, 1.0)
        UsdGeom.SetStageUpAxis(self.stage, UsdGeom.Tokens.z)
        GroundPlane(self.plan["scene"]["ground_path"], templates=None, sizes=100.0)
        self.scenario = ManipulationScenario("franka", robot_prim_path=self.plan["robot"]["prim_path"])
        self.articulation = self.scenario.setup_scene()
        SimulationManager.setup_simulation(dt=self.plan["scene"]["dt_seconds"], device="cpu")
        scenes = SimulationManager.get_physics_scenes()
        if len(scenes) != 1:
            raise RuntimeError(f"expected one PhysX scene, found {len(scenes)}")
        self.physics_scene = scenes[0]
        self.physics_scene.set_enabled_gpu_dynamics(False)
        if self.physics_scene.get_enabled_gpu_dynamics() is not False:
            raise RuntimeError("PhysX GPU dynamics could not be disabled")
        Cube(
            self.plan["scene"]["cube_path"],
            sizes=self.plan["scene"]["cube_edge_m"],
            positions=self.plan["scene"]["cube_position_m"],
            orientations=self.plan["scene"]["cube_orientation_wxyz"],
            reset_xform_op_properties=True,
        )
        GeomPrim(self.plan["scene"]["cube_path"], apply_collision_apis=True)
        self.cube = RigidPrim(
            self.plan["scene"]["cube_path"],
            masses=self.plan["scene"]["cube_mass_kg"],
            reset_xform_op_properties=True,
        )
        self.cube.set_default_state(
            positions=self.plan["scene"]["cube_position_m"],
            orientations=self.plan["scene"]["cube_orientation_wxyz"],
            linear_velocities=[0.0, 0.0, 0.0],
            angular_velocities=[0.0, 0.0, 0.0],
        )
        self.dof_names = list(self.articulation.dof_names)
        self.dof_index = {name: index for index, name in enumerate(self.dof_names)}
        self.home = {str(name): float(value) for name, value in self.scenario.robot_config.default_joint_positions}
        if set(self.home) != set(self.dof_names):
            raise RuntimeError(f"robot DOF/config mismatch: dofs={self.dof_names}, defaults={sorted(self.home)}")

    def prepare(self) -> dict[str, Any]:
        if self.app is None or self.stage is None:
            raise RuntimeError("driver.open must complete before prepare")
        self._asset_inventory = self._collect_asset_inventory()
        if self._asset_inventory["known_unique_bytes"] > self.plan["limits"]["max_asset_transfer_bytes"]:
            raise RuntimeError("resolved Panda dependency byte estimate exceeds 2 GiB asset budget")
        overlap = self._check_static_cube_robot_overlap()
        if overlap["robot_collision_prim_count"] <= 0 or overlap["invalid_bounds_paths"]:
            raise RuntimeError(f"static Panda collision geometry could not be proven: {overlap}")
        if overlap["overlap_paths"]:
            raise RuntimeError(f"static cube/Panda collision AABBs overlap: {overlap['overlap_paths']}")
        physics_inventory = self._collect_physics_inventory()
        if physics_inventory["unexpected_rigid_body_paths"] or len(physics_inventory["physics_scene_paths"]) != 1:
            raise RuntimeError(f"unexpected physical objects in baseline scene: {physics_inventory}")
        import omni.usd
        app_utils = self.app_utils
        manager = self.SimulationManager
        # The official robot is authored before the first physical step; its
        # composition and asset inventory are frozen above.
        before_index = int(manager.get_num_physics_steps())
        before_time = float(manager.get_simulation_time())
        app_utils.play()
        app_utils.update_app(steps=2)
        after_index = int(manager.get_num_physics_steps())
        after_time = float(manager.get_simulation_time())
        bootstrap = {
            "kind": "timeline_view_initialization",
            "physics_steps": after_index - before_index,
            "physics_index_before": before_index,
            "physics_index_after": after_index,
            "simulation_time_before_s": before_time,
            "simulation_time_after_s": after_time,
            "simulation_time_delta_s": after_time - before_time,
            "expected_dt_s": float(self.physics_scene.get_dt()),
            "application_updates": 2,
        }
        if after_index - before_index < 0:
            raise RuntimeError("physics counter moved backwards during bootstrap")
        if after_index - before_index > MAX_PHYSICS_STEPS:
            raise RuntimeError("bootstrap exceeded total physics step budget")
        if after_time - before_time > MAX_SIMULATION_SECONDS:
            raise RuntimeError("bootstrap exceeded total simulation time budget")
        if not self.articulation.is_physics_tensor_entity_valid() or not self.cube.is_physics_tensor_entity_valid():
            raise RuntimeError("experimental articulation or rigid body view is not valid after bootstrap")
        low_array, high_array = self.articulation.get_dof_limits()
        lows = low_array.numpy()[0]
        highs = high_array.numpy()[0]
        self.lower = {name: float(lows[i]) for i, name in enumerate(self.dof_names)}
        self.upper = {name: float(highs[i]) for i, name in enumerate(self.dof_names)}
        self._physics_start_index = before_index
        self._time_start = before_time
        self.callback_uid = manager.register_callback(self._on_physics_step, event=self.SimulationEvent.PHYSICS_POST_STEP)
        self.callbacks_registered = 1
        self._scene_identity = {
            "physics_scene_type": type(self.physics_scene).__name__,
            "physics_scene_module": type(self.physics_scene).__module__,
            "physics_device_configured": "cpu",
            "physics_dt_s": float(self.physics_scene.get_dt()),
            "gpu_dynamics_enabled": bool(self.physics_scene.get_enabled_gpu_dynamics()),
            "stage_meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(self.stage)),
            "stage_up_axis": str(UsdGeom.GetStageUpAxis(self.stage)),
            "root_layer_identifier": self.stage.GetRootLayer().identifier,
            "robot_prim_path": self.plan["robot"]["prim_path"],
            "ground_prim_path": self.plan["scene"]["ground_path"],
            "cube_prim_path": self.plan["scene"]["cube_path"],
            "stage_camera_prim_paths": self._camera_paths(),
            "static_overlap_check": overlap,
            "physics_inventory": physics_inventory,
            "official_scenario_added_dome_light": self.stage.GetPrimAtPath("/World/DomeLight").IsValid(),
            "cube_mass_kg": self._numpy(self.cube.get_masses())[0][0],
            "sample_sources": {
                "joint_positions": "Articulation.get_dof_positions actual physics state",
                "joint_velocities": "Articulation.get_dof_velocities actual physics state",
                "position_targets": "Articulation.get_dof_position_targets controller target state",
                "velocity_targets": "Articulation.get_dof_velocity_targets controller target state",
                "cube_pose": "RigidPrim.get_world_poses actual physics state",
                "cube_velocity": "RigidPrim.get_velocities actual physics state",
                "physics_index": "SimulationManager.get_num_physics_steps",
                "simulation_time": "SimulationManager.get_simulation_time",
            },
        }
        self._prepare_done = True
        return {
            "asset_inventory": self._asset_inventory,
            "scene_identity": self._scene_identity,
            "home_positions": self.home,
            "joint_lower_limits": self.lower,
            "joint_upper_limits": self.upper,
            "physics_steps_at_start": before_index,
            "simulation_time_start_s": before_time,
            "bootstrap": [bootstrap],
        }

    @staticmethod
    def _numpy(value: Any) -> list[Any]:
        return value.numpy().tolist()

    def _on_physics_step(self, step_dt: float, _context: Any) -> None:
        # The supervisor enforces aggregate limits; this callback also leaves a
        # direct public API hook count for teardown and callback lifecycle proof.
        if not math.isfinite(float(step_dt)):
            raise RuntimeError("non-finite PhysicsStepContext dt")

    def _camera_paths(self) -> list[str]:
        from pxr import UsdGeom

        return [str(prim.GetPath()) for prim in self.stage.Traverse() if prim.IsA(UsdGeom.Camera)]

    def _check_static_cube_robot_overlap(self) -> dict[str, Any]:
        from pxr import Usd, UsdGeom, UsdPhysics

        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        cx, cy, cz = (float(v) for v in CUBE_POSITION)
        half = CUBE_EDGE_M / 2.0
        cube_min = (cx - half, cy - half, cz - half)
        cube_max = (cx + half, cy + half, cz + half)
        overlaps: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        colliders = 0
        for prim in self.stage.Traverse():
            path = str(prim.GetPath())
            if not path.startswith(ROBOT_PATH + "/") and path != ROBOT_PATH:
                continue
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            colliders += 1
            world_range = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            low = tuple(float(v) for v in world_range.GetMin())
            high = tuple(float(v) for v in world_range.GetMax())
            if (len(low) != 3 or len(high) != 3 or not all(math.isfinite(v) for v in (*low, *high))
                    or any(low[i] > high[i] for i in range(3))):
                invalid.append({"path": path, "aabb_min_m": low, "aabb_max_m": high})
                continue
            intersects = all(cube_min[i] <= high[i] and low[i] <= cube_max[i] for i in range(3))
            if intersects:
                overlaps.append({"path": path, "aabb_min_m": low, "aabb_max_m": high})
        return {"robot_collision_prim_count": colliders, "cube_aabb_min_m": cube_min,
                "cube_aabb_max_m": cube_max, "overlap_paths": overlaps,
                "invalid_bounds_paths": invalid}

    def _collect_physics_inventory(self) -> dict[str, Any]:
        from pxr import UsdPhysics

        rigid_bodies: list[str] = []
        physics_scenes: list[str] = []
        joints: list[str] = []
        unexpected: list[str] = []
        for prim in self.stage.Traverse():
            path = str(prim.GetPath())
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                rigid_bodies.append(path)
                if not (path == ROBOT_PATH or path.startswith(ROBOT_PATH + "/") or path == CUBE_PATH):
                    unexpected.append(path)
            if prim.IsA(UsdPhysics.Scene):
                physics_scenes.append(path)
            if prim.IsA(UsdPhysics.Joint):
                joints.append(path)
        return {
            "rigid_body_paths": sorted(rigid_bodies),
            "physics_scene_paths": sorted(physics_scenes),
            "joint_paths": sorted(joints),
            "cube_is_rigid_body": CUBE_PATH in rigid_bodies,
            "unexpected_rigid_body_paths": sorted(unexpected),
        }

    def _collect_asset_inventory(self) -> dict[str, Any]:
        from isaacsim.storage.native import get_assets_root_path
        import omni.client
        from pxr import Ar, UsdUtils

        config = self.scenario.robot_config
        assets_root = get_assets_root_path()
        if not assets_root:
            raise RuntimeError("Isaac assets root could not be resolved")
        authored = str(assets_root) + str(config.asset_path)
        layers, asset_paths, unresolved = UsdUtils.ComputeAllDependencies(self.stage.GetRootLayer().identifier)
        identities: list[dict[str, Any]] = []
        layer_ids = [str(getattr(layer, "identifier", None) or layer) for layer in layers]
        identifiers = sorted(set([authored, *[str(v) for v in asset_paths], *layer_ids]))
        for identifier in identifiers:
            resolved_obj = Ar.GetResolver().Resolve(identifier)
            resolved = resolved_obj.GetPathString() if hasattr(resolved_obj, "GetPathString") else str(resolved_obj)
            row: dict[str, Any] = {"authored_identifier": identifier, "resolved_identifier": resolved or None,
                                   "size_bytes": None, "sha256": None, "identity_status": "unknown"}
            if resolved and not resolved.startswith(("omniverse://", "omni://")):
                path = Path(resolved.removeprefix("file://"))
                if path.is_file():
                    row["size_bytes"] = path.stat().st_size
                    if row["size_bytes"] <= 128 * 1024 * 1024:
                        row["sha256"] = _sha256(path)
                        row["identity_status"] = "local_bytes_hashed"
                    else:
                        row["identity_status"] = "local_size_only_above_hash_cap"
            elif resolved:
                try:
                    result, entry = omni.client.stat(resolved)
                    row["omni_client_stat_result"] = str(result)
                    size = getattr(entry, "size", None)
                    if size is not None:
                        row["size_bytes"] = int(size)
                    row["omni_client_version"] = getattr(entry, "version", None)
                    row["identity_status"] = "remote_stat_only" if row["size_bytes"] is not None else "remote_size_unknown"
                except Exception as exc:
                    row["identity_status"] = "remote_stat_failed"
                    row["stat_error"] = {"type": type(exc).__name__, "message": str(exc)}
            identities.append(row)
        unique = {row["resolved_identifier"] or row["authored_identifier"]: row for row in identities}
        known_bytes = sum(int(row["size_bytes"]) for row in unique.values() if row["size_bytes"] is not None)
        return {
            "schema": "f01-asset-inventory-v1",
            "robot_asset_authored": authored,
            "robot_asset_path_from_official_config": config.asset_path,
            "robot_variants": dict(config.variants),
            "scenario_default_joint_positions": [[str(k), float(v)] for k, v in config.default_joint_positions],
            "dependency_count": len(identifiers),
            "dependency_identities": identities,
            "unique_resolved_dependency_count": len(unique),
            "known_unique_bytes": known_bytes,
            "unknown_size_count": sum(row["size_bytes"] is None for row in unique.values()),
            "usd_utils_unresolved": [str(v) for v in unresolved],
            "root_layer_identifier": self.stage.GetRootLayer().identifier,
            "resolver": type(Ar.GetResolver()).__name__,
            "assets_root": str(assets_root),
            "source_revision": "installed Isaac Sim 6.2.0.0 RobotConfig; remote content revision/hash not exposed by resolved URL",
            "content_hash_limitations": "remote omni:// dependencies were stat-identified only; host network RX cap and cache delta are recorded by supervisor",
        }

    def reset(self, home: dict[str, float], _plan: dict[str, Any]) -> dict[str, Any]:
        if not self._prepare_done:
            raise RuntimeError("prepare must finish before reset")
        positions = [float(home[name]) for name in self.dof_names]
        self.articulation.set_dof_positions(positions)
        self.articulation.set_dof_velocities([0.0] * len(self.dof_names))
        self.articulation.set_dof_position_targets(positions)
        self.articulation.set_dof_velocity_targets([0.0] * len(self.dof_names))
        self.cube.set_world_poses(positions=CUBE_POSITION, orientations=CUBE_ORIENTATION_WXYZ)
        self.cube.set_velocities(linear_velocities=[0.0, 0.0, 0.0], angular_velocities=[0.0, 0.0, 0.0])
        state = self.read_state()
        return state

    def refresh_views(self) -> dict[str, Any]:
        # Rebuild the wrappers through the scenario's documented bind-existing
        # lifecycle. No USD or articulation data is rewritten between rounds.
        self.scenario.cleanup()
        from isaacsim.robot_motion.examples.manipulation import ManipulationScenario
        from isaacsim.core.experimental.prims import RigidPrim

        self.scenario = ManipulationScenario("franka", robot_prim_path=ROBOT_PATH)
        self.articulation = self.scenario.bind_existing_robot()
        self.cube = RigidPrim(CUBE_PATH)
        if not self.articulation.is_physics_tensor_entity_valid() or not self.cube.is_physics_tensor_entity_valid():
            before_i = int(self.SimulationManager.get_num_physics_steps())
            before_t = float(self.SimulationManager.get_simulation_time())
            self.app_utils.update_app(steps=1)
            after_i = int(self.SimulationManager.get_num_physics_steps())
            after_t = float(self.SimulationManager.get_simulation_time())
            if not self.articulation.is_physics_tensor_entity_valid() or not self.cube.is_physics_tensor_entity_valid():
                raise RuntimeError("refreshed articulation or rigid-body view is not valid after one Kit update")
            return {"kind": "view_refresh_bootstrap", "physics_steps": after_i - before_i,
                    "physics_index_before": before_i, "physics_index_after": after_i,
                    "simulation_time_before_s": before_t, "simulation_time_after_s": after_t,
                    "application_updates": 1}
        return {"kind": "view_refresh", "physics_steps": 0,
                "physics_index": int(self.SimulationManager.get_num_physics_steps()),
                "simulation_time_s": float(self.SimulationManager.get_simulation_time())}

    def set_selected_joint_target(self, name: str, value: float) -> None:
        self.articulation.set_dof_position_targets([float(value)], dof_indices=[self.dof_index[name]])
        self._selected_target = float(value)

    def step(self) -> None:
        self.SimulationManager.step(steps=1, update_fabric=False)

    def read_state(self) -> dict[str, Any]:
        q = self.articulation.get_dof_positions().numpy()[0]
        qd = self.articulation.get_dof_velocities().numpy()[0]
        targets = self.articulation.get_dof_position_targets().numpy()[0]
        vtargets = self.articulation.get_dof_velocity_targets().numpy()[0]
        cube_position, cube_orientation = self.cube.get_world_poses()
        linear, angular = self.cube.get_velocities()
        return {
            "physics_index": int(self.SimulationManager.get_num_physics_steps()),
            "simulation_time_s": float(self.SimulationManager.get_simulation_time()),
            "joint_positions": {name: float(q[i]) for i, name in enumerate(self.dof_names)},
            "joint_velocities": {name: float(qd[i]) for i, name in enumerate(self.dof_names)},
            "position_targets": {name: float(targets[i]) for i, name in enumerate(self.dof_names)},
            "velocity_targets": {name: float(vtargets[i]) for i, name in enumerate(self.dof_names)},
            "cube_position_m": [float(v) for v in cube_position.numpy()[0]],
            "cube_orientation_wxyz": [float(v) for v in cube_orientation.numpy()[0]],
            "cube_linear_velocity_m_s": [float(v) for v in linear.numpy()[0]],
            "cube_angular_velocity_rad_s": [float(v) for v in angular.numpy()[0]],
        }

    def final_counters(self) -> dict[str, Any]:
        if self.SimulationManager is None:
            return {"physics_index": None, "simulation_time_s": None}
        return {"physics_index": int(self.SimulationManager.get_num_physics_steps()),
                "simulation_time_s": float(self.SimulationManager.get_simulation_time())}

    def stop(self) -> None:
        if self._stop_called:
            return
        self._stop_called = True
        errors: list[str] = []
        if self.app_utils is not None:
            self.timeline_stop_attempts += 1
            try:
                self.app_utils.stop()
            except BaseException as exc:
                errors.append(f"timeline stop: {type(exc).__name__}: {exc}")
        if self.callback_uid is not None and self.SimulationManager is not None:
            try:
                removed = self.SimulationManager.deregister_callback(self.callback_uid)
                if not removed:
                    errors.append("PhysicsStep callback deregistration returned false")
                else:
                    self.callbacks_deregistered += 1
                    self.callback_uid = None
            except BaseException as exc:
                errors.append(f"callback deregistration: {type(exc).__name__}: {exc}")
        if self.scenario is not None:
            try:
                self.scenario.cleanup()
            except BaseException as exc:
                errors.append(f"scenario cleanup: {type(exc).__name__}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def close(self) -> None:
        if self.app is None:
            return
        self.app_close_attempts += 1
        if self.app_close_attempts > 1:
            raise RuntimeError("SimulationApp.close attempted more than once")
        self.app.close(wait_for_replicator=False, skip_cleanup=False, exit_code=0)
        self.app_closed = True


def _load_plan(run_dir: Path) -> dict[str, Any]:
    path = Path(run_dir) / "run_plan.json"
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant rejected: {value}")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    expected = default_plan()
    for key in ("application", "robot", "scene", "limits"):
        if value.get(key) != expected[key]:
            raise ValueError(f"frozen F01 plan section changed: {key}")
    if value.get("schema") != expected["schema"]:
        raise ValueError("unsupported F01 plan schema")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="metadata-only preflight; never starts Kit")
    mode.add_argument("--native-worker", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--synthetic-s1-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--synthetic-fault", choices=("none", "primary", "primary-and-cleanup", "close", "fail-before-step", "partial-progress", "nan-state", "final-receipt-write"), default="none", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.check:
        result = check_installation()
        print(json.dumps(_strict_json_value(result), sort_keys=True, allow_nan=False))
        return 0 if result["expected_packages_match"] and result["provider_free"] else 2
    if args.run_dir is None:
        parser.error("--run-dir is required for worker modes")
    try:
        plan = _load_plan(args.run_dir)
    except Exception as exc:
        print(json.dumps({"status": "PLAN_REJECTED", "error": str(exc)}, allow_nan=False))
        return 2
    if args.synthetic_s1_worker:
        fault = args.synthetic_fault
        driver_options = {
            "primary_error": "primary_and_cleanup" if fault == "primary-and-cleanup" else ("primary" if fault == "primary" else None),
            "close_error": "injected close failure" if fault in {"close", "primary-and-cleanup"} else None,
            "fail_before_step": fault == "fail-before-step",
            "fail_after_step": 21 if fault == "partial-progress" else None,
            "nan_state": fault == "nan-state",
        }
        writer = _write_json_new
        if fault == "final-receipt-write":
            def writer(_path: Path, _value: Any) -> None:
                raise OSError("injected final receipt write failure")
        def handle_termination(signum: int, _frame: Any) -> None:
            raise KeyboardInterrupt(f"received signal {signum}")
        signal.signal(signal.SIGTERM, handle_termination)
        outcome = run_worker(args.run_dir, plan,
                             driver_factory=lambda p, r: FakeDriver(p, r, **driver_options),
                             evidence_kind="synthetic_fixture", result_writer=writer)
    else:
        def handle_termination(signum: int, _frame: Any) -> None:
            raise KeyboardInterrupt(f"received signal {signum}")
        signal.signal(signal.SIGTERM, handle_termination)
        outcome = run_worker(args.run_dir, plan, driver_factory=lambda p, r: NativeDriver(p, r), evidence_kind="real_native")
    print(json.dumps(_strict_json_value({"exit_code": outcome["exit_code"], "error": outcome.get("error"),
                                         "status": outcome.get("report", {}).get("status"),
                                         "result_path": outcome.get("result_path"), "trace_path": outcome.get("trace_path")}),
                     sort_keys=True, allow_nan=False))
    return int(outcome["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
