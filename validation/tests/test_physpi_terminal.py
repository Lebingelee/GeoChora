"""Offline collector admission, using synthetic public replies and immutable files.

No simulation or label oracle: these tests protect source/run/clock separation,
source-requested sample completeness, and numeric pose facts only.
"""

from validation.tests.fixtures.runtime import _write, _run, _queries, _collect, _boundary_fixture
import re
from copy import deepcopy

import pytest

from validation.adapters import physpi as collector


def _native_fixture():
    build = {'imports': [{'bodies': [{'index': 0, 'key': 'body'}],
                          'joint_layout': {'qpos0': [0.]}, 'attached_solver_indices': [2]}]}
    mappings = collector._native_solver_mappings(build)
    rows = []
    for step in range(3):
        channels = {**{f'body_pos.0.{i}': 0. for i in range(3)},
                    **{f'body_quat.0.{i}': float(i == 0) for i in range(4)},
                    'qpos.0': 0., 'ctrl.0': 1., 'actuator_force.0': 2.,
                    **{f'host_calls.{n}': 0. for n in ('set_ctrl','set_qfrc_applied',
                        'write_positions','write_orientations','write_qpos','write_qvel')}}
        rows.extend({'step': step, 't': step*.01, 'name': 'solver2.'+name, 'value': value}
                    for name,value in channels.items())
    runtime = {'start_step': 0, 'start_time': 0., 'dt': .01, 'sample_dt': .01}
    return build, mappings, rows, runtime


def test_native_dynamic_solver_layout_and_recorded_grid():
    _, maps, rows, runtime = _native_fixture()
    result = collector._native_samples(rows, maps, runtime, 0., .02)
    assert result['recorded_sample_grid_complete']
    assert result['expected_steps'] == [0,1,2]
    assert result['samples'][-1]['solvers']['2']['actuator_force'] == [2.]
    assert not result['solver_layouts']['2']['full_native_actuator_inventory_known']


@pytest.mark.parametrize('field', ['body_pos.0.1', 'qpos.0', 'host_calls.write_qpos'])
def test_native_missing_scalar_is_unknown_not_zero(field):
    _, maps, rows, runtime = _native_fixture()
    rows = [r for r in rows if not (r['step'] == 1 and r['name'] == 'solver2.'+field)]
    result = collector._native_samples(rows, maps, runtime, 0., .02)
    assert not result['recorded_sample_grid_complete']
    assert any('sample_grid_incomplete' in x for x in result['reasons'])


@pytest.mark.parametrize('corruption', ['duplicate', 'clock', 'body_index', 'unmapped_solver'])
def test_native_identity_and_channel_corruption_rejected(corruption):
    _, maps, rows, runtime = _native_fixture()
    if corruption == 'duplicate': rows.append(dict(rows[0]))
    elif corruption == 'clock': rows[0]['t'] = .005
    elif corruption == 'body_index': rows[0]['name'] = 'solver2.body_pos.1.0'
    else: rows[0]['name'] = 'solver3.body_pos.0.0'
    with pytest.raises(ValueError):
        collector._native_samples(rows, maps, runtime, 0., .02)


def test_merged_native_map_requires_recorded_final_body_names():
    build = {'imports': [{'joint_layout': {'qpos0':[0.,0.]}}, {'joint_layout': {'qpos0':[0.]}}],
        'compositions': [{'inputs':[{'kind':'import','index':0},{'kind':'import','index':1}],
                          'attached_solver_indices':[0]}]}
    with pytest.raises(ValueError, match='body map'):
        collector._native_solver_mappings(build)
    build['contact_observations'] = {'0': {'body_names':['a','b'], 'body_indices':{'a':0,'b':1}}}
    mapping = collector._native_solver_mappings(build)['0']
    assert mapping['body_names'] == ['a','b'] and mapping['qpos_count'] == 3
    assert mapping['joint_layout'] is None and not mapping['global_joint_layout_known']
    build['contact_observations']['0']['body_indices']['a'] = 1
    with pytest.raises(ValueError, match='disagree'):
        collector._native_solver_mappings(build)


def _pose_projection_files(tmp_path, *, mutate=None, incomplete_source_grid=False):
    from validation.tests.fixtures.evidence import evidence

    base = evidence()
    if incomplete_source_grid:
        base['terminal_window']['complete'] = False
    build = {'imports': [{'bodies': [{'index': i, 'key': name} for i, name in enumerate(('a', 'b'))],
                         'joint_layout': {'qpos0': []}, 'attached_solver_indices': [0]}]}
    mappings = collector._native_solver_mappings(build)
    rows = []
    for sample in base['terminal_window']['samples']:
        for index, name in enumerate(('a', 'b')):
            for field, values in (('body_pos', sample['positions'][name]),
                                  ('body_quat', sample['orientations_wxyz'][name])):
                rows.extend({'step': sample['step'], 't': sample['time_s'],
                             'name': f'solver0.{field}.{index}.{axis}', 'value': value}
                            for axis, value in enumerate(values))
    samples = collector._native_samples(rows, mappings,
        {'start_step': 0, 'start_time': 0., 'dt': .5, 'sample_dt': .5}, 0., 1.)
    samples.update(schema_version='native-samples/0.2', endpoint=base['endpoint'],
                   solver_mappings=mappings, source_grid_steps=[0, 1, 2])
    if mutate:
        mutate(samples)
    def store(name, value):
        path = _write(tmp_path / name, value)
        return {'path': name, 'sha256': collector.digest(path)}
    native = {'schema_version': 'native-evidence/0.2', 'endpoint': base['endpoint'], 'run': base['run'],
              'capture': {'owner': 'physpi_runtime.cli.cmd_query'}, 'native_build_evidence': build,
              'base_evidence_ref': store('base.json', base), 'native_samples': store('samples.json', samples)}
    return store('native.json', native)


def test_native_pose_projection_preserves_usable_poses_when_control_counters_are_missing(tmp_path):
    reference = _pose_projection_files(tmp_path)
    result = collector.collect_native_pose_measurements(tmp_path, reference)
    assert result['source_grid_complete']
    assert result['body_names'] == ['a', 'b']
    assert result['samples'][-1]['positions']['b'] == [2., 0., 1.]
    fact = result['body_pose_spread']['a']
    assert fact['available'] and fact['maximum_pairwise_body_origin_distance_m'] == 0.
    assert 'maximum_pairwise_center_distance_m' not in fact
    assert result['coordinate_frame'] == 'world_native_body_origin_not_source_object_center'
    assert not result['geometry_or_support_inferred'] and result['task_verdict'] is None
    assert len(result['source_refs']) == 3


def test_native_pose_projection_keeps_missing_pose_distinct_from_zero(tmp_path):
    reference = _pose_projection_files(tmp_path, mutate=lambda s:
        s['samples'][1]['solvers']['0']['body_positions'][1].__setitem__(0, None))
    result = collector.collect_native_pose_measurements(tmp_path, reference)
    assert not result['source_grid_complete']
    assert result['body_pose_spread']['a']['available']
    assert not result['body_pose_spread']['b']['available']
    assert 'b' not in result['samples'][1]['positions']
    selected = collector.collect_native_pose_measurements(tmp_path, reference, body_names=['a'])
    assert selected['source_grid_complete']


def test_native_pose_projection_does_not_claim_complete_source_window_from_partial_grid(tmp_path):
    reference = _pose_projection_files(tmp_path, incomplete_source_grid=True)
    result = collector.collect_native_pose_measurements(tmp_path, reference)
    assert not result['source_grid_complete']
    assert all(not fact['available'] and fact['reason'] == 'source_sample_grid_incomplete'
               for fact in result['body_pose_spread'].values())
    assert result['source_window']['seconds'] == 1.
    assert result['observed_span_seconds'] == 1.


@pytest.mark.parametrize('corruption', ['map', 'grid', 'clock', 'tracked_pose', 'duplicate'])
def test_native_pose_projection_rejects_mismatched_source_or_identity(tmp_path, corruption):
    def mutate(samples):
        if corruption == 'map':
            samples['solver_mappings']['0']['body_names'].reverse()
        elif corruption == 'grid':
            samples['source_grid_steps'].pop()
        elif corruption == 'clock':
            samples['samples'][1]['time_s'] = .6
        elif corruption == 'tracked_pose':
            samples['samples'][1]['solvers']['0']['body_positions'][1][0] = 9.
        else:
            samples['samples'].append(deepcopy(samples['samples'][0]))
    reference = _pose_projection_files(tmp_path, mutate=mutate)
    with pytest.raises(ValueError):
        collector.collect_native_pose_measurements(tmp_path, reference)


def test_native_pose_projection_checks_file_bytes_and_scope(tmp_path):
    reference = _pose_projection_files(tmp_path)
    with pytest.raises(ValueError, match='scope'):
        collector.collect_native_pose_measurements(tmp_path, reference, body_names=['foreign'])
    (tmp_path / 'samples.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash'):
        collector.collect_native_pose_measurements(tmp_path, reference)


def test_boundary_images_are_bound_to_actual_state_source_and_clock(tmp_path, monkeypatch):
    _, _, _, refs = _boundary_fixture(tmp_path, monkeypatch)
    result = collector.collect_boundary_images(tmp_path, *refs())
    assert [image['kind'] for image in result['images']] == ['native_context_image', 'native_image']
    assert [image['time_s'] for image in result['images']] == [0., 2.]
    assert not result['diagnostics']


@pytest.mark.parametrize('count', [3, 10])
def test_resident_boundary_accepts_clock_roundoff_but_rejects_a_different_time(tmp_path, monkeypatch, count):
    _, packet, path, refs = _boundary_fixture(tmp_path, monkeypatch, resident=True, count=count)
    state = collector.read_json(tmp_path / 'evidence.json')
    assert state['endpoint']['valid']
    # Resident clocks round to nine decimals; multiplication need not have identical binary bits.
    packet['groups'][1]['t'] = count * .1
    _write(path, packet)
    result = collector.collect_boundary_images(tmp_path, *refs())
    assert result['images'][-1]['id'] == 'final_overview'
    assert result['images'][-1]['time_s'] == state['terminal']['time_s']
    packet['groups'][1]['t'] += 1e-7
    _write(path, packet)
    result = collector.collect_boundary_images(tmp_path, *refs())
    assert all(image['kind'] != 'native_image' for image in result['images'])
    assert result['diagnostics'][-1]['boundary'] == 'final'


@pytest.mark.parametrize('field,value', [('clock_valid', False), ('same_observed_state', False),
    ('camera_restored', False), ('step', 19), ('t', 1.9), ('t', None), ('t', '2'),
    ('branch', 'other'), ('state_after_sha256', 'b' * 64)])
def test_boundary_invalid_final_capture_cannot_supply_visual_evidence(tmp_path, monkeypatch, field, value):
    _, packet, path, refs = _boundary_fixture(tmp_path, monkeypatch)
    packet['groups'][1][field] = value
    _write(path, packet)
    result = collector.collect_boundary_images(tmp_path, *refs())
    assert [image['kind'] for image in result['images']] == ['native_context_image']
    assert result['diagnostics'][0]['boundary'] == 'final'


def test_boundary_pixels_and_source_bytes_must_match_retained_hashes(tmp_path, monkeypatch):
    setup, packet, path, refs = _boundary_fixture(tmp_path, monkeypatch)
    packet['groups'][1]['images'][0]['sha256'] = 'c' * 64
    _write(path, packet)
    with pytest.raises(ValueError):
        collector.collect_boundary_images(tmp_path, *refs())
    packet['code_sha256'] = 'd' * 64
    _write(path, packet)
    with pytest.raises(ValueError, match='identity mismatch'):
        collector.collect_boundary_images(tmp_path, *refs())


@pytest.mark.parametrize('resident', [False, True])
def test_actual_initial_terminal_and_requested_tail_are_source_bound(tmp_path, monkeypatch, resident):
    setup = _run(tmp_path, resident=resident)
    calls = _queries(monkeypatch, setup[-1])
    evidence = _collect(tmp_path, setup)
    assert evidence['endpoint']['valid'] is True
    assert evidence['endpoint']['asset_family'] == 'fixture-boxes'
    assert all(value.startswith('native-physpi::') for value in evidence['identities'].values())
    assert evidence['initial']['valid_for_task_initial'] is not resident
    assert evidence['terminal_window']['complete'] is True
    assert len(evidence['terminal_window']['samples']) == 11
    spread = evidence['facts']['terminal_window_pose_spread']['cube']
    assert spread['maximum_pairwise_center_distance_m'] == pytest.approx(0.1 if resident else 0.01)
    assert spread['maximum_pairwise_orientation_angle_deg'] == pytest.approx(0.)
    assert evidence['facts']['actual_support'] is None
    assert evidence['facts']['robot_release'] is None
    assert evidence['process'] == 'not_evaluated' and evidence['task_success'] is None
    assert not any('measurements' in query['sql'] for query in calls)
    assert not evidence['facts']['native_measurements_collected']


def test_missing_tail_sample_withholds_stability_but_not_observed_terminal(tmp_path, monkeypatch):
    setup = _run(tmp_path)
    _queries(monkeypatch, [r for r in setup[-1] if r['step'] != 15])
    evidence = _collect(tmp_path, setup)
    assert evidence['endpoint']['valid']
    assert not evidence['terminal_window']['complete']
    assert 'requested_window_sample_grid_incomplete' in evidence['terminal_window']['reasons']
    assert not evidence['facts']['terminal_window_pose_spread']['cube']['available']


def test_source_requirement_and_runtime_cadence_may_not_be_reinterpreted(tmp_path, monkeypatch):
    setup = _run(tmp_path)
    _queries(monkeypatch, setup[-1])
    index = collector.read_json(setup[2])
    index['timing']['trace_sample_dt'] = 0.2
    _write(setup[2], index)
    result = _collect(tmp_path, setup)
    assert not result['terminal_window']['complete']
    assert 'source_sample_cadence_not_established' in result['terminal_window']['reasons']


def test_source_window_cannot_be_changed_to_fit_observed_outcome(tmp_path, monkeypatch):
    setup = _run(tmp_path)
    _queries(monkeypatch, setup[-1])
    setup[3]['seconds'] = 0.5
    with pytest.raises(ValueError, match='equal the source'):
        _collect(tmp_path, setup)
    assert not (tmp_path / 'evidence.json').exists()


def test_job_clock_mismatch_makes_endpoint_invalid(tmp_path, monkeypatch):
    setup = _run(tmp_path)
    _queries(monkeypatch, setup[-1])
    path = setup[0] / 'job.json'
    job = collector.read_json(path)
    job['simulation']['dt'] = 0.2
    _write(path, job)
    evidence = _collect(tmp_path, setup)
    assert not evidence['endpoint']['valid']
    assert 'runtime_job_timebase_mismatch' in evidence['endpoint']['reasons']


def test_wrong_branch_trace_location_and_wrong_entity_are_rejected(tmp_path, monkeypatch):
    setup = _run(tmp_path, resident=True)
    _queries(monkeypatch, setup[-1])
    with pytest.raises(ValueError, match='requested entities'):
        _collect(tmp_path, setup, entities=['a_different_object'])
    index = collector.read_json(setup[2])
    other = setup[0] / 'timeline/other/trace/states.parquet'
    other.parent.mkdir(parents=True)
    other.write_bytes(b'foreign branch')
    index['branches']['main']['trace'] = 'timeline/other/trace/states.parquet'
    _write(setup[2], index)
    with pytest.raises(ValueError, match='query location'):
        _collect(tmp_path, setup)


@pytest.mark.parametrize('which', ['source', 'trace'])
def test_source_or_trace_mutation_fails_before_publishing(tmp_path, monkeypatch, which):
    setup = _run(tmp_path)
    path = tmp_path / 'requirement.json' if which == 'source' else setup[0] / 'trace/states.parquet'
    _queries(monkeypatch, setup[-1], mutate=lambda: path.write_bytes(b'changed'))
    with pytest.raises(ValueError, match='changed while querying'):
        _collect(tmp_path, setup)
    assert not (tmp_path / 'evidence.json').exists()


def test_no_window_does_not_invent_stability_and_never_overwrites(tmp_path, monkeypatch):
    setup = _run(tmp_path)
    calls = _queries(monkeypatch, setup[-1])
    evidence = collector.collect_evidence(setup[0], 'unused', tmp_path, tmp_path / 'evidence.json')
    assert evidence['terminal_window'] is None
    assert evidence['facts']['terminal_window_pose_spread'] == {}
    assert len(calls) == 3
    with pytest.raises(FileExistsError):
        collector.collect_evidence(setup[0], 'unused', tmp_path, tmp_path / 'evidence.json')


def test_native_measurement_allowlist_excludes_task_verdicts_and_controller_phases():
    for name in ('success', 'task.success', 'solver0.phase', 'controller.phase',
                 'solver0.contact.success', 'solver0.contact.sample.0.failed'):
        assert re.fullmatch(collector._MEASUREMENT_PATTERN, name) is None
    for name in ('solver0.contact.phase', 'solver0.contact.sample.2.geometry_time_s',
                 'solver0.contact.sample.2.point.0.body.1', 'solver0.body_pos.13.2'):
        assert re.fullmatch(collector._MEASUREMENT_PATTERN, name)


def test_preintegration_contacts_never_become_current_terminal_contacts():
    runtime = {'index': {'terminal_contacts': {'known': True, 'source_id': 'solver0',
        'branch': 'main', 'step': 10, 't': 1., 'sealed': True, 'source_bundle': {},
        'source': {}, 'owner': 'owner', 'episode': 0, 'phase': 'pre_qpos_integration'}},
        'build': {'contact_observations': {'0': {}}}}
    result = collector._terminal_contacts(runtime, 'main', {'step': 10, 'time_s': 1.})
    assert result['known'] is False


def test_current_contact_packet_requires_source_pose_clock_and_capacity():
    source = {'owner': 'owner', 'initial_episode': 0, 'body_names': ['cube', 'table']}
    terminal = {'step': 10, 'time_s': 1., 'positions': {'cube': [0., 0., 0.02]},
                'orientations_wxyz': {'cube': [1., 0., 0., 0.]}}
    packet = {'known': True, 'source_id': 'solver0', 'branch': 'main', 'step': 10, 't': 1.,
              'sealed': True, 'source_bundle': {}, 'source': source, 'owner': 'owner', 'episode': 0,
              'generation': 10, 'completed_substeps': 10, 'geometry_substep': 10,
              'phase': 'terminal_geometry', 'impulses_known': False,
              'geometry_time_s': 1., 'available_time_s': 1.,
              'geometry_positions': [[0., 0., 0.02], [0., 0., -0.025]],
              'geometry_orientations': [[1., 0., 0., 0.], [1., 0., 0., 0.]],
              'points': [{'bodies': ['cube', 'table'], 'distance': 0., 'position': [0., 0., 0.], 'touching': True}],
              'capacity': dict(count=1, capacity=8, required_count=1, max_contacts_per_pair=4,
                    admitted=1, required_count_exact=1, overflow=0, overflow_stage=0,
                    pair_index_overflow=0, truncated_candidate_count=0, stream_stopped=0,
                    reservation_invariant_violation=0)}
    runtime = {'index': {'terminal_contacts': packet, 'source_bundle': {}},
               'build': {'contact_observations': {'0': source}}}
    result = collector._terminal_contacts(runtime, 'main', terminal)
    assert result['known'] and result['impulses_known'] is False
    assert 'support' not in result
    for field, value in [('phase', 'pre_qpos_integration'), ('geometry_time_s', 0.99),
                         ('points', []), ('geometry_positions', [[0., 0., 0.03], [0., 0., -0.025]])]:
        altered = deepcopy(runtime)
        altered['index']['terminal_contacts'][field] = value
        assert not collector._terminal_contacts(altered, 'main', terminal)['known']
    assert not collector._terminal_contacts(runtime, 'other', terminal)['known']


def test_source_frame_window_must_end_at_the_same_runtime_endpoint(tmp_path, monkeypatch):
    setup = _run(tmp_path)
    _queries(monkeypatch, setup[-1])
    requirement = tmp_path / 'requirement.json'
    _write(requirement, {'final_frames': [0, 10], 'frame_dt': 0.1})
    setup[3].clear()
    setup[3].update(start_frame=0, end_frame=10, source_ref={
        'path': 'requirement.json', 'sha256': collector.digest(requirement)}, pointer='/final_frames',
        sample_dt_seconds=0.1, sample_dt_pointer='/frame_dt')
    evidence = _collect(tmp_path, setup)
    assert not evidence['terminal_window']['complete']
    assert 'source_frame_window_does_not_end_at_runtime_terminal' in evidence['terminal_window']['reasons']


def _dense_run(tmp_path):
    setup = list(_run(tmp_path))
    index = collector.read_json(setup[2])
    index['scene']['dt'] = index['timing']['trace_sample_dt'] = 0.01
    index['timing']['sim_steps'] = 200
    _write(setup[2], index)
    path = setup[0] / 'job.json'
    job = collector.read_json(path)
    job['simulation'].update(dt=0.01, steps=200)
    _write(path, job)
    rows = []
    for step in range(201):
        for name in ('cube', 'table'):
            row = dict.fromkeys(collector._STATE_FIELDS, 0.0)
            row.update(entity=name, step=step, t=step*0.01, quat_w=1.,
                       pos_x=1. if name == 'cube' and step % 10 else 0.)
            rows.append(row)
    setup[-1] = rows
    return setup


def test_dense_trace_projects_original_grid_without_extra_stability_requirements(tmp_path, monkeypatch):
    setup = _dense_run(tmp_path)
    _queries(monkeypatch, setup[-1])
    evidence = _collect(tmp_path, setup)
    tail = evidence['terminal_window']
    assert tail['complete'] and len(tail['samples']) == 11
    assert tail['recorded_sample_dt_seconds'] == 0.01 and tail['sample_dt_seconds'] == 0.1
    assert tail['recorded_sample_count'] == 101
    assert tail['grid_projection']['excluded_intermediate_sample_count'] == 90
    assert tail['grid_projection']['selected_steps'] == list(range(100, 201, 10))
    assert tail['grid_projection']['proves_continuous_stability'] is False
    fact = evidence['facts']['terminal_window_pose_spread']['cube']
    assert fact['available'] and fact['maximum_pairwise_center_distance_m'] == 0
    # A source rule with a 5 mm sampled threshold passes despite 1 m excursions
    # between its requested output times. This says nothing about continuous motion.
    assert fact['maximum_pairwise_center_distance_m'] <= 0.005


@pytest.mark.parametrize('failure', ['missing_grid', 'wrong_clock', 'noninteger_cadence'])
def test_dense_grid_missing_misaligned_or_incommensurate_remains_unknown(tmp_path, monkeypatch, failure):
    setup = _dense_run(tmp_path)
    if failure == 'missing_grid':
        setup[-1] = [row for row in setup[-1] if row['step'] != 150]
    elif failure == 'wrong_clock':
        for row in setup[-1]:
            if row['step'] == 150:
                row['t'] += 0.0001
    else:
        index = collector.read_json(setup[2])
        index['timing']['trace_sample_dt'] = 0.03
        _write(setup[2], index)
    _queries(monkeypatch, setup[-1])
    evidence = _collect(tmp_path, setup)
    assert not evidence['terminal_window']['complete']
    assert not evidence['facts']['terminal_window_pose_spread']['cube']['available']
    if failure == 'noninteger_cadence':
        assert 'source_sample_cadence_not_established' in evidence['terminal_window']['reasons']
    else:
        assert evidence['terminal_window']['grid_projection']['missing_or_ambiguous_required_times_s'] == [1.5]
