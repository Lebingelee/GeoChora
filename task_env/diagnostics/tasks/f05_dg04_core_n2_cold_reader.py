"""Independent H5 reader for the DG04 Isaac native-adaptation Core N2 cell."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


CORE = Path(__file__).resolve().parents[3]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())
    import os
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _view_from_witness(row: dict) -> dict:
    return row.get("canonical_state_view_v1", {})


def _bound_errors(bundle: dict) -> list[dict]:
    from task_env.diagnostics.tasks.f05_dg02_core_n2_cold_reader import (
        _frame, _joint_rows, _load_episode, _quat_error_rad, _rotate_vector_wxyz,
        _stored_cube_pose_matches,
    )
    from task_env.controllers.canonical.kinematics import PandaKinematics, PANDA_HAND_ORIGIN_TCP_V1

    errors = []
    plan, worker, supervisor = bundle["plan"], bundle["worker"], bundle["supervisor"]
    oracle = plan["oracle"]
    contract = oracle["physical_acceptance"]
    threshold = contract["thresholds"]
    _check = lambda ok, code, detail: errors.append({"code": code, "detail": detail}) if not ok else None

    _check(plan["run_id"] == worker.get("run_id") == supervisor.get("run_id"),
           "cross_run", "plan, worker, supervisor run ids differ")
    _check(worker.get("plan_sha256") == bundle["plan_sha256"] == supervisor.get("plan_sha256"),
           "cross_run", "worker/supervisor receipt is not bound to the frozen N2 plan")
    _check(worker.get("core_head") == plan["input_identity"]["core_input_head"],
           "source_identity", "worker Core HEAD differs from the frozen input")
    _check(worker.get("native_starts") == supervisor.get("native_starts") == 1,
           "native_start", "formal N2 did not have exactly one supervised Isaac start")
    _check(supervisor.get("exit_code") == 0 and supervisor.get("abort_reason") is None
           and supervisor.get("process_group_gone_before_release") is True
           and supervisor.get("lock_released_after_process_group_exit") is True
           and supervisor.get("shared_lock_free_after") is True,
           "exit_code_zero", "supervisor exit/process/lock receipt is not clean")
    _check(supervisor.get("physics_steps_attempted") == 3000
           and supervisor.get("physics_steps_completed") == 3000
           and supervisor.get("counter_valid") is True
           and worker.get("physics_steps_attempted") == 3000
           and worker.get("physics_steps_completed") == 3000
           and worker.get("formal_physics_steps_public_manager_delta") == 3000,
           "step_count", "exact 3000 formal Core/native advances were not independently bound")
    _check(worker.get("episode_count") == 2 and worker.get("same_selected_env_instance") is True
           and worker.get("selected_env_close_returned") is True,
           "episode_lifecycle", "formal cell did not reuse one real Env and close it")
    _check(worker.get("candidate") == plan["candidate"],
           "candidate_identity", "worker candidate differs from the source-bound full-horizon plan")
    _check(worker.get("pxr_runtime_identity", {}).get("verification", "").startswith("all adapter-consumed OpenUSD modules originate inside Isaac 6.2"),
           "runtime_identity", "native OpenUSD module origins were not bound to the Isaac 6.2 install")
    _check(worker.get("bootstrap_steps_at_app_open", 0) >= 0,
           "runtime_identity", "worker did not report app-start bootstrap steps separately")
    _check(worker.get("candidate_build_physics_steps") == 0,
           "reset_bootstrap", "source-bound candidate construction advanced native physics")
    _check(worker.get("public_manager_counter_scope")
           == "per_provider_materialization; aggregate sums episode-local deltas",
           "reset_bootstrap", "worker did not identify the public counter's per-materialization scope")
    bootstrap_receipt_total = int(worker.get("bootstrap_steps_at_app_open", -1))
    episode_bootstrap_steps = []
    if len(bundle["episodes"]) == 2 and len(worker.get("episodes", [])) == 2:
        for episode_index, (episode, producer_episode) in enumerate(
                zip(bundle["episodes"], worker["episodes"], strict=True), 1):
            env_meta = episode.get("metadata", {}).get("env_meta", {})
            reference_profile = env_meta.get("reference_profile", {}) if isinstance(env_meta, dict) else {}
            environment = env_meta.get("environment", {}) if isinstance(env_meta, dict) else {}
            _check(environment.get("name") == "SelectedReferenceEnv.F05Dg04IsaacNativePosition"
                   and reference_profile.get("schema_version") == "f05-dg04-isaac-native-core-position-profile-v1"
                   and reference_profile.get("profile_id") == "f05-dg04-isaac-native-mimic-v1",
                   "h5_profile", f"episode {episode_index} H5 does not identify the DG04 native Core route")
            _check(reference_profile.get("provenance_kind") == "native_runtime"
                   and reference_profile.get("runtime_admitted") is True,
                   "h5_profile", f"episode {episode_index} H5 profile is not native-runtime admitted")
            profile_identity_fields = (
                "task_source_identity_sha256", "task_artifact_identity_sha256", "scene_identity_sha256",
                "source_id", "source_closure_sha256", "execution_identity_sha256",
                "reset_plan_identity_sha256", "controller_identity_sha256",
                "control_binding_plan_identity_sha256",
            )
            _check(all(reference_profile.get(field) == plan["candidate"].get(field)
                       for field in profile_identity_fields)
                   and reference_profile.get("reset_sample_id") == plan["candidate"]["reset_sample_id"],
                   "h5_profile", f"episode {episode_index} DG04 profile identities differ from the frozen candidate")
            drive_receipt = reference_profile.get("native_position_drive_receipt", {})
            _check(isinstance(drive_receipt, dict)
                   and drive_receipt.get("identity_sha256")
                   == reference_profile.get("native_position_drive_receipt_identity_sha256"),
                   "h5_profile", f"episode {episode_index} DG04 drive receipt is missing or detached")
            bootstrap = reference_profile.get("native_public_bootstrap_receipt", {})
            steps = bootstrap.get("physics_steps") if isinstance(bootstrap, dict) else None
            bootstrap_dt = bootstrap.get("physics_dt_s") if isinstance(bootstrap, dict) else None
            bootstrap_time = bootstrap.get("physics_time_s") if isinstance(bootstrap, dict) else None
            bootstrap_step_before = bootstrap.get("step_index_before") if isinstance(bootstrap, dict) else None
            bootstrap_step_after = bootstrap.get("step_index_after") if isinstance(bootstrap, dict) else None
            reset_delta = producer_episode.get("reset_manager_physics_steps_delta")
            reset_raw_delta = producer_episode.get("reset_manager_physics_steps_raw_delta")
            reset_before = producer_episode.get("reset_manager_physics_steps_before")
            reset_after = producer_episode.get("reset_manager_physics_steps_after")
            reset_rebased = producer_episode.get("reset_manager_counter_rebased")
            reset_outside_bootstrap = producer_episode.get("reset_physics_steps_outside_bootstrap")
            producer_materialization_id = producer_episode.get("provider_materialization_id")
            witness_rows = episode.get("witness", {}).get("rows", [])
            first_boundary = (
                _view_from_witness(witness_rows[0]).get("boundary", {}) if witness_rows else {}
            )
            h5_materialization_id = first_boundary.get("provider_materialization_id")
            previous_materialization_id = (
                worker["episodes"][episode_index - 2].get("provider_materialization_id")
                if episode_index > 1 else None
            )
            materialization_changed = (
                previous_materialization_id is not None
                and producer_materialization_id != previous_materialization_id
            )
            episode_manager_delta = producer_episode.get("manager_physics_steps_delta_including_bootstrap")
            episode_formal_manager_delta = producer_episode.get("formal_physics_steps_public_manager_delta")
            expected_episode_formal_steps = int(plan["oracle"]["control_intervals_per_episode"]) * int(
                plan["oracle"]["control_substeps"]
            )
            valid_steps = type(steps) is int and 0 <= steps <= int(
                plan["limits"]["bootstrap_steps_per_materialization_max"]
            )
            valid_time = (
                isinstance(bootstrap_dt, (int, float))
                and isinstance(bootstrap_time, (int, float))
                and math.isfinite(float(bootstrap_dt))
                and float(bootstrap_dt) > 0.0
                and math.isfinite(float(bootstrap_time))
                and abs(float(bootstrap_time) - int(steps or 0) * float(bootstrap_dt)) <= 1e-8
                and type(bootstrap_step_before) is int
                and type(bootstrap_step_after) is int
                and bootstrap_step_after - bootstrap_step_before == steps
            )
            bootstrap_identity = hashlib.sha256(json.dumps(
                bootstrap, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")).hexdigest() if isinstance(bootstrap, dict) else None
            _check(bootstrap.get("schema_version") == "isaac-public-physics-bootstrap-v1"
                   and valid_steps and valid_time,
                   "reset_bootstrap", f"episode {episode_index} H5 public bootstrap receipt is missing or invalid")
            _check(type(reset_delta) is int and valid_steps and reset_delta == steps
                   and reset_outside_bootstrap == 0
                   and type(reset_before) is int and type(reset_after) is int
                   and type(reset_raw_delta) is int and reset_raw_delta == reset_after - reset_before
                   and reset_rebased == (reset_raw_delta < 0)
                   and reset_after == bootstrap_step_after
                   and reset_after - bootstrap_step_before == steps,
                   "reset_bootstrap", f"episode {episode_index} reset manager delta is not explained by its materialization bootstrap receipt")
            _check(producer_materialization_id == h5_materialization_id
                   and (reset_raw_delta >= 0 or materialization_changed),
                   "reset_bootstrap", f"episode {episode_index} counter rebase is not bound to a new H5 materialization identity")
            _check(episode_manager_delta == expected_episode_formal_steps + steps
                   and episode_formal_manager_delta == expected_episode_formal_steps,
                   "reset_bootstrap", f"episode {episode_index} public manager total does not reconcile within its materialization")
            _check(producer_episode.get("bootstrap_physics_steps") == steps
                   and producer_episode.get("bootstrap_receipt_identity_sha256") == bootstrap_identity,
                   "reset_bootstrap", f"episode {episode_index} producer bootstrap facts differ from cold H5 metadata")
            if valid_steps:
                episode_bootstrap_steps.append(steps)
                bootstrap_receipt_total += steps
    if len(episode_bootstrap_steps) == 2:
        expected_manager_delta = int(plan["limits"]["physics_steps_reserved"]) + sum(episode_bootstrap_steps)
        _check(worker.get("manager_physics_steps_delta_including_episode_bootstrap") == expected_manager_delta,
               "reset_bootstrap", "worker public manager total does not equal 3000 formal steps plus episode bootstrap")
    _check(bootstrap_receipt_total <= int(plan["limits"]["bootstrap_physics_steps_reserved"])
           and worker.get("bootstrap_steps_charged") == bootstrap_receipt_total,
           "reset_bootstrap", "measured app-open plus episode bootstrap exceeds or differs from the frozen bootstrap reservation")
    _check(supervisor.get("max_process_group_rss_bytes", 2**63) <= plan["limits"]["max_process_group_rss_bytes"]
           and supervisor.get("min_mem_available_bytes", 0) >= plan["limits"]["abort_mem_available_bytes_below"]
           and supervisor.get("min_gpu_free_bytes", 0) >= plan["limits"]["abort_gpu_free_bytes_below"]
           and supervisor.get("max_sample_gap_s", math.inf) <= 2.0,
           "resource_envelope", "supervised native execution breached its frozen emergency envelope")
    _check(len(bundle["episodes"]) == 2 and len(worker.get("episodes", [])) == 2,
           "episode_count", "exactly two cold H5 episodes and worker episode receipts are required")
    if len(bundle["episodes"]) != 2 or len(worker.get("episodes", [])) != 2:
        return errors

    source = plan["source"]
    from task_env.tasks.position_candidate.builder import build_f05_dg04_isaac_native_candidate
    rebuilt_input, rebuilt_candidate = build_f05_dg04_isaac_native_candidate(
        source["delivery_manifest"]["path"], horizon=300,
    )
    rebuilt_identity = {
        "schema_version": rebuilt_input.schema_version,
        "provider": rebuilt_candidate.env.provider,
        "backend": rebuilt_candidate.env.backend,
        "horizon": int(rebuilt_candidate.env.horizon),
        "task_seed": int(rebuilt_input.reset_plan.reset_sample.task_seed),
        "reset_sample_id": rebuilt_input.reset_plan.reset_sample.sample_id,
        "source_id": rebuilt_input.runtime_source.source_id,
        "source_closure_sha256": rebuilt_input.runtime_source.source_closure_digest,
        "task_artifact_identity_sha256": rebuilt_input.artifact.identity_hash,
        "execution_identity_sha256": rebuilt_input.execution.identity_hash,
        "reset_plan_identity_sha256": rebuilt_input.reset_plan.identity_hash,
        "scene_identity_sha256": rebuilt_candidate.scene.identity_hash,
        "control_binding_plan_identity_sha256": rebuilt_candidate.controller_binding_plan.identity_hash,
        "controller_identity_sha256": rebuilt_candidate.env.controller.identity,
        "task_source_identity_sha256": rebuilt_input.task_source.identity_hash,
        "kinematics_source_sha256": rebuilt_input.kinematics_source_sha256,
        "task_scene_recipe_sha256": rebuilt_input.task_scene_recipe_sha256,
        "physics_profile": rebuilt_input.execution.physics_profile,
    }
    _check(rebuilt_identity == plan["candidate"],
           "candidate_identity", "cold reader rebuilt a different source-bound candidate")
    _check(rebuilt_input.runtime_source.source_closure_digest == plan["source_delivery_identity_sha256"],
           "source_closure", "cold reader source closure differs from the frozen native source")
    model = PandaKinematics(rebuilt_input.kinematics_source_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
    arm_names = [f"joint{index}" for index in range(1, 8)]
    expected_order = oracle["joint_order"]
    run_episode_ids, reset_sample_ids, run_drive_receipt_ids = [], [], set()
    fk_position_errors, fk_orientation_errors = [], []
    tracking_rows, contact_rows = [], []

    for episode_index, episode in enumerate(bundle["episodes"], 1):
        arrays, witness = episode["arrays"], episode["witness"]
        rows, controls = witness.get("rows", []), episode["controls"]
        producer_episode = worker["episodes"][episode_index - 1]
        identity = episode["identity"]
        _check(identity["sha256"] == producer_episode.get("h5_sha256"),
               "durable_file", f"episode {episode_index} H5 SHA differs from producer")
        _check(identity["bytes"] == producer_episode.get("h5_bytes")
               and producer_episode.get("durable_file") is True,
               "durable_file", f"episode {episode_index} H5 size/durability differs from producer")
        _check(producer_episode.get("transition_count") == 300
               and producer_episode.get("observation_count") == 301
               and producer_episode.get("reset_sample_id") == plan["candidate"]["reset_sample_id"],
               "producer_receipt", f"episode {episode_index} worker T/T+1 or reset receipt differs")
        reset_metrics = producer_episode.get("reset", {}).get("task_metrics", {})
        _check({"raw_lift_height_predicate", "free_cube_center_z_m", "lifecycle_terminated"}.issubset(reset_metrics)
               and type(reset_metrics.get("raw_lift_height_predicate")) is bool
               and reset_metrics.get("lifecycle_terminated") is False,
               "raw_task_reset_witness", f"episode {episode_index} reset omitted separate raw/lifecycle Task facts")
        root_attrs = episode["metadata"].get("root_attrs", {})
        _check(int(root_attrs.get("transition_count", -1)) == 300
               and int(root_attrs.get("observation_count", -1)) == 301
               and bool(root_attrs.get("episode_complete", False)),
               "h5_metadata", f"episode {episode_index} root metadata is not a finalized T/T+1 episode")
        _check(len(rows) == 301 and witness.get("observation_count") == 301
               and len(controls) == 300 and len(producer_episode.get("transitions", [])) == 300,
               "t_plus_1", f"episode {episode_index} does not contain 301 boundaries and 300 transitions")
        expected_layouts = {
            "joint_position": ((301, 9), np.dtype("float32")),
            "ee_pose": ((301, 7), np.dtype("float32")),
            "hand_pose": ((301, 7), np.dtype("float32")),
            "target_body_pose": ((301, 1, 7), np.dtype("float32")),
            "boundary_digest": ((301, 32), np.dtype("uint8")),
            "terminated": ((300,), np.dtype("bool")),
            "truncated": ((300,), np.dtype("bool")),
            "task_free_cube_center_z_m": ((300,), np.dtype("float64")),
            "task_lift_threshold_z_m": ((300,), np.dtype("float64")),
            "task_raw_lift_predicate": ((300,), np.dtype("bool")),
            "task_lifecycle_terminated": ((300,), np.dtype("bool")),
        }
        for name, (shape, dtype) in expected_layouts.items():
            actual = arrays[name]
            _check(actual.shape == shape and actual.dtype == dtype,
                   "h5_layout", f"episode {episode_index} {name} layout/dtype differs")
            if np.issubdtype(actual.dtype, np.number):
                _check(bool(np.isfinite(actual).all()), "h5_nonfinite", f"episode {episode_index} {name} has nonfinite values")
        _check(np.array_equal(arrays["terminated"], np.zeros(300, dtype=np.bool_))
               and np.array_equal(arrays["truncated"], np.r_[np.zeros(299, dtype=np.bool_), True]),
               "lifecycle", f"episode {episode_index} flags do not encode the one expected final truncation")
        outcome = episode["outcome"]
        _check(outcome.get("end_reason") == "horizon_reached" and outcome.get("final_boundary") == 300
               and outcome.get("terminated") is False and outcome.get("truncated") is True
               and outcome.get("bootstrap_allowed") is True,
               "lifecycle", f"episode {episode_index} outcome differs from frozen horizon policy")
        _check(len(episode["events"]) == 1 and episode["events"][0].get("event_type") == "episode_ended"
               and episode["events"][0].get("boundary_index") == 300,
               "lifecycle", f"episode {episode_index} final BoundaryEvent is missing")

        q_rows, dq_rows, z_rows, vz_rows, twist_rows = [], [], [], [], []
        episode_id = None
        reset_id = None
        for boundary_index, row in enumerate(rows):
            view = _view_from_witness(row)
            boundary = view.get("boundary", {})
            clock = view.get("sample_clock", {})
            _check(row.get("boundary_index") == boundary_index,
                   "stale_time", f"episode {episode_index} witness row {boundary_index} index differs")
            _check(row.get("state_boundary_identity") == boundary,
                   "boundary_identity", f"episode {episode_index} typed boundary witness differs at {boundary_index}")
            expected_time = boundary_index * float(oracle["outer_control_dt_s"])
            _check(boundary.get("control_step") == boundary_index
                   and clock.get("clock_domain") == "evaluation_boundary"
                   and clock.get("sample_index") == boundary_index
                   and abs(float(clock.get("simulation_time_s", math.nan)) - expected_time) <= 1e-9,
                   "stale_time", f"episode {episode_index} clock is stale at boundary {boundary_index}")
            encoded = json.dumps(boundary, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            digest = hashlib.sha256(encoded).digest()
            _check(bytes(arrays["boundary_digest"][boundary_index].tolist()) == digest,
                   "boundary_digest", f"episode {episode_index} H5 boundary digest differs at {boundary_index}")
            _check(boundary.get("provider_materialization_id") == producer_episode.get("provider_materialization_id"),
                   "episode_identity", f"episode {episode_index} materialization identity differs at boundary {boundary_index}")
            if boundary_index == 0:
                episode_id, reset_id = boundary.get("episode_id"), boundary.get("reset_sample_id")
                reset_sample_ids.append(reset_id)
                _check(boundary.get("control_step") == 0 and clock.get("sample_index") == 0
                       and float(clock.get("simulation_time_s", math.nan)) == 0.0
                       and reset_id == producer_episode.get("reset_sample_id"),
                       "reset_identity", f"episode {episode_index} does not start from the producer's reset identity")
                reset_cube = _frame(view, "free-cube", "free_cube")
                if reset_cube is not None:
                    reset_z = float(reset_cube["position"][2])
                    raw_at_reset = bool(reset_metrics.get("raw_lift_height_predicate"))
                    _check(abs(float(reset_metrics.get("free_cube_center_z_m", math.nan)) - reset_z) <= 2e-7
                           and raw_at_reset == (reset_z >= float(reset_metrics.get("lift_threshold_z_m", math.nan))),
                           "raw_task_reset_witness", f"episode {episode_index} reset raw predicate differs from typed cube height")
            run_episode_ids.append(boundary.get("episode_id"))
            joints = _joint_rows(view, "panda-main")
            _check(set(joints) == set(expected_order), "joint_order", f"episode {episode_index} named joint set differs")
            q, dq = {}, {}
            if set(expected_order).issubset(joints):
                values = []
                for name in expected_order:
                    joint = joints[name]
                    pos, vel = joint.get("position", []), joint.get("velocity", [])
                    _check(len(pos) == 1 and len(vel) == 1,
                           "joint_shape", f"episode {episode_index} {name} is not a scalar joint")
                    if len(pos) != 1 or len(vel) != 1:
                        continue
                    unit = "meter" if name.startswith("finger") else "radian"
                    kind = "prismatic" if name.startswith("finger") else "revolute"
                    _check(joint.get("position_representation") == unit and joint.get("kind") == kind,
                           "joint_unit", f"episode {episode_index} {name} kind/unit differs")
                    values.append(float(pos[0]))
                    # Keep the native finger coordinates in the per-boundary
                    # maps too; arm-only gates select arm_names explicitly.
                    q[name], dq[name] = float(pos[0]), float(vel[0])
                _check(np.array_equal(arrays["joint_position"][boundary_index], np.asarray(values, dtype=np.float32)),
                       "typed_projection", f"episode {episode_index} H5 joint projection differs at {boundary_index}")
            q_rows.append(q)
            dq_rows.append(dq)

            hand = _frame(view, "panda-main", "hand")
            cube = _frame(view, "free-cube", "free_cube")
            free_joint = _joint_rows(view, "free-cube").get("cube_freejoint")
            _check(hand is not None and cube is not None and free_joint is not None,
                   "typed_state", f"episode {episode_index} misses Hand/cube frame or free joint")
            if hand is not None:
                hand_vec = [*hand["position"], *hand["quaternion_wxyz"]]
                for leaf in ("ee_pose", "hand_pose"):
                    _check(np.array_equal(arrays[leaf][boundary_index], np.asarray(hand_vec, dtype=np.float32)),
                           "typed_projection", f"episode {episode_index} {leaf} differs at {boundary_index}")
                if all(name in q for name in arm_names):
                    fk = model.pose([q[name] for name in arm_names])
                    position_error = float(np.linalg.norm(np.asarray(fk.position) - np.asarray(hand["position"])))
                    orientation_error = _quat_error_rad(fk.quaternion_wxyz, hand["quaternion_wxyz"])
                    fk_position_errors.append(position_error)
                    fk_orientation_errors.append(orientation_error)
                    _check(position_error <= threshold["fk_position_error_max_m"]
                           and orientation_error <= threshold["fk_orientation_error_max_rad"],
                           "source_fk", f"episode {episode_index} measured-state Hand FK differs at boundary {boundary_index}")
            if cube is None or free_joint is None:
                z_rows.append(math.nan); vz_rows.append(math.nan); twist_rows.append([math.nan] * 6)
            else:
                z = float(cube["position"][2])
                _check(_stored_cube_pose_matches(arrays["target_body_pose"][boundary_index, 0], cube),
                       "typed_projection", f"episode {episode_index} H5 cube pose differs at {boundary_index}")
                position, velocity = free_joint.get("position", []), free_joint.get("velocity", [])
                _check(len(position) == 7 and len(velocity) == 6
                       and free_joint.get("position_representation") == "xyz_meter_quaternion_wxyz"
                       and free_joint.get("velocity_representation") == "linear_xyz_meter_per_second_angular_xyz_radian_per_second"
                       and free_joint.get("velocity_expressed_in") == {"entity_id": "free-cube", "frame_id": "free_cube"}
                       and free_joint.get("velocity_reference_point") == {"entity_id": "free-cube", "frame_id": "free_cube"},
                       "free_joint_contract", f"episode {episode_index} free cube typed velocity contract differs")
                local_velocity = np.asarray(velocity[:3], dtype=np.float64)
                world_velocity = _rotate_vector_wxyz(cube["quaternion_wxyz"], local_velocity)
                z_rows.append(z)
                vz_rows.append(float(world_velocity[2]))
                twist_rows.append([float(value) for value in velocity])
                if boundary_index > 0:
                    metric_index = boundary_index - 1
                    metric_z = float(arrays["task_free_cube_center_z_m"][metric_index])
                    lift_threshold = float(arrays["task_lift_threshold_z_m"][metric_index])
                    raw = bool(arrays["task_raw_lift_predicate"][metric_index])
                    _check(abs(metric_z - z) <= 2e-7 and raw == (metric_z >= lift_threshold),
                           "raw_task_predicate", f"episode {episode_index} raw Task predicate/height mismatch at {metric_index}")
                    _check(not bool(arrays["task_lifecycle_terminated"][metric_index]),
                           "task_lifecycle", f"episode {episode_index} Task lifecycle terminated at {metric_index}")

        _check(reset_id == producer_episode.get("reset_sample_id")
               and reset_id == plan["candidate"]["reset_sample_id"],
               "reset_identity", f"episode {episode_index} reset identity differs from the frozen candidate")
        _check(len(set(run_episode_ids[-301:])) == 1, "episode_identity", f"episode {episode_index} boundary episode ids changed")

        # Recompute every held-target and settling gate from the stored boundaries.
        phase_metrics = []
        for phase in oracle["schedule"]:
            end = int(phase["stop"])
            indices = range(end - 9, end + 1)
            errors_by_joint = {
                name: [q_rows[i].get(name, math.nan) - float(phase["arm_target_position_rad"][name])
                       for i in indices]
                for name in arm_names
            }
            max_error = max(abs(value) for values in errors_by_joint.values() for value in values)
            peak_to_peak = max(max(values) - min(values) for values in errors_by_joint.values())
            max_velocity = max(abs(dq_rows[i].get(name, math.nan)) for i in indices for name in arm_names)
            phase_metrics.append({"phase": phase["phase"], "sample_boundary_indices": list(indices),
                                  "max_abs_joint_error_rad": max_error,
                                  "max_joint_peak_to_peak_rad": peak_to_peak,
                                  "max_abs_joint_velocity_rad_s": max_velocity})
            _check(max_error <= oracle["tracking"]["home_hold_max_abs_position_error_rad"],
                   "tracking", f"episode {episode_index} phase {phase['phase']} held-target error exceeds the frozen bound")
            _check(peak_to_peak <= oracle["tracking"]["late_hold_peak_to_peak_rad"]
                   and max_velocity <= oracle["tracking"]["late_hold_max_abs_velocity_rad_s"],
                   "tracking_settle", f"episode {episode_index} phase {phase['phase']} late hold is not settled")
        home_q = oracle["home_joint_position_rad"]
        point_phase = next(row for row in oracle["schedule"] if row["phase"] == "unloaded_point")
        point_end = int(point_phase["stop"])
        home_end = int(next(row for row in oracle["schedule"] if row["phase"] == "unloaded_home_hold")["stop"])
        _check(max(abs(q_rows[i][name] - float(home_q[name])) for i in range(home_end - 9, home_end + 1) for name in arm_names)
               <= oracle["tracking"]["home_hold_max_abs_position_error_rad"],
               "tracking", f"episode {episode_index} home hold exceeds its target bound")
        _check(max(abs(q_rows[i][name] - float(point_phase["arm_target_position_rad"][name]))
                   for i in range(point_end - 9, point_end + 1) for name in arm_names)
               <= oracle["tracking"]["point_hold_max_abs_position_error_rad"],
               "tracking", f"episode {episode_index} point hold exceeds its target bound")
        joint1_excursion = abs(q_rows[point_end]["joint1"] - q_rows[0]["joint1"])
        final_joint1_error = abs(q_rows[-1]["joint1"] - float(home_q["joint1"]))
        _check(joint1_excursion >= threshold["arm_joint1_excursion_min_rad"],
               "arm_motion", f"episode {episode_index} joint1 excursion is below the frozen minimum")
        _check(final_joint1_error <= threshold["arm_joint1_return_max_error_rad"],
               "arm_motion", f"episode {episode_index} joint1 did not return within the frozen bound")

        close_boundary = next(row["stop"] for row in oracle["schedule"] if row["phase"] == "gripper_close")
        open_boundary = next(row["stop"] for row in oracle["schedule"] if row["phase"] == "gripper_open")
        final_close = sum(q_rows[int(close_boundary)].get(name, math.nan) for name in ("finger_joint1", "finger_joint2"))
        final_open = sum(q_rows[int(open_boundary)].get(name, math.nan) for name in ("finger_joint1", "finger_joint2"))
        _check(final_close <= oracle["tracking"]["finger_sum_final_close_max_m"],
               "gripper", f"episode {episode_index} final close opening exceeds the frozen bound")
        _check(final_open >= oracle["tracking"]["finger_sum_final_open_min_m"]
               and final_open >= final_close + threshold["gripper_opening_delta_min_m"],
               "gripper", f"episode {episode_index} final open/delta is below the frozen minimum")
        symmetry_indices = sorted(set(range(191, 201)) | set(range(241, 251)) | set(range(291, 301)))
        symmetry_max = max(abs(q_rows[i]["finger_joint1"] - q_rows[i]["finger_joint2"]) for i in symmetry_indices)
        _check(symmetry_max <= oracle["tracking"]["late_symmetric_finger_difference_max_m"],
               "gripper_symmetry", f"episode {episode_index} late finger symmetry exceeds the frozen bound")

        reset_twist_max = max(abs(value) for value in twist_rows[0])
        expected_reset_z = float(contract["reset_pose_world_m"][2])
        drop = z_rows[0] - min(z_rows)
        max_downward_speed = max(-value for value in vz_rows)
        settled = z_rows[-10:]
        settled_mean = float(np.mean(settled))
        settled_deviation = max(abs(value - settled_mean) for value in settled)
        settled_speed = max(abs(value) for value in vz_rows[-10:])
        _check(abs(z_rows[0] - expected_reset_z) <= threshold["reset_position_tolerance_m"]
               and reset_twist_max <= threshold["reset_twist_max_abs"],
               "free_body_reset", f"episode {episode_index} cube reset pose/twist exceeds the frozen bound")
        _check(drop >= threshold["free_body_drop_min_m"]
               and max_downward_speed >= threshold["free_body_downward_speed_min_m_s"],
               "free_body_motion", f"episode {episode_index} cube did not fall through the frozen distance/speed")
        _check(float(threshold["settled_center_min_m"]) <= settled_mean <= float(threshold["settled_center_max_m"])
               and settled_deviation <= threshold["settled_center_max_deviation_m"]
               and settled_speed <= threshold["settled_vertical_speed_max_m_s"],
               "free_body_settle", f"episode {episode_index} cube did not settle within the frozen height/speed bound")

        # Read the exact DG04 adapter receipts from stored Core H5 controls.
        contact_substeps, support_hits = [], []
        receipt_index = 0
        for interval, control in enumerate(controls):
            phase = next(row for row in oracle["schedule"] if int(row["start"]) <= interval < int(row["stop"]))
            request = control.get("request", {})
            groups = {row.get("group_id"): row for row in request.get("groups", [])}
            arm_group, gripper_group = groups.get("arm"), groups.get("gripper")
            expected_pose = phase["source_fk_hand_pose_world"]
            expected_arm = [*expected_pose["position_m"], *expected_pose["quaternion_wxyz"]]
            expected_command = 2.0 * float(phase["opening_m"]) / float(oracle["gripper_opening_range_m"]) - 1.0
            _check(arm_group is not None and np.allclose(np.asarray(arm_group.get("values", []), dtype=np.float64),
                                                          expected_arm, atol=2e-7, rtol=0),
                   "stored_action", f"episode {episode_index} interval {interval} arm request differs from frozen FK")
            _check(gripper_group is not None and np.allclose(gripper_group.get("values", []), [expected_command], atol=1e-7, rtol=0),
                   "stored_action", f"episode {episode_index} interval {interval} gripper command differs")
            writer_controls = control.get("writer_controls", [])
            payload = writer_controls[0].get("applied_control", {}).get("payload", {}) if len(writer_controls) == 1 else {}
            native_ack = payload.get("native_position_write_ack_v1", {})
            receipts = payload.get("native_interval_advance_receipts_v1", [])
            producer_transition = producer_episode.get("transitions", [{}])[interval]
            _check(bool(producer_transition.get("task_raw_lift_predicate") is bool(arrays["task_raw_lift_predicate"][interval])
                        and producer_transition.get("task_lifecycle_terminated") is bool(arrays["task_lifecycle_terminated"][interval])),
                   "raw_task_predicate", f"episode {episode_index} stored and producer raw/lifecycle Task fields differ at {interval}")
            _check(len(receipts) == oracle["control_substeps"], "advance_receipt",
                   f"episode {episode_index} interval {interval} lacks five native receipts")
            _check(native_ack.get("schema_version") == "native-position-write-ack-v1"
                   and native_ack.get("partial") is False
                   and bool(native_ack.get("target_identity_sha256"))
                   and set(native_ack.get("native_names", [])) == {*(f"joint{i}" for i in range(1, 8)), "finger_joint1"}
                   and len(native_ack.get("native_names", [])) == 8
                   and len(native_ack.get("applied_values", [])) == 8,
                   "position_ack", f"episode {episode_index} interval {interval} lacks a complete public Position Ack")
            for substep_index, substep in enumerate(receipts):
                expected_index = receipt_index + 1
                receipt_index += 1
                app = substep.get("native_adaptation_application", {})
                contact = app.get("public_contact_witness", {})
                target_id = native_ack.get("target_identity_sha256")
                _check(substep.get("schema_version") == "native-advance-receipt-v1"
                       and substep.get("completed_count") == 1
                       and substep.get("native_step_index") == (interval * 5 + substep_index + 1)
                       and abs(float(substep.get("simulation_time_s", math.nan)) - ((interval * 5 + substep_index + 1) * oracle["physics_dt_s"])) <= 1e-9,
                       "advance_clock", f"episode {episode_index} interval {interval} native step index/time differs")
                _check(app.get("schema_version") == "native-physx-mimic-substep-application-v1"
                       and app.get("provenance_kind") == "native_runtime"
                       and app.get("profile_id") == "isaacsim-6.2-physx-native-mimic-leader-drive-v1"
                       and app.get("target_identity_sha256") == target_id
                       and app.get("native_mimic_api") == "PhysxMimicJointAPI:transX"
                       and app.get("native_drive_api") == "PhysicsDriveAPI:linear"
                       and isinstance(app.get("drive_receipt_identity_sha256"), str)
                       and len(app.get("drive_receipt_identity_sha256", "")) == 64
                       and app.get("public_effort_api") == "Articulation.get_dof_projected_joint_forces"
                       and app.get("effort_measurement_semantics") == "projected_active_joint_force",
                       "native_adaptation_receipt", f"episode {episode_index} substep {expected_index} receipt identity/provenance differs")
                run_drive_receipt_ids.add(app.get("drive_receipt_identity_sha256"))
                relation = float(app.get("relation_error_m", math.nan))
                reference_position = float(app.get("reference_position_m", math.nan))
                follower_position = float(app.get("follower_position_m", math.nan))
                reference_target = float(app.get("reference_target_m", math.nan))
                applied_opening = float(payload.get("gripper_servo_opening_m", math.nan))
                effort = float(app.get("reference_effort_N", math.nan))
                cap = float(app.get("maximum_effort_N", math.nan))
                _check(math.isfinite(relation) and math.isclose(relation, follower_position - reference_position, abs_tol=1e-7)
                       and abs(relation) <= oracle["gripper_native_adaptation"]["joint_relation_abs_error_max_m"]
                       and math.isfinite(applied_opening)
                       and 0.0 <= applied_opening <= float(oracle["gripper_opening_range_m"])
                       and math.isclose(reference_target, applied_opening / 2.0, rel_tol=0.0, abs_tol=1e-7)
                       and math.isfinite(effort) and abs(effort) <= cap + 1e-6 and cap == 100.0,
                       "native_mimic_gate", f"episode {episode_index} substep {expected_index} physical coupling/force/applied target gate failed")
                raw_count = contact.get("raw_contact_count")
                actor_paths = contact.get("raw_contact_actor_paths", [])
                magnitudes = contact.get("raw_contact_normal_forces_N", [])
                signed = contact.get("raw_contact_signed_normal_force_scalars_N", [])
                normals = contact.get("raw_contact_normals_world", [])
                separations = contact.get("raw_contact_separations_m", [])
                support_forces = contact.get("support_contact_normal_forces_N", [])
                support_path = contact.get("support_path")
                is_contact_ok = (
                    contact.get("schema_version") == "f05-dg04-native-contact-witness-v1"
                    and contact.get("provenance_kind") == "native_runtime"
                    and contact.get("api") == "RigidPrim.get_raw_contact_data"
                    and contact.get("sensor_path") == "/F05Scene/free_cube"
                    and support_path == "/F05Scene/support/collision"
                    and type(raw_count) is int and 0 <= raw_count <= 32
                    and all(type(values) is list and len(values) == raw_count
                            for values in (actor_paths, magnitudes, signed, normals, separations))
                    and type(support_forces) is list
                    and type(contact.get("contact_count")) is int
                    and contact.get("contact_count") == len(support_forces)
                    and contact.get("contact_present") is (len(support_forces) > 0)
                    and contact.get("force_magnitude_mapping") == "abs(raw_signed_normal_force_scalar_N)"
                )
                _check(is_contact_ok, "contact_witness", f"episode {episode_index} substep {expected_index} DG04 contact witness is malformed")
                if is_contact_ok:
                    _check(all(isinstance(path, str) and path.startswith("/") for path in actor_paths)
                           and all(math.isfinite(float(value)) and float(value) >= 0.0 for value in magnitudes)
                           and all(math.isclose(float(mag), abs(float(raw)), rel_tol=0.0, abs_tol=1e-7)
                                   for mag, raw in zip(magnitudes, signed, strict=True))
                           and all(len(normal) == 3 and all(math.isfinite(float(value)) for value in normal) for normal in normals)
                           and all(math.isfinite(float(value)) for value in separations)
                           and all(math.isfinite(float(value)) and float(value) >= 0.0 for value in support_forces),
                           "contact_witness", f"episode {episode_index} substep {expected_index} aligned raw contact values are invalid")
                    support_indices = [i for i, path in enumerate(actor_paths)
                                       if path == support_path or path.startswith(support_path + "/") or path == "/F05Scene/support"]
                    _check(len(support_indices) == len(support_forces)
                           and np.allclose(support_forces, [magnitudes[i] for i in support_indices], atol=1e-7, rtol=1e-7)
                           and math.isclose(float(contact.get("normal_force_sum_N", math.nan)), math.fsum(support_forces), abs_tol=1e-7),
                           "contact_mapping", f"episode {episode_index} substep {expected_index} support-force mapping differs")
                    if support_forces and math.fsum(support_forces) > 0.0:
                        cube_z = z_rows[interval + 1]
                        support_hits.append({"interval": interval, "substep_index": expected_index,
                                             "cube_center_z_m": cube_z,
                                             "support_normal_force_sum_N": math.fsum(support_forces)})
                contact_substeps.append(contact)
        _check(len(contact_substeps) == 1500, "contact_witness", f"episode {episode_index} does not store all 1500 contact witnesses")
        _check(any(abs(hit["cube_center_z_m"] - float(contract["expected_rest_center_z_m"])) <= 0.003
                   and hit["support_normal_force_sum_N"] > 0.0 for hit in support_hits),
               "contact_witness", f"episode {episode_index} has no positive public support force at frozen rest height")
        contact_rows.append({"episode_index": episode_index, "substep_witness_count": len(contact_substeps),
                             "support_contact_hits": support_hits,
                             "positive_support_force_at_rest": any(
                                 abs(hit["cube_center_z_m"] - float(contract["expected_rest_center_z_m"])) <= 0.003
                                 and hit["support_normal_force_sum_N"] > 0.0 for hit in support_hits)})
        tracking_rows.append({"episode_index": episode_index, "phase_metrics": phase_metrics,
                              "joint1_excursion_rad": joint1_excursion,
                              "joint1_final_home_error_rad": final_joint1_error,
                              "final_close_finger_sum_m": final_close,
                              "final_open_finger_sum_m": final_open,
                              "late_finger_symmetry_max_m": symmetry_max,
                              "free_body": {"initial_center_z_m": z_rows[0], "minimum_center_z_m": min(z_rows),
                                            "drop_m": drop, "max_downward_speed_m_s": max_downward_speed,
                                            "settled_mean_center_z_m": settled_mean,
                                            "settled_max_deviation_m": settled_deviation,
                                            "settled_max_vertical_speed_m_s": settled_speed}})

    _check(len(set(run_episode_ids)) == 2, "episode_identity", "the two episode ids are not distinct")
    _check(len(run_drive_receipt_ids) == 1, "native_adaptation_receipt",
           "native DG04 drive receipt identity changed across the two episodes")
    _check(len(reset_sample_ids) == 2 and len(set(reset_sample_ids)) == 1
           and reset_sample_ids[0] == plan["candidate"]["reset_sample_id"],
           "reset_identity", "the same frozen content-addressed ResetSample was not reused")
    bundle["tracking_gate_rows"] = tracking_rows
    bundle["contact_gate_rows"] = contact_rows
    bundle["source_fk_summary"] = {
        "measurement": "measured public arm joints through source PandaKinematics versus independently stored typed Hand frame",
        "max_position_error_m": max(fk_position_errors, default=math.nan),
        "max_orientation_error_rad": max(fk_orientation_errors, default=math.nan),
        "sample_count": len(fk_position_errors),
    }
    return errors


def run(plan_path: Path, sidecar_path: Path, supervisor_path: Path, worker_path: Path,
        receipt_path: Path) -> dict:
    from task_env.diagnostics.tasks.f05_dg02_core_n2_cold_reader import _load_episode

    started = time.monotonic()
    plan_path, sidecar_path = plan_path.resolve(strict=True), sidecar_path.resolve(strict=True)
    plan_bytes = plan_path.read_bytes()
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    if plan_sha != sidecar_path.read_text(encoding="ascii").split()[0]:
        raise ValueError("DG04 cold-reader plan SHA mismatch")
    plan = json.loads(plan_bytes)
    if plan.get("schema_version") != "f05-dg04-core-n2-plan-v1":
        raise ValueError("unsupported DG04 cold-reader plan")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"DG04 independent reader code/source hash changed: {path}")
    for label, row in plan["source"].items():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            path = Path(row["path"]).resolve(strict=True)
            if _sha(path) != row["sha256"]:
                raise ValueError(f"DG04 frozen source hash differs: {label}")
    supervisor_path, worker_path = supervisor_path.resolve(strict=True), worker_path.resolve(strict=True)
    supervisor, worker = (json.loads(supervisor_path.read_text()), json.loads(worker_path.read_text()))
    if supervisor.get("worker_receipt_sha256") != _sha(worker_path):
        raise ValueError("DG04 supervisor receipt does not bind worker receipt bytes")
    static_receipt = json.loads(Path(plan["source"]["candidate_static_receipt"]["path"]).read_text())
    _check_static = static_receipt.get("candidate") == plan["candidate"]
    if not _check_static or static_receipt.get("status") != "PASS_ZERO_STEP_SOURCE_BOUND_CANDIDATE_REBUILD":
        raise ValueError("frozen zero-step candidate receipt differs from the N2 candidate")
    episodes = []
    for index, output in enumerate(plan["output"]["episode_h5_paths"], 1):
        path = Path(output).resolve(strict=True)
        loaded = _load_episode(path)
        episodes.append(loaded)
    bundle = {"plan": plan, "plan_sha256": plan_sha, "supervisor": supervisor,
              "worker": worker, "episodes": episodes}
    errors = _bound_errors(bundle)
    raw_predicate_initial = []
    for item in worker.get("episodes", []):
        metrics = item.get("reset", {}).get("task_metrics", {})
        if "raw_lift_height_predicate" not in metrics or "lifecycle_terminated" not in metrics:
            raw_predicate_initial.append(None)
        else:
            raw_predicate_initial.append(bool(metrics["raw_lift_height_predicate"]))
    if len(raw_predicate_initial) != 2 or any(value is None for value in raw_predicate_initial):
        # The missing reset witness is independently reported as a failed receipt check.
        errors.append({"code": "raw_task_reset_witness", "detail": "producer omitted initial raw/lifecycle Task metrics"})
    reader_receipt = {
        "schema_version": "f05-dg04-core-n2-cold-reader-receipt-v1",
        "run_id": plan["run_id"], "plan_path": str(plan_path), "plan_sha256": plan_sha,
        "worker_receipt_path": str(worker_path), "worker_receipt_sha256": _sha(worker_path),
        "supervisor_receipt_sha256": _sha(supervisor_path),
        "reader_source_sha256": _sha(Path(__file__).resolve(strict=True)),
        "episodes": [
            {"episode_index": index, "h5_path": episode["identity"]["path"],
             "h5_bytes": episode["identity"]["bytes"], "h5_sha256": episode["identity"]["sha256"],
             "observations": len(episode["witness"].get("rows", [])),
             "transitions": len(episode["controls"]), "outcome": episode["outcome"],
             "episode_id": episode["witness"]["rows"][0]["canonical_state_view_v1"]["boundary"]["episode_id"]}
            for index, episode in enumerate(episodes, 1)
        ],
        "actual_observations": sum(len(ep["witness"].get("rows", [])) for ep in episodes),
        "actual_transitions": sum(len(ep["controls"]) for ep in episodes),
        "native_advances": int(supervisor.get("physics_steps_completed", 0)),
        "source_fk": bundle.get("source_fk_summary"),
        "tracking_gate_rows": bundle.get("tracking_gate_rows", []),
        "contact_gate_rows": bundle.get("contact_gate_rows", []),
        "raw_task_predicate_initial": raw_predicate_initial,
        "raw_task_predicate_is_not_lifecycle_success": True,
        "lifecycle_valid_success_assessed": False,
        "qualification_granted": False,
        "reader_wall_seconds": time.monotonic() - started,
        "failure_reasons": errors,
        "status": "PASS_DG04_CORE_N2_INDEPENDENT_COLD_READ" if not errors else "PARTIAL_DG04_CORE_N2_COLD_READ",
    }
    _atomic(receipt_path, reader_receipt)
    if errors:
        raise RuntimeError(f"DG04 independent N2 cold reader found {len(errors)} failed checks")
    return reader_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--supervisor", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.plan, args.plan_sha256, args.supervisor, args.worker, args.receipt)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
