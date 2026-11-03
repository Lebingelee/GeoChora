"""Native supervision failure must override a worker's optimistic row."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_candidate_runner as runner
from feasibility_probe import initial_row


def solved_row():
    row = initial_row(0, 5)
    row.update(artifact_hash='a' * 64, classification='solved', phase='execution',
               reason='task_and_expert_completion_confirmed', construction_succeeded=True,
               reset_attempted=True, reset_succeeded=True, steps=1, step_attempts=1,
               task_success=True, solution_done=True, expert_complete=True,
               completion_basis='selected_expert_completion', completion_eligible=True,
               close_attempted=True, close_succeeded=True)
    return row


@pytest.mark.parametrize('status,returncode,retired', [
    ('TIMEOUT', -15, True),
    ('RESOURCE_VIOLATION', -9, True),
    ('WORKER_FAILED', 1, True),
    ('COMPLETED', 0, False),
])
def test_supervision_failure_invalidates_written_solved_row(tmp_path, status, returncode, retired):
    (tmp_path / 'row.json').write_text(json.dumps(solved_row()))
    receipt = {'status': status, 'returncode': returncode,
               'process_group_retired': retired, 'reason': 'injected failure'}
    with patch.object(runner, 'launch_worker', return_value=receipt):
        row = runner.run_seed_native(spec=None, catalog={}, provider='isaacsim', seed=0,
                                     horizon=5, output_dir=tmp_path, expected_artifact_hash='a' * 64)
    assert row['classification'] == 'invalid'
    assert row['error_type'] == 'NativeWorkerFailed'
    assert row['worker_row']['classification'] == 'solved'


@pytest.mark.parametrize('defect', [None, 'missing_facts', 'false_completion', 'wrong_seed', 'wrong_artifact'])
def test_parent_rejects_invalid_worker_completion_facts(tmp_path, defect):
    row = solved_row()
    if defect == 'missing_facts':
        del row['task_success']
    elif defect == 'false_completion':
        row['task_success'] = False
    elif defect == 'wrong_seed':
        row['seed'] = 9
    elif defect == 'wrong_artifact':
        row['artifact_hash'] = 'b' * 64
    (tmp_path / 'row.json').write_text(json.dumps(row))
    receipt = {'status': 'COMPLETED', 'returncode': 0, 'process_group_retired': True}
    with patch.object(runner, 'launch_worker', return_value=receipt):
        result = runner.run_seed_native(spec=None, catalog={}, provider='isaacsim', seed=0,
                                        horizon=5, output_dir=tmp_path, expected_artifact_hash='a' * 64)
    assert result['classification'] == ('solved' if defect is None else 'invalid')
    assert result['error_type'] == (None if defect is None else 'NativeWorkerRowInvalid')


def test_builtin_launch_refuses_unconfirmed_native_retirement(tmp_path, monkeypatch):
    import builtin_example_validation as validation
    from builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1

    spec = BuiltinPickCubeExampleV1.from_dict({
        'schema_version': 'harness-builtin-pickcube-example-v1',
        'example_id': 'pickcube-harness-example-v1', 'task_uid': 'pick-cube-p16-reference-v1',
        'provider': 'mujoco', 'backend': 'cpu', 'device': 'cpu',
        'controller_profile': 'r3_continuous_v1', 'seeds': [31, 32, 33],
        'horizon_control_ticks': 1000, 'physics_dt_s': .002, 'control_substeps': 5,
        'source_delivery_manifest': None,
    })
    spec_path, catalog_path, scope_path = (tmp_path / name for name in ('spec.json', 'catalog.json', 'scope.json'))
    spec_path.write_text(json.dumps(spec.to_dict()))
    catalog_path.write_text('{}')
    scope_path.write_text(json.dumps(ExampleWorkingTreeScopeV1(
        'harness-example-working-tree-scope-v1', (),
    ).to_dict()))
    lock_path = tmp_path / 'native.lock'
    validation.native_cleanup_blocker_path(lock_path).write_text('{}')
    monkeypatch.setattr(validation, 'native_lock_path', lambda: lock_path)
    monkeypatch.setattr(validation, 'core_python', lambda: Path(sys.executable))
    monkeypatch.setattr(validation, '_mem_available_bytes', lambda: 12 * 1024**3)
    with patch.object(validation.subprocess, 'Popen') as popen:
        receipt = validation._run_one(spec_path, catalog_path, scope_path, 31,
                                       tmp_path / 'run', provider='mujoco')
    assert receipt['status'] == 'BLOCKED_NATIVE_LOCK'
    popen.assert_not_called()


@pytest.mark.parametrize('interruption,location,cleanup_failure', [
    (TimeoutError, 'sleep', None),
    (KeyboardInterrupt, 'sleep', None),
    (TimeoutError, 'spawn', None),
    (TimeoutError, 'monitor', None),
    (TimeoutError, 'sleep', 'unretired'),
    (TimeoutError, 'sleep', 'wait_error'),
])
def test_parent_interruption_retires_worker_before_releasing_lock(
        tmp_path, monkeypatch, interruption, location, cleanup_failure):
    import fcntl

    lock_path = tmp_path / 'native.lock'
    children = []
    kill_signals = []
    real_popen = subprocess.Popen
    real_kill = runner._kill_process_group
    real_sleep = time.sleep

    def launch(_command, **kwargs):
        child = real_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
        children.append(child)
        if location == 'spawn':
            os.kill(os.getpid(), signal.SIGALRM)
        return child

    def kill_while_locked(process, sig):
        with lock_path.open('a') as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        kill_signals.append(sig)
        real_kill(process, sig)

    sleeps = 0

    def interrupt_once(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1 and location == 'sleep':
            raise interruption('parent interruption sentinel')
        real_sleep(seconds)

    def monitor(_pid):
        if location == 'monitor':
            os.kill(os.getpid(), signal.SIGALRM)
        return 1024

    def alarm_handler(*_args):
        raise TimeoutError('parent interruption sentinel')

    monkeypatch.setattr(runner, 'isaac_python', lambda: Path(sys.executable))
    monkeypatch.setattr(runner, 'native_lock_path', lambda: lock_path)
    monkeypatch.setattr(runner, '_mem_available_bytes', lambda: 12 * 1024**3)
    monkeypatch.setattr(runner, '_gpu_free_mib', lambda: 7000)
    monkeypatch.setattr(runner, '_proc_rss_tree', monitor)
    monkeypatch.setattr(runner, '_core_site', lambda: tmp_path)
    monkeypatch.setattr(runner, '_populate_isaac_core_site_overlay', lambda *_: {})
    monkeypatch.setattr(runner, '_set_child_affinity', lambda: None)
    monkeypatch.setattr(runner, '_kill_process_group', kill_while_locked)
    monkeypatch.setattr(runner.subprocess, 'Popen', launch)
    monkeypatch.setattr(runner.time, 'sleep', interrupt_once)
    if cleanup_failure == 'unretired':
        monkeypatch.setattr(runner, '_wait_process_group', lambda _process: False)
    elif cleanup_failure == 'wait_error':
        monkeypatch.setattr(runner, '_stop_worker_group', lambda _process: (_ for _ in ()).throw(
            subprocess.TimeoutExpired('injected child wait', 5)))
    output = tmp_path / 'run'
    spec = SimpleNamespace(save=lambda path: path.write_text('{}'))
    previous_mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM, signal.SIGINT})
    previous_handler = signal.signal(signal.SIGALRM, alarm_handler)
    try:
        with pytest.raises(interruption, match='parent interruption sentinel'):
            runner.launch_worker(mode='oracle', spec=spec, catalog={}, provider='isaacsim',
                                 seed=0, horizon=5, output_dir=output, time_limit_s=30)
        if cleanup_failure != 'wait_error':
            assert children[0].poll() is not None
            with pytest.raises(ProcessLookupError):
                os.killpg(children[0].pid, 0)
            assert kill_signals[0] == signal.SIGTERM
        receipt = json.loads((output / 'native_run_receipt.json').read_text())
        assert receipt['status'] == ('TIMEOUT' if interruption is TimeoutError else 'INTERRUPTED')
        assert receipt['process_group_retired'] is (cleanup_failure is None)
        assert receipt['interruption_type'] == interruption.__name__
        if cleanup_failure is not None:
            blocker = runner.native_cleanup_blocker_path(lock_path)
            assert blocker.is_file()
            next_receipt = runner.launch_worker(
                mode='probe', spec=spec, catalog={}, provider='isaacsim', seed=1,
                horizon=5, output_dir=tmp_path / 'next', time_limit_s=30)
            assert next_receipt['status'] == 'BLOCKED_NATIVE_LOCK'
            assert len(children) == 1
        assert signal.pthread_sigmask(signal.SIG_BLOCK, set()).isdisjoint({signal.SIGALRM, signal.SIGINT})
        with lock_path.open('a') as contender:
            fcntl.flock(contender.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        signal.signal(signal.SIGALRM, previous_handler)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        for child in children:
            real_kill(child, signal.SIGKILL)
            child.wait(timeout=5)
