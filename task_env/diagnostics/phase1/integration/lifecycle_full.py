"""One-rate FULL Expert lifecycle diagnostic; no qualification promotion."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

from . import live_recording as recording_module
from .live_recording import LiveRecording
from ..frequency_grasp import run as frequency_run
from ..frequency_grasp.arm_schedule import RampedArmAudit, ramped_control_interval
from ..frequency_grasp.cadence import validate_native_cadence
from ..frequency_grasp.native import AppliedStepObserver, NativeObserver
from ..nutassembly_r5_architecture import tracking_worker as worker
from ....tasks.nut_assembly.canonical_solution_v2 import NutAssemblyStableGraspCandidateV2
from ....controllers.canonical.contracts import digest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def context(rate: int):
    """Build the exact NoSlip2/native-ramp/native-500Hz recipe with V2 lifecycle."""
    value = frequency_run.context(rate, "arm_ramp_native_grip")
    old_solution_identity = value["solution_identity"]
    old_controller_identity = value["controller_identity"]
    solution = NutAssemblyStableGraspCandidateV2(
        config=value["solution_config"],
        control_dt=value["artifact"].timebase.control_dt,
        arm_hold=value["controller"].hold,
    )
    value["solution"] = solution
    value["solution_identity"] = solution.identity
    controller = value["controller"].hold.controller
    controller.identity = digest({
        "base_controller_identity": old_controller_identity,
        "prior_solution_identity": old_solution_identity,
        "solution_identity": solution.identity,
        "lifecycle_contract": solution.lifecycle.version,
    })
    value["controller_identity"] = controller.identity
    value["recipe_identity"] = digest({
        "base_recipe": value["recipe_identity"],
        "prior_solution_identity": old_solution_identity,
        "solution_identity": solution.identity,
        "controller_identity": controller.identity,
        "completion_policy": solution.completion_policy.value,
        "lifecycle_version": solution.lifecycle.version,
    })
    return value


def run(*, provider: str, rate: int, output: Path) -> dict:
    if provider != "mujoco":
        raise ValueError("this bounded lifecycle run is MuJoCo-only")
    if rate != 100:
        raise ValueError("this requested FULL lifecycle diagnostic is pinned to 100 Hz")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    value = context(rate)
    value["_loaded_diagnostics"] = True
    value["_recording_role"] = "full_nutassembly_expert_lifecycle_v2"
    worker.CLOSE_TIME_LIMIT_S = 1.5

    observer = NativeObserver(output)
    original_snapshot = recording_module.snapshot
    original_native_audit = worker.NativeAudit
    original_runtime_readback = worker._runtime_diagnostic_readback
    original_reset = worker._reset

    def diagnostic_snapshot(owner_value, state, session_provider):
        saved = original_snapshot(owner_value, state, session_provider)
        if "_arm_schedule_memory" in owner_value:
            saved.pop("integrity_hash")
            saved["owners"]["arm_schedule"] = {
                "version": "arm-schedule-public-ack-memory-v2",
                "source_sha256": _sha(Path(frequency_run.__file__).parent / "arm_schedule.py"),
                "fields": {"last_applied_arm": {
                    "present": True,
                    "value": owner_value["_arm_schedule_memory"].last_applied_arm,
                }},
            }
            saved["integrity_hash"] = digest(saved)
        return saved

    recording_module.snapshot = diagnostic_snapshot
    worker.NativeAudit = RampedArmAudit

    def capture_required(session, session_provider, stage):
        del session_provider, stage
        try:
            return session._mj.latest
        except Exception as exc:
            observer.errors.append({"time_s": float(session._data.time),
                                    "required_contact_capture_error": repr(exc)})
            return {"available": False, "error": repr(exc)}

    worker._runtime_diagnostic_readback = capture_required

    def diagnostic_reset(owner_value, session_provider):
        result = original_reset(owner_value, session_provider)
        session = result[0]
        session._mj = AppliedStepObserver(
            session._mj, session, observer, lambda: owner_value["solution"].stage
        )
        session._diagnostic_arm_ramp_active = lambda: owner_value["solution"]._lift_released
        session._diagnostic_arm_ramp_memory = owner_value["_arm_schedule_memory"]
        session.step_control_interval = __import__("types").MethodType(
            ramped_control_interval, session
        )
        return result

    worker._reset = diagnostic_reset

    class LifecycleRecording(LiveRecording):
        def __init__(self, owner_value, *args, **kwargs):
            super().__init__(owner_value, *args, **kwargs)
            recipe = self.recorder.value["recipe"]
            recipe.update(
                factory="task_env.diagnostics.phase1.frequency_grasp.run.context",
                diagnostic_case="arm_ramp_native_grip",
                diagnostic_sample="nominal",
                source_xml_sha256=hashlib.sha256(
                    owner_value["source"].scene_source.xml.encode()
                ).hexdigest(),
                contact_profile=owner_value.get("_contact_profile"),
                qualification=False,
                arm_schedule="linear-native-ramp-after-lift-v2-public-ack-memory",
                cadence="fixed-native-500hz-v1",
            )

        def finish(self, report):
            validate_native_cadence(self.recorder.value)
            return super().finish(report)

    value["live_recording_factory"] = lambda *args: LifecycleRecording(
        *args, output=output
    )

    status = subprocess.run(
        ["git", "status", "--short", "--branch"], check=True,
        text=True, capture_output=True,
    ).stdout
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True,
    ).stdout.strip()
    worker._write(output / "launch.json", {
        "schema": "p1.8-nutassembly-lifecycle-full-launch-v1",
        "branch": "codex/p1.8-frequency-robust-grasp",
        "head": head,
        "dirty_status": status.strip().splitlines(),
        "provider": provider,
        "rate_hz": rate,
        "case": "arm_ramp_native_grip",
        "contact_solver_profile": "MuJoCo NoSlip2",
        "arm_schedule": "linear-native-ramp-after-lift-v2-public-ack-memory",
        "gripper_command_rate_hz": 500,
        "gripper_rate_semantics": "fixed-native-500hz-v1",
        "physics_dt_s": value["artifact"].timebase.physics_dt,
        "control_dt_s": value["artifact"].timebase.control_dt,
        "task_artifact_hash": value["artifact"].identity_hash,
        "solution_identity": value["solution_identity"],
        "recipe_identity": value["recipe_identity"],
        "completion_policy": value["solution"].completion_policy.value,
        "reset_sample": "canonical_reset seed from frozen profile",
        "qualification": False,
    })
    try:
        result = worker.run_loaded(value, provider, output, "FULL")
    finally:
        observer.close()
        recording_module.snapshot = original_snapshot
        worker.NativeAudit = original_native_audit
        worker._runtime_diagnostic_readback = original_runtime_readback
        worker._reset = original_reset
    expected_native_samples = (result.get("total_transitions", 0) *
                               value["artifact"].timebase.control_substeps)
    native_capture_pass = bool(
        not observer.errors and observer.count == expected_native_samples
    )
    if result.get("pass") and not native_capture_pass:
        result["pass"] = False
        result["failure_boundary"] = "native_diagnostic_capture_admission"
    result.update(
        mode="FULL",
        candidate=value["solution"].version,
        development_only=True,
        qualification_status="REVIEW_PENDING",
        provider=provider,
        outer_rate_hz=rate,
        gripper_rate_hz=500,
        equal_rate=False,
        diagnostic_case="arm_ramp_native_grip",
        contact_solver_profile="MuJoCo NoSlip2",
        arm_schedule="linear-native-ramp-after-lift-v2-public-ack-memory",
        native_gripper_cadence="fixed-native-500hz-v1",
        native_capture_count=observer.count,
        expected_native_capture_count=expected_native_samples,
        native_capture_pass=native_capture_pass,
        native_capture_errors=observer.errors,
        physics_dt_s=value["artifact"].timebase.physics_dt,
        control_dt_s=value["artifact"].timebase.control_dt,
        grasp_offset_m=list(value["solution_config"].grasp_offset),
        absolute_height_gate_enabled=False,
        force_target_N=10.0,
        native_force_cap_N=10.0,
        close_authorization_deadline_s=1.5,
        close_authorization_policy="controller_close_ready_only",
        fallback_enabled=False,
        forced_lift=False,
        task_success_definition="unchanged canonical NutAssembly task semantics",
        completion_policy=value["solution"].completion_policy.value,
        solution_identity=value["solution_identity"],
        recipe_identity=value["recipe_identity"],
        reset_sample_hash=result.get("reset_sample_hash"),
        final_task_success_valid=bool(result.get("final_task_success_valid")),
        environment_terminated=False,
        environment_truncated=False,
        formal_d0_d2_status="NOT RUN; lifecycle replay readiness check only",
        source_head=head,
        dirty_status=status.strip().splitlines(),
        package_versions={
            name: importlib.metadata.version(name)
            for name in ("numpy", "h5py", "gymnasium", "mujoco")
            if any(dist.metadata["Name"].lower() == name
                   for dist in importlib.metadata.distributions())
        },
    )
    result["full_expert_status"] = (
        "FULL_EXPERT_DEVELOPMENT_PASS" if result.get("pass") else "FULL_EXPERT_FAILED"
    )
    result["golden_acceptance_status"] = (
        "FROZEN_GOLDEN_CANDIDATE_REVIEW_PENDING" if result.get("pass") else "NOT_ELIGIBLE"
    )
    worker._write(output / "full_expert_result.json", result)
    source_paths = {
        "lifecycle_core": Path("task_env/tasks/canonical_solution_lifecycle.py"),
        "nutassembly_lifecycle_solution": Path("task_env/tasks/nut_assembly/canonical_solution_v2.py"),
        "nutassembly_v1": Path("task_env/tasks/nut_assembly/canonical_solution.py"),
        "stable_grasp_candidate_v1": Path("task_env/tasks/nut_assembly/stable_grasp_candidate.py"),
        "tracking_worker": Path(worker.__file__),
        "live_recording": Path(LiveRecording.__module__.replace(".", "/") + ".py"),
        "replay_preparation": Path("task_env/diagnostics/phase1/integration/replay_preparation.py"),
        "checkpoint_validation": Path("task_env/diagnostics/phase1/integration/checkpoint_validation.py"),
        "frequency_grasp_runner": Path(frequency_run.__file__),
        "frequency_arm_schedule": Path(frequency_run.__file__).parent / "arm_schedule.py",
        "frequency_native_cadence": Path(frequency_run.__file__).parent / "cadence.py",
        "frequency_native_observer": Path(frequency_run.__file__).parent / "native.py",
        "lifecycle_runner": Path(__file__),
    }
    manifest = {
        "schema": "p1.8-canonical-solution-lifecycle-evidence-v1",
        "branch": "codex/p1.8-frequency-robust-grasp",
        "head": head,
        "provider": provider,
        "rate_hz": rate,
        "physics_dt_s": value["artifact"].timebase.physics_dt,
        "control_dt_s": value["artifact"].timebase.control_dt,
        "task_artifact_hash": value["artifact"].identity_hash,
        "solution_identity": value["solution_identity"],
        "recipe_identity": value["recipe_identity"],
        "reset_sample_hash": result.get("reset_sample_hash"),
        "source_sha256": {name: _sha(path) for name, path in source_paths.items()},
        "result_sha256": _sha(output / "full_expert_result.json"),
        "execution_h5": result.get("live_recording", {}).get("path"),
        "execution_h5_sha256": (
            _sha(Path(result["live_recording"]["path"]))
            if result.get("live_recording", {}).get("path") else None
        ),
        "development_only": True,
        "qualification_status": "REVIEW_PENDING",
    }
    worker._write(output / "full_expert_evidence_manifest.json", manifest)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("mujoco",), default="mujoco")
    parser.add_argument("--rate", type=int, choices=(100,), default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(provider=args.provider, rate=args.rate, output=args.output)
    print(json.dumps({key: report.get(key) for key in (
        "pass", "failure_boundary", "expert_complete", "expert_failed",
        "completion_reason", "canonical_task_success", "coordinator_stage_sequence",
        "release_retreat_endpoint_pass", "live_recording",
    )}, indent=2, allow_nan=False), flush=True)
    return 0 if report.get("pass") and report.get("live_recording", {}).get("roundtrip_exact") else 1


if __name__ == "__main__":
    raise SystemExit(main())
