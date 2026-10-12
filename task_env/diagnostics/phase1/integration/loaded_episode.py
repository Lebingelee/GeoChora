"""Run frozen 10 N NutAssembly G0/T1/full expert using the canonical live path.

This is an opt-in task-local diagnostic entry.  It uses the same +1 mm,
height-gate-disabled recipe as ``grasp_height_probe`` and does not modify the
shared controllers, planner, physics configuration, or task semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from .grasp_height_probe import context
from .live_recording import LiveRecording
from ..nutassembly_r5_architecture import tracking_worker as worker


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _module_hashes() -> dict[str, str]:
    from ....controllers.canonical import production_r3, gripper_execution
    from ....tasks.nut_assembly import canonical_solution, stable_grasp_candidate
    from . import height_gate_ablation

    paths = {
        "tracking_worker": Path(worker.__file__),
        "loaded_episode_runner": Path(__file__),
        "live_recording": Path(LiveRecording.__module__.replace(".", "/") + ".py"),
        "grasp_height_probe": Path(__import__("task_env.diagnostics.phase1.integration.grasp_height_probe", fromlist=["__file__"]).__file__),
        "height_gate_ablation": Path(height_gate_ablation.__file__),
        "stable_grasp_candidate": Path(stable_grasp_candidate.__file__),
        "canonical_solution": Path(canonical_solution.__file__),
        "controller_r3": Path(production_r3.__file__),
        "gripper_execution": Path(gripper_execution.__file__),
    }
    return {name: _sha(path) for name, path in paths.items()}


def run(mode: str, provider: str, rate: int, output: Path) -> dict:
    if mode not in {"G0", "T1", "FULL"}:
        raise ValueError("mode must be G0, T1, or FULL")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    value = context(rate)
    value["_loaded_diagnostics"] = True
    value["_recording_role"] = {
        "G0": "g0_regression", "T1": "t1_loaded_transport", "FULL": "full_nutassembly_expert"
    }[mode]
    value["live_recording_factory"] = lambda *args: LiveRecording(*args, output=output)

    # The already-authorized 1.5 s fail-closed deadline is the only close
    # deadline used here.  The stable-grasp coordinator still authorizes only
    # controller_close_ready; no fallback or forced lift is enabled.
    worker.CLOSE_TIME_LIMIT_S = 1.5
    report = worker.run_loaded(value, provider, output, mode)
    report.update(
        mode=mode,
        candidate="nutassembly-r5-stable-grasp-10n-plus1mm-height-gate-disabled",
        development_only=True,
        qualification_status="REVIEW_PENDING",
        provider=provider,
        outer_rate_hz=rate,
        gripper_rate_hz=rate,
        equal_rate=True,
        physics_dt_s=value["artifact"].timebase.physics_dt,
        control_dt_s=value["artifact"].timebase.control_dt,
        grasp_offset_m=list(value["solution_config"].grasp_offset),
        absolute_height_gate_enabled=False,
        force_target_N=10.0,
        native_force_cap_N=10.0,
        force_deadband_N=1.0,
        close_authorization_deadline_s=1.5,
        close_authorization_policy="controller_close_ready_only",
        fallback_enabled=False,
        forced_lift=False,
        post_authorization_regulated_hold_s=0.1,
        readiness_stable_window_s=0.1,
        pose_stability_minimum_wait_s=0.5,
        verify_lift_target_offset_m=0.1,
        capture_translation_limit_m=worker.CAPTURE_POSITION_LIMIT_M,
        capture_rotation_limit_rad=worker.CAPTURE_ROTATION_LIMIT_RAD,
        pose_endpoint_position_limit_m=worker.POSE_POSITION_LIMIT_M,
        pose_endpoint_rotation_limit_rad=worker.POSE_ROTATION_LIMIT_RAD,
        solution_events=list(value["solution"].events),
        task_artifact_hash=value["artifact"].identity_hash,
        reset_sample_hash=report.get("reset_sample_hash"),
        recipe_identity=value["recipe_identity"],
        solution_identity=value["solution_identity"],
        controller_identity=value["controller_identity"],
        profile_sha256=value["profile_sha256"],
        dynamic_profile_sha256=value["dynamic_profile_sha256"],
        source_module_sha256=_module_hashes(),
        package_versions={
            name: importlib.metadata.version(name)
            for name in ("numpy", "h5py", "gymnasium", "mujoco")
            if any(dist.metadata["Name"].lower() == name for dist in importlib.metadata.distributions())
        },
    )
    if mode == "G0":
        report["g0_status"] = "G0_REGRESSION_PASS" if report.get("pass") else "G0_REGRESSION_FAIL"
        report["full_task_success_claimed"] = False
    elif mode == "T1":
        report["t1_status"] = "T1_DEVELOPMENT_PASS" if report.get("pass") else "T1_PARTIAL_OR_NO_GO"
        report["full_task_success_claimed"] = False
    else:
        report["full_expert_status"] = "FULL_EXPERT_DEVELOPMENT_PASS" if report.get("pass") else "FULL_EXPERT_FAILED"
        report["golden_acceptance_status"] = "FROZEN_GOLDEN_CANDIDATE_REVIEW_PENDING" if report.get("pass") else "NOT_ELIGIBLE"
    worker._write(output / "report.json", report)
    worker._write(output / "provenance.json", {
        "schema": "p1.8-nutassembly-loaded-run-provenance-v1",
        "mode": mode,
        "provider": provider,
        "rate_hz": rate,
        "report_sha256": _sha(output / "report.json"),
        "execution_h5": report.get("live_recording", {}).get("path"),
        "execution_h5_sha256": (_sha(Path(report["live_recording"]["path"]))
                                 if report.get("live_recording", {}).get("path") else None),
        "development_only": True,
        "qualification_status": "REVIEW_PENDING",
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("G0", "T1", "FULL"), required=True)
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True)
    parser.add_argument("--rate", type=int, choices=(500, 100, 50), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.mode, args.provider, args.rate, args.output)
    summary = {key: report.get(key) for key in (
        "mode", "probe", "provider", "outer_rate_hz", "pass", "failure_boundary",
        "close_authorization", "verify_lift_pass", "max_capture_position_drift_m",
        "max_capture_rotation_drift_rad", "coordinator_stage_sequence",
        "canonical_task_success", "live_recording",
    )}
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
    return 0 if report.get("pass") and report.get("live_recording", {}).get("roundtrip_exact") else 1


if __name__ == "__main__":
    raise SystemExit(main())
