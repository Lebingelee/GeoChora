"""Strict recorder I/O parity and corruption tests; no FULL qualification claim."""

import copy
import gzip
import json
from pathlib import Path

import h5py
import pytest

from task_env.controllers.canonical.contracts import digest
from task_env.trajectory.canonical.execution import (
    ExecutionRecorder, LEGACY_SCHEMA, expand_snapshot, load, save, validate,
)
from task_env.trajectory.canonical.contracts import BoundaryRecord, EpisodeMetadata
from task_env.trajectory.canonical.streaming import (
    _JsonCursor, _json_bytes, load_streaming, logical_chunks, save_streaming, snapshot_digest,
    validate_streaming, verify_payload_integrity, verify_roundtrip,
)
from task_env.diagnostics.phase1.integration.recording_io_audit import audit


@pytest.fixture
def episode():
    path = Path(__file__).parent / "fixtures/execution_prefix_fixture.json.gz"
    return json.loads(gzip.decompress(path.read_bytes()))


def test_chunked_json_is_exact_for_float_unicode_and_nested_values():
    value = {"schema": "test", "boundaries": [{"unicode": "夹爪", "zero": -0.0,
              "floats": [1e-200, 1e200, 0.1], "escaped": '\\"\n'}],
             "transitions": [], "blobs": {"x": {"kind": "content-ref"}},
             "other": [None, True, False, 3]}
    assert b"".join(logical_chunks(value, 17)) == _json_bytes(value)
    assert b"".join(logical_chunks(value, 1)) == _json_bytes(value)
    with pytest.raises(ValueError):
        list(logical_chunks({"x": float("nan")}))


@pytest.mark.parametrize("legacy", [False, True])
def test_old_and_streaming_h5_have_identical_logical_payload_and_reader_output(tmp_path, episode, legacy):
    if legacy:
        episode["schema"] = LEGACY_SCHEMA
    old, new = tmp_path / "old.h5", tmp_path / "new.h5"
    save(old, episode)
    receipt = save_streaming(new, episode, chunk_bytes=4096)
    checked = verify_roundtrip(new, episode, chunk_bytes=8192)
    assert receipt["logical_hash"] == checked["logical_hash"] == digest(episode)
    assert checked["byte_exact"] and not checked["legacy_full_object_load_executed"]
    assert load(old) == load(new) == episode
    assert load_streaming(old, chunk_bytes=257) == load_streaming(new) == episode
    assert validate_streaming(old, chunk_bytes=257)["semantic_validation"] == "PASS"
    assert validate_streaming(new, chunk_bytes=257)["semantic_validation"] == "PASS"
    with h5py.File(old, "r") as a, h5py.File(new, "r") as b:
        assert a["logical_json_utf8"][:].tobytes() == b["logical_json_utf8"][:].tobytes()
        assert a.attrs["schema"] == b.attrs["schema"]


def test_snapshot_hash_matches_historical_expansion_without_mutating_source(episode):
    before = copy.deepcopy(episode)
    cache = {name: _json_bytes(blob) for name, blob in episode["blobs"].items()}
    for boundary in episode["boundaries"]:
        expanded = expand_snapshot(boundary["owners"], episode["blobs"])
        expanded.pop("integrity_hash")
        assert snapshot_digest(boundary["owners"], cache) == digest(expanded)
    validate(episode)
    assert episode == before


def test_content_references_in_other_owner_fields_remain_compatible(episode):
    stage = episode["boundaries"][0]["owners"]["owners"]["coordinator"]["fields"]["_stage_index"]["value"]
    key = digest(stage)
    episode["blobs"][key] = stage
    for boundary in episode["boundaries"]:
        boundary["owners"]["owners"]["coordinator"]["fields"]["_stage_index"]["value"] = {
            "kind": "content-ref", "sha256": key}
    # Expanded mappings and their original snapshot hashes are unchanged.
    validate(episode)


@pytest.mark.parametrize("mutation,message", [
    ("boundary", "T\\+1/T invariant"),
    ("substep", "missing/skipped native substep"),
    ("count", "missing/skipped native substep"),
    ("ack", "applied/target identity"),
    ("time", "state boundary mismatch"),
    ("owner", "owner integrity/alignment"),
    ("blob", "corrupted owner blob"),
])
def test_source_corruption_is_rejected_before_file_creation(tmp_path, episode, mutation, message):
    if mutation == "boundary":
        episode["boundaries"].pop()
    elif mutation == "substep":
        episode["transitions"][0]["interval"]["substeps"].pop()
    elif mutation == "count":
        episode["transitions"][0]["interval"]["native_step_count"] -= 1
    elif mutation == "ack":
        episode["transitions"][0]["interval"]["substeps"][0]["applied"]["target_hash"] = "0" * 64
    elif mutation == "time":
        episode["boundaries"][1]["record"]["simulation_time"] += 0.002
    elif mutation == "owner":
        episode["boundaries"][1]["owners"]["control_step"] += 1
    else:
        key = next(iter(episode["blobs"]))
        episode["blobs"][key] = {"corrupted": True}
    path = tmp_path / "bad.h5"
    with pytest.raises(ValueError, match=message):
        save_streaming(path, episode)
    assert not path.exists() and not path.with_suffix(".h5.tmp").exists()


@pytest.mark.parametrize("mutation,message", [
    ("payload", "logical byte divergence"),
    ("hash", "logical hash"),
    ("projection", "numeric projection"),
    ("truncate", "truncated logical payload"),
    ("append", "extra logical payload bytes"),
    ("dataset", "H5 execution schema"),
])
def test_persisted_corruption_is_rejected(tmp_path, episode, mutation, message):
    path = tmp_path / "episode.h5"
    save_streaming(path, episode)
    with h5py.File(path, "r+") as handle:
        dataset = handle["logical_json_utf8"]
        if mutation == "payload":
            dataset[0] = ord("[")
        elif mutation == "hash":
            handle.attrs["logical_hash"] = "0" * 64
        elif mutation == "projection":
            handle["control_step"][1] = 999
        elif mutation == "truncate":
            dataset.resize((dataset.size - 1,))
        elif mutation == "append":
            dataset.resize((dataset.size + 1,))
            dataset[-1] = ord(" ")
        else:
            del handle["native_step_index"]
    with pytest.raises(ValueError, match=message):
        verify_roundtrip(path, episode, chunk_bytes=4096)


def test_no_overwrite_and_archived_integrity_scope(tmp_path, episode):
    path = tmp_path / "episode.h5"
    save_streaming(path, episode)
    with pytest.raises(FileExistsError):
        save_streaming(path, episode)
    result = verify_payload_integrity(path)
    assert result["payload_integrity"] == "PASS"
    assert result["semantic_validation"] == "NOT_RUN"
    assert result["full_expert_status"] == "UNKNOWN"
    with h5py.File(path, "r+") as handle:
        handle["logical_json_utf8"][0] = ord("[")
    with pytest.raises(ValueError, match="logical hash"):
        verify_payload_integrity(path)


@pytest.mark.parametrize("chunk_bytes", [17, 4096])
def test_streaming_semantic_audit_matches_resident_validator(tmp_path, episode, chunk_bytes):
    path = tmp_path / "semantic.h5"
    save_streaming(path, episode, chunk_bytes=4096)
    profile = {}
    summary = validate_streaming(path, chunk_bytes=chunk_bytes, profile=profile)
    final = episode["boundaries"][-1]
    owners = expand_snapshot(final["owners"], episode["blobs"])
    assert summary["semantic_validation"] == "PASS"
    assert summary["payload_integrity"] == "PASS"
    assert summary["boundaries"] == len(episode["boundaries"])
    assert summary["transitions"] == len(episode["transitions"])
    assert summary["last_task_success"] == final["record"]["is_success"]
    assert summary["last_lifecycle_state"] == owners["owners"]["coordinator"]["fields"].get("lifecycle_state")
    assert summary["last_simulation_time_s"] == final["record"]["simulation_time"]
    assert profile["max_episode_records_retained"] == 1
    assert profile["logical_bytes"] > 0
    assert type(summary["boundaries"]) is int and type(summary["transitions"]) is int


def test_recording_audit_uses_bounded_semantic_summary(tmp_path, episode):
    path = tmp_path / "audit.h5"
    save_streaming(path, episode)
    report = audit(path, semantic=True)
    assert report["integrity"]["semantic_validation"] == "PASS"
    assert report["semantic"]["validation_mode"] == "streaming-semantic-summary-v1"
    assert report["semantic"]["full_expert_status"] == "NOT_ADJUDICATED"
    assert report["qualification"] == "NOT_RUN"
    assert report["replay"] == "NOT_RUN"


def test_incremental_parser_handles_split_utf8_numbers_and_trailing_data(tmp_path):
    expected = {"blobs": {"number": 1.2345e-99}, "boundaries": [{"text": "夹爪"}],
                "transitions": [], "metadata": {"number": -1.234e200}}
    raw = json.dumps(expected, ensure_ascii=False, separators=(",", ":")).encode()
    path = tmp_path / "parser.h5"
    with h5py.File(path, "w") as handle:
        import numpy as np
        d = handle.create_dataset("payload", data=np.frombuffer(raw, dtype=np.uint8))
        assert _JsonCursor(d, 7).episode() == expected
        assert _JsonCursor(d, 1).episode() == expected
        d = handle.create_dataset("extra", data=np.frombuffer(raw + b"[]", dtype=np.uint8))
        with pytest.raises(ValueError, match="extra logical JSON data"):
            _JsonCursor(d, 17).episode()


def test_incremental_loader_retains_semantic_validation_for_tampered_valid_json(tmp_path, episode):
    import numpy as np
    path = tmp_path / "tampered.h5"
    save_streaming(path, episode)
    episode["transitions"][0]["interval"]["native_step_count"] -= 1
    raw = _json_bytes(episode)
    # Recompute a matching hash: semantic validation must still reject it.
    with h5py.File(path, "r+") as handle:
        d = handle["logical_json_utf8"]
        d.resize((len(raw),))
        d[:] = np.frombuffer(raw, dtype=np.uint8)
        handle.attrs["logical_hash"] = digest(episode)
    for reader in (load, load_streaming, validate_streaming):
        with pytest.raises(ValueError, match="missing/skipped native substep"):
            reader(path)


@pytest.mark.parametrize("fields", [None, ("_actions", "events", "lifecycle_state",
                                        "_transition_guard_state", "_close_authorization")])
def test_owner_blob_encoding_preserves_expanded_snapshots_and_owned_copies(tmp_path, episode, fields):
    recorder = ExecutionRecorder(EpisodeMetadata.from_mapping(episode["metadata"]),
                                 episode["recipe"], content_fields=fields)
    for boundary in episode["boundaries"]:
        expanded = expand_snapshot(boundary["owners"], episode["blobs"])
        recorder.boundary(BoundaryRecord.from_mapping(boundary["record"]), expanded,
                          boundary["stage"], boundary["task_metrics_raw"], boundary["native_time"])
        actual = recorder.value["boundaries"][-1]["owners"]
        assert expand_snapshot(actual, recorder.value["blobs"]) == expanded
        # Input mutations must not change the recorded owner or shared blobs.
        expanded["owners"]["coordinator"]["fields"]["events"]["value"].append({"external": True})
        assert expand_snapshot(actual, recorder.value["blobs"]) == expand_snapshot(
            boundary["owners"], episode["blobs"])
    recorder.value["transitions"] = copy.deepcopy(episode["transitions"])
    saved = recorder.freeze(episode["stop_reason"])
    path = tmp_path / "dedup.h5"
    save_streaming(path, saved)
    assert load(path) == load_streaming(path) == saved


def test_detailed_profile_preserves_streaming_validation(tmp_path, episode):
    path = tmp_path / "profile.h5"
    save_streaming(path, episode)
    plain = validate_streaming(path, chunk_bytes=257)
    profile = {}
    measured = validate_streaming(path, chunk_bytes=257, profile=profile)
    assert {k: v for k, v in measured.items() if k != "profile"} == {
        k: v for k, v in plain.items() if k != "profile"}
    detail = profile["detailed"]
    for pass_name in ("first_pass", "second_pass"):
        assert set(detail[pass_name]) == {
            "h5_read_decompress_s", "utf8_buffer_s", "json_decode_s"}
        assert all(0 <= elapsed <= profile["total_s"] for elapsed in detail[pass_name].values())
    for name in ("first_pass_record_encode_hash_s", "boundary_validation_s",
                 "transition_validation_s", "clock_validation_s"):
        assert 0 < detail[name] <= profile["total_s"]
    assert profile["max_episode_records_retained"] == 1
