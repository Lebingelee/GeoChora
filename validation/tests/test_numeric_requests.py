"""Analytic pose and input-boundary oracles for the retained measurement entry."""
from copy import deepcopy
import math

import pytest

from validation.terminal.numeric import measure_source_requests, numeric_request_digest
from validation.tests.fixtures.evidence import evidence, REFS
from validation.protocol import _digest


def inputs(method='initial_displacement_within/v1', params=None):
    record = evidence()
    params = {'maximum_translation_m': .05} if params is None else params
    source = {'condition': {'method': method, 'params': params},
              'requirements': {'window_seconds': 1., 'sample_dt_seconds': .5},
              'frames': {'a': 'Explicit independently bound source reference point.'}}
    requests = [{'request_id': 'goal', 'method': method,
                 'arguments': [record['identities']['a']], 'params': params,
                 'source_basis': [{'path': 'memory/task.json', 'pointer': '/condition'}]}]
    return source, record, requests


def references(source, record, requests, *, offsets=None, rotations=None):
    offsets = offsets or {}
    rotations = rotations or {}
    entries = []
    for request in requests:
        if request['method'] == 'orientation_unchanged/v1':
            continue
        orientation = request['method'] == 'orientation_matches/v1'
        for identity in request['arguments']:
            entries.append({'request_id': request['request_id'], 'entity_id': identity,
                'reference_kind': 'source_orientation' if orientation else 'source_object_center',
                ('orientation_body_wxyz' if orientation else 'offset_body_m'):
                    rotations.get(request['request_id'], [1., 0., 0., 0.]) if orientation
                    else offsets.get(request['request_id'], [0., 0., 0.]),
                'source_basis': [{'path': 'memory/task.json', 'pointer': '/frames/a'}],
                'basis_refs': deepcopy([record['source_refs'][2], REFS[0]])})
    return {'requests_sha256': numeric_request_digest(requests), 'source_sha256': _digest(source),
            'episode_id': record['endpoint']['episode_id'], 'entries': entries}


def assess(source, record, requests, **kwargs):
    kwargs.setdefault('reference_bindings', references(source, record, requests))
    return measure_source_requests(source, source_ref=record['source_refs'][2], evidence=record,
        evidence_refs=REFS, requests=requests, **kwargs)


def test_initial_displacement_rotates_each_explicit_source_offset():
    source, record, requests = inputs(params={'maximum_translation_m': .5})
    record['terminal']['orientations_wxyz']['a'] = [0., 0., 0., 1.]
    result = assess(source, record, requests,
        reference_bindings=references(source, record, requests, offsets={'goal': [1., 0., 0.]}))
    row, = result['measurements']
    assert row['value'] is False
    assert row['diagnostics']['initial_displacement_m'] == pytest.approx(2.)
    assert 'terminal' not in result and 'task_success' not in result


def test_the_same_body_can_have_distinct_source_reference_points_per_request():
    source, record, requests = inputs(params={'maximum_translation_m': .5})
    requests.append({**deepcopy(requests[0]), 'request_id': 'other-center'})
    record['terminal']['orientations_wxyz']['a'] = [0., 0., 0., 1.]
    result = assess(source, record, requests,
        reference_bindings=references(source, record, requests, offsets={'other-center': [1., 0., 0.]}))
    assert [r['value'] for r in result['measurements']] == [True, False]
    assert [r['diagnostics']['initial_displacement_m'] for r in result['measurements']] == pytest.approx([0., 2.])


@pytest.mark.parametrize('sign', [1., -1.])
def test_orientation_matches_composes_local_source_frame_and_preserves_quaternion_sign_equivalence(sign):
    q = [math.sqrt(.5), 0., 0., math.sqrt(.5)]
    params = {**{'target_' + axis: sign * value for axis, value in zip('wxyz', q)}, 'maximum_angle_deg': .001}
    source, record, requests = inputs('orientation_matches/v1', params)
    result = assess(source, record, requests,
        reference_bindings=references(source, record, requests, rotations={'goal': q}))
    assert result['measurements'][0]['value'] is True
    assert result['measurements'][0]['diagnostics']['maximum_angle_deg'] < .001


def test_stability_checks_interior_samples_and_withholds_incomplete_source_grid():
    source, record, requests = inputs('sampled_pose_stable/v1',
        {'window_seconds': 1., 'maximum_translation_m': .05, 'maximum_rotation_deg': 1.})
    record['terminal_window']['samples'][1]['positions']['a'][0] = .08
    result = assess(source, record, requests)
    assert result['measurements'][0]['value'] is False
    assert result['measurements'][0]['diagnostics']['maximum_pairwise_translation_m'] == pytest.approx(.08)
    del record['terminal_window']['samples'][1]
    result = assess(source, record, requests)
    assert result['measurements'][0]['value'] is None
    assert result['measurements'][0]['diagnostics']['reason'] == 'requested_sample_grid_incomplete_or_over_budget'


def test_missing_reference_is_unknown_and_is_not_replaced_by_body_origin():
    source, record, requests = inputs()
    result = assess(source, record, requests, reference_bindings=None)
    assert result['measurements'][0]['value'] is None
    assert result['measurements'][0]['diagnostics']['reason'] == 'source_reference_binding_unavailable'


def test_invalid_endpoint_cannot_release_a_determinate_numeric_measurement():
    source, record, requests = inputs()
    record['endpoint'].update(valid=False, reasons=['recording_not_complete'])
    result = assess(source, record, requests)
    assert result['measurements'][0]['value'] is None
    assert result['measurements'][0]['diagnostics']['reason'] == 'completed_record_end_not_established'


@pytest.mark.parametrize('mutation', [
    lambda r: r.update(method='unregistered/v1'),
    lambda r: r['params'].update(unknown_parameter=1.),
    lambda r: r['params'].update(maximum_translation_m=True),
    lambda r: r['params'].update(maximum_translation_m=-.1),
    lambda r: r['params'].update(maximum_translation_m=float('nan')),
    lambda r: r.update(arguments=[]),
    lambda r: r.update(extra='not admitted'),
])
def test_explicit_measurement_parameters_and_fields_are_checked_before_calculation(mutation):
    source, record, requests = inputs()
    mutation(requests[0])
    with pytest.raises(ValueError):
        assess(source, record, requests)


@pytest.mark.parametrize('method,params', [
    ('sampled_pose_stable/v1', {'window_seconds': 0., 'maximum_translation_m': 1., 'maximum_rotation_deg': 1.}),
    ('orientation_matches/v1', {'target_w': 2., 'target_x': 0., 'target_y': 0., 'target_z': 0., 'maximum_angle_deg': 1.}),
    ('orientation_unchanged/v1', {'maximum_angle_deg': 181.}),
])
def test_time_angle_and_unit_quaternion_limits_are_preserved(method, params):
    source, record, requests = inputs(method, params)
    with pytest.raises(ValueError):
        assess(source, record, requests)


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(requests_sha256='0' * 64),
    lambda p: p.update(source_sha256='0' * 64),
    lambda p: p.update(episode_id='foreign'),
    lambda p: p['entries'][0].update(entity_id='foreign'),
    lambda p: p['entries'][0]['source_basis'][0].update(pointer='/absent'),
    lambda p: p['entries'][0]['basis_refs'][0].update(sha256='0' * 64),
])
def test_reference_point_bindings_keep_request_source_identity_and_hash_guards(mutation):
    source, record, requests = inputs()
    packet = references(source, record, requests)
    mutation(packet)
    with pytest.raises(ValueError):
        assess(source, record, requests, reference_bindings=packet)
