"""Run the frozen two-episode DG01 SelectedReference/Core MuJoCo cell."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_once(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _append_jsonl(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _joint_readback(env) -> dict[str, dict[str, float]]:
    result = {}
    for value in env.typed_state.view.joints:
        if value.entity_id == "panda-main" and value.joint_id in {
            *(f"joint{index}" for index in range(1, 8)),
            "finger_joint1", "finger_joint2",
        }:
            result[value.joint_id] = {
                "position": float(value.position[0]),
                "velocity": float(value.velocity[0]),
            }
    expected = {*(f"joint{index}" for index in range(1, 8)),
                "finger_joint1", "finger_joint2"}
    if set(result) != expected:
        raise RuntimeError(f"DG01 typed joint publication incomplete: {sorted(result)}")
    return result


def _frame_readback(env, entity_id: str, frame_id: str) -> dict:
    values = [item for item in env.typed_state.view.frames
              if item.frame.entity_id == entity_id and item.frame.frame_id == frame_id]
    if len(values) != 1:
        raise RuntimeError(f"DG01 typed frame missing/ambiguous: {entity_id}/{frame_id}")
    pose = values[0].pose_world
    return {
        "position_m": [float(value) for value in pose.position],
        "quaternion_wxyz": [float(value) for value in pose.quaternion_wxyz],
    }


def _boundary_readback(env) -> dict:
    view = env.typed_state.view
    return {
        "boundary": view.boundary.to_mapping(),
        "sample_clock": view.sample_clock.to_mapping(),
        "joints": _joint_readback(env),
        "hand": _frame_readback(env, "panda-main", "hand"),
        "cube": _frame_readback(env, "free-cube", "free_cube"),
        "task_metrics": dict(env.info.get("task_metrics", {})),
        "task_semantics": {
            key: env.info.get(key) for key in (
                "task_success_semantics", "raw_task_predicate",
                "lifecycle_valid_success", "lifecycle_valid_success_assessed",
            )
        },
    }


def _episode_request(candidate, env, arm_q: tuple[float, ...], opening_m: float):
    from task_env.controllers.canonical.contracts import (
        ControlGroupActionV1, StructuredActionRequestV1,
    )

    pose = env.controller.model.pose(arm_q)
    schema_id = env.controller.controller_binding().action_schema.schema_id
    request = StructuredActionRequestV1(
        "structured-action-request-v1", env.position_scene.identity_hash,
        env.position_plan.identity_hash,
        (
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "arm", schema_id,
                tuple(float(value) for value in (*pose.position, *pose.quaternion_wxyz)),
            ),
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "gripper", schema_id,
                (float(2.0 * opening_m / 0.08 - 1.0),),
            ),
        ),
    )
    request.validate()
    return request


def _phase_at(index: int, schedule: list[dict]) -> dict:
    matches = [item for item in schedule if item["start"] <= index < item["stop"]]
    if len(matches) != 1:
        raise ValueError(f"control interval {index} has no unique frozen schedule row")
    return matches[0]


def _fsync_file_and_parent(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_h5_witness(path: Path, witness: dict) -> None:
    import h5py

    encoded = json.dumps(witness, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with h5py.File(path, "r+") as h5:
        meta = h5.require_group("meta")
        if "dg01_native_run_witness_v1_json" in meta:
            raise FileExistsError("DG01 run witness already exists")
        dtype = h5py.string_dtype(encoding="utf-8")
        meta.create_dataset("dg01_native_run_witness_v1_json", data=encoded, dtype=dtype)
        h5.flush()
    _fsync_file_and_parent(path)


def run(plan_path: Path, output: Path) -> dict:
    from dataclasses import asdict
    from task_env.tasks.position_candidate.builder import build_f05_dg01_mujoco_candidate
    from task_env.runtime.sessions.source import lower_mujoco_scene_source
    from task_env.environment.config import ActionConfig

    plan_path = plan_path.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != "f05-dg01-native-run-plan-v1":
        raise ValueError("unsupported DG01 Core cell plan")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_id = str(plan["run_id"])
    plan_sha = _sha256(plan_path)
    code_hashes = plan["code_sha256"]
    repo_root = Path(plan["workdir"]).resolve()
    for relative, expected in code_hashes.items():
        actual = _sha256(repo_root / relative)
        if actual != expected:
            raise ValueError(f"frozen DG01 source drift: {relative}: {actual}")
    expected_model = plan["frozen_source"]["model_receipt_identity_sha256"]
    schedule = plan["schedule"]
    expected_intervals = int(plan["control_intervals_per_episode"])
    expected_steps = (expected_intervals * int(plan["physics_steps_per_interval"])
                      * int(plan["episodes_per_env"]))
    if expected_intervals != 300 or expected_steps != 3000:
        raise ValueError("formal DG01 Core cell plan must reserve exactly 2x300x5 steps")
    trace_path = output / "core_boundaries.jsonl"
    started = _utc_now()
    started_monotonic = time.monotonic()
    controller_action_config = plan.get("controller_action_config")
    if not isinstance(controller_action_config, dict):
        raise ValueError("formal DG01 plan must freeze its complete Position ActionConfig")
    controller_config = ActionConfig(**controller_action_config)
    candidate = build_f05_dg01_mujoco_candidate(
        output / "candidate-build", horizon=300,
        controller_config=controller_config,
    )
    env = candidate.env
    if asdict(env.controller.config) != controller_action_config:
        raise ValueError("DG01 Core candidate Position ActionConfig differs from its frozen plan")
    session_ids = []
    session_handles = []
    episodes = []
    total_steps = 0
    previous_episode_id = None
    try:
        derived_scene_path = output / "derived_task_scene.xml"
        derived_scene_path.write_bytes(candidate.source.scene_source.xml.encode("utf-8"))
        lowered_xml, lowered_assets = lower_mujoco_scene_source(
            candidate.source.scene_source, candidate.source.scene_definition,
            candidate.source.source_closure_digest,
        )
        lowered_scene_path = output / "runtime_lowered_scene.xml"
        lowered_scene_path.write_bytes(lowered_xml.encode("utf-8"))
        _write_once(output / "runtime_lowered_assets.json", {
            name: hashlib.sha256(value).hexdigest()
            for name, value in sorted(lowered_assets.items())
        })
        source_files = {
            "derived_task_scene_xml": {
                "path": str(derived_scene_path), "sha256": _sha256(derived_scene_path),
            },
            "runtime_lowered_scene_xml": {
                "path": str(lowered_scene_path), "sha256": _sha256(lowered_scene_path),
            },
            "panda_source_closure_sha256": candidate.panda_closure_digest,
            "runtime_source_closure_sha256": candidate.source_closure_digest,
        }
        reset_joints = candidate.candidate_input.artifact.initialization.joint_position
        home = {name.split("/", 1)[1]: float(value)
                for name, value in reset_joints.items()}
        arm_home = tuple(home[f"joint{index}"] for index in range(1, 8))
        for episode_index in range(int(plan["episodes_per_env"])):
            episode_started = time.monotonic()
            previous_sessions = tuple(session_handles)
            _, reset_info = env.reset(seed=int(plan["task_seed"]))
            if not all(getattr(previous, "_closed", False) for previous in previous_sessions):
                raise RuntimeError("same-Env reset did not close its prior RuntimeSession")
            session = env.session
            if session is None or getattr(session, "_native_steps", None) != 0:
                raise RuntimeError("DG01 formal reset must create a zero-step RuntimeSession")
            model_receipt = getattr(session, "_f05_dg01_model_receipt", None)
            if (not isinstance(model_receipt, dict)
                    or model_receipt.get("identity_sha256") != expected_model):
                raise RuntimeError("formal episode model differs from frozen N0/N1 model")
            episode_id = env.typed_state.view.boundary.episode_id
            if episode_id == previous_episode_id:
                raise RuntimeError("DG01 episodes must have distinct real lifecycle identities")
            previous_episode_id = episode_id
            session_ids.append(str(session._provider_materialization_id))
            session_handles.append(session)
            if env.state.control_step != 0 or env.state.simulation_time != 0.0:
                raise RuntimeError("DG01 reset advanced control/physics clock")
            reset_boundary = _boundary_readback(env)
            if reset_boundary["boundary"]["control_step"] != 0:
                raise RuntimeError("DG01 reset publication is not boundary zero")
            h5_path = output / f"episode_{episode_index + 1:02d}.h5"
            env.start_recording(h5_path)
            _append_jsonl(trace_path, {
                "kind": "reset", "run_id": run_id,
                "episode_index": episode_index, "episode_id": episode_id,
                "reset_physics_steps": 0, "reset_info": reset_info,
                "model_receipt_identity_sha256": expected_model,
                "boundary": reset_boundary,
            })
            episode_rows = []
            for interval_index in range(expected_intervals):
                phase = _phase_at(interval_index, schedule)
                offsets = tuple(float(value) for value in phase["arm_offsets_rad"])
                arm_target = tuple(value + offset for value, offset in zip(
                    arm_home, offsets, strict=True,
                ))
                request = _episode_request(candidate, env, arm_target, float(phase["opening_m"]))
                before_native_steps = int(session._native_steps)
                _observation, reward, terminated, truncated, info = env.step(request)
                advances = tuple(getattr(session, "_last_dg01_interval_advances", ()))
                if len(advances) != 5:
                    raise RuntimeError(f"DG01 interval {interval_index} has {len(advances)} accepted substeps")
                after_native_steps = int(session._native_steps)
                if after_native_steps - before_native_steps != 5:
                    raise RuntimeError("DG01 native step counter differs from five accepted advances")
                if bool(terminated) or (bool(truncated) != (interval_index == 299)):
                    raise RuntimeError(
                        f"DG01 lifecycle changed unexpectedly at {interval_index}: "
                        f"terminated={terminated}, truncated={truncated}"
                    )
                state = _boundary_readback(env)
                row = {
                    "run_id": run_id, "episode_index": episode_index,
                    "episode_id": episode_id, "interval_index": interval_index,
                    "phase": phase["phase"], "target_arm_position_rad": list(arm_target),
                    "requested_opening_m": float(phase["opening_m"]),
                    "native_step_start": before_native_steps,
                    "native_step_end": after_native_steps,
                    "advance_receipts": [dict(item) for item in advances],
                    "state": state, "reward": float(reward),
                    "terminated": bool(terminated), "truncated": bool(truncated),
                    "task_metrics": dict(info.get("task_metrics", {})),
                }
                _append_jsonl(trace_path, {"kind": "transition", **row})
                episode_rows.append(row)
                total_steps += 5
            finish = env.finish_recording("horizon")
            outcome = finish.get("outcome")
            if not isinstance(outcome, dict):
                raise RuntimeError("DG01 recorder did not return an EpisodeOutcome")
            session_id = str(session._provider_materialization_id)
            episode_payload = {
                "episode_index": episode_index,
                "episode_id": episode_id,
                "provider_materialization_id": session_id,
                "h5_path": str(h5_path),
                "h5_sha256_before_witness": _sha256(h5_path),
                "outcome": outcome,
                "interval_count": len(episode_rows),
                "accepted_physics_steps": sum(
                    len(row["advance_receipts"]) for row in episode_rows
                ),
                "reset_physics_steps": 0,
                "final_control_step": int(env.state.control_step),
                "final_simulation_time_s": float(env.state.simulation_time),
                "episode_wall_s": time.monotonic() - episode_started,
                "reset_boundary": reset_boundary,
                "boundary_rows": [reset_boundary, *[row["state"] for row in episode_rows]],
                "transition_rows": episode_rows,
                "recording_summary": finish,
                "task_predicate_final": dict(info.get("task_metrics", {})),
            }
            episodes.append(episode_payload)
            _append_jsonl(trace_path, {
                "kind": "episode_complete", "run_id": run_id,
                "episode_index": episode_index, "episode_id": episode_id,
                "outcome": outcome,
                "accepted_physics_steps": episode_payload["accepted_physics_steps"],
                "h5_path": str(h5_path),
            })
        env.close()
        if not getattr(env, "_closed", False):
            raise RuntimeError("DG01 SelectedReferenceEnv did not close")
        if not all(getattr(item, "_closed", False) for item in session_handles):
            raise RuntimeError("DG01 one or more episode RuntimeSessions remained open")
        for episode in episodes:
            h5_path = Path(episode["h5_path"])
            witness = {
                "schema_version": "f05-dg01-native-run-witness-v1",
                "run_id": run_id,
                "run_plan_sha256": plan_sha,
                "worker_code_sha256": code_hashes[
                    "task_env/diagnostics/tasks/f05_dg01_core_cell.py"
                ],
                "episode_index": episode["episode_index"],
                "episode_id": episode["episode_id"],
                "provider_materialization_id": episode["provider_materialization_id"],
                "model_receipt_identity_sha256": expected_model,
                "control_intervals": expected_intervals,
                "accepted_physics_steps": episode["accepted_physics_steps"],
                "reset_physics_steps": 0,
                "task_seed": int(plan["task_seed"]),
            }
            _append_h5_witness(h5_path, witness)
            episode["h5_sha256"] = _sha256(h5_path)
            episode["h5_bytes"] = h5_path.stat().st_size
        payload = {
            "schema_version": "f05-dg01-core-cell-worker-result-v1",
            "run_id": run_id,
            "run_plan_sha256": plan_sha,
            "started_utc": started,
            "finished_utc": _utc_now(),
            "worker_wall_s": time.monotonic() - started_monotonic,
            "candidate_type": type(candidate.env).__name__,
            "same_environment_object": True,
            "episodes": episodes,
            "distinct_provider_materializations": len(set(session_ids)),
            "native_invocations": 1,
            "native_model_compiles": len(session_handles),
            "integration_steps": total_steps,
            "expected_integration_steps": expected_steps,
            "environment_closed": True,
            "core_session_ids": session_ids,
            "core_boundaries_jsonl": str(trace_path),
            "source_files": source_files,
        }
        _write_once(output / "worker_result.json", payload)
        return payload
    finally:
        if not getattr(env, "_closed", False):
            env.close()


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run(args.plan, args.output)
    print(json.dumps({
        "run_id": result["run_id"],
        "integration_steps": result["integration_steps"],
        "episodes": len(result["episodes"]),
        "environment_closed": result["environment_closed"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
