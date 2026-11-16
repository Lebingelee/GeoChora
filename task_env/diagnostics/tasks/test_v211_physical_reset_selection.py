"""Provider-free reset selection: semantic identity, generation and preflight."""
from types import SimpleNamespace
import numpy as np
import pytest

from task_env.artifacts.state import StateRequirements
from task_env.controllers.canonical.reset_selection import PhysicalResetSelection
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1


def _factory(kind, **parameters):
    plan, _, _, _ = _case()
    identity = ('c'*64 if parameters else {'A':'a'*64,'B':'b'*64}[kind])
    controller = SimpleNamespace(binding=plan.binding, identity=identity,
                                 writer_id='controller-a', action_shape=(8,), compute=lambda *args: None)
    return PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 0)


def test_same_shape_aba_rejects_prior_generations_and_foreign_candidate():
    selection = PhysicalResetSelection(_factory, initial_kind='A', allowed_kinds=('A','B'))
    first = selection.prepare(); selection.commit(first)
    old_a = selection.bind_action(np.arange(8.))
    assert np.array_equal(selection.validate_action(old_a), np.arange(8.))
    second = selection.prepare('B'); assert selection.current is first
    selection.commit(second)
    with pytest.raises(ValueError, match='stale or foreign'):
        selection.validate_action(old_a)
    old_b = selection.bind_action(np.arange(8.))
    third = selection.prepare('A'); selection.commit(third)
    assert third.spec_id == first.spec_id and third.execution.generation == 3
    for old in (old_a, old_b):
        with pytest.raises(ValueError, match='stale or foreign'):
            selection.validate_action(old)
    other = PhysicalResetSelection(_factory, initial_kind='A', allowed_kinds=('A','B'))
    with pytest.raises(ValueError, match='stale or foreign'):
        other.commit(other.prepare().__class__(object(), 0, first.kind, (), first.execution, first.spec_id))
    with pytest.raises(ValueError, match='stale or foreign'):
        selection.commit(third)


def test_fixed_semantics_rejects_same_shape_change_before_commit_and_bad_batches():
    selection = PhysicalResetSelection(_factory, initial_kind='A', allowed_kinds=('A','B'),
                                       space_policy='fixed_semantic')
    first = selection.prepare(); selection.commit(first)
    with pytest.raises(ValueError, match='fixed semantic'):
        selection.prepare('B')
    assert selection.current is first
    for values in (np.zeros((2,8)), np.full(8, np.nan), np.array([True]*8)):
        with pytest.raises(ValueError, match='finite scalar layout'):
            selection.validate_action(selection.bind_action(values))
    with pytest.raises(ValueError, match='spec_id, generation'):
        selection.validate_action(np.zeros(8))


def test_parameter_change_has_new_spec_and_is_preserved_on_plain_reset():
    selection = PhysicalResetSelection(_factory, initial_kind='A', allowed_kinds=('A','B'))
    first = selection.prepare(); selection.commit(first)
    candidate = selection.prepare({'kind':'A','parameters':{'kp':100.}})
    assert candidate.spec_id != first.spec_id and selection.current is first
    selection.commit(candidate)
    assert selection.describe()['parameters'] == {'kp':100.}
    following = selection.prepare()
    assert following.spec_id == candidate.spec_id and dict(following.parameters) == {'kp':100.}


def test_live_physical_controller_switch_rejected_before_session_effect():
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.environment.types import StageUnavailableError
    env = object.__new__(SelectedReferenceEnv)
    effects = []
    env.binding = SimpleNamespace(physical_control_profile=lambda _: effects.append('profile'))
    env.session = SimpleNamespace(step=lambda: effects.append('step'), close=lambda: effects.append('close'))
    with pytest.raises(StageUnavailableError, match='only change at reset'):
        env.switch_position_controller(object())
    assert effects == []


def test_fixed_semantic_cached_space_accepts_new_generation_and_validator_rejects_old():
    selection = PhysicalResetSelection(_factory, initial_kind='A', allowed_kinds=('A','B'),
                                       space_policy='fixed_semantic')
    selection.commit(selection.prepare())
    cached_space = selection.action_space()
    old = selection.bind_action(np.zeros(8, dtype=np.float32))
    selection.commit(selection.prepare())
    new = selection.bind_action(np.zeros(8, dtype=np.float32))
    assert cached_space.contains(new)
    assert np.array_equal(selection.validate_action(new), np.zeros(8))
    with pytest.raises(ValueError, match='stale or foreign'):
        selection.validate_action(old)
