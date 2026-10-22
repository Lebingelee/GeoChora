"""S1 lifecycle and refusal checks for the bounded C02c Position switch."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.recorders import load_structured_control_records_h5
from task_env.runtime.sessions.control import (
    apply_position_control_target,
    prepare_structured_action,
)
from task_env.tasks.reference_env import SelectedReferenceEnv


def _request(env, *, dx=0.0):
    frame = next(
        item for item in env.typed_state.view.frames
        if item.frame.entity_id == 'panda-main' and item.frame.frame_id == 'hand'
    )
    schema = env.position_plan.controller_bindings[0].action_schema
    arm = (
        frame.pose_world.position[0] + dx,
        *frame.pose_world.position[1:],
        *frame.pose_world.quaternion_wxyz,
    )
    from task_env.controllers.canonical.contracts import (
        ControlGroupActionV1,
        StructuredActionRequestV1,
    )

    return StructuredActionRequestV1(
        'structured-action-request-v1', env.position_plan.scene_identity_hash,
        env.position_plan.identity_hash,
        (
            ControlGroupActionV1(
                'control-group-action-v1', 'panda-main', 'arm', schema.schema_id,
                tuple(float(value) for value in arm),
            ),
            ControlGroupActionV1(
                'control-group-action-v1', 'panda-main', 'gripper', schema.schema_id,
                (1.0,),
            ),
        ),
    )


def _memory(profile):
    return (
        profile._plan_identity_hash, profile._episode_id,
        profile._reset_sample_id, profile._next_control_step,
        profile._activation_boundary_id,
    )


def _candidate(base, *, config=None):
    return PandaPositionServoProfileV1.from_source(
        base.env.artifact, base.source,
        config=config or base.env.controller.config,
    )


def _build_active_recording(tmp_path, *, horizon=5):
    pytest.importorskip('scene', reason='GeoPhys public Scene importer is required')
    base = build_position_candidate(tmp_path / 'source', provider='mujoco', horizon=horizon)
    env = base.env
    env.reset()
    env.start_recording(tmp_path / 'c02c-s1.h5')
    return base


def test_switch_is_boundary_only_seeds_fresh_memory_and_records_first_new_target(tmp_path, monkeypatch):
    base = _build_active_recording(tmp_path)
    env = base.env
    old = env.controller
    first_request = _request(env)
    env.step(first_request)
    _canonical0, old_target, _applied0 = env.last_position_transition
    boundary = env._published_position_typed_state.view.boundary
    old_memory = _memory(old)

    # reset() remains an episode-start API. A live boundary cannot be passed to it.
    with pytest.raises(ValueError, match='initial evaluation boundary'):
        old.reset(env.typed_state, env.position_plan)
    assert _memory(old) == old_memory

    switched = _candidate(
        base,
        config=replace(old.config, ik_position_gain=old.config.ik_position_gain * 0.5),
    )
    assert switched.identity != old.identity
    assert switched.controller_binding() == old.controller_binding()
    assert _memory(switched) == (None, None, None, None, None)

    calls = {'compute': 0, 'apply': 0, 'step': 0}
    original_compute = PandaPositionServoProfileV1.compute
    session_type = type(env.session)
    original_apply = session_type.apply_control
    original_step = session_type.step

    def counted_compute(profile, *args, **kwargs):
        calls['compute'] += 1
        return original_compute(profile, *args, **kwargs)

    def counted_apply(session, *args, **kwargs):
        calls['apply'] += 1
        return original_apply(session, *args, **kwargs)

    def counted_step(session, *args, **kwargs):
        calls['step'] += 1
        return original_step(session, *args, **kwargs)

    recorder_counts = (env.recorder.transition_count, env.recorder.observation_count)
    provider_state = env.session.snapshot()
    with monkeypatch.context() as patcher:
        patcher.setattr(PandaPositionServoProfileV1, 'compute', counted_compute)
        patcher.setattr(session_type, 'apply_control', counted_apply)
        patcher.setattr(session_type, 'step', counted_step)
        event = env.switch_position_controller(switched)
    assert calls == {'compute': 0, 'apply': 0, 'step': 0}
    assert env.session.snapshot().to_mapping() == provider_state.to_mapping()
    assert (env.recorder.transition_count, env.recorder.observation_count) == recorder_counts
    assert event.event_type == 'controller_instance_switch'
    assert event.boundary_index == boundary.control_step == 1
    assert event.payload['result'] == {
        'preparation': 'validated',
        'switch': 'effective',
        'first_control_application': 'pending_next_step',
    }
    assert event.payload['effective_boundary']['boundary_id'] == boundary.boundary_id
    assert event.payload['effective_clock']['sample_index'] == boundary.control_step
    assert event.payload['previous_controller']['controller_identity'] == old.identity
    assert event.payload['effective_controller']['controller_identity'] == switched.identity
    assert env.controller is switched and env.position_profiles == (switched,)
    assert env.session._position_profiles_by_writer[switched.writer_id] is switched
    assert _memory(old) == old_memory
    assert _memory(switched) == (
        env.position_plan.identity_hash, boundary.episode_id,
        boundary.reset_sample_id, boundary.control_step, boundary.boundary_id,
    )
    superseding = _candidate(
        base,
        config=replace(old.config, ik_position_gain=old.config.ik_position_gain * 0.25),
    )
    with pytest.raises(RuntimeError, match='must be applied by one complete step'):
        env.switch_position_controller(superseding)
    assert _memory(superseding) == (None, None, None, None, None)
    assert (env.recorder.transition_count, env.recorder.observation_count) == recorder_counts

    # An old-parameter target forged for the current boundary is refused by the
    # active Profile identity before provider application.
    request = _request(env, dx=0.025)
    old_shadow = _candidate(base, config=old.config)
    activation = old_shadow._prepare_switch_activation(env.typed_state, env.position_plan)
    old_shadow._activate_switch_memory(activation)
    requested = prepare_structured_action(env.position_plan, request)[0][1]
    _old_canonical, current_boundary_old_target = old_shadow.compute(
        env.typed_state, requested, env.position_plan,
    )
    calls_before = dict(calls)
    with monkeypatch.context() as patcher:
        patcher.setattr(PandaPositionServoProfileV1, 'compute', counted_compute)
        patcher.setattr(session_type, 'apply_control', counted_apply)
        patcher.setattr(session_type, 'step', counted_step)
        for target in (old_target, current_boundary_old_target):
            with pytest.raises(ValueError, match='position target writer/Profile/plan/source boundary mismatch'):
                apply_position_control_target(
                    env.session, target,
                    controller_profile=switched, plan=env.position_plan,
                    publication=env.typed_state, scene=env.position_scene,
                    joint_bindings=env.position_joint_bindings,
                    frame_bindings=env.position_frame_bindings,
                )
    assert calls == calls_before

    env.step(request)
    canonical1, new_target, applied1 = env.last_position_transition
    assert new_target.controller_identity == switched.identity
    assert new_target.source_boundary.boundary_id == boundary.boundary_id
    assert applied1.target_hash == new_target.target.identity_hash
    assert switched._next_control_step == boundary.control_step + 1
    assert env._pending_position_switch is None
    assert not np.allclose(
        np.asarray(tuple(new_target.target.arm_position.values())),
        np.asarray(tuple(current_boundary_old_target.target.arm_position.values())),
        rtol=0.0, atol=1.0e-10,
    ), 'the changed Position parameter must alter the target for this non-deadband request'

    env.stop('c02c-s1')
    finish = env.finish_recording('c02c-s1')
    loaded = load_structured_control_records_h5(finish['path'])
    assert (loaded['transition_count'], loaded['observation_count']) == (2, 3)
    switch_events = [event for event in loaded['boundary_events']
                     if event.event_type == 'controller_instance_switch']
    assert len(switch_events) == 1
    assert switch_events[0].payload['effective_controller']['controller_identity'] == switched.identity
    second_writer = loaded['structured_controls'][1].writer_controls[0]
    assert second_writer['controller_target']['payload']['controller_identity'] == switched.identity
    assert second_writer['controller_target']['identity_hash'] == second_writer['applied_control']['target_hash']
    nested = second_writer['canonical_action']
    assert nested['position_target_v1']['source_boundary']['control_step'] == boundary.control_step
    application = nested['controller_switch_application']
    assert application['switch_id'] == switch_events[0].payload['switch_id']
    assert application['status'] == 'target_and_applied_ack_recorded'
    env.close()


@pytest.mark.parametrize(
    'mutation', [
        'same_identity', 'schema', 'frame', 'resource', 'source', 'timebase',
        'required_state', 'identity', 'config',
    ],
)
def test_rejected_candidate_preserves_active_controller_memory_and_recording(
    tmp_path, mutation,
):
    base = _build_active_recording(tmp_path)
    env = base.env
    env.step(_request(env))
    active = env.controller
    candidate = _candidate(base)
    if mutation == 'same_identity':
        error = 'distinct parameterized instance'
    elif mutation == 'identity':
        candidate.identity = '0' * 64
        error = 'identity/configuration changed after construction'
    elif mutation == 'config':
        candidate.config = replace(candidate.config, ik_position_gain=0.4)
        error = 'identity/configuration changed after construction'
    elif mutation == 'schema':
        binding = candidate.controller_binding()
        candidate.controller_binding = lambda: replace(
            binding,
            action_schema=replace(binding.action_schema, reference='base'),
        )
        error = 'Controller/action/group contract mismatch'
    elif mutation == 'frame':
        candidate.tcp_profile = replace(candidate.tcp_profile, hand_frame_id='other-hand')
        error = 'schema, source, frame, unit, timebase or ownership'
    elif mutation == 'resource':
        candidate._target_bindings['panda-main/joint1'] = 'foreign-actuator'
        error = 'plan actuator mapping mismatch|owned binding field'
    else:
        if mutation == 'source':
            candidate.source = replace(
                candidate.source,
                joint_targets={**candidate.source.joint_targets, 'panda-main/joint1': 'foreign-actuator'},
            )
            error = 'RuntimeSource identity or bindings changed'
        elif mutation == 'timebase':
            from task_env.artifacts import Timebase
            candidate.artifact = replace(candidate.artifact, timebase=Timebase(0.002, 4, 0.008))
            error = 'RuntimeSource identity or bindings changed'
        else:
            candidate.requirements = replace(
                candidate.requirements,
                requirements=tuple(candidate.requirements.requirements[:-1]),
            )
            error = 'Controller/action/group contract mismatch'
    active_memory = _memory(active)
    candidate_memory = _memory(candidate)
    recorder_counts = (env.recorder.transition_count, env.recorder.observation_count)
    physical = env.session.snapshot().to_mapping()
    with pytest.raises((ValueError, TypeError), match=error):
        env.switch_position_controller(candidate)
    assert env.controller is active
    assert env.session._position_profiles_by_writer[active.writer_id] is active
    assert _memory(active) == active_memory
    assert _memory(candidate) == candidate_memory
    assert (env.recorder.transition_count, env.recorder.observation_count) == recorder_counts
    assert env.session.snapshot().to_mapping() == physical
    assert env.execution_fault is None
    env.close()


def test_switch_rejects_closed_faulted_stopped_or_horizon_states():
    candidate = object()
    cases = (
        (dict(_closed=True), 'closed'),
        (dict(_closed=False, _execution_fault=object()), 'faulted'),
        (dict(_closed=False, _execution_fault=None, position_profile=True,
              dual_entity_position=False, _stopped=True), 'live, nonterminal'),
        (dict(_closed=False, _execution_fault=None, position_profile=True,
              dual_entity_position=False, _stopped=False, _position_episode_end=None,
              session=object(), _published_position_typed_state=object(),
              state=SimpleNamespace(control_step=1), horizon=1), 'horizon'),
    )
    for kwargs, message in cases:
        stub = SimpleNamespace(**kwargs)
        with pytest.raises(RuntimeError, match=message):
            SelectedReferenceEnv.switch_position_controller(stub, candidate)


def test_switch_requires_active_v3_recording_and_aligned_public_boundary(tmp_path):
    pytest.importorskip('scene', reason='GeoPhys public Scene importer is required')
    base = build_position_candidate(tmp_path / 'source', provider='mujoco', horizon=5)
    env = base.env
    env.reset()
    old = env.controller
    candidate = _candidate(
        base,
        config=replace(old.config, ik_position_gain=old.config.ik_position_gain * 0.5),
    )
    state = env.session.snapshot().to_mapping()
    candidate_memory = _memory(candidate)
    with pytest.raises(RuntimeError, match='active Generic H5 v3 recording'):
        env.switch_position_controller(candidate)
    assert env.controller is old and _memory(candidate) == candidate_memory
    assert env.session.snapshot().to_mapping() == state

    env.start_recording(tmp_path / 'c02c-unsafe-boundary.h5')
    reset_publication = env.typed_state
    request = _request(env)
    env.step(request)
    saved_publication = env._published_position_typed_state
    env._published_position_typed_state = reset_publication
    state = env.session.snapshot().to_mapping()
    old_memory = _memory(old)
    with pytest.raises(RuntimeError, match='last complete public control boundary'):
        env.switch_position_controller(candidate)
    assert env.controller is old and _memory(old) == old_memory
    assert _memory(candidate) == candidate_memory
    assert env.session.snapshot().to_mapping() == state
    env._published_position_typed_state = saved_publication
    env.close()


def test_switch_rejects_invalid_required_joint_unit_without_mutating_active_profile(tmp_path):
    base = _build_active_recording(tmp_path)
    env = base.env
    env.step(_request(env))
    active = env.controller
    candidate = _candidate(
        base,
        config=replace(active.config, ik_position_gain=active.config.ik_position_gain * 0.5),
    )
    joint = next(
        item for item in env.typed_state.view.joints
        if item.entity_id == 'panda-main' and item.joint_id == 'joint1'
    )
    original_representation = joint.position_representation
    active_memory = _memory(active)
    candidate_memory = _memory(candidate)
    recorder_counts = (env.recorder.transition_count, env.recorder.observation_count)
    try:
        object.__setattr__(joint, 'position_representation', 'meter')
        with pytest.raises(ValueError, match='typed joint state does not match its A02 JointDefinition'):
            env.switch_position_controller(candidate)
    finally:
        object.__setattr__(joint, 'position_representation', original_representation)
    assert env.controller is active
    assert _memory(active) == active_memory
    assert _memory(candidate) == candidate_memory
    assert (env.recorder.transition_count, env.recorder.observation_count) == recorder_counts
    assert env.execution_fault is None
    env.close()


def test_postcommit_event_failure_faults_and_keeps_an_outcome_receipt(tmp_path):
    base = _build_active_recording(tmp_path, horizon=3)
    env = base.env
    old = env.controller
    switched = _candidate(
        base,
        config=replace(old.config, ik_position_gain=old.config.ik_position_gain * 0.5),
    )
    counts = (env.recorder.transition_count, env.recorder.observation_count)

    def fail_event(_event):
        raise OSError('injected effective event write failure')

    env.recorder.add_boundary_event = fail_event
    with pytest.raises(OSError, match='injected effective event write failure'):
        env.switch_position_controller(switched)
    assert env.controller is switched
    assert env.session._position_profiles_by_writer[switched.writer_id] is switched
    assert env.execution_fault is not None and env._stopped
    assert (env.recorder.transition_count, env.recorder.observation_count) == counts
    assert env.state.control_step == 0
    assert switched._next_control_step == 0
    assert env._position_controller_switch_fault_receipt['switch_effective'] is True
    assert env._position_controller_switch_fault_receipt['effective_event_recorded'] is False
    assert env._position_controller_switch_fault_receipt['first_control_application'] == 'not_attempted'
    assert env._pending_position_switch is None
    assert env._position_controller_switch_fault_receipt['execution_fault']['physical_progress'] == 'not_advanced'

    env.stop('switch-record-fault')
    finish = env.finish_recording('switch-record-fault')
    loaded = load_structured_control_records_h5(finish['path'])
    assert loaded['transition_count'] == 0 and loaded['observation_count'] == 1
    assert not any(event.event_type == 'controller_instance_switch'
                   for event in loaded['boundary_events'])
    end_event = next(event for event in loaded['boundary_events']
                     if event.event_type == 'episode_ended')
    assert end_event.payload['controller_switch_fault_receipt']['switch_effective'] is True
    assert end_event.payload['controller_switch_fault_receipt']['effective_event_recorded'] is False
    assert end_event.payload['controller_switch_fault_receipt']['request']['action_config']['ik_position_gain'] == switched.config.ik_position_gain
    with pytest.raises(RuntimeError, match='faulted'):
        env.step(_request(env))
    env.close()


def test_stop_before_first_new_controller_step_records_that_it_was_never_applied(tmp_path):
    base = _build_active_recording(tmp_path, horizon=3)
    env = base.env
    old = env.controller
    switched = _candidate(
        base,
        config=replace(old.config, ik_position_gain=old.config.ik_position_gain * 0.5),
    )
    switch_event = env.switch_position_controller(switched)
    env.stop('switch-not-applied')
    finish = env.finish_recording('switch-not-applied')
    loaded = load_structured_control_records_h5(finish['path'])
    assert loaded['transition_count'] == 0 and loaded['observation_count'] == 1
    events_by_type = {event.event_type: event for event in loaded['boundary_events']}
    assert events_by_type['controller_instance_switch'].payload['switch_id'] == switch_event.payload['switch_id']
    pending = events_by_type['episode_ended'].payload['pending_controller_switch_application']
    assert pending['switch_id'] == switch_event.payload['switch_id']
    assert pending['status'] == 'not_attempted_before_episode_end'
    env.close()


def test_post_switch_target_ack_without_recorded_transition_is_not_promoted(tmp_path):
    base = _build_active_recording(tmp_path, horizon=3)
    env = base.env
    old = env.controller
    switched = _candidate(
        base,
        config=replace(old.config, ik_position_gain=old.config.ik_position_gain * 0.5),
    )
    switch_event = env.switch_position_controller(switched)

    def fail_append(*_args, **_kwargs):
        raise OSError('injected transition append failure after target acknowledgement')

    env.recorder.append_transition = fail_append
    with pytest.raises(OSError, match='injected transition append failure'):
        env.step(_request(env, dx=0.025))
    assert env.execution_fault is not None and env._stopped
    assert env.state.control_step == 1
    assert env._published_position_state.control_step == 0
    assert env.execution_fault.physical_progress == 'advanced'
    assert env.execution_fault.transition_status == 'rejected'
    assert (env.recorder.transition_count, env.recorder.observation_count) == (0, 1)

    env.stop('post-switch-record-fault')
    finish = env.finish_recording('post-switch-record-fault')
    loaded = load_structured_control_records_h5(finish['path'])
    assert loaded['transition_count'] == 0 and loaded['observation_count'] == 1
    end_event = next(event for event in loaded['boundary_events'] if event.event_type == 'episode_ended')
    pending = end_event.payload['pending_controller_switch_application']
    assert pending['switch_id'] == switch_event.payload['switch_id']
    assert pending['status'] == 'target_ack_observed_but_transition_not_recorded'
    assert pending['target_identity_hash'] == pending['applied_target_hash']
    assert pending['observed_runtime_boundary'] == 1
    env.close()
