"""Real, one-process-per-provider C02b dual-Entity Position probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import h5py
import numpy as np

from task_env.artifacts import StateBoundaryIdentity
from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1,
    StructuredActionRequestV1,
)
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.c02b_dual_entity_candidate import (
    DUAL_ENTITY_SEED,
    MAIN_ENTITY,
    SECONDARY_ENTITY,
    build_dual_entity_position_candidate,
)
from task_env.recorders import load_structured_control_records_h5
from task_env.utils.rotation import matrix_to_quat_wxyz, matrix_to_rotvec


FK_POSITION_ATOL_M = 1.0e-6
FK_QUATERNION_SIGN_INVARIANT_L2_ATOL = 1.0e-6
JACOBIAN_FINITE_DIFFERENCE_ATOL = 5.0e-5
NATIVE_CLOCK_ATOL_S = 1.0e-9
FD_EPSILON_RAD = 1.0e-6
CONTROLS_PER_ENTITY = 15


def _raise_force_access(*_args, **_kwargs):
    raise AssertionError('force-free dual Position profile called control_feedback()')


def _joint_values(env, profile):
    by_id = {
        item.joint_id: item for item in env.typed_state.view.joints
        if item.entity_id == profile.entity_id
    }
    names = (*profile.joint_ids, *profile.finger_joint_ids)
    if set(by_id) != set(names):
        raise AssertionError(f'{profile.entity_id} typed Joint identities are incomplete')
    return np.asarray([by_id[name].position[0] for name in names], dtype=np.float64)


def _hand_pose(env, profile):
    values = [
        item for item in env.typed_state.view.frames
        if item.frame.entity_id == profile.entity_id
        and item.frame.frame_id == profile.hand_frame_id
    ]
    if len(values) != 1:
        raise AssertionError(f'{profile.entity_id}/{profile.hand_frame_id} Frame identity is ambiguous')
    return values[0].pose_world


def _request(env, desired_poses):
    groups = []
    for profile in env.position_profiles:
        schema = profile.controller_binding().action_schema
        pose = desired_poses.get(profile.entity_id, _hand_pose(env, profile))
        groups.extend((
            ControlGroupActionV1(
                'control-group-action-v1', profile.entity_id, 'arm', schema.schema_id,
                tuple(float(value) for value in (*pose.position, *pose.quaternion_wxyz)),
            ),
            ControlGroupActionV1(
                'control-group-action-v1', profile.entity_id, 'gripper', schema.schema_id, (1.0,),
            ),
        ))
    return StructuredActionRequestV1(
        'structured-action-request-v1', env.position_plan.scene_identity_hash,
        env.position_plan.identity_hash, tuple(groups),
    )


def _pose_with_x(pose, dx):
    return type(pose)(
        (float(pose.position[0] + dx), *pose.position[1:]), pose.quaternion_wxyz,
    )


def _fk_jacobian_evidence(env, profile):
    q = _joint_values(env, profile)[:7]
    transform, jacobian = profile.model.fk_jacobian(q)
    measured = _hand_pose(env, profile)
    quaternion = matrix_to_quat_wxyz(transform[:3, :3])
    measured_quaternion = np.asarray(measured.quaternion_wxyz, dtype=np.float64)
    quat_error = min(
        float(np.linalg.norm(quaternion - measured_quaternion)),
        float(np.linalg.norm(quaternion + measured_quaternion)),
    )
    position_error = float(np.linalg.norm(
        transform[:3, 3] - np.asarray(measured.position, dtype=np.float64),
    ))
    finite_difference = np.empty_like(jacobian)
    for index in range(7):
        delta = np.zeros(7, dtype=np.float64)
        delta[index] = FD_EPSILON_RAD
        plus, _ = profile.model.fk_jacobian(q + delta)
        minus, _ = profile.model.fk_jacobian(q - delta)
        finite_difference[:3, index] = (
            plus[:3, 3] - minus[:3, 3]
        ) / (2 * FD_EPSILON_RAD)
        finite_difference[3:, index] = matrix_to_rotvec(
            plus[:3, :3] @ minus[:3, :3].T,
        ) / (2 * FD_EPSILON_RAD)
    jacobian_error = float(np.max(np.abs(jacobian - finite_difference)))
    if position_error > FK_POSITION_ATOL_M:
        raise AssertionError(f'{profile.entity_id} hand-origin FK position error {position_error:g} m')
    if quat_error > FK_QUATERNION_SIGN_INVARIANT_L2_ATOL:
        raise AssertionError(f'{profile.entity_id} FK quaternion error {quat_error:g}')
    if jacobian_error > JACOBIAN_FINITE_DIFFERENCE_ATOL:
        raise AssertionError(f'{profile.entity_id} TCP Jacobian finite-difference error {jacobian_error:g}')
    return {
        'entity_id': profile.entity_id,
        'hand_frame_id': profile.hand_frame_id,
        'tcp_profile': profile.tcp_profile.to_mapping(),
        'fk_position_error_m': position_error,
        'fk_quaternion_sign_invariant_l2_error': quat_error,
        'jacobian_max_abs_finite_difference_error': jacobian_error,
    }


def _state_observation(observation):
    return {
        entity: {
            'joint_position': np.asarray(values['joint_position'], dtype=np.float32).copy(),
            'hand_pose': np.asarray(values['hand_pose'], dtype=np.float32).copy(),
        }
        for entity, values in observation['state']['entities'].items()
    }


def _boundary_bytes(boundary_id):
    return np.frombuffer(
        bytes.fromhex(boundary_id.removeprefix('state-boundary-')),
        dtype=np.uint8,
    ).copy()


def _guard_without_dispatch(env, action, counters, label):
    before = dict(counters)
    transition_count = None if env.recorder is None else env.recorder.transition_count
    observation_count = None if env.recorder is None else env.recorder.observation_count
    try:
        env.step(action)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f'{label} accepted a post-terminal/closed action')
    if counters != before:
        raise AssertionError(f'{label} rejection dispatched Controller/Provider work')
    if env.recorder is not None and (
        env.recorder.transition_count != transition_count
        or env.recorder.observation_count != observation_count
    ):
        raise AssertionError(f'{label} rejection appended a transition')


def _failure_boundary_trial(provider, output):
    candidate = build_dual_entity_position_candidate(
        output / f'{provider}-failure-source', provider=provider, horizon=2,
    )
    env = candidate.env
    try:
        env.reset()
        env.start_recording(output / f'{provider}-inflight-failure.h5')
        main, secondary = env.position_profiles
        action = _request(env, {})
        before_state = env.state
        counters = {'compute': 0, 'apply_attempt': 0, 'acknowledged_apply': 0, 'step': 0}
        original_compute = PandaPositionServoProfileV1.compute
        session_type = type(env.session)
        original_apply = session_type.apply_control
        original_step = session_type.step
        events = []

        def counted_compute(profile, *args, **kwargs):
            counters['compute'] += 1
            return original_compute(profile, *args, **kwargs)

        def fail_secondary_apply(session, target):
            if session is not env.session:
                return original_apply(session, target)
            counters['apply_attempt'] += 1
            events.append('main_acknowledged' if target.controller_identity == main.identity else 'secondary_apply_attempt')
            if target.controller_identity == secondary.identity:
                raise RuntimeError('injected second Entity native apply failure')
            result = original_apply(session, target)
            counters['acknowledged_apply'] += 1
            return result

        def counted_step(session):
            if session is env.session:
                counters['step'] += 1
            return original_step(session)

        with (
            patch.object(PandaPositionServoProfileV1, 'compute', counted_compute),
            patch.object(session_type, 'apply_control', fail_secondary_apply),
            patch.object(session_type, 'step', counted_step),
        ):
            try:
                env.step(action)
            except RuntimeError as error:
                if 'injected second Entity' not in str(error):
                    raise
            else:
                raise AssertionError('injected second writer apply failure was not propagated')
            fault = env.execution_fault
            if fault is None or fault.physical_progress != 'not_advanced':
                raise AssertionError('C03a did not latch a no-native-step partial apply failure')
            if (env.state.control_step, env.state.simulation_time) != (
                before_state.control_step, before_state.simulation_time,
            ):
                raise AssertionError('in-flight apply fault advanced the physical clock')
            counts_after_failure = (env.recorder.transition_count, env.recorder.observation_count)
            if counts_after_failure != (0, 1):
                raise AssertionError('in-flight apply fault appended a pseudo transition')
            before_guard = dict(counters)
            try:
                env.step(action)
            except RuntimeError:
                pass
            else:
                raise AssertionError('faulted dual environment admitted another action')
            if counters != before_guard:
                raise AssertionError('fault latch performed additional compute/apply/step work')
        finish = env.finish_recording('execution_fault')
        return {
            'fault_phase': fault.phase,
            'physical_progress': fault.physical_progress,
            'control_step_before': fault.control_step_before,
            'control_step_after': fault.control_step_after,
            'interval_attempted': fault.interval_attempted,
            'interval_completed': fault.interval_completed,
            'transition_status': fault.transition_status,
            'events': events,
            'counters': counters,
            'recorder_counts_after_fault': counts_after_failure,
            'fault_episode_h5': finish,
            'provider_control_rollback_claimed': False,
            'native_steps_requested': candidate.artifact.timebase.control_substeps,
            'native_steps_completed': 0,
        }
    finally:
        env.close()


def run_probe(provider: str, output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    horizon = 2 * CONTROLS_PER_ENTITY
    candidate = build_dual_entity_position_candidate(
        output / 'candidate-source', provider=provider, horizon=horizon,
    )
    env = candidate.env
    try:
        reset_observation, _reset_info = env.reset(seed=DUAL_ENTITY_SEED)
        reset_publication = env.typed_state
        view = reset_publication.view
        boundary = view.boundary
        if (boundary.scene_identity_hash != candidate.scene.identity_hash
                or boundary.reset_sample_id != candidate.reset_plan.reset_sample.sample_id
                or view.sample_clock.clock_domain != 'evaluation_boundary'
                or view.sample_clock.sample_index != 0):
            raise AssertionError('dual reset state identity/sample phase is invalid')
        if {profile.entity_id for profile in env.position_profiles} != {MAIN_ENTITY, SECONDARY_ENTITY}:
            raise AssertionError('candidate Controller set does not bind the two declared Entities')
        fk = [_fk_jacobian_evidence(env, profile) for profile in env.position_profiles]

        start_poses = {profile.entity_id: _hand_pose(env, profile) for profile in env.position_profiles}
        destinations = {
            MAIN_ENTITY: _pose_with_x(start_poses[MAIN_ENTITY], +0.025),
            SECONDARY_ENTITY: _pose_with_x(start_poses[SECONDARY_ENTITY], -0.025),
        }
        start_positions = {profile.entity_id: _joint_values(env, profile) for profile in env.position_profiles}
        observation_rows = [_state_observation(reset_observation)]
        boundary_ids = [boundary.boundary_id]
        clock_rows = []
        writer_ack_rows = []
        submitted_requests = []
        counters = {'compute': 0, 'apply': 0, 'step': 0}
        original_compute = PandaPositionServoProfileV1.compute
        session_type = type(env.session)
        original_apply = session_type.apply_control
        original_step = session_type.step

        def counted_compute(profile, *args, **kwargs):
            counters['compute'] += 1
            return original_compute(profile, *args, **kwargs)

        def counted_apply(session, target):
            if session is env.session:
                counters['apply'] += 1
            return original_apply(session, target)

        def counted_step(session):
            if session is env.session:
                counters['step'] += 1
            return original_step(session)

        record_path = output / f'{provider}-dual-entity.h5'
        env.start_recording(record_path)
        with (
            patch.object(PandaPositionServoProfileV1, 'compute', counted_compute),
            patch.object(session_type, 'apply_control', counted_apply),
            patch.object(session_type, 'step', counted_step),
            patch.object(session_type, 'control_feedback', _raise_force_access),
        ):
            for phase, active_entity in enumerate((MAIN_ENTITY, SECONDARY_ENTITY)):
                for step_index in range(CONTROLS_PER_ENTITY):
                    desired = {
                        active_entity: destinations[active_entity],
                    }
                    request = _request(env, desired)
                    submitted_requests.append(request)
                    before = env.state
                    result = env.step(request)
                    after = env.state
                    elapsed = float(after.simulation_time - before.simulation_time)
                    inferred_native_steps = int(round(elapsed / candidate.artifact.timebase.physics_dt))
                    if (after.control_step != before.control_step + 1
                            or inferred_native_steps != 5
                            or abs(elapsed - 0.01) > NATIVE_CLOCK_ATOL_S):
                        raise AssertionError('one structured interval did not complete 5×2 ms native time')
                    clock_rows.append({
                        'control_step_before': before.control_step,
                        'control_step_after': after.control_step,
                        'native_time_before_s': before.simulation_time,
                        'native_time_after_s': after.simulation_time,
                        'native_time_delta_s': elapsed,
                        'native_steps_requested': 5,
                        'native_steps_inferred_from_public_clock': inferred_native_steps,
                        'phase': 'main_entity' if phase == 0 else 'secondary_entity',
                        'commanded_entity': active_entity,
                    })
                    boundary_ids.append(env.typed_state.view.boundary.boundary_id)
                    observation_rows.append(_state_observation(result[0]))
                    for _canonical, bound_target, applied in env.last_position_transition:
                        writer_profile = next(
                            profile for profile in env.position_profiles
                            if profile.writer_id == bound_target.writer_id
                        )
                        if set(bound_target.target.arm_joint_order) != set(writer_profile._target_bindings):
                            raise AssertionError('target actuator keys escaped their Entity namespace')
                        if applied.target_hash != bound_target.target.identity_hash:
                            raise AssertionError('native acknowledgement refers to another Controller target')
                        writer_ack_rows.append({
                            'control_step': bound_target.source_boundary.control_step,
                            'writer_id': bound_target.writer_id,
                            'entity_id': writer_profile.entity_id,
                            'target_boundary_id': bound_target.source_boundary.boundary_id,
                            'target_arm_joints': bound_target.target.arm_joint_order,
                            'ack_target_hash': applied.target_hash,
                        })
        if counters != {'compute': horizon * 2, 'apply': horizon * 2, 'step': horizon}:
            raise AssertionError(f'dual dispatcher did not compute/apply both writers exactly once: {counters}')
        terminal_action = _request(env, {})
        transition_counts_before = (env.recorder.transition_count, env.recorder.observation_count)
        _guard_without_dispatch(env, terminal_action, counters, 'terminal/horizon')
        if transition_counts_before != (horizon, horizon + 1):
            raise AssertionError('recorder did not preserve T/T+1 before terminal refusal')
        finish = env.finish_recording('horizon')
        h5_path = Path(finish['path'])
        records = load_structured_control_records_h5(h5_path)
        if (records['transition_count'], records['observation_count']) != (horizon, horizon + 1):
            raise AssertionError('Generic H5 v3 disk reader lost T/T+1 boundaries')
        if len(records['structured_controls']) != horizon:
            raise AssertionError('Generic H5 v3 disk reader lost structured controls')
        if records['outcome'].episode_id != boundary.episode_id or records['outcome'].final_boundary != horizon:
            raise AssertionError('recorded EpisodeOutcome is not bound to the active dual episode')

        saved_writer_controls = []
        for index, control in enumerate(records['structured_controls']):
            if control.request != submitted_requests[index]:
                raise AssertionError('Generic H5 request readback differs from the submitted action')
            expected_groups = {
                (MAIN_ENTITY, 'arm'), (MAIN_ENTITY, 'gripper'),
                (SECONDARY_ENTITY, 'arm'), (SECONDARY_ENTITY, 'gripper'),
            }
            if {(group.entity_id, group.group_id) for group in control.request.groups} != expected_groups:
                raise AssertionError('recorded request omitted an Entity-qualified group')
            if {writer['writer_id'] for writer in control.writer_controls} != {
                profile.writer_id for profile in env.position_profiles
            }:
                raise AssertionError('recorded writer set differs from the admitted Controller set')
            for writer in control.writer_controls:
                target = writer['controller_target']
                applied = writer['applied_control']
                if target['identity_hash'] != applied['target_hash']:
                    raise AssertionError('recorded applied acknowledgement target hash mismatch')
                binding_target = writer['canonical_action']['position_target_v1']
                target_boundary_id = StateBoundaryIdentity.from_mapping(
                    binding_target['source_boundary'],
                ).boundary_id
                if (binding_target['writer_id'] != writer['writer_id']
                        or binding_target['source_boundary']['control_step'] != index
                        or binding_target['source_boundary']['episode_id'] != boundary.episode_id
                        or target_boundary_id != boundary_ids[index]):
                    raise AssertionError('recorded writer target boundary/episode identity mismatch')
                target_keys = set(writer['controller_target']['payload']['arm_joint_order'])
                profile = next(item for item in env.position_profiles if item.writer_id == writer['writer_id'])
                if target_keys != set(profile._target_bindings):
                    raise AssertionError('recorded Controller target contains another Entity resources')
                saved_writer_controls.append({
                    'transition_index': index,
                    'writer_id': writer['writer_id'],
                    'entity_id': profile.entity_id,
                    'target_hash': target['identity_hash'],
                    'ack_target_hash': applied['target_hash'],
                    'source_boundary_id': target_boundary_id,
                })

        with h5py.File(h5_path, 'r') as handle:
            disk_joints = {
                entity: np.asarray(handle[f'obs/state/entities/{entity}/joint_position'])
                for entity in (MAIN_ENTITY, SECONDARY_ENTITY)
            }
            disk_hands = {
                entity: np.asarray(handle[f'obs/state/entities/{entity}/hand_pose'])
                for entity in (MAIN_ENTITY, SECONDARY_ENTITY)
            }
            disk_boundary = np.asarray(handle['obs/state/boundary_identity_sha256'])
            if any(not np.array_equal(disk_joints[entity], np.stack([
                row[entity]['joint_position'] for row in observation_rows
            ])) for entity in (MAIN_ENTITY, SECONDARY_ENTITY)):
                raise AssertionError('disk Entity Joint leaves differ from returned state boundaries')
            if any(not np.array_equal(disk_hands[entity], np.stack([
                row[entity]['hand_pose'] for row in observation_rows
            ])) for entity in (MAIN_ENTITY, SECONDARY_ENTITY)):
                raise AssertionError('disk Entity hand pose leaves differ from returned state boundaries')
            expected_boundary_bytes = np.stack([_boundary_bytes(item) for item in boundary_ids])
            if not np.array_equal(disk_boundary, expected_boundary_bytes):
                raise AssertionError('disk reset/transition boundary identities differ from live publications')
            if str(handle.attrs.get('schema_version')) != 'v3':
                raise AssertionError('recording is not Generic TaskEnv H5 v3')

        phase_end_positions = {
            entity: disk_joints[entity][CONTROLS_PER_ENTITY].copy()
            for entity in (MAIN_ENTITY, SECONDARY_ENTITY)
        }
        final_positions = {
            entity: disk_joints[entity][-1].copy()
            for entity in (MAIN_ENTITY, SECONDARY_ENTITY)
        }
        phase_motion = {
            MAIN_ENTITY: float(np.linalg.norm(phase_end_positions[MAIN_ENTITY] - start_positions[MAIN_ENTITY])),
            SECONDARY_ENTITY: float(np.linalg.norm(final_positions[SECONDARY_ENTITY] - phase_end_positions[SECONDARY_ENTITY])),
        }
        if any(value < 1.0e-3 for value in phase_motion.values()):
            raise AssertionError(f'a commanded Entity did not show real arm Joint motion: {phase_motion}')
        # Confirm that the inactive Entity's drift is recorded as physics state,
        # while the writer target/ack rows above remain Entity-local.
        passive_physics_drift = {
            'secondary_during_main_command': float(np.linalg.norm(
                phase_end_positions[SECONDARY_ENTITY] - start_positions[SECONDARY_ENTITY],
            )),
            'main_during_secondary_command': float(np.linalg.norm(
                final_positions[MAIN_ENTITY] - phase_end_positions[MAIN_ENTITY],
            )),
        }

        old_episode_id = boundary.episode_id
        previous_profiles = env.position_profiles
        env.reset()  # Fixed ResetPlan seed defaults to the same value.
        reset_after = env.typed_state.view.boundary
        if reset_after.episode_id == old_episode_id or reset_after.reset_sample_id != candidate.reset_plan.reset_sample.sample_id:
            raise AssertionError('repeat reset did not isolate the Episode identity and fixed sample')
        if any(profile._next_control_step != 0 for profile in env.position_profiles):
            raise AssertionError('repeat reset did not reset both Controller memories')
        if len({id(profile) for profile in env.position_profiles}) != 2 or any(
            new is old for new, old in zip(env.position_profiles, previous_profiles, strict=True)
        ):
            raise AssertionError('repeat reset reused a prior Entity Controller instance')
        for profile in env.position_profiles:
            expected = candidate.reset_plan.reset_sample.joint_position
            actual = _joint_values(env, profile)
            names = (*profile.joint_ids, *profile.finger_joint_ids)
            wanted = np.asarray([expected[f'{profile.entity_id}/{name}'] for name in names])
            if not np.allclose(actual, wanted, atol=1.0e-6, rtol=0.0):
                raise AssertionError(f'reset did not restore {profile.entity_id} state')
        terminal_action = _request(env, {})
        env.close()
        _guard_without_dispatch(env, terminal_action, counters, 'closed environment')

        fault = _failure_boundary_trial(provider, output)
        try:
            import mujoco
            provider_engine_version = mujoco.__version__ if provider == 'mujoco' else None
        except ImportError:
            provider_engine_version = None

        return {
            'schema_version': 'geochora.c02b-dual-entity-position-s2-receipt-v1',
            'status': 'PASS_BOUNDED_DUAL_ENTITY_POSITION_S2',
            'provider': provider,
            'backend': 'cpu',
            'provider_engine_version': provider_engine_version,
            'task_artifact_identity_hash': candidate.artifact.identity_hash,
            'task_source_identity_hash': candidate.task_source.identity_hash,
            'scene_identity_hash': candidate.scene.identity_hash,
            'scene_id': candidate.scene.scene_id,
            'source_closure_digest': candidate.source_closure_digest,
            'panda_asset_closure_digest': candidate.panda_closure_digest,
            'panda_asset_file_count': candidate.panda_file_count,
            'reset_plan_identity_hash': candidate.reset_plan.identity_hash,
            'reset_sample_id': candidate.reset_plan.reset_sample.sample_id,
            'control_binding_plan_identity_hash': candidate.controller_binding_plan.identity_hash,
            'controllers': [{
                'entity_id': profile.entity_id,
                'profile_id': profile.profile_id,
                'writer_id': profile.writer_id,
                'controller_identity': profile.identity,
                'required_state_field_count': len(profile.requirements.requirements),
                'force_feedback': 'not_consumed',
            } for profile in candidate.profiles],
            'source_layout': {
                'root_entities': [MAIN_ENTITY, SECONDARY_ENTITY],
                'root_relationship': 'independent articulated roots in one Scene/RuntimeSession; no attachment or Assembly',
                'secondary_native_prefix': 'secondary_',
                'secondary_root_world_offset_m': [-1.6, 0.0, 0.0],
                'resource_count': len(candidate.controller_binding_plan.resource_writers),
                'source_closure_changed_from_frozen_a05': True,
            },
            'timebase': {
                'outer_hz': 100,
                'control_dt_s': 0.01,
                'physics_dt_s': 0.002,
                'native_steps_per_control_requested': 5,
                'controls_per_entity_command_phase': CONTROLS_PER_ENTITY,
                'completed_control_intervals': horizon,
            },
            'reset_state_identity': {
                'episode_id': old_episode_id,
                'boundary_id': boundary.boundary_id,
                'reset_sample_id': boundary.reset_sample_id,
                'joint_and_hand_state_entities': [MAIN_ENTITY, SECONDARY_ENTITY],
            },
            'fk_jacobian': {
                'entities': fk,
                'tolerances': {
                    'fk_position_atol_m': FK_POSITION_ATOL_M,
                    'fk_quaternion_sign_invariant_l2_atol': FK_QUATERNION_SIGN_INVARIANT_L2_ATOL,
                    'jacobian_finite_difference_atol': JACOBIAN_FINITE_DIFFERENCE_ATOL,
                    'finite_difference_epsilon_rad': FD_EPSILON_RAD,
                },
            },
            'writer_isolation': {
                'per_interval_compute_count': counters['compute'],
                'per_interval_apply_ack_count': counters['apply'],
                'physical_step_count': counters['step'],
                'entity_local_target_ack_rows': writer_ack_rows,
                'controlled_entity_arm_joint_delta_rad': phase_motion,
                'other_entity_physical_drift_rad': passive_physics_drift,
                'interpretation': 'resource writes and target/ack identities are Entity-local; non-commanded Entity state is measured and may respond to physics',
            },
            'clock_evidence': {
                'rows': clock_rows,
                'completion_source': 'RuntimeSession.step returned; public control boundary advanced by one and simulation clock by 0.010 s',
                'native_substep_limit': 'five 2 ms steps inferred from public native time; no provider-private counter read',
            },
            'recording': {
                'path': str(h5_path),
                'schema_id': 'task-env-h5',
                'schema_version': 'v3',
                'transition_count': records['transition_count'],
                'observation_count': records['observation_count'],
                'writer_control_rows': saved_writer_controls,
                'entity_joint_leaf_shapes': {entity: list(values.shape) for entity, values in disk_joints.items()},
                'entity_hand_leaf_shapes': {entity: list(values.shape) for entity, values in disk_hands.items()},
                'boundary_identity_leaf_shape': list(disk_boundary.shape),
                'disk_numeric_and_boundary_identity_readback': 'PASS',
                'outcome': records['outcome'].to_mapping(),
                'finish_api_result': finish,
            },
            'guards': {
                'post_horizon_action': 'rejected without additional compute/apply/step/transition',
                'after_close_action': 'rejected without additional compute/apply/step',
                'repeat_reset': {
                    'new_episode_id': reset_after.episode_id,
                    'same_reset_sample_id': reset_after.reset_sample_id,
                    'controller_memories_reset_independently': True,
                },
            },
            'partial_commit_fault': fault,
            'force_free': {
                'control_feedback_called_during_rollout': False,
                'measured_actuator_force_requested': False,
            },
        }
    finally:
        if env.session is not None:
            env.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=('geophys', 'mujoco'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt_path = args.output / f'{args.provider}-receipt.json'
    try:
        receipt = run_probe(args.provider, args.output)
    except BaseException as error:
        receipt = {
            'schema_version': 'geochora.c02b-dual-entity-position-s2-receipt-v1',
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
