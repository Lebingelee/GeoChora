"""Bounded one-worker supervisor for the explicitly budgeted DG01 MuJoCo runs."""

from __future__ import annotations

import atexit
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _mem_available_bytes():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable is unavailable')


def _process_group_rss_bytes(pgid):
    total = 0
    found = False
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / 'stat').read_text()
            fields = stat[stat.rfind(')') + 2:].split()
            if int(fields[2]) != pgid:
                continue
            status = (entry / 'status').read_text()
            rss_kib = next(
                int(line.split()[1]) for line in status.splitlines()
                if line.startswith('VmRSS:')
            )
            total += rss_kib * 1024
            found = True
        except (FileNotFoundError, ProcessLookupError, StopIteration, ValueError, IndexError):
            continue
    return total if found else 0


def _group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_group(process, pgid, grace_s):
    if _group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + grace_s
    while _group_exists(pgid) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        pass


def run(plan_path: Path, receipt_path: Path):
    plan_path = plan_path.resolve()
    receipt_path = receipt_path.resolve()
    plan = json.loads(plan_path.read_text())
    if plan.get('schema_version') != 'f05-dg01-native-run-plan-v1':
        raise ValueError('unsupported DG01 native run plan')
    argv = plan.get('argv')
    if (not isinstance(argv, list) or not argv
            or any(type(item) is not str for item in argv)):
        raise ValueError('DG01 run plan requires an explicit argument vector')
    workdir = Path(plan['workdir']).resolve()
    if not workdir.is_dir():
        raise ValueError('DG01 run workdir is not an existing directory')
    limits = plan['limits']
    required = {
        'start_mem_available_bytes_min': 6 * 1024**3,
        'abort_mem_available_bytes_below': 1 * 1024**3,
        'group_rss_bytes_max': 4 * 1024**3,
        'sample_interval_s_max': 0.25,
        'term_grace_s': 5,
        'worker_wall_s_max': 300,
        'cpu_threads_max': 4,
    }
    for name, maximum in required.items():
        value = limits.get(name)
        if type(value) not in (int, float) or value <= 0 or value > maximum:
            raise ValueError(f'DG01 plan violates the frozen {name} ceiling')

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    lock_path = Path(plan['shared_lock_path']).resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open('a+')
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError('shared native execution lock is held by another writer') from exc

    cleanup_state = {
        'lock': lock,
        'process': None,
        'process_group_id': None,
        'released': False,
        'signals': [],
    }
    previous_handlers = {
        signum: signal.getsignal(signum)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }

    def note_signal(signum, _frame):
        cleanup_state['signals'].append(signum)

    def emergency_cleanup():
        process = cleanup_state['process']
        process_group_id = cleanup_state['process_group_id']
        if process is not None and process_group_id is not None:
            if _group_exists(process_group_id):
                _terminate_group(process, process_group_id, limits['term_grace_s'])
        if not cleanup_state['released']:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except (OSError, ValueError):
                pass
            try:
                lock.close()
            except OSError:
                pass
            cleanup_state['released'] = True
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)

    for signum in previous_handlers:
        signal.signal(signum, note_signal)
    atexit.register(emergency_cleanup)

    start_mem = _mem_available_bytes()
    if start_mem < limits['start_mem_available_bytes_min']:
        raise RuntimeError(f'native start gate failed: MemAvailable={start_mem}')

    run_dir = receipt_path.parent
    stdout_path = run_dir / 'worker.stdout.log'
    stderr_path = run_dir / 'worker.stderr.log'
    if stdout_path.exists() or stderr_path.exists():
        raise FileExistsError('DG01 worker log already exists')
    env = dict(os.environ)
    env.update({
        'OMP_NUM_THREADS': str(int(limits['cpu_threads_max'])),
        'OPENBLAS_NUM_THREADS': str(int(limits['cpu_threads_max'])),
        'MKL_NUM_THREADS': str(int(limits['cpu_threads_max'])),
    })
    env.update({str(k): str(v) for k, v in plan.get('environment', {}).items()})
    started = _utc_now()
    start_monotonic = time.monotonic()
    samples = []
    violation = None
    process = None
    process_group_id = None
    with stdout_path.open('x', encoding='utf-8') as stdout, stderr_path.open('x', encoding='utf-8') as stderr:
        if cleanup_state['signals']:
            raise RuntimeError('DG01 supervisor was interrupted before native worker start')
        process = subprocess.Popen(
            argv, cwd=workdir, env=env, stdout=stdout, stderr=stderr,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        process_group_id = process.pid
        cleanup_state['process'] = process
        cleanup_state['process_group_id'] = process_group_id
        deadline = start_monotonic + limits['worker_wall_s_max']
        next_sample = start_monotonic
        exited_at = None
        while True:
            now = time.monotonic()
            return_code = process.poll()
            if cleanup_state['signals'] and violation is None:
                signum = cleanup_state['signals'][-1]
                violation = f'supervisor_signal_{signal.Signals(signum).name}'
            if return_code is not None and exited_at is None:
                exited_at = now
            rss = _process_group_rss_bytes(process_group_id)
            available = _mem_available_bytes()
            samples.append({
                'elapsed_s': now - start_monotonic,
                'group_rss_bytes': rss,
                'mem_available_bytes': available,
            })
            if rss > limits['group_rss_bytes_max']:
                violation = 'process_group_rss_limit'
            elif available < limits['abort_mem_available_bytes_below']:
                violation = 'minimum_mem_available_abort'
            elif now >= deadline and return_code is None:
                violation = 'worker_wall_limit'
            elif exited_at is not None and _group_exists(process_group_id) and now - exited_at > 5:
                violation = 'worker_left_child_process_group'
            if violation is not None:
                _terminate_group(process, process_group_id, limits['term_grace_s'])
                break
            if return_code is not None and not _group_exists(process_group_id):
                break
            next_sample += limits['sample_interval_s_max']
            time.sleep(max(0.0, next_sample - time.monotonic()))
        return_code = process.poll()
        if return_code is None:
            try:
                return_code = process.wait(timeout=limits['term_grace_s'])
            except subprocess.TimeoutExpired:
                _terminate_group(process, process_group_id, limits['term_grace_s'])
                return_code = process.poll()

    remaining_group = _group_exists(process_group_id)
    if remaining_group:
        _terminate_group(process, process_group_id, limits['term_grace_s'])
        remaining_group = _group_exists(process_group_id)
    result = {
        'schema_version': 'f05-dg01-native-supervisor-receipt-v1',
        'run_id': plan['run_id'],
        'run_plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        'started_utc': started,
        'finished_utc': _utc_now(),
        'wall_seconds': time.monotonic() - start_monotonic,
        'start_mem_available_bytes': start_mem,
        'minimum_mem_available_bytes': min(item['mem_available_bytes'] for item in samples),
        'maximum_process_group_rss_bytes': max(item['group_rss_bytes'] for item in samples),
        'sample_interval_s_max_observed': max(
            (b['elapsed_s'] - a['elapsed_s'] for a, b in zip(samples, samples[1:])),
            default=0.0,
        ),
        'sample_count': len(samples),
        'worker_pid': process.pid,
        'worker_process_group_id': process_group_id,
        'worker_exit_code': return_code,
        'resource_violation': violation,
        'child_process_group_remaining_after_cleanup': remaining_group,
        'native_invocation_counted': True,
        'physics_steps': None,
        'stdout_path': str(stdout_path),
        'stderr_path': str(stderr_path),
        'resource_samples': samples,
        'lock_released': True,
    }
    with receipt_path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    lock.close()
    cleanup_state['released'] = True
    for signum, handler in previous_handlers.items():
        signal.signal(signum, handler)
    atexit.unregister(emergency_cleanup)
    if violation is not None or return_code != 0 or remaining_group:
        raise RuntimeError(
            f'DG01 native worker did not complete cleanly: exit={return_code}, '
            f'violation={violation}, remaining_group={remaining_group}'
        )
    return result


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args(argv)
    run(args.plan, args.receipt)


if __name__ == '__main__':
    main()
