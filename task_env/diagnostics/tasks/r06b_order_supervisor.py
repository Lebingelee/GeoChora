"""Exclusive-lock supervisor for the one R06b CPU worker and raw reader."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = Path('/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock')


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _available_bytes() -> int:
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable is not available from /proc/meminfo')


def _process_group_rss(pgid: int) -> list[dict[str, int]]:
    rows = []
    for status in Path('/proc').glob('[0-9]*/status'):
        try:
            pid = int(status.parent.name)
            stat = (status.parent / 'stat').read_text().split()
            if int(stat[4]) != pgid:
                continue
            vmrss = next(line for line in status.read_text().splitlines()
                         if line.startswith('VmRSS:'))
            rows.append({'pid': pid, 'rss_bytes': int(vmrss.split()[1]) * 1024})
        except (OSError, ValueError, StopIteration, IndexError):
            continue
    return rows


def _process_group_pids(pgid: int) -> list[int]:
    members = []
    for stat_path in Path('/proc').glob('[0-9]*/stat'):
        try:
            tail = stat_path.read_text().rsplit(')', 1)[1].split()
            if tail[0] != 'Z' and int(tail[2]) == pgid:
                members.append(int(stat_path.parent.name))
        except (OSError, ValueError, IndexError):
            continue
    return members


def _terminate_group(pgid: int, process: subprocess.Popen) -> dict[str, object]:
    receipt = {'term_sent': False, 'kill_sent': False, 'term_wait_seconds': 0.0}
    try:
        os.killpg(pgid, signal.SIGTERM)
        receipt['term_sent'] = True
    except ProcessLookupError:
        return receipt
    started = time.monotonic()
    deadline = started + 10
    while time.monotonic() < deadline and _process_group_pids(pgid):
        time.sleep(0.1)
    if _process_group_pids(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
            receipt['kill_sent'] = True
        except ProcessLookupError:
            pass
    process.wait()
    receipt['term_wait_seconds'] = time.monotonic() - started
    return receipt


def _wait_for_lock(fd: int, max_wait_seconds: int, output_dir: Path) -> tuple[bool, float]:
    started = time.monotonic()
    deadline = started + max_wait_seconds
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True, time.monotonic() - started
        except BlockingIOError:
            if time.monotonic() >= deadline:
                receipt = {
                    'status': 'NOT_RUN_LOCK_PENDING', 'lock_path': str(LOCK_PATH),
                    'lock_wait_seconds': time.monotonic() - started,
                    'max_lock_wait_seconds': max_wait_seconds,
                    'native_worker_started': False,
                }
                _write_json(output_dir / 'native_window.json', receipt)
                return False, time.monotonic() - started
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def run_supervisor(contract_path: Path, *, max_lock_wait_seconds: int = 1200) -> dict[str, object]:
    contract_path = contract_path.resolve()
    contract = json.loads(contract_path.read_text())
    output_dir = Path(contract['output_dir']).resolve()
    native_dir = output_dir / 'native'
    if native_dir.exists() or (output_dir / 'native_start_ledger.json').exists():
        raise FileExistsError('R06b native start/output already exists; this attempt has no retry')
    if max_lock_wait_seconds != 1200:
        raise ValueError('R06b lock wait is frozen to 1200 seconds')
    # Import only the standard-library worker module for hash preflight. It does
    # not import TaskEnv, MuJoCo or a provider at module import time.
    import r06b_order_worker
    r06b_order_worker._check_frozen_contract(contract, contract_path)
    if _available_bytes() < 2 * 1024 * 1024 * 1024:
        receipt = {
            'status': 'NOT_RUN_MEMORY_PREFLIGHT', 'native_worker_started': False,
            'mem_available_bytes': _available_bytes(), 'minimum_bytes': 2 * 1024 * 1024 * 1024,
        }
        _write_json(output_dir / 'native_window.json', receipt)
        return receipt
    if not LOCK_PATH.is_file():
        raise FileNotFoundError(f'shared native lock file is missing: {LOCK_PATH}')
    lock_fd = os.open(LOCK_PATH, os.O_RDWR)
    locked, wait_seconds = _wait_for_lock(lock_fd, max_lock_wait_seconds, output_dir)
    if not locked:
        os.close(lock_fd)
        return json.loads((output_dir / 'native_window.json').read_text())
    process = None
    group_pgid = None
    started = None
    outcome = None
    primary_error = None
    cleanup_error = None
    low_memory_samples = 0
    rss_samples = []
    worker_log = output_dir / 'native_worker.log'
    reader_log = output_dir / 'raw_reader.log'
    ledger = None
    reader_returncode = None
    reader_started = None
    reader_started_at_unix_s = None
    reader_wall_seconds = None
    memory_available = None
    termination = None
    environment = os.environ.copy()
    environment.update({
        'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
        'NUMEXPR_NUM_THREADS': '1', 'CUDA_VISIBLE_DEVICES': '',
        'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONPATH': f"{ROOT}:{ROOT / 'GeoPhys/src'}",
    })
    try:
        memory_available = _available_bytes()
        if memory_available < 2 * 1024 * 1024 * 1024:
            outcome = {
                'status': 'NOT_RUN_MEMORY_AFTER_LOCK', 'native_worker_started': False,
                'mem_available_bytes': memory_available,
                'minimum_bytes': 2 * 1024 * 1024 * 1024,
            }
        else:
            ledger = {
                'schema': 'r06b-native-start-ledger-v1', 'native_start_count': 1,
                'native_worker': 'r06b_order_worker.py', 'contract_sha256': contract['contract_sha256'],
                'input_head': contract['input_head'], 'branch': contract['branch'],
                'lock_path': str(LOCK_PATH), 'lock_wait_seconds': wait_seconds,
                'lock_device': os.fstat(lock_fd).st_dev, 'lock_inode': os.fstat(lock_fd).st_ino,
                'lock_acquired_at_unix_s': time.time(), 'parent_pid': os.getpid(),
                'worker_started': False,
            }
            _write_json(output_dir / 'native_start_ledger.json', ledger)
            with worker_log.open('wb') as log:
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / 'task_env/diagnostics/tasks/r06b_order_worker.py'),
                     '--contract', str(contract_path)],
                    cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                group_pgid = process.pid
                started = time.monotonic()
                ledger.update({'worker_started': True, 'worker_pid': process.pid,
                               'worker_pgid': group_pgid, 'worker_started_at_unix_s': time.time()})
                _write_json(output_dir / 'native_start_ledger.json', ledger)
                terminate_reason = None
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    rss_rows = _process_group_rss(group_pgid)
                    rss_total = sum(item['rss_bytes'] for item in rss_rows)
                    sample = {
                        'elapsed_seconds': elapsed, 'mem_available_bytes': _available_bytes(),
                        'process_rss': rss_rows, 'group_rss_bytes': rss_total,
                    }
                    rss_samples.append(sample)
                    if rss_total > 4 * 1024 * 1024 * 1024:
                        terminate_reason = 'sampled_process_group_rss_exceeded_4_GiB'
                    if sample['mem_available_bytes'] < 768 * 1024 * 1024:
                        low_memory_samples += 1
                    else:
                        low_memory_samples = 0
                    if low_memory_samples >= 3:
                        terminate_reason = 'MemAvailable_below_768_MiB_for_three_samples'
                    if elapsed > 300:
                        terminate_reason = 'worker_wall_exceeded_300_seconds'
                    if terminate_reason:
                        termination = _terminate_group(group_pgid, process)
                        outcome = {
                            'status': 'NATIVE_TERMINATED_RESOURCE_LIMIT',
                            'terminate_reason': terminate_reason,
                            'termination': termination,
                            'worker_returncode': process.returncode,
                        }
                        break
                    time.sleep(1.0)
            ledger.update({
                'worker_returncode': process.returncode,
                'worker_finished_at_unix_s': time.time(),
                'worker_wall_seconds': None if started is None else time.monotonic() - started,
            })
            _write_json(output_dir / 'native_start_ledger.json', ledger)
            if outcome is None:
                successful_result = (native_dir / 'native_result.json').is_file()
                outcome = {
                    'status': ('NATIVE_WORKER_EXITED_SUCCESS'
                               if process.returncode == 0 and successful_result
                               else 'NATIVE_WORKER_FAILED'),
                    'worker_returncode': process.returncode,
                    'native_result_present': successful_result,
                }
            if outcome['status'] == 'NATIVE_WORKER_EXITED_SUCCESS':
                result = json.loads((native_dir / 'native_result.json').read_text())
                if result.get('status') != 'R06B_NATIVE_WORKER_PASS_PENDING_READBACK':
                    raise ValueError('native worker exited zero without its exact pending-success result')
                raw_command = [
                    sys.executable, str(ROOT / 'task_env/diagnostics/tasks/r06b_order_readback.py'),
                    '--contract', str(contract_path), '--native-result',
                    str(native_dir / 'native_result.json'),
                ]
                with reader_log.open('wb') as log:
                    reader_started = time.monotonic()
                    reader_started_at_unix_s = time.time()
                    try:
                        reader = subprocess.run(raw_command, cwd=ROOT, env=environment,
                                                stdout=log, stderr=subprocess.STDOUT,
                                                timeout=60, check=False)
                    finally:
                        reader_wall_seconds = time.monotonic() - reader_started
                reader_returncode = reader.returncode
                if reader.returncode != 0:
                    raise ValueError(f'independent raw H5 witness exited {reader.returncode}')
                raw_receipt = json.loads((output_dir / 'raw_readback.json').read_text())
                outcome = {
                    'status': 'R06B_BOUNDED_ORDER_REGRESSION_PASS_PENDING_SOL_REVIEW',
                    'native_worker_returncode': process.returncode,
                    'raw_reader_returncode': reader.returncode,
                    'lock_held_until_raw_reader_exit': True,
                    'native_wall_seconds': None if started is None else time.monotonic() - started,
                    'native_result_sha256': _sha(native_dir / 'native_result.json'),
                    'raw_readback_sha256': _sha(output_dir / 'raw_readback.json'),
                    'raw_readback': raw_receipt,
                }
    except BaseException as error:
        primary_error = {
            'type': type(error).__name__, 'message': str(error),
            'traceback': ''.join(__import__('traceback').format_exception(error)),
        }
        outcome = {
            'status': 'NATIVE_SUPERVISOR_FAILED', 'native_worker_started': process is not None,
            'worker_returncode': None if process is None else process.poll(),
        }
    finally:
        if process is not None and group_pgid is not None:
            try:
                if process.poll() is None or _process_group_pids(group_pgid):
                    termination = _terminate_group(group_pgid, process)
            except BaseException as error:
                cleanup_error = {'type': type(error).__name__, 'message': str(error)}
        if group_pgid is not None and _process_group_pids(group_pgid):
            cleanup_error = cleanup_error or {
                'type': 'ProcessGroupStillAlive', 'message': f'process group {group_pgid} remained alive',
            }
        if outcome is None:
            outcome = {'status': 'NATIVE_SUPERVISOR_FAILED', 'native_worker_started': process is not None}
        samples_observed = bool(rss_samples)
        final = {
            **outcome,
            'lock_path': str(LOCK_PATH), 'lock_wait_seconds': wait_seconds,
            'mem_available_initial_bytes': memory_available,
            'native_worker_started': process is not None,
            'worker_pid': None if process is None else process.pid,
            'worker_pgid': group_pgid,
            'worker_returncode': None if process is None else process.poll(),
            'worker_start_ledger': ledger,
            'worker_start_ledger_sha256': (
                _sha(output_dir / 'native_start_ledger.json')
                if (output_dir / 'native_start_ledger.json').is_file() else None
            ),
            'worker_log': str(worker_log),
            'worker_log_sha256': _sha(worker_log) if worker_log.is_file() else None,
            'reader_log': str(reader_log),
            'reader_log_sha256': _sha(reader_log) if reader_log.is_file() else None,
            'raw_reader_returncode': reader_returncode,
            'raw_reader_started_at_unix_s': reader_started_at_unix_s,
            'raw_reader_wall_seconds': reader_wall_seconds,
            'rss_sample_count': len(rss_samples),
            'rss_peak_sampled_group_bytes': max(
                (item['group_rss_bytes'] for item in rss_samples), default=None,
            ),
            'rss_samples': rss_samples,
            'rss_peak_is_sampled_not_interval_hard_peak': samples_observed,
            'termination': termination,
            'primary_error': primary_error,
            'cleanup_error': cleanup_error,
            'lock_held_through_cleanup': True,
            'lock_released_after_group': False,
        }
        try:
            _write_json(output_dir / 'native_window.json', final)
        except BaseException as error:
            cleanup_error = cleanup_error or {'type': type(error).__name__, 'message': str(error)}
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
        final['lock_released_after_group'] = not bool(group_pgid and _process_group_pids(group_pgid))
        final['lock_released_at_unix_s'] = time.time()
        if cleanup_error is not None:
            final['cleanup_error'] = cleanup_error
            if final['status'] == 'R06B_BOUNDED_ORDER_REGRESSION_PASS_PENDING_SOL_REVIEW':
                final['status'] = 'NATIVE_SUPERVISOR_CLEANUP_FAILED'
        _write_json(output_dir / 'native_window.json', final)
    return final


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--max-lock-wait-seconds', type=int, default=1200)
    args = parser.parse_args(argv)
    result = run_supervisor(args.contract, max_lock_wait_seconds=args.max_lock_wait_seconds)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
