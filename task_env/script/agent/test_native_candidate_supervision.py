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


@pytest.mark.parametrize('interruption', [TimeoutError, KeyboardInterrupt])
def test_parent_interruption_retires_worker_before_releasing_lock(tmp_path, monkeypatch, interruption):
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
        if sleeps == 1:
            raise interruption('parent interruption sentinel')
        real_sleep(seconds)

    monkeypatch.setattr(runner, 'isaac_python', lambda: Path(sys.executable))
    monkeypatch.setattr(runner, 'native_lock_path', lambda: lock_path)
    monkeypatch.setattr(runner, '_mem_available_bytes', lambda: 12 * 1024**3)
    monkeypatch.setattr(runner, '_gpu_free_mib', lambda: 7000)
    monkeypatch.setattr(runner, '_proc_rss_tree', lambda _pid: 1024)
    monkeypatch.setattr(runner, '_core_site', lambda: tmp_path)
    monkeypatch.setattr(runner, '_populate_isaac_core_site_overlay', lambda *_: {})
    monkeypatch.setattr(runner, '_set_child_affinity', lambda: None)
    monkeypatch.setattr(runner, '_kill_process_group', kill_while_locked)
    monkeypatch.setattr(runner.subprocess, 'Popen', launch)
    monkeypatch.setattr(runner.time, 'sleep', interrupt_once)
    output = tmp_path / 'run'
    spec = SimpleNamespace(save=lambda path: path.write_text('{}'))
    try:
        with pytest.raises(interruption, match='parent interruption sentinel'):
            runner.launch_worker(mode='oracle', spec=spec, catalog={}, provider='isaacsim',
                                 seed=0, horizon=5, output_dir=output, time_limit_s=30)
        assert children[0].poll() is not None
        with pytest.raises(ProcessLookupError):
            os.killpg(children[0].pid, 0)
        assert kill_signals[0] == signal.SIGTERM
        receipt = json.loads((output / 'native_run_receipt.json').read_text())
        assert receipt['status'] == ('TIMEOUT' if interruption is TimeoutError else 'INTERRUPTED')
        assert receipt['process_group_retired'] is True
        assert receipt['interruption_type'] == interruption.__name__
        with lock_path.open('a') as contender:
            fcntl.flock(contender.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        for child in children:
            real_kill(child, signal.SIGKILL)
            child.wait(timeout=5)
