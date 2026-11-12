"""H5 metadata carries declared fields without inventing legacy units."""
import os
from types import SimpleNamespace

import pytest

from task_env.recorders.h5 import _env_meta
from task_env.recorders import load_physical_recording_h5


def test_v3_preserves_declared_units_frame_and_clock_without_changing_v2():
    trajectory = SimpleNamespace(record_metadata={
        'env_metadata': {
            'action_schema': {'schema_id': 'test', 'components': ('torque',)},
            'observation_schema': {'leaf_specs': [{
                'path': 'state.position', 'semantic': 'joint angle',
                'unit': 'rad', 'frame': 'joint', 'time_reference': 'evaluation_boundary',
            }]},
        },
    }, reset_info={})
    leaves = [{'path': 'state/position', 'shape': [1], 'dtype': 'float32'},
              {'path': 'state/unknown', 'shape': [1], 'dtype': 'float32'}]
    actions = [{'name': 'torque', 'shape': [1], 'dtype': 'float32'}]
    v3 = _env_meta(trajectory, leaves, actions, h5_version='v3')['observation_schema']['state']['leaves']
    assert (v3['position']['unit'], v3['position']['frame'], v3['position']['time_reference']) == (
        'rad', 'joint', 'evaluation_boundary')
    assert 'unit' not in v3['unknown']
    v2 = _env_meta(trajectory, leaves, actions, h5_version='v2')['observation_schema']['state']['leaves']
    assert v2['position'] == {'shape': [1], 'dtype': 'float32', 'semantic': 'joint angle'}


def test_formal_pendulum_record_keeps_published_observation_metadata():
    path = os.environ.get('TASK_ENV_METADATA_RECORD')
    if not path:
        pytest.skip('explicit bounded native recording is required')
    record = load_physical_recording_h5(path)
    fields = record['env_meta']['observation_schema']
    state = fields['state']['leaves']['proprioception']
    image = fields['task_rgb']['leaves']['']
    assert (state['unit'], state['frame'], state['time_reference']) == (
        '1, 1, rad/s', 'pendulum_hinge joint coordinates', 'same_reset_or_step_boundary')
    assert (image['unit'], image['frame'], image['time_reference']) == (
        'normalized RGB [0,1]', 'camera pixel grid', 'same_reset_or_step_boundary')
