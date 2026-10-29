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


def read(h5_path: Path, expected_path: Path):
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    with h5py.File(h5_path, 'r') as handle:
        if set(handle) != {'logical_json_utf8', 'control_step', 'native_step_index'}:
            raise ValueError('unexpected raw HDF5 dataset set')
        raw = handle['logical_json_utf8'][:].tobytes()
        value = json.loads(raw)
        if handle.attrs['logical_hash'] != _canonical_digest(value):
            raise ValueError('raw HDF5 logical_hash mismatch')
        if len(value['boundaries']) != 3 or len(value['transitions']) != 2:
            raise ValueError('raw HDF5 does not contain exactly 3 boundaries / 2 transitions')
        if not np.array_equal(handle['control_step'][:], np.asarray([0, 1, 2], dtype=np.int64)):
            raise ValueError('raw HDF5 control_step projection mismatch')
        if not np.array_equal(handle['native_step_index'][:], np.asarray([0, 5, 10], dtype=np.int64)):
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
            or config['gripper_control_hz'] != 500
            or config['gripper_feedback_hz'] != 500):
        raise ValueError('raw HDF5 resolved profile/cadence mismatch')

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

    if (len(sequence) != 10 or any(b != a + 1 for a, b in zip(sequence, sequence[1:]))
            or any(b != a + 1 for a, b in zip(native_indices, native_indices[1:]))
            or len(source_generations) != 1
            or any(b <= a for a, b in zip(state_revisions, state_revisions[1:]))
            or any(b < a for a, b in zip(configuration_revisions, configuration_revisions[1:]))):
        raise ValueError('raw HDF5 native sample sequence/generation/revision is incomplete or stale')
    if (episode_ids != {expected['episode_id']}
            or reset_ids != {expected['reset_sample_id']}
            or materialization_ids != {expected['provider_materialization_id']}):
        raise ValueError('raw HDF5 per-sample runtime identities mismatch')
    return {
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--h5', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = read(args.h5, args.expected)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
