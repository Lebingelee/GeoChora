"""Single-Panda structured R1 behavior plus Generic H5 v3 disk probe.

This is a diagnostic composition of the existing plan-bound RuntimeSession
dispatch and TransitionRecorder. Each provider run must use a fresh output
directory and its own process.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from task_env.artifacts import ExecutionSpec, FrameReference
from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1,
    StructuredActionRequestV1,
)
from task_env.diagnostics.tasks.c02b_r1_force_candidate import build_r1_force_candidate
from task_env.diagnostics.tasks.test_phase_ii_c02b_r1_typed_force import _candidate_bindings
from task_env.recorders import (
    RecorderConfig,
    TransitionRecorder,
    load_structured_control_records_h5,
    load_structured_training_actions_h5,
)
from task_env.runtime.sessions import control as control_sessions
from task_env.runtime.sessions.control import (
    ControlBinding,
    _r1_controller_state_from_publication,
    execute_plan_bound_r1_control_interval,
    materialize_control,
)
from task_env.trajectory.canonical.episode import EpisodeOutcomeV1, StructuredControlTransitionV1


PHASES = (
    ("open_at_reset_pose", 65, 1.0),
    ("close_free_space", 65, -1.0),
    ("open_and_approach_existing_peg", 240, 1.0),
    ("obstructed_close", 40, -1.0),
    ("force_hold", 10, -1.0),
    ("reopen", 65, 1.0),
)
PHASE_CODE = {name: index + 1 for index, (name, _count, _gripper) in enumerate(PHASES)}
FINAL_PHASE_CODE = len(PHASES) + 1
PEG_CENTER_WORLD_M = (0.58, 0.045, 0.522)
FULL_TRAVEL_M = 0.08
OPENING_ACCEPTANCE_M = 0.078
FORCE_ACTIVATION_N = max(0.5, 0.10 * 30.0)
FORCE_HOLD_SECONDS = 0.10
FORCE_HOLD_INTERVALS = 10
APPROACH_POSITION_TOLERANCE_M = 0.006
APPROACH_ROTATION_TOLERANCE_RAD = 0.035
# Source-kinematics solution for the existing peg at hand-local
# (0, +10.5 mm, +128.5 mm). Unlike the exploratory target, this posture's FK is
# itself the action target; the peg offset is not applied as an extra hand
# translation. The constrained solution keeps the target near the stable
# run_010 posture while avoiding a mismatched FK/action pose.
GRASP_TARGET_JOINTS_RAD = (
    -0.061750807549276365, 0.8861182377766594, -0.24073848566439934,
    -0.07121286643234488, 0.5939733439323666, 0.6801101893897122,
    -2.2423040597004724,
)


def _exclusive_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _identity_bytes(value: str) -> np.ndarray:
    return np.frombuffer(value.encode("utf-8"), dtype=np.uint8).copy()


def _frame(publication, entity_id: str, frame_id: str):
    rows = [item for item in publication.view.frames if item.frame.entity_id == entity_id and item.frame.frame_id == frame_id]
    if len(rows) != 1:
        raise ValueError(f"expected one typed Frame {entity_id}/{frame_id}")
    return rows[0]


def _force(publication):
    rows = [item for item in publication.view.actuator_forces if item.entity_id == "panda-main" and item.actuator_id == "actuator8"]
    if len(rows) != 1 or not rows[0].valid:
        raise ValueError("required Panda actuator8 force is missing or invalid")
    return rows[0]


def _observation(candidate, publication, feedback, memory, readiness, phase_code):
    view = publication.view
    force = _force(publication)
    positions = {f"{item.entity_id}/{item.joint_id}": item.position for item in view.joints}
    velocities = {f"{item.entity_id}/{item.joint_id}": item.velocity for item in view.joints}
    joint_order = tuple(candidate.source.joints)
    if set(positions) != set(joint_order) or set(velocities) != set(joint_order):
        raise ValueError("typed Joint state does not exactly cover the candidate source")
    hand = _frame(publication, "panda-main", "hand").pose_world
    boundary = view.boundary
    return {
        "state": {
            "joint_position": np.asarray([positions[name] for name in joint_order], dtype=np.float64),
            "joint_velocity": np.asarray([velocities[name] for name in joint_order], dtype=np.float64),
            "hand_pose_world": np.asarray((*hand.position, *hand.quaternion_wxyz), dtype=np.float64),
            "raw_force_signed_N": np.asarray([force.signed_value], dtype=np.float64),
            "canonical_closing_force_N": np.asarray([feedback.gripper.closing_force_N], dtype=np.float64),
            "gripper_feedback": np.asarray([
                feedback.gripper.opening_m,
                feedback.gripper.closing_force_N,
            ], dtype=np.float64),
            "actuator_control": np.asarray([force.actuator_control_value], dtype=np.float64),
            "force_clock": np.asarray([
                force.sample_sequence,
                force.native_step_index,
                force.native_sample_time_s,
                force.evaluation_control_step,
                force.evaluation_simulation_time_s,
            ], dtype=np.float64),
            "controller_status": np.asarray([
                memory.force_mode_active if memory is not None else False,
                memory.force_mode_initialized if memory is not None else False,
                readiness is not None,
                readiness.gripper.close_ready if readiness is not None else False,
            ], dtype=np.uint8),
            "readiness_values": np.asarray([
                feedback.gripper.closing_force_N,
                candidate.controller.gripper_config.force_limit_N,
                (candidate.controller.gripper_config.force_limit_N - feedback.gripper.closing_force_N),
            ], dtype=np.float64),
            "phase_code": np.asarray([phase_code], dtype=np.int16),
            "identity": {
                "artifact_identity": _identity_bytes(candidate.artifact.identity_hash),
                "scene_identity": _identity_bytes(candidate.scene.identity_hash),
                "source_closure_digest": _identity_bytes(candidate.source.source_closure_digest),
                "controller_identity": _identity_bytes(candidate.controller.identity),
                "tcp_identity": _identity_bytes(candidate.controller.tcp_profile_identity),
                "plan_identity": _identity_bytes(candidate.plan.identity_hash),
                "episode_id": _identity_bytes(boundary.episode_id),
                "reset_sample_id": _identity_bytes(boundary.reset_sample_id),
                "provider_materialization_id": _identity_bytes(boundary.provider_materialization_id),
                "boundary_id": _identity_bytes(boundary.boundary_id),
            },
            "boundary_clock": np.asarray([
                boundary.control_step,
                view.sample_clock.simulation_time_s,
                boundary.state_revision,
            ], dtype=np.float64),
        }
    }


def _request(candidate, pose, gripper_scalar):
    schema = candidate.plan.controller_bindings[0].action_schema
    request = StructuredActionRequestV1(
        "structured-action-request-v1",
        candidate.plan.scene_identity_hash,
        candidate.plan.identity_hash,
        (
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "arm", schema.schema_id,
                tuple(float(value) for value in (*pose[0], *pose[1])),
            ),
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "gripper", schema.schema_id,
                (float(gripper_scalar),),
            ),
        ),
    )
    request.validate()
    return request


def _structured_transition(candidate, request, canonical, target, acknowledgement):
    schema = candidate.plan.controller_bindings[0].action_schema
    components = tuple(schema.components)
    target_payload = target.to_mapping()
    applied_payload = acknowledgement.to_mapping()
    row = {
        "writer_id": candidate.writer_id,
        "action_schema_id": schema.schema_id,
        "components": components,
        "groups": (
            {"entity_id": "panda-main", "group_id": "arm", "action_components": components[:7]},
            {"entity_id": "panda-main", "group_id": "gripper", "action_components": components[7:]},
        ),
        "requested_action": canonical.requested.to_mapping(),
        "canonical_action": canonical.to_mapping(),
        "controller_target": {
            "schema_version": target.schema_version,
            "payload": target_payload,
            "identity_hash": target.identity_hash,
        },
        "applied_control": {
            "schema_version": acknowledgement.schema_version,
            "payload": applied_payload,
            "target_hash": acknowledgement.target_hash,
        },
    }
    transition = StructuredControlTransitionV1.from_mapping({
        "schema_version": "structured-control-transition-v1",
        "request": request.to_mapping(),
        "writer_controls": [row],
    })
    transition.validate()
    return transition


def _quat_error(a, b) -> float:
    qa = np.asarray(a, dtype=np.float64)
    qb = np.asarray(b, dtype=np.float64)
    qa /= np.linalg.norm(qa)
    qb /= np.linalg.norm(qb)
    return 2.0 * math.acos(float(np.clip(abs(np.dot(qa, qb)), -1.0, 1.0)))


def _events_and_outcome(episode_id: str, final_boundary: int):
    from task_env.trajectory.canonical.episode import BoundaryEventV1

    outcome = EpisodeOutcomeV1(
        "episode-outcome-v1", episode_id, final_boundary, "external_stop",
        False, True, True, None, None,
    )
    event = BoundaryEventV1(
        "boundary-event-v1", episode_id, final_boundary, 0,
        f"{episode_id}:episode-ended:{final_boundary}", "episode_ended", "diagnostic",
        {
            "end_reason": "external_stop", "terminated": False,
            "truncated": True, "bootstrap_allowed": True,
        },
    )
    outcome.validate()
    event.validate()
    return event, outcome


def _readback(path: Path, recorder, observations, transitions, candidate):
    import h5py

    loaded = load_structured_control_records_h5(path)
    projected = load_structured_training_actions_h5(path)
    expected_t = len(transitions)
    if loaded["transition_count"] != expected_t or loaded["observation_count"] != expected_t + 1:
        raise ValueError("Generic H5 v3 reader returned inconsistent T/T+1")
    if len(loaded["structured_controls"]) != expected_t:
        raise ValueError("Generic H5 v3 reader lost structured transitions")
    expected_actions = tuple(tuple(float(v) for v in row["action"]) for row in transitions)
    if projected != expected_actions:
        raise ValueError("Generic H5 action projection differs from actual R1 canonical actions")
    for index, (loaded_control, expected_control) in enumerate(zip(
        loaded["structured_controls"], recorder.frozen.structured_controls, strict=True,
    )):
        if loaded_control != expected_control:
            raise ValueError(f"structured H5 transition {index} differs from the Recorder input")
    with h5py.File(path, "r") as handle:
        if int(handle.attrs["transition_count"]) != expected_t:
            raise ValueError("on-disk transition_count differs from T")
        if int(handle.attrs["observation_count"]) != expected_t + 1:
            raise ValueError("on-disk observation_count differs from T+1")
        disk_positions = np.asarray(handle["obs/state/joint_position"])
        disk_hand = np.asarray(handle["obs/state/hand_pose_world"])
        disk_force = np.asarray(handle["obs/state/raw_force_signed_N"])
        disk_canonical = np.asarray(handle["obs/state/canonical_closing_force_N"])
        disk_gripper_feedback = np.asarray(handle["obs/state/gripper_feedback"])
        disk_clock = np.asarray(handle["obs/state/boundary_clock"])
        disk_native = np.asarray(handle["obs/state/force_clock"])
        disk_boundary_ids = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/boundary_id"]]
        disk_artifact = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/artifact_identity"]]
        disk_scene = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/scene_identity"]]
        disk_source = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/source_closure_digest"]]
        disk_controller = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/controller_identity"]]
        disk_tcp = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/tcp_identity"]]
        disk_plan = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/plan_identity"]]
        disk_episode = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/episode_id"]]
        disk_reset = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/reset_sample_id"]]
        disk_materialization = [bytes(row.tolist()).decode("utf-8") for row in handle["obs/state/identity/provider_materialization_id"]]

    expected_positions = np.stack([obs["state"]["joint_position"] for obs in observations])
    expected_hand = np.stack([obs["state"]["hand_pose_world"] for obs in observations])
    expected_force = np.stack([obs["state"]["raw_force_signed_N"] for obs in observations])
    expected_canonical = np.stack([obs["state"]["canonical_closing_force_N"] for obs in observations])
    expected_gripper_feedback = np.stack([obs["state"]["gripper_feedback"] for obs in observations])
    expected_clock = np.stack([obs["state"]["boundary_clock"] for obs in observations])
    expected_native = np.stack([obs["state"]["force_clock"] for obs in observations])
    for actual, expected in ((disk_positions, expected_positions), (disk_hand, expected_hand),
                             (disk_force, expected_force), (disk_canonical, expected_canonical),
                             (disk_gripper_feedback, expected_gripper_feedback),
                             (disk_clock, expected_clock), (disk_native, expected_native)):
        np.testing.assert_array_equal(actual, expected)
    expected_boundaries = [bytes(obs["state"]["identity"]["boundary_id"].tolist()).decode("utf-8") for obs in observations]
    if disk_boundary_ids != expected_boundaries:
        raise ValueError("H5 boundary identity readback differs from the in-memory publications")
    static_identities = {
        "artifact": (disk_artifact, candidate.artifact.identity_hash),
        "scene": (disk_scene, candidate.scene.identity_hash),
        "source": (disk_source, candidate.source.source_closure_digest),
        "controller": (disk_controller, candidate.controller.identity),
        "tcp": (disk_tcp, candidate.controller.tcp_profile_identity),
        "plan": (disk_plan, candidate.plan.identity_hash),
    }
    for name, (values, expected) in static_identities.items():
        if set(values) != {expected}:
            raise ValueError(f"H5 {name} identity readback mismatch")
    if len(set(disk_episode)) != 1 or len(set(disk_reset)) != 1 or len(set(disk_materialization)) != 1:
        raise ValueError("H5 episode/reset/materialization identity changes inside one trajectory")
    if loaded["outcome"].final_boundary != expected_t or loaded["outcome"].end_reason != "external_stop":
        raise ValueError("H5 outcome/final boundary mismatch")
    return {
        "reader": "load_structured_control_records_h5",
        "action_reader": "load_structured_training_actions_h5",
        "transition_count": loaded["transition_count"],
        "observation_count": loaded["observation_count"],
        "state_leaf_shapes": {
            "joint_position": list(disk_positions.shape),
            "hand_pose_world": list(disk_hand.shape),
            "raw_force_signed_N": list(disk_force.shape),
            "canonical_closing_force_N": list(disk_canonical.shape),
            "gripper_feedback": list(disk_gripper_feedback.shape),
            "boundary_clock": list(disk_clock.shape),
            "force_clock": list(disk_native.shape),
        },
        "boundary_id_count": len(disk_boundary_ids),
        "identity_sets": {name: sorted(set(values)) for name, (values, _expected) in static_identities.items()},
        "episode_id": disk_episode[0],
        "reset_sample_id": disk_reset[0],
        "provider_materialization_id": disk_materialization[0],
        "request_target_ack_roundtrip": True,
        "numeric_state_roundtrip": True,
    }


def run(provider: str, output_dir: Path) -> dict:
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    candidate = build_r1_force_candidate(root / "candidate")
    scene = candidate.scene
    grasp_target_matrix, _ = candidate.kinematics.fk_jacobian(np.asarray(GRASP_TARGET_JOINTS_RAD, dtype=np.float64))
    peg_center = np.asarray(PEG_CENTER_WORLD_M, dtype=np.float64)
    peg_center_hand_local = np.asarray((0.0, 0.0105, 0.1285), dtype=np.float64)
    hand_target_world = grasp_target_matrix[:3, 3].copy()
    if (np.linalg.norm(grasp_target_matrix[:3, :3].T @ (peg_center - hand_target_world) - peg_center_hand_local) > 1.0e-8):
        raise ValueError("source-derived grasp posture does not place the existing peg on the hand-local finger axis")
    grasp_reference_pose = candidate.kinematics.pose(np.asarray(GRASP_TARGET_JOINTS_RAD, dtype=np.float64))
    grasp_pose = (tuple(float(v) for v in hand_target_world), tuple(grasp_reference_pose.quaternion_wxyz))
    joint_bindings, frame_bindings = _candidate_bindings(scene, candidate.source)
    execution = ExecutionSpec(provider, "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict")
    binding = ControlBinding("panda-main/gripper", FULL_TRAVEL_M)
    schema = candidate.plan.controller_bindings[0].action_schema
    config = {
        "schema": "c02b-r1-structured-behavior-probe-v1",
        "provider": provider,
        "backend": "cpu",
        "execution": execution.to_mapping(),
        "seed": 31,
        "outer_frequency_hz": 100,
        "physics_dt_s": 0.002,
        "native_steps_per_interval": 5,
        "gripper_full_travel_m": FULL_TRAVEL_M,
        "opening_step_m_per_10ms": candidate.controller.gripper_config.opening_step_m,
        "force_limit_N": candidate.controller.gripper_config.force_limit_N,
        "force_deadband_N": candidate.controller.gripper_config.force_deadband_N,
        "force_adjust_step_m": candidate.controller.gripper_config.force_adjust_step_m,
        "force_mode_activation_N": FORCE_ACTIVATION_N,
        "force_hold_duration_s": FORCE_HOLD_SECONDS,
        "force_hold_intervals": FORCE_HOLD_INTERVALS,
        "phase_schedule": [{"name": name, "intervals": count, "gripper_request": action} for name, count, action in PHASES],
        "approach_target_world_hand_origin_m": list(hand_target_world),
        "approach_target_arm_joints_rad": list(GRASP_TARGET_JOINTS_RAD),
        "approach_trajectory": "linear_joint_reference_then_constant_source_derived_FK_pose_settle",
        "approach_intervals": 240,
        "approach_ramp_intervals": 120,
        "approach_settle_intervals": 120,
        "resolved_approach_pose_world": {
            "position_m": list(grasp_pose[0]),
            "quaternion_wxyz": list(grasp_pose[1]),
            "peg_center_in_hand_local_m": peg_center_hand_local.tolist(),
        },
        "approach_posture_provenance": "offline constrained FK solution on this candidate source; FK places existing peg at hand-local [0, 0.0105, 0.1285] m and is the arm action target",
        "existing_obstacle": {
            "entity_id": "square-peg-instance", "center_world_m": list(PEG_CENTER_WORLD_M),
            "box_half_size_m": [0.016, 0.016, 0.06],
        },
        "approach_failure_criteria": {
            "position_error_max_m": APPROACH_POSITION_TOLERANCE_M,
            "rotation_error_max_rad": APPROACH_ROTATION_TOLERANCE_RAD,
            "source_values": ["ActionConfig.ik_position_deadband", "ActionConfig.ik_rotation_deadband"],
        },
        "behavior_failure_criteria": {
            "opening_min_at_open_endpoints_m": OPENING_ACCEPTANCE_M,
            "free_close_force_mode_must_remain_inactive": True,
            "obstructed_close_must_activate_force_mode": True,
            "hold_force_mode_active_each_interval": FORCE_HOLD_INTERVALS,
            "reopen_must_clear_force_mode": True,
            "reopen_min_opening_m": OPENING_ACCEPTANCE_M,
            "native_sample_and_index_delta_per_interval": 5,
        },
    }
    _exclusive_json(root / "predeclared_probe.json", config)

    if provider == "geophys":
        provider_build = control_sessions.provider_build_identity("geophys")
    else:
        provider_build, runtime_version = control_sessions._mujoco_r1_build_identity()
        provider_build["runtime_version"] = runtime_version
    identities = {
        "artifact_identity": candidate.artifact.identity_hash,
        "scene_identity": scene.identity_hash,
        "source_closure_digest": candidate.source.source_closure_digest,
        "source_xml_sha256": candidate.controller.source_xml_sha256,
        "controller_identity": candidate.controller.identity,
        "kinematics_identity": candidate.controller.source_kinematics_identity,
        "tcp_identity": candidate.controller.tcp_profile_identity,
        "plan_identity": candidate.plan.identity_hash,
        "reset_sample_id": candidate.reset_plan.reset_sample.sample_id,
    }
    session = materialize_control(
        candidate.artifact, execution, source=candidate.source, binding=binding,
        controller_binding_plan=candidate.plan, controller_profile=candidate.controller,
    )
    recorder = TransitionRecorder(RecorderConfig(schema_version="v3", max_transitions=500))
    rows = []
    observations = []
    transitions = []
    criteria = {"checks": {}, "passed": False}
    current_phase_index = 0
    stage_boundaries: dict[str, tuple[int, int]] = {}
    try:
        realized = session.reset_plan(candidate.reset_plan)
        initial_state = session.snapshot()
        initial_publication = session.snapshot_v2(
            scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            requirements=candidate.plan.controller_bindings[0].feedback_requirements,
        )
        initial_force = _force(initial_publication)
        initial_feedback = session.control_feedback(initial_state, actuator_force=initial_force)
        initial_hand = _frame(initial_publication, "panda-main", "hand").pose_world
        reset_pose = (tuple(initial_hand.position), tuple(initial_hand.quaternion_wxyz))
        peg_pose = grasp_pose
        episode_id = initial_publication.view.boundary.episode_id
        if realized.reset_sample_id != initial_publication.view.boundary.reset_sample_id:
            raise ValueError("materialized reset identity differs from initial typed publication")

        phase_codes = {name: PHASE_CODE[name] for name, _count, _action in PHASES}
        record_metadata = {
            "env_metadata": {
                "env_name": "c02b-r1-structured-behavior-probe",
                "task_name": candidate.artifact.task_id,
                "task_version": candidate.artifact.artifact_version,
                "scene_uid": candidate.artifact.scene_id,
                "agent_uids": ("panda-main",),
                "physics_dt": 0.002,
                "control_substeps": 5,
                "control_frequency": 100,
                "action_schema": {
                    "schema_id": schema.schema_id,
                    "schema_version": schema.schema_version,
                    "controller_kind": schema.controller_kind,
                    "reference": schema.reference,
                    "rotation_representation": schema.rotation_representation,
                    "components": tuple(schema.components),
                },
                "observation_schema": {"leaf_specs": []},
                "universal_action_schema": {
                    "version": "panda-universal-action-v1", "dimension": 8,
                    "components": tuple(schema.components),
                },
            },
            "universal_action_schema": {
                "version": "panda-universal-action-v1", "dimension": 8,
                "components": tuple(schema.components),
            },
            "resolved_config": {"r1_probe": {"identity": identities, "provider_build": provider_build, "phase_code": phase_codes, "final_phase_code": FINAL_PHASE_CODE, "declared_config": config}},
        }
        initial_obs = _observation(candidate, initial_publication, initial_feedback, None, None, PHASE_CODE[PHASES[0][0]])
        recorder.begin_episode(initial_obs, {"seed": 31, "reset_sample_id": realized.reset_sample_id}, record_metadata)
        observations.append(initial_obs)

        global_index = 0
        current_publication = initial_publication
        current_state = initial_state
        current_feedback = initial_feedback
        for phase_index, (phase_name, count, grip_scalar) in enumerate(PHASES):
            current_phase_index = phase_index
            start_boundary = current_state.control_step
            stage_boundaries[phase_name] = (start_boundary, start_boundary + count)
            pose = reset_pose if phase_name in {"open_at_reset_pose", "close_free_space"} else peg_pose
            arm_start_q = np.asarray([
                current_state.joint_position[f"panda-main/joint{index}"]
                for index in range(1, 8)
            ], dtype=np.float64)
            for phase_interval in range(count):
                phase_code = PHASE_CODE[phase_name]
                force_before = _force(current_publication)
                if not force_before.valid:
                    raise ValueError("required force feedback became invalid before R1 compute")
                if force_before.evaluation_boundary_id != current_publication.view.boundary.boundary_id:
                    raise ValueError("required force feedback is not bound to the current evaluation boundary")
                interval_pose = pose
                if phase_name == "open_and_approach_existing_peg" and phase_interval < 120:
                    alpha = (phase_interval + 1) / 120
                    q_reference = arm_start_q + alpha * (np.asarray(GRASP_TARGET_JOINTS_RAD, dtype=np.float64) - arm_start_q)
                    reference_pose = candidate.kinematics.pose(q_reference)
                    interval_pose = (tuple(reference_pose.position), tuple(reference_pose.quaternion_wxyz))
                request = _request(candidate, interval_pose, grip_scalar)
                consumed_force_expected = force_before.signed_value
                consumed_boundary_id = current_publication.view.boundary.boundary_id
                canonical, target, acknowledgement, next_state, next_publication, consumed_feedback = execute_plan_bound_r1_control_interval(
                    session, candidate.controller, candidate.plan, request, current_publication,
                    scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
                )
                if consumed_feedback.gripper.closing_force_N != max(0.0, -consumed_force_expected):
                    raise ValueError("R1 consumed feedback differs from the current signed-force publication")
                if acknowledgement.target_hash != target.identity_hash:
                    raise ValueError("applied acknowledgement does not match this Controller target")
                if {(g.entity_id, g.group_id) for g in request.groups} != {
                    ("panda-main", "arm"), ("panda-main", "gripper"),
                }:
                    raise ValueError("structured request did not cover both exact Panda groups")
                next_force = _force(next_publication)
                if next_force.sample_sequence - force_before.sample_sequence != 5:
                    raise ValueError("native sample sequence did not advance by five real steps")
                if next_force.native_step_index - force_before.native_step_index != 5:
                    raise ValueError("native force sample index did not advance by five steps")
                if next_state.control_step != current_state.control_step + 1:
                    raise ValueError("control boundary did not advance exactly one interval")
                if abs(next_state.simulation_time - (current_state.simulation_time + 0.01)) > 1.0e-12:
                    raise ValueError("control clock did not advance by exactly 10 ms")
                if abs(next_force.native_sample_time_s - (next_force.native_step_index * 0.002 - 0.002)) > 1.0e-12:
                    raise ValueError("completed-step force phase/time does not name the last pre-integration sample")
                if next_force.evaluation_control_step != next_state.control_step or abs(next_force.evaluation_simulation_time_s - next_state.simulation_time) > 1.0e-12:
                    raise ValueError("typed force publication and next state boundary differ")

                structured = _structured_transition(candidate, request, canonical, target, acknowledgement)
                memory = candidate.controller.memory()
                next_feedback = session.control_feedback(next_state, actuator_force=next_force)
                readiness_state = _r1_controller_state_from_publication(next_publication, scene)
                readiness = candidate.controller.readiness(readiness_state, next_feedback)
                phase_code_next = phase_code
                if phase_interval == count - 1:
                    phase_code_next = (
                        PHASE_CODE[PHASES[phase_index + 1][0]]
                        if phase_index + 1 < len(PHASES)
                        else FINAL_PHASE_CODE
                    )
                next_obs = _observation(candidate, next_publication, next_feedback, memory, readiness, phase_code_next)
                action_values = tuple(float(value) for value in canonical.requested.values)
                recorder.append_transition(
                    np.asarray(action_values, dtype=np.float32),
                    np.asarray(action_values, dtype=np.float32),
                    next_obs, 0.0, False, False, False,
                    {"phase": phase_name}, structured_control=structured,
                )
                transitions.append({
                    "index": global_index,
                    "phase": phase_name,
                    "action": list(canonical.requested.values),
                    "source_boundary_id": consumed_boundary_id,
                    "source_raw_force": force_before.to_mapping(),
                    "consumed_feedback": consumed_feedback.to_mapping(),
                    "request": request.to_mapping(),
                    "canonical_action": canonical.to_mapping(),
                    "target": target.to_mapping(),
                    "target_hash": target.identity_hash,
                    "acknowledgement": acknowledgement.to_mapping(),
                    "next_boundary": next_publication.view.boundary.to_mapping(),
                    "next_raw_force": next_force.to_mapping(),
                    "next_state": {
                        "control_step": next_state.control_step,
                        "simulation_time_s": next_state.simulation_time,
                        "joint_position": dict(next_state.joint_position),
                        "joint_velocity": dict(next_state.joint_velocity),
                        "hand_pose_world": _frame(next_publication, "panda-main", "hand").pose_world.to_mapping(),
                    },
                    "controller_memory_after_compute": memory.to_mapping(),
                    "readiness_at_next_boundary": readiness.to_mapping(),
                    "native_steps_completed_evidence": {
                        "sample_sequence_delta": next_force.sample_sequence - force_before.sample_sequence,
                        "native_step_index_delta": next_force.native_step_index - force_before.native_step_index,
                        "clock_delta_s": next_state.simulation_time - current_state.simulation_time,
                    },
                })
                observations.append(next_obs)
                rows.append({
                    "index": global_index,
                    "phase": phase_name,
                    "signed_raw_force_N": force_before.signed_value,
                    "canonical_closing_force_N": consumed_feedback.gripper.closing_force_N,
                    "opening_m": consumed_feedback.gripper.opening_m,
                    "force_mode_active_after_compute": memory.force_mode_active,
                    "force_initialized_after_compute": memory.force_mode_initialized,
                    "readiness_at_next_boundary": readiness.gripper.close_ready,
                    "readiness_force_N": readiness.gripper.closing_force_N,
                    "readiness_error_N": readiness.gripper.force_error_N,
                    "servo_opening_target_m": target.gripper.servo_opening_m,
                    "applied_opening_m": acknowledgement.gripper_servo_opening_m,
                    "next_opening_m": next_feedback.gripper.opening_m,
                    "control_step": next_state.control_step,
                    "simulation_time_s": next_state.simulation_time,
                    "native_sample_index": next_force.native_step_index,
                    "native_sample_time_s": next_force.native_sample_time_s,
                    "source_boundary_id": consumed_boundary_id,
                    "next_boundary_id": next_publication.view.boundary.boundary_id,
                })
                global_index += 1
                current_state, current_publication, current_feedback = next_state, next_publication, next_feedback

        final_state = current_state
        final_publication = current_publication
        final_force = _force(final_publication)
        final_feedback = session.control_feedback(final_state, actuator_force=final_force)
        final_readiness_state = _r1_controller_state_from_publication(final_publication, scene)
        final_readiness = candidate.controller.readiness(final_readiness_state, final_feedback)
        final_memory = candidate.controller.memory()
        if recorder.observation_count != recorder.transition_count + 1:
            raise ValueError("Recorder lost the final T+1 state boundary")
        event, outcome = _events_and_outcome(episode_id, recorder.transition_count)
        recorder.add_boundary_event(event)
        recorder.end_episode("external_stop", outcome=outcome)
        h5_path = recorder.save_h5(root, "single_panda_structured_r1_v3.h5")

        # Predeclared outcome checks. All thresholds above were fixed before
        # provider execution and derive from the resolved R1/arm configuration.
        def phase_rows(name):
            return [item for item in rows if item["phase"] == name]

        open_rows = phase_rows("open_at_reset_pose")
        free_close_rows = phase_rows("close_free_space")
        approach_rows = phase_rows("open_and_approach_existing_peg")
        obstacle_rows = phase_rows("obstructed_close")
        hold_rows = phase_rows("force_hold")
        reopen_rows = phase_rows("reopen")
        final_hand = _frame(final_publication, "panda-main", "hand").pose_world
        pos_error = float(np.linalg.norm(np.asarray(final_hand.position) - hand_target_world))
        approach_hand = _frame(
            next((item for item in [current_publication] if item is not None), final_publication),
            "panda-main", "hand",
        ).pose_world
        # The 60-interval approach endpoint is retained in the interval rows.
        approach_endpoint_row = transitions[stage_boundaries["open_and_approach_existing_peg"][1] - 1]
        approach_endpoint_pose = approach_endpoint_row["next_state"]["hand_pose_world"]
        approach_pos_error = float(np.linalg.norm(np.asarray(approach_endpoint_pose["position"]) - hand_target_world))
        approach_rot_error = _quat_error(approach_endpoint_pose["quaternion_wxyz"], grasp_pose[1])
        activation = next((item for item in obstacle_rows if item["force_mode_active_after_compute"]), None)
        activation_feedback = None if activation is None else activation["canonical_closing_force_N"]
        force_influence = None
        if activation is not None:
            transition_row = transitions[activation["index"]]
            consumed_opening = transition_row["consumed_feedback"]["gripper"]["opening_m"]
            measured_force = transition_row["consumed_feedback"]["gripper"]["closing_force_N"]
            config_gripper = candidate.controller.gripper_config
            stiffness = candidate.source.config.action.gripper_position_stiffness_N_per_m
            correction = config_gripper.force_adjust_step_m if config_gripper.force_limit_N - measured_force > config_gripper.force_deadband_N else 0.0
            expected_servo = float(np.clip(consumed_opening - config_gripper.force_limit_N / stiffness - correction, 0.0, FULL_TRAVEL_M))
            force_influence = {
                "activation_force_N": measured_force,
                "activation_threshold_N": FORCE_ACTIVATION_N,
                "servo_opening_target_m": transition_row["target"]["gripper"]["servo_opening_m"],
                "config_derived_force_mode_servo_target_m": expected_servo,
                "matches_controller_law": math.isclose(transition_row["target"]["gripper"]["servo_opening_m"], expected_servo, rel_tol=0.0, abs_tol=1.0e-12),
            }
        criteria["checks"] = {
            "initial_reset_force_valid": bool(initial_force.valid and initial_force.sample_phase == "reset_forward"),
            "open_endpoint_reached": bool(open_rows and open_rows[-1]["next_opening_m"] >= OPENING_ACCEPTANCE_M),
            "free_close_reached_closed_without_force_mode": bool(free_close_rows and free_close_rows[-1]["next_opening_m"] <= 0.002 and not any(item["force_mode_active_after_compute"] for item in free_close_rows)),
            "peg_approach_position_tolerance": approach_pos_error <= APPROACH_POSITION_TOLERANCE_M,
            "peg_approach_rotation_tolerance": approach_rot_error <= APPROACH_ROTATION_TOLERANCE_RAD,
            "obstructed_close_force_mode_activated": activation is not None and activation_feedback is not None and activation_feedback >= FORCE_ACTIVATION_N,
            "nonzero_force_changes_r1_servo_target": bool(force_influence and force_influence["matches_controller_law"]),
            "force_hold_active_for_all_intervals": bool(len(hold_rows) == FORCE_HOLD_INTERVALS and all(item["force_mode_active_after_compute"] for item in hold_rows)),
            "force_hold_uses_finite_feedback_below_limit": bool(len(hold_rows) == FORCE_HOLD_INTERVALS and all(math.isfinite(item["canonical_closing_force_N"]) and 0.0 <= item["canonical_closing_force_N"] <= candidate.controller.gripper_config.force_limit_N for item in hold_rows)),
            "reopen_clears_force_mode": bool(reopen_rows and not reopen_rows[-1]["force_mode_active_after_compute"]),
            "reopen_endpoint_reached": bool(reopen_rows and reopen_rows[-1]["next_opening_m"] >= OPENING_ACCEPTANCE_M),
            "all_requests_cover_both_groups": all({(g.entity_id, g.group_id) for g in StructuredActionRequestV1.from_mapping(row["request"]).groups} == {("panda-main", "arm"), ("panda-main", "gripper")} for row in transitions),
            "all_target_ack_pairs_match": all(row["acknowledgement"]["target_hash"] == row["target_hash"] for row in transitions),
            "five_native_steps_each_interval": all(row["native_steps_completed_evidence"]["sample_sequence_delta"] == 5 and row["native_steps_completed_evidence"]["native_step_index_delta"] == 5 for row in transitions),
            "continuous_clock_and_boundary": all(row["next_state"]["control_step"] == index + 1 and abs(row["next_state"]["simulation_time_s"] - (index + 1) * 0.01) <= 1.0e-12 for index, row in enumerate(transitions)),
            "force_mode_cleared_after_reopen": not final_memory.force_mode_active,
        }
        criteria["approach"] = {
            "end_position_error_m": approach_pos_error,
            "end_rotation_error_rad": approach_rot_error,
            "tolerance_position_m": APPROACH_POSITION_TOLERANCE_M,
            "tolerance_rotation_rad": APPROACH_ROTATION_TOLERANCE_RAD,
            "target_world_m": list(hand_target_world),
            "peg_center_world_m": list(PEG_CENTER_WORLD_M),
        }
        criteria["force_influence"] = force_influence
        criteria["readiness"] = {
            "ready_true_boundaries": sum(item["readiness_at_next_boundary"] for item in rows),
            "total_post_compute_boundaries": len(rows),
            "final_ready": final_readiness.gripper.close_ready,
            "final_force_mode": final_memory.force_mode_active,
            "final_closing_force_N": final_feedback.gripper.closing_force_N,
            "final_opening_m": final_feedback.gripper.opening_m,
            "interpretation": "readiness is recorded separately from physical motion and task predicates",
        }
        criteria["passed"] = all(criteria["checks"].values())
        roundtrip = _readback(h5_path, recorder, observations, transitions, candidate)
        result = {
            "schema": "c02b-r1-structured-behavior-result-v1",
            "status": "PASS" if criteria["passed"] else "FAIL",
            "provider": provider,
            "provider_build": provider_build,
            "execution": execution.to_mapping(),
            "identities": identities,
            "episode_id": episode_id,
            "reset_sample_id": realized.reset_sample_id,
            "provider_materialization_id": initial_publication.view.boundary.provider_materialization_id,
            "reset_force": initial_force.to_mapping(),
            "phase_boundaries": stage_boundaries,
            "phase_counts": {name: count for name, count, _action in PHASES},
            "criteria": criteria,
            "transition_count": recorder.transition_count,
            "observation_count": recorder.observation_count,
            "outcome": outcome.to_mapping(),
            "h5_file": h5_path.name,
            "h5_sha256": __import__("hashlib").sha256(h5_path.read_bytes()).hexdigest(),
            "same_file_readback": roundtrip,
            "transition_rows": transitions,
            "boundary_rows": [
                {"control_step": int(obs["state"]["boundary_clock"][0]),
                 "simulation_time_s": float(obs["state"]["boundary_clock"][1]),
                 "native_sample_index": int(obs["state"]["force_clock"][1]),
                 "native_sample_time_s": float(obs["state"]["force_clock"][2]),
                 "signed_raw_force_N": float(obs["state"]["raw_force_signed_N"][0]),
                 "canonical_closing_force_N": float(obs["state"]["canonical_closing_force_N"][0]),
                 "opening_m": float(obs["state"]["gripper_feedback"][0]),
                 "phase_code": int(obs["state"]["phase_code"][0])}
                for obs in observations
            ],
        }
        _exclusive_json(root / "result.json", result)
        return result
    except BaseException as exc:
        try:
            failed_clock = session.snapshot()
            failed_boundary = {
                "control_step": failed_clock.control_step,
                "simulation_time_s": failed_clock.simulation_time,
            }
        except BaseException as snapshot_exc:
            failed_boundary = {"unavailable": type(snapshot_exc).__name__, "detail": str(snapshot_exc)}
        _exclusive_json(root / "failure.json", {
            "schema": "c02b-r1-structured-behavior-failure-v1",
            "provider": provider,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "phase_index": current_phase_index,
            "completed_intervals": len(rows),
            "partial_recorder_transition_count": recorder.transition_count,
            "partial_recorder_observation_count": recorder.observation_count,
            "runtime_boundary_after_failure": failed_boundary,
            "completed_transition_rows": transitions,
            "completed_behavior_rows": rows,
            "candidate_identities": identities,
            "provider_build": provider_build,
        })
        raise
    finally:
        session.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True)
    parser.add_argument("--output", type=Path, required=True, help="fresh, unused Evidence directory")
    args = parser.parse_args(argv)
    result = run(args.provider, args.output)
    print(json.dumps({"status": result["status"], "provider": result["provider"], "output": str(args.output.resolve()), "criteria": result["criteria"]["checks"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
