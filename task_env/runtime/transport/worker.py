"""Interpreter worker lifecycle and messages for a single native batch."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile


def _send(stream, message):
    stream.write(json.dumps(message, allow_nan=False) + '\n')
    stream.flush()


def _receive(stream, timeout=900):
    if not select.select([stream], [], [], timeout)[0]:
        raise TimeoutError(f'native batch worker did not respond within {timeout} seconds')
    line = stream.readline()
    if not line:
        raise ConnectionError('native batch worker exited without a response')
    response = json.loads(line)
    if response.get('error'):
        raise RuntimeError(f"native batch worker {response['phase']} failed: {response['error']}")
    return response


class RuntimeWorker:
    """Start one interpreter and exchange control-plane messages with it."""

    def __init__(self, interpreter, request, *, working_directory=None):
        self._temporary_directory = None
        self._close_timeout = 180 if request.get('provider') == 'isaacsim' else 10
        if working_directory is None:
            self._temporary_directory = tempfile.TemporaryDirectory(prefix='geochora-mjwarp-')
            directory = self._temporary_directory.name
        else:
            directory = tempfile.mkdtemp(prefix='geochora-mjwarp-', dir=working_directory)
        root = Path(__file__).resolve().parents[3]
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(root)
        if request.get('provider') == 'geophys':
            environment['PYTHONPATH'] += os.pathsep + str(root / 'GeoPhys' / 'src')
        environment['PYTHONNOUSERSITE'] = '1'
        self._process = None
        try:
            self._process = subprocess.Popen([str(interpreter), '-u', '-m', 'task_env.runtime.transport.worker'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
                env=environment, cwd=directory)
            _send(self._process.stdin, request)
            self.description = _receive(self._process.stdout)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'worker cleanup also failed: {cleanup_error!r}')
            raise

    def call(self, command, **payload):
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError('native batch worker is closed')
        _send(self._process.stdin, {'command': command, **payload})
        return _receive(self._process.stdout)

    @property
    def closed(self):
        return self._process is None

    def close(self):
        process = self._process
        error = None
        def record(caught, operation):
            nonlocal error
            if error is None:
                error = caught
            else:
                error.add_note(f'{operation} also failed: {caught!r}')

        if process is not None:
            if process.poll() is None:
                try:
                    _send(process.stdin, {'command': 'close'})
                    _receive(process.stdout, timeout=self._close_timeout)
                except BaseException as caught:
                    record(caught, 'worker close request')
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    record(TimeoutError('native batch worker did not close'), 'worker wait')
                    try:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    except BaseException as caught:
                        record(caught, 'worker retirement')
                except BaseException as caught:
                    record(caught, 'worker wait')
            if process.poll() is not None and process.returncode != 0 and error is None:
                error = RuntimeError(f'native batch worker exited with code {process.returncode}')
            for name in ('stdin', 'stdout'):
                stream = getattr(process, name)
                if stream is not None and not stream.closed:
                    try:
                        stream.close()
                    except BaseException as caught:
                        record(caught, f'worker {name} close')
            if process.poll() is not None and all(
                    stream is None or stream.closed for stream in (process.stdin, process.stdout)):
                self._process = None
        if self._temporary_directory is not None and (process is None or process.poll() is not None):
            try:
                self._temporary_directory.cleanup()
                self._temporary_directory = None
            except BaseException as caught:
                record(caught, 'worker directory cleanup')
        if error is not None:
            raise error


def main():
    # Native libraries may write directly to file descriptor 1, bypassing
    # redirect_stdout. Keep a private duplicate for protocol replies and send
    # all library output to stderr so it cannot corrupt the JSON stream.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    native = None
    phase = 'construction'
    try:
        request = _receive(sys.stdin, timeout=None)
        with contextlib.redirect_stdout(sys.stderr):
            from ..factory import load_device_provider
            native_type = load_device_provider(request['provider'], worker=True)
            native = native_type(request)
            description = native.description()
        _send(protocol, description)
        while True:
            message = _receive(sys.stdin, timeout=None)
            phase = message['command']
            with contextlib.redirect_stdout(sys.stderr):
                if phase == 'bind_event':
                    native.bind_written_event(message['handle'])
                elif phase == 'reset':
                    native.reset()
                elif phase == 'step':
                    native.step()
                elif phase == 'close':
                    native.close()
                    native = None
                else:
                    raise ValueError(f'unsupported worker command: {phase}')
            _send(protocol, {'ok': True})
            if phase == 'close':
                if request['provider'] == 'isaacsim':
                    protocol.close()
                    from ..sessions.worker import _exit_after_isaac_cleanup
                    _exit_after_isaac_cleanup(0)
                return
    except BaseException as error:
        _send(protocol, {'phase': phase, 'error': f'{type(error).__name__}: {error}'})
        raise
    finally:
        protocol.close()
        if native is not None:
            with contextlib.redirect_stdout(sys.stderr):
                native.close()


if __name__ == '__main__':
    main()
