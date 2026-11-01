"""Run the DG04 formal cell through SelectedReferenceEnv and the Core Runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np


CORE = Path(__file__).resolve().parents[3]
ISAAC_ROOT = CORE / "workspace/environments/isaacsim-6.2.0"
CORE_SITE = Path("/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages")


def _python_dependency_setup() -> None:
    if (Path(sys.executable).resolve() != (ISAAC_ROOT / "bin/python").resolve()
            or Path(sys.prefix).resolve() != ISAAC_ROOT.resolve()):
        raise RuntimeError("DG04 formal N2 must use the pinned Isaac Sim 6.2 interpreter")
    if os.environ.get("PYTHONPATH"):
        raise RuntimeError("DG04 formal N2 requires inherited PYTHONPATH to be unset")
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    if str(CORE_SITE) not in sys.path:
        # Isaac site-packages stays first; Core's existing environment supplies
        # pure-Python dependencies such as Gymnasium and HDF5.
        sys.path.append(str(CORE_SITE))


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


def _verify_plan(path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    plan_sha = hashlib.sha256(raw).hexdigest()
    if plan_sha != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("DG04 formal N2 plan SHA-256 mismatch")
    plan = json.loads(raw)
    if (plan.get("schema_version") != "f05-dg04-core-n2-plan-v1"
            or plan.get("classification") != (
                "actual Core SelectedReferenceEnv PositionServoV1; "
                "source-bound Isaac 6.2 GPU PhysX native adaptation; bounded diagnostic, not qualification"
            )):
        raise ValueError("unsupported or misclassified DG04 formal plan")
    for row in plan["code"]["tracked_inputs"]:
        source = Path(row["path"]).resolve(strict=True)
        if _sha(source) != row["sha256"]:
            raise ValueError(f"DG04 formal N2 code changed after plan freeze: {source}")
    for label, row in plan["source"].items():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            source = Path(row["path"]).resolve(strict=True)
            if _sha(source) != row["sha256"]:
                raise ValueError(f"DG04 formal N2 source changed after plan freeze: {label}")
    identity = plan["input_identity"]
    core = Path(identity["core_worktree"]).resolve(strict=True)
    head = subprocess.run(["git", "-C", str(core), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "-C", str(core), "branch", "--show-current"],
                            check=True, capture_output=True, text=True).stdout.strip()
    if head != identity["core_input_head"] or branch != identity["core_branch"]:
        raise ValueError("Core branch/HEAD changed after the DG04 N2 plan freeze")
    dirty = subprocess.run(
        ["git", "-C", str(core), "status", "--porcelain=v1", "--untracked-files=all"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    if sorted(dirty) != identity["expected_git_status_lines"]:
        raise ValueError(f"Core dirty paths differ from plan freeze: {dirty!r}")
    if int(plan["oracle"]["episode_count"]) != 2 or int(plan["limits"]["physics_steps_reserved"]) != 3000:
        raise ValueError("DG04 formal N2 must reserve exactly two episodes and 3000 accepted steps")
    return plan, plan_sha


def _counter_update(path: Path, plan: dict, *, completed: bool) -> None:
    counter = json.loads(path.read_text(encoding="utf-8"))
    if counter.get("run_id") != plan["run_id"]:
        raise ValueError("DG04 N2 counter belongs to another run")
    key = "completed_physics_steps" if completed else "attempted_physics_steps"
    value = int(counter[key]) + int(plan["oracle"]["control_substeps"])
    if not completed and value > int(plan["limits"]["physics_steps_reserved"]):
        raise RuntimeError("DG04 N2 attempted to exceed its frozen 3000-step reservation")
    if completed and value > int(counter["attempted_physics_steps"]):
        raise RuntimeError("DG04 N2 completion count exceeds attempted steps")
    counter[key] = value
    _atomic_json(path, counter)


def _candidate_identity(candidate, input_v1) -> dict:
    env = candidate.env
    return {
        "schema_version": input_v1.schema_version,
        "provider": env.provider,
        "backend": env.backend,
        "horizon": int(env.horizon),
        "task_seed": int(input_v1.reset_plan.reset_sample.task_seed),
        "reset_sample_id": input_v1.reset_plan.reset_sample.sample_id,
        "source_id": input_v1.runtime_source.source_id,
        "source_closure_sha256": input_v1.runtime_source.source_closure_digest,
        "task_artifact_identity_sha256": input_v1.artifact.identity_hash,
        "execution_identity_sha256": input_v1.execution.identity_hash,
        "reset_plan_identity_sha256": input_v1.reset_plan.identity_hash,
        "scene_identity_sha256": candidate.scene.identity_hash,
        "control_binding_plan_identity_sha256": candidate.controller_binding_plan.identity_hash,
        "controller_identity_sha256": env.controller.identity,
        "task_source_identity_sha256": input_v1.task_source.identity_hash,
        "kinematics_source_sha256": input_v1.kinematics_source_sha256,
        "task_scene_recipe_sha256": input_v1.task_scene_recipe_sha256,
        "physics_profile": input_v1.execution.physics_profile,
    }


def _run_episode(env, *, plan: dict, episode_index: int, counter_path: Path) -> dict:
    from task_env.diagnostics.tasks.f05_dg02_core_n2_probe import (
        _finite, _pose as _pose_mapping, _record_state, _request, _target_pose,
    )
    from task_env.recorders import load_structured_control_records_h5
    from isaacsim.core.simulation_manager import SimulationManager

    app_steps_before_reset = int(SimulationManager.get_num_physics_steps())
    obs, info = env.reset()
    app_steps_after_reset = int(SimulationManager.get_num_physics_steps())
    if app_steps_after_reset != app_steps_before_reset:
        raise ValueError("DG04 Core reset advanced native physics despite reset_physics_steps_expected=0")
    if env.state.control_step != 0 or abs(float(env.state.simulation_time)) > 1e-12:
        raise ValueError("DG04 Core N2 reset did not start at boundary/time zero")
    if info.get("source_closure_digest") != env.value["source"].source_closure_digest:
        raise ValueError("DG04 reset source closure differs from the actual RuntimeSource")
    initial = _record_state(env)
    if int(env.sample.task_seed) != int(plan["candidate"]["task_seed"]):
        raise ValueError("DG04 reset task seed differs from the frozen candidate")

    output = Path(plan["output"]["episode_h5_paths"][episode_index - 1]).resolve()
    env.start_recording(output)
    expected_dt = float(plan["oracle"]["outer_control_dt_s"])
    phases = plan["oracle"]["schedule"]
    interval_count = int(plan["oracle"]["control_intervals_per_episode"])
    phase_poses = {phase["phase"]: _target_pose(env, phase) for phase in phases}
    boundaries = [initial]
    transitions = []
    run_instance_id = id(env)

    for index in range(interval_count):
        phase = next(row for row in phases if int(row["start"]) <= index < int(row["stop"]))
        before = _record_state(env)
        opening_m = float(phase["opening_m"])
        opening_range_m = float(plan["oracle"]["gripper_opening_range_m"])
        command = (2.0 * opening_m / opening_range_m) - 1.0
        hand_pose = phase_poses[phase["phase"]]
        request = _request(env, hand_pose, command)
        _counter_update(counter_path, plan, completed=False)
        result = env.step(request)
        if type(result) is not tuple or len(result) != 5:
            raise TypeError("DG04 SelectedReferenceEnv.step did not return the ordinary five-value transition")
        obs, reward, terminated, truncated, step_info = result
        after = _record_state(env)
        if after["control_step"] != before["control_step"] + 1:
            raise ValueError("DG04 Core N2 did not advance exactly one public control boundary")
        if abs(after["simulation_time_s"] - before["simulation_time_s"] - expected_dt) > 1e-10:
            raise ValueError("DG04 Core N2 public clock differs from the frozen 10 ms interval")
        final = index == interval_count - 1
        if bool(terminated) or bool(truncated) != final:
            raise RuntimeError(
                f"DG04 Core N2 lifecycle differs from the frozen nonterminal horizon at {index}: "
                f"terminated={terminated}, truncated={truncated}"
            )
        if bool(step_info["task_metrics"]["lifecycle_terminated"]):
            raise RuntimeError("DG04 raw Task lifecycle marked an unexpected terminal transition")
        _counter_update(counter_path, plan, completed=True)
        transitions.append({
            "interval_index": index,
            "phase": phase["phase"],
            "requested_opening_m": opening_m,
            "requested_gripper_command": command,
            "requested_arm_target_position_rad": phase["arm_target_position_rad"],
            "requested_hand_pose_world": _pose_mapping(hand_pose),
            "reward": _finite(reward, "reward"),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "task_raw_lift_predicate": bool(step_info["task_metrics"]["raw_lift_height_predicate"]),
            "task_lifecycle_terminated": bool(step_info["task_metrics"]["lifecycle_terminated"]),
            "before_boundary_index": index,
            "after_boundary_index": index + 1,
        })
        boundaries.append(after)
        _atomic_json(counter_path.with_name("worker_progress.json"), {
            "schema_version": "f05-dg04-core-n2-progress-v1",
            "run_id": plan["run_id"],
            "episode_index": episode_index,
            "completed_control_intervals": index + 1,
            "completed_physics_steps": int(json.loads(counter_path.read_text())["completed_physics_steps"]),
            "updated_monotonic_s": time.monotonic(),
        })

    if len(boundaries) != interval_count + 1 or len(transitions) != interval_count:
        raise ValueError("DG04 Core N2 did not produce the frozen T/T+1 episode shape")
    episode_end = env.stop(f"dg04_core_n2_episode_{episode_index}")
    outcome = episode_end.outcome
    if (outcome.end_reason != "horizon_reached" or outcome.terminated
            or not outcome.truncated or not outcome.bootstrap_allowed):
        raise ValueError("DG04 N2 horizon outcome differs from explicit nonterminal policy")
    recording = env.finish_recording(outcome.end_reason)
    h5_path = Path(recording["path"]).resolve(strict=True)
    if h5_path != output:
        raise ValueError("DG04 Core Recorder finalized a different H5 path")
    with h5_path.open("rb") as stream:
        os.fsync(stream.fileno())
    directory_fd = os.open(h5_path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    cold_metadata = load_structured_control_records_h5(h5_path)
    if (recording["transition_count"] != interval_count
            or recording["observation_count"] != interval_count + 1
            or cold_metadata["transition_count"] != interval_count
            or cold_metadata["observation_count"] != interval_count + 1):
        raise ValueError("DG04 Core Generic H5 finalizer/readback rejected T/T+1 counts")
    return {
        "episode_index": episode_index,
        "run_instance_id": run_instance_id,
        "reset": initial,
        "reset_sample_id": env.sample.sample_id,
        "task_seed": int(env.sample.task_seed),
        "provider": env.provider,
        "backend": env.backend,
        "session_type": f"{type(env.session).__module__}.{type(env.session).__name__}",
        "execution_identity_sha256": env.value["execution_spec_v1"].identity_hash,
        "controller_identity_sha256": env.controller.identity,
        "source_closure_sha256": env.value["source"].source_closure_digest,
        "task_artifact_identity_sha256": env.artifact.identity_hash,
        "scene_identity_sha256": env.position_scene.identity_hash,
        "control_binding_plan_identity_sha256": env.position_plan.identity_hash,
        "transition_count": recording["transition_count"],
        "observation_count": recording["observation_count"],
        "episode_outcome": outcome.to_mapping(),
        "h5_path": str(h5_path),
        "h5_bytes": h5_path.stat().st_size,
        "h5_sha256": _sha(h5_path),
        "durable_file": True,
        "in_process_h5_readback": {
            "transition_count": cold_metadata["transition_count"],
            "observation_count": cold_metadata["observation_count"],
        },
        "boundaries": boundaries,
        "transitions": transitions,
    }


def run(plan_path: Path, sidecar: Path, receipt_path: Path, counter_path: Path) -> dict:
    plan, plan_sha = _verify_plan(plan_path.resolve(strict=True), sidecar.resolve(strict=True))
    run_dir = Path(plan["output"]["run_dir"]).resolve(strict=True)
    if receipt_path.resolve() != Path(plan["output"]["worker_receipt"]).resolve():
        raise ValueError("DG04 N2 worker receipt path differs from frozen plan")
    if counter_path.resolve() != run_dir / "step_counter.json":
        raise ValueError("DG04 N2 counter path differs from frozen plan")
    if (Path(sys.executable).resolve() != (ISAAC_ROOT / "bin/python").resolve()
            or Path(sys.prefix).resolve() != ISAAC_ROOT.resolve()):
        raise RuntimeError("DG04 N2 must use the pinned Isaac Sim 6.2 interpreter")
    if os.environ.get("PYTHONPATH"):
        raise RuntimeError("DG04 N2 requires an unset inherited PYTHONPATH")
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    if str(CORE_SITE) not in sys.path:
        sys.path.append(str(CORE_SITE))

    from task_env.runtime.sessions.isaac_native_io import _process_app_owner
    from task_env.diagnostics.tasks.f05_dg04_native_mimic_core_n1 import (
        _validate_loaded_pxr_paths,
    )
    from task_env.tasks.position_candidate.builder import build_f05_dg04_isaac_native_candidate
    from task_env.tasks.reference_env import SelectedReferenceEnv

    started = time.monotonic()
    app_owner = _process_app_owner()
    app_owner.open()
    pxr_identity = _validate_loaded_pxr_paths()
    from isaacsim.core.simulation_manager import SimulationManager

    bootstrap_steps_after_app_open = int(SimulationManager.get_num_physics_steps())
    input_v1, candidate = build_f05_dg04_isaac_native_candidate(
        plan["source"]["delivery_manifest"]["path"], horizon=300,
    )
    input_v1.validate()
    actual_candidate = _candidate_identity(candidate, input_v1)
    if actual_candidate != plan["candidate"]:
        raise ValueError("rebuilt DG04 full-horizon candidate differs from the frozen source-bound candidate")
    env = candidate.env
    if not isinstance(env, SelectedReferenceEnv) or env.provider != "isaacsim" or env.backend != "cuda":
        raise TypeError("DG04 formal worker did not build the admitted SelectedReferenceEnv CUDA route")
    episodes, primary_error, close_returned = [], None, False
    physics_before = int(SimulationManager.get_num_physics_steps())
    physics_after_formal = None
    try:
        for episode_index in range(1, 3):
            episodes.append(_run_episode(
                env, plan=plan, episode_index=episode_index, counter_path=counter_path,
            ))
        if len({row["run_instance_id"] for row in episodes}) != 1:
            raise ValueError("DG04 formal episodes did not reuse one SelectedReferenceEnv instance")
    except BaseException as error:
        primary_error = error
    finally:
        try:
            physics_after_formal = int(SimulationManager.get_num_physics_steps())
        except BaseException as physics_error:
            if primary_error is None:
                primary_error = physics_error
        try:
            env.close()
            close_returned = True
        except BaseException as cleanup_error:
            if primary_error is None:
                primary_error = cleanup_error
            elif callable(getattr(primary_error, "add_note", None)):
                primary_error.add_note(f"SelectedReferenceEnv.close also failed: {cleanup_error!r}")
    counter = json.loads(counter_path.read_text(encoding="utf-8"))
    expected = int(plan["limits"]["physics_steps_reserved"])
    if primary_error is None and (
        counter.get("attempted_physics_steps") != expected
        or counter.get("completed_physics_steps") != expected
        or physics_after_formal is None
        or physics_after_formal - physics_before != expected
    ):
        primary_error = RuntimeError(
            "DG04 formal step accounting differs from the exact 3000-step reservation: "
            f"counter={counter!r}, public_manager_delta="
            f"{None if physics_after_formal is None else physics_after_formal - physics_before}"
        )
    result = {
        "schema_version": "f05-dg04-core-n2-worker-receipt-v1",
        "run_id": plan["run_id"],
        "plan_sha256": plan_sha,
        "core_head": plan["input_identity"]["core_input_head"],
        "candidate": actual_candidate,
        "pxr_runtime_identity": pxr_identity,
        "bootstrap_steps_at_app_open": bootstrap_steps_after_app_open,
        "formal_physics_steps_public_manager_delta": (
            None if physics_after_formal is None else physics_after_formal - physics_before
        ),
        "physics_steps_attempted": counter.get("attempted_physics_steps"),
        "physics_steps_completed": counter.get("completed_physics_steps"),
        "native_starts": 1,
        "episode_count": len(episodes),
        "episodes": episodes,
        "same_selected_env_instance": bool(episodes) and len({row["run_instance_id"] for row in episodes}) == 1,
        "selected_env_close_returned": close_returned,
        "status": "PRODUCER_COMPLETE_PENDING_INDEPENDENT_COLD_READ" if primary_error is None else "PARTIAL_CORE_N2",
        "wall_seconds_worker": time.monotonic() - started,
    }
    if primary_error is not None:
        result["failure"] = f"{type(primary_error).__name__}: {primary_error}"
        result["traceback"] = "".join(traceback.format_exception(primary_error))
    _atomic_json(receipt_path, result)
    if primary_error is not None:
        raise primary_error
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--counter", type=Path, required=True)
    args = parser.parse_args()
    _python_dependency_setup()
    from task_env.diagnostics.tasks.f05_dg04_native_mimic_core_n1 import _terminate_worker

    try:
        result = run(args.plan, args.plan_sha256, args.receipt, args.counter)
        print(json.dumps({key: value for key, value in result.items() if key != "episodes"},
                         sort_keys=True, indent=2, allow_nan=False))
        _terminate_worker(0)
    except BaseException:
        traceback.print_exc()
        _terminate_worker(1)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
