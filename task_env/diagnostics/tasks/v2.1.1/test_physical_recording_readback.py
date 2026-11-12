"""Offline readback of explicitly supplied, bounded real physical episodes."""
import json
import os
from pathlib import Path
import shutil

import h5py
import numpy as np
import pytest

from task_env.recorders import load_physical_recording_h5


@pytest.mark.parametrize('name,dimension,rgb', [
    ('pendulum-rgb', 1, True), ('two-wheel', 2, False), ('panda-rgb', 8, True),
])
def test_real_physical_record_and_boundary_tamper(name, dimension, rgb, tmp_path):
    directory = os.environ.get('TASK_ENV_PHYSICAL_RECORDINGS')
    if not directory:
        pytest.skip('explicit bounded native recording directory is required')
    path = Path(directory) / name / 'episode.h5'
    data = load_physical_recording_h5(path)
    assert (data['transition_count'], data['observation_count']) == (1, 2)
    assert len(data['actions'][0]) == dimension
    assert len(data['observations']['state']) > 0
    assert data['clocks'][1].simulation_time_s > data['clocks'][0].simulation_time_s
    assert data['outcome'].end_reason == 'external_stop'
    assert len(data['task_rgb_captures']) == (2 if rgb else 0)
    if rgb:
        assert data['observations']['task_rgb'].shape == (2, 48, 64, 3)
        assert np.isfinite(data['observations']['task_rgb']).all()
    tampered = tmp_path / 'wrong-clock.h5'
    shutil.copyfile(path, tampered)
    with h5py.File(tampered, 'r+') as handle:
        dataset = handle['meta/boundary_context_v1_json']
        contexts = json.loads(dataset.asstr()[()])
        contexts[0]['state_sample_clock']['simulation_time_s'] += 1
        dataset[()] = json.dumps(contexts)
    with pytest.raises(ValueError):
        load_physical_recording_h5(tampered)
