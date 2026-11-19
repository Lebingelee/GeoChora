"""Synthetic recorded-world-pose and pipeline boundary counterexamples."""

from copy import deepcopy
import hashlib
import json

import pytest

from validation.artifact_io import digest
from validation.terminal.evidence_views import prepare_evidence_views
from validation.adapters.physpi import prepare_source_evidence
from validation.terminal.source_run import prepare_source_run
from validation.terminal.reviews import prepare_source_review
from validation.adapters.recorded import adapt_recorded_poses, read_recorded_poses
from validation.adapters import recorded as recorded_terminal
from validation.terminal.numeric import measure_source_requests, numeric_request_digest
from validation.protocol import _digest


SCHEMA = {'frame': 'world', 'position_unit': 'm', 'time_unit': 's', 'orientation_order': 'wxyz'}
CODE = {'path': 'input/recorder.py', 'sha256': '1' * 64}
TRACE = {'path': 'input/trace.json', 'sha256': '2' * 64}
CLAIM = {'path': 'input/completion.json', 'sha256': '3' * 64}
TASK = {'path': 'memory/task.json', 'sha256': '4' * 64}


@pytest.mark.parametrize('name,missing_middle', [('gear', False), ('renamed-part/17', False), ('gear', True)])
def test_recorded_public_source_route_projects_and_expands_real_samples(tmp_path, name, missing_middle):
    """Recorded format, arbitrary identity; an interior violation must survive expansion."""
    def save(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return {'path': name, 'sha256': digest(path)}

    frames = [{'orientations': {name: [1., 0., 0., 0.]}, 'time': t,
               'positions': {name: [x, 0., 0.], 'other': [9., 0., 0.]}}
              for t, x in [(0., 0.), (.75, .8), (2., 0.)]]
    if missing_middle:
        del frames[1]['positions'][name]
    code = save('code.json', {'synthetic': True})
    trace = save('trace.json', frames)
    claim = save('completion.json', {'run_id': 'unseen-source', 'bodies': [name, 'other'],
        'code_ref': code, 'trace_ref': trace, 'frame_count': 3, 'last_recorded_time_s': 2.,
        'last_recorded_step': 20, 'actual_final_time_s': 2., 'actual_final_step': 20,
        'first_step': 0, 'complete': True})
    record = read_recorded_poses(tmp_path, run_id='unseen-source', bodies=[name, 'other'],
        code_ref=code, trace_ref=trace, completion_ref=claim, pose_schema=SCHEMA)
    state = save('state.json', record)
    bundle = prepare_source_evidence(tmp_path, state, tmp_path / 'bundle')
    profile = {'name': 'synthetic/model', 'reasoning_effort': 'medium'}
    request = prepare_source_review({'goal': 'Check every recorded pose in [0, 2] seconds.'},
        bundle['endpoint'], required_source_pointers=['/goal'], model_profile=profile,
        evidence=bundle['evidence'])
    prepare_source_run(request, tmp_path, tmp_path / 'run', verification_model_profile=profile,
                       evidence_mode='adaptive')
    view = json.loads((tmp_path / 'run/evidence-initial/index.json').read_text())
    entry = next(e for e in view['catalogue']['entries'] if e['id'] == 'observed_state')
    catalogue = json.loads(entry['description'].split('Archived observations, not delivered data. ')[1])
    assert catalogue['recorded_times_s'] == [0., .75, 2.]
    assert entry['channels'] == ['pose'] and entry['source_grid'] is False
    descriptor = next(e for e in view['evidence'] if e['id'] == 'observed_state')
    boundary = json.loads((tmp_path / descriptor['path']).read_text())['observations']
    assert 'frames' not in boundary['provenance']
    assert boundary['provenance']['pose_schema'] == SCHEMA
    assert boundary['initial'] == record['initial'] and boundary['terminal'] == record['terminal']
    query = {'evidence_id': 'observed_state', 'source_pointers': ['/goal'], 'entities': [name],
        'channels': ['pose'], 'time_range_s': [0., 2.], 'sampling': 'recorded', 'reason': 'Inspect window.'}
    expanded = prepare_evidence_views(tmp_path, view['evidence'], bundle['endpoint'],
        tmp_path / 'expanded', mode='expanded', queries=[query])
    assert expanded['outcomes'][0]['status'] == 'delivered'
    assert expanded['outcomes'][0]['delivered_times_s'] == [0., .75, 2.]
    selected = json.loads((tmp_path / expanded['evidence'][0]['path']).read_text())['observations']
    rows = selected['requested_window_samples']
    assert [r['time'] for r in rows] == [0., .75, 2.]
    assert rows[1]['positions'] == ({} if missing_middle else {name: [.8, 0., 0.]})
    assert all('other' not in r['positions'] for r in rows)
    assert 'frames' not in selected['provenance']
    assert digest(tmp_path / state['path']) == state['sha256']
    unavailable = prepare_evidence_views(tmp_path, bundle['evidence'], bundle['endpoint'],
        tmp_path / 'no-grid', mode='expanded', queries=[{**query, 'sampling': 'source_grid'}])
    assert unavailable['outcomes'][0]['reason'] == 'source_grid_not_recorded'
    contact = prepare_evidence_views(tmp_path, bundle['evidence'], bundle['endpoint'],
        tmp_path / 'no-contact', mode='expanded', queries=[{**query, 'channels': ['contact']}])
    assert contact['outcomes'][0]['reason'] == 'requested_channels_not_recorded'


def input_data():
    # Fields deliberately change order, and names do not match existing fixtures.
    frames = [
        {'orientations': {'gear': [1., 0., 0., 0.]}, 'time': 0.,
         'positions': {'gear': [1., 2., 3.], 'stand': [0., 0., 0.]}},
        {'positions': {'stand': [0., 0., 0.], 'gear': [2., 2., 3.]},
         'time': 1., 'orientations': {'gear': [1., 0., 0., 0.]}},
    ]
    claim = {'trace_ref': deepcopy(TRACE), 'run_id': 'r-unique', 'code_ref': deepcopy(CODE),
        'bodies': ['gear', 'stand'], 'frame_count': 2, 'last_recorded_time_s': 1.,
        'last_recorded_step': 20, 'actual_final_time_s': 1., 'actual_final_step': 20,
        'complete': True, 'first_step': 0}
    return frames, claim


def adapt(frames=None, claim=None, **kwargs):
    original, original_claim = input_data()
    return adapt_recorded_poses(original if frames is None else frames,
        run_id='r-unique', bodies=['gear', 'stand'], code_ref=CODE, trace_ref=TRACE,
        completion_ref=CLAIM, completion=original_claim if claim is None else claim,
        pose_schema=SCHEMA, source_refs=[TASK], **kwargs)


@pytest.mark.parametrize('producer_path', [
    'task_env/diagnostics/qualification/terminal/recorded.py',
    'task_env/diagnostics/qualification/recorded_terminal.py',
])
def test_frozen_recorded_producer_identity_survives_module_extraction(producer_path, monkeypatch):
    with monkeypatch.context() as historical:
        historical.setattr(recorded_terminal, '_IMPLEMENTATION',
                           {'path': producer_path, 'sha256': 'a' * 64})
        record = adapt()
    assert recorded_terminal.validate_recorded_evidence(record) == record
    record['provenance']['frames'][0]['positions']['gear'][0] += 1
    with pytest.raises(ValueError, match='differs from its source-bound inputs'):
        recorded_terminal.validate_recorded_evidence(record)


SOURCE = {'prompt': 'Use the explicitly provided final-state requirement.',
          'reference_frames': {name: {'offset_body_m': [0., 0., 0.]} for name in ('a', 'b')}}

def measurement_request(predicate='orientation_unchanged/v1', params=None):
    return {'request_id': 'goal', 'method': predicate,
        'names': ['gear', 'stand'] if predicate == 'center_ordered/v1' else ['gear'],
        'params': {'maximum_angle_deg': 0.} if params is None else params}


def assess(record, specification=None, **kwargs):
    selected = measurement_request() if specification is None else specification
    request = {k: deepcopy(v) for k, v in selected.items() if k != 'names'}
    request.update(arguments=[record['identities'][n] for n in selected['names']],
                   source_basis=[{'path': TASK['path'], 'pointer': '/prompt'}])
    return measure_source_requests(SOURCE, source_ref=TASK, evidence=record,
        evidence_refs=[{'path': 'output/evidence.json', 'sha256': '5' * 64}, TASK],
        requests=[request], **kwargs)


@pytest.mark.parametrize('rotation,expected', [([1., 0., 0., 0.], True), ([0., 1., 0., 0.], False), (None, None)])
def test_real_pipeline_retains_true_false_and_missing_orientation(rotation, expected):
    frames, claim = input_data()
    if rotation is None:
        del frames[-1]['orientations']['gear']
    else:
        frames[-1]['orientations']['gear'] = rotation
    record = adapt(frames, claim)
    assert record['schema_version'] == 'terminal-evidence/0.3'
    assert record['capture']['owner'] == 'recorded.world_pose_file'
    assert assess(record)['measurements'][0]['value'] is expected
    assert record['task_success'] is None


@pytest.mark.parametrize('stand_x,expected', [(3., True), (1., False), (None, None)])
def test_pipeline_measures_source_bound_world_position_or_preserves_missing(stand_x, expected):
    frames, claim = input_data()
    if stand_x is None:
        del frames[-1]['positions']['stand']
    else:
        frames[-1]['positions']['stand'][0] = stand_x
    record = adapt(frames, claim)
    spec = measurement_request('center_ordered/v1', {'axis': 'x', 'minimum_gap_m': .5})
    entries = [{'request_id': 'goal', 'entity_id': record['identities'][name],
                'reference_kind': 'source_object_center', 'offset_body_m': [0., 0., 0.],
                'source_basis': [{'path': TASK['path'], 'pointer': '/reference_frames/' + symbol}],
                'basis_refs': [TASK, CODE]}
               for symbol, name in [('a', 'gear'), ('b', 'stand')]]
    references = {'requests_sha256': numeric_request_digest([{k: v for k, v in {**spec, 'arguments': [record['identities'][n] for n in spec['names']], 'source_basis': [{'path': TASK['path'], 'pointer': '/prompt'}]}.items() if k != 'names'}]), 'source_sha256': _digest(SOURCE),
                  'episode_id': record['endpoint']['episode_id'], 'entries': entries}
    assert assess(record, spec, reference_bindings=references)['measurements'][0]['value'] is expected


def test_incomplete_final_clock_is_not_an_endpoint_and_no_initial_is_invented():
    frames, claim = input_data()
    claim.update(complete=False, actual_final_time_s=2., actual_final_step=40, first_step=None)
    record = adapt(frames, claim)
    assert record['endpoint']['valid'] is False
    assert record['terminal']['time_s'] == 1.
    assert record['initial']['valid_for_task_initial'] is False
    assert record['initial']['step'] is None
    assert assess(record)['measurements'][0]['value'] is None


def test_missing_initial_even_at_zero_remains_unknown():
    frames, claim = input_data()
    claim['first_step'] = None
    record = adapt(frames, claim)
    assert not record['initial']['valid_for_task_initial']
    assert assess(record)['measurements'][0]['value'] is None


def test_tail_requirement_remains_unknown_without_source_requested_grid():
    record = adapt()
    spec = measurement_request('sampled_pose_stable/v1', {'window_seconds': 1., 'maximum_translation_m': .02,
                                                'maximum_rotation_deg': 1.})
    result = assess(record, spec)
    assert result['measurements'][0]['value'] is None
    assert result['measurements'][0]['diagnostics']['reason'] == 'complete_source_requested_window_unavailable'


@pytest.mark.parametrize('change', [
    lambda f, c: f[1].update(time=0.),
    lambda f, c: f[1].update(time=-1.),
    lambda f, c: f[1]['positions'].update(ghost=[0., 0., 0.]),
    lambda f, c: f[1]['positions'].update(gear=[0., 1.]),
    lambda f, c: f[1]['positions'].update(gear=[0., 1., float('nan')]),
    lambda f, c: f[1]['orientations'].update(gear=[0., 0., 0., 0.]),
    lambda f, c: c.update(frame_count=3),
    lambda f, c: c.update(actual_final_time_s=2.),
    lambda f, c: c.update(actual_final_step=21),
    lambda f, c: c.update(first_step=20),
    lambda f, c: c.update(run_id='another-run'),
    lambda f, c: c.update(trace_ref={'path': TRACE['path'], 'sha256': '9' * 64}),
    lambda f, c: c.update(code_ref={'path': CODE['path'], 'sha256': '9' * 64}),
    lambda f, c: c.update(bodies=['gear', 'ghost']),
])
def test_invalid_source_clocks_poses_identities_or_bindings_are_rejected(change):
    frames, claim = input_data()
    change(frames, claim)
    with pytest.raises(ValueError):
        adapt(frames, claim)


@pytest.mark.parametrize('change', [{'orientation_order': 'xyzw'}, {'position_unit': 'mm'},
                                  {'time_unit': 'ms'}, {'frame': 'local'}])
def test_pose_units_frame_and_quaternion_order_must_be_explicit_and_supported(change):
    frames, claim = input_data()
    with pytest.raises(ValueError):
        adapt_recorded_poses(frames, run_id='r-unique', bodies=['gear', 'stand'],
            code_ref=CODE, trace_ref=TRACE, completion_ref=CLAIM, completion=claim,
            pose_schema={**SCHEMA, **change})


@pytest.mark.parametrize('change', [
    lambda r: r['capture'].update(owner='physpi_runtime.cli.cmd_query'),
    lambda r: r['capture'].update(owner='mujoco.public_state_and_contact'),
    lambda r: r['implementation'].update(path='physpi_terminal.py'),
    lambda r: r['implementation'].update(sha256='bad-hash'),
    lambda r: r['implementation'].update(sha256='f' * 64),
    lambda r: r['endpoint'].update(time_s=2.),
    lambda r: r['endpoint'].update(asset_family='some-other-domain'),
    lambda r: r['endpoint'].update(endpoint_id='0' * 64),
    lambda r: r['terminal']['positions']['gear'].__setitem__(0, 99.),
    lambda r: r['provenance']['trace_ref'].update(sha256='9' * 64),
    lambda r: r['source_refs'][0].update(sha256='9' * 64),
    lambda r: r['identities'].update(ghost='fake'),
    lambda r: r['facts'].update(terminal_contact={'known': True}),
])
def test_pipeline_revalidates_record_and_rejects_tampered_envelope(change):
    record = adapt()
    change(record)
    with pytest.raises(ValueError):
        assess(record)


def test_historical_producer_reference_is_preserved_and_bound_to_the_episode(monkeypatch):
    current = deepcopy(recorded_terminal._IMPLEMENTATION)
    historical = {**current, 'sha256': '8' * 64}
    monkeypatch.setattr(recorded_terminal, '_IMPLEMENTATION', historical)
    record = adapt()
    monkeypatch.setattr(recorded_terminal, '_IMPLEMENTATION', current)
    assert record['implementation'] == historical
    assert assess(record)['measurements'][0]['value'] is True
    record['implementation']['sha256'] = '9' * 64
    with pytest.raises(ValueError):
        assess(record)


@pytest.mark.parametrize('modified', ['code', 'trace', 'completion', 'extra'])
def test_file_loader_checks_real_bytes_for_each_source_and_rejects_stale_hashes(tmp_path, modified):
    frames, claim = input_data()
    def write(name, value):
        data = value.encode('utf-8') if isinstance(value, str) else json.dumps(value).encode('utf-8')
        (tmp_path / name).write_bytes(data)
        return {'path': name, 'sha256': hashlib.sha256(data).hexdigest()}

    code = write('recorder.py', '# recorded source, never executed\n')
    trace = write('trace.json', frames)
    claim.update(code_ref=code, trace_ref=trace)
    completion = write('completion.json', claim)
    extra = write('source.json', {'requirements': 'explicit'})
    kwargs = dict(run_id='r-unique', bodies=['gear', 'stand'], code_ref=code, trace_ref=trace,
                  completion_ref=completion, pose_schema=SCHEMA, source_refs=[extra])
    assert assess(read_recorded_poses(tmp_path, **kwargs))['measurements'][0]['value'] is True
    ref = {'code': code, 'trace': trace, 'completion': completion, 'extra': extra}[modified]
    (tmp_path / ref['path']).write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        read_recorded_poses(tmp_path, **kwargs)
