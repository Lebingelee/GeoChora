"""Source leases and Controller choices across the common reset transaction."""

from types import SimpleNamespace

import pytest

from task_env.environment.reference_binding import _StandardResetReconstruction


def test_reconstruction_replaces_source_only_after_validation(monkeypatch):
    from task_env.runtime.sessions import source as source_module

    old = SimpleNamespace(closed=False)
    new = SimpleNamespace(closed=False)
    old.close = lambda: setattr(old, 'closed', True)
    new.close = lambda: setattr(new, 'closed', True)
    monkeypatch.setattr(source_module, 'source_resource_receipt', lambda value: value)
    checked = []
    binding = SimpleNamespace(compose_robot_source=None, reset_runtime_input=None,
        build_for_request=lambda *args: {'source': new, 'solution': None},
        validate_external_solution=lambda value, solution: checked.append((value, solution)))
    strategy = _StandardResetReconstruction(binding, 'mujoco', 'cpu', 8)
    current = {'source': old}
    def reject(_value):
        raise ValueError('source mismatch')
    with pytest.raises(ValueError, match='source mismatch'):
        strategy.reconstruct(current, 'artifact', 31, None, lambda artifact, *_: artifact,
                             verify_source=reject)
    assert new.closed and not old.closed

    new.closed = False
    solution = object()
    result = strategy.reconstruct(current, 'artifact', 42, solution, lambda artifact, *_: artifact,
                                  verify_source=lambda value: None)
    assert old.closed and not new.closed
    assert result.value['source'] is new and result.seed == 42
    assert checked == [(result.value, solution)]


def test_prepared_controller_value_is_shared_without_mutating_source_mapping():
    from task_env.controllers.canonical.reset_selection import PreparedPhysicalSelection

    controller = object()
    execution = SimpleNamespace(controllers=(controller,), selection_profile_id='profile')
    selection = PreparedPhysicalSelection(object(), 0, 'kind', (), execution, 'spec')
    original = {'source': object(), 'controller': object()}
    selected = selection.bind_value(original)
    assert selected['source'] is original['source']
    assert selected['controller'] is controller and original['controller'] is not controller
    assert selected['physical_execution'] is execution
    assert selected['selected_controller_profile_id'] == 'profile'
