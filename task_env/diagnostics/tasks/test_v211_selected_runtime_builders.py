"""Provider-free negative checks for declared runtime construction owners."""
from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.selected_materialization import RuntimeBuildResult, build_selected_runtime


def _env(execution):
    return SimpleNamespace(value={'source': SimpleNamespace(), 'physical_execution': execution},
        binding=SimpleNamespace(scalar_control_binding=None, physical_control_profile=None))


def _selected():
    return SimpleNamespace(leaf_plan=None, position_capabilities=())


def test_undeclared_or_foreign_builder_fails_before_provider_creation():
    calls = []
    with pytest.raises(TypeError, match='lacks its runtime construction capability'):
        build_selected_runtime(_env(object()), _selected(), None, None,
                               lambda *_a, **_k: calls.append('native'), None)
    class Foreign:
        def selected_runtime_builder(self, _selected):
            return SimpleNamespace(declaring_owner=object(), priority=40, create=lambda *_: calls.append('native'))
    with pytest.raises(ValueError, match='foreign or invalid'):
        build_selected_runtime(_env(Foreign()), _selected(), None, None,
                               lambda *_a, **_k: calls.append('native'), None)
    assert calls == []


def test_controller_declared_owner_constructs_and_publishes_its_state_capability():
    events = []
    state_capability = SimpleNamespace(supports_stop=True)
    class Owner:
        def selected_runtime_builder(self, _selected):
            owner = self
            class Builder:
                declaring_owner = owner
                priority = 30
                def create(self, env, *_):
                    events.append('owner-created-session')
                    env.session = object()
                    return RuntimeBuildResult((state_capability,))
            return Builder()
    owner = Owner()
    selected = SimpleNamespace(leaf_plan=None, position_capabilities=(owner,))
    env = _env(None)
    result = build_selected_runtime(env, selected, None, None, None, None)
    assert events == ['owner-created-session']
    assert result.initial_capabilities == (state_capability,)
    assert env._selected_state_capabilities == (state_capability,)
    assert env._selected_reset_stop_capability is True
