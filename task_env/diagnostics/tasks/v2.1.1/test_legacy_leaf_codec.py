"""Read historical leaf records without native SDK and retain strict old judge."""
from pathlib import Path
import runpy
import shutil

import h5py
import pytest

from task_env.recorders import load_legacy_leaf_control_h5

ROOT = Path(__file__).resolve().parents[4]
RUNS = ROOT / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001'
JUDGE = Path(__file__).with_name('legacy_leaf_judge.py')


@pytest.mark.parametrize('relative', ['r02c_005/native_run_001/E3-simultaneous-default.h5',
                                     'r03c_004/native/E3.h5'])
def test_old_leaf_h5_decodes_and_old_judge_remains_strict(relative, tmp_path):
    source = RUNS / relative
    generic = load_legacy_leaf_control_h5(source)
    assert generic['transition_count'] == 64 and generic['observation_count'] == 65
    assert generic['observations']['state']['boundary_identity_sha256'].shape == (65, 32)
    judge = runpy.run_path(str(JUDGE))['load_leaf_control_records_h5']
    strict = judge(source)
    assert strict['transition_count'] == 64 and strict['leaf_profile']['profile_id']
    tampered = tmp_path / 'tampered.h5'
    shutil.copyfile(source, tampered)
    with h5py.File(tampered, 'r+') as root:
        values = root['obs/state/boundary_identity_sha256']
        values[1, 0] = int(values[1, 0]) ^ 1
    # Decoding and experimental assessment are distinct claims: the latter
    # must still catch a forged state boundary.
    with pytest.raises(ValueError):
        judge(tampered)


_COMMON_TAMPERS = (
    'target_identity', 'ack_writer', 'prepared_command', 'source_digest',
    'configuration_identity', 'missing_writer', 'duplicate_slot',
    'boundary_observation', 't_plus_one', 'control_clock',
)
_ATTACHMENT_TAMPERS = ('attachment_plan_hash', 'entity_binding', 'native_tcp')


@pytest.mark.parametrize('relative,case', [
    *[(relative, case) for relative in (
        'r02c_005/native_run_001/E3-simultaneous-default.h5',
        'r03c_004/native/E3.h5',
    ) for case in _COMMON_TAMPERS],
    *[('r03c_004/native/E3.h5', case) for case in _ATTACHMENT_TAMPERS],
])
def test_historical_judge_rejects_tampered_control_and_metadata(relative, case, tmp_path):
    """Preserve the R02c/R03c negative matrix against copies, never original H5."""
    import json
    from task_env.trajectory.metadata import dump_metadata, load_metadata

    attachment_cases = {'attachment_plan_hash', 'entity_binding', 'native_tcp'}
    source = RUNS / relative
    destination = tmp_path / (case + '.h5')
    shutil.copyfile(source, destination)
    with h5py.File(destination, 'r+') as root:
        if case == 'boundary_observation':
            values = root['obs/state/boundary_identity_sha256']
            values[1, 0] = (int(values[1, 0]) + 1) % 256
        elif case == 't_plus_one':
            root.attrs['observation_count'] = 64
        elif case in attachment_cases or case == 'control_clock':
            raw = root['meta/env_meta'][()]
            metadata = load_metadata(raw.decode('utf-8') if isinstance(raw, bytes) else str(raw))
            profile = metadata['reference_profile']
            if case == 'control_clock':
                profile['control_dt_s'] = 0.02
            elif case == 'attachment_plan_hash':
                profile['attachment_plan_identity_sha256'] = '0' * 64
            elif case == 'entity_binding':
                profile['writers'][0]['entity_id'] = 'panda-secondary'
            else:
                profile['attachment_receipt']['native_body_mappings']['panda-hand/hand']['native_name'] = 'hand'
            del root['meta/env_meta']
            root.create_dataset('meta/env_meta', data=dump_metadata(metadata),
                                dtype=h5py.string_dtype(encoding='utf-8'))
        else:
            raw = root['meta/structured_controls_v1_json'][()]
            controls = json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else str(raw))
            writers = controls[0]['writer_controls']
            first = writers[0]
            if case == 'target_identity':
                first['controller_target']['identity_hash'] = '0' * 64
            elif case == 'ack_writer':
                first['canonical_action']['application_ack']['writer_id'] = 'tampered-writer'
            elif case == 'prepared_command':
                first['canonical_action']['prepared_command']['slot_values'][0]['value'] = 999.0
            elif case == 'source_digest':
                first['canonical_action']['source_closure_sha256'] = '0' * 64
            elif case == 'configuration_identity':
                first['canonical_action']['configuration_identity_sha256'] = '0' * 64
            elif case == 'missing_writer':
                writers.pop()
            elif case == 'duplicate_slot':
                slot = first['canonical_action']['prepared_command']['slot_values'][0]['ctrl_slot']
                writers[1]['applied_control']['payload']['applied_slots'] = [slot]
            else:
                raise AssertionError(f'unknown tamper case: {case}')
            del root['meta/structured_controls_v1_json']
            root.create_dataset('meta/structured_controls_v1_json', data=json.dumps(controls, sort_keys=True),
                                dtype=h5py.string_dtype(encoding='utf-8'))
    judge = runpy.run_path(str(JUDGE))['load_leaf_control_records_h5']
    with pytest.raises((ValueError, TypeError, KeyError)):
        judge(destination)
