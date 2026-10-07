"""Experimental P1.6 100 Hz PickCube route; never used for provider qualification.

This module intentionally derives an opt-in TaskArtifact/source pair and talks
to the existing GeoPhys session adapter directly.  The production capability
manifest remains CPU-only and all results are diagnostic evidence.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import math
import traceback

import numpy as np

from task_env.artifacts import ExecutionSpec
from task_env.artifacts.contracts import Timebase
from task_env.artifacts.execution import ResetSample
from task_env.controllers.canonical import ProductionCanonicalPandaController, RequestedAction
from task_env.controllers.canonical.kinematics import ARM, FINGERS
from task_env.diagnostics.phase1.control.worker import observation
from task_env.planners.completion import ExpertExecutionInfo
from task_env.runtime.sessions.control import ControlBinding
from task_env.runtime.sessions.provenance import provider_build_identity
from task_env.tasks.pick_cube.candidate import build_candidate
from task_env.tasks.pick_cube.canonical_semantics import evaluate
from task_env.tasks.pick_cube.readiness_solution import PickCubeReadinessConfig, PickCubeReadinessSolution
from task_env.tasks.pick_cube.reset import sample_reset
from task_env.tasks.pick_cube.runtime_source import build_runtime_source
from task_env.trajectory.canonical import BoundaryRecord, CanonicalRecorder, EpisodeMetadata, TransitionRecord, load, save
from task_env.controllers.canonical.contracts import digest


EXPERIMENTAL_ARTIFACT_ID = "pick-cube-v1/p1_6_experimental_100hz"
EXPERIMENTAL_ARTIFACT_VERSION = "ver_p1_6_experimental_100hz"
EXPERIMENTAL_PROFILE = "p1_6_experimental_100hz_diagnostic_v0"
HISTORICAL_TRAJECTORY = Path("workspace/qualification/phase1/p1_6_flow_preparation/trajectories/seed1000/trajectory.h5")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path | str) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def write_json(path: Path | str, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n")


def context(backend: str):
    """Build a new timebase identity without changing the default candidate."""
    if backend not in {"cpu", "cuda"}:
        raise ValueError("diagnostic backend must be cpu or cuda")
    historical = build_candidate()
    experimental = replace(
        historical,
        artifact_id=EXPERIMENTAL_ARTIFACT_ID,
        artifact_version=EXPERIMENTAL_ARTIFACT_VERSION,
        timebase=replace(historical.timebase, physics_dt=0.002, control_substeps=5, control_dt=0.010),
    )
    source0 = build_runtime_source(historical)
    runtime = replace(
        source0.config.runtime,
        physics_dt=0.002,
        control_substeps=5,
        backend=backend,
        prewarm=False,
    )
    source = replace(
        source0,
        task_artifact_hash=experimental.identity_hash,
        config=replace(source0.config, runtime=runtime),
    )
    readiness = PickCubeReadinessConfig.from_source(experimental, source)
    controller = ProductionCanonicalPandaController.from_source(experimental, source)
    expert = PickCubeReadinessSolution(config=readiness)
    return historical, experimental, source, readiness, controller, expert


def sample_for_variant(experimental_artifact, seed: int) -> ResetSample:
    """Reuse the exact v0 task-seed draw, rebinding only the artifact identity."""
    historical_sample = sample_reset(build_candidate(), int(seed))
    payload = historical_sample.to_mapping()
    payload.pop("sample_id")
    payload["task_artifact_hash"] = experimental_artifact.identity_hash
    rebound = ResetSample.create(**payload)
    if rebound.task_seed != int(seed) or rebound.task_artifact_hash != experimental_artifact.identity_hash:
        raise ValueError("experimental ResetSample identity mismatch")
    if rebound.poses_world != historical_sample.poses_world or rebound.joint_position != historical_sample.joint_position:
        raise ValueError("artifact rebinding changed the semantic reset values")
    return rebound


def source_bindings(source) -> dict:
    return {
        "joints": dict(source.joints),
        "bodies": dict(source.bodies),
        "frames": dict(source.frames),
        "free_joints": dict(source.free_joints),
        "joint_targets": dict(source.joint_targets),
        "open_actuators": list(source.open_actuators),
    }


def source_provenance(source) -> dict:
    recipe = {
        "source_xml_sha256": sha256_bytes(source.scene_source.xml.encode()),
        "semantic_bindings": source_bindings(source),
        "resolved_runtime_config": asdict(source.config),
        "recipe_scope": "Panda/Cube source and runtime construction values; diagnostic-only 100Hz profile",
    }
    recipe["materialization_recipe_sha256"] = sha256_bytes(canonical_json(recipe).encode())
    return recipe


def _open_session(artifact, source):
    """Use the existing adapter without claiming its production manifest supports CUDA."""
    from task_env.runtime.sessions.geophys import _GeoPhysSession

    session = _GeoPhysSession(artifact, source)
    session._control_binding = ControlBinding("panda-v1/gripper", 0.08)
    class NativeSubstepCounter:
        """Diagnostic hook called by GeoPhys once per native simulation substep."""
        def __init__(self):
            self.completed = 0
            self.last_substep_id = None

        def before_substep(self, simulator, substep_id):
            return None

        def after_substep(self, simulator, substep_id):
            self.completed += 1
            self.last_substep_id = int(substep_id)

    counter = NativeSubstepCounter()
    session._boundary._scheduler.add_hook(counter)
    session._diagnostic_native_substeps = counter
    return session


def _clock(session) -> dict:
    counter = session._diagnostic_native_substeps
    return {
        "physics_ticks": int(counter.completed),
        "last_native_substep_id": counter.last_substep_id,
        "counter_source": "GeoPhys SimulatorHook.after_substep",
    }


def _finite_state(state) -> bool:
    values = [state.simulation_time, *state.joint_position.values(), *state.joint_velocity.values()]
    for pose in state.pose_world.values():
        values.extend(pose.position)
        values.extend(pose.quaternion_wxyz)
    return bool(np.isfinite(np.asarray(values, dtype=np.float64)).all())


def _taichi_arch() -> str | None:
    try:
        import taichi as ti
        arch = ti.lang.impl.current_cfg().arch
        return getattr(arch, "name", str(arch))
    except Exception:
        return None


def g0(backend: str) -> dict:
    historical, artifact, source, readiness, controller, expert = context(backend)
    sample = sample_for_variant(artifact, 1000)
    result = {
        "route": "G0_timebase_smoke",
        "diagnostic_only": True,
        "provider_qualification_claim": False,
        "historical_artifact_sha256": historical.identity_hash,
        "experimental_artifact_sha256": artifact.identity_hash,
        "backend_requested": backend,
        "reset_sample_hash": sample.identity_hash,
        "source_materialization": source_provenance(source),
        "pass": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    session = None
    stage = "materialization"
    try:
        session = _open_session(artifact, source)
        stage = "reset"
        realized = session.reset(sample)
        before = session.snapshot()
        feedback0 = session.control_feedback(before)
        controller.reset(before, feedback0)
        request = RequestedAction("absolute_joint", None, "none", tuple(float(sample.joint_position[n]) for n in ARM) + (1.0,))
        canonical, target = controller.compute(before, feedback0, request)
        applied = session.apply_control(target)
        native_before = _clock(session)
        stage = "native_step"
        after = session.step()
        stage = "post_step_readback"
        native_after = _clock(session)
        feedback1 = session.control_feedback(after)
        native_ticks_before = native_before.get("physics_ticks")
        native_ticks_after = native_after.get("physics_ticks")
        native_delta = None if native_ticks_before is None or native_ticks_after is None else int(native_ticks_after) - int(native_ticks_before)
        delta_time = after.simulation_time - before.simulation_time
        checks = {
            "reset_at_step_zero_time_zero": realized.measured_state.control_step == 0 and realized.measured_state.simulation_time == 0.0 and before.control_step == 0 and before.simulation_time == 0.0,
            "exactly_five_native_physics_ticks": native_delta == 5,
            "one_canonical_control_step": after.control_step == before.control_step + 1,
            "simulation_time_delta_0_010": abs(delta_time - 0.010) <= max(math.ulp(0.010), math.ulp(after.simulation_time)),
            "finite_canonical_state": _finite_state(before) and _finite_state(after),
            "post_step_feedback_boundary_matches": feedback1.control_step == after.control_step and feedback1.simulation_time == after.simulation_time,
            "applied_control_target_linked": applied.target_hash == target.identity_hash,
        }
        result.update({
            "native_backend": _taichi_arch(),
            "native_clock_before": native_before,
            "native_clock_after": native_after,
            "native_physics_tick_delta": native_delta,
            "reset_state": before.to_mapping(),
            "post_step_state": after.to_mapping(),
            "control_feedback": feedback1.to_mapping(),
            "action_clipped": canonical.clipped,
            "time_delta_s": delta_time,
            "checks": checks,
            "pass": all(checks.values()),
        })
        result["status"] = "pass" if result["pass"] else "fail"
    except Exception as exc:
        cuda_runtime_failure = backend == "cuda" and stage in {"materialization", "reset", "native_step"}
        result.update({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(), "failure_stage": stage,
                       "native_backend": _taichi_arch(), "status": "gpu_collection_blocked" if cuda_runtime_failure else "fail"})
    finally:
        if session is not None:
            session.close()
    return result


def boundary(controller, state, feedback, info):
    return BoundaryRecord(
        state.control_step,
        state.simulation_time,
        state,
        feedback,
        controller.readiness(state, feedback),
        {k: float(v) for k, v in info["task_metrics"].items() if isinstance(v, (int, float, np.number))},
        bool(info["is_success"]),
        bool(info["task_failure"]),
    )


def temporal_summary(trajectory) -> dict:
    dt = trajectory.metadata.timebase.control_dt
    stages = {}
    for stage in sorted({t.expert_stage for t in trajectory.transitions}):
        indexed = [(i, t) for i, t in enumerate(trajectory.transitions) if t.expert_stage == stage]
        planned = sum(t.planned_action for _, t in indexed)
        holds = sum(t.readiness_hold for _, t in indexed)
        total = len(indexed)
        stages[stage] = {
            "planned_frames": planned,
            "readiness_hold_frames": holds,
            "total_frames": total,
            "simulated_duration_s": total * dt,
        }
    total = len(trajectory.transitions)
    holds = trajectory.hold_count
    return {
        "physics_dt": trajectory.metadata.timebase.physics_dt,
        "control_substeps": trajectory.metadata.timebase.control_substeps,
        "control_dt": dt,
        "physics_frequency_hz": 1.0 / trajectory.metadata.timebase.physics_dt,
        "control_frequency_hz": 1.0 / dt,
        "total_control_frames": total,
        "total_simulation_duration_s": trajectory.boundaries[-1].simulation_time - trajectory.boundaries[0].simulation_time,
        "total_planned_frames": total - holds,
        "total_readiness_hold_frames": holds,
        "hold_fraction": holds / total if total else 0.0,
        "per_stage": stages,
    }


def collect(backend: str, seed: int, role: str, output: Path) -> dict:
    if role not in {"train", "validation", "pilot"}:
        raise ValueError("role must be train, validation, or pilot")
    historical, artifact, source, readiness, controller, expert = context(backend)
    sample = sample_for_variant(artifact, seed)
    sample_before = sample.to_mapping()
    provider = provider_build_identity("geophys")
    recipe = source_provenance(source)
    ctrl = ProductionCanonicalPandaController.from_source(artifact, source)
    readiness_identity = digest({
        "schema": "canonical-control-readiness-v1",
        "policies": [p.to_mapping() for p in readiness.policies],
        "profile_identity": readiness.profile_identity,
        "config_identity": readiness.identity,
        "contract_source_sha256": sha256_file("task_env/controllers/canonical/readiness.py"),
    })
    result = {
        "seed": seed,
        "role": role,
        "backend": backend,
        "diagnostic_only": True,
        "provider_qualification_claim": False,
        "task_artifact_hash": artifact.identity_hash,
        "reset_sample_hash": sample.identity_hash,
        "readiness_config_identity": readiness.identity,
        "controller_identity": ctrl.identity,
        "expert_identity": expert.identity,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pass": False,
    }
    session = None
    recorder = None
    stage = "materialization"
    try:
        session = _open_session(artifact, source)
        realized = session.reset(sample)
        state = session.snapshot()
        feedback = session.control_feedback(state)
        controller.reset(state, feedback)
        obs, info, evaluation = observation(state, artifact)
        initial = boundary(controller, state, feedback, info)
        execution = ExecutionSpec("geophys", EXPERIMENTAL_PROFILE, "none", backend, 0, "best_effort")
        provider_provenance = {k: json.dumps(v, sort_keys=True) for k, v in provider.items()}
        provider_provenance.update({"execution_backend": backend, "diagnostic_only": "true"})
        source_values = {
            "source_xml_sha256": recipe["source_xml_sha256"],
            "source_bindings_json": canonical_json(recipe["semantic_bindings"]),
            "materialization_recipe_sha256": recipe["materialization_recipe_sha256"],
            "resolved_runtime_config_json": canonical_json(recipe["resolved_runtime_config"]),
        }
        metadata = EpisodeMetadata(
            "canonical-trajectory-metadata-v0",
            artifact.identity_hash,
            sample,
            realized,
            execution,
            provider_provenance,
            source_values,
            artifact.timebase,
            ctrl.identity,
            expert.identity,
            readiness_identity,
            readiness.identity,
            seed,
            "regression" if role == "pilot" else role,
        )
        recorder = CanonicalRecorder(metadata, initial)
        expert.reset(
            obs,
            info,
            {"action_schema": {"controller_kind": "absolute_pose", "reference": "world", "rotation_representation": "quaternion_wxyz", "dimension": 8}},
            execution_info=ExpertExecutionInfo("expert-execution-info-v1", 0, 0.0, initial.readiness),
        )
        max_lift = float(info["task_metrics"]["cube_lift"])
        native_start = _clock(session)
        stage = "expert_execution"
        while not expert.done and not expert.failed:
            public = expert.act()
            request = RequestedAction("absolute_pose", "world", "quaternion_wxyz", tuple(map(float, public.action)))
            canonical, target = controller.compute(state, feedback, request)
            applied = session.apply_control(target)
            state = session.step()
            feedback = session.control_feedback(state)
            obs, info, evaluation = observation(state, artifact)
            after = boundary(controller, state, feedback, info)
            expert.observe(
                obs,
                evaluation.reward,
                False,
                False,
                info,
                execution_info=ExpertExecutionInfo("expert-execution-info-v1", state.control_step, state.simulation_time, after.readiness),
            )
            hold = bool(public.diagnostics["readiness_hold"])
            diagnostics = {str(k): json.dumps(v, sort_keys=True, default=str) for k, v in public.diagnostics.items()}
            recorder.append(
                TransitionRecord(request, canonical, target, applied, float(evaluation.reward), False, False,
                                 public.stage, diagnostics, not hold, hold),
                after,
            )
            max_lift = max(max_lift, float(info["task_metrics"]["cube_lift"]))
        native_end = _clock(session)
        stage = "trajectory_validation"
        trajectory = recorder.freeze("expert_endpoint" if expert.done else expert.failure_reason or "expert_failed")
        trajectory.validate()
        output = Path(output)
        trajectory_path = output.parent / "trajectory.h5"
        trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        save(trajectory_path, trajectory)
        loaded = load(trajectory_path)
        loaded.validate()
        roundtrip = loaded.to_mapping() == trajectory.to_mapping()
        historical_trajectory = load(HISTORICAL_TRAJECTORY) if seed == 1000 and HISTORICAL_TRAJECTORY.exists() else None
        history = None
        if historical_trajectory is not None:
            history = {
                "trajectory_sha256": sha256_file(HISTORICAL_TRAJECTORY),
                "logical_hash": historical_trajectory.identity_hash,
                "T": len(historical_trajectory.transitions),
                "total_simulation_duration_s": historical_trajectory.boundaries[-1].simulation_time - historical_trajectory.boundaries[0].simulation_time,
                "temporal": temporal_summary(historical_trajectory),
            }
        temporal = temporal_summary(loaded)
        result.update({
            "pass": bool(expert.done and info["is_success"] and max_lift >= 0.105 and roundtrip and sample.to_mapping() == sample_before),
            "first_boundary": None if expert.done else "100hz_expert_behavior",
            "failure_reason": expert.failure_reason,
            "endpoint_reached": bool(expert.done),
            "task_success": bool(info["is_success"]),
            "collection_endpoint_m": 0.105,
            "max_cube_lift_m": max_lift,
            "stop_reason": loaded.stop_reason,
            "T": len(loaded.transitions),
            "boundary_count": len(loaded.boundaries),
            "hold_count": loaded.hold_count,
            "planned_count": len(loaded.transitions) - loaded.hold_count,
            "per_stage_counts": temporal["per_stage"],
            "temporal_metrics": temporal,
            "native_clock_before": native_start,
            "native_clock_after": native_end,
            "native_physics_ticks": None if "physics_ticks" not in native_start or "physics_ticks" not in native_end else int(native_end["physics_ticks"]) - int(native_start["physics_ticks"]),
            "native_backend": _taichi_arch(),
            "roundtrip": roundtrip,
            "trajectory_file": str(trajectory_path),
            "trajectory_file_sha256": sha256_file(trajectory_path),
            "trajectory_logical_hash": loaded.identity_hash,
            "historical_500hz_seed1000": history,
            "sample_unchanged": sample.to_mapping() == sample_before,
            "source_materialization": recipe,
        })
        if historical_trajectory is not None:
            result["frame_count_ratio_100hz_over_500hz"] = len(loaded.transitions) / len(historical_trajectory.transitions)
            result["simulation_duration_ratio_100hz_over_500hz"] = temporal["total_simulation_duration_s"] / history["total_simulation_duration_s"]
        write_json(output.parent / "trajectory_metrics.json", {"temporal": temporal, "historical_500hz": history})
    except Exception as exc:
        result.update({"pass": False, "first_boundary": stage, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(), "native_backend": _taichi_arch()})
        if recorder is not None:
            write_json(Path(output).parent / "partial_records.json", {
                "boundaries": [b.to_mapping() for b in recorder.boundaries],
                "transitions": [t.to_mapping() for t in recorder.transitions],
            })
    finally:
        if session is not None:
            session.close()
    write_json(output, result)
    return result


def action_from_target(target) -> RequestedAction:
    arm = tuple(float(target.arm_position[n]) for n in ARM)
    opening = float(target.gripper.opening_m)
    scalar = 2.0 * opening / 0.08 - 1.0
    return RequestedAction("absolute_joint", None, "none", arm + (scalar,))


def compare_target(reference, observed) -> dict:
    arm_desired = max(abs(float(reference.arm_position[n]) - float(observed.arm_position[n])) for n in ARM)
    arm_servo = max(abs(float(reference.arm_servo_position[n]) - float(observed.arm_servo_position[n])) for n in ARM)
    return {
        "arm_position_max_abs": arm_desired,
        "arm_servo_position_max_abs": arm_servo,
        "gripper_desired_opening_abs_m": abs(reference.gripper.opening_m - observed.gripper.opening_m),
        "gripper_servo_opening_abs_m": abs(reference.gripper.servo_opening_m - observed.gripper.servo_opening_m),
        "gripper_force_limit_abs_N": abs(reference.gripper.force_limit_N - observed.gripper.force_limit_N),
    }


def d0(trajectory_path: Path, output: Path) -> dict:
    trajectory = load(trajectory_path)
    artifact = replace(build_candidate(), artifact_id=EXPERIMENTAL_ARTIFACT_ID,
                       artifact_version=EXPERIMENTAL_ARTIFACT_VERSION,
                       timebase=replace(build_candidate().timebase, physics_dt=0.002, control_substeps=5, control_dt=0.010))
    if trajectory.metadata.task_artifact_hash != artifact.identity_hash:
        raise ValueError("100Hz trajectory/artifact identity mismatch")
    _, _, source, readiness, controller, _ = context(trajectory.metadata.execution.backend)
    controller.reset(trajectory.boundaries[0].state, trajectory.boundaries[0].feedback)
    rows = []
    first_mismatch = None
    per_stage = {}
    maxima = {"arm_position_max_abs": 0.0, "arm_servo_position_max_abs": 0.0,
              "gripper_desired_opening_abs_m": 0.0, "gripper_servo_opening_abs_m": 0.0,
              "gripper_force_limit_abs_N": 0.0}
    clip_count = 0
    clip_match_count = 0
    target_hash_matches = 0
    for i, transition in enumerate(trajectory.transitions):
        reference = transition.controller_target
        request = action_from_target(reference)
        canonical, target = controller.compute(trajectory.boundaries[i].state, trajectory.boundaries[i].feedback, request)
        errors = compare_target(reference, target)
        for key, value in errors.items():
            maxima[key] = max(maxima[key], value)
        clip_count += int(canonical.clipped)
        target_hash_matches += int(target.identity_hash == reference.identity_hash)
        stage = transition.expert_stage
        item = per_stage.setdefault(stage, {"frames": 0, "clip_count": 0, "max_errors": {k: 0.0 for k in maxima}})
        item["frames"] += 1
        item["clip_count"] += int(canonical.clipped)
        clip_match_count += int(bool(transition.canonical_action.clipped) == bool(canonical.clipped))
        for key, value in errors.items():
            item["max_errors"][key] = max(item["max_errors"][key], value)
        row = {"transition": i, "stage": stage, "action": request.to_mapping(), "canonical_action_clipped": canonical.clipped,
               "reference_pose_canonical_clipped": transition.canonical_action.clipped,
               "target_hash_match": target.identity_hash == reference.identity_hash, "errors": errors}
        rows.append(row)
        if first_mismatch is None and max(errors.values()) > 1.0e-12:
            first_mismatch = i
    passed = max(maxima.values()) <= 1.0e-12 and len(trajectory.boundaries) == len(trajectory.transitions) + 1 and all(math.isfinite(v) for v in maxima.values())
    report = {"route": "D0_teacher_forced_absolute_joint_target_equivalence", "pass": passed,
              "first_mismatch_transition": first_mismatch, "max_errors": maxima,
              "reconstructed_action_clip_count": clip_count,
              "reference_absolute_pose_canonical_clip_count": sum(t.canonical_action.clipped for t in trajectory.transitions),
              "clip_boolean_equal_count": clip_match_count,
              "clip_comparison_note": "Pose-mode and joint-mode clipping flags are reported separately; the hard gate is target-field equivalence.",
              "target_hash_equal_count": target_hash_matches, "T": len(trajectory.transitions), "per_stage": per_stage,
              "tolerance": 1.0e-12, "trajectory_logical_hash": trajectory.identity_hash}
    write_json(output.parent / "per_step_errors.json", rows)
    write_json(output, report)
    return report


def _cube_position(state):
    return np.asarray(state.pose_world["cube-v1"].position, dtype=np.float64)


def _state_error(reference, observed):
    q_ref = np.asarray([reference.joint_position[n] for n in ARM], dtype=np.float64)
    q = np.asarray([observed.joint_position[n] for n in ARM], dtype=np.float64)
    ee = np.asarray(reference.pose_world["panda-v1/ee"].position) - np.asarray(observed.pose_world["panda-v1/ee"].position)
    cube = np.asarray(reference.pose_world["cube-v1"].position) - np.asarray(observed.pose_world["cube-v1"].position)
    return {"arm_q_rms": float(np.sqrt(np.mean((q_ref-q)**2))), "arm_q_max_abs": float(np.max(np.abs(q_ref-q))),
            "ee_position_error_m": float(np.linalg.norm(ee)), "cube_position_error_m": float(np.linalg.norm(cube))}


def _close_geometry(trace, trajectory):
    indices = [i for i, t in enumerate(trajectory.transitions) if t.expert_stage == "close_gripper"]
    if not indices:
        return {"close_stage_frames": 0}
    start = _cube_position(trace[indices[0]])
    post = [_cube_position(trace[i+1]) for i in indices]
    drifts = [v-start for v in post]
    steps = [np.linalg.norm(_cube_position(trace[i+1])-_cube_position(trace[i])) for i in indices]
    return {"close_stage_frames": len(indices), "max_close_cube_xyz_drift_m": float(max(np.linalg.norm(x) for x in drifts)),
            "max_close_cube_xy_drift_m": float(max(np.linalg.norm(x[:2]) for x in drifts)),
            "max_close_single_step_cube_displacement_m": float(max(steps)),
            "close_start_cube_position": start.tolist()}


def replay(route: str, backend: str, trajectory_path: Path, output: Path) -> dict:
    if route not in {"D1", "D2"}:
        raise ValueError("route must be D1 or D2")
    trajectory = load(trajectory_path)
    trajectory.validate()
    _, artifact, source, readiness, controller, _ = context(backend)
    if trajectory.metadata.task_artifact_hash != artifact.identity_hash:
        raise ValueError("100Hz trajectory/artifact identity mismatch")
    sample = trajectory.metadata.reset_sample
    sample_before = sample.to_mapping()
    session = None
    states = [None] * (len(trajectory.transitions)+1)
    rows = []
    report = {"route": "D1_exact_target_replay" if route == "D1" else "D2_transformed_absolute_joint_replay",
              "backend": backend, "seed": sample.task_seed, "reset_sample_hash": sample.identity_hash,
              "trajectory_logical_hash": trajectory.identity_hash, "pass": False, "first_boundary": None}
    try:
        session = _open_session(artifact, source)
        session.reset(sample)
        state = session.snapshot()
        states[0] = state
        feedback = session.control_feedback(state)
        if route == "D2":
            controller.reset(state, feedback)
        native_start = _clock(session)
        last_time = state.simulation_time
        max_target_errors = {"arm_position_max_abs": 0.0, "arm_servo_position_max_abs": 0.0,
                             "gripper_desired_opening_abs_m": 0.0, "gripper_servo_opening_abs_m": 0.0,
                             "gripper_force_limit_abs_N": 0.0}
        clipping = 0
        for i, transition in enumerate(trajectory.transitions):
            reference = transition.controller_target
            if route == "D1":
                request = None
                canonical = None
                target = reference
            else:
                request = action_from_target(reference)
                canonical, target = controller.compute(state, feedback, request)
                clipping += int(canonical.clipped)
                errors = compare_target(reference, target)
                for key, value in errors.items():
                    max_target_errors[key] = max(max_target_errors[key], value)
            target_hash_before = target.identity_hash
            applied = session.apply_control(target)
            state_before = state
            state = session.step()
            feedback = session.control_feedback(state)
            if target.identity_hash != target_hash_before or applied.target_hash != target_hash_before:
                raise ValueError(f"provider target mutation/link failure at transition {i}")
            if state.control_step != state_before.control_step + 1 or not (state.simulation_time > last_time):
                raise ValueError(f"monotonic control/time failure at transition {i}")
            expected_time = last_time + artifact.timebase.control_dt
            if abs(state.simulation_time-expected_time) > max(math.ulp(expected_time), math.ulp(state.simulation_time)):
                raise ValueError(f"canonical timebase mismatch at transition {i}")
            if not _finite_state(state):
                raise ValueError(f"nonfinite canonical state at transition {i}")
            states[i+1] = state
            evaluation = evaluate(state, artifact.semantics)
            rows.append({
                "transition": i, "expert_stage_reference_only": transition.expert_stage,
                "control_step": state.control_step, "simulation_time": state.simulation_time,
                "requested_action": None if request is None else request.to_mapping(),
                "canonical_action": None if canonical is None else canonical.to_mapping(),
                "controller_target": target.to_mapping(), "applied_control": applied.to_mapping(),
                "joint_position": dict(state.joint_position), "joint_velocity": dict(state.joint_velocity),
                "cube_pose": state.pose_world["cube-v1"].to_mapping(), "ee_pose": state.pose_world["panda-v1/ee"].to_mapping(),
                "measured_gripper_opening_m": float(sum(state.joint_position[n] for n in FINGERS)),
                "task_metrics": dict(evaluation.metrics), "is_success": evaluation.success,
                "target_hash": target_hash_before,
            })
            last_time = state.simulation_time
        native_end = _clock(session)
        final_eval = evaluate(state, artifact.semantics)
        max_lift = max(float(evaluate(s, artifact.semantics).metrics["cube_lift"]) for s in states)
        errors = [_state_error(trajectory.boundaries[i+1].state, states[i+1]) for i in range(len(trajectory.transitions))]
        aggregated = {key: {"max": max(x[key] for x in errors), "rms": float(np.sqrt(np.mean([x[key]**2 for x in errors])))} for key in errors[0]} if errors else {}
        frames = temporal_summary(trajectory)
        close = _close_geometry(states, trajectory)
        ticks_start, ticks_end = native_start.get("physics_ticks"), native_end.get("physics_ticks")
        native_delta = None if ticks_start is None or ticks_end is None else int(ticks_end)-int(ticks_start)
        report.update({
            "pass": bool(final_eval.success and max_lift >= 0.10 and len(rows) == len(trajectory.transitions) and sample.to_mapping() == sample_before),
            "first_boundary": None if final_eval.success and max_lift >= 0.10 else ("100hz_exact_target_replay" if route == "D1" else "100hz_transformed_absolute_joint_replay"),
            "task_success": bool(final_eval.success), "max_cube_lift_m": max_lift,
            "final_cube_position": list(state.pose_world["cube-v1"].position),
            "final_ee_position": list(state.pose_world["panda-v1/ee"].position),
            "state_divergence_vs_expert": aggregated,
            "close_window": close,
            "total_control_frames": len(rows), "total_simulation_duration_s": state.simulation_time,
            "native_physics_tick_delta": native_delta, "expected_native_physics_ticks": len(rows)*5,
            "native_clock_before": native_start, "native_clock_after": native_end,
            "max_target_divergence_vs_expert": max_target_errors if route == "D2" else None,
            "absolute_joint_clipping_count": clipping,
            "target_hashes_unchanged": True, "sample_unchanged": sample.to_mapping() == sample_before,
            "finite_state": all(_finite_state(s) for s in states), "monotonic_time": True,
            "temporal_metrics": frames,
        })
        write_json(output.parent / "trace.json", rows)
        write_json(output.parent / "states.json", [s.to_mapping() for s in states])
    except Exception as exc:
        report.update({"pass": False, "first_boundary": "100hz_exact_target_replay" if route == "D1" else "100hz_transformed_absolute_joint_replay",
                      "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(), "partial_steps": len(rows)})
        write_json(output.parent / "trace.json", rows)
    finally:
        if session is not None:
            session.close()
    write_json(output, report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", choices=("g0", "collect", "d0", "d1", "d2"), required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--role", default="pilot")
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.route == "g0":
        report = g0(args.backend)
        write_json(args.output, report)
    elif args.route == "collect":
        report = collect(args.backend, args.seed, args.role, args.output)
    elif args.route == "d0":
        if args.trajectory is None:
            parser.error("--trajectory is required for D0")
        report = d0(args.trajectory, args.output)
    else:
        if args.trajectory is None:
            parser.error("--trajectory is required for D1/D2")
        report = replay(args.route.upper(), args.backend, args.trajectory, args.output)
    print(json.dumps(report, sort_keys=True, allow_nan=False, default=str))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
