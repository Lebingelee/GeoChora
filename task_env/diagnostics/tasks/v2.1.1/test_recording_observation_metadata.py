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


@pytest.mark.parametrize('semantic', ['measured tool pose', 'Nut tool pose', 'custom task tool pose'])
def test_physical_metadata_preserves_declared_pose_semantic(semantic):
    import numpy as np
    from task_env.environment.gym_compat import Box, Dict
    from task_env.environment.types import ObservationFieldSpec, ObservationSchema
    from task_env.recorders.physical_metadata import physical_record_metadata

    schema = ObservationSchema('declared-tool-v1', (ObservationFieldSpec(
        'state.ee_pose', (7,), 'float32', semantic, 'm + unit quaternion', 'world'),),
        groups=('state',))
    env = SimpleNamespace(
        binding=SimpleNamespace(robot=None, object_poses=(), observation_metadata=None,
            task_observation_schema=schema, action_schema={'mode': 'effort', 'components': ('torque',),
                'schema_id': 'declared-action-v1', 'schema_version': 'v1'}),
        observation_space=Dict({'state': Dict({'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32)})}),
        obs={'state': {'ee_pose': np.array([0., 0., 0., 1., 0., 0., 0.], dtype=np.float32)}},
        artifact=SimpleNamespace(task_id='declared-task', artifact_version='v1', identity_hash='artifact',
            timebase=SimpleNamespace(physics_dt=.002, control_substeps=5, control_dt=.01)),
        value={'source': SimpleNamespace(source_closure_digest='closure'),
               'reset_plan': SimpleNamespace(identity_hash='plan', reset_sample=SimpleNamespace(sample_id='reset'))},
        provider='mujoco', backend='cpu', horizon=3, get_execution_receipt=lambda: {})
    env._physical_execution = lambda: SimpleNamespace(
        scene=SimpleNamespace(scene_id='scene', identity_hash='scene-hash'), subjects=(),
        compiled=SimpleNamespace(binding=SimpleNamespace(identity_hash='binding')))
    metadata = physical_record_metadata(env)
    leaf = metadata['env_metadata']['observation_schema']['leaf_specs'][0]
    assert (leaf['semantic'], leaf['unit'], leaf['frame']) == (semantic, 'm + unit quaternion', 'world')
    recorded = _env_meta(SimpleNamespace(record_metadata=metadata, reset_info={}),
        [{'path': 'state/ee_pose', 'shape': [7], 'dtype': 'float32'}],
        [{'name': 'torque', 'shape': [1], 'dtype': 'float32'}], h5_version='v3')
    assert recorded['observation_schema']['state']['leaves']['ee_pose']['semantic'] == semantic
