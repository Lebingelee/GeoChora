"""Bounded P1.6 V2a D3 cross-provider policy check.

This diagnostic keeps policy preprocessing/action semantics shared and selects
only the runtime materialization adapter by provider. GeoPhys CUDA uses the
already-established diagnostic session route; MuJoCo uses the admitted P1.2
controlled runtime session on CPU.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import traceback

import numpy as np
import torch
import yaml

import task_env.alg.agent_factory  # noqa: F401 - installs package bridge
from agent_factory.agents.registry import make_agent
from agent_factory.training.identity import config_identity
from task_env.artifacts import ExecutionSpec
from task_env.artifacts.execution import ResetSample
from task_env.controllers.canonical.kinematics import ARM
from task_env.diagnostics.phase1.control.worker import observation
from task_env.diagnostics.phase1.policy_search.config_utils import load_variant_config
from task_env.diagnostics.phase1.policy_search.flow100_data import (
    select_observation_features,
)
from task_env.diagnostics.phase1.policy_search.flow100_rollout import (
    finite_state,
    mapping,
    percentile_ms,
    _close_metrics,
)
from task_env.diagnostics.phase1.policy_search.flow_variants import _verify_dataset
from task_env.diagnostics.phase1.policy_search.timebase100 import (
    context,
    sha256_file,
    write_json,
    _open_session as open_geophys_cuda_session,
)
from task_env.alg.state_bc.features import features, requested_action
from task_env.tasks.pick_cube.canonical_semantics import evaluate
from task_env.trajectory.canonical import load as load_trajectory


REPO_ROOT = Path.cwd()
VARIANT_ROOT = Path(
    "workspace/experiments/p1_6_policy_search/"
    "100hz_gpu_flow_h50_a36_no_qvel_v2a_15000"
)
TRAIN_ROOT = VARIANT_ROOT / "training"
MANIFEST = Path(
    "workspace/experiments/p1_6_policy_search/100hz_gpu_flow/"
    "training_dataset_manifest_100hz.json"
)
CHECKPOINT = TRAIN_ROOT / "checkpoints/final_step15000.pth"
EVIDENCE_ROOT = Path("workspace/qualification/phase1/p1_6_closure/d3")
EXPECTED_CHECKPOINT_SHA256 = (
    "9c4e073659bd4862d0ef9921f6c12b9e83beb893ad949e3d4d26fda961bd24e9"
)
EXPECTED_MANIFEST_SHA256 = (
    "0e13517ce9f179daf7d4c525a6fb7d33629d3bb6fdd7683b4f06ac9492cf10dd"
)
EXPECTED_ARTIFACT_SHA256 = (
    "fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4"
)
EXPECTED_CONFIG_SHA256 = (
    "b40fdb55041c98bf0defb08aa1675ee42317a447eca8daecad360294a9699e1f"
)
EXPECTED_LOGICAL_DATASET_IDENTITY = (
    "f2ebc763dd98ec5c78ec77c2d988255ec112ca24e331afebeea2fe45a5bff478"
)
OBSERVATION_IDENTITY = (
    "be8fb4cc60b33454c9ae2a87e3e4cc9017016ccdf6770656d5ebb955d3c1c076"
)
ACTION_IDENTITY = (
    "4888f67cacb175ad4bf41195c1c4dc9465e653485e05b53f5ca33a61ad93eba5"
)
MAX_CONTROL_STEPS = 2500
CONTROL_DT = 0.010
PHYSICS_DT = 0.002
CONTROL_SUBSTEPS = 5


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping in {path}")
    return value


def _manifest_and_rows() -> tuple[dict, dict[str, dict[int, dict]]]:
    manifest, digest = _verify_dataset()
    if digest != EXPECTED_MANIFEST_SHA256:
        raise ValueError("d3_dataset_identity: manifest SHA256 mismatch")
    if manifest["logical_identity"] != EXPECTED_LOGICAL_DATASET_IDENTITY:
        raise ValueError("d3_dataset_identity: logical identity mismatch")
    if manifest["identities"]["task_artifact"] != EXPECTED_ARTIFACT_SHA256:
        raise ValueError("d3_artifact_identity: TaskArtifact mismatch")
    rows = {
        role: {int(row["seed"]): row for row in manifest["trajectories"][role]}
        for role in ("train", "validation")
    }
    return manifest, rows


def _spread_indices(count: int) -> list[int]:
    return [i * (count - 1) // 9 for i in range(10)]


def freeze_spec() -> dict:
    """Freeze sorted mechanical cohorts and serialized source ResetSamples."""
    spec_path = EVIDENCE_ROOT / "d3_eval_spec.yaml"
    lock_path = EVIDENCE_ROOT / "d3_eval_spec_lock.json"
    if spec_path.exists() or lock_path.exists():
        raise FileExistsError("refusing to replace an existing D3 spec or lock")
    manifest, rows = _manifest_and_rows()
    manifest_sha = sha256_file(MANIFEST)
    config_path = VARIANT_ROOT / "resolved_config.yaml"
    config = load_variant_config(config_path)
    config_sha = config_identity(config)
    if config_sha != EXPECTED_CONFIG_SHA256:
        raise ValueError("d3_config_identity: resolved V2a config mismatch")
    checkpoint_sha = sha256_file(CHECKPOINT)
    if checkpoint_sha != EXPECTED_CHECKPOINT_SHA256:
        raise ValueError("d3_checkpoint_identity: frozen V2a final checkpoint mismatch")

    # The H5 metadata is the already-serialized corpus ResetSample. D3 copies
    # that value once into the locked spec and both providers read this mapping.
    cohorts: dict[str, list[dict]] = {}
    for role in ("train", "validation"):
        seeds = sorted(int(seed) for seed in manifest[f"selected_{role}_seeds"])
        if len(seeds) != (80 if role == "train" else 20):
            raise ValueError(f"d3_dataset_identity: selected {role} count mismatch")
        indices = _spread_indices(len(seeds))
        chosen = [seeds[index] for index in indices]
        records = []
        for seed in chosen:
            row = rows[role][seed]
            trajectory_path = Path(row["file"])
            if sha256_file(trajectory_path) != row["file_sha256"]:
                raise ValueError(f"d3_dataset_identity: trajectory file changed for {seed}")
            trajectory = load_trajectory(trajectory_path)
            if trajectory.identity_hash != row["logical_hash"]:
                raise ValueError(f"d3_dataset_identity: logical trajectory changed for {seed}")
            if (
                trajectory.metadata.task_seed != seed
                or not trajectory.boundaries[-1].is_success
                or trajectory.stop_reason != "expert_endpoint"
            ):
                raise ValueError(f"d3_dataset_identity: invalid successful route for {seed}")
            sample = trajectory.metadata.reset_sample
            sample_mapping = sample.to_mapping()
            if (
                sample.identity_hash != row["reset_sample_hash"]
                or sample.task_artifact_hash != EXPECTED_ARTIFACT_SHA256
                or sample.task_seed != seed
            ):
                raise ValueError(f"d3_reset_sample_identity: sample mismatch for {seed}")
            records.append(
                {
                    "seed": seed,
                    "selection_index": indices[chosen.index(seed)],
                    "trajectory_path": str(trajectory_path),
                    "trajectory_logical_hash": trajectory.identity_hash,
                    "trajectory_file_sha256": row["file_sha256"],
                    "reset_sample_id": sample.sample_id,
                    "reset_sample_hash": sample.identity_hash,
                    "reset_sample": sample_mapping,
                }
            )
        cohorts[role] = records

    # Derive the concrete 100 Hz artifact without materializing either provider.
    _, artifact, _, _, _, _ = context("cpu")
    if artifact.identity_hash != EXPECTED_ARTIFACT_SHA256:
        raise ValueError("d3_artifact_identity: current source does not build expected artifact")
    train_spec = _yaml(TRAIN_ROOT / "training_spec.yaml")
    rollout_spec = _yaml(VARIANT_ROOT / "rollout_spec.yaml")
    if rollout_spec.get("checkpoint_sha256") != checkpoint_sha:
        raise ValueError("d3_checkpoint_identity: V2a rollout spec checkpoint mismatch")
    if rollout_spec.get("dataset_manifest_sha256") != manifest_sha:
        raise ValueError("d3_dataset_identity: V2a rollout spec manifest mismatch")
    if train_spec.get("resolved_config_sha256") != config_sha:
        raise ValueError("d3_config_identity: V2a training spec config mismatch")

    spec = {
        "schema": "p1_6-d3-cross-provider-evaluation-v0",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "policy": "Flow_Vanilla / ConditionalUnet1D",
            "checkpoint_role": "final",
            "checkpoint_path": str(CHECKPOINT),
            "checkpoint_sha256": checkpoint_sha,
            "config_path": str(VARIANT_ROOT / "resolved_config.yaml"),
            "resolved_config_sha256": config_sha,
            "dataset_manifest_path": str(MANIFEST),
            "dataset_manifest_sha256": manifest_sha,
            "dataset_logical_identity": manifest["logical_identity"],
            "task_artifact_sha256": artifact.identity_hash,
            "observation_contract_identity": OBSERVATION_IDENTITY,
            "action_contract_identity": ACTION_IDENTITY,
            "observation": {"state_dim": 26, "excluded_fields": ["arm_velocity7"]},
            "action": {"mode": "absolute_joint", "dimension": 8},
            "horizons": {"obs": 2, "pred": 50, "act": 36},
            "normalization": "checkpoint-frozen train-only state mean/std and action q01-q99",
            "policy_device": "cuda",
        },
        "temporal_profile": {
            "physics_dt": PHYSICS_DT,
            "control_substeps": CONTROL_SUBSTEPS,
            "control_dt": CONTROL_DT,
            "physics_frequency_hz": 1.0 / PHYSICS_DT,
            "control_frequency_hz": 1.0 / CONTROL_DT,
        },
        "providers": {
            "geophys": {"physics_backend": "cuda", "session_route": "existing diagnostic-only P1.6 CUDA route"},
            "mujoco": {"physics_backend": "cpu", "session_route": "admitted P1.2 controlled runtime adapter"},
        },
        "execution": {
            "same_reset_sample_for_both_providers": True,
            "provider_resampling": False,
            "provider_specific_policy_patch": False,
            "controller": "ProductionCanonicalPandaController",
            "public_action_route": "absolute_joint -> canonical controller -> target -> provider session",
            "success_predicate": "cube_lift >= 0.10 m",
            "max_control_steps_per_episode": MAX_CONTROL_STEPS,
            "policy_rng_rule": "100000 + task_seed; one sample realization per seed/provider",
            "synchronous_inference": True,
            "simulator_frozen_during_inference": True,
            "cohort_selection": "sort selected role seeds ascending; indices floor(i*(N-1)/9), i=0..9",
        },
        "cohorts": cohorts,
    }
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    spec_bytes = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True).encode("utf-8")
    spec_path.write_bytes(spec_bytes)
    digest = _sha256_bytes(spec_bytes)
    lock = {
        "schema": "p1_6-d3-eval-spec-lock-v0",
        "algorithm": "sha256",
        "sha256": digest,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "first_provider_rollout_after_lock": True,
    }
    write_json(lock_path, lock)
    return {"spec": spec, "sha256": digest, "lock": lock}


def _provider_context(provider: str, seed: int):
    backend = "cuda" if provider == "geophys" else "cpu"
    _, artifact, source, _, controller, _ = context(backend)
    if provider == "geophys":
        session = open_geophys_cuda_session(artifact, source)
    elif provider == "mujoco":
        from task_env.runtime.sessions.control import ControlBinding, materialize_control
        from task_env.runtime.sessions.api import provider_manifest

        manifest = provider_manifest("mujoco")
        execution = ExecutionSpec(
            physics_provider="mujoco",
            physics_profile=manifest.physics_profile,
            render_provider="none",
            backend="cpu",
            provider_seed=int(seed),
            determinism_mode="strict",
        )
        session = materialize_control(
            artifact,
            execution,
            source=source,
            binding=ControlBinding("panda-v1/gripper", 0.08),
        )
    else:
        raise ValueError(f"unsupported D3 provider: {provider}")
    return artifact, source, controller, session, backend


def _load_spec() -> tuple[dict, str]:
    spec_path = EVIDENCE_ROOT / "d3_eval_spec.yaml"
    lock_path = EVIDENCE_ROOT / "d3_eval_spec_lock.json"
    spec_bytes = spec_path.read_bytes()
    spec_sha = _sha256_bytes(spec_bytes)
    lock = json.loads(lock_path.read_text())
    if lock.get("sha256") != spec_sha:
        raise ValueError("D3 evaluation spec lock mismatch")
    return yaml.safe_load(spec_bytes), spec_sha


def run_one(provider: str, cohort: str, seed: int, output_dir: Path) -> dict:
    if provider not in ("geophys", "mujoco") or cohort not in ("train_support", "validation_support"):
        raise ValueError("invalid provider/cohort")
    report_path = output_dir / "report.json"
    trace_path = output_dir / "trace.json"
    if report_path.exists() or trace_path.exists():
        raise FileExistsError(f"refusing to rerun/overwrite D3 evidence at {output_dir}")
    spec, spec_sha = _load_spec()
    role = "train" if cohort == "train_support" else "validation"
    sample_record = next(
        (item for item in spec["cohorts"][role] if int(item["seed"]) == int(seed)), None
    )
    if sample_record is None:
        raise ValueError("seed is not in the locked D3 cohort")
    sample = ResetSample.from_mapping(sample_record["reset_sample"])
    if sample.identity_hash != sample_record["reset_sample_hash"]:
        raise ValueError("locked ResetSample hash mismatch")

    candidate = spec["candidate"]
    if sha256_file(CHECKPOINT) != candidate["checkpoint_sha256"]:
        raise ValueError("d3_checkpoint_identity: checkpoint bytes changed")
    if sha256_file(MANIFEST) != candidate["dataset_manifest_sha256"]:
        raise ValueError("d3_dataset_identity: manifest bytes changed")
    config = load_variant_config(candidate["config_path"])
    actual_config_sha = config_identity(config)
    if actual_config_sha != candidate["resolved_config_sha256"]:
        raise ValueError("d3_config_identity: resolved config changed")
    agent = make_agent("Flow_Vanilla", config)
    checkpoint_meta = agent.load(str(CHECKPOINT))
    if checkpoint_meta.get("artifact_identity") != config.agent_sp.artifact_identity:
        raise ValueError("checkpoint artifact identity mismatch")
    agent.to(torch.device("cuda"))
    agent.eval()

    policy_seed = 100000 + int(seed)
    random.seed(policy_seed)
    np.random.seed(policy_seed)
    torch.manual_seed(policy_seed)
    torch.cuda.manual_seed_all(policy_seed)

    artifact = source = controller = session = None
    trace: list[dict] = []
    h2d: list[float] = []
    inference: list[float] = []
    d2h: list[float] = []
    max_lift = -math.inf
    runtime_error = None
    stage = "provider_materialization"
    stop_reason = "control_step_budget"
    try:
        artifact, source, controller, session, physics_backend = _provider_context(provider, seed)
        if artifact.identity_hash != candidate["task_artifact_sha256"]:
            raise ValueError("provider context built the wrong TaskArtifact")
        if (
            artifact.timebase.physics_dt != PHYSICS_DT
            or artifact.timebase.control_substeps != CONTROL_SUBSTEPS
            or artifact.timebase.control_dt != CONTROL_DT
        ):
            raise ValueError("100 Hz TaskArtifact timebase mismatch")
        stage = "reset"
        sample_before = sample.to_mapping()
        realized = session.reset(sample)
        state = session.snapshot()
        if state.control_step != 0 or state.simulation_time != 0.0:
            raise ValueError("reset did not establish canonical step=0,time=0")
        feedback = session.control_feedback(state)
        controller.reset(state, feedback)
        obs, info, _evaluation = observation(state, artifact)
        excluded_fields = candidate["observation"]["excluded_fields"]

        def policy_features(current_state, current_feedback):
            return select_observation_features(
                features(current_state, current_feedback), excluded_fields
            )

        history = [policy_features(state, feedback)]
        max_lift = float(info["task_metrics"]["cube_lift"])
        issued = replans = clip_count = 0
        clip_dimensions = np.zeros(8, dtype=np.int64)
        max_violation = np.zeros(8, dtype=np.float64)
        inference_freeze_checks = 0
        finite_actions = True
        target_deltas: list[float] = []
        servo_deltas: list[float] = []
        gripper_deltas: list[float] = []
        previous_target = None
        stage = "policy_rollout"
        while state.control_step < MAX_CONTROL_STEPS and not info["is_success"] and not info["task_failure"]:
            recent = [history[0]] * 2 if len(history) < 2 else history[-2:]
            cpu_obs = torch.from_numpy(np.stack(recent).astype(np.float32, copy=False)).unsqueeze(0).contiguous()
            torch.cuda.synchronize()
            started = time.perf_counter()
            gpu_obs = cpu_obs.to("cuda", non_blocking=False)
            torch.cuda.synchronize()
            h2d.append(time.perf_counter() - started)

            before_step = int(state.control_step)
            before_time = float(state.simulation_time)
            torch.cuda.synchronize()
            started = time.perf_counter()
            action_chunk = agent.sample_action({"state": gpu_obs})
            torch.cuda.synchronize()
            inference.append(time.perf_counter() - started)
            if tuple(action_chunk.shape) != (1, 50, 8):
                raise ValueError(f"Flow output shape mismatch: {tuple(action_chunk.shape)}")
            if not bool(torch.isfinite(action_chunk).all()):
                finite_actions = False
                stop_reason = "nonfinite_action"
                break
            started = time.perf_counter()
            chunk = action_chunk[0].detach().to("cpu", non_blocking=False).numpy().copy()
            torch.cuda.synchronize()
            d2h.append(time.perf_counter() - started)
            frozen = session.snapshot()
            if frozen.control_step != before_step or frozen.simulation_time != before_time:
                raise RuntimeError("simulator advanced during synchronous inference")
            inference_freeze_checks += 1
            replans += 1

            for chunk_index in range(min(36, MAX_CONTROL_STEPS - state.control_step)):
                action = np.asarray(chunk[chunk_index], dtype=np.float32)
                request = requested_action(action)
                canonical, target = controller.compute(state, feedback, request)
                interpreted = np.asarray(canonical.interpreted_values, dtype=np.float64).reshape(-1)
                if interpreted.shape != (8,):
                    raise ValueError("absolute_joint canonical action must be 8D")
                violation = np.abs(action.astype(np.float64) - interpreted)
                max_violation = np.maximum(max_violation, violation)
                clip_dimensions += (violation > 1e-8).astype(np.int64)
                clip_count += int(bool(canonical.clipped))
                issued += 1

                applied = session.apply_control(target)
                next_state = session.step()
                next_feedback = session.control_feedback(next_state)
                if next_state.control_step != state.control_step + 1:
                    raise RuntimeError("canonical control_step did not advance once")
                delta_t = next_state.simulation_time - state.simulation_time
                if abs(delta_t - CONTROL_DT) > 1e-9:
                    raise RuntimeError(f"canonical timebase delta mismatch: {delta_t}")
                _next_obs, next_info, _next_eval = observation(next_state, artifact)
                cube_position = np.asarray(next_state.pose_world["cube-v1"].position, dtype=np.float64)
                row = {
                    "control_step": int(next_state.control_step),
                    "simulation_time": float(next_state.simulation_time),
                    "requested_absolute_joint": action.astype(float).tolist(),
                    "canonical_action": canonical.to_mapping(),
                    "target": target.to_mapping(),
                    "controller_target": target.to_mapping(),
                    "applied_control": applied.to_mapping(),
                    "arm_position": {name: float(next_state.joint_position[name]) for name in ARM},
                    "arm_velocity": {name: float(next_state.joint_velocity[name]) for name in ARM},
                    "ee_pose": next_state.pose_world["panda-v1/ee"].to_mapping(),
                    "cube_pose": next_state.pose_world["cube-v1"].to_mapping(),
                    "cube_position": cube_position.tolist(),
                    "measured_gripper_opening_m": float(next_feedback.gripper.opening_m),
                    "closing_force_N": float(next_feedback.gripper.closing_force_N),
                    "task_metrics": {str(k): float(v) for k, v in next_info["task_metrics"].items()},
                    "is_success": bool(next_info["is_success"]),
                    "task_failure": bool(next_info["task_failure"]),
                    "finite_state": finite_state(next_state),
                    "finite_action": bool(np.isfinite(action).all()),
                    "action_clipped": bool(canonical.clipped),
                }
                trace.append(row)
                if previous_target is not None:
                    target_deltas.append(max(abs(target.arm_position[n] - previous_target.arm_position[n]) for n in ARM))
                    servo_deltas.append(max(abs(target.arm_servo_position[n] - previous_target.arm_servo_position[n]) for n in ARM))
                    gripper_deltas.append(abs(target.gripper.opening_m - previous_target.gripper.opening_m))
                previous_target = target
                if not row["finite_state"]:
                    stop_reason = "nonfinite_state"
                state, feedback, info = next_state, next_feedback, next_info
                history.append(policy_features(state, feedback))
                max_lift = max(max_lift, float(info["task_metrics"]["cube_lift"]))
                if info["is_success"]:
                    stop_reason = "task_success"
                    break
                if info["task_failure"]:
                    stop_reason = "task_failure"
                    break
                if stop_reason == "nonfinite_state":
                    break
            if stop_reason in ("task_success", "task_failure", "nonfinite_state", "nonfinite_action"):
                break

        if info.get("is_success"):
            stop_reason = "task_success"
        elif info.get("task_failure"):
            stop_reason = "task_failure"
        sample_after = sample.to_mapping()
        provider_version = None
        try:
            from task_env.runtime.sessions.provenance import provider_build_identity
            provider_version = provider_build_identity(provider)
        except Exception as exc:  # provenance helper failure is preserved in report
            provider_version = {"error": f"{type(exc).__name__}: {exc}"}
        result = {
            "schema": "p1_6-d3-policy-episode-v0",
            "provider": provider,
            "cohort": cohort,
            "seed": int(seed),
            "sample_id": sample.sample_id,
            "reset_sample_hash": sample.identity_hash,
            "reset_sample_hash_in_manifest": sample_record["reset_sample_hash"],
            "reset_sample_unchanged": sample_before == sample_after,
            "checkpoint_sha256": candidate["checkpoint_sha256"],
            "resolved_config_sha256": candidate["resolved_config_sha256"],
            "dataset_manifest_sha256": candidate["dataset_manifest_sha256"],
            "task_artifact_sha256": artifact.identity_hash,
            "observation_contract_identity": candidate["observation_contract_identity"],
            "action_contract_identity": candidate["action_contract_identity"],
            "provider_build_identity": provider_version,
            "policy_rng_seed": policy_seed,
            "policy_device": "cuda",
            "physics_backend": physics_backend,
            "physics_dt": PHYSICS_DT,
            "control_substeps": CONTROL_SUBSTEPS,
            "control_dt": CONTROL_DT,
            "control_frequency_hz": 100.0,
            "success": bool(info["is_success"]),
            "success_predicate": "cube_lift >= 0.10 m",
            "max_cube_lift_m": float(max_lift),
            "control_frames": int(state.control_step),
            "simulated_duration_s": float(state.simulation_time),
            "replan_count": replans,
            "issued_policy_action_count": issued,
            "action_clipping_count": clip_count,
            "action_clipping_rate": clip_count / issued if issued else 0.0,
            "per_dimension_clip_count": clip_dimensions.tolist(),
            "max_preclamp_violation": max_violation.tolist(),
            "finite_state": finite_state(state) and all(row["finite_state"] for row in trace),
            "finite_action": finite_actions and all(row["finite_action"] for row in trace),
            "simulator_frozen_during_inference": inference_freeze_checks == replans,
            "inference_freeze_checks": inference_freeze_checks,
            "failure_reason": stop_reason if not info["is_success"] else None,
            "latency_ms": {
                "h2d_p50": percentile_ms(h2d, 50),
                "h2d_p95": percentile_ms(h2d, 95),
                "inference_p50": percentile_ms(inference, 50),
                "inference_p95": percentile_ms(inference, 95),
                "d2h_p50": percentile_ms(d2h, 50),
                "d2h_p95": percentile_ms(d2h, 95),
                "inference_calls": len(inference),
            },
            "max_per_step_arm_target_delta_rad": max(target_deltas) if target_deltas else 0.0,
            "max_per_step_arm_servo_delta_rad": max(servo_deltas) if servo_deltas else 0.0,
            "max_per_step_gripper_opening_delta_m": max(gripper_deltas) if gripper_deltas else 0.0,
            "close_window": _close_metrics(trace),
            "d3_spec_sha256": spec_sha,
            "runner_source_commit": spec["source_commit"],
            "trace_path": str(trace_path),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        runtime_error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        result = {
            "schema": "p1_6-d3-policy-episode-v0",
            "provider": provider,
            "cohort": cohort,
            "seed": int(seed),
            "reset_sample_id": sample.sample_id,
            "reset_sample_hash": sample.identity_hash,
            "checkpoint_sha256": candidate["checkpoint_sha256"],
            "task_artifact_sha256": candidate["task_artifact_sha256"],
            "d3_spec_sha256": spec_sha,
            "policy_device": "cuda",
            "physics_backend": "cuda" if provider == "geophys" else "cpu",
            "stage": stage,
            "runtime_error": runtime_error,
            "success": False,
            "failure_reason": f"{stage}:{type(exc).__name__}: {exc}",
            "control_frames": len(trace),
            "trace_path": str(trace_path),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as exc:
                result = result or {}
                result["close_error"] = f"{type(exc).__name__}: {exc}"
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(trace_path, trace)
    write_json(report_path, result)
    return result


def run_matrix() -> dict:
    spec, spec_sha = _load_spec()
    all_results = []
    interpreter = sys.executable
    for role, cohort in (("train", "train_support"), ("validation", "validation_support")):
        for provider in ("geophys", "mujoco"):
            for item in spec["cohorts"][role]:
                seed = int(item["seed"])
                output_dir = EVIDENCE_ROOT / cohort / provider / f"seed{seed}"
                output_dir.mkdir(parents=True, exist_ok=True)
                report_path = output_dir / "report.json"
                if report_path.exists():
                    raise FileExistsError(f"D3 episode already exists; no retry: {report_path}")
                command = [
                    interpreter,
                    "-m",
                    "task_env.diagnostics.phase1.policy_search.d3_cross_provider",
                    "--run-one",
                    "--provider",
                    provider,
                    "--cohort",
                    cohort,
                    "--seed",
                    str(seed),
                    "--output-dir",
                    str(output_dir),
                ]
                (output_dir / "command.txt").write_text(" ".join(command) + "\n")
                env = os.environ.copy()
                env["PYTHONPATH"] = "GeoPhys/src:."
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                proc = subprocess.run(
                    command,
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                (output_dir / "stdout.log").write_text(proc.stdout)
                (output_dir / "stderr.log").write_text(proc.stderr)
                if not report_path.exists():
                    write_json(
                        report_path,
                        {
                            "schema": "p1_6-d3-policy-episode-v0",
                            "provider": provider,
                            "cohort": cohort,
                            "seed": seed,
                            "success": False,
                            "runtime_error": {
                                "type": "WorkerProcessFailure",
                                "exit_code": proc.returncode,
                                "stdout_path": str(output_dir / "stdout.log"),
                                "stderr_path": str(output_dir / "stderr.log"),
                            },
                            "d3_spec_sha256": spec_sha,
                        },
                    )
                episode = json.loads(report_path.read_text())
                episode["worker_exit_code"] = proc.returncode
                write_json(report_path, episode)
                all_results.append(episode)
                # Stop immediately if a provider cannot even materialize/run a
                # session; repeating a broken software route cannot add signal.
                if episode.get("stage") == "provider_materialization" and episode.get("runtime_error"):
                    summary = _summarize(spec, spec_sha, all_results, incomplete=True)
                    write_json(EVIDENCE_ROOT / "d3_summary.json", summary)
                    return summary
    summary = _summarize(spec, spec_sha, all_results, incomplete=False)
    write_json(EVIDENCE_ROOT / "d3_summary.json", summary)
    (EVIDENCE_ROOT / "d3_summary.md").write_text(_summary_markdown(summary))
    return summary


def _summarize(spec: dict, spec_sha: str, episodes: list[dict], *, incomplete: bool) -> dict:
    by = {(e.get("cohort"), e.get("provider")): [] for e in episodes}
    for episode in episodes:
        by.setdefault((episode.get("cohort"), episode.get("provider")), []).append(episode)
    cells = {}
    for cohort in ("train_support", "validation_support"):
        cells[cohort] = {}
        for provider in ("geophys", "mujoco"):
            rows = by.get((cohort, provider), [])
            cells[cohort][provider] = {
                "completed": len(rows),
                "successes": sum(bool(row.get("success")) for row in rows),
                "failures": sum(not bool(row.get("success")) for row in rows),
                "success_rate": (sum(bool(row.get("success")) for row in rows) / len(rows)) if rows else None,
                "runtime_errors": sum(bool(row.get("runtime_error")) for row in rows),
                "episodes": rows,
            }
    paired = {}
    for cohort in ("train_support", "validation_support"):
        role = "train" if cohort == "train_support" else "validation"
        pairs = {}
        geo = {int(e["seed"]): e for e in by.get((cohort, "geophys"), [])}
        muj = {int(e["seed"]): e for e in by.get((cohort, "mujoco"), [])}
        for row in spec["cohorts"][role]:
            seed = int(row["seed"])
            if seed in geo and seed in muj:
                a = "PASS" if geo[seed].get("success") else "FAIL"
                b = "PASS" if muj[seed].get("success") else "FAIL"
                pairs[str(seed)] = f"{a}/{b}"
        paired[cohort] = pairs
    combined_counts = {key: 0 for key in ("PASS/PASS", "PASS/FAIL", "FAIL/PASS", "FAIL/FAIL")}
    for value in [*paired["train_support"].values(), *paired["validation_support"].values()]:
        combined_counts[value] += 1
    provider_complete = {}
    for provider in ("geophys", "mujoco"):
        rows = [e for e in episodes if e.get("provider") == provider]
        provider_complete[provider] = len(rows) == 20 and not any(e.get("runtime_error") for e in rows)
    return {
        "schema": "p1_6-d3-cross-provider-summary-v0",
        "status": "incomplete_runtime_failure" if incomplete else "completed",
        "d3_spec_sha256": spec_sha,
        "checkpoint_sha256": spec["candidate"]["checkpoint_sha256"],
        "task_artifact_sha256": spec["candidate"]["task_artifact_sha256"],
        "dataset_manifest_sha256": spec["candidate"]["dataset_manifest_sha256"],
        "resolved_config_sha256": spec["candidate"]["resolved_config_sha256"],
        "selected_train_seeds": [row["seed"] for row in spec["cohorts"]["train"]],
        "selected_validation_seeds": [row["seed"] for row in spec["cohorts"]["validation"]],
        "cells": cells,
        "paired_outcomes": paired,
        "paired_counts": combined_counts,
        "paired_agreement_count": combined_counts["PASS/PASS"] + combined_counts["FAIL/FAIL"],
        "software_checkpoint_portability": all(provider_complete.values()),
        "provider_specific_policy_patch": False,
        "same_checkpoint_bytes": all(e.get("checkpoint_sha256", spec["candidate"]["checkpoint_sha256"]) == spec["candidate"]["checkpoint_sha256"] for e in episodes),
        "same_reset_samples": all(e.get("reset_sample_unchanged", False) for e in episodes if "runtime_error" not in e),
        "policy_device": "cuda",
        "simulator_frozen_checks_all_pass": all(e.get("simulator_frozen_during_inference", False) for e in episodes if "runtime_error" not in e),
        "statistical_robustness_claim": False,
        "provider_wide_qualification_claim": False,
        "p1_6_formal_closure_decision": "pending Human Review",
        "episodes_completed": len(episodes),
        "episodes": episodes,
    }


def _summary_markdown(summary: dict) -> str:
    cells = summary["cells"]
    lines = [
        "# P1.6 D3 Cross-Provider Policy Check",
        "",
        f"Status: `{summary['status']}`",
        f"Spec SHA256: `{summary['d3_spec_sha256']}`",
        f"Checkpoint SHA256: `{summary['checkpoint_sha256']}`",
        "",
        "| Cohort | GeoPhys | MuJoCo |",
        "|---|---:|---:|",
    ]
    for cohort, title in (("train_support", "Train support 10"), ("validation_support", "Validation support 10")):
        left, right = cells[cohort]["geophys"], cells[cohort]["mujoco"]
        lines.append(f"| {title} | {left['successes']}/{left['completed']} | {right['successes']}/{right['completed']} |")
    lines.extend([
        "",
        f"Software/checkpoint portability: `{summary['software_checkpoint_portability']}`",
        f"Provider-specific policy patch: `{summary['provider_specific_policy_patch']}`",
        f"Same ResetSamples: `{summary['same_reset_samples']}`",
        "Statistical robustness and provider-wide qualification are not claimed.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-spec", action="store_true")
    parser.add_argument("--run-one", action="store_true")
    parser.add_argument("--run-matrix", action="store_true")
    parser.add_argument("--provider", choices=("geophys", "mujoco"))
    parser.add_argument("--cohort", choices=("train_support", "validation_support"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    modes = sum((args.freeze_spec, args.run_one, args.run_matrix))
    if modes != 1:
        parser.error("choose exactly one of --freeze-spec, --run-one, or --run-matrix")
    if args.freeze_spec:
        print(json.dumps(freeze_spec(), indent=2, sort_keys=True))
    elif args.run_matrix:
        print(json.dumps(run_matrix(), indent=2, sort_keys=True, allow_nan=False))
    else:
        if args.provider is None or args.cohort is None or args.seed is None or args.output_dir is None:
            parser.error("--run-one requires --provider, --cohort, --seed, and --output-dir")
        result = run_one(args.provider, args.cohort, args.seed, args.output_dir)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        if result.get("runtime_error"):
            raise SystemExit(2)


if __name__ == "__main__":
    main()
