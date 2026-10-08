"""Isolated A0/A1/D0/D1/D2 worker for P1.8-E-R3 nominal acceptance."""
from dataclasses import asdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import traceback

import numpy as np

from ....controllers.canonical import RequestedAction
from ....controllers.canonical.contracts import digest
from ....controllers.canonical.kinematics import ARM
from ....runtime.sessions.control import ControlBinding, materialize_control
from ....runtime.sessions.provenance import provider_build_identity
from ....tasks.nut_assembly.canonical_reset import sample_reset
from ....trajectory.canonical import (
    BoundaryRecord,
    CanonicalRecorder,
    EpisodeMetadata,
    TransitionRecord,
    load,
    save,
)
from ..multirate.common import NativeAudit, write
from ..nutassembly.common import METADATA, observation
from ..nutassembly.native import contact_readback
from ..p1_2_runtime import execution
from .common import context, sha256_file


RESET_BOUND = 1.0e-5


def _finite(value):
    if isinstance(value, dict):
        return all(_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite(v) for v in value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float, np.number)):
        return math.isfinite(float(value))
    return True


def _no_native_storage(mapping):
    forbidden = {"qpos", "qvel", "qacc", "ctrl", "actuator_id", "body_id", "site_id", "native_id", "mjmodel", "mjdata"}
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in forbidden:
                    return False
                if not visit(child):
                    return False
        elif isinstance(value, (tuple, list)):
            return all(visit(child) for child in value)
        return True
    return visit(mapping)


def _reset_checks(state, sample):
    joints = {name: abs(float(state.joint_position[name]) - float(value))
              for name, value in sample.joint_position.items()}
    pose_checks = {}
    for name, requested in sample.poses_world.items():
        measured = state.pose_world[name]
        pose_checks[name] = {
            "position_max_abs_m": max(abs(float(a) - float(b)) for a, b in zip(requested.position, measured.position)),
            "quaternion_max_abs": max(abs(float(a) - float(b)) for a, b in zip(requested.quaternion_wxyz, measured.quaternion_wxyz)),
        }
    return {
        "joint_position_max_abs": max(joints.values(), default=0.0),
        "joint_position_errors": joints,
        "pose_checks": pose_checks,
        "joint_velocity_max_abs": max((abs(float(v)) for v in state.joint_velocity.values()), default=0.0),
        "control_step": state.control_step,
        "simulation_time_s": state.simulation_time,
        "finite": _finite(state.to_mapping()),
        "semantic_field_names": {"joints": sorted(state.joint_position), "poses": sorted(state.pose_world)},
        "no_native_storage_fields": _no_native_storage(state.to_mapping()),
    }


def _boundary(controller, state, feedback, info):
    return BoundaryRecord(
        state.control_step,
        state.simulation_time,
        state,
        feedback,
        controller.readiness(state, feedback),
        {key: float(value) for key, value in info["task_metrics"].items()},
        bool(info["is_success"]),
        bool(info["task_failure"]),
    )


def _make_noop_action(state):
    pose = state.pose_world["panda-v1/ee"]
    return RequestedAction(
        "absolute_pose", "world", "quaternion_wxyz",
        tuple(float(v) for v in (*pose.position, *pose.quaternion_wxyz, 1.0)),
    )


def precheck(root, rate, provider, phase="phase_a"):
    root = Path(root)
    folder = root / phase / "precheck" / rate.lower().replace("na-", "") / provider
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / "report.json"
    if report_path.exists():
        raise FileExistsError("precheck Evidence collision")
    value = context(rate)
    artifact, source, controller = value["artifact"], value["source"], value["controller"]
    sample = sample_reset(artifact, int(value["profile"]["reset"]["seed"]))
    exec_spec = execution(provider)
    session = audit = None
    report = {"rate": rate, "provider": provider, "pass": False, "task_artifact_hash": artifact.identity_hash,
              "reset_sample_hash": sample.identity_hash, "source_recipe_hash": value["recipe_identity"],
              "provider_build_identity": provider_build_identity(provider)}
    try:
        session = materialize_control(artifact, exec_spec, source=source,
                                      binding=ControlBinding("panda-v1/gripper", .08))
        audit = NativeAudit(session, provider, artifact.timebase)
        realized = session.reset(sample)
        initial = session.snapshot()
        feedback = session.control_feedback(initial)
        controller.reset(initial, feedback)
        reset = _reset_checks(initial, sample)
        reset["hidden_native_steps"] = audit.count
        reset["realized_state_equals_snapshot"] = realized.measured_state.to_mapping() == initial.to_mapping()
        no_op = _make_noop_action(initial)
        canonical, target = controller.compute(initial, feedback, no_op)
        applied = session.apply_control(target)
        after = audit.step(target)
        measured_feedback = session.control_feedback(after)
        next_checks = {
            "control_step": after.control_step,
            "simulation_time_s": after.simulation_time,
            "expected_simulation_time_s": artifact.timebase.control_dt,
            "time_increment_s": after.simulation_time - initial.simulation_time,
            "native_substep_count": audit.boundaries[-1]["observed_native_substeps"],
            "requested_substeps": artifact.timebase.control_substeps,
            "zoh_target_hash": target.identity_hash,
            "all_substep_hashes_identical": audit.boundaries[-1]["all_substep_hashes_identical"],
            "applied_target_hash_matches": applied.target_hash == target.identity_hash,
            "canonical_state_finite": _finite(after.to_mapping()),
            "canonical_state_no_native_ids": _no_native_storage(after.to_mapping()),
            "feedback_finite": _finite(measured_feedback.to_mapping()),
        }
        steps_before_repeat_reset = audit.count
        repeated_realized = session.reset(sample)
        repeated = session.snapshot()
        repeat_exact = repeated.to_mapping() == initial.to_mapping()
        repeated_realized_matches = repeated_realized.measured_state.to_mapping() == initial.to_mapping()
        repeat_reset_no_hidden_steps = audit.count == steps_before_repeat_reset
        result = {
            "reset": reset,
            "one_control_boundary": next_checks,
            "repeat_reset_exact": repeat_exact,
            "repeat_realized_matches_initial": repeated_realized_matches,
            "repeat_reset_no_hidden_steps": repeat_reset_no_hidden_steps,
            "repeat_sample_identity_unchanged": sample.identity_hash == report["reset_sample_hash"],
            "sample_mapping": sample.to_mapping(),
            "artifact_timebase": artifact.timebase.to_mapping(),
            "source_xml_sha256": hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
            "normalized_source_xml_sha256": value["recipe"]["normalized_source_xml_sha256"],
            "controller_identity": controller.identity,
            "solution_identity": value["solution_identity"],
        }
        reset_ok = (reset["control_step"] == 0 and reset["simulation_time_s"] == 0.0
                    and reset["hidden_native_steps"] == 0 and reset["finite"]
                    and reset["no_native_storage_fields"] and reset["realized_state_equals_snapshot"]
                    and reset["joint_position_max_abs"] <= RESET_BOUND
                    and reset["joint_velocity_max_abs"] <= RESET_BOUND
                    and all(x["position_max_abs_m"] <= RESET_BOUND and x["quaternion_max_abs"] <= RESET_BOUND
                            for x in reset["pose_checks"].values()))
        step_ok = (next_checks["control_step"] == 1
                   and abs(next_checks["simulation_time_s"] - artifact.timebase.control_dt) <= math.ulp(artifact.timebase.control_dt)
                   and next_checks["native_substep_count"] == artifact.timebase.control_substeps
                   and next_checks["all_substep_hashes_identical"] and next_checks["applied_target_hash_matches"]
                   and next_checks["canonical_state_finite"] and next_checks["canonical_state_no_native_ids"]
                   and next_checks["feedback_finite"])
        report.update(result)
        report["pass"] = bool(reset_ok and step_ok and repeat_exact and repeated_realized_matches and repeat_reset_no_hidden_steps)
        report["failure_boundary"] = None if report["pass"] else "reset_source_timebase_precheck"
        write(folder / "native_audit.json", audit.boundaries)
    except Exception as error:
        report.update(failure_boundary="materialization_or_reset_precheck", error=str(error), traceback=traceback.format_exc())
    finally:
        if audit:
            audit.close()
        if session:
            session.close()
        write(report_path, report)
    return report


def _episode_metadata(value, sample, realized, provider, controller, solution):
    artifact, source = value["artifact"], value["source"]
    return EpisodeMetadata(
        "canonical-trajectory-metadata-v0",
        artifact.identity_hash,
        sample,
        realized,
        execution(provider),
        {key: json.dumps(item, sort_keys=True) for key, item in provider_build_identity(provider).items()},
        {
            "source_xml_sha256": hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
            "source_recipe_sha256": value["recipe_identity"],
            "normalized_source_xml_sha256": value["recipe"]["normalized_source_xml_sha256"],
            "asset_profile_sha256": sha256_file("task_env/tasks/nut_assembly/profiles/nutassembly-nominal-v1.json"),
            "semantic_bindings_json": json.dumps({key: dict(getattr(source, key)) for key in
                ("joints", "bodies", "frames", "free_joints", "joint_targets")}, sort_keys=True),
        },
        artifact.timebase,
        controller.identity,
        solution.identity,
        value["readiness_identity"],
        digest({"solution_config": asdict(solution.config), "profile": "nutassembly-nominal-v1"}),
        sample.task_seed,
        "evaluation",
    )


def _native_contact_snapshot(session, provider):
    if provider in ("geophys", "mujoco"):
        return contact_readback(session, provider)
    return {"status": "provider diagnostic adapter not implemented", "provider": provider}


def _verify_lift_summary(value, start, state, feedback, metrics, initial_nut_z, trace, *, completed):
    if start is None:
        return None
    start_ee, start_nut = start["ee_pose"], start["nut_pose"]
    end_ee, end_nut = state.pose_world["panda-v1/ee"], state.pose_world["square-nut-v1"]
    return {
        "start_control_step": start["control_step"],
        "end_control_step": state.control_step,
        "start_time_s": start["simulation_time_s"],
        "end_time_s": state.simulation_time,
        "requested_ee_lift_m": float(value["solution_config"].verify_lift_m),
        "actual_ee_lift_m": float(end_ee.position[2] - start_ee["position"][2]),
        "actual_nut_lift_m": float(end_nut.position[2] - start_nut["position"][2]),
        "nut_max_lift_from_reset_m": float(max(
            (x["state"]["pose_world"]["square-nut-v1"]["position"][2] for x in trace),
            default=initial_nut_z) - initial_nut_z),
        "nut_ee_relative_position_drift_m": _relative_position_drift(
            np.asarray(start_nut["position"], dtype=float), np.asarray(start_ee["position"], dtype=float),
            np.asarray(end_nut.position, dtype=float), np.asarray(end_ee.position, dtype=float)),
        "nut_ee_relative_orientation_drift_rad": _relative_orientation_drift(
            np.asarray(start_nut["quaternion_wxyz"], dtype=float), np.asarray(start_ee["quaternion_wxyz"], dtype=float),
            np.asarray(end_nut.quaternion_wxyz, dtype=float), np.asarray(end_ee.quaternion_wxyz, dtype=float)),
        "gripper_opening_m": float(feedback.gripper.opening_m),
        "closing_force_N": float(feedback.gripper.closing_force_N),
        "lifted_nut": bool(metrics.get("lifted_nut", False)),
        "translation_slip_bound_m": float(value["solution_config"].capture_translation_slip_m),
        "rotation_slip_bound_rad": float(value["solution_config"].capture_rotation_slip_rad),
        "verify_lift_pass": bool(completed),
    }


def expert(root, rate, provider, phase="phase_a"):
    root = Path(root)
    folder = root / phase / "expert" / rate.lower().replace("na-", "") / provider
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "report.json").exists():
        raise FileExistsError("expert Evidence collision")
    value = context(rate)
    artifact, source, controller = value["artifact"], value["source"], value["controller"]
    solution = value["solution"]
    sample = sample_reset(artifact, int(value["profile"]["reset"]["seed"]))
    provider_execution = execution(provider)
    report = {"rate": rate, "provider": provider, "success": False, "failure_boundary": "materialization",
              "task_artifact_hash": artifact.identity_hash, "reset_sample_hash": sample.identity_hash,
              "controller_identity": controller.identity, "solution_identity": solution.identity,
              "source_recipe_hash": value["recipe_identity"]}
    session = audit = recorder = None
    trace = []
    contacts = []
    close_rows = []
    verify_lift_start = None
    verify_lift_result = None
    current_stage = "materialization"
    events = {name: None for name in ("grasp", "lift", "hover", "insert", "release", "success")}
    try:
        session = materialize_control(artifact, provider_execution, source=source,
                                      binding=ControlBinding("panda-v1/gripper", .08))
        audit = NativeAudit(session, provider, artifact.timebase)
        realized = session.reset(sample)
        state = session.snapshot()
        if audit.count != 0 or state.control_step != 0 or state.simulation_time != 0.0:
            raise ValueError("expert reset applied a hidden settle or nonzero timebase")
        feedback = session.control_feedback(state)
        controller.reset(state, feedback)
        obs, info, evaluation = observation(state, artifact)
        solution.reset(obs, info, METADATA)
        recorder = CanonicalRecorder(_episode_metadata(value, sample, realized, provider, controller, solution),
                                     _boundary(controller, state, feedback, info))
        initial_nut = np.asarray(state.pose_world["square-nut-v1"].position, dtype=float)
        previous_stage = solution.stage
        report["failure_boundary"] = "closed_loop_expert"
        while not solution.done and not solution.failed:
            public = solution.act()
            current_stage = public.stage
            request = RequestedAction("absolute_pose", "world", "quaternion_wxyz", tuple(map(float, public.action)))
            canonical, target = controller.compute(state, feedback, request)
            target_hash = target.identity_hash
            applied = session.apply_control(target)
            state = audit.step(target)
            feedback = session.control_feedback(state)
            obs, info, evaluation = observation(state, artifact)
            readiness = controller.readiness(state, feedback)
            before_stage = solution.stage
            if before_stage == "verify_lift" and verify_lift_start is None:
                verify_lift_start = {
                    "control_step": state.control_step - 1,
                    "simulation_time_s": state.simulation_time - artifact.timebase.control_dt,
                    "ee_pose": recorder.boundaries[-1].state.pose_world["panda-v1/ee"].to_mapping(),
                    "nut_pose": recorder.boundaries[-1].state.pose_world["square-nut-v1"].to_mapping(),
                }
            solution.observe(obs, evaluation.reward, False, False, info, readiness=readiness)
            after = _boundary(controller, state, feedback, info)
            hold = bool(public.diagnostics.get("readiness_hold", False))
            diagnostics = {key: json.dumps(value, sort_keys=True) for key, value in public.diagnostics.items()}
            recorder.append(TransitionRecord(request, canonical, target, applied, float(evaluation.reward), False,
                False, public.stage, diagnostics, not hold, hold), after)
            if target.identity_hash != target_hash or applied.target_hash != target_hash:
                raise ValueError("canonical target mutated or detached")
            metrics = dict(info["task_metrics"])
            for event, metric in (("lift", "lifted_nut"), ("hover", "hovered_over_peg"),
                                  ("insert", "inserted_on_peg"), ("release", "released_nut"),
                                  ("success", "task_success")):
                if metrics.get(metric) and events[event] is None:
                    events[event] = {"control_step": state.control_step, "simulation_time_s": state.simulation_time}
            row = {
                "stage": public.stage,
                "control_step": state.control_step,
                "simulation_time_s": state.simulation_time,
                "state": state.to_mapping(),
                "feedback": feedback.to_mapping(),
                "readiness": readiness.to_mapping(),
                "requested_action": request.to_mapping(),
                "canonical_action": canonical.to_mapping(),
                "controller_target": target.to_mapping(),
                "applied_control": applied.to_mapping(),
                "metrics": metrics,
                "expert_diagnostics": dict(public.diagnostics),
                "controller_memory": controller.memory().to_mapping(),
                "finite": _finite(state.to_mapping()) and _finite(feedback.to_mapping()) and _finite(target.to_mapping()),
                "no_native_storage_fields": _no_native_storage(state.to_mapping()),
            }
            trace.append(row)
            if public.stage == "close_gripper":
                close_rows.append({"opening_m": float(feedback.gripper.opening_m),
                                   "closing_force_N": float(feedback.gripper.closing_force_N),
                                   "grasped_nut": bool(metrics["grasped_nut"])})
            if public.stage in ("close_gripper", "verify_lift", "raise_for_transport", "move_above_square_peg",
                                "align_nut_yaw", "descend_to_peg_top", "lower_nut_to_table", "open_gripper"):
                contacts.append({"stage": public.stage, "control_step": state.control_step,
                                 "simulation_time_s": state.simulation_time,
                                 "native": _native_contact_snapshot(session, provider)})
            if previous_stage == "close_gripper" and solution.stage != "close_gripper":
                ticks = max(1, int(math.ceil(float(value["profile"]["solution"]["fallback_window_s"])
                                             / artifact.timebase.control_dt - 1e-10)))
                window = close_rows[-ticks:]
                opening_span = max((x["opening_m"] for x in window), default=math.nan) - min(
                    (x["opening_m"] for x in window), default=math.nan)
                all_grasped = len(window) == ticks and all(x["grasped_nut"] for x in window)
                minimum_force = min((x["closing_force_N"] for x in window), default=math.nan)
                fallback_satisfied = (
                    len(window) == ticks
                    and opening_span <= float(value["solution_config"].opening_stable_range_m)
                    and all_grasped
                    and minimum_force >= float(value["solution_config"].grasp_min_closing_force_N)
                )
                branch = ("controller_close_ready" if readiness.gripper.close_ready else
                          "stable_grasp_fallback" if fallback_satisfied else "unclassified")
                events["grasp"] = {
                    "control_step": state.control_step,
                    "simulation_time_s": state.simulation_time,
                    "authorization_branch": branch,
                    "controller_close_ready": bool(readiness.gripper.close_ready),
                    "fallback_window_ticks": ticks,
                    "fallback_window_physical_seconds": ticks * artifact.timebase.control_dt,
                    "fallback_minimum_force_N": minimum_force,
                    "fallback_opening_span_m": opening_span,
                    "fallback_grasped_nut_throughout": all_grasped,
                    "fallback_satisfied": fallback_satisfied,
                    "end_opening_m": float(feedback.gripper.opening_m),
                    "end_closing_force_N": float(feedback.gripper.closing_force_N),
                }
                row["close_transition_authorization"] = branch
            if before_stage == "verify_lift" and solution.stage != "verify_lift" and verify_lift_start is not None:
                verify_lift_result = _verify_lift_summary(value, verify_lift_start, state, feedback,
                    info["task_metrics"], initial_nut[2], trace, completed=True)
            previous_stage = solution.stage
        success = bool(solution.done and not solution.failed and evaluation.success
                       and info["task_metrics"].get("inserted_on_peg")
                       and info["task_metrics"].get("gripper_released")
                       and info["task_metrics"].get("released_nut")
                       and info["task_metrics"].get("task_success"))
        reason = "expert_success" if success else solution.failure_reason or "expert_ended_without_state_success"
        trajectory = recorder.freeze(reason)
        trajectory_path = folder / ("trajectory.h5" if success else "unsuccessful_trajectory.h5")
        save(trajectory_path, trajectory)
        loaded = load(trajectory_path)
        if loaded.to_mapping() != trajectory.to_mapping():
            raise ValueError("strict CanonicalTrajectory roundtrip mismatch")
        final_metrics = dict(info["task_metrics"])
        if verify_lift_result is None:
            verify_lift_result = _verify_lift_summary(value, verify_lift_start, state, feedback,
                info["task_metrics"], initial_nut[2], trace, completed=(solution.stage != "verify_lift"))
        report.update(
            success=success,
            expert_done=bool(solution.done),
            expert_failed=bool(solution.failed),
            failure_reason=solution.failure_reason,
            final_stage=solution.stage,
            failure_stage=None if success else trace[-1]["stage"] if trace else None,
            T=len(loaded.transitions),
            duration_s=state.simulation_time,
            holds=loaded.hold_count,
            trajectory_path=str(trajectory_path.resolve()),
            logical_hash=loaded.identity_hash,
            h5_sha256=sha256_file(trajectory_path),
            roundtrip_exact=True,
            events=events,
            verify_lift=verify_lift_result,
            final_metrics=final_metrics,
            max_nut_lift_from_reset_m=max((float(x["state"]["pose_world"]["square-nut-v1"]["position"][2])
                                           - initial_nut[2] for x in trace), default=0.0),
            source_xml_sha256=hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
            source_recipe_hash=value["recipe_identity"],
            native_substep_count_valid=(audit.count == len(loaded.transitions) * artifact.timebase.control_substeps),
            sample_mapping_unchanged=(sample.to_mapping() == loaded.metadata.reset_sample.to_mapping()),
            final_precision={key: final_metrics.get(key) for key in ("peg_xy_error", "yaw_error", "peg_z_error",
                                                                    "gripper_opening", "eef_to_nut_dist")},
            provider_version=provider_build_identity(provider),
            time_to_grasp_s=events["grasp"]["simulation_time_s"] if events["grasp"] else None,
            time_to_lift_s=events["lift"]["simulation_time_s"] if events["lift"] else None,
            time_to_hover_s=events["hover"]["simulation_time_s"] if events["hover"] else None,
            time_to_insert_s=events["insert"]["simulation_time_s"] if events["insert"] else None,
            time_to_release_s=events["release"]["simulation_time_s"] if events["release"] else None,
            time_to_success_s=events["success"]["simulation_time_s"] if events["success"] else None,
        )
        report["failure_boundary"] = None if success else "closed_loop_expert/" + str(report["failure_stage"] or report["final_stage"])
    except Exception as error:
        report.update(failure_boundary="expert_execution/" + str(current_stage), error=str(error),
                      traceback=traceback.format_exc(), completed_transitions=len(trace))
        if recorder is not None and trace:
            try:
                partial = recorder.freeze("expert_exception")
                path = folder / "partial_trajectory.h5"
                save(path, partial)
                loaded = load(path)
                report.update(partial_trajectory_path=str(path.resolve()), partial_roundtrip_exact=loaded.to_mapping() == partial.to_mapping(),
                              partial_logical_hash=loaded.identity_hash, partial_h5_sha256=sha256_file(path), T=len(partial.transitions))
            except Exception as serialization_error:
                report["partial_serialization_error"] = str(serialization_error)
    finally:
        if audit:
            write(folder / "native_audit.json", audit.boundaries)
            audit.close()
        if session:
            session.close()
        write(folder / "trace.json", trace)
        write(folder / "contacts.json", contacts)
        write(folder / "report.json", report)
    return report


def _relative_position_drift(start_nut, start_ee, end_nut, end_ee):
    return float(np.linalg.norm((end_nut - end_ee) - (start_nut - start_ee)))


def _relative_orientation_drift(start_nut, start_ee, end_nut, end_ee):
    from ....utils.rotation import quat_multiply_wxyz, quat_angle_wxyz
    start_inv = start_ee.copy(); start_inv[1:] *= -1
    end_inv = end_ee.copy(); end_inv[1:] *= -1
    start_relative = quat_multiply_wxyz(start_inv, start_nut)
    end_relative = quat_multiply_wxyz(end_inv, end_nut)
    return float(quat_angle_wxyz(start_relative, end_relative))


def d0(root, rate, source_provider, phase="phase_a"):
    root = Path(root)
    source_folder = root / phase / "expert" / rate.lower().replace("na-", "") / source_provider
    ref = json.loads((source_folder / "report.json").read_text())
    if not ref.get("success"):
        raise ValueError("D0 requires a successful governed expert golden")
    trajectory_path = Path(ref["trajectory_path"])
    trajectory = load(trajectory_path)
    if trajectory.identity_hash != ref["logical_hash"] or sha256_file(trajectory_path) != ref["h5_sha256"]:
        raise ValueError("D0 golden identity/hash mismatch")
    value = context(rate)
    controller = value["controller"]
    controller.reset(trajectory.boundaries[0].state, trajectory.boundaries[0].feedback)
    actions = []
    mismatches = []
    for i, transition in enumerate(trajectory.transitions):
        stored = transition.controller_target
        request = RequestedAction("absolute_joint", None, "none", tuple(
            [float(stored.arm_position[name]) for name in ARM]
            + [2.0 * float(stored.gripper.opening_m) / .08 - 1.0]))
        canonical, recomputed = controller.compute(trajectory.boundaries[i].state,
                                                   trajectory.boundaries[i].feedback, request)
        actions.append(request.to_mapping())
        if (recomputed.to_mapping() != stored.to_mapping()
                or recomputed.identity_hash != stored.identity_hash):
            mismatches.append({"transition": i, "stored_hash": stored.identity_hash,
                               "recomputed_hash": recomputed.identity_hash})
    folder = root / phase / "d0" / rate.lower().replace("na-", "") / source_provider
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "report.json").exists():
        raise FileExistsError("D0 Evidence collision")
    action_hash = digest(actions)
    write(folder / "actions.json", actions)
    report = {"rate": rate, "source_provider": source_provider, "pass": not mismatches,
              "exact_matches": len(actions) - len(mismatches), "total": len(actions),
              "target_mismatches": mismatches, "action_sequence_identity": action_hash,
              "trajectory_logical_hash": trajectory.identity_hash,
              "controller_identity": controller.identity}
    write(folder / "report.json", report)
    return report


def replay(root, rate, source_provider, provider, route, phase="phase_a", source_phase=None):
    root = Path(root)
    source_phase = source_phase or phase
    rate_label = rate.lower().replace("na-", "")
    source_folder = root / source_phase / "expert" / rate_label / source_provider
    ref = json.loads((source_folder / "report.json").read_text())
    if not ref.get("success"):
        raise ValueError("replay requires a successful frozen expert source")
    trajectory_path = Path(ref["trajectory_path"])
    trajectory = load(trajectory_path)
    if trajectory.identity_hash != ref["logical_hash"] or sha256_file(trajectory_path) != ref["h5_sha256"]:
        raise ValueError("replay golden identity/hash mismatch")
    d0_folder = root / source_phase / "d0" / rate_label / source_provider
    d0_report = json.loads((d0_folder / "report.json").read_text())
    actions = json.loads((d0_folder / "actions.json").read_text())
    if not d0_report["pass"] or digest(actions) != d0_report["action_sequence_identity"]:
        raise ValueError("frozen D0 public action identity mismatch")
    value = context(rate)
    artifact, source, controller = value["artifact"], value["source"], value["controller"]
    sample = sample_reset(artifact, int(value["profile"]["reset"]["seed"]))
    if sample.to_mapping() != trajectory.metadata.reset_sample.to_mapping():
        raise ValueError("replay ResetSample does not match source golden")
    folder = root / phase / route.lower() / rate_label / source_provider / provider
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "report.json").exists():
        raise FileExistsError("replay Evidence collision")
    report = {"rate": rate, "source_provider": source_provider, "provider": provider,
              "route": route, "execution_valid": False, "task_valid": False,
              "action_sequence_identity": d0_report["action_sequence_identity"],
              "source_trajectory_hash": trajectory.identity_hash}
    session = audit = None
    trace = []
    contacts = []
    try:
        session = materialize_control(artifact, execution(provider), source=source,
                                      binding=ControlBinding("panda-v1/gripper", .08))
        audit = NativeAudit(session, provider, artifact.timebase)
        realized = session.reset(sample)
        state = session.snapshot()
        feedback = session.control_feedback(state)
        if state.control_step != 0 or state.simulation_time != 0.0 or realized.measured_state.to_mapping() != state.to_mapping():
            raise ValueError("replay reset boundary mismatch")
        if route == "D2":
            controller.reset(state, feedback)
        initial_nut_z = float(state.pose_world["square-nut-v1"].position[2])
        expected_joint_names = set(state.joint_position)
        expected_pose_names = set(state.pose_world)
        first_success = None
        for i, stored_transition in enumerate(trajectory.transitions):
            stored_target = stored_transition.controller_target
            if route == "D1":
                target = stored_target
                request = canonical = None
            elif route == "D2":
                request = RequestedAction.from_mapping(actions[i])
                canonical, target = controller.compute(state, feedback, request)
            else:
                raise ValueError("unsupported replay route")
            target_hash = target.identity_hash
            applied = session.apply_control(target)
            state = audit.step(target)
            feedback = session.control_feedback(state)
            _, info, evaluation = observation(state, artifact)
            if (target.identity_hash != target_hash or applied.target_hash != target_hash
                    or not _finite(state.to_mapping()) or not _finite(feedback.to_mapping())
                    or not _no_native_storage(state.to_mapping())):
                raise ValueError("replay target/state validity failure")
            if set(state.joint_position) != expected_joint_names or set(state.pose_world) != expected_pose_names:
                raise ValueError("semantic field set changed")
            if evaluation.success and first_success is None:
                first_success = {"control_step": state.control_step, "simulation_time_s": state.simulation_time}
            row = {
                "control_step": state.control_step,
                "simulation_time_s": state.simulation_time,
                "target_hash": target_hash,
                "applied_target_hash": applied.target_hash,
                "state": state.to_mapping(),
                "feedback": feedback.to_mapping(),
                "task_metrics": info["task_metrics"],
                "is_success": evaluation.success,
                "task_failure": evaluation.failure,
                "finite": True,
                "no_native_ids": True,
            }
            if route == "D2":
                row["requested_action"] = request.to_mapping()
                row["canonical_action"] = canonical.to_mapping()
                row["controller_target"] = target.to_mapping()
            trace.append(row)
            if row["task_metrics"].get("grasped_nut") or row["task_metrics"].get("lifted_nut") or row["task_metrics"].get("inserted_on_peg"):
                contacts.append({"control_step": state.control_step, "simulation_time_s": state.simulation_time,
                                 "task_metrics": row["task_metrics"], "native": _native_contact_snapshot(session, provider)})
        final_metrics = dict(trace[-1]["task_metrics"]) if trace else {}
        lifts = [float(row["task_metrics"]["nut_z"]) - initial_nut_z for row in trace]
        report.update(
            execution_valid=bool(len(trace) == len(trajectory.transitions)
                and audit.count == len(trace) * artifact.timebase.control_substeps
                and all(row["finite"] and row["no_native_ids"] and row["target_hash"] == row["applied_target_hash"] for row in trace)
                and state.control_step == len(trajectory.transitions)
                and abs(state.simulation_time - len(trace) * artifact.timebase.control_dt) <= max(math.ulp(state.simulation_time), math.ulp(artifact.timebase.control_dt))),
            task_valid=bool(final_metrics.get("task_success", False) and evaluation.success),
            first_success=first_success,
            final_metrics=final_metrics,
            final_lift_m=lifts[-1] if lifts else None,
            max_lift_m=max(lifts, default=None),
            failure_boundary=None if final_metrics.get("task_success", False) else "replay_task_success_not_reached",
            T=len(trace),
            native_substeps_observed=audit.count,
            requested_native_substeps=len(trace) * artifact.timebase.control_substeps,
            target_mutation=False,
            reset_sample_hash=sample.identity_hash,
        )
    except Exception as error:
        report.update(failure_boundary=report.get("failure_boundary") or "replay_execution", error=str(error), traceback=traceback.format_exc(), T=len(trace))
    finally:
        if audit:
            write(folder / "native_audit.json", audit.boundaries)
            audit.close()
        if session:
            session.close()
        write(folder / "trace.json", trace)
        write(folder / "contacts.json", contacts)
        write(folder / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--route", choices=("precheck", "expert", "D0", "D1", "D2"), required=True)
    parser.add_argument("--rate", choices=("NA-TB500", "NA-TB100", "NA-TB50"), required=True)
    parser.add_argument("--provider", choices=("geophys", "mujoco", "sapien", "genesis"), default="geophys")
    parser.add_argument("--source-provider", choices=("geophys", "mujoco", "sapien", "genesis"))
    parser.add_argument("--route-name", choices=("D1", "D2"))
    parser.add_argument("--phase", default="phase_a", choices=("phase_a", "phase_b", "phase_b/primary_to_boundary"))
    parser.add_argument("--source-phase", choices=("phase_a", "phase_b"))
    args = parser.parse_args()
    if args.route == "precheck":
        result = precheck(args.root, args.rate, args.provider, args.phase)
    elif args.route == "expert":
        result = expert(args.root, args.rate, args.provider, args.phase)
    elif args.route == "D0":
        result = d0(args.root, args.rate, args.source_provider or args.provider, args.phase)
    else:
        source_provider = args.source_provider
        if not source_provider or not args.route_name:
            parser.error("D1/D2 requires --source-provider and --route-name")
        result = replay(args.root, args.rate, source_provider, args.provider, args.route_name,
                        args.phase, args.source_phase)
    print(json.dumps(result, indent=2, allow_nan=False), flush=True)
    return 0 if result.get("pass", result.get("success", result.get("execution_valid", False) and result.get("task_valid", False))) else 1


if __name__ == "__main__":
    raise SystemExit(main())
