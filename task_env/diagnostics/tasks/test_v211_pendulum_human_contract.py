"""Contract checks for a selected Env with unavailable human presentation."""
from types import SimpleNamespace

import pytest

from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.render import RenderUnavailableError


class _Lifecycle:
    def __init__(self):
        self.closed = False

    def require_open(self, message):
        if self.closed:
            raise RuntimeError(message)


def test_unavailable_human_is_not_a_render_fault():
    lifecycle = _Lifecycle()
    env = SimpleNamespace(_human_display_unavailable=True, render_mode='human',
                          _execution_fault=None, _episode_execution_state=lambda: lifecycle)
    with pytest.raises(RenderUnavailableError, match='human display is not available'):
        SelectedReferenceEnv.render(env)
    assert env._execution_fault is None
    with pytest.raises(ValueError, match='fixed at construction'):
        SelectedReferenceEnv.render(env, 'rgb_array')
    env._execution_fault = object()
    with pytest.raises(RuntimeError, match='execution is faulted'):
        SelectedReferenceEnv.render(env)
    env._execution_fault = None
    lifecycle.closed = True
    with pytest.raises(RuntimeError, match='environment is closed'):
        SelectedReferenceEnv.render(env)
