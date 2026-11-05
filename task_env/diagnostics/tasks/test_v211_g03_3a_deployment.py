"""Offline deployment preflight: metadata only, never a native capability claim."""
import importlib.metadata
import sys
from pathlib import Path

import pytest

from task_env.runtime.sessions.provenance import probe_interpreter_environment
from task_env.utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT


def test_current_interpreter_metadata_is_bound_to_current_source():
    result = probe_interpreter_environment(sys.executable)
    assert result['origins']['task_env'] == str((GEOCHORA_ROOT / 'task_env/__init__.py').resolve())
    assert result['origins']['geophys'] == str((GEOPHYS_PROVIDER_ROOT / 'src/geophys/__init__.py').resolve())
    assert result['origins']['scene'] == str((GEOPHYS_PROVIDER_ROOT / 'src/scene/__init__.py').resolve())
    try:
        expected = importlib.metadata.version('mujoco')
    except importlib.metadata.PackageNotFoundError:
        expected = None
    assert result['versions']['mujoco'] == expected


def test_wrong_source_and_missing_interpreter_rejected_before_spawn(monkeypatch, tmp_path):
    from task_env.runtime.sessions import provenance
    monkeypatch.setattr(provenance.subprocess, 'run', lambda *a, **kw: pytest.fail('must not spawn'))
    with pytest.raises(ValueError, match='source origin differs'):
        probe_interpreter_environment(sys.executable, core_root=tmp_path)
    with pytest.raises(ValueError, match='source origin differs'):
        probe_interpreter_environment(sys.executable, geophys_src=tmp_path)
    with pytest.raises(ValueError, match='interpreter unavailable'):
        probe_interpreter_environment(tmp_path / 'missing')


@pytest.mark.parametrize('version,provider,status', [
    ('3.8.1', 'mujoco', 'available'),
    ('3.8.1', 'geophys', 'unavailable'),
    ('3.15.0', 'mujoco', 'unavailable'),
    ('3.15.0', 'geophys', 'available'),
    (None, 'mujoco', 'unavailable'),
    ('3.15.0rc1', 'geophys', 'unknown'),
    ('3.8.1', 'isaacsim', 'unknown'),
])
def test_distribution_constraint_is_route_specific(version, provider, status):
    from task_env.runtime.sessions.provenance import assess_mujoco_distribution
    result = assess_mujoco_distribution(provider, {'versions': {'mujoco': version}})
    assert result['status'] == status
    assert result['observed_version'] == version


def test_requirements_assessment_separates_core_geophys_and_unknown_metadata():
    from task_env.runtime.sessions.provenance import assess_declared_dependencies
    # Synthetic distribution facts exercise the actual checked-in declarations;
    # they are not an environment or provider capability claim.
    versions = {
        'numpy': '2.2.6', 'scipy': '1.14.0', 'psutil': '6.0.0', 'pydantic': '2.11.0',
        'taichi-forge': '0.6.3', 'trimesh': '4.0.0', 'pyvista': '0.46.5',
        'Pillow': '11.1.0', 'mujoco': '3.8.1', 'gymnasium': '1.3.0',
        'h5py': '3.12.0', 'PyYAML': '6.0',
    }
    facts = {'versions': versions, 'module_origins': {name: '/fixture/' + name for name in versions},
             'origin_ownership': {name: 'owned' for name in versions}, 'python_version': [3, 12, 0]}
    core = assess_declared_dependencies('mujoco', facts)
    geo = assess_declared_dependencies('geophys', facts)
    assert core['status'] == 'available'
    assert geo['status'] == 'unavailable'
    assert [(r['requirement'], r['status']) for r in geo['requirements'] if r['name'] == 'mujoco'] == [
        ('mujoco>=3.15.0', 'unavailable')]
    versions['mujoco'] = '3.15.0'
    assert assess_declared_dependencies('geophys', facts)['status'] == 'available'
    assert assess_declared_dependencies('mujoco', facts)['status'] == 'unavailable'
    del versions['psutil']
    assert assess_declared_dependencies('geophys', facts)['status'] == 'unknown'
    assert assess_declared_dependencies('isaacsim', facts)['status'] == 'unknown'
    versions['isaacsim'] = None
    facts['module_origins']['isaacsim'] = None
    assert assess_declared_dependencies('isaacsim', facts)['status'] == 'unavailable'


def test_real_conflicting_metadata_rejects_before_existing_session_is_closed(monkeypatch):
    from types import SimpleNamespace
    from task_env import make_env
    from task_env.runtime.sessions.provenance import DeploymentPreflightError
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'geophys', 'deployment': 'isolated_worker',
                      'interpreter': sys.executable},
    })
    effects = []
    sentinel = SimpleNamespace(close=lambda: effects.append('session.close'))
    env.session = sentinel
    monkeypatch.setattr(env, '_close_camera_consumer', lambda: effects.append('camera.close'))
    try:
        with pytest.raises(DeploymentPreflightError, match='dependency_unavailable') as failure:
            env._prepare_reference_reset(seed=31)
        receipt = failure.value.receipt
        rows = [r for r in receipt['dependency']['requirements'] if r['name'] == 'mujoco']
        assert rows == [{'name': 'mujoco', 'requirement': 'mujoco>=3.15.0',
                         'observed_version': '3.8.1', 'status': 'unavailable',
                         'reason': 'version conflicts with declaration'}]
        assert receipt['native_effective']['status'] == 'unknown'
        assert failure.value.phase == 'static_preflight'
        assert len(failure.value.request_identity) == 64
        assert env.session is sentinel and effects == []
    finally:
        env.session = None
        env.close()


def test_missing_asset_closure_rejects_before_existing_session_is_closed(monkeypatch):
    import json
    from types import SimpleNamespace
    from task_env import make_env
    from task_env.runtime.sessions.provenance import DeploymentPreflightError
    from dataclasses import replace
    env = make_env('pick-cube-p16-reference-v1', config={'provider': 'mujoco'})
    original_source = env.value['source']
    env.value['source'] = replace(original_source, execution_source_receipt=None, source_closure_digest=None)
    effects = []
    sentinel = SimpleNamespace(close=lambda: effects.append('session.close'))
    env.session = sentinel
    monkeypatch.setattr(env, '_close_camera_consumer', lambda: effects.append('camera.close'))
    try:
        with pytest.raises(DeploymentPreflightError, match='capability_rejected') as failure:
            env._prepare_reference_reset(seed=31)
        receipt = failure.value.receipt
        row = next(r for r in receipt['assessment']['rows'] if r['capability_id'] == 'source_closure')
        assert row['requirement_status'] == 'unsatisfied'
        assert 'no source-bound receipt' in row['reason']
        assert json.loads(json.dumps(receipt)) == receipt
        assert env.session is sentinel and effects == []
    finally:
        env.session = None
        env.value['source'] = original_source
        env.close()
