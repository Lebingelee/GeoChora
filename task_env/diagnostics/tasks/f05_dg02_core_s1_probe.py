"""Bounded source-bound DG02 S1 through SelectedReferenceEnv and Core RuntimeSession."""

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


def _record_attempt(counter_path: Path, plan: dict, *, completed: bool = False) -> None:
    counter = json.loads(counter_path.read_text(encoding="utf-8"))
    if counter.get("run_id") != plan["run_id"]:
        raise ValueError("Core S1 step counter belongs to another run")
    reservation = int(plan["limits"]["physics_steps_reserved"])
    substeps = int(plan["oracle"]["control_substeps"])
    key = "completed_physics_steps" if completed else "attempted_physics_steps"
    next_value = int(counter[key]) + substeps
    if not completed and next_value > reservation:
        raise RuntimeError("Core S1 attempted to exceed its frozen physics-step reservation")
    if completed and next_value > int(counter["attempted_physics_steps"]):
        raise RuntimeError("Core S1 completed-step count exceeds attempted steps")
    counter[key] = next_value
    counter["expected_native_steps_per_core_interval"] = substeps
    counter["physics_dt_s"] = float(plan["oracle"]["physics_dt_s"])
    _atomic_json(counter_path, counter)


def _verify(plan_path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    plan_hash = hashlib.sha256(raw).hexdigest()
    if plan_hash != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("DG02 Core S1 plan SHA-256 mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-n1-public-consumer-plan-v1":
        raise ValueError("unsupported DG02 Core S1 plan schema")
    if plan.get("classification") != "actual Core SelectedReferenceEnv S1; source-bound GeoPhys/USD; not qualification":
        raise ValueError("Core S1 classification changed after freeze")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"Core S1 code changed after plan freeze: {path}")
    for label, row in plan["source"].items():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            path = Path(row["path"]).resolve(strict=True)
            if _sha(path) != row["sha256"]:
                raise ValueError(f"Core S1 frozen source changed after plan freeze: {label}")
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
            raise ValueError(f"Core S1 {repo_key} branch/HEAD changed after plan freeze")
    return plan, plan_hash


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Core S1 observation contains a non-finite value")
    return number


def _pose_mapping(pose) -> dict[str, list[float]]:
    return {
        "position_m": [_finite(value) for value in pose.position],
        "quaternion_wxyz": [_finite(value) for value in pose.quaternion_wxyz],
    }


def _frame_pose(env, entity_id: str, frame_id: str):
    matches = [
        item for item in env.typed_state.view.frames
        if item.frame.entity_id == entity_id and item.frame.frame_id == frame_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Core S1 typed state must contain exactly one {entity_id}/{frame_id}")
    return matches[0].pose_world


def _state_record(env) -> dict:
    state = env.state
    boundary = env.typed_state.view.boundary
    sample_clock = env.typed_state.view.sample_clock
    task_metrics = env.info.get("task_metrics")
    if not isinstance(task_metrics, Mapping):
        raise ValueError("Core S1 public Task metrics are missing")
    if "raw_lift_height_predicate" not in task_metrics:
        raise ValueError("Core S1 actual Task raw-lift readout is missing")
    cube = state.pose_world.get("free-cube/free_cube")
    if cube is None:
        raise ValueError("Core S1 public state lacks the free-cube Frame")
    return {
        "control_step": int(state.control_step),
        "simulation_time_s": _finite(state.simulation_time),
        "boundary_id": boundary.boundary_id,
        "typed_control_step": int(boundary.control_step),
        "typed_simulation_time_s": _finite(sample_clock.simulation_time_s),
        "sample_clock": sample_clock.to_mapping(),
        "hand_pose_world": _pose_mapping(_frame_pose(env, "panda-main", "hand")),
        "free_cube_pose_world": _pose_mapping(cube),
        "task_metrics": {
            str(key): (bool(value) if isinstance(value, (bool, np.bool_)) else _finite(value))
            for key, value in task_metrics.items()
        },
        "observation_ee_pose": [
            _finite(value) for value in np.asarray(env.obs["state"]["ee_pose"]).reshape(-1)
        ],
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


def _run_episode(env, *, plan: dict, episode_index: int, counter_path: Path) -> dict:
    from task_env.recorders import load_structured_control_records_h5

    schedule = plan["oracle"]["gripper_schedule_by_episode"][episode_index - 1]
    if len(schedule) != int(plan["oracle"]["control_intervals_per_episode"]):
        raise ValueError("Core S1 frozen gripper schedule length does not match intervals")
    obs, info = env.reset()
    if env.state.control_step != 0 or abs(float(env.state.simulation_time)) > 1e-12:
        raise ValueError("Core S1 reset did not return to control step/time zero")
    initial = _state_record(env)
    if info.get("source_closure_digest") != env.value["source"].source_closure_digest:
        raise ValueError("Core S1 reset info source closure differs from RuntimeSource")
    output = Path(plan["output"]["episode_h5_paths"][episode_index - 1]).resolve()
    env.start_recording(output)
    expected_dt = float(env.artifact.timebase.control_dt)
    substeps = int(env.artifact.timebase.control_substeps)
    transitions = []
    hand_pose = _frame_pose(env, "panda-main", "hand")
    for index, command in enumerate(schedule):
        before = _state_record(env)
        request = _request(env, hand_pose, float(command))
        _record_attempt(counter_path, plan)
        result = env.step(request)
        if type(result) is not tuple or len(result) != 5:
            raise TypeError("SelectedReferenceEnv.step must return the ordinary five-value transition")
        obs, reward, terminated, truncated, step_info = result
        after = _state_record(env)
        if after["control_step"] != before["control_step"] + 1:
            raise ValueError("Core S1 did not advance exactly one control boundary")
        if abs((after["simulation_time_s"] - before["simulation_time_s"]) - expected_dt) > 1e-10:
            raise ValueError("Core S1 selected boundary clock differs from its frozen control dt")
        if bool(terminated) or bool(truncated):
            raise RuntimeError("Core S1 unexpectedly terminated or truncated before its planned stop")
        _record_attempt(counter_path, plan, completed=True)
        transitions.append({
            "interval_index": index,
            "requested_gripper_command": float(command),
            "requested_hand_pose_world": _pose_mapping(hand_pose),
            "reward": _finite(reward),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "before": before,
            "after": after,
            "task_raw_lift_predicate": bool(step_info["task_metrics"]["raw_lift_height_predicate"]),
        })
    expected_transitions = int(plan["oracle"]["control_intervals_per_episode"])
    if len(transitions) != expected_transitions:
        raise ValueError("Core S1 interval count differs from its frozen plan")
    episode_end = env.stop(f"dg02_core_s1_episode_{episode_index}")
    recording = env.finish_recording(episode_end.outcome.end_reason)
    h5_path = Path(recording["path"]).resolve(strict=True)
    if h5_path != output:
        raise ValueError("Core S1 H5 path differs from the frozen episode output")
    with h5_path.open("rb") as stream:
        os.fsync(stream.fileno())
    directory_fd = os.open(h5_path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    cold_metadata = load_structured_control_records_h5(h5_path)
    if (cold_metadata["transition_count"] != expected_transitions
            or cold_metadata["observation_count"] != expected_transitions + 1):
        raise ValueError("Core S1 in-process Generic H5 reader rejected T/T+1 counts")
    if (recording["transition_count"] != expected_transitions
            or recording["observation_count"] != expected_transitions + 1):
        raise ValueError("Core S1 finalizer receipt rejected T/T+1 counts")
    return {
        "episode_index": episode_index,
        "reset": initial,
        "reset_sample_id": env.sample.sample_id,
        "task_seed": int(env.sample.task_seed),
        "session_type": f"{type(env.session).__module__}.{type(env.session).__name__}",
        "provider": env.provider,
        "backend": env.backend,
        "execution_identity_sha256": env.execution.identity_hash,
        "controller_identity": env.controller.identity,
        "source_closure_sha256": env.value["source"].source_closure_digest,
        "task_artifact_identity_sha256": env.artifact.identity_hash,
        "scene_identity_sha256": env.position_scene.identity_hash,
        "control_binding_plan_identity_sha256": env.position_plan.identity_hash,
        "native_drive_receipt_identity_sha256": env.controller.native_drive_receipt.identity_sha256,
        "transition_count": recording["transition_count"],
        "observation_count": recording["observation_count"],
        "episode_outcome": recording["outcome"],
        "h5_path": str(h5_path),
        "h5_bytes": h5_path.stat().st_size,
        "h5_sha256": _sha(h5_path),
        "in_process_h5_readback": {
            "transition_count": cold_metadata["transition_count"],
            "observation_count": cold_metadata["observation_count"],
        },
        "transitions": transitions,
    }


def run(plan_path: Path, sidecar: Path, receipt_path: Path, counter_path: Path) -> dict:
    plan, plan_hash = _verify(plan_path.resolve(strict=True), sidecar.resolve(strict=True))
    run_dir = Path(plan["output"]["run_dir"]).resolve(strict=True)
    if receipt_path.resolve() != Path(plan["output"]["worker_receipt"]).resolve():
        raise ValueError("Core S1 worker receipt path differs from frozen output")
    if counter_path.resolve() != run_dir / "step_counter.json":
        raise ValueError("Core S1 step-counter path differs from frozen output")
    static_row = plan["source"]["core_candidate_receipt"]
    static_receipt = json.loads(Path(static_row["path"]).resolve(strict=True).read_text())
    if _sha(Path(static_row["path"]).resolve(strict=True)) != static_row["sha256"]:
        raise ValueError("Core S1 static candidate receipt changed after freeze")
    from task_env.diagnostics.tasks.f05_dg02_core_source_receipt import build_candidate_receipt

    rebuilt, candidate = build_candidate_receipt(plan, include_candidate=True)
    if (rebuilt["source_actuation_receipt_identity_sha256"]
            != static_receipt["source_actuation_receipt_identity_sha256"]
            or rebuilt["provider_source_closure_sha256"]
            != static_receipt["provider_source_closure_sha256"]
            or rebuilt["dg02_task_artifact_identity_sha256"]
            != static_receipt["dg02_task_artifact_identity_sha256"]):
        raise ValueError("Core S1 candidate rebuild differs from the frozen static admission receipt")
    env = candidate.env
    episodes = []
    primary_error = None
    close_returned = False
    try:
        for episode_index in (1, 2):
            episodes.append(_run_episode(
                env, plan=plan, episode_index=episode_index, counter_path=counter_path,
            ))
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
                    add_note(f"Core S1 SelectedReferenceEnv.close also failed: {cleanup_error!r}")
    counter = json.loads(counter_path.read_text(encoding="utf-8"))
    result = {
        "schema_version": "f05-dg02-core-s1-receipt-v1",
        "run_id": plan["run_id"],
        "plan_sha256": plan_hash,
        "static_candidate_receipt_sha256": static_row["sha256"],
        "source_delivery_identity_sha256": plan["source"]["delivery_identity_sha256"],
        "usd_stage_sha256": plan["source"]["usd_stage"]["sha256"],
        "native_starts": 1,
        "physics_steps_attempted": counter["attempted_physics_steps"],
        "physics_steps_completed": counter["completed_physics_steps"],
        "expected_physics_steps_per_interval": int(plan["oracle"]["control_substeps"]),
        "episodes": episodes,
        "selected_env_close_returned": close_returned,
        "status": "PASS_CORE_S1_SELECTED_REFERENCE_RUNTIME_RECORDER_H5" if primary_error is None else "FAIL_CORE_S1",
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
