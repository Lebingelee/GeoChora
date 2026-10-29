"""Exclusive-lock and resource supervisor for the bounded F01 Isaac process."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
ATTEMPT_DIR = REPO / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f01_002"
LOCK_PATH = REPO / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock"
ENV_PYTHON = REPO / "workspace/environments/isaacsim-6.2.0/bin/python"
MAX_LOCK_WAIT_S = 1200.0
MAX_PROCESS_WALL_S = 900.0
MAX_NETWORK_RX_BYTES = 2 * 1024**3
MAX_ASSET_CACHE_GROWTH_BYTES = 2 * 1024**3
MAX_EVIDENCE_BYTES = 512 * 1024**2
MAX_LOG_BYTES = 256 * 1024**2
MAX_WORKER_RSS_BYTES = 10 * 1024**3
MIN_SYSTEM_AVAILABLE_BYTES = 768 * 1024**2
MIN_START_AVAILABLE_BYTES = 6 * 1024**3
MIN_START_GPU_FREE_MIB = 5 * 1024
MIN_RUNTIME_GPU_FREE_MIB = 256


def _json_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _json_replace(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    payload = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with temp.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _mem_available_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _gpu_free_mib() -> int | None:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        values = [int(line.strip()) for line in completed.stdout.splitlines() if line.strip()]
        return values[0] if values else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _gpu_process_memory_mib(pid: int) -> int | None:
    """Return nvidia-smi's process-scoped VRAM usage for one worker PID."""
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        for line in completed.stdout.splitlines():
            columns = [column.strip() for column in line.split(",", 1)]
            if len(columns) != 2 or int(columns[0]) != pid:
                continue
            memory_text = columns[1].split()[0]
            if memory_text.upper() in {"N/A", "[N/A]"}:
                return None
            return int(memory_text)
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None
    return None


def _network_rx_bytes() -> int | None:
    try:
        total = 0
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            if ":" not in line:
                continue
            counters = line.split(":", 1)[1].split()
            if counters:
                total += int(counters[0])
        return total
    except (OSError, ValueError, IndexError):
        return None


def _proc_group_rss_bytes(pgid: int) -> int:
    page_bytes = os.sysconf("SC_PAGE_SIZE")
    total = 0
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            tail = stat[stat.rfind(")") + 2:].split()
            if int(tail[2]) != pgid:
                continue
            resident_pages = int((entry / "statm").read_text().split()[1])
            total += resident_pages * page_bytes
        except (OSError, ValueError, IndexError):
            continue
    return total


def _proc_group_alive(pgid: int) -> bool:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            tail = stat[stat.rfind(")") + 2:].split()
            if int(tail[2]) == pgid and tail[0] != "Z":
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def _cache_bytes(path: Path) -> tuple[int | None, int]:
    """Return the sum of regular-file sizes and a count without following links."""
    if not path.exists():
        return 0, 0
    total = 0
    count = 0
    try:
        for root, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
            for name in files:
                candidate = Path(root) / name
                try:
                    if candidate.is_file() and not candidate.is_symlink():
                        total += candidate.stat().st_size
                        count += 1
                except OSError:
                    continue
    except OSError:
        return None, count
    return total, count


def _sample(pgid: int) -> dict[str, Any]:
    return {
        "monotonic": time.monotonic(),
        "mem_available_bytes": _mem_available_bytes(),
        "worker_group_rss_bytes": _proc_group_rss_bytes(pgid),
        "gpu0_free_mib": _gpu_free_mib(),
        "gpu_process_pid": pgid,
        "gpu_process_memory_mib": _gpu_process_memory_mib(pgid),
        "host_network_rx_bytes": _network_rx_bytes(),
    }


def _terminate_group(proc: subprocess.Popen[Any], grace_s: float = 10.0) -> dict[str, Any]:
    receipt: dict[str, Any] = {"term_sent": False, "kill_sent": False, "term_grace_s": grace_s}
    if proc.poll() is not None and not _proc_group_alive(proc.pid):
        receipt["already_exited"] = True
        return receipt
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        receipt["term_sent"] = True
    except ProcessLookupError:
        return receipt
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if proc.poll() is not None and not _proc_group_alive(proc.pid):
            break
        time.sleep(0.2)
    if proc.poll() is None or _proc_group_alive(proc.pid):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            receipt["kill_sent"] = True
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        receipt["wait_after_kill_timed_out"] = True
    return receipt


def monitor_process(proc: subprocess.Popen[Any], log_path: Path, *, started: float,
                    timeout_s: float = MAX_PROCESS_WALL_S, interval_s: float = 2.0,
                    sample_fn: Callable[[int], dict[str, Any]] = _sample,
                    network_baseline: int | None = None,
                    network_budget_bytes: int = MAX_NETWORK_RX_BYTES) -> dict[str, Any]:
    """Monitor one process group; injectable sampler supports bounded S1 tests."""
    samples: list[dict[str, Any]] = []
    low_ram = high_rss = low_gpu = 0
    stop_reason = None
    while proc.poll() is None or _proc_group_alive(proc.pid):
        now = time.monotonic()
        if now - started > timeout_s:
            stop_reason = "process_wall_timeout"
            break
        try:
            sample = sample_fn(proc.pid)
        except Exception as exc:
            stop_reason = f"resource_sampler_error:{type(exc).__name__}:{exc}"
            break
        samples.append(sample)
        mem = sample.get("mem_available_bytes")
        rss = sample.get("worker_group_rss_bytes")
        gpu = sample.get("gpu0_free_mib")
        low_ram = low_ram + 1 if isinstance(mem, int) and mem < MIN_SYSTEM_AVAILABLE_BYTES else 0
        high_rss = high_rss + 1 if isinstance(rss, int) and rss > MAX_WORKER_RSS_BYTES else 0
        low_gpu = low_gpu + 1 if isinstance(gpu, int) and gpu < MIN_RUNTIME_GPU_FREE_MIB else 0
        if low_ram >= 3:
            stop_reason = "system_available_ram_below_768_mib_three_samples"
            break
        if high_rss >= 3:
            stop_reason = "worker_group_rss_above_10_gib_three_samples"
            break
        if low_gpu >= 3:
            stop_reason = "gpu_free_below_256_mib_three_samples"
            break
        rx = sample.get("host_network_rx_bytes")
        if isinstance(rx, int) and network_baseline is not None and rx - network_baseline > network_budget_bytes:
            stop_reason = "host_network_rx_budget_exceeded"
            break
        try:
            if log_path.stat().st_size > MAX_LOG_BYTES:
                stop_reason = "native_log_budget_exceeded"
                break
        except FileNotFoundError:
            pass
        time.sleep(interval_s)
    termination = _terminate_group(proc) if stop_reason else {"term_sent": False, "kill_sent": False}
    code = proc.poll()
    if code is None:
        try:
            code = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            code = None
    return {
        "exit_code": code,
        "stop_reason": stop_reason,
        "wall_seconds": time.monotonic() - started,
        "samples": samples,
        "termination": termination,
        "gpu_process_pid": proc.pid,
        "max_sampled_gpu_process_memory_mib": max(
            (s.get("gpu_process_memory_mib") for s in samples
             if isinstance(s.get("gpu_process_memory_mib"), int)),
            default=None,
        ),
        "max_sampled_worker_group_rss_bytes": max((s.get("worker_group_rss_bytes", 0) or 0 for s in samples), default=0),
        "min_sampled_mem_available_bytes": min((s.get("mem_available_bytes") for s in samples if isinstance(s.get("mem_available_bytes"), int)), default=None),
        "min_sampled_gpu0_free_mib": min((s.get("gpu0_free_mib") for s in samples if isinstance(s.get("gpu0_free_mib"), int)), default=None),
        "host_network_rx_delta_bytes": max((s.get("host_network_rx_bytes", network_baseline or 0) - (network_baseline or 0) for s in samples if isinstance(s.get("host_network_rx_bytes"), int)), default=0),
    }


def _read_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "f01-native-start-ledger-v1", "starts": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "f01-native-start-ledger-v1" or not isinstance(value.get("starts"), list):
        raise ValueError("native start ledger has an unsupported structure")
    return value


def _worker_default_plan() -> dict[str, Any]:
    worker_path = REPO / "task_env/diagnostics/tasks/f01_isaac_native_baseline.py"
    spec = importlib.util.spec_from_file_location("f01_native_worker_plan", worker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load provider-free worker plan source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.default_plan()


def _ordinary_prestep_wiring_failure(start: dict[str, Any]) -> bool:
    worker = start.get("worker_receipt") or {}
    error = worker.get("worker_error") or {}
    eula_block = (
        start.get("failure_category") in {None, "eula_acceptance_required_prephysics"}
        and error.get("type") == "SystemExit"
        and error.get("stage") == "app_start"
        and "EULA not accepted" in str(error.get("message", ""))
        and "OMNI_KIT_ACCEPT_EULA=YES" in str(error.get("message", ""))
    )
    if start.get("failure_category") != "ordinary_bootstrap_api_asset_wiring" and not eula_block:
        return False
    if worker.get("total_physics_steps") != 0:
        return False
    if worker.get("physics_steps_at_start") not in (None, 0):
        # A non-zero manager counter is not itself a step in this process, but
        # the native receipt must prove that bootstrap and task counters did not advance.
        bootstrap = worker.get("bootstrap") or []
        if any(int(row.get("physics_steps", 0)) != 0 for row in bootstrap):
            return False
    if error.get("stage") not in {"app_start", "scene_prepare"}:
        return False
    if not eula_block and error.get("type") not in {"ImportError", "ModuleNotFoundError", "AttributeError", "FileNotFoundError", "TypeError"}:
        return False
    if start.get("stop_reason") or start.get("resource_abort") or start.get("timed_out"):
        return False
    return True


def launch_native(run_id: str, *, attempt_second_start: bool = False, eula_already_accepted: bool = False,
                  lock_wait_s: float = MAX_LOCK_WAIT_S, process_timeout_s: float = MAX_PROCESS_WALL_S) -> dict[str, Any]:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", run_id):
        raise ValueError("run id contains unsupported characters")
    run_dir = ATTEMPT_DIR / "native_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    plan_path = run_dir / "run_plan.json"
    plan = _worker_default_plan()
    plan["run_id"] = run_id
    _json_new(plan_path, plan)
    lock_wait_started = time.monotonic()
    lock_fd = LOCK_PATH.open("a+")
    lock_acquired = False
    lock_wait = 0.0
    lock_receipt: dict[str, Any] = {
        "schema": "f01-shared-native-lock-v1",
        "path": str(LOCK_PATH),
        "mode": "exclusive_flock",
        "wait_budget_s": lock_wait_s,
    }
    try:
        while time.monotonic() - lock_wait_started <= lock_wait_s:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_acquired = True
                lock_wait = time.monotonic() - lock_wait_started
                break
            except BlockingIOError:
                time.sleep(2.0)
        lock_receipt.update({"acquired": lock_acquired, "wait_seconds": lock_wait, "observed_at": time.time()})
        if not lock_acquired:
            lock_receipt["status"] = "NOT_RUN_LOCK_WAIT_EXPIRED"
            _json_new(run_dir / "lock_receipt.json", lock_receipt)
            return {"status": lock_receipt["status"], "run_dir": str(run_dir)}
        startup_mem = _mem_available_bytes()
        startup_gpu = _gpu_free_mib()
        startup_rx = _network_rx_bytes()
        startup = {
            "schema": "f01-native-start-resource-preflight-v1",
            "mem_available_bytes": startup_mem,
            "gpu0_free_mib": startup_gpu,
            "host_network_rx_bytes": startup_rx,
            "required_mem_available_bytes": MIN_START_AVAILABLE_BYTES,
            "required_gpu_free_mib": MIN_START_GPU_FREE_MIB,
            "passed": isinstance(startup_mem, int) and startup_mem >= MIN_START_AVAILABLE_BYTES
                      and isinstance(startup_gpu, int) and startup_gpu >= MIN_START_GPU_FREE_MIB
                      and isinstance(startup_rx, int),
            "measured_at": time.time(),
        }
        _json_new(run_dir / "startup_resource_preflight.json", startup)
        if not startup["passed"]:
            lock_receipt["status"] = "RESOURCE_PENDING"
            _json_new(run_dir / "lock_receipt.json", lock_receipt)
            return {"status": "RESOURCE_PENDING", "run_dir": str(run_dir), "startup_resource_preflight": startup}

        ledger_path = ATTEMPT_DIR / "native_start_ledger.json"
        ledger = _read_ledger(ledger_path)
        starts = ledger["starts"]
        if len(starts) >= 2:
            raise RuntimeError("F01 attempt002 exhausted its two App-start reservations")
        expected_index = len(starts) + 1
        if attempt_second_start != (expected_index == 2):
            raise RuntimeError("second App start requires explicit attempt_second_start=true after first-start evidence review")
        if expected_index == 2 and not _ordinary_prestep_wiring_failure(starts[-1]):
            raise RuntimeError("second App start is not permitted by the recorded first-start failure evidence")
        previous_worker = starts[-1].get("worker_receipt") or {} if starts else {}
        previous_error = previous_worker.get("worker_error") or {}
        eula_retry = (
            expected_index == 2
            and previous_error.get("type") == "SystemExit"
            and previous_error.get("stage") == "app_start"
            and "EULA not accepted" in str(previous_error.get("message", ""))
            and "OMNI_KIT_ACCEPT_EULA=YES" in str(previous_error.get("message", ""))
        )
        if eula_retry and not eula_already_accepted:
            raise RuntimeError("EULA-blocked retry requires explicit confirmation that the EULA was already accepted")
        if eula_already_accepted and not eula_retry:
            raise RuntimeError("EULA acceptance flag is only valid for the recorded EULA-blocked second start")

        prior_network_rx = sum(int(start.get("network_rx_delta_bytes", 0) or 0) for start in starts)
        remaining_network = max(0, MAX_NETWORK_RX_BYTES - prior_network_rx)
        if remaining_network <= 0:
            raise RuntimeError("aggregate F01 network RX budget already exhausted")
        cache_root = Path.home() / ".cache/ov"
        cache_before, cache_before_files = _cache_bytes(cache_root)
        rx_before = startup_rx
        reservation = {
            "app_start_number": expected_index,
            "run_id": run_id,
            "state": "reserved_before_process_launch",
            "reserved_at": time.time(),
            "run_dir": str(run_dir),
            "app_constructor_may_be_attempted": True,
            "app_process_launched": False,
            "physical_steps_observed": None,
            "failure_category": None,
            "worker_receipt": None,
            "stop_reason": None,
            "resource_abort": False,
            "timed_out": False,
        }
        starts.append(reservation)
        _json_replace(ledger_path, ledger)
        _json_new(run_dir / "app_start_reservation.json", reservation)
        lock_receipt["status"] = "LOCK_HELD_LAUNCHING"
        lock_receipt["pid"] = os.getpid()
        lock_receipt["app_start_number"] = expected_index
        lock_receipt["acquired_monotonic"] = time.monotonic()
        _json_new(run_dir / "lock_receipt.json", lock_receipt)

        env = dict(os.environ)
        env.update({
            "PYTHONPATH": str(REPO),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUNBUFFERED": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "TOKENIZERS_PARALLELISM": "false",
        })
        if eula_already_accepted:
            env["OMNI_KIT_ACCEPT_EULA"] = "YES"
        worker_script = REPO / "task_env/diagnostics/tasks/f01_isaac_native_baseline.py"
        reader_script = REPO / "task_env/diagnostics/tasks/f01_isaac_native_reader.py"
        supervisor_script = Path(__file__).resolve()
        source_hashes = {
            "F01_WORKER_SHA256": hashlib.sha256(worker_script.read_bytes()).hexdigest(),
            "F01_READER_SHA256": hashlib.sha256(reader_script.read_bytes()).hexdigest(),
            "F01_SUPERVISOR_SHA256": hashlib.sha256(supervisor_script.read_bytes()).hexdigest(),
        }
        env.update(source_hashes)
        command = [str(ENV_PYTHON), "-B", str(worker_script), "--native-worker", "--run-dir", str(run_dir)]
        _json_new(run_dir / "native_command.json", {
            "command": command,
            "cwd": str(REPO),
            "thread_env": {k: env[k] for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
            "python_no_user_site": env["PYTHONNOUSERSITE"],
            "eula_already_accepted_flag_applied": eula_already_accepted,
            "omni_kit_accept_eula": env.get("OMNI_KIT_ACCEPT_EULA"),
            "frozen_source_sha256": source_hashes,
        })
        log_path = run_dir / "native_worker.log"
        with log_path.open("xb") as log_stream:
            started = time.monotonic()
            with subprocess.Popen(command, cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                                  stdout=log_stream, stderr=subprocess.STDOUT, start_new_session=True) as proc:
                reservation.update({"state": "worker_process_started", "app_process_launched": True,
                                    "worker_pid": proc.pid, "worker_pgid": proc.pid, "launch_time": time.time()})
                ledger["starts"][-1] = reservation
                _json_replace(ledger_path, ledger)
                monitor = monitor_process(proc, log_path, started=started, timeout_s=process_timeout_s,
                                          network_baseline=rx_before, network_budget_bytes=remaining_network)
        worker_receipt = None
        result_path = run_dir / "native_result.json"
        if result_path.is_file():
            try:
                worker_receipt = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                worker_receipt = {"receipt_parse_error": True}
        cache_after, cache_after_files = _cache_bytes(cache_root)
        cache_delta = None if cache_before is None or cache_after is None else max(0, cache_after - cache_before)
        rx_delta = monitor.get("host_network_rx_delta_bytes")
        resource_abort = monitor.get("stop_reason") is not None and monitor.get("stop_reason") != "process_wall_timeout"
        timed_out = monitor.get("stop_reason") == "process_wall_timeout"
        over_caps = []
        if rx_delta > MAX_NETWORK_RX_BYTES:
            over_caps.append("host_network_rx_bytes")
        if cache_delta is not None and cache_delta > MAX_ASSET_CACHE_GROWTH_BYTES:
            over_caps.append("ov_cache_growth_bytes")
        try:
            evidence_bytes = sum(p.stat().st_size for p in run_dir.rglob("*") if p.is_file())
        except OSError:
            evidence_bytes = None
        log_bytes = log_path.stat().st_size if log_path.exists() else 0
        if log_bytes > MAX_LOG_BYTES:
            over_caps.append("native_log_bytes")
        if evidence_bytes is not None and evidence_bytes > MAX_EVIDENCE_BYTES:
            over_caps.append("evidence_bytes")
        native_physics_steps = worker_receipt.get("total_physics_steps") if isinstance(worker_receipt, dict) else None
        failure_category = None
        if (monitor.get("exit_code") not in (0, None) and isinstance(worker_receipt, dict)
                and worker_receipt.get("worker_error", {}).get("stage") in {"app_start", "scene_prepare"}
                and worker_receipt.get("worker_error", {}).get("type") in {"ImportError", "ModuleNotFoundError", "AttributeError", "FileNotFoundError", "TypeError"}
                and not monitor.get("stop_reason") and native_physics_steps == 0
                and not any(int(r.get("physics_steps", 0)) > 0 for r in worker_receipt.get("bootstrap", []) if isinstance(r, dict))):
            failure_category = "ordinary_bootstrap_api_asset_wiring"
        if (monitor.get("exit_code") not in (0, None) and isinstance(worker_receipt, dict)
                and worker_receipt.get("worker_error", {}).get("stage") == "app_start"
                and worker_receipt.get("worker_error", {}).get("type") == "SystemExit"
                and "EULA not accepted" in str(worker_receipt.get("worker_error", {}).get("message", ""))
                and "OMNI_KIT_ACCEPT_EULA=YES" in str(worker_receipt.get("worker_error", {}).get("message", ""))
                and not monitor.get("stop_reason") and native_physics_steps == 0
                and not any(int(r.get("physics_steps", 0)) > 0 for r in worker_receipt.get("bootstrap", []) if isinstance(r, dict))):
            failure_category = "eula_acceptance_required_prephysics"
        reservation.update({
            "state": "worker_process_exited",
            "exit_time": time.time(),
            "process_exit_code": monitor.get("exit_code"),
            "stop_reason": monitor.get("stop_reason"),
            "resource_abort": resource_abort,
            "timed_out": timed_out,
            "failure_category": failure_category,
            "worker_receipt": worker_receipt,
            "physical_steps_observed": native_physics_steps,
            "network_rx_delta_bytes": rx_delta,
        })
        ledger["starts"][-1] = reservation
        _json_replace(ledger_path, ledger)
        parent_receipt = {
            "schema": "f01-native-parent-exit-v1",
            "run_id": run_id,
            "process_monitor": monitor,
            "resource_preflight": startup,
            "network_rx_before_bytes": rx_before,
            "network_rx_delta_bytes": rx_delta,
            "network_rx_budget_bytes": MAX_NETWORK_RX_BYTES,
            "ov_cache_root": str(cache_root),
            "ov_cache_bytes_before": cache_before,
            "ov_cache_file_count_before": cache_before_files,
            "ov_cache_bytes_after": cache_after,
            "ov_cache_file_count_after": cache_after_files,
            "ov_cache_growth_bytes": cache_delta,
            "ov_cache_growth_budget_bytes": MAX_ASSET_CACHE_GROWTH_BYTES,
            "native_log_bytes": log_bytes,
            "native_log_budget_bytes": MAX_LOG_BYTES,
            "evidence_tree_bytes": evidence_bytes,
            "evidence_budget_bytes": MAX_EVIDENCE_BYTES,
            "over_budget_items": over_caps,
            "lock_held_through_worker_exit_and_post_cleanup_measurement": True,
            "worker_receipt_present": isinstance(worker_receipt, dict) and "schema" in worker_receipt,
        }
        _json_new(run_dir / "parent_exit_receipt.json", parent_receipt)
        held_seconds = time.monotonic() - float(lock_receipt["acquired_monotonic"])
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_acquired = False
        lock_fd.close()
        lock_receipt.update({"status": "RELEASED_AFTER_WORKER_EXIT", "released_at": time.time(),
                             "held_seconds": held_seconds})
        _json_replace(run_dir / "lock_receipt.json", lock_receipt)
        passed_parent = monitor.get("exit_code") == 0 and monitor.get("stop_reason") is None and not over_caps
        return {"status": "WORKER_EXITED" if passed_parent else "WORKER_OR_RESOURCE_FAILURE",
                "run_dir": str(run_dir), "exit_code": monitor.get("exit_code"),
                "stop_reason": monitor.get("stop_reason"), "failure_category": failure_category,
                "over_budget_items": over_caps, "lock_acquired": True}
    finally:
        if lock_acquired:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            finally:
                lock_fd.close()
        else:
            lock_fd.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt-second-start", action="store_true")
    parser.add_argument("--eula-already-accepted", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--lock-wait-s", type=float, default=MAX_LOCK_WAIT_S, help=argparse.SUPPRESS)
    parser.add_argument("--process-timeout-s", type=float, default=MAX_PROCESS_WALL_S, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = launch_native(args.run_id, attempt_second_start=args.attempt_second_start,
                               eula_already_accepted=args.eula_already_accepted,
                               lock_wait_s=args.lock_wait_s, process_timeout_s=args.process_timeout_s)
    except Exception as exc:
        result = {"status": "SUPERVISOR_ERROR", "error": {"type": type(exc).__name__, "message": str(exc)}}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result.get("status") in {"WORKER_EXITED", "NOT_RUN_LOCK_WAIT_EXPIRED", "RESOURCE_PENDING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
