"""Provider-free binding and replay checks for the separately admitted R05c candidate."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.controllers.canonical.contracts import CanonicalControlTarget, GripperControlTarget
from task_env.runtime.sessions.common import LegacyStateBoundaryIdentity
from task_env.runtime.sessions.control_lifecycle import ControlLifecycleDispatchV1
from task_env.runtime.sessions.control_submission import submit_control_command
from task_env.runtime.sessions.legacy_native_feedback_binding import (
    LegacyNativeFeedbackBindingV1, native_feedback_interval,
)
from task_env.diagnostics.tasks.test_v211_control_submission_contract import _Clock, _ack


def case():
    joints = tuple(f'robot/joint-{i}' for i in range(1, 8))
    positions = dict.fromkeys(joints, 0.)
    target = CanonicalControlTarget('canonical-control-v0', 'b' * 64, 'controller-1',
        joints, positions, positions, GripperControlTarget('robot/gripper', .02, 30., .02))
    receipt = SimpleNamespace(source_closure_digest='a' * 64)
    source = SimpleNamespace(source_id='task', source_closure_digest=None,
        execution_source_receipt=receipt, joint_targets={j: f'act-{i}' for i, j in enumerate(joints)},
        open_actuators=('hand-actuator',), position_subject_binding=None)
    controller = SimpleNamespace(identity='controller-1', control_submission_writer_id='writer-1',
                                 gripper_semantic_id='robot/gripper')
    boundary = LegacyStateBoundaryIdentity('legacy-state-boundary-identity-v1', 'episode-1',
        'reset-1', 'b' * 64, 'task', 'a' * 64, 'scene-1', 'materialization-1', 0, 0)
    state = SimpleNamespace(control_step=0, to_mapping=lambda: {'control_step': 0})
    session = SimpleNamespace(_source=source, _artifact=SimpleNamespace(identity_hash='b' * 64,
        timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.01)),
        _provider='geophys', provider_materialization_id='materialization-1', episode_id='episode-1',
        state_revision=0, snapshot=lambda: state, state_boundary_identity=lambda: boundary)
    binding = LegacyNativeFeedbackBindingV1('task', 'a' * 64, 'b' * 64, 'controller-1',
        'writer-1', tuple(sorted(source.joint_targets.items())), 'robot/gripper',
        ('hand-actuator',), 'materialization-1', source, receipt, controller)
    session._legacy_native_feedback_binding = binding
    session._control_lifecycle_dispatch = ControlLifecycleDispatchV1(
        'control-lifecycle-dispatch-v1', 'position-target', 'task', 'a' * 64, 'b' * 64,
        'episode-1', boundary.boundary_id, 0, 0, ('controller-1',), 'prepared')
    return session, controller, state, target, boundary, binding


def submit(session, target, boundary, binding, writes):
    return submit_control_command(session, target, command_kind='position-target',
        command_sha256=target.identity_hash, source_id='task', source_closure_sha256='a' * 64,
        artifact_sha256='b' * 64, boundary=boundary, sample_clock=_Clock(), controller_generation=0,
        controller_identities=('controller-1',), writer_ids=('writer-1',),
        resource_ids=binding.resources, resource_owners=(('writer-1', binding.resources),),
        units=('arm-position:rad', 'gripper-position:m'), lowering='test',
        subject_execution_mode='native-feedback', lower=lambda: (writes.append(True), _ack())[1])


def test_real_interval_commit_and_replay_gate():
    session, controller, state, target, boundary, binding = case()
    writes = []
    with native_feedback_interval(session, target, state, controller=controller):
        submit(session, target, boundary, binding, writes)
    assert writes == [True]
    outer = session._last_scene_control_submission
    assert outer['status'] == 'acknowledged'
    row, = outer['interval']['contributions']
    assert (row['command_kind'], row['composition'], row['start_substep'], row['end_substep']) == (
        'position-reference-native-feedback', 'controller-managed', 0, 5)
    assert outer['interval']['binding_sha256'] == binding.identity_hash
    with pytest.raises(ValueError, match='already consumed'):
        with native_feedback_interval(session, target, state, controller=controller):
            pass


@pytest.mark.parametrize('tamper', ('source', 'controller', 'owner', 'boundary'))
def test_tampering_or_missing_inflight_never_calls_provider(tamper):
    session, controller, state, target, boundary, binding = case()
    writes = []
    if tamper == 'source':
        session._source.joint_targets[next(iter(session._source.joint_targets))] = 'foreign'
    elif tamper == 'controller':
        controller.identity = 'foreign'
    elif tamper == 'owner':
        session._source.execution_source_receipt = SimpleNamespace(source_closure_digest='a' * 64)
    if tamper == 'boundary':
        with pytest.raises(ValueError, match='live binding'):
            submit(session, target, boundary, binding, writes)
    else:
        with pytest.raises(ValueError, match='admitted owners'):
            with native_feedback_interval(session, target, state, controller=controller):
                submit(session, target, boundary, binding, writes)
    assert not writes
    assert not getattr(session, '_control_submission_consumed', set())
