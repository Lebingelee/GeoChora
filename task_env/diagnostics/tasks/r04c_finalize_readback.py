"""Gate the bounded R04c PASS label on supervisor, readback, tamper and size receipts."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import traceback


PASS = "R04C_BOUNDED_CAMERA_H5_S3_PASS_PENDING_SOL_REVIEW"
EVIDENCE_CAP_BYTES = 256 * 1024 * 1024
EXPECTED_PUBLIC_VALUES_PER_EPISODE = 13 * 2 * (3 * 241 * 321 + 2 * 241 * 321)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_size(root: Path) -> tuple[int, int]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def _verify_native_inputs(*, output_root: Path, worker_path: Path, supervisor_path: Path,
                          semantic_path: Path, raw_path: Path, matrix_path: Path,
                          lock_path: Path) -> dict[str, object]:
    worker = _read_json(worker_path)
    supervisor = _read_json(supervisor_path)
    semantic = _read_json(semantic_path)
    raw = _read_json(raw_path)
    matrix = _read_json(matrix_path)

    if (supervisor.get("status") != "NATIVE_WORKER_EXITED_ZERO"
            or supervisor.get("lock_acquired") is not True
            or supervisor.get("native_processes_launched") != 1
            or supervisor.get("native_worker_exit_code") != 0
            or supervisor.get("termination_signal") is not None
            or supervisor.get("stop_reason") is not None
            or supervisor.get("frozen_branch") != "codex/phase-ii-01-camera"):
        raise ValueError("supervisor receipt did not record one clean worker exit under the native gate")
    if worker.get("status") != "R04C_NATIVE_RECORDING_COMPLETE_PENDING_OFFLINE_READBACK":
        raise ValueError("native worker receipt is not a complete R04c run awaiting readback")
    if (worker.get("primary_error") is not None or worker.get("cleanup_errors")
            or worker.get("cleanup_error") is not None):
        raise ValueError("native worker receipt contains a primary or cleanup error")
    if (worker.get("frozen_head") != supervisor.get("frozen_head")
            or worker.get("branch") != supervisor.get("frozen_branch")
            or worker.get("runtime", {}).get("core_revision") != supervisor.get("frozen_head")):
        raise ValueError("native worker and supervisor input freeze identities disagree")
    counters = worker.get("native_counters", {})
    exact_counters = {
        "reset_attempts": 2, "outer_steps": 24,
        "accepted_physics_substeps": 120, "clock_inferred_substeps": 120,
        "runtime_boundary_step_calls": 24, "runtime_boundary_step_successes": 24,
        "controller_compute_calls": 24, "public_boundary_captures": 52,
        "renderer_capture_calls": 53, "isolation_capture_calls": 1,
        "renderer_render_calls": 159, "renderer_render_successes": 159,
        "native_renderer_close_calls": 4, "native_renderer_close_successes": 4,
    }
    for key, expected in exact_counters.items():
        if counters.get(key) != expected:
            raise ValueError(f"native successful route count mismatch: {key}={counters.get(key)!r}, expected {expected}")
    if abs(float(counters.get("simulation_seconds", -1.0)) - 0.24) > 2e-9:
        raise ValueError("native simulation clock is not the bounded 0.24 seconds")
    if worker.get("env_close_calls") != 1 or worker.get("env_close_successes") != 1:
        raise ValueError("native Env close was not observed exactly once successfully")
    if worker.get("closed_before_receipt") is not True:
        raise ValueError("native Environment was not closed before its worker receipt")
    if worker.get("qualification_granted") is not False:
        raise ValueError("R04c evidence must not grant formal Qualification")

    episodes = worker.get("episode_recordings")
    if not isinstance(episodes, list) or len(episodes) != 2:
        raise ValueError("native worker did not finalize exactly two Generic H5 episodes")
    h5_hashes = []
    h5_bytes = 0
    for index, episode in enumerate(episodes, 1):
        result = episode.get("finalizer_result") or {}
        path = Path(episode.get("path", ""))
        if (episode.get("status") != "FINALIZED" or result.get("schema_id") != "task-env-h5"
                or result.get("schema_version") != "v3" or result.get("transition_count") != 12
                or result.get("observation_count") != 13 or not path.is_file()):
            raise ValueError(f"episode {index} is not one finalized Generic H5 v3 T=12/T+1=13 file")
        digest = _sha256(path)
        if episode.get("file_sha256") != digest:
            raise ValueError(f"episode {index} H5 hash differs from the closed worker receipt")
        h5_hashes.append(digest)
        h5_bytes += path.stat().st_size

    if semantic.get("status") != "R04C_PUBLIC_H5_SEMANTIC_READBACK_PASS" or semantic.get("engine_modules_imported"):
        raise ValueError("independent public TaskEnv semantic reader did not pass without engine imports")
    if raw.get("status") != "R04C_RAW_H5_PREWRITE_WITNESS_PASS" or raw.get("forbidden_imports"):
        raise ValueError("independent raw comparator did not pass without TaskEnv/provider/engine imports")
    if len(semantic.get("episodes", ())) != 2 or len(raw.get("episodes", ())) != 2:
        raise ValueError("both independent readback processes must verify both native H5 episodes")
    for index in range(2):
        public = semantic["episodes"][index]
        pixel = raw["episodes"][index]
        if (public.get("episode_id") != pixel.get("episode_id")
                or public.get("transition_count") != 12 or public.get("observation_count") != 13
                or pixel.get("h5_sha256") != h5_hashes[index]
                or pixel.get("checked_public_boundary_camera_values") != EXPECTED_PUBLIC_VALUES_PER_EPISODE
                or pixel.get("status") != "RAW_H5_PREWRITE_WITNESS_PASS"):
            raise ValueError(f"independent semantic/raw readers disagree on native episode {index + 1}")

    cases = matrix.get("cases")
    if (matrix.get("status") != "R04C_NATIVE_H5_TAMPER_MATRIX_PASS"
            or not isinstance(cases, list) or len(cases) < 21
            or any(case.get("rejected") is not True for case in cases)):
        raise ValueError("native-derived H5 tamper matrix is incomplete or includes an accepted mutation")

    resources = supervisor.get("resources_start", {})
    gpus = resources.get("gpus") or []
    if (resources.get("memory_available_bytes", 0) < 4 * 1024**3 or not gpus
            or gpus[0].get("memory_free_bytes", 0) < 2 * 1024**3):
        raise ValueError("supervisor startup RAM/VRAM admission thresholds were not met")
    sample_path = Path(supervisor_path).parent / "resource_samples.jsonl"
    samples = [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not samples or max(int(row["process_group_rss_bytes"]) for row in samples) > 4 * 1024**3:
        raise ValueError("native supervisor has no valid samples or crossed the RSS stop gate")
    if (supervisor.get("native_worker_elapsed_s", 1e9) > 300
            or supervisor.get("resource_sample_count") != len(samples)):
        raise ValueError("native worker exceeded its wall budget or has a mismatched resource sample count")

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_released = True
        fcntl.flock(fd, fcntl.LOCK_UN)
    except BlockingIOError:
        lock_released = False
    finally:
        os.close(fd)
    if not lock_released:
        raise RuntimeError("shared native lock is still held during independent readback finalization")

    file_count, evidence_bytes = _tree_size(output_root)
    return {
        "status": PASS,
        "supervisor_status": supervisor["status"],
        "supervisor_receipt": str(supervisor_path),
        "worker_receipt": str(worker_path),
        "semantic_reader_receipt": str(semantic_path),
        "raw_comparator_receipt": str(raw_path),
        "native_negative_matrix": str(matrix_path),
        "native_processes_launched": supervisor["native_processes_launched"],
        "lock_acquired_and_released": lock_released,
        "frozen_head": supervisor["frozen_head"],
        "frozen_branch": supervisor["frozen_branch"],
        "episode_h5_sha256": h5_hashes,
        "episode_h5_bytes": h5_bytes,
        "native_negative_cases": len(cases),
        "resource_sample_count": len(samples),
        "maximum_sampled_process_group_rss_bytes": max(int(row["process_group_rss_bytes"]) for row in samples),
        "evidence_file_count_before_final_receipt": file_count,
        "evidence_bytes_before_final_receipt": evidence_bytes,
        "evidence_cap_bytes": EVIDENCE_CAP_BYTES,
        "qualification_granted": False,
        "review_status": "PENDING_SOL_REVIEW",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--worker-receipt", type=Path, required=True)
    parser.add_argument("--supervisor-receipt", type=Path, required=True)
    parser.add_argument("--semantic-receipt", type=Path, required=True)
    parser.add_argument("--raw-receipt", type=Path, required=True)
    parser.add_argument("--negative-matrix", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        receipt = _verify_native_inputs(
            output_root=args.output_root.resolve(), worker_path=args.worker_receipt.resolve(),
            supervisor_path=args.supervisor_receipt.resolve(), semantic_path=args.semantic_receipt.resolve(),
            raw_path=args.raw_receipt.resolve(), matrix_path=args.negative_matrix.resolve(),
            lock_path=args.lock.resolve(),
        )
        receipt["elapsed_s"] = time.monotonic() - started
        serialized_size = len(json.dumps(receipt, sort_keys=True, allow_nan=False).encode("utf-8")) + 512
        receipt["estimated_final_evidence_bytes"] = receipt["evidence_bytes_before_final_receipt"] + serialized_size
        if receipt["estimated_final_evidence_bytes"] > receipt["evidence_cap_bytes"]:
            raise ValueError("R04c cumulative evidence exceeds its 256 MiB cap including final receipt reserve")
    except BaseException as error:
        receipt = {
            "schema_version": "r04c-final-readback-gate-v1",
            "status": "R04C_FINAL_GATE_FAIL",
            "error": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()},
            "qualification_granted": False,
        }
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.receipt_out.with_name(args.receipt_out.name + ".tmp")
        temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, args.receipt_out)
        print(json.dumps({"status": receipt["status"], "error": receipt["error"]["message"]}, sort_keys=True))
        return 1
    receipt["schema_version"] = "r04c-final-readback-gate-v1"
    temporary = args.receipt_out.with_name(args.receipt_out.name + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, args.receipt_out)
    print(json.dumps({"status": receipt["status"], "native_negative_cases": receipt["native_negative_cases"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
