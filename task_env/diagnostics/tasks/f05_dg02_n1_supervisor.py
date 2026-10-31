"""Exclusive native supervisor for frozen DG02 source-consumer probes."""

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


PAGE_BYTES = os.sysconf("SC_PAGE_SIZE")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable unavailable")


def _group(pgid: int) -> tuple[int, list[int]]:
    total, pids = 0, []
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            stat = (item / "stat").read_text()
            fields = stat[stat.rfind(")") + 2 :].split()
            if int(fields[2]) != pgid:
                continue
            total += int((item / "statm").read_text().split()[1]) * PAGE_BYTES
            pids.append(int(item.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
    return total, sorted(pids)


def _counter(path: Path, *, reserve: int) -> tuple[int, int, bool]:
    try:
        data = json.loads(path.read_text())
        attempted = int(data["attempted_physics_steps"])
        completed = int(data["completed_physics_steps"])
        if not 0 <= completed <= attempted <= reserve:
            return reserve, min(reserve, completed), False
        return attempted, completed, True
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return 0, 0, False


def _terminate(proc: subprocess.Popen, grace: float) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def run(plan_path: Path, sidecar: Path, receipt_path: Path) -> dict:
    plan_path = plan_path.resolve(strict=True)
    sidecar = sidecar.resolve(strict=True)
    plan_raw = plan_path.read_bytes()
    plan_hash = hashlib.sha256(plan_raw).hexdigest()
    if plan_hash != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("N1 plan hash mismatch")
    plan = json.loads(plan_raw)
    supported_plan_schemas = {
        "f05-dg02-n1-public-consumer-plan-v1",
        "f05-dg02-equality-coupling-plan-v1",
        "f05-dg02-core-n2-plan-v1",
    }
    if plan.get("schema_version") not in supported_plan_schemas:
        raise ValueError("unsupported DG02 source-consumer native plan schema")
    inputs = {row["path"]: row["sha256"] for row in plan["code"]["tracked_inputs"]}
    worker = Path(
        plan.get("output", {}).get(
            "worker_script",
            Path(__file__).with_name("f05_dg02_n1_public_consumer_probe.py"),
        )
    ).resolve(strict=True)
    if inputs.get(str(worker)) != _sha(worker) or inputs.get(str(Path(__file__).resolve())) != _sha(Path(__file__).resolve()):
        raise ValueError("N1 worker/supervisor code changed after plan freeze")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"N1 code hash mismatch: {path}")
    for key in (
        "usd_stage",
        "delivery_manifest",
        "recipe",
        "source_inventory",
        "source_audit",
        "mjcf_source",
        "parent_model_compile_plan",
        "parent_model_compile_receipt",
        "parent_model_compile_worker_receipt",
        "diagnostic_variants_manifest",
        "equality_positive_variant_stage",
        "equality_negative_variant_stage",
        "equality_removed_variant_stage",
        "coupling_active_variant_stage",
        "coupling_inactive_variant_stage",
        "coupling_variants_manifest",
    ):
        if key not in plan["source"]:
            continue
        row = plan["source"][key]
        if _sha(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
            raise ValueError(f"N1 source hash mismatch: {key}")
    identity = plan["input_identity"]
    provider, core = Path(identity["provider_worktree"]).resolve(strict=True), Path(identity["core_worktree"]).resolve(strict=True)
    if subprocess.run(["git", "-C", str(provider), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() != identity["provider_input_head"]:
        raise ValueError("provider checkout HEAD changed before N1")
    if subprocess.run(["git", "-C", str(core), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() != identity["core_input_head"]:
        raise ValueError("Core checkout HEAD changed before N1")

    limits, runtime = plan["limits"], plan["runtime"]
    if _mem_available() < int(limits["start_native_mem_available_bytes_min"]):
        raise RuntimeError("N1 native memory start gate failed")
    lock_path = Path(limits["shared_native_lock_path"]).resolve()
    output_dir = Path(plan["output"]["run_dir"]).resolve()
    supervisor_receipt = Path(receipt_path).resolve()
    lock = lock_path.open("a+")
    acquired, process = False, None
    start = time.monotonic()
    max_rss, peak_pids, reason = 0, [], None
    exit_code = None
    native_start = 0
    mem_before, mem_start = _mem_available(), None
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise RuntimeError("shared native execution lock is occupied") from exc
        mem_start = _mem_available()
        if mem_start < int(limits["start_native_mem_available_bytes_min"]):
            raise RuntimeError("N1 native memory fell below start gate after lock acquisition")
        python = Path(runtime["python"]).resolve(strict=True)
        if _sha(python) != runtime["python_sha256"]:
            raise ValueError("N1 Python executable changed after freeze")
        for raw_path, expected in runtime["file_sha256"].items():
            if _sha(Path(raw_path).resolve(strict=True)) != expected:
                raise ValueError(f"N1 runtime file hash mismatch: {raw_path}")
        cwd = Path(runtime["working_directory"]).resolve(strict=True)
        pythonpath = [str(Path(item).resolve(strict=True)) for item in runtime["pythonpath"]]
        runtime_environment_sha256 = hashlib.sha256(json.dumps(
            runtime, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        expected_runtime_environment_sha256 = plan.get("runtime_environment_sha256")
        if (expected_runtime_environment_sha256 is not None
                and expected_runtime_environment_sha256 != runtime_environment_sha256):
            raise ValueError("frozen runtime environment identity differs from the plan")
        output_dir.mkdir(parents=True, exist_ok=False)
        counter_path = output_dir / "step_counter.json"
        counter_path.write_text(json.dumps({"schema_version": "f05-dg02-step-counter-v1", "run_id": plan["run_id"], "attempted_physics_steps": 0, "completed_physics_steps": 0, "physics_dt_s": 0.002}, sort_keys=True) + "\n")
        stdout_path, stderr_path = output_dir / "stdout.txt", output_dir / "stderr.txt"
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
            "F05_NATIVE_RUN_ID": plan["run_id"],
            "F05_NATIVE_RUN_PLAN_SHA256": plan_hash,
            "F05_NATIVE_RUNTIME_ENVIRONMENT_SHA256": runtime_environment_sha256,
        })
        command = [str(python), str(worker), "--plan", str(plan_path), "--plan-sha256", str(sidecar), "--receipt", str(Path(plan["output"]["worker_receipt"])), "--counter", str(counter_path)]
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            native_start = 1
            while process.poll() is None:
                rss, pids = _group(process.pid)
                max_rss, peak_pids = max(max_rss, rss), pids
                attempted, _, counter_ok = _counter(counter_path, reserve=int(limits["physics_steps_reserved"]))
                mem = _mem_available()
                if rss > int(limits["native_process_group_sampled_rss_bytes_max"]):
                    reason = "process-group RSS exceeded N1 limit"
                elif mem < int(limits["abort_mem_available_bytes_below"]):
                    reason = "MemAvailable below emergency threshold"
                elif time.monotonic() - start > int(limits["worker_wall_s_max"]):
                    reason = "N1 worker exceeded wall limit"
                elif attempted > int(limits["physics_steps_reserved"]):
                    reason = "worker exceeded frozen physics-step reservation"
                elif (stdout_path.stat().st_size + stderr_path.stat().st_size) > int(limits["native_log_bytes_max"]):
                    reason = "native logs exceeded frozen byte limit"
                elif not counter_ok and attempted >= int(limits["physics_steps_reserved"]):
                    reason = "step counter malformed after reservation may have been consumed"
                if reason:
                    _terminate(process, float(limits["term_grace_s"]))
                    break
                time.sleep(float(limits["sample_interval_s"]))
            exit_code = process.wait()
            # Confirm the entire process group is gone before releasing the lock.
            pgid = process.pid
            gone_started = time.monotonic()
            while True:
                rss, pids = _group(pgid)
                if not pids:
                    break
                sig = signal.SIGTERM if time.monotonic() - gone_started <= float(limits["term_grace_s"]) else signal.SIGKILL
                try:
                    os.killpg(pgid, sig)
                except ProcessLookupError:
                    pass
                time.sleep(0.1)
            max_rss = max(max_rss, rss)
        attempted, completed, counter_ok = _counter(counter_path, reserve=int(limits["physics_steps_reserved"]))
        if not counter_ok and native_start:
            attempted = int(limits["physics_steps_reserved"])
        worker_receipt = Path(plan["output"]["worker_receipt"])
        receipt = {
            "schema_version": "f05-dg02-n1-supervisor-receipt-v1",
            "run_id": plan["run_id"],
            "plan_path": str(plan_path),
            "plan_sha256": plan_hash,
            "runtime_environment_sha256": runtime_environment_sha256,
            "command": command if "command" in locals() else None,
            "native_starts": native_start,
            "physics_steps_attempted": attempted,
            "physics_steps_completed": completed,
            "exit_code": exit_code,
            "abort_reason": reason,
            "wall_seconds": time.monotonic() - start,
            "max_sampled_process_group_rss_bytes": max_rss,
            "peak_process_ids": peak_pids,
            "mem_available_before_lock_bytes": mem_before,
            "mem_available_before_start_bytes": mem_start,
            "mem_available_after_exit_bytes": _mem_available(),
            "lock_acquired": acquired,
            "process_group_gone_before_release": process is None or not _group(process.pid)[1],
            "lock_released_after_process_group_exit": False,
            "step_counter_path": str(counter_path),
            "step_counter_sha256": _sha(counter_path),
            "worker_receipt_path": str(worker_receipt),
            "worker_receipt_exists": worker_receipt.is_file(),
            "worker_receipt_sha256": _sha(worker_receipt) if worker_receipt.is_file() else None,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
        if acquired:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            acquired = False
        receipt["lock_released_after_process_group_exit"] = receipt["process_group_gone_before_release"]
        supervisor_receipt.parent.mkdir(parents=True, exist_ok=True)
        supervisor_receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        if exit_code != 0 or reason or not receipt["process_group_gone_before_release"]:
            raise RuntimeError(f"N1 probe failed: exit={exit_code}, reason={reason}")
        return receipt
    finally:
        if process is not None and process.poll() is None:
            _terminate(process, float(limits["term_grace_s"]))
        if process is not None:
            while _group(process.pid)[1]:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                time.sleep(0.1)
        if acquired:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    run(args.plan, args.plan_sha256, args.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
