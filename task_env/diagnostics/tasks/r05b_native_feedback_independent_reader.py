#!/usr/bin/env python3
"""Minimal raw HDF5 reader for one R05b run; imports no Core/provider code."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


CANONICAL_XML_SHA256 = '909759def6bbaa4c5644a100a36625400464cd571dcab1222f807efaaf1c225d'
TRUSTED_SOURCE_MANIFEST = (
    Path(__file__).resolve().parents[2] / 'tasks' / 'nut_assembly'
    / 'r05b_trusted_execution_source_manifest.json'
)


def _canonical_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    ).hexdigest()


def _closure_digest(files):
    payload = {
        'schema_version': 'source-closure-v1',
        'files': files,
    }
    return _canonical_digest(payload)


def _resolved_field(value, blobs, owner, field):
    entry = value['boundaries'][-1]['owners']['owners'][owner]['fields'][field]['value']
    if isinstance(entry, dict) and entry.get('kind') == 'content-ref':
        return blobs[entry['sha256']]
    return entry


def _validate_full_episode(value, expected, receipt):
    transitions = value['transitions']
    boundaries = value['boundaries']
    total = len(transitions)
    if total < 1 or len(boundaries) != total + 1:
        raise ValueError('full HDF5 must contain T transitions and T+1 boundaries')
    if total != expected['transition_count'] or total > 6000:
        raise ValueError('full HDF5 transition count differs from the worker receipt or task horizon')
    for index, boundary in enumerate(boundaries):
        record = boundary.get('record', {})
        state = record.get('state', {})
        if (record.get('control_step') != index
                or state.get('control_step') != index
                or boundary.get('native_step_index') != index * 5
                or abs(float(record.get('simulation_time')) - index * 0.01) > 1e-10
                or abs(float(state.get('simulation_time')) - index * 0.01) > 1e-10):
            raise ValueError('full HDF5 boundary T/T+1 clocks or native index mismatch')
    if value.get('stop_reason') != 'nutassembly-external-expert-complete':
        raise ValueError('full HDF5 did not stop at completed normal-profile Expert')
    blobs = value['blobs']
    outcome = _resolved_field(value, blobs, 'coordinator', 'task_outcome')
    lifecycle = outcome.get('original_expert_lifecycle_status', {})
    if not (outcome.get('task_success') is True
            and outcome.get('planned_trajectory_completed') is True
            and outcome.get('outcome_complete') is True
            and lifecycle.get('expert_complete') is True
            and lifecycle.get('expert_failed') is False
            and not outcome.get('readiness_warnings')
            and outcome.get('runtime_error') is None
            and outcome.get('unapproved_override_used') is not True
            and outcome.get('control_step') == total):
        raise ValueError('disk Outcome or strict Expert lifecycle is incomplete')
    if expected.get('require_task_success') is True and outcome.get('task_success') is not True:
        raise ValueError('disk task Outcome is not successful')

    all_samples = []
    close_samples = []
    update_count = hold_count = 0
    law_hz = expected['gripper_control_hz']
    config = json.loads(value['metadata']['source_provenance']['resolved_configuration_json'])
    if (config.get('controller_identity') != expected['controller_identity']
            or config.get('solution_identity') != expected['solution_identity']):
        raise ValueError('full HDF5 resolved Controller or Solution identity mismatch')
    for step, transition in enumerate(transitions):
        record = transition['record']
        interval = transition['interval']
        if (interval.get('control_step') != step or interval.get('native_step_count') != 5
                or len(interval.get('substeps', [])) != 5):
            raise ValueError('full HDF5 interval lacks the five-native-step contract')
        if record.get('terminated') is True or record.get('truncated') is True:
            raise ValueError('full HDF5 terminated/truncated before the complete Expert stop')
        stage = record.get('expert_stage')
        for substep, row in enumerate(interval['substeps']):
            sample = row.get('native_feedback_sample_v1')
            if not isinstance(sample, dict):
                raise ValueError('full HDF5 lacks a typed native feedback sample')
            if sample.get('applied_acknowledgement') != row.get('applied'):
                raise ValueError('full HDF5 acknowledgement differs from applied control')
            force = sample['provider_feedback_sample']['actuator_force_measurement']
            native_index = step * 5 + substep
            phase = 'reset_forward' if native_index == 0 else 'native_step_pre_integration'
            if (force.get('valid') is not True or force.get('phase') != phase
                    or force.get('native_step_index') != native_index
                    or force.get('evaluation_control_step') != step
                    or force.get('sample_sequence') != sample.get('sample_sequence')):
                raise ValueError('full HDF5 native feedback validity/phase/index/sequence mismatch')
            evaluation_time = step * 0.01 + substep * 0.002
            sample_time = 0.0 if native_index == 0 else evaluation_time - 0.002
            if (abs(float(force['evaluation_simulation_time_s']) - evaluation_time) > 1e-10
                    or abs(float(force['native_sample_time_s']) - sample_time) > 1e-10
                    or abs(float(sample['evaluation_time_s']) - evaluation_time) > 1e-10
                    or abs(float(sample['sample_time_s']) - sample_time) > 1e-10):
                raise ValueError('full HDF5 native sample and evaluation clocks diverge')
            diagnostics = sample['controller_diagnostics']
            updated = diagnostics.get('inner_update_performed') is True
            should_update = law_hz == 500 or substep == 0
            if (updated is not should_update
                    or diagnostics.get('configured_inner_rate_hz') != law_hz
                    or abs(float(diagnostics.get('inner_update_period_s')) - (0.002 if law_hz == 500 else 0.01)) > 1e-12
                    or row.get('updated') is not should_update):
                raise ValueError('full HDF5 gripper law update/hold cadence mismatch')
            update_count += int(updated)
            hold_count += int(not updated)
            raw_force = float(force['signed_force_N'])
            if (not np.isfinite(raw_force) or force.get('force_unit') != 'N'
                    or force.get('actuator_id') != 'actuator8'
                    or sample.get('target_hash') != row['applied'].get('target_hash')
                    or row['applied'].get('provider_name') != 'geophys'
                    or sample.get('provider') != 'geophys'
                    or sample.get('task_artifact_hash') != expected['artifact_identity']
                    or sample.get('source_id') != expected['source_id']
                    or sample.get('source_xml_sha256') != expected['source_xml_sha256']
                    or sample.get('controller_identity') != expected['controller_identity']
                    or sample.get('solution_identity') != expected['solution_identity']
                    or sample.get('control_step') != step
                    or sample.get('substep_index') != substep
                    or sample.get('episode_id') != expected['episode_id']
                    or sample.get('reset_sample_id') != expected['reset_sample_id']
                    or sample.get('provider_materialization_id') != expected['provider_materialization_id']):
                raise ValueError('full HDF5 force/target/runtime identity mismatch')
            if abs(float(sample['feedback']['gripper']['closing_force_N']) - max(0.0, -raw_force)) > 1e-10:
                raise ValueError('full HDF5 raw and closing force disagree')
            all_samples.append(sample)
            if stage == 'close_gripper':
                close_samples.append(sample)

    if (len(all_samples) != total * 5
            or update_count != total * (5 if law_hz == 500 else 1)
            or hold_count != total * (0 if law_hz == 500 else 4)):
        raise ValueError('full HDF5 native sample or law update/hold count mismatch')
    auth = outcome.get('close_authorization')
    if not isinstance(auth, dict):
        raise ValueError('full HDF5 Outcome lacks Guard close authorization')
    if (auth.get('authorization_guard_id') not in {'primary_controller_close_ready', 'alternative_force_8n'}
            or auth.get('required_stable_duration_s') != 0.1
            or float(auth.get('observed_stable_duration_s', 0.0)) < 0.1 - 1e-10
            or int(auth.get('native_sample_count', 0)) < 50
            or float(auth['authorization_time_s']) > float(auth['transition_consumed_at_outer_boundary_s'])):
        raise ValueError('full HDF5 Guard authorization is outside the frozen policy')
    seq = int(auth['values']['native_sample_sequence'])
    count = int(auth['native_sample_count'])
    authorized = [sample for sample in close_samples
                  if seq - count + 1 <= int(sample['sample_sequence']) <= seq]
    if (len(authorized) != count
            or [int(s['sample_sequence']) for s in authorized] != list(range(seq - count + 1, seq + 1))
            or any(max(0.0, -float(s['provider_feedback_sample']['actuator_force_measurement']['signed_force_N'])) < 8.0
                   or s['controller_diagnostics'].get('force_mode_active') is not True
                   for s in authorized)):
        raise ValueError('full HDF5 Guard evidence lacks the continuous authorized native window')
    return {
        'transition_count': total, 'boundary_count': len(boundaries),
        'native_sample_count': len(all_samples), 'gripper_update_count': update_count,
        'gripper_hold_count': hold_count, 'guard_authorization': auth,
        'disk_outcome': outcome, 'stop_reason': value['stop_reason'],
        'closure_file_count': len(receipt['files']),
    }


def read(h5_path: Path, expected_path: Path, *, mode: str = 'short'):
    if mode not in {'short', 'full'}:
        raise ValueError(f'unsupported reader mode: {mode}')
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    with h5py.File(h5_path, 'r') as handle:
        if set(handle) != {'logical_json_utf8', 'control_step', 'native_step_index'}:
            raise ValueError('unexpected raw HDF5 dataset set')
        raw = handle['logical_json_utf8'][:].tobytes()
        value = json.loads(raw)
        if handle.attrs['logical_hash'] != _canonical_digest(value):
            raise ValueError('raw HDF5 logical_hash mismatch')
        transition_count = 2 if mode == 'short' else expected.get('transition_count')
        if type(transition_count) is not int or transition_count < 1:
            raise ValueError('raw HDF5 expected transition count is missing or invalid')
        if len(value['boundaries']) != transition_count + 1 or len(value['transitions']) != transition_count:
            raise ValueError('raw HDF5 T/T+1 structure mismatch')
        if not np.array_equal(handle['control_step'][:], np.arange(transition_count + 1, dtype=np.int64)):
            raise ValueError('raw HDF5 control_step projection mismatch')
        if not np.array_equal(handle['native_step_index'][:], np.arange(transition_count + 1, dtype=np.int64) * 5):
            raise ValueError('raw HDF5 native_step_index projection mismatch')

    metadata = value['metadata']
    provenance = metadata['source_provenance']
    receipt = json.loads(provenance['runtime_execution_source_receipt_json'])
    trusted = json.loads(TRUSTED_SOURCE_MANIFEST.read_text(encoding='utf-8'))
    if receipt['schema_version'] != 'runtime-execution-source-receipt-v1':
        raise ValueError('raw HDF5 source receipt version mismatch')
    if receipt['canonical_xml_sha256'] != CANONICAL_XML_SHA256:
        raise ValueError('raw HDF5 canonical source XML digest mismatch')
    if (trusted.get('schema_version') != 'r05b-trusted-execution-source-manifest-v1'
            or receipt['source_id'] != trusted['source_id']
            or receipt['canonical_xml_sha256'] != trusted['canonical_xml_sha256']
            or receipt['importer_xml_sha256'] != trusted['importer_xml_sha256']
            or receipt['files'] != trusted['files']
            or receipt['source_closure_digest'] != trusted['source_closure_digest']
            or _closure_digest(receipt['files']) != trusted['source_closure_digest']):
        raise ValueError('raw HDF5 source receipt differs from the trusted full source closure')
    identity_values = {
        'backend': metadata['execution']['backend'],
        'artifact_identity': metadata['task_artifact_hash'],
        'source_id': provenance['runtime_source_id'],
        'source_xml_sha256': provenance['runtime_source_xml_sha256'],
        'controller_identity': metadata['controller_identity'],
        'solution_identity': metadata['expert_identity'],
    }
    for name, expected_value in identity_values.items():
        if expected[name] != expected_value:
            raise ValueError(f'raw HDF5 {name} differs from the worker receipt')
    if receipt['source_id'] != identity_values['source_id']:
        raise ValueError('raw HDF5 receipt source label differs from runtime source label')
    if receipt['canonical_xml_sha256'] != identity_values['source_xml_sha256']:
        raise ValueError('raw HDF5 source XML digest differs from the execution receipt')
    config = json.loads(provenance['resolved_configuration_json'])
    if (config['runtime_config']['runtime']['backend'] != expected['backend']
            or config['gripper_control_hz'] != expected.get('gripper_control_hz', 500)
            or config['gripper_feedback_hz'] != 500):
        raise ValueError('raw HDF5 resolved profile/cadence mismatch')
    if mode == 'full':
        runtime = config['runtime_config']['runtime']
        artifact_timebase = config.get('artifact', {}).get('timebase', {})
        if (config.get('diagnostic_experiment') is not None
                or config.get('artifact', {}).get('artifact_id') !=
                'nut-assembly-square-v1/p1_8_e/nominal-v1'
                or runtime.get('integrator') != 'implicitfast'
                or runtime.get('physics_dt') != 0.002
                or runtime.get('control_substeps') != 5
                or artifact_timebase.get('control_dt') != 0.01
                or artifact_timebase.get('physics_dt') != 0.002
                or config.get('runtime_config', {}).get('render', {}).get('camera_obs') is not False
                or config.get('runtime_config', {}).get('render', {}).get('cameras') != []
                or identity_values['artifact_identity'] !=
                '99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe'
                or receipt.get('importer_xml_sha256') !=
                '16b19e020f843dfd11b0f2086da777426cd56e015d69c5363a97e5f86dc6dc17'
                or expected.get('provider_commit') != '67da1165149486d3ae3e779c13ce31af49e17d50'
                or expected.get('provider_import_origin') !=
                '/home/lly/.codex/worktrees/v210-integration/Geochora/GeoPhys/src/geophys/__init__.py'):
            raise ValueError('raw HDF5 is outside the frozen normal-profile source/build envelope')

    episode_ids = set()
    reset_ids = set()
    materialization_ids = set()
    sequence = []
    phases = []
    evaluation_times = []
    sample_times = []
    source_generations = set()
    state_revisions = []
    configuration_revisions = []
    native_indices = []
    for transition_index, transition in enumerate(value['transitions']):
        interval = transition['interval']
        if interval['control_step'] != transition_index or interval['native_step_count'] != 5:
            raise ValueError('raw HDF5 interval count/identity mismatch')
        rows = interval['substeps']
        if len(rows) != 5:
            raise ValueError('raw HDF5 interval lacks five native applications')
        for substep_index, row in enumerate(rows):
            sample = row.get('native_feedback_sample_v1')
            if not isinstance(sample, dict):
                raise ValueError('raw HDF5 is missing the native feedback sample')
            if sample['applied_acknowledgement'] != row['applied']:
                raise ValueError('raw HDF5 feedback acknowledgement differs from applied target')
            if sample['target_hash'] != row['applied']['target_hash']:
                raise ValueError('raw HDF5 target hash differs from its acknowledgement')
            provider_sample = sample['provider_feedback_sample']
            force = provider_sample['actuator_force_measurement']
            native_index = transition_index * 5 + substep_index
            expected_phase = (
                'reset_forward' if transition_index == 0 and substep_index == 0
                else 'native_step_pre_integration'
            )
            if not force['valid'] or force['phase'] != expected_phase:
                raise ValueError('raw HDF5 force sample validity/phase mismatch')
            if (force['native_step_index'] != native_index
                    or force['evaluation_control_step'] != transition_index
                    or force['sample_sequence'] != sample['sample_sequence']
                    or type(force['sample_sequence']) is not int
                    or force['sample_sequence'] < 1
                    or type(force['source_generation']) is not int
                    or type(force['state_revision']) is not int
                    or type(force['configuration_revision']) is not int):
                raise ValueError('raw HDF5 force sample generation/revision/index identity mismatch')
            eval_time = transition_index * 0.01 + substep_index * 0.002
            expected_sample_time = 0.0 if expected_phase == 'reset_forward' else eval_time - 0.002
            if (abs(float(force['evaluation_simulation_time_s']) - eval_time) > 1e-10
                    or abs(float(force['native_sample_time_s']) - expected_sample_time) > 1e-10):
                raise ValueError('raw HDF5 evaluation/sample clocks mismatch')
            raw_force = float(force['signed_force_N'])
            if (not np.isfinite(raw_force)
                    or not np.isfinite(float(force['actuator_ctrl']))
                    or force['actuator_id'] != 'actuator8'
                    or force['force_unit'] != 'N'
                    or force['invalid_reason'] is not None):
                raise ValueError('raw HDF5 force/control measurement is nonfinite or invalid')
            closing = float(sample['feedback']['gripper']['closing_force_N'])
            if abs(closing - max(0.0, -raw_force)) > 1e-10:
                raise ValueError('raw HDF5 raw/closing force mapping mismatch')
            episode_ids.add(sample['episode_id'])
            reset_ids.add(sample['reset_sample_id'])
            materialization_ids.add(sample['provider_materialization_id'])
            sequence.append(int(sample['sample_sequence']))
            phases.append(force['phase'])
            evaluation_times.append(float(force['evaluation_simulation_time_s']))
            sample_times.append(float(force['native_sample_time_s']))
            source_generations.add(force['source_generation'])
            state_revisions.append(force['state_revision'])
            configuration_revisions.append(force['configuration_revision'])
            native_indices.append(force['native_step_index'])

    if (len(sequence) != transition_count * 5
            or any(b != a + 1 for a, b in zip(sequence, sequence[1:]))
            or any(b != a + 1 for a, b in zip(native_indices, native_indices[1:]))
            or len(source_generations) != 1
            or any(b <= a for a, b in zip(state_revisions, state_revisions[1:]))
            or any(b < a for a, b in zip(configuration_revisions, configuration_revisions[1:]))):
        raise ValueError('raw HDF5 native sample sequence/generation/revision is incomplete or stale')
    if (episode_ids != {expected['episode_id']}
            or reset_ids != {expected['reset_sample_id']}
            or materialization_ids != {expected['provider_materialization_id']}):
        raise ValueError('raw HDF5 per-sample runtime identities mismatch')
    full = _validate_full_episode(value, expected, receipt) if mode == 'full' else None
    result = {
        'schema_version': 'r05b-independent-raw-h5-reader-v1',
        'result': 'PASS',
        'h5_sha256': hashlib.sha256(h5_path.read_bytes()).hexdigest(),
        'h5_size_bytes': h5_path.stat().st_size,
        'backend': expected['backend'],
        'artifact_identity': expected['artifact_identity'],
        'source_id': expected['source_id'],
        'canonical_xml_sha256': receipt['canonical_xml_sha256'],
        'source_closure_digest': receipt['source_closure_digest'],
        'closure_file_count': len(receipt['files']),
        'controller_identity': expected['controller_identity'],
        'solution_identity': expected['solution_identity'],
        'episode_id': expected['episode_id'],
        'reset_sample_id': expected['reset_sample_id'],
        'provider_materialization_id': expected['provider_materialization_id'],
        'boundary_count': len(value['boundaries']),
        'transition_count': len(value['transitions']),
        'native_sample_count': len(sequence),
        'sample_sequences': sequence,
        'source_generation': next(iter(source_generations)),
        'state_revisions': state_revisions,
        'configuration_revisions': configuration_revisions,
        'sample_phases': phases,
        'evaluation_times_s': evaluation_times,
        'native_sample_times_s': sample_times,
        'imports_task_env': False,
    }
    if full is not None:
        result.update(full)
        result['schema_version'] = 'r05c-independent-raw-full-h5-reader-v1'
        result['task_success'] = True
        result['strict_expert_complete'] = True
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--h5', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('short', 'full'), default='short')
    args = parser.parse_args()
    result = read(args.h5, args.expected, mode=args.mode)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
