"""Independent validation of closed LIBERO worker result bundles."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any

import h5py
import numpy as np

from task_env.controllers.canonical.contracts import (
    AppliedMixedActuatorCommandV1, MixedActuatorCommandV1, digest,
)
from task_env.artifacts import ResetPlanV1
from task_env.recorders import inspect_trajectory_h5, load_structured_control_records_h5
from task_env.utils.rotation import (
    quat_angle_wxyz, quat_multiply_wxyz, quat_wxyz_to_matrix,
    rotate_vector_wxyz, rotation_vector_error,
)

from bench_deploy.libero.artifacts.contracts import TASK_1
from bench_deploy.libero.controllers.osc import LiberoMixedControllerV7
from bench_deploy.libero.tasks.solution import solution_identity_v8
from bench_deploy.libero.trajectory.worker import (
    _PINNED_MUJOCO_RUNTIME_IDENTITY, _TASK1_COMPOSED_XML_SHA256,
    _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256, _canonical,
    _pose_world_mapping_matches, _public_motion_metrics,
    _source_on_predicate_oracle_v1, _task1_iterative_resolver_identity,
    _validate_physical_state_monitor, _validate_public_motion_gate,
    _verify_solution_source_bundle,
)

def _validate_parent_run_record(bundle_path: Path, result: Mapping[str, Any],
                                run_record_path: Path, expected_lock_path: Path) -> dict[str, Any]:
    """Bind the semantic bundle to its bounded native parent process receipt."""
    record_path = Path(run_record_path).resolve(strict=True)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    is_solution = result.get("schema_version") == "r07-v210-task-solution-worker-result-v8"
    accepted_schemas = {"r07-v210-required123-run-record-v1"} if is_solution else {"r07c-d01-run-record-v1"}
    if record.get("schema_version") not in accepted_schemas:
        raise ValueError("parent run record schema is unsupported")
    if (record.get("exit_code") != 0 or record.get("termination_reason") is not None
            or record.get("process_group_confirmed_exited") is not True):
        raise ValueError("parent native worker did not exit successfully with its process group closed")
    parent_lock_path = record.get("lock_path")
    if (record.get("lock_acquired") is not True
            or record.get("lock_released_after_group_exit") is not True
            or type(parent_lock_path) is not str
            or Path(parent_lock_path).resolve() != Path(expected_lock_path).resolve()):
        raise ValueError("parent native lock receipt is missing, mismatched, or not released after worker exit")
    argv = record.get("argv")
    if (not isinstance(argv, list) or "-m" not in argv
            or "bench_deploy.libero.script.cli" not in argv):
        raise ValueError("parent run record does not identify the D01 native worker module")
    if is_solution and "--task-solution" not in argv:
        raise ValueError("parent run record does not identify the task #1 Solution route")
    if not argv or Path(argv[0]).resolve() != Path(sys.executable).resolve():
        raise ValueError("parent run record used an unpinned Python interpreter or camera checkout")
    cwd = record.get("cwd")
    if is_solution:
        expected_cwd = record_path.parent.resolve()
        if (type(cwd) is not str or Path(cwd).resolve() != expected_cwd
                or expected_cwd != bundle_path.parent.parent.resolve()):
            raise ValueError("task Solution parent run directory differs from its recorded bundle layout")
    elif cwd != "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora":
        raise ValueError("D01 parent run record did not use the pinned camera checkout")
    try:
        worker_index = argv.index("--run-worker")
        worker_dir = Path(argv[worker_index + 1]).resolve()
    except (ValueError, IndexError, TypeError) as exc:
        raise ValueError("parent run record omits the worker bundle output directory") from exc
    if worker_dir != bundle_path.parent.resolve():
        raise ValueError("parent run record points to a different worker bundle")
    try:
        steps_index = argv.index("--steps")
        recorded_steps = int(argv[steps_index + 1])
    except (ValueError, IndexError, TypeError) as exc:
        raise ValueError("parent run record omits the bounded D01 step limit") from exc
    counts = [episode.get("h5", {}).get("transition_count") for episode in result.get("episodes", ())]
    recorded_rows = tuple(result.get("episode_rows", ()))
    try:
        row_arg_index = argv.index("--rows")
        argv_rows = []
        for token in argv[row_arg_index + 1:]:
            if token.startswith("--"):
                break
            argv_rows.append(int(token))
        recorded_argv_rows = tuple(argv_rows)
    except (ValueError, TypeError):
        recorded_argv_rows = (0, 1, 2)
    if (any(type(value) is not int or value < 1 or value > recorded_steps for value in counts)
            or (not is_solution and any(value != recorded_steps for value in counts))
            or recorded_rows != tuple(episode.get("row_index") for episode in result.get("episodes", ()))
            or recorded_argv_rows != recorded_rows):
        raise ValueError("parent worker step limit differs from one or more episode records")
    environment = record.get("environment")
    expected_pythonpath = (
        "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora/GeoPhys/src:"
        "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora"
    )
    if not isinstance(environment, dict) or environment.get("PYTHONPATH") != expected_pythonpath:
        raise ValueError("parent run record did not use the frozen camera/GeoPhys import path")
    output_root = record_path.parents[2]
    log_paths = {}
    for stream in ("stdout", "stderr"):
        relative = record.get(f"{stream}_path")
        if type(relative) is not str or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"parent run record has an unsafe {stream} path")
        log_path = (output_root / relative).resolve(strict=True)
        if output_root not in log_path.parents:
            raise ValueError(f"parent {stream} path escaped the package output root")
        raw = log_path.read_bytes()
        if len(raw) != record.get(f"{stream}_bytes"):
            raise ValueError(f"parent {stream} byte count differs from its process receipt")
        log_paths[stream] = (log_path, raw)
    stdout_lines = [line for line in log_paths["stdout"][1].decode("utf-8").splitlines() if line.strip()]
    if not stdout_lines:
        raise ValueError("parent native worker stdout omits its completion receipt")
    try:
        worker_stdout = json.loads(stdout_lines[-1])
    except json.JSONDecodeError as exc:
        raise ValueError("parent native worker stdout completion receipt is malformed") from exc
    if (worker_stdout.get("status") != "complete"
            or worker_stdout.get("result_sha256") != result.get("result_sha256")
            or worker_stdout.get("episode_count") != result.get("episode_count")
            or worker_stdout.get("transition_count") != result.get("transition_count")
            or worker_stdout.get("observation_count") != result.get("observation_count")
            or worker_stdout.get("native_step_count") != result.get("native_step_count")):
        raise ValueError("parent stdout result/exit summary does not match the independently read worker bundle")
    return {
        "schema_version": "r07c-d01-parent-process-receipt-v1",
        "status": "verified_parent_exit_and_lock_release",
        "run_record_path": str(record_path),
        "run_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
        "exit_code": 0,
        "termination_reason": None,
        "lock_path": str(Path(expected_lock_path).resolve()),
        "lock_released_after_group_exit": True,
        "process_group_confirmed_exited": True,
        "stdout_path": str(log_paths["stdout"][0]),
        "stderr_path": str(log_paths["stderr"][0]),
    }

def _equivalent_wxyz_quaternions(left: Any, right: Any, *, tolerance: float = 1e-7) -> bool:
    """Compare unit quaternions by orientation, allowing the equivalent q/-q signs."""
    try:
        left_value = np.asarray(left, dtype=np.float64).reshape(-1)
        right_value = np.asarray(right, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return False
    if (left_value.shape != (4,) or right_value.shape != (4,)
            or not np.isfinite(left_value).all() or not np.isfinite(right_value).all()
            or abs(float(np.linalg.norm(left_value)) - 1.0) > tolerance
            or abs(float(np.linalg.norm(right_value)) - 1.0) > tolerance):
        return False
    return min(
        float(np.linalg.norm(left_value - right_value)),
        float(np.linalg.norm(left_value + right_value)),
    ) <= tolerance

def _validate_v4_osc_receipt(canonical_action: Mapping[str, Any], expected_controller: Mapping[str, Any],
                             target: MixedActuatorCommandV1, public_action: np.ndarray,
                             h5_joint_position: np.ndarray | None, h5_ee_pose: np.ndarray | None,
                             resource_close: Mapping[str, Any], *,
                             receipt_override: Mapping[str, Any] | None = None,
                             initial_joint_reference: np.ndarray | None = None,
                             source_xml_sha256: str = _TASK1_COMPOSED_XML_SHA256,
                             source_closure_digest: str = _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256,
                             expected_desired_twist_world: np.ndarray | None = None) -> None:
    """Independently recompute the bounded V4 OSC law from recorded source-state values."""
    from task_env.utils.rotation import quat_wxyz_to_matrix

    receipt = receipt_override or canonical_action.get("controller_receipt")
    controller_schema = expected_controller.get("schema_version")
    physics_rate_profile = controller_schema in {
        "libero-mixed-controller-identity-v4", "libero-mixed-controller-identity-v5",
        "libero-mixed-controller-identity-v6", "libero-mixed-controller-identity-v7",
    }
    velocity_feedforward_profile = controller_schema in {
        "libero-mixed-controller-identity-v5", "libero-mixed-controller-identity-v7",
    }
    expected_receipt_schema = (
        "libero-mixed-control-receipt-v7" if controller_schema == "libero-mixed-controller-identity-v7" else
        "libero-mixed-control-receipt-v6" if controller_schema == "libero-mixed-controller-identity-v6" else
        "libero-mixed-control-receipt-v5" if velocity_feedforward_profile else
        "libero-mixed-control-receipt-v4" if physics_rate_profile
        else "libero-mixed-control-receipt-v3"
    )
    expected_algorithm = (
        "source_osc_pose_pd_with_bounded_planner_twist_feedforward_qfrc_bias_v1"
        if controller_schema == "libero-mixed-controller-identity-v7" else
        "robosuite_osc_pose_uncoupled_lambda_and_qfrc_bias_v1"
        if controller_schema == "libero-mixed-controller-identity-v6" else
        "source_osc_pose_pd_with_bounded_planner_twist_feedforward_v1" if velocity_feedforward_profile else
        "robosuite_osc_pose_uncoupled_lambda_and_reset_nullspace_v2" if physics_rate_profile
        else "robosuite_osc_pose_uncoupled_lambda_and_nullspace_v1"
    )
    if (not isinstance(receipt, Mapping)
            or canonical_action.get("schema_version") != "libero-world-pose-canonical-v1"
            or canonical_action.get("arm_target_schema_version") != "canonical-arm-target-v1"
            or canonical_action.get("arm_target_source_xml_sha256") != source_xml_sha256
            or not isinstance(expected_controller.get("arm_resolver_identity"), str)
            or len(expected_controller.get("arm_resolver_identity", "")) != 64
            or canonical_action.get("arm_target_controller_identity")
               != expected_controller.get("arm_resolver_identity")
                or tuple(canonical_action.get("arm_joint_order", ()))
                   != tuple(expected_controller.get("arm_joint_order", ()))
                or tuple(canonical_action.get("qdesired_joint_order", ()))
                   != tuple(f"joint{i}" for i in range(1, 8))
            or canonical_action.get("controller_identity") != expected_controller.get("identity_sha256")
            or receipt.get("schema_version") != expected_receipt_schema
            or receipt.get("controller_identity") != expected_controller.get("identity_sha256")
            or receipt.get("algorithm") != expected_algorithm
            or receipt.get("source_state_profile_id") != expected_controller.get("source_state_profile_id")
            or receipt.get("source_xml_sha256") != source_xml_sha256
            or receipt.get("source_closure_digest") != source_closure_digest
            or receipt.get("source_model_identity_sha256") != resource_close.get("model_identity_sha256")
            or receipt.get("tcp_site_name") != "gripper0_grip_site"
            or receipt.get("hold_policy") != expected_controller.get("hold_policy")
            or (expected_controller.get("gravity_feedforward_source") is not None
                and receipt.get("gravity_feedforward_source")
                    != expected_controller.get("gravity_feedforward_source"))
            or (physics_rate_profile
                and receipt.get("nullspace_reference_policy")
                    != expected_controller.get("nullspace_reference_policy"))
            or (physics_rate_profile
                and receipt.get("q_reference_source") != "reset_initial_joint_v1")
            or canonical_action.get("arm_resolution_diagnostics") != receipt.get("canonical_arm_resolution")):
        raise ValueError("task Solution v4 OSC receipt is missing or differs from the frozen task/source identity")
    resolution_diagnostics = canonical_action.get("arm_resolution_diagnostics")
    if (not isinstance(resolution_diagnostics, Mapping)
            or resolution_diagnostics.get("schema_version") != "canonical-arm-resolution-diagnostics-v1"
            or resolution_diagnostics.get("method_id") != "shared_canonical_dls_iterative_v1"
            or type(resolution_diagnostics.get("iteration_count")) is not int
            or resolution_diagnostics.get("iteration_count") < 1
            or resolution_diagnostics.get("converged") is not True
            or float(resolution_diagnostics.get("position_residual_m", float("inf")))
               > float(resolution_diagnostics.get("position_tolerance_m", -1.0))
            or float(resolution_diagnostics.get("orientation_residual_rad", float("inf")))
               > float(resolution_diagnostics.get("orientation_tolerance_rad", -1.0))
            or any(name not in resolution_diagnostics for name in (
                "initial_position_gap_m", "initial_orientation_gap_rad",
                "model_position_tolerance_m", "model_orientation_tolerance_rad",
            ))):
        raise ValueError("task Solution v4 canonical arm resolution did not report converged FK residuals")
    try:
        model_position_gap = float(resolution_diagnostics["initial_position_gap_m"])
        model_orientation_gap = float(resolution_diagnostics["initial_orientation_gap_rad"])
        model_position_tolerance = float(resolution_diagnostics["model_position_tolerance_m"])
        model_orientation_tolerance = float(resolution_diagnostics["model_orientation_tolerance_rad"])
    except (TypeError, ValueError) as exc:
        raise ValueError("task Solution v4 source-model agreement receipt is malformed") from exc
    if (not all(math.isfinite(value) for value in (
            model_position_gap, model_orientation_gap,
            model_position_tolerance, model_orientation_tolerance,
        ))
            or min(model_position_gap, model_orientation_gap) < 0.0
            or min(model_position_tolerance, model_orientation_tolerance) <= 0.0
            or model_position_gap > model_position_tolerance
            or model_orientation_gap > model_orientation_tolerance):
        raise ValueError("task Solution v4 public TCP and source FK agreement exceeds its recorded gate")
    try:
        q_ref = np.asarray(
            receipt.get("q_reference_rad") if physics_rate_profile
            else canonical_action.get("qdesired_rad"), dtype=np.float64,
        )
        q = np.asarray(receipt.get("q_rad"), dtype=np.float64)
        qdot = np.asarray(receipt.get("qdot_rad_s"), dtype=np.float64)
        mass = np.asarray(receipt.get("mass_matrix_arm"), dtype=np.float64)
        jacobian = np.asarray(receipt.get("jacobian_world"), dtype=np.float64)
        feedforward_receipt_field = expected_controller.get(
            "gravity_feedforward_receipt_field", "bias_minus_passive_Nm",
        )
        bias = np.asarray(receipt.get(feedforward_receipt_field), dtype=np.float64)
        current_position = np.asarray(receipt.get("current_world_pose", {}).get("position_m"), dtype=np.float64)
        current_rotation = np.asarray(receipt.get("current_world_pose", {}).get("rotation_matrix"), dtype=np.float64)
        target_position = np.asarray(receipt.get("target_world_pose", {}).get("position_m"), dtype=np.float64)
        target_quaternion = np.asarray(receipt.get("target_world_pose", {}).get("quaternion_wxyz"), dtype=np.float64)
        position_error = np.asarray(receipt.get("position_error_m"), dtype=np.float64)
        orientation_error = np.asarray(receipt.get("orientation_error_rad_vector"), dtype=np.float64)
        ee_velocity = np.asarray(receipt.get("ee_velocity"), dtype=np.float64)
        desired_twist = np.asarray(receipt.get("desired_tcp_twist_world"), dtype=np.float64)
        task_torque = np.asarray(receipt.get("task_torque_Nm"), dtype=np.float64)
        null_torque = np.asarray(receipt.get("nullspace_torque_Nm"), dtype=np.float64)
        raw_torque = np.asarray(receipt.get("raw_torque_Nm"), dtype=np.float64)
        applied_torque = np.asarray(receipt.get("applied_torque_Nm"), dtype=np.float64)
        clipped = np.asarray(receipt.get("torque_clipped"), dtype=bool)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("task Solution v4 OSC arrays are malformed") from exc
    vectors7 = (q_ref, q, qdot, bias, task_torque, null_torque, raw_torque, applied_torque)
    if (any(value.shape != (7,) or not np.isfinite(value).all() for value in vectors7)
            or mass.shape != (7, 7) or not np.isfinite(mass).all()
            or jacobian.shape != (6, 7) or not np.isfinite(jacobian).all()
            or current_position.shape != (3,) or not np.isfinite(current_position).all()
            or current_rotation.shape != (3, 3) or not np.isfinite(current_rotation).all()
            or target_position.shape != (3,) or not np.isfinite(target_position).all()
            or target_quaternion.shape != (4,) or not np.isfinite(target_quaternion).all()
            or position_error.shape != (3,) or not np.isfinite(position_error).all()
            or orientation_error.shape != (3,) or not np.isfinite(orientation_error).all()
            or ee_velocity.shape != (6,) or not np.isfinite(ee_velocity).all()
            or desired_twist.shape != (6,) or not np.isfinite(desired_twist).all()
            or clipped.shape != (7,)
            or public_action.shape != (8,) or not np.isfinite(public_action).all()
            or (h5_joint_position is not None and (
                h5_joint_position.shape != (9,) or not np.isfinite(h5_joint_position).all()))
            or (h5_ee_pose is not None and (
                h5_ee_pose.shape != (7,) or not np.isfinite(h5_ee_pose).all()))):
        raise ValueError("task Solution v4 OSC receipt contains invalid dimensions or non-finite values")
    if ((h5_joint_position is not None and not np.allclose(
                q, h5_joint_position[:7], rtol=0.0, atol=2e-6))
            or (h5_ee_pose is not None and not np.allclose(
                current_position, h5_ee_pose[:3], rtol=0.0, atol=0.003))
            or (h5_ee_pose is not None and not np.allclose(
                current_rotation,
                quat_wxyz_to_matrix(np.asarray(h5_ee_pose[3:7], dtype=np.float64)),
                rtol=0.0, atol=0.03))
            or (initial_joint_reference is not None and not np.allclose(
                q_ref, initial_joint_reference, rtol=0.0, atol=2e-7))
            or not np.allclose(position_error, target_position - current_position,
                               rtol=0.0, atol=2e-8)
            or not np.allclose(target_position, np.asarray(public_action[:3]), rtol=0.0, atol=1e-7)
            or not _equivalent_wxyz_quaternions(target_quaternion, public_action[3:7])):
        raise ValueError("task Solution v4 OSC source-state pose differs from H5 or requested action")
    target_rotation = quat_wxyz_to_matrix(target_quaternion)
    recomputed_orientation = 0.5 * sum(
        (np.cross(current_rotation[:, axis], target_rotation[:, axis]) for axis in range(3)),
        start=np.zeros(3, dtype=np.float64),
    )
    recomputed_velocity = jacobian @ qdot
    kp_pos = float(expected_controller["position_kp_N_per_m"])
    kp_ori = float(expected_controller["orientation_kp_Nm_per_rad"])
    damping = float(expected_controller["damping_ratio"])
    expected_twist = (np.zeros(6, dtype=np.float64) if expected_desired_twist_world is None
                      else np.asarray(expected_desired_twist_world, dtype=np.float64))
    if (expected_twist.shape != (6,) or not np.isfinite(expected_twist).all()
            or not np.allclose(desired_twist, expected_twist, rtol=0.0, atol=2e-8)
            or (velocity_feedforward_profile and expected_desired_twist_world is None)
            or (not velocity_feedforward_profile and np.any(desired_twist != 0.0))
            or not np.allclose(orientation_error, recomputed_orientation, rtol=0.0, atol=2e-8)
            or not np.allclose(ee_velocity, recomputed_velocity, rtol=0.0, atol=2e-8)):
        raise ValueError("task Solution v4 OSC pose error or end-effector velocity is inconsistent")
    mass_inv = np.linalg.inv(mass)
    j_pos, j_ori = jacobian[:3], jacobian[3:]
    lambda_full = np.linalg.pinv(jacobian @ mass_inv @ jacobian.T)
    lambda_pos = np.linalg.pinv(j_pos @ mass_inv @ j_pos.T)
    lambda_ori = np.linalg.pinv(j_ori @ mass_inv @ j_ori.T)
    j_bar = mass_inv @ jacobian.T @ lambda_full
    nullspace = np.eye(7, dtype=np.float64) - j_bar @ jacobian
    desired_force = kp_pos * position_error + 2.0 * math.sqrt(kp_pos) * damping * (desired_twist[:3] - recomputed_velocity[:3])
    desired_moment = kp_ori * orientation_error + 2.0 * math.sqrt(kp_ori) * damping * (desired_twist[3:] - recomputed_velocity[3:])
    expected_task = jacobian.T @ np.concatenate((lambda_pos @ desired_force,
                                                 lambda_ori @ desired_moment))
    kp_null = float(expected_controller["nullspace_kp_per_s2"])
    expected_null = nullspace.T @ (
        mass @ (kp_null * (q_ref - q) - 2.0 * math.sqrt(kp_null) * qdot)
    )
    expected_raw = expected_task + expected_null + bias
    limits = np.asarray([expected_controller["torque_limits_Nm"][f"joint{i}"]
                         for i in range(1, 8)], dtype=np.float64)
    expected_applied = np.clip(expected_raw, -limits, limits)
    expected_clipped = np.abs(expected_raw - expected_applied) > 1e-12
    if (not np.allclose(task_torque, expected_task, rtol=0.0, atol=2e-7)
            or not np.allclose(null_torque, expected_null, rtol=0.0, atol=2e-7)
            or not np.allclose(raw_torque, expected_raw, rtol=0.0, atol=2e-7)
            or not np.allclose(applied_torque, expected_applied, rtol=0.0, atol=2e-7)
            or not np.array_equal(clipped, expected_clipped)
            or not np.allclose([target.channel_values[f"joint{i}"] for i in range(1, 8)],
                               expected_applied, rtol=0.0, atol=2e-7)):
        raise ValueError("task Solution v4 mixed Target differs from independently recomputed OSC torque law")
    aggregate_opening = 0.04 * (float(public_action[7]) + 1.0)
    if (not 0.0 <= aggregate_opening <= 0.08
            or abs(float(receipt.get("opening_m", float("nan"))) - aggregate_opening) > 1e-8
            or not np.allclose(
                [target.channel_values["finger_joint1"], target.channel_values["finger_joint2"]],
                (aggregate_opening / 2.0, -aggregate_opening / 2.0), rtol=0.0, atol=1e-8)):
        raise ValueError("task Solution v4 gripper action differs from its mixed Target mapping")

def _validate_v5_stepwise_osc_receipt(
    canonical_action: Mapping[str, Any], expected_controller: Mapping[str, Any],
    first_target: MixedActuatorCommandV1, public_action: np.ndarray,
    h5_joint_position: np.ndarray, h5_ee_pose: np.ndarray,
    resource_close: Mapping[str, Any], initial_joint_reference: np.ndarray,
    *, outer_transition_index: int,
    source_xml_sha256: str = _TASK1_COMPOSED_XML_SHA256,
    source_closure_digest: str = _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256,
    expected_desired_twist_world: np.ndarray | None = None,
) -> int:
    """Read back every physics-rate OSC command in one recorded outer action."""
    from task_env.controllers.canonical.contracts import MixedActuatorCommandV1

    interval = canonical_action.get("physics_rate_control_v1")
    count = expected_controller.get("control_substeps")
    expected_revision = outer_transition_index * count
    if (not isinstance(interval, Mapping)
            or interval.get("schema_version") != "mixed-actuator-stepwise-interval-receipt-v1"
            or interval.get("provider_name") != "mujoco"
            or interval.get("native_substep_count") != count
            or interval.get("physics_dt_s") != expected_controller.get("physics_dt_s")
            or interval.get("start_control_step") != outer_transition_index
            or interval.get("end_control_step") != outer_transition_index + 1
            or interval.get("start_state_revision") != expected_revision
            or interval.get("end_state_revision") != expected_revision + count
            or not isinstance(interval.get("substeps"), (list, tuple))
            or len(interval["substeps"]) != count):
        raise ValueError("task Solution v5 stepwise OSC interval receipt has an invalid outer/native boundary")
    root_receipt = canonical_action.get("controller_receipt")
    rows = interval["substeps"]
    if root_receipt != rows[0].get("controller_receipt"):
        raise ValueError("task Solution v5 outer OSC receipt differs from its first physics substep")
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError("task Solution v5 physics substep receipt is malformed")
        try:
            target = MixedActuatorCommandV1(**dict(row["target"]))
            target.validate()
            receipt = row["controller_receipt"]
            applied = row["applied"]
            before_revision = expected_revision + index
            before_time = outer_transition_index * float(expected_controller["physics_dt_s"]) * count + index * float(expected_controller["physics_dt_s"])
            after_time = before_time + float(expected_controller["physics_dt_s"])
            simulation_before = float(row["simulation_time_before_s"])
            simulation_after = float(row["simulation_time_after_s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("task Solution v5 physics substep fields are incomplete") from exc
        if (row.get("substep_index") != index
                or row.get("state_revision_before") != before_revision
                or row.get("state_revision_after") != before_revision + 1
                or not np.isclose(simulation_before, before_time, rtol=0.0, atol=2e-8)
                or not np.isclose(simulation_after, after_time, rtol=0.0, atol=2e-8)
                or target.control_step != outer_transition_index
                or target.state_revision != before_revision
                or not np.isclose(target.simulation_time_s, simulation_before, rtol=0.0, atol=2e-8)
                or row.get("target_identity_sha256") != target.identity_hash
                or target.plan_identity_hash != first_target.plan_identity_hash
                or target.task_artifact_hash != first_target.task_artifact_hash
                or target.source_id != first_target.source_id
                or target.source_closure_digest != first_target.source_closure_digest
                or target.controller_identity != expected_controller.get("identity_sha256")
                or target.provider_materialization_id != first_target.provider_materialization_id
                or target.episode_id != first_target.episode_id
                or target.reset_sample_id != first_target.reset_sample_id
                or not isinstance(applied, Mapping)
                or applied.get("schema_version") != "applied-mixed-actuator-command-v1"
                or applied.get("target_hash") != target.identity_hash
                or applied.get("provider_name") != "mujoco"
                or applied.get("clipped") is not False
                or applied.get("channel_values") != dict(target.channel_values)
                or applied.get("channel_units") != dict(target.channel_units)):
            raise ValueError("task Solution v5 substep target/Ack differs from its frozen Runtime boundary")
        nested_action = dict(canonical_action)
        nested_action.pop("physics_rate_control_v1", None)
        _validate_v4_osc_receipt(
            nested_action, expected_controller, target, public_action,
            h5_joint_position if index == 0 else None,
            h5_ee_pose if index == 0 else None,
            resource_close, receipt_override=receipt,
            initial_joint_reference=initial_joint_reference,
            source_xml_sha256=source_xml_sha256,
            source_closure_digest=source_closure_digest,
            expected_desired_twist_world=expected_desired_twist_world,
        )
    if (first_target.identity_hash != rows[0].get("target_identity_sha256")
            or int(resource_close.get("forward_call_count", -1)) < count):
        raise ValueError("task Solution v5 first Target or source OSC operation receipt is inconsistent")
    return count

def _consume_libero_solution_bundle(bundle_path: Path, report: Mapping[str, Any], *, require_motion_thresholds: bool, require_mujoco_runtime_identity: bool) -> dict[str, Any]:
    """Independent provider-free H5/source/outcome readback for the v2.1.0 route."""
    from bench_deploy.libero.tasks.solution import solution_identity_v8
    from bench_deploy.libero.controllers.osc import LiberoMixedControllerV7
    schema = report.get('schema_version')
    if schema != 'r07-v210-task-solution-worker-result-v8':
        raise ValueError('retired task Solution worker schemas must be read from their frozen source commit')
    payload = {key: value for key, value in report.items() if key != 'result_sha256'}
    if hashlib.sha256(_canonical(payload)).hexdigest() != report.get('result_sha256'):
        raise ValueError('task Solution worker result digest mismatch')
    attempted_episode_receipts = report.get('attempted_episode_receipts')
    failed_episode_receipts = report.get('failed_episode_receipts')
    raw_rows = report.get('episode_rows')
    expected_rows = tuple(raw_rows) if isinstance(raw_rows, list) else ()
    expected_scope = 'task1_final_rows_0_1_2' if expected_rows == (0, 1, 2) else 'task1_bounded_probe' if expected_rows == (0,) else None
    if schema != 'r07-v210-task-solution-worker-result-v8' or report.get('status') != 'complete' or report.get('worker_error') is not None or (report.get('close_error') is not None) or (report.get('solution_resource_close_error') is not None) or (expected_scope is None) or (report.get('run_scope') != expected_scope) or (report.get('episode_count') != len(expected_rows)) or (len(report.get('episodes', ())) != len(expected_rows)) or (not isinstance(attempted_episode_receipts, list)) or (len(attempted_episode_receipts) != len(expected_rows)) or (not isinstance(failed_episode_receipts, list)) or failed_episode_receipts or (report.get('reset_count') != len(expected_rows)):
        raise ValueError('task Solution worker bundle is incomplete or has an invalid schema/count')
    source_readback = _verify_solution_source_bundle(bundle_path, report.get('source_bundle'))
    source_xml_bytes = source_readback.pop('_canonical_xml_bytes')
    source_readback.pop('_raw_source_xml_bytes', None)
    source_readback.pop('_model_profile_bytes', None)
    expected_source_xml_sha256 = source_readback['canonical_xml_sha256']
    expected_source_closure_digest = source_readback['source_closure_digest']
    recorded_controller = report['episodes'][0].get('control_plan', {})
    resolver_policy = {'max_iterations': 64, 'position_tolerance_m': 0.001, 'orientation_tolerance_rad': 0.005, 'model_position_tolerance_m': 0.003, 'model_orientation_tolerance_rad': 0.03}
    resolver_identity = _task1_iterative_resolver_identity(source_xml_bytes, report['episodes'][0]['task_artifact_identity_hash'], resolver_policy, high_precision_profile=True)
    expected_controller = LiberoMixedControllerV7(arm_resolver_identity=resolver_identity).identity_mapping()
    if dict(recorded_controller) != expected_controller:
        raise ValueError('task Solution pose Controller identity differs from its frozen profile')
    expected_solution_identity = solution_identity_v8(source_readback['canonical_xml_sha256'], source_readback['source_closure_digest'], arm_resolver_identity=resolver_identity)
    resource_close = report.get('solution_resource_close_receipt')
    if not isinstance(resource_close, Mapping) or resource_close.get('schema_version') != 'libero-source-gravity-model-close-v1' or resource_close.get('closed') is not True or (resource_close.get('model_released') is not True) or (resource_close.get('data_released') is not True) or (resource_close.get('mj_step_call_count') != 0) or (resource_close.get('source_xml_sha256') != expected_source_xml_sha256) or (resource_close.get('source_closure_digest') != expected_source_closure_digest) or (source_readback.get('model_profile_id') is not None and (resource_close.get('raw_source_xml_sha256') != source_readback.get('raw_source_xml_sha256') or resource_close.get('model_profile_id') != source_readback.get('model_profile_id') or resource_close.get('model_profile_receipt_sha256') != source_readback.get('model_profile_receipt_sha256'))):
        raise ValueError('task Solution source gravity model is not explicitly closed')
    total_t = total_obs = total_native = 0
    episodes = []
    for index, (expected_row, episode, attempted) in enumerate(zip(expected_rows, report['episodes'], attempted_episode_receipts, strict=True)):
        expected_episode_schema = "r07-v210-task-solution-episode-v8"
        if episode.get('schema_version') != expected_episode_schema or episode.get('episode_index') != index or episode.get('row_index') != expected_row or (episode.get('seed') != 19) or (episode.get('task_uid') != TASK_1) or (episode.get('source_id') != source_readback.get('source_id')) or (episode.get('source_closure_digest') != source_readback.get('source_closure_digest')) or (episode.get('source_xml_sha256') != source_readback.get('canonical_xml_sha256')) or (episode.get('solution_identity') != expected_solution_identity):
            raise ValueError('task Solution episode task/row/seed/order identity mismatch')
        if episode.get('solution_schema_version') != "libero-bowl-to-plate-solution-v8" or episode.get('action_schema_id') != 'libero-world-pose-wxyz-absolute-v1':
            raise ValueError('task Solution pose episode omits its explicit world-pose profile identity')
        prior_close = episode.get('prior_session_close_receipt')
        if index == 0 and prior_close is not None or (index > 0 and (not isinstance(prior_close, Mapping) or prior_close.get('session_closed') is not True)):
            raise ValueError('task Solution same-Env reset omitted the prior RuntimeSession close receipt')
        sample = episode.get('reset_sample')
        realization = episode.get('reset_realization')
        readback = episode.get('reset_readback')
        progress = episode.get('runtime_progress')
        compiled = episode.get('compiled_model_layout_v1')
        pre_reset = episode.get('pre_reset_compiled_validation_v1')
        if not all((isinstance(value, Mapping) for value in (sample, realization, readback, progress, compiled, pre_reset))):
            raise ValueError('task Solution episode omits source/reset/progress/layout receipts')
        runtime_identity = pre_reset.get('runtime_identity')
        if require_mujoco_runtime_identity and runtime_identity != _PINNED_MUJOCO_RUNTIME_IDENTITY:
            raise ValueError('task Solution pre-reset receipt does not identify the pinned MuJoCo runtime')
        start = attempted.get('receipt')
        start_relative = attempted.get('relative_path')
        if type(start_relative) is not str or Path(start_relative).is_absolute() or '..' in Path(start_relative).parts:
            raise ValueError('task Solution start receipt path is unsafe')
        start_path = (bundle_path.parent / start_relative).resolve(strict=True)
        if bundle_path.parent not in start_path.parents:
            raise ValueError('task Solution start receipt escaped its worker bundle')
        start_raw = start_path.read_bytes()
        if len(start_raw) != attempted.get('bytes') or hashlib.sha256(start_raw).hexdigest() != attempted.get('sha256') or start != json.loads(start_raw.decode('utf-8')) or (start.get('schema_version') != "r07-v210-task-solution-start-receipt-v8") or (start.get('episode_index') != index) or (start.get('row_index') != expected_row) or (start.get('seed') != 19) or (start.get('task_uid') != TASK_1) or (start.get('solution_identity') != expected_solution_identity) or (start.get('episode_id') != episode.get('episode_id')) or (start.get('source_id') != episode.get('source_id')) or (start.get('source_closure_digest') != episode.get('source_closure_digest')) or (start.get('pre_reset_compiled_validation_v1') != pre_reset):
            raise ValueError('task Solution start receipt differs from its episode/runtime identity')
        if sample.get('init_row_index') != expected_row or sample.get('source_id') != episode.get('source_id') or sample.get('source_closure_digest') != episode.get('source_closure_digest') or (readback.get('reset_sample_id') != sample.get('sample_id')) or (readback.get('joint_position') != sample.get('joint_position')) or (readback.get('joint_velocity') != sample.get('joint_velocity')) or (readback.get('poses_world') != sample.get('poses_world')) or (readback.get('free_joint_velocity') != sample.get('free_joint_velocity')) or (not _pose_world_mapping_matches(readback.get('fixture_pose_world'), sample.get('fixture_pose_world'))) or (realization.get('init_row_index') != expected_row) or (realization.get('init_row_sha256') != sample.get('init_row_sha256')) or (progress.get('episode_id') != episode.get('episode_id')) or (progress.get('provider_materialization_id') is None) or (progress.get('native_step_count') != episode.get('h5', {}).get('transition_count', 0) * 25):
            raise ValueError('task Solution reset/progress source identity differs from the public readback')
        if compiled.get('schema_version') != 'compiled-model-layout-v1' or compiled.get('source_id') != episode.get('source_id') or compiled.get('source_closure_digest') != episode.get('source_closure_digest') or (pre_reset.get('reset_not_yet_applied') is not True) or (pre_reset.get('compiled_layout') != compiled) or (compiled.get('dimensions', {}).get('nq') != 48) or (compiled.get('dimensions', {}).get('nv') != 43) or (compiled.get('dimensions', {}).get('nu') != 9):
            raise ValueError('task Solution compiled source/layout receipt is invalid or post-reset')
        relative = episode.get('h5', {}).get('relative_path')
        if type(relative) is not str or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('task Solution H5 path escapes its worker bundle')
        h5_path = (bundle_path.parent / relative).resolve(strict=True)
        if bundle_path.parent not in h5_path.parents:
            raise ValueError('task Solution H5 path escaped the worker bundle')
        raw = h5_path.read_bytes()
        if len(raw) != episode['h5'].get('bytes') or hashlib.sha256(raw).hexdigest() != episode['h5'].get('sha256'):
            raise ValueError('task Solution H5 bytes or digest differ from the worker receipt')
        inspected = inspect_trajectory_h5(h5_path)
        semantic = load_structured_control_records_h5(h5_path)
        if inspected.get('schema_version') != 'v3' or semantic['transition_count'] != episode['h5'].get('transition_count') or semantic['observation_count'] != semantic['transition_count'] + 1 or (semantic['outcome'].episode_id != episode.get('episode_id')) or (semantic['outcome'].final_boundary != semantic['transition_count']) or (semantic['outcome'].task_success is not episode.get('task_success')) or (semantic['outcome'].solution_completed is not episode.get('solution_completed')):
            raise ValueError('task Solution H5 T/T+1, outcome, or completion facts differ from worker data')
        if semantic['outcome'].solution_completed is True and (semantic['outcome'].task_success is not True or semantic['outcome'].terminated or semantic['outcome'].truncated or (semantic['outcome'].end_reason != 'solution_completed')):
            raise ValueError('H5 claims Solution completion without task success and clean lifecycle facts')
        if semantic['outcome'].solution_completed is False and episode.get('solution_failed') is False and (semantic['outcome'].end_reason == 'solution_completed'):
            raise ValueError('H5 end reason upgrades a non-completed Solution')
        if type(episode.get('solution_completed')) is not bool or type(episode.get('solution_failed')) is not bool or type(episode.get('task_success')) is not bool or (episode['solution_completed'] and (not episode['task_success'] or episode['solution_failed'])):
            raise ValueError('task Solution worker outcome booleans are inconsistent')
        task_context = None
        with h5py.File(h5_path, 'r') as handle:
            required = ('obs/state/joint_position', 'obs/state/ee_pose', 'obs/state/boundary_identity_sha256', 'obs/privileged_state/bowl_body_pose', 'obs/privileged_state/plate_body_pose', 'meta/task_context_json', 'meta/boundary_context_v1_json')
            if any((name not in handle for name in required)):
                raise ValueError('task Solution H5 omits state, pose, identity, or boundary context')
            task_context = json.loads(handle['meta/task_context_json'][()].decode('utf-8'))
            boundaries = json.loads(handle['meta/boundary_context_v1_json'][()].decode('utf-8'))
            joints = handle['obs/state/joint_position'][:]
            ee_poses = handle['obs/state/ee_pose'][:]
            boundary_ids = handle['obs/state/boundary_identity_sha256'][:]
            bowl_poses = handle['obs/privileged_state/bowl_body_pose'][:, 0, :]
            plate_poses = handle['obs/privileged_state/plate_body_pose'][:, 0, :]
            action_names = ['world_x_m', 'world_y_m', 'world_z_m', 'world_qw', 'world_qx', 'world_qy', 'world_qz', 'gripper_normalized']
            if any((f'universal_action/{name}' not in handle for name in action_names)):
                raise ValueError('task Solution H5 omits one or more public action channels')
            actions = np.column_stack([handle[f'universal_action/{name}'][:].reshape(-1) for name in action_names])
        count = semantic['transition_count']
        observation_count = semantic['observation_count']
        if joints.shape != (observation_count, 9) or not np.isfinite(joints).all() or ee_poses.shape != (observation_count, 7) or (not np.isfinite(ee_poses).all()) or (boundary_ids.shape != (observation_count, 32)) or (boundary_ids.dtype != np.uint8) or (bowl_poses.shape != (observation_count, 7)) or (not np.isfinite(bowl_poses).all()) or (plate_poses.shape != (observation_count, 7)) or (not np.isfinite(plate_poses).all()) or (actions.shape != (count, 8)) or (not np.isfinite(actions).all()) or (len(boundaries) != observation_count):
            raise ValueError('task Solution H5 public state/action arrays violate their T/T+1 schemas')
        if task_context.get('schema_version') != 'libero-episode-context-v1' or task_context.get('task_artifact_identity_hash') != episode.get('task_artifact_identity_hash') or task_context.get('solution_identity') != episode.get('solution_identity') or (task_context.get('source_id') != episode.get('source_id')) or (task_context.get('source_xml_sha256') != episode.get('source_xml_sha256')) or (task_context.get('source_closure_digest') != episode.get('source_closure_digest')) or (task_context.get('episode_id') != episode.get('episode_id')) or (task_context.get('init_row_index') != expected_row) or (task_context.get('reset_sample_id') != sample.get('sample_id')) or (task_context.get('provider_materialization_id') != progress.get('provider_materialization_id')) or (task_context.get('controller_identity') != expected_controller.get('identity_sha256')):
            raise ValueError('task Solution H5 task/source/solution identity differs from worker receipts')
        identity_fields = ('source_id', 'source_closure_digest', 'provider_materialization_id', 'episode_id', 'reset_sample_id', 'control_step', 'state_revision', 'simulation_time_s')
        stepwise_solution = True
        for boundary_index, boundary in enumerate(boundaries):
            expected_revision = boundary_index * (int(expected_controller['control_substeps']) if stepwise_solution else 1)
            if not isinstance(boundary, Mapping) or boundary.get('schema_version') != 'task-observation-context-v1' or any((boundary.get(name) != task_context.get(name) for name in identity_fields[:5])) or (boundary.get('control_step') != boundary_index) or (boundary.get('state_revision') != expected_revision) or (boundary.get('simulation_time_s') != boundary_index * 0.05):
                raise ValueError('task Solution H5 boundary identity/order/clock is invalid')
            digest_payload = {name: boundary[name] for name in identity_fields}
            expected_digest = digest(digest_payload)
            if boundary.get('state_boundary_identity_sha256') != expected_digest or bytes(boundary_ids[boundary_index]).hex() != expected_digest:
                raise ValueError('task Solution H5 observation boundary digest is invalid')
            contact = boundary.get('contact_summary_v2')
            predicate = boundary.get('predicate_v1')
            expected_contact_pairs = [['akita_black_bowl_1', 'panda-v1/finger-left'], ['akita_black_bowl_1', 'panda-v1/finger-right'], ['akita_black_bowl_1', 'plate_1']]
            if not isinstance(contact, Mapping) or contact.get('schema_version') != 'task-contact-summary-v2' or contact.get('requested_pairs') != expected_contact_pairs or (contact.get('covered_pairs') != contact.get('requested_pairs')) or any((contact.get(name) != boundary.get(name) for name in identity_fields)) or (contact.get('state_revision') != boundary.get('state_revision')):
                raise ValueError('task Solution H5 contact summary is missing, stale, or incomplete')
            count_contact = contact.get('pair_counts', {}).get('akita_black_bowl_1/plate_1')
            if type(count_contact) is not int or count_contact < 0:
                raise ValueError('task Solution H5 contact pair count is invalid')
            source_on = bool(count_contact > 0 and bowl_poses[boundary_index, 2] >= plate_poses[boundary_index, 2] and (float(np.linalg.norm(bowl_poses[boundary_index, :2] - plate_poses[boundary_index, :2])) < 0.03))
            if not isinstance(predicate, Mapping) or predicate.get('status') != 'available' or predicate.get('value') is not source_on:
                raise ValueError('task Solution H5 On predicate differs from the source-rule recomputation')
        if len(semantic['structured_controls']) != count or any((control is None for control in semantic['structured_controls'])):
            raise ValueError('task Solution H5 omits a typed mixed-control Target/Ack')
        previous_controller_target_pose = None
        for transition_index, control in enumerate(semantic['structured_controls']):
            control.validate()
            expected_action_schema = 'libero-world-pose-wxyz-absolute-v1'
            if len(control.request.groups) != 1 or len(control.writer_controls) != 1 or control.request.groups[0].action_schema_id != expected_action_schema or (not np.allclose(np.asarray(control.request.groups[0].values), actions[transition_index], rtol=0.0, atol=1e-07)):
                raise ValueError('task Solution typed action differs from its public H5 action row')
            writer = control.writer_controls[0]
            target_mapping = writer.get('controller_target', {}).get('payload')
            ack_mapping = writer.get('applied_control', {}).get('payload')
            if not isinstance(target_mapping, Mapping) or not isinstance(ack_mapping, Mapping):
                raise ValueError('task Solution structured control lacks target/ack payload')
            target = MixedActuatorCommandV1.from_mapping(dict(target_mapping))
            ack = AppliedMixedActuatorCommandV1.from_mapping(dict(ack_mapping))
            expected_target_revision = transition_index * (int(expected_controller['control_substeps']) if stepwise_solution else 1)
            if ack.target_hash != target.identity_hash or ack.clipped is not False or dict(ack.channel_values) != dict(target.channel_values) or (dict(ack.channel_units) != dict(target.channel_units)) or (target.task_artifact_hash != task_context.get('task_artifact_identity_hash')) or (target.source_id != task_context.get('source_id')) or (target.source_closure_digest != task_context.get('source_closure_digest')) or (target.controller_identity != task_context.get('controller_identity')) or (target.provider_materialization_id != task_context.get('provider_materialization_id')) or (target.episode_id != task_context.get('episode_id')) or (target.reset_sample_id != task_context.get('reset_sample_id')) or (target.control_step != transition_index) or (target.state_revision != expected_target_revision) or (target.simulation_time_s != transition_index * 0.05) or (ack.provider_name != 'mujoco'):
                raise ValueError('task Solution H5 Target/Ack source, control, or boundary identity mismatch')
            writer = control.writer_controls[0]
            canonical_action = writer.get('canonical_action')
            expected_twist = None
            from task_env.utils.rotation import quat_wxyz_to_matrix, rotation_vector_error
            controller_receipt = canonical_action.get('controller_receipt')
            target_pose_receipt = controller_receipt.get('target_world_pose') if isinstance(controller_receipt, Mapping) else None
            if not isinstance(target_pose_receipt, Mapping):
                raise ValueError('task Solution v6 controller receipt omits its precise target pose')
            current_target_position = np.asarray(target_pose_receipt.get('position_m'), dtype=np.float64)
            current_target_quaternion = np.asarray(target_pose_receipt.get('quaternion_wxyz'), dtype=np.float64)
            if current_target_position.shape != (3,) or current_target_quaternion.shape != (4,) or (not np.isfinite(current_target_position).all()) or (not np.isfinite(current_target_quaternion).all()):
                raise ValueError('task Solution v6 controller target pose is malformed')
            current_target_rotation = quat_wxyz_to_matrix(current_target_quaternion)
            if previous_controller_target_pose is None:
                expected_twist = np.zeros(6, dtype=np.float64)
            else:
                previous_position, previous_rotation = previous_controller_target_pose
                linear = (current_target_position - previous_position) / 0.05
                linear_norm = float(np.linalg.norm(linear))
                if linear_norm > 0.05:
                    linear *= 0.05 / linear_norm
                angular = rotation_vector_error(previous_rotation, current_target_rotation) / 0.05
                angular_norm = float(np.linalg.norm(angular))
                if angular_norm > 0.5:
                    angular *= 0.5 / angular_norm
                expected_twist = np.concatenate((linear, angular))
            previous_controller_target_pose = (current_target_position.copy(), current_target_rotation.copy())
            _validate_v5_stepwise_osc_receipt(canonical_action, expected_controller, target, actions[transition_index], np.asarray(joints[transition_index], dtype=np.float64), np.asarray(ee_poses[transition_index], dtype=np.float64), resource_close, np.asarray(joints[0, :7], dtype=np.float64), outer_transition_index=transition_index, source_xml_sha256=expected_source_xml_sha256, source_closure_digest=expected_source_closure_digest, expected_desired_twist_world=expected_twist)
        action_trace = episode.get('action_trace')
        if not isinstance(action_trace, list) or len(action_trace) != count:
            raise ValueError('task Solution action trace does not cover every H5 transition')
        gravity_receipt = episode.get('gravity_compensation')
        if gravity_receipt is not None:
            raise ValueError('task Solution pose profiles must keep source gravity outside the Solution outcome')
        frozen_v6_references = None
        for transition_index, action in enumerate(action_trace):
            if not isinstance(action, Mapping) or type(action.get('control_step')) is not int or action.get('control_step') != transition_index + 1 or (not np.isclose(float(action.get('simulation_time_s', float('nan'))), (transition_index + 1) * 0.05, rtol=0.0, atol=1e-09)) or (type(action.get('terminated')) is not bool) or (type(action.get('truncated')) is not bool) or (not isinstance(action.get('solution_stage'), str)) or (not isinstance(action.get('solution_diagnostics'), Mapping)) or (not np.allclose(np.asarray(action.get('solution_action'), dtype=np.float64), actions[transition_index], rtol=0.0, atol=1e-07)):
                raise ValueError('task Solution action trace differs from public H5 control rows')
            diagnostics = action['solution_diagnostics']
            receipt = action.get('solution_action_receipt')
            expected_planner_owner = 'CartesianPosePlanner.plan_gripper_transition' if action.get('solution_stage') in {'grasp', 'release'} else 'CartesianPosePlanner.plan_to_pose'
            feedback = receipt.get('post_step_feedback') if isinstance(receipt, Mapping) else None
            try:
                position_error = float(feedback.get('planner_tracking_position_error_m'))
                orientation_error = float(feedback.get('planner_tracking_orientation_error_rad'))
                path_index = diagnostics.get('planner_path_index')
                path_length = diagnostics.get('planner_path_length')
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError('task Solution v4 action omits convergence-gate feedback') from exc
            if not isinstance(receipt, Mapping) or receipt.get('solution_schema_version') != "libero-bowl-to-plate-solution-v8" or receipt.get('solution_identity') != expected_solution_identity or (receipt.get('stage') != action.get('solution_stage')) or (not np.allclose(np.asarray(receipt.get('action'), dtype=np.float64), np.asarray(action.get('solution_action'), dtype=np.float64), rtol=0.0, atol=1e-07)) or (not isinstance(feedback, Mapping)) or (feedback.get('stage_before') != action.get('solution_stage')) or (type(feedback.get('waypoint_advanced')) is not bool) or (not math.isfinite(position_error)) or (position_error < 0.0) or (not math.isfinite(orientation_error)) or (orientation_error < 0.0) or (type(path_index) is not int) or (path_index < 0) or (type(path_length) is not int) or (path_length <= path_index) or (diagnostics.get('planner_owner') != expected_planner_owner) or (diagnostics.get('advancement_policy') != 'public_TCP_waypoint_convergence_gated_v1') or (diagnostics.get('source_pose_observation_used') is not True) or ((position_error > 0.025 or orientation_error > 0.25) and feedback.get('waypoint_advanced') is True) or (feedback.get('waypoint_advanced') is True and (position_error > 0.006 or orientation_error > 0.03)):
                raise ValueError('task Solution v4 action does not record its shared convergence-gated planner')
            from task_env.utils.rotation import quat_angle_wxyz, quat_multiply_wxyz, rotate_vector_wxyz
            frame = receipt.get('grasp_frame')
            try:
                bowl_reference = np.asarray(frame.get('bowl_reference_pose_world_wxyz'), dtype=np.float64)
                plate_reference = np.asarray(frame.get('plate_reference_pose_world_wxyz'), dtype=np.float64)
                local_tcp_quaternion = np.asarray(frame.get('tcp_quaternion_in_bowl_wxyz'), dtype=np.float64)
                local_offset = np.asarray(frame.get('bowl_local_tcp_offset_m'), dtype=np.float64)
                recorded_target = np.asarray(receipt.get('target_world_pose'), dtype=np.float64)
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError('task Solution v6 action omits its typed rim-grasp frame') from exc
            if frame.get('dataset_revision') != 'e434c228d52f21e37c6f45046a6476a8fa362b8d' or frame.get('dataset_file_sha256') != 'ff6f26121653c77280eb40a38773a74141c11a8509f3466058cb56dd2cc60ead' or bowl_reference.shape != (7,) or (plate_reference.shape != (7,)) or (local_tcp_quaternion.shape != (4,)) or (local_offset.shape != (3,)) or (recorded_target.shape != (7,)) or (not all((np.isfinite(value).all() for value in (bowl_reference, plate_reference, local_tcp_quaternion, local_offset, recorded_target)))) or (not np.allclose(local_offset, (-0.044920013921162995, 0.00462166895747628, 0.024593639582228065), rtol=0.0, atol=1e-12)) or (frame.get('offset_source') != 'demo40 source-model FK at first bilateral contact state 51') or (frame.get('orientation_source') != 'demo40_state51_source_fk_v1' or frame.get('jaw_opening_source') != 'demo40_state51_first_bilateral_contact_v1' or frame.get('sample_index') != 51 or (not np.allclose(local_tcp_quaternion, (0.03300342281417691, -0.996740012700174, 0.04855030219620138, -0.05534427993626179), rtol=0.0, atol=1e-12))):
                raise ValueError('task Solution v6 rim-grasp frame differs from the frozen demo profile')
            stage_name = action['solution_stage']
            if stage_name in {'approach', 'descend'} or (stage_name == 'grasp' and frozen_v6_references is None):
                expected_bowl_reference = bowl_poses[transition_index]
                expected_plate_reference = plate_poses[transition_index]
                if stage_name == 'grasp':
                    frozen_v6_references = (expected_bowl_reference.copy(), expected_plate_reference.copy())
            else:
                if frozen_v6_references is None:
                    raise ValueError('task Solution v6 advanced past approach without freezing its grasp frame')
                expected_bowl_reference, expected_plate_reference = frozen_v6_references
            if not np.allclose(bowl_reference[:3], expected_bowl_reference[:3], rtol=0.0, atol=2e-06) or not np.allclose(plate_reference[:3], expected_plate_reference[:3], rtol=0.0, atol=2e-06) or quat_angle_wxyz(bowl_reference[3:7], expected_bowl_reference[3:7]) > 2e-05 or (quat_angle_wxyz(plate_reference[3:7], expected_plate_reference[3:7]) > 2e-05):
                raise ValueError('task Solution v6 grasp-frame references differ from public H5 poses')
            bowl_quaternion = bowl_reference[3:7]
            world_offset = rotate_vector_wxyz(bowl_quaternion, local_offset)
            if stage_name == 'approach':
                approach_offset = local_offset.copy()
                approach_offset[2] = 0.15
                expected_position = bowl_reference[:3] + rotate_vector_wxyz(bowl_quaternion, approach_offset)
            elif stage_name in {'descend', 'grasp'}:
                expected_position = bowl_reference[:3] + world_offset
            elif stage_name == 'lift':
                expected_position = bowl_reference[:3] + world_offset + (0.0, 0.0, 0.2)
            elif stage_name == 'carry':
                expected_position = np.asarray((plate_reference[0], plate_reference[1], bowl_reference[2] + 0.2)) + world_offset
            else:
                expected_position = plate_reference[:3] + (0.0, 0.0, 0.085) + world_offset
            expected_quaternion = quat_multiply_wxyz(bowl_quaternion, local_tcp_quaternion)
            stage_openings = {'approach': 0.042, 'descend': 0.042, 'grasp': 0.01, 'lift': 0.008, 'carry': 0.008, 'place': 0.008, 'release': 0.042}
            stage_openings.update({'descend': 0.01344940828870882, 'grasp': 0.006517432981670807, 'lift': 0.006517432981670807, 'carry': 0.006517432981670807, 'place': 0.006517432981670807})
            if stage_name not in stage_openings or not np.allclose(recorded_target[:3], expected_position, rtol=0.0, atol=2e-06) or quat_angle_wxyz(recorded_target[3:7], expected_quaternion) > 2e-05 or (not np.isclose(float(receipt.get('opening_target_m', float('nan'))), stage_openings[stage_name], rtol=0.0, atol=1e-12)):
                raise ValueError('task Solution v6 rim target or stage opening differs from its frozen geometry')
        for previous, current in zip(action_trace, action_trace[1:]):
            previous_receipt = previous['solution_action_receipt']
            feedback = previous_receipt['post_step_feedback']
            next_diagnostics = current['solution_diagnostics']
            if feedback.get('stage_after') != current.get('solution_stage'):
                raise ValueError('task Solution v4 stage transition does not match the next planned action')
            previous_diagnostics = previous['solution_diagnostics']
            old_index = previous_diagnostics['planner_path_index']
            old_length = previous_diagnostics['planner_path_length']
            if feedback.get('stage_after') != previous.get('solution_stage'):
                expected_index = 0
            elif feedback['planner_tracking_position_error_m'] > 0.025 or feedback['planner_tracking_orientation_error_rad'] > 0.25:
                expected_index = 0
            elif feedback['waypoint_advanced']:
                expected_index = old_index + 1 if old_index + 1 < old_length else 0
            else:
                expected_index = old_index
            if next_diagnostics.get('planner_path_index') != expected_index:
                raise ValueError('task Solution v4 path index advanced without public waypoint convergence')
        initial_observation = episode.get('initial_observation')
        final_observation = episode.get('final_observation')
        if not isinstance(initial_observation, Mapping) or not isinstance(final_observation, Mapping):
            raise ValueError('task Solution worker omits public initial/final observation receipts')
        for observation_receipt, index in ((initial_observation, 0), (final_observation, -1)):
            if not np.allclose(np.asarray(observation_receipt.get('joint_position'), dtype=np.float64), joints[index], rtol=0.0, atol=1e-07) or not np.allclose(np.asarray(observation_receipt.get('ee_pose'), dtype=np.float64), ee_poses[index], rtol=0.0, atol=1e-07) or observation_receipt.get('boundary_identity_sha256') != bytes(boundary_ids[index]).hex():
                raise ValueError('task Solution worker observation receipt differs from independent H5 state')
        actual_motion = _public_motion_metrics(np.asarray(joints[0], dtype=np.float64), np.asarray(joints[-1], dtype=np.float64), np.asarray(ee_poses[0], dtype=np.float64), np.asarray(ee_poses[-1], dtype=np.float64))
        recorded_motion = episode.get('motion_summary')
        if not isinstance(recorded_motion, Mapping) or any((not np.isclose(float(recorded_motion.get(name, float('nan'))), value, rtol=0.0, atol=1e-07) for name, value in actual_motion.items())):
            raise ValueError('task Solution public motion summary differs from H5 state')
        if require_motion_thresholds and (actual_motion['arm_joint_max_abs_delta_rad'] < 0.05 and actual_motion['tcp_translation_delta_m'] < 0.02):
            raise ValueError('task Solution episode lacks the required public arm/TCP excursion')
        if require_motion_thresholds and actual_motion['aggregate_finger_position_delta_m'] < 0.005:
            raise ValueError('task Solution episode lacks the required aggregate gripper-opening change')
        monitor_summary = _validate_physical_state_monitor(episode.get('physical_state_monitor'), progress, compiled, joints)
        if episode.get('h5', {}).get('transition_count') != count or episode.get('h5', {}).get('observation_count') != observation_count or episode.get('h5', {}).get('episode_id') != episode.get('episode_id') or (episode.get('h5', {}).get('final_boundary') != count) or (semantic['outcome'].final_boundary != count):
            raise ValueError('task Solution H5 receipt T/T+1/final boundary mismatch')
        episodes.append({'episode_id': episode.get('episode_id'), 'row_index': expected_row, 'task_success': semantic['outcome'].task_success, 'solution_completed': semantic['outcome'].solution_completed, 'solution_failed': episode.get('solution_failed'), 'end_reason': semantic['outcome'].end_reason, 'terminated': semantic['outcome'].terminated, 'truncated': semantic['outcome'].truncated, 'transition_count': count, 'observation_count': observation_count, 'h5_sha256': episode['h5']['sha256'], 'physical_state_monitor': monitor_summary, 'gravity_compensation': None})
        total_t += count
        total_obs += observation_count
        total_native += int(progress['native_step_count'])
    close = report.get('final_session_close_receipt')
    if not isinstance(close, Mapping) or close.get('session_closed') is not True:
        raise ValueError('task Solution worker omitted a successful final RuntimeSession close receipt')
    if resource_close.get('forward_call_count') != total_native:
        raise ValueError("task Solution v8 source OSC call count differs from physics-rate substeps")
    if report.get('transition_count') != total_t or report.get('observation_count') != total_obs or report.get('native_step_count') != total_native:
        raise ValueError('task Solution aggregate worker counters differ from independently read H5s')
    return {'schema_version': "r07-v210-task-solution-independent-reader-v8", 'status': 'verified_complete', 'source_bundle': source_readback, 'motion_thresholds_required': bool(require_motion_thresholds), 'mujoco_runtime_identity_required': bool(require_mujoco_runtime_identity), 'episode_count': len(episodes), 'episode_rows': list(expected_rows), 'run_scope': expected_scope, 'transition_count': total_t, 'observation_count': total_obs, 'native_step_count': total_native, 'task_success_episodes': sum((bool(item['task_success']) for item in episodes)), 'solution_completed_episodes': sum((bool(item['solution_completed']) for item in episodes)), 'episodes': episodes}

def consume_libero_candidate_bundle(bundle_path: Path, *, parent_run_record_path: Path | None = None,
                                    expected_lock_path: Path | None = None,
                                    require_motion_thresholds: bool = False,
                                    require_mujoco_runtime_identity: bool = False) -> dict[str, Any]:
    """Provider-free independent readback of a completed worker and all H5s."""
    bundle_path = Path(bundle_path).resolve(strict=True)
    report = json.loads(bundle_path.read_text(encoding="utf-8"))
    if report.get("schema_version") == "r07-v210-task-solution-worker-result-v8":
        result = _consume_libero_solution_bundle(
            bundle_path, report, require_motion_thresholds=require_motion_thresholds,
            require_mujoco_runtime_identity=require_mujoco_runtime_identity,
        )
        if parent_run_record_path is not None:
            if expected_lock_path is None:
                raise ValueError("independent native readback requires the expected shared lock path")
            result["parent_process"] = _validate_parent_run_record(
                bundle_path, report, parent_run_record_path, expected_lock_path,
            )
        elif expected_lock_path is not None:
            raise ValueError("expected native lock path requires a parent run record")
        return result
    payload = {key: value for key, value in report.items() if key != "result_sha256"}
    if hashlib.sha256(_canonical(payload)).hexdigest() != report.get("result_sha256"):
        raise ValueError("worker result digest mismatch")
    if report.get("schema_version") != "r07c-d01-libero-worker-result-v1":
        raise ValueError("unsupported R07c D01 worker-result schema")
    if report.get("status") != "complete" or report.get("worker_error") is not None or report.get("close_error") is not None:
        raise ValueError("worker bundle is incomplete or reports a lifecycle failure")
    if report.get("episode_count") != 3 or len(report.get("episodes", ())) != 3:
        raise ValueError("worker result does not contain all three source rows")
    total_t = total_obs = total_native = 0
    h5_receipts = []
    for expected_index, (expected_row, episode) in enumerate(zip((0, 1, 2), report["episodes"], strict=True)):
        if (episode.get("episode_index") != expected_index or episode.get("row_index") != expected_row
                or episode.get("seed") != 19):
            raise ValueError("worker episode row/seed/order identity mismatch")
        sample = episode.get("reset_sample")
        realization = episode.get("reset_realization")
        readback = episode.get("reset_readback")
        progress = episode.get("runtime_progress")
        if not all(isinstance(value, dict) for value in (sample, realization, readback, progress)):
            raise ValueError("episode bundle omits reset/source/progress receipts")
        compiled = episode.get("compiled_model_layout_v1")
        pre_reset = episode.get("pre_reset_compiled_validation_v1")
        if not isinstance(compiled, dict) or not isinstance(pre_reset, dict):
            raise ValueError("episode bundle omits the pre-reset compiled-model layout proof")
        # Counts beyond nq/nv/na/nu are model-dependent inventory, but every
        # value and the fixed source dimensions must be retained.
        dimensions = compiled.get("dimensions")
        if (compiled.get("schema_version") != "compiled-model-layout-v1"
                or not isinstance(dimensions, dict)
                or any(type(dimensions.get(name)) is not int for name in (
                    "nq", "nv", "na", "nu", "njnt", "nbody", "nsite", "ngeom",
                ))
                or tuple(dimensions.get(name) for name in ("nq", "nv", "na", "nu", "njnt"))
                != (48, 43, 0, 9, 18)):
            raise ValueError("independent bundle has an invalid compiled-model dimension receipt")
        if (compiled.get("source_id") != episode.get("source_id")
                or compiled.get("source_closure_digest") != episode.get("source_closure_digest")
                or pre_reset.get("reset_not_yet_applied") is not True
                or pre_reset.get("compiled_layout") != compiled):
            raise ValueError("compiled model was not validated before reset or differs from the episode source")
        expected_scalar_addresses = {
            **{f"joint{i}": [i - 1, i - 1] for i in range(1, 8)},
            "finger_joint1": [7, 7], "finger_joint2": [8, 8],
            "wooden_cabinet_1.top_level": [44, 39],
            "wooden_cabinet_1.middle_level": [45, 40],
            "wooden_cabinet_1.bottom_level": [46, 41],
            "flat_stove_1.button": [47, 42],
        }
        expected_free_addresses = {
            name: [9 + 7 * index, 9 + 6 * index]
            for index, name in enumerate((
                "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
                "glazed_rim_porcelain_ramekin_1", "plate_1",
            ))
        }
        if (compiled.get("named_joint_addresses") != expected_scalar_addresses
                or compiled.get("named_free_joint_addresses") != expected_free_addresses):
            raise ValueError("compiled named Joint/qpos/dof layout differs from the fixed .pruned_init mapping")
        expected_bodies = {
            "main_table", "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
            "glazed_rim_porcelain_ramekin_1", "plate_1", "wooden_cabinet_1", "flat_stove_1",
        }
        body_ids = compiled.get("named_body_ids")
        frame_ids = compiled.get("named_frame_ids")
        if (not isinstance(body_ids, dict) or set(body_ids) != expected_bodies
                or any(type(value) is not int or value <= 0 for value in body_ids.values())
                or len(set(body_ids.values())) != len(body_ids)
                or not isinstance(frame_ids, dict) or set(frame_ids) != {"panda-v1/ee"}
                or type(frame_ids.get("panda-v1/ee")) is not int or frame_ids["panda-v1/ee"] <= 0):
            raise ValueError("compiled named Body/Frame inventory differs from the fixed LIBERO source map")
        expected_channel_specs = {
            **{
                f"joint{i}": {
                    "actuator_name": f"robot0_torq_j{i}",
                    "joint_name": f"robot0_joint{i}", "drive_mode": "joint_torque",
                    "unit": "N*m", "control_range": [-80.0, 80.0] if i <= 5 else [-12.0, 12.0],
                } for i in range(1, 8)
            },
            "finger_joint1": {
                "actuator_name": "gripper0_gripper_finger_joint1",
                "joint_name": "gripper0_finger_joint1", "drive_mode": "joint_position",
                "unit": "m", "control_range": [0.0, 0.04],
            },
            "finger_joint2": {
                "actuator_name": "gripper0_gripper_finger_joint2",
                "joint_name": "gripper0_finger_joint2", "drive_mode": "joint_position",
                "unit": "m", "control_range": [-0.04, 0.0],
            },
        }
        torque_ids = compiled.get("named_torque_actuator_ids")
        position_ids = compiled.get("named_position_actuator_ids")
        channel_layout = compiled.get("named_actuator_channels")
        if (not isinstance(torque_ids, dict) or set(torque_ids) != {f"joint{i}" for i in range(1, 8)}
                or not isinstance(position_ids, dict) or set(position_ids) != {"finger_joint1", "finger_joint2"}
                or not isinstance(channel_layout, dict) or set(channel_layout) != set(expected_channel_specs)):
            raise ValueError("compiled actuator receipt omits a named torque or finger slot")
        actuator_ids = []
        for name, spec in expected_channel_specs.items():
            entry = channel_layout[name]
            expected_id = torque_ids.get(name) if name in torque_ids else position_ids.get(name)
            if (type(expected_id) is not int or entry.get("actuator_id") != expected_id
                    or entry.get("actuator_name") != spec["actuator_name"]
                    or entry.get("joint_name") != spec["joint_name"]
                    or entry.get("transmission_target") != spec["joint_name"]
                    or entry.get("transmission_type") != "joint"
                    or entry.get("drive_mode") != spec["drive_mode"]
                    or entry.get("unit") != spec["unit"]
                    or entry.get("control_limited") is not True
                    or entry.get("control_range") != spec["control_range"]):
                raise ValueError(f"compiled actuator transmission/drive/range receipt is invalid: {name}")
            actuator_ids.append(expected_id)
        if sorted(actuator_ids) != list(range(9)):
            raise ValueError("compiled actuator layout does not uniquely cover all nine ctrl slots")
        geom_groups = compiled.get("named_contact_geom_groups")
        if (not isinstance(geom_groups, dict)
                or set(geom_groups) != {
                    "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
                    "glazed_rim_porcelain_ramekin_1", "plate_1",
                    "wooden_cabinet_1", "flat_stove_1",
                }
                or any(not isinstance(items, list) or not items
                       or any(type(item.get("id")) is not int or item["id"] < 0
                              or type(item.get("name")) is not str or not item["name"]
                              for item in items if isinstance(item, dict))
                       or any(not isinstance(item, dict) for item in items)
                       for items in geom_groups.values())):
            raise ValueError("compiled semantic contact geom groups are incomplete or malformed")
        all_geom_ids = [item["id"] for items in geom_groups.values() for item in items]
        if len(all_geom_ids) != len(set(all_geom_ids)):
            raise ValueError("compiled semantic contact geom groups overlap in native IDs")
        runtime = pre_reset.get("runtime_identity")
        expected_runtime = {
            "provider_build": {
                "dirty_build_sha256": None,
                "import_origin": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
                "manifest_version": "package:3.8.1",
                "origin_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
                "package_version": "3.8.1", "provider": "mujoco",
                "repository_revision": None,
            },
            "runtime": {
                "api_version": 3008001,
                "binding_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/_functions.cpython-312-x86_64-linux-gnu.so",
                "binding_sha256": "9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3",
                "mapped_native_libraries": [{
                    "path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/libmujoco.so.3.8.1",
                    "sha256": "8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592",
                }],
                "package_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
                "package_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
                "package_version": "3.8.1",
                "public_header_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/include/mujoco/mujoco.h",
                "public_header_sha256": "d5ccfb227eb06586edfb4def5812a8082c1cbdf8e6dc5c3176abd9772a57fd07",
                "renderer_initialized": False, "runtime_version": "3.8.1",
            },
        }
        if runtime != expected_runtime:
            raise ValueError("compiled runtime identity differs from the frozen MuJoCo 3.8.1 CPU files")
        if (sample.get("init_row_index") != expected_row
                or sample.get("source_id") != episode.get("source_id")
                or sample.get("source_closure_digest") != episode.get("source_closure_digest")
                or readback.get("reset_sample_id") != sample.get("sample_id")
                or readback.get("simulation_time_s") != sample.get("simulation_time_s")
                or readback.get("joint_position") != sample.get("joint_position")
                or readback.get("joint_velocity") != sample.get("joint_velocity")
                or readback.get("poses_world") != sample.get("poses_world")
                or readback.get("free_joint_velocity") != sample.get("free_joint_velocity")
                or not _pose_world_mapping_matches(
                    readback.get("fixture_pose_world"), sample.get("fixture_pose_world"),
                )
                or realization.get("init_row_index") != expected_row
                or realization.get("init_row_sha256") != sample.get("init_row_sha256")
                or progress.get("episode_id") != episode.get("episode_id")
                or progress.get("native_step_count") != episode["h5"].get("transition_count", 0) * 25):
            raise ValueError("episode reset/progress identity does not match the worker source")
        relative = episode["h5"].get("relative_path")
        if type(relative) is not str or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("worker H5 path must stay inside its bundle directory")
        try:
            h5_path = (bundle_path.parent / relative).resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("worker bundle is missing a required H5 artifact") from exc
        if bundle_path.parent not in h5_path.parents:
            raise ValueError("worker H5 path escaped the bundle directory")
        raw = h5_path.read_bytes()
        if len(raw) != episode["h5"].get("bytes") or hashlib.sha256(raw).hexdigest() != episode["h5"].get("sha256"):
            raise ValueError("worker H5 bytes or digest mismatch")
        inspected = inspect_trajectory_h5(h5_path)
        semantic = load_structured_control_records_h5(h5_path)
        if (inspected.get("schema_version") != "v3"
                or semantic["transition_count"] != episode["h5"].get("transition_count")
                or semantic["observation_count"] != episode["h5"].get("observation_count")
                or semantic["observation_count"] != semantic["transition_count"] + 1
                or semantic["outcome"].episode_id != episode.get("episode_id")
                or semantic["outcome"].final_boundary != semantic["transition_count"]):
            raise ValueError("independent H5 T/T+1, EpisodeOutcome, or final boundary mismatch")
        with h5py.File(h5_path, "r") as handle:
            context_raw = handle["meta/task_context_json"][()].decode("utf-8")
            task_context = json.loads(context_raw)
            required_paths = (
                "obs/state/joint_position", "obs/state/boundary_identity_sha256",
                "obs/state/ee_pose", "obs/privileged_state/bowl_body_pose",
                "obs/privileged_state/plate_body_pose", "meta/boundary_context_v1_json",
            )
            if any(name not in handle for name in required_paths):
                raise ValueError("independent H5 is missing public state/boundary context evidence")
            joints = handle["obs/state/joint_position"][:]
            if joints.shape != (semantic["observation_count"], 9) or not np.isfinite(joints).all():
                raise ValueError("independent H5 joint observations are incomplete or non-finite")
            boundary_ids = handle["obs/state/boundary_identity_sha256"][:]
            if boundary_ids.shape != (semantic["observation_count"], 32) or boundary_ids.dtype != np.uint8:
                raise ValueError("independent H5 boundary identity observations have the wrong shape/dtype")
            ee_poses = handle["obs/state/ee_pose"][:]
            bowl_poses = handle["obs/privileged_state/bowl_body_pose"][:, 0, :]
            plate_poses = handle["obs/privileged_state/plate_body_pose"][:, 0, :]
            if (ee_poses.shape != (semantic["observation_count"], 7)
                    or bowl_poses.shape != (semantic["observation_count"], 7)
                    or plate_poses.shape != (semantic["observation_count"], 7)
                    or not np.isfinite(ee_poses).all()
                    or not np.isfinite(bowl_poses).all()
                    or not np.isfinite(plate_poses).all()):
                raise ValueError("independent H5 public frame/object observations are incomplete or non-finite")
            boundaries = json.loads(handle["meta/boundary_context_v1_json"][()].decode("utf-8"))
            if len(boundaries) != semantic["observation_count"]:
                raise ValueError("independent H5 boundary context must cover all T+1 observations")
            action_names = [*(f"joint{i}" for i in range(1, 8)), "aggregate_opening_m"]
            if any(f"universal_action/{name}" not in handle for name in action_names):
                raise ValueError("independent H5 public action channels are incomplete")
            actions = np.column_stack([
                handle[f"universal_action/{name}"][:].reshape(-1) for name in action_names
            ])
            if actions.shape != (semantic["transition_count"], 8) or not np.isfinite(actions).all():
                raise ValueError("independent H5 public actions are incomplete or non-finite")
        monitor_summary = _validate_physical_state_monitor(
            episode.get("physical_state_monitor"), progress, compiled, joints,
        )
        if (task_context.get("init_row_index") != expected_row
                or task_context.get("reset_sample_id") != sample.get("sample_id")
                or task_context.get("source_id") != episode.get("source_id")
                or task_context.get("source_closure_digest") != episode.get("source_closure_digest")):
            raise ValueError("independent H5 task context is not bound to the worker's reset row/source")
        if (task_context.get("schema_version") != "libero-episode-context-v1"
                or task_context.get("episode_id") != episode.get("episode_id")
                or task_context.get("provider_materialization_id") != progress.get("provider_materialization_id")
                or task_context.get("controller_identity") != episode.get("control_plan", {}).get("identity_sha256")):
            raise ValueError("independent H5 episode/materialization/controller identity mismatch")
        if (len(semantic["structured_controls"]) != semantic["transition_count"]
                or any(item is None for item in semantic["structured_controls"])):
            raise ValueError("independent H5 omits typed control target/Ack on one or more transitions")
        boundary_identity_fields = (
            "source_id", "source_closure_digest", "provider_materialization_id",
            "episode_id", "reset_sample_id", "control_step", "state_revision",
            "simulation_time_s",
        )
        for index, boundary in enumerate(boundaries):
            if (not isinstance(boundary, dict)
                    or boundary.get("schema_version") != "task-observation-context-v1"
                    or any(boundary.get(name) != task_context.get(name) for name in (
                        "source_id", "source_closure_digest", "provider_materialization_id",
                        "episode_id", "reset_sample_id",
                    ))
                    or boundary.get("control_step") != index
                    or boundary.get("state_revision") != index
                    or boundary.get("simulation_time_s") != index * 0.05):
                raise ValueError("independent H5 T/T+1 boundary order, clock, or episode identity mismatch")
            identity = {name: boundary[name] for name in boundary_identity_fields}
            expected_digest = digest(identity)
            if (boundary.get("state_boundary_identity_sha256") != expected_digest
                    or bytes(boundary_ids[index]).hex() != expected_digest):
                raise ValueError("independent H5 T/T+1 boundary identity digest mismatch")
            contact = boundary.get("contact_summary_v2")
            if (not isinstance(contact, dict)
                    or contact.get("status") != "available"
                    or contact.get("schema_version") != "task-contact-summary-v2"
                    or contact.get("requested_pairs") != [["akita_black_bowl_1", "plate_1"]]
                    or contact.get("covered_pairs") != contact.get("requested_pairs")
                    or any(contact.get(name) != boundary.get(name) for name in (
                        "source_id", "source_closure_digest", "provider_materialization_id",
                        "episode_id", "reset_sample_id", "control_step", "simulation_time_s",
                    ))):
                raise ValueError("independent H5 contact query coverage/freshness is incomplete")
            if contact.get("state_revision") != boundary.get("state_revision"):
                raise ValueError("independent H5 contact summary belongs to a stale state revision")
            count = contact.get("pair_counts", {}).get("akita_black_bowl_1/plate_1")
            if type(count) is not int or count < 0:
                raise ValueError("independent H5 contact pair count is missing or invalid")
            predicate = boundary.get("predicate_v1")
            xy_delta = bowl_poses[index, :2] - plate_poses[index, :2]
            source_on = bool(
                count > 0 and bowl_poses[index, 2] >= plate_poses[index, 2]
                and float(np.linalg.norm(xy_delta)) < 0.03
            )
            if (not isinstance(predicate, dict) or predicate.get("status") != "available"
                    or predicate.get("value") is not source_on):
                raise ValueError("independent H5 On predicate disagrees with source contact/pose rule")
        if boundaries[0]["control_step"] != 0 or boundaries[-1]["control_step"] != semantic["outcome"].final_boundary:
            raise ValueError("independent H5 reset/final boundary context does not match EpisodeOutcome")
        for index, control in enumerate(semantic["structured_controls"]):
            control.validate()
            if len(control.request.groups) != 1 or len(control.writer_controls) != 1:
                raise ValueError("independent H5 must contain the exact single mixed writer route")
            request_values = np.asarray(control.request.groups[0].values, dtype=np.float64)
            if request_values.shape != (8,) or not np.allclose(
                    request_values, actions[index], rtol=0.0, atol=1e-7):
                raise ValueError("independent H5 typed request differs from its public action row")
            if (control.request.groups[0].action_schema_id != "libero-joint-space-absolute-v1"
                    or any(not low <= float(value) <= high for value, (low, high) in zip(
                        request_values[:7], (
                            (-2.8973, 2.8973), (-1.7628, 1.7628), (-2.8973, 2.8973),
                            (-3.0718, -0.0698), (-2.8973, 2.8973), (-0.0175, 3.7525),
                            (-2.8973, 2.8973),
                        ), strict=True))
                    or not 0.0 <= float(request_values[7]) <= 0.08):
                raise ValueError("independent H5 action schema, joint order, or physical units are invalid")
            writer = control.writer_controls[0]
            if (writer.get("writer_id") != "libero-spatial-mixed-controller-v1"
                    or writer.get("action_schema_id") != "libero-joint-space-absolute-v1"
                    or writer.get("requested_action", {}).get("unit") != "rad_x7_plus_aggregate_opening_m"):
                raise ValueError("independent H5 mixed writer identity or unit metadata is invalid")
            raw_target = writer.get("controller_target", {}).get("payload")
            raw_ack = writer.get("applied_control", {}).get("payload")
            if not isinstance(raw_target, Mapping) or not isinstance(raw_ack, Mapping):
                raise ValueError("independent H5 structured control lacks the named target/Ack payload")
            target = MixedActuatorCommandV1.from_mapping(dict(raw_target))
            ack = AppliedMixedActuatorCommandV1.from_mapping(dict(raw_ack))
            if target.identity_hash != writer["controller_target"].get("identity_hash"):
                raise ValueError("independent H5 target payload identity hash mismatch")
            if ack.target_hash != target.identity_hash:
                raise ValueError("independent H5 target/Ack identity mismatch")
            if (target.task_artifact_hash != task_context.get("task_artifact_identity_hash")
                    or target.source_id != task_context.get("source_id")
                    or target.source_closure_digest != task_context.get("source_closure_digest")
                    or target.controller_identity != task_context.get("controller_identity")
                    or target.provider_materialization_id != task_context.get("provider_materialization_id")
                    or target.episode_id != task_context.get("episode_id")
                    or target.reset_sample_id != task_context.get("reset_sample_id")
                    or target.control_step != index or target.state_revision != index
                    or target.simulation_time_s != index * 0.05):
                raise ValueError("independent H5 target/source/boundary identity mismatch")
            expected_units = {
                **{f"joint{i}": "N*m" for i in range(1, 8)},
                "finger_joint1": "m", "finger_joint2": "m",
            }
            torque_limits = {
                **{f"joint{i}": 80.0 for i in range(1, 6)},
                "joint6": 12.0, "joint7": 12.0,
            }
            if (set(target.channel_values) != set(expected_units)
                    or dict(target.channel_units) != expected_units
                    or any(abs(float(target.channel_values[name])) > torque_limits[name]
                           for name in torque_limits)
                    or dict(ack.channel_values) != dict(target.channel_values)
                    or dict(ack.channel_units) != dict(target.channel_units)
                    or ack.provider_name != "mujoco"
                    or target.plan_identity_hash != compiled.get("plan_identity_hash")):
                raise ValueError("independent H5 native Ack does not match the named target")
            opening = float(request_values[7])
            expected_fingers = {"finger_joint1": opening / 2.0, "finger_joint2": -opening / 2.0}
            if any(not np.isclose(target.channel_values[name], value, rtol=0.0, atol=1e-7)
                   for name, value in expected_fingers.items()):
                raise ValueError("independent H5 target finger sign or aggregate-opening conversion is invalid")
        for endpoint_name, obs_index in (("initial_observation", 0), ("final_observation", -1)):
            endpoint = episode.get(endpoint_name)
            if not isinstance(endpoint, dict):
                raise ValueError("worker result omits a public initial/final observation receipt")
            if (not np.array_equal(joints[obs_index], np.asarray(endpoint.get("joint_position"), dtype=np.float64))
                    or not np.array_equal(ee_poses[obs_index], np.asarray(endpoint.get("ee_pose"), dtype=np.float64))
                    or bytes(boundary_ids[obs_index]).hex() != endpoint.get("boundary_identity_sha256")):
                raise ValueError("independent H5 initial/final observation differs from the worker's public receipt")
            for name in ("bowl_body_pose", "plate_body_pose"):
                if not np.array_equal(
                        (bowl_poses if name == "bowl_body_pose" else plate_poses)[obs_index],
                        np.asarray(endpoint.get("privileged_state", {}).get(name), dtype=np.float64)):
                    raise ValueError("independent H5 initial/final object pose differs from its public receipt")
        motion = _validate_public_motion_gate(
            episode.get("motion_summary", {}), joints[0], joints[-1], ee_poses[0], ee_poses[-1],
            require_thresholds=semantic["transition_count"] == 64,
        )
        total_t += semantic["transition_count"]
        total_obs += semantic["observation_count"]
        total_native += int(progress["native_step_count"])
        h5_receipts.append({"row_index": expected_row, "path": relative,
                            "transition_count": semantic["transition_count"],
                            "observation_count": semantic["observation_count"],
                            "episode_id": semantic["outcome"].episode_id,
                            "motion": motion,
                            "physical_state_monitor": monitor_summary,
                            "h5_sha256": episode["h5"]["sha256"]})
    if (total_t != report.get("transition_count") or total_obs != report.get("observation_count")
            or total_native != report.get("native_step_count")):
        raise ValueError("aggregate worker counts disagree with independently read H5 bundles")
    endpoints = report.get("diagnostic_endpoints")
    if (not isinstance(endpoints, list) or len(endpoints) != 2
            or report.get("reset_count") != report.get("episode_count") + len(endpoints)):
        raise ValueError("worker result omits the two separately counted public contact ResetPlan endpoints")
    for expected_name, expected_value, endpoint in zip(
            ("negative", "positive"), (False, True), endpoints, strict=True):
        plan_mapping = endpoint.get("reset_plan_v1")
        if not isinstance(plan_mapping, Mapping):
            raise ValueError("diagnostic endpoint omits its public ResetPlanV1 mapping")
        plan = ResetPlanV1.from_mapping(dict(plan_mapping))
        plan.validate()
        sample = plan.reset_sample
        readback = endpoint.get("reset_readback_v1")
        contact = endpoint.get("contact_summary_v2")
        predicate = endpoint.get("core_predicate_v1")
        source_oracle = endpoint.get("source_predicate_oracle")
        observation = endpoint.get("public_observation")
        progress = endpoint.get("runtime_progress")
        evidence = endpoint.get("reset_plan_evidence_v1")
        if (endpoint.get("endpoint") != expected_name
                or plan.purpose != "diagnostic_contact_endpoint"):
            raise ValueError("diagnostic endpoint name or ResetPlan purpose is invalid")
        if endpoint.get("reset_plan_identity_sha256") != plan.identity_hash:
            raise ValueError("diagnostic endpoint ResetPlan identity hash mismatch")
        if (not isinstance(readback, dict) or not isinstance(contact, dict)
                or not isinstance(predicate, dict) or not isinstance(source_oracle, dict)
                or not isinstance(observation, dict) or not isinstance(progress, dict)
                or not isinstance(evidence, dict)):
            raise ValueError("diagnostic endpoint readback, contact, or predicate receipt is incomplete")
        if (evidence.get("schema_version") != "reset-plan-evidence-v1"
                or evidence.get("reset_plan_identity_sha256") != plan.identity_hash
                or evidence.get("purpose") != plan.purpose
                or evidence.get("reset_sample_id") != sample.sample_id
                or readback.get("reset_sample_id") != sample.sample_id
                or readback.get("simulation_time_s") != sample.simulation_time_s
                or readback.get("joint_position") != dict(sample.joint_position)
                or readback.get("joint_velocity") != dict(sample.joint_velocity)
                or readback.get("poses_world") != {key: value.to_mapping() for key, value in sample.poses_world.items()}
                or readback.get("free_joint_velocity") != {key: list(value) for key, value in sample.free_joint_velocity.items()}
                or progress.get("episode_id") != contact.get("episode_id")
                or progress.get("reset_sample_id") != sample.sample_id
                or progress.get("native_step_count") != 0
                or progress.get("control_step") != 0):
            raise ValueError("diagnostic endpoint ResetPlan readback or zero-step progress identity mismatch")
        if (contact.get("status") != "available"
                or contact.get("schema_version") != "task-contact-summary-v2"
                or contact.get("requested_pairs") != [["akita_black_bowl_1", "plate_1"]]
                or contact.get("covered_pairs") != contact.get("requested_pairs")
                or any(contact.get(key) != progress.get(key) for key in (
                    "source_id", "source_closure_digest", "provider_materialization_id",
                    "episode_id", "reset_sample_id", "control_step",
                ))
                or contact.get("state_revision") != progress.get("state_revision")
                or contact.get("simulation_time_s") != progress.get("simulation_time_episode_s")):
            raise ValueError("diagnostic endpoint contact query is unavailable, stale, or incomplete")
        poses = observation.get("privileged_state", {})
        bowl = poses.get("bowl_body_pose")
        plate = poses.get("plate_body_pose")
        if (not isinstance(bowl, list) or len(bowl) != 7
                or not isinstance(plate, list) or len(plate) != 7):
            raise ValueError("diagnostic endpoint lacks named public bowl/plate body poses")
        expected_source_value = _source_on_predicate_oracle_v1(contact, bowl, plate)
        if (source_oracle.get("schema_version") != "libero-on-source-oracle-v1"
                or source_oracle.get("value") is not expected_source_value
                or predicate.get("status") != "available"
                or predicate.get("value") is not expected_source_value
                or expected_source_value is not expected_value):
            raise ValueError("diagnostic endpoint Core/source On predicate positive-negative oracle mismatch")
        boundary_identity = {key: contact[key] for key in (
            "source_id", "source_closure_digest", "provider_materialization_id",
            "episode_id", "reset_sample_id", "control_step", "state_revision",
            "simulation_time_s",
        )}
        if observation.get("boundary_identity_sha256") != digest(boundary_identity):
            raise ValueError("diagnostic endpoint observation/contact boundary identity mismatch")
    if report["final_session_close_receipt"].get("session_closed") is not True:
        raise ValueError("worker result lacks the final RuntimeSession close receipt")
    result = {
        "schema_version": "r07c-d01-independent-reader-v1",
        "status": "verified_complete",
        "episode_count": 3,
        "transition_count": total_t,
        "observation_count": total_obs,
        "native_step_count": total_native,
        "reset_count": report["reset_count"],
        "diagnostic_endpoint_count": len(endpoints),
        "h5": h5_receipts,
    }
    if parent_run_record_path is not None:
        if expected_lock_path is None:
            raise ValueError("independent native readback requires the expected shared lock path")
        result["parent_process"] = _validate_parent_run_record(
            bundle_path, report, parent_run_record_path, expected_lock_path,
        )
    elif expected_lock_path is not None:
        raise ValueError("expected native lock path requires a parent run record")
    return result

__all__ = ["consume_libero_candidate_bundle"]
