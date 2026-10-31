"""Cold-read one bounded DG02 Core tracking probe without promotion to N2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import h5py
import numpy as np


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json_dataset(dataset) -> object:
    raw = dataset[()]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(str(raw))


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_probe(plan_path: Path, sidecar_path: Path) -> dict:
    plan_path = plan_path.resolve(strict=True)
    plan_sha256 = _sha(plan_path)
    if plan_sha256 != sidecar_path.resolve(strict=True).read_text(encoding="ascii").split()[0]:
        raise ValueError("DG02 tracking probe plan SHA-256 mismatch")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    expected_class = (
        "actual Core SelectedReferenceEnv PositionServoV1; source-bound GeoPhys/USD; "
        "bounded tracking probe, not a formal cell or qualification"
    )
    if plan.get("classification") != expected_class:
        raise ValueError("reader refuses to treat a non-probe plan as a tracking probe")
    reader_path = Path(__file__).resolve(strict=True)
    frozen_reader_rows = [
        row for row in plan["code"]["tracked_inputs"]
        if Path(row["path"]).resolve() == reader_path
    ]
    if len(frozen_reader_rows) != 1:
        raise ValueError("tracking probe plan does not bind exactly one cold-reader source")
    frozen_reader_sha256 = frozen_reader_rows[0]["sha256"]
    if (plan["oracle"]["episode_count"] != 1
            or plan["oracle"]["control_intervals_per_episode"] != 100
            or plan["limits"]["physics_steps_reserved"] != 500):
        raise ValueError("tracking probe plan differs from the frozen one-episode 500-step envelope")

    normalization_ref = plan["source"].get("control_oracles")
    if not isinstance(normalization_ref, dict):
        raise ValueError("tracking probe plan does not bind the frozen control-oracles source")
    normalization_path = Path(normalization_ref["path"]).resolve(strict=True)
    normalization_sha256 = _sha(normalization_path)
    if normalization_sha256 != normalization_ref["sha256"]:
        raise ValueError("tracking probe control-oracles source hash differs from its frozen plan")
    control_oracles = json.loads(normalization_path.read_text(encoding="utf-8"))
    normalization = control_oracles.get("normalization")
    if not isinstance(normalization, dict) or "usd_f32_abs_tolerance" not in normalization:
        raise ValueError("frozen control-oracles source lacks the USD float32 normalization tolerance")
    usd_f32_abs_tolerance = float(normalization["usd_f32_abs_tolerance"])
    if not np.isfinite(usd_f32_abs_tolerance) or usd_f32_abs_tolerance <= 0:
        raise ValueError("frozen USD float32 normalization tolerance is invalid")

    run_dir = Path(plan["output"]["run_dir"]).resolve(strict=True)
    worker_path = Path(plan["output"]["worker_receipt"]).resolve(strict=True)
    supervisor_path = Path(plan["output"]["native_receipt"]).resolve(strict=True)
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    supervisor = json.loads(supervisor_path.read_text(encoding="utf-8"))
    if supervisor.get("plan_sha256") != plan_sha256 or worker.get("plan_sha256") != plan_sha256:
        raise ValueError("tracking probe receipts are not bound to the frozen plan")
    if (supervisor.get("exit_code") != 0 or supervisor.get("abort_reason")
            or supervisor.get("lock_released_after_process_group_exit") is not True
            or supervisor.get("process_group_gone_before_release") is not True):
        raise ValueError("tracking probe native supervisor did not cleanly complete its child")
    expected_steps = int(plan["limits"]["physics_steps_reserved"])
    if (supervisor.get("physics_steps_attempted") != expected_steps
            or supervisor.get("physics_steps_completed") != expected_steps
            or worker.get("physics_steps_attempted") != expected_steps
            or worker.get("physics_steps_completed") != expected_steps):
        raise ValueError("tracking probe did not complete its exact frozen step reservation")
    if worker.get("status") != "PASS_CORE_N2_TRACKING_PROBE":
        raise ValueError(f"tracking probe worker failed: {worker.get('failure')}")
    if worker.get("episode_count") != 1 or len(worker.get("episodes", [])) != 1:
        raise ValueError("tracking probe worker did not produce exactly one episode")

    h5_path = Path(plan["output"]["episode_h5_paths"][0]).resolve(strict=True)
    h5_sha256 = _sha(h5_path)
    episode = worker["episodes"][0]
    if episode.get("h5_sha256") != h5_sha256:
        raise ValueError("tracking probe H5 hash differs from the worker receipt")
    oracle = plan["oracle"]
    interval_count = int(oracle["control_intervals_per_episode"])
    joint_order = [str(value) for value in oracle["joint_order"]]
    arm_names = [f"joint{index}" for index in range(1, 8)]
    if joint_order[:7] != arm_names:
        raise ValueError("tracking probe oracle arm order differs from the frozen seven-joint order")

    with h5py.File(h5_path, "r") as h5:
        positions = np.asarray(h5["obs/state/joint_position"], dtype=np.float64)
        controls = _load_json_dataset(h5["meta/structured_controls_v1_json"])
        witness = _load_json_dataset(h5["meta/f05_public_typed_state_witness_v1_json"])
        outcome = _load_json_dataset(h5["meta/episode_outcome_v1_json"])
        terminated = np.asarray(h5["terminated"], dtype=bool)
        truncated = np.asarray(h5["truncated"], dtype=bool)
        observation_ids = np.asarray(h5["obs/state/boundary_identity_sha256"], dtype=np.uint8)
    if positions.shape != (interval_count + 1, len(joint_order)):
        raise ValueError(f"tracking H5 joint-position shape is invalid: {positions.shape}")
    if len(controls) != interval_count or len(witness.get("rows", [])) != interval_count + 1:
        raise ValueError("tracking H5 control/witness boundary counts differ from T/T+1")
    if witness.get("observation_count") != interval_count + 1:
        raise ValueError("typed-state witness observation count differs from T+1")
    if observation_ids.shape != (interval_count + 1, 32):
        raise ValueError("tracking H5 boundary identity storage shape is invalid")
    if terminated.any() or truncated[:-1].any() or not truncated[-1]:
        raise ValueError("tracking probe lifecycle differs from its planned final-horizon truncation")
    if (outcome.get("end_reason") != "horizon_reached" or outcome.get("terminated") is not False
            or outcome.get("truncated") is not True or outcome.get("final_boundary") != interval_count):
        raise ValueError("tracking probe H5 episode outcome differs from its bounded horizon")

    phase_by_index = {
        index: phase for phase in oracle["schedule"]
        for index in range(int(phase["start"]), int(phase["stop"]))
    }
    for index, control in enumerate(controls):
        if control.get("schema_version") != "structured-control-transition-v1":
            raise ValueError(f"tracking control row {index} has the wrong schema")
        request = control["request"]
        arm_group = next(
            (group for group in request["groups"] if group.get("group_id") == "arm"), None,
        )
        expected_pose = phase_by_index[index]["source_fk_hand_pose_world"]
        expected_values = [
            *expected_pose["position_m"], *expected_pose["quaternion_wxyz"],
        ]
        if arm_group is None or not np.allclose(
            np.asarray(arm_group["values"], dtype=np.float64),
            np.asarray(expected_values, dtype=np.float64), atol=1e-7, rtol=1e-7,
        ):
            raise ValueError(f"Core request at interval {index} differs from the frozen source-FK phase target")
        writers = control.get("writer_controls", [])
        if len(writers) != 1:
            raise ValueError(f"Core transition {index} does not have exactly one public controller writer")
        payload = writers[0]["applied_control"]["payload"]
        if payload.get("native_interval_advance_attempts") != int(oracle["control_substeps"]):
            raise ValueError(f"Core transition {index} native advance count differs from the frozen schedule")
        ack = payload.get("arm_servo_position")
        if not isinstance(ack, dict) or set(ack) != {f"panda-main/{name}" for name in arm_names}:
            raise ValueError(f"Core transition {index} lacks its exact named arm-target acknowledgement")
        if not np.isfinite(np.asarray(list(ack.values()), dtype=np.float64)).all():
            raise ValueError(f"Core transition {index} arm-target acknowledgement is non-finite")

    typed_positions = np.empty((interval_count + 1, len(joint_order)), dtype=np.float64)
    typed_velocities = np.empty((interval_count + 1, 7), dtype=np.float64)
    for row_index, row in enumerate(witness["rows"]):
        joints = {
            item["joint_id"]: item for item in row["canonical_state_view_v1"]["joints"]
            if item.get("entity_id") == "panda-main"
        }
        if set(joints) != set(joint_order):
            raise ValueError(f"typed witness row {row_index} lacks the exact nine Panda scalar joints")
        typed_positions[row_index] = [float(joints[name]["position"][0]) for name in joint_order]
        typed_velocities[row_index] = [float(joints[name]["velocity"][0]) for name in arm_names]
    if not np.isfinite(typed_positions).all() or not np.isfinite(typed_velocities).all():
        raise ValueError("tracking probe typed states contain non-finite joint values")
    max_storage_error = float(np.max(np.abs(positions - typed_positions)))
    if max_storage_error > usd_f32_abs_tolerance:
        raise ValueError("float32 H5 observations disagree with their typed public-state witness")

    gates = []
    failed = []
    phase_index = {row["phase"]: row for row in oracle["schedule"]}
    required_phases = ("unloaded_home_hold", "unloaded_point")
    if set(phase_index) != set(required_phases):
        raise ValueError("tracking probe does not bind exactly the planned home and point phases")
    for phase_name in required_phases:
        phase = phase_index[phase_name]
        first, stop = int(phase["stop"]) - 9, int(phase["stop"]) + 1
        target = np.asarray([float(phase["arm_target_position_rad"][name]) for name in arm_names])
        q = typed_positions[first:stop, :7]
        dq = typed_velocities[first:stop, :]
        if q.shape != (10, 7) or dq.shape != (10, 7):
            raise ValueError(f"late-window selection for {phase_name} did not yield ten boundaries")
        target_error = float(np.max(np.abs(q - target[None, :])))
        jitter = float(np.max(np.ptp(q, axis=0)))
        velocity = float(np.max(np.abs(dq)))
        target_limit = float(
            oracle["tracking"]["home_hold_max_abs_position_error_rad"]
            if phase_name == "unloaded_home_hold"
            else oracle["tracking"]["point_hold_max_abs_position_error_rad"]
        )
        row = {
            "phase": phase_name,
            "boundary_indices_inclusive": [first, stop - 1],
            "late_max_abs_target_error_rad": target_error,
            "late_max_joint_p2p_rad": jitter,
            "late_max_abs_velocity_rad_s": velocity,
            "frozen_target_error_limit_rad": target_limit,
            "frozen_jitter_limit_rad": float(oracle["tracking"]["late_hold_peak_to_peak_rad"]),
            "frozen_velocity_limit_rad_s": float(oracle["tracking"]["late_hold_max_abs_velocity_rad_s"]),
        }
        row["pass"] = (
            target_error <= row["frozen_target_error_limit_rad"]
            and jitter <= row["frozen_jitter_limit_rad"]
            and velocity <= row["frozen_velocity_limit_rad_s"]
        )
        gates.append(row)
        if not row["pass"]:
            failed.append(phase_name)

    result = {
        "schema_version": "f05-dg02-core-tracking-probe-reader-v2",
        "run_id": plan["run_id"],
        "classification": plan["classification"],
        "status": "PASS_BOUNDED_TRACKING_PROBE" if not failed else "FAIL_BOUNDED_TRACKING_PROBE",
        "formal_cell_pass": False,
        "qualification_granted": False,
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha256,
        "reader_code_sha256_at_plan_freeze": frozen_reader_sha256,
        "reader_code_sha256_at_read_time": _sha(reader_path),
        "reader_code_changed_after_native_worker": frozen_reader_sha256 != _sha(reader_path),
        "normalization_source_path": str(normalization_path),
        "normalization_source_sha256": normalization_sha256,
        "usd_f32_abs_tolerance": usd_f32_abs_tolerance,
        "worker_receipt_sha256": _sha(worker_path),
        "supervisor_receipt_sha256": _sha(supervisor_path),
        "h5_path": str(h5_path),
        "h5_sha256": h5_sha256,
        "actual_observations": int(positions.shape[0]),
        "actual_transitions": len(controls),
        "actual_native_advances": expected_steps,
        "typed_state_witness_rows": len(witness["rows"]),
        "max_float32_storage_vs_typed_error_rad_or_m": max_storage_error,
        "controller_method": oracle["controller_method"],
        "controller_action_config": oracle["controller_action_config"],
        "tracking_gates": gates,
        "failed_phases": failed,
    }
    result_path = Path(plan["output"]["tracking_probe_reader_receipt"]).resolve()
    _atomic_json(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    args = parser.parse_args()
    result = read_probe(args.plan, args.plan_sha256)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS_BOUNDED_TRACKING_PROBE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
