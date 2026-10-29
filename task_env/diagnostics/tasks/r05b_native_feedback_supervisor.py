#!/usr/bin/env python3
"""Exclusive-lock and resource supervisor for one R05b native process group."""
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


GIB = 1024 ** 3
MIB = 1024 ** 2
LOCK_PATH = Path(
    '/home/lly/Program_Files/Geochora/workspace/maintenance/'
    'phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock'
)
CORE = Path('/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora')
WORKER = CORE / 'task_env/diagnostics/tasks/r05b_native_feedback_s2_worker.py'
READER = CORE / 'task_env/diagnostics/tasks/r05b_native_feedback_independent_reader.py'


def _json_write(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def _mem_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable is unavailable')


def _gpu_info():
    raw = subprocess.check_output([
        'nvidia-smi', '--query-gpu=index,name,uuid,driver_version,memory.total,memory.used,memory.free',
        '--format=csv,noheader,nounits',
    ], text=True, stderr=subprocess.STDOUT, timeout=10).strip().splitlines()
    if len(raw) != 1:
        raise RuntimeError(f'R05b requires one visible CUDA device, found {len(raw)}')
    cells = [cell.strip() for cell in raw[0].split(',')]
    if len(cells) != 7:
        raise RuntimeError('nvidia-smi GPU inventory shape is unsupported')
    total_mib, used_mib, free_mib = map(int, cells[4:])
    return {
        'index': cells[0], 'name': cells[1], 'uuid': cells[2], 'driver_version': cells[3],
        'total_bytes': total_mib * MIB, 'used_bytes': used_mib * MIB, 'free_bytes': free_mib * MIB,
    }


def _compute_apps():
    raw = subprocess.check_output([
        'nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits',
    ], text=True, stderr=subprocess.STDOUT, timeout=10).strip()
    if not raw:
        return []
    result = []
    for line in raw.splitlines():
        pid, used = [item.strip() for item in line.split(',', 1)]
        if pid not in {'N/A', '[Not Found]'} and used not in {'N/A', '[Not Found]'}:
            result.append({'pid': int(pid), 'used_bytes': int(used) * MIB})
    return result


def _process_group(pgid):
    output = subprocess.check_output(['ps', '-eo', 'pid=,pgid=,rss='], text=True)
    rows = []
    total_rss = 0
    for line in output.splitlines():
        cells = line.split()
        if len(cells) != 3:
            continue
        pid, process_group, rss_kib = map(int, cells)
        if process_group == pgid:
            rows.append(pid)
            total_rss += rss_kib * 1024
    return rows, total_rss


def _output_size(root):
    total = 0
    for path in root.rglob('*'):
        if path.is_file():
            total += path.stat().st_size
    return total


def _terminate_group(pgid, process):
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def _resource_snapshot(backend):
    ram = _mem_available()
    gpu = _gpu_info() if backend == 'cuda' else None
    apps = _compute_apps() if backend == 'cuda' else []
    eligible = ram >= 5 * GIB
    cap = None
    if gpu is not None:
        eligible = eligible and gpu['free_bytes'] >= 2 * GIB and not apps
        cap = min(7 * GIB, gpu['free_bytes'] - 512 * MIB)
    return {
        'mem_available_bytes': ram,
        'gpu': gpu,
        'compute_apps': apps,
        'worker_gpu_memory_cap_bytes': cap,
        'eligible': eligible and (cap is None or cap > 0),
    }


def _worker_resources_pass(*, backend, child_return, resource_limit_reason,
                           worker_result, rss_sample_count, rss_max_sample_bytes,
                           minimum_mem_available_sample_bytes,
                           minimum_gpu_free_sample_bytes):
    """Require an initialized resource receipt before accepting worker output."""
    resource_receipt_ready = (
        type(rss_sample_count) is int and rss_sample_count > 0
        and type(rss_max_sample_bytes) is int and rss_max_sample_bytes > 0
        and type(minimum_mem_available_sample_bytes) is int
        and minimum_mem_available_sample_bytes > 0
        and (backend != 'cuda' or (
            type(minimum_gpu_free_sample_bytes) is int
            and minimum_gpu_free_sample_bytes > 0
        ))
    )
    return bool(
        resource_receipt_ready and child_return == 0 and resource_limit_reason is None
        and worker_result is not None and worker_result.get('status') == 'passed'
        and worker_result.get('close_success') is True
    )


def check(backend: str, cell: str, python: Path, output_path: Path):
    """Provider-free launch gate; it never starts the worker or materializes physics."""
    if not LOCK_PATH.is_file() or not python.is_file():
        raise RuntimeError('shared lock or selected Python executable is missing')
    lock_fd = os.open(LOCK_PATH, os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_stat = LOCK_PATH.stat()
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    except BlockingIOError as exc:
        raise RuntimeError('shared native lock is currently held') from exc
    finally:
        os.close(lock_fd)
    core_head = subprocess.check_output(['git', '-C', str(CORE), 'rev-parse', 'HEAD'], text=True).strip()
    core_status = subprocess.check_output(['git', '-C', str(CORE), 'status', '--porcelain'], text=True)
    provider_root = CORE / 'GeoPhys'
    provider_head = subprocess.check_output(['git', '-C', str(provider_root), 'rev-parse', 'HEAD'], text=True).strip()
    provider_status = subprocess.check_output(['git', '-C', str(provider_root), 'status', '--porcelain'], text=True)
    menagerie = subprocess.check_output(
        ['git', '-C', str(CORE), 'ls-tree', 'HEAD', 'asset/external/mujoco_menagerie'], text=True,
    ).split()[2]
    if core_status.strip() or provider_status.strip():
        raise RuntimeError('Core and Provider trees must be clean before R05c native freeze')
    if provider_head != 'c6df840bef8d36b1150150167df08e29dc3f664c':
        raise RuntimeError(f'unexpected GeoPhys pin: {provider_head}')
    if menagerie != 'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7':
        raise RuntimeError(f'unexpected Menagerie pin: {menagerie}')
    resources = _resource_snapshot(backend)
    if not resources['eligible']:
        raise RuntimeError(f'native resource gate is not eligible: {resources}')
    hashes = {}
    for path in (WORKER, READER, CORE / 'task_env/diagnostics/tasks/r05b_native_feedback_supervisor.py',
                 CORE / 'task_env/diagnostics/tasks/c05c_geophys_gripper_cadence.py'):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {
        'schema_version': 'r05c-native-launch-check-v1', 'status': 'passed',
        'cell': cell, 'backend': backend, 'python': str(python), 'core_head': core_head,
        'core_clean': True, 'provider_head': provider_head, 'provider_clean': True,
        'menagerie_pin': menagerie, 'lock_path': str(LOCK_PATH),
        'lock_device': lock_stat.st_dev, 'lock_inode': lock_stat.st_ino,
        'worker_hashes': hashes, 'resources': resources,
        'native_start_count': 0, 'provider_materialization_count': 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _json_write(output_path, result)
    return result


def run(backend: str, run_root: Path, python: Path, *, gripper_hz: int = 500,
        full_episode: bool = False):
    run_root.mkdir(parents=True, exist_ok=False)
    worker_dir = run_root / 'worker'
    worker_log = run_root / 'native_worker.log'
    progress_path = run_root / 'progress.jsonl'
    result_path = run_root / 'supervisor_result.json'
    lock_start = time.monotonic()
    pre_lock = subprocess.run(
        ['lslocks', '--notruncate', '-o', 'PID,COMMAND,PATH'],
        text=True, capture_output=True, timeout=10,
    )
    lock_inventory_before = pre_lock.stdout.strip()
    if not LOCK_PATH.is_file():
        result = {'status': 'blocked_lock_missing', 'lock_path': str(LOCK_PATH)}
        _json_write(result_path, result)
        return result
    lock_fd = os.open(LOCK_PATH, os.O_RDWR)
    os.set_inheritable(lock_fd, True)
    lock_wait = None
    native_started = False
    child = None
    child_return = None
    pgid = None
    maximum_rss = 0
    maximum_gpu = 0
    minimum_mem = None
    minimum_gpu_free = None
    resource_limit_reason = None
    samples = 0
    lock_acquired_wall = None
    snapshot = None
    try:
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_wait = time.monotonic() - lock_start
                lock_acquired_wall = time.time()
                break
            except BlockingIOError:
                if time.monotonic() - lock_start >= 1800:
                    result = {
                        'status': 'not_run_lock_pending', 'lock_wait_seconds': time.monotonic() - lock_start,
                        'lock_path': str(LOCK_PATH), 'lock_inventory_before': lock_inventory_before,
                    }
                    _json_write(result_path, result)
                    return result
                time.sleep(1.0)

        resource_wait_start = time.monotonic()
        while True:
            snapshot = _resource_snapshot(backend)
            if snapshot['eligible']:
                break
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            if time.monotonic() - resource_wait_start >= 1800:
                result = {
                    'status': 'not_run_resource_pending', 'resource_snapshot': snapshot,
                    'lock_wait_seconds': lock_wait, 'lock_path': str(LOCK_PATH),
                }
                _json_write(result_path, result)
                return result
            time.sleep(10.0)
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - resource_wait_start >= 1800:
                        result = {
                            'status': 'not_run_resource_pending', 'resource_snapshot': snapshot,
                            'lock_wait_seconds': time.monotonic() - lock_start,
                            'lock_path': str(LOCK_PATH),
                        }
                        _json_write(result_path, result)
                        return result
                    time.sleep(1.0)

        lock_stat = LOCK_PATH.stat()
        argv = [str(python), str(WORKER), '--backend', backend, '--output-dir', str(worker_dir),
                '--gripper-hz', str(gripper_hz)]
        if full_episode:
            argv.append('--full-episode')
        env = os.environ.copy()
        env.update({
            'PYTHONPATH': str(CORE) + os.pathsep + str(CORE / 'GeoPhys/src'),
            'PYTHONDONTWRITEBYTECODE': '1',
            'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
            'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1',
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        })
        with worker_log.open('xb') as stream:
            child = subprocess.Popen(
                argv, cwd=CORE, env=env, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True, pass_fds=(lock_fd,),
            )
            pgid = child.pid
            native_started = True
            launch = {
                'schema_version': 'r05c-full-native-launch-v1' if full_episode else 'r05b-native-launch-v1',
                'backend': backend, 'gripper_hz': gripper_hz, 'full_episode': full_episode,
                'argv': argv, 'cwd': str(CORE),
                'lock_path': str(LOCK_PATH), 'lock_device': lock_stat.st_dev,
                'lock_inode': lock_stat.st_ino, 'lock_wait_seconds': lock_wait,
                'lock_acquired_at_unix_s': lock_acquired_wall,
                'native_start_count': 1, 'worker_pid': child.pid, 'worker_pgid': pgid,
                'prelaunch_resources': snapshot,
                'caps': {
                    'wall_seconds': 1500 if full_episode else 900,
                    'process_group_rss_bytes': 4 * GIB,
                    'output_bytes': 128 * MIB if full_episode else 64 * MIB,
                    'log_bytes': 16 * MIB,
                    'outer_steps': 6000 if full_episode else 2,
                    'native_steps': 30000 if full_episode else 10,
                    'worker_gpu_memory_bytes': snapshot['worker_gpu_memory_cap_bytes'],
                },
                'thread_environment': {key: env[key] for key in (
                    'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                    'NUMEXPR_NUM_THREADS',
                )},
            }
            _json_write(run_root / 'launch.json', launch)
            start = time.monotonic()
            while child.poll() is None:
                pids, group_rss = _process_group(pgid)
                maximum_rss = max(maximum_rss, group_rss)
                current_mem = _mem_available()
                minimum_mem = current_mem if minimum_mem is None else min(minimum_mem, current_mem)
                gpu_memory = 0
                if backend == 'cuda':
                    gpu = _gpu_info()
                    minimum_gpu_free = (gpu['free_bytes'] if minimum_gpu_free is None
                                        else min(minimum_gpu_free, gpu['free_bytes']))
                    own_pids = set(pids)
                    apps = _compute_apps()
                    gpu_memory = sum(item['used_bytes'] for item in apps if item['pid'] in own_pids)
                    other_apps = [item for item in apps if item['pid'] not in own_pids]
                    if other_apps:
                        resource_limit_reason = 'other_cuda_compute_process_appeared'
                    maximum_gpu = max(maximum_gpu, gpu_memory)
                    if gpu_memory > snapshot['worker_gpu_memory_cap_bytes']:
                        resource_limit_reason = 'worker_gpu_memory_cap_exceeded'
                output_bytes = _output_size(run_root)
                worker_log_bytes = worker_log.stat().st_size if worker_log.exists() else 0
                elapsed = time.monotonic() - start
                samples += 1
                event = {
                    'sample': samples, 'elapsed_seconds': elapsed,
                    'worker_pids': pids, 'process_group_rss_bytes': group_rss,
                    'mem_available_bytes': current_mem,
                    'worker_gpu_memory_bytes': gpu_memory,
                    'output_bytes': output_bytes,
                    'worker_log_bytes': worker_log_bytes,
                }
                with progress_path.open('a', encoding='utf-8') as log:
                    log.write(json.dumps(event, sort_keys=True) + '\n')
                if group_rss > 4 * GIB:
                    resource_limit_reason = 'process_group_rss_cap_exceeded'
                elif output_bytes > (128 * MIB if full_episode else 64 * MIB):
                    resource_limit_reason = 'output_cap_exceeded'
                elif full_episode and worker_log_bytes > 16 * MIB:
                    resource_limit_reason = 'worker_log_cap_exceeded'
                elif elapsed > (1500 if full_episode else 900):
                    resource_limit_reason = 'worker_wall_cap_exceeded'
                if resource_limit_reason:
                    _terminate_group(pgid, child)
                    break
                time.sleep(1.0)
            child_return = child.wait()
            # Confirm no child remains in this process group before releasing the lock.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                remaining, _ = _process_group(pgid)
                if not remaining:
                    break
                time.sleep(0.2)
            remaining, leftover_rss = _process_group(pgid)
            if remaining:
                _terminate_group(pgid, child)
                resource_limit_reason = resource_limit_reason or 'worker_group_did_not_exit_cleanly'
            maximum_rss = max(maximum_rss, leftover_rss)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_release_wall = time.time()

        worker_result_path = worker_dir / 'result.json'
        worker_result = json.loads(worker_result_path.read_text()) if worker_result_path.is_file() else None
        status = 'passed' if _worker_resources_pass(
            backend=backend,
            child_return=child_return,
            resource_limit_reason=resource_limit_reason,
            worker_result=worker_result,
            rss_sample_count=samples,
            rss_max_sample_bytes=maximum_rss,
            minimum_mem_available_sample_bytes=minimum_mem,
            minimum_gpu_free_sample_bytes=minimum_gpu_free,
        ) else 'failed_or_blocked'
        reader_result = None
        reader_exit = None
        if status == 'passed':
            full_ok = (not full_episode or (
                worker_result.get('profile') == 'normal'
                and worker_result.get('gripper_control_hz') == gripper_hz
                and worker_result.get('native_feedback_profile') == 'nutassembly-native-feedback-v1'
                and worker_result.get('close_success') is True
                and worker_result.get('s2', {}).get('status') == 'passed'
                and worker_result.get('s3', {}).get('status') == 'passed'
            ))
            if not full_ok:
                status = 'failed_or_blocked_full_task_or_s3'
        if status == 'passed':
            expected = {
                name: worker_result[name] for name in (
                    'backend', 'artifact_identity', 'source_id', 'source_xml_sha256',
                    'controller_identity', 'solution_identity', 'episode_id',
                    'reset_sample_id', 'provider_materialization_id',
                )
            }
            if full_episode:
                expected.update({
                    'gripper_control_hz': gripper_hz,
                    'transition_count': worker_result['s2']['transition_count'],
                    'require_task_success': True,
                    'provider_commit': worker_result['provider_build_identity']['repository_revision'],
                    'provider_import_origin': worker_result['provider_build_identity']['import_origin'],
                })
            expected_path = run_root / 'reader_expected.json'
            _json_write(expected_path, expected)
            reader_argv = [
                str(python), str(READER), '--h5', (
                    worker_result['h5_full_path'] if full_episode else worker_result['h5_path']
                ),
                '--expected', str(expected_path), '--output', str(run_root / 'independent_reader.json'),
            ]
            if full_episode:
                reader_argv.extend(['--mode', 'full'])
            reader_env = {
                'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1',
                'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
                'NUMEXPR_NUM_THREADS': '1',
            }
            reader_start = time.monotonic()
            with (run_root / 'independent_reader.log').open('xb') as stream:
                reader = subprocess.run(
                    reader_argv, cwd=run_root, env=reader_env,
                    stdout=stream, stderr=subprocess.STDOUT, timeout=180 if full_episode else 60,
                )
            reader_exit = reader.returncode
            reader_result_path = run_root / 'independent_reader.json'
            reader_result = json.loads(reader_result_path.read_text()) if reader_result_path.is_file() else None
            reader_wall = time.monotonic() - reader_start
            if (reader_wall > (180 if full_episode else 60) or reader_exit != 0
                    or reader_result is None or reader_result.get('result') != 'PASS'):
                status = 'failed_or_blocked_independent_reader'
        else:
            reader_wall = None
        final = {
            'schema_version': 'r05c-full-native-supervisor-result-v1' if full_episode
            else 'r05b-native-supervisor-result-v1',
            'status': status, 'backend': backend, 'lock_path': str(LOCK_PATH),
            'gripper_hz': gripper_hz, 'full_episode': full_episode,
            'lock_device': lock_stat.st_dev, 'lock_inode': lock_stat.st_ino,
            'lock_wait_seconds': lock_wait, 'lock_held_through_native_worker_exit': True,
            'lock_released_at_unix_s': lock_release_wall,
            'lock_released_before_independent_reader': True,
            'native_start_count': int(native_started), 'worker_pid': child.pid,
            'worker_pgid': pgid, 'worker_returncode': child_return,
            'resource_limit_reason': resource_limit_reason,
            'worker_wall_seconds': None if child is None else time.monotonic() - start,
            'process_group_rss_max_sample_bytes': maximum_rss,
            'process_group_rss_sample_count': samples,
            'minimum_mem_available_sample_bytes': minimum_mem,
            'worker_gpu_memory_max_sample_bytes': maximum_gpu if backend == 'cuda' else None,
            'minimum_gpu_free_sample_bytes': minimum_gpu_free,
            'output_bytes_at_worker_exit': _output_size(run_root),
            'worker_result': worker_result,
            'independent_reader_exit': reader_exit,
            'independent_reader_wall_seconds': reader_wall,
            'independent_reader_result': reader_result,
        }
        _json_write(result_path, final)
        return final
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--gripper-hz', type=int, choices=(100, 500), default=500)
    parser.add_argument('--full-episode', action='store_true')
    parser.add_argument('--cell', default=None)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--check-output', type=Path)
    parser.add_argument('--python', type=Path, default=Path('/home/lly/miniconda3/envs/geochora/bin/python'))
    args = parser.parse_args()
    if args.check:
        if not args.cell or args.check_output is None:
            parser.error('--check requires --cell and --check-output')
        result = check(args.backend, args.cell, args.python, args.check_output)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return
    result = run(args.backend, args.run_root, args.python, gripper_hz=args.gripper_hz,
                 full_episode=args.full_episode)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    if result['status'] != 'passed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
