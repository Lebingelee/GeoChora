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


def test_failed_reset_retains_previous_runtime_owner_until_env_close(monkeypatch):
    from task_env.environment import reference_binding
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import source as source_module

    events = []
    previous = SimpleNamespace(
        close=lambda: events.append('session'),
        close_runtime_owner=lambda: events.append('owner'),
    )
    def reject_reconstruction(*args, **kwargs):
        raise RuntimeError('reconstruction failed')
    reconstruction = SimpleNamespace(use_binding=lambda binding: None,
                                     reconstruct=reject_reconstruction)
    state = SimpleNamespace(fault=None, require_open=lambda message: None)
    env = SimpleNamespace(
        _episode_execution_state=lambda: state, _task_rgb_config=None,
        _physical_reset_selection=None, _physical_execution=lambda: None,
        recorder=None, binding=SimpleNamespace(prepare_reset_switch=None),
        _reset_reconstruction=reconstruction, resolved_public_config=None,
        value={'source': object()}, _selected_execution_context=lambda: (None, None),
        _position_episode_end=None, session=previous, artifact=object(),
        _close_camera_consumer=lambda: None, reset_failure_receipt={},
        _latch_fault=lambda phase, error: None, _execution_fault=object(),
    )
    monkeypatch.setattr(reference_binding, 'prepare_selected_reset', lambda *args, **kwargs: 31)
    monkeypatch.setattr(source_module, 'close_source_and_task_resources',
                        lambda source, binding, error=None: error)
    operations = SelectedReferenceEnv._prepare_reference_reset(env, seed=31)
    with pytest.raises(RuntimeError, match='reconstruction failed') as caught:
        operations['prepare']()
    operations['on_failure']('prepare', caught.value)
    assert events == ['session']
    assert env.session is None
    SelectedReferenceEnv._close_reference_resources(env)
    assert events == ['session', 'session', 'owner']
    SelectedReferenceEnv._close_reference_resources(env)
    assert events == ['session', 'session', 'owner']


@pytest.mark.parametrize('requested_seed', [None, 47])
def test_rejected_reset_preflight_preserves_task_rng(requested_seed):
    from copy import deepcopy
    import numpy as np
    from task_env.environment.reference_env import SelectedReferenceEnv

    env = object.__new__(SelectedReferenceEnv)
    env._np_random = np.random.default_rng(31)
    env._np_random_seed = 31
    old_rng = env._np_random
    old_state = deepcopy(old_rng.bit_generator.state)
    env.binding = SimpleNamespace(task_reset_sampler=lambda rng: rng.random())
    env._reset_reconstruction = SimpleNamespace(sampled_reset=None)
    env.config = None
    env._execute_reset_operations = lambda prepare: prepare()
    def reject(**kwargs):
        raise ValueError('preflight rejected')
    env._prepare_reference_reset = reject
    with pytest.raises(ValueError, match='preflight rejected'):
        env._reset_selected_task(seed=requested_seed, options=None)
    assert env._np_random is old_rng
    assert env._np_random_seed == 31
    assert env._np_random.bit_generator.state == old_state
    assert env._reset_reconstruction.sampled_reset is None
