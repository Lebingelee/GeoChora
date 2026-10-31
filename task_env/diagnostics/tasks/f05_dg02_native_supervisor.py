"""Exclusive lock and process-group resource supervisor for DG02 native probes."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


_PAGE_BYTES = os.sysconf("SC_PAGE_SIZE")


def _mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def _process_group(pgid: int) -> tuple[int, list[int]]:
    rss_total = 0
    pids = []
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            stat = (item / "stat").read_text()
            end = stat.rfind(")")
            fields = stat[end + 2 :].split()
            if int(fields[2]) != pgid:
                continue
            rss = int((item / "statm").read_text().split()[1]) * _PAGE_BYTES
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
        pids.append(int(item.name))
        rss_total += rss
    return rss_total, sorted(pids)


def _terminate(process: subprocess.Popen, *, grace_s: float) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def _wait_group_gone(pgid: int, *, grace_s: float) -> tuple[int, list[int]]:
    started = time.monotonic()
    while True:
        rss, pids = _process_group(pgid)
        if not pids:
            return rss, []
        signal_to_send = signal.SIGTERM if time.monotonic() - started <= grace_s else signal.SIGKILL
        try:
            os.killpg(pgid, signal_to_send)
        except ProcessLookupError:
            pass
        time.sleep(0.1)


def run(*, python: Path, worker: Path, plan: Path, plan_sha256: Path,
        receipt: Path, output_root: Path, lock_path: Path) -> dict:
    python = python.resolve(strict=True)
    worker = worker.resolve(strict=True)
    plan = plan.resolve(strict=True)
    plan_sha256 = plan_sha256.resolve(strict=True)
    receipt = receipt.resolve()
    output_root = output_root.resolve()
    lock_path = lock_path.resolve()
    plan_bytes = plan.read_bytes()
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    if plan_hash != plan_sha256.read_text(encoding="ascii").strip().split()[0]:
        raise ValueError("DG02 native run plan SHA-256 mismatch")
    frozen = json.loads(plan_bytes)
    if frozen.get("schema_version") != "f05-dg02-n0-model-compile-plan-v1":
        raise ValueError("unsupported DG02 native plan schema")
    runtime = frozen["runtime"]
    cwd = Path(runtime["working_directory"]).resolve(strict=True)
    pythonpath = [str(Path(item).resolve(strict=True)) for item in runtime["pythonpath"]]
    if not pythonpath or not all(Path(item).is_dir() for item in pythonpath):
        raise ValueError("frozen N0 Python module paths must all be existing directories")
    provider_src = Path(frozen["input_identity"]["provider_worktree"]).resolve(strict=True) / "src"
    if cwd != provider_src or Path(pythonpath[0]) != provider_src:
        raise ValueError("N0 worker must run from and import the frozen GeoPhys src directory")
    limits = frozen["limits"]
    mem_before = _mem_available()
    if mem_before < int(limits["start_native_mem_available_bytes_min"]):
        raise RuntimeError("MemAvailable is below the frozen native start gate")
    if lock_path.resolve() != Path(limits["shared_native_lock_path"]).resolve():
        raise ValueError("supervisor lock path differs from the frozen run plan")
    output_root.mkdir(parents=True, exist_ok=False)
    stdout_path = output_root / "stdout.txt"
    stderr_path = output_root / "stderr.txt"
    worker_receipt = output_root / "worker_receipt.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_stream = lock_path.open("a+")
    acquired = False
    acquired_utc = None
    process = None
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    max_rss = 0
    max_pids = []
    reason = None
    exit_code = None
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
            acquired_utc = datetime.now(timezone.utc).isoformat()
        except BlockingIOError as exc:
            raise RuntimeError("shared native execution lock is already owned") from exc
        # Recheck resources after exclusive lock acquisition and immediately
        # before starting the native child.
        mem_after_lock = _mem_available()
        if mem_after_lock < int(limits["start_native_mem_available_bytes_min"]):
            raise RuntimeError("MemAvailable fell below the frozen start gate after lock acquisition")
        command = [str(python), str(worker), "--plan", str(plan), "--plan-sha256", str(plan_sha256), "--receipt", str(worker_receipt)]
        env = dict(os.environ)
        env.update({
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(pythonpath),
            "GEOPHYS_TAICHI_BACKEND": "taichi-forge",
            "GEOPHYS_TAICHI_ARCH": "cpu",
            "CUDA_VISIBLE_DEVICES": "",
            "OMP_NUM_THREADS": "4",
            "OPENBLAS_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4",
            "NUMEXPR_NUM_THREADS": "4",
        })
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command, cwd=cwd, stdout=stdout, stderr=stderr, env=env,
                start_new_session=True,
            )
            while process.poll() is None:
                rss, pids = _process_group(process.pid)
                max_rss = max(max_rss, rss)
                max_pids = pids
                mem_now = _mem_available()
                elapsed = time.monotonic() - started
                if rss > int(limits["native_process_group_sampled_rss_bytes_max"]):
                    reason = "native process-group RSS exceeded frozen maximum"
                elif mem_now < int(limits["abort_mem_available_bytes_below"]):
                    reason = "MemAvailable fell below emergency abort threshold"
                elif elapsed > int(limits["per_model_compile_worker_wall_s_max"]):
                    reason = "model compile worker exceeded frozen wall limit"
                if reason:
                    _terminate(process, grace_s=float(limits["term_grace_s"]))
                    break
                time.sleep(float(limits["sample_interval_s"]))
            exit_code = process.wait()
            remaining_rss, remaining_pids = _wait_group_gone(
                process.pid, grace_s=float(limits["term_grace_s"]),
            )
            max_rss = max(max_rss, remaining_rss)
            if remaining_pids:
                reason = reason or "process group remained after worker exit"
                max_pids = remaining_pids
        duration = time.monotonic() - started
        result = {
            "schema_version": "f05-dg02-native-supervisor-receipt-v1",
            "run_id": frozen["run_id"],
            "plan_path": str(plan),
            "plan_sha256": plan_hash,
            "command": command,
            "working_directory": str(cwd),
            "pythonpath": pythonpath,
            "native_starts": 1,
            "physics_steps": 0,
            "exit_code": exit_code,
            "abort_reason": reason,
            "wall_seconds": duration,
            "sample_interval_seconds": float(limits["sample_interval_s"]),
            "max_sampled_process_group_rss_bytes": max_rss,
            "last_observed_process_ids": max_pids,
            "mem_available_before_lock_bytes": mem_before,
            "mem_available_before_start_bytes": mem_after_lock,
            "mem_available_after_exit_bytes": _mem_available(),
            "lock_acquired": acquired,
            "lock_acquired_utc": acquired_utc,
            "lock_released_after_process_group_exit": False,
            "process_group_gone_before_release": False,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "worker_receipt_path": str(worker_receipt),
            "worker_receipt_exists": worker_receipt.is_file(),
            "worker_receipt_sha256": hashlib.sha256(worker_receipt.read_bytes()).hexdigest() if worker_receipt.is_file() else None,
        }
        group_rss, group_pids = _process_group(process.pid)
        result["process_group_gone_before_release"] = not group_pids
        if acquired:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
            acquired = False
        result["lock_released_after_process_group_exit"] = True
        result["max_sampled_process_group_rss_bytes"] = max(max_rss, group_rss)
        result["last_observed_process_ids"] = group_pids or max_pids
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        if exit_code != 0 or reason is not None or group_pids:
            raise RuntimeError(f"native model compile failed: exit={exit_code}, reason={reason}, remaining={group_pids}")
        return result
    finally:
        group_gone = True
        if process is not None:
            if process.poll() is None:
                _terminate(process, grace_s=float(limits["term_grace_s"]))
            _wait_group_gone(process.pid, grace_s=float(limits["term_grace_s"]))
            group_gone = not _process_group(process.pid)[1]
        held_until_cleanup = acquired
        if acquired:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
            acquired = False
        lock_stream.close()
        if not receipt.exists():
            failure = sys.exc_info()[1]
            aborted = {
                "schema_version": "f05-dg02-native-supervisor-receipt-v1",
                "run_id": frozen["run_id"],
                "plan_path": str(plan),
                "plan_sha256": plan_hash,
                "command": command if "command" in locals() else None,
                "native_starts": 1 if process is not None else 0,
                "physics_steps": 0,
                "exit_code": process.poll() if process is not None else None,
                "abort_reason": str(failure) if failure is not None else "supervisor ended before receipt creation",
                "wall_seconds": time.monotonic() - started,
                "sample_interval_seconds": float(limits["sample_interval_s"]),
                "max_sampled_process_group_rss_bytes": max_rss,
                "process_group_gone_before_release": group_gone,
                "lock_acquired": acquired_utc is not None,
                "lock_held_until_process_group_cleanup": held_until_cleanup,
                "lock_released_after_process_group_exit": group_gone,
                "mem_available_before_lock_bytes": mem_before,
                "mem_available_after_exit_bytes": _mem_available(),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "worker_receipt_path": str(worker_receipt),
                "worker_receipt_exists": worker_receipt.is_file(),
            }
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(aborted, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    def interrupt_on_terminate(signum, frame):
        raise KeyboardInterrupt(f"received signal {signum}")

    signal.signal(signal.SIGTERM, interrupt_on_terminate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--lock-path", type=Path, required=True)
    args = parser.parse_args()
    result = run(**vars(args))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
