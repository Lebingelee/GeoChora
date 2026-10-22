#!/usr/bin/env python3
"""One isolated C05c GeoPhys gripper-cadence group, including S2 and same-run S3."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from task_env.controllers.canonical.contracts import CanonicalControlTarget
from task_env.runtime.sessions.provenance import provider_build_identity
from task_env.tasks.nut_assembly.task import (
    NutAssemblyReferenceEnv,
    build_gripper_cadence_diagnostic_solution,
)
from task_env.trajectory.canonical.execution import expand_snapshot, load


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finite_leaves(value):
    if isinstance(value, dict):
        return all(_finite_leaves(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(_finite_leaves(item) for item in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value))
    return True


def _arm_values(mapping):
    return {str(key): float(value) for key, value in mapping['arm_servo_position'].items()}


def _close_authorization(value):
    for boundary in value.get('boundaries', ()):
        snapshot = expand_snapshot(boundary['owners'], value['blobs'])
        outcome = snapshot['owners']['coordinator']['fields']['task_outcome']['value']
        authorization = outcome.get('close_authorization')
        if authorization is not None:
            return authorization
    return None


def validate_h5(value, expected, *, require_guard=False):
    """Read back structured execution data and verify identities, cadence and clocks."""
    transitions = value['transitions']
    boundaries = value['boundaries']
    assert len(boundaries) == len(transitions) + 1
    assert len(transitions) > 0
    metadata = value['metadata']
    assert metadata['execution']['physics_provider'] == 'geophys'
    assert metadata['execution']['backend'] == expected['backend']
    assert metadata['expert_identity'] == expected['solution_identity']
    assert metadata['controller_identity'] == expected['controller_identity']
    assert metadata['task_artifact_hash'] == expected['artifact_identity']
    provenance = metadata['source_provenance']
    assert provenance['runtime_source_id'] == expected['source_id']
    assert provenance['runtime_source_xml_sha256'] == expected['source_xml_sha256']
    assert provenance['controller_identity'] == expected['controller_identity']
    assert provenance['solution_identity'] == expected['solution_identity']

    resolved = json.loads(provenance['resolved_configuration_json'])
    assert resolved['source_xml_sha256'] == expected['source_xml_sha256']
    assert resolved['runtime_config']['runtime']['backend'] == expected['backend']
    assert resolved['gripper_control_hz'] == expected['gripper_control_hz']
    assert resolved['gripper_feedback_hz'] == 500
    assert resolved['controller_identity'] == expected['controller_identity']
    assert resolved['solution_identity'] == expected['solution_identity']

    for boundary_index, boundary in enumerate(boundaries):
        record = boundary['record']
        state = record['state']
        expected_time = boundary_index * 0.01
        assert record['control_step'] == boundary_index
        assert state['control_step'] == boundary_index
        assert abs(record['simulation_time'] - expected_time) <= 1e-10
        assert abs(state['simulation_time'] - expected_time) <= 1e-10
        assert boundary['native_step_index'] == boundary_index * 5
        assert _finite_leaves(state)

    stage_counts = Counter()
    modes = Counter()
    all_samples = []
    guard_samples = []
    force_values = []
    openings = []
    force_mode_samples = 0
    update_count = hold_count = 0
    descend_position_errors = []
    for step, transition in enumerate(transitions):
        record = transition['record']
        interval = transition['interval']
        stage = record['expert_stage']
        stage_counts[stage] += 1
        rows = interval['substeps']
        assert interval['control_step'] == step
        assert interval['native_step_count'] == 5 and len(rows) == 5
        assert [row['index'] for row in rows] == list(range(5))
        assert [row['native_step_index'] for row in rows] == [step * 5 + i + 1 for i in range(5)]
        request = json.loads(record['expert_diagnostics']['arm_execution_request_v1'])
        assert request['schema_version'] == 'arm-target-execution-request-v1'
        assert request['profile_id'] == 'nutassembly-r3-hold-ramp-v1'
        assert request['mode'] in {'track', 'hold_last_applied', 'ramp_from_last_applied'}
        modes[request['mode']] += 1
        start_snapshot = expand_snapshot(boundaries[step]['owners'], value['blobs'])
        start_outcome = start_snapshot['owners']['coordinator']['fields']['task_outcome']['value']
        start_boundary_id = start_outcome['expert_execution_boundary_v1']['identity_hash']
        for substep_index, row in enumerate(rows):
            state = row['state']
            target_time = step * 0.01 + substep_index * 0.002
            assert state['control_step'] == step
            assert abs(state['simulation_time'] - target_time) <= 1e-10
            assert _finite_leaves(state)
            target, applied = row['target'], row['applied']
            target_identity = CanonicalControlTarget.from_mapping(target).identity_hash
            assert applied['target_hash'] == target_identity
            assert applied['provider_name'] == 'geophys'
            sample = row['native_feedback_sample_v1']
            assert sample['provider'] == 'geophys'
            assert sample['provider_materialization_id'] == expected['provider_materialization_id']
            assert sample['task_artifact_hash'] == expected['artifact_identity']
            assert sample['source_id'] == expected['source_id']
            assert sample['source_xml_sha256'] == expected['source_xml_sha256']
            assert sample['controller_identity'] == expected['controller_identity']
            assert sample['solution_identity'] == expected['solution_identity']
            assert sample['episode_id'] == expected['episode_id']
            assert sample['reset_sample_id'] == expected['reset_sample_id']
            assert sample['evaluation_boundary_id'] == start_boundary_id
            assert sample['control_step'] == step and sample['substep_index'] == substep_index
            assert abs(sample['evaluation_time_s'] - target_time) <= 1e-10
            phase = 'reset_forward' if step == 0 and substep_index == 0 else 'native_step_pre_integration'
            assert sample['sample_phase'] == phase
            expected_sample_time = 0.0 if phase == 'reset_forward' else target_time - 0.002
            assert abs(sample['sample_time_s'] - expected_sample_time) <= 1e-10
            native = sample['provider_feedback_sample']
            measurement = native['actuator_force_measurement']
            assert measurement['valid'] is True
            assert measurement['force_unit'] == 'N'
            assert measurement['phase'] == phase
            expected_native_index = step * 5 + substep_index
            assert int(measurement['native_step_index']) == expected_native_index
            assert abs(float(measurement['evaluation_simulation_time_s']) - target_time) <= 1e-10
            expected_native_time = 0.0 if phase == 'reset_forward' else target_time - 0.002
            assert abs(float(measurement['native_sample_time_s']) - expected_native_time) <= 1e-10
            assert measurement['episode_id'] == expected['episode_id']
            assert measurement['reset_sample_id'] == expected['reset_sample_id']
            assert int(measurement['sample_sequence']) == int(sample['sample_sequence'])
            assert math.isfinite(float(measurement['signed_force_N']))
            raw_force = float(measurement['signed_force_N'])
            closing_force = float(sample['feedback']['gripper']['closing_force_N'])
            assert abs(closing_force - max(0.0, -raw_force)) <= 1e-10
            diagnostics = sample['controller_diagnostics']
            performed = bool(diagnostics['inner_update_performed'])
            period = 0.002 if expected['gripper_control_hz'] == 500 else 0.01
            assert int(diagnostics['configured_inner_rate_hz']) == expected['gripper_control_hz']
            assert abs(float(diagnostics['inner_update_period_s']) - period) <= 1e-12
            expected_update = expected['gripper_control_hz'] == 500 or substep_index == 0
            assert performed is expected_update
            update_count += int(performed)
            hold_count += int(not performed)
            force_values.append(raw_force)
            openings.append(float(diagnostics['measured_opening_m']))
            force_mode_samples += int(bool(diagnostics['force_mode_active']))
            assert sample['applied_acknowledgement'] == applied
            assert sample['target_hash'] == applied['target_hash']
            all_samples.append(sample)
            if stage == 'close_gripper':
                guard_samples.append(sample)

        outer_target = CanonicalControlTarget.from_mapping(record['controller_target'])
        assert record['applied_control']['target_hash'] == outer_target.identity_hash
        assert record['applied_control']['provider_name'] == 'geophys'
        assert rows[-1]['target'] == record['controller_target']
        assert rows[-1]['applied'] == record['applied_control']

        if stage == 'descend_to_handle':
            desired = np.asarray(record['requested_action']['values'][:3], dtype=np.float64)
            actual = np.asarray(boundaries[step + 1]['record']['state']['pose_world']['panda-v1/ee']['position'], dtype=np.float64)
            descend_position_errors.append(float(np.linalg.norm(actual - desired)))

    sequences = [int(sample['sample_sequence']) for sample in all_samples]
    assert len(all_samples) == len(transitions) * 5
    assert all(after == before + 1 for before, after in zip(sequences, sequences[1:]))
    expected_updates = len(transitions) * (5 if expected['gripper_control_hz'] == 500 else 1)
    expected_holds = len(transitions) * (0 if expected['gripper_control_hz'] == 500 else 4)
    assert update_count == expected_updates and hold_count == expected_holds
    assert modes['hold_last_applied'] >= 0 and modes['ramp_from_last_applied'] >= 0

    for step, transition in enumerate(transitions):
        mode = json.loads(transition['record']['expert_diagnostics']['arm_execution_request_v1'])['mode']
        if mode == 'hold_last_applied':
            assert step > 0
            previous = _arm_values(transitions[step - 1]['record']['applied_control'])
            for row in transition['interval']['substeps']:
                assert _arm_values(row['target']) == previous
                assert _arm_values(row['applied']) == previous
        elif mode == 'ramp_from_last_applied':
            assert step > 0
            initial = _arm_values(transitions[step - 1]['record']['applied_control'])
            endpoint = _arm_values(transition['record']['controller_target'])
            for i, row in enumerate(transition['interval']['substeps']):
                fraction = (i + 1) / 5
                expected_ramp = {key: initial[key] + fraction * (endpoint[key] - initial[key]) for key in initial}
                assert all(abs(_arm_values(row['target'])[key] - expected_ramp[key]) <= 1e-12 for key in initial)
                # Provider applied acknowledgements are float32. The observed
                # maximum quantization error on this source is below 1.2e-7 rad.
                assert all(abs(_arm_values(row['applied'])[key] - expected_ramp[key]) <= 2e-7 for key in initial)

    authorization = _close_authorization(value)
    if require_guard:
        assert authorization is not None
        assert authorization['authorization_guard_id'] in {'primary_controller_close_ready', 'alternative_force_8n'}
        assert authorization['required_stable_duration_s'] == 0.1
        assert authorization['observed_stable_duration_s'] >= 0.1 - 1e-10
        assert authorization['native_sample_count'] >= 50
        assert authorization['authorization_time_s'] <= authorization['transition_consumed_at_outer_boundary_s']
        auth_sequence = int(authorization['values']['native_sample_sequence'])
        window_count = int(authorization['native_sample_count'])
        authorized_window = [sample for sample in guard_samples
                             if auth_sequence - window_count + 1 <= int(sample['sample_sequence']) <= auth_sequence]
        assert len(authorized_window) == window_count
        assert [int(sample['sample_sequence']) for sample in authorized_window] == list(
            range(auth_sequence - window_count + 1, auth_sequence + 1)
        )
        assert all(max(0.0, -float(sample['provider_feedback_sample']['actuator_force_measurement']['signed_force_N']))
                   >= 8.0 for sample in authorized_window)
        assert all(sample['controller_diagnostics']['force_mode_active'] is True
                   for sample in authorized_window)

    final_snapshot = expand_snapshot(boundaries[-1]['owners'], value['blobs'])
    disk_outcome = final_snapshot['owners']['coordinator']['fields']['task_outcome']['value']
    final_joint = boundaries[-1]['record']['state']['joint_position']
    initial_joint = boundaries[0]['record']['state']['joint_position']
    max_joint_delta = max(abs(float(final_joint[name]) - float(initial_joint[name])) for name in initial_joint)
    nut_start = np.asarray(boundaries[0]['record']['state']['pose_world']['square-nut-v1']['position'], dtype=np.float64)
    nut_end = np.asarray(boundaries[-1]['record']['state']['pose_world']['square-nut-v1']['position'], dtype=np.float64)
    task_success_first = next((i + 1 for i, t in enumerate(transitions) if t['record'].get('reward', 0.0) > 0.0), None)
    return {
        'transition_count': len(transitions), 'boundary_count': len(boundaries),
        'native_sample_count': len(all_samples), 'guard_close_sample_count': len(guard_samples),
        'gripper_update_count': update_count, 'gripper_hold_count': hold_count,
        'arm_execution_modes': dict(modes), 'stage_counts': dict(stage_counts),
        'force_mode_native_sample_count': force_mode_samples,
        'raw_signed_force_N': {'min': min(force_values), 'max': max(force_values),
                               'last': force_values[-1]},
        'canonical_closing_force_N': {
            'min': min(max(0.0, -value) for value in force_values),
            'max': max(max(0.0, -value) for value in force_values),
        },
        'gripper_opening_m': {'min': min(openings), 'max': max(openings), 'last': openings[-1]},
        'descend_request_tracking_error_m': {
            'count': len(descend_position_errors),
            'rmse': float(np.sqrt(np.mean(np.square(descend_position_errors)))) if descend_position_errors else None,
            'max': max(descend_position_errors) if descend_position_errors else None,
        },
        'max_joint_position_delta_rad': max_joint_delta,
        'nut_displacement_m': float(np.linalg.norm(nut_end - nut_start)),
        'guard_authorization': authorization,
        'disk_outcome': disk_outcome,
        'disk_outcome_control_step': disk_outcome['control_step'],
        'start_time_s': float(boundaries[0]['record']['simulation_time']),
        'end_time_s': float(boundaries[-1]['record']['simulation_time']),
        'stop_reason': value['stop_reason'],
    }


def _install_reader_timer(phase, timing):
    from control.robot_arm_observation import RobotArmObservationReader
    original = RobotArmObservationReader.read_cpu_snapshot

    def measured(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            timing[phase['name']]['reader_cpu_snapshot_s'].append(time.perf_counter() - start)

    RobotArmObservationReader.read_cpu_snapshot = measured


def _instrument(env, phase, timing):
    def wrap(owner, name, metric):
        original = getattr(owner, name)

        def measured(*args, **kwargs):
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                timing[phase['name']][metric].append(time.perf_counter() - start)

        setattr(owner, name, measured)

    wrap(env.session, 'control_feedback', 'session_control_feedback_s')
    wrap(env.session, 'apply_control', 'session_apply_control_s')
    wrap(env.session, '_step_physics_once', 'core_native_step_call_s')
    wrap(env.controller.inner, 'inner_gripper_step', 'gripper_law_call_s')


def _timing_summary(timing):
    summary = {}
    for phase, metrics in timing.items():
        summary[phase] = {}
        for name, values in metrics.items():
            arr = np.asarray(values, dtype=np.float64)
            summary[phase][name] = {
                'count': int(arr.size),
                'total_s': float(arr.sum()) if arr.size else 0.0,
                'mean_s': float(arr.mean()) if arr.size else None,
                'median_s': float(np.median(arr)) if arr.size else None,
                'p95_s': float(np.quantile(arr, 0.95)) if arr.size else None,
                'max_s': float(arr.max()) if arr.size else None,
            }
    return summary


def _gpu_evidence():
    try:
        return subprocess.check_output([
            'nvidia-smi', '--query-gpu=index,name,uuid,driver_version,memory.total',
            '--format=csv,noheader',
        ], text=True, stderr=subprocess.STDOUT, timeout=10).strip()
    except Exception as exc:
        return f'{type(exc).__name__}: {exc}'


def run_group(backend, gripper_hz, output_dir):
    output_dir.mkdir(parents=True, exist_ok=False)
    h5_probe = output_dir / 'geophys-cadence-probe.h5'
    h5_full = output_dir / 'geophys-external-expert-s2-s3.h5'
    result_path = output_dir / 'result.json'
    log_path = output_dir / 'stdout.log'
    phase = {'name': 'construct_reset'}
    timing = defaultdict(lambda: defaultdict(list))
    _install_reader_timer(phase, timing)
    result = {
        'schema': 'c05c-geophys-gripper-cadence-group-v1',
        'provider': 'geophys', 'provider_revision_required': 'a53a8cfed7c9d6464274b5c96fca601271dc4ee4',
        'backend': backend, 'gripper_control_hz': gripper_hz,
        'native_feedback_hz': 500, 'outer_control_hz': 100,
        'physics_dt_s': 0.002, 'control_dt_s': 0.01, 'native_steps_per_interval': 5,
        'task_uid': 'nut-assembly-outcome-reference-v1', 'seed': 19,
        'artifact_id': 'nut-assembly-square-v1/p1_8_e/nominal-v1',
        'guard_threshold_N': 8.0, 'guard_dwell_s': 0.1,
        'force_target_N': 10.0, 'force_limit_N': 10.0,
        'h5_probe_path': str(h5_probe), 'h5_full_path': str(h5_full),
        'gpu_inventory': _gpu_evidence(),
        's2': {'status': 'not_run'}, 's3': {'status': 'not_run'},
    }
    env = solution = None
    try:
        start_setup = time.perf_counter()
        env = NutAssemblyReferenceEnv.for_gripper_cadence_diagnostic(
            backend=backend, gripper_control_hz=gripper_hz, horizon=6000,
        )
        solution = build_gripper_cadence_diagnostic_solution(
            backend=backend, gripper_control_hz=gripper_hz,
        )
        reset_observation, reset_info = env.reset_for_solution(solution, seed=19)
        initial_boundary = reset_info['expert_execution_boundary_v1']
        source = env.value['source']
        provider_identity = provider_build_identity('geophys')
        if provider_identity['repository_revision'] != result['provider_revision_required']:
            raise RuntimeError(f"wrong GeoPhys checkout: {provider_identity['manifest_version']}")
        if env.execution.backend != backend or source.config.runtime.backend != backend:
            raise RuntimeError('requested backend does not match materialized source/ExecutionSpec')
        result.update({
            'provider_build_identity': provider_identity,
            'task_artifact_identity': env.artifact.identity_hash,
            'source_id': source.scene_source.source_id,
            'source_xml_sha256': hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
            'source_closure_digest': source.source_closure_digest,
            'controller_identity': env.controller.identity,
            'solution_identity': solution.identity,
            'reset_sample_id': initial_boundary['reset_sample_id'],
            'episode_id': initial_boundary['episode_id'],
            'provider_materialization_id': initial_boundary['provider_materialization_id'],
            'reset_boundary_identity': initial_boundary['identity_hash'],
            'reset_clock': {'control_step': int(env.state.control_step),
                            'simulation_time_s': float(env.state.simulation_time)},
            'reset_observation_keys': sorted(reset_observation),
            'runtime_config': env.value['recipe']['runtime_config'],
            'diagnostic_identity': env.value['recipe'].get('diagnostic_experiment'),
            'configuration_diff': {
                'fixed': ['NA-S0 seed19', 'R3', '10 N target/cap', '8 N / 0.1 s Guard',
                          '500 Hz native feedback', '100 Hz outer', '2 ms native dt',
                          'five native steps', 'arm hold/ramp and outcome policy'],
                'varied': ['GeoPhys backend', 'gripper control cadence'],
                'backend': backend, 'gripper_control_hz': gripper_hz,
            },
        })
        setup_reset_wall = time.perf_counter() - start_setup

        phase['name'] = 'probe'
        _instrument(env, phase, timing)
        env.start_recording(h5_probe)
        probe_wall = []
        for index in range(2):
            start = time.perf_counter()
            _, _, terminated, truncated, info = env.step_with_solution(solution)
            probe_wall.append(time.perf_counter() - start)
            if terminated or truncated:
                raise RuntimeError('minimal cadence Probe ended before two complete intervals')
        probe_finish = env.finish_recording('gripper-cadence-probe-complete')
        probe_disk = load(h5_probe)
        probe_expected = {
            'backend': backend, 'gripper_control_hz': gripper_hz,
            'artifact_identity': result['task_artifact_identity'],
            'source_id': result['source_id'], 'source_xml_sha256': result['source_xml_sha256'],
            'controller_identity': result['controller_identity'],
            'solution_identity': result['solution_identity'],
            'episode_id': initial_boundary['episode_id'], 'reset_sample_id': initial_boundary['reset_sample_id'],
            'provider_materialization_id': initial_boundary['provider_materialization_id'],
            'request_boundary_id': initial_boundary['identity_hash'],
        }
        probe_readback = validate_h5(probe_disk, probe_expected)
        assert probe_readback['transition_count'] == 2 and probe_readback['native_sample_count'] == 10
        assert env.state.control_step == 2 and abs(env.state.simulation_time - 0.02) <= 1e-10
        probe_servo_counts = {
            'updates': int(env.controller.inner.update_count),
            'holds': int(env.controller.inner.held_count),
        }
        expected_probe_counts = {'updates': 10 if gripper_hz == 500 else 2,
                                 'holds': 0 if gripper_hz == 500 else 8}
        assert probe_servo_counts == expected_probe_counts
        result['probe'] = {
            'status': 'passed', 'intervals': 2, 'native_samples': probe_readback['native_sample_count'],
            'requested_steps': 10, 'completed_steps': 10,
            'probe_end_clock': {'control_step': int(env.state.control_step),
                                'simulation_time_s': float(env.state.simulation_time)},
            'servo_counts': probe_servo_counts, 'readback': probe_readback,
            'recorder_finish': probe_finish, 'h5_sha256': _sha(h5_probe.read_bytes()),
            'interval_wall_s': probe_wall,
        }
        result['provider_cuda_context_evidence'] = (
            'see stdout.log for Taichi arch banner and GPU inventory above' if backend == 'cuda'
            else 'CPU requested and materialized; no CUDA context required'
        )

        # Reuse the same task-owned Solution and the same deterministic ResetSample.
        # Probe is finalized before reset; the full S2/S3 run then gets one fresh episode.
        phase['name'] = 'full_reset'
        before_full_reset = time.perf_counter()
        _, full_reset_info = env.reset_for_solution(solution, seed=19)
        full_boundary = full_reset_info['expert_execution_boundary_v1']
        assert full_boundary['reset_sample_id'] == initial_boundary['reset_sample_id']
        assert env.state.control_step == 0 and env.state.simulation_time == 0.0
        full_reset_wall = time.perf_counter() - before_full_reset
        result['full_episode_identity'] = {
            'episode_id': full_boundary['episode_id'],
            'reset_sample_id': full_boundary['reset_sample_id'],
            'provider_materialization_id': full_boundary['provider_materialization_id'],
            'reset_boundary_identity': full_boundary['identity_hash'],
        }
        phase['name'] = 'full_expert'
        _instrument(env, phase, timing)
        env.start_recording(h5_full)
        stage_trace = []
        previous_stage = None
        task_success_first = None
        steps = 0
        final_info = dict(env.info)
        terminated = truncated = False
        loop_start = time.perf_counter()
        while not solution.done and not solution.failed and not (terminated or truncated):
            _, _, terminated, truncated, final_info = env.step_with_solution(solution)
            steps += 1
            stage = str(final_info.get('expert_stage', 'unknown'))
            if stage != previous_stage:
                stage_trace.append({'control_step': int(env.state.control_step),
                                    'simulation_time_s': float(env.state.simulation_time), 'stage': stage})
                previous_stage = stage
            if task_success_first is None and bool(final_info.get('task_metrics', {}).get('task_success', False)):
                task_success_first = {'control_step': int(env.state.control_step),
                                      'simulation_time_s': float(env.state.simulation_time)}
            if steps >= 6000 and not (solution.done or solution.failed or terminated or truncated):
                raise RuntimeError('NutAssembly external Solution exceeded fixed 6000 interval horizon')
        full_loop_wall = time.perf_counter() - loop_start
        outcome = solution.outcome_report()
        result['s2'] = {
            'status': 'passed' if (
                solution.done and not solution.failed and outcome['task_success']
                and outcome['planned_trajectory_completed'] and outcome['outcome_complete']
                and outcome['original_expert_lifecycle_status']['expert_complete']
                and not outcome['original_expert_lifecycle_status']['expert_failed']
                and not outcome['readiness_warnings'] and not terminated and not truncated
            ) else 'failed',
            'transition_count': steps,
            'requested_native_steps': steps * 5,
            'completed_native_steps': len(timing['full_expert']['core_native_step_call_s']),
            'simulated_time_s': float(env.state.simulation_time),
            'task_success': bool(outcome['task_success']),
            'task_success_first': task_success_first,
            'outcome_complete': bool(outcome['outcome_complete']),
            'planned_trajectory_completed': bool(outcome['planned_trajectory_completed']),
            'original_strict_expert_lifecycle': outcome['original_expert_lifecycle_status'],
            'readiness_warnings': outcome['readiness_warnings'],
            'solution_done': bool(solution.done), 'solution_failed': bool(solution.failed),
            'failure_reason': solution.failure_reason,
            'first_failure_stage': (solution.stage if solution.failed else None),
            'stage_trace': stage_trace,
            'terminated': bool(terminated), 'truncated': bool(truncated),
            'runtime_fault': None if env.execution_fault is None else env.execution_fault.to_mapping(),
            'solution_outcome_report': outcome,
            'full_loop_wall_s': full_loop_wall,
            'simulated_speed_x': float(env.state.simulation_time) / full_loop_wall if full_loop_wall else None,
        }
        reason = 'nutassembly-external-expert-complete' if solution.done else (
            'nutassembly-external-expert-failed-' + str(solution.failure_reason)
        )
        phase['name'] = 'full_finalize'
        result['recorder_finish'] = env.finish_recording(reason)
        phase['name'] = 'full_disk_readback'
        full_disk = load(h5_full)
        full_expected = {
            'backend': backend, 'gripper_control_hz': gripper_hz,
            'artifact_identity': result['task_artifact_identity'],
            'source_id': result['source_id'], 'source_xml_sha256': result['source_xml_sha256'],
            'controller_identity': result['controller_identity'],
            'solution_identity': result['solution_identity'],
            'episode_id': full_boundary['episode_id'], 'reset_sample_id': full_boundary['reset_sample_id'],
            'provider_materialization_id': full_boundary['provider_materialization_id'],
            'request_boundary_id': full_boundary['identity_hash'],
        }
        readback = validate_h5(full_disk, full_expected,
                               require_guard=bool(outcome.get('close_authorization')))
        disk_h5_sha = _sha(h5_full.read_bytes())
        result['s3'] = {
            'status': 'passed' if (
                len(full_disk['boundaries']) == len(full_disk['transitions']) + 1
                and readback['transition_count'] == steps
                and readback['disk_outcome']['task_success'] == outcome['task_success']
                and readback['disk_outcome']['outcome_complete'] == outcome['outcome_complete']
            ) else 'failed',
            **readback, 'h5_sha256': disk_h5_sha,
            'h5_size_bytes': h5_full.stat().st_size,
        }
        result['timing'] = {
            'setup_and_initial_reset_wall_s': setup_reset_wall,
            'second_reset_wall_s': full_reset_wall,
            'full_expert_loop_wall_s': full_loop_wall,
            'full_expert_plus_recording_and_readback_wall_s': time.perf_counter() - start_setup,
            'probe_first_interval_includes_initial_native_compile': probe_wall[0],
            'probe_second_interval_steady_candidate': probe_wall[1],
            'phase_costs': _timing_summary(timing),
            'note': 'read_cpu_snapshot timing includes host copy/synchronization; CUDA step timing may be asynchronous submission, so do not sum overlapping counters.',
        }
        result['s2_s3_status'] = 'passed' if result['s2']['status'] == result['s3']['status'] == 'passed' else 'not_passed'
        result['status'] = result['s2_s3_status']
    except BaseException as exc:
        result['status'] = 'failed_or_blocked'
        result['error'] = f'{type(exc).__name__}: {exc}'
        result['failure_phase'] = phase['name']
        if solution is not None:
            result['partial_solution'] = {
                'stage': getattr(solution, 'stage', None),
                'done': bool(getattr(solution, 'done', False)),
                'failed': bool(getattr(solution, 'failed', False)),
                'failure_reason': getattr(solution, 'failure_reason', None),
            }
        if env is not None:
            try:
                result['runtime_fault'] = None if env.execution_fault is None else env.execution_fault.to_mapping()
                result['partial_clock'] = {'control_step': int(env.state.control_step),
                                           'simulation_time_s': float(env.state.simulation_time)}
            except Exception:
                pass
        result['timing'] = {'phase_costs': _timing_summary(timing)}
    finally:
        if env is not None:
            try:
                env.close()
            except BaseException as close_error:
                result['close_error'] = f'{type(close_error).__name__}: {close_error}'
        result['result_sha256'] = None
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--gripper-hz', type=int, choices=(100, 500), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = run_group(args.backend, args.gripper_hz, args.output_dir)
    if result['status'] != 'passed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
