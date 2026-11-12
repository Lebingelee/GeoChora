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
