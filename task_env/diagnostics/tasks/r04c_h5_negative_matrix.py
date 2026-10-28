"""Run a bounded semantic/raw refusal matrix against one finalized R04c H5 copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import h5py
import numpy as np


CAMERA_ID = "d04-fixed-square-peg-calibration-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rewrite_meta(root, name: str, value) -> None:
    path = f"meta/{name}"
    del root[path]
    root["meta"].create_dataset(
        name, data=np.asarray(json.dumps(value, sort_keys=True), dtype=h5py.string_dtype("utf-8")),
    )


def _sidecar_edit(name: str, edit):
    def apply(root):
        value = json.loads(root[f"meta/{name}"][()].decode("utf-8"))
        edit(value)
        _rewrite_meta(root, name, value)
    return apply


def _mutations():
    def missing_sidecar(root):
        del root["meta/camera_observation_contract_v1_json"]

    def unknown_schema(root):
        root.attrs["schema_version"] = "v2"

    def transition_count(root):
        root.attrs["transition_count"] = 11

    def rgb_shape(root):
        path = f"obs/rgb/{CAMERA_ID}"
        del root[path]
        root.create_dataset(path, data=np.zeros((13, 3, 240, 321), dtype=np.uint8))

    def rgb_dtype(root):
        path = f"obs/rgb/{CAMERA_ID}"
        del root[path]
        root.create_dataset(path, data=np.zeros((13, 3, 241, 321), dtype=np.uint16))

    def bad_mask_value(root):
        root[f"obs/entity_mask/{CAMERA_ID}"][0, 0, 0] = np.uint32(999)

    def bad_mask_digest(value):
        value[0]["captures"][0]["mask_sha256"] = "0" * 64

    def bad_rgb_pixel(root):
        dataset = root[f"obs/rgb/{CAMERA_ID}"]
        dataset[0, 0, 0, 0] = np.uint8((int(dataset[0, 0, 0, 0]) + 1) % 256)

    def bad_depth_pixel(root):
        dataset = root[f"obs/depth/{CAMERA_ID}"]
        dataset[0, 0, 0] = np.float32(dataset[0, 0, 0]) + np.float32(1.0)

    def state_digest(root):
        root["obs/state/boundary_identity_sha256"][0, 0] ^= np.uint8(1)

    def bad_clock(value):
        value["boundaries"][0]["state_sample_clock"]["simulation_time_s"] += 0.001

    def bad_materialization(value):
        value[0]["captures"][0]["capture_identity"]["state_boundary"]["provider_materialization_id"] = "wrong-materialization"

    def bad_episode(value):
        value[0]["captures"][0]["capture_identity"]["state_boundary"]["episode_id"] = "wrong-episode"

    def bad_reset(value):
        value[0]["captures"][0]["capture_identity"]["state_boundary"]["reset_sample_id"] = "reset-" + "0" * 64

    def bad_calibration(value):
        value[0]["captures"][0]["calibration"]["camera"]["width"] = 320

    def bad_label_map(value):
        value[0]["captures"][0]["label_map"]["labels"][0]["label"] = 99

    def bad_target_ack(value):
        value[0]["writer_controls"][0]["applied_control"]["target_hash"] = "0" * 64

    def reverse_controls(value):
        value[0], value[1] = value[1], value[0]

    def bad_outcome(root):
        outcome = json.loads(root["meta/episode_outcome_v1_json"][()].decode("utf-8"))
        outcome["end_reason"] = "internal_stop"
        _rewrite_meta(root, "episode_outcome_v1_json", outcome)
        root.attrs["stop_reason"] = "internal_stop"

    def incomplete(root):
        root.attrs["episode_complete"] = False

    def bad_action(root):
        name = next(iter(root["action"].keys()))
        dataset = root[f"action/{name}"]
        dataset[0, 0] = np.float32(dataset[0, 0]) + np.float32(0.01)

    return [
        ("missing-camera-sidecar", missing_sidecar, "semantic"),
        ("unknown-version", unknown_schema, "semantic"),
        ("transition-count", transition_count, "semantic"),
        ("rgb-shape", rgb_shape, "semantic"),
        ("rgb-dtype", rgb_dtype, "semantic"),
        ("mask-unknown-label", bad_mask_value, "semantic"),
        ("mask-digest", _sidecar_edit("camera_observations_v1_json", bad_mask_digest), "semantic"),
        ("rgb-pixel-change", bad_rgb_pixel, "raw"),
        ("finite-depth-pixel-change", bad_depth_pixel, "raw"),
        ("state-boundary-digest", state_digest, "semantic"),
        ("sample-clock", _sidecar_edit("camera_recording_binding_v1_json", bad_clock), "semantic"),
        ("provider-materialization", _sidecar_edit("camera_observations_v1_json", bad_materialization), "semantic"),
        ("episode-identity", _sidecar_edit("camera_observations_v1_json", bad_episode), "semantic"),
        ("reset-identity", _sidecar_edit("camera_observations_v1_json", bad_reset), "semantic"),
        ("camera-calibration", _sidecar_edit("camera_observations_v1_json", bad_calibration), "semantic"),
        ("canonical-label-map", _sidecar_edit("camera_observations_v1_json", bad_label_map), "semantic"),
        ("target-ack", _sidecar_edit("structured_controls_v1_json", bad_target_ack), "semantic"),
        ("control-order", _sidecar_edit("structured_controls_v1_json", reverse_controls), "semantic"),
        ("end-reason", bad_outcome, "semantic"),
        ("unfinalized", incomplete, "semantic"),
        ("numeric-action", bad_action, "semantic"),
    ]


def _run_reader(command, receipt_path: Path, expected_status: str) -> tuple[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        command, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if result.returncode != 1 or receipt.get("status") != expected_status:
        raise AssertionError(
            f"expected reader refusal status={expected_status}, exit=1; got exit={result.returncode}, "
            f"receipt={receipt.get('status')}, stdout={result.stdout}, stderr={result.stderr}"
        )
    return receipt.get("error", {}).get("message", ""), hashlib.sha256(Path(command[3]).read_bytes()).hexdigest()


def run(*, worker_output: Path, matrix_output: Path) -> dict[str, object]:
    started = time.monotonic()
    worker_output = worker_output.resolve()
    worker = json.loads((worker_output / "r04c_worker_receipt.json").read_text(encoding="utf-8"))
    if worker.get("status") != "R04C_NATIVE_RECORDING_COMPLETE_PENDING_OFFLINE_READBACK":
        raise ValueError("negative matrix requires a worker receipt awaiting independent readback")
    entries = worker.get("episode_recordings", ())
    if not entries or entries[0].get("status") != "FINALIZED":
        raise ValueError("negative matrix requires a finalized first Generic H5 v3 episode")
    original_h5 = Path(entries[0]["path"]).resolve()
    original_hash = _sha256(original_h5)
    working_h5 = worker_output / "tamper_working.h5"
    semantic_receipt = worker_output / "tamper_semantic_receipt.json"
    raw_receipt = worker_output / "tamper_raw_receipt.json"
    semantic_script = Path(__file__).with_name("r04c_public_h5_semantic_reader.py").resolve()
    raw_script = Path(__file__).with_name("r04c_raw_h5_comparator.py").resolve()
    results = []

    for case_id, mutation, kind in _mutations():
        shutil.copyfile(original_h5, working_h5)
        with h5py.File(working_h5, "r+") as root:
            mutation(root)
        if kind == "semantic":
            command = [sys.executable, "-I", "-B", str(semantic_script), "--h5", str(working_h5),
                       "--receipt-out", str(semantic_receipt)]
            error, reader_hash = _run_reader(
                command, semantic_receipt, "R04C_PUBLIC_H5_SEMANTIC_READBACK_FAIL",
            )
        else:
            command = [sys.executable, "-I", "-B", str(raw_script), "--worker-output", str(worker_output),
                       "--h5-override", str(working_h5), "--episode-index", "1",
                       "--receipt-out", str(raw_receipt)]
            error, reader_hash = _run_reader(
                command, raw_receipt, "R04C_RAW_H5_PREWRITE_WITNESS_FAIL",
            )
        results.append({
            "case_id": case_id, "target_reader": kind, "rejected": True,
            "return_code": 1, "error": error, "reader_script_sha256": reader_hash,
            "working_h5_sha256": _sha256(working_h5),
        })

    partial_path = worker_output / "tamper_partial_worker_receipt.json"
    partial = json.loads((worker_output / "r04c_worker_receipt.json").read_text(encoding="utf-8"))
    partial["episode_recordings"][0]["status"] = "RECORDING"
    partial["episode_recordings"][0]["finalizer_result"] = None
    partial_path.write_text(json.dumps(partial, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = [sys.executable, "-I", "-B", str(raw_script), "--worker-output", str(worker_output),
               "--worker-receipt", str(partial_path), "--receipt-out", str(raw_receipt)]
    error, reader_hash = _run_reader(command, raw_receipt, "R04C_RAW_H5_PREWRITE_WITNESS_FAIL")
    results.append({
        "case_id": "partial-receipt-masquerading-complete", "target_reader": "raw",
        "rejected": True, "return_code": 1, "error": error,
        "reader_script_sha256": reader_hash,
        "working_h5_sha256": _sha256(working_h5),
    })
    if _sha256(original_h5) != original_hash:
        raise RuntimeError("native/source H5 original changed during negative audits")
    receipt = {
        "schema_version": "r04c-native-h5-tamper-matrix-v1",
        "status": "R04C_NATIVE_H5_TAMPER_MATRIX_PASS",
        "source_h5": str(original_h5),
        "source_h5_sha256": original_hash,
        "working_h5": str(working_h5),
        "working_copy_count": 1,
        "cases": results,
        "case_count": len(results),
        "elapsed_s": time.monotonic() - started,
        "qualification_granted": False,
    }
    matrix_output.parent.mkdir(parents=True, exist_ok=True)
    temporary = matrix_output.with_name(matrix_output.name + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, matrix_output)
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-output", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = run(worker_output=args.worker_output, matrix_output=args.receipt_out)
    except BaseException as error:
        receipt = {
            "schema_version": "r04c-native-h5-tamper-matrix-v1",
            "status": "R04C_NATIVE_H5_TAMPER_MATRIX_FAIL",
            "error": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()},
            "qualification_granted": False,
        }
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "error": receipt["error"]["message"]}, sort_keys=True))
        return 1
    print(json.dumps({"status": receipt["status"], "cases": receipt["case_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
