"""Production metadata and worker bootstrap retain the selected launcher context."""
import shlex
import sys
from pathlib import Path
import pytest

from task_env.runtime.sessions.provenance import probe_interpreter_environment
from task_env.runtime.sessions.transport import start_selected_worker
from task_env.utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT


def test_launcher_context_is_consumed_and_bound_without_sdk_import(tmp_path):
    sdk = tmp_path / 'SDK with spaces' / 'extension packages'
    module = sdk / 'isaacsim'
    module.mkdir(parents=True)
    (module / '__init__.py').write_text('raise AssertionError("metadata probe must not import SDK")\n')
    launcher = tmp_path / 'SDK with spaces' / 'python.sh'
    launcher.write_text('#!/bin/sh\nprintf "SDK startup log\\n"\nexport PYTHONPATH='
                        + shlex.quote(str(sdk)) + '\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    launcher.chmod(0o755)
    environment = probe_interpreter_environment(launcher)
    assert environment['module_origins']['isaacsim'] == str((module / '__init__.py').resolve())
    assert environment['launcher_pythonpath'] == [str(sdk.resolve())]
    assert environment['worker_executable'] == str(Path(sys.executable).absolute())
    payload = {'core_root': str(GEOCHORA_ROOT), 'geophys_src': str(GEOPHYS_PROVIDER_ROOT / 'src'),
               'environment': environment, 'selection': {'physics_provider': 'mujoco'},
               'uid': 'not-a-registered-task', 'config': {}}
    # The real worker validates the source and SDK paths, then fails only at
    # the deliberately unknown task. No admission/materializer is replaced.
    with pytest.raises((ValueError, KeyError, RuntimeError)) as failure:
        start_selected_worker(launcher, payload, timeout=15)
    assert 'worker dependency origin changed' not in str(failure.value)
    assert 'worker launcher Python path differs' not in str(failure.value)
    assert 'not-a-registered-task' in str(failure.value)

    changed = tmp_path / 'different SDK path'
    changed.mkdir()
    launcher.write_text('#!/bin/sh\nexport PYTHONPATH=' + shlex.quote(str(changed))
                        + '\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    with pytest.raises(ValueError, match='launcher Python path differs'):
        start_selected_worker(launcher, payload, timeout=15)
