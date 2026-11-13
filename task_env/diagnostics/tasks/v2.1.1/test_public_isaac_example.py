"""Offline routing checks for the ordinary installed-asset Isaac example."""

from contextlib import contextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


def test_start_routes_isaac_to_direct_example_without_manifest(tmp_path, monkeypatch):
    from examples import start

    source = tmp_path / 'src'
    (source / 'scene').mkdir(parents=True)
    (source / 'scene' / '__init__.py').write_text('')
    calls = []
    monkeypatch.setattr(start.subprocess, 'run', lambda argv, **kwargs:
                        calls.append((argv, kwargs)) or SimpleNamespace(returncode=0))
    assert start.main(['--geophys-src', str(source), '--uid', 'pick-cube-p16-reference-v1',
                       '--provider', 'isaacsim', '--backend', 'cuda', '--renderer', 'none',
                       '--isaac-python', sys.executable, '--seed', '41', '--horizon', '55']) == 0
    argv, _ = calls[0]
    assert '--execution' not in argv
    assert '--source-delivery-manifest' not in argv
    assert argv[argv.index('--isaac-python') + 1] == str(Path(sys.executable).absolute())
    assert argv[argv.index('--seed') + 1] == '41'


def test_direct_isaac_forwards_formal_execution_and_reports_failure(tmp_path, monkeypatch, capsys):
    from examples.tasks import pick_cube
    import task_env

    calls = []
    limits = []

    @contextmanager
    def fake_budget(memory, time, *, limit_address_space=True):
        limits.append((memory, time, limit_address_space))
        yield {'fake': True}

    def fail_make_env(uid, *, config):
        calls.append((uid, config))
        raise ValueError('synthetic construction error')

    monkeypatch.setattr(pick_cube, 'bounded_process', fake_budget)
    monkeypatch.setattr(pick_cube, 'bootstrap_imports', lambda: None)
    monkeypatch.setattr(task_env, 'make_env', fail_make_env)
    result = pick_cube.main(['--provider', 'isaacsim', '--isaac-python', sys.executable,
                             '--seed', '41', '--horizon', '55', '--recording', str(tmp_path / 'unused.h5')])
    assert result == 1
    execution = calls[0][1]['execution']
    assert execution == {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                         'physics_device': 'cuda:0', 'interpreter': str(Path(sys.executable).absolute())}
    assert calls[0][1]['episode']['horizon'] == 55
    assert limits == [(8192, 420, False)]
    report = json.loads(capsys.readouterr().out)
    assert report['backend'] == 'cuda' and report['device'] == 'cuda:0'
    assert report['runtime_valid'] is False and 'synthetic construction error' in report['error']


def test_direct_isaac_rejects_unsupported_address_space_limit():
    from examples.tasks import pick_cube

    with pytest.raises(SystemExit):
        pick_cube.main(['--provider', 'isaacsim', '--memory-limit-mb', '4096'])


def test_identity_summary_uses_resolved_backend_without_inventing_cpu():
    from examples._common import identity_summary

    env = SimpleNamespace(metadata={}, config=SimpleNamespace(runtime=SimpleNamespace(backend='cuda')))
    assert identity_summary(env, provider='isaacsim')['backend'] == 'cuda'
    assert identity_summary(SimpleNamespace(metadata={}), provider='isaacsim')['backend'] is None


def test_public_yaml_and_mapping_have_same_selected_configuration(tmp_path):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.script.env._common import public_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    path = tmp_path / 'pick-cube.yaml'
    path.write_text('execution:\n  physics_provider: mujoco\n  physics_backend: cpu\n'
                    '  physics_device: cpu\nepisode:\n  horizon: 10\n')
    mapping = {'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                             'physics_device': 'cpu'}, 'episode': {'horizon': 10}}
    assert public_config('pick-cube-p16-reference-v1', 'cpu', 10, path) == mapping
    assert resolve_task_env_config(PickCubeReferenceEnv, mapping) == resolve_task_env_config(
        PickCubeReferenceEnv, public_config('pick-cube-p16-reference-v1', 'cpu', 10, path))


@pytest.mark.parametrize('close_fails', [False, True])
def test_direct_isaac_reports_runtime_and_close_separately(tmp_path, monkeypatch, capsys, close_fails):
    from contextlib import nullcontext
    import task_env
    import task_env.tasks.pick_cube as pick_task
    from examples.tasks import pick_cube
    from task_env.trajectory.canonical import h5

    class Env:
        metadata = {}
        config = SimpleNamespace(runtime=SimpleNamespace(backend='cuda'))
        controller = SimpleNamespace(identity='controller')
        session = SimpleNamespace(provider_materialization_id='provider')

        def reset(self, *, seed):
            return {}, {}

        def start_recording(self, path):
            path.write_bytes(b'fake')

        def finish_recording(self, reason):
            return {'fake': True}

        def close(self):
            if close_fails:
                raise OSError('close failed')

    solution = SimpleNamespace(identity='solution', reset=lambda *args: None)
    monkeypatch.setattr(task_env, 'make_env', lambda *args, **kwargs: Env())
    monkeypatch.setattr(pick_task, 'build_readiness_solution', lambda **kwargs: solution)
    monkeypatch.setattr(pick_cube, 'bootstrap_imports', lambda: None)
    monkeypatch.setattr(pick_cube, 'bounded_process', lambda *args, **kwargs: nullcontext({}))
    monkeypatch.setattr(pick_cube, 'run_caller_solution', lambda *args, **kwargs:
                        {'task_success': True, 'expert_complete': True, 'completion_eligible': True})
    monkeypatch.setattr(pick_cube, 'load_recording_summary', lambda path: {'t_plus_one_valid': True})
    monkeypatch.setattr(h5, 'load', lambda path: SimpleNamespace(transitions=[SimpleNamespace(planned_action=True)]))
    code = pick_cube.main(['--provider', 'isaacsim', '--recording', str(tmp_path / 'fake.h5')])
    report = json.loads(capsys.readouterr().out)
    assert report['close_attempted'] is True and report['close_succeeded'] is not close_fails
    assert report['runtime_valid'] is not close_fails
    assert report['identity']['backend'] == 'cuda'
    assert (report['task_outcome'] == 'SOLVED') is not close_fails
    assert code == (1 if close_fails else 0)
