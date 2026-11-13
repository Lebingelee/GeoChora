"""Formal Isaac source resolution through an independently installed delivery."""
import importlib
from pathlib import Path

import pytest

from task_env import ENV_REGISTRY
from task_env.assembly.usd_cache import install_usd_delivery, installed_usd_manifest
from task_env.environment.configuration import resolve_task_env_config

ROOT = Path(__file__).resolve().parents[4]
G05 = ROOT / 'workspace/maintenance/v211_g05_5c_unit005_isaac_continuation_20261110_002/g05-delivery-014'
PANDA = ROOT / 'workspace/maintenance/v211_e11_e16_u5_20261113_001/assets/isaac-panda/restored/isaac-delivery/delivery_manifest.json'


@pytest.mark.parametrize(('task_uid', 'robot_uid', 'manifest', 'profile'), [
    ('pendulum-v1', 'pendulum-v1', G05 / 'pendulum/delivery_manifest.json', 'direct_joint_effort_v1'),
    ('two-wheel-balance-v1', 'two-wheel-balance-v1', G05 / 'two-wheel/delivery_manifest.json', 'direct_joint_effort_v1'),
    ('pick-cube-p16-reference-v1', 'panda-v1', PANDA, 'r3_continuous_v1'),
])
def test_formal_isaac_configuration_uses_installed_verified_robot_asset(
        tmp_path, monkeypatch, task_uid, robot_uid, manifest, profile):
    if not manifest.is_file():
        pytest.skip('validated USD delivery is unavailable')
    monkeypatch.setenv('GEOCHORA_USD_ASSET_ROOT', str(tmp_path))
    installed = install_usd_delivery(manifest, provider='isaacsim', robot_uid=robot_uid)
    assert installed == installed_usd_manifest('isaacsim', robot_uid)
    assert installed.read_bytes() == manifest.read_bytes()
    assert not installed.is_relative_to(manifest.parent)
    importlib.import_module('task_env.tasks')
    task = ENV_REGISTRY.get(task_uid)
    config = {'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                            'physics_device': 'cuda:0'}, 'controller': {'profile_id': profile}}
    resolved = resolve_task_env_config(task, config)
    assert resolved.source_delivery_manifest == str(installed)
    assert resolve_task_env_config(task, resolved) == resolved
    assert install_usd_delivery(manifest, provider='isaacsim', robot_uid=robot_uid) == installed


def test_missing_asset_and_invalid_key_fail_without_implicit_historical_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv('GEOCHORA_USD_ASSET_ROOT', str(tmp_path))
    with pytest.raises(ValueError, match='install the supported asset'):
        installed_usd_manifest('isaacsim', 'pendulum-v1')
    with pytest.raises(ValueError, match='simple identifiers'):
        installed_usd_manifest('isaacsim', '../other')


def test_install_does_not_replace_other_or_corrupted_package(tmp_path):
    first = G05 / 'pendulum/delivery_manifest.json'
    other = G05 / 'two-wheel/delivery_manifest.json'
    if not first.is_file() or not other.is_file():
        pytest.skip('validated USD deliveries are unavailable')
    installed = install_usd_delivery(first, provider='isaacsim', robot_uid='pendulum-v1', root=tmp_path)
    before = installed.read_bytes()
    with pytest.raises(FileExistsError, match='different USD asset'):
        install_usd_delivery(other, provider='isaacsim', robot_uid='pendulum-v1', root=tmp_path)
    assert installed.read_bytes() == before
    import json
    entry = json.loads(before)['entry_file']
    target = installed.parent / entry
    target.write_bytes(target.read_bytes() + b'\n# modified\n')
    with pytest.raises(ValueError):
        install_usd_delivery(first, provider='isaacsim', robot_uid='pendulum-v1', root=tmp_path)
    assert installed.read_bytes() == before


def test_asset_lookup_does_not_import_provider_sdk(tmp_path):
    import os
    import subprocess
    import sys

    manifest = tmp_path / 'isaacsim' / 'pendulum-v1' / 'delivery_manifest.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{}')
    script = '''
import sys
import task_env.tasks
from task_env import ENV_REGISTRY
from task_env.environment.configuration import resolve_task_env_config
resolved = resolve_task_env_config(ENV_REGISTRY.get('pendulum-v1'), {
    'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda', 'physics_device': 'cuda:0'}})
assert resolved.source_delivery_manifest
assert not any(name == 'pxr' or name.startswith('omni.') or name == 'isaacsim' for name in sys.modules)
'''
    env = dict(os.environ, GEOCHORA_USD_ASSET_ROOT=str(tmp_path))
    subprocess.run([sys.executable, '-c', script], env=env, check=True)

@pytest.mark.parametrize('rendering', [False, True])
def test_isaac_app_is_ready_before_source_inspection(monkeypatch, rendering):
    from task_env.runtime.sessions import isaac_native_io

    events = []
    class Owner:
        app = None
        def open(self, *, f06_compatibility):
            events.append(('open', f06_compatibility))
            self.app = object()
        def close(self):
            events.append(('close',))

    owner = Owner()
    monkeypatch.setattr(isaac_native_io, '_process_app_owner', lambda **kwargs: owner)
    with isaac_native_io.prepare_isaac_source(rendering=rendering):
        events.append(('inspect', owner.app is not None))
    assert events == [('open', True), ('inspect', True)]

    owner.app = None
    with pytest.raises(RuntimeError, match='source failure'):
        with isaac_native_io.prepare_isaac_source(rendering=rendering):
            raise RuntimeError('source failure')
    assert events[-2:] == [('open', True), ('close',)]
