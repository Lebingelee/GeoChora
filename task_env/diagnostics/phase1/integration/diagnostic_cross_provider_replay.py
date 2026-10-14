"""D0/D1/D2 diagnostics for frozen GeoPhys NutAssembly action sources.

These runs are candidate-scoped development evidence. They never qualify an
Expert and never alter the source H5.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import time
from pathlib import Path
from types import MethodType

import numpy as np

from ....controllers.canonical.contracts import (
    CanonicalControlTarget,
    RequestedAction,
    digest,
)
from ....diagnostics.phase1.frequency_grasp.arm_schedule import (
    ArmRampMemory,
    RampedArmAudit,
    ramped_control_interval,
)
from ....trajectory.canonical.streaming import load_streaming
from ..nutassembly.common import observation
from ..nutassembly_r5_architecture import tracking_worker as worker
from .diagnostic_shadow import POLICY_ID
from .lifecycle_full import context


CANDIDATE = "guarded-primary-readiness-alternative-8n-v2-v5-clearance"
SOURCE_PROVIDER = "geophys"
MODES = {"d0", "d1", "d2"}
CONTACT_SAMPLE_STRIDE = 10


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _parse_diagnostics(record):
    result = {}
    # The canonical TransitionRecord calls this mapping ``expert_diagnostics``.
    # Keep a fallback for older experimental mappings without weakening the
    # required per-transition shadow-state check below.
    payload = record.get("expert_diagnostics", record.get("diagnostics", {}))
    for key, value in payload.items():
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        result[key] = value
    return result


def _first_mapping_difference(expected, actual, path=""):
    """Return the first small, actionable difference between canonical maps."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            child = f"{path}.{key}" if path else str(key)
            if key not in expected or key not in actual:
                return {"path": child, "expected": expected.get(key),
                        "actual": actual.get(key)}
            difference = _first_mapping_difference(expected[key], actual[key], child)
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return {"path": path, "expected_length": len(expected),
                    "actual_length": len(actual)}
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = _first_mapping_difference(left, right, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if expected != actual:
        return {"path": path, "expected": expected, "actual": actual}
    return None


def _quat_angle(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na <= 0 or nb <= 0:
        return None
    dot = min(1.0, max(-1.0, abs(float(np.dot(a / na, b / nb)))))
    return float(2.0 * math.acos(dot))


def _state_delta(source, target):
    """Provider-neutral first-divergence projection from canonical states."""
    joints = source.get("joint_position", {})
    target_joints = target.get("joint_position", {})
    common_joints = sorted(set(joints) & set(target_joints))
    joint_max = max((abs(float(joints[k]) - float(target_joints[k]))
                     for k in common_joints), default=0.0)
    source_poses, target_poses = source.get("pose_world", {}), target.get("pose_world", {})
    result = {"max_joint_position_delta": float(joint_max),
              "joint_position_units": "source canonical joint units",
              "ee_position_delta_m": None, "ee_rotation_delta_rad": None,
              "nut_position_delta_m": None, "nut_rotation_delta_rad": None,
              "nut_relative_ee_translation_delta_m": None}
    for key, prefix in (("panda-v1/ee", "ee"), ("square-nut-v1", "nut")):
        if key in source_poses and key in target_poses:
            s, t = source_poses[key], target_poses[key]
            sp = np.asarray(s["position"], dtype=float)
            tp = np.asarray(t["position"], dtype=float)
            result[f"{prefix}_position_delta_m"] = float(np.linalg.norm(sp - tp))
            result[f"{prefix}_rotation_delta_rad"] = _quat_angle(
                s["quaternion_wxyz"], t["quaternion_wxyz"]
            )
    if all(result.get(k) is not None for k in (
        "ee_position_delta_m", "nut_position_delta_m"
    )):
        result["nut_relative_ee_translation_delta_m"] = abs(
            result["nut_position_delta_m"] - result["ee_position_delta_m"]
        )
        # Vector relative displacement is more informative than the scalar
        # difference above; keep a separate exact norm when both poses exist.
        sn = np.asarray(source_poses["square-nut-v1"]["position"], dtype=float)
        se = np.asarray(source_poses["panda-v1/ee"]["position"], dtype=float)
        tn = np.asarray(target_poses["square-nut-v1"]["position"], dtype=float)
        te = np.asarray(target_poses["panda-v1/ee"]["position"], dtype=float)
        result["nut_relative_ee_translation_delta_m"] = float(
            np.linalg.norm((sn - se) - (tn - te))
        )
    return result


def _metric_predicates(metrics):
    return {k: v for k, v in metrics.items() if isinstance(v, bool)}


def _swap_bytes():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("SwapTotal:"):
                total = int(line.split()[1])
            elif line.startswith("SwapFree:"):
                free = int(line.split()[1])
        return {"total_bytes": total * 1024, "free_bytes": free * 1024,
                "used_bytes": (total - free) * 1024}
    except (OSError, UnboundLocalError, ValueError):
        return None


def _setup_target(rate, provider):
    value = context(rate, CANDIDATE, provider=provider)
    original_audit = worker.NativeAudit
    worker.NativeAudit = RampedArmAudit
    try:
        session, audit, sample, realized, state, feedback, controller = worker._reset(
            value, provider
        )
    except Exception:
        worker.NativeAudit = original_audit
        raise
    value["_arm_schedule_memory"] = ArmRampMemory()
    ramp_active = {"value": False}
    session._diagnostic_arm_ramp_active = lambda: bool(ramp_active["value"])
    session._diagnostic_arm_ramp_memory = value["_arm_schedule_memory"]
    session.step_control_interval = MethodType(ramped_control_interval, session)
    value["_diagnostic_replay_ramp_active"] = ramp_active
    return value, session, audit, sample, realized, state, feedback, controller, original_audit


def _reset_report_fields(source, target_provider, mode, source_path):
    source_result_path = Path(source_path).parent / "full_expert_result.json"
    source_result = (json.loads(source_result_path.read_text())
                     if source_result_path.exists() else {})
    report = {
        "schema": "p1.8-diagnostic-cross-provider-replay-v1",
        "mode": mode.upper(),
        "source_role": "DIAGNOSTIC_ACTION_SOURCE",
        "source_provider": SOURCE_PROVIDER,
        "target_provider": target_provider,
        "source_h5": str(source_path),
        "source_h5_sha256": _sha(source_path),
        "source_logical_hash": digest(source),
        "source_recipe_identity": source["recipe"].get("recipe_identity"),
        "diagnostic_execution_mode": source["recipe"].get("diagnostic_execution_mode"),
        "source_solution_identity": source["metadata"].get("expert_identity"),
        "source_controller_identity": source["metadata"].get("controller_identity"),
        "outer_rate_hz": round(1.0 / source["metadata"]["timebase"]["control_dt"]),
        "physics_dt_s": source["metadata"]["timebase"]["physics_dt"],
        "control_substeps": source["metadata"]["timebase"]["control_substeps"],
        "source_transitions": len(source["transitions"]),
        "source_native_steps": sum(t["interval"]["native_step_count"]
                                    for t in source["transitions"]),
        "task_success": False,
        "environment_terminated": None,
        "environment_truncated": None,
        "environment_lifecycle_signal": (
            "CanonicalRuntimeSession has no Gym terminated/truncated return; "
            "provider execution stop is reported independently"
        ),
        "first_execution_divergence": None,
        "first_physical_divergence": None,
        "first_significant_physical_divergence": None,
        "physical_divergence_thresholds": {
            "position_m": 1e-6,
            "rotation_rad": 1e-6,
            "joint_units": 1e-6,
            "first_nonzero_epsilon": 1e-12,
        },
        "execution_valid": False,
        "task_outcome": "NOT_RUN",
        "physical_task_outcome": "NOT_RUN",
        "diagnostic_sequence_completed": bool(
            source_result.get("diagnostic_sequence_complete", False)
        ),
        "source_result_sha256": (_sha(source_result_path)
                                 if source_result_path.exists() else None),
        "expert_qualification_pass": False,
        "contact_sampling": {
            "source": "full boundary contact sidecar from source run",
            "target_stride_boundaries": CONTACT_SAMPLE_STRIDE,
            "provider_pair_level_equivalence_assumed": False,
        },
    }
    return report


def replay(source_path: Path, output_path: Path, *, mode: str,
           target_provider: str) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    if target_provider not in {"geophys", "mujoco"}:
        raise ValueError("target provider must be geophys or mujoco")
    source_path, output_path = Path(source_path), Path(output_path)
    started = time.perf_counter()
    swap_before = _swap_bytes()
    source_file_bytes = source_path.stat().st_size
    source = load_streaming(source_path)
    rate = round(1.0 / source["metadata"]["timebase"]["control_dt"])
    report = _reset_report_fields(source, target_provider, mode, source_path)
    if source["metadata"]["execution"]["physics_provider"] != SOURCE_PROVIDER:
        raise ValueError("campaign source must be GeoPhys")
    recipe = source["recipe"]
    if recipe.get("diagnostic_execution_mode") != POLICY_ID:
        raise ValueError("source is not marked with diagnostic shadow policy")
    if recipe.get("episode_role") != "DIAGNOSTIC_ACTION_SOURCE":
        raise ValueError("source role is not DIAGNOSTIC_ACTION_SOURCE")
    if recipe.get("solution_version") != (
        "nutassembly-r5-v5-clearance-primary-readiness-"
        "alternative-8n-guarded-v2"
    ):
        raise ValueError("source candidate identity does not match frozen V5/guarded route")
    if len(source["boundaries"]) != len(source["transitions"]) + 1:
        raise ValueError("source must preserve T/T+1 boundaries")
    diag_states = []
    for index, transition in enumerate(source["transitions"]):
        diagnostics = _parse_diagnostics(transition["record"])
        shadow = diagnostics.get("diagnostic_shadow_state")
        if not isinstance(shadow, dict) or shadow.get("policy_id") != POLICY_ID:
            raise ValueError(f"diagnostic shadow state missing at transition {index}")
        diag_states.append(shadow)
    report["diagnostic_shadow_state_count"] = len(diag_states)
    report["source_diagnostic_stage_sequence"] = list(dict.fromkeys(
        state["stage"] for state in diag_states
    ))
    report["source_diagnostic_stage_sequence_matches_sidecar"] = True

    target = None
    session = audit = None
    original_audit = worker.NativeAudit
    trace = []
    contacts = []
    checked = 0
    native_steps = 0
    max_delta = {"ee_position_delta_m": 0.0, "ee_rotation_delta_rad": 0.0,
                 "nut_position_delta_m": 0.0, "nut_rotation_delta_rad": 0.0,
                 "max_joint_position_delta": 0.0,
                 "nut_relative_ee_translation_delta_m": 0.0}
    source_initial = source["boundaries"][0]["record"]["state"]
    try:
        (target, session, audit, sample, realized, state, feedback, controller,
         original_audit) = _setup_target(rate, target_provider)
        artifact = target["artifact"]
        if sample.to_mapping() != source["metadata"]["reset_sample"]:
            raise ValueError("ResetSample identity mismatch")
        if artifact.identity_hash != source["metadata"]["task_artifact_hash"]:
            raise ValueError("TaskArtifact identity mismatch")
        if target["controller_identity"] != source["metadata"]["controller_identity"]:
            raise ValueError("controller identity mismatch")
        if target["solution_identity"] != source["metadata"]["expert_identity"]:
            raise ValueError("Expert identity mismatch")
        report["target_provider_build_identity"] = worker.provider_build_identity(target_provider)
        report["target_reset_sample_hash"] = sample.identity_hash
        report["source_reset_sample_hash"] = source["metadata"]["reset_sample"].get("identity_hash")
        report["target_task_artifact_hash"] = artifact.identity_hash
        report["target_controller_identity"] = target["controller_identity"]
        report["target_solution_identity"] = target["solution_identity"]

        def compare_boundary(boundary_index, source_state, target_state, metrics=None):
            nonlocal report
            delta = _state_delta(source_state, target_state.to_mapping())
            for key, val in delta.items():
                if key in max_delta and val is not None:
                    max_delta[key] = max(max_delta[key], float(val))
            values = [delta.get("ee_position_delta_m"), delta.get("nut_position_delta_m"),
                      delta.get("ee_rotation_delta_rad"), delta.get("nut_rotation_delta_rad"),
                      delta.get("max_joint_position_delta")]
            nonzero = any(v is not None and v > 1e-12 for v in values)
            significant = any(
                isinstance(v, (int, float))
                and v > report["physical_divergence_thresholds"].get(key, 1e-6)
                for key, v in delta.items()
            )
            if nonzero and report["first_physical_divergence"] is None:
                report["first_physical_divergence"] = {
                    "control_boundary": boundary_index,
                    "simulation_time_s": float(target_state.simulation_time),
                    "delta": delta,
                }
            if significant and report["first_significant_physical_divergence"] is None:
                report["first_significant_physical_divergence"] = {
                    "control_boundary": boundary_index,
                    "simulation_time_s": float(target_state.simulation_time),
                    "delta": delta,
                }
            if metrics is not None:
                source_metrics = source["boundaries"][boundary_index]["task_metrics_raw"]
                target_predicates = _metric_predicates(metrics)
                source_predicates = _metric_predicates(source_metrics)
                if target_predicates != source_predicates and report.get(
                    "first_task_predicate_divergence"
                ) is None:
                    report["first_task_predicate_divergence"] = {
                        "control_boundary": boundary_index,
                        "simulation_time_s": float(target_state.simulation_time),
                        "source": source_predicates,
                        "target": target_predicates,
                    }

        # Boundary zero matters: materialization divergence can precede the
        # first control application.
        compare_boundary(0, source_initial, state)

        if mode == "d1":
            for index, transition in enumerate(source["transitions"]):
                interval = transition["interval"]
                active = bool(diag_states[index].get("lift_motion_released", False))
                target["_diagnostic_replay_ramp_active"]["value"] = active
                before = session.snapshot()
                substeps = interval["substeps"]
                endpoint_target = CanonicalControlTarget.from_mapping(substeps[-1]["target"])
                # D1 audits the frozen source ramp. On a different provider,
                # its acknowledged target history can differ from the source
                # even though the streamed target sequence is unchanged.
                if index > 0:
                    initial_arm = dict(source["transitions"][index - 1]["interval"]
                                       ["substeps"][-1]["applied"]["arm_servo_position"])
                else:
                    initial_arm = dict(substeps[0]["target"]["arm_servo_position"])
                audit._diagnostic_plan = (
                    initial_arm, dict(endpoint_target.arm_servo_position), active
                )
                audit.begin_inner_interval(before)
                session._inner_interval_active = True
                try:
                    for subindex, substep in enumerate(substeps):
                        command = CanonicalControlTarget.from_mapping(substep["target"])
                        if command.task_artifact_hash != artifact.identity_hash:
                            raise ValueError("frozen target TaskArtifact identity mismatch")
                        ack = session.apply_control(command)
                        if (ack.target_hash != command.identity_hash
                                or ack.provider_name != target_provider
                                or ack.gripper_force_limit_N != command.gripper.force_limit_N):
                            raise ValueError("target provider applied-control acknowledgment mismatch")
                        audit.execute_inner_substep(command, session._step_physics_once)
                        target["_arm_schedule_memory"].last_applied_arm = dict(
                            ack.arm_servo_position
                        )
                        native_steps += 1
                finally:
                    session._inner_interval_active = False
                session._control_step += 1
                state = session.snapshot()
                audit.complete_inner_interval(state)
                feedback = session.control_feedback(state)
                _obs, info, _evaluation = observation(state, artifact)
                checked += 1
                if index % CONTACT_SAMPLE_STRIDE == 0 or index == len(source["transitions"]) - 1:
                    try:
                        contacts.append({"control_boundary": index + 1,
                                         "simulation_time_s": state.simulation_time,
                                         "stage": diag_states[index].get("stage"),
                                         "contact": worker._contact_diagnostics(session,
                                                                              target_provider)})
                    except Exception as exc:
                        contacts.append({"control_boundary": index + 1,
                                         "error": f"{type(exc).__name__}: {exc}"})
                compare_boundary(index + 1,
                                 source["boundaries"][index + 1]["record"]["state"],
                                 state, info.get("task_metrics", {}))
                trace.append({"control_boundary": index + 1,
                              "simulation_time_s": state.simulation_time,
                              "stage": diag_states[index].get("stage"),
                              "task_metrics": info.get("task_metrics", {})})
        else:
            for index, transition in enumerate(source["transitions"]):
                source_record = transition["record"]
                request = RequestedAction.from_mapping(source_record["requested_action"])
                canonical, held_target = controller.compute(state, feedback, request)
                if mode == "d0":
                    canonical_difference = _first_mapping_difference(
                        source_record["canonical_action"], canonical.to_mapping()
                    )
                    if canonical_difference is not None:
                        report["first_execution_divergence"] = {
                            "transition": index,
                            "native_substep": None,
                            "kind": "canonical_action",
                            "first_field_difference": canonical_difference,
                        }
                        raise ValueError(
                            f"source canonical-action reconstruction mismatch at {index}"
                        )
                active = bool(diag_states[index].get("lift_motion_released", False))
                target["_diagnostic_replay_ramp_active"]["value"] = active
                applied_substeps = []

                def capture_substep(subindex, substate, subfeedback, command, ack, diagnostics):
                    applied_substeps.append({"target": command.to_mapping(),
                                             "applied": ack.to_mapping(),
                                             "substep_index": subindex})

                state, applied_target, applied, inner_rows = session.step_control_interval(
                    held_target, controller, audit=audit,
                    interval_observer=capture_substep,
                )
                feedback = session.control_feedback(state)
                native_steps += len(inner_rows)
                if mode == "d0":
                    expected_substeps = transition["interval"]["substeps"]
                    if len(applied_substeps) != len(expected_substeps):
                        report["first_execution_divergence"] = {
                            "transition": index, "native_substep": None,
                            "kind": "native_substep_count",
                            "expected": len(expected_substeps),
                            "actual": len(applied_substeps),
                        }
                        raise ValueError(f"source native-substep count mismatch at {index}")
                    for subindex, (actual, expected) in enumerate(zip(applied_substeps,
                                                                      expected_substeps)):
                        target_difference = _first_mapping_difference(
                            expected["target"], actual["target"]
                        )
                        if target_difference is not None:
                            report["first_execution_divergence"] = {
                                "transition": index, "native_substep": subindex,
                                "kind": "native_controller_target",
                                "first_field_difference": target_difference,
                            }
                            raise ValueError(f"source controller target mismatch at {index}:{subindex}")
                        applied_difference = _first_mapping_difference(
                            expected["applied"], actual["applied"]
                        )
                        if applied_difference is not None:
                            report["first_execution_divergence"] = {
                                "transition": index, "native_substep": subindex,
                                "kind": "applied_control_acknowledgment",
                                "first_field_difference": applied_difference,
                            }
                            raise ValueError(f"source applied-control mismatch at {index}:{subindex}")
                _obs, info, _evaluation = observation(state, artifact)
                checked += 1
                if index % CONTACT_SAMPLE_STRIDE == 0 or index == len(source["transitions"]) - 1:
                    try:
                        contacts.append({"control_boundary": index + 1,
                                         "simulation_time_s": state.simulation_time,
                                         "stage": diag_states[index].get("stage"),
                                         "contact": worker._contact_diagnostics(session,
                                                                              target_provider)})
                    except Exception as exc:
                        contacts.append({"control_boundary": index + 1,
                                         "error": f"{type(exc).__name__}: {exc}"})
                compare_boundary(index + 1,
                                 source["boundaries"][index + 1]["record"]["state"],
                                 state, info.get("task_metrics", {}))
                trace.append({"control_boundary": index + 1,
                              "simulation_time_s": state.simulation_time,
                              "stage": diag_states[index].get("stage"),
                              "task_metrics": info.get("task_metrics", {})})

        final_metrics = trace[-1]["task_metrics"] if trace else {}
        task_success = bool(final_metrics.get("task_success", False))
        inserted = bool(final_metrics.get("inserted_on_peg", False))
        released = bool(final_metrics.get("released_nut", False))
        report.update(
            transitions_replayed=checked,
            native_steps_replayed=native_steps,
            target_native_audit_count=audit.count,
            target_native_audit_boundaries=len(audit.boundaries),
            target_native_audit_errors=[],
            source_stage_sequence=report["source_diagnostic_stage_sequence"],
            task_success=task_success,
            inserted_on_peg=inserted,
            released_nut=released,
            final_task_metrics=final_metrics,
            task_outcome=("PHYSICAL_TASK_SUCCESS" if task_success
                          else "PHYSICAL_TASK_FAILED"),
            physical_task_outcome=("PHYSICAL_TASK_SUCCESS" if task_success
                                   else "PHYSICAL_TASK_FAILED"),
            execution_valid=(checked == len(source["transitions"])
                             and native_steps == report["source_native_steps"]
                             and audit.count == report["source_native_steps"]),
            expert_qualification_pass=False,
            physical_divergence_maxima=max_delta,
            target_contact_samples=len(contacts),
            target_contact_sidecar=f"{output_path.stem}_contacts.json",
            runtime_stop_reason="SOURCE_ACTION_SEQUENCE_EXHAUSTED",
            target_runtime_error=None,
        )
        if mode == "d0":
            report["source_reconstruction"] = {
                "canonical_action_reconstruction": "EXACT",
                "native_target_stream_reconstruction": "EXACT",
                "diagnostic_shadow_states_checked": len(diag_states),
                "original_expert_failure_preserved": True,
                "scope": "same-provider source reconstruction from recorded RequestActions; diagnostic schedule is replayed, not regenerated from task success",
            }
        report["status"] = (
            "EXECUTION_VALID_TASK_SUCCESS" if report["execution_valid"] and task_success
            else "EXECUTION_VALID_TASK_FAILED" if report["execution_valid"]
            else "EXECUTION_INVALID"
        )
        report["replay_validity"] = "VALID" if report["execution_valid"] else "INVALID"
        report["timebase"] = source["metadata"]["timebase"]
        report["source_file_bytes"] = source_file_bytes
        report["source_logical_payload_bytes"] = source.get("logical_bytes")
        report["source_hash"] = report["source_h5_sha256"]
        report["logical_source_hash"] = report["source_logical_hash"]
        report["target_trace"] = trace
        report["contacts"] = contacts
    except Exception as exc:
        report.update(
            status="REPLAY_ERROR",
            replay_validity="INVALID",
            execution_valid=False,
            task_outcome="NOT_ESTABLISHED",
            physical_task_outcome="NOT_ESTABLISHED",
            target_runtime_error=f"{type(exc).__name__}: {exc}",
            first_execution_divergence=report.get("first_execution_divergence") or {
                "transition": checked, "error": f"{type(exc).__name__}: {exc}"
            },
            transitions_replayed=checked,
            native_steps_replayed=native_steps,
        )
        if state is not None and checked < len(source.get("boundaries", [])):
            try:
                source_state = source["boundaries"][checked]["record"]["state"]
                divergence = _state_delta(source_state, state.to_mapping())
                report["physical_state_at_execution_divergence"] = {
                    "control_boundary": checked,
                    "delta": divergence,
                }
            except (KeyError, TypeError, AttributeError):
                pass
    finally:
        if audit is not None:
            try:
                audit.close()
            except Exception:
                pass
        if session is not None:
            session.close()
        worker.NativeAudit = original_audit
    report.update(
        wall_time_s=time.perf_counter() - started,
        peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
        swap_before=swap_before,
        swap_after=_swap_bytes(),
        target_provider_build_identity=(report.get("target_provider_build_identity")
                                        or worker.provider_build_identity(target_provider)),
        diagnostic_only=True,
        qualification_status="NOT_QUALIFIED_DIAGNOSTIC_REPLAY",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n")
    if contacts:
        (output_path.parent / f"{output_path.stem}_contacts.json").write_text(
            json.dumps(contacts, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(MODES), required=True)
    parser.add_argument("--target-provider", choices=("geophys", "mujoco"), required=True)
    args = parser.parse_args()
    result = replay(args.source, args.output, mode=args.mode,
                    target_provider=args.target_provider)
    print(json.dumps({k: result.get(k) for k in (
        "status", "replay_validity", "execution_valid", "physical_task_outcome",
        "transitions_replayed", "native_steps_replayed", "first_execution_divergence",
        "first_significant_physical_divergence", "wall_time_s", "peak_rss_bytes",
    )}, indent=2, allow_nan=False), flush=True)
    return 0 if result.get("execution_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
