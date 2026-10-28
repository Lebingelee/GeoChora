"""Independent standard-library reader for F01 native worker evidence.

This module deliberately imports neither Isaac Sim nor the diagnostic worker.
It treats the worker receipt as untrusted and recomputes every task gate from
the append-only JSONL observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


SCHEMA = "geochora-f01-isaac-native-baseline-v1"
DT = 1.0 / 120.0
EXPECTED_STEPS = 240
EXPECTED_ROUNDS = 2
ARM = "panda_joint1"
HOME = {
    "panda_joint1": 0.012,
    "panda_joint2": -0.568,
    "panda_joint3": 0.0,
    "panda_joint4": -2.811,
    "panda_joint5": 0.0,
    "panda_joint6": 3.037,
    "panda_joint7": 0.741,
    "panda_finger_joint1": 0.04,
    "panda_finger_joint2": 0.04,
}
CUBE_START = (0.8, 0.0, 0.25)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant rejected: {value}")


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _finite_vector(value: Any, length: int) -> bool:
    return isinstance(value, list) and len(value) == length and all(_finite_number(v) for v in value)


def _quat_error(a: Any, b: Any) -> float:
    if not _finite_vector(a, 4) or not _finite_vector(b, 4):
        return math.inf
    an = math.sqrt(sum(float(x) ** 2 for x in a))
    bn = math.sqrt(sum(float(x) ** 2 for x in b))
    if an <= 0 or bn <= 0:
        return math.inf
    dot = abs(sum((float(x) / an) * (float(y) / bn) for x, y in zip(a, b)))
    return 2 * math.acos(max(-1.0, min(1.0, dot)))


def _target(step: int) -> float:
    if step <= 60:
        delta = 0.1 * step / 60.0
    elif step <= 120:
        delta = 0.1
    elif step <= 180:
        delta = 0.1 * (1.0 - (step - 120) / 60.0)
    else:
        delta = 0.0
    return HOME[ARM] + delta


def _check_reset(state: dict[str, Any]) -> dict[str, Any]:
    q = state.get("joint_positions")
    qd = state.get("joint_velocities")
    pt = state.get("position_targets")
    vt = state.get("velocity_targets")
    has_full_dof_state = all(
        isinstance(v, dict) and set(v) == set(HOME) and all(_finite_number(v[name]) for name in HOME)
        for v in (q, qd, pt, vt)
    )
    q_err = max((abs(float(q[k]) - v) for k, v in HOME.items()), default=math.inf) if has_full_dof_state else math.inf
    target_err = max((abs(float(pt[k]) - v) for k, v in HOME.items()), default=math.inf) if has_full_dof_state else math.inf
    qd_max = max((abs(float(qd[k])) for k in HOME), default=math.inf) if has_full_dof_state else math.inf
    vt_max = max((abs(float(vt[k])) for k in HOME), default=math.inf) if has_full_dof_state else math.inf
    cube_pos = state.get("cube_position_m")
    cube_quat = state.get("cube_orientation_wxyz")
    cube_lin = state.get("cube_linear_velocity_m_s")
    cube_ang = state.get("cube_angular_velocity_rad_s")
    position_error = max((abs(float(cube_pos[i]) - CUBE_START[i]) for i in range(3)), default=math.inf) if _finite_vector(cube_pos, 3) else math.inf
    quat_error = _quat_error(cube_quat, [1.0, 0.0, 0.0, 0.0])
    lin_max = max((abs(float(v)) for v in cube_lin), default=math.inf) if _finite_vector(cube_lin, 3) else math.inf
    ang_max = max((abs(float(v)) for v in cube_ang), default=math.inf) if _finite_vector(cube_ang, 3) else math.inf
    return {
        "complete_dof_inventory": has_full_dof_state,
        "joint_positions_at_home": q_err <= 1e-4,
        "position_targets_cleared_to_home": target_err <= 1e-4,
        "joint_velocities_zero": qd_max <= 1e-4,
        "velocity_targets_zero": vt_max <= 1e-4,
        "cube_position_at_reset": position_error <= 1e-5,
        "cube_orientation_at_reset": quat_error <= 1e-4,
        "cube_velocity_zero_at_reset": lin_max <= 1e-6 and ang_max <= 1e-6,
        "joint_position_error_max": q_err,
        "joint_target_error_max": target_err,
        "joint_velocity_max": qd_max,
        "velocity_target_max": vt_max,
        "cube_position_error_m": position_error,
        "cube_orientation_error_rad": quat_error,
        "cube_linear_velocity_max_m_s": lin_max,
        "cube_angular_velocity_max_rad_s": ang_max,
    }


def _check_round(rows: list[dict[str, Any]], reset_state: dict[str, Any], round_no: int,
                 lower: dict[str, Any], upper: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {"expected_step_count": len(rows) == EXPECTED_STEPS}
    if len(rows) != EXPECTED_STEPS:
        checks["observed_step_count"] = len(rows)
        return checks
    first_index = reset_state.get("physics_index")
    first_time = reset_state.get("simulation_time_s")
    contiguous = type(first_index) is int and _finite_number(first_time)
    clock_ok = contiguous
    joint_finite = True
    lower = lower if isinstance(lower, dict) else {}
    upper = upper if isinstance(upper, dict) else {}
    joint_limits_ok = set(lower) == set(HOME) and set(upper) == set(HOME)
    targets_ok = True
    selected: list[float] = []
    start_cube = reset_state.get("cube_position_m")
    for expected_step, row in enumerate(rows, 1):
        state = row.get("state")
        if not isinstance(state, dict):
            contiguous = clock_ok = joint_finite = joint_limits_ok = targets_ok = False
            continue
        idx = state.get("physics_index")
        sim_time = state.get("simulation_time_s")
        if type(idx) is not int or type(first_index) is not int or idx != first_index + expected_step:
            contiguous = False
        if not _finite_number(sim_time) or not _finite_number(first_time) or abs(float(sim_time) - (float(first_time) + expected_step * DT)) > 1e-5:
            clock_ok = False
        q = state.get("joint_positions")
        qd = state.get("joint_velocities")
        pt = state.get("position_targets")
        if not isinstance(q, dict) or set(q) != set(HOME) or not isinstance(qd, dict) or set(qd) != set(HOME):
            joint_finite = False
        else:
            for name in HOME:
                if not _finite_number(q[name]) or not _finite_number(qd[name]):
                    joint_finite = False
                    continue
                if not _finite_number(lower.get(name)) or not _finite_number(upper.get(name)):
                    joint_limits_ok = False
                elif float(q[name]) < float(lower[name]) - 1e-4 or float(q[name]) > float(upper[name]) + 1e-4:
                    joint_limits_ok = False
            if _finite_number(q.get(ARM)):
                selected.append(float(q[ARM]))
        expected_target = _target(expected_step)
        if (not _finite_number(row.get("commanded_target_rad"))
                or abs(float(row["commanded_target_rad"]) - expected_target) > 1e-8
                or not isinstance(pt, dict) or not _finite_number(pt.get(ARM))
                or set(pt) != set(HOME) or abs(float(pt[ARM]) - expected_target) > 1e-4
                or any(not _finite_number(pt.get(name)) or abs(float(pt[name]) - HOME[name]) > 1e-4 for name in HOME if name != ARM)):
            targets_ok = False
    motion = max(selected) - min(selected) if selected and len(selected) == EXPECTED_STEPS else 0.0
    final_error = abs(selected[-1] - HOME[ARM]) if selected and len(selected) == EXPECTED_STEPS else math.inf
    last_state = rows[-1].get("state", {})
    final_cube = last_state.get("cube_position_m")
    final_quat = last_state.get("cube_orientation_wxyz")
    final_linear = last_state.get("cube_linear_velocity_m_s")
    final_angular = last_state.get("cube_angular_velocity_rad_s")
    start_z = float(start_cube[2]) if _finite_vector(start_cube, 3) else math.nan
    final_z = float(final_cube[2]) if _finite_vector(final_cube, 3) else math.nan
    drop = start_z - final_z
    quat_norm = math.sqrt(sum(float(v) ** 2 for v in final_quat)) if _finite_vector(final_quat, 4) else math.nan
    checks.update({
        "physics_indices_contiguous": contiguous,
        "clock_dt_consistent": clock_ok,
        "all_joint_state_finite": joint_finite,
        "joint_limits": joint_limits_ok,
        "commanded_targets_match_recipe": targets_ok,
        "selected_joint_motion_rad": motion,
        "selected_joint_motion": motion >= 0.04,
        "final_home_error_rad": final_error,
        "final_home": final_error <= 0.05,
        "cube_drop_m": drop,
        "cube_dropped": _finite_number(drop) and drop >= 0.05,
        "final_cube_center_z_m": final_z,
        "cube_final_height": _finite_number(final_z) and 0.015 <= final_z <= 0.04,
        "final_cube_pose_valid": _finite_vector(final_cube, 3) and _finite_vector(final_quat, 4) and _finite_number(quat_norm) and abs(quat_norm - 1.0) <= 1e-3,
        "final_cube_velocity_valid": _finite_vector(final_linear, 3) and _finite_vector(final_angular, 3),
        "round": round_no,
    })
    return checks


def verify(result_path: Path, trace_path: Path, *, allow_synthetic_fixture: bool = False) -> dict[str, Any]:
    receipt = _json(result_path)
    if not isinstance(receipt, dict):
        raise ValueError("worker receipt must be a JSON object")
    if receipt.get("schema") != SCHEMA:
        raise ValueError("unsupported worker receipt schema")
    evidence_kind = receipt.get("evidence_kind")
    if evidence_kind == "synthetic_fixture" and not allow_synthetic_fixture:
        return {"schema": "f01-independent-reader-v1", "status": "REJECTED_SYNTHETIC_EVIDENCE", "native_gate": False}
    if evidence_kind not in {"real_native", "synthetic_fixture"}:
        raise ValueError(f"unsupported evidence kind: {evidence_kind!r}")
    if evidence_kind == "synthetic_fixture" and allow_synthetic_fixture is not True:
        raise ValueError("synthetic fixture requires explicit test-only opt-in")
    actual_hash = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    if actual_hash != receipt.get("trace_sha256"):
        raise ValueError("trace SHA-256 does not match receipt")
    expected_trace_rows = receipt.get("trace_rows")
    rows: list[dict[str, Any]] = []
    with trace_path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.endswith("\n"):
                raise ValueError(f"trace line {line_no} is not newline terminated")
            row = json.loads(line, parse_constant=_reject_constant)
            if not isinstance(row, dict):
                raise ValueError(f"trace row {line_no} is not an object")
            rows.append(row)
    if type(expected_trace_rows) is not int or expected_trace_rows != len(rows):
        raise ValueError("trace row count does not match receipt")
    checks: dict[str, Any] = {}
    checks["worker_receipt_success_claim"] = receipt.get("pass") is True and receipt.get("exit_code") == 0 and receipt.get("receipt_written") is True
    checks["app_closed_exactly_once"] = receipt.get("app_closed") is True and receipt.get("app_close_attempts") == 1
    checks["timeline_stopped_once"] = receipt.get("timeline_stop_attempts") == 1
    checks["callbacks_released"] = receipt.get("callbacks_registered") == 1 and receipt.get("callbacks_deregistered") == 1
    checks["no_cleanup_errors"] = receipt.get("cleanup_errors") == []
    checks["worker_error_absent"] = receipt.get("worker_error") is None
    checks["trace_hash_matches"] = True
    checks["two_rounds_reported"] = isinstance(receipt.get("rounds"), list) and len(receipt["rounds"]) == EXPECTED_ROUNDS
    checks["physics_budget"] = _finite_number(receipt.get("total_physics_steps")) and 0 <= int(receipt["total_physics_steps"]) <= 1200
    checks["simulation_time_budget"] = _finite_number(receipt.get("total_simulation_time_s")) and 0 <= float(receipt["total_simulation_time_s"]) <= 10.0 + 1e-5

    identity = receipt.get("scene_identity") or {}
    checks["cpu_physx_and_no_gpu_dynamics"] = identity.get("physics_scene_type") == "PhysxScene" and identity.get("physics_device_configured") == "cpu" and identity.get("gpu_dynamics_enabled") is False
    checks["fixed_stage_identity"] = identity.get("stage_meters_per_unit") == 1.0 and identity.get("stage_up_axis") == "Z"
    checks["official_robot_and_no_camera"] = identity.get("robot_prim_path") == "/World/robot" and identity.get("stage_camera_prim_paths") == []
    checks["static_overlap_precheck"] = (
        isinstance(identity.get("static_overlap_check"), dict)
        and identity["static_overlap_check"].get("robot_collision_prim_count", 0) > 0
        and identity["static_overlap_check"].get("invalid_bounds_paths") == []
        and identity["static_overlap_check"].get("overlap_paths") == []
    )
    physics = identity.get("physics_inventory") or {}
    checks["no_unexpected_rigid_bodies"] = physics.get("unexpected_rigid_body_paths") == [] and physics.get("cube_is_rigid_body") is True
    checks["one_physics_scene"] = isinstance(physics.get("physics_scene_paths"), list) and len(physics["physics_scene_paths"]) == 1
    checks["cube_mass_recipe"] = _finite_number(identity.get("cube_mass_kg")) and abs(float(identity["cube_mass_kg"]) - 0.08) <= 1e-6
    assets = receipt.get("asset_inventory") or {}
    checks["asset_transfer_budget"] = _finite_number(assets.get("known_unique_bytes")) and 0 <= int(assets["known_unique_bytes"]) <= 2 * 1024**3

    trace_rounds: list[list[dict[str, Any]]] = [[], []]
    reset_states: dict[int, dict[str, Any]] = {}
    trace_structure_ok = True
    for row in rows:
        event = row.get("event")
        round_no = row.get("round")
        if type(round_no) is not int or round_no not in (1, 2):
            trace_structure_ok = False
            continue
        if event == "round_reset":
            if round_no in reset_states or not isinstance(row.get("state"), dict):
                trace_structure_ok = False
            else:
                reset_states[round_no] = row["state"]
        elif event == "physics_step":
            trace_rounds[round_no - 1].append(row)
        else:
            trace_structure_ok = False
    checks["trace_structure"] = trace_structure_ok and set(reset_states) == {1, 2}
    lower = receipt.get("joint_lower_limits")
    upper = receipt.get("joint_upper_limits")
    reset_checks: dict[str, Any] = {}
    round_checks: dict[str, Any] = {}
    for round_no in (1, 2):
        if round_no not in reset_states:
            reset_checks[str(round_no)] = {"missing_reset": False}
            round_checks[str(round_no)] = {"missing_reset": False}
            continue
        reset_checks[str(round_no)] = _check_reset(reset_states[round_no])
        round_checks[str(round_no)] = _check_round(trace_rounds[round_no - 1], reset_states[round_no], round_no, lower, upper)
    checks["round_2_views_refreshed"] = receipt.get("rounds", [{}, {}])[1].get("view_refresh") is True if checks["two_rounds_reported"] else False
    checks["reset_gates_all_pass"] = all(all(value is True for value in gate.values() if isinstance(value, bool)) for gate in reset_checks.values())
    checks["round_gates_all_pass"] = all(all(value is True for value in gate.values() if isinstance(value, bool)) for gate in round_checks.values())
    native_gate = evidence_kind == "real_native" and all(value is True for value in checks.values() if isinstance(value, bool))
    if evidence_kind == "synthetic_fixture":
        synthetic_trace_gates = checks.get("trace_structure") is True and checks.get("reset_gates_all_pass") is True and checks.get("round_gates_all_pass") is True
        return {
            "schema": "f01-independent-reader-v1",
            "status": "SYNTHETIC_FIXTURE_VERIFIED_ONLY",
            "native_gate": False,
            "synthetic_trace_gates": synthetic_trace_gates,
            "trace_sha256": actual_hash,
            "trace_rows": len(rows),
            "checks": checks,
            "reset_checks": reset_checks,
            "round_checks": round_checks,
        }
    return {
        "schema": "f01-independent-reader-v1",
        "status": "PASS_NATIVE_PENDING_SOL_REVIEW" if native_gate else "REJECTED_NATIVE_GATES",
        "native_gate": native_gate,
        "evidence_kind": evidence_kind,
        "trace_sha256": actual_hash,
        "trace_rows": len(rows),
        "checks": checks,
        "reset_checks": reset_checks,
        "round_checks": round_checks,
        "worker_report_checks_not_trusted_for_decision": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-synthetic-fixture", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = verify(args.result, args.trace, allow_synthetic_fixture=args.allow_synthetic_fixture)
    except Exception as exc:
        result = {"schema": "f01-independent-reader-v1", "status": "READER_ERROR", "error": {"type": type(exc).__name__, "message": str(exc)}}
    payload = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    print(payload, end="")
    if result.get("status") == "PASS_NATIVE_PENDING_SOL_REVIEW":
        return 0
    if result.get("status") == "SYNTHETIC_FIXTURE_VERIFIED_ONLY":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
