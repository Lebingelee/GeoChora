"""Source leases and Controller choices across the common reset transaction."""

from types import SimpleNamespace

import pytest

from task_env.environment.reference_binding import (
    SourceBoundTaskBuilder, TaskBuildRequest, _StandardResetReconstruction,
)


def test_shared_source_builder_resamples_and_rejects_foreign_route():
    source = object()
    compiled = []
    def compile_source(request):
        compiled.append(request.provider)
        return {'source': source}
    builder = SourceBoundTaskBuilder(compile_source, lambda value, request: (value['source'], request.seed),
                                    backend='cpu', reuse_source=True)
    request = lambda provider, seed: TaskBuildRequest(provider, 'cpu', seed, 8, None, None)
    first = builder(request('mujoco', 31))
    second = builder(request('mujoco', 42))
    assert compiled == ['mujoco']
    assert first['reset_plan'] == (source, 31) and second['reset_plan'] == (source, 42)
    with pytest.raises(ValueError, match='requested provider/backend'):
        builder(request('geophys', 42))
    assert compiled == ['mujoco']


def test_failed_first_reset_plan_releases_only_new_source(monkeypatch):
    from task_env.runtime.sessions import source as source_module

    receipt = SimpleNamespace(closed=False)
    receipt.close = lambda: setattr(receipt, 'closed', True)
    monkeypatch.setattr(source_module, 'source_resource_receipt', lambda source: source)
    def reject(_value, _request):
        raise ValueError('invalid reset')
    builder = SourceBoundTaskBuilder(lambda _request: {'source': receipt}, reject,
                                    backend='cpu', reuse_source=True)
    with pytest.raises(ValueError, match='invalid reset'):
        builder(TaskBuildRequest('mujoco', 'cpu', 31, 8, None, None))
    assert receipt.closed and builder._cached is None


def test_cached_builder_rejects_closed_execution_source_before_reset_plan():
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1

    xml = b'<mujoco/>'
    receipt = ExecutionSourceReceiptV1.create(source_id='test-source', canonical_xml=xml,
        importer_xml=xml, closure_files={'canonical-source.xml': xml})
    source = SimpleNamespace(execution_source_receipt=receipt)
    plans = []
    builder = SourceBoundTaskBuilder(lambda _request: {'source': source},
        lambda _value, request: plans.append(request.seed), backend='cpu', reuse_source=True)
    request = lambda seed: TaskBuildRequest('mujoco', 'cpu', seed, 8, None, None)
    try:
        builder(request(31))
        builder(request(32))
        receipt.close()
        with pytest.raises(ValueError, match='snapshot is missing'):
            builder(request(33))
        assert plans == [31, 32]
    finally:
        receipt.close()


def test_cached_builder_rejects_stale_usd_source_before_reset_plan():
    stale = False
    def assert_fresh():
        if stale:
            raise ValueError('USD source is stale')
    source = SimpleNamespace(scene_source=SimpleNamespace(assert_fresh=assert_fresh))
    plans = []
    builder = SourceBoundTaskBuilder(lambda _request: {'source': source},
        lambda _value, request: plans.append(request.seed), backend='cuda', reuse_source=True)
    request = lambda seed: TaskBuildRequest('isaacsim', 'cuda', seed, 8, None, None)
    builder(request(31))
    stale = True
    with pytest.raises(ValueError, match='USD source is stale'):
        builder(request(32))
    assert plans == [31]


def test_failed_controller_compilation_releases_new_source(monkeypatch):
    from task_env.runtime.sessions import source as source_module

    receipt = SimpleNamespace(closed=False)
    receipt.close = lambda: setattr(receipt, 'closed', True)
    monkeypatch.setattr(source_module, 'source_resource_receipt', lambda source: source)
    def reject(_value, _request):
        raise ValueError('invalid Controller')
    builder = SourceBoundTaskBuilder(lambda _request: {'source': receipt},
        lambda _value, _request: None, backend='cpu', reuse_source=True,
        compile_control=reject)
    with pytest.raises(ValueError, match='invalid Controller'):
        builder(TaskBuildRequest('mujoco', 'cpu', 31, 8, None, None))
    assert receipt.closed and builder._cached is None


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
