"""Worker source ownership uses the same lifecycle as the scalar Env."""
import socket
import threading
from types import SimpleNamespace

import pytest


def test_worker_initial_build_failure_releases_binding_and_keeps_primary_error(monkeypatch):
    import sys
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions import provenance, worker
    from task_env.runtime.sessions.transport import request_identity
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'deployment': 'isolated_worker',
                      'interpreter': sys.executable}, 'episode': {'horizon': 8},
    })
    calls = []
    primary = ValueError('worker source build failed')
    def initial(*, seed):
        raise primary
    def close():
        calls.append('task')
        raise OSError('task cleanup failed')
    binding = SimpleNamespace(reset_reconstruction_strategy=lambda *_args: SimpleNamespace(initial=initial),
                              close_task_resources=close)
    monkeypatch.setattr(PickCubeReferenceEnv, '_build_selected_binding', lambda _config: binding)
    dependency = {'status': 'available'}
    monkeypatch.setattr(provenance, 'assess_declared_dependencies', lambda *_args, **_kwargs: dependency)
    facts = {'selection': config.execution_spec_v2.to_mapping(), 'environment': {},
             'task_uid': PickCubeReferenceEnv.uid, 'seed': 31, 'dependency': dependency}
    payload = {'uid': PickCubeReferenceEnv.uid, 'config': config,
               'selection': config.execution_spec_v2.to_mapping(), 'environment': {}, 'seed': 31,
               'preflight_identity_facts': facts, 'preflight_request_identity': request_identity(facts)}
    with pytest.raises(ValueError, match='worker source build failed') as caught:
        worker._materialize_selected(payload)
    assert caught.value is primary
    assert calls == ['task']
    assert any('task cleanup failed' in note for note in caught.value.__notes__)
    from task_env.runtime.sessions.transport import _error, _raise_remote
    with pytest.raises(ValueError, match='worker source build failed') as remote:
        _raise_remote(_error(caught.value), phase='worker_startup')
    assert any('task cleanup failed' in note for note in remote.value.__notes__)


@pytest.mark.parametrize('source_fails', [False, True])
def test_worker_close_response_includes_source_and_task_cleanup(source_fails):
    from task_env.runtime.sessions.source import close_source_and_task_resources
    from task_env.runtime.sessions.transport import _receive, _send, serve_session

    events = []
    def source_close():
        events.append('source')
        if source_fails:
            raise OSError('source cleanup failed')
    source = SimpleNamespace(source_snapshot_receipt=SimpleNamespace(close=source_close))
    binding = SimpleNamespace(close_task_resources=lambda: events.append('task'))
    session = SimpleNamespace(provider_materialization_id='materialization',
        close=lambda: events.append('session'), close_runtime_owner=lambda: events.append('runtime'))
    def close_owned():
        error = close_source_and_task_resources(source, binding)
        if error is not None:
            raise error
    server, client = socket.socketpair()
    outcomes = []
    thread = threading.Thread(target=lambda: outcomes.append(serve_session(
        server, session, 'request', close_owned=close_owned)))
    thread.start()
    try:
        assert _receive(client)['kind'] == 'ready'
        _send(client, {'kind': 'call', 'request_identity': 'request', 'sequence': 1,
                       'materialization_id': 'materialization', 'method': 'close'})
        reply = _receive(client)
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert events == ['session', 'runtime', 'source', 'task']
        assert outcomes == [not source_fails]
        if source_fails:
            assert 'source cleanup failed' in reply['error']['message']
        else:
            assert reply['error'] is None
    finally:
        client.close()
        server.close()


def test_worker_handler_setup_failure_closes_materialized_session_and_sources(monkeypatch):
    import sys
    import task_env.artifacts as artifacts
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions import api, control, provenance, worker
    from task_env.runtime.sessions.transport import request_identity
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'deployment': 'isolated_worker',
                      'interpreter': sys.executable}, 'episode': {'horizon': 8},
    })
    events = []
    class Session:
        @property
        def apply_control(self):
            raise ValueError('handler setup failed')
        def close(self):
            events.append('session')
        def close_runtime_owner(self):
            events.append('runtime')
    source = SimpleNamespace(source_snapshot_receipt=SimpleNamespace(close=lambda: events.append('source')))
    artifact = SimpleNamespace(timebase=SimpleNamespace(to_mapping=lambda: {'dt': .01}))
    value = {'artifact': artifact, 'source': source, 'controller': object()}
    binding = SimpleNamespace(reset_reconstruction_strategy=lambda *_args: SimpleNamespace(initial=lambda **_kwargs: value),
        scalar_control_binding=None, interval_mode='grouped', close_task_resources=lambda: events.append('task'))
    monkeypatch.setattr(PickCubeReferenceEnv, '_build_selected_binding', lambda _config: binding)
    monkeypatch.setattr(provenance, 'assess_declared_dependencies', lambda *_args, **_kwargs: {'status': 'available'})
    execution = artifacts.ExecutionSpec('mujoco', 'profile', 'none', 'cpu', 0, 'strict')
    monkeypatch.setattr(artifacts, 'decode_execution_spec', lambda _value: execution)
    facts = {key: key for key in ('artifact_identity', 'source_id', 'source_bindings',
             'source_xml_sha256', 'source_closure', 'scene_identity', 'controller_identities')}
    identity = {**facts, 'selection': config.execution_spec_v2.to_mapping(), 'environment': {},
                'task_uid': PickCubeReferenceEnv.uid, 'seed': 31, 'dependency': {'status': 'available'},
                'timebase': {'dt': .01}, 'assessment_rows': [], 'control_binding_plan': None}
    monkeypatch.setattr(worker, 'source_execution_facts', lambda *_args: facts)
    monkeypatch.setattr(api, 'assess_selected_request', lambda **_kwargs:
                        SimpleNamespace(to_mapping=lambda: {'rows': []}, decision='admitted'))
    monkeypatch.setattr(control, 'bind_selected_controller', lambda *_args, **_kwargs:
                        SimpleNamespace(position_profiles=(), position=False, controller=object()))
    monkeypatch.setattr(control, 'materialize_control', lambda *_args, **_kwargs: Session())
    payload = {'uid': PickCubeReferenceEnv.uid, 'config': config, 'execution': {}, 'facts': facts,
               'selection': config.execution_spec_v2.to_mapping(), 'environment': {}, 'seed': 31,
               'preflight_identity_facts': identity, 'preflight_request_identity': request_identity(identity)}
    with pytest.raises(ValueError, match='handler setup failed'):
        worker._materialize_selected(payload)
    assert events == ['session', 'runtime', 'source', 'task']


def test_worker_preserves_all_cleanup_failures_after_session_error():
    from task_env.runtime.sessions.source import close_source_and_task_resources
    from task_env.runtime.sessions.transport import _receive, _send, serve_session

    def fail(message):
        raise RuntimeError(message)
    source = SimpleNamespace(source_snapshot_receipt=SimpleNamespace(close=lambda: fail('source failed')))
    binding = SimpleNamespace(close_task_resources=lambda: fail('task failed'))
    session = SimpleNamespace(provider_materialization_id='materialization',
        close=lambda: fail('session failed'), close_runtime_owner=lambda: None)
    def close_owned():
        error = close_source_and_task_resources(source, binding)
        if error is not None:
            raise error
    server, client = socket.socketpair()
    outcomes = []
    thread = threading.Thread(target=lambda: outcomes.append(serve_session(
        server, session, 'request', close_owned=close_owned)))
    thread.start()
    try:
        _receive(client)
        _send(client, {'kind': 'call', 'request_identity': 'request', 'sequence': 1,
                       'materialization_id': 'materialization', 'method': 'close'})
        reply = _receive(client)
        thread.join(timeout=5)
        assert not thread.is_alive() and outcomes == [False]
        assert 'session failed' in reply['error']['message']
        assert any('source failed' in note for note in reply['error']['notes'])
        assert any('task failed' in note for note in reply['error']['notes'])
    finally:
        client.close()
        server.close()


@pytest.mark.parametrize(('uid', 'provider', 'starts_app'), [
    ('pick-cube-p16-reference-v1', 'isaacsim', True),
    ('pendulum-v1', 'isaacsim', True),
    ('two-wheel-balance-v1', 'isaacsim', True),
    ('nut-assembly-outcome-reference-v1', 'mujoco', False),
])
def test_worker_prepares_isaac_by_provider_before_task_source(monkeypatch, uid, provider, starts_app):
    import os
    import sys
    from task_env.runtime.sessions import isaac_native_io, worker
    from task_env.runtime.sessions.transport import request_identity

    payload = {'uid': uid, 'selection': {'physics_provider': provider}}
    identity = request_identity(payload)
    events, responses = [], []
    class Owner:
        def open(self, **kwargs):
            events.append(('app-open', kwargs))
        def close(self):
            events.append(('app-close',))
    monkeypatch.setattr(isaac_native_io, '_process_app_owner', lambda **_kwargs: Owner())
    monkeypatch.setattr(worker, '_receive', lambda _sock: {
        'kind': 'build', 'request_identity': identity, 'payload': payload})
    monkeypatch.setattr(worker, '_validate_environment', lambda _payload: None)
    def fail_build(_payload):
        events.append(('source',))
        raise ValueError('source build failed')
    monkeypatch.setattr(worker, '_materialize_selected', fail_build)
    monkeypatch.setattr(worker, '_send', lambda _sock, response: responses.append(response))
    monkeypatch.setattr(worker, '_write_runtime_scope_receipt', lambda: None)
    server, client = socket.socketpair()
    worker_fd = os.dup(server.fileno())
    monkeypatch.setattr(sys, 'argv', ['worker', str(worker_fd)])
    try:
        result = worker.main()
        assert result == (1 if starts_app else None)
        assert responses[0]['kind'] == 'startup_error'
        if starts_app:
            assert events == [('app-open', {'f06_compatibility': True}), ('source',), ('app-close',)]
        else:
            assert events == [('source',)]
    finally:
        server.close()
        client.close()


@pytest.mark.parametrize('close_fails', [False, True])
def test_worker_app_open_failure_still_closes_owner(monkeypatch, close_fails):
    import os
    import sys
    from task_env.runtime.sessions import isaac_native_io, worker
    from task_env.runtime.sessions.transport import request_identity

    payload = {'uid': 'pendulum-v1', 'selection': {'physics_provider': 'isaacsim'}}
    events, replies = [], []
    class Owner:
        def open(self, **_kwargs):
            events.append('open')
            raise RuntimeError('open failed')
        def close(self):
            events.append('close')
            if close_fails:
                raise RuntimeError('close failed')
    monkeypatch.setattr(isaac_native_io, '_process_app_owner', lambda **_kwargs: Owner())
    monkeypatch.setattr(worker, '_receive', lambda _sock: {
        'kind': 'build', 'request_identity': request_identity(payload), 'payload': payload})
    monkeypatch.setattr(worker, '_validate_environment', lambda _payload: None)
    monkeypatch.setattr(worker, '_send', lambda _sock, reply: replies.append(reply))
    monkeypatch.setattr(worker, '_write_runtime_scope_receipt', lambda: None)
    monkeypatch.setattr(worker, '_materialize_selected', lambda _payload: pytest.fail('unexpected build'))
    server, client = socket.socketpair()
    monkeypatch.setattr(sys, 'argv', ['worker', str(os.dup(server.fileno()))])
    try:
        if close_fails:
            with pytest.raises(RuntimeError, match='close failed'):
                worker.main()
        else:
            assert worker.main() == 1
        assert events == ['open', 'close']
        assert replies[0]['kind'] == 'startup_error'
        assert 'open failed' in replies[0]['error']['message']
    finally:
        server.close()
        client.close()


@pytest.mark.parametrize(('deployment', 'expected'), [
    ('in_process', ['app-open']),
    ('isolated_worker', []),
])
def test_parent_only_opens_isaac_for_in_process_source(monkeypatch, deployment, expected):
    from contextlib import contextmanager
    import sys
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions import isaac_native_io, provenance
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                      'physics_device': 'cuda:0', 'deployment': deployment,
                      'interpreter': sys.executable},
        'episode': {'horizon': 8},
    })
    events = []
    @contextmanager
    def app_source(**_kwargs):
        events.append('app-open')
        yield
    class SourceConstructionReached(Exception):
        pass
    def stop_before_source(_cls, _config):
        raise SourceConstructionReached()
    monkeypatch.setattr(provenance, 'preflight_selected_source', lambda *_a, **_k: None)
    monkeypatch.setattr(isaac_native_io, 'prepare_isaac_source', app_source)
    monkeypatch.setattr(PickCubeReferenceEnv, '_build_selected_binding', classmethod(stop_before_source))
    with pytest.raises(SourceConstructionReached):
        PickCubeReferenceEnv.from_resolved_config(config)
    assert events == expected
