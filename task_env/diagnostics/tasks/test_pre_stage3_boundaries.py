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


def test_execution_boundary_reuses_xml_digest_but_invalidates_on_replacement(monkeypatch):
    import hashlib
    from task_env.tasks.reference_env import SelectedReferenceEnv

    original_sha256 = hashlib.sha256
    xml_inputs = []
    def counting_sha256(data=b''):
        if data in (b'<scene/>', b'<scene changed="yes"/>'):
            xml_inputs.append(data)
        return original_sha256(data)
    monkeypatch.setattr(hashlib, 'sha256', counting_sha256)
    scene = SimpleNamespace(source_id='scene', xml='<scene/>')
    env = SimpleNamespace(
        value={'source': SimpleNamespace(scene_source=scene, source_closure_digest=None)},
        _selected_episode_id='episode', artifact=SimpleNamespace(identity_hash='a' * 64),
        session=SimpleNamespace(provider_materialization_id='materialization'),
        controller=SimpleNamespace(identity='b' * 64),
        _active_solution_identity=lambda: 'c' * 64,
        sample=SimpleNamespace(sample_id='reset'),
    )
    info = SimpleNamespace(control_step=0, simulation_time=0.0)
    first = SelectedReferenceEnv._execution_boundary(env, info)
    info.control_step = 1
    info.simulation_time = 0.01
    second = SelectedReferenceEnv._execution_boundary(env, info)
    assert first['identity_hash'] != second['identity_hash']
    assert first['source_xml_sha256'] == second['source_xml_sha256']
    scene.xml = '<scene changed="yes"/>'
    third = SelectedReferenceEnv._execution_boundary(env, info)
    assert third['source_xml_sha256'] != second['source_xml_sha256']
    assert third['identity_hash'] != second['identity_hash']
    assert xml_inputs == [b'<scene/>', b'<scene changed="yes"/>']


def test_selected_compatibility_exports_reference_the_canonical_objects():
    from task_env.environment.reference_binding import ReferenceTaskBinding
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.tasks.reference_env import (
        ReferenceTaskBinding as old_binding,
        SelectedReferenceEnv as old_env,
    )

    assert old_env is SelectedReferenceEnv
    assert old_binding is ReferenceTaskBinding


def test_example_bootstrap_accepts_explicit_geophys_source_and_rejects_missing(monkeypatch, tmp_path):
    import sys
    from examples._common import bootstrap_imports

    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setenv('GEOCHORA_GEOPHYS_SRC', str(tmp_path / 'missing'))
    with pytest.raises(ValueError, match='GeoPhys src directory'):
        bootstrap_imports()
    source = tmp_path / 'src'
    (source / 'scene').mkdir(parents=True)
    (source / 'scene' / '__init__.py').write_text('')
    monkeypatch.setenv('GEOCHORA_GEOPHYS_SRC', str(source))
    monkeypatch.setitem(sys.modules, 'scene', SimpleNamespace(__file__=str(tmp_path / 'old' / 'scene.py')))
    with pytest.raises(RuntimeError, match='already imported outside'):
        bootstrap_imports()
    monkeypatch.delitem(sys.modules, 'scene')
    bootstrap_imports()
    assert str(source) in sys.path


def test_start_routes_explicit_paths_and_rejects_unsupported_without_spawning(monkeypatch, tmp_path):
    import sys
    from examples import start

    source = tmp_path / 'geophys' / 'src'
    (source / 'scene').mkdir(parents=True)
    (source / 'scene' / '__init__.py').write_text('')
    captured = []
    monkeypatch.setattr(start.subprocess, 'run', lambda command, **kwargs: (
        captured.append((command, kwargs)) or SimpleNamespace(returncode=0)
    ))
    base = ['--python', sys.executable, '--geophys-src', str(source),
            '--uid', 'pendulum-v1', '--provider', 'geophys', '--backend', 'cpu',
            '--renderer', 'none', '--seed', '73']
    assert start.main(base) == 0
    command, options = captured[0]
    assert command[0] == str(__import__('pathlib').Path(sys.executable).resolve())
    assert command[1].endswith('examples/tasks/scalar_step.py')
    assert command[-2:] == ['--seed', '73']
    assert options['env']['GEOCHORA_GEOPHYS_SRC'] == str(source)
    assert options['env']['GEOCHORA_CORE_PYTHON'] == command[0]
    assert options['env']['PYTHONPATH'].split(__import__('os').pathsep) == [str(start.ROOT), str(source)]
    with pytest.raises(SystemExit):
        start.main(base[:-4] + ['--backend', 'cuda', '--renderer', 'none'])
    assert len(captured) == 1


def test_start_passes_external_isaac_interpreter_and_manifest(monkeypatch, tmp_path):
    import sys
    from examples import start

    source = tmp_path / 'src'
    (source / 'scene').mkdir(parents=True)
    (source / 'scene' / '__init__.py').write_text('')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}')
    captured = []
    monkeypatch.setattr(start.subprocess, 'run', lambda command, **kwargs: (
        captured.append((command, kwargs)) or SimpleNamespace(returncode=0)
    ))
    assert start.main(['--python', sys.executable, '--geophys-src', str(source),
                       '--uid', 'pick-cube-p16-reference-v1', '--provider', 'isaacsim',
                       '--backend', 'cuda', '--renderer', 'none', '--isaac-python', sys.executable,
                       '--source-delivery-manifest', str(manifest), '--seed', '31']) == 0
    command, options = captured[0]
    assert command[command.index('--isaac-python') + 1] == str(__import__('pathlib').Path(sys.executable).resolve())
    assert command[command.index('--source-delivery-manifest') + 1] == str(manifest)
    assert options['env']['GEOCHORA_GEOPHYS_SRC'] == str(source)
