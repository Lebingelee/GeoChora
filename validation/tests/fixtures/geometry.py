"""Independent geometry factories; no reference labels or model calls."""
from copy import deepcopy
from itertools import product
import numpy as np


def mesh(bounds):
    lo, hi = np.asarray(bounds)
    v = list(product(*zip(lo, hi)))
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return {'vertices_m': v, 'triangles': [[q[0], q[1], q[2]] for q in quads] + [[q[0], q[2], q[3]] for q in quads]}


def fixture():
    bounds = [[-.04, -.02, 0], [.04, .02, .02]]
    rigid = {'pieces': [mesh(bounds)], 'geometric_center_local_m': [0, 0, .01],
             'bounds_local_m': bounds, 'long_axis_local': [1, 0, 0], 'width_m': .04}
    geometry = {'units': 'm', 'quaternion_order': 'wxyz', 'table_bounds_world_m': [[-1, -1, -.1], [1, 1, 0]],
        'spheres': {'ball': {'radius_m': .02}, 'other': {'radius_m': .02}},
        'containers': {'drawer': {'closed_origin_world_m': [0, .5, .1], 'closed_orientation_wxyz': [1, 0, 0, 0],
            'opening_axis_world': [0, -1, 0], 'cavity_bounds_local_m': [[-.1, -.1, 0], [.1, .1, .1]]}},
        'gripper_enclosing_radii_m': {'hand': .1}, 'rigids': {n: deepcopy(rigid) for n in ['a', 'b', 'c']}}
    positions = {'ball': [0, .5, .12], 'other': [.5, .5, .02], 'drawer': [0, .5, .1],
                 'a': [0, 0, 0], 'b': [0, 0, .02], 'c': [.3, 0, 0], 'hand': [5, 5, 5]}
    rotations = {n: [1, 0, 0, 0] for n in positions}
    return geometry, positions, rotations
