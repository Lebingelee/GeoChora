"""Run the frozen DG02 formal cell through the actual Core Position route."""

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
from typing import Mapping

import numpy as np


CORE = Path(__file__).resolve().parents[3]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _verify(plan_path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    plan_hash = hashlib.sha256(raw).hexdigest()
    if plan_hash != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("DG02 formal Core N2 plan SHA-256 mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-core-n2-plan-v1":
        raise ValueError("unsupported DG02 formal Core N2 plan schema")
    formal_classification = (
        "actual Core SelectedReferenceEnv PositionServoV1; source-bound GeoPhys/USD; "
        "formal bounded diagnostic, not qualification"
    )
    tracking_probe_classification = (
        "actual Core SelectedReferenceEnv PositionServoV1; source-bound GeoPhys/USD; "
        "bounded tracking probe, not a formal cell or qualification"
    )
    classification = plan.get("classification")
    if classification not in {formal_classification, tracking_probe_classification}:
        raise ValueError("unsupported Core N2 plan classification")
    if classification == tracking_probe_classification:
        oracle = plan["oracle"]
        limits = plan["limits"]
        expected_steps = (
            int(oracle["episode_count"])
            * int(oracle["control_intervals_per_episode"])
            * int(oracle["control_substeps"])
        )
        if (
            int(oracle["episode_count"]) != 1
            or int(oracle["control_intervals_per_episode"]) != 100
            or int(oracle["horizon"]) != 100
            or int(plan["source"]["candidate_horizon"]) != 100
            or expected_steps != 500
            or int(limits["physics_steps_reserved"]) != expected_steps
            or expected_steps > int(limits["per_probe_steps_max"])
            or int(limits["physics_steps_before"]) + expected_steps
            > int(limits["probe_physics_steps_max"])
        ):
            raise ValueError("DG02 tracking probe exceeds or changes its frozen 500-step envelope")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"formal Core N2 code changed after plan freeze: {path}")
    for label, row in plan["source"].items():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            path = Path(row["path"]).resolve(strict=True)
            if _sha(path) != row["sha256"]:
                raise ValueError(f"formal Core N2 frozen source changed after plan freeze: {label}")
    identity = plan["input_identity"]
    for repo_key, head_key, branch_key in (
        ("core_worktree", "core_input_head", "core_branch"),
        ("provider_worktree", "provider_input_head", "provider_branch"),
    ):
        repo = Path(identity[repo_key]).resolve(strict=True)
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if head != identity[head_key] or branch != identity[branch_key]:
            raise ValueError(f"formal Core N2 {repo_key} branch/HEAD changed after plan freeze")
    return plan, plan_hash


def _finite(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"formal Core N2 {label} contains a non-finite value")
    return number


def _joint_values(env) -> tuple[dict[str, float], dict[str, float]]:
    positions: dict[str, float] = {}
    velocities: dict[str, float] = {}
    for item in env.typed_state.view.joints:
        if item.entity_id != "panda-main":
            continue
        position = np.asarray(item.position, dtype=np.float64).reshape(-1)
        velocity = np.asarray(item.velocity, dtype=np.float64).reshape(-1)
        if position.size != 1 or velocity.size != 1:
            raise ValueError(f"expected scalar Panda joint state for {item.joint_id}")
        positions[str(item.joint_id)] = _finite(position[0], f"{item.joint_id}.position")
        velocities[str(item.joint_id)] = _finite(velocity[0], f"{item.joint_id}.velocity")
    required = {*(f"joint{index}" for index in range(1, 8)), "finger_joint1", "finger_joint2"}
    if set(positions) != required or set(velocities) != required:
        raise ValueError("typed Core state does not expose the exact seven arm and two finger joints")
    return positions, velocities


def _pose(pose) -> dict[str, list[float]]:
    return {
        "position_m": [_finite(value, "pose.position") for value in pose.position],
        "quaternion_wxyz": [_finite(value, "pose.quaternion_wxyz") for value in pose.quaternion_wxyz],
    }


def _frame_pose(env, entity_id: str, frame_id: str):
    matches = [
        item for item in env.typed_state.view.frames
        if item.frame.entity_id == entity_id and item.frame.frame_id == frame_id
    ]
    if len(matches) != 1:
        raise ValueError(f"typed Core state must contain exactly one {entity_id}/{frame_id} frame")
    return matches[0].pose_world


def _record_state(env) -> dict:
    state = env.state
    publication = env.typed_state.view
    boundary = publication.boundary
    clock = publication.sample_clock
    task_metrics = env.info.get("task_metrics")
    if not isinstance(task_metrics, Mapping):
        raise ValueError("actual public Task metrics are missing")
    required_metrics = {"raw_lift_height_predicate", "free_cube_center_z_m", "lifecycle_terminated"}
    if not required_metrics.issubset(task_metrics):
        raise ValueError("actual Task readout omitted required raw/lifecycle/free-cube facts")
    cube = state.pose_world.get("free-cube/free_cube")
    if cube is None:
        raise ValueError("public Core state lacks the free-cube pose")
    positions, velocities = _joint_values(env)
    boundary_mapping = boundary.to_mapping()
    boundary_hash = hashlib.sha256(json.dumps(
        boundary_mapping, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    observation = env.obs["state"]
    joint_order = [*(f"joint{index}" for index in range(1, 8)), "finger_joint1", "finger_joint2"]
    return {
        "control_step": int(state.control_step),
        "simulation_time_s": _finite(state.simulation_time, "state.simulation_time"),
        "boundary": boundary_mapping,
        "boundary_identity_sha256": boundary_hash,
        "typed_control_step": int(boundary.control_step),
        "sample_clock": clock.to_mapping(),
        "typed_simulation_time_s": _finite(clock.simulation_time_s, "sample_clock.simulation_time_s"),
        "joint_position": positions,
        "joint_velocity": velocities,
        "hand_pose_world": _pose(_frame_pose(env, "panda-main", "hand")),
        "free_cube_pose_world": _pose(cube),
        "free_cube_velocity": next(
            {
                "joint_id": item.joint_id,
                "position": [float(value) for value in item.position],
                "velocity": [float(value) for value in item.velocity],
                "velocity_expressed_in": (
                    None if item.velocity_expressed_in is None
                    else item.velocity_expressed_in.to_mapping()
                ),
                "velocity_reference_point": (
                    None if item.velocity_reference_point is None
                    else item.velocity_reference_point.to_mapping()
                ),
            }
            for item in publication.joints
            if item.entity_id == "free-cube" and item.kind == "floating"
        ),
        "task_metrics": {
            str(key): (bool(value) if isinstance(value, (bool, np.bool_))
                       else _finite(value, f"task_metrics.{key}"))
            for key, value in task_metrics.items()
        },
        "observation_state": {
            "joint_position": [_finite(value, "obs.joint_position")
                               for value in np.asarray(observation["joint_position"]).reshape(-1)],
            "ee_pose": [_finite(value, "obs.ee_pose")
                        for value in np.asarray(observation["ee_pose"]).reshape(-1)],
            "hand_pose": [_finite(value, "obs.hand_pose")
                          for value in np.asarray(observation["hand_pose"]).reshape(-1)],
        },
        "observation_joint_order": joint_order,
    }


def _request(env, hand_pose, gripper_command: float):
    from task_env.controllers.canonical.contracts import (
        ControlGroupActionV1,
        StructuredActionRequestV1,
    )

    schema_id = env.controller.controller_binding().action_schema.schema_id
    request = StructuredActionRequestV1(
        "structured-action-request-v1",
        env.position_scene.identity_hash,
        env.position_plan.identity_hash,
        (
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "arm", schema_id,
                tuple(float(value) for value in (*hand_pose.position, *hand_pose.quaternion_wxyz)),
            ),
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "gripper", schema_id,
                (float(gripper_command),),
            ),
        ),
    )
    request.validate()
    return request


def _target_pose(env, phase: dict):
    target_q = phase["arm_target_position_rad"]
    pose = env.controller.model.pose([target_q[f"joint{index}"] for index in range(1, 8)])
    actual = _pose(pose)
    expected = phase["source_fk_hand_pose_world"]
    if not np.allclose(actual["position_m"], expected["position_m"], atol=2e-8, rtol=1e-8):
        raise ValueError(f"source FK target position changed after freeze for {phase['phase']}")
    q_actual, q_expected = np.asarray(actual["quaternion_wxyz"]), np.asarray(expected["quaternion_wxyz"])
    if min(np.linalg.norm(q_actual - q_expected), np.linalg.norm(q_actual + q_expected)) > 2e-8:
        raise ValueError(f"source FK target orientation changed after freeze for {phase['phase']}")
    return pose


def _run_episode(env, *, plan: dict, episode_index: int, counter_path: Path) -> dict:
    from task_env.diagnostics.tasks.f05_dg02_core_s1_probe import (
        _record_attempt,
        _pose_mapping,
    )
    from task_env.recorders import load_structured_control_records_h5

    obs, info = env.reset()
    if env.state.control_step != 0 or abs(float(env.state.simulation_time)) > 1e-12:
        raise ValueError("Core N2 reset did not start at boundary/time zero")
    if info.get("source_closure_digest") != env.value["source"].source_closure_digest:
        raise ValueError("Core N2 reset source closure differs from the actual RuntimeSource")
    contact_reset = env.session.read_contact_observation()
    contact_reset_owner = contact_reset.get("owner")
    contact_reset_episode = contact_reset.get("episode")
    contact_reset_generation = contact_reset.get("generation")
    if (
        contact_reset.get("schema_version") != "f05-dg02-public-contact-observation-v1"
        or contact_reset.get("known") is not False
        or not isinstance(contact_reset_owner, str)
        or not contact_reset_owner
        or type(contact_reset_episode) is not int
        or contact_reset_episode < 1
        or type(contact_reset_generation) is not int
        or contact_reset_generation < 0
        or contact_reset.get("completed_substeps") != 0
        or contact_reset.get("delivery_errors") != 0
    ):
        raise RuntimeError(
            "Core N2 reset did not establish a fresh one-based public contact epoch "
            f"with zero completed substeps: {contact_reset}"
        )
    initial = _record_state(env)
    if int(env.sample.task_seed) != int(plan["source"]["task_seed"]):
        raise ValueError("Core N2 reset task seed differs from frozen DG02 source")
    output = Path(plan["output"]["episode_h5_paths"][episode_index - 1]).resolve()
    env.start_recording(output)
    expected_dt = float(plan["oracle"]["outer_control_dt_s"])
    substeps = int(plan["oracle"]["control_substeps"])
    phases = plan["oracle"]["schedule"]
    interval_count = int(plan["oracle"]["control_intervals_per_episode"])
    phase_poses = {phase["phase"]: _target_pose(env, phase) for phase in phases}
    boundaries = [initial]
    transitions = []
    run_instance_id = id(env)
    for index in range(interval_count):
        phase = next(row for row in phases if row["start"] <= index < row["stop"])
        before = _record_state(env)
        opening_m = float(phase["opening_m"])
        opening_range_m = float(plan["oracle"]["controller_action_config"]["gripper_opening_range_m"])
        command = (2.0 * opening_m / opening_range_m) - 1.0
        hand_pose = phase_poses[phase["phase"]]
        request = _request(env, hand_pose, command)
        _record_attempt(counter_path, plan)
        result = env.step(request)
        if type(result) is not tuple or len(result) != 5:
            raise TypeError("SelectedReferenceEnv.step did not return the five-value transition")
        obs, reward, terminated, truncated, step_info = result
        after = _record_state(env)
        contact_observation = env.session.read_contact_observation()
        if after["control_step"] != before["control_step"] + 1:
            raise ValueError("Core N2 did not advance exactly one public control boundary")
        if abs((after["simulation_time_s"] - before["simulation_time_s"]) - expected_dt) > 1e-10:
            raise ValueError("Core N2 public clock differs from the frozen control interval")
        expected_final_boundary = index == int(plan["oracle"]["control_intervals_per_episode"]) - 1
        if bool(terminated):
            raise RuntimeError(f"Core N2 lifecycle terminated unexpectedly at interval {index}")
        if bool(truncated) != expected_final_boundary:
            raise RuntimeError(
                "Core N2 horizon truncation differs from the frozen explicit final-boundary policy "
                f"at interval {index}: truncated={truncated}"
            )
        if bool(step_info["task_metrics"]["lifecycle_terminated"]):
            raise RuntimeError("Core N2 actual Task lifecycle marked a terminal state")
        expected_contact_episode = contact_reset_episode
        expected_contact_substeps = (index + 1) * substeps
        expected_contact_generation = contact_reset_generation + expected_contact_substeps
        if (contact_observation.get("known") is not True
                or contact_observation.get("impulses_known") is not True
                or contact_observation.get("owner") != contact_reset_owner
                or contact_observation.get("episode") != expected_contact_episode
                or contact_observation.get("generation") != expected_contact_generation
                or contact_observation.get("completed_substeps") != expected_contact_substeps):
            failed_sample = {
                key: contact_observation.get(key)
                for key in (
                    "known", "reason", "phase", "geometry_substep", "impulses_known",
                    "owner", "episode", "generation", "completed_substeps", "delivery_errors",
                )
            }
            raise RuntimeError(
                "Core N2 public GeoPhys contact sample is not known and reset-bound "
                "at the exact native boundary "
                f"(expected_owner={contact_reset_owner}, expected_episode={expected_contact_episode}, "
                f"expected_generation={expected_contact_generation}, "
                f"expected_completed_substeps={expected_contact_substeps}, sample={failed_sample})"
            )
        _record_attempt(counter_path, plan, completed=True)
        transitions.append({
            "interval_index": index,
            "phase": phase["phase"],
            "requested_opening_m": opening_m,
            "requested_gripper_command": command,
            "requested_arm_target_position_rad": phase["arm_target_position_rad"],
            "requested_hand_pose_world": _pose_mapping(hand_pose),
            "reward": _finite(reward, "reward"),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "before_boundary_index": index,
            "after_boundary_index": index + 1,
            "task_raw_lift_predicate": bool(step_info["task_metrics"]["raw_lift_height_predicate"]),
            "contact_observation": contact_observation,
        })
        boundaries.append(after)
    if len(boundaries) != interval_count + 1 or len(transitions) != interval_count:
        raise ValueError("Core N2 did not publish the frozen T/T+1 episode shape")
    episode_end = env.stop(f"dg02_core_n2_episode_{episode_index}")
    outcome = episode_end.outcome
    if (outcome.end_reason != "horizon_reached" or outcome.terminated
            or not outcome.truncated or not outcome.bootstrap_allowed):
        raise ValueError("Core N2 final horizon outcome differs from explicit nonterminal policy")
    recording = env.finish_recording(outcome.end_reason)
    h5_path = Path(recording["path"]).resolve(strict=True)
    if h5_path != output:
        raise ValueError("Core N2 finalizer wrote a different H5 output path")
    with h5_path.open("rb") as stream:
        os.fsync(stream.fileno())
    directory_fd = os.open(h5_path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    cold_metadata = load_structured_control_records_h5(h5_path)
    if (recording["transition_count"] != interval_count
            or recording["observation_count"] != interval_count + 1
            or cold_metadata["transition_count"] != interval_count
            or cold_metadata["observation_count"] != interval_count + 1):
        raise ValueError("Core N2 Generic H5 finalizer/readback rejected T/T+1 counts")
    counter = json.loads(counter_path.read_text(encoding="utf-8"))
    return {
        "episode_index": episode_index,
        "run_instance_id": run_instance_id,
        "reset": initial,
        "reset_sample_id": env.sample.sample_id,
        "contact_observation_reset": {
            key: contact_reset.get(key)
            for key in (
                "schema_version", "known", "reason", "owner", "episode", "generation",
                "completed_substeps", "delivery_errors",
            )
        },
        "task_seed": int(env.sample.task_seed),
        "provider": env.provider,
        "backend": env.backend,
        "session_type": f"{type(env.session).__module__}.{type(env.session).__name__}",
        "execution_identity_sha256": env.execution.identity_hash,
        "controller_identity": env.controller.identity,
        "source_closure_sha256": env.value["source"].source_closure_digest,
        "task_artifact_identity_sha256": env.artifact.identity_hash,
        "scene_identity_sha256": env.position_scene.identity_hash,
        "control_binding_plan_identity_sha256": env.position_plan.identity_hash,
        "native_drive_receipt_identity_sha256": env.controller.native_drive_receipt.identity_sha256,
        "transition_count": recording["transition_count"],
        "observation_count": recording["observation_count"],
        "episode_outcome": outcome.to_mapping(),
        "h5_path": str(h5_path),
        "h5_bytes": h5_path.stat().st_size,
        "h5_sha256": _sha(h5_path),
        "durable_file": True,
        "in_process_h5_readback": {
            "transition_count": cold_metadata["transition_count"],
            "observation_count": cold_metadata["observation_count"],
        },
        "boundaries": boundaries,
        "transitions": transitions,
        "physics_steps_attempted_after_episode": counter["attempted_physics_steps"],
        "physics_steps_completed_after_episode": counter["completed_physics_steps"],
    }


def run(plan_path: Path, sidecar: Path, receipt_path: Path, counter_path: Path) -> dict:
    plan, plan_hash = _verify(plan_path.resolve(strict=True), sidecar.resolve(strict=True))
    run_dir = Path(plan["output"]["run_dir"]).resolve(strict=True)
    if receipt_path.resolve() != Path(plan["output"]["worker_receipt"]).resolve():
        raise ValueError("Core N2 worker receipt path differs from frozen output")
    if counter_path.resolve() != run_dir / "step_counter.json":
        raise ValueError("Core N2 step-counter path differs from frozen output")
    static_row = plan["source"]["core_candidate_receipt"]
    static_path = Path(static_row["path"]).resolve(strict=True)
    static_receipt = json.loads(static_path.read_text(encoding="utf-8"))
    from task_env.diagnostics.tasks.f05_dg02_core_source_receipt import build_candidate_receipt

    rebuilt, candidate = build_candidate_receipt(plan, include_candidate=True)
    for key in (
        "source_actuation_receipt_identity_sha256",
        "provider_source_closure_sha256",
        "provider_delivery_closure_sha256",
        "dg02_task_artifact_identity_sha256",
        "dg02_scene_identity_sha256",
        "controller_binding_plan_identity_sha256",
        "controller_identity_sha256",
        "controller_method",
        "public_model_counts",
    ):
        if rebuilt.get(key) != static_receipt.get(key):
            raise ValueError(f"Core N2 source candidate rebuild differs from frozen static receipt: {key}")
    expected_counts = plan["oracle"]["required_public_model_counts"]
    actual_counts = rebuilt.get("public_model_counts", {})
    if not isinstance(actual_counts, dict) or any(
        actual_counts.get(name) != count for name, count in expected_counts.items()
    ):
        raise ValueError("Core N2 actual source model counts differ from the frozen public model requirements")
    geometry_audit = json.loads(
        Path(plan["source"]["usd_geometry_audit_v2"]["path"]).read_text(encoding="utf-8")
    )
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
    if (
        geometry_audit.get("passed") is not True
        or geometry_audit.get("usd_stage_sha256") != plan["source"]["usd_stage"]["sha256"]
        or expected_geom_count is None
        or actual_counts.get("n_geoms") != expected_geom_count
    ):
        raise ValueError("Core N2 actual source geom count differs from the hashed USD collision-shape audit")
    env = candidate.env
    episodes = []
    primary_error = None
    close_returned = False
    try:
        episode_count = int(plan["oracle"]["episode_count"])
        for episode_index in range(1, episode_count + 1):
            episodes.append(_run_episode(env, plan=plan, episode_index=episode_index, counter_path=counter_path))
        if len({row["run_instance_id"] for row in episodes}) != 1:
            raise ValueError("Core N2 episodes did not use the same SelectedReferenceEnv instance")
    except BaseException as error:
        primary_error = error
    finally:
        try:
            env.close()
            close_returned = True
        except BaseException as cleanup_error:
            if primary_error is None:
                primary_error = cleanup_error
            else:
                add_note = getattr(primary_error, "add_note", None)
                if callable(add_note):
                    add_note(f"Core N2 SelectedReferenceEnv.close also failed: {cleanup_error!r}")
    counter = json.loads(counter_path.read_text(encoding="utf-8"))
    expected_steps = int(plan["limits"]["physics_steps_reserved"])
    counts_complete = (
        counter.get("attempted_physics_steps") == expected_steps
        and counter.get("completed_physics_steps") == expected_steps
    )
    if primary_error is None and not counts_complete:
        primary_error = RuntimeError("Core N2 physics-step counter differs from exact frozen reservation")
    result = {
        "schema_version": "f05-dg02-core-n2-worker-receipt-v1",
        "run_id": plan["run_id"],
        "plan_sha256": plan_hash,
        "static_candidate_receipt_sha256": static_row["sha256"],
        "public_model_counts": actual_counts,
        "source_delivery_identity_sha256": plan["source"]["delivery_identity_sha256"],
        "usd_stage_sha256": plan["source"]["usd_stage"]["sha256"],
        "provider_head": plan["input_identity"]["provider_input_head"],
        "core_head": plan["input_identity"]["core_input_head"],
        "native_starts": 1,
        "physics_steps_attempted": counter.get("attempted_physics_steps"),
        "physics_steps_completed": counter.get("completed_physics_steps"),
        "expected_physics_steps_per_core_interval": int(plan["oracle"]["control_substeps"]),
        "episode_count": len(episodes),
        "episodes": episodes,
        "same_selected_env_instance": (
            bool(episodes) and len({row["run_instance_id"] for row in episodes}) == 1
        ),
        "selected_env_close_returned": close_returned,
        "status": (
            "PASS_CORE_N2_FORMAL_2X300"
            if primary_error is None and plan["oracle"]["episode_count"] == 2
            and plan["oracle"]["control_intervals_per_episode"] == 300
            else "PASS_CORE_N2_TRACKING_PROBE"
            if primary_error is None
            else "PARTIAL_CORE_N2"
        ),
    }
    if primary_error is not None:
        result["failure"] = f"{type(primary_error).__name__}: {primary_error}"
        result["traceback"] = "".join(traceback.format_exception(primary_error))
    _atomic_json(receipt_path, result)
    if primary_error is not None:
        raise primary_error
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--counter", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.plan, args.plan_sha256, args.receipt, args.counter)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
