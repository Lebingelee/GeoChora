"""Independent process reader for the two source-bound DG02 Core N2 H5 files."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import h5py
import numpy as np


CORE = Path(__file__).resolve().parents[3]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_file(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return bytes(value).decode("utf-8")
    if isinstance(value, np.ndarray) and value.shape == ():
        return _decode(value.item())
    return str(value)


def _json_dataset(file: h5py.File, name: str):
    return json.loads(_decode(file[name][()]))


def _yaml_dataset(file: h5py.File, name: str):
    from task_env.trajectory.metadata import load_metadata

    return load_metadata(_decode(file[name][()]))


def _h5_identity(path: Path) -> dict:
    stat = path.stat()
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    return {"path": str(path.resolve()), "bytes": stat.st_size, "sha256": _sha(path)}


def _quat_error_rad(actual, expected) -> float:
    qa = np.asarray(actual, dtype=np.float64)
    qe = np.asarray(expected, dtype=np.float64)
    qa /= np.linalg.norm(qa)
    qe /= np.linalg.norm(qe)
    dot = min(1.0, max(-1.0, abs(float(np.dot(qa, qe)))))
    return float(2.0 * math.acos(dot))


def _rotate_vector_wxyz(quaternion, vector) -> np.ndarray:
    q = np.asarray(quaternion, dtype=np.float64)
    v = np.asarray(vector, dtype=np.float64)
    if q.shape != (4,) or v.shape != (3,) or not np.isfinite(q).all() or not np.isfinite(v).all():
        raise ValueError("free-body frame rotation requires finite wxyz quaternion and xyz vector")
    norm = float(np.linalg.norm(q))
    if norm <= 1e-15:
        raise ValueError("free-body orientation quaternion has zero norm")
    w, x, y, z = q / norm
    rotation = np.asarray((
        (1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)),
        (2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)),
        (2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)),
    ), dtype=np.float64)
    return rotation @ v


def _load_episode(path: Path) -> dict:
    identity = _h5_identity(path)
    with h5py.File(path, "r") as file:
        arrays = {
            "joint_position": np.asarray(file["obs/state/joint_position"]),
            "ee_pose": np.asarray(file["obs/state/ee_pose"]),
            "hand_pose": np.asarray(file["obs/state/hand_pose"]),
            "boundary_digest": np.asarray(file["obs/state/boundary_identity_sha256"]),
            "terminated": np.asarray(file["terminated"]),
            "truncated": np.asarray(file["truncated"]),
            "success": np.asarray(file["success"]),
            "reward": np.asarray(file["reward"]),
            "task_free_cube_center_z_m": np.asarray(file["info/task_metrics/free_cube_center_z_m"]),
            "task_lift_threshold_z_m": np.asarray(file["info/task_metrics/lift_threshold_z_m"]),
            "task_raw_lift_predicate": np.asarray(file["info/task_metrics/raw_lift_height_predicate"]),
            "task_lifecycle_terminated": np.asarray(file["info/task_metrics/lifecycle_terminated"]),
            "task_reset_initial_raw_predicate": np.asarray(
                file["info/task_metrics/reset_initial_height_already_satisfies_raw_predicate"]
            ),
        }
        witness = _json_dataset(file, "meta/f05_public_typed_state_witness_v1_json")
        controls = _json_dataset(file, "meta/structured_controls_v1_json")
        events = _json_dataset(file, "meta/boundary_events_v1_json")
        outcome = _json_dataset(file, "meta/episode_outcome_v1_json")
        metadata = {
            "env_meta": _yaml_dataset(file, "meta/env_meta"),
            "env_cfg": _yaml_dataset(file, "meta/env_cfg"),
            "root_attrs": {str(key): _decode(value) for key, value in file.attrs.items()},
        }
        action = {}
        for group in ("action", "universal_action"):
            action[group] = {}
            for name in file[group].keys():
                action[group][name] = np.asarray(file[f"{group}/{name}"])
    return {
        "identity": identity,
        "arrays": arrays,
        "witness": witness,
        "controls": controls,
        "events": events,
        "outcome": outcome,
        "metadata": metadata,
        "action": action,
    }


def _frame(view: dict, entity: str, frame: str) -> dict | None:
    matches = [
        row for row in view["frames"]
        if row["frame"].get("entity_id") == entity and row["frame"].get("frame_id") == frame
    ]
    return None if len(matches) != 1 else matches[0]["pose_world"]


def _joint_rows(view: dict, entity: str) -> dict[str, dict]:
    rows = [row for row in view["joints"] if row.get("entity_id") == entity]
    return {str(row["joint_id"]): row for row in rows}


def _check(condition: bool, code: str, detail: str, errors: list[dict]) -> None:
    if not condition:
        errors.append({"code": code, "detail": detail})


def _validate_bundle(bundle: dict) -> list[dict]:
    errors: list[dict] = []
    plan = bundle["plan"]
    worker = bundle["worker"]
    supervisor = bundle["supervisor"]
    static = bundle["static_receipt"]
    geometry_audit = bundle["source_geometry_audit"]
    oracle = plan["oracle"]
    physical = _json_file(Path(plan["source"]["original_physical_oracle"]["path"]))
    source_actuation = static.get("source_actuation_receipt", {})

    _check(plan.get("run_id") == worker.get("run_id") == supervisor.get("run_id"),
           "cross_run", "plan/worker/supervisor run identity differs", errors)
    _check(worker.get("plan_sha256") == bundle["plan_sha256"] == supervisor.get("plan_sha256"),
           "cross_run", "worker/supervisor receipt is not bound to the frozen plan", errors)
    _check(worker.get("core_head") == plan["input_identity"]["core_input_head"]
           and worker.get("provider_head") == plan["input_identity"]["provider_input_head"],
           "cross_run", "worker Core/provider heads differ from the frozen input", errors)
    _check(supervisor.get("native_starts") == 1 and worker.get("native_starts") == 1,
           "cross_run", "formal cell did not record exactly one native start", errors)
    _check(supervisor.get("exit_code") == 0 and supervisor.get("abort_reason") is None
           and supervisor.get("process_group_gone_before_release") is True
           and supervisor.get("lock_released_after_process_group_exit") is True,
           "exit_code_zero", "supervisor exit/process/lock receipt is not a clean zero exit", errors)
    _check(supervisor.get("physics_steps_attempted") == 3000
           and supervisor.get("physics_steps_completed") == 3000
           and worker.get("physics_steps_attempted") == 3000
           and worker.get("physics_steps_completed") == 3000,
           "cross_run", "exact formal 3000 accepted native advances are not present", errors)
    _check(worker.get("same_selected_env_instance") is True and worker.get("episode_count") == 2,
           "cross_run", "two episodes do not share one actual SelectedReferenceEnv instance", errors)
    _check(worker.get("selected_env_close_returned") is True,
           "cross_run", "SelectedReferenceEnv.close did not return", errors)

    expected_source_closure = plan["source"]["source_closure_sha256"]
    _check(static.get("provider_source_closure_sha256") == expected_source_closure
           and worker.get("source_delivery_identity_sha256") == plan["source"]["delivery_identity_sha256"]
           and worker.get("usd_stage_sha256") == plan["source"]["usd_stage"]["sha256"],
           "source_closure", "current receipt/worker does not bind the frozen USD source closure", errors)
    _check(static.get("checks", {}).get("solver_initialized") is False
           and static.get("checks", {}).get("solver_constructed") is False
           and static.get("checks", {}).get("physics_steps") == 0,
           "model_shape", "static receipt is not a zero-step source-bound admission", errors)
    expected_counts = oracle["required_public_model_counts"]
    public_model_counts = static.get("public_model_counts", {})
    actual_geom_count = (
        public_model_counts.get("n_geoms")
        if isinstance(public_model_counts, dict)
        else None
    )
    _check(isinstance(public_model_counts, dict) and all(
        public_model_counts.get(name) == count for name, count in expected_counts.items()
    ),
           "model_shape", "public source model counts differ from the required Panda model", errors)
    panda_geometry_count = geometry_audit.get("panda", {}).get("collision_shape_count")
    task_scene = geometry_audit.get("task_scene", {})
    task_geom_count = sum(bool(task_scene.get(key)) for key in (
        "free_cube_prim_exists", "support_prim_exists",
    ))
    expected_geom_count = (
        int(panda_geometry_count) + task_geom_count
        if isinstance(panda_geometry_count, int) and task_geom_count == 2
        else None
    )
    _check(geometry_audit.get("passed") is True
           and geometry_audit.get("usd_stage_sha256") == plan["source"]["usd_stage"]["sha256"]
           and expected_geom_count is not None
           and actual_geom_count == expected_geom_count,
           "model_shape",
           "public geom count differs from the hashed USD collision-shape audit plus the two task collision prims",
           errors)
    _check(oracle.get("joint_order") == [*(f"joint{i}" for i in range(1, 8)), "finger_joint1", "finger_joint2"],
           "joint_address", "frozen observation joint address map/order changed", errors)
    _check(oracle.get("original_physical_acceptance") == physical["physical_acceptance"],
           "com", "formal physical thresholds/COM reference differ from the unchanged oracle", errors)

    _check(source_actuation.get("tendon_joint_names") == ["finger_joint1", "finger_joint2"]
           and source_actuation.get("tendon_coefficients") == [0.5, 0.5],
           "tendon_coefficient", "public source tendon coordinates/Jacobian differ from frozen source", errors)
    drives = source_actuation.get("drives", [])
    _check(len(drives) == 9 and [row.get("native_dof_name") for row in drives[:7]]
           == [f"joint{i}" for i in range(1, 8)]
           and [row.get("native_dof_name") for row in drives[7:]]
           == ["finger_joint1", "finger_joint2"],
           "joint_address", "static source actuator-to-joint address mapping changed", errors)
    _check(len(drives) == 9 and all(
        row.get("native_actuator_index") == 7
        and row.get("native_actuator_name") == "actuator8"
        and row.get("control_lower") == 0.0 and row.get("control_upper") == 255.0
        and row.get("force_lower") == -100.0 and row.get("force_upper") == 100.0
        for row in drives[7:]),
        "force_clip", "native affine actuator control/force clipping changed", errors)
    _check(source_actuation.get("equality_name") == "finger_joint1_finger_joint2"
           and source_actuation.get("equality_solref") == [0.005, 1.0]
           and source_actuation.get("equality_solimp") == [0.95, 0.99, 0.001],
           "equality", "source equality compliance/name was altered", errors)

    episodes = bundle["episodes"]
    _check(len(episodes) == 2 and len(worker.get("episodes", [])) == 2,
           "cross_run", "two episode outputs/receipts are not present", errors)
    if len(episodes) != 2:
        return errors
    episode_ids, reset_ids = [], []
    original_thresholds = physical["physical_acceptance"]["thresholds"]
    home = oracle["home_joint_position_rad"]
    arm_names = [f"joint{i}" for i in range(1, 8)]
    phases = oracle["schedule"]
    expected_observation_order = oracle["joint_order"]
    fk_pos_errors: list[float] = []
    fk_rot_errors: list[float] = []
    gate_rows = []
    contact_gate_rows = []

    for episode_index, episode in enumerate(episodes, 1):
        arrays, witness = episode["arrays"], episode["witness"]
        rows = witness.get("rows", [])
        worker_episode = worker.get("episodes", [{}])[episode_index - 1]
        contact_reset = worker_episode.get("contact_observation_reset", {})
        contact_owner = contact_reset.get("owner")
        contact_episode = contact_reset.get("episode")
        contact_generation = contact_reset.get("generation")
        _check(episode["identity"]["sha256"] == episode["worker_h5_sha256"],
               "durable_file", f"episode {episode_index} file hash differs from producer receipt", errors)
        _check(episode["identity"]["bytes"] == episode["worker_h5_bytes"]
               and episode["worker_durable_file"] is True,
               "durable_file", f"episode {episode_index} file durability/length receipt differs", errors)
        _check(len(rows) == 301 and witness.get("observation_count") == 301,
               "obs_length", f"episode {episode_index} typed witness is not T+1=301", errors)
        expected_shapes = {
            "joint_position": ((301, 9), np.dtype("float32")),
            "ee_pose": ((301, 7), np.dtype("float32")),
            "hand_pose": ((301, 7), np.dtype("float32")),
            "boundary_digest": ((301, 32), np.dtype("uint8")),
            "terminated": ((300,), np.dtype("bool")),
            "truncated": ((300,), np.dtype("bool")),
            "task_free_cube_center_z_m": ((300,), np.dtype("float64")),
            "task_lift_threshold_z_m": ((300,), np.dtype("float64")),
            "task_raw_lift_predicate": ((300,), np.dtype("bool")),
            "task_lifecycle_terminated": ((300,), np.dtype("bool")),
        }
        for name, (shape, dtype) in expected_shapes.items():
            value = arrays[name]
            _check(value.shape == shape, "obs_length", f"episode {episode_index} {name} shape {value.shape} != {shape}", errors)
            _check(value.dtype == dtype, "obs_dtype", f"episode {episode_index} {name} dtype {value.dtype} != {dtype}", errors)
            if np.issubdtype(value.dtype, np.number):
                _check(bool(np.isfinite(value).all()), "obs_nonfinite", f"episode {episode_index} {name} has non-finite values", errors)
        controls = episode["controls"]
        worker_transitions = worker_episode.get("transitions", [])
        _check(len(controls) == 300, "obs_length", f"episode {episode_index} has not recorded 300 controls", errors)
        _check(len(worker_transitions) == 300, "contact_observation", f"episode {episode_index} has not recorded 300 Core-boundary contact samples", errors)
        _check(contact_reset.get("schema_version") == "f05-dg02-public-contact-observation-v1"
               and contact_reset.get("known") is False
               and isinstance(contact_owner, str) and bool(contact_owner)
               and type(contact_episode) is int and contact_episode >= 1
               and type(contact_generation) is int and contact_generation >= 0
               and contact_reset.get("completed_substeps") == 0
               and contact_reset.get("delivery_errors") == 0,
               "contact_observation", f"episode {episode_index} reset did not establish a fresh one-based public contact epoch", errors)
        _check(np.array_equal(arrays["terminated"], np.zeros(300, dtype=np.bool_))
               and np.array_equal(arrays["truncated"], np.r_[np.zeros(299, dtype=np.bool_), True]),
               "exit_code_zero", f"episode {episode_index} lifecycle boundary flags differ from the explicit horizon policy", errors)
        outcome = episode["outcome"]
        _check(outcome.get("end_reason") == "horizon_reached"
               and outcome.get("final_boundary") == 300
               and outcome.get("terminated") is False
               and outcome.get("truncated") is True
               and outcome.get("bootstrap_allowed") is True,
               "exit_code_zero", f"episode {episode_index} terminal outcome differs from the planned horizon", errors)
        _check(len(episode["events"]) == 1
               and episode["events"][0].get("event_type") == "episode_ended"
               and episode["events"][0].get("boundary_index") == 300,
               "exit_code_zero", f"episode {episode_index} lacks its final episode-ended boundary event", errors)

        q_rows: list[dict[str, float]] = []
        dq_rows: list[dict[str, float]] = []
        z_rows: list[float] = []
        vz_rows: list[float] = []
        twist_rows: list[list[float]] = []
        for index, row in enumerate(rows):
            _check(row.get("boundary_index") == index, "stale_time", f"episode {episode_index} witness row index is stale", errors)
            view = row.get("canonical_state_view_v1", {})
            boundary = view.get("boundary", {})
            clock = view.get("sample_clock", {})
            identity = row.get("state_boundary_identity", {})
            _check(identity == boundary, "reset_write_receipt", f"episode {episode_index} typed boundary identity differs", errors)
            reset_id = boundary.get("reset_sample_id")
            if index == 0:
                reset_ids.append(reset_id)
                _check(boundary.get("control_step") == 0 and clock.get("sample_index") == 0
                       and float(clock.get("simulation_time_s", math.nan)) == 0.0,
                       "reset_write_receipt", f"episode {episode_index} did not begin at a true reset boundary", errors)
                _check(reset_id == episode["worker_reset_sample_id"],
                       "reset_write_receipt", f"episode {episode_index} reset write receipt identity differs", errors)
            episode_ids.append(boundary.get("episode_id"))
            expected_time = index * float(oracle["outer_control_dt_s"])
            _check(boundary.get("control_step") == index
                   and clock.get("clock_domain") == "evaluation_boundary"
                   and clock.get("sample_index") == index
                   and abs(float(clock.get("simulation_time_s", math.nan)) - expected_time) <= 1e-9,
                   "stale_time", f"episode {episode_index} boundary/clock sample {index} is stale", errors)
            digest = hashlib.sha256(json.dumps(
                boundary, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")).digest()
            _check(arrays["boundary_digest"].shape[0] > index
                   and bytes(arrays["boundary_digest"][index].tolist()) == digest,
                   "obs_boundary_digest", f"episode {episode_index} stored boundary digest {index} differs", errors)
            joints = _joint_rows(view, "panda-main")
            expected_names = set(expected_observation_order)
            _check(set(joints) == expected_names, "joint_address", f"episode {episode_index} public joints differ from exact source names", errors)
            arm_q: dict[str, float] = {}
            arm_dq: dict[str, float] = {}
            if expected_names.issubset(joints):
                vector = []
                for joint_id in expected_observation_order:
                    item = joints[joint_id]
                    position = item.get("position", [])
                    velocity = item.get("velocity", [])
                    _check(len(position) == 1 and len(velocity) == 1,
                           "joint_address", f"episode {episode_index} {joint_id} is not a scalar coordinate", errors)
                    if len(position) != 1 or len(velocity) != 1:
                        continue
                    expected_unit = "meter" if joint_id.startswith("finger") else "radian"
                    expected_kind = "prismatic" if joint_id.startswith("finger") else "revolute"
                    _check(item.get("position_representation") == expected_unit
                           and item.get("kind") == expected_kind,
                           "unit", f"episode {episode_index} {joint_id} unit/kind differs", errors)
                    if joint_id.startswith("joint"):
                        arm_q[joint_id] = float(position[0])
                        arm_dq[joint_id] = float(velocity[0])
                    vector.append(float(position[0]))
                # The public H5 projection is arm-first, then the two fingers.
                arm_vector = [float(joints[name]["position"][0]) for name in arm_names if name in joints]
                finger_vector = [float(joints[name]["position"][0]) for name in ("finger_joint1", "finger_joint2") if name in joints]
                expected_vector = np.asarray(arm_vector + finger_vector, dtype=np.float32)
                if arrays["joint_position"].shape[0] > index:
                    _check(arrays["joint_position"].shape[1:] == expected_vector.shape
                           and np.array_equal(arrays["joint_position"][index], expected_vector),
                           "obs_joint_position", f"episode {episode_index} H5 joint observation differs from typed state at {index}", errors)
            q_rows.append(arm_q)
            dq_rows.append(arm_dq)

            hand = _frame(view, "panda-main", "hand")
            cube = _frame(view, "free-cube", "free_cube")
            free_joint = _joint_rows(view, "free-cube").get("cube_freejoint")
            _check(hand is not None and cube is not None and free_joint is not None,
                   "obs_cube_pose", f"episode {episode_index} lacks public Hand/cube frame or cube joint", errors)
            if cube is None or free_joint is None:
                z_rows.append(math.nan)
                vz_rows.append(math.nan)
                twist_rows.append([math.nan] * 6)
                continue
            z = float(cube["position"][2])
            z_rows.append(z)
            q_cube = free_joint.get("position", [])
            v_cube = free_joint.get("velocity", [])
            _check(len(q_cube) == 7 and len(v_cube) == 6
                   and free_joint.get("position_representation") == "xyz_meter_quaternion_wxyz"
                   and free_joint.get("velocity_representation") == "linear_xyz_meter_per_second_angular_xyz_radian_per_second"
                   and free_joint.get("velocity_expressed_in") == {"entity_id": "free-cube", "frame_id": "free_cube"}
                   and free_joint.get("velocity_reference_point") == {"entity_id": "free-cube", "frame_id": "free_cube"},
                   "obs_cube_pose", f"episode {episode_index} cube free-joint contract is malformed", errors)
            if len(q_cube) == 7:
                _check(np.allclose(np.asarray(q_cube[:3], dtype=np.float64), cube["position"], atol=2e-7, rtol=0),
                       "obs_cube_pose", f"episode {episode_index} cube COM/free-joint position differs at {index}", errors)
            try:
                world_linear_velocity = _rotate_vector_wxyz(cube["quaternion_wxyz"], v_cube[:3])
                vz = float(world_linear_velocity[2])
            except (TypeError, ValueError, IndexError):
                vz = math.nan
            twist_rows.append([float(value) for value in v_cube] if len(v_cube) == 6 else [math.nan] * 6)
            vz_rows.append(vz)
            if hand is not None:
                expected_hand_position = np.asarray(hand["position"], dtype=np.float32)
                expected_hand_quaternion = np.asarray(hand["quaternion_wxyz"], dtype=np.float32)
                for leaf_name in ("ee_pose", "hand_pose"):
                    if arrays[leaf_name].shape[0] > index:
                        stored = arrays[leaf_name][index]
                        _check(np.allclose(stored[:3], expected_hand_position, atol=2e-7, rtol=0)
                               and _quat_error_rad(stored[3:], expected_hand_quaternion) <= 2e-5,
                               "obs_ee_pose" if leaf_name == "ee_pose" else "obs_hand_pose",
                               f"episode {episode_index} {leaf_name} differs from actual typed Hand frame at {index}", errors)
            if index > 0 and arrays["task_free_cube_center_z_m"].shape[0] >= index:
                metric_z = float(arrays["task_free_cube_center_z_m"][index - 1])
                threshold = float(arrays["task_lift_threshold_z_m"][index - 1])
                raw = bool(arrays["task_raw_lift_predicate"][index - 1])
                _check(abs(metric_z - z) <= 2e-7, "task_predicate", f"episode {episode_index} public Task cube height differs from typed state at transition {index - 1}", errors)
                _check(raw == (metric_z >= threshold), "task_predicate", f"episode {episode_index} raw lift predicate is inconsistent with its actual height/threshold at {index - 1}", errors)
                _check(not bool(arrays["task_lifecycle_terminated"][index - 1]), "task_predicate", f"episode {episode_index} Task lifecycle terminated at transition {index - 1}", errors)
                _check(bool(arrays["terminated"][index - 1]) is False
                       and bool(arrays["truncated"][index - 1]) == (index == 300),
                       "task_predicate", f"episode {episode_index} Task/lifecycle termination policy differs at {index - 1}", errors)

        # Each control request is checked against the exact frozen phase target and action.
        _check(len(controls) == 300, "obs_length", f"episode {episode_index} structured-control row count is not 300", errors)
        for index, control_row in enumerate(controls[:300]):
            phase = next(row for row in phases if row["start"] <= index < row["stop"])
            request = control_row.get("request", {})
            groups = {row.get("group_id"): row for row in request.get("groups", [])}
            arm_group, grip_group = groups.get("arm"), groups.get("gripper")
            expected_pose = phase["source_fk_hand_pose_world"]
            expected_arm = [*expected_pose["position_m"], *expected_pose["quaternion_wxyz"]]
            expected_command = 2.0 * float(phase["opening_m"]) / float(oracle["controller_action_config"]["gripper_opening_range_m"]) - 1.0
            _check(arm_group is not None and np.allclose(
                np.asarray(arm_group.get("values", []), dtype=np.float64), expected_arm, atol=2e-7, rtol=0,
            ), "obs_hand_pose", f"episode {episode_index} requested arm pose differs at interval {index}", errors)
            _check(grip_group is not None and len(grip_group.get("values", [])) == 1
                   and abs(float(grip_group["values"][0]) - expected_command) <= 1e-7,
                   "task_predicate", f"episode {episode_index} structured gripper command differs at interval {index}", errors)
            native_receipts = control_row.get("writer_controls", [{}])[0].get("applied_control", {}).get("payload", {}).get("native_interval_advance_receipts_v1", [])
            _check(len(native_receipts) == int(oracle["control_substeps"])
                   and all(row.get("completed_count") == 1 for row in native_receipts),
                   "stale_time", f"episode {episode_index} native advance receipts missing at interval {index}", errors)
            if len(native_receipts) == int(oracle["control_substeps"]):
                expected_end_time = (index + 1) * float(oracle["outer_control_dt_s"])
                _check(abs(float(native_receipts[-1].get("simulation_time_s", math.nan)) - expected_end_time) <= 1e-8,
                       "stale_time", f"episode {episode_index} native simulation time is stale at interval {index}", errors)
            for field, expected_value in zip(("x", "y", "z", "qw", "qx", "qy", "qz", "gripper"),
                                             (*expected_arm, expected_command)):
                projection = episode["action"].get("action", {}).get(field)
                if projection is not None and projection.shape[0] > index:
                    _check(abs(float(projection[index].reshape(-1)[0]) - float(expected_value)) <= 2e-7,
                           "task_predicate", f"episode {episode_index} stored action/{field} differs at interval {index}", errors)

        contact_roles = oracle.get("contact_body_roles", {})
        free_cube_semantics = set(contact_roles.get("free_cube", {}).get("semantic_ids", []))
        support_semantics = set(contact_roles.get("support", {}).get("semantic_ids", []))
        source_contact_hits = []
        for index, transition in enumerate(worker_transitions[:300]):
            sample = transition.get("contact_observation", {})
            _check(sample.get("schema_version") == "f05-dg02-public-contact-observation-v1"
                   and sample.get("known") is True and sample.get("impulses_known") is True,
                   "contact_observation", f"episode {episode_index} contact sample {index} is not known public solver evidence", errors)
            _check(sample.get("owner") == contact_owner
                   and sample.get("episode") == contact_episode
                   and sample.get("generation") == contact_generation + (index + 1) * int(oracle["control_substeps"])
                   and sample.get("completed_substeps") == (index + 1) * int(oracle["control_substeps"])
                   and sample.get("delivery_errors") == 0,
                   "contact_observation", f"episode {episode_index} contact sample {index} has stale/reset-mismatched provenance", errors)
            count = sample.get("contact_count")
            point_count = sample.get("point_count")
            pairs = sample.get("pairs", [])
            _check(type(count) is int and count >= 0 and type(point_count) is int and point_count >= 0
                   and len(pairs) == count,
                   "contact_observation", f"episode {episode_index} contact sample {index} has invalid manifold shape/counts", errors)
            for field, expected_length in (
                ("ncon", count), ("normal_world", count), ("friction", count), ("condim", count),
                ("distance_m", point_count), ("penetration_m", point_count),
                ("point_world_m", point_count), ("normal_impulse_ns", point_count),
                ("dynamic_normal_impulse_ns", point_count),
            ):
                values = sample.get(field, [])
                _check(isinstance(values, list) and len(values) == expected_length,
                       "contact_observation", f"episode {episode_index} contact sample {index} {field} length differs", errors)
                if isinstance(values, list):
                    try:
                        numeric = np.asarray(values, dtype=np.float64)
                        _check(bool(np.isfinite(numeric).all()), "contact_observation",
                               f"episode {episode_index} contact sample {index} {field} is non-finite", errors)
                    except (TypeError, ValueError):
                        _check(False, "contact_observation", f"episode {episode_index} contact sample {index} {field} is not numeric", errors)
            _check(sample.get("capacity_overflow") == 0
                   and sample.get("narrowphase_failure_count") == 0
                   and sample.get("stream_stopped") == 0
                   and sample.get("reservation_invariant_violation") == 0,
                   "contact_observation", f"episode {episode_index} contact sample {index} is incomplete or overflowed", errors)
            for pair in pairs if isinstance(pairs, list) else []:
                names_a = set(pair.get("body_a_semantics", []))
                names_b = set(pair.get("body_b_semantics", []))
                source_pair = (
                    bool(names_a & free_cube_semantics) and bool(names_b & support_semantics)
                ) or (
                    bool(names_b & free_cube_semantics) and bool(names_a & support_semantics)
                )
                if source_pair:
                    cube_pose = _frame(rows[index + 1]["canonical_state_view_v1"], "free-cube", "free_cube")
                    cube_z = math.nan if cube_pose is None else float(cube_pose["position"][2])
                    impulses = np.asarray(sample.get("normal_impulse_ns", []), dtype=np.float64)
                    source_contact_hits.append({
                        "interval_index": index,
                        "pair": pair,
                        "cube_center_z_m": cube_z,
                        "normal_impulse_sum_ns": float(impulses.sum()),
                    })
        expected_rest_z = float(physical["physical_acceptance"]["expected_rest_center_z_m"])
        _check(bool(source_contact_hits), "contact_observation",
               f"episode {episode_index} never observed a public free-cube/support manifold", errors)
        _check(any(
            float(hit["normal_impulse_sum_ns"]) > 0.0
            and abs(float(hit["cube_center_z_m"]) - expected_rest_z) <= 0.003
            for hit in source_contact_hits
        ), "contact_observation", f"episode {episode_index} free-cube/support contact lacks a nonzero solved normal impulse at the frozen rest height", errors)
        contact_gate_rows.append({
            "episode_index": episode_index,
            "provider_contact_owner": contact_owner,
            "provider_contact_episode_index": contact_episode,
            "samples": len(worker_transitions),
            "source_free_cube_support_hits": source_contact_hits,
            "positive_solved_impulse_at_rest": any(
                float(hit["normal_impulse_sum_ns"]) > 0.0
                and abs(float(hit["cube_center_z_m"]) - expected_rest_z) <= 0.003
                for hit in source_contact_hits
            ),
        })

        if len(q_rows) == 301 and all(all(name in row for name in arm_names) for row in q_rows):
            for phase in phases:
                late_start, late_stop = int(phase["stop"]) - 9, int(phase["stop"]) + 1
                late = q_rows[late_start:late_stop]
                late_dq = dq_rows[late_start:late_stop]
                target = phase["arm_target_position_rad"]
                errors_abs = [abs(q_rows[index][joint] - target[joint])
                              for index in range(late_start, late_stop) for joint in arm_names]
                p2p = [max(q[joint] for q in late) - min(q[joint] for q in late) for joint in arm_names]
                peak_velocity = max(abs(v[joint]) for v in late_dq for joint in arm_names)
                gate_rows.append({"episode_index": episode_index, "phase": phase["phase"],
                                  "late_max_abs_target_error_rad": max(errors_abs),
                                  "late_max_joint_p2p_rad": max(p2p),
                                  "late_max_abs_velocity_rad_s": peak_velocity})
                _check(max(p2p) <= float(oracle["tracking"]["late_hold_peak_to_peak_rad"]),
                       "task_predicate", f"episode {episode_index} {phase['phase']} late hold jitter exceeds frozen threshold", errors)
                _check(peak_velocity <= float(oracle["tracking"]["late_hold_max_abs_velocity_rad_s"]),
                       "task_predicate", f"episode {episode_index} {phase['phase']} late velocity exceeds frozen threshold", errors)
                if phase["phase"] == "unloaded_home_hold":
                    _check(max(errors_abs) <= float(oracle["tracking"]["home_hold_max_abs_position_error_rad"]),
                           "task_predicate", f"episode {episode_index} home hold tracking exceeds frozen threshold", errors)
                if phase["phase"] == "unloaded_point":
                    _check(max(errors_abs) <= float(oracle["tracking"]["point_hold_max_abs_position_error_rad"]),
                           "task_predicate", f"episode {episode_index} point hold tracking exceeds frozen threshold", errors)
            point_start, point_stop = 51, 101
            excursion = max(abs(q_rows[index]["joint1"] - float(home["joint1"]))
                            for index in range(point_start, point_stop))
            return_error = max(abs(q_rows[index]["joint1"] - float(home["joint1"]))
                               for index in range(141, 151))
            _check(excursion >= float(original_thresholds["arm_joint1_excursion_min_rad"]),
                   "task_predicate", f"episode {episode_index} joint1 motion excursion did not reach the frozen minimum", errors)
            _check(return_error <= float(original_thresholds["arm_joint1_return_max_error_rad"]),
                   "task_predicate", f"episode {episode_index} home return exceeds the frozen tolerance", errors)

        openings = [sum(float(row["canonical_state_view_v1"]["joints"][next(
            i for i, item in enumerate(row["canonical_state_view_v1"]["joints"])
            if item.get("entity_id") == "panda-main" and item.get("joint_id") == finger
        )]["position"][0]) for finger in ("finger_joint1", "finger_joint2")) for row in rows]
        if len(openings) == 301:
            initial_opening = openings[0]
            close_final = openings[200]
            open_final = openings[250]
            _check(initial_opening - min(openings[151:201]) >= float(oracle["tracking"]["finger_sum_final_close_max_m"]) * 0
                   + float(original_thresholds["gripper_opening_delta_min_m"]),
                   "task_predicate", f"episode {episode_index} gripper opening change is below frozen minimum", errors)
            _check(close_final <= float(oracle["tracking"]["finger_sum_final_close_max_m"]),
                   "task_predicate", f"episode {episode_index} final close opening exceeds frozen maximum", errors)
            _check(open_final >= float(oracle["tracking"]["finger_sum_final_open_min_m"]),
                   "task_predicate", f"episode {episode_index} reopened gripper is below frozen minimum", errors)
            symmetry_rows = [
                rows[index]["canonical_state_view_v1"]["joints"]
                for start, stop in ((191, 201), (241, 251), (291, 301))
                for index in range(start, stop)
            ]
            for index, joint_list in enumerate(symmetry_rows):
                pair = {row["joint_id"]: row for row in joint_list if row.get("entity_id") == "panda-main"}
                if {"finger_joint1", "finger_joint2"}.issubset(pair):
                    diff = abs(float(pair["finger_joint1"]["position"][0]) - float(pair["finger_joint2"]["position"][0]))
                    _check(diff <= float(oracle["tracking"]["late_symmetric_finger_difference_max_m"]),
                           "task_predicate", f"episode {episode_index} fingers are asymmetric in late hold row {index}", errors)

        if len(z_rows) == 301 and len(vz_rows) == 301 and all(math.isfinite(z) for z in z_rows):
            drop = max(z_rows[0] - z for z in z_rows)
            downward_speed = max(-velocity for velocity in vz_rows if math.isfinite(velocity))
            settled = z_rows[-10:]
            settled_mean = float(np.mean(settled))
            settled_deviation = max(abs(value - settled_mean) for value in settled)
            settled_speed = max(abs(value) for value in vz_rows[-10:])
            _check(abs(z_rows[0] - float(physical["physical_acceptance"]["reset_pose_world_m"][2]))
                   <= float(original_thresholds["reset_position_tolerance_m"]),
                   "obs_cube_pose", f"episode {episode_index} reset free-cube height differs from frozen source", errors)
            _check(max(abs(value) for value in twist_rows[0]) <= float(original_thresholds["reset_twist_max_abs"]),
                   "obs_cube_pose", f"episode {episode_index} reset free-cube twist exceeds frozen bound", errors)
            _check(drop >= float(original_thresholds["free_body_drop_min_m"]),
                   "task_predicate", f"episode {episode_index} free cube did not fall the frozen minimum distance", errors)
            _check(downward_speed >= float(original_thresholds["free_body_downward_speed_min_m_s"]),
                   "task_predicate", f"episode {episode_index} free cube did not reach frozen downward speed", errors)
            _check(float(original_thresholds["settled_center_min_m"]) <= settled_mean
                   <= float(original_thresholds["settled_center_max_m"])
                   and settled_deviation <= float(original_thresholds["settled_center_max_deviation_m"])
                   and settled_speed <= float(original_thresholds["settled_vertical_speed_max_m_s"]),
                   "task_predicate", f"episode {episode_index} free cube did not satisfy the frozen settled-height/speed gates", errors)

        _check(len(set(episode_ids)) == 2, "cross_run", "episode boundary identities are duplicated across resets", errors)
    _check(len(set(reset_ids)) == 2, "cross_run", "reset-sample identities are duplicated across episodes", errors)
    bundle["tracking_gate_rows"] = gate_rows
    bundle["contact_gate_rows"] = contact_gate_rows
    return errors


def _mutate_negative(bundle: dict, name: str) -> None:
    episode = bundle["episodes"][0]
    if name == "source_closure":
        bundle["worker"]["source_delivery_identity_sha256"] = "0" * 64
    elif name == "model_shape":
        bundle["static_receipt"]["public_model_counts"]["n_dof"] -= 1
    elif name == "joint_address":
        bundle["plan"]["oracle"]["joint_order"].reverse()
    elif name == "unit":
        joints = bundle["episodes"][0]["witness"]["rows"][0]["canonical_state_view_v1"]["joints"]
        next(row for row in joints if row.get("entity_id") == "panda-main" and row.get("joint_id") == "joint1")["position_representation"] = "meter"
    elif name == "com":
        bundle["plan"]["oracle"]["original_physical_acceptance"]["expected_rest_center_z_m"] += 0.01
    elif name == "tendon_coefficient":
        bundle["static_receipt"]["source_actuation_receipt"]["tendon_coefficients"][0] = 1.0
    elif name == "force_clip":
        bundle["static_receipt"]["source_actuation_receipt"]["drives"][7]["force_upper"] = 50.0
    elif name == "equality":
        bundle["static_receipt"]["source_actuation_receipt"]["equality_solref"][0] = 0.02
    elif name == "reset_write_receipt":
        episode["worker_reset_sample_id"] = "reset-negative"
    elif name == "task_predicate":
        episode["arrays"]["task_raw_lift_predicate"][0] = not bool(episode["arrays"]["task_raw_lift_predicate"][0])
    elif name == "stale_time":
        episode["witness"]["rows"][10]["canonical_state_view_v1"]["sample_clock"]["simulation_time_s"] += 0.02
    elif name == "cross_run":
        episode["witness"]["rows"][0]["canonical_state_view_v1"]["boundary"]["episode_id"] = "episode-duplicate"
        episode["witness"]["rows"][0]["state_boundary_identity"]["episode_id"] = "episode-duplicate"
    elif name == "durable_file":
        episode["worker_h5_sha256"] = "0" * 64
    elif name == "obs_joint_position":
        episode["arrays"]["joint_position"][100, 0] += np.float32(0.1)
    elif name == "obs_ee_pose":
        episode["arrays"]["ee_pose"][100, 0] += np.float32(0.1)
    elif name == "obs_hand_pose":
        episode["arrays"]["hand_pose"][100, 0] += np.float32(0.1)
    elif name == "obs_cube_pose":
        view = episode["witness"]["rows"][100]["canonical_state_view_v1"]
        next(row for row in view["frames"] if row["frame"]["entity_id"] == "free-cube" and row["frame"]["frame_id"] == "free_cube")["pose_world"]["position"][2] += 0.1
    elif name == "obs_boundary_digest":
        episode["arrays"]["boundary_digest"][100, 0] ^= np.uint8(1)
    elif name == "obs_dtype":
        episode["arrays"]["joint_position"] = episode["arrays"]["joint_position"].astype(np.float64)
    elif name == "obs_length":
        episode["arrays"]["joint_position"] = episode["arrays"]["joint_position"][:-1]
    elif name == "obs_nonfinite":
        episode["arrays"]["joint_position"][100, 0] = np.nan
    elif name == "exit_code_zero":
        bundle["supervisor"]["exit_code"] = 1
    elif name == "contact_observation":
        transitions = bundle["worker"]["episodes"][0].get("transitions", [])
        if transitions:
            transitions[0]["contact_observation"]["known"] = False
        else:
            bundle["worker"]["episodes"][0]["transitions"] = []
    else:
        raise ValueError(name)


def _negative_suite(bundle: dict) -> dict:
    classes = (
        "source_closure", "model_shape", "joint_address", "unit", "com",
        "tendon_coefficient", "force_clip", "equality", "reset_write_receipt",
        "task_predicate", "stale_time", "cross_run", "durable_file",
        "obs_joint_position", "obs_ee_pose", "obs_hand_pose", "obs_cube_pose",
        "obs_boundary_digest", "obs_dtype", "obs_length", "obs_nonfinite",
        "exit_code_zero", "contact_observation",
    )
    results = []
    for name in classes:
        mutated = copy.deepcopy(bundle)
        _mutate_negative(mutated, name)
        errors = _validate_bundle(mutated)
        caught = any(row["code"] == name for row in errors)
        row = {"class": name, "rejected": caught, "error_codes": sorted({row["code"] for row in errors})}
        if name == "model_shape":
            geom_mutated = copy.deepcopy(bundle)
            geom_mutated["static_receipt"]["public_model_counts"]["n_geoms"] += 1
            geom_errors = _validate_bundle(geom_mutated)
            geom_rejected = any(item["code"] == "model_shape" for item in geom_errors)
            row["subchecks"] = {
                "required_dof_count_mutation_rejected": caught,
                "source_geom_count_mutation_rejected": geom_rejected,
            }
            row["rejected"] = caught and geom_rejected
            row["error_codes"] = sorted({
                item["code"] for item in (*errors, *geom_errors)
            })
        results.append(row)
    return {
        "schema_version": "f05-dg02-core-n2-negative-suite-v1",
        "required_classes": len(classes),
        "passed_classes": sum(bool(row["rejected"]) for row in results),
        "results": results,
        "inherited_dg01_required_classes": 22,
        "dg02_additional_required_classes": len(classes) - 22,
        "status": "PASS_DG01_22_PLUS_DG02_NEGATIVES" if all(row["rejected"] for row in results) else "FAIL_NEGATIVE_SUITE",
    }


def _build_source_fk_model(plan: dict):
    core = Path(plan["input_identity"]["core_worktree"]).resolve(strict=True)
    provider = Path(plan["input_identity"]["provider_worktree"]).resolve(strict=True)
    provider_src = provider / "src"
    for item in (core, provider_src):
        if str(item) not in sys.path:
            sys.path.insert(0, str(item))
    from task_env.diagnostics.tasks.f05_dg02_core_source_receipt import build_candidate_receipt

    rebuilt, candidate = build_candidate_receipt(plan, include_candidate=True)
    frozen = _json_file(Path(plan["source"]["core_candidate_receipt"]["path"]))
    if rebuilt.get("source_actuation_receipt_identity_sha256") != frozen.get("source_actuation_receipt_identity_sha256"):
        raise ValueError("independent cold reader rebuilt a different source actuation receipt")
    if rebuilt.get("public_model_counts") != frozen.get("public_model_counts"):
        raise ValueError("independent cold reader rebuilt different public model counts")
    return candidate.env.controller.model


def _add_fk_audit(bundle: dict, model) -> dict:
    errors = []
    max_position, max_orientation = 0.0, 0.0
    for episode_index, episode in enumerate(bundle["episodes"], 1):
        for index, row in enumerate(episode["witness"]["rows"]):
            view = row["canonical_state_view_v1"]
            joints = _joint_rows(view, "panda-main")
            hand = _frame(view, "panda-main", "hand")
            if hand is None or any(name not in joints for name in (f"joint{i}" for i in range(1, 8))):
                errors.append({"code": "task_predicate", "detail": f"episode {episode_index} FK state missing at {index}"})
                continue
            q = [float(joints[f"joint{i}"]["position"][0]) for i in range(1, 8)]
            expected = model.pose(q)
            pos_error = float(np.linalg.norm(np.asarray(expected.position) - np.asarray(hand["position"])))
            rot_error = _quat_error_rad(expected.quaternion_wxyz, hand["quaternion_wxyz"])
            max_position, max_orientation = max(max_position, pos_error), max(max_orientation, rot_error)
    thresholds = bundle["plan"]["oracle"]["original_physical_acceptance"]["thresholds"]
    if max_position > float(thresholds["fk_position_error_max_m"]):
        errors.append({"code": "task_predicate", "detail": f"source FK position residual {max_position} exceeds frozen threshold"})
    if max_orientation > float(thresholds["fk_orientation_error_max_rad"]):
        errors.append({"code": "task_predicate", "detail": f"source FK orientation residual {max_orientation} exceeds frozen threshold"})
    return {"max_position_error_m": max_position, "max_orientation_error_rad": max_orientation, "errors": errors}


def run(plan_path: Path, sidecar_path: Path, supervisor_path: Path, worker_path: Path, receipt_path: Path) -> dict:
    started = time.monotonic()
    plan_path = plan_path.resolve(strict=True)
    sidecar_path = sidecar_path.resolve(strict=True)
    plan_raw = plan_path.read_bytes()
    plan_hash = hashlib.sha256(plan_raw).hexdigest()
    if plan_hash != sidecar_path.read_text(encoding="ascii").split()[0]:
        raise ValueError("cold reader plan SHA-256 mismatch")
    plan = json.loads(plan_raw)
    if plan.get("schema_version") != "f05-dg02-core-n2-plan-v1":
        raise ValueError("cold reader received an unsupported formal plan")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"cold reader code input hash differs: {path}")
    for label, row in plan["source"].items():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            path = Path(row["path"]).resolve(strict=True)
            if _sha(path) != row["sha256"]:
                raise ValueError(f"cold reader frozen source hash differs: {label}")
    supervisor_path, worker_path = supervisor_path.resolve(strict=True), worker_path.resolve(strict=True)
    supervisor = _json_file(supervisor_path)
    worker = _json_file(worker_path)
    static_receipt = _json_file(Path(plan["source"]["core_candidate_receipt"]["path"]))
    source_geometry_audit = _json_file(Path(plan["source"]["usd_geometry_audit_v2"]["path"]))
    expected_worker_hash = _sha(worker_path)
    if supervisor.get("worker_receipt_sha256") != expected_worker_hash:
        raise ValueError("supervisor receipt does not bind the cold-read worker receipt bytes")
    episodes = []
    for index, output in enumerate(plan["output"]["episode_h5_paths"], 1):
        path = Path(output).resolve(strict=True)
        loaded = _load_episode(path)
        producer = worker["episodes"][index - 1]
        episodes.append({
            **loaded,
            "worker_h5_sha256": producer["h5_sha256"],
            "worker_h5_bytes": producer["h5_bytes"],
            "worker_durable_file": producer["durable_file"],
            "worker_reset_sample_id": producer["reset_sample_id"],
            "worker_episode_id": producer["reset"]["boundary"]["episode_id"],
            "worker_reset_task_metrics": producer["reset"]["task_metrics"],
        })
    bundle = {
        "plan": plan,
        "plan_sha256": plan_hash,
        "supervisor": supervisor,
        "worker": worker,
        "static_receipt": static_receipt,
        "source_geometry_audit": source_geometry_audit,
        "episodes": episodes,
    }
    errors = _validate_bundle(bundle)
    fk_model = _build_source_fk_model(plan)
    fk_audit = _add_fk_audit(bundle, fk_model)
    errors.extend(fk_audit["errors"])
    negative = _negative_suite(bundle)
    if negative["status"] != "PASS_DG01_22_PLUS_DG02_NEGATIVES":
        errors.append({"code": "negative_suite", "detail": "one or more inherited DG01 or DG02-specific negative mutations were not detected"})
    raw_predicate_start = [
        bool(ep["worker_reset_task_metrics"]["raw_lift_height_predicate"])
        for ep in episodes
    ]
    receipt = {
        "schema_version": "f05-dg02-core-n2-cold-reader-receipt-v1",
        "run_id": plan["run_id"],
        "plan_path": str(plan_path),
        "plan_sha256": plan_hash,
        "worker_receipt_path": str(worker_path),
        "worker_receipt_sha256": expected_worker_hash,
        "supervisor_receipt_sha256": _sha(supervisor_path),
        "episodes": [
            {
                "episode_index": index,
                "h5_path": ep["identity"]["path"],
                "h5_bytes": ep["identity"]["bytes"],
                "h5_sha256": ep["identity"]["sha256"],
                "observation_count": len(ep["witness"]["rows"]),
                "transition_count": len(ep["controls"]),
                "boundary_ids": [row["canonical_state_view_v1"]["boundary"]["boundary_id"]
                                 for row in ep["witness"]["rows"]],
                "episode_id": ep["witness"]["rows"][0]["canonical_state_view_v1"]["boundary"]["episode_id"],
                "reset_sample_id": ep["witness"]["rows"][0]["canonical_state_view_v1"]["boundary"]["reset_sample_id"],
                "contact_observation_reset": worker["episodes"][index - 1].get("contact_observation_reset"),
                "raw_lift_predicate_initial_observed": bool(ep["arrays"]["task_raw_lift_predicate"][0]),
                "outcome": ep["outcome"],
            }
            for index, ep in enumerate(episodes, 1)
        ],
        "actual_observations": sum(len(ep["witness"]["rows"]) for ep in episodes),
        "actual_transitions": sum(len(ep["controls"]) for ep in episodes),
        "native_advances": int(supervisor["physics_steps_completed"]),
        "source_fk": {key: value for key, value in fk_audit.items() if key != "errors"},
        "tracking_gate_rows": bundle.get("tracking_gate_rows", []),
        "contact_gate_rows": bundle.get("contact_gate_rows", []),
        "negative_suite": negative,
        "raw_lift_predicate_initial": raw_predicate_start,
        "raw_predicate_reset_witness_present": ["raw_lift_height_predicate" in ep["worker_reset_task_metrics"] for ep in episodes],
        "lifecycle_valid_success_assessed": False,
        "formal_qualification": False,
        "reader_wall_seconds": time.monotonic() - started,
        "failure_reasons": errors,
        "status": "PASS_N2_COLD_READ_AND_22_NEGATIVES" if not errors else "FAIL_N2_COLD_READ",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, receipt_path)
    directory_fd = os.open(receipt_path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    if errors:
        raise RuntimeError(f"DG02 formal N2 cold reader found {len(errors)} failed checks")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--supervisor", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.plan, args.plan_sha256, args.supervisor, args.worker, args.receipt)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
