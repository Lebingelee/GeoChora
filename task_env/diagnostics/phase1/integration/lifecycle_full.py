"""One-rate FULL Expert lifecycle diagnostic; no qualification promotion."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
from dataclasses import replace
import xml.etree.ElementTree as ET

import numpy as np

from . import live_recording as recording_module
from .live_recording import LiveRecording
from ..frequency_grasp import run as frequency_run
from ..frequency_grasp.arm_schedule import RampedArmAudit, ramped_control_interval
from ..frequency_grasp.cadence import validate_native_cadence
from ..frequency_grasp.native import AppliedStepObserver, NativeObserver
from ..nutassembly_r5_architecture import tracking_worker as worker
from ....tasks.nut_assembly.canonical_solution_v2 import NutAssemblyStableGraspCandidateV2
from ....tasks.nut_assembly.clearance_candidate_v3 import NutAssemblyHandClearanceCandidateV3
from ....tasks.nut_assembly.clearance_candidate_v4 import NutAssemblyHandClearanceCandidateV4
from ....tasks.nut_assembly.clearance_candidate_v5 import NutAssemblyHandClearanceCandidateV5
from ....tasks.nut_assembly.guarded_authorization_candidate import (
    NutAssemblyGuardedAuthorizationCandidateV1,
)
from ....tasks.nut_assembly.guarded_authorization_candidate_v2 import (
    NutAssemblyGuardedAuthorizationCandidateV2,
)
from ....controllers.canonical.contracts import digest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compile_contact_probe_model(xml: str):
    """Compile the same normalized MJCF used by the MuJoCo session adapter."""
    import mujoco

    root = ET.fromstring(xml)
    for element in root.iter("freejoint"):
        element.tag = "joint"
        element.set("type", "free")
    for element in root.findall("keyframe"):
        root.remove(element)
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))


def _exclude_hand_peg_pair(value: dict) -> dict:
    """Add one diagnostic-only hand/peg body-pair exclusion.

    The production TaskArtifact remains unchanged. A compiled-model guard
    ensures the intervention changes only MuJoCo's contact exclusion table.
    """
    source = value["source"]
    original_xml = source.scene_source.xml
    root = ET.fromstring(original_xml)
    contact = root.find("contact")
    if contact is None:
        contact = ET.SubElement(root, "contact")
    for exclusion in contact.findall("exclude"):
        if {exclusion.get("body1"), exclusion.get("body2")} == {"hand", "peg1"}:
            raise ValueError("hand/peg diagnostic exclusion already exists")
    ET.SubElement(contact, "exclude", body1="hand", body2="peg1")
    variant_xml = ET.tostring(root, encoding="unicode")

    base_model = _compile_contact_probe_model(original_xml)
    variant_model = _compile_contact_probe_model(variant_xml)
    for model in (base_model, variant_model):
        if model.opt.timestep != 0.002 or model.opt.noslip_iterations != 2:
            raise ValueError("hand/peg ablation requires the frozen dt=0.002 NoSlip2 model")
    if variant_model.nexclude != base_model.nexclude + 1:
        raise ValueError("diagnostic must add exactly one compiled body-pair exclusion")

    invariant_arrays = (
        "body_mass", "body_inertia", "body_ipos", "body_iquat", "body_parentid",
        "geom_type", "geom_size", "geom_pos", "geom_quat", "geom_friction",
        "geom_solref", "geom_solimp", "geom_condim", "geom_bodyid", "geom_contype",
        "geom_conaffinity", "geom_margin", "geom_gap", "actuator_trntype",
        "actuator_trnid", "actuator_gainprm", "actuator_biasprm", "actuator_forcerange",
        "actuator_ctrlrange", "dof_damping", "dof_armature", "jnt_qposadr",
        "jnt_dofadr", "jnt_range", "eq_type", "eq_data", "tendon_adr",
        "tendon_num", "wrap_type", "wrap_objid", "wrap_prm",
    )
    changed_arrays = [
        name for name in invariant_arrays
        if not np.array_equal(getattr(base_model, name), getattr(variant_model, name))
    ]
    if changed_arrays:
        raise ValueError(f"unrelated compiled model arrays changed: {changed_arrays}")
    if base_model.ngeom != variant_model.ngeom or base_model.nbody != variant_model.nbody:
        raise ValueError("diagnostic collision intervention changed scene geometry")

    source_hash = hashlib.sha256(variant_xml.encode()).hexdigest()
    scene = replace(
        source.scene_source,
        xml=variant_xml,
        source_id=source.scene_source.source_id + "/diagnostic-hand-peg-exclusion-v1",
    )
    value["source"] = replace(source, scene_source=scene)
    intervention = {
        "id": "diagnostic-hand-peg-body-pair-exclusion-v1",
        "body_pair": ["hand", "peg1"],
        "scope": "all hand-body geoms versus square-peg body; finger bodies and other pairs remain enabled",
        "production_eligible": False,
        "base_compiled_nexclude": int(base_model.nexclude),
        "variant_compiled_nexclude": int(variant_model.nexclude),
        "base_ngeom": int(base_model.ngeom),
        "variant_ngeom": int(variant_model.ngeom),
        "base_nbody": int(base_model.nbody),
        "variant_nbody": int(variant_model.nbody),
        "invariant_compiled_arrays": list(invariant_arrays),
        "changed_unrelated_compiled_arrays": changed_arrays,
        "timestep_s": float(variant_model.opt.timestep),
        "noslip_iterations": int(variant_model.opt.noslip_iterations),
        "source_xml_sha256": source_hash,
    }
    value["_collision_intervention"] = intervention
    value["recipe_identity"] = digest({
        "base_recipe": value["recipe_identity"],
        "collision_intervention": intervention["id"],
        "source_xml_sha256": source_hash,
    })
    return intervention


def context(rate: int, trajectory_candidate: str = "lifecycle-v2"):
    """Build the fixed NoSlip2/native-ramp/native-500Hz recipe and solution."""
    value = frequency_run.context(rate, "arm_ramp_native_grip")
    old_solution_identity = value["solution_identity"]
    old_controller_identity = value["controller_identity"]
    solution_classes = {
        "lifecycle-v2": NutAssemblyStableGraspCandidateV2,
        "handle-clearance-v3": NutAssemblyHandClearanceCandidateV3,
        "handle-clearance-v4-live-settle": NutAssemblyHandClearanceCandidateV4,
        "handle-clearance-v5-shared-height-correction": NutAssemblyHandClearanceCandidateV5,
        "guarded-primary-readiness-alternative-8n-v1": NutAssemblyGuardedAuthorizationCandidateV1,
        "guarded-primary-readiness-alternative-8n-v2-v5-clearance":
            NutAssemblyGuardedAuthorizationCandidateV2,
    }
    try:
        solution_class = solution_classes[trajectory_candidate]
    except KeyError as exc:
        raise ValueError(f"unsupported trajectory candidate: {trajectory_candidate}") from exc
    solution_kwargs = dict(
        config=value["solution_config"],
        control_dt=value["artifact"].timebase.control_dt,
        arm_hold=value["controller"].hold,
    )
    if issubclass(solution_class, NutAssemblyGuardedAuthorizationCandidateV1):
        solution_kwargs["physics_dt_s"] = value["artifact"].timebase.physics_dt
    solution = solution_class(**solution_kwargs)
    value["solution"] = solution
    value["solution_identity"] = solution.identity
    if isinstance(solution, NutAssemblyGuardedAuthorizationCandidateV1):
        value["close_authorization_policy"] = {
            **solution.policy_mapping,
            "identity": solution.policy_identity,
        }
        value["allowed_close_authorization_guards"] = [
            solution.primary_guard_id, solution.alternative_guard_id,
        ]
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
        "close_authorization_policy": value.get("close_authorization_policy"),
    })
    return value


def run(*, provider: str, rate: int, output: Path,
        collision_ablation: str = "none",
        trajectory_candidate: str = "lifecycle-v2") -> dict:
    if provider != "mujoco":
        raise ValueError("this bounded lifecycle run is MuJoCo-only")
    if rate not in {20, 50, 100, 500}:
        raise ValueError("FULL lifecycle diagnostic requires a supported 20/50/100/500 Hz rate")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    value = context(rate, trajectory_candidate)
    if collision_ablation != "none" and trajectory_candidate != "lifecycle-v2":
        raise ValueError("collision ablations are restricted to the frozen Lifecycle V2 baseline")
    collision_intervention = None
    if collision_ablation == "hand-peg-body-pair-exclude":
        collision_intervention = _exclude_hand_peg_pair(value)
    elif collision_ablation != "none":
        raise ValueError(f"unsupported collision ablation: {collision_ablation}")
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
                collision_intervention=collision_intervention,
                diagnostic_only=bool(collision_intervention),
                trajectory_candidate=owner_value["solution"].version,
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
        "trajectory_candidate": value["solution"].version,
        "contact_solver_profile": "MuJoCo NoSlip2",
        "arm_schedule": "linear-native-ramp-after-lift-v2-public-ack-memory",
        "gripper_command_rate_hz": 500,
        "gripper_rate_semantics": "fixed-native-500hz-v1",
        "physics_dt_s": value["artifact"].timebase.physics_dt,
        "control_dt_s": value["artifact"].timebase.control_dt,
        "task_artifact_hash": value["artifact"].identity_hash,
        "solution_identity": value["solution_identity"],
        "recipe_identity": value["recipe_identity"],
        "collision_intervention": collision_intervention,
        "trajectory_candidate": value["solution"].version,
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
        qualification_status=("NOT_ELIGIBLE_DIAGNOSTIC_ONLY"
                              if collision_intervention else "REVIEW_PENDING"),
        historical_9n_qualification_status=(
            "NOT_PASSED_BY_ALTERNATIVE_CANDIDATE" if value.get("close_authorization_policy")
            else "HISTORICAL_POLICY_ACTIVE"
        ),
        alternative_authorization_development_status=(
            "PASS" if result.get("pass") and value.get("close_authorization_policy")
            else "FAIL" if value.get("close_authorization_policy") else "NOT_APPLICABLE"
        ),
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
        close_authorization_policy=(value.get("close_authorization_policy")
                                    or "controller_close_ready_only"),
        close_authorization_acceptance_policy=(
            "primary_or_declared_alternative_guard" if value.get("close_authorization_policy")
            else "historical_controller_close_ready_only"
        ),
        allowed_close_authorization_guards=value.get(
            "allowed_close_authorization_guards", ["controller_close_ready"]
        ),
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
        collision_intervention=collision_intervention,
        trajectory_candidate=value["solution"].version,
        package_versions={
            name: importlib.metadata.version(name)
            for name in ("numpy", "h5py", "gymnasium", "mujoco")
            if any(dist.metadata["Name"].lower() == name
                   for dist in importlib.metadata.distributions())
        },
    )
    result["full_expert_status"] = (
        "DIAGNOSTIC_ONLY_PASS" if result.get("pass") and collision_intervention
        else "DIAGNOSTIC_ONLY_FAIL" if collision_intervention
        else "FULL_EXPERT_ALTERNATIVE_AUTHORIZATION_DEVELOPMENT_PASS"
        if result.get("pass") and value.get("close_authorization_policy")
        else "FULL_EXPERT_DEVELOPMENT_PASS" if result.get("pass")
        else "FULL_EXPERT_FAILED"
    )
    result["golden_acceptance_status"] = (
        "NOT_ELIGIBLE_DIAGNOSTIC_COLLISION_INTERVENTION"
        if collision_intervention else
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
        "clearance_candidate_v3": Path("task_env/tasks/nut_assembly/clearance_candidate_v3.py"),
        "clearance_candidate_v4": Path("task_env/tasks/nut_assembly/clearance_candidate_v4.py"),
        "clearance_candidate_v5": Path("task_env/tasks/nut_assembly/clearance_candidate_v5.py"),
        "guarded_transition_evaluator": Path("task_env/tasks/guarded_transition.py"),
        "guarded_authorization_candidate": Path(
            "task_env/tasks/nut_assembly/guarded_authorization_candidate.py"),
        "guarded_authorization_candidate_v2": Path(
            "task_env/tasks/nut_assembly/guarded_authorization_candidate_v2.py"),
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
        "collision_intervention": collision_intervention,
        "trajectory_candidate": value["solution"].version,
        "reset_sample_hash": result.get("reset_sample_hash"),
        "source_sha256": {name: _sha(path) for name, path in source_paths.items()},
        "result_sha256": _sha(output / "full_expert_result.json"),
        "execution_h5": result.get("live_recording", {}).get("path"),
        "execution_h5_sha256": (
            _sha(Path(result["live_recording"]["path"]))
            if result.get("live_recording", {}).get("path") else None
        ),
        "development_only": True,
        "qualification_status": (
            "NOT_ELIGIBLE_DIAGNOSTIC_ONLY" if collision_intervention else "REVIEW_PENDING"
        ),
    }
    worker._write(output / "full_expert_evidence_manifest.json", manifest)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("mujoco",), default="mujoco")
    parser.add_argument("--rate", type=int, choices=(20, 50, 100, 500), default=100)
    parser.add_argument(
        "--trajectory-candidate",
        choices=("lifecycle-v2", "handle-clearance-v3", "handle-clearance-v4-live-settle",
                 "handle-clearance-v5-shared-height-correction",
                 "guarded-primary-readiness-alternative-8n-v1",
                 "guarded-primary-readiness-alternative-8n-v2-v5-clearance"),
        default="lifecycle-v2",
    )
    parser.add_argument(
        "--collision-ablation",
        choices=("none", "hand-peg-body-pair-exclude"),
        default="none",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(provider=args.provider, rate=args.rate, output=args.output,
                 collision_ablation=args.collision_ablation,
                 trajectory_candidate=args.trajectory_candidate)
    print(json.dumps({key: report.get(key) for key in (
        "pass", "failure_boundary", "expert_complete", "expert_failed",
        "completion_reason", "canonical_task_success", "coordinator_stage_sequence",
        "release_retreat_endpoint_pass", "live_recording",
    )}, indent=2, allow_nan=False), flush=True)
    return 0 if report.get("pass") and report.get("live_recording", {}).get("roundtrip_exact") else 1


if __name__ == "__main__":
    raise SystemExit(main())
