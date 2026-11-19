"""Analytic counterexamples, not simulated-trajectory success labels."""

from validation.tests.fixtures.geometry import mesh, fixture
import math

import numpy as np
import pytest

from validation.terminal import TerminalPolicy, TerminalScene
from validation.geometry import ConvexPiece, box_piece, separation


def scene(g, p, q):
    return TerminalScene(geometry=g, positions=p, orientations_wxyz=q)


@pytest.mark.parametrize('height,expected', [(0, True), (.0005, True), (.002, None), (.01, False), (-.01, False)])
def test_support_contact_hover_boundary_and_penetration(height, expected):
    g, p, q = fixture()
    p['a'][2] = height
    assert scene(g, p, q).supported('a')['value'] is expected


def test_stacking_uses_actual_collision_faces_not_outer_aabb():
    g, p, q = fixture()
    # Lower has two tall studs; upper hollow sides rest on the lower roof.
    # Their enclosing boxes overlap by 1 cm, but actual pieces only touch.
    g['rigids']['a']['pieces'] += [mesh([[-.01, -.01, .02], [.01, .01, .03]])]
    g['rigids']['b']['pieces'] = [mesh([[-.04, -.02, 0], [.04, -.015, .02]]),
        mesh([[-.04, .015, 0], [.04, .02, .02]]), mesh([[-.04, -.02, .015], [.04, .02, .02]])]
    result = scene(g, p, q).supported('b', 'a')
    assert result['value'] is True
    assert result['measurements']['penetration_m'] < 1e-10


def test_support_allows_partial_overhang_but_not_center_outside():
    g, p, q = fixture()
    p['b'][0] = .02
    assert scene(g, p, q).supported('b', 'a')['value'] is True
    p['b'][0] = .06
    assert scene(g, p, q).supported('b', 'a')['value'] is False


def test_missing_or_invalid_rigid_pose_is_unknown():
    g, p, q = fixture()
    q['a'] = [2, 0, 0, 0]
    assert scene(g, p, q).supported('a')['value'] is None
    del p['ball']
    assert scene(g, p, q).sphere_inside('ball', 'drawer')['value'] is None


def test_whole_sphere_and_container_local_frame():
    g, p, q = fixture()
    assert scene(g, p, q).sphere_inside('ball', 'drawer')['value'] is True
    p['ball'] = [.095, .5, .14]  # center inside, sphere crosses the wall
    assert scene(g, p, q).sphere_inside('ball', 'drawer')['value'] is False
    # Rotate both frame and ball by 90 degrees about the drawer origin.
    q['drawer'] = [math.sqrt(.5), 0, 0, math.sqrt(.5)]
    p['ball'] = [0, .595, .14]
    assert scene(g, p, q).sphere_inside('ball', 'drawer')['value'] is False


def test_enclosing_sphere_overlap_cannot_prove_held():
    g, p, q = fixture()
    assert scene(g, p, q).released('ball')['value'] is True
    p['hand'] = p['ball']
    result = scene(g, p, q).released('ball')
    assert result['value'] is None
    assert 'not_proof_of_grasp' in result['reason']


def test_drawer_lateral_displacement_rotation_and_clearance():
    g, p, q = fixture()
    p['drawer'][1] -= .1
    assert scene(g, p, q).drawer_state('drawer', required_opening_m=.04)['value'] is True
    p['drawer'][0] += .02
    assert scene(g, p, q).drawer_state('drawer', required_opening_m=.04)['value'] is False
    p['drawer'][0] = 0
    q['drawer'] = [math.sqrt(.5), 0, 0, math.sqrt(.5)]
    assert scene(g, p, q).drawer_state('drawer', required_opening_m=.04)['value'] is False


def row_fixture():
    g, p, q = fixture()
    p.update(a=[-.3, -.3, 0], b=[0, 0, 0], c=[.5, .5, 0])
    q['c'] = [0, 0, 0, 1]  # opposite direction is the same unoriented long axis
    return g, p, q


def test_diagonal_unequally_spaced_parallel_row():
    g, p, q = row_fixture()
    assert scene(g, p, q).parallel_row(['a', 'b', 'c'])['value'] is True


@pytest.mark.parametrize('angle,expected', [(1, True), (5, None), (20, False)])
def test_parallel_angle_bands(angle, expected):
    g, p, q = row_fixture()
    theta = math.radians(angle) / 2
    q['b'] = [math.cos(theta), 0, 0, math.sin(theta)]
    assert scene(g, p, q).parallel_row(['a', 'b', 'c'])['value'] is expected


def test_parallel_but_not_a_row_and_overlapping_objects():
    g, p, q = row_fixture()
    p['b'] = [0, .3, 0]
    assert scene(g, p, q).parallel_row(['a', 'b', 'c'])['value'] is False
    p['b'] = p['a']
    assert scene(g, p, q).parallel_row(['a', 'b', 'c'])['value'] is False


def test_translation_and_object_renaming_invariance():
    g, p, q = fixture()
    before = scene(g, p, q).supported('b', 'a')['value']
    offset = np.array([8, -5, 2])
    p = {n: (np.asarray(v) + offset).tolist() for n, v in p.items()}
    g['table_bounds_world_m'] = (np.asarray(g['table_bounds_world_m']) + offset).tolist()
    g['rigids']['renamed'] = g['rigids'].pop('b')
    p['renamed'], q['renamed'] = p.pop('b'), q.pop('b')
    assert scene(g, p, q).supported('renamed', 'a')['value'] is before is True


def test_scalar_cavity_bounds_do_not_broadcast_into_an_invented_volume():
    g, p, q = fixture()
    g['containers']['drawer']['cavity_bounds_local_m'] = [0, 1]
    p['drawer'], p['ball'] = [0, 0, 0], [.5, .5, .5]
    with pytest.raises(ValueError, match='cavity'):
        scene(g, p, q).sphere_inside('ball', 'drawer')


@pytest.mark.parametrize('offset_x', [0, .01])
def test_vertical_layers_are_not_a_separated_horizontal_row(offset_x):
    g, p, q = fixture()
    p.update(a=[0, 0, 0], b=[offset_x, 0, .1], c=[2 * offset_x, 0, .2])
    # Horizontal projections overlap, although the 3-D bodies have clear gaps.
    assert scene(g, p, q).parallel_row(['a', 'b', 'c'])['value'] is False


def test_concentric_nonintersecting_frames_do_not_define_a_row():
    g, p, q = fixture()
    for name, x, y, thickness in [('a', .15, .05, .005), ('b', .10, .03, .005), ('c', .05, .01, .003)]:
        g['rigids'][name] = {
            'pieces': [mesh([[-x, -y, 0], [x, -y + thickness, .02]]),
                       mesh([[-x, y - thickness, 0], [x, y, .02]]),
                       mesh([[-x, -y + thickness, 0], [-x + thickness, y - thickness, .02]]),
                       mesh([[x - thickness, -y + thickness, 0], [x, y - thickness, .02]])],
            'geometric_center_local_m': [0, 0, .01], 'long_axis_local': [1, 0, 0], 'width_m': 2 * y,
        }
        p[name] = [0, 0, 0]
    result = scene(g, p, q).parallel_row(['a', 'b', 'c'])
    assert result['value'] is None
    assert result['reason'] == 'horizontal_row_centers_not_distinct'


def test_low_platform_can_support_an_object_below_its_own_overall_center():
    g, p, q = fixture()
    g['table_bounds_world_m'] = [[-1, -1, -.1], [1, 1, -.02]]
    g['rigids']['a'] = {
        'pieces': [mesh([[-.1, -.1, -.02], [.1, .1, 0]]),
                   mesh([[.08, -.02, 0], [.1, .02, 1]])],
        'geometric_center_local_m': [.045, 0, .245],
    }
    g['rigids']['b'] = {
        'pieces': [mesh([[-.02, -.02, 0], [.02, .02, .04]])],
        'geometric_center_local_m': [0, 0, .02],
    }
    p['a'] = p['b'] = [0, 0, 0]
    assert scene(g, p, q).supported('b', 'a')['value'] is True


def test_an_object_cannot_be_its_own_support_even_inside_distance_tolerance():
    g, p, q = fixture()
    g['rigids']['a']['pieces'] = [mesh([[-.04, -.02, 0], [.04, .02, .0005]])]
    g['rigids']['a']['geometric_center_local_m'] = [0, 0, .00025]
    with pytest.raises(ValueError, match='distinct'):
        scene(g, p, q).supported('a', 'a')


def test_scene_owns_snapshot_inputs_even_after_collision_pieces_are_cached():
    g, p, q = fixture()
    observed = scene(g, p, q)
    assert observed.supported('a')['value'] is True
    p['a'][2] = 1
    q['a'][:] = [0, 1, 0, 0]
    g['rigids']['a']['geometric_center_local_m'][0] = 10
    assert observed.position('a').tolist() == [0, 0, 0]
    assert observed.supported('a')['value'] is True
    assert scene(g, p, q).supported('a')['value'] is False


def test_mesh_validation_and_sat_rotated_boxes():
    m = mesh([[-1, -1, -1], [1, 1, 1]])
    with pytest.raises(ValueError, match='closed'):
        ConvexPiece.from_mesh(m['vertices_m'], m['triangles'][:-1])
    a = box_piece([[-1, -1, -1], [1, 1, 1]])
    b = a.transformed(np.eye(3), np.array([3, 0, 0]))
    assert separation(a, b) == pytest.approx(1)
    assert separation(a, a) == pytest.approx(-2)


def test_duplicate_open_faces_cannot_masquerade_as_closed_support():
    # Every edge occurs twice, but these are only two duplicated open triangles.
    vertices = [[-.04, -.02, 0], [-.04, -.02, .02], [.04, -.02, 0],
                [.04, -.02, .02], [0, .02, 0], [0, .02, .02]]
    triangles = [[0, 2, 4], [0, 2, 4], [1, 3, 5], [1, 3, 5]]
    with pytest.raises(ValueError, match='duplicate'):
        ConvexPiece.from_mesh(vertices, triangles)
    triangles[1] = [4, 2, 0]
    with pytest.raises(ValueError, match='duplicate'):
        ConvexPiece.from_mesh(vertices, triangles)


def test_disconnected_duplicate_shell_is_rejected():
    m = mesh([[-1, -1, -1], [1, 1, 1]])
    vertices = np.concatenate([m['vertices_m'], m['vertices_m']])
    triangles = np.concatenate([m['triangles'], np.asarray(m['triangles']) + 8])
    with pytest.raises(ValueError, match='connected'):
        ConvexPiece.from_mesh(vertices, triangles)


@pytest.mark.parametrize('kwargs', [{'distance_pass_m': 0}, {'angle_pass_deg': 20}, {'row_pass_widths': float('nan')}])
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        TerminalPolicy(**kwargs)


def test_bad_asset_geometry_is_rejected_not_silently_scored():
    g, p, q = fixture()
    g['spheres']['ball']['radius_m'] = float('nan')
    with pytest.raises(ValueError, match='radii'):
        scene(g, p, q)
    g, p, q = fixture()
    g['rigids']['a']['long_axis_local'] = [2, 0, 0]
    with pytest.raises(ValueError, match='unit vector'):
        scene(g, p, q)
