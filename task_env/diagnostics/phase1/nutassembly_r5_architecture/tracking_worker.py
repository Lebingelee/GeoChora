"""One isolated T0 or G0 provider/rate cell for the P1.8-E-R5 spike."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import traceback

import numpy as np

from ....controllers.canonical import RequestedAction
from ....controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
from ....controllers.canonical.kinematics import ARM
from ....planners import AbsolutePosePlanner, AbsolutePosePlannerConfig
from ....runtime.sessions.control import ControlBinding, materialize_control
from ....runtime.sessions.provenance import provider_build_identity
from ....tasks.nut_assembly.assets import TABLE_TOP_Z
from ....tasks.nut_assembly.canonical_reset import sample_reset
from ....utils.rotation import quat_angle_wxyz, quat_multiply_wxyz
from ..multirate.common import NativeAudit, write
from ..nutassembly.common import METADATA, observation
from ..nutassembly.native import contact_readback
from ..p1_2_runtime import execution
from ..nutassembly_nominal.common import RATE_NAMES, context as _r4_context


PROFILE_PATH = Path("task_env/tasks/nut_assembly/profiles/nutassembly-nominal-v2.json")
EVIDENCE_ROOT = Path("workspace/qualification/phase1/p1_8_nutassembly_r5_architecture")
POSE_POSITION_LIMIT_M = 0.007
POSE_ROTATION_LIMIT_RAD = 0.06
CAPTURE_POSITION_LIMIT_M = 0.008
CAPTURE_ROTATION_LIMIT_RAD = 0.15
CLOSE_TIME_LIMIT_S = 1.0
T0_ROUTE_PROFILE = {
    "schema_version": "p1.8-e-r4-t0-route-v2",
    "route_id": "na-s0-free-space-lateral-100mm-v2",
    "vertical_translation_m": 0.10,
    "lateral_translation_m": 0.10,
    "diagonal_translation_m": [-0.10, 0.10, 0.04],
    "yaw_change_rad": 0.36,
    "combined_translation_m": [-0.05, -0.06, 0.03],
    "combined_yaw_change_rad": -0.24,
    "reason_for_revision": (
        "The prior +120 mm lateral waypoint was at the edge of the reachable workspace: "
        "source-derived IK settled at 6.95 mm position / 0.039 rad rotation error. "
        "The revised +100 mm displacement remains within the requested 100-150 mm "
        "probe range and has a source-derived solution at 0.45 mm / 0.0025 rad."
    ),
}


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _finite(value):
    if isinstance(value, dict):
        return all(_finite(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite(child) for child in value)
    if isinstance(value, (bool, str)) or value is None:
        return True
    if isinstance(value, (int, float, np.number)):
        return math.isfinite(float(value))
    return True


def _pose_array(pose):
    return np.asarray((*pose.position, *pose.quaternion_wxyz), dtype=float)


def _pose_error(goal, state):
    actual = state.pose_world["panda-v1/ee"]
    return {
        "position_error_m": float(np.linalg.norm(np.asarray(actual.position) - np.asarray(goal[:3]))),
        "rotation_error_rad": float(quat_angle_wxyz(actual.quaternion_wxyz, goal[3:7])),
    }


def _relative_pose(state):
    ee = _pose_array(state.pose_world["panda-v1/ee"])
    nut = _pose_array(state.pose_world["square-nut-v1"])
    ee_inv = ee[3:].copy()
    ee_inv[1:] *= -1.0
    return {
        "position": _quat_rotate_inverse(ee[3:], nut[:3] - ee[:3]).tolist(),
        "orientation": quat_multiply_wxyz(ee_inv, nut[3:]).tolist(),
    }


def _quat_rotate_inverse(quaternion, vector):
    # Rotation helper without importing provider code.
    q = np.asarray(quaternion, dtype=float)
    v = np.asarray(vector, dtype=float)
    qv = q[1:]
    t = -2.0 * np.cross(qv, v)
    return v + q[0] * t + np.cross(qv, t)


def _relative_drift(baseline, state):
    from ....utils.rotation import quat_angle_wxyz
    current = _relative_pose(state)
    return {
        "position_m": float(np.linalg.norm(np.asarray(current["position"]) - np.asarray(baseline["position"]))),
        "rotation_rad": float(quat_angle_wxyz(current["orientation"], baseline["orientation"])),
    }


def _controller_row(controller, state, feedback, request, canonical, target, applied,
                    readiness, public_action, stage, diagnostics, metrics):
    ee = state.pose_world["panda-v1/ee"]
    requested_pose = canonical.resolved_world_pose
    if requested_pose is None:
        requested_mapping = None
        error = {"position_error_m": None, "rotation_error_rad": None}
    else:
        requested_mapping = requested_pose.to_mapping()
        error = _pose_error(_pose_array(requested_pose), state)
    memory = controller.memory()
    return {
        "stage": stage,
        "control_step": state.control_step,
        "simulation_time_s": state.simulation_time,
        "requested_action": request.to_mapping(),
        "requested_ee_pose": requested_mapping,
        "actual_ee_pose": ee.to_mapping(),
        **error,
        "joint_target": dict(target.arm_position),
        "servo_target": dict(target.arm_servo_position),
        "joint_achieved": {name: float(state.joint_position[name]) for name in ARM},
        "applied_control": applied.to_mapping(),
        "feedback": feedback.to_mapping(),
        "readiness": readiness.to_mapping(),
        "controller_memory": controller.memory().to_mapping(),
        "arm_trajectory_diagnostics": dict(getattr(controller, "last_arm_diagnostics", {})),
        "task_metrics": dict(metrics),
        "expert_diagnostics": dict(diagnostics),
        "requested_gripper_opening_m": float((float(public_action[-1]) + 1.0) * 0.5 * 0.08),
        "desired_gripper_opening_m": float(target.gripper.opening_m),
        "servo_gripper_opening_m": float(target.gripper.servo_opening_m),
        "measured_gripper_opening_m": float(feedback.gripper.opening_m),
        "closing_force_N": float(feedback.gripper.closing_force_N),
        "force_mode_active": bool(memory.force_mode_active),
        "force_mode_initialized": bool(memory.force_mode_initialized),
        "controller_close_ready": bool(readiness.gripper.close_ready),
        "finite": _finite(state.to_mapping()) and _finite(target.to_mapping()) and _finite(feedback.to_mapping()),
    }


def _reset(value, provider):
    artifact = value["artifact"]
    sample = sample_reset(artifact, int(value["profile"]["reset"]["seed"]))
    session = materialize_control(artifact, execution(provider), source=value["source"],
                                  binding=ControlBinding("panda-v1/gripper", 0.08))
    audit = NativeAudit(session, provider, artifact.timebase)
    realized = session.reset(sample)
    state = session.snapshot()
    feedback = session.control_feedback(state)
    controller = value["controller"]
    controller.reset(state, feedback)
    if audit.count or state.control_step != 0 or state.simulation_time != 0.0:
        raise ValueError("tracking reset applied hidden steps or nonzero time")
    return session, audit, sample, realized, state, feedback, controller


def _execute(value, provider, session, audit, controller, state, feedback, action, stage, diagnostics, info):
    request = RequestedAction("absolute_pose", "world", "quaternion_wxyz", tuple(map(float, action)))
    canonical, target = controller.compute(state, feedback, request)
    target_hash = target.identity_hash
    inner_rows = None
    if hasattr(controller, "inner_gripper_step"):
        native_diagnostic = None
        if stage == "close_gripper":
            native_diagnostic = lambda current: _contact_diagnostics(current, provider)
        state, applied_target, applied, inner_rows = session.step_control_interval(
            target, controller, audit=audit, diagnostic_readback=native_diagnostic
        )
        target = applied_target
    else:
        applied = session.apply_control(target)
        state = audit.step(target)
    feedback = session.control_feedback(state)
    obs, info, evaluation = observation(state, value["artifact"])
    readiness = controller.readiness(state, feedback)
    row = _controller_row(controller, state, feedback, request, canonical, target, applied,
                          readiness, action, stage, diagnostics, info["task_metrics"])
    if inner_rows is not None:
        row["outer_target_hash"] = target_hash
        row["final_inner_target_hash"] = target.identity_hash
        row["target_hash_unchanged"] = applied.target_hash == target.identity_hash
        row["gripper_inner_trace"] = inner_rows
        row["arm_target_held"] = all(x.get("arm_target_hash") == inner_rows[0].get("arm_target_hash")
                                      for x in inner_rows) if inner_rows else True
    else:
        row["target_hash_unchanged"] = target.identity_hash == target_hash and applied.target_hash == target_hash
    return state, feedback, obs, info, evaluation, row


def _contact_diagnostics(session, provider):
    """Diagnostic-only native contact projection; never read by R3 control."""
    from ..nutassembly.native import contact_readback
    raw = contact_readback(session, provider)
    if provider == "mujoco":
        contacts = raw.get("contacts", [])
        def classify(row):
            names = [str(x or "").lower() for x in row.get("source_body_names", [])]
            nut = any("nut" in name for name in names)
            finger = any("finger" in name for name in names)
            hand = any("hand" in name for name in names)
            table = any("table" in name for name in names)
            return {
                "finger_nut": bool(nut and finger),
                "hand_nut": bool(nut and hand),
                "finger_table": bool(table and finger),
                "normal_contact_force_native": abs(float(row.get("contact_frame_force_native", [0])[0])),
                "source_body_names": row.get("source_body_names"),
            }
        return {"provider": provider, "raw": raw,
                "classified_contacts": [classify(row) for row in contacts]}
    # GeoPhys exposes completed-substep body aggregates in this pinned runtime.
    # Preserve all semantic rows because pair-level finger attribution is absent.
    return {"provider": provider, "raw": raw,
            "pair_level_contact_available": False}


def _planner(value):
    solution = value["solution"]
    config = solution.config
    dt = solution.control_dt
    return AbsolutePosePlanner(AbsolutePosePlannerConfig(
        max_translation_per_step=config.translation_speed_m_s * dt,
        max_translation_acceleration_per_step=config.translation_acceleration_m_s2 * dt * dt,
        max_rotation_per_step=config.rotation_speed_rad_s * dt,
        max_rotation_acceleration_per_step=config.rotation_acceleration_rad_s2 * dt * dt,
        settle_steps=solution._ticks(config.settle_duration_s),
        max_steps=solution._ticks(config.max_stage_plan_s),
    ))


def _t0_goals(start):
    first = start.copy()
    first[2] = max(start[2] + 0.10, TABLE_TOP_Z + 0.25)
    lateral = first.copy()
    lateral[0] += T0_ROUTE_PROFILE["lateral_translation_m"]
    diagonal = lateral.copy()
    diagonal[:3] += np.asarray([-0.10, 0.10, 0.04])
    yaw = diagonal.copy()
    yaw_q = np.asarray([math.cos(0.18), 0.0, 0.0, math.sin(0.18)])
    yaw[3:] = quat_multiply_wxyz(yaw_q, yaw[3:])
    combined = yaw.copy()
    combined[:3] += np.asarray([-0.05, -0.06, 0.03])
    yaw_delta = np.asarray([math.cos(-0.12), 0.0, 0.0, math.sin(-0.12)])
    combined[3:] = quat_multiply_wxyz(yaw_delta, yaw[3:])
    return [
        ("vertical_translation", first),
        ("lateral_translation", lateral),
        ("diagonal_translation", diagonal),
        ("orientation_yaw", yaw),
        ("combined_translation_rotation", combined),
    ]


def _summary_errors(rows):
    positions = np.asarray([r["position_error_m"] for r in rows if r["position_error_m"] is not None], dtype=float)
    rotations = np.asarray([r["rotation_error_rad"] for r in rows if r["rotation_error_rad"] is not None], dtype=float)
    if not len(positions) or not len(rotations):
        return {"position_rms_m": None, "position_p95_m": None, "position_max_m": None,
                "rotation_rms_rad": None, "rotation_p95_rad": None, "rotation_max_rad": None}
    return {
        "position_rms_m": float(np.sqrt(np.mean(positions ** 2))),
        "position_p95_m": float(np.percentile(positions, 95)),
        "position_max_m": float(np.max(positions)),
        "rotation_rms_rad": float(np.sqrt(np.mean(rotations ** 2))),
        "rotation_p95_rad": float(np.percentile(rotations, 95)),
        "rotation_max_rad": float(np.max(rotations)),
    }


def run_t0(value, provider, folder):
    session = audit = None
    trace = []
    endpoints = []
    report = {"probe": "T0", "provider": provider, "pass": False,
              "rate": value["artifact"].timebase.to_mapping(),
              "controller_identity": value["controller_identity"],
              "solution_identity": value["solution_identity"],
              "dynamic_profile_sha256": value["dynamic_profile_sha256"],
              "trajectory_profile": T0_ROUTE_PROFILE}
    try:
        session, audit, sample, realized, state, feedback, controller = _reset(value, provider)
        reset_state_mapping = state.to_mapping()
        planner = _planner(value)
        start = _pose_array(state.pose_world["panda-v1/ee"])
        for name, goal in _t0_goals(start):
            segment_start = state.simulation_time
            segment_start_pose = _pose_array(state.pose_world["panda-v1/ee"])
            actions = planner.plan_to_pose(current_pose=segment_start_pose, goal_pose=goal, gripper=1.0)
            planned_steps = int(len(actions))
            move_steps = max(0, planned_steps - planner.config.settle_steps)
            segment_rows = []
            for action_index, action in enumerate(actions):
                state, feedback, _obs, info, _evaluation, row = _execute(
                    value, provider, session, audit, controller, state, feedback, action,
                    name, {"plan_action_index": action_index, "readiness_hold": False}, info=None)
                trace.append(row)
                segment_rows.append(row)
                if row["task_metrics"].get("grasped_nut", False):
                    raise ValueError("T0 path unexpectedly grasped the Nut")
            plan_exhausted_time = state.simulation_time
            stable_ticks = value["solution"]._ticks(value["solution"].config.readiness_stable_s)
            hold_limit_ticks = value["solution"]._ticks(value["solution"].config.max_pose_hold_s)
            stable = 0
            hold_rows = []
            while stable < stable_ticks and len(hold_rows) < hold_limit_ticks:
                hold_index = len(hold_rows)
                action = np.asarray((*goal[:7], 1.0), dtype=float)
                state, feedback, _obs, info, _evaluation, row = _execute(
                    value, provider, session, audit, controller, state, feedback, action,
                    name, {"plan_action_index": planned_steps + hold_index, "readiness_hold": True}, info=None)
                trace.append(row)
                hold_rows.append(row)
                segment_rows.append(row)
                within = (row["position_error_m"] <= POSE_POSITION_LIMIT_M
                          and row["rotation_error_rad"] <= POSE_ROTATION_LIMIT_RAD)
                stable = stable + 1 if within else 0
                if row["task_metrics"].get("grasped_nut", False):
                    raise ValueError("T0 path unexpectedly contacted/grasped the Nut")
            direction = goal[:3] - segment_start_pose[:3]
            length = float(np.linalg.norm(direction))
            direction = direction / length if length > 1e-12 else np.zeros(3)
            actual_positions = np.asarray([r["actual_ee_pose"]["position"] for r in hold_rows], dtype=float)
            overshoot = (float(max(0.0, np.max((actual_positions - goal[:3]) @ direction)))
                         if len(actual_positions) else None)
            endpoint_window = hold_rows[-stable_ticks:]
            endpoint_max_pos = max((r["position_error_m"] for r in endpoint_window), default=None)
            endpoint_max_rot = max((r["rotation_error_rad"] for r in endpoint_window), default=None)
            endpoint_pass = (stable >= stable_ticks and len(endpoint_window) == stable_ticks
                             and endpoint_max_pos <= POSE_POSITION_LIMIT_M
                             and endpoint_max_rot <= POSE_ROTATION_LIMIT_RAD)
            endpoints.append({
                "waypoint": name,
                "requested_goal_pose": {"position": goal[:3].tolist(), "quaternion_wxyz": goal[3:7].tolist()},
                "segment_entry_time_s": segment_start,
                "planned_trajectory_duration_s": planned_steps * value["artifact"].timebase.control_dt,
                "planned_motion_duration_s": move_steps * value["artifact"].timebase.control_dt,
                "planned_steps": planned_steps,
                "time_to_stable_readiness_s": (state.simulation_time - segment_start) if endpoint_pass else None,
                "actual_duration_until_stable_or_timeout_s": state.simulation_time - segment_start,
                "readiness_hold_s": len(hold_rows) * value["artifact"].timebase.control_dt,
                "plan_exhaustion_time_s": plan_exhausted_time,
                "actual_endpoint_pose": state.pose_world["panda-v1/ee"].to_mapping(),
                "max_position_error_in_stable_window_m": endpoint_max_pos,
                "max_rotation_error_in_stable_window_rad": endpoint_max_rot,
                "position_overshoot_along_segment_m": overshoot,
                "stable_window_ticks": stable,
                "required_stable_window_ticks": stable_ticks,
                "measured_endpoint_window_ticks": len(endpoint_window),
                "pass": bool(endpoint_pass),
            })
            if not endpoint_pass:
                report["failure_boundary"] = "T0_endpoint_pose_readiness_not_reached"
                break
        report.update(
            pass_=bool(len(endpoints) == len(_t0_goals(start)) and all(x["pass"] for x in endpoints)),
            endpoints=endpoints,
            error_summary=_summary_errors(trace),
            total_transitions=len(trace),
            native_substeps_observed=audit.count,
            reset_sample_hash=sample.identity_hash,
            reset_realized_matches_snapshot=realized.measured_state.to_mapping() == reset_state_mapping,
        )
        report["pass"] = report.pop("pass_")
        if report["pass"]:
            report["failure_boundary"] = None
        else:
            report.setdefault("failure_boundary", "T0_endpoint_pose_readiness_not_reached")
    except Exception as exc:
        report.update(failure_boundary=report.get("failure_boundary") or "T0_execution",
                      error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        if audit:
            _write(folder / "native_audit.json", audit.boundaries)
            audit.close()
        if session:
            session.close()
        _write(folder / "trace.json", trace)
        _write(folder / "report.json", report)
    return report


def _stage_endpoint(stage, rows, value):
    dt = value["artifact"].timebase.control_dt
    required = value["solution"]._ticks(value["solution"].config.readiness_stable_s)
    # The solution's stable counter includes the final plan sample when it is
    # already inside the readiness bounds. Counting only rows labeled
    # readiness_hold drops that sample and reports 49/50 at an otherwise
    # qualified endpoint. Gate on the last required observed boundaries across
    # the whole stage; retain hold-only duration as a separate diagnostic.
    window = rows[-required:]
    max_pos = max((row["stage_goal_position_error_m"] for row in window), default=None)
    max_rot = max((row["stage_goal_rotation_error_rad"] for row in window), default=None)
    capture_rows = [row["capture_drift"] for row in window if row.get("capture_drift") is not None]
    max_rel_pos = max((row["position_m"] for row in capture_rows), default=None)
    max_rel_rot = max((row["rotation_rad"] for row in capture_rows), default=None)
    pose_pass = (len(window) == required and max_pos is not None and max_pos <= POSE_POSITION_LIMIT_M
                 and max_rot is not None and max_rot <= POSE_ROTATION_LIMIT_RAD)
    capture_pass = (stage not in {"verify_lift", "raise_for_transport", "move_above_square_peg",
                                  "align_nut_yaw", "descend_to_peg_top"}
                    or (max_rel_pos is not None and max_rel_pos <= CAPTURE_POSITION_LIMIT_M
                        and max_rel_rot is not None and max_rel_rot <= CAPTURE_ROTATION_LIMIT_RAD))
    return {
        "stage": stage,
        "planned_trajectory_duration_s": rows[0]["planned_trajectory_duration_s"] if rows else None,
        "actual_physical_duration_s": (rows[-1]["simulation_time_s"] - rows[0]["stage_entry_time_s"]
                                       if rows else None),
        "readiness_hold_s": sum(bool(row["expert_diagnostics"].get("readiness_hold")) for row in rows) * dt,
        "endpoint_position_error_max_m": max_pos,
        "endpoint_rotation_error_max_rad": max_rot,
        "endpoint_capture_position_drift_max_m": max_rel_pos,
        "endpoint_capture_rotation_drift_max_rad": max_rel_rot,
        "stable_window_ticks": len(window),
        "required_stable_window_ticks": required,
        "pose_gate_pass": bool(pose_pass),
        "capture_gate_pass": bool(capture_pass),
    }


def run_loaded(value, provider, folder, probe):
    session = audit = None
    trace = []
    stage_rows = {}
    endpoints = []
    close_rows = []
    inner_servo_rows = []
    report = {"probe": probe, "provider": provider, "pass": False,
              "rate": value["artifact"].timebase.to_mapping(),
              "controller_identity": value["controller_identity"],
              "solution_identity": value["solution_identity"],
              "dynamic_profile_sha256": value["dynamic_profile_sha256"]}
    try:
        session, audit, sample, realized, state, feedback, controller = _reset(value, provider)
        artifact, solution = value["artifact"], value["solution"]
        obs, info, evaluation = observation(state, artifact)
        solution.reset(obs, info, METADATA)
        close_start_time = None
        close_authorization = None
        capture_baseline = None
        grasp_authorized = False
        grasp_loss = False
        max_rel_pos = 0.0
        max_rel_rot = 0.0
        verify_lift_pass = False
        close_pose_pass = False
        current_stage = solution.stage
        stage_entry = {current_stage: state.simulation_time}
        stage_plan_duration = {current_stage: len(solution._actions) * artifact.timebase.control_dt}
        t1_stages = ("verify_lift", "raise_for_transport", "move_above_square_peg",
                     "align_nut_yaw", "descend_to_peg_top")
        auth_ticks = value["solution"]._ticks(value["profile"]["solution"]["fallback_window_s"])
        while not solution.done and not solution.failed:
            public = solution.act()
            before_stage = solution.stage
            if before_stage == "close_gripper" and close_start_time is None:
                close_start_time = state.simulation_time
            goal_before = solution._goal.copy()
            plan_duration = stage_plan_duration.get(before_stage)
            diagnostics = dict(public.diagnostics)
            if before_stage == "verify_lift" and capture_baseline is None:
                capture_baseline = _relative_pose(state)
            state, feedback, obs, info, evaluation, row = _execute(
                value, provider, session, audit, controller, state, feedback,
                public.action, before_stage, diagnostics, info)
            row["stage_entry_time_s"] = stage_entry.get(before_stage, state.simulation_time)
            row["planned_trajectory_duration_s"] = plan_duration
            row["stage_goal_pose"] = {"position": goal_before[:3].tolist(), "quaternion_wxyz": goal_before[3:7].tolist()}
            stage_goal_error = _pose_error(goal_before, state)
            row["stage_goal_position_error_m"] = stage_goal_error["position_error_m"]
            row["stage_goal_rotation_error_rad"] = stage_goal_error["rotation_error_rad"]
            if capture_baseline is not None:
                drift = _relative_drift(capture_baseline, state)
                row["capture_drift"] = drift
                max_rel_pos = max(max_rel_pos, drift["position_m"])
                max_rel_rot = max(max_rel_rot, drift["rotation_rad"])
            else:
                row["capture_drift"] = None
            if before_stage == "close_gripper":
                inner_servo_rows.extend(row.get("gripper_inner_trace", []))
                close_rows.append({
                    "simulation_time_s": state.simulation_time,
                    "requested_opening_m": row["requested_gripper_opening_m"],
                    "desired_opening_m": row["desired_gripper_opening_m"],
                    "servo_opening_m": row["servo_gripper_opening_m"],
                    "measured_opening_m": row["measured_gripper_opening_m"],
                    "closing_force_N": row["closing_force_N"],
                    "force_mode_active": row["force_mode_active"],
                    "force_mode_initialized": row["force_mode_initialized"],
                    "controller_close_ready": row["controller_close_ready"],
                    "grasped_nut": bool(info["task_metrics"].get("grasped_nut", False)),
                })
            if grasp_authorized and not info["task_metrics"].get("grasped_nut", False):
                grasp_loss = True
            row["grasp_authorized"] = grasp_authorized
            stage_rows.setdefault(before_stage, []).append(row)
            trace.append(row)
            solution.observe(obs, evaluation.reward, False, False, info, readiness=controller.readiness(state, feedback))
            after_stage = solution.stage
            if after_stage != before_stage:
                endpoint = _stage_endpoint(before_stage, stage_rows[before_stage], value)
                endpoints.append(endpoint)
                if before_stage == "close_gripper":
                    window = close_rows[-auth_ticks:]
                    opening_span = (max((x["measured_opening_m"] for x in window), default=math.nan)
                                    - min((x["measured_opening_m"] for x in window), default=math.nan))
                    minimum_force = min((x["closing_force_N"] for x in window), default=math.nan)
                    all_grasped = len(window) == auth_ticks and all(x["grasped_nut"] for x in window)
                    fallback = (len(window) == auth_ticks
                                and opening_span <= value["solution_config"].opening_stable_range_m
                                and minimum_force >= value["solution_config"].grasp_min_closing_force_N
                                and all_grasped)
                    ready = bool(row["controller_close_ready"])
                    branch = "controller_close_ready" if ready else "stable_grasp_fallback" if fallback else "unclassified"
                    auth_time = state.simulation_time - close_start_time if close_start_time is not None else None
                    close_authorization = {
                        "authorization_branch": branch,
                        "authorization_time_s": auth_time,
                        "controller_close_ready": ready,
                        "stable_fallback_satisfied": bool(fallback),
                        "fallback_window_ticks": auth_ticks,
                        "fallback_window_duration_s": auth_ticks * artifact.timebase.control_dt,
                        "fallback_minimum_force_N": minimum_force,
                        "fallback_opening_span_m": opening_span,
                        "fallback_grasped_nut_throughout": all_grasped,
                        "end_opening_m": feedback.gripper.opening_m,
                        "end_closing_force_N": feedback.gripper.closing_force_N,
                        "pose_gate_at_authorization": endpoint["pose_gate_pass"],
                    }
                    grasp_authorized = branch in {"controller_close_ready", "stable_grasp_fallback"}
                    row["close_transition_authorization"] = branch
                if before_stage == "verify_lift":
                    verify_lift_pass = bool(endpoint["pose_gate_pass"] and endpoint["capture_gate_pass"]
                                            and info["task_metrics"].get("lifted_nut", False))
                if probe == "G0" and before_stage == "verify_lift":
                    break
                if probe == "T1" and before_stage == "descend_to_peg_top":
                    break
                stage_entry[after_stage] = state.simulation_time
                stage_plan_duration[after_stage] = len(solution._actions) * artifact.timebase.control_dt
        if solution.failed:
            report["failure_boundary"] = "nutassembly_solution/" + str(solution.failure_reason)
        goal_stages = ("verify_lift",) if probe == "G0" else t1_stages
        endpoints_by_stage = {item["stage"]: item for item in endpoints}
        required_endpoints_pass = all(endpoints_by_stage.get(stage, {}).get("pose_gate_pass", False)
                                      and endpoints_by_stage.get(stage, {}).get("capture_gate_pass", False)
                                      for stage in goal_stages)
        close_time_ok = bool(close_authorization and close_authorization["authorization_branch"] in
                             {"controller_close_ready", "stable_grasp_fallback"}
                             and close_authorization["authorization_time_s"] <= CLOSE_TIME_LIMIT_S
                             and close_authorization["pose_gate_at_authorization"])
        capture_ok = max_rel_pos <= CAPTURE_POSITION_LIMIT_M and max_rel_rot <= CAPTURE_ROTATION_LIMIT_RAD
        complete = (verify_lift_pass if probe == "G0" else
                    bool(verify_lift_pass and all(stage in endpoints_by_stage for stage in t1_stages)))
        passed = bool(close_time_ok and verify_lift_pass and required_endpoints_pass
                      and not grasp_loss and capture_ok and complete)
        report.update(
            pass_=passed,
            endpoints=endpoints,
            close_authorization=close_authorization,
            close_stage_trace=close_rows,
            inner_servo_trace=inner_servo_rows,
            verify_lift_pass=verify_lift_pass,
            max_capture_position_drift_m=max_rel_pos,
            max_capture_rotation_drift_rad=max_rel_rot,
            grasp_loss=grasp_loss,
            total_transitions=len(trace),
            native_substeps_observed=audit.count,
            reset_sample_hash=sample.identity_hash,
            provider_build_identity=provider_build_identity(provider),
            final_task_metrics=dict(info["task_metrics"]),
        )
        report["pass"] = report.pop("pass_")
        if report["pass"]:
            report["failure_boundary"] = None
        else:
            report.setdefault("failure_boundary", "G0_close_or_verify_lift_gate" if probe == "G0"
                              else "T1_loaded_tracking_or_capture_gate")
    except Exception as exc:
        report.update(failure_boundary=report.get("failure_boundary") or probe + "_execution",
                      error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        if audit:
            _write(folder / "native_audit.json", audit.boundaries)
            audit.close()
        if session:
            session.close()
        _write(folder / "trace.json", trace)
        _write(folder / "stage_endpoints.json", endpoints)
        _write(folder / "report.json", report)
    return report


def _context(rate, profile_path, dynamic_profile_path):
    value = _r4_context(rate, profile_path=profile_path,
                        dynamic_profile_path=dynamic_profile_path)
    controller = ProductionCanonicalPandaControllerR3.from_source(
        value["artifact"], value["source"], profile=value["dynamic_profile"]
    )
    value["controller"] = controller
    value["controller_identity"] = controller.identity
    return value


def run(root, probe, rate, provider, candidate, profile_path, dynamic_profile_path, attempt=1):
    value = _context(rate, profile_path=profile_path, dynamic_profile_path=dynamic_profile_path)
    label = rate.lower().replace("na-", "")
    candidate_label = f"candidate-{int(candidate):02d}"
    category = {"T0": "t0", "G0": "g0"}[probe]
    folder = Path(root) / category / provider / label
    if int(attempt) > 1:
        folder = folder / f"attempt-{int(attempt):02d}"
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "report.json").exists():
        raise FileExistsError("tracking Evidence collision")
    source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if probe == "T0":
        report = run_t0(value, provider, folder)
    elif probe in {"G0", "T1"}:
        report = run_loaded(value, provider, folder, probe)
    else:
        raise ValueError("probe must be T0, G0, or T1")
    report.update(
        candidate_id="R5-R3-C11-REFERENCE",
        tracking_worker_sha256=source_sha,
        task_artifact_hash=value["artifact"].identity_hash,
        source_recipe_hash=value["recipe_identity"],
        profile_sha256=value["profile_sha256"],
        dynamic_profile_sha256=value["dynamic_profile_sha256"],
        controller_rate_profile=value["controller"].rate_profile_mapping()
        if hasattr(value["controller"], "rate_profile_mapping") else None,
    )
    _write(folder / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--probe", choices=("T0", "G0"), required=True)
    parser.add_argument("--rate", choices=RATE_NAMES, required=True)
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True)
    parser.add_argument("--candidate", type=int, default=11)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--profile-path", type=Path, default=PROFILE_PATH)
    parser.add_argument("--dynamic-profile", type=Path,
                        default=EVIDENCE_ROOT / "c11_dynamic_profile.yaml")
    args = parser.parse_args()
    report = run(args.root, args.probe, args.rate, args.provider, args.candidate,
                 args.profile_path, args.dynamic_profile, args.attempt)
    print(json.dumps({key: report.get(key) for key in
                      ("probe", "candidate_id", "provider", "rate", "pass", "failure_boundary",
                       "error_summary", "close_authorization", "verify_lift_pass",
                       "max_capture_position_drift_m", "max_capture_rotation_drift_rad")},
                     indent=2, allow_nan=False), flush=True)
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
