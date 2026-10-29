"""Provider-free contract tests for the R05c full normal-profile route."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from task_env.diagnostics.tasks import r05b_native_feedback_s2_worker as worker
from task_env.diagnostics.tasks import r05b_native_feedback_independent_reader as reader


ARTIFACT = '99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe'
SOURCE = 'nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1'
CANONICAL = '909759def6bbaa4c5644a100a36625400464cd571dcab1222f807efaaf1c225d'
IMPORTER = '16b19e020f843dfd11b0f2086da777426cd56e015d69c5363a97e5f86dc6dc17'
PROVIDER = 'c6df840bef8d36b1150150167df08e29dc3f664c'
CONTROLLER = 'controller-synthetic-r3'
SOLUTION = 'solution-synthetic-na-s0'
EPISODE = 'episode-synthetic-full'
RESET = 'reset-synthetic-full'
MATERIALIZATION = 'geophys-materialization-synthetic-full'


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode()).hexdigest()


def _full_value(law_hz=100, transitions=12):
    trusted = json.loads(reader.TRUSTED_SOURCE_MANIFEST.read_text())
    blobs = {}
    outcome = {
        'task_success': True, 'planned_trajectory_completed': True, 'outcome_complete': True,
        'original_expert_lifecycle_status': {'expert_complete': True, 'expert_failed': False},
        'readiness_warnings': [], 'runtime_error': None, 'unapproved_override_used': False,
        'control_step': transitions,
        'close_authorization': {
            'authorization_guard_id': 'alternative_force_8n',
            'required_stable_duration_s': 0.1, 'observed_stable_duration_s': 0.1,
            'native_sample_count': 50, 'authorization_time_s': 0.1,
            'transition_consumed_at_outer_boundary_s': 0.11,
            'values': {'native_sample_sequence': transitions * 5},
        },
    }
    outcome_hash = _digest(outcome)
    blobs[outcome_hash] = outcome
    boundaries = []
    for i in range(transitions + 1):
        boundaries.append({
            'record': {'control_step': i, 'simulation_time': i * 0.01,
                       'state': {'control_step': i, 'simulation_time': i * 0.01}},
            'native_step_index': i * 5,
            'owners': {'owners': {'coordinator': {'fields': {
                'task_outcome': {'value': {'kind': 'content-ref', 'sha256': outcome_hash}},
            }}}},
        })
    rows_by_step = []
    for step in range(transitions):
        rows = []
        for substep in range(5):
            native_index = step * 5 + substep
            sequence = native_index + 1
            evaluation = step * 0.01 + substep * 0.002
            sample_time = 0.0 if native_index == 0 else evaluation - 0.002
            phase = 'reset_forward' if native_index == 0 else 'native_step_pre_integration'
            target_hash = f'target-{sequence}'
            update = law_hz == 500 or substep == 0
            applied = {'target_hash': target_hash, 'provider_name': 'geophys'}
            force = {
                'valid': True, 'phase': phase, 'native_step_index': native_index,
                'evaluation_control_step': step, 'sample_sequence': sequence,
                'source_generation': 1, 'state_revision': native_index + 1,
                'configuration_revision': 1, 'evaluation_simulation_time_s': evaluation,
                'native_sample_time_s': sample_time, 'signed_force_N': -9.0,
                'actuator_ctrl': 12.0, 'actuator_id': 'actuator8', 'force_unit': 'N',
                'invalid_reason': None,
            }
            sample = {
                'applied_acknowledgement': applied, 'target_hash': target_hash,
                'provider': 'geophys', 'task_artifact_hash': ARTIFACT,
                'source_id': SOURCE, 'source_xml_sha256': CANONICAL,
                'controller_identity': CONTROLLER, 'solution_identity': SOLUTION,
                'control_step': step, 'substep_index': substep,
                'provider_feedback_sample': {'actuator_force_measurement': force},
                'sample_sequence': sequence, 'episode_id': EPISODE,
                'reset_sample_id': RESET, 'provider_materialization_id': MATERIALIZATION,
                'evaluation_time_s': evaluation, 'sample_time_s': sample_time,
                'controller_diagnostics': {
                    'inner_update_performed': update,
                    'configured_inner_rate_hz': law_hz,
                    'inner_update_period_s': 0.002 if law_hz == 500 else 0.01,
                    'force_mode_active': True,
                },
                'feedback': {'gripper': {'closing_force_N': 9.0}},
            }
            rows.append({'applied': applied, 'native_feedback_sample_v1': sample,
                         'updated': update})
        rows_by_step.append({
            'record': {'expert_stage': 'close_gripper', 'terminated': False, 'truncated': False},
            'interval': {'control_step': step, 'native_step_count': 5, 'substeps': rows},
        })
    files = trusted['files']
    receipt = {
        'schema_version': 'runtime-execution-source-receipt-v1', 'source_id': SOURCE,
        'canonical_xml_sha256': CANONICAL, 'importer_xml_sha256': IMPORTER,
        'files': files, 'source_closure_digest': trusted['source_closure_digest'],
    }
    config = {
        'runtime_config': {
            'runtime': {'backend': 'cpu', 'integrator': 'implicitfast',
                        'physics_dt': 0.002, 'control_substeps': 5},
            'render': {'camera_obs': False, 'cameras': []},
        },
        'gripper_control_hz': law_hz, 'gripper_feedback_hz': 500,
        'controller_identity': CONTROLLER, 'solution_identity': SOLUTION,
        'diagnostic_experiment': None,
        'artifact': {'artifact_id': 'nut-assembly-square-v1/p1_8_e/nominal-v1',
                     'timebase': {'control_dt': 0.01, 'physics_dt': 0.002}},
    }
    value = {
        'schema': 'canonical-execution-trajectory-v2',
        'metadata': {
            'execution': {'backend': 'cpu', 'physics_provider': 'geophys'},
            'task_artifact_hash': ARTIFACT, 'controller_identity': CONTROLLER,
            'expert_identity': SOLUTION,
            'source_provenance': {
                'runtime_source_id': SOURCE, 'runtime_source_xml_sha256': CANONICAL,
                'runtime_execution_source_receipt_json': json.dumps(receipt, sort_keys=True),
                'resolved_configuration_json': json.dumps(config, sort_keys=True),
            },
        },
        'recipe': {}, 'boundaries': boundaries, 'transitions': rows_by_step,
        'blobs': blobs, 'stop_reason': 'nutassembly-external-expert-complete',
    }
    return value, receipt


def _write_h5(path, value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    with h5py.File(path, 'w') as handle:
        handle.create_dataset('logical_json_utf8', data=np.frombuffer(raw, dtype=np.uint8))
        handle.create_dataset('control_step', data=np.arange(len(value['boundaries']), dtype=np.int64))
        handle.create_dataset('native_step_index', data=np.arange(len(value['boundaries']), dtype=np.int64) * 5)
        handle.attrs['logical_hash'] = _digest(value)


def _reader_input(tmp_path, value, law_hz=100):
    h5 = tmp_path / 'synthetic-full.h5'
    expected = tmp_path / 'expected.json'
    _write_h5(h5, value)
    expected.write_text(json.dumps({
        'backend': 'cpu', 'artifact_identity': ARTIFACT, 'source_id': SOURCE,
        'source_xml_sha256': CANONICAL, 'controller_identity': CONTROLLER,
        'solution_identity': SOLUTION, 'episode_id': EPISODE, 'reset_sample_id': RESET,
        'provider_materialization_id': MATERIALIZATION, 'transition_count': len(value['transitions']),
        'gripper_control_hz': law_hz, 'require_task_success': True, 'provider_commit': PROVIDER,
        'provider_import_origin': '/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora/GeoPhys/src/geophys/__init__.py',
    }))
    return h5, expected


def test_full_worker_route_selects_real_normal_profile_owner(monkeypatch, tmp_path):
    called = {}
    from task_env.diagnostics.tasks import c05c_geophys_gripper_cadence as owner

    def fake_run(backend, law, output, *, profile):
        called.update(backend=backend, law=law, output=output, profile=profile)
        return {'status': 'synthetic-route-dispatch'}

    monkeypatch.setattr(owner, 'run_group', fake_run)
    result = worker.run('cuda', tmp_path / 'run', gripper_hz=100, full_episode=True)
    assert result['status'] == 'synthetic-route-dispatch'
    assert called == {'backend': 'cuda', 'law': 100, 'output': tmp_path / 'run', 'profile': 'normal'}


@pytest.mark.parametrize('law_hz,expected_updates,expected_holds', [(100, 12, 48), (500, 60, 0)])
def test_independent_full_reader_accepts_complete_synthetic_episode(
        tmp_path, law_hz, expected_updates, expected_holds):
    value, _ = _full_value(law_hz=law_hz)
    h5, expected = _reader_input(tmp_path, value, law_hz)
    result = reader.read(h5, expected, mode='full')
    assert result['result'] == 'PASS'
    assert result['transition_count'] == 12 and result['boundary_count'] == 13
    assert result['native_sample_count'] == 60
    assert result['gripper_update_count'] == expected_updates
    assert result['gripper_hold_count'] == expected_holds
    assert result['strict_expert_complete'] is True


def test_independent_full_reader_rejects_guard_gap_and_outcome_failure(tmp_path):
    value, _ = _full_value()
    value['transitions'][3]['record']['expert_stage'] = 'lift_nut'
    h5, expected = _reader_input(tmp_path, value)
    with pytest.raises(ValueError, match='continuous authorized native window'):
        reader.read(h5, expected, mode='full')

    failed, _ = _full_value()
    ref = failed['boundaries'][-1]['owners']['owners']['coordinator']['fields']['task_outcome']['value']['sha256']
    failed['blobs'][ref]['task_success'] = False
    h5, expected = _reader_input(tmp_path, failed)
    with pytest.raises(ValueError, match='disk Outcome or strict Expert lifecycle'):
        reader.read(h5, expected, mode='full')


def test_independent_full_reader_rejects_identity_projection_and_hash_tampering(tmp_path):
    value, _ = _full_value()
    h5, expected = _reader_input(tmp_path, value)
    wrong = json.loads(expected.read_text())
    wrong['episode_id'] = 'wrong-episode'
    expected.write_text(json.dumps(wrong))
    with pytest.raises(ValueError, match='runtime identities mismatch'):
        reader.read(h5, expected, mode='full')

    value, _ = _full_value()
    h5, expected = _reader_input(tmp_path, value)
    with h5py.File(h5, 'a') as handle:
        handle.attrs['logical_hash'] = '0' * 64
    with pytest.raises(ValueError, match='logical_hash mismatch'):
        reader.read(h5, expected, mode='full')


def test_independent_full_reader_rejects_t_plus_one_projection_and_wrong_law(tmp_path):
    value, _ = _full_value()
    value['boundaries'].pop()
    h5, expected = _reader_input(tmp_path, value)
    with pytest.raises(ValueError, match=r'T/T\+1 structure mismatch'):
        reader.read(h5, expected, mode='full')

    value, _ = _full_value()
    h5, expected = _reader_input(tmp_path, value)
    with h5py.File(h5, 'a') as handle:
        handle['native_step_index'][-1] = -1
    with pytest.raises(ValueError, match='projection mismatch'):
        reader.read(h5, expected, mode='full')

    value, _ = _full_value(law_hz=100)
    h5, expected = _reader_input(tmp_path, value, law_hz=500)
    with pytest.raises(ValueError, match='resolved profile/cadence mismatch'):
        reader.read(h5, expected, mode='full')
