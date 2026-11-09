"""Provider-free admission checks for bounded physical action slices."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env import PhysicalActionSequenceV1, PhysicalActionSliceV1


def test_contiguous_same_controller_slices_and_input_rejection():
    one, two = 'a' * 64, 'b' * 64
    first = PhysicalActionSliceV1(0, 2, ((one, (1.0,)), (two, (0.0,))))
    second = PhysicalActionSliceV1(2, 5, ((one, (2.0,)), (two, (0.0,))))
    sequence = PhysicalActionSequenceV1((first, second))
    sequence.validate(substeps=5, controller_identities=(one, two))
    assert sequence.identity_hash != replace(sequence, slices=(first, replace(second, end_substep=4))).identity_hash
    for changed in (replace(second, start_substep=1), replace(second, start_substep=3),
                    replace(second, start_substep=2.0)):
        with pytest.raises(ValueError):
            replace(sequence, slices=(first, changed)).validate(substeps=5, controller_identities=(one, two))
    with pytest.raises(ValueError, match='cover the bound Controllers'):
        replace(sequence, slices=(first, replace(second, actions=((one, (2.0,)),)))).validate(
            substeps=5, controller_identities=(one, two))
    with pytest.raises(ValueError, match='finite numeric'):
        replace(sequence, slices=(first, replace(second, actions=((one, (True,)), (two, (0.0,)))))).validate(
            substeps=5, controller_identities=(one, two))


def test_existing_submission_owner_binds_each_nonoverlapping_batch_and_rejects_replay():
    from task_env.artifacts.state import StateRequirements
    from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1
    from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case, _joint_receipt
    from task_env.runtime.sessions.control_submission import submit_control_command
    from task_env.runtime.sessions.physical_control import (PhysicalControlExecutionV1,
        ResolvedPhysicalSequenceV1, prepare_physical_command_batch)

    plan, context, effort, assessment = _case()
    controller = SimpleNamespace(identity='c'*64, writer_id='controller-a', binding=plan.binding,
                                 generation=7, compute=lambda *_: None)
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1)
    def resolve(value):
        batch = PhysicalCommandBatchV1('physical-command-batch-v1', context,
                                       (effort('same-effect', value, 'exclusive'),), (), ())
        admitted = prepare_physical_command_batch(plan, batch, expected_context=context,
            assessment=assessment('joint_effort'), joint_build_receipt=_joint_receipt(plan, context))
        # Only the synthetic terminal uses this marker; it is not native evidence.
        return replace(admitted, mapping_provenance=('native_build',))
    first, second = resolve(1.), resolve(2.)
    action = PhysicalActionSequenceV1((PhysicalActionSliceV1(0, 2, ((controller.identity, (1.,)),)),
                                       PhysicalActionSliceV1(2, 5, ((controller.identity, (2.,)),))))
    sequence = ResolvedPhysicalSequenceV1(action, ((0, 2, first), (2, 5, second)))
    session = SimpleNamespace(_physical_port=SimpleNamespace(execution=execution),
        _physical_controller_versions=execution.controller_versions(), physical_control_generation=1,
        _artifact=SimpleNamespace(identity_hash='a'*64,
            timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.01)),
        _source=SimpleNamespace(source_id='source-a', source_closure_digest='b'*64),
        _provider='test-double', provider_materialization_id='material-a', episode_id='episode-a',
        _prepared_physical_sequence=sequence,
        state_boundary_identity=lambda: context.boundary)
    calls = []
    kwargs = dict(command_kind='physical-effort-sequence', command_sha256=sequence.identity_hash,
        source_id='source-a', source_closure_sha256='b'*64, artifact_sha256='a'*64,
        boundary=context.boundary, sample_clock=context.clock, controller_generation=1,
        controller_identities=(controller.identity,), writer_ids=('controller-a',),
        resource_ids=('arm/drive',), units=('N*m',), lowering='fake-sequence-stage',
        lower=lambda: calls.append('write'))
    forged = replace(sequence, action=replace(action, slices=(
        action.slices[0], replace(action.slices[1], actions=((controller.identity, (3.,)),)))))
    with pytest.raises(ValueError, match='not prepared by this live session'):
        submit_control_command(session, forged, **{**kwargs, 'command_sha256': forged.identity_hash})
    assert calls == [] and not getattr(session, '_control_submission_consumed', set())
    foreign_context = replace(context, generation=2)
    foreign_effort = replace(second.input_batch.joint_efforts[0], context=foreign_context)
    foreign_batch = replace(second.input_batch, context=foreign_context, joint_efforts=(foreign_effort,))
    foreign_sequence = replace(sequence, slices=((0, 2, first), (2, 5, replace(second, input_batch=foreign_batch))))
    session._prepared_physical_sequence = foreign_sequence
    with pytest.raises(ValueError, match='context differs'):
        submit_control_command(session, foreign_sequence,
                               **{**kwargs, 'command_sha256': foreign_sequence.identity_hash})
    assert calls == [] and not getattr(session, '_control_submission_consumed', set())
    session._prepared_physical_sequence = sequence
    unbound = SimpleNamespace(**vars(session))
    unbound._physical_port = None
    with pytest.raises(ValueError, match='requires the live source-bound scene interval'):
        submit_control_command(unbound, sequence, **kwargs)
    assert calls == [] and not getattr(unbound, '_control_submission_consumed', set())
    submit_control_command(session, sequence, **kwargs)
    outer = session._last_scene_control_submission
    assert calls == ['write']
    assert outer['inner_batch_sha256'] == (first.input_batch.identity_hash, second.input_batch.identity_hash)
    assert [(item['start_substep'], item['end_substep']) for item in outer['interval']['contributions']] == [(0, 2), (2, 5)]
    assert [item['controller_generation'] for item in outer['interval']['contributions']] == [7, 7]
    assert session._prepared_physical_sequence is None
    session._prepared_physical_sequence = sequence  # fixture simulates a duplicate prepare attempt
    with pytest.raises(ValueError, match='already has a logical submission'):
        submit_control_command(session, sequence, **kwargs)
    assert calls == ['write']
    fresh = SimpleNamespace(**vars(session))
    fresh._control_submission_consumed = set()
    fresh._prepared_physical_sequence = sequence
    progress = {'attempted_writer_ids': [], 'completed_writer_ids': []}
    def fail_after_attempt():
        progress['attempted_writer_ids'].append('controller-a')
        raise RuntimeError('injected sequence staging failure')
    with pytest.raises(RuntimeError, match='staging failure'):
        submit_control_command(fresh, sequence, **{**kwargs, 'lower': fail_after_attempt,
                                                    'submission_progress': progress})
    assert fresh._last_control_submission['status'] == 'failed_partial'
    assert fresh._last_control_submission['attempted_writer_ids'] == ('controller-a',)
    assert fresh._last_control_submission['completed_writer_ids'] == ()
    assert fresh._prepared_physical_sequence is None


def test_mujoco_sequence_port_requires_common_submission_before_native_write():
    from task_env.runtime.sessions.mujoco_physical import MuJoCoPhysicalPort
    from task_env.runtime.sessions.physical_control import ResolvedPhysicalSequenceV1
    controller = SimpleNamespace(identity='a'*64)
    execution = SimpleNamespace(controllers=(controller,), controller_versions=lambda: (('writer', 'a'*64, None),))
    action = PhysicalActionSequenceV1((PhysicalActionSliceV1(0, 5, ((controller.identity, (1.,)),)),))
    resolved = SimpleNamespace(input_batch=SimpleNamespace(identity_hash='b'*64))
    sequence = ResolvedPhysicalSequenceV1(action, ((0, 5, resolved),))
    port = object.__new__(MuJoCoPhysicalPort)
    port.execution = execution
    port.session = SimpleNamespace(_physical_controller_versions=execution.controller_versions(),
        _artifact=SimpleNamespace(timebase=SimpleNamespace(control_substeps=5)),
        _prepared_physical_sequence=sequence)
    with pytest.raises(ValueError, match='pending common scene submission'):
        port.write_sequence(sequence)


def test_sequence_capability_rejects_unverified_legacy_observer():
    from task_env.environment.types import StageUnavailableError
    from task_env.runtime.sessions.physical_sequence import describe_physical_sequence_capability
    env = SimpleNamespace(provider='mujoco', backend='cpu', _legacy_observer_requested=True,
        binding=SimpleNamespace(physical_direct_effort_feedback=False,
            physical_observation_binding=lambda _env: None, external_actions=True),
        session=SimpleNamespace(), recorder=None)
    with pytest.raises(StageUnavailableError, match='RGB/observer, caller wrench or active Recorder'):
        describe_physical_sequence_capability(env, None)
    env._legacy_observer_requested = False
    env.recorder = SimpleNamespace(_frozen=False)
    with pytest.raises(StageUnavailableError, match='active Recorder'):
        describe_physical_sequence_capability(env, None)
    env.recorder = None
    env.provider = 'geophys'
    with pytest.raises(StageUnavailableError, match='MuJoCo CPU'):
        describe_physical_sequence_capability(env, None)
