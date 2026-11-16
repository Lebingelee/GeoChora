"""TaskEnv delegates backend initialization to GeoPhys's public runtime owner."""
import os
import sys
from types import ModuleType

import pytest


def test_public_bootstrap_forwards_selection_and_preserves_environment(monkeypatch):
    from task_env.runtime.provider_bootstrap import init_task_env_backend

    calls = []
    geophys = ModuleType('geophys')
    geophys.init_taichi = lambda **kwargs: calls.append(kwargs)
    monkeypatch.setitem(sys.modules, 'geophys', geophys)
    monkeypatch.delenv('GEOPHYS_VULKAN_SPARSE_EXPERIMENTAL', raising=False)

    init_task_env_backend(' Vulkan ', compile_mode='balanced')
    assert calls == [{'arch': 'vulkan', 'compile_mode': 'balanced'}]
    assert os.environ['GEOPHYS_TAICHI_ARCH'] == 'vulkan'
    assert os.environ['GEOPHYS_VULKAN_SPARSE_EXPERIMENTAL'] == '0'
    monkeypatch.setenv('GEOPHYS_VULKAN_SPARSE_EXPERIMENTAL', '1')
    init_task_env_backend('vulkan')
    assert os.environ['GEOPHYS_VULKAN_SPARSE_EXPERIMENTAL'] == '1'


def test_public_bootstrap_rejects_unknown_arch_without_initializing(monkeypatch):
    from task_env.runtime.provider_bootstrap import init_task_env_backend

    geophys = ModuleType('geophys')
    geophys.init_taichi = lambda **kwargs: pytest.fail('invalid backend reached GeoPhys')
    monkeypatch.setitem(sys.modules, 'geophys', geophys)
    monkeypatch.setenv('GEOPHYS_TAICHI_ARCH', 'cpu')
    with pytest.raises(ValueError, match='unsupported runtime arch'):
        init_task_env_backend('invalid')
    assert os.environ['GEOPHYS_TAICHI_ARCH'] == 'cpu'
