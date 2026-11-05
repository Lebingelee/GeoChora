"""No-engine worker fixtures cover only the transport contract."""
import os
import socket
import subprocess
import sys

import pytest

from task_env.runtime.sessions.transport import RemoteSession, _encode


WORKER = r'''
import importlib.abc, os, socket, sys, time
class BlockNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco','taichi','taichi_forge','scene','solvers','geophys','isaacsim','omni','carb','pxr','isaaclab','sapien','genesis','warp'}:
            raise AssertionError('native import forbidden: ' + fullname)
sys.meta_path.insert(0, BlockNative())
from task_env.runtime.sessions.transport import serve_session
class FakeSession:
    provider_materialization_id = 'fake-materialization'
    def __init__(self): self._episode = None; self._revision = 0; self._closed = False
    @property
    def episode_id(self):
        if self._episode is None: raise RuntimeError('no episode')
        return self._episode
    @property
    def state_revision(self): return self._revision
    @property
    def native_interval_evidence(self):
        return {'position_ack': {'partial': False}, 'advances': [{'step': 1}],
                'advance_attempts': 1, 'provenance_kind': 'synthetic_fixture'}
    def reset(self, value): self._episode = value; return {'episode': value, 'items': [1, 2]}
    def reset_plan(self, value): self._episode = value; return {'episode': value}
    def snapshot(self): return {'episode': self._episode, 'revision': self._revision}
    def step(self): self._revision += 1; return self.snapshot()
    def control_feedback(self, value): raise ValueError('fixture failure')
    def apply_control(self, value): return value
    def step_control_interval(self, target, servo, *, interval_observer=None, arm_schedule=None):
        if arm_schedule: arm_schedule.begin(target)
        value, diag = servo.inner_gripper_step({'state': 1}, {'feedback': 2})
        if arm_schedule: value = arm_schedule.target(value, 0, 1); arm_schedule.applied(value)
        if interval_observer: interval_observer(0, value, diag)
        return (value, diag)
    def close(self):
        if not self._closed:
            self._closed = True
            with open(sys.argv[2], 'a') as f: f.write('close\n')
sock = socket.socket(fileno=int(sys.argv[1]))
serve_session(sock, FakeSession(), 'a' * 64)
'''


def _spawn(tmp_path, *, code=WORKER, identity='a' * 64, timeout=5):
    parent, child = socket.socketpair()
    path = tmp_path / 'closed.txt'
    process = subprocess.Popen([sys.executable, '-c', code, str(child.fileno()), str(path)],
        pass_fds=(child.fileno(),), env=os.environ.copy(), start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child.close()
    try:
        proxy = RemoteSession(process, parent, identity, timeout=timeout)
    except BaseException:
        parent.close()
        raise
    return proxy, process, path


def test_worker_dispatch_callbacks_owned_values_and_idempotent_close(tmp_path):
    session, process, path = _spawn(tmp_path)
    class Servo:
        def inner_gripper_step(self, state, feedback): return (state['state'] + feedback['feedback'], {'ok': True})
    class Schedule:
        def begin(self, target): self.target0 = target
        def target(self, target, index, count): return target + index + count
        def applied(self, target): self.applied_target = target
    observed = []
    schedule = Schedule()
    try:
        assert session.reset('episode-a') == {'episode': 'episode-a', 'items': [1, 2]}
        assert session.episode_id == 'episode-a'
        assert session.reset_plan('episode-b') == {'episode': 'episode-b'}
        assert session.episode_id == 'episode-b'
        assert session.native_interval_evidence['provenance_kind'] == 'synthetic_fixture'
        assert session.native_interval_evidence['advances'] == [{'step': 1}]
        assert session.step()['revision'] == 1
        from task_env.artifacts import CanonicalStateView
        state = CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz', 1, .01, {}, {}, {})
        assert session.apply_control(state) == state
        result = session.step_control_interval('target', Servo(), arm_schedule=schedule,
                                               interval_observer=lambda *args: observed.append(args))
        assert result == (4, {'ok': True})
        assert schedule.target0 == 'target' and schedule.applied_target == 4
        assert observed == [(0, 4, {'ok': True})]
        with pytest.raises(ValueError, match='fixture failure') as failure:
            session.control_feedback({})
        assert failure.value.phase == 'worker_operation'
        assert failure.value.reason == 'remote_ValueError'
        assert failure.value.request_identity == 'a' * 64
    finally:
        session.close()
        session.close()
    assert process.poll() == 0
    assert path.read_text() == 'close\n'


def test_worker_rejects_non_value_before_sending_and_wrong_startup_identity(tmp_path):
    with pytest.raises(TypeError, match='non-value'):
        _encode(object())
    with pytest.raises(ValueError, match='startup identity mismatch'):
        _spawn(tmp_path, identity='b' * 64)


def test_episode_tamper_stops_worker_and_timeout_exits_process(tmp_path):
    session, process, _path = _spawn(tmp_path)
    session.reset('episode-a')
    session._episode_id = 'wrong-episode'
    with pytest.raises((EOFError, OSError)):
        session.snapshot()
    assert process.poll() is not None
    session.close()

    slow_code = WORKER.replace("def step(self): self._revision += 1; return self.snapshot()",
                               "def step(self): time.sleep(5); return self.snapshot()")
    slow, process, _path = _spawn(tmp_path, code=slow_code, timeout=5)
    slow.reset('episode-b')
    slow._sock.settimeout(.2)
    with pytest.raises((TimeoutError, OSError)):
        slow.step()
    assert process.poll() is not None
    slow.close()


PRODUCTION_BOOTSTRAP_FAKE_SESSION = r'''
import importlib.abc, importlib.machinery, importlib.util, pathlib, sys, sysconfig
core, geophys, fd, launcher_mode = sys.argv[1:]
prefix = str(pathlib.Path(sys.executable).parent.parent)
paths = sysconfig.get_paths(vars={'base': prefix, 'platbase': prefix})
sys.path[:0] = [core, geophys, paths['purelib'], paths['platlib']]
class BlockNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco','taichi','taichi_forge','scene','solvers','geophys','isaacsim','omni','carb','pxr','isaaclab','sapien','genesis','warp'}:
            raise AssertionError('native import forbidden: ' + fullname)
sys.meta_path.insert(0, BlockNative())
real_find_spec = importlib.util.find_spec
def find_spec(name, package=None):
    if name in {'geophys','mujoco','control','scene','simulation','solvers'}:
        return importlib.machinery.PathFinder.find_spec(name, sys.path)
    return real_find_spec(name, package)
importlib.util.find_spec = find_spec
from task_env.runtime.sessions import api, worker
class FakeSession:
    provider_materialization_id = 'fixture-materialization'
    def __init__(self): self._episode = None
    @property
    def episode_id(self):
        if self._episode is None: raise RuntimeError('no episode')
        return self._episode
    @property
    def state_revision(self): return 0
    def reset(self, sample): self._episode = 'fixture-episode'; return sample
    def close(self): pass
api._materialize_admitted = lambda *args, **kwargs: FakeSession()
sys.argv = ['worker', fd]
worker.main()
'''


@pytest.mark.parametrize('use_launcher', [False, True])
def test_production_worker_rebuilds_real_source_and_dispatches_to_fixture(monkeypatch, tmp_path, use_launcher):
    from task_env import make_env
    from task_env.artifacts import ExecutionSpec
    from task_env.runtime.sessions import transport
    from task_env.runtime.sessions.api import PROFILE
    from task_env.runtime.sessions.provenance import probe_interpreter_environment
    from task_env.utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT

    env = make_env('pick-cube-p16-reference-v1', config={'provider': 'mujoco'})
    try:
        execution = ExecutionSpec('mujoco', PROFILE, 'none', 'cpu', 0, 'strict')
        source = env.value['source']
        from dataclasses import replace
        from task_env.runtime.sessions import provenance
        interpreter = sys.executable
        if use_launcher:
            import shlex
            launcher = tmp_path / 'SDK with spaces' / 'python.sh'
            launcher.parent.mkdir()
            launcher.write_text('#!/bin/sh\nprintf "SDK launcher log\\n"\nexec '
                                + shlex.quote(sys.executable) + ' "$@"\n')
            launcher.chmod(0o755)
            interpreter = str(launcher)
        observed = probe_interpreter_environment(interpreter)
        monkeypatch.setattr(provenance, 'probe_interpreter_environment', lambda _: observed)
        selection = replace(env.resolved_public_config.execution_spec_v2,
                            deployment='isolated_worker', interpreter=interpreter)
        preflight = provenance.preflight_selected_deployment(
            selection, requested={'deployment': 'isolated_worker'}, task_uid=env.uid,
            artifact=env.artifact, source=source, controller=env.value['controller'], seed=31,
            binding=env.binding, value=env.value,
        )
        payload = {
            'uid': env.uid, 'config': {k: v for k, v in env._recorded_execution_configuration().items() if k != 'env_id'},
            'seed': 31, 'execution': execution.to_mapping(), 'selection': selection.to_mapping(),
            'facts': transport.source_execution_facts(env.artifact, execution, source, env.value['controller']),
            'preflight_request_identity': preflight['request_identity'],
            'preflight_identity_facts': preflight['identity_facts'],
            'core_root': str(GEOCHORA_ROOT), 'geophys_src': str(GEOPHYS_PROVIDER_ROOT / 'src'),
            'environment': observed,
        }
        monkeypatch.setattr(transport, '_WORKER_BOOTSTRAP', PRODUCTION_BOOTSTRAP_FAKE_SESSION)
        monkeypatch.chdir(tmp_path)
        session = transport.start_selected_worker(interpreter, payload)
        try:
            sample = env.binding.reset_sample(env.artifact, 31)
            assert session.reset(sample) == sample
            assert session.episode_id == 'fixture-episode'
        finally:
            session.close()
        assert session._process.poll() == 0
        wrong = {**payload, 'facts': {**payload['facts'], 'source_xml_sha256': '0' * 64}}
        with pytest.raises(ValueError, match='identity mismatch'):
            transport.start_selected_worker(interpreter, wrong)
    finally:
        env.close()


def test_public_factory_remote_rejects_unchecked_fixture(monkeypatch):
    """A synthetic session without the production layout check cannot reset."""
    from task_env import make_env
    from task_env.runtime.sessions import transport
    fake_bootstrap = PRODUCTION_BOOTSTRAP_FAKE_SESSION.replace(
        "api._materialize_admitted = lambda *args, **kwargs: FakeSession()",
        "from task_env.diagnostics.tasks.test_selected_consumers import FakeSession as FixtureSession\n"
        "from task_env.runtime.sessions import control\n"
        "control.materialize_control = FixtureSession",
    )
    monkeypatch.setattr(transport, '_WORKER_BOOTSTRAP', fake_bootstrap)
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'isolated_worker',
                      'interpreter': sys.executable},
        'episode': {'horizon': 3}, 'task': {'controller_profile': 'r3_continuous_v1'},
    })
    try:
        with pytest.raises(RuntimeError, match='layout was not checked'):
            env.reset(seed=31)
    finally:
        env.close()


def test_malformed_json_reply_terminates_owned_worker(tmp_path):
    from task_env.runtime.sessions.transport import TransportProtocolError
    server = WORKER.replace(
        "serve_session(sock, FakeSession(), 'a' * 64)",
        "from task_env.runtime.sessions.transport import _send, _receive\n"
        "_send(sock, {'kind':'ready', 'request_identity':'a'*64, "
        "'materialization_id':'fake-materialization', 'methods':['snapshot'], 'properties':[]})\n"
        "_receive(sock)\n_send(sock, [])\ntime.sleep(30)",
    )
    session, process, _ = _spawn(tmp_path, code=server)
    with pytest.raises(TransportProtocolError, match='JSON object'):
        session.snapshot()
    assert process.poll() is not None
    session.close()
