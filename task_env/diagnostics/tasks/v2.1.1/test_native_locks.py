import fcntl
import importlib.util
import os
from pathlib import Path
import runpy

import pytest


spec = importlib.util.spec_from_file_location('native_locks', Path(__file__).with_name('native_locks.py'))
native_locks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_locks)


def test_plan_deduplicates_aliases_but_locks_distinct_inodes(tmp_path, monkeypatch):
    first, alias, second = (tmp_path / name for name in ('first', 'alias', 'second'))
    first.touch()
    monkeypatch.setattr(native_locks, 'CANONICAL_LOCK', first)
    os.link(first, alias)
    second.touch()
    handles = []
    try:
        native_locks.acquire_plan_locks([first, alias, second], handles)
        assert len(handles) == 2
        for path in (alias, second):
            with path.open('r+') as other:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        for handle in handles:
            handle.close()


def test_plan_fails_closed_when_other_owner_holds_lock(tmp_path, monkeypatch):
    path = tmp_path / 'lock'
    path.touch()
    monkeypatch.setattr(native_locks, 'CANONICAL_LOCK', path)
    handles = []
    with path.open('r+') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            native_locks.acquire_plan_locks([path], handles)
    assert not handles


def test_caller_can_release_first_lock_when_second_is_busy(tmp_path, monkeypatch):
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.touch()
    monkeypatch.setattr(native_locks, 'CANONICAL_LOCK', first)
    second.touch()
    handles = []
    with second.open('r+') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(BlockingIOError):
                native_locks.acquire_plan_locks([first, second], handles)
            assert len(handles) == 1
        finally:
            for handle in reversed(handles):
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
    with first.open('r+') as available:
        fcntl.flock(available, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_old_plan_without_canonical_lock_fails_closed(tmp_path, monkeypatch):
    canonical, old = tmp_path / 'canonical', tmp_path / 'old'
    canonical.touch()
    os.link(canonical, old)
    monkeypatch.setattr(native_locks, 'CANONICAL_LOCK', canonical)
    handles = []
    with pytest.raises(ValueError, match='canonical'):
        native_locks.acquire_plan_locks([old], handles)
    assert not handles


def test_canonical_lock_missing_or_symlink_fails_closed(tmp_path, monkeypatch):
    canonical = tmp_path / 'canonical'
    monkeypatch.setattr(native_locks, 'CANONICAL_LOCK', canonical)
    with pytest.raises(FileNotFoundError):
        native_locks.acquire_plan_locks([canonical], [])
    target = tmp_path / 'target'
    target.touch()
    canonical.symlink_to(target)
    with pytest.raises(OSError):
        native_locks.acquire_plan_locks([canonical], [])


@pytest.mark.parametrize(('filename', 'entry', 'args', 'kwargs'), [
    ('f05_dg02_n1_supervisor.py', 'run', (None, None, None), {}),
    ('f05_dg02_native_supervisor.py', 'run', (), dict.fromkeys(
        ('python', 'worker', 'plan', 'plan_sha256', 'receipt', 'output_root', 'lock_path'))),
    ('r04b_native_supervisor.py', 'supervise', (), dict.fromkeys(
        ('lock_path', 'output', 'worker_output', 'worktree', 'python', 'worker_script', 'wait_lock_s'))),
    ('r05b_native_feedback_supervisor.py', 'run', (None, None, None), {}),
    ('r06b_order_supervisor.py', 'run_supervisor', (None,), {}),
])
def test_historical_native_supervisor_is_retired(filename, entry, args, kwargs):
    module = runpy.run_path(str(Path(__file__).resolve().parent.parent / filename), run_name='lock_test')
    with pytest.raises(RuntimeError, match='retired historical native supervisor'):
        module[entry](*args, **kwargs)
