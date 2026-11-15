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
        if working_directory is None:
            self._temporary_directory = tempfile.TemporaryDirectory(prefix='geochora-mjwarp-')
            directory = self._temporary_directory.name
        else:
            directory = tempfile.mkdtemp(prefix='geochora-mjwarp-', dir=working_directory)
        root = Path(__file__).resolve().parents[3]
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(root)
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

    def close(self):
        process, self._process = self._process, None
        error = None
        try:
            if process is not None:
                if process.poll() is None:
                    try:
                        _send(process.stdin, {'command': 'close'})
                        _receive(process.stdout, timeout=10)
                    except BaseException as caught:
                        error = caught
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        if error is None:
                            error = TimeoutError('native batch worker did not close')
                        try:
                            process.terminate()
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                if process.returncode != 0 and error is None:
                    error = RuntimeError(f'native batch worker exited with code {process.returncode}')
                if process.stdin is not None:
                    process.stdin.close()
                if process.stdout is not None:
                    process.stdout.close()
        finally:
            if self._temporary_directory is not None:
                self._temporary_directory.cleanup()
        if error is not None:
            raise error


def main():
    native = None
    phase = 'construction'
    try:
        request = _receive(sys.stdin, timeout=None)
        with contextlib.redirect_stdout(sys.stderr):
            from ..providers.mujoco_warp.batch import MuJoCoWarpNativeBatch
            native = MuJoCoWarpNativeBatch(request)
            description = native.description()
        _send(sys.stdout, description)
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
            _send(sys.stdout, {'ok': True})
            if phase == 'close':
                return
    except BaseException as error:
        _send(sys.stdout, {'phase': phase, 'error': f'{type(error).__name__}: {error}'})
        raise
    finally:
        if native is not None:
            with contextlib.redirect_stdout(sys.stderr):
                native.close()


if __name__ == '__main__':
    main()
