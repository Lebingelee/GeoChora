"""Real, one-process-per-provider S2 probe for the C02b Position candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import h5py
import numpy as np

from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1,
    StructuredActionRequestV1,
)
from task_env.controllers.canonical.kinematics import PANDA_HAND_ORIGIN_TCP_V1
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.c02b_position_candidate import (
    POSITION_CANDIDATE_SEED,
    build_position_candidate,
)
from task_env.recorders import (
    load_structured_control_records_h5,
    load_structured_training_actions_h5,
)
from task_env.utils.rotation import matrix_to_quat_wxyz, matrix_to_rotvec


FK_POSITION_ATOL_M = 1.0e-6
FK_QUATERNION_SIGN_INVARIANT_L2_ATOL = 1.0e-6
JACOBIAN_FINITE_DIFFERENCE_ATOL = 5.0e-5
NATIVE_CLOCK_ATOL_S = 1.0e-9
FD_EPSILON_RAD = 1.0e-6
_JOINTS = tuple(f'joint{i}' for i in range(1, 8))
_ALL_JOINTS = (*_JOINTS, 'finger_joint1', 'finger_joint2')


def _raise_force_access(*_args, **_kwargs):
    raise AssertionError('force-free Position profile called control_feedback()')


def _request(plan, hand_pose, gripper):
    schema = plan.controller_bindings[0].action_schema
    arm = (*hand_pose.position, *hand_pose.quaternion_wxyz)
    return StructuredActionRequestV1(
        'structured-action-request-v1', plan.scene_identity_hash, plan.identity_hash,
        (
            ControlGroupActionV1(
                'control-group-action-v1', 'panda-main', 'arm', schema.schema_id,
                tuple(float(value) for value in arm),
            ),
            ControlGroupActionV1(
                'control-group-action-v1', 'panda-main', 'gripper', schema.schema_id,
                (float(gripper),),
            ),
        ),
    )


def _typed_hand_and_joints(env):
    view = env.typed_state.view
    joints = {item.joint_id: item for item in view.joints if item.entity_id == 'panda-main'}
    hand = [item for item in view.frames
            if item.frame.entity_id == 'panda-main' and item.frame.frame_id == 'hand']
    if set(joints) != set(_ALL_JOINTS) or len(hand) != 1:
        raise AssertionError('reset publication lacks exact Panda hand/joint identities')
    if view.boundary.reset_sample_id != env.value['reset_plan'].reset_sample.sample_id:
        raise AssertionError('typed state boundary does not bind the fixed ResetSample')
    if view.sample_clock.clock_domain != 'evaluation_boundary' or (
        view.sample_clock.sample_index != view.boundary.control_step
    ):
        raise AssertionError('typed state publication has the wrong sample phase')
    return joints, hand[0].pose_world


def _fk_and_jacobian_evidence(env):
    joints, measured_hand = _typed_hand_and_joints(env)
    q = np.asarray([joints[name].position[0] for name in _JOINTS], dtype=np.float64)
    transform, jacobian = env.controller.model.fk_jacobian(q)
    fk_quaternion = matrix_to_quat_wxyz(transform[:3, :3])
    measured_quaternion = np.asarray(measured_hand.quaternion_wxyz, dtype=np.float64)
    quat_error = min(
        float(np.linalg.norm(fk_quaternion - measured_quaternion)),
        float(np.linalg.norm(fk_quaternion + measured_quaternion)),
    )
    position_error = float(np.linalg.norm(
        transform[:3, 3] - np.asarray(measured_hand.position, dtype=np.float64),
    ))
    finite_difference = np.empty_like(jacobian)
    for index in range(7):
        delta = np.zeros(7, dtype=np.float64)
        delta[index] = FD_EPSILON_RAD
        plus, _ = env.controller.model.fk_jacobian(q + delta)
        minus, _ = env.controller.model.fk_jacobian(q - delta)
        finite_difference[:3, index] = (plus[:3, 3] - minus[:3, 3]) / (2 * FD_EPSILON_RAD)
        finite_difference[3:, index] = matrix_to_rotvec(
            plus[:3, :3] @ minus[:3, :3].T,
        ) / (2 * FD_EPSILON_RAD)
    jacobian_error = float(np.max(np.abs(jacobian - finite_difference)))
    if position_error > FK_POSITION_ATOL_M:
        raise AssertionError(f'hand-origin FK position error {position_error:g} m')
    if quat_error > FK_QUATERNION_SIGN_INVARIANT_L2_ATOL:
        raise AssertionError(f'hand-origin FK quaternion error {quat_error:g}')
    if jacobian_error > JACOBIAN_FINITE_DIFFERENCE_ATOL:
        raise AssertionError(f'hand-origin TCP Jacobian finite-difference error {jacobian_error:g}')
    if env.controller.tcp_profile != PANDA_HAND_ORIGIN_TCP_V1:
        raise AssertionError('Controller and FK do not share the versioned hand-origin TCP')
    return {
        'fk_position_error_m': position_error,
        'fk_quaternion_sign_invariant_l2_error': quat_error,
        'jacobian_max_abs_finite_difference_error': jacobian_error,
        'tolerances': {
            'fk_position_atol_m': FK_POSITION_ATOL_M,
            'fk_quaternion_sign_invariant_l2_atol': FK_QUATERNION_SIGN_INVARIANT_L2_ATOL,
            'jacobian_finite_difference_atol': JACOBIAN_FINITE_DIFFERENCE_ATOL,
            'finite_difference_epsilon_rad': FD_EPSILON_RAD,
        },
        'tcp_profile': env.controller.tcp_profile.to_mapping(),
    }


def _observation_arrays(observation):
    return {
        'joint_position': np.asarray(observation['state']['joint_position']).copy(),
        'hand_pose': np.asarray(observation['state']['hand_pose']).copy(),
        'boundary_identity_sha256': np.asarray(
            observation['state']['boundary_identity_sha256'], dtype=np.uint8,
        ).copy(),
    }


def _boundary_identity_hash(env):
    boundary_id = env.typed_state.view.boundary.boundary_id
    return bytes.fromhex(boundary_id.removeprefix('state-boundary-'))


def _new_env(root, provider, *, horizon, public_factory=False):
    if not public_factory:
        return build_position_candidate(root, provider=provider, horizon=horizon)
    from types import SimpleNamespace
    from task_env import make_env

    env = make_env('panda-position-servo-candidate-v1', config={
        'provider': provider, 'backend': 'cpu', 'horizon': horizon,
        'source_workspace': str(root),
    })
    return SimpleNamespace(
        env=env, scene=env.value['source'].scene_definition,
        task_source=env.value['task_source'], artifact=env.artifact,
        reset_plan=env.value['reset_plan'], source=env.value['source'],
        controller_binding_plan=env.value['controller_binding_plan'],
        panda_closure_digest=env.value['panda_closure_digest'],
        panda_file_count=env.value['panda_file_count'], provider=provider,
    )


def _guard_no_dispatch(env, request, counters, label):
    before = dict(counters)
    recorder_before = None if env.recorder is None else (
        env.recorder.transition_count, env.recorder.observation_count,
    )
    try:
        env.step(request)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f'{label} guard accepted a Position action')
    if counters != before:
        raise AssertionError(f'{label} refusal computed/applied/stepped: {before} -> {counters}')
    recorder_after = None if env.recorder is None else (
        env.recorder.transition_count, env.recorder.observation_count,
    )
    if recorder_after != recorder_before:
        raise AssertionError(f'{label} refusal appended a transition')


def _fault_trial(candidate, provider, root, kind, counters):
    env = candidate.env
    if env.state.control_step != 0 or env.execution_fault is not None:
        env.reset()
    pose = _typed_hand_and_joints(env)[1]
    request = _request(candidate.controller_binding_plan, pose, 1.0)
    if kind == 'record':
        env.start_recording(root / f'{provider}-fault-record.h5')
    session_type = type(env.session)
    if kind == 'apply':
        original = session_type.apply_control

        def fail_apply(session, target):
            if session is env.session:
                raise RuntimeError('injected apply acknowledgement failure')
            return original(session, target)

        injection = patch.object(session_type, 'apply_control', fail_apply)
    elif kind == 'step':
        original = session_type.step

        def fail_after_native_step(session):
            result = original(session)
            if session is env.session:
                raise RuntimeError('injected post-step readback failure')
            return result

        injection = patch.object(session_type, 'step', fail_after_native_step)
    elif kind == 'record':
        from task_env.recorders import TransitionRecorder
        original = TransitionRecorder.append_transition

        def fail_record(recorder, *args, **kwargs):
            if recorder is env.recorder:
                raise RuntimeError('injected transition append failure')
            return original(recorder, *args, **kwargs)

        injection = patch.object(TransitionRecorder, 'append_transition', fail_record)
    else:
        raise AssertionError(kind)

    with injection:
        try:
            env.step(request)
        except RuntimeError as error:
            if not str(error).startswith('injected '):
                raise
        else:
            raise AssertionError(f'{kind} fault injection did not fail')
    fault = env.execution_fault
    if fault is None or not env._stopped:
        raise AssertionError(f'{kind} failure did not latch the existing C03a execution fault')
    before_guard = dict(counters)
    try:
        env.step(request)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f'{kind} fault latch admitted another action')
    if counters != before_guard:
        raise AssertionError(f'{kind} fault guard issued another dispatch')
    recorder = None if env.recorder is None else {
        'transitions': env.recorder.transition_count,
        'observations': env.recorder.observation_count,
    }
    if kind == 'record' and recorder != {'transitions': 0, 'observations': 1}:
        raise AssertionError(f'record failure left a partial transition: {recorder}')
    result = {
        'fault_kind': kind,
        'phase': fault.phase,
        'physical_progress': fault.physical_progress,
        'control_step_before': fault.control_step_before,
        'control_step_after': fault.control_step_after,
        'interval_attempted': fault.interval_attempted,
        'interval_completed': fault.interval_completed,
        'transition_status': fault.transition_status,
        'recorder_counts_after_failure': recorder,
    }
    if kind == 'apply' and result['physical_progress'] != 'not_advanced':
        raise AssertionError(f'apply failure advanced physics: {result}')
    if kind in {'step', 'record'} and not result['interval_completed']:
        raise AssertionError(f'{kind} failure lost completed-step evidence: {result}')
    if kind == 'record' and result['transition_status'] != 'rejected':
        raise AssertionError(f'record failure did not report rejected transition: {result}')
    return result


def run_probe(provider: str, output: Path, *, public_factory=False) -> dict:
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('probe output must be fresh; prior Evidence is preserved')
    output.mkdir(parents=True, exist_ok=True)
    horizon = 64
    candidate = _new_env(output / 'candidate-source', provider, horizon=horizon, public_factory=public_factory)
    env = candidate.env
    counters = {'compute': 0, 'apply': 0, 'step': 0}
    profile_compute = PandaPositionServoProfileV1.compute
    session_type = None

    def counted_compute(profile, *args, **kwargs):
        counters['compute'] += 1
        return profile_compute(profile, *args, **kwargs)

    try:
        initial_request = _request(
            candidate.controller_binding_plan,
            # The initial hand pose is available in the fixed ResetSample only
            # after reset, so use any valid request solely for refusal checks.
            type('Pose', (), {
                'position': (0.0, 0.0, 0.0),
                'quaternion_wxyz': (1.0, 0.0, 0.0, 0.0),
            })(),
            1.0,
        )
        try:
            env.step(initial_request)
        except RuntimeError as error:
            if 'reset required' not in str(error):
                raise
        else:
            raise AssertionError('Position candidate accepted step before reset')
        if env.session is not None or env.recorder is not None:
            raise AssertionError('reset-before-step guard materialized or recorded state')
        try:
            env.reset(seed=POSITION_CANDIDATE_SEED + 1)
        except ValueError as error:
            if 'fixed ResetPlan' not in str(error):
                raise
        else:
            raise AssertionError('Position candidate silently accepted a mismatched seed')
        if env.session is not None:
            raise AssertionError('mismatched seed materialized a Provider')

        reset_observation, reset_info = env.reset(seed=POSITION_CANDIDATE_SEED)
        reset_realization_evidence = env.session.reset_plan_evidence
        reset_session = env.session
        reset_boundary = env.typed_state.view.boundary.boundary_id
        try:
            env.reset(seed=POSITION_CANDIDATE_SEED + 1)
        except ValueError as error:
            if 'fixed ResetPlan' not in str(error):
                raise
        else:
            raise AssertionError('live candidate accepted a mismatched ResetPlan seed')
        if env.session is not reset_session or env.typed_state.view.boundary.boundary_id != reset_boundary:
            raise AssertionError('mismatched seed closed or changed a live ResetPlan session')
        session_type = type(env.session)
        session_apply = session_type.apply_control
        session_step = session_type.step

        def counted_apply(session, *args, **kwargs):
            counters['apply'] += 1
            return session_apply(session, *args, **kwargs)

        def counted_step(session, *args, **kwargs):
            counters['step'] += 1
            return session_step(session, *args, **kwargs)

        fk_evidence = _fk_and_jacobian_evidence(env)
        boundary_ids = [env.typed_state.view.boundary.boundary_id]
        observation_rows = [_observation_arrays(reset_observation)]
        initial_joint = observation_rows[0]['joint_position'].copy()
        initial_hand = observation_rows[0]['hand_pose'].copy()
        initial_opening = float(initial_joint[-2] + initial_joint[-1])
        sample_id = env.typed_state.view.boundary.reset_sample_id
        sample_identity = candidate.reset_plan.identity_hash
        scene_identity = candidate.scene.identity_hash
        profile_identity = env.controller.identity
        writer_id = env.controller.writer_id
        source_closure = candidate.source.source_closure_digest
        plan_identity = candidate.controller_binding_plan.identity_hash
        control_dt = candidate.artifact.timebase.control_dt
        physics_dt = candidate.artifact.timebase.physics_dt
        native_steps_requested = candidate.artifact.timebase.control_substeps
        if (control_dt, physics_dt, native_steps_requested) != (0.01, 0.002, 5):
            raise AssertionError('candidate timebase differs from 100 Hz / five 2 ms steps')

        # Three repeated public reads must return the same evaluation-boundary
        # identity and clocks without a physics advance or Controller compute.
        before_reads = (env.state.control_step, env.state.simulation_time)
        publication_reads = []
        for _ in range(3):
            view = env.session.snapshot_v1(
                scene=env.position_scene,
                joint_bindings=env.position_joint_bindings,
                frame_bindings=env.position_frame_bindings,
                requirements=env.controller.requirements,
            )
            publication_reads.append(view.view.boundary.boundary_id)
        if len(set(publication_reads + [boundary_ids[0]])) != 1:
            raise AssertionError('read-only typed state sampling changed boundary identity')
        if before_reads != (env.state.control_step, env.state.simulation_time):
            raise AssertionError('read-only typed state sampling advanced the Provider')

        open_pose = _typed_hand_and_joints(env)[1]
        moved_pose = type(open_pose)(
            (open_pose.position[0] + 0.02, *open_pose.position[1:]),
            open_pose.quaternion_wxyz,
        )
        actions = []
        actions.extend((_request(candidate.controller_binding_plan, open_pose, 1.0),) * 20)
        actions.extend((_request(candidate.controller_binding_plan, moved_pose, 1.0),) * 12)
        actions.extend((_request(candidate.controller_binding_plan, moved_pose, -1.0),) * 20)
        actions.extend((_request(candidate.controller_binding_plan, moved_pose, 1.0),) * 12)
        if len(actions) != horizon:
            raise AssertionError('S2 candidate action sequence/horizon count mismatch')
        record_path = output / f'{provider}-position-s2.h5'
        env.start_recording(record_path)
        clock_rows = []
        with (
            patch.object(PandaPositionServoProfileV1, 'compute', counted_compute),
            patch.object(session_type, 'apply_control', counted_apply),
            patch.object(session_type, 'step', counted_step),
            patch.object(session_type, 'control_feedback', _raise_force_access),
        ):
            for index, action in enumerate(actions):
                before_step = env.state
                result = env.step(action)
                after_step = env.state
                terminated, truncated = bool(result[2]), bool(result[3])
                if after_step.control_step != before_step.control_step + 1:
                    raise AssertionError('completed outer control clock did not advance by one')
                elapsed = float(after_step.simulation_time - before_step.simulation_time)
                inferred_steps = int(round(elapsed / physics_dt))
                if inferred_steps != native_steps_requested or abs(elapsed - control_dt) > NATIVE_CLOCK_ATOL_S:
                    raise AssertionError(
                        f'native clock delta does not imply five completed steps: {elapsed}s'
                    )
                clock_rows.append({
                    'transition': index,
                    'requested_native_steps': native_steps_requested,
                    'control_step_before': before_step.control_step,
                    'control_step_after': after_step.control_step,
                    'native_time_before_s': before_step.simulation_time,
                    'native_time_after_s': after_step.simulation_time,
                    'native_time_delta_s': elapsed,
                    'native_step_count_inferred_from_clock': inferred_steps,
                    'completion_evidence': 'RuntimeSession.step returned; public control clock +1 and native simulation clock +0.010s',
                })
                boundary_ids.append(env.typed_state.view.boundary.boundary_id)
                observation_rows.append(_observation_arrays(result[0]))
                if terminated or truncated:
                    if index != len(actions) - 1 or terminated or not truncated:
                        raise AssertionError('candidate stopped before/other than the fixed horizon boundary')
        if counters != {'compute': horizon, 'apply': horizon, 'step': horizon}:
            raise AssertionError(f'not exactly one compute/apply/step per outer action: {counters}')

        # Rejected terminal action must not compute, apply, step, or record.
        final_request = actions[-1]
        _guard_no_dispatch(env, final_request, counters, 'terminal/horizon')
        if env.recorder.transition_count != horizon or env.recorder.observation_count != horizon + 1:
            raise AssertionError('live recorder did not retain T/T+1 after terminal guard')
        finish = env.finish_recording('horizon')
        h5_path = Path(finish['path'])
        structured = load_structured_control_records_h5(h5_path)
        training_actions = load_structured_training_actions_h5(h5_path)
        if structured['transition_count'] != horizon or structured['observation_count'] != horizon + 1:
            raise AssertionError('Generic H5 v3 reader lost T/T+1 alignment')
        if len(training_actions) != horizon:
            raise AssertionError('Generic H5 v3 action projection count mismatch')
        writer_rows = []
        for index, control in enumerate(structured['structured_controls']):
            if len(control.writer_controls) != 1:
                raise AssertionError('structured H5 transition has more than one writer')
            writer = control.writer_controls[0]
            if writer['writer_id'] != writer_id:
                raise AssertionError('recorded writer identity differs from actual Profile')
            if {(group['entity_id'], group['group_id']) for group in writer['groups']} != {
                ('panda-main', 'arm'), ('panda-main', 'gripper'),
            }:
                raise AssertionError('structured action omitted one of the two complete groups')
            if writer['controller_target']['identity_hash'] != writer['applied_control']['target_hash']:
                raise AssertionError('applied acknowledgement does not match the target')
            if control.request != actions[index]:
                raise AssertionError('disk structured-control request differs from the issued action')
            writer_rows.append({
                'writer_id': writer['writer_id'],
                'action_schema_id': writer['action_schema_id'],
                'groups': [list(item) for item in sorted(
                    (group['entity_id'], group['group_id']) for group in writer['groups']
                )],
                'target_hash': writer['controller_target']['identity_hash'],
                'ack_hash': writer['applied_control']['target_hash'],
            })

        with h5py.File(h5_path, 'r') as handle:
            disk_joints = np.asarray(handle['obs/state/joint_position'])
            disk_hand = np.asarray(handle['obs/state/hand_pose'])
            disk_boundary = np.asarray(handle['obs/state/boundary_identity_sha256'])
            if not np.array_equal(disk_joints, np.stack([row['joint_position'] for row in observation_rows])):
                raise AssertionError('disk joint observation leaves differ from live state boundaries')
            if not np.array_equal(disk_hand, np.stack([row['hand_pose'] for row in observation_rows])):
                raise AssertionError('disk hand-frame observation leaves differ from live state boundaries')
            if not np.array_equal(
                disk_boundary,
                np.stack([row['boundary_identity_sha256'] for row in observation_rows]),
            ):
                raise AssertionError('disk state-boundary identity leaves differ from live boundaries')
            if str(handle.attrs['schema_version']) != 'v3':
                raise AssertionError('saved trajectory is not Generic H5 v3')
        if not np.array_equal(
            np.asarray(training_actions, dtype=np.float32),
            np.stack([np.asarray([value for group in action.groups for value in group.values], dtype=np.float32)
                      for action in actions]),
        ):
            raise AssertionError('training action projection differs from exact structured requests')

        final_joint = disk_joints[-1]
        final_opening = float(final_joint[-2] + final_joint[-1])
        arm_joint_delta = float(np.max(np.abs(final_joint[:7] - initial_joint[:7])))
        open_peak = float(np.max(disk_joints[1:33, -2] + disk_joints[1:33, -1]))
        close_end = float(disk_joints[52, -2] + disk_joints[52, -1])
        if arm_joint_delta < 1.0e-4:
            raise AssertionError(f'arm Joint state did not show real motion: {arm_joint_delta}')
        if open_peak - initial_opening < 1.0e-3:
            raise AssertionError('gripper opening action produced no measured finger motion')
        if open_peak - close_end < 1.0e-3:
            raise AssertionError('closing action produced no measured gripper motion')
        if final_opening - close_end < 1.0e-3:
            raise AssertionError('reopening action produced no measured gripper motion')

        if counters != {'compute': horizon, 'apply': horizon, 'step': horizon}:
            raise AssertionError('readback/finish changed physics or Controller counts')
        recorder_counts = (env.recorder.transition_count, env.recorder.observation_count)
        env.reset()  # omitted seed uses the ResetPlan's bound seed
        if env.typed_state.view.boundary.reset_sample_id != sample_id:
            raise AssertionError('repeat reset changed the fixed ResetSample identity')
        if env.typed_state.view.boundary.episode_id == structured['outcome'].episode_id:
            raise AssertionError('repeat reset reused the prior episode identity')
        if env.state.control_step != 0 or env.state.simulation_time != 0.0:
            raise AssertionError('repeat reset advanced the Provider')
        if env.recorder is not None:
            raise AssertionError('repeat reset retained the prior episode recorder')
        repeated_reset = {
            'same_reset_sample_id': sample_id,
            'new_episode_id': env.typed_state.view.boundary.episode_id,
            'control_step': env.state.control_step,
            'simulation_time_s': env.state.simulation_time,
        }
        env.close()
        _guard_no_dispatch(env, final_request, counters, 'close')

        fault_results = []
        for kind in ('apply', 'step', 'record'):
            fault_candidate = _new_env(
                output / f'fault-{kind}-source', provider, horizon=2, public_factory=public_factory,
            )
            try:
                fault_candidate.env.reset()
                fault_results.append(_fault_trial(
                    fault_candidate, provider, output, kind, counters,
                ))
            finally:
                fault_candidate.env.close()

        return {
            'schema_version': 'geochora.c02b-position-s2-receipt-v1',
            'status': 'PASS_BOUNDED_POSITION_PROFILE_S2',
            'construction_route': 'task_env.make_env' if public_factory else 'diagnostic builder',
            'environment_uid': env.uid,
            'provider': provider,
            'backend': 'cpu',
            'task_artifact_identity_hash': candidate.artifact.identity_hash,
            'scene_identity_hash': scene_identity,
            'task_source_identity_hash': candidate.task_source.identity_hash,
            'reset_plan_identity_hash': sample_identity,
            'reset_sample_id': sample_id,
            'source_closure_digest': source_closure,
            'panda_asset_closure_digest': candidate.panda_closure_digest,
            'panda_asset_file_count': candidate.panda_file_count,
            'profile_id': env.controller.profile_id,
            'controller_identity': profile_identity,
            'writer_id': writer_id,
            'control_binding_plan_identity_hash': plan_identity,
            'timebase': {
                'control_frequency_hz': 100,
                'control_dt_s': control_dt,
                'physics_dt_s': physics_dt,
                'native_steps_requested_per_control': native_steps_requested,
                'number_of_controls': horizon,
            },
            'reset_realization_evidence': reset_realization_evidence,
            'fk_jacobian': fk_evidence,
            'read_only_sampling': {
                'reads': len(publication_reads),
                'same_boundary_identity': True,
                'same_public_control_and_native_clocks': True,
            },
            'control_clock_evidence': clock_rows,
            'completion_evidence_limit': (
                'Provider.step returned and public clocks advanced by one control boundary and 0.010 s; '
                'the five native steps are inferred from the native clock, not an exposed Core counter.'
            ),
            'measured_motion': {
                'arm_max_joint_delta_rad': arm_joint_delta,
                'gripper_opening_initial_m': initial_opening,
                'gripper_opening_peak_m': open_peak,
                'gripper_opening_after_close_m': close_end,
                'gripper_opening_final_m': final_opening,
            },
            'recording': {
                'path': str(h5_path), 'schema_id': 'task-env-h5', 'schema_version': 'v3',
                'transition_count': structured['transition_count'],
                'observation_count': structured['observation_count'],
                'structured_control_count': len(structured['structured_controls']),
                'training_action_projection_count': len(training_actions),
                'writer_controls': writer_rows,
                'disk_joint_leaf_shape': list(disk_joints.shape),
                'disk_hand_leaf_shape': list(disk_hand.shape),
                'disk_boundary_identity_leaf_shape': list(disk_boundary.shape),
                'disk_numeric_and_boundary_identity_readback': 'PASS',
                'outcome': structured['outcome'].to_mapping(),
                'finish_api_result': finish,
            },
            'guard_evidence': {
                'reset_before_step': 'rejected_without_dispatch',
                'mismatched_reset_seed': 'rejected_before_provider_materialization',
                'mismatched_seed_with_live_session': 'rejected_without_closing_or_changing_session',
                'terminal_horizon': 'rejected_without_compute_apply_step_or_transition',
                'repeat_reset': repeated_reset,
                'close': 'rejected_without_dispatch',
                'pre_close_recorder_counts': list(recorder_counts),
            },
            'fault_injection': fault_results,
            'force_free': {
                'control_feedback_called': False,
                'provider_session_control_feedback': 'instrumented to raise if called during rollout',
                'actuator_force_readback_or_copy': 'not requested by the candidate Required State',
            },
        }
    finally:
        if env.session is not None:
            env.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=('geophys', 'mujoco'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-factory', action='store_true')
    args = parser.parse_args(argv)
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('output must be fresh; prior Evidence is preserved')
    receipt_path = args.output / f'{args.provider}-receipt.json'
    try:
        receipt = run_probe(args.provider, args.output, public_factory=args.public_factory)
    except BaseException as error:
        receipt = {
            'schema_version': 'geochora.c02b-position-s2-receipt-v1',
            'status': 'FAIL', 'provider': args.provider,
            'exception_type': type(error).__name__, 'error': str(error),
            'traceback': traceback.format_exc(),
        }
        args.output.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(receipt, sort_keys=True, indent=2))
        return 1
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
