"""Bounded JSON transport for one existing scalar RuntimeSession.

The worker owns the existing RuntimeSession. Only explicitly registered
Core value contracts cross the socket; SDK objects, handles and callables do
not. This module does not own another physics or episode lifecycle.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import math
import os
import signal
import socket
import struct
import subprocess

_MAX_FRAME = 16 * 1024 * 1024


class TransportProtocolError(ValueError):
    """The worker or connection violated the session transport protocol."""

_METHODS = frozenset({
    'reset', 'reset_plan', 'snapshot', 'snapshot_v1', 'snapshot_v2',
    'control_feedback', 'native_control_feedback_sample', 'apply_control',
    'step', 'step_control_interval', 'apply_mixed_actuator_command',
    'bind_mixed_controller', 'step_mixed_actuator_interval',
    'position_preflight', 'position_apply',
})
_PROPERTIES = frozenset({
    'provider_materialization_id', 'episode_id', 'state_revision',
    'runtime_progress_receipt', 'reset_readback_v1', 'compiled_layout_receipt',
    'reset_plan_evidence', 'close_receipt', 'build_layout_facts', 'native_interval_evidence',
})


def _types():
    from ...artifacts import (CanonicalStateView, CanonicalStateViewV1,
        CanonicalStateViewV2, CanonicalStatePublicationV1, CanonicalStatePublicationV2,
        SceneDefinition, JointDefinition, FrameReference, StateRequirements)
    from ...artifacts.execution import (ResetSample, ResetSampleV1, ResetPlanV1,
        EpisodeResetPlanV1, RealizedInitialState)
    from ...controllers.canonical.contracts import (CanonicalControlTarget,
        AppliedCanonicalControl, GripperControlTarget, MixedActuatorCommandV1,
        AppliedMixedActuatorCommandV1, PositionControlTargetV1)
    from ...controllers.canonical.feedback import (CanonicalControlFeedback,
        NativeControlFeedbackSampleV1)
    values = (CanonicalStateView, CanonicalStateViewV1, CanonicalStateViewV2,
        CanonicalStatePublicationV1, CanonicalStatePublicationV2, SceneDefinition,
        JointDefinition, FrameReference, StateRequirements, ResetSample, ResetSampleV1,
        ResetPlanV1, EpisodeResetPlanV1, RealizedInitialState, CanonicalControlTarget,
        AppliedCanonicalControl, GripperControlTarget, MixedActuatorCommandV1,
        AppliedMixedActuatorCommandV1, PositionControlTargetV1, CanonicalControlFeedback,
        NativeControlFeedbackSampleV1)
    return {item.__name__: item for item in values}


def _encode(value):
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('transport refuses nonfinite numbers')
        return value
    known = _types()
    if type(value).__name__ in known and type(value) is known[type(value).__name__]:
        return {'$type': type(value).__name__, 'value': value.to_mapping()}
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value) or '$type' in value or '$tuple' in value:
            raise TypeError('transport mappings require string keys and reserve $type')
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return {'$tuple': [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    raise TypeError(f'transport refuses non-value type {type(value).__name__}')


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if '$tuple' in value:
            if set(value) != {'$tuple'} or not isinstance(value['$tuple'], list):
                raise ValueError('invalid transport tuple')
            return tuple(_decode(item) for item in value['$tuple'])
        if '$type' in value:
            if set(value) != {'$type', 'value'} or value['$type'] not in _types():
                raise ValueError('unknown transport contract')
            return _types()[value['$type']].from_mapping(value['value'])
        return {key: _decode(item) for key, item in value.items()}
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError('invalid transport value')


def _send(sock, message):
    raw = json.dumps(message, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > _MAX_FRAME:
        raise ValueError('transport frame exceeds limit')
    sock.sendall(struct.pack('!I', len(raw)) + raw)


def _receive(sock):
    def exact(count):
        data = bytearray()
        while len(data) < count:
            part = sock.recv(count - len(data))
            if not part:
                raise EOFError('runtime worker connection closed')
            data.extend(part)
        return bytes(data)
    size = struct.unpack('!I', exact(4))[0]
    if size > _MAX_FRAME:
        raise TransportProtocolError('transport frame exceeds limit')
    def bad_constant(_):
        raise TransportProtocolError('nonfinite transport JSON')
    def unique_pairs(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise TransportProtocolError('duplicate transport JSON key')
            result[key] = item
        return result
    try:
        value = json.loads(exact(size), parse_constant=bad_constant, object_pairs_hook=unique_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TransportProtocolError('invalid transport JSON') from exc
    if not isinstance(value, dict):
        raise TransportProtocolError('transport message must be a JSON object')
    return value


def _episode(session):
    try:
        return session.episode_id
    except RuntimeError:
        return None


def _error(error):
    return {'type': type(error).__name__, 'message': str(error)}


def _raise_remote(value, *, request_identity=None, phase='worker_operation'):
    cls = {'ValueError': ValueError, 'TypeError': TypeError, 'RuntimeError': RuntimeError,
           'KeyError': KeyError, 'TimeoutError': TimeoutError}.get(value.get('type'), RuntimeError)
    error = cls('remote RuntimeSession: ' + str(value.get('message', 'unknown failure')))
    error.phase = phase
    error.reason = 'remote_' + str(value.get('type', 'error'))
    error.request_identity = request_identity
    raise error


class _WorkerCallback:
    def __init__(self, sock, identity, sequence, name, materialization, episode):
        self.sock, self.identity, self.sequence, self.name = sock, identity, sequence, name
        self.materialization, self.episode = materialization, episode

    def call(self, method, *args):
        _send(self.sock, {'kind': 'callback', 'request_identity': self.identity,
                          'sequence': self.sequence, 'materialization_id': self.materialization,
                          'episode_id': self.episode, 'callback': self.name,
                          'method': method, 'args': _encode(args)})
        response = _receive(self.sock)
        if (response.get('kind'), response.get('request_identity'), response.get('sequence'),
                response.get('materialization_id'), response.get('episode_id')) != (
                'callback_result', self.identity, self.sequence, self.materialization, self.episode):
            raise ValueError('worker callback identity mismatch')
        if response.get('error') is not None:
            _raise_remote(response['error'])
        return _decode(response.get('result'))

    def inner_gripper_step(self, *args): return self.call('inner_gripper_step', *args)
    def begin(self, *args): return self.call('begin', *args)
    def target(self, *args): return self.call('target', *args)
    def applied(self, *args): return self.call('applied', *args)
    def __call__(self, *args): return self.call('__call__', *args)


def serve_session(sock, session, request_identity, *, handlers=None):
    """Forward one session until close; check operation and episode identity."""
    materialization = session.provider_materialization_id
    handlers = {} if handlers is None else dict(handlers)
    if set(handlers) - {'position_preflight', 'position_apply'}:
        raise ValueError('unknown worker control handler')
    methods = sorted(name for name in _METHODS if name in handlers or callable(getattr(session, name, None)))
    properties = sorted(name for name in _PROPERTIES
                        if hasattr(type(session), name) or name in vars(session))
    sequence, cleaned = 0, False

    def cleanup():
        nonlocal cleaned
        if cleaned:
            return
        cleaned = True
        error = None
        try:
            session.close()
        except BaseException as exc:
            error = exc
        try:
            close_owner = getattr(session, 'close_runtime_owner', None)
            if callable(close_owner):
                close_owner()
        except BaseException as exc:
            if error is None:
                error = exc
            else:
                error.add_note(f'worker owner close also failed: {exc}')
        if error is not None:
            raise error

    try:
        _send(sock, {'kind': 'ready', 'request_identity': request_identity,
                     'materialization_id': materialization, 'methods': methods, 'properties': properties})
        while True:
            request = _receive(sock)
            sequence += 1
            if (request.get('kind'), request.get('request_identity'), request.get('sequence'),
                    request.get('materialization_id')) != ('call', request_identity, sequence, materialization):
                raise ValueError('worker operation identity mismatch')
            method = request.get('method')
            if method != 'close' and request.get('episode_id') != _episode(session):
                raise ValueError('worker episode identity mismatch')
            try:
                if method == 'close':
                    cleanup()
                    result = None
                elif method in _PROPERTIES and method in properties:
                    result = getattr(session, method)
                elif method in _METHODS and method in methods:
                    args = _decode(request.get('args', []))
                    kwargs = _decode(request.get('kwargs', {}))
                    if method == 'step_control_interval':
                        callbacks = request.get('callbacks', [])
                        args = (*args, _WorkerCallback(sock, request_identity, sequence, 'servo', materialization, _episode(session)))
                        if 'observer' in callbacks:
                            kwargs['interval_observer'] = _WorkerCallback(sock, request_identity, sequence, 'observer', materialization, _episode(session))
                        if 'schedule' in callbacks:
                            kwargs['arm_schedule'] = _WorkerCallback(sock, request_identity, sequence, 'schedule', materialization, _episode(session))
                    if method == 'step_mixed_actuator_interval':
                        args = (*args, _WorkerCallback(sock, request_identity, sequence, 'command_factory', materialization, _episode(session)))
                    function = handlers[method] if method in handlers else getattr(session, method)
                    result = function(*args, **kwargs)
                else:
                    raise ValueError(f'unsupported worker operation: {method}')
                response = {'result': _encode(result), 'error': None}
            except BaseException as error:
                response = {'result': None, 'error': _error(error)}
            response.update(kind='result', request_identity=request_identity, sequence=sequence,
                            materialization_id=materialization, episode_id=_episode(session) if method != 'close' else None)
            _send(sock, response)
            if method == 'close':
                return
    finally:
        cleanup()


class RemoteSession:
    """Own a worker and forward the existing scalar session operations."""
    def __init__(self, process, sock, request_identity, *, timeout=30.0):
        self._process, self._sock = process, sock
        self._sock.settimeout(timeout)
        self._request_identity, self._sequence, self._closed = request_identity, 0, False
        self._episode_id = None
        try:
            ready = _receive(sock)
            if ready.get('request_identity') != request_identity:
                raise TransportProtocolError('worker startup identity mismatch')
            if ready.get('kind') == 'startup_error':
                _raise_remote(ready.get('error', {}), request_identity=request_identity, phase='worker_startup')
            if ready.get('kind') != 'ready':
                raise TransportProtocolError('worker startup response invalid')
            self._materialization_id = ready['materialization_id']
            self._methods = frozenset(ready['methods'])
            self._properties = frozenset(ready['properties'])
        except BaseException:
            self._terminate()
            raise

    def _terminate(self):
        self._sock.close()
        try:
            os.killpg(self._process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self._process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._process.wait(timeout=3)

    def _call(self, method, *args, callbacks=None, **kwargs):
        if self._closed:
            raise RuntimeError('runtime worker is closed')
        encoded_args, encoded_kwargs = _encode(args), _encode(kwargs)
        self._sequence += 1
        callbacks = callbacks or {}
        request = {'kind': 'call', 'request_identity': self._request_identity,
                   'sequence': self._sequence, 'materialization_id': self._materialization_id,
                   'episode_id': self._episode_id, 'method': method,
                   'args': encoded_args, 'kwargs': encoded_kwargs, 'callbacks': list(callbacks)}
        try:
            try:
                _send(self._sock, request)
            except (ValueError, TypeError):
                self._sequence -= 1  # Local encoding rejection sends no frame.
                raise
            while True:
                response = _receive(self._sock)
                if (response.get('request_identity'), response.get('sequence')) != (self._request_identity, self._sequence):
                    raise TransportProtocolError('worker response identity mismatch')
                if response.get('kind') != 'callback':
                    break
                if (response.get('materialization_id'), response.get('episode_id')) != (
                        self._materialization_id, self._episode_id):
                    raise TransportProtocolError('worker callback materialization/episode mismatch')
                try:
                    callback = callbacks[response['callback']]
                    callback_method = response['method']
                    if callback_method not in {'__call__', 'inner_gripper_step', 'begin', 'target', 'applied'}:
                        raise ValueError('unknown worker callback method')
                    function = callback if callback_method == '__call__' else getattr(callback, callback_method)
                    result = function(*_decode(response['args']))
                    answer = {'result': _encode(result), 'error': None}
                except BaseException as error:
                    answer = {'result': None, 'error': _error(error)}
                answer.update(kind='callback_result', request_identity=self._request_identity, sequence=self._sequence,
                              materialization_id=self._materialization_id, episode_id=self._episode_id)
                _send(self._sock, answer)
            if (response.get('kind'), response.get('materialization_id')) != ('result', self._materialization_id):
                raise TransportProtocolError('worker response materialization mismatch')
            response_episode = response.get('episode_id')
            if method not in {'reset', 'reset_plan', 'close'} and response_episode != self._episode_id:
                raise TransportProtocolError('worker response episode mismatch')
            self._episode_id = response_episode
            if response.get('error') is not None:
                _raise_remote(response['error'], request_identity=self._request_identity)
            try:
                return _decode(response.get('result'))
            except (ValueError, TypeError, KeyError) as error:
                raise TransportProtocolError('invalid worker result') from error
        except (EOFError, OSError, TimeoutError, TransportProtocolError):
            self._terminate()
            self._closed = True
            raise

    @property
    def provider_materialization_id(self):
        return self._materialization_id

    @property
    def episode_id(self):
        if self._episode_id is None:
            raise RuntimeError('runtime worker has no active episode')
        return self._episode_id

    @property
    def state_revision(self):
        return self._call('state_revision')

    def step_control_interval(self, target, servo, *, interval_observer=None, arm_schedule=None):
        callbacks = {'servo': servo}
        if interval_observer is not None:
            callbacks['observer'] = interval_observer
        if arm_schedule is not None:
            callbacks['schedule'] = arm_schedule
        return self._call('step_control_interval', target, callbacks=callbacks)

    def step_mixed_actuator_interval(self, command_factory):
        return self._call('step_mixed_actuator_interval', callbacks={'command_factory': command_factory})

    def __getattr__(self, name):
        if name in self._methods:
            return lambda *args, **kwargs: self._call(name, *args, **kwargs)
        if name in self._properties:
            return self._call(name)
        raise AttributeError(name)

    def close(self):
        if self._closed:
            return
        try:
            self._call('close')
        finally:
            self._closed = True
            self._sock.close()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._terminate()


def request_identity(payload):
    """Bind a worker request to strict, canonical JSON facts."""
    import hashlib
    data = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def source_binding_facts(source):
    """Canonical declared semantic/native mappings for one selected source."""
    result = {name: dict(getattr(source, name, {})) for name in
              ('joints', 'free_joints', 'bodies', 'frames', 'joint_targets',
               'torque_actuators', 'position_actuators')}
    result['open_actuators'] = list(getattr(source, 'open_actuators', ()))
    plan = getattr(source, 'mixed_actuator_plan', None)
    result['mixed_actuator_plan'] = None if plan is None else plan.identity_hash
    return result


def source_execution_facts(artifact, execution, source, controller):
    """Project request-bound Core facts without exporting live provider objects."""
    import hashlib
    source_value = source.scene_source
    xml = getattr(source_value, 'xml', None)
    scene = getattr(source, 'scene_definition', None)
    profiles = tuple(controller) if isinstance(controller, (tuple, list)) else (controller,)
    identities = []
    for item in profiles:
        identity = getattr(item, 'identity', None)
        if not isinstance(identity, str) or not identity:
            raise ValueError('worker request requires a Controller identity')
        identities.append(identity)
    return {
        'artifact_identity': artifact.identity_hash,
        'execution_identity': request_identity(execution.to_mapping()),
        'source_id': source_value.source_id,
        'source_bindings': source_binding_facts(source),
        'source_closure': getattr(source, 'source_closure_digest', None),
        'source_xml_sha256': None if xml is None else hashlib.sha256(xml.encode()).hexdigest(),
        'scene_identity': None if scene is None else scene.identity_hash,
        'controller_identities': sorted(identities),
    }


_WORKER_BOOTSTRAP = r'''
import os, pathlib, runpy, sys, sysconfig
core, geophys, fd, launcher_mode = sys.argv[1:]
prefix = str(pathlib.Path(sys.executable).parent.parent)
paths = sysconfig.get_paths(vars={'base': prefix, 'platbase': prefix})
launcher_paths = ([str(pathlib.Path(item).resolve()) for item in os.environ.get('PYTHONPATH', '').split(os.pathsep) if item]
                  if launcher_mode == 'launcher' else [])
sys.path[:0] = [core, geophys, *launcher_paths, paths['purelib'], paths['platlib']]
sys.argv = ['task_env.runtime.sessions.worker', fd]
runpy.run_module('task_env.runtime.sessions.worker', run_name='__main__')
'''


def start_selected_worker(interpreter, payload, *, timeout=30.0):
    """Start one source-bound worker using an already checked environment."""
    from pathlib import Path
    from ...utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT
    core = GEOCHORA_ROOT.resolve()
    geophys = (GEOPHYS_PROVIDER_ROOT / 'src').resolve()
    executable = Path(interpreter).expanduser().absolute()
    if not executable.is_file():
        raise ValueError(f'worker interpreter unavailable: {executable}')
    environment = payload['environment']
    expected_launcher = environment.get('launcher')
    launcher_matches = (str(executable) == expected_launcher if expected_launcher is not None
                        else str(executable.resolve()) == environment['python'])
    if (Path(payload['core_root']).resolve() != core
            or Path(payload['geophys_src']).resolve() != geophys
            or not launcher_matches):
        raise ValueError('worker deployment differs from preflight origins or interpreter')
    identity = request_identity(payload)
    parent, child = socket.socketpair()
    parent.settimeout(timeout)
    process = None
    try:
        env = dict(os.environ, GEOCHORA_GEOPHYS_SRC=str(geophys),
                   GEOCHORA_CORE_PYTHON=str(executable), PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.Popen(
            [str(executable), '-I', '-S', '-B', '-c', _WORKER_BOOTSTRAP,
             str(core), str(geophys), str(child.fileno()),
             'launcher' if executable.name == 'python.sh' else 'python'],
            cwd=os.getcwd(), env=env, pass_fds=(child.fileno(),), start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=None if payload['selection']['physics_provider'] == 'isaacsim' else subprocess.DEVNULL,
            stderr=None if payload['selection']['physics_provider'] == 'isaacsim' else subprocess.DEVNULL,
        )
        child.close()
        _send(parent, {'kind': 'build', 'request_identity': identity, 'payload': payload})
        return RemoteSession(process, parent, identity, timeout=timeout)
    except BaseException:
        child.close()
        parent.close()
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        raise
