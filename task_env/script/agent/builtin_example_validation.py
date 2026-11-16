"""Supervise fixed-seed runs for the versioned built-in PickCube example."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

if __package__:
    from .builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1
    from .isaac_core_site_overlay import populate_isaac_core_site_overlay
else:
    from builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1
    from isaac_core_site_overlay import populate_isaac_core_site_overlay

CORE = Path(__file__).resolve().parents[3]
LEGACY_LOCK = CORE / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock'
LOCK = CORE / 'workspace/locks/shared_native_execution.lock'
CPU_PYTHON = Path(sys.executable)
MAX_WORKER_LOG_BYTES = 64 * 1024**2
MAX_RUN_EVIDENCE_BYTES = 2 * 1024**3
# Isaac 6.2's accepted F06 startup currently advances 18 public physics
# substeps before the task reset. Keep that finite bootstrap inside each plan.
ISAAC_BOOTSTRAP_PHYSICS_STEPS_UPPER_BOUND = 18


_populate_isaac_core_site_overlay = populate_isaac_core_site_overlay


def _lock_matches_legacy(stream, *, require_legacy=False):
    """Check the canonical inode and any retained compatibility alias."""
    opened = os.fstat(stream.fileno())
    current = LOCK.lstat()
    if not (stat.S_ISREG(opened.st_mode) and stat.S_ISREG(current.st_mode)
            and (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)):
        return False
    try:
        legacy = LEGACY_LOCK.lstat()
    except FileNotFoundError:
        return not require_legacy
    return (stat.S_ISREG(legacy.st_mode)
            and (opened.st_dev, opened.st_ino) == (legacy.st_dev, legacy.st_ino))


def _open_shared_native_lock():
    """Open the existing canonical lock without creating a competing inode."""
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW)
    stream = os.fdopen(fd, 'r+')
    try:
        if not _lock_matches_legacy(stream):
            raise RuntimeError('native lock alias does not match legacy lock')
    except BaseException:
        stream.close()
        raise
    return stream


def _isaac_python(explicit=None):
    """Choose an external interpreter without probing or starting Isaac."""
    value = explicit if explicit is not None else os.environ.get('ISAAC_SIM_PYTHON')
    if not value:
        raise ValueError('Isaac requires --isaac-python or ISAAC_SIM_PYTHON')
    return Path(value).expanduser().absolute()


def _core_python():
    value = os.environ.get('GEOCHORA_CORE_PYTHON')
    return Path(value).expanduser().absolute() if value else CPU_PYTHON


def _isaac_dependency_overlay(executable, output):
    """Expose only the missing task/recording packages, after SDK packages."""
    query = ('import json,sys,sysconfig; print(json.dumps({'
             '"version":list(sys.version_info[:2]),"purelib":sysconfig.get_paths()["purelib"]}))')
    clean_env = os.environ.copy()
    clean_env.pop('PYTHONPATH', None)
    clean_env.pop('GEOCHORA_CORE_SITE', None)
    clean_env['PYTHONNOUSERSITE'] = '1'
    core = json.loads(subprocess.check_output([str(_core_python()), '-c', query], env=clean_env, text=True, timeout=10))
    isaac = json.loads(subprocess.check_output([str(executable), '-c', query], env=clean_env, text=True, timeout=10))
    if core['version'] != isaac['version']:
        raise ValueError('Core and Isaac Python versions differ; dependency overlay is unsafe')
    core_site = Path(core['purelib']).resolve(strict=True)
    overlay = output / 'isaac_dependency_overlay'
    overlay.mkdir()
    names = ['gymnasium', 'farama_notifications', 'h5py', 'h5py.libs']
    for prefix in ('gymnasium-', 'farama_notifications-', 'h5py-'):
        names.extend(p.name for p in core_site.iterdir() if p.name.startswith(prefix) and p.name.endswith('.dist-info'))
    for name in names:
        source = core_site / name
        if source.exists():
            (overlay / name).symlink_to(source, target_is_directory=source.is_dir())
        elif name in ('gymnasium', 'h5py'):
            raise ValueError(f'Core dependency is missing: {source}')
    check = ('import sys,json,tempfile; sys.path.append(sys.argv[1]); '
             'import numpy,h5py,gymnasium; '
             'f=tempfile.TemporaryFile(); '
             'h=h5py.File(f,"w"); h["x"]=numpy.array([0.,1.]); h.close(); '
             'f.seek(0); h=h5py.File(f,"r"); assert h["x"][:].tolist()==[0.,1.]; h.close(); f.close(); '
             'assert gymnasium.spaces.Box(-1.,1.,shape=(2,),dtype=numpy.float32).contains(numpy.array([0.,1.],dtype=numpy.float32)); '
             'print(json.dumps({"modules":{m.__name__:{"version":m.__version__,"path":m.__file__} for m in (numpy,h5py,gymnasium)},'
             '"hdf5_runtime":h5py.version.hdf5_version,"hdf5_built":h5py.version.hdf5_built_version_tuple}))')
    result = json.loads(subprocess.check_output([str(executable), '-c', check, str(overlay)],
                                                 cwd=output, env=clean_env, text=True, timeout=30))
    numpy_path = Path(result['modules']['numpy']['path']).resolve(strict=True)
    if not numpy_path.is_relative_to(Path(isaac['purelib']).resolve(strict=True)):
        raise ValueError(f'Isaac NumPy is outside the SDK site-packages: {numpy_path}')
    _write_json(output / 'isaac_dependency_overlay.json', {'core_site': str(core_site),
                'python_version': core['version'], 'entries': names, 'import_check': result})
    return overlay


def _geophys_source():
    value = os.environ.get('GEOCHORA_GEOPHYS_SRC')
    path = Path(value).expanduser().resolve() if value else CORE / 'GeoPhys/src'
    if not (path / 'scene' / '__init__.py').is_file():
        raise ValueError(f'GeoPhys src directory is missing scene/__init__.py: {path}')
    return path


def core_python():
    return _core_python()


def isaac_python():
    return _isaac_python()


def native_lock_path():
    return LOCK


def native_cleanup_blocker_path(lock_path):
    return Path(lock_path).with_name(Path(lock_path).name + '.unretired.json')


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _directory_bytes(path):
    return sum(item.stat().st_size for item in Path(path).rglob('*') if item.is_file())


def _planned_action_route_evidence(rows):
    seeds = sorted({
        item.get('seed') for item in rows
        if type(item.get('planning_action_count')) is int
        and item['planning_action_count'] > 0
    })
    total = sum(
        item['planning_action_count'] for item in rows
        if type(item.get('planning_action_count')) is int
        and item['planning_action_count'] > 0
    )
    return total, seeds


def _mem_available_bytes():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable unavailable')


def _gpu_free_mib():
    result = subprocess.run(
        ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'],
        check=True, capture_output=True, text=True, timeout=5,
    )
    values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    if not values:
        raise RuntimeError('GPU memory report is empty')
    return values[0]


def _proc_rss_tree(pid):
    pending = [pid]
    seen = set()
    total = 0
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            status = Path(f'/proc/{current}/status').read_text().splitlines()
            for line in status:
                if line.startswith('VmRSS:'):
                    total += int(line.split()[1]) * 1024
                    break
            children = Path(f'/proc/{current}/task/{current}/children').read_text().split()
            pending.extend(int(child) for child in children)
        except FileNotFoundError:
            continue
    return total


def _set_child_affinity():
    available = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, set(available[:4]))


def _kill_process_group(process, sig):
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def _retire_process_group(process):
    """Keep the caller's lock held until the supervised group has exited."""
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM, signal.SIGHUP})
    try:
        interrupted = process.poll() is None
        if interrupted:
            try:
                _kill_process_group(process, signal.SIGTERM)
            except PermissionError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    _kill_process_group(process, signal.SIGKILL)
                except PermissionError:
                    pass
                process.wait()
        deadline = time.monotonic() + 5
        while True:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return interrupted
            except PermissionError:
                # Do not release the lock when group retirement is unknown.
                interrupted = True
                time.sleep(.1)
                continue
            if time.monotonic() >= deadline:
                interrupted = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    return interrupted
                except PermissionError:
                    pass
            time.sleep(.1)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


@contextmanager
def _supervised_worker(command, *, environment, stdout, stderr, cwd=None, lock_fd=None):
    """Turn termination signals into cleanup and close the startup window."""
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)

    previous_handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGHUP)}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM, signal.SIGHUP})
    state = {'forced_retirement': False}
    try:
        def prepare_child():
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            _set_child_affinity()

        child_environment = dict(environment)
        child_environment.pop('GEOCHORA_SUPERVISED_NATIVE_LOCK_FD', None)
        inherited_fds = ()
        if lock_fd is not None:
            os.fstat(lock_fd)
            child_environment['GEOCHORA_SUPERVISED_NATIVE_LOCK_FD'] = str(lock_fd)
            inherited_fds = (lock_fd,)
        process = subprocess.Popen(
            command, cwd=CORE if cwd is None else cwd, env=child_environment, stdout=stdout, stderr=stderr,
            pass_fds=inherited_fds,
            start_new_session=True, preexec_fn=prepare_child,
        )
        try:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            yield process, state
        finally:
            state['forced_retirement'] = _retire_process_group(process)
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def _cold_read_h5(output, receipt, *, provider):
    h5_path = Path(output) / 'episode.h5'
    cold_path = Path(output) / 'cold_read.json'
    result = {
        'schema_version': 'harness-example-cold-read-v1',
        'reader': 'examples/recording/inspect_h5.py',
        'provider': provider,
        'status': 'FAIL',
        'checks': {},
    }
    if not h5_path.is_file():
        result['error'] = 'episode H5 is missing'
    else:
        environment = os.environ.copy()
        environment['PYTHONPATH'] = f'{_geophys_source()}:{CORE}'
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        try:
            inspected = subprocess.run(
                [str(_core_python()), str(CORE / 'examples/recording/inspect_h5.py'),
                 '--input', str(h5_path)],
                cwd=CORE, env=environment, capture_output=True, text=True, timeout=30,
                start_new_session=True,
            )
            result['returncode'] = inspected.returncode
            result['stdout'] = inspected.stdout
            result['stderr'] = inspected.stderr
            payload = json.loads(inspected.stdout.strip().splitlines()[-1]) if inspected.stdout.strip() else None
            result['summary'] = payload
            checks = {
                'reader_exit_zero': inspected.returncode == 0,
                'reader_status_pass': isinstance(payload, dict) and payload.get('status') == 'PASS',
                't_plus_one': isinstance(payload, dict) and payload.get('t_plus_one_valid') is True,
                'artifact_identity': isinstance(payload, dict) and payload.get('task_artifact_sha256') == receipt.get('artifact_sha256'),
                'controller_identity': isinstance(payload, dict) and payload.get('controller_identity') == receipt.get('controller_identity'),
                'solution_identity': isinstance(payload, dict) and payload.get('expert_identity') == receipt.get('solution_identity'),
                'provider_provenance': isinstance(payload, dict) and payload.get('provider_provenance_present') is True,
                'source_provenance': isinstance(payload, dict) and payload.get('source_provenance_present') is True,
                'transition_count': isinstance(payload, dict) and payload.get('transitions') == receipt.get('executed_transition_count'),
            }
            if provider == 'isaacsim':
                run_plan = json.loads((Path(output) / 'run_plan.json').read_text())
                app_profile = receipt.get('isaac_app_launch_profile')
                checks['isaac_app_launch_profile_matches_plan'] = (
                    run_plan.get('schema_version') == 'harness-builtin-pickcube-example-run-plan-v2'
                    and isinstance(app_profile, dict)
                    and app_profile.get('profile_id') == run_plan.get('isaac_app_launch_profile_id')
                    and isinstance(app_profile.get('simulation_app_config'), dict)
                )
            result['checks'] = checks
            result['status'] = 'PASS' if all(checks.values()) else 'FAIL'
        except BaseException as error:
            result['error'] = f'{type(error).__name__}: {error}'
    result['h5_sha256'] = __import__('hashlib').sha256(h5_path.read_bytes()).hexdigest() if h5_path.is_file() else None
    cold_path.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n')
    if receipt is not None:
        receipt['independent_cold_read'] = {
            'path': cold_path.name, 'status': result['status'],
            'checks': result.get('checks', {}), 'h5_sha256': result['h5_sha256'],
        }
        if result['status'] != 'PASS':
            receipt['runtime_valid'] = False
            receipt['status'] = 'INVALID'
            receipt['task_outcome'] = 'UNRESOLVED_RUNTIME_FAILURE'
            receipt.setdefault('errors', []).append({
                'phase': 'independent-cold-read', 'type': 'ColdReadFailure',
                'message': result.get('error') or str(result.get('checks')),
            })
        (Path(output) / 'run.json').write_text(
            json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + '\n'
        )
    return result


def _run_one(spec_path, catalog_path, scope_path, seed, output, *, provider, isaac_python=None):
    output.mkdir(parents=True, exist_ok=False)
    stdout_path, stderr_path = output / 'worker.stdout.log', output / 'worker.stderr.log'
    if provider == 'isaacsim':
        executable = _isaac_python(isaac_python)
        timeout_s = 1200
    else:
        executable = _core_python()
        timeout_s = 420
    spec = BuiltinPickCubeExampleV1.load(spec_path)
    catalog = json.loads(Path(catalog_path).read_text())
    scope = ExampleWorkingTreeScopeV1.load(scope_path)
    plan = {
        'schema_version': 'harness-builtin-pickcube-example-run-plan-v2',
        'provider': provider, 'backend': spec.backend, 'device': spec.device,
        'isaac_app_launch_profile_id': (
            'f06-headless-no-render-v1' if provider == 'isaacsim' else None
        ),
        'controller_profile': spec.controller_profile, 'seed': seed,
        'horizon_control_ticks': spec.horizon_control_ticks,
        'physics_dt_s': spec.physics_dt_s, 'control_substeps': spec.control_substeps,
        'native_app_starts_upper_bound': 1 if provider == 'isaacsim' else 0,
        'bootstrap_physics_steps_upper_bound': (
            ISAAC_BOOTSTRAP_PHYSICS_STEPS_UPPER_BOUND if provider == 'isaacsim' else 0
        ),
        'physics_steps_upper_bound': (
            spec.horizon_control_ticks * spec.control_substeps
            + ISAAC_BOOTSTRAP_PHYSICS_STEPS_UPPER_BOUND
            if provider == 'isaacsim' else spec.horizon_control_ticks * spec.control_substeps
        ),
        'watchdog_seconds': timeout_s,
        'process_group_rss_limit_bytes': 10 * 1024**3,
        'log_limit_bytes': MAX_WORKER_LOG_BYTES,
        'run_evidence_limit_bytes': MAX_RUN_EVIDENCE_BYTES,
        'core_commit': catalog.get('core_commit'),
        'input_sha256': {
            'spec': _sha256(spec_path), 'catalog': _sha256(catalog_path),
            'working_tree_scope': _sha256(scope_path),
        },
        'expected_untracked': scope.to_dict()['expected_untracked'],
        'worker_python': str(executable), 'output_dir': str(output.resolve()),
    }
    _write_json(output / 'run_plan.json', plan)
    if not executable.is_file():
        _write_json(output / 'run_preflight.json', {
            'schema_version': 'harness-builtin-pickcube-example-preflight-v1',
            'status': 'NOT_RUN_DEPENDENCY', 'worker_python': str(executable),
            'python_available': False,
        })
        return {'seed': seed, 'provider': provider, 'status': 'NOT_RUN_DEPENDENCY',
                'reason': f'Python runtime is absent: {executable}'}
    mem_start = _mem_available_bytes()
    gpu_start = _gpu_free_mib() if provider == 'isaacsim' else None
    if mem_start < 6 * 1024**3:
        _write_json(output / 'run_preflight.json', {
            'schema_version': 'harness-builtin-pickcube-example-preflight-v1',
            'status': 'NOT_RUN_RESOURCE_GATE', 'mem_available_start_bytes': mem_start,
            'gpu_free_start_mib': gpu_start, 'shared_native_lock_acquired': False,
        })
        return {'seed': seed, 'provider': provider, 'status': 'NOT_RUN_RESOURCE_GATE',
                'mem_available_bytes': mem_start, 'reason': 'less than 6 GiB available RAM'}
    if provider == 'isaacsim' and gpu_start < 5120:
        _write_json(output / 'run_preflight.json', {
            'schema_version': 'harness-builtin-pickcube-example-preflight-v1',
            'status': 'NOT_RUN_RESOURCE_GATE', 'mem_available_start_bytes': mem_start,
            'gpu_free_start_mib': gpu_start, 'shared_native_lock_acquired': False,
        })
        return {'seed': seed, 'provider': provider, 'status': 'NOT_RUN_RESOURCE_GATE',
                'gpu_free_mib': gpu_start, 'reason': 'less than 5120 MiB free GPU memory'}
    environment = os.environ.copy()
    environment.pop('GEOCHORA_ISAAC_DEPENDENCY_OVERLAY', None)
    environment.pop('PYTHONPATH', None) if provider == 'isaacsim' else None
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    if provider != 'isaacsim':
        environment['PYTHONPATH'] = f'{_geophys_source()}:{CORE}'
    else:
        environment['PYTHONNOUSERSITE'] = '1'
        environment.update({
            'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4',
            'OPENBLAS_NUM_THREADS': '4', 'NUMEXPR_NUM_THREADS': '4',
            'TOKENIZERS_PARALLELISM': 'false',
        })
        # The SDK interpreter must use its own dependencies.  Importing a
        # second Python environment's binary modules can mix incompatible ABIs.
        environment.pop('GEOCHORA_CORE_SITE', None)
        try:
            environment['GEOCHORA_ISAAC_DEPENDENCY_OVERLAY'] = str(_isaac_dependency_overlay(executable, output))
        except Exception as error:
            _write_json(output / 'run_preflight.json', {
                'schema_version': 'harness-builtin-pickcube-example-preflight-v1',
                'status': 'NOT_RUN_DEPENDENCY', 'shared_native_lock_acquired': False,
                'reason': f'Isaac dependency overlay: {type(error).__name__}: {error}',
            })
            return {'seed': seed, 'provider': provider, 'status': 'NOT_RUN_DEPENDENCY',
                    'reason': f'Isaac dependency overlay: {type(error).__name__}: {error}'}
    command = [str(executable), str(Path(__file__).with_name('builtin_example_worker.py')),
               '--spec', str(spec_path), '--catalog', str(catalog_path),
               '--working-tree-scope', str(scope_path), '--seed', str(seed),
               '--output', str(output)]
    wall_start = time.perf_counter()
    with _open_shared_native_lock() as lock_stream:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _write_json(output / 'run_preflight.json', {
                'schema_version': 'harness-builtin-pickcube-example-preflight-v1',
                'status': 'BLOCKED_NATIVE_LOCK', 'mem_available_start_bytes': mem_start,
                'gpu_free_start_mib': gpu_start, 'shared_native_lock_acquired': False,
            })
            return {'seed': seed, 'provider': provider, 'status': 'BLOCKED_NATIVE_LOCK',
                    'reason': 'another process owns the shared native execution lock'}
        legacy_was_present = os.path.lexists(LEGACY_LOCK)
        if not _lock_matches_legacy(lock_stream, require_legacy=legacy_was_present):
            raise RuntimeError('native lock alias changed while acquiring lock')
        blocker = native_cleanup_blocker_path(LOCK)
        if blocker.exists():
            return {'seed': seed, 'provider': provider, 'status': 'BLOCKED_NATIVE_LOCK',
                    'reason': f'unconfirmed native process retirement; inspect {blocker}'}
        _write_json(output / 'run_preflight.json', {
            'schema_version': 'harness-builtin-pickcube-example-preflight-v1',
            'status': 'READY', 'mem_available_start_bytes': mem_start,
            'gpu_free_start_mib': gpu_start, 'shared_native_lock_acquired': True,
            'shared_native_lock_path': str(LOCK), 'cpu_affinity_slots': 4,
        })
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            with _supervised_worker(command, environment=environment, stdout=stdout, stderr=stderr,
                                    cwd=output.resolve(), lock_fd=lock_stream.fileno()) as (process, worker_state):
                timed_out = False
                resource_violation = None
                while process.poll() is None:
                    try:
                        lock_valid = _lock_matches_legacy(lock_stream, require_legacy=legacy_was_present)
                    except OSError:
                        lock_valid = False
                    if not lock_valid:
                        resource_violation = 'shared native lock path changed during worker execution'
                        _kill_process_group(process, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            _kill_process_group(process, signal.SIGKILL)
                        break
                    elapsed = time.perf_counter() - wall_start
                    if elapsed > timeout_s:
                        timed_out = True
                        resource_violation = f'wall watchdog {timeout_s}s exceeded'
                        _kill_process_group(process, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            _kill_process_group(process, signal.SIGKILL)
                        break
                    try:
                        available = _mem_available_bytes()
                        rss = _proc_rss_tree(process.pid)
                        gpu_free = _gpu_free_mib() if provider == 'isaacsim' else None
                    except Exception as error:
                        resource_violation = f'resource monitoring unavailable: {type(error).__name__}: {error}'
                        _kill_process_group(process, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            _kill_process_group(process, signal.SIGKILL)
                        break
                    if available < 1024**3:
                        resource_violation = f'MemAvailable below 1 GiB: {available}'
                    elif rss > 10 * 1024**3:
                        resource_violation = f'process-group RSS above 10 GiB: {rss}'
                    elif provider == 'isaacsim' and gpu_free < 256:
                        resource_violation = f'GPU free memory below 256 MiB: {gpu_free}'
                    elif stdout_path.stat().st_size + stderr_path.stat().st_size > MAX_WORKER_LOG_BYTES:
                        resource_violation = 'worker stdout/stderr exceeded 64 MiB log budget'
                    elif _directory_bytes(output) > MAX_RUN_EVIDENCE_BYTES:
                        resource_violation = 'run output exceeded 2 GiB evidence budget'
                    if resource_violation:
                        _kill_process_group(process, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            _kill_process_group(process, signal.SIGKILL)
                        break
                    time.sleep(1.0)
                returncode = process.wait()
                worker_process_wall_s = time.perf_counter() - wall_start
            group_intervened = worker_state['forced_retirement']
        try:
            if not _lock_matches_legacy(lock_stream, require_legacy=legacy_was_present):
                resource_violation = resource_violation or 'shared native lock path changed during worker execution'
        except OSError:
            resource_violation = resource_violation or 'shared native lock path changed during worker execution'
        pg_alive = False
        if group_intervened:
            resource_violation = resource_violation or 'worker process group required forced retirement'
        # Close our descriptor on context exit; an isolated Runtime descendant
        # retains the same locked open-file description until it exits. An
        # explicit LOCK_UN here would release the lock on behalf of the child.
    lock_available_after_worker = False
    try:
        with _open_shared_native_lock() as probe:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_available_after_worker = True
    except (OSError, RuntimeError):
        pass
    _write_json(output / 'lock_receipt.json', {
        'schema_version': 'harness-builtin-pickcube-example-lock-receipt-v1',
        'shared_native_lock_path': str(LOCK),
        'released_after_worker_process_group_exit': lock_available_after_worker and not pg_alive,
        'shared_lock_available_after_worker_exit': lock_available_after_worker,
        'lock_held_for_worker': True,
    })
    if not lock_available_after_worker:
        return {'seed': seed, 'provider': provider, 'status': 'INVALID',
                'runtime_valid': False, 'worker_process_group_ended': not pg_alive,
                'reason': 'shared lock remains held or changed after worker exit; cold read deferred'}
    receipt_path = output / 'run.json'
    receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else None
    cold_read = _cold_read_h5(output, receipt, provider=provider)
    receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else receipt
    status = ('RUNTIME_VALID' if receipt and receipt.get('runtime_valid')
              and returncode == 0 and resource_violation is None else 'INVALID')
    return {
        'seed': seed, 'provider': provider, 'status': status,
        'returncode': returncode, 'timed_out': timed_out,
        'resource_violation': resource_violation,
        'mem_available_start_bytes': mem_start, 'gpu_free_start_mib': gpu_start,
        'wall_time_s': time.perf_counter() - wall_start,
        'worker_process_wall_s': worker_process_wall_s,
        'worker_process_starts': 1,
        'physics_steps_upper_bound': plan['physics_steps_upper_bound'],
        'worker_process_group_ended': not pg_alive,
        'run_receipt': str(receipt_path.relative_to(CORE)) if receipt else None,
        'run_receipt_sha256': __import__('hashlib').sha256(receipt_path.read_bytes()).hexdigest() if receipt else None,
        'worker_stdout': str(stdout_path.relative_to(CORE)),
        'worker_stderr': str(stderr_path.relative_to(CORE)),
        'task_outcome': receipt.get('task_outcome') if receipt else None,
        'compiled': receipt.get('compiled') if receipt else None,
        'runtime_valid': status == 'RUNTIME_VALID',
        'isaac_app_launch_profile_id': (
            receipt.get('isaac_app_launch_profile', {}).get('profile_id')
            if receipt and isinstance(receipt.get('isaac_app_launch_profile'), dict) else None
        ),
        'planning_action_count': receipt.get('planning_action_count') if receipt else 0,
        'recording': receipt.get('recording') if receipt else None,
        'independent_cold_read': cold_read,
    }


def validate_provider(spec_path, catalog_path, scope_path, output_dir, *, only_seed=None,
                      provider_override=None, source_delivery_manifest=None, isaac_python=None):
    spec = BuiltinPickCubeExampleV1.load(spec_path)
    if provider_override is not None:
        route = {
            'mujoco': ('cpu', 'cpu'), 'geophys': ('cpu', 'cpu'),
            'isaacsim': ('cuda', 'cuda:0'), 'genesis': ('cpu', 'cpu'),
            'sapien': ('cpu', 'cpu'),
        }[provider_override]
        manifest = source_delivery_manifest if provider_override == 'isaacsim' else None
        if provider_override == 'isaacsim' and manifest is None:
            manifest = spec.source_delivery_manifest
        if manifest is not None:
            manifest = str(Path(manifest).expanduser().resolve(strict=True))
        spec = replace(spec, provider=provider_override, backend=route[0], device=route[1],
                       source_delivery_manifest=manifest)
    scope = ExampleWorkingTreeScopeV1.load(scope_path)
    catalog = json.loads(Path(catalog_path).read_text())
    if __package__:
        from .harness_compiler import resolve_builtin_pickcube_example
    else:
        from harness_compiler import resolve_builtin_pickcube_example
    resolve_builtin_pickcube_example(spec, catalog, working_tree_scope=scope)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    save_inputs = output_dir / 'inputs'
    save_inputs.mkdir()
    (save_inputs / 'example_spec.json').write_text(json.dumps(spec.to_dict(), indent=2, ensure_ascii=False) + '\n')
    (save_inputs / 'catalog.json').write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
    (save_inputs / 'working_tree_scope.json').write_text(json.dumps(scope.to_dict(), indent=2, ensure_ascii=False) + '\n')
    seeds = (only_seed,) if only_seed is not None else spec.seeds
    rows = []
    for seed in seeds:
        if seed not in spec.seeds:
            raise ValueError(f'seed {seed} is outside the fixed F06 seed set')
        run_dir = output_dir / f'seed_{seed}'
        row = _run_one(
            save_inputs / 'example_spec.json', save_inputs / 'catalog.json',
            save_inputs / 'working_tree_scope.json', seed, run_dir, provider=spec.provider,
            isaac_python=isaac_python,
        )
        rows.append(row)
        # The F06 route gate only counts the fixed seeds; diagnostic seeds are
        # reported separately and never supply the required evidence.
        planned_action_count_total, planned_action_seed_ids = _planned_action_route_evidence(
            [item for item in rows if item.get('seed') in spec.seeds[:3]]
        )
        diagnostic_planned_action_count, diagnostic_planned_action_seed_ids = (
            _planned_action_route_evidence(
                [item for item in rows if item.get('seed') not in spec.seeds[:3]]
            )
        )
        compiled_values = [item.get('compiled') for item in rows]
        compiled_consistent = bool(compiled_values and all(
            isinstance(value, dict) and value == compiled_values[0] for value in compiled_values
        ))
        matrix = {
            'schema_version': 'harness-builtin-pickcube-example-matrix-v1',
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'spec_sha256': spec.identity_sha256,
            'compiled': compiled_values[0] if compiled_values else None,
            'compiled_consistent': compiled_consistent,
            'provider': spec.provider, 'backend': spec.backend, 'device': spec.device,
            'profile': spec.controller_profile, 'horizon': spec.horizon_control_ticks,
            'seeds_required': list(spec.seeds[:3]), 'seeds_diagnostic': list(spec.seeds[3:]),
            'seeds_run': list(seeds),
            'rows': rows,
            'runtime_valid_count': sum(item.get('runtime_valid') is True for item in rows),
            'task_solved_count': sum(item.get('task_outcome') == 'SOLVED' for item in rows),
            'planned_action_count_total': planned_action_count_total,
            'planned_action_seed_ids': planned_action_seed_ids,
            'diagnostic_planned_action_count': diagnostic_planned_action_count,
            'diagnostic_planned_action_seed_ids': diagnostic_planned_action_seed_ids,
            'planned_action_route_gate': (
                'PASS' if planned_action_count_total > 0 else 'MISSING_CORE_PLANNED_ACTION_EVIDENCE'
            ),
            'disposition': 'PASS' if (
                sorted(item.get('seed') for item in rows if item.get('seed') in spec.seeds[:3])
                == sorted(spec.seeds[:3])
                and all(item.get('runtime_valid') is True for item in rows)
                and compiled_consistent and planned_action_count_total > 0
            )
                           else 'PREFLIGHT' if only_seed is not None and compiled_consistent and all(item.get('runtime_valid') is True for item in rows)
                           else 'PARTIAL',
            'qualification': False,
            'strict_candidate_oracle_judge_unchanged': True,
        }
        (output_dir / 'provider_matrix.json.tmp').write_text(json.dumps(matrix, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        (output_dir / 'provider_matrix.json.tmp').replace(output_dir / 'provider_matrix.json')
        print(json.dumps({'provider': spec.provider, 'seed': seed, 'status': row.get('status')}, sort_keys=True), flush=True)
    return matrix


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--working-tree-scope', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--provider', choices=('mujoco', 'geophys', 'isaacsim', 'genesis', 'sapien'))
    parser.add_argument('--source-delivery-manifest', type=Path,
                        help='required exact F06 PickCube USD manifest for --provider isaacsim')
    parser.add_argument('--only-seed', type=int, choices=(31, 32, 33))
    parser.add_argument('--isaac-python', type=Path,
                        help='Isaac interpreter; overrides ISAAC_SIM_PYTHON')
    args = parser.parse_args(argv)
    result = validate_provider(args.spec, args.catalog, args.working_tree_scope,
                               args.output_dir, only_seed=args.only_seed,
                               provider_override=args.provider,
                               source_delivery_manifest=args.source_delivery_manifest,
                               isaac_python=args.isaac_python)
    print(json.dumps({'provider': result['provider'], 'disposition': result['disposition'],
                      'runtime_valid_count': result['runtime_valid_count'],
                      'task_solved_count': result['task_solved_count']}, sort_keys=True))
    return 0 if result['disposition'] in ('PASS', 'PREFLIGHT') else 1


if __name__ == '__main__':
    raise SystemExit(main())
