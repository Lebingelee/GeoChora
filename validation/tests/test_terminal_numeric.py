"""Independent deterministic counterexamples for the real pipeline numeric route.

Synthetic metre/WXYZ boxes protect frame, scope, exact source thresholds and
three-valued physical inference. They do not qualify a simulator or asset.
"""

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from validation.tests.fixtures.evidence import evidence, REFS
from validation.protocol import _digest as digest
from validation.terminal.numeric import measure_source_requests, numeric_request_digest


def fixture(predicate, params=None, second_type=None):
    source = {'task_id': 'numeric-fixture', 'prompt': 'Measure the stated source-bound condition.',
        'requirements': {'window_seconds': 1., 'sample_dt_seconds': .5},
        'reference_frames': {'a': {}, 'b': {}}}
    record = evidence()
    requests = [{'request_id': 'goal', 'method': predicate,
        'arguments': [record['identities'][name] for name in (('a', 'b') if second_type else ('a',))],
        'params': params or {}, 'source_basis': [{'path': 'memory/task.json', 'pointer': '/prompt'}]}]
    basis = {'source_basis': [{'path': 'memory/task.json', 'pointer': '/reference_frames'}],
             'basis_refs': [record['source_refs'][2], REFS[0]]}
    body = {**basis, 'boxes': [{'half_extents_m': [.1, .1, .1], 'center_body_m': [0., 0., 0.],
                              'orientation_body_wxyz': [1., 0., 0., 0.]}],
            'enclosing_radius_m': math.sqrt(.03), 'source_center_body_m': [0., 0., 0.],
            'source_orientation_body_wxyz': [1., 0., 0., 0.]}
    producer = {'path': 'memory/verified_adapter.py', 'sha256': 'a' * 64}
    packet = {'schema_version': 'terminal-numeric-evidence/0.2', 'requests_sha256': numeric_request_digest(requests),
        'source_sha256': digest(source), 'episode_id': record['endpoint']['episode_id'],
        'endpoint_id': record['endpoint']['endpoint_id'], 'producer': producer,
        'basis_refs': basis['basis_refs'], 'bodies': {name: deepcopy(body) for name in ('a', 'b')},
        'scopes': {record['identities'][name]: {**deepcopy(basis), 'body_names': [name], 'complete': True,
                   'contact_only_retention': None} for name in (('a', 'b') if second_type else ('a',))},
        'regions': {}, 'samples': [{k: deepcopy(s[k]) for k in ('step', 'time_s', 'positions', 'orientations_wxyz')}
                                  for s in record['terminal_window']['samples']], 'contact_samples': []}
    if second_type == 'region':
        packet['regions'][record['identities']['b']] = {**deepcopy(basis), 'native_body': None,
            'origin_m': [0., 0., 0.], 'orientation_wxyz': [1., 0., 0., 0.], 'half_extents_xy_m': [.5, .5]}
    verified_refs = deepcopy([*REFS, producer])
    def run():
        return measure_source_requests(source, source_ref=record['source_refs'][2], evidence=record,
            evidence_refs=verified_refs, requests=requests, numeric_evidence=packet)
    run.requests = requests
    return record, packet, run


def move(record, packet, name, *, position=None, quaternion=None, index=None):
    indices = range(3) if index is None else [index]
    for i in indices:
        for field, value in (('positions', position), ('orientations_wxyz', quaternion)):
            if value is not None:
                record['terminal_window']['samples'][i][field][name] = deepcopy(value)
                packet['samples'][i][field][name] = deepcopy(value)
                if i == 2:
                    record['terminal'][field][name] = deepcopy(value)


@pytest.mark.parametrize('feature,position,expected', [
    ('source_object_center', [.6, 0., 1.], True), ('collision_min', [.6, 0., 1.], True),
    ('collision_max', [.6, 0., 1.], False), ('source_object_center', [.61, 0., 1.], False)])
def test_world_bound_uses_named_feature_and_exact_inclusive_source_bound(feature, position, expected):
    record, packet, run = fixture('world_coordinate_bound/v1',
        {'feature': feature, 'axis': 'x', 'bound': 'upper', 'value_m': .6, 'inclusive': True})
    move(record, packet, 'a', position=position)
    assert run()['measurements'][0]['value'] is expected
    packet['bodies']['a']['source_center_body_m'] = None
    if feature == 'source_object_center':
        assert run()['measurements'][0]['value'] is None


def test_center_offset_rotates_with_native_body_and_does_not_default_to_origin():
    record, packet, run = fixture('world_coordinate_bound/v1',
        {'feature': 'source_object_center', 'axis': 'x', 'bound': 'lower', 'value_m': .2, 'inclusive': False})
    packet['bodies']['a']['source_center_body_m'] = [.3, 0., 0.]
    assert run()['measurements'][0]['value'] is True
    move(record, packet, 'a', quaternion=[0., 0., 0., 1.])
    assert run()['measurements'][0]['value'] is False


@pytest.mark.parametrize('direction,expected', [('directed', False), ('undirected', True)])
def test_signed_axis_preserves_direction_without_imposing_yaw(direction, expected):
    record, packet, run = fixture('axis_angle_to_world/v1',
        {'object_axis': 'z', 'world_axis': '-z', 'direction': direction, 'maximum_angle_deg': 0.})
    assert run()['measurements'][0]['value'] is expected
    move(record, packet, 'a', quaternion=[math.sqrt(.5), 0., 0., math.sqrt(.5)])
    assert run()['measurements'][0]['value'] is expected
    packet['bodies']['a']['source_orientation_body_wxyz'] = None
    assert run()['measurements'][0]['value'] is None


def test_axis_parallel_uses_explicit_region_frame():
    record, packet, run = fixture('axis_parallel/v1',
        {'object_axis': 'x', 'region_axis': 'y', 'maximum_angle_deg': 0.}, 'region')
    assert run()['measurements'][0]['value'] is False
    packet['regions'][record['identities']['b']]['orientation_wxyz'] = [math.sqrt(.5), 0., 0., math.sqrt(.5)]
    assert run()['measurements'][0]['value'] is True


@pytest.mark.parametrize('boundary,expected', [('closed', True), ('open', False)])
def test_footprint_uses_all_rotated_collision_vertices_and_open_closed_boundary(boundary, expected):
    record, packet, run = fixture('collision_footprint_inside_region/v2', {'boundary': boundary}, 'region')
    move(record, packet, 'a', position=[.4, 0., 1.])
    assert run()['measurements'][0]['value'] is expected
    move(record, packet, 'a', quaternion=[math.cos(math.pi/8), 0., 0., math.sin(math.pi/8)])
    assert run()['measurements'][0]['value'] is False  # Center is still inside.
    packet['bodies']['a']['boxes'] = []  # An enclosing sphere cannot prove a failure.
    assert run()['measurements'][0]['value'] is None


def test_region_attached_to_a_body_follows_its_current_pose():
    record, packet, run = fixture('collision_footprint_inside_region/v1', {}, 'region')
    packet['regions'][record['identities']['b']]['native_body'] = 'b'
    assert run()['measurements'][0]['value'] is False
    move(record, packet, 'b', position=[0., 0., 0.])
    assert run()['measurements'][0]['value'] is True


def test_window_checks_interior_samples_and_missing_grid_is_unknown():
    record, packet, run = fixture('collision_footprint_inside_region/v1', {'window_seconds': 1.}, 'region')
    assert run()['measurements'][0]['value'] is True
    move(record, packet, 'a', position=[1., 0., 1.], index=1)
    assert run()['measurements'][0]['value'] is False
    del packet['samples'][1]
    assert run()['measurements'][0]['value'] is None


def test_separation_proves_release_but_overlap_does_not_prove_retention():
    record, packet, run = fixture('released_from_gripper/v1', {}, 'gripper')
    packet['scopes'][record['identities']['b']]['contact_only_retention'] = True
    assert run()['measurements'][0]['value'] is True
    move(record, packet, 'b', position=[.15, 0., 1.])
    assert run()['measurements'][0]['value'] is None


@pytest.mark.parametrize('support_x,expected_gap', [(2., 1.8), (.15, -.05)])
def test_support_without_load_still_exports_conservative_geometry_without_claiming_support(support_x, expected_gap):
    record, packet, run = fixture('physically_supported_by/v2', {}, 'support')
    move(record, packet, 'b', position=[support_x, 0., 1.])
    report = run()
    assert report['measurements'][0]['value'] is None
    atom, = report['measurements']
    assert atom['value'] is None
    sample, = atom['diagnostics']['samples']
    assert sample['support_geometry']['conservative_enclosure_gap_m'] == pytest.approx(expected_gap)
    assert sample['support_geometry']['scope'] == 'positive_excludes_direct_contact_nonpositive_does_not_establish_contact_or_support'
    packet['bodies']['b']['boxes'] = []
    packet['bodies']['b']['enclosing_radius_m'] = None
    assert run()['measurements'][0]['diagnostics']['samples'][0]['support_geometry']['conservative_enclosure_gap_m'] is None


@pytest.mark.parametrize('contact_only', [None, False])
def test_geometric_separation_cannot_prove_release_with_unexcluded_weld_or_tether(contact_only):
    record, packet, run = fixture('released_from_gripper/v1', {}, 'gripper')
    packet['scopes'][record['identities']['b']]['contact_only_retention'] = contact_only
    assert run()['measurements'][0]['value'] is None
    packet['scopes'][record['identities']['b']]['complete'] = False
    assert run()['measurements'][0]['value'] is None


def contacts(packet, *, force=[0., 0., 1.], touching=True, complete=True, paths=True):
    packet['contact_samples'] = [{'step': s['step'], 'time_s': s['time_s'],
        'phase': 'current_solved_state', 'body_names': ['a', 'b'], 'complete': complete,
        'force_scope': 'all_contact_forces', 'support_paths_complete': paths,
        'gravity_world_m_s2': [0., 0., -9.81],
        'points': [{'bodies': ['a', 'b'], 'distance_m': 0. if touching else .01,
                    'position_m': [0., 0., .9], 'force_on_first_world_n': force}]} for s in packet['samples']]


@pytest.mark.parametrize('force,expected', [([0., 0., 1.], True), ([1., 0., 0.], False), ([0., 0., -1.], False)])
def test_actual_support_requires_current_load_opposing_gravity(force, expected):
    record, packet, run = fixture('physically_supported_by/v2', {'window_seconds': 1.}, 'support')
    assert run()['measurements'][0]['value'] is None
    contacts(packet, force=force)
    assert run()['measurements'][0]['value'] is expected
    packet['contact_samples'][1]['force_scope'] = 'unavailable'
    packet['contact_samples'][1]['support_paths_complete'] = False
    packet['contact_samples'][1]['points'][0]['force_on_first_world_n'] = None
    assert run()['measurements'][0]['value'] is (None if expected else False)


@pytest.mark.parametrize('predicate,kind', [('no_robot_contact/v1', 'robot'), ('no_contact_between/v1', 'rigid')])
@pytest.mark.parametrize('complete', [False, True])
def test_current_touch_disproves_no_contact_even_with_partial_contact_list_or_separated_enclosures(predicate, kind, complete):
    _, packet, run = fixture(predicate, {}, kind)
    contacts(packet, complete=complete, paths=False)
    for sample in packet['contact_samples']:
        sample.update(phase='current_geometry', force_scope='unavailable', support_paths_complete=False)
        sample['points'][0]['force_on_first_world_n'] = None
    assert run()['measurements'][0]['value'] is False


@pytest.mark.parametrize('complete', [False, True])
@pytest.mark.parametrize('predicate,params,kind', [
    ('released_from_gripper/v1', {}, 'gripper'),
    ('not_supported_by/v1', {'support_path': 'direct'}, 'support')])
def test_known_touch_with_unknown_load_cannot_be_overridden_by_geometric_separation(predicate, params, kind, complete):
    record, packet, run = fixture(predicate, params, kind)
    packet['scopes'][record['identities']['b']]['contact_only_retention'] = True
    contacts(packet, complete=complete, paths=False)
    for sample in packet['contact_samples']:
        sample.update(phase='current_geometry', force_scope='unavailable')
        sample['points'][0]['force_on_first_world_n'] = None
    assert run()['measurements'][0]['value'] is None


@pytest.mark.parametrize('predicate,params,kind', [
    ('released_from_gripper/v1', {}, 'gripper'),
    ('not_supported_by/v1', {'support_path': 'direct'}, 'support')])
def test_known_touch_force_with_incomplete_load_inventory_cannot_certify_release_or_non_support(predicate, params, kind):
    record, packet, run = fixture(predicate, params, kind)
    packet['scopes'][record['identities']['b']]['contact_only_retention'] = True
    contacts(packet, complete=False, paths=False)
    assert run()['measurements'][0]['value'] is None


@pytest.mark.parametrize('complete', [False, True])
@pytest.mark.parametrize('predicate,params,kind', [
    ('no_robot_contact/v1', {}, 'robot'), ('no_contact_between/v1', {}, 'rigid'),
    ('released_from_gripper/v1', {}, 'gripper'), ('physically_supported_by/v1', {}, 'support'),
    ('physically_supported_by/v2', {}, 'support'),
    ('not_supported_by/v1', {'support_path': 'direct'}, 'support'),
    ('not_supported_by/v1', {'support_path': 'any'}, 'support')])
def test_positive_gap_with_nonzero_current_force_cannot_certify_contact_or_load_absence(predicate, params, kind, complete):
    record, packet, run = fixture(predicate, params, kind)
    packet['scopes'][record['identities']['b']]['contact_only_retention'] = True
    contacts(packet, touching=False, complete=complete, paths=complete)
    assert run()['measurements'][0]['value'] is None


@pytest.mark.parametrize('force', [None, [0., 0., 0.]])
@pytest.mark.parametrize('predicate,params,kind', [
    ('no_robot_contact/v1', {}, 'robot'), ('no_contact_between/v1', {}, 'rigid'),
    ('released_from_gripper/v1', {}, 'gripper'),
    ('not_supported_by/v1', {'support_path': 'direct'}, 'support')])
def test_positive_gap_without_observed_interaction_allows_independent_complete_geometry(predicate, params, kind, force):
    record, packet, run = fixture(predicate, params, kind)
    packet['scopes'][record['identities']['b']]['contact_only_retention'] = True
    contacts(packet, force=force, touching=False, complete=False, paths=False)
    if force is None:
        for sample in packet['contact_samples']:
            sample.update(phase='current_geometry', force_scope='unavailable')
    assert run()['measurements'][0]['value'] is True


@pytest.mark.parametrize('predicate,params', [
    ('physically_supported_by/v1', {}), ('not_supported_by/v1', {'support_path': 'any'})])
def test_force_across_positive_gap_on_intermediate_path_cannot_be_discarded_to_certify_absence(predicate, params):
    _, packet, run = fixture(predicate, params, 'support')
    packet['bodies']['c'] = deepcopy(packet['bodies']['a'])
    contacts(packet)
    for sample in packet['contact_samples']:
        sample['body_names'].append('c')
        point = sample['points'][0]
        sample['points'] = [{**point, 'bodies': ['a', 'c']},
                            {**point, 'bodies': ['c', 'b'], 'distance_m': .01}]
    assert run()['measurements'][0]['value'] is None


@pytest.mark.parametrize('split', ['target', 'support'])
@pytest.mark.parametrize('predicate,params', [
    ('physically_supported_by/v2', {}), ('not_supported_by/v1', {'support_path': 'direct'})])
@pytest.mark.parametrize('opposing_force,net_bearing', [(-2., False), (-1., False), (-.5, True)])
def test_direct_bearing_uses_net_force_across_complete_source_entity_scope(split, predicate, params, opposing_force, net_bearing):
    record, packet, run = fixture(predicate, params, 'support')
    symbol = 'a' if split == 'target' else 'b'
    record['identities']['c'] = record['endpoint']['episode_id'] + '::c'
    packet['bodies']['c'] = deepcopy(packet['bodies'][symbol])
    for sample in [record['initial'], record['terminal'], *record['terminal_window']['samples'], *packet['samples']]:
        sample['positions']['c'] = [0., 0., 1.2]
        sample['orientations_wxyz']['c'] = [1., 0., 0., 0.]
    scope = packet['scopes'].pop(record['identities'][symbol])
    scope['body_names'] = [symbol, 'c']
    group = 'source-declared::' + record['endpoint']['episode_id'] + '::source-group'
    packet['scopes'][group] = scope
    run.requests[0]['arguments'][0 if symbol == 'a' else 1] = group
    packet['requests_sha256'] = numeric_request_digest(run.requests)
    contacts(packet)
    for sample in packet['contact_samples']:
        sample['body_names'].append('c')
        pair = ['b', 'c'] if split == 'target' else ['c', 'a']
        sample['points'].append({**sample['points'][0], 'bodies': pair,
                                'force_on_first_world_n': [0., 0., -opposing_force]})
    report = run()
    expected = not net_bearing if predicate == 'not_supported_by/v1' else net_bearing
    assert report['measurements'][0]['value'] is expected


def test_native_fallback_cannot_drop_source_window_counterexample_by_claiming_a_slower_cadence():
    record, packet, run = fixture('collision_footprint_inside_region/v1', {'window_seconds': 1.}, 'region')
    move(record, packet, 'a', position=[1., 0., 1.], index=1)
    assert run()['measurements'][0]['value'] is False
    tail = record['terminal_window']
    tail['requested'].pop('sample_dt_seconds')
    tail['requested'].pop('sample_dt_pointer')
    tail['recorded_sample_dt_seconds'] = .5
    tail['sample_dt_seconds'] = 1.
    del tail['samples'][1]
    result = run()
    assert result['measurements'][0]['value'] is None
    assert result['measurements'][0]['diagnostics']['reason'] == 'native_fallback_cadence_mismatch'


def test_direct_non_support_does_not_exclude_indirect_support():
    _, packet, run = fixture('not_supported_by/v1', {'support_path': 'any'}, 'support')
    assert run()['measurements'][0]['value'] is None  # Far apart alone says nothing about an indirect path.
    contacts(packet, force=[0., 0., 0.], paths=False)
    assert run()['measurements'][0]['value'] is None
    for sample in packet['contact_samples']:
        sample['support_paths_complete'] = True
    assert run()['measurements'][0]['value'] is True
    contacts(packet)
    assert run()['measurements'][0]['value'] is False


def test_reversed_contact_order_cannot_create_load_from_cancelling_forces():
    _, packet, run = fixture('physically_supported_by/v1', {}, 'support')
    contacts(packet)
    for sample in packet['contact_samples']:
        sample['points'].append({**sample['points'][0], 'bodies': ['b', 'a']})
    assert run()['measurements'][0]['value'] is False


@pytest.mark.parametrize('predicate,params,expected', [
    ('physically_supported_by/v2', {}, None), ('not_supported_by/v1', {'support_path': 'any'}, None),
    ('not_supported_by/v1', {'support_path': 'direct'}, True)])
def test_indirect_positive_graph_is_not_target_load_attribution(predicate, params, expected):
    _, packet, run = fixture(predicate, params, 'support')
    packet['bodies']['c'] = deepcopy(packet['bodies']['a'])
    for sample in packet['samples']:
        sample['positions']['c'] = [0., 0., .5]
        sample['orientations_wxyz']['c'] = [1., 0., 0., 0.]
    contacts(packet)
    for sample in packet['contact_samples']:
        sample['body_names'].append('c')
        point = sample['points'][0]
        sample['points'] = [{**point, 'bodies': ['a', 'c']}, {**point, 'bodies': ['c', 'b']}]
    assert run()['measurements'][0]['value'] is expected


def test_complete_load_path_absence_cannot_omit_a_declared_intermediate_body():
    _, packet, run = fixture('not_supported_by/v1', {'support_path': 'any'}, 'support')
    packet['bodies']['c'] = deepcopy(packet['bodies']['a'])
    contacts(packet, force=[0., 0., 0.])
    with pytest.raises(ValueError, match='omit'):
        run()


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(episode_id='foreign'),
    lambda p: p['producer'].update(sha256='b' * 64),
    lambda p: p['bodies']['a']['basis_refs'].append({'path': 'foreign.json', 'sha256': 'b' * 64}),
    lambda p: p['samples'][-1]['positions']['a'].__setitem__(0, 1.),
    lambda p: p['contact_samples'][-1].update(phase='pre_qpos_integration'),
])
def test_foreign_owner_source_pose_or_historical_contact_phase_is_rejected(mutate):
    _, packet, run = fixture('physically_supported_by/v1', {}, 'support')
    contacts(packet)
    mutate(packet)
    with pytest.raises(ValueError):
        run()
