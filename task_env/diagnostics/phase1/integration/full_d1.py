"""Replay every recorded native MuJoCo control application from a FULL source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ....controllers.canonical.contracts import CanonicalControlTarget
from ....trajectory.canonical.streaming import load_streaming as load
from ....trajectory.canonical.execution import expand_snapshot
from ..nutassembly.common import observation
from ..nutassembly_r5_architecture import tracking_worker as worker
from .lifecycle_full import context


def replay_full(path: Path, output: Path) -> dict:
    path, output = Path(path), Path(output)
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    recorded = load(path)
    hz = round(1.0 / recorded["metadata"]["timebase"]["control_dt"])
    provider = recorded["metadata"]["execution"]["physics_provider"]
    if provider != "mujoco":
        raise ValueError("D1 scope is same-provider MuJoCo only")
    if recorded["recipe"].get("solution_version") != (
        "nutassembly-r5-v5-clearance-primary-readiness-"
        "alternative-8n-guarded-v2"
    ):
        raise ValueError("full guarded-authorization source required")
    value = context(hz, "guarded-primary-readiness-alternative-8n-v2-v5-clearance")
    if value["artifact"].identity_hash != recorded["metadata"]["task_artifact_hash"]:
        raise ValueError("TaskArtifact identity mismatch")
    if value["controller_identity"] != recorded["metadata"]["controller_identity"]:
        raise ValueError("controller identity mismatch")
    if value["solution_identity"] != recorded["metadata"]["expert_identity"]:
        raise ValueError("Canonical Solution identity mismatch")
    if value["recipe_identity"] != recorded["recipe"].get("recipe_identity"):
        raise ValueError("execution recipe identity mismatch")

    session = audit = None
    first_divergence = None
    target_mismatches = []
    state_mismatches = []
    task_mismatches = []
    native_steps = 0
    checked_transitions = 0
    stage_order = []
    try:
        session, audit, sample, realized, state, feedback, _controller = worker._reset(value, provider)
        if sample.to_mapping() != recorded["metadata"]["reset_sample"]:
            raise ValueError("ResetSample mismatch")
        if state.to_mapping() != recorded["boundaries"][0]["record"]["state"]:
            raise ValueError("realized initial state mismatch")
        for index, transition in enumerate(recorded["transitions"]):
            if first_divergence is not None:
                break
            interval = transition["interval"]
            record = transition["record"]
            if interval["control_step"] != index:
                first_divergence = {"boundary": index, "phase": "interval_index"}
                break
            stage = record["expert_stage"]
            if not stage_order or stage_order[-1] != stage:
                stage_order.append(stage)
            before = session.snapshot()
            session._inner_interval_active = True
            try:
                for subindex, substep in enumerate(interval["substeps"]):
                    target = CanonicalControlTarget.from_mapping(substep["target"])
                    expected_ack = substep["applied"]
                    actual_ack = session.apply_control(target)
                    if actual_ack.to_mapping() != expected_ack:
                        target_mismatches.append({
                            "control_step": index,
                            "native_substep": subindex,
                            "field": "applied_acknowledgment",
                        })
                        first_divergence = target_mismatches[-1]
                        break
                    audit.active = target
                    audit.expected_hash = target.identity_hash
                    session._step_physics_once()
                    audit.active = None
                    native_steps += 1
                if first_divergence is not None:
                    break
            finally:
                audit.active = None
                session._inner_interval_active = False
            session._control_step += 1
            after = session.snapshot()
            expected_state = recorded["boundaries"][index + 1]["record"]["state"]
            if after.to_mapping() != expected_state:
                state_mismatches.append({
                    "boundary": index + 1,
                    "max_joint_error": max(
                        abs(after.joint_position[name] - expected_state["joint_position"][name])
                        for name in after.joint_position
                    ),
                    "max_pose_position_error_m": max(
                        max(abs(a - b) for a, b in zip(after.pose_world[name].position,
                            expected_state["pose_world"][name]["position"]))
                        for name in after.pose_world
                    ),
                })
                first_divergence = {"boundary": index + 1, "phase": "physics_state"}
                break
            actual_feedback = session.control_feedback(after)
            expected_feedback = recorded["boundaries"][index + 1]["record"]["feedback"]
            if actual_feedback.to_mapping() != expected_feedback:
                first_divergence = {"boundary": index + 1, "phase": "canonical_feedback"}
                break
            _obs, info, _evaluation = observation(after, value["artifact"])
            if info["task_metrics"] != recorded["boundaries"][index + 1]["task_metrics_raw"]:
                task_mismatches.append({"boundary": index + 1, "phase": "task_metrics"})
                first_divergence = task_mismatches[-1]
                break
            checked_transitions += 1
            state = after
        last_boundary = recorded["boundaries"][checked_transitions]
        final_task_success = bool(last_boundary["record"]["is_success"])
        final_snapshot = expand_snapshot(recorded["boundaries"][-1]["owners"], recorded["blobs"])
        final_owner = final_snapshot["owners"]["coordinator"]["fields"]["lifecycle_state"]["value"]
        full_stream = checked_transitions == len(recorded["transitions"])
        lifecycle_completed = final_owner.get("status") == "completed"
        expected_native_steps = sum(
            transition["interval"]["native_step_count"]
            for transition in recorded["transitions"]
        )
        passed = bool(full_stream and first_divergence is None and final_task_success
                      and lifecycle_completed and native_steps == expected_native_steps)
        result = {
            "schema": "p1.8-full-d1-recorded-native-control-replay-v1",
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "provider": provider,
            "outer_rate_hz": hz,
            "source_execution_h5": str(path),
            "source_execution_h5_sha256": source_sha,
            "transitions_expected": len(recorded["transitions"]),
            "transitions_replayed": checked_transitions,
            "native_steps_expected": sum(t["interval"]["native_step_count"]
                                          for t in recorded["transitions"]),
            "native_steps_replayed": native_steps,
            "ordered_stage_sequence": stage_order,
            "final_task_success": final_task_success,
            "final_lifecycle_status": final_owner.get("status"),
            "target_mismatches": target_mismatches[:20],
            "state_mismatches": state_mismatches[:20],
            "task_mismatches": task_mismatches[:20],
            "first_divergence": first_divergence,
            "scope": "same-provider full native target stream; adaptive controller not recomputed",
        }
    except Exception as exc:
        result = {
            "schema": "p1.8-full-d1-recorded-native-control-replay-v1",
            "status": "ERROR",
            "passed": False,
            "provider": provider,
            "outer_rate_hz": hz,
            "source_execution_h5": str(path),
            "source_execution_h5_sha256": source_sha,
            "transitions_expected": len(recorded["transitions"]),
            "transitions_replayed": checked_transitions,
            "native_steps_replayed": native_steps,
            "first_divergence": first_divergence or {
                "boundary": checked_transitions,
                "phase": "replay_exception",
                "error": f"{type(exc).__name__}: {exc}",
            },
        }
    finally:
        if audit is not None:
            audit.close()
        if session is not None:
            session.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay_full(args.input, args.output)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
