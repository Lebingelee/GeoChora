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


@pytest.mark.parametrize('role', ('leaf', 'position', 'mixed', 'scalar'))
def test_incomplete_declared_owner_cannot_fall_back_to_another_builder(role):
    """A declared capability without a builder must not silently select scalar."""
    events = []
    class ScalarOwner:
        def selected_runtime_builder(self, _selected):
            owner = self
            return SimpleNamespace(declaring_owner=owner, priority=10,
                create=lambda *_: events.append('provider created'))
    env = _env(None)
    env.binding.scalar_control_binding = ScalarOwner()
    selected = _selected()
    if role == 'leaf':
        selected.leaf_plan = object()
    elif role == 'position':
        selected.position_capabilities = (object(),)
    elif role == 'mixed':
        env.value['source'].mixed_actuator_plan = object()
    else:
        env.binding.scalar_control_binding = object()
    with pytest.raises(TypeError, match='declared owner lacks'):
        build_selected_runtime(env, selected, None, None, None, None)
    assert not events


def test_equal_priority_declarations_are_rejected_before_creating_session():
    events = []
    class Owner:
        def selected_runtime_builder(self, _selected):
            return SimpleNamespace(declaring_owner=self, priority=30,
                create=lambda *_: events.append('provider created'))
    env = _env(None)
    selected = SimpleNamespace(leaf_plan=Owner(), position_capabilities=(Owner(),))
    with pytest.raises(ValueError, match='conflicting construction capabilities'):
        build_selected_runtime(env, selected, None, None, None, None)
    assert not events


def test_position_and_physical_owners_cooperate_in_the_actual_priority_order(monkeypatch):
    from task_env.runtime.sessions.control import SelectedPositionCapabilityV1
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1
    from task_env.runtime.sessions.selected_materialization import PositionRuntimeBuilder

    events = []
    position_owner = object()
    capability = SelectedPositionCapabilityV1(position_owner)
    physical = object.__new__(PhysicalControlExecutionV1)
    selected = SimpleNamespace(leaf_plan=None, position_capabilities=(capability,))
    env = _env(physical)
    env.binding.physical_control_profile = lambda _env: physical
    env.binding.physical_observation_binding = object()
    state = SimpleNamespace(supports_stop=True)
    class Session:
        def bind_physical_control(self, value):
            assert value is physical
            events.append('physical-bound')
    def create(_builder, actual_env, *_args):
        events.append('position-created')
        actual_env.session = Session()
        return RuntimeBuildResult((state,))
    monkeypatch.setattr(PositionRuntimeBuilder, 'create', create)
    result = build_selected_runtime(env, selected, None, None, None, None)
    assert events == ['position-created', 'physical-bound']
    assert result.initial_capabilities == (state,)
    assert len(env._selected_state_capabilities) == 2
    assert env._selected_state_capabilities[1].execution is physical
