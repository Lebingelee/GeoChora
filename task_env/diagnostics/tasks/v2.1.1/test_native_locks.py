import fcntl
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

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


def test_transport_forwards_supervised_lock_fd(tmp_path, monkeypatch):
    from task_env.runtime.sessions import transport
    from task_env.utils import _paths

    core, geophys = tmp_path / 'core', tmp_path / 'geophys'
    lock = core / 'workspace/locks/shared_native_execution.lock'
    lock.parent.mkdir(parents=True)
    lock.touch()
    (geophys / 'src').mkdir(parents=True)
    monkeypatch.setattr(_paths, 'GEOCHORA_ROOT', core)
    monkeypatch.setattr(_paths, 'GEOPHYS_PROVIDER_ROOT', geophys)
    captured = {}

    def intercept(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError('synthetic stop before launch')

    monkeypatch.setattr(transport.subprocess, 'Popen', intercept)
    payload = {'core_root': str(core), 'geophys_src': str(geophys / 'src'),
               'environment': {'python': str(Path(sys.executable).resolve())},
               'selection': {'physics_provider': 'mujoco'}}
    with lock.open('r+') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setenv('GEOCHORA_SUPERVISED_NATIVE_LOCK_FD', str(held.fileno()))
        with pytest.raises(RuntimeError, match='synthetic stop'):
            transport.start_selected_worker(sys.executable, payload)
        assert held.fileno() in captured['pass_fds']
        assert captured['env']['GEOCHORA_SUPERVISED_PARENT_PID'] == str(os.getpid())


def test_runtime_bootstrap_dies_with_supervised_parent(tmp_path):
    from task_env.runtime.sessions.transport import _WORKER_BOOTSTRAP

    lock, ready = tmp_path / 'lock', tmp_path / 'ready'
    lock.touch()
    bootstrap = _WORKER_BOOTSTRAP.split('core, geophys, fd, launcher_mode =', 1)[0]
    bootstrap += "\nimport pathlib,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)\n"
    parent_code = r'''import fcntl,os,subprocess,sys,time
f=open(sys.argv[1],'r+'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
env=dict(os.environ,GEOCHORA_SUPERVISED_NATIVE_LOCK_FD=str(f.fileno()),GEOCHORA_SUPERVISED_PARENT_PID=str(os.getpid()))
subprocess.Popen([sys.executable,'-I','-S','-c',sys.argv[2],sys.argv[3]],env=env,pass_fds=(f.fileno(),),start_new_session=True)
time.sleep(60)
'''
    parent = subprocess.Popen([sys.executable, '-c', parent_code, str(lock), bootstrap, str(ready)])
    runtime_pid = None
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and parent.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists()
        runtime_pid = int(ready.read_text())
        with lock.open('r+') as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            parent.kill()
            parent.wait(timeout=10)
            deadline = time.monotonic() + 10
            while True:
                try:
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    assert time.monotonic() < deadline
                    time.sleep(.05)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if runtime_pid is not None:
            try:
                os.killpg(runtime_pid, 9)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize('termination_signal', [15, 9])
def test_real_transport_forwards_lock_to_bootstrapped_detached_worker(tmp_path, termination_signal):
    root = Path(__file__).resolve().parents[4]
    core, geophys = tmp_path / 'core', tmp_path / 'geophys'
    lock = core / 'workspace/locks/shared_native_execution.lock'
    lock.parent.mkdir(parents=True)
    lock.touch()
    (geophys / 'src').mkdir(parents=True)
    ready = tmp_path / 'ready'
    fake_session = r'''import socket,struct,json,time
s=socket.socket(fileno=int(fd))
def exact(n):
 b=b''
 while len(b)<n: b+=s.recv(n-len(b))
 return b
n=struct.unpack('!I',exact(4))[0]; request=json.loads(exact(n))
reply={'kind':'ready','request_identity':request['request_identity'],
       'materialization_id':'fake','methods':[],'properties':[]}
data=json.dumps(reply).encode();s.sendall(struct.pack('!I',len(data))+data)
time.sleep(60)
'''
    parent_code = r'''import fcntl,os,pathlib,sys,time
sys.path.insert(0,sys.argv[1])
from task_env.runtime.sessions import transport
from task_env.utils import _paths
_paths.GEOCHORA_ROOT=pathlib.Path(sys.argv[2]); _paths.GEOPHYS_PROVIDER_ROOT=pathlib.Path(sys.argv[3])
transport._WORKER_BOOTSTRAP=transport._WORKER_BOOTSTRAP.replace("runpy.run_module('task_env.runtime.sessions.worker', run_name='__main__')",sys.argv[5])
f=open(sys.argv[4],'r+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
os.environ['GEOCHORA_SUPERVISED_NATIVE_LOCK_FD']=str(f.fileno())
payload={'core_root':sys.argv[2],'geophys_src':str(pathlib.Path(sys.argv[3])/'src'),
         'environment':{'python':str(pathlib.Path(sys.executable).resolve())},'selection':{'physics_provider':'mujoco'}}
session=transport.start_selected_worker(sys.executable,payload,timeout=10)
pathlib.Path(sys.argv[6]).write_text(str(session._process.pid))
time.sleep(60)
'''
    parent = subprocess.Popen([sys.executable, '-c', parent_code, str(root), str(core), str(geophys),
                               str(lock), fake_session, str(ready)])
    runtime_pid = None
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and parent.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists()
        runtime_pid = int(ready.read_text())
        with lock.open('r+') as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            parent.send_signal(termination_signal)
            parent.wait(timeout=10)
            deadline = time.monotonic() + 10
            while True:
                try:
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    assert time.monotonic() < deadline
                    time.sleep(.05)
        stat_path = Path(f'/proc/{runtime_pid}/stat')
        try:
            state = stat_path.read_text().split()[2]
        except FileNotFoundError:
            state = 'exited'
        assert state in ('Z', 'exited')
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if runtime_pid is not None:
            try:
                os.killpg(runtime_pid, 9)
            except ProcessLookupError:
                pass


def test_real_transport_rejects_parent_death_before_prctl(tmp_path):
    root = Path(__file__).resolve().parents[4]
    core, geophys = tmp_path / 'core', tmp_path / 'geophys'
    lock = core / 'workspace/locks/shared_native_execution.lock'
    lock.parent.mkdir(parents=True)
    lock.touch()
    (geophys / 'src').mkdir(parents=True)
    before_prctl, after_prctl = tmp_path / 'before', tmp_path / 'after'
    parent_code = r'''import fcntl,os,pathlib,sys,time
sys.path.insert(0,sys.argv[1])
from task_env.runtime.sessions import transport
from task_env.utils import _paths
_paths.GEOCHORA_ROOT=pathlib.Path(sys.argv[2]); _paths.GEOPHYS_PROVIDER_ROOT=pathlib.Path(sys.argv[3])
marker="pathlib.Path(%r).write_text(str(os.getpid())); import time; time.sleep(2)\n" % sys.argv[5]
transport._WORKER_BOOTSTRAP=transport._WORKER_BOOTSTRAP.replace("if os.environ.get('GEOCHORA_SUPERVISED_NATIVE_LOCK_FD') is not None:",marker+"if os.environ.get('GEOCHORA_SUPERVISED_NATIVE_LOCK_FD') is not None:")
transport._WORKER_BOOTSTRAP=transport._WORKER_BOOTSTRAP.replace("core, geophys, fd, launcher_mode = sys.argv[1:]","pathlib.Path(%r).write_text('unsafe')\ncore, geophys, fd, launcher_mode = sys.argv[1:]" % sys.argv[6])
f=open(sys.argv[4],'r+'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
os.environ['GEOCHORA_SUPERVISED_NATIVE_LOCK_FD']=str(f.fileno())
payload={'core_root':sys.argv[2],'geophys_src':str(pathlib.Path(sys.argv[3])/'src'),
         'environment':{'python':str(pathlib.Path(sys.executable).resolve())},'selection':{'physics_provider':'mujoco'}}
transport.start_selected_worker(sys.executable,payload,timeout=10)
'''
    parent = subprocess.Popen([sys.executable, '-c', parent_code, str(root), str(core), str(geophys),
                               str(lock), str(before_prctl), str(after_prctl)])
    runtime_pid = None
    try:
        deadline = time.monotonic() + 10
        while not before_prctl.exists() and parent.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert before_prctl.exists()
        runtime_pid = int(before_prctl.read_text())
        parent.kill()
        parent.wait(timeout=10)
        deadline = time.monotonic() + 10
        with lock.open('r+') as contender:
            while True:
                try:
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    assert time.monotonic() < deadline
                    time.sleep(.05)
        assert not after_prctl.exists()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if runtime_pid is not None:
            try:
                os.killpg(runtime_pid, 9)
            except ProcessLookupError:
                pass
