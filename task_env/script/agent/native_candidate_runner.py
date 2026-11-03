"""Supervised native worker launcher for strict candidates that cannot run in-process.

Isaac Sim episodes need the frozen Isaac Python and one headless
``SimulationApp`` per process. This module launches ``candidate_worker.py``
under that interpreter with the same resource gates, shared native lock,
filtered Core dependency overlay and process-group retirement that the F06
built-in example supervisor uses, then hands the worker's raw row/receipt back
to the in-process Harness report logic. It never fabricates an outcome: a
worker that produced no row becomes an invalid row carrying its preflight and
supervision facts.
"""
from __future__ import annotations

import json
import importlib.util
import os
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path

if __package__:
    from .builtin_example_validation import (
        ISAAC_PYTHON, LOCK as F06_LOCK, MAX_WORKER_LOG_BYTES, MAX_RUN_EVIDENCE_BYTES,
        _directory_bytes, _gpu_free_mib, _kill_process_group, _mem_available_bytes,
        _populate_isaac_core_site_overlay, _proc_rss_tree, _set_child_affinity, _write_json,
    )
    from .feasibility_probe import invalid_row
    from .harness_spec_schema import save_json
    from .provider_routes import requires_native_worker, route_for
else:
    from builtin_example_validation import (
        ISAAC_PYTHON, LOCK as F06_LOCK, MAX_WORKER_LOG_BYTES, MAX_RUN_EVIDENCE_BYTES,
        _directory_bytes, _gpu_free_mib, _kill_process_group, _mem_available_bytes,
        _populate_isaac_core_site_overlay, _proc_rss_tree, _set_child_affinity, _write_json,
    )
    from feasibility_probe import invalid_row
    from harness_spec_schema import save_json
    from provider_routes import requires_native_worker, route_for

CORE = Path(__file__).resolve().parents[3]
WORKER = Path(__file__).with_name('candidate_worker.py')
DEFAULT_LOCK = CORE / 'workspace/harness/shared_native_execution.lock'
RECEIPT_SCHEMA = 'harness-candidate-native-run-receipt-v1'
PLAN_SCHEMA = 'harness-candidate-native-run-plan-v1'
DEFAULT_TIMEOUT_S = 1200
NOT_RUN_STATUSES = ('NOT_RUN_DEPENDENCY', 'NOT_RUN_RESOURCE_GATE', 'BLOCKED_NATIVE_LOCK')


def isaac_python() -> Path:
    override = os.environ.get('GEOCHORA_ISAAC_PYTHON')
    return Path(override).expanduser() if override else ISAAC_PYTHON


def native_lock_path() -> Path:
    """One lock serializes every native run on a machine; the F06 lock is reused when present."""
    override = os.environ.get('GEOCHORA_NATIVE_LOCK')
    if override:
        path = Path(override).expanduser().resolve()
    elif F06_LOCK.parent.is_dir():
        path = F06_LOCK
    else:
        path = DEFAULT_LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _core_site() -> Path:
    # A system-site-packages venv may inherit Core dependencies from its base.
    dependency = importlib.util.find_spec('gymnasium')
    if dependency is not None and dependency.origin:
        return Path(dependency.origin).resolve().parent.parent
    return Path(sysconfig.get_paths()['purelib']).resolve()


def _receipt(status, **values):
    return {'schema_version': RECEIPT_SCHEMA, 'status': status, **values}


def launch_worker(*, mode, spec, catalog, provider, seed, horizon, output_dir, time_limit_s=None,
                  extra_args=()):
    """Run one worker episode; returns the supervision receipt (also written to disk)."""
    route = route_for(provider)
    if not requires_native_worker(provider):
        raise ValueError(f'{provider} runs in-process; the native launcher is only for native-worker routes')
    if mode not in ('probe', 'oracle'):
        raise ValueError('worker mode must be probe or oracle')
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / 'inputs'
    inputs.mkdir()
    spec_path, catalog_path = inputs / 'candidate.spec.json', inputs / 'catalog.json'
    spec.save(spec_path)
    save_json(catalog, catalog_path)
    executable = isaac_python()
    timeout_s = int(time_limit_s or DEFAULT_TIMEOUT_S)
    stdout_path, stderr_path = output / 'worker.stdout.log', output / 'worker.stderr.log'
    plan = {
        'schema_version': PLAN_SCHEMA, 'mode': mode, 'provider': provider, 'backend': route['backend'],
        'device': route['device'], 'seed': seed, 'horizon': horizon, 'worker': str(WORKER),
        'worker_python': str(executable), 'watchdog_seconds': timeout_s,
        'process_group_rss_limit_bytes': 10 * 1024**3, 'log_limit_bytes': MAX_WORKER_LOG_BYTES,
        'run_evidence_limit_bytes': MAX_RUN_EVIDENCE_BYTES, 'core_commit': catalog.get('core_commit'),
        'eula_acceptance_passthrough': 'OMNI_KIT_ACCEPT_EULA' in os.environ,
        'output_dir': str(output),
    }
    _write_json(output / 'native_run_plan.json', plan)
    wall_start = time.perf_counter()

    def finish(status, **values):
        receipt = _receipt(status, mode=mode, provider=provider, seed=seed, horizon=horizon,
                           worker_python=str(executable), output_dir=str(output),
                           wall_time_s=time.perf_counter() - wall_start, **values)
        _write_json(output / 'native_run_receipt.json', receipt)
        return receipt

    if not executable.is_file():
        return finish('NOT_RUN_DEPENDENCY', reason=f'native worker Python is absent: {executable}')
    try:
        mem_start = _mem_available_bytes()
        gpu_start = _gpu_free_mib()
    except Exception as error:
        return finish('NOT_RUN_RESOURCE_GATE', reason=f'resource probes unavailable: {type(error).__name__}: {error}')
    if mem_start < 6 * 1024**3:
        return finish('NOT_RUN_RESOURCE_GATE', reason='less than 6 GiB available RAM', mem_available_bytes=mem_start)
    if gpu_start < 5120:
        return finish('NOT_RUN_RESOURCE_GATE', reason='less than 5120 MiB free GPU memory', gpu_free_mib=gpu_start)

    environment = os.environ.copy()
    environment.pop('PYTHONPATH', None)
    environment.update({
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
        'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4',
        'NUMEXPR_NUM_THREADS': '4', 'TOKENIZERS_PARALLELISM': 'false',
    })
    overlay_owner = tempfile.TemporaryDirectory(prefix='geochora-isaac-core-site-')
    try:
        plan['isaac_core_site_overlay'] = _populate_isaac_core_site_overlay(_core_site(), overlay_owner.name)
        environment['GEOCHORA_CORE_SITE'] = overlay_owner.name
        _write_json(output / 'native_run_plan.json', plan)
        command = [str(executable), str(WORKER), '--mode', mode, '--spec', str(spec_path),
                   '--catalog', str(catalog_path), '--provider', provider, '--seed', str(seed),
                   '--horizon', str(horizon), '--output', str(output), *extra_args]
        lock_path = native_lock_path()
        import fcntl
        with lock_path.open('a') as lock_stream:
            try:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return finish('BLOCKED_NATIVE_LOCK', reason='another process owns the shared native execution lock',
                              lock_path=str(lock_path))
            violation = None
            preexec = _set_child_affinity if hasattr(os, 'sched_setaffinity') else None
            with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
                process = subprocess.Popen(command, cwd=CORE, env=environment, stdout=stdout, stderr=stderr,
                                           start_new_session=True, preexec_fn=preexec)
                while process.poll() is None:
                    if time.perf_counter() - wall_start > timeout_s:
                        violation = f'wall watchdog {timeout_s}s exceeded'
                    else:
                        try:
                            available = _mem_available_bytes()
                            rss = _proc_rss_tree(process.pid)
                            gpu_free = _gpu_free_mib()
                        except Exception as error:
                            violation = f'resource monitoring unavailable: {type(error).__name__}: {error}'
                        else:
                            if available < 1024**3:
                                violation = f'MemAvailable below 1 GiB: {available}'
                            elif rss > 10 * 1024**3:
                                violation = f'process-group RSS above 10 GiB: {rss}'
                            elif gpu_free < 256:
                                violation = f'GPU free memory below 256 MiB: {gpu_free}'
                            elif stdout_path.stat().st_size + stderr_path.stat().st_size > MAX_WORKER_LOG_BYTES:
                                violation = 'worker stdout/stderr exceeded the log budget'
                            elif _directory_bytes(output) > MAX_RUN_EVIDENCE_BYTES:
                                violation = 'run output exceeded the evidence budget'
                    if violation:
                        _kill_process_group(process, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            _kill_process_group(process, signal.SIGKILL)
                        break
                    time.sleep(1.0)
                returncode = process.wait()
            # Retain the lock until the whole process group is gone so an abnormal
            # Kit shutdown cannot overlap the next native run.
            group_alive = True
            for _ in range(50):
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    group_alive = False
                    break
                time.sleep(0.1)
            if group_alive:
                _kill_process_group(process, signal.SIGTERM)
                time.sleep(0.5)
                _kill_process_group(process, signal.SIGKILL)
                violation = violation or 'worker process group did not end after worker exit'
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
    finally:
        overlay_owner.cleanup()
    status = 'COMPLETED' if violation is None else ('TIMEOUT' if violation.startswith('wall watchdog') else 'RESOURCE_VIOLATION')
    if violation is None and returncode != 0:
        violation = f'native worker exited with status {returncode}'
        status = 'WORKER_FAILED'
    return finish(status, returncode=returncode, reason=violation, lock_path=str(lock_path),
                  process_group_retired=not group_alive, stdout=stdout_path.name, stderr=stderr_path.name)


def run_seed_native(*, spec, catalog, provider, seed, horizon, output_dir, expected_artifact_hash=None):
    """Return one feasibility row produced by the worker, or an invalid row with the receipt."""
    receipt = launch_worker(mode='probe', spec=spec, catalog=catalog, provider=provider, seed=seed,
                            horizon=horizon, output_dir=output_dir)
    output = Path(output_dir).resolve()
    row_path = output / 'row.json'
    row = None
    if row_path.is_file():
        try:
            row = json.loads(row_path.read_text())
            if row.get('seed') != seed or row.get('horizon') != horizon:
                raise ValueError('worker row seed/horizon differ from the request')
            if (expected_artifact_hash is not None and row.get('construction_succeeded')
                    and row.get('artifact_hash') != expected_artifact_hash):
                raise ValueError('worker row artifact identity differs from the parent compilation')
        except Exception as error:
            row = invalid_row(seed, horizon, error_type='NativeWorkerRowInvalid', message=str(error),
                              traceback_text=json.dumps(receipt, sort_keys=True),
                              wall_time_s=receipt.get('wall_time_s', 0.0))
    if row is None:
        error_type = 'NativeWorkerUnavailable' if receipt['status'] in NOT_RUN_STATUSES else 'NativeWorkerFailed'
        row = invalid_row(seed, horizon, error_type=error_type,
                          message=receipt.get('reason') or receipt['status'],
                          traceback_text=json.dumps(receipt, sort_keys=True),
                          wall_time_s=receipt.get('wall_time_s', 0.0))
    if (receipt['status'] != 'COMPLETED' or receipt.get('returncode') != 0
            or receipt.get('process_group_retired') is not True):
        worker_row = row
        row = invalid_row(seed, horizon, error_type='NativeWorkerFailed',
                          message=receipt.get('reason') or 'native execution did not finish cleanly',
                          traceback_text=json.dumps(receipt, sort_keys=True),
                          wall_time_s=receipt.get('wall_time_s', 0.0))
        row['worker_row'] = worker_row
    row['native_run'] = {'status': receipt['status'], 'reason': receipt.get('reason'),
                         'returncode': receipt.get('returncode'), 'output_dir': str(output),
                         'receipt': 'native_run_receipt.json', 'worker_python': receipt.get('worker_python')}
    return row


def run_oracle_native(*, spec, catalog, provider, seed, directory, time_limit_s):
    """Run the recording worker; returns (worker payload or None, receipt)."""
    directory = Path(directory).resolve()
    h5 = directory / 'oracle.h5'
    receipt = launch_worker(mode='oracle', spec=spec, catalog=catalog, provider=provider, seed=seed,
                            horizon=spec.horizon, output_dir=directory / 'native', time_limit_s=time_limit_s,
                            extra_args=('--h5', str(h5), '--time-limit-s', str(int(time_limit_s))))
    payload_path = directory / 'native' / 'worker_receipt.json'
    payload = json.loads(payload_path.read_text()) if payload_path.is_file() else None
    if (receipt['status'] != 'COMPLETED' or receipt.get('returncode') != 0
            or receipt.get('process_group_retired') is not True):
        if payload is None:
            payload = {'facts': None, 'errors': []}
        payload.setdefault('errors', []).append({
            'phase': 'native_supervision', 'type': 'NativeWorkerFailed',
            'message': receipt.get('reason') or 'native execution did not finish cleanly',
        })
    return payload, receipt


__all__ = ['DEFAULT_LOCK', 'NOT_RUN_STATUSES', 'isaac_python', 'launch_worker', 'native_lock_path',
           'run_oracle_native', 'run_seed_native']
