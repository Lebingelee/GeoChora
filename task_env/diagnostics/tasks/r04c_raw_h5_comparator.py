"""Independent raw H5/NPZ comparator for the bounded R04c camera recording.

This module intentionally has no TaskEnv or provider imports. It compares the
pre-write public Env witness against Generic H5 datasets and sidecars.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

import numpy as np


CAMERA_IDS = (
    "d04-fixed-square-peg-calibration-v1",
    "d04-panda-hand-mounted-camera-v1",
)
ENGINE_PREFIXES = ("task_env", "geophys", "GeoPhys", "mujoco", "taichi", "OpenGL", "glfw")


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL {path.name}:{line_no}") from error
    return rows


def _h5_text(dataset) -> str:
    value = dataset[()]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return bytes(value).decode("utf-8")
    return str(value)


def _forbidden_modules(modules) -> list[str]:
    return sorted(name for name in modules if any(
        name == prefix or name.startswith(prefix + ".") for prefix in ENGINE_PREFIXES
    ))


def _compare_episode(*, h5_path: Path, episode_index: int, witness_rows, capture_rows, npz, h5py) -> dict[str, object]:
    selected = [row for row in witness_rows if row.get("episode_index") == episode_index]
    if len(selected) != 13 or [row.get("boundary_index") for row in selected] != list(range(13)):
        raise ValueError(f"episode {episode_index} requires exactly ordered public boundaries 0..12")
    first_identity = selected[0]["state_boundary_identity"]
    materialization_id = first_identity["provider_materialization_id"]
    episode_id = first_identity["episode_id"]
    reset_sample_id = first_identity["reset_sample_id"]

    with h5py.File(h5_path, "r") as root:
        attrs = root.attrs
        if (str(attrs.get("schema_id", "")), str(attrs.get("schema_version", "")),
                int(attrs.get("transition_count", -1)), int(attrs.get("observation_count", -1)),
                bool(attrs.get("episode_complete", False)), str(attrs.get("stop_reason", ""))) != (
                "task-env-h5", "v3", 12, 13, True, "external_stop"):
            raise ValueError("H5 is not a finalized Generic v3 external-stop T=12/T+1=13 episode")

        metadata = root["meta"]
        required_meta = (
            "camera_observations_v1_json", "camera_recording_binding_v1_json",
            "structured_controls_v1_json", "episode_outcome_v1_json", "env_meta",
        )
        if any(name not in metadata for name in required_meta):
            raise ValueError("H5 lacks required public camera/recording/control/outcome metadata")
        camera_boundaries = json.loads(_h5_text(metadata["camera_observations_v1_json"]))
        binding = json.loads(_h5_text(metadata["camera_recording_binding_v1_json"]))
        controls = json.loads(_h5_text(metadata["structured_controls_v1_json"]))
        outcome = json.loads(_h5_text(metadata["episode_outcome_v1_json"]))
        import yaml
        env_meta = yaml.safe_load(_h5_text(metadata["env_meta"]))
        if len(camera_boundaries) != 13 or len(binding.get("boundaries", ())) != 13:
            raise ValueError("H5 camera sidecar and recording binding must contain 13 boundaries")
        if len(controls) != 12 or len(root["action"]) == 0:
            raise ValueError("H5 must contain 12 ordered structured controls and action leaves")
        if (outcome.get("episode_id") != episode_id or outcome.get("final_boundary") != 12
                or outcome.get("end_reason") != "external_stop" or outcome.get("terminated")
                or not outcome.get("truncated") or outcome.get("task_success") is True
                or outcome.get("solution_completed") is not None):
            raise ValueError("H5 final EpisodeOutcome differs from the pre-write episode identity/stop")
        if not np.array_equal(np.asarray(root["terminated"][...]), np.zeros(12, dtype=np.bool_)):
            raise ValueError("external Stop must not rewrite returned transition terminated flags")
        if not np.array_equal(np.asarray(root["truncated"][...]), np.zeros(12, dtype=np.bool_)):
            raise ValueError("external Stop must not rewrite returned transition truncated flags")

        expected_order = (
            "d04-fixed-square-peg-calibration-v1", "d04-panda-hand-mounted-camera-v1",
        )
        camera_ids = tuple(camera.get("camera_id") for camera in camera_boundaries[0].get("captures", ()))
        if camera_ids != expected_order:
            raise ValueError("H5 camera sidecar does not preserve the canonical camera order")

        checked_pixels = 0
        checked_state_arrays = 0
        checked_state_scalars = 0
        for boundary_index, witness in enumerate(selected):
            identity = witness["state_boundary_identity"]
            if identity["control_step"] != boundary_index:
                raise ValueError("pre-write StateBoundaryIdentity control_step is out of order")
            if (identity["episode_id"], identity["reset_sample_id"], identity["provider_materialization_id"]
                    ) != (episode_id, reset_sample_id, materialization_id):
                raise ValueError("pre-write boundary identity changed episode/reset/materialization")
            anchor = binding["boundaries"][boundary_index]
            if (_canonical(anchor.get("state_boundary_identity")) != _canonical(identity)
                    or anchor.get("boundary_index") != boundary_index
                    or anchor.get("state_boundary_id") != witness["state_boundary_id"]):
                raise ValueError("recording-binding state identity differs from the independent public witness")
            identity_digest = hashlib.sha256(_canonical(identity).encode("utf-8")).digest()
            if witness["state_boundary_id"] != "state-boundary-" + identity_digest.hex():
                raise ValueError("public state boundary ID does not recompute from its canonical mapping")
            stored_digest = np.asarray(root["obs/state/boundary_identity_sha256"][boundary_index])
            if stored_digest.dtype != np.uint8 or stored_digest.shape != (32,) or bytes(stored_digest) != identity_digest:
                raise ValueError("stored state-boundary digest differs from pre-write public identity")

            clock = witness["state_sample_clock"]
            if (_canonical(anchor.get("state_sample_clock")) != _canonical(clock)
                    or clock.get("sample_index") != boundary_index
                    or clock.get("clock_domain") != "evaluation_boundary"):
                raise ValueError("H5 boundary clock differs from the pre-write public evaluation clock")
            if _canonical(camera_boundaries[boundary_index]) != _canonical(witness["camera_observation_v1"]):
                raise ValueError("H5 camera sidecar is not the same public boundary metadata captured before write")

            camera_meta_captures = camera_boundaries[boundary_index].get("captures", ())
            if tuple(item.get("camera_id") for item in camera_meta_captures) != expected_order:
                raise ValueError("public camera metadata order changed within the stored episode")
            capture_indices = witness.get("capture_rows", ())
            if len(capture_indices) != 2:
                raise ValueError("pre-write public boundary does not point to exactly two capture records")
            raw_captures = [capture_rows[int(index)] for index in capture_indices]
            raw_by_id = {capture.get("camera_id"): capture for capture in raw_captures}
            if tuple(raw_by_id) != expected_order:
                raise ValueError("pre-write renderer records do not preserve the canonical camera order")
            for metadata_capture in camera_meta_captures:
                raw_capture = raw_by_id[metadata_capture["camera_id"]]
                for field in ("capture_identity", "calibration", "label_map", "mask_sha256"):
                    if _canonical(metadata_capture.get(field)) != _canonical(raw_capture.get(field)):
                        raise ValueError(
                            f"H5 public camera metadata {field} differs from its same-boundary capture record"
                        )

            for group_dot, expected_scalar in witness.get("observation_scalars", {}).items():
                group, leaf = group_dot.split(".", 1)
                dataset_path = f"obs/{group}/{leaf.replace('.', '/') }"
                if dataset_path not in root:
                    raise ValueError(f"pre-write scalar observation leaf is absent from H5: {dataset_path}")
                actual_scalar = np.asarray(root[dataset_path][boundary_index]).item()
                if isinstance(expected_scalar, float) and not np.isfinite(expected_scalar):
                    raise ValueError(f"pre-write public scalar is non-finite at {dataset_path}")
                if actual_scalar != expected_scalar:
                    raise ValueError(f"stored scalar state differs from pre-write public witness: {dataset_path}")
                checked_state_scalars += 1

            for group_dot, key in witness.get("observation_array_keys", {}).items():
                group, leaf = group_dot.split(".", 1)
                dataset_path = f"obs/{group}/{leaf.replace('.', '/') }"
                if dataset_path not in root:
                    raise ValueError(f"pre-write observation leaf is absent from H5: {dataset_path}")
                expected = np.asarray(npz[key])
                actual = np.asarray(root[dataset_path][boundary_index])
                if actual.dtype != expected.dtype or not np.array_equal(actual, expected):
                    raise ValueError(f"stored state/privileged value differs from pre-write public witness: {dataset_path}")
                checked_state_arrays += 1

            for modality, h5_modality in (("rgb", "rgb"), ("depth", "depth"), ("entity_mask", "entity_mask")):
                for camera_id in expected_order:
                    key = witness["camera_array_keys"][modality][camera_id]
                    expected = np.asarray(npz[key])
                    dataset_path = f"obs/{h5_modality}/{camera_id}"
                    if dataset_path not in root:
                        raise ValueError(f"required camera H5 dataset missing: {dataset_path}")
                    actual = np.asarray(root[dataset_path][boundary_index])
                    if modality == "rgb":
                        if expected.dtype != np.float32 or expected.ndim != 3 or expected.shape[-1] != 3:
                            raise ValueError("pre-write RGB witness must be float32 HWC")
                        quantized = np.rint(expected * np.float32(255.0)).astype(np.uint8).transpose(2, 0, 1)
                        expected = np.ascontiguousarray(quantized)
                    if actual.dtype != expected.dtype or actual.shape != expected.shape or not np.array_equal(actual, expected):
                        raise ValueError(f"stored {modality} pixel/value mismatch at {camera_id} boundary {boundary_index}")
                    checked_pixels += int(actual.size)

            if boundary_index > 0:
                transition_index = boundary_index - 1
                transition = witness.get("control_transition")
                if not isinstance(transition, dict) or _canonical(controls[transition_index].get("request")) != _canonical(witness.get("request")):
                    raise ValueError("structured H5 request is missing or out of order against the public witness")
                writers = controls[transition_index].get("writer_controls", ())
                if len(writers) != 1:
                    raise ValueError("R04c Position H5 transition must contain one existing writer")
                writer = writers[0]
                expected_canonical = dict(transition.get("canonical_action", {}))
                expected_canonical["position_target_v1"] = transition.get("target")
                expected_canonical["position_target_identity_hash"] = transition.get("target_identity_hash")
                if (_canonical(writer.get("canonical_action")) != _canonical(expected_canonical)
                        or writer.get("components") != witness.get("action_components")):
                    raise ValueError("H5 canonical Action/Target/Ack differs from the pre-write public transition")
                target = transition.get("target", {})
                target_envelope = writer.get("controller_target", {})
                if (target_envelope.get("identity_hash") != transition.get("canonical_target_identity_hash")
                        or _canonical(target_envelope.get("payload")) != _canonical(target.get("target"))):
                    raise ValueError("H5 nested canonical Position target differs from pre-write Target witness")
                applied = transition.get("applied", {})
                applied_envelope = writer.get("applied_control", {})
                if (_canonical(applied_envelope.get("payload")) != _canonical(applied)
                        or applied_envelope.get("target_hash") != transition.get("applied_target_hash")
                        or applied_envelope.get("target_hash") != transition.get("canonical_target_identity_hash")):
                    raise ValueError("H5 applied-control acknowledgement differs from pre-write Target/Ack witness")
                action_key = witness.get("action_array_key")
                expected_action = np.asarray(npz[action_key])
                for component_index, component in enumerate(witness["action_components"]):
                    dataset_path = f"action/{component}"
                    actual = np.asarray(root[dataset_path][transition_index]).reshape(-1)
                    if actual.dtype != expected_action.dtype or not np.array_equal(actual, expected_action[component_index:component_index + 1]):
                        raise ValueError(f"H5 numeric action component differs from pre-write request: {component}")
        if int(binding.get("transition_count", -1)) != 12 or int(binding.get("observation_count", -1)) != 13:
            raise ValueError("H5 recording binding does not preserve the T/T+1 boundary counts")
        if (binding.get("episode_id"), binding.get("reset_sample_id"), binding.get("scene_identity_hash"),
                binding.get("task_artifact_identity_hash")) != (
                episode_id, reset_sample_id, first_identity["scene_identity_hash"],
                selected[0]["capture_rows"] and selected[0]["camera_observation_v1"]["captures"][0]["capture_identity"]["task_artifact_hash"]):
            raise ValueError("H5 recording binding episode/reset/scene/artifact differs from pre-write witness")
        action_order = env_meta.get("action_schema", {}).get("order", ())
        if tuple(action_order) != tuple(selected[1]["action_components"]):
            raise ValueError("H5 env_meta action component order differs from the public Position schema")

    return {
        "episode_index": episode_index,
        "h5_path": str(h5_path),
        "h5_sha256": _sha256(h5_path),
        "episode_id": episode_id,
        "reset_sample_id": reset_sample_id,
        "provider_materialization_id": materialization_id,
        "transition_count": 12,
        "observation_count": 13,
        "camera_ids": list(CAMERA_IDS),
        "checked_public_boundary_camera_values": checked_pixels,
        "checked_state_arrays": checked_state_arrays,
        "checked_state_scalars": checked_state_scalars,
        "status": "RAW_H5_PREWRITE_WITNESS_PASS",
    }


def verify(*, worker_output: Path, receipt_path: Path | None = None,
           h5_override: Path | None = None, episode_index: int | None = None) -> dict[str, object]:
    started = time.monotonic()
    modules_before = sorted(sys.modules)
    import h5py

    worker_output = worker_output.resolve()
    receipt_path = receipt_path or worker_output / "r04c_worker_receipt.json"
    worker = _read_json(receipt_path)
    if worker.get("status") != "R04C_NATIVE_RECORDING_COMPLETE_PENDING_OFFLINE_READBACK":
        raise ValueError("worker receipt is incomplete or has already failed the R04c native recording gate")
    if worker.get("primary_error") is not None or worker.get("cleanup_errors"):
        raise ValueError("worker receipt contains a primary or cleanup error")
    entries = worker.get("episode_recordings")
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError("R04c raw comparator requires exactly two finalized episode records")
    if h5_override is not None:
        if episode_index not in (1, 2):
            raise ValueError("--episode-index must be 1 or 2 when using an H5 override")
        selected = [(episode_index, h5_override.resolve())]
    else:
        if episode_index is not None:
            raise ValueError("--episode-index requires --h5-override")
        selected = [(index, Path(entry["path"]).resolve()) for index, entry in enumerate(entries, 1)]
    if any(entry.get("status") != "FINALIZED"
           or entry.get("finalizer_result", {}).get("transition_count") != 12
           or entry.get("finalizer_result", {}).get("observation_count") != 13
           for entry in entries):
        raise ValueError("worker receipt contains an unfinalized or partial H5 entry")
    witness_path = Path(worker.get("public_witness_rows", ""))
    if not witness_path.is_absolute():
        witness_path = worker_output / witness_path
    if not witness_path.is_file():
        raise FileNotFoundError("pre-write public H5 witness JSONL is absent")
    witness_rows = _read_jsonl(witness_path)
    if len(witness_rows) != 26:
        raise ValueError("two episode recordings require exactly 26 pre-write public witness rows")
    capture_rows = _read_jsonl(worker_output / "capture_rows.jsonl")
    if len(capture_rows) != 53:
        raise ValueError("raw comparator requires the 52 public and one isolation capture rows")
    capture_rows_path = worker_output / "capture_rows.jsonl"
    expected_capture_hash = worker.get("evidence", {}).get("capture_rows_sha256")
    if expected_capture_hash not in (None, _sha256(capture_rows_path)):
        raise ValueError("capture metadata rows hash differs from the closed worker receipt")
    arrays_path = worker_output / "raw_camera_arrays.npz"
    if not arrays_path.is_file():
        raise FileNotFoundError("raw public camera/state witness NPZ is absent")
    if worker.get("evidence", {}).get("raw_camera_arrays_sha256") not in (None, _sha256(arrays_path)):
        raise ValueError("raw public witness NPZ hash differs from the closed worker receipt")
    witness_sha = worker.get("evidence", {}).get("public_h5_witness_rows_sha256")
    if witness_sha not in (None, _sha256(witness_path)):
        raise ValueError("pre-write witness JSONL hash differs from the closed worker receipt")

    episodes = []
    with np.load(arrays_path, allow_pickle=False) as npz:
        for index, path in selected:
            episodes.append(_compare_episode(
                h5_path=path, episode_index=index, witness_rows=witness_rows,
                capture_rows=capture_rows, npz=npz, h5py=h5py,
            ))
    modules_after = sorted(sys.modules)
    forbidden = _forbidden_modules(modules_after)
    if forbidden:
        raise RuntimeError(f"raw comparator imported a TaskEnv/provider/engine module: {forbidden}")
    return {
        "schema_version": "r04c-raw-h5-comparator-v1",
        "status": "R04C_RAW_H5_PREWRITE_WITNESS_PASS",
        "episodes": episodes,
        "worker_receipt": str(receipt_path),
        "public_witness_rows": str(witness_path),
        "raw_arrays": str(arrays_path),
        "modules_before": modules_before,
        "modules_after": modules_after,
        "forbidden_imports": forbidden,
        "elapsed_s": time.monotonic() - started,
    }


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-output", type=Path, required=True)
    parser.add_argument("--worker-receipt", type=Path)
    parser.add_argument("--h5-override", type=Path)
    parser.add_argument("--episode-index", type=int)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = verify(
            worker_output=args.worker_output, receipt_path=args.worker_receipt,
            h5_override=args.h5_override, episode_index=args.episode_index,
        )
    except BaseException as error:
        receipt = {
            "schema_version": "r04c-raw-h5-comparator-v1",
            "status": "R04C_RAW_H5_PREWRITE_WITNESS_FAIL",
            "error": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()},
            "modules_after": sorted(sys.modules),
            "forbidden_imports": _forbidden_modules(sorted(sys.modules)),
        }
        _write_json(args.receipt_out, receipt)
        print(json.dumps({"status": receipt["status"], "error": receipt["error"]["message"]}, sort_keys=True))
        return 1
    _write_json(args.receipt_out, receipt)
    print(json.dumps({"status": receipt["status"], "episodes": len(receipt["episodes"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
