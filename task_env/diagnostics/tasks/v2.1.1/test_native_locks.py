import fcntl
import importlib.util
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('native_locks', Path(__file__).with_name('native_locks.py'))
native_locks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_locks)


def test_plan_deduplicates_aliases_but_locks_distinct_inodes(tmp_path):
    first, alias, second = (tmp_path / name for name in ('first', 'alias', 'second'))
    first.touch()
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


def test_plan_fails_closed_when_other_owner_holds_lock(tmp_path):
    path = tmp_path / 'lock'
    path.touch()
    handles = []
    with path.open('r+') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            native_locks.acquire_plan_locks([path], handles)
    assert not handles


def test_caller_can_release_first_lock_when_second_is_busy(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.touch()
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
