"""Physical IPC values and build binding; no native simulation in these tests."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.diagnostics.tasks.physical_contract_fixtures import _case, _joint_receipt
from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1
from task_env.runtime.sessions.physical_control import prepare_physical_command_batch
from task_env.runtime.sessions.transport import RemoteSession, _encode, _decode


def test_resolved_effort_roundtrip_keeps_context_and_rejects_extra_fields():
    plan, context, effort, assessment = _case()
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context,
                                  (effort('one', 1.25),), (), ())
    resolved = prepare_physical_command_batch(plan, batch, expected_context=context,
        assessment=assessment('joint_effort', 'sum'), joint_build_receipt=_joint_receipt(plan, context))
    encoded = _encode(resolved)
    assert _decode(encoded) == resolved
    encoded['value']['unowned'] = 'port'
    with pytest.raises(ValueError, match='transport fields'):
        _decode(encoded)
    with pytest.raises(ValueError, match='joint effort only'):
        _encode(replace(resolved, body_wrenches=(object(),)))


def test_remote_binding_is_published_only_after_child_confirmation(monkeypatch):
    from task_env.runtime.sessions import selected_materialization as assembly
    declared = object()
    facts = {'generation': 3, 'controller_versions': (('writer', 'a'*64, None),)}
    monkeypatch.setattr(assembly, 'physical_execution_facts', lambda _: facts)
    remote = object.__new__(RemoteSession)
    remote._call = lambda _: {**facts, 'generation': 2}
    with pytest.raises(ValueError, match='binding differs'):
        remote.bind_physical_control(declared)
    assert remote.physical_control_execution is None
    remote._call = lambda _: facts
    remote.bind_physical_control(declared)
    assert remote.physical_control_execution is declared
    with pytest.raises(ValueError, match='bound once'):
        remote.bind_physical_control(declared)


def test_shared_assembly_selects_position_before_composed_physical_port():
    from task_env.runtime.sessions.selected_materialization import materialize_selected_session
    seen = []
    value = {'source': object(), 'physical_execution': object()}
    selected = SimpleNamespace(position_profiles=('selected-profile',))
    session = materialize_selected_session(object(), object(), value=value, binding=None,
        selected=selected, position=('plan', 'joints', 'frames', 'binding'),
        materialize=lambda *_a, **_k: pytest.fail('created a second physical world'),
        materialize_control=lambda *_a, **kwargs: seen.append(kwargs) or 'native-session')
    assert session == 'native-session'
    assert seen[0]['controller_profile'] == ('selected-profile',)
    assert seen[0]['controller_binding_plan'] == 'plan'


def test_model_proxy_refuses_foreign_metadata_or_a_stepping_result():
    import numpy as np
    from task_env.runtime.sessions.transport import _RemoteSourceDynamics
    plan, context, *_ = _case()
    session = SimpleNamespace(provider_materialization_id=context.boundary.provider_materialization_id,
        episode_id=context.boundary.episode_id,
        physical_control_execution=SimpleNamespace(compiled=plan))
    metadata = {'source_closure_sha256': plan.binding.source_closure_sha256,
                'boundary': context.boundary}
    with pytest.raises(ValueError, match='episode/source'):
        _RemoteSourceDynamics(session, {**metadata, 'source_closure_sha256': '0'*64})
    proxy = _RemoteSourceDynamics(session, metadata)
    session._call = lambda *_: {'mass_matrix': [[1.]], 'bias': [2.],
                              'boundary': context.boundary, 'physics_steps': 1}
    with pytest.raises(ValueError, match='stale or advancing'):
        proxy.evaluate([0.], [0.], context.boundary)
    session._call = lambda *_: {'mass_matrix': [[1.]], 'bias': [2.],
                              'boundary': context.boundary, 'physics_steps': 0}
    result = proxy.evaluate(np.array([0.]), np.array([0.]), context.boundary)
    assert result['mass_matrix'].shape == (1,1) and result['bias'].dtype == np.float64


def test_another_controller_reuses_physical_assembly_without_profile_dispatch():
    from task_env.artifacts.state import StateRequirements
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1
    from task_env.runtime.sessions.selected_materialization import materialize_selected_session
    plan, context, effort, _ = _case()
    class AnotherController:
        binding = plan.binding
        identity = 'f'*64
        writer_id = 'controller-a'
        def compute(self, action, view, expected_context):
            return PhysicalCommandBatchV1('physical-command-batch-v1', expected_context,
                                         (effort('another', action),), (), ())
    controller = AnotherController()
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {},
        StateRequirements('state-requirements-v1','controller','controller-a',()),1)
    seen = []
    actual = materialize_selected_session('artifact', 'execution',
        value={'source':'source','physical_execution':execution}, binding=None,
        selected=SimpleNamespace(controller=controller),
        materialize=lambda *_a, **kwargs: seen.append(kwargs['source']) or 'session')
    assert actual == 'session' and seen == ['source']
    assert execution.controller_batch(.2,None,context).joint_efforts[0].value == .2
