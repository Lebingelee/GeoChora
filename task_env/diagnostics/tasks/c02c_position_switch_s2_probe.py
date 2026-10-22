"""Real-provider, single-process-per-provider C02c Position switch S2 probe."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import traceback

import h5py
import numpy as np

from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.c02b_position_candidate import (
    POSITION_CANDIDATE_SEED,
    build_position_candidate,
)
from task_env.recorders import load_structured_control_records_h5
from task_env.runtime.sessions.control import (
    apply_position_control_target,
    prepare_structured_action,
)


def _request(env, *, dx):
    frame = next(
        item for item in env.typed_state.view.frames
        if item.frame.entity_id == 'panda-main' and item.frame.frame_id == 'hand'
    )
    schema = env.position_plan.controller_bindings[0].action_schema
    values = (
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
                tuple(float(value) for value in values),
            ),
            ControlGroupActionV1(
                'control-group-action-v1', 'panda-main', 'gripper', schema.schema_id,
                (1.0,),
            ),
        ),
    )


def _state_leaves(observation):
    return {
        'joint_position': np.asarray(observation['state']['joint_position']).copy(),
        'hand_pose': np.asarray(observation['state']['hand_pose']).copy(),
        'boundary_identity_sha256': np.asarray(
            observation['state']['boundary_identity_sha256'], dtype=np.uint8,
        ).copy(),
    }


def _ordered_positions(target):
    return np.asarray([target.arm_position[key] for key in sorted(target.arm_position)])


def run_probe(provider: str, output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    candidate = build_position_candidate(output / 'candidate-source', provider=provider, horizon=4)
    env = candidate.env
    record_path = output / f'{provider}-c02c-position-switch.h5'
    leaf_rows = []
    session_type = None
    try:
        reset_observation, _reset_info = env.reset()
        env.start_recording(record_path)
        leaf_rows.append(_state_leaves(reset_observation))

        # Control once under the original C02b parameterization. This establishes
        # the first complete, recorded T/T+1 boundary before a switch is requested.
        first = env.step(_request(env, dx=0.0))
        leaf_rows.append(_state_leaves(first[0]))
        old_profile = env.controller
        old_target = env.last_position_transition[1]
        old_identity = old_profile.identity
        effective_publication = env.typed_state
        effective_boundary = effective_publication.view.boundary
        effective_clock = effective_publication.view.sample_clock
        before_switch_state = env.session.snapshot()
        recorder_before = (env.recorder.transition_count, env.recorder.observation_count)
        session_type = type(env.session)

        switched = PandaPositionServoProfileV1.from_source(
            env.artifact,
            candidate.source,
            config=replace(
                old_profile.config,
                ik_position_gain=old_profile.config.ik_position_gain * 0.5,
            ),
        )
        if (switched.identity == old_identity
                or switched.controller_binding() != old_profile.controller_binding()
                or switched.config == old_profile.config):
            raise AssertionError('candidate switch is not a distinct compatible parameterized instance')

        dispatch = {'compute': 0, 'apply': 0, 'step': 0}
        original_compute = PandaPositionServoProfileV1.compute
        original_apply = session_type.apply_control
        original_step = session_type.step

        def counted_compute(profile, *args, **kwargs):
            dispatch['compute'] += 1
            return original_compute(profile, *args, **kwargs)

        def counted_apply(session, *args, **kwargs):
            dispatch['apply'] += 1
            return original_apply(session, *args, **kwargs)

        def counted_step(session, *args, **kwargs):
            dispatch['step'] += 1
            return original_step(session, *args, **kwargs)

        # This real boundary operation must not call any execution owner.
        from unittest.mock import patch
        with (
            patch.object(PandaPositionServoProfileV1, 'compute', counted_compute),
            patch.object(session_type, 'apply_control', counted_apply),
            patch.object(session_type, 'step', counted_step),
        ):
            switch_event = env.switch_position_controller(switched)
            if dispatch != {'compute': 0, 'apply': 0, 'step': 0}:
                raise AssertionError(f'switch itself dispatched execution: {dispatch}')
            if env.session.snapshot().to_mapping() != before_switch_state.to_mapping():
                raise AssertionError('switch changed public physical state or clock')
            if (env.recorder.transition_count, env.recorder.observation_count) != recorder_before:
                raise AssertionError('switch appended a transition or changed T/T+1')

            # Make a same-boundary old-identity target and verify it is refused
            # before any Provider apply/step while the new Profile is admitted.
            old_shadow = PandaPositionServoProfileV1.from_source(
                env.artifact, candidate.source, config=old_profile.config,
            )
            activation = old_shadow._prepare_switch_activation(
                env.typed_state, env.position_plan,
            )
            old_shadow._activate_switch_memory(activation)
            next_request = _request(env, dx=0.025)
            requested = prepare_structured_action(env.position_plan, next_request)[0][1]
            _old_canonical, old_same_boundary_target = old_shadow.compute(
                env.typed_state, requested, env.position_plan,
            )
            # The shadow compute above is diagnostic-only; exclude it from the
            # live switch call counters from here on and use a fresh dispatch row.
            dispatch.update({'compute': 0, 'apply': 0, 'step': 0})
            try:
                apply_position_control_target(
                    env.session, old_same_boundary_target,
                    controller_profile=switched, plan=env.position_plan,
                    publication=env.typed_state, scene=env.position_scene,
                    joint_bindings=env.position_joint_bindings,
                    frame_bindings=env.position_frame_bindings,
                )
            except ValueError as error:
                if 'position target writer/Profile/plan/source boundary mismatch' not in str(error):
                    raise
            else:
                raise AssertionError('old Controller target was accepted after the switch')
            if dispatch != {'compute': 0, 'apply': 0, 'step': 0}:
                raise AssertionError(f'rejected old target dispatched execution: {dispatch}')

            old_boundary_state = env.state
            old_boundary_id = effective_boundary.boundary_id
            old_time = old_boundary_state.simulation_time
            next_result = env.step(next_request)
        leaf_rows.append(_state_leaves(next_result[0]))

        if dispatch != {'compute': 1, 'apply': 1, 'step': 1}:
            raise AssertionError(f'first post-switch action did not dispatch exactly once: {dispatch}')
        if env.state.control_step != effective_boundary.control_step + 1:
            raise AssertionError('post-switch control clock did not advance exactly once')
        elapsed = float(env.state.simulation_time - old_time)
        if abs(elapsed - env.artifact.timebase.control_dt) > 1.0e-9:
            raise AssertionError(f'post-switch interval time delta is wrong: {elapsed}')
        inferred_native_steps = int(round(elapsed / env.artifact.timebase.physics_dt))
        if inferred_native_steps != env.artifact.timebase.control_substeps:
            raise AssertionError('public native clock does not imply the configured five substeps')

        canonical, new_target, applied = env.last_position_transition
        if new_target.controller_identity != switched.identity:
            raise AssertionError('first actual post-switch target did not use the new Controller identity')
        if new_target.source_boundary.boundary_id != old_boundary_id:
            raise AssertionError('new target is not bound to the switch effective T boundary')
        if applied.target_hash != new_target.target.identity_hash:
            raise AssertionError('new target and applied acknowledgement identity differ')
        if np.allclose(
            _ordered_positions(new_target.target),
            _ordered_positions(old_same_boundary_target.target),
            rtol=0.0, atol=1.0e-10,
        ):
            raise AssertionError('new gain did not change actual arm target values for the chosen request')
        if switched._activation_boundary_id != old_boundary_id:
            raise AssertionError('new Controller memory was not initialized at the effective boundary')

        env.stop('c02c-s2-boundary')
        finish = env.finish_recording('c02c-s2-boundary')
        h5_path = Path(finish['path'])
        structured = load_structured_control_records_h5(h5_path)
        if (structured['transition_count'], structured['observation_count']) != (2, 3):
            raise AssertionError('Generic H5 v3 did not retain exactly T=2 and T+1=3')
        switch_events = [item for item in structured['boundary_events']
                         if item.event_type == 'controller_instance_switch']
        if len(switch_events) != 1:
            raise AssertionError('Generic H5 v3 switch event count mismatch')
        disk_event = switch_events[0]
        if (disk_event.boundary_index != effective_boundary.control_step
                or disk_event.payload['effective_boundary']['boundary_id'] != old_boundary_id
                or disk_event.payload['effective_clock']['sample_index'] != effective_boundary.control_step):
            raise AssertionError('H5 event did not preserve the effective boundary and clock')
        if disk_event.payload['previous_controller']['controller_identity'] != old_identity:
            raise AssertionError('H5 switch event omitted the previous Controller identity')
        if disk_event.payload['effective_controller']['controller_identity'] != switched.identity:
            raise AssertionError('H5 switch event omitted the effective Controller identity')
        writer = structured['structured_controls'][1].writer_controls[0]
        if (writer['controller_target']['payload']['controller_identity'] != switched.identity
                or writer['controller_target']['identity_hash'] != writer['applied_control']['target_hash']):
            raise AssertionError('H5 next target/ack does not prove new instance control application')
        application = writer['canonical_action']['controller_switch_application']
        if (application['switch_id'] != disk_event.payload['switch_id']
                or application['status'] != 'target_and_applied_ack_recorded'
                or application['target_identity_hash'] != writer['controller_target']['identity_hash']
                or application['applied_target_hash'] != writer['applied_control']['target_hash']):
            raise AssertionError('H5 does not join the effective switch event to its first applied target/ack')
        target_row = writer['canonical_action']['position_target_v1']
        if (target_row['controller_identity'] != switched.identity
                or target_row['source_boundary']['control_step'] != effective_boundary.control_step):
            raise AssertionError('H5 source-bound target does not identify the T/T+1 application boundary')

        with h5py.File(h5_path, 'r') as handle:
            if str(handle.attrs['schema_version']) != 'v3':
                raise AssertionError('switch recording is not Generic H5 v3')
            disk_joint = np.asarray(handle['obs/state/joint_position'])
            disk_hand = np.asarray(handle['obs/state/hand_pose'])
            disk_boundary = np.asarray(handle['obs/state/boundary_identity_sha256'])
            if not np.array_equal(disk_joint, np.stack([row['joint_position'] for row in leaf_rows])):
                raise AssertionError('H5 joint-position leaves differ from the three live boundaries')
            if not np.array_equal(disk_hand, np.stack([row['hand_pose'] for row in leaf_rows])):
                raise AssertionError('H5 hand-pose leaves differ from the three live boundaries')
            if not np.array_equal(
                disk_boundary,
                np.stack([row['boundary_identity_sha256'] for row in leaf_rows]),
            ):
                raise AssertionError('H5 boundary identity leaves differ from live T/T+1 boundaries')

        return {
            'schema_version': 'geochora.c02c-position-switch-s2-receipt-v1',
            'status': 'PASS_BOUNDED_SINGLE_PANDA_POSITION_SWITCH_S2',
            'provider': provider,
            'backend': 'cpu',
            'task_artifact_identity_hash': env.artifact.identity_hash,
            'source_closure_digest': candidate.source.source_closure_digest,
            'reset_sample_id': candidate.reset_plan.reset_sample.sample_id,
            'control_binding_plan_identity_hash': env.position_plan.identity_hash,
            'initial_controller_identity': old_identity,
            'replacement_controller_identity': switched.identity,
            'initial_parameters': {
                'ik_position_gain': old_profile.config.ik_position_gain,
            },
            'replacement_parameters': {
                'ik_position_gain': switched.config.ik_position_gain,
            },
            'action_schema_id': switched.controller_binding().action_schema.schema_id,
            'frame': switched.tcp_profile.to_mapping(),
            'timebase': {
                'physics_dt_s': env.artifact.timebase.physics_dt,
                'control_substeps': env.artifact.timebase.control_substeps,
                'control_dt_s': env.artifact.timebase.control_dt,
            },
            'effective_boundary': {
                'boundary_id': old_boundary_id,
                'control_step': effective_boundary.control_step,
                'simulation_time_s': old_time,
            },
            'post_switch_boundary': {
                'control_step': env.state.control_step,
                'simulation_time_s': env.state.simulation_time,
                'inferred_native_steps_from_public_clock': inferred_native_steps,
            },
            'switch_dispatch_counts': {'compute': 0, 'apply': 0, 'step': 0},
            'post_switch_dispatch_counts': dict(dispatch),
            'old_same_boundary_target_rejected': True,
            'new_target_hash': new_target.target.identity_hash,
            'applied_ack_target_hash': applied.target_hash,
            'old_parameter_shadow_target': _ordered_positions(old_same_boundary_target.target).tolist(),
            'new_parameter_target': _ordered_positions(new_target.target).tolist(),
            'recording': {
                'path': str(h5_path), 'schema_version': 'v3',
                'transition_count': structured['transition_count'],
                'observation_count': structured['observation_count'],
                'switch_event_count': len(switch_events),
                'first_applied_switch_id': application['switch_id'],
                'state_leaves_read_back': ['joint_position', 'hand_pose', 'boundary_identity_sha256'],
                'source_boundary_for_first_new_target_control_step': target_row['source_boundary']['control_step'],
            },
            'evidence_claims': [
                'bounded Position candidate intersection only',
                'single panda-main Entity, CPU backend',
                'no provider-private state read',
                'no switch-time compute/apply/physics step/transition',
                'new instance first applied on the next real step',
                'not full C02b, full C02c, or Phase II completion',
            ],
        }
    finally:
        if env.session is not None:
            env.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=('geophys', 'mujoco'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt_path = args.output / f'{args.provider}-c02c-position-switch-s2-receipt.json'
    try:
        receipt = run_probe(args.provider, args.output)
    except BaseException as error:
        receipt = {
            'schema_version': 'geochora.c02c-position-switch-s2-receipt-v1',
            'status': 'FAIL', 'provider': args.provider,
            'exception_type': type(error).__name__, 'error': str(error),
            'traceback': traceback.format_exc(),
        }
        args.output.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(receipt, sort_keys=True, indent=2))
        return 1
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8',
    )
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
