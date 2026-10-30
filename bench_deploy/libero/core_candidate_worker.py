"""Bounded worker and independent readback for the R07c D01 pilot route.

The worker uses only the SelectedReferenceEnv lifecycle and recording
interfaces.  It owns no reset, control, physics, or recording implementation.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any

import h5py
import numpy as np

from task_env.controllers.canonical.contracts import (
    AppliedMixedActuatorCommandV1, MixedActuatorCommandV1, digest,
)
from task_env.artifacts import PoseWorld, ResetPlanV1, ResetSampleV1
from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest
from task_env.recorders import inspect_trajectory_h5, load_structured_control_records_h5

from .planner import plan_episode_actions, selected_action_from_planner
from .task_contracts import LIBERO_REVISION, ROBOSUITE_REVISION, TASK_1


_TASK1_COMPOSED_XML_SHA256 = "4a922f3729e3f44004579958e719466dbe66f4bfc4162a8221414622aed57fa0"
_TASK1_COMPOSITION_PLAN_SHA256 = "b00fc11157c4d7ea7fee4ecaf8e099f6bf2d780704af802cdcc88b1f8a0ba656"
_TASK1_SOURCE_MANIFEST_SHA256 = "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"
_TASK1_ASSET_CLOSURE_SHA256 = "f56207a835e80c04e7b4746a90fd3fd39b6170326a54b1445df5244d5047ca05"
_TASK1_EXECUTION_SOURCE_CLOSURE_SHA256 = "3881f687e5306ff66b0774b1385bb69716951d52d1f24d9625e1981a40f1a6a7"
_PINNED_MUJOCO_RUNTIME_IDENTITY = {
    "provider_build": {
        "dirty_build_sha256": None,
        "import_origin": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
        "manifest_version": "package:3.8.1",
        "origin_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
        "package_version": "3.8.1", "provider": "mujoco",
        "repository_revision": None,
    },
    "runtime": {
        "api_version": 3008001,
        "binding_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/_functions.cpython-312-x86_64-linux-gnu.so",
        "binding_sha256": "9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3",
        "mapped_native_libraries": [{
            "path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/libmujoco.so.3.8.1",
            "sha256": "8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592",
        }],
        "package_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
        "package_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
        "package_version": "3.8.1",
        "public_header_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/include/mujoco/mujoco.h",
        "public_header_sha256": "d5ccfb227eb06586edfb4def5812a8082c1cbdf8e6dc5c3176abd9772a57fd07",
        "renderer_initialized": False, "runtime_version": "3.8.1",
    },
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _write_solution_source_bundle(output_dir: Path, *,
                                  source_closure_files: Mapping[str, bytes],
                                  composition_plan_bytes: bytes) -> dict[str, Any]:
    """Persist the exact task #1 importer snapshot and selected composition plan."""
    files = dict(source_closure_files)
    if ("canonical-source.xml" not in files or "scene.xml" not in files
            or files["canonical-source.xml"] != files["scene.xml"]):
        raise ValueError("task #1 source bundle must bind identical canonical and importer XML bytes")
    source_xml = files["canonical-source.xml"]
    xml_sha = hashlib.sha256(source_xml).hexdigest()
    closure_digest = _source_closure_digest(files)
    plan = json.loads(bytes(composition_plan_bytes).decode("utf-8"))
    plan_sha = hashlib.sha256(bytes(composition_plan_bytes)).hexdigest()
    if (xml_sha != _TASK1_COMPOSED_XML_SHA256
            or closure_digest != _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256
            or plan_sha != _TASK1_COMPOSITION_PLAN_SHA256
            or plan.get("schema_version") != "libero-source-composition-mjcf-v4"
            or plan.get("identity", {}).get("task_uid") != TASK_1
            or plan.get("identity", {}).get("manifest_sha256") != _TASK1_SOURCE_MANIFEST_SHA256
            or plan.get("identity", {}).get("asset_closure_sha256") != _TASK1_ASSET_CLOSURE_SHA256
            or plan.get("identity", {}).get("source_revisions") != {
                "libero": LIBERO_REVISION, "robosuite": ROBOSUITE_REVISION,
            }
            or plan.get("output", {}).get("composed_mjcf_sha256") != xml_sha):
        raise ValueError("task #1 source bundle differs from the frozen composition/task manifest")
    source_root = output_dir / "source_inputs"
    closure_root = source_root / "closure"
    for logical_path, content in files.items():
        if (type(logical_path) is not str or not logical_path or logical_path.startswith("/")
                or "\\" in logical_path or any(part in {"", ".", ".."} for part in logical_path.split("/"))
                or not isinstance(content, bytes)):
            raise ValueError("task #1 source bundle contains an unsafe path or non-byte payload")
        target = closure_root.joinpath(*logical_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    plan_path = source_root / "composition_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_bytes(bytes(composition_plan_bytes))
    return {
        "schema_version": "r07-v210-task-source-bundle-v1",
        "source_id": f"libero-spatial-pilot-v1:{xml_sha}",
        "canonical_xml_sha256": xml_sha,
        "importer_xml_sha256": hashlib.sha256(files["scene.xml"]).hexdigest(),
        "source_closure_digest": closure_digest,
        "closure_files": list(_source_closure_manifest(files)),
        "composition_plan": {
            "relative_path": "source_inputs/composition_plan.json",
            "bytes": len(composition_plan_bytes),
            "sha256": plan_sha,
        },
    }


def _verify_solution_source_bundle(bundle_path: Path, source_bundle: Any) -> dict[str, Any]:
    """Independently reread and recompute the task #1 immutable source closure."""
    if not isinstance(source_bundle, Mapping) or source_bundle.get("schema_version") != "r07-v210-task-source-bundle-v1":
        raise ValueError("task Solution bundle omits its versioned immutable source inputs")
    closure_rows = source_bundle.get("closure_files")
    if not isinstance(closure_rows, list) or not closure_rows:
        raise ValueError("task Solution source bundle closure manifest is empty")
    closure_root = (bundle_path.parent / "source_inputs/closure").resolve(strict=True)
    if bundle_path.parent not in closure_root.parents:
        raise ValueError("task Solution source closure escaped its worker bundle")
    files: dict[str, bytes] = {}
    for row in closure_rows:
        if not isinstance(row, Mapping):
            raise ValueError("task Solution source closure manifest row is malformed")
        logical = row.get("path")
        if (type(logical) is not str or not logical or logical.startswith("/")
                or "\\" in logical or any(part in {"", ".", ".."} for part in logical.split("/"))
                or logical in files):
            raise ValueError("task Solution source closure path is unsafe or duplicated")
        source_path = (closure_root / logical).resolve(strict=True)
        if closure_root not in source_path.parents:
            raise ValueError("task Solution source closure member escaped its root")
        content = source_path.read_bytes()
        if (len(content) != row.get("size_bytes")
                or hashlib.sha256(content).hexdigest() != row.get("sha256")):
            raise ValueError(f"task Solution source closure bytes differ from their manifest: {logical}")
        files[logical] = content
    nodes = list(closure_root.rglob("*"))
    if any(path.is_symlink() for path in nodes):
        raise ValueError("task Solution source closure contains a symlink")
    actual_paths = {path.relative_to(closure_root).as_posix() for path in nodes if path.is_file()}
    if actual_paths != set(files):
        raise ValueError("task Solution source closure contains missing or unlisted files")
    if (_source_closure_digest(files) != source_bundle.get("source_closure_digest")
            or source_bundle.get("source_closure_digest") != _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256):
        raise ValueError("task Solution source closure digest does not recompute")
    canonical_xml = files.get("canonical-source.xml")
    importer_xml = files.get("scene.xml")
    if (canonical_xml is None or importer_xml != canonical_xml
            or hashlib.sha256(canonical_xml).hexdigest() != source_bundle.get("canonical_xml_sha256")
            or hashlib.sha256(importer_xml).hexdigest() != source_bundle.get("importer_xml_sha256")
            or source_bundle.get("canonical_xml_sha256") != _TASK1_COMPOSED_XML_SHA256
            or source_bundle.get("source_id") != f"libero-spatial-pilot-v1:{_TASK1_COMPOSED_XML_SHA256}"):
        raise ValueError("task Solution source XML identity differs from the pinned task composition")
    plan_info = source_bundle.get("composition_plan")
    if not isinstance(plan_info, Mapping) or plan_info.get("relative_path") != "source_inputs/composition_plan.json":
        raise ValueError("task Solution bundle omits its source composition plan")
    plan_path = (bundle_path.parent / plan_info["relative_path"]).resolve(strict=True)
    if bundle_path.parent not in plan_path.parents:
        raise ValueError("task Solution composition plan escaped the worker bundle")
    plan_bytes = plan_path.read_bytes()
    if (len(plan_bytes) != plan_info.get("bytes")
            or hashlib.sha256(plan_bytes).hexdigest() != plan_info.get("sha256")
            or plan_info.get("sha256") != _TASK1_COMPOSITION_PLAN_SHA256):
        raise ValueError("task Solution composition plan bytes differ from the pinned plan")
    plan = json.loads(plan_bytes.decode("utf-8"))
    identity = plan.get("identity", {})
    if (plan.get("schema_version") != "libero-source-composition-mjcf-v4"
            or identity.get("task_uid") != TASK_1
            or identity.get("manifest_sha256") != _TASK1_SOURCE_MANIFEST_SHA256
            or identity.get("asset_closure_sha256") != _TASK1_ASSET_CLOSURE_SHA256
            or identity.get("source_revisions") != {
                "libero": LIBERO_REVISION, "robosuite": ROBOSUITE_REVISION,
            }
            or plan.get("output", {}).get("composed_mjcf_sha256") != source_bundle.get("canonical_xml_sha256")):
        raise ValueError("task Solution composition plan is not the pinned task #1 source plan")
    return {
        "schema_version": "r07-v210-task-source-bundle-readback-v1",
        "status": "verified_source_closure_and_plan",
        "source_id": source_bundle["source_id"],
        "source_closure_digest": source_bundle["source_closure_digest"],
        "canonical_xml_sha256": source_bundle["canonical_xml_sha256"],
        "composition_plan_sha256": plan_info["sha256"],
        "closure_file_count": len(files),
    }


def _public_motion_metrics(initial_joints: np.ndarray, final_joints: np.ndarray,
                           initial_ee_pose: np.ndarray, final_ee_pose: np.ndarray) -> dict[str, float]:
    """Measure arm, TCP, and signed Panda finger-aperture motion from public state."""
    initial = np.asarray(initial_joints, dtype=np.float64)
    final = np.asarray(final_joints, dtype=np.float64)
    initial_ee = np.asarray(initial_ee_pose, dtype=np.float64)
    final_ee = np.asarray(final_ee_pose, dtype=np.float64)
    if (initial.shape != (9,) or final.shape != (9,)
            or initial_ee.shape != (7,) or final_ee.shape != (7,)
            or not all(np.isfinite(values).all() for values in (initial, final, initial_ee, final_ee))):
        raise ValueError("public motion gate requires finite seven-arm/two-finger and TCP pose receipts")
    # Panda finger_joint2 uses a negative signed coordinate.  Aggregate
    # opening is q1 - q2, matching the public controller's [opening/2,
    # -opening/2] mapping; summing the signed coordinates cancels symmetric
    # motion and understates the physical aperture change.
    initial_opening = float(initial[7] - initial[8])
    final_opening = float(final[7] - final[8])
    return {
        "arm_joint_max_abs_delta_rad": float(np.max(np.abs(final[:7] - initial[:7]))),
        "tcp_translation_delta_m": float(np.linalg.norm(final_ee[:3] - initial_ee[:3])),
        "aggregate_finger_position_delta_m": abs(final_opening - initial_opening),
    }


def _validate_public_motion_gate(summary: Mapping[str, Any], initial_joints: np.ndarray,
                                 final_joints: np.ndarray, initial_ee_pose: np.ndarray,
                                 final_ee_pose: np.ndarray, *, require_thresholds: bool) -> dict[str, float]:
    """Cross-check worker summary against H5 state and enforce the full pilot gate."""
    actual = _public_motion_metrics(initial_joints, final_joints, initial_ee_pose, final_ee_pose)
    for name, value in actual.items():
        reported = summary.get(name)
        if (isinstance(reported, bool) or not isinstance(reported, (int, float))
                or not np.isfinite(reported) or not np.isclose(float(reported), value, rtol=0.0, atol=1e-7)):
            raise ValueError(f"worker motion summary {name} differs from independent public H5 state")
    if require_thresholds:
        if actual["arm_joint_max_abs_delta_rad"] < 0.05 and actual["tcp_translation_delta_m"] < 0.02:
            raise ValueError("per-episode public motion gate requires arm delta >=0.05 rad or TCP delta >=0.02 m")
        if actual["aggregate_finger_position_delta_m"] < 0.005:
            raise ValueError("per-episode public motion gate requires aggregate finger opening delta >=0.005 m")
    return actual


def _validate_physical_state_monitor(
    monitor: Any, progress: Mapping[str, Any], compiled: Mapping[str, Any],
    observed_joints: np.ndarray,
) -> dict[str, Any]:
    """Check the provider's per-native-step physical receipt independently."""
    if not isinstance(monitor, Mapping) or monitor != progress.get("physical_state_monitor"):
        raise ValueError("episode physical-state monitor is missing or differs from public RuntimeSession progress")
    native_steps = progress.get("native_step_count")
    if (monitor.get("schema_version") != "physical-state-monitor-v1"
            or monitor.get("status") != "passed"
            or monitor.get("first_violation") is not None
            or type(native_steps) is not int or native_steps < 0
            or monitor.get("native_step_count") != native_steps
            or monitor.get("samples_including_reset") != native_steps + 1
            or monitor.get("source_id") != progress.get("source_id")
            or monitor.get("source_closure_digest") != progress.get("source_closure_digest")
            or monitor.get("provider_materialization_id") != progress.get("provider_materialization_id")
            or monitor.get("episode_id") != progress.get("episode_id")
            or monitor.get("reset_sample_id") != progress.get("reset_sample_id")
            or monitor.get("canonical_xml_sha256") != compiled.get("canonical_xml_sha256")):
        raise ValueError("physical-state monitor identity, status, or per-step count is invalid")
    expected_model_hash = hashlib.sha256(json.dumps(
        compiled, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if monitor.get("compiled_model_identity_sha256") != expected_model_hash:
        raise ValueError("physical-state monitor is bound to a different compiled model")
    tolerance = monitor.get("tolerance")
    if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not np.isfinite(tolerance) or not 0.0 <= float(tolerance) <= 1.0e-8):
        raise ValueError("physical-state monitor tolerance exceeds the frozen numeric bound")
    limits = compiled.get("named_joint_limits")
    addresses = compiled.get("named_joint_addresses")
    ranges = monitor.get("joint_ranges")
    if not isinstance(limits, Mapping) or not isinstance(addresses, Mapping) or not isinstance(ranges, Mapping):
        raise ValueError("physical-state monitor omits compiled limited-joint bindings")
    expected_limited = {name: row for name, row in limits.items() if row.get("limited") is True}
    if set(ranges) != set(expected_limited):
        raise ValueError("physical-state monitor does not cover every compiled limited scalar joint")
    maximum_excursion = 0.0
    for name, expected in expected_limited.items():
        row = ranges[name]
        low, high = expected.get("range", ())
        if (row.get("joint_name") != expected.get("joint_name")
                or row.get("qpos_address") != addresses.get(name, [None])[0]
                or row.get("range") != expected.get("range")):
            raise ValueError(f"physical-state monitor source range differs from compiled joint: {name}")
        minimum, maximum = row.get("minimum_observed"), row.get("maximum_observed")
        if (type(minimum) not in (int, float) or type(maximum) not in (int, float)
                or not np.isfinite((minimum, maximum)).all() or minimum > maximum):
            raise ValueError(f"physical-state monitor extrema are malformed: {name}")
        excursion = max(0.0, float(low) - float(minimum), float(maximum) - float(high))
        maximum_excursion = max(maximum_excursion, excursion)
        if excursion > float(tolerance):
            raise ValueError(f"measured physical state exceeded a compiled joint limit: {name}")
    reported_excursion = monitor.get("maximum_excursion")
    if (isinstance(reported_excursion, bool) or not isinstance(reported_excursion, (int, float))
            or not np.isfinite(reported_excursion)
            or not np.isclose(float(reported_excursion), maximum_excursion, rtol=0.0, atol=1e-12)):
        raise ValueError("physical-state monitor maximum excursion differs from its recorded extrema")
    warning_counts = monitor.get("warning_counts")
    if (not isinstance(warning_counts, list)
            or len(warning_counts) != 7
            or any(type(value) is not int or value < 0 for value in warning_counts)
            or any(warning_counts)):
        raise ValueError("physical-state monitor omits warning counters or records a MuJoCo warning")
    joint_names = [*(f"joint{i}" for i in range(1, 8)), "finger_joint1", "finger_joint2"]
    if observed_joints.shape[1] != len(joint_names):
        raise ValueError("H5 joint observations do not cover the task's mapped monitor channels")
    for index, name in enumerate(joint_names):
        row = ranges.get(name)
        if row is None:
            raise ValueError(f"physical-state monitor omitted observed task joint: {name}")
        # H5 state channels are float32; this tolerance only accounts for that
        # serialization quantization, not for source-limit excursion.
        if (float(np.min(observed_joints[:, index])) < float(row["minimum_observed"]) - 2.0e-7
                or float(np.max(observed_joints[:, index])) > float(row["maximum_observed"]) + 2.0e-7):
            raise ValueError(f"public H5 joint observations escape the native-step monitor extrema: {name}")
    return {
        "status": "verified_physical_state_monitor",
        "native_step_count": native_steps,
        "samples_including_reset": monitor["samples_including_reset"],
        "limited_joint_count": len(ranges),
        "warning_counts": list(warning_counts),
        "maximum_excursion": float(reported_excursion),
        "tolerance": float(tolerance),
        "compiled_model_identity_sha256": expected_model_hash,
    }


def _validate_parent_run_record(bundle_path: Path, result: Mapping[str, Any],
                                run_record_path: Path, expected_lock_path: Path) -> dict[str, Any]:
    """Bind the semantic bundle to its bounded native parent process receipt."""
    record_path = Path(run_record_path).resolve(strict=True)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    is_solution = result.get("schema_version") == "r07-v210-task-solution-worker-result-v1"
    accepted_schemas = {"r07-v210-required123-run-record-v1"} if is_solution else {"r07c-d01-run-record-v1"}
    if record.get("schema_version") not in accepted_schemas:
        raise ValueError("parent run record schema is unsupported")
    if (record.get("exit_code") != 0 or record.get("termination_reason") is not None
            or record.get("process_group_confirmed_exited") is not True):
        raise ValueError("parent native worker did not exit successfully with its process group closed")
    parent_lock_path = record.get("lock_path")
    if (record.get("lock_acquired") is not True
            or record.get("lock_released_after_group_exit") is not True
            or type(parent_lock_path) is not str
            or Path(parent_lock_path).resolve() != Path(expected_lock_path).resolve()):
        raise ValueError("parent native lock receipt is missing, mismatched, or not released after worker exit")
    argv = record.get("argv")
    if (not isinstance(argv, list) or "-m" not in argv
            or "bench_deploy.libero.core_candidate_worker" not in argv):
        raise ValueError("parent run record does not identify the D01 native worker module")
    if is_solution and "--task-solution-1" not in argv:
        raise ValueError("parent run record does not identify the task #1 Solution route")
    if (not argv or Path(argv[0]).resolve() != Path(sys.executable).resolve()
            or record.get("cwd") != "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora"):
        raise ValueError("parent run record used an unpinned Python interpreter or camera checkout")
    try:
        worker_index = argv.index("--run-worker")
        worker_dir = Path(argv[worker_index + 1]).resolve()
    except (ValueError, IndexError, TypeError) as exc:
        raise ValueError("parent run record omits the worker bundle output directory") from exc
    if worker_dir != bundle_path.parent.resolve():
        raise ValueError("parent run record points to a different worker bundle")
    try:
        steps_index = argv.index("--steps")
        recorded_steps = int(argv[steps_index + 1])
    except (ValueError, IndexError, TypeError) as exc:
        raise ValueError("parent run record omits the bounded D01 step limit") from exc
    counts = [episode.get("h5", {}).get("transition_count") for episode in result.get("episodes", ())]
    if (any(type(value) is not int or value < 1 or value > recorded_steps for value in counts)
            or (not is_solution and any(value != recorded_steps for value in counts))):
        raise ValueError("parent worker step limit differs from one or more episode records")
    environment = record.get("environment")
    expected_pythonpath = (
        "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora/GeoPhys/src:"
        "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora"
    )
    if not isinstance(environment, dict) or environment.get("PYTHONPATH") != expected_pythonpath:
        raise ValueError("parent run record did not use the frozen camera/GeoPhys import path")
    output_root = record_path.parents[2]
    log_paths = {}
    for stream in ("stdout", "stderr"):
        relative = record.get(f"{stream}_path")
        if type(relative) is not str or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"parent run record has an unsafe {stream} path")
        log_path = (output_root / relative).resolve(strict=True)
        if output_root not in log_path.parents:
            raise ValueError(f"parent {stream} path escaped the package output root")
        raw = log_path.read_bytes()
        if len(raw) != record.get(f"{stream}_bytes"):
            raise ValueError(f"parent {stream} byte count differs from its process receipt")
        log_paths[stream] = (log_path, raw)
    stdout_lines = [line for line in log_paths["stdout"][1].decode("utf-8").splitlines() if line.strip()]
    if not stdout_lines:
        raise ValueError("parent native worker stdout omits its completion receipt")
    try:
        worker_stdout = json.loads(stdout_lines[-1])
    except json.JSONDecodeError as exc:
        raise ValueError("parent native worker stdout completion receipt is malformed") from exc
    if (worker_stdout.get("status") != "complete"
            or worker_stdout.get("result_sha256") != result.get("result_sha256")
            or worker_stdout.get("episode_count") != result.get("episode_count")
            or worker_stdout.get("transition_count") != result.get("transition_count")
            or worker_stdout.get("observation_count") != result.get("observation_count")
            or worker_stdout.get("native_step_count") != result.get("native_step_count")):
        raise ValueError("parent stdout result/exit summary does not match the independently read worker bundle")
    return {
        "schema_version": "r07c-d01-parent-process-receipt-v1",
        "status": "verified_parent_exit_and_lock_release",
        "run_record_path": str(record_path),
        "run_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
        "exit_code": 0,
        "termination_reason": None,
        "lock_path": str(Path(expected_lock_path).resolve()),
        "lock_released_after_group_exit": True,
        "process_group_confirmed_exited": True,
        "stdout_path": str(log_paths["stdout"][0]),
        "stderr_path": str(log_paths["stderr"][0]),
    }


def _state_observation_receipt(observation: dict[str, Any]) -> dict[str, Any]:
    state = observation["state"]
    return {
        "joint_position": [float(value) for value in np.asarray(state["joint_position"]).reshape(-1)],
        "ee_pose": [float(value) for value in np.asarray(state["ee_pose"]).reshape(-1)],
        "boundary_identity_sha256": bytes(
            np.asarray(state["boundary_identity_sha256"], dtype=np.uint8).reshape(32)
        ).hex(),
        "privileged_state": {
            name: np.asarray(value).reshape(-1).astype(np.float64).tolist()
            for name, value in observation["privileged_state"].items()
        },
    }


def _episode_record(env, *, output_dir: Path, episode_index: int, row_index: int,
                    seed: int, steps: int) -> dict[str, Any]:
    reset_observation, reset_info = env.reset(
        seed=seed, options={"init_row_index": row_index},
    )
    previous_close = None
    if episode_index:
        # SelectedReferenceEnv closes the previous RuntimeSession before it
        # materializes the next one.  The read-only receipt is captured via
        # its public lifecycle property after that transition.
        previous_close = env.close_receipt
    episode_id = reset_info.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("SelectedReferenceEnv reset omitted its RuntimeSession episode identity")
    reset_sample = reset_info.get("reset_sample_v1")
    reset_realization = reset_info.get("reset_realization_v1")
    reset_readback = reset_info.get("reset_readback_v1")
    if not all(isinstance(item, dict) for item in (reset_sample, reset_realization, reset_readback)):
        raise ValueError("SelectedReferenceEnv reset omitted the versioned source/realization/readback receipts")
    episode_dir = output_dir / f"episode_{episode_index:02d}_row_{row_index:02d}"
    h5_path = episode_dir / "trajectory.h5"
    env.start_recording(h5_path)
    planner_actions = plan_episode_actions(reset_observation, row_index=row_index, steps=steps)
    action_trace = []
    final_info = dict(reset_info)
    final_observation = reset_observation
    terminated = truncated = False
    for planner_action in planner_actions:
        selected_action = selected_action_from_planner(planner_action)
        observation, reward, terminated, truncated, info = env.step(selected_action)
        final_observation, final_info = observation, info
        action_trace.append({
            "planner_action": [float(value) for value in planner_action],
            "selected_public_action": [float(value) for value in selected_action],
            "planner_to_selected_opening_m": float(selected_action[7]),
            "reward": float(reward),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "control_step": int(info.get("control_step", -1)),
            "simulation_time_s": float(info.get("simulation_time_s", float("nan"))),
            "mixed_actuator_command_v1": info.get("mixed_actuator_command_v1"),
            "applied_mixed_actuator_command_v1": info.get("applied_mixed_actuator_command_v1"),
        })
        if terminated or truncated:
            break
    if len(action_trace) != steps:
        raise ValueError(f"selected episode ended after {len(action_trace)} of {steps} planned actions")
    if not (terminated or truncated):
        episode_end = env.stop("bounded_worker_complete")
        end_reason = episode_end.outcome.end_reason
    else:
        end_payload = final_info.get("episode_end_v1")
        if not isinstance(end_payload, dict):
            raise ValueError("terminal public step omitted EpisodeEndV1")
        end_reason = end_payload.get("outcome", {}).get("end_reason")
        if not isinstance(end_reason, str):
            end_reason = "horizon_reached" if truncated else "terminated"
    finalized = env.finish_recording(end_reason)
    h5_path = Path(finalized["path"]).resolve(strict=True)
    h5_bytes = h5_path.read_bytes()
    progress = env.get_runtime_progress_receipt()
    if (progress.get("episode_id") != episode_id
            or progress.get("native_step_count") != steps * 25
            or progress.get("control_step") != steps):
        raise ValueError("public RuntimeSession progress receipt disagrees with the planned episode")
    final_joints = np.asarray(final_observation["state"]["joint_position"], dtype=np.float64)
    initial_joints = np.asarray(reset_observation["state"]["joint_position"], dtype=np.float64)
    if final_joints.shape != (9,) or initial_joints.shape != (9,):
        raise ValueError("public reset/step observation omitted the nine mapped joint positions")
    return {
        "schema_version": "r07c-d01-libero-episode-result-v1",
        "episode_index": episode_index,
        "row_index": row_index,
        "seed": seed,
        "episode_id": episode_id,
        "task_artifact_identity_hash": env.get_record_metadata()["candidate_identity"]["task_artifact_identity_hash"],
        "source_id": reset_info.get("source_id"),
        "source_closure_digest": reset_info.get("source_closure_digest"),
        "compiled_model_layout_v1": reset_info.get("compiled_model_layout_v1"),
        "pre_reset_compiled_validation_v1": reset_info.get("pre_reset_compiled_validation_v1"),
        "reset_sample": reset_sample,
        "reset_realization": reset_realization,
        "reset_readback": reset_readback,
        "prior_session_close_receipt": previous_close,
        "control_plan": env.get_record_metadata()["control_plan"],
        "action_trace": action_trace,
        "motion_summary": _public_motion_metrics(
            initial_joints, final_joints,
            np.asarray(reset_observation["state"]["ee_pose"], dtype=np.float64),
            np.asarray(final_observation["state"]["ee_pose"], dtype=np.float64),
        ),
        "initial_observation": _state_observation_receipt(reset_observation),
        "final_observation": _state_observation_receipt(final_observation),
        "final_info": {
            "predicate_v1": final_info.get("predicate_v1"),
            "contact_summary_v2": final_info.get("contact_summary_v2"),
            "mixed_actuator_command_v1": final_info.get("mixed_actuator_command_v1"),
            "applied_mixed_actuator_command_v1": final_info.get("applied_mixed_actuator_command_v1"),
            "episode_end_v1": final_info.get("episode_end_v1"),
        },
        "runtime_progress": progress,
        "physical_state_monitor": progress.get("physical_state_monitor"),
        "finalizer": finalized,
        "h5": {
            "relative_path": str(h5_path.relative_to(output_dir.resolve())),
            "bytes": len(h5_bytes),
            "sha256": hashlib.sha256(h5_bytes).hexdigest(),
            "schema_version": finalized.get("schema_version"),
            "transition_count": finalized.get("transition_count"),
            "observation_count": finalized.get("observation_count"),
            "episode_id": episode_id,
            "final_boundary": steps,
        },
    }


def _episode_solution_record(env, *, output_dir: Path, episode_index: int,
                             row_index: int, seed: int, max_steps: int,
                             solution_factory) -> dict[str, Any]:
    """Run one task-owned Solution through the same SelectedReferenceEnv."""
    solution = solution_factory()
    if type(getattr(solution, "identity", None)) is not str or len(solution.identity) != 64:
        raise TypeError("task Solution factory must return a versioned 64-hex identity")
    reset_observation, reset_info = env.reset_for_solution(
        solution, seed=seed, options={"init_row_index": row_index},
    )
    previous_close = env.close_receipt if episode_index else None
    episode_id = reset_info.get("episode_id")
    reset_sample = reset_info.get("reset_sample_v1")
    reset_realization = reset_info.get("reset_realization_v1")
    reset_readback = reset_info.get("reset_readback_v1")
    if (type(episode_id) is not str or not episode_id
            or not all(isinstance(value, dict) for value in (
                reset_sample, reset_realization, reset_readback,
            ))):
        raise ValueError("Solution reset omitted its public episode/source/readback receipts")
    episode_dir = output_dir / f"episode_{episode_index:02d}_row_{row_index:02d}"
    episode_dir.mkdir(parents=True, exist_ok=False)
    pre_reset = reset_info.get("pre_reset_compiled_validation_v1")
    if not isinstance(pre_reset, Mapping):
        raise ValueError("Solution reset omitted its pre-reset compiled/runtime identity receipt")
    start_receipt = {
        "schema_version": "r07-v210-task-solution-start-receipt-v1",
        "episode_index": episode_index, "row_index": row_index, "seed": seed,
        "task_uid": env.artifact.task_id,
        "task_artifact_identity_hash": env.artifact.identity_hash,
        "solution_identity": solution.identity,
        "episode_id": episode_id,
        "source_id": reset_info.get("source_id"),
        "source_xml_sha256": reset_info.get("source_xml_sha256"),
        "source_closure_digest": reset_info.get("source_closure_digest"),
        "compiled_model_layout_v1": reset_info.get("compiled_model_layout_v1"),
        "pre_reset_compiled_validation_v1": dict(pre_reset),
        "reset_sample": reset_sample,
        "reset_realization": reset_realization,
        "reset_readback": reset_readback,
    }
    _write_json(episode_dir / "start_receipt.json", start_receipt)
    start_receipt_bytes = (episode_dir / "start_receipt.json").read_bytes()
    h5_path = episode_dir / "trajectory.h5"
    env.start_recording(h5_path)
    final_info = dict(reset_info)
    final_observation = reset_observation
    action_trace = []
    terminated = truncated = False
    try:
        for _ in range(max_steps):
            observation, reward, terminated, truncated, info = env.step_with_solution(solution)
            final_observation, final_info = observation, info
            action_trace.append({
                "solution_action": [float(value) for value in info.get("external_action", ())],
                "solution_stage": info.get("selected_solution_action_v1", {}).get("stage"),
                "solution_diagnostics": info.get("selected_solution_action_v1", {}).get("diagnostics"),
                "reward": float(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "control_step": int(info.get("control_step", -1)),
                "simulation_time_s": float(info.get("simulation_time_s", float("nan"))),
                "mixed_actuator_command_v1": info.get("mixed_actuator_command_v1"),
                "applied_mixed_actuator_command_v1": info.get("applied_mixed_actuator_command_v1"),
            })
            if terminated or truncated or solution.done or solution.failed:
                break
    except BaseException as exc:
        fault = getattr(env, "execution_fault", None)
        failure_receipt = {
            "schema_version": "r07-v210-task-solution-failure-receipt-v1",
            "episode_index": episode_index, "row_index": row_index, "seed": seed,
            "task_uid": env.artifact.task_id,
            "task_artifact_identity_hash": env.artifact.identity_hash,
            "solution_identity": solution.identity,
            "episode_id": episode_id,
            "source_id": reset_info.get("source_id"),
            "source_xml_sha256": reset_info.get("source_xml_sha256"),
            "source_closure_digest": reset_info.get("source_closure_digest"),
            "last_successful_control_step": int(final_info.get("control_step", -1)),
            "next_control_step_attempted": int(final_info.get("control_step", -1)) + 1,
            "last_successful_public_state": _state_observation_receipt(final_observation),
            "last_successful_public_boundary": {
                key: final_info.get(key) for key in (
                    "source_id", "source_closure_digest", "provider_materialization_id",
                    "episode_id", "reset_sample_id", "control_step", "simulation_time_s",
                    "state_revision",
                )
            },
            "solution": solution.outcome_report(),
            "completed_action_trace": action_trace,
            "execution_fault": fault.to_mapping() if hasattr(fault, "to_mapping") else None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        _write_json(episode_dir / "failure_receipt.json", failure_receipt)
        raise
    if not action_trace:
        raise RuntimeError("task Solution produced no public action")
    episode_end = final_info.get("episode_end_v1")
    if not isinstance(episode_end, dict):
        episode_end = env.stop("bounded_solution_worker_complete").to_mapping()
    end_reason = episode_end.get("outcome", {}).get("end_reason")
    if type(end_reason) is not str or not end_reason:
        raise ValueError("task Solution episode omitted a typed end reason")
    finalized = env.finish_recording(end_reason)
    h5_path = Path(finalized["path"]).resolve(strict=True)
    h5_bytes = h5_path.read_bytes()
    progress = env.get_runtime_progress_receipt()
    transition_count = len(action_trace)
    if (progress.get("episode_id") != episode_id
            or progress.get("native_step_count") != transition_count * 25
            or progress.get("control_step") != transition_count):
        raise ValueError("public runtime progress differs from the task Solution action trace")
    initial_joints = np.asarray(reset_observation["state"]["joint_position"], dtype=np.float64)
    final_joints = np.asarray(final_observation["state"]["joint_position"], dtype=np.float64)
    initial_ee = np.asarray(reset_observation["state"]["ee_pose"], dtype=np.float64)
    final_ee = np.asarray(final_observation["state"]["ee_pose"], dtype=np.float64)
    return {
        "schema_version": "r07-v210-task-solution-episode-v1",
        "episode_index": episode_index,
        "row_index": row_index,
        "seed": seed,
        "episode_id": episode_id,
        "task_uid": env.artifact.task_id,
        "task_artifact_identity_hash": env.artifact.identity_hash,
        "solution_identity": solution.identity,
        "source_id": reset_info.get("source_id"),
        "source_xml_sha256": reset_info.get("source_xml_sha256"),
        "source_closure_digest": reset_info.get("source_closure_digest"),
        "compiled_model_layout_v1": reset_info.get("compiled_model_layout_v1"),
        "pre_reset_compiled_validation_v1": reset_info.get("pre_reset_compiled_validation_v1"),
        "start_receipt": {
            "relative_path": str((episode_dir / "start_receipt.json").relative_to(output_dir.resolve())),
            "bytes": len(start_receipt_bytes),
            "sha256": hashlib.sha256(start_receipt_bytes).hexdigest(),
            "receipt": start_receipt,
        },
        "reset_sample": reset_sample,
        "reset_realization": reset_realization,
        "reset_readback": reset_readback,
        "prior_session_close_receipt": previous_close,
        "control_plan": env.get_record_metadata()["control_plan"],
        "action_trace": action_trace,
        "task_success": bool(final_info.get("is_success", False)),
        "solution_completed": bool(solution.done),
        "solution_failed": bool(solution.failed),
        "solution_failure_reason": getattr(solution, "failure_reason", None),
        "episode_end_v1": episode_end,
        "final_info": {
            "is_success": final_info.get("is_success"),
            "task_metrics": final_info.get("task_metrics"),
            "predicate_v1": final_info.get("predicate_v1"),
            "contact_summary_v2": final_info.get("contact_summary_v2"),
            "selected_policy_execution_complete": final_info.get("selected_policy_execution_complete"),
            "selected_policy_execution_failed": final_info.get("selected_policy_execution_failed"),
            "solution_stage": final_info.get("solution_stage"),
        },
        "motion_summary": _public_motion_metrics(initial_joints, final_joints, initial_ee, final_ee),
        "initial_observation": _state_observation_receipt(reset_observation),
        "final_observation": _state_observation_receipt(final_observation),
        "runtime_progress": progress,
        "physical_state_monitor": progress.get("physical_state_monitor"),
        "finalizer": finalized,
        "h5": {
            "relative_path": str(h5_path.relative_to(output_dir.resolve())),
            "bytes": len(h5_bytes),
            "sha256": hashlib.sha256(h5_bytes).hexdigest(),
            "schema_version": finalized.get("schema_version"),
            "transition_count": finalized.get("transition_count"),
            "observation_count": finalized.get("observation_count"),
            "episode_id": episode_id,
            "final_boundary": transition_count,
        },
    }


def _contact_endpoint_plan(base_sample: ResetSampleV1, *, positive: bool) -> ResetPlanV1:
    """Make an explicit diagnostic pose override without touching runtime state."""
    base_sample.validate()
    plate = base_sample.poses_world["plate_1"]
    offset = 0.0 if positive else 0.20
    height = 0.0 if positive else 0.05
    bowl_pose = PoseWorld(
        (plate.position[0] + offset, plate.position[1], plate.position[2] + height),
        plate.quaternion_wxyz,
    )
    values = base_sample.to_mapping()
    values["poses_world"] = {**base_sample.poses_world, "akita_black_bowl_1": bowl_pose}
    sample = ResetSampleV1.create(**values)
    plan = ResetPlanV1(
        schema_version="reset-plan-v1", reset_sample=sample,
        purpose="diagnostic_contact_endpoint",
    )
    plan.validate()
    return plan


def _source_on_predicate_oracle_v1(contact, bowl_pose, plate_pose) -> bool:
    """Independent transcription of the pinned object-object On rule."""
    dx = float(bowl_pose[0]) - float(plate_pose[0])
    dy = float(bowl_pose[1]) - float(plate_pose[1])
    return bool(
        int(contact["pair_counts"]["akita_black_bowl_1/plate_1"]) > 0
        and float(bowl_pose[2]) >= float(plate_pose[2])
        and (dx * dx + dy * dy) ** 0.5 < 0.03
    )


def _run_contact_endpoints(env, *, base_sample_mapping: dict) -> list[dict[str, Any]]:
    base_sample = ResetSampleV1.from_mapping(base_sample_mapping)
    endpoints = []
    for name, positive in (("negative", False), ("positive", True)):
        plan = _contact_endpoint_plan(base_sample, positive=positive)
        observation, info = env.reset(
            seed=plan.reset_sample.task_seed, options={"reset_plan_v1": plan},
        )
        contact = info.get("contact_summary_v2")
        predicate = info.get("predicate_v1", {}).get("on_bowl_plate")
        if not isinstance(contact, dict) or not isinstance(predicate, dict):
            raise ValueError("public ResetPlan endpoint omitted contact or On predicate evidence")
        poses = _state_observation_receipt(observation)["privileged_state"]
        bowl = poses["bowl_body_pose"]
        plate = poses["plate_body_pose"]
        source_value = _source_on_predicate_oracle_v1(contact, bowl, plate)
        if predicate.get("status") != "available" or predicate.get("value") is not source_value:
            raise ValueError("Core On predicate differs from independent source rule at ResetPlan endpoint")
        if source_value is not positive:
            raise ValueError(f"public diagnostic {name} ResetPlan endpoint did not realize its expected source predicate")
        endpoints.append({
            "endpoint": name,
            "reset_plan_v1": plan.to_mapping(),
            "reset_plan_identity_sha256": plan.identity_hash,
            "reset_plan_evidence_v1": info.get("reset_plan_evidence_v1"),
            "reset_readback_v1": info.get("reset_readback_v1"),
            "contact_summary_v2": contact,
            "core_predicate_v1": predicate,
            "source_predicate_oracle": {"schema_version": "libero-on-source-oracle-v1", "value": source_value},
            "public_observation": _state_observation_receipt(observation),
            "runtime_progress": env.get_runtime_progress_receipt(),
        })
    return endpoints


def run_libero_candidate_worker(env, *, output_dir: Path, seed: int = 19,
                                rows: tuple[int, ...] = (0, 1, 2), steps: int = 64,
                                solution_factory=None,
                                source_closure_files: Mapping[str, bytes] | None = None,
                                composition_plan_bytes: bytes | None = None) -> dict[str, Any]:
    """Run same-instance public resets, action route, H5 closure and receipts."""
    output_dir = Path(output_dir).resolve()
    if tuple(rows) != (0, 1, 2) or type(seed) is not int or seed != 19:
        raise ValueError("D01 worker freezes seed 19 and source rows (0,1,2)")
    maximum_steps = 1000 if solution_factory is not None else 64
    if type(steps) is not int or not 1 <= steps <= maximum_steps:
        raise ValueError(f"LIBERO worker supports 1..{maximum_steps} public outer steps per episode")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"worker output directory must be fresh and empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    episodes = []
    diagnostic_endpoints = []
    source_bundle = None
    worker_error = None
    close_error = None
    close_receipt = None
    try:
        if solution_factory is not None:
            if source_closure_files is None or not isinstance(composition_plan_bytes, bytes):
                raise ValueError("task Solution worker requires exact source closure files and composition-plan bytes")
            source_bundle = _write_solution_source_bundle(
                output_dir, source_closure_files=source_closure_files,
                composition_plan_bytes=composition_plan_bytes,
            )
        for index, row_index in enumerate(rows):
            if solution_factory is None:
                episodes.append(_episode_record(
                    env, output_dir=output_dir, episode_index=index,
                    row_index=row_index, seed=seed, steps=steps,
                ))
            else:
                episodes.append(_episode_solution_record(
                    env, output_dir=output_dir, episode_index=index, row_index=row_index,
                    seed=seed, max_steps=steps, solution_factory=solution_factory,
                ))
        if solution_factory is None:
            diagnostic_endpoints = _run_contact_endpoints(
                env, base_sample_mapping=episodes[-1]["reset_sample"],
            )
    except BaseException as exc:
        worker_error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        try:
            env.close()
            close_receipt = env.close_receipt
        except BaseException as exc:
            close_error = {"type": type(exc).__name__, "message": str(exc)}
            try:
                close_receipt = env.close_receipt
            except BaseException:
                pass
    solution_route = solution_factory is not None
    attempted_episode_receipts = []
    failed_episode_receipts = []
    if solution_route:
        for start_path in sorted(output_dir.glob("episode_*_row_*/start_receipt.json")):
            raw_start = start_path.read_bytes()
            attempted_episode_receipts.append({
                "relative_path": str(start_path.relative_to(output_dir.resolve())),
                "bytes": len(raw_start),
                "sha256": hashlib.sha256(raw_start).hexdigest(),
                "receipt": json.loads(raw_start.decode("utf-8")),
            })
        for failure_path in sorted(output_dir.glob("episode_*_row_*/failure_receipt.json")):
            raw_failure = failure_path.read_bytes()
            failed_episode_receipts.append({
                "relative_path": str(failure_path.relative_to(output_dir.resolve())),
                "bytes": len(raw_failure),
                "sha256": hashlib.sha256(raw_failure).hexdigest(),
                "receipt": json.loads(raw_failure.decode("utf-8")),
            })
    payload = {
        "schema_version": (
            "r07-v210-task-solution-worker-result-v1" if solution_route
            else "r07c-d01-libero-worker-result-v1"
        ),
        "status": "complete" if (worker_error is None and close_error is None
                                  and len(episodes) == len(rows)
                                  and (solution_route or len(diagnostic_endpoints) == 2)) else "failed",
        "episode_count": len(episodes),
        "transition_count": sum(int(item["h5"]["transition_count"] or 0) for item in episodes),
        "observation_count": sum(int(item["h5"]["observation_count"] or 0) for item in episodes),
        "native_step_count": sum(int(item["runtime_progress"]["native_step_count"]) for item in episodes),
        "episodes": episodes,
        "attempted_episode_receipts": attempted_episode_receipts if solution_route else None,
        "failed_episode_receipts": failed_episode_receipts if solution_route else None,
        "source_bundle": source_bundle,
        "diagnostic_endpoints": diagnostic_endpoints,
        "reset_count": len(episodes) + len(diagnostic_endpoints),
        "solution_coverage": {
            "task_success_episodes": sum(bool(item.get("task_success")) for item in episodes),
            "solution_completed_episodes": sum(bool(item.get("solution_completed")) for item in episodes),
            "failed_episodes": sum(bool(item.get("solution_failed")) for item in episodes),
        } if solution_route else None,
        "final_session_close_receipt": close_receipt,
        "worker_error": worker_error,
        "close_error": close_error,
        "worker_process_group_cleanup": "parent_must_confirm_after_worker_exit",
        "evidence_class": "synthetic_fixture" if any(
            item.get("reset_sample", {}).get("evidence_class") == "synthetic_fixture" for item in episodes
        ) else "runtime_candidate",
    }
    result = {**payload, "result_sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
    _write_json(output_dir / "worker_result.json", result)
    return result


def _consume_libero_solution_bundle(bundle_path: Path, report: Mapping[str, Any], *,
                                   require_motion_thresholds: bool,
                                   require_mujoco_runtime_identity: bool) -> dict[str, Any]:
    """Independent provider-free H5/source/outcome readback for the v2.1.0 route."""
    from .solution import solution_identity_v1
    payload = {key: value for key, value in report.items() if key != "result_sha256"}
    if hashlib.sha256(_canonical(payload)).hexdigest() != report.get("result_sha256"):
        raise ValueError("task Solution worker result digest mismatch")
    attempted_episode_receipts = report.get("attempted_episode_receipts")
    failed_episode_receipts = report.get("failed_episode_receipts")
    if (report.get("schema_version") != "r07-v210-task-solution-worker-result-v1"
            or report.get("status") != "complete"
            or report.get("worker_error") is not None
            or report.get("close_error") is not None
            or report.get("episode_count") != 3
            or len(report.get("episodes", ())) != 3
            or not isinstance(attempted_episode_receipts, list)
            or len(attempted_episode_receipts) != 3
            or not isinstance(failed_episode_receipts, list)
            or failed_episode_receipts
            or report.get("reset_count") != 3):
        raise ValueError("task Solution worker bundle is incomplete or has an invalid schema/count")
    source_readback = _verify_solution_source_bundle(bundle_path, report.get("source_bundle"))
    expected_solution_identity = solution_identity_v1(source_readback["canonical_xml_sha256"])
    total_t = total_obs = total_native = 0
    episodes = []
    for index, (expected_row, episode, attempted) in enumerate(zip(
            (0, 1, 2), report["episodes"], attempted_episode_receipts, strict=True)):
        if (episode.get("schema_version") != "r07-v210-task-solution-episode-v1"
                or episode.get("episode_index") != index or episode.get("row_index") != expected_row
                or episode.get("seed") != 19 or episode.get("task_uid") != TASK_1
                or episode.get("source_id") != source_readback.get("source_id")
                or episode.get("source_closure_digest") != source_readback.get("source_closure_digest")
                or episode.get("source_xml_sha256") != source_readback.get("canonical_xml_sha256")
                or episode.get("solution_identity") != expected_solution_identity):
            raise ValueError("task Solution episode task/row/seed/order identity mismatch")
        prior_close = episode.get("prior_session_close_receipt")
        if ((index == 0 and prior_close is not None)
                or (index > 0 and (not isinstance(prior_close, Mapping)
                                   or prior_close.get("session_closed") is not True))):
            raise ValueError("task Solution same-Env reset omitted the prior RuntimeSession close receipt")
        sample = episode.get("reset_sample")
        realization = episode.get("reset_realization")
        readback = episode.get("reset_readback")
        progress = episode.get("runtime_progress")
        compiled = episode.get("compiled_model_layout_v1")
        pre_reset = episode.get("pre_reset_compiled_validation_v1")
        if not all(isinstance(value, Mapping) for value in (
                sample, realization, readback, progress, compiled, pre_reset)):
            raise ValueError("task Solution episode omits source/reset/progress/layout receipts")
        runtime_identity = pre_reset.get("runtime_identity")
        if (require_mujoco_runtime_identity
                and runtime_identity != _PINNED_MUJOCO_RUNTIME_IDENTITY):
            raise ValueError("task Solution pre-reset receipt does not identify the pinned MuJoCo runtime")
        start = attempted.get("receipt")
        start_relative = attempted.get("relative_path")
        if (type(start_relative) is not str or Path(start_relative).is_absolute()
                or ".." in Path(start_relative).parts):
            raise ValueError("task Solution start receipt path is unsafe")
        start_path = (bundle_path.parent / start_relative).resolve(strict=True)
        if bundle_path.parent not in start_path.parents:
            raise ValueError("task Solution start receipt escaped its worker bundle")
        start_raw = start_path.read_bytes()
        if (len(start_raw) != attempted.get("bytes")
                or hashlib.sha256(start_raw).hexdigest() != attempted.get("sha256")
                or start != json.loads(start_raw.decode("utf-8"))
                or start.get("schema_version") != "r07-v210-task-solution-start-receipt-v1"
                or start.get("episode_index") != index or start.get("row_index") != expected_row
                or start.get("seed") != 19 or start.get("task_uid") != TASK_1
                or start.get("solution_identity") != expected_solution_identity
                or start.get("episode_id") != episode.get("episode_id")
                or start.get("source_id") != episode.get("source_id")
                or start.get("source_closure_digest") != episode.get("source_closure_digest")
                or start.get("pre_reset_compiled_validation_v1") != pre_reset):
            raise ValueError("task Solution start receipt differs from its episode/runtime identity")
        if (sample.get("init_row_index") != expected_row
                or sample.get("source_id") != episode.get("source_id")
                or sample.get("source_closure_digest") != episode.get("source_closure_digest")
                or readback.get("reset_sample_id") != sample.get("sample_id")
                or readback.get("joint_position") != sample.get("joint_position")
                or readback.get("joint_velocity") != sample.get("joint_velocity")
                or readback.get("poses_world") != sample.get("poses_world")
                or readback.get("free_joint_velocity") != sample.get("free_joint_velocity")
                or readback.get("fixture_pose_world") != sample.get("fixture_pose_world")
                or realization.get("init_row_index") != expected_row
                or realization.get("init_row_sha256") != sample.get("init_row_sha256")
                or progress.get("episode_id") != episode.get("episode_id")
                or progress.get("provider_materialization_id") is None
                or progress.get("native_step_count") != episode.get("h5", {}).get("transition_count", 0) * 25):
            raise ValueError("task Solution reset/progress source identity differs from the public readback")
        if (compiled.get("schema_version") != "compiled-model-layout-v1"
                or compiled.get("source_id") != episode.get("source_id")
                or compiled.get("source_closure_digest") != episode.get("source_closure_digest")
                or pre_reset.get("reset_not_yet_applied") is not True
                or pre_reset.get("compiled_layout") != compiled
                or compiled.get("dimensions", {}).get("nq") != 48
                or compiled.get("dimensions", {}).get("nv") != 43
                or compiled.get("dimensions", {}).get("nu") != 9):
            raise ValueError("task Solution compiled source/layout receipt is invalid or post-reset")
        relative = episode.get("h5", {}).get("relative_path")
        if type(relative) is not str or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("task Solution H5 path escapes its worker bundle")
        h5_path = (bundle_path.parent / relative).resolve(strict=True)
        if bundle_path.parent not in h5_path.parents:
            raise ValueError("task Solution H5 path escaped the worker bundle")
        raw = h5_path.read_bytes()
        if (len(raw) != episode["h5"].get("bytes")
                or hashlib.sha256(raw).hexdigest() != episode["h5"].get("sha256")):
            raise ValueError("task Solution H5 bytes or digest differ from the worker receipt")
        inspected = inspect_trajectory_h5(h5_path)
        semantic = load_structured_control_records_h5(h5_path)
        if (inspected.get("schema_version") != "v3"
                or semantic["transition_count"] != episode["h5"].get("transition_count")
                or semantic["observation_count"] != semantic["transition_count"] + 1
                or semantic["outcome"].episode_id != episode.get("episode_id")
                or semantic["outcome"].final_boundary != semantic["transition_count"]
                or semantic["outcome"].task_success is not episode.get("task_success")
                or semantic["outcome"].solution_completed is not episode.get("solution_completed")):
            raise ValueError("task Solution H5 T/T+1, outcome, or completion facts differ from worker data")
        if (semantic["outcome"].solution_completed is True
                and (semantic["outcome"].task_success is not True
                     or semantic["outcome"].terminated or semantic["outcome"].truncated
                     or semantic["outcome"].end_reason != "solution_completed")):
            raise ValueError("H5 claims Solution completion without task success and clean lifecycle facts")
        if (semantic["outcome"].solution_completed is False
                and episode.get("solution_failed") is False
                and semantic["outcome"].end_reason == "solution_completed"):
            raise ValueError("H5 end reason upgrades a non-completed Solution")
        if (type(episode.get("solution_completed")) is not bool
                or type(episode.get("solution_failed")) is not bool
                or type(episode.get("task_success")) is not bool
                or (episode["solution_completed"] and (not episode["task_success"] or episode["solution_failed"]))):
            raise ValueError("task Solution worker outcome booleans are inconsistent")
        task_context = None
        with h5py.File(h5_path, "r") as handle:
            required = (
                "obs/state/joint_position", "obs/state/ee_pose",
                "obs/state/boundary_identity_sha256",
                "obs/privileged_state/bowl_body_pose", "obs/privileged_state/plate_body_pose",
                "meta/task_context_json", "meta/boundary_context_v1_json",
            )
            if any(name not in handle for name in required):
                raise ValueError("task Solution H5 omits state, pose, identity, or boundary context")
            task_context = json.loads(handle["meta/task_context_json"][()].decode("utf-8"))
            boundaries = json.loads(handle["meta/boundary_context_v1_json"][()].decode("utf-8"))
            joints = handle["obs/state/joint_position"][:]
            ee_poses = handle["obs/state/ee_pose"][:]
            boundary_ids = handle["obs/state/boundary_identity_sha256"][:]
            bowl_poses = handle["obs/privileged_state/bowl_body_pose"][:, 0, :]
            plate_poses = handle["obs/privileged_state/plate_body_pose"][:, 0, :]
            action_names = [*(f"joint{i}" for i in range(1, 8)), "aggregate_opening_m"]
            if any(f"universal_action/{name}" not in handle for name in action_names):
                raise ValueError("task Solution H5 omits one or more public action channels")
            actions = np.column_stack([
                handle[f"universal_action/{name}"][:].reshape(-1) for name in action_names
            ])
        count = semantic["transition_count"]
        observation_count = semantic["observation_count"]
        if (joints.shape != (observation_count, 9) or not np.isfinite(joints).all()
                or ee_poses.shape != (observation_count, 7) or not np.isfinite(ee_poses).all()
                or boundary_ids.shape != (observation_count, 32) or boundary_ids.dtype != np.uint8
                or bowl_poses.shape != (observation_count, 7) or not np.isfinite(bowl_poses).all()
                or plate_poses.shape != (observation_count, 7) or not np.isfinite(plate_poses).all()
                or actions.shape != (count, 8) or not np.isfinite(actions).all()
                or len(boundaries) != observation_count):
            raise ValueError("task Solution H5 public state/action arrays violate their T/T+1 schemas")
        if (task_context.get("schema_version") != "libero-episode-context-v1"
                or task_context.get("task_artifact_identity_hash") != episode.get("task_artifact_identity_hash")
                or task_context.get("solution_identity") != episode.get("solution_identity")
                or task_context.get("source_id") != episode.get("source_id")
                or task_context.get("source_xml_sha256") != episode.get("source_xml_sha256")
                or task_context.get("source_closure_digest") != episode.get("source_closure_digest")
                or task_context.get("episode_id") != episode.get("episode_id")
                or task_context.get("init_row_index") != expected_row
                or task_context.get("reset_sample_id") != sample.get("sample_id")
                or task_context.get("provider_materialization_id") != progress.get("provider_materialization_id")):
            raise ValueError("task Solution H5 task/source/solution identity differs from worker receipts")
        identity_fields = (
            "source_id", "source_closure_digest", "provider_materialization_id",
            "episode_id", "reset_sample_id", "control_step", "state_revision", "simulation_time_s",
        )
        for boundary_index, boundary in enumerate(boundaries):
            if (not isinstance(boundary, Mapping)
                    or boundary.get("schema_version") != "task-observation-context-v1"
                    or any(boundary.get(name) != task_context.get(name) for name in identity_fields[:5])
                    or boundary.get("control_step") != boundary_index
                    or boundary.get("state_revision") != boundary_index
                    or boundary.get("simulation_time_s") != boundary_index * 0.05):
                raise ValueError("task Solution H5 boundary identity/order/clock is invalid")
            digest_payload = {name: boundary[name] for name in identity_fields}
            expected_digest = digest(digest_payload)
            if (boundary.get("state_boundary_identity_sha256") != expected_digest
                    or bytes(boundary_ids[boundary_index]).hex() != expected_digest):
                raise ValueError("task Solution H5 observation boundary digest is invalid")
            contact = boundary.get("contact_summary_v2")
            predicate = boundary.get("predicate_v1")
            if (not isinstance(contact, Mapping)
                    or contact.get("schema_version") != "task-contact-summary-v2"
                    or contact.get("requested_pairs") != [["akita_black_bowl_1", "plate_1"]]
                    or contact.get("covered_pairs") != contact.get("requested_pairs")
                    or any(contact.get(name) != boundary.get(name) for name in identity_fields)
                    or contact.get("state_revision") != boundary.get("state_revision")):
                raise ValueError("task Solution H5 contact summary is missing, stale, or incomplete")
            count_contact = contact.get("pair_counts", {}).get("akita_black_bowl_1/plate_1")
            if type(count_contact) is not int or count_contact < 0:
                raise ValueError("task Solution H5 contact pair count is invalid")
            source_on = bool(
                count_contact > 0
                and bowl_poses[boundary_index, 2] >= plate_poses[boundary_index, 2]
                and float(np.linalg.norm(bowl_poses[boundary_index, :2] - plate_poses[boundary_index, :2])) < 0.03
            )
            if (not isinstance(predicate, Mapping)
                    or predicate.get("status") != "available"
                    or predicate.get("value") is not source_on):
                raise ValueError("task Solution H5 On predicate differs from the source-rule recomputation")
        if len(semantic["structured_controls"]) != count or any(
                control is None for control in semantic["structured_controls"]):
            raise ValueError("task Solution H5 omits a typed mixed-control Target/Ack")
        for transition_index, control in enumerate(semantic["structured_controls"]):
            control.validate()
            if (len(control.request.groups) != 1 or len(control.writer_controls) != 1
                    or control.request.groups[0].action_schema_id != "libero-joint-space-absolute-v1"
                    or not np.allclose(np.asarray(control.request.groups[0].values), actions[transition_index],
                                       rtol=0.0, atol=1e-7)):
                raise ValueError("task Solution typed action differs from its public H5 action row")
            writer = control.writer_controls[0]
            target_mapping = writer.get("controller_target", {}).get("payload")
            ack_mapping = writer.get("applied_control", {}).get("payload")
            if not isinstance(target_mapping, Mapping) or not isinstance(ack_mapping, Mapping):
                raise ValueError("task Solution structured control lacks target/ack payload")
            target = MixedActuatorCommandV1.from_mapping(dict(target_mapping))
            ack = AppliedMixedActuatorCommandV1.from_mapping(dict(ack_mapping))
            if (ack.target_hash != target.identity_hash
                    or ack.clipped is not False
                    or dict(ack.channel_values) != dict(target.channel_values)
                    or dict(ack.channel_units) != dict(target.channel_units)
                    or target.task_artifact_hash != task_context.get("task_artifact_identity_hash")
                    or target.source_id != task_context.get("source_id")
                    or target.source_closure_digest != task_context.get("source_closure_digest")
                    or target.controller_identity != task_context.get("controller_identity")
                    or target.provider_materialization_id != task_context.get("provider_materialization_id")
                    or target.episode_id != task_context.get("episode_id")
                    or target.reset_sample_id != task_context.get("reset_sample_id")
                    or target.control_step != transition_index
                    or target.state_revision != transition_index
                    or target.simulation_time_s != transition_index * 0.05
                    or ack.provider_name != "mujoco"):
                raise ValueError("task Solution H5 Target/Ack source, control, or boundary identity mismatch")
        action_trace = episode.get("action_trace")
        if not isinstance(action_trace, list) or len(action_trace) != count:
            raise ValueError("task Solution action trace does not cover every H5 transition")
        for transition_index, action in enumerate(action_trace):
            if (not isinstance(action, Mapping)
                    or type(action.get("control_step")) is not int
                    or action.get("control_step") != transition_index + 1
                    or not np.isclose(float(action.get("simulation_time_s", float("nan"))),
                                      (transition_index + 1) * 0.05, rtol=0.0, atol=1e-9)
                    or type(action.get("terminated")) is not bool
                    or type(action.get("truncated")) is not bool
                    or not isinstance(action.get("solution_stage"), str)
                    or not isinstance(action.get("solution_diagnostics"), Mapping)
                    or not np.allclose(np.asarray(action.get("solution_action"), dtype=np.float64),
                                       actions[transition_index], rtol=0.0, atol=1e-7)):
                raise ValueError("task Solution action trace differs from public H5 control rows")
        initial_observation = episode.get("initial_observation")
        final_observation = episode.get("final_observation")
        if not isinstance(initial_observation, Mapping) or not isinstance(final_observation, Mapping):
            raise ValueError("task Solution worker omits public initial/final observation receipts")
        for observation_receipt, index in ((initial_observation, 0), (final_observation, -1)):
            if (not np.allclose(np.asarray(observation_receipt.get("joint_position"), dtype=np.float64),
                                joints[index], rtol=0.0, atol=1e-7)
                    or not np.allclose(np.asarray(observation_receipt.get("ee_pose"), dtype=np.float64),
                                       ee_poses[index], rtol=0.0, atol=1e-7)
                    or observation_receipt.get("boundary_identity_sha256") != bytes(boundary_ids[index]).hex()):
                raise ValueError("task Solution worker observation receipt differs from independent H5 state")
        actual_motion = _public_motion_metrics(
            np.asarray(joints[0], dtype=np.float64), np.asarray(joints[-1], dtype=np.float64),
            np.asarray(ee_poses[0], dtype=np.float64), np.asarray(ee_poses[-1], dtype=np.float64),
        )
        recorded_motion = episode.get("motion_summary")
        if (not isinstance(recorded_motion, Mapping)
                or any(not np.isclose(float(recorded_motion.get(name, float("nan"))), value,
                                      rtol=0.0, atol=1e-7)
                       for name, value in actual_motion.items())):
            raise ValueError("task Solution public motion summary differs from H5 state")
        if require_motion_thresholds and (
                actual_motion["arm_joint_max_abs_delta_rad"] < 0.05
                and actual_motion["tcp_translation_delta_m"] < 0.02):
            raise ValueError("task Solution episode lacks the required public arm/TCP excursion")
        if require_motion_thresholds and actual_motion["aggregate_finger_position_delta_m"] < 0.005:
            raise ValueError("task Solution episode lacks the required aggregate gripper-opening change")
        monitor_summary = _validate_physical_state_monitor(
            episode.get("physical_state_monitor"), progress, compiled, joints,
        )
        if (episode.get("h5", {}).get("transition_count") != count
                or episode.get("h5", {}).get("observation_count") != observation_count
                or episode.get("h5", {}).get("episode_id") != episode.get("episode_id")
                or episode.get("h5", {}).get("final_boundary") != count
                or semantic["outcome"].final_boundary != count):
            raise ValueError("task Solution H5 receipt T/T+1/final boundary mismatch")
        episodes.append({
            "episode_id": episode.get("episode_id"),
            "row_index": expected_row,
            "task_success": semantic["outcome"].task_success,
            "solution_completed": semantic["outcome"].solution_completed,
            "solution_failed": episode.get("solution_failed"),
            "end_reason": semantic["outcome"].end_reason,
            "terminated": semantic["outcome"].terminated,
            "truncated": semantic["outcome"].truncated,
            "transition_count": count,
            "observation_count": observation_count,
            "h5_sha256": episode["h5"]["sha256"],
            "physical_state_monitor": monitor_summary,
        })
        total_t += count
        total_obs += observation_count
        total_native += int(progress["native_step_count"])
    close = report.get("final_session_close_receipt")
    if not isinstance(close, Mapping) or close.get("session_closed") is not True:
        raise ValueError("task Solution worker omitted a successful final RuntimeSession close receipt")
    if (report.get("transition_count") != total_t
            or report.get("observation_count") != total_obs
            or report.get("native_step_count") != total_native):
        raise ValueError("task Solution aggregate worker counters differ from independently read H5s")
    return {
        "schema_version": "r07-v210-task-solution-independent-reader-v1",
        "status": "verified_complete",
        "source_bundle": source_readback,
        "motion_thresholds_required": bool(require_motion_thresholds),
        "mujoco_runtime_identity_required": bool(require_mujoco_runtime_identity),
        "episode_count": len(episodes),
        "transition_count": total_t,
        "observation_count": total_obs,
        "native_step_count": total_native,
        "task_success_episodes": sum(bool(item["task_success"]) for item in episodes),
        "solution_completed_episodes": sum(bool(item["solution_completed"]) for item in episodes),
        "episodes": episodes,
    }


def consume_libero_candidate_bundle(bundle_path: Path, *, parent_run_record_path: Path | None = None,
                                    expected_lock_path: Path | None = None,
                                    require_motion_thresholds: bool = False,
                                    require_mujoco_runtime_identity: bool = False) -> dict[str, Any]:
    """Provider-free independent readback of a completed worker and all H5s."""
    bundle_path = Path(bundle_path).resolve(strict=True)
    report = json.loads(bundle_path.read_text(encoding="utf-8"))
    if report.get("schema_version") == "r07-v210-task-solution-worker-result-v1":
        result = _consume_libero_solution_bundle(
            bundle_path, report, require_motion_thresholds=require_motion_thresholds,
            require_mujoco_runtime_identity=require_mujoco_runtime_identity,
        )
        if parent_run_record_path is not None:
            if expected_lock_path is None:
                raise ValueError("independent native readback requires the expected shared lock path")
            result["parent_process"] = _validate_parent_run_record(
                bundle_path, report, parent_run_record_path, expected_lock_path,
            )
        elif expected_lock_path is not None:
            raise ValueError("expected native lock path requires a parent run record")
        return result
    payload = {key: value for key, value in report.items() if key != "result_sha256"}
    if hashlib.sha256(_canonical(payload)).hexdigest() != report.get("result_sha256"):
        raise ValueError("worker result digest mismatch")
    if report.get("schema_version") != "r07c-d01-libero-worker-result-v1":
        raise ValueError("unsupported R07c D01 worker-result schema")
    if report.get("status") != "complete" or report.get("worker_error") is not None or report.get("close_error") is not None:
        raise ValueError("worker bundle is incomplete or reports a lifecycle failure")
    if report.get("episode_count") != 3 or len(report.get("episodes", ())) != 3:
        raise ValueError("worker result does not contain all three source rows")
    total_t = total_obs = total_native = 0
    h5_receipts = []
    for expected_index, (expected_row, episode) in enumerate(zip((0, 1, 2), report["episodes"], strict=True)):
        if (episode.get("episode_index") != expected_index or episode.get("row_index") != expected_row
                or episode.get("seed") != 19):
            raise ValueError("worker episode row/seed/order identity mismatch")
        sample = episode.get("reset_sample")
        realization = episode.get("reset_realization")
        readback = episode.get("reset_readback")
        progress = episode.get("runtime_progress")
        if not all(isinstance(value, dict) for value in (sample, realization, readback, progress)):
            raise ValueError("episode bundle omits reset/source/progress receipts")
        compiled = episode.get("compiled_model_layout_v1")
        pre_reset = episode.get("pre_reset_compiled_validation_v1")
        if not isinstance(compiled, dict) or not isinstance(pre_reset, dict):
            raise ValueError("episode bundle omits the pre-reset compiled-model layout proof")
        # Counts beyond nq/nv/na/nu are model-dependent inventory, but every
        # value and the fixed source dimensions must be retained.
        dimensions = compiled.get("dimensions")
        if (compiled.get("schema_version") != "compiled-model-layout-v1"
                or not isinstance(dimensions, dict)
                or any(type(dimensions.get(name)) is not int for name in (
                    "nq", "nv", "na", "nu", "njnt", "nbody", "nsite", "ngeom",
                ))
                or tuple(dimensions.get(name) for name in ("nq", "nv", "na", "nu", "njnt"))
                != (48, 43, 0, 9, 18)):
            raise ValueError("independent bundle has an invalid compiled-model dimension receipt")
        if (compiled.get("source_id") != episode.get("source_id")
                or compiled.get("source_closure_digest") != episode.get("source_closure_digest")
                or pre_reset.get("reset_not_yet_applied") is not True
                or pre_reset.get("compiled_layout") != compiled):
            raise ValueError("compiled model was not validated before reset or differs from the episode source")
        expected_scalar_addresses = {
            **{f"joint{i}": [i - 1, i - 1] for i in range(1, 8)},
            "finger_joint1": [7, 7], "finger_joint2": [8, 8],
            "wooden_cabinet_1.top_level": [44, 39],
            "wooden_cabinet_1.middle_level": [45, 40],
            "wooden_cabinet_1.bottom_level": [46, 41],
            "flat_stove_1.button": [47, 42],
        }
        expected_free_addresses = {
            name: [9 + 7 * index, 9 + 6 * index]
            for index, name in enumerate((
                "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
                "glazed_rim_porcelain_ramekin_1", "plate_1",
            ))
        }
        if (compiled.get("named_joint_addresses") != expected_scalar_addresses
                or compiled.get("named_free_joint_addresses") != expected_free_addresses):
            raise ValueError("compiled named Joint/qpos/dof layout differs from the fixed .pruned_init mapping")
        expected_bodies = {
            "main_table", "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
            "glazed_rim_porcelain_ramekin_1", "plate_1", "wooden_cabinet_1", "flat_stove_1",
        }
        body_ids = compiled.get("named_body_ids")
        frame_ids = compiled.get("named_frame_ids")
        if (not isinstance(body_ids, dict) or set(body_ids) != expected_bodies
                or any(type(value) is not int or value <= 0 for value in body_ids.values())
                or len(set(body_ids.values())) != len(body_ids)
                or not isinstance(frame_ids, dict) or set(frame_ids) != {"panda-v1/ee"}
                or type(frame_ids.get("panda-v1/ee")) is not int or frame_ids["panda-v1/ee"] <= 0):
            raise ValueError("compiled named Body/Frame inventory differs from the fixed LIBERO source map")
        expected_channel_specs = {
            **{
                f"joint{i}": {
                    "actuator_name": f"robot0_torq_j{i}",
                    "joint_name": f"robot0_joint{i}", "drive_mode": "joint_torque",
                    "unit": "N*m", "control_range": [-80.0, 80.0] if i <= 5 else [-12.0, 12.0],
                } for i in range(1, 8)
            },
            "finger_joint1": {
                "actuator_name": "gripper0_gripper_finger_joint1",
                "joint_name": "gripper0_finger_joint1", "drive_mode": "joint_position",
                "unit": "m", "control_range": [0.0, 0.04],
            },
            "finger_joint2": {
                "actuator_name": "gripper0_gripper_finger_joint2",
                "joint_name": "gripper0_finger_joint2", "drive_mode": "joint_position",
                "unit": "m", "control_range": [-0.04, 0.0],
            },
        }
        torque_ids = compiled.get("named_torque_actuator_ids")
        position_ids = compiled.get("named_position_actuator_ids")
        channel_layout = compiled.get("named_actuator_channels")
        if (not isinstance(torque_ids, dict) or set(torque_ids) != {f"joint{i}" for i in range(1, 8)}
                or not isinstance(position_ids, dict) or set(position_ids) != {"finger_joint1", "finger_joint2"}
                or not isinstance(channel_layout, dict) or set(channel_layout) != set(expected_channel_specs)):
            raise ValueError("compiled actuator receipt omits a named torque or finger slot")
        actuator_ids = []
        for name, spec in expected_channel_specs.items():
            entry = channel_layout[name]
            expected_id = torque_ids.get(name) if name in torque_ids else position_ids.get(name)
            if (type(expected_id) is not int or entry.get("actuator_id") != expected_id
                    or entry.get("actuator_name") != spec["actuator_name"]
                    or entry.get("joint_name") != spec["joint_name"]
                    or entry.get("transmission_target") != spec["joint_name"]
                    or entry.get("transmission_type") != "joint"
                    or entry.get("drive_mode") != spec["drive_mode"]
                    or entry.get("unit") != spec["unit"]
                    or entry.get("control_limited") is not True
                    or entry.get("control_range") != spec["control_range"]):
                raise ValueError(f"compiled actuator transmission/drive/range receipt is invalid: {name}")
            actuator_ids.append(expected_id)
        if sorted(actuator_ids) != list(range(9)):
            raise ValueError("compiled actuator layout does not uniquely cover all nine ctrl slots")
        geom_groups = compiled.get("named_contact_geom_groups")
        if (not isinstance(geom_groups, dict)
                or set(geom_groups) != {
                    "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
                    "glazed_rim_porcelain_ramekin_1", "plate_1",
                    "wooden_cabinet_1", "flat_stove_1",
                }
                or any(not isinstance(items, list) or not items
                       or any(type(item.get("id")) is not int or item["id"] < 0
                              or type(item.get("name")) is not str or not item["name"]
                              for item in items if isinstance(item, dict))
                       or any(not isinstance(item, dict) for item in items)
                       for items in geom_groups.values())):
            raise ValueError("compiled semantic contact geom groups are incomplete or malformed")
        all_geom_ids = [item["id"] for items in geom_groups.values() for item in items]
        if len(all_geom_ids) != len(set(all_geom_ids)):
            raise ValueError("compiled semantic contact geom groups overlap in native IDs")
        runtime = pre_reset.get("runtime_identity")
        expected_runtime = {
            "provider_build": {
                "dirty_build_sha256": None,
                "import_origin": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
                "manifest_version": "package:3.8.1",
                "origin_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
                "package_version": "3.8.1", "provider": "mujoco",
                "repository_revision": None,
            },
            "runtime": {
                "api_version": 3008001,
                "binding_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/_functions.cpython-312-x86_64-linux-gnu.so",
                "binding_sha256": "9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3",
                "mapped_native_libraries": [{
                    "path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/libmujoco.so.3.8.1",
                    "sha256": "8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592",
                }],
                "package_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
                "package_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
                "package_version": "3.8.1",
                "public_header_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/include/mujoco/mujoco.h",
                "public_header_sha256": "d5ccfb227eb06586edfb4def5812a8082c1cbdf8e6dc5c3176abd9772a57fd07",
                "renderer_initialized": False, "runtime_version": "3.8.1",
            },
        }
        if runtime != expected_runtime:
            raise ValueError("compiled runtime identity differs from the frozen MuJoCo 3.8.1 CPU files")
        if (sample.get("init_row_index") != expected_row
                or sample.get("source_id") != episode.get("source_id")
                or sample.get("source_closure_digest") != episode.get("source_closure_digest")
                or readback.get("reset_sample_id") != sample.get("sample_id")
                or readback.get("simulation_time_s") != sample.get("simulation_time_s")
                or readback.get("joint_position") != sample.get("joint_position")
                or readback.get("joint_velocity") != sample.get("joint_velocity")
                or readback.get("poses_world") != sample.get("poses_world")
                or readback.get("free_joint_velocity") != sample.get("free_joint_velocity")
                or readback.get("fixture_pose_world") != sample.get("fixture_pose_world")
                or realization.get("init_row_index") != expected_row
                or realization.get("init_row_sha256") != sample.get("init_row_sha256")
                or progress.get("episode_id") != episode.get("episode_id")
                or progress.get("native_step_count") != episode["h5"].get("transition_count", 0) * 25):
            raise ValueError("episode reset/progress identity does not match the worker source")
        relative = episode["h5"].get("relative_path")
        if type(relative) is not str or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("worker H5 path must stay inside its bundle directory")
        try:
            h5_path = (bundle_path.parent / relative).resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("worker bundle is missing a required H5 artifact") from exc
        if bundle_path.parent not in h5_path.parents:
            raise ValueError("worker H5 path escaped the bundle directory")
        raw = h5_path.read_bytes()
        if len(raw) != episode["h5"].get("bytes") or hashlib.sha256(raw).hexdigest() != episode["h5"].get("sha256"):
            raise ValueError("worker H5 bytes or digest mismatch")
        inspected = inspect_trajectory_h5(h5_path)
        semantic = load_structured_control_records_h5(h5_path)
        if (inspected.get("schema_version") != "v3"
                or semantic["transition_count"] != episode["h5"].get("transition_count")
                or semantic["observation_count"] != episode["h5"].get("observation_count")
                or semantic["observation_count"] != semantic["transition_count"] + 1
                or semantic["outcome"].episode_id != episode.get("episode_id")
                or semantic["outcome"].final_boundary != semantic["transition_count"]):
            raise ValueError("independent H5 T/T+1, EpisodeOutcome, or final boundary mismatch")
        with h5py.File(h5_path, "r") as handle:
            context_raw = handle["meta/task_context_json"][()].decode("utf-8")
            task_context = json.loads(context_raw)
            required_paths = (
                "obs/state/joint_position", "obs/state/boundary_identity_sha256",
                "obs/state/ee_pose", "obs/privileged_state/bowl_body_pose",
                "obs/privileged_state/plate_body_pose", "meta/boundary_context_v1_json",
            )
            if any(name not in handle for name in required_paths):
                raise ValueError("independent H5 is missing public state/boundary context evidence")
            joints = handle["obs/state/joint_position"][:]
            if joints.shape != (semantic["observation_count"], 9) or not np.isfinite(joints).all():
                raise ValueError("independent H5 joint observations are incomplete or non-finite")
            boundary_ids = handle["obs/state/boundary_identity_sha256"][:]
            if boundary_ids.shape != (semantic["observation_count"], 32) or boundary_ids.dtype != np.uint8:
                raise ValueError("independent H5 boundary identity observations have the wrong shape/dtype")
            ee_poses = handle["obs/state/ee_pose"][:]
            bowl_poses = handle["obs/privileged_state/bowl_body_pose"][:, 0, :]
            plate_poses = handle["obs/privileged_state/plate_body_pose"][:, 0, :]
            if (ee_poses.shape != (semantic["observation_count"], 7)
                    or bowl_poses.shape != (semantic["observation_count"], 7)
                    or plate_poses.shape != (semantic["observation_count"], 7)
                    or not np.isfinite(ee_poses).all()
                    or not np.isfinite(bowl_poses).all()
                    or not np.isfinite(plate_poses).all()):
                raise ValueError("independent H5 public frame/object observations are incomplete or non-finite")
            boundaries = json.loads(handle["meta/boundary_context_v1_json"][()].decode("utf-8"))
            if len(boundaries) != semantic["observation_count"]:
                raise ValueError("independent H5 boundary context must cover all T+1 observations")
            action_names = [*(f"joint{i}" for i in range(1, 8)), "aggregate_opening_m"]
            if any(f"universal_action/{name}" not in handle for name in action_names):
                raise ValueError("independent H5 public action channels are incomplete")
            actions = np.column_stack([
                handle[f"universal_action/{name}"][:].reshape(-1) for name in action_names
            ])
            if actions.shape != (semantic["transition_count"], 8) or not np.isfinite(actions).all():
                raise ValueError("independent H5 public actions are incomplete or non-finite")
        monitor_summary = _validate_physical_state_monitor(
            episode.get("physical_state_monitor"), progress, compiled, joints,
        )
        if (task_context.get("init_row_index") != expected_row
                or task_context.get("reset_sample_id") != sample.get("sample_id")
                or task_context.get("source_id") != episode.get("source_id")
                or task_context.get("source_closure_digest") != episode.get("source_closure_digest")):
            raise ValueError("independent H5 task context is not bound to the worker's reset row/source")
        if (task_context.get("schema_version") != "libero-episode-context-v1"
                or task_context.get("episode_id") != episode.get("episode_id")
                or task_context.get("provider_materialization_id") != progress.get("provider_materialization_id")
                or task_context.get("controller_identity") != episode.get("control_plan", {}).get("identity_sha256")):
            raise ValueError("independent H5 episode/materialization/controller identity mismatch")
        if (len(semantic["structured_controls"]) != semantic["transition_count"]
                or any(item is None for item in semantic["structured_controls"])):
            raise ValueError("independent H5 omits typed control target/Ack on one or more transitions")
        boundary_identity_fields = (
            "source_id", "source_closure_digest", "provider_materialization_id",
            "episode_id", "reset_sample_id", "control_step", "state_revision",
            "simulation_time_s",
        )
        for index, boundary in enumerate(boundaries):
            if (not isinstance(boundary, dict)
                    or boundary.get("schema_version") != "task-observation-context-v1"
                    or any(boundary.get(name) != task_context.get(name) for name in (
                        "source_id", "source_closure_digest", "provider_materialization_id",
                        "episode_id", "reset_sample_id",
                    ))
                    or boundary.get("control_step") != index
                    or boundary.get("state_revision") != index
                    or boundary.get("simulation_time_s") != index * 0.05):
                raise ValueError("independent H5 T/T+1 boundary order, clock, or episode identity mismatch")
            identity = {name: boundary[name] for name in boundary_identity_fields}
            expected_digest = digest(identity)
            if (boundary.get("state_boundary_identity_sha256") != expected_digest
                    or bytes(boundary_ids[index]).hex() != expected_digest):
                raise ValueError("independent H5 T/T+1 boundary identity digest mismatch")
            contact = boundary.get("contact_summary_v2")
            if (not isinstance(contact, dict)
                    or contact.get("status") != "available"
                    or contact.get("schema_version") != "task-contact-summary-v2"
                    or contact.get("requested_pairs") != [["akita_black_bowl_1", "plate_1"]]
                    or contact.get("covered_pairs") != contact.get("requested_pairs")
                    or any(contact.get(name) != boundary.get(name) for name in (
                        "source_id", "source_closure_digest", "provider_materialization_id",
                        "episode_id", "reset_sample_id", "control_step", "simulation_time_s",
                    ))):
                raise ValueError("independent H5 contact query coverage/freshness is incomplete")
            if contact.get("state_revision") != boundary.get("state_revision"):
                raise ValueError("independent H5 contact summary belongs to a stale state revision")
            count = contact.get("pair_counts", {}).get("akita_black_bowl_1/plate_1")
            if type(count) is not int or count < 0:
                raise ValueError("independent H5 contact pair count is missing or invalid")
            predicate = boundary.get("predicate_v1")
            xy_delta = bowl_poses[index, :2] - plate_poses[index, :2]
            source_on = bool(
                count > 0 and bowl_poses[index, 2] >= plate_poses[index, 2]
                and float(np.linalg.norm(xy_delta)) < 0.03
            )
            if (not isinstance(predicate, dict) or predicate.get("status") != "available"
                    or predicate.get("value") is not source_on):
                raise ValueError("independent H5 On predicate disagrees with source contact/pose rule")
        if boundaries[0]["control_step"] != 0 or boundaries[-1]["control_step"] != semantic["outcome"].final_boundary:
            raise ValueError("independent H5 reset/final boundary context does not match EpisodeOutcome")
        for index, control in enumerate(semantic["structured_controls"]):
            control.validate()
            if len(control.request.groups) != 1 or len(control.writer_controls) != 1:
                raise ValueError("independent H5 must contain the exact single mixed writer route")
            request_values = np.asarray(control.request.groups[0].values, dtype=np.float64)
            if request_values.shape != (8,) or not np.allclose(
                    request_values, actions[index], rtol=0.0, atol=1e-7):
                raise ValueError("independent H5 typed request differs from its public action row")
            if (control.request.groups[0].action_schema_id != "libero-joint-space-absolute-v1"
                    or any(not low <= float(value) <= high for value, (low, high) in zip(
                        request_values[:7], (
                            (-2.8973, 2.8973), (-1.7628, 1.7628), (-2.8973, 2.8973),
                            (-3.0718, -0.0698), (-2.8973, 2.8973), (-0.0175, 3.7525),
                            (-2.8973, 2.8973),
                        ), strict=True))
                    or not 0.0 <= float(request_values[7]) <= 0.08):
                raise ValueError("independent H5 action schema, joint order, or physical units are invalid")
            writer = control.writer_controls[0]
            if (writer.get("writer_id") != "libero-spatial-mixed-controller-v1"
                    or writer.get("action_schema_id") != "libero-joint-space-absolute-v1"
                    or writer.get("requested_action", {}).get("unit") != "rad_x7_plus_aggregate_opening_m"):
                raise ValueError("independent H5 mixed writer identity or unit metadata is invalid")
            raw_target = writer.get("controller_target", {}).get("payload")
            raw_ack = writer.get("applied_control", {}).get("payload")
            if not isinstance(raw_target, Mapping) or not isinstance(raw_ack, Mapping):
                raise ValueError("independent H5 structured control lacks the named target/Ack payload")
            target = MixedActuatorCommandV1.from_mapping(dict(raw_target))
            ack = AppliedMixedActuatorCommandV1.from_mapping(dict(raw_ack))
            if target.identity_hash != writer["controller_target"].get("identity_hash"):
                raise ValueError("independent H5 target payload identity hash mismatch")
            if ack.target_hash != target.identity_hash:
                raise ValueError("independent H5 target/Ack identity mismatch")
            if (target.task_artifact_hash != task_context.get("task_artifact_identity_hash")
                    or target.source_id != task_context.get("source_id")
                    or target.source_closure_digest != task_context.get("source_closure_digest")
                    or target.controller_identity != task_context.get("controller_identity")
                    or target.provider_materialization_id != task_context.get("provider_materialization_id")
                    or target.episode_id != task_context.get("episode_id")
                    or target.reset_sample_id != task_context.get("reset_sample_id")
                    or target.control_step != index or target.state_revision != index
                    or target.simulation_time_s != index * 0.05):
                raise ValueError("independent H5 target/source/boundary identity mismatch")
            expected_units = {
                **{f"joint{i}": "N*m" for i in range(1, 8)},
                "finger_joint1": "m", "finger_joint2": "m",
            }
            torque_limits = {
                **{f"joint{i}": 80.0 for i in range(1, 6)},
                "joint6": 12.0, "joint7": 12.0,
            }
            if (set(target.channel_values) != set(expected_units)
                    or dict(target.channel_units) != expected_units
                    or any(abs(float(target.channel_values[name])) > torque_limits[name]
                           for name in torque_limits)
                    or dict(ack.channel_values) != dict(target.channel_values)
                    or dict(ack.channel_units) != dict(target.channel_units)
                    or ack.provider_name != "mujoco"
                    or target.plan_identity_hash != compiled.get("plan_identity_hash")):
                raise ValueError("independent H5 native Ack does not match the named target")
            opening = float(request_values[7])
            expected_fingers = {"finger_joint1": opening / 2.0, "finger_joint2": -opening / 2.0}
            if any(not np.isclose(target.channel_values[name], value, rtol=0.0, atol=1e-7)
                   for name, value in expected_fingers.items()):
                raise ValueError("independent H5 target finger sign or aggregate-opening conversion is invalid")
        for endpoint_name, obs_index in (("initial_observation", 0), ("final_observation", -1)):
            endpoint = episode.get(endpoint_name)
            if not isinstance(endpoint, dict):
                raise ValueError("worker result omits a public initial/final observation receipt")
            if (not np.array_equal(joints[obs_index], np.asarray(endpoint.get("joint_position"), dtype=np.float64))
                    or not np.array_equal(ee_poses[obs_index], np.asarray(endpoint.get("ee_pose"), dtype=np.float64))
                    or bytes(boundary_ids[obs_index]).hex() != endpoint.get("boundary_identity_sha256")):
                raise ValueError("independent H5 initial/final observation differs from the worker's public receipt")
            for name in ("bowl_body_pose", "plate_body_pose"):
                if not np.array_equal(
                        (bowl_poses if name == "bowl_body_pose" else plate_poses)[obs_index],
                        np.asarray(endpoint.get("privileged_state", {}).get(name), dtype=np.float64)):
                    raise ValueError("independent H5 initial/final object pose differs from its public receipt")
        motion = _validate_public_motion_gate(
            episode.get("motion_summary", {}), joints[0], joints[-1], ee_poses[0], ee_poses[-1],
            require_thresholds=semantic["transition_count"] == 64,
        )
        total_t += semantic["transition_count"]
        total_obs += semantic["observation_count"]
        total_native += int(progress["native_step_count"])
        h5_receipts.append({"row_index": expected_row, "path": relative,
                            "transition_count": semantic["transition_count"],
                            "observation_count": semantic["observation_count"],
                            "episode_id": semantic["outcome"].episode_id,
                            "motion": motion,
                            "physical_state_monitor": monitor_summary,
                            "h5_sha256": episode["h5"]["sha256"]})
    if (total_t != report.get("transition_count") or total_obs != report.get("observation_count")
            or total_native != report.get("native_step_count")):
        raise ValueError("aggregate worker counts disagree with independently read H5 bundles")
    endpoints = report.get("diagnostic_endpoints")
    if (not isinstance(endpoints, list) or len(endpoints) != 2
            or report.get("reset_count") != report.get("episode_count") + len(endpoints)):
        raise ValueError("worker result omits the two separately counted public contact ResetPlan endpoints")
    for expected_name, expected_value, endpoint in zip(
            ("negative", "positive"), (False, True), endpoints, strict=True):
        plan_mapping = endpoint.get("reset_plan_v1")
        if not isinstance(plan_mapping, Mapping):
            raise ValueError("diagnostic endpoint omits its public ResetPlanV1 mapping")
        plan = ResetPlanV1.from_mapping(dict(plan_mapping))
        plan.validate()
        sample = plan.reset_sample
        readback = endpoint.get("reset_readback_v1")
        contact = endpoint.get("contact_summary_v2")
        predicate = endpoint.get("core_predicate_v1")
        source_oracle = endpoint.get("source_predicate_oracle")
        observation = endpoint.get("public_observation")
        progress = endpoint.get("runtime_progress")
        evidence = endpoint.get("reset_plan_evidence_v1")
        if (endpoint.get("endpoint") != expected_name
                or plan.purpose != "diagnostic_contact_endpoint"):
            raise ValueError("diagnostic endpoint name or ResetPlan purpose is invalid")
        if endpoint.get("reset_plan_identity_sha256") != plan.identity_hash:
            raise ValueError("diagnostic endpoint ResetPlan identity hash mismatch")
        if (not isinstance(readback, dict) or not isinstance(contact, dict)
                or not isinstance(predicate, dict) or not isinstance(source_oracle, dict)
                or not isinstance(observation, dict) or not isinstance(progress, dict)
                or not isinstance(evidence, dict)):
            raise ValueError("diagnostic endpoint readback, contact, or predicate receipt is incomplete")
        if (evidence.get("schema_version") != "reset-plan-evidence-v1"
                or evidence.get("reset_plan_identity_sha256") != plan.identity_hash
                or evidence.get("purpose") != plan.purpose
                or evidence.get("reset_sample_id") != sample.sample_id
                or readback.get("reset_sample_id") != sample.sample_id
                or readback.get("simulation_time_s") != sample.simulation_time_s
                or readback.get("joint_position") != dict(sample.joint_position)
                or readback.get("joint_velocity") != dict(sample.joint_velocity)
                or readback.get("poses_world") != {key: value.to_mapping() for key, value in sample.poses_world.items()}
                or readback.get("free_joint_velocity") != {key: list(value) for key, value in sample.free_joint_velocity.items()}
                or progress.get("episode_id") != contact.get("episode_id")
                or progress.get("reset_sample_id") != sample.sample_id
                or progress.get("native_step_count") != 0
                or progress.get("control_step") != 0):
            raise ValueError("diagnostic endpoint ResetPlan readback or zero-step progress identity mismatch")
        if (contact.get("status") != "available"
                or contact.get("schema_version") != "task-contact-summary-v2"
                or contact.get("requested_pairs") != [["akita_black_bowl_1", "plate_1"]]
                or contact.get("covered_pairs") != contact.get("requested_pairs")
                or any(contact.get(key) != progress.get(key) for key in (
                    "source_id", "source_closure_digest", "provider_materialization_id",
                    "episode_id", "reset_sample_id", "control_step",
                ))
                or contact.get("state_revision") != progress.get("state_revision")
                or contact.get("simulation_time_s") != progress.get("simulation_time_episode_s")):
            raise ValueError("diagnostic endpoint contact query is unavailable, stale, or incomplete")
        poses = observation.get("privileged_state", {})
        bowl = poses.get("bowl_body_pose")
        plate = poses.get("plate_body_pose")
        if (not isinstance(bowl, list) or len(bowl) != 7
                or not isinstance(plate, list) or len(plate) != 7):
            raise ValueError("diagnostic endpoint lacks named public bowl/plate body poses")
        expected_source_value = _source_on_predicate_oracle_v1(contact, bowl, plate)
        if (source_oracle.get("schema_version") != "libero-on-source-oracle-v1"
                or source_oracle.get("value") is not expected_source_value
                or predicate.get("status") != "available"
                or predicate.get("value") is not expected_source_value
                or expected_source_value is not expected_value):
            raise ValueError("diagnostic endpoint Core/source On predicate positive-negative oracle mismatch")
        boundary_identity = {key: contact[key] for key in (
            "source_id", "source_closure_digest", "provider_materialization_id",
            "episode_id", "reset_sample_id", "control_step", "state_revision",
            "simulation_time_s",
        )}
        if observation.get("boundary_identity_sha256") != digest(boundary_identity):
            raise ValueError("diagnostic endpoint observation/contact boundary identity mismatch")
    if report["final_session_close_receipt"].get("session_closed") is not True:
        raise ValueError("worker result lacks the final RuntimeSession close receipt")
    result = {
        "schema_version": "r07c-d01-independent-reader-v1",
        "status": "verified_complete",
        "episode_count": 3,
        "transition_count": total_t,
        "observation_count": total_obs,
        "native_step_count": total_native,
        "reset_count": report["reset_count"],
        "diagnostic_endpoint_count": len(endpoints),
        "h5": h5_receipts,
    }
    if parent_run_record_path is not None:
        if expected_lock_path is None:
            raise ValueError("independent native readback requires the expected shared lock path")
        result["parent_process"] = _validate_parent_run_record(
            bundle_path, report, parent_run_record_path, expected_lock_path,
        )
    elif expected_lock_path is not None:
        raise ValueError("expected native lock path requires a parent run record")
    return result


def main(argv: list[str] | None = None) -> int:
    """Native worker and separate provider-free reader entry points."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--run-worker", metavar="OUTPUT_DIR")
    modes.add_argument("--read-bundle", metavar="WORKER_RESULT_JSON")
    parser.add_argument("--parent-run-record", type=Path)
    parser.add_argument("--expected-lock-path", type=Path)
    parser.add_argument("--steps", type=int, default=64)
    parser.add_argument("--task-solution-1", action="store_true")
    parser.add_argument("--source-xml", type=Path)
    parser.add_argument("--composition-plan", type=Path)
    parser.add_argument("--install-root", type=Path)
    parser.add_argument("--require-motion-thresholds", action="store_true")
    parser.add_argument("--require-mujoco-runtime-identity", action="store_true")
    args = parser.parse_args(argv)
    if args.read_bundle:
        receipt = consume_libero_candidate_bundle(
            Path(args.read_bundle), parent_run_record_path=args.parent_run_record,
            expected_lock_path=args.expected_lock_path,
            require_motion_thresholds=args.require_motion_thresholds,
            require_mujoco_runtime_identity=args.require_mujoco_runtime_identity,
        )
        print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
        return 0
    if args.task_solution_1:
        if not all((args.source_xml, args.composition_plan, args.install_root)):
            parser.error("--task-solution-1 requires --source-xml, --composition-plan, and --install-root")
        from .selected_candidate import build_libero_solution_candidate
        from .solution import LiberoPickPlaceSolutionV1
        from task_env.runtime.sessions.source import source_asset_bytes

        source_xml = args.source_xml.resolve(strict=True).read_bytes()
        composition_plan_path = args.composition_plan.resolve(strict=True)
        plan_bytes = composition_plan_path.read_bytes()
        install_root = args.install_root.resolve(strict=True)
        env = build_libero_solution_candidate(
            xml=source_xml, composed_mjcf_sha256=hashlib.sha256(source_xml).hexdigest(),
            install_root=install_root, composition_plan_path=composition_plan_path,
            horizon=args.steps,
        )
        source_files = {
            "canonical-source.xml": source_xml,
            "scene.xml": source_xml,
            **source_asset_bytes(install_root, source_xml.decode("utf-8")),
        }
        result = run_libero_candidate_worker(
            env, output_dir=Path(args.run_worker), steps=args.steps,
            solution_factory=lambda: LiberoPickPlaceSolutionV1(source_xml),
            source_closure_files=source_files,
            composition_plan_bytes=plan_bytes,
        )
    else:
        from .selected_candidate import build_libero_selected_candidate

        env = build_libero_selected_candidate(horizon=args.steps)
        result = run_libero_candidate_worker(env, output_dir=Path(args.run_worker), steps=args.steps)
    print(json.dumps({
        "status": result["status"], "episode_count": result["episode_count"],
        "transition_count": result["transition_count"],
        "observation_count": result["observation_count"],
        "native_step_count": result["native_step_count"],
        "result_sha256": result["result_sha256"],
    }, sort_keys=True))
    return 0 if result["status"] == "complete" else 2


__all__ = ["consume_libero_candidate_bundle", "run_libero_candidate_worker"]


if __name__ == "__main__":
    raise SystemExit(main())
