"""Lock-owning resource supervisor for one bounded R04b/R04c native worker.

This script uses only the Python standard library and launches exactly one
worker process group. The exclusive advisory lock is held through the complete
child-group lifetime, including any TERM/KILL cleanup.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback


RAM_START_MIN = 4 * 1024**3
RAM_STOP_MIN = 768 * 1024**2
GPU_START_MIN = 2 * 1024**3
GPU_STOP_MIN = 256 * 1024**2
RSS_STOP_MAX = 4 * 1024**3
SAMPLE_SECONDS = 2.0
PROCESS_WALL_LIMIT = 300.0


def _mem_available_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _gpu_rows() -> list[dict[str, object]] | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,uuid,memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    rows = []
    for line in result.stdout.splitlines():
        values = [value.strip() for value in line.split(",")]
        if len(values) != 5:
            return None
        try:
            rows.append({
                "index": int(values[0]), "name": values[1], "uuid": values[2],
                "memory_free_bytes": int(values[3]) * 1024**2,
                "memory_total_bytes": int(values[4]) * 1024**2,
            })
        except ValueError:
            return None
    return rows or None


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _group_rss_bytes(pgid: int) -> int:
    total = 0
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            stat = (proc / "stat").read_text()
            right = stat.rfind(")")
            fields = stat[right + 2:].split()
            if int(fields[2]) != pgid:
                continue
            for line in (proc / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) * 1024
                    break
        except (OSError, ValueError, IndexError):
            continue
    return total


def _append_jsonl(path: Path, record) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, record) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _stop_group(process: subprocess.Popen, pgid: int) -> str:
    signal_name = "SIGTERM"
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return "already_exited"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _process_group_exists(pgid):
            process.poll()
            return signal_name
        time.sleep(0.1)
    signal_name = "SIGKILL"
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    while _process_group_exists(pgid):
        time.sleep(0.1)
    process.poll()
    return signal_name


def supervise(*, lock_path: Path, output: Path, worker_output: Path, worktree: Path,
              python: Path, worker_script: Path, wait_lock_s: float) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("supervisor output directory must be fresh")
    worker_output.mkdir(parents=True, exist_ok=False)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output / "launch_receipt.json"
    lock_wait_path = output / "lock_wait.jsonl"
    sample_path = output / "resource_samples.jsonl"
    command_log = output / "native_worker.log"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    lock_start = time.monotonic()
    lock_acquired = False
    process = None
    stop_reason = None
    termination_signal = None
    samples = 0
    low_mem_streak = 0
    resources_start = {"memory_available_bytes": None, "gpus": None}
    worker_exit = None
    native_processes_launched = 0
    status = "NOT_RUN_RESOURCE_PENDING"

    def finish(record):
        _write_json(receipt_path, record)
        return record

    try:
        while time.monotonic() - lock_start < wait_lock_s:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_acquired = True
                break
            except BlockingIOError:
                _append_jsonl(lock_wait_path, {
                    "event": "native_lock_busy", "waited_s": time.monotonic() - lock_start,
                    "lock_path": str(lock_path), "native_processes_launched": 0,
                })
                print("WAIT_LOCK shared native lock busy; no native budget consumed", flush=True)
                time.sleep(SAMPLE_SECONDS)
        if not lock_acquired:
            stop_reason = "shared_native_lock_wait_timeout"
            status = "NOT_RUN_RESOURCE_PENDING"
            return finish({
                "schema_version": "r04b-native-supervisor-v1", "status": status,
                "lock_acquired": False, "lock_wait_s": time.monotonic() - lock_start,
                "native_processes_launched": 0, "stop_reason": stop_reason,
            })

        memory = _mem_available_bytes()
        gpus = _gpu_rows()
        resources_start = {"memory_available_bytes": memory, "gpus": gpus}
        selected_gpu = None if not gpus else gpus[0]
        if memory is None or gpus is None:
            stop_reason = "resource_probe_unavailable"
            return finish({
                "schema_version": "r04b-native-supervisor-v1", "status": status,
                "lock_acquired": True, "lock_wait_s": time.monotonic() - lock_start,
                "resources_start": resources_start, "native_processes_launched": 0,
                "stop_reason": stop_reason,
            })
        if memory < RAM_START_MIN:
            stop_reason = "system_memavailable_below_4_gib"
            return finish({
                "schema_version": "r04b-native-supervisor-v1", "status": status,
                "lock_acquired": True, "lock_wait_s": time.monotonic() - lock_start,
                "resources_start": resources_start, "native_processes_launched": 0,
                "stop_reason": stop_reason,
            })
        if selected_gpu["memory_free_bytes"] < GPU_START_MIN:
            stop_reason = "selected_gpu_free_below_2_gib"
            return finish({
                "schema_version": "r04b-native-supervisor-v1", "status": status,
                "lock_acquired": True, "lock_wait_s": time.monotonic() - lock_start,
                "resources_start": resources_start, "native_processes_launched": 0,
                "stop_reason": stop_reason,
            })

        frozen_head = subprocess.check_output(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True,
        ).strip()
        frozen_branch = subprocess.check_output(
            ["git", "-C", str(worktree), "branch", "--show-current"], text=True,
        ).strip()
        dirty_paths = subprocess.check_output(
            ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"], text=True,
        ).strip()
        submodule_status = subprocess.check_output(
            ["git", "-C", str(worktree), "submodule", "status"], text=True,
        ).splitlines()
        expected_submodules = {
            "a53a8cfed7c9d6464274b5c96fca601271dc4ee4": "GeoPhys",
            "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7": "asset/external/mujoco_menagerie",
        }
        pins_match = len(submodule_status) == 2 and all(
            any(line.startswith(f" {revision} ") and path in line for line in submodule_status)
            for revision, path in expected_submodules.items()
        )
        if (frozen_branch != "codex/phase-ii-01-camera" or dirty_paths or not pins_match):
            stop_reason = "camera_worktree_not_clean_at_native_freeze"
            return finish({
                "schema_version": "r04b-native-supervisor-v1", "status": status,
                "lock_acquired": True, "lock_wait_s": time.monotonic() - lock_start,
                "resources_start": resources_start, "frozen_head": frozen_head,
                "frozen_branch": frozen_branch, "dirty_paths": dirty_paths,
                "submodule_status": submodule_status,
                "native_processes_launched": 0, "stop_reason": stop_reason,
            })

        environment = dict(os.environ)
        environment.update({
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join((str(worktree), str(worktree / "GeoPhys" / "src"))),
            "MUJOCO_GL": "egl",
            "PYOPENGL_PLATFORM": "egl",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "NUMBA_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "TAICHI_NUM_THREADS": "1",
            "R04B_FROZEN_HEAD": frozen_head,
            "R04C_FROZEN_HEAD": frozen_head,
        })
        command = [str(python), str(worker_script), "--output", str(worker_output)]
        launch_start = time.monotonic()
        with command_log.open("wb") as stream:
            process = subprocess.Popen(
                command, cwd=worktree, env=environment, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
            )
            native_processes_launched = 1
            pgid = process.pid
            while True:
                elapsed = time.monotonic() - launch_start
                memory_now = _mem_available_bytes()
                gpu_now = _gpu_rows()
                rss_now = _group_rss_bytes(pgid)
                samples += 1
                low_mem_streak = low_mem_streak + 1 if memory_now is not None and memory_now < RAM_STOP_MIN else 0
                sample = {
                    "elapsed_s": elapsed,
                    "process_group_id": pgid,
                    "process_group_rss_bytes": rss_now,
                    "system_memavailable_bytes": memory_now,
                    "gpu_free_bytes": None if gpu_now is None else [item["memory_free_bytes"] for item in gpu_now],
                    "system_mem_low_consecutive_samples": low_mem_streak,
                }
                _append_jsonl(sample_path, sample)
                if rss_now > RSS_STOP_MAX:
                    stop_reason = "process_group_rss_above_4_gib"
                elif low_mem_streak >= 3:
                    stop_reason = "system_memavailable_below_768_mib_three_samples"
                elif gpu_now is None:
                    stop_reason = "gpu_resource_probe_failed_during_run"
                elif min(item["memory_free_bytes"] for item in gpu_now) < GPU_STOP_MIN:
                    stop_reason = "gpu_free_below_256_mib"
                elif elapsed > PROCESS_WALL_LIMIT:
                    stop_reason = "native_worker_wall_limit_300s"
                if stop_reason is not None:
                    termination_signal = _stop_group(process, pgid)
                    worker_exit = process.wait(timeout=2)
                    break
                worker_exit = process.poll()
                if worker_exit is not None and not _process_group_exists(pgid):
                    break
                time.sleep(SAMPLE_SECONDS)
            if process.poll() is None:
                worker_exit = process.wait(timeout=2)
            # The lock is kept until all descendants in the launched process group have exited.
            while _process_group_exists(pgid):
                time.sleep(0.1)
        if stop_reason is None and worker_exit == 0:
            status = "NATIVE_WORKER_EXITED_ZERO"
        else:
            status = "NATIVE_WORKER_FAILED_OR_ABORTED"
        return finish({
            "schema_version": "r04b-native-supervisor-v1", "status": status,
            "lock_acquired": True, "lock_path": str(lock_path),
            "lock_wait_s": launch_start - lock_start,
            "resources_start": resources_start, "selected_gpu_monitor_target": selected_gpu,
            "command": command, "cwd": str(worktree),
            "environment": {key: environment[key] for key in (
                "PYTHONDONTWRITEBYTECODE", "PYTHONPATH", "MUJOCO_GL", "PYOPENGL_PLATFORM",
                "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
            "TAICHI_NUM_THREADS",
            "R04B_FROZEN_HEAD",
            "R04C_FROZEN_HEAD",
            )},
            "frozen_head": frozen_head,
            "frozen_branch": frozen_branch,
            "submodule_status": submodule_status,
            "native_processes_launched": native_processes_launched,
            "native_worker_pid": process.pid,
            "native_worker_process_group_id": process.pid,
            "native_worker_exit_code": worker_exit,
            "native_worker_elapsed_s": time.monotonic() - launch_start,
            "resource_sample_count": samples,
            "termination_signal": termination_signal,
            "stop_reason": stop_reason,
            "log_path": str(command_log),
            "worker_output": str(worker_output),
        })
    finally:
        try:
            if lock_acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        # Always leave a readable receipt, including lock/resource deferrals.
        if not receipt_path.exists():
            fallback = {
                "schema_version": "r04b-native-supervisor-v1", "status": status,
                "lock_acquired": lock_acquired, "lock_path": str(lock_path),
                "lock_wait_s": time.monotonic() - lock_start,
                "resources_start": resources_start,
                "native_processes_launched": native_processes_launched,
                "native_worker_exit_code": worker_exit,
                "resource_sample_count": samples,
                "termination_signal": termination_signal,
                "stop_reason": stop_reason,
                "log_path": str(command_log) if command_log.exists() else None,
                "worker_output": str(worker_output),
            }
            _write_json(receipt_path, fallback)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-output", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--worker-script", type=Path, required=True)
    parser.add_argument("--wait-lock-s", type=float, default=900.0)
    args = parser.parse_args(argv)
    try:
        receipt = supervise(
            lock_path=args.lock.resolve(), output=args.output.resolve(),
            worker_output=args.worker_output.resolve(), worktree=args.worktree.resolve(),
            python=args.python.resolve(), worker_script=args.worker_script.resolve(),
            wait_lock_s=args.wait_lock_s,
        )
        print(json.dumps({"status": receipt["status"], "native_processes_launched": receipt.get("native_processes_launched", 0)}, sort_keys=True), flush=True)
        return 0 if receipt["status"] == "NATIVE_WORKER_EXITED_ZERO" else 75
    except BaseException as error:
        print(json.dumps({"status": "SUPERVISOR_ERROR", "error": f"{type(error).__name__}: {error}",
                          "traceback": traceback.format_exc()}, sort_keys=True), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
