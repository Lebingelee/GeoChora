"""Internal R07c candidate worker wrapper for provider-free S1 only.

This composes the existing BaseTaskEnv, TransitionRecordWrapper and H5 readers.
It is not a registered environment, native worker, or supported deployment API.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from task_env.recorders import (
    RecorderConfig,
    TransitionRecordWrapper,
    inspect_trajectory_h5,
    load_structured_control_records_h5,
)


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def run_candidate_episode(
    env,
    *,
    action: np.ndarray,
    output_dir: Path,
    run_id: str,
    seed: int,
) -> dict[str, Any]:
    """Run one already-built candidate Env, finalize it, and write a receipt.

    Exceptions from reset/step are captured in the worker result so the same
    finalizer and report consumer can verify both success and failure paths.
    """
    output_dir = Path(output_dir).resolve()
    if type(run_id) is not str or not run_id or Path(run_id).name != run_id:
        raise ValueError("run_id must be a non-empty filename stem")
    output_dir.mkdir(parents=True, exist_ok=True)
    recording = TransitionRecordWrapper(
        env,
        RecorderConfig(schema_version="v3", max_transitions=4, max_buffer_bytes=2_000_000),
    )
    worker_error = None
    close_error = None
    reset_info: dict[str, Any] = {}
    final_info: dict[str, Any] = {}
    final_transition_count = 0
    final_observation_count = 0
    recording.start_record()
    try:
        _, reset_info = recording.reset(seed=seed)
        _, _, _, _, final_info = recording.step(np.asarray(action, dtype=np.float32))
        final_transition_count = recording.recorder.transition_count
        final_observation_count = recording.recorder.observation_count
    except Exception as exc:
        worker_error = {"type": type(exc).__name__, "message": str(exc)}
        final_transition_count = recording.recorder.transition_count
        final_observation_count = recording.recorder.observation_count
    finally:
        try:
            recording.close()
        except Exception as exc:
            close_error = {"type": type(exc).__name__, "message": str(exc)}

    h5_path = recording.save_h5(output_dir, run_id)
    inspection = inspect_trajectory_h5(h5_path)
    semantic = load_structured_control_records_h5(h5_path)
    end = env._last_episode_end
    outcome = end.outcome
    h5_bytes = h5_path.read_bytes()
    payload: dict[str, Any] = {
        "schema_version": "r07c-libero-core-candidate-worker-result-v1",
        "run_id": run_id,
        "task_uid": getattr(env, "task_uid", None),
        "source_xml_sha256": getattr(env._task_definition, "source_xml_sha256", None),
        "episode_id": outcome.episode_id,
        "execution_status": (
            "passed" if worker_error is None and close_error is None else "failed"
        ),
        "task_success": final_info.get("is_success"),
        "worker_error": worker_error,
        "close_error": close_error,
        "close_success": close_error is None and bool(getattr(env, "_closed", False)),
        "finalizer": {
            "end_reason": outcome.end_reason,
            "final_boundary": outcome.final_boundary,
            "episode_id": outcome.episode_id,
            "requested_reason": end.boundary_event.payload.get("requested_reason"),
        },
        "recorder_counts": {
            "transition_count": final_transition_count,
            "observation_count": final_observation_count,
        },
        "h5": {
            "relative_path": h5_path.name,
            "bytes": len(h5_bytes),
            "sha256": hashlib.sha256(h5_bytes).hexdigest(),
            "schema_version": inspection.get("schema_version"),
            "transition_count": semantic["transition_count"],
            "observation_count": semantic["observation_count"],
            "episode_id": semantic["outcome"].episode_id,
            "final_boundary": semantic["outcome"].final_boundary,
        },
        "production_readers": {
            "trajectory_inspection": "passed",
            "structured_control_records": "passed",
        },
    }
    report_path = output_dir / f"{run_id}.result.json"
    report = {**payload, "result_sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def consume_candidate_episode_report(report_path: Path) -> dict[str, Any]:
    """Independently verify the worker receipt and raw H5 identity/counts."""
    import h5py

    report_path = Path(report_path).resolve(strict=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest = report.get("result_sha256")
    payload = {key: value for key, value in report.items() if key != "result_sha256"}
    if type(digest) is not str or hashlib.sha256(_canonical(payload)).hexdigest() != digest:
        raise ValueError("worker result self-digest does not match")
    if report.get("schema_version") != "r07c-libero-core-candidate-worker-result-v1":
        raise ValueError("unsupported candidate worker result schema")
    filename = report.get("h5", {}).get("relative_path")
    if type(filename) is not str or not filename or Path(filename).name != filename:
        raise ValueError("worker H5 path must be a sibling filename")
    h5_path = report_path.parent / filename
    h5_bytes = h5_path.read_bytes()
    h5_summary = report["h5"]
    if len(h5_bytes) != h5_summary.get("bytes"):
        raise ValueError("worker H5 byte count mismatch")
    if hashlib.sha256(h5_bytes).hexdigest() != h5_summary.get("sha256"):
        raise ValueError("worker H5 digest mismatch")
    with h5py.File(h5_path, "r") as handle:
        transition_count = int(handle.attrs["transition_count"])
        observation_count = int(handle.attrs["observation_count"])
        outcome = json.loads(handle["meta/episode_outcome_v1_json"][()].decode("utf-8"))
    if (transition_count != h5_summary.get("transition_count")
            or observation_count != h5_summary.get("observation_count")
            or observation_count != transition_count + 1):
        raise ValueError("independent H5 count/T+1 verification failed")
    if (outcome.get("episode_id") != report.get("episode_id")
            or outcome.get("episode_id") != h5_summary.get("episode_id")
            or outcome.get("final_boundary") != h5_summary.get("final_boundary")):
        raise ValueError("independent H5 outcome identity mismatch")
    execution_status = report.get("execution_status")
    if execution_status == "passed":
        if (report.get("worker_error") is not None or report.get("close_error") is not None
                or report.get("close_success") is not True or transition_count < 1):
            raise ValueError("worker success status lacks successful execution/finalizer evidence")
    elif execution_status == "failed":
        if report.get("worker_error") is None and report.get("close_error") is None:
            raise ValueError("worker failure status has no recorded failure")
    else:
        raise ValueError("unknown worker execution status")
    return {
        "status": "verified_success" if execution_status == "passed" else "verified_failure",
        "task_success": report.get("task_success"),
        "transition_count": transition_count,
        "observation_count": observation_count,
        "episode_id": outcome["episode_id"],
    }


__all__ = ["consume_candidate_episode_report", "run_candidate_episode"]
