"""Independent semantic reader for unified LIBERO replay results."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from task_env.controllers.canonical.contracts import (
    AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
)
from task_env.recorders import load_structured_control_records_h5


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _read_result(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    result = json.loads(raw)
    if not isinstance(result, Mapping) or result.get("schema_version") != "libero-replay-result-v1":
        raise ValueError("unsupported LIBERO replay result schema")
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    if result.get("result_sha256") != hashlib.sha256(_canonical(payload)).hexdigest():
        raise ValueError("LIBERO replay result digest mismatch")
    if (result.get("status") != "complete" or result.get("worker_error") is not None
            or result.get("close_error") is not None
            or result.get("mode") not in {"frozen-actions", "solution-v8"}):
        raise ValueError("LIBERO replay result is incomplete or failed")
    close = result.get("final_session_close_receipt")
    if (not isinstance(close, Mapping) or close.get("session_closed") is not True
            or close.get("cleanup_completed", True) is not True
            or close.get("cleanup_error") is not None
            or close.get("task_resource_close_error") is not None):
        raise ValueError("LIBERO replay did not close its RuntimeSession and task resources cleanly")
    return dict(result)


def _validate_source_receipt(episode: Mapping[str, Any]) -> dict[str, Any]:
    receipt = episode.get("source_receipt")
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != "runtime-execution-source-receipt-v1":
        raise ValueError("LIBERO replay omitted its RuntimeSource closure receipt")
    files = receipt.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("LIBERO RuntimeSource receipt has no closure manifest")
    paths = []
    for item in files:
        if (not isinstance(item, Mapping) or set(item) != {"path", "size_bytes", "sha256"}
                or type(item.get("path")) is not str or type(item.get("size_bytes")) is not int
                or item["size_bytes"] < 0 or type(item.get("sha256")) is not str
                or len(item["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in item["sha256"])):
            raise ValueError("LIBERO RuntimeSource closure manifest entry is invalid")
        logical = PurePosixPath(item["path"])
        if (logical.is_absolute() or logical.as_posix() != item["path"]
                or any(part in {"", ".", ".."} for part in logical.parts)):
            raise ValueError("LIBERO RuntimeSource closure contains an unsafe logical path")
        paths.append(item["path"])
    if paths != sorted(set(paths)):
        raise ValueError("LIBERO RuntimeSource closure manifest is not unique and canonical")
    files_by_path = {item["path"]: item for item in files}
    canonical = files_by_path.get("canonical-source.xml")
    importer = files_by_path.get("scene.xml")
    if (canonical is None or importer is None
            or canonical["sha256"] != receipt.get("canonical_xml_sha256")
            or importer["sha256"] != receipt.get("importer_xml_sha256")
            or receipt.get("source_id") != episode.get("source_id")
            or receipt.get("source_closure_digest") != episode.get("source_closure_digest")
            or receipt.get("canonical_xml_sha256") != episode.get("source_xml_sha256")):
        raise ValueError("LIBERO RuntimeSource receipt differs from the episode identity")
    closure_payload = {"schema_version": "source-closure-v1", "files": files}
    closure_digest = hashlib.sha256(_canonical(closure_payload)).hexdigest()
    if closure_digest != receipt.get("source_closure_digest"):
        raise ValueError("LIBERO RuntimeSource closure digest does not match its manifest")
    return dict(receipt)


def _read_h5(bundle: Path, episode: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    receipt = episode.get("recording")
    if not isinstance(receipt, Mapping):
        raise ValueError("LIBERO replay result omitted its recording receipt")
    name = receipt.get("relative_path")
    logical = PurePosixPath(name) if type(name) is str else PurePosixPath("..")
    if logical.is_absolute() or any(part in {"", ".", ".."} for part in logical.parts):
        raise ValueError("LIBERO replay H5 path is unsafe")
    path = bundle.joinpath(*logical.parts)
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True).parent != bundle:
        raise ValueError("LIBERO replay H5 is missing or escaped its result directory")
    raw = path.read_bytes()
    if (len(raw) != receipt.get("bytes")
            or hashlib.sha256(raw).hexdigest() != receipt.get("sha256")):
        raise ValueError("LIBERO replay H5 bytes or hash differ from the recording receipt")
    return path, load_structured_control_records_h5(path)


def _validate_episode(episode: Mapping[str, Any], bundle: Path, mode: str) -> dict[str, Any]:
    path, records = _read_h5(bundle, episode)
    source_receipt = _validate_source_receipt(episode)
    outcome = records["outcome"]
    actions = episode.get("action_trace")
    count = records["transition_count"]
    if (not isinstance(actions, list) or len(actions) != count
            or records["observation_count"] != count + 1
            or outcome.final_boundary != count
            or outcome.episode_id != episode.get("episode_id")):
        raise ValueError("LIBERO replay H5 has a T/T+1, episode, or final-boundary mismatch")
    if (records["env_meta"].get("action_schema", {}).get("schema_id")
            != episode.get("action_schema", {}).get("schema_id")):
        raise ValueError("LIBERO replay action schema differs from the independently stored H5 metadata")
    metadata_context = records["env_meta"].get("task_context")
    if (not isinstance(metadata_context, Mapping)
            or metadata_context.get("task_artifact_identity_hash") != episode.get("task_artifact_identity_hash")
            or metadata_context.get("source_id") != episode.get("source_id")
            or metadata_context.get("source_xml_sha256") != source_receipt.get("canonical_xml_sha256")
            or metadata_context.get("source_closure_digest") != episode.get("source_closure_digest")
            or metadata_context.get("controller_identity") != episode.get("controller_identity")
            or metadata_context.get("episode_id") != episode.get("episode_id")
            or metadata_context.get("reset_sample_id") != episode.get("reset_sample", {}).get("sample_id")
            or metadata_context.get("provider_materialization_id")
               != episode.get("runtime_progress", {}).get("provider_materialization_id")
            or metadata_context.get("solution_identity") != episode.get("solution_identity")):
        raise ValueError("LIBERO replay identity differs from independently stored H5 task metadata")
    if mode == "solution-v8":
        if episode.get("solution_schema_version") != "libero-bowl-to-plate-solution-v8":
            raise ValueError("LIBERO Solution replay omitted its V8 strategy identity")
        from bench_deploy.libero.tasks.solution import solution_identity_v8

        expected_solution_identity = solution_identity_v8(
            source_receipt["canonical_xml_sha256"],
            source_receipt["source_closure_digest"],
            arm_resolver_identity=episode.get("arm_resolver_identity"),
        )
        if (episode.get("solution_identity") != expected_solution_identity
                or episode.get("solution_identity") != metadata_context.get("solution_identity")):
            raise ValueError("LIBERO V8 strategy hash differs from its pinned source/controller parameters")
    elif episode.get("solution_identity") is not None:
        raise ValueError("frozen-action replay must not claim a V8 Solution identity")
    contexts = records.get("boundary_contexts")
    if not isinstance(contexts, list) or len(contexts) != count + 1:
        raise ValueError("LIBERO replay H5 omitted its T/T+1 public boundary identities")
    first_target = None
    for index, (control, trace, context) in enumerate(zip(records["structured_controls"], actions, contexts)):
        if control is None or not isinstance(trace, Mapping):
            raise ValueError(f"LIBERO replay transition {index} is missing typed control evidence")
        action = np.asarray(trace.get("action"), dtype=np.float64)
        mapping = control.to_mapping()
        groups = mapping["request"]["groups"]
        writers = mapping["writer_controls"]
        if (action.ndim != 1 or len(groups) != 1 or len(writers) != 1
                or not np.allclose(np.asarray(groups[0]["values"], dtype=np.float64), action,
                                   rtol=0.0, atol=1e-7)):
            raise ValueError(f"LIBERO replay transition {index} Action differs from the H5 request")
        writer = writers[0]
        if writer.get("action_schema_id") != episode["action_schema"].get("schema_id"):
            raise ValueError(f"LIBERO replay transition {index} uses another action schema")
        target_row = writer.get("controller_target")
        ack_row = writer.get("applied_control")
        if not isinstance(target_row, Mapping) or not isinstance(ack_row, Mapping):
            raise ValueError(f"LIBERO replay transition {index} omits Target or Ack")
        target = MixedActuatorCommandV1.from_mapping(dict(target_row["payload"]))
        ack = AppliedMixedActuatorCommandV1.from_mapping(dict(ack_row["payload"]))
        if ack.mapping == "source_bound_named_actuator_channels_float32_control_zoh_v1":
            # GeoPhys stores native controls as float32. Its acknowledgement
            # reports the exact representable value written to that control
            # vector, so compare against that deterministic representation of
            # the Target instead of treating ordinary narrowing as clipping.
            applied_values_match = (
                ack.provider_name == "geophys"
                and dict(ack.channel_values) == {
                    key: float(np.float32(value))
                    for key, value in target.channel_values.items()
                }
            )
        else:
            applied_values_match = dict(ack.channel_values) == dict(target.channel_values)
        if (target.identity_hash != target_row.get("identity_hash")
                or ack.target_hash != target.identity_hash or ack.clipped
                or not applied_values_match
                or dict(ack.channel_units) != dict(target.channel_units)):
            raise ValueError(f"LIBERO replay transition {index} Target/Ack mismatch or clipping")
        if (target.task_artifact_hash != episode.get("task_artifact_identity_hash")
                or target.source_id != episode.get("source_id")
                or target.source_closure_digest != episode.get("source_closure_digest")
                or target.controller_identity != episode.get("controller_identity")
                or target.episode_id != episode.get("episode_id")
                or target.control_step != index
                or context.get("control_step") != index
                or context.get("episode_id") != target.episode_id
                or context.get("source_id") != target.source_id
                or context.get("source_closure_digest") != target.source_closure_digest
                or context.get("reset_sample_id") != target.reset_sample_id
                or context.get("provider_materialization_id") != target.provider_materialization_id):
            raise ValueError(f"LIBERO replay transition {index} source or boundary identity mismatch")
        if first_target is None:
            first_target = target
        if ack.provider_name != episode.get("provider"):
            raise ValueError(f"LIBERO replay transition {index} provider Ack mismatch")
    final_context = contexts[-1]
    if (first_target is None or final_context.get("control_step") != count
            or final_context.get("episode_id") != first_target.episode_id
            or final_context.get("source_id") != first_target.source_id
            or final_context.get("source_closure_digest") != first_target.source_closure_digest
            or final_context.get("reset_sample_id") != first_target.reset_sample_id
            or final_context.get("provider_materialization_id") != first_target.provider_materialization_id):
        raise ValueError("LIBERO replay final T+1 boundary identity differs from its transition sequence")
    predicate = episode.get("predicate")
    if (episode.get("task_success") is not outcome.task_success
            or (outcome.task_success is True and not isinstance(predicate, Mapping))
            or (isinstance(predicate, Mapping) and any(
                item.get("status") == "unavailable" and outcome.task_success is True
                for item in predicate.values() if isinstance(item, Mapping)
            ))):
        raise ValueError("LIBERO replay task-success claim conflicts with H5 outcome or predicate availability")
    if episode.get("episode_end", {}).get("outcome", {}).get("end_reason") != outcome.end_reason:
        raise ValueError("LIBERO replay end reason differs from the independently stored H5 outcome")
    if (episode.get("recording", {}).get("transition_count") != count
            or episode.get("recording", {}).get("observation_count") != count + 1):
        raise ValueError("LIBERO replay recording receipt has incorrect T/T+1 counts")
    return {"episode_id": outcome.episode_id, "h5_path": str(path),
            "transition_count": count, "observation_count": count + 1,
            "end_reason": outcome.end_reason, "task_success": outcome.task_success,
            "mode": mode}


def consume_libero_replay_result(result_path: Path) -> dict[str, Any]:
    """Recompute result/H5 integrity, typed action-target-ack, source, and lifecycle facts."""
    path = Path(result_path).resolve(strict=True)
    result = _read_result(path)
    episode = result.get("episode")
    if not isinstance(episode, Mapping):
        raise ValueError("LIBERO replay result omitted its episode")
    summary = _validate_episode(episode, path.parent, result["mode"])
    return {"schema_version": "libero-replay-independent-reader-v1",
            "status": "verified_complete", "result_sha256": result["result_sha256"],
            "episode": summary}


__all__ = ["consume_libero_replay_result"]
