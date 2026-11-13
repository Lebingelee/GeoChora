"""CPU-only mass-center checks for the bounded MJCF tracking-light path."""
import numpy as np
import pytest

from task_env.runtime.sessions.geophys import _rest_center_of_mass, _world_center_of_mass


def test_world_com_rotates_inertial_offsets_and_weights_mass():
    bodies = [{'name': 'a', 'mass_kg': 1., 'com_body_m': [1., 0., 0.]},
              {'name': 'b', 'mass_kg': 3., 'com_body_m': [0., 0., 0.]}]
    q = np.sqrt(.5)
    result = _world_center_of_mass(bodies, {'a': 0, 'b': 1},
                                   [[0, 0, 0], [2, 0, 0]],
                                   [[q, 0, 0, q], [1, 0, 0, 0]])
    assert np.allclose(result, [1.5, .25, 0.])
    with pytest.raises(ValueError, match='every compiled body'):
        _world_center_of_mass(bodies, {'a': 0}, [[0, 0, 0]], [[1, 0, 0, 0]])


def test_rest_com_uses_hierarchy_and_rejects_nonzero_joint():
    bodies = [{'name': 'a', 'mass_kg': 1., 'com_body_m': [0., 0., 0.]},
              {'name': 'b', 'mass_kg': 1., 'com_body_m': [0., 0., 0.]}]
    q = np.sqrt(.5)
    data = {'body_parentid': [-1, 0], 'body_pos': [[0, 0, 0], [1, 0, 0]],
            'body_quat': [[q, 0, 0, q], [1, 0, 0, 0]], 'initial_qpos': [0.],
            'jnt_type': [2], 'jnt_qposadr': [0], 'body_jntnum': [0, 1],
            'body_jntadr': [0, 0]}
    assert np.allclose(_rest_center_of_mass(bodies, {'a': 0, 'b': 1}, data), [0, .5, 0])
    data['initial_qpos'] = [.1]
    with pytest.raises(ValueError, match='zero scalar'):
        _rest_center_of_mass(bodies, {'a': 0, 'b': 1}, data)
