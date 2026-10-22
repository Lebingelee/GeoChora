"""Real legacy PickCube external-Solution S2 + canonical-v0 S3 probe.

Run one Provider per process. This uses the production selected factory,
task-owned readiness Solution, RuntimeSession and canonical Recorder; it does
not replace the session, feedback, Controller or Reader with a test double.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import traceback


TASK_UID = "pick-cube-p16-reference-v1"
TASK_SEED = 31
ARTIFACT_HASH = "fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4"
CONTROLLER_IDENTITY = "76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9"
SOLUTION_IDENTITY = "514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241"
SOURCE_ID = "task-env-pick-cube"
SOURCE_XML_SHA256 = "bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed"
TASK_SUCCESS_LIFT_M = 0.10
EXPERT_COMPLETION_LIFT_M = 0.105


def _value(value):
    if hasattr(value, "to_mapping"):
        return _value(value.to_mapping())
    if is_dataclass(value):
        return _value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_value(item) for item in value]
    if hasattr(value, "tolist"):
        return _value(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_value(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _same_clock(left, right):
    tolerance = max(math.ulp(float(left)), math.ulp(float(right)), math.ulp(0.01))
    return abs(float(left) - float(right)) <= tolerance


def _one_control_interval(start_time, end_time, control_dt):
    tolerance = max(
        math.ulp(float(start_time)),
        math.ulp(float(end_time)),
        math.ulp(float(control_dt)),
    )
    return abs((float(end_time) - float(start_time)) - float(control_dt)) <= tolerance


def _check_saved_trajectory(provider: str, receipt: dict, h5_path: Path):
    from task_env.trajectory.canonical.h5 import load as load_canonical

    trajectory = load_canonical(h5_path)
    trajectory.validate()
    metadata = trajectory.metadata
    source_provenance = metadata.source_provenance
    solution_identity = receipt["solution_identity"]
    sample_id = receipt["expected_reset_sample_id"]
    _require(receipt["expert_done"] and not receipt["expert_failed"],
             "real external Expert did not complete successfully")
    _require(receipt["task_success_seen"], "Task success was never observed")
    _require(float(receipt["final_task_metrics"]["cube_lift"]) >= EXPERT_COMPLETION_LIFT_M,
             "completed Expert did not reach its frozen 0.105 m endpoint")
    _require(metadata.task_artifact_hash == ARTIFACT_HASH, "H5 Artifact identity mismatch")
    _require(metadata.execution.physics_provider == provider, "H5 Provider identity mismatch")
    _require(metadata.task_seed == TASK_SEED, "H5 task seed mismatch")
    _require(metadata.controller_identity == CONTROLLER_IDENTITY, "H5 Controller identity mismatch")
    _require(metadata.expert_identity == solution_identity, "H5 Solution identity mismatch")
    _require(source_provenance.get("artifact_identity") == ARTIFACT_HASH,
             "H5 source provenance Artifact identity mismatch")
    _require(source_provenance.get("controller_identity") == CONTROLLER_IDENTITY,
             "H5 source provenance Controller identity mismatch")
    _require(source_provenance.get("solution_identity") == solution_identity,
             "H5 source provenance Solution identity mismatch")
    _require(source_provenance.get("runtime_source_id") == SOURCE_ID,
             "H5 RuntimeSource ID is absent or mismatched")
    _require(source_provenance.get("runtime_source_xml_sha256") == SOURCE_XML_SHA256,
             "H5 RuntimeSource bytes are absent or mismatched")
    expected_closure = receipt["actual_reset_boundary"]["source_closure_digest"]
    if expected_closure is None:
        _require("runtime_source_closure_digest" not in source_provenance,
                 "H5 invented a closure identity for the legacy RuntimeSource")
    else:
        _require(source_provenance.get("runtime_source_closure_digest") == expected_closure,
                 "H5 RuntimeSource closure differs from the exercised route")
    _require(metadata.reset_sample.sample_id == sample_id, "H5 ResetSample identity mismatch")
    _require(metadata.realized_initial_state.reset_sample_id == sample_id,
             "H5 realized reset identity mismatch")
    _require(len(trajectory.transitions) == receipt["step_count"], "H5 transition count mismatch")
    _require(len(trajectory.boundaries) == receipt["step_count"] + 1, "H5 T+1 boundary mismatch")
    _require(trajectory.stop_reason == "expert_completed", "H5 stop reason mismatch")

    for index, (boundary_value, expected) in enumerate(zip(
        trajectory.boundaries, receipt["runtime_boundaries"], strict=True,
    )):
        _require(boundary_value.control_step == expected["control_step"],
                 f"H5 state boundary {index} step mismatch")
        _require(_same_clock(boundary_value.simulation_time, expected["simulation_time_s"]),
                 f"H5 state boundary {index} time mismatch")
        _require(boundary_value.state.to_mapping() == expected["state"],
                 f"H5 state boundary {index} numerical readback mismatch")
        _require(boundary_value.feedback.to_mapping() == expected["feedback"],
                 f"H5 feedback boundary {index} readback mismatch")
        _require(boundary_value.readiness.to_mapping() == expected["readiness"],
                 f"H5 readiness boundary {index} readback mismatch")
        _require(boundary_value.task_metrics == expected["task_metrics"],
                 f"H5 Task metrics boundary {index} mismatch")
        _require(boundary_value.is_success == expected["task_success"],
                 f"H5 Task-success flag boundary {index} mismatch")
        _require(boundary_value.task_failure == expected["task_failure"],
                 f"H5 Task-failure flag boundary {index} mismatch")

    for index, (transition, expected) in enumerate(zip(
        trajectory.transitions, receipt["steps"], strict=True,
    )):
        app = expected["application"]
        _require(transition.requested_action.to_mapping() == app["requested_action"],
                 f"H5 requested action {index} mismatch")
        _require(transition.canonical_action.to_mapping() == app["canonical_action"],
                 f"H5 canonical action {index} mismatch")
        _require(transition.controller_target.to_mapping() == app["target"],
                 f"H5 target {index} mismatch")
        _require(transition.applied_control.to_mapping() == app["applied"],
                 f"H5 AppliedCanonicalControl {index} mismatch")
        _require(transition.applied_control.target_hash == transition.controller_target.identity_hash,
                 f"H5 target/ack linkage {index} mismatch")
        _require(transition.expert_stage == expected["stage_before"],
                 f"H5 Expert stage {index} mismatch")
        _require(_same_clock(transition.reward, expected["reward"]),
                 f"H5 reward {index} mismatch")
        _require(transition.terminated == expected["terminated"],
                 f"H5 terminated flag {index} mismatch")
        _require(transition.truncated == expected["truncated"],
                 f"H5 truncated flag {index} mismatch")

    return {
        "status": "PASS",
        "path": str(h5_path),
        "logical_identity_hash": trajectory.identity_hash,
        "schema_version": trajectory.schema_version,
        "provider_build": _value(metadata.provider_provenance),
        "artifact_identity": metadata.task_artifact_hash,
        "source_identity": {
            "source_id": source_provenance["runtime_source_id"],
            "source_xml_sha256": source_provenance["runtime_source_xml_sha256"],
            "source_closure_digest": source_provenance.get("runtime_source_closure_digest"),
            "closure_identity_available": "runtime_source_closure_digest" in source_provenance,
        },
        "controller_identity": metadata.controller_identity,
        "solution_identity": metadata.expert_identity,
        "reset_sample_id": metadata.reset_sample.sample_id,
        "transition_count": len(trajectory.transitions),
        "boundary_count": len(trajectory.boundaries),
        "stop_reason": trajectory.stop_reason,
        "task_success_step": receipt["task_success_step"],
        "expert_completion_step": receipt["expert_completion_step"],
        "numeric_states_compared_with_runtime": len(trajectory.boundaries),
        "request_to_applied_ack_compared": len(trajectory.transitions),
    }


def _readback_existing(run_path: Path):
    receipt = json.loads(run_path.read_text(encoding="utf-8"))
    provider = receipt["provider"]
    h5_path = Path(receipt["recording_path"])
    _require(h5_path.is_file(), f"saved canonical trajectory is missing: {h5_path}")
    s3 = _check_saved_trajectory(provider, receipt, h5_path)
    result = {
        "schema_version": "c05b-pickcube-external-s3-readback-v1",
        "provider": provider,
        "source_run_receipt": str(run_path),
        "recording_path": str(h5_path),
        "s2_result": {
            "external_step_count": receipt["step_count"],
            "expert_done": receipt["expert_done"],
            "expert_failed": receipt["expert_failed"],
            "task_success_seen": receipt["task_success_seen"],
            "final_cube_lift_m": receipt["final_task_metrics"]["cube_lift"],
            "observe_before_append_count": len(receipt["observe_before_append"]),
        },
        "h5_readback": s3,
        "status": "S2_PASS_S3_PASS",
    }
    _require(result["s2_result"]["expert_done"] and not result["s2_result"]["expert_failed"],
             "S2 run receipt does not show external Expert completion")
    _require(result["s2_result"]["observe_before_append_count"] == result["s2_result"]["external_step_count"],
             "S2 run receipt lacks observe-before-append for each transition")
    output_path = run_path.parent / "s3_readback_final.json"
    result["evidence_path"] = str(output_path)
    _write_json(output_path, result)
    return result


def run(provider: str, evidence_dir: Path):
    from task_env import make_env
    from task_env.tasks.pick_cube import build_artifact, build_readiness_solution, sample_reset
    from task_env.tasks.pick_cube.task import build_runtime_source

    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_path = evidence_dir / f"{provider}_run.json"
    h5_path = evidence_dir / "pickcube_external_expert.h5"
    if run_path.exists() or h5_path.exists():
        raise FileExistsError(f"refusing to overwrite evidence under {evidence_dir}")

    artifact = build_artifact()
    reset_sample = sample_reset(artifact, TASK_SEED)
    expected_source = build_runtime_source(artifact, backend="cpu")
    expected_xml_hash = hashlib.sha256(expected_source.scene_source.xml.encode()).hexdigest()
    solution = build_readiness_solution(backend="cpu")
    env = None
    receipt = {
        "schema_version": "c05b-pickcube-external-s2-s3-probe-v1",
        "provider": provider,
        "backend": "cpu",
        "task_uid": TASK_UID,
        "task_seed": TASK_SEED,
        "artifact_identity": artifact.identity_hash,
        "expected_reset_sample": reset_sample.to_mapping(),
        "expected_reset_sample_id": reset_sample.sample_id,
        "timebase": artifact.timebase.to_mapping(),
        "success_thresholds_m": {
            "task_success": TASK_SUCCESS_LIFT_M,
            "expert_completion": EXPERT_COMPLETION_LIFT_M,
        },
        "expected_source_id": expected_source.scene_source.source_id,
        "expected_source_xml_sha256": expected_xml_hash,
        "solution_identity": solution.identity,
        "solution_version": solution.version,
        "status": "running",
        "steps": [],
        "runtime_boundaries": [],
        "observe_before_append": [],
    }
    reset_info = None
    recorder_finalized = False
    try:
        env = make_env(TASK_UID, config={"provider": provider, "backend": "cpu", "horizon": 6000})
        _require(artifact.identity_hash == ARTIFACT_HASH, "unexpected frozen PickCube Artifact")
        _require(solution.identity == SOLUTION_IDENTITY, "unexpected task-owned Solution identity")
        _require(expected_source.scene_source.source_id == SOURCE_ID, "unexpected legacy RuntimeSource ID")
        _require(expected_xml_hash == SOURCE_XML_SHA256, "legacy RuntimeSource bytes changed")

        observation, reset_info = env.reset_for_solution(solution, seed=TASK_SEED)
        boundary = reset_info["expert_execution_boundary_v1"]
        _require(boundary["task_artifact_hash"] == ARTIFACT_HASH, "reset Artifact identity mismatch")
        _require(boundary["source_id"] == SOURCE_ID, "reset source identity mismatch")
        _require(boundary["source_xml_sha256"] == SOURCE_XML_SHA256, "reset source bytes mismatch")
        _require(boundary["controller_identity"] == CONTROLLER_IDENTITY, "reset Controller identity mismatch")
        _require(boundary["solution_identity"] == solution.identity, "reset Solution identity mismatch")
        _require(boundary["reset_sample_id"] == reset_sample.sample_id, "actual reset differs from requested ResetSample")
        _require("control_application_v1" not in reset_info, "reset fabricated an applied acknowledgement")
        _require(env.state.control_step == 0 and env.state.simulation_time == 0.0,
                 "reset advanced the evaluation boundary")
        _require(env.observation_space.contains(observation), "reset observation is outside the selected space")

        reset_readiness = reset_info["control_readiness_v1"]
        reset_force = float(reset_readiness["gripper"]["closing_force_N"])
        _require(math.isfinite(reset_force) and reset_force >= 0.0, "reset R1 feedback is not finite/valid")
        reset_feedback = env.feedback.to_mapping()
        reset_memory = env.controller.memory().to_mapping()
        receipt.update({
            "actual_reset_boundary": boundary,
            "reset_readiness": reset_readiness,
            "reset_feedback": reset_feedback,
            "reset_controller_memory": reset_memory,
            "reset_state": env.state.to_mapping(),
            "reset_observation": observation,
            "episode_id": boundary["episode_id"],
        })
        env.start_recording(h5_path)

        # This observer/append instrumentation wraps the actual production
        # owners and delegates to their original methods. It proves call order
        # without substituting a fake Solution, Recorder, Runtime or feedback.
        observe_marks = []
        original_observe = solution.observe

        def observe_then_mark(*args, **kwargs):
            result = original_observe(*args, **kwargs)
            observe_marks.append({
                "control_step": int(args[4]["control_step"]),
                "solution_stage_after_observe": solution.stage,
                "solution_done_after_observe": bool(solution.done),
            })
            return result

        solution.observe = observe_then_mark
        original_append = env.recorder.append

        def append_after_observe(transition, next_boundary, **kwargs):
            expected_count = len(env.recorder.transitions) + 1
            _require(len(observe_marks) == expected_count,
                     "canonical Recorder append occurred before matching Solution.observe")
            receipt["observe_before_append"].append({
                "transition_index": expected_count - 1,
                "observed_control_step": observe_marks[-1]["control_step"],
                "append_boundary_step": next_boundary.control_step,
            })
            return original_append(transition, next_boundary, **kwargs)

        env.recorder.append = append_after_observe

        previous_info = reset_info
        previous_boundary = boundary
        initial_runtime_boundary = {
            "control_step": env.state.control_step,
            "simulation_time_s": env.state.simulation_time,
            "state": env.state.to_mapping(),
            "feedback": env.feedback.to_mapping(),
            "readiness": reset_readiness,
            "task_metrics": dict(reset_info["task_metrics"]),
            "task_success": bool(reset_info["is_success"]),
            "task_failure": bool(reset_info["task_failure"]),
            "terminated": False,
            "truncated": False,
            "boundary_identity": boundary,
        }
        receipt["runtime_boundaries"].append(initial_runtime_boundary)
        _write_json(run_path, receipt)

        for _ in range(env.horizon):
            if solution.done or solution.failed:
                break
            stage_before = solution.stage
            feedback_before = env.feedback.to_mapping()
            memory_before = env.controller.memory().to_mapping()
            previous_boundary = previous_info["expert_execution_boundary_v1"]
            observation, reward, terminated, truncated, info = env.step_with_solution(solution)
            current_boundary = info["expert_execution_boundary_v1"]
            application = info.get("control_application_v1")
            _require(application is not None, "completed external step omitted control acknowledgement")
            _require(application["request_boundary"] == previous_boundary,
                     "applied request belongs to the wrong source boundary")
            _require(application["evaluation_boundary"] == current_boundary,
                     "applied acknowledgement belongs to the wrong evaluation boundary")
            _require(application["target_identity_hash"] == application["applied_target_hash"],
                     "target/applied acknowledgement hash mismatch")
            _require(application["applied"]["target_hash"] == application["target_identity_hash"],
                     "AppliedCanonicalControl does not acknowledge the actual target")
            _require(application["task_artifact_hash"] == ARTIFACT_HASH,
                     "step acknowledgement Artifact identity mismatch")
            _require(application["controller_identity"] == CONTROLLER_IDENTITY,
                     "step acknowledgement Controller identity mismatch")
            _require(application["source_id"] == SOURCE_ID, "step acknowledgement source identity mismatch")
            _require(application["reset_sample_id"] == reset_sample.sample_id,
                     "step acknowledgement ResetSample identity mismatch")
            _require(current_boundary["episode_id"] == receipt["episode_id"],
                     "step boundary changed episode identity")
            _require(current_boundary["control_step"] == previous_boundary["control_step"] + 1,
                     "evaluation boundary is not continuous")
            _require(_one_control_interval(
                previous_boundary["simulation_time_s"],
                current_boundary["simulation_time_s"],
                artifact.timebase.control_dt,
            ), "step did not complete one 10 ms control interval")

            readiness = info["control_readiness_v1"]
            measured_closing_force = float(readiness["gripper"]["closing_force_N"])
            _require(math.isfinite(measured_closing_force) and measured_closing_force >= 0.0,
                     "post-step measured feedback is invalid")
            feedback_after = env.feedback.to_mapping()
            memory_after = env.controller.memory().to_mapping()
            lift = float(info["task_metrics"]["cube_lift"])
            _require(not info["is_success"] or lift >= TASK_SUCCESS_LIFT_M,
                     "Task success violated its frozen 0.10 m predicate")
            _require(not solution.done or (info["is_success"] and lift >= EXPERT_COMPLETION_LIFT_M),
                     "Expert completed without frozen 0.105 m endpoint and Task success")

            row = {
                "control_step": int(current_boundary["control_step"]),
                "simulation_time_s": float(current_boundary["simulation_time_s"]),
                "stage_before": stage_before,
                "stage_after_observe": solution.stage,
                "solution_done": bool(solution.done),
                "solution_failed": bool(solution.failed),
                "expert_failure_reason": getattr(solution, "failure_reason", None),
                "reward": float(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "task_success": bool(info["is_success"]),
                "task_failure": bool(info["task_failure"]),
                "cube_lift_m": lift,
                "pre_step_feedback": feedback_before,
                "post_step_feedback": feedback_after,
                "pre_step_controller_memory": memory_before,
                "post_step_controller_memory": memory_after,
                "readiness": readiness,
                "application": application,
                "state": env.state.to_mapping(),
                "boundary_identity": current_boundary,
                "observation": observation,
                "observe_mark": observe_marks[-1] if observe_marks else None,
            }
            receipt["steps"].append(row)
            receipt["runtime_boundaries"].append({
                "control_step": int(env.state.control_step),
                "simulation_time_s": float(env.state.simulation_time),
                "state": env.state.to_mapping(),
                "feedback": feedback_after,
                "readiness": readiness,
                "task_metrics": dict(info["task_metrics"]),
                "task_success": bool(info["is_success"]),
                "task_failure": bool(info["task_failure"]),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "boundary_identity": current_boundary,
            })
            previous_info = info

            if len(receipt["steps"]) % 25 == 0:
                _write_json(run_path, receipt)
                print(json.dumps({
                    "provider": provider, "control_step": env.state.control_step,
                    "stage": solution.stage, "task_success": bool(info["is_success"]),
                    "cube_lift_m": lift, "expert_done": bool(solution.done),
                }), flush=True)
            if terminated or truncated:
                break

        receipt["step_count"] = len(receipt["steps"])
        receipt["task_success_step"] = next((
            row["control_step"] for row in receipt["steps"] if row["task_success"]
        ), None)
        receipt["expert_completion_step"] = (
            receipt["steps"][-1]["control_step"] if solution.done and receipt["steps"] else None
        )
        receipt["task_success_seen"] = bool(
            receipt["steps"] and any(row["task_success"] for row in receipt["steps"])
        )
        receipt["expert_done"] = bool(solution.done)
        receipt["expert_failed"] = bool(solution.failed)
        receipt["expert_failure_reason"] = getattr(solution, "failure_reason", None)
        receipt["final_solution_stage"] = solution.stage
        receipt["final_task_metrics"] = dict(previous_info["task_metrics"])
        receipt["final_task_success"] = bool(previous_info["is_success"])
        receipt["final_flags"] = {
            "terminated": bool(receipt["steps"][-1]["terminated"]) if receipt["steps"] else False,
            "truncated": bool(receipt["steps"][-1]["truncated"]) if receipt["steps"] else False,
        }
        receipt["recording_path"] = str(h5_path)

        if not solution.done:
            receipt["status"] = "S2_FAILED"
            receipt["reason"] = solution.failure_reason or (
                "environment_terminated_or_truncated" if receipt["step_count"] else "no_step_completed"
            )
            return receipt

        _require(receipt["task_success_seen"], "Task success was never observed")
        _require(receipt["expert_completion_step"] is not None, "Expert did not report completion")
        _require(len(receipt["observe_before_append"]) == receipt["step_count"],
                 "not every real transition observed before its canonical append")

        receipt["finish_recording_result"] = env.finish_recording("expert_completed")
        recorder_finalized = True
        receipt["status"] = "S2_PASS_S3_READING"
        _write_json(run_path, receipt)

        receipt["h5_readback"] = _check_saved_trajectory(provider, receipt, h5_path)
        receipt["status"] = "S2_PASS_S3_PASS"
        return receipt
    except BaseException as error:
        receipt["status"] = "FAILED"
        receipt["failure"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "step_count": len(receipt["steps"]),
            "provider_clock": (
                {"control_step": env.state.control_step, "simulation_time_s": env.state.simulation_time}
                if env is not None and getattr(env, "state", None) is not None else None
            ),
            "recording_finalized": recorder_finalized,
            "h5_exists": h5_path.exists(),
        }
        raise
    finally:
        try:
            if env is not None:
                env.close()
        except BaseException as close_error:
            receipt["close_failure"] = {
                "type": type(close_error).__name__,
                "message": str(close_error),
                "traceback": traceback.format_exc(),
            }
            if receipt["status"] == "S2_PASS_S3_PASS":
                receipt["status"] = "CLOSE_FAILED"
        _write_json(run_path, receipt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("geophys", "mujoco"))
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--readback-existing", type=Path,
                         help="run canonical-v0 S3 against a saved S2 JSON receipt and its exact H5 file")
    args = parser.parse_args()
    if args.readback_existing is not None:
        result = _readback_existing(args.readback_existing)
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        return
    if args.provider is None or args.evidence_dir is None:
        parser.error("--provider and --evidence-dir are required unless --readback-existing is used")
    receipt = run(args.provider, args.evidence_dir)
    print(json.dumps({
        "provider": receipt["provider"],
        "status": receipt["status"],
        "step_count": receipt.get("step_count"),
        "expert_done": receipt.get("expert_done"),
        "expert_failed": receipt.get("expert_failed"),
        "h5_readback": receipt.get("h5_readback"),
        "evidence_dir": str(args.evidence_dir),
    }, indent=2, sort_keys=True), flush=True)
    if receipt["status"] != "S2_PASS_S3_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
