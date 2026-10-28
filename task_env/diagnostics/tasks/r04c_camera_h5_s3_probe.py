"""Run the bounded R04c same-Env camera-to-Generic-H5 v3 S3 episode."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

from task_env.diagnostics.tasks import r04b_public_camera_s2_probe as camera_probe


INPUT_HEAD = "cb6313f117f70678ee7c821e8344d8c595dea5ad"
FROZEN_HEAD_ENV = "R04C_FROZEN_HEAD"
WORKER_RECEIPT = "r04c_worker_receipt.json"
PENDING_READBACK = "R04C_NATIVE_RECORDING_COMPLETE_PENDING_OFFLINE_READBACK"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _source_workspace_receipt(output: Path) -> dict[str, object] | None:
    source_workspace = output / "source_workspace_public"
    if not source_workspace.is_dir():
        return None
    files = []
    for path in sorted(item for item in source_workspace.rglob("*") if item.is_file()):
        files.append({
            "path": path.relative_to(source_workspace).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    receipt = {
        "schema_version": "r04c-source-workspace-inventory-v1",
        "disposition": "raw workspace removed after preserving per-file hashes",
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    _write_json(output / "source_workspace_manifest.json", receipt)
    shutil.rmtree(source_workspace)
    return receipt


def run_s3(output: str | Path) -> dict[str, object]:
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("R04c native worker output must be fresh; existing evidence is preserved")
    output.mkdir(parents=True, exist_ok=True)
    started = __import__("time").monotonic()
    worker_receipt = None
    primary_error = None
    cleanup_errors = []
    source_workspace = None

    try:
        native = camera_probe.run_s2(
            output,
            recording_root=output / "episodes",
            input_head=INPUT_HEAD,
            frozen_head_env=FROZEN_HEAD_ENV,
        )
        worker_receipt = native
        if native.get("status") != "R04B_PUBLIC_ENV_TWO_CAMERA_S2_PASS":
            raise RuntimeError("shared public camera worker did not complete its frozen R04b path")
        recordings = native.get("r04c_recordings")
        if (not isinstance(recordings, list) or len(recordings) != 2
                or any(not isinstance(item, dict) or item.get("status") != "FINALIZED"
                       for item in recordings)):
            raise RuntimeError("R04c requires exactly two finalized public Generic H5 episodes")
        if any((item.get("finalizer_result") or {}).get("transition_count") != 12
               or (item.get("finalizer_result") or {}).get("observation_count") != 13
               for item in recordings):
            raise RuntimeError("R04c H5 finalizer did not return the required T=12/T+1=13 counts")
    except BaseException as error:
        primary_error = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        worker_path = output / "worker_receipt.json"
        if worker_path.is_file():
            try:
                worker_receipt = json.loads(worker_path.read_text(encoding="utf-8"))
            except BaseException as read_error:
                cleanup_errors.append({"type": type(read_error).__name__, "message": str(read_error)})
    finally:
        try:
            source_workspace = _source_workspace_receipt(output)
        except BaseException as error:
            cleanup_errors.append({
                "type": type(error).__name__, "message": f"source workspace inventory/cleanup: {error}",
                "traceback": traceback.format_exc(),
            })

    passed_native = primary_error is None and not cleanup_errors and worker_receipt is not None
    frozen_head = os.environ.get(FROZEN_HEAD_ENV)
    worktree = Path(__file__).resolve().parents[3]
    receipt = {
        "schema_version": "r04c-camera-h5-s3-native-worker-v1",
        "status": PENDING_READBACK if passed_native else "R04C_NATIVE_RECORDING_FAIL",
        "input_head": INPUT_HEAD,
        "frozen_head": frozen_head,
        "branch": subprocess.run(
            ["git", "branch", "--show-current"], cwd=worktree,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        ).stdout.strip(),
        "runtime": None if worker_receipt is None else worker_receipt.get("runtime"),
        "worker_status": None if worker_receipt is None else worker_receipt.get("status"),
        "native_counters": None if worker_receipt is None else worker_receipt.get("counters"),
        "env_close_calls": None if worker_receipt is None else worker_receipt.get("env_close_calls"),
        "env_close_successes": None if worker_receipt is None else worker_receipt.get("env_close_successes"),
        "closed_before_receipt": None if worker_receipt is None else worker_receipt.get("closed_before_receipt"),
        "cleanup_error": None if worker_receipt is None else worker_receipt.get("cleanup_error"),
        "episode_recordings": [] if worker_receipt is None else worker_receipt.get("r04c_recordings", []),
        "public_witness_rows": None if worker_receipt is None else worker_receipt.get("public_h5_witness_rows"),
        "evidence": None if worker_receipt is None else worker_receipt.get("evidence"),
        "source_workspace_inventory": source_workspace,
        "worker_receipt_path": str(output / "worker_receipt.json"),
        "primary_error": primary_error,
        "cleanup_errors": cleanup_errors,
        "elapsed_s": __import__("time").monotonic() - started,
        "offline_readback": "NOT_RUN_BY_NATIVE_WORKER",
        "qualification_granted": False,
    }
    _write_json(output / WORKER_RECEIPT, receipt)
    if not passed_native:
        raise RuntimeError(f"R04c native recording worker failed: {primary_error or cleanup_errors}")
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = run_s3(args.output)
    except BaseException as error:
        print(json.dumps({"status": "FAIL", "error": f"{type(error).__name__}: {error}"}, sort_keys=True))
        return 1
    print(json.dumps({
        "status": receipt["status"],
        "worker_receipt": str(args.output / WORKER_RECEIPT),
        "episodes": len(receipt["episode_recordings"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
