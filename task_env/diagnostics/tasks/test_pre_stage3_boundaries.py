"""Offline regression checks for maintenance boundaries."""
from types import SimpleNamespace

import pytest


def test_historical_pickcube_rejection_is_available_without_diagnostics_dependency():
    from task_env.environment._historical import make_replay_env
    from task_env.diagnostics.historical_tasks import make_historical_env

    for constructor in (make_replay_env, make_historical_env):
        with pytest.raises(RuntimeError, match='retired.*immutable v1.0.0'):
            constructor('pick-cube-v1')


def test_recording_owner_uses_start_snapshot_without_rereading_source(monkeypatch):
    from pathlib import Path
    from task_env.tasks.reference_env import SelectedReferenceEnv

    calls = []
    def unexpected_read(path):
        calls.append(path)
        raise AssertionError('recording boundary reread source')
    monkeypatch.setattr(Path, 'read_bytes', unexpected_read)
    env = SimpleNamespace(
        _episode_mode='external', info={'is_success': False},
        state=SimpleNamespace(control_step=0, simulation_time=0.0),
        artifact=SimpleNamespace(identity_hash='a' * 64),
        controller=SimpleNamespace(identity='b' * 64), provider='mujoco',
        _active_solution_identity=lambda: 'c' * 64,
        _recording_adapter_source_sha256='d' * 64,
    )
    for step in range(3):
        env.state.control_step = step
        receipt = SelectedReferenceEnv._owners(env)
        assert receipt['owners']['coordinator']['source_sha256'] == 'd' * 64
        assert receipt['control_step'] == step
    assert calls == []
