"""Run one frozen LIBERO action sequence through the public TaskEnv lifecycle."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")


def _action_values(item: Any) -> list[float]:
    if isinstance(item, Mapping):
        if "action" in item:
            item = item["action"]
        elif {"expected_target_position_m", "expected_target_quaternion_wxyz", "raw_action"} <= set(item):
            item = [*item["expected_target_position_m"],
                    *item["expected_target_quaternion_wxyz"], item["raw_action"][6]]
        else:
            raise ValueError("action row must contain action or frozen upstream target fields")
    values = np.asarray(item, dtype=np.float64)
    if values.shape != (8,) or not np.isfinite(values).all():
        raise ValueError("LIBERO replay actions must contain eight finite values")
    return values.tolist()


def _reset_options(row_index: int, options: Mapping[str, Any] | None) -> dict[str, Any]:
    if options is not None:
        return dict(options)
    return {"init_row_index": row_index}


def run_libero_replay(env, *, output_dir: Path, action_sequence: Sequence[Any] | None = None,
                      solution_factory=None, seed: int = 19, row_index: int = 0,
                      reset_options: Mapping[str, Any] | None = None,
                      maximum_steps: int = 1000) -> dict[str, Any]:
    """Use one lifecycle and result shape for captured actions or optional V8."""
    if (type(seed) is not int or type(row_index) is not int or row_index not in (0, 1, 2)
            or type(maximum_steps) is not int or not 1 <= maximum_steps <= 1000):
        raise ValueError("LIBERO replay requires seed, row, and step limits in the supported range")
    if (action_sequence is None) == (solution_factory is None):
        raise ValueError("select exactly one frozen action sequence or optional Solution")
    actions = None if action_sequence is None else [_action_values(row) for row in action_sequence]
    if actions is not None and not actions:
        raise ValueError("LIBERO replay action sequence must not be empty")
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"replay output directory must be fresh and empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "solution-v8" if solution_factory is not None else "frozen-actions"
    episode = None
    error = None
    close_error = None
    close_receipt = None
    finalized = None
    recording_started = False
    solution = None
    reset_info: dict[str, Any] = {}
    final_info: dict[str, Any] = {}
    trace = []
    h5_path = output_dir / "trajectory.h5"
    try:
        if solution_factory is None:
            _, reset_info = env.reset(
                seed=seed, options=_reset_options(row_index, reset_options),
            )
        else:
            solution = solution_factory(output_dir)
            if getattr(solution, "solution_schema_version", None) != "libero-bowl-to-plate-solution-v8":
                raise ValueError("optional Solution factory must return the frozen V8 policy")
            _, reset_info = env.reset_for_solution(
                solution, seed=seed, options=_reset_options(row_index, reset_options),
            )
        env.start_recording(h5_path)
        recording_started = True
        final_info = dict(reset_info)
        terminated = truncated = False
        step_limit = len(actions) if actions is not None else maximum_steps
        for index in range(step_limit):
            if actions is None:
                _, _, terminated, truncated, info = env.step_with_solution(solution)
                action = info.get("external_action")
                if action is None:
                    raise ValueError("V8 public step omitted its typed external action")
                values = np.asarray(action, dtype=np.float64).reshape(-1).tolist()
            else:
                values = actions[index]
                _, _, terminated, truncated, info = env.step(np.asarray(values))
            trace.append({
                "index": index,
                "action": values,
                "control_step": int(info.get("control_step", -1)),
                "simulation_time_s": float(info.get("simulation_time_s", float("nan"))),
                "terminated": bool(terminated), "truncated": bool(truncated),
            })
            final_info = dict(info)
            if terminated or truncated or (solution is not None and (solution.done or solution.failed)):
                break
        if not trace:
            raise RuntimeError("LIBERO replay produced no public transitions")
        end = final_info.get("episode_end_v1")
        if not isinstance(end, Mapping):
            end = env.stop("frozen_replay_complete").to_mapping()
        reason = end.get("outcome", {}).get("end_reason")
        if type(reason) is not str or not reason:
            raise ValueError("public episode end omitted a typed reason")
        finalized = env.finish_recording(reason)
        recording_started = False
        h5_path = Path(finalized["path"]).resolve(strict=True)
        raw_h5 = h5_path.read_bytes()
        progress = env.get_runtime_progress_receipt()
        if (progress.get("episode_id") != reset_info.get("episode_id")
                or progress.get("control_step") != len(trace)
                or progress.get("native_step_count") != len(trace) * env.artifact.timebase.control_substeps):
            raise ValueError("Runtime progress receipt differs from the frozen replay boundaries")
        source = env.value.get("source")
        receipt = getattr(source, "execution_source_receipt", None)
        source_receipt = receipt.to_mapping() if callable(getattr(receipt, "to_mapping", None)) else None
        if source_receipt is None:
            raise ValueError("LIBERO replay requires the public RuntimeSource receipt")
        episode = {
            "episode_id": reset_info.get("episode_id"),
            "task_uid": env.artifact.task_id,
            "provider": getattr(env, "provider", None),
            "task_artifact_identity_hash": env.artifact.identity_hash,
            "source_id": reset_info.get("source_id"),
            "source_xml_sha256": receipt.canonical_xml_sha256,
            "source_closure_digest": reset_info.get("source_closure_digest"),
            "controller_identity": getattr(env.controller, "identity", None),
            "controller_profile_id": getattr(env.controller, "profile_id", None),
            "solution_schema_version": getattr(solution, "solution_schema_version", None),
            "solution_identity": getattr(solution, "identity", None),
            "arm_resolver_identity": env.value.get("arm_resolver_identity"),
            "action_schema": env.value.get("action_schema"),
            "reset_sample": reset_info.get("reset_sample_v1"),
            "reset_realization": reset_info.get("reset_realization_v1"),
            "reset_readback": reset_info.get("reset_readback_v1"),
            "pre_reset_compiled_validation": reset_info.get("pre_reset_compiled_validation_v1"),
            "action_trace": trace,
            "task_success": bool(final_info.get("is_success", False)),
            "predicate": final_info.get("predicate_v1"),
            "episode_end": end,
            "runtime_progress": progress,
            "source_receipt": source_receipt,
            "recording": {
                "relative_path": h5_path.relative_to(output_dir).as_posix(),
                "bytes": len(raw_h5), "sha256": hashlib.sha256(raw_h5).hexdigest(),
                "transition_count": finalized.get("transition_count"),
                "observation_count": finalized.get("observation_count"),
            },
        }
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        if recording_started:
            try:
                finalized = env.finish_recording("execution_fault")
            except BaseException as finish_error:
                error["recording_close_error"] = {
                    "type": type(finish_error).__name__, "message": str(finish_error),
                }
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
    payload = {
        "schema_version": "libero-replay-result-v1",
        "status": "complete" if episode is not None and error is None and close_error is None
                  and isinstance(close_receipt, Mapping)
                  and close_receipt.get("session_closed") is True
                  and close_receipt.get("cleanup_completed", True) is True
                  and close_receipt.get("cleanup_error") is None
                  and close_receipt.get("task_resource_close_error") is None else "failed",
        "mode": mode, "task_uid": getattr(getattr(env, "artifact", None), "task_id", None),
        "seed": seed, "row_index": row_index,
        "action_sequence_sha256": None if actions is None else hashlib.sha256(_canonical(actions)).hexdigest(),
        "episode": episode, "final_session_close_receipt": close_receipt,
        "worker_error": error, "close_error": close_error,
    }
    result = {**payload, "result_sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
    _write_json(output_dir / "result.json", result)
    return result


__all__ = ["run_libero_replay"]
