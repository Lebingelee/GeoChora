"""Recorded-contact and source-input contracts, without physics or model calls."""

from copy import deepcopy
import re

import pytest

from validation.adapters import physpi as collector
from validation.adapters.contacts import CONTACT_PATTERN, decode_contact_records
from validation.tests.fixtures.runtime import _run, _queries, _write, _boundary_fixture


def contact_fixture():
    source = {'owner': 'recorded-owner', 'body_names': ['cube', 'table'],
              'body_indices': {'cube': 0, 'table': 1}, 'phase': 'pre_qpos_integration',
              'phase_code': 1, 'substep_dt': .1, 'history_capacity': 1}
    fields = {'known': 1., 'phase': 1., 'available_time_s': 2., 'geometry_time_s': 1.9,
              'episode': 0., 'generation': 20., 'sample_count': 1.}
    sample = {'episode': 0., 'generation': 20., 'completed_substeps': 20., 'geometry_substep': 19.,
              'geometry_time_s': 1.9, 'point_count': 1., 'point.0.body.0': 0., 'point.0.body.1': 1.,
              'point.0.geom.0': 2., 'point.0.geom.1': 4., 'point.0.distance': -.0001,
              'point.0.normal_impulse': .12, 'point.0.position.0': 0., 'point.0.position.1': 0.,
              'point.0.position.2': 0.}
    cap = dict(count=1, capacity=8, required_count=1, required_count_exact=1, admitted=1,
               overflow=0, overflow_stage=0, pair_index_overflow=0, truncated_candidate_count=0,
               stream_stopped=0, reservation_invariant_violation=0, max_contacts_per_pair=4)
    sample.update({'capacity.'+k: float(v) for k, v in cap.items()})
    fields.update({'sample.0.'+k: v for k, v in sample.items()})
    rows = [{'step': 20, 't': 2., 'name': 'solver2.contact.'+k, 'value': v} for k, v in fields.items()]
    runtime = {'start_step': 0, 'start_time': 0., 'dt': .1, 'sample_dt': .1}
    return rows, {'2': source}, runtime


def decode(rows=None, sources=None, runtime=None):
    default_rows, default_sources, default_runtime = contact_fixture()
    return decode_contact_records(default_rows if rows is None else rows,
        default_sources if sources is None else sources, default_runtime if runtime is None else runtime, 2., 2.)


def change(rows, suffix, value):
    next(r for r in rows if r['name'].endswith('contact.'+suffix))['value'] = value


def test_raw_impulses_and_body_identity_retain_the_preintegration_clock():
    result = decode()
    sample = result['records'][0]['samples'][0]
    assert result['status'] == 'available' and result['recorded_grid_complete']
    assert sample['geometry_time_s'] == 1.9 and result['records'][0]['record_time_s'] == 2.
    assert sample['points'][0]['bodies'] == ['cube', 'table']
    assert sample['points'][0]['normal_impulse'] == .12
    assert sample['points'][0]['touching'] is True
    assert result['actual_support'] is None and result['task_success'] is None
    assert not result['current_endpoint_geometry_proven'] and not result['continuous_contact_coverage_proven']
    assert 'force' not in sample['points'][0]


@pytest.mark.parametrize('gap', ['not_recorded', 'disabled', 'overflow', 'missing_point', 'phase'])
def test_evidence_gaps_never_establish_zero_contact(gap):
    rows, sources, runtime = contact_fixture()
    if gap == 'not_recorded': rows = []
    elif gap == 'disabled': rows = [dict(rows[0], value=0.)]
    elif gap == 'overflow': change(rows, 'sample.0.capacity.overflow', 1.)
    elif gap == 'missing_point': rows = [r for r in rows if not r['name'].endswith('point.0.body.1')]
    else: change(rows, 'phase', 2.)
    result = decode(rows, sources, runtime)
    assert result['status'] == 'unavailable' and not result['recorded_grid_complete']
    assert result['reasons'] and not result['records'][0]['known']


def test_observed_empty_manifold_is_distinct_from_missing_recording():
    rows, sources, runtime = contact_fixture()
    rows = [r for r in rows if '.point.0.' not in r['name']]
    change(rows, 'sample.0.point_count', 0.)
    change(rows, 'sample.0.capacity.count', 0.)
    result = decode(rows, sources, runtime)
    assert result['status'] == 'available'
    assert result['records'][0]['samples'][0]['points'] == []
    assert decode([], {}, runtime)['status'] == 'unavailable'


@pytest.mark.parametrize('bad', ['duplicate', 'clock', 'geometry_clock', 'body', 'source',
                                'generation', 'point_index', 'nan', 'unknown_channel'])
def test_corrupt_or_wrong_run_records_are_collection_errors(bad):
    rows, sources, runtime = contact_fixture()
    if bad == 'duplicate': rows.append(deepcopy(rows[0]))
    elif bad == 'clock': rows[0]['t'] = 1.5
    elif bad == 'geometry_clock': change(rows, 'sample.0.geometry_time_s', 2.)
    elif bad == 'body': change(rows, 'sample.0.point.0.body.0', 99.)
    elif bad == 'source': sources['2']['body_indices']['cube'] = 1
    elif bad == 'generation': change(rows, 'sample.0.generation', 19.)
    elif bad == 'point_index': rows.append(dict(rows[-1], name='solver2.contact.sample.0.point.5.distance'))
    elif bad == 'nan': rows[0]['value'] = float('nan')
    else: rows[0]['name'] = 'task.success'
    with pytest.raises(ValueError): decode(rows, sources, runtime)


def test_unknown_sample_in_window_retains_usable_records_and_partial_status():
    rows, sources, runtime = contact_fixture()
    rows.insert(0, {'step': 19, 't': 1.9, 'name': 'solver2.contact.known', 'value': 0.})
    result = decode_contact_records(rows, sources, runtime, 1.9, 2.)
    assert result['status'] == 'partial' and result['usable_sample_count'] == 1
    assert len(result['records']) == 2 and not result['recorded_grid_complete']


def test_whitelist_retains_contact_geometry_but_excludes_task_verdicts():
    assert re.fullmatch(CONTACT_PATTERN, 'solver2.contact.sample.0.geometry_positions.0.1')
    assert re.fullmatch(CONTACT_PATTERN, 'solver2.contact.sample.0.point.0.geom.1')
    for name in ('task.success', 'controller.phase', 'solver2.contact.sample.0.passed'):
        assert re.fullmatch(CONTACT_PATTERN, name) is None


def _contact_run(tmp_path, monkeypatch, *, contacts=True, native=False):
    setup = _run(tmp_path)
    directory, branch, index_path, window, states = setup
    rows, sources, _ = contact_fixture()
    build = {'contact_observations': sources}
    if native:
        build['imports'] = [{'bodies':[{'index':i,'key':n} for i,n in enumerate(('cube','table'))],
                             'joint_layout':{'qpos0':[]}, 'attached_solver_indices':[2]}]
    _write(directory/'trace/build_evidence.json', build)
    index = collector.read_json(index_path)
    index['artifacts']['build_evidence'] = 'trace/build_evidence.json'
    _write(index_path, index)
    (directory/'trace/measurements.parquet').write_bytes(b'retained scalar-contact fixture')
    _queries(monkeypatch, states)
    fallback = collector._public_query
    def query(directory, python, branch, request):
        if 'FROM measurements' not in request['sql']:
            return fallback(directory, python, branch, request)
        columns = ['step','t','name','value']
        selected = list(rows) if contacts else []
        if native:
            for i, name in enumerate(('cube','table')):
                pose = next(r for r in states if r['step']==20 and r['entity']==name)
                for field, values in (('body_pos',[pose['pos_'+a] for a in 'xyz']),
                                      ('body_quat',[pose['quat_'+a] for a in 'wxyz'])):
                    selected.extend({'step':20,'t':2.,'name':f'solver2.{field}.{i}.{a}','value':v}
                                    for a,v in enumerate(values))
        pattern = re.search(r"regexp_full_match\(name, '([^']*)'\)", request['sql']).group(1)
        selected = [r for r in selected if re.fullmatch(pattern,r['name'])]
        return {'ok':True, 'run_dir':str(directory), 'truncated':False,
                'result':{'columns':columns,'rows':[[r[k] for k in columns] for r in selected]}}
    monkeypatch.setattr(collector, '_public_query', query)
    return directory


@pytest.mark.parametrize('contacts', [False, True])
def test_real_collector_sidecar_and_compact_pack_feed_existing_model_transport(tmp_path, monkeypatch, contacts):
    from validation.terminal.reviews import prepare_source_review
    from validation.terminal.dispatch import prepare_terminal_job
    directory = _contact_run(tmp_path, monkeypatch, contacts=contacts)
    evidence = collector.collect_evidence(directory, 'unused', tmp_path, tmp_path/'state.json',
                                          include_native_measurements=True)
    ref = {'path':'state.json','sha256':collector.digest(tmp_path/'state.json')}
    packet = collector.prepare_source_evidence(tmp_path, ref, tmp_path/'prepared')
    assert evidence['facts']['contact_collection_status'] == ('available' if contacts else 'unavailable')
    assert any(item['kind']=='native_contact' for item in packet['evidence'])
    original = collector.read_json(collector.checked_ref(tmp_path,evidence['facts']['native_contacts']))
    prepared_contacts = collector.read_json(tmp_path/'prepared/recorded-contacts.json')
    assert prepared_contacts['records'] == original['records']
    assert prepared_contacts['original_evidence'] == evidence['facts']['native_contacts']
    compact = collector.read_json(tmp_path/'prepared/observed-state.json')
    assert not compact['facts'].get('native_measurements')
    assert (compact['facts']['raw_native_measurement_count'] > 0) is contacts
    request = prepare_source_review({'task_id':'fixture','prompt':'The cube is supported by the table.'},
        packet['endpoint'], required_source_pointers=['/prompt'],
        model_profile={'name':'fixture','reasoning_effort':'none'}, evidence=packet['evidence'])
    job = prepare_terminal_job(request, job_id='offline-evidence', context_id='fresh',
                               transport='external_file', artifact_root=tmp_path)
    assert job['kind']=='terminal-source-review'
    assert 'task_success' not in request['source']
    with pytest.raises(ValueError, match='fresh'):
        collector.prepare_source_evidence(tmp_path, ref, tmp_path/'prepared')


def test_contact_file_hash_and_identity_are_checked_before_pack_publication(tmp_path, monkeypatch):
    directory = _contact_run(tmp_path, monkeypatch)
    state = collector.collect_evidence(directory, 'unused', tmp_path, tmp_path/'state.json', include_native_measurements=True)
    ref = {'path':'state.json','sha256':collector.digest(tmp_path/'state.json')}
    p = tmp_path/state['facts']['native_contacts']['path']
    p.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError): collector.prepare_source_evidence(tmp_path,ref,tmp_path/'bad-pack')
    assert not (tmp_path/'bad-pack').exists()


def test_input_mutation_between_hash_check_and_read_is_rejected(tmp_path, monkeypatch):
    import json
    directory = _contact_run(tmp_path,monkeypatch)
    state=collector.collect_evidence(directory,'unused',tmp_path,tmp_path/'state.json',include_native_measurements=True)
    ref={'path':'state.json','sha256':collector.digest(tmp_path/'state.json')}
    original=collector.checked_ref
    mutated=[]
    def changed(root,reference):
        p=original(root,reference)
        if p.name=='state.contacts.json' and not mutated:
            content=collector.read_json(p)
            content['records'][0]['samples'][0]['points'][0]['normal_impulse']=123.
            p.write_text(json.dumps(content),encoding='utf-8')
            mutated.append(True)
        return p
    monkeypatch.setattr(collector,'checked_ref',changed)
    with pytest.raises(ValueError,match='hash mismatch'):
        collector.prepare_source_evidence(tmp_path,ref,tmp_path/'changed-pack')
    assert not (tmp_path/'changed-pack').exists()


def test_boundary_image_pack_preserves_actual_pixels_and_terminal_clock(tmp_path, monkeypatch):
    setup, _, _, refs = _boundary_fixture(tmp_path, monkeypatch)
    packet = collector.prepare_source_evidence(tmp_path, refs()[0], tmp_path/'images', boundary_views_ref=refs()[1])
    assert [e['kind'] for e in packet['evidence'] if 'capture_verified' in e] == ['native_context_image','native_image']
    assert packet['missing_structured_evidence'] == ['contact_observations_not_collected', 'runtime_asset_record_not_available']
    assert packet['asset_collection_status'] == 'unavailable'


def test_native_supplement_collects_contacts_and_packages_them_with_poses(tmp_path, monkeypatch):
    directory = _contact_run(tmp_path, monkeypatch, native=True)
    collector.collect_evidence(directory,'unused',tmp_path,tmp_path/'base.json')
    ref = {'path':'base.json','sha256':collector.digest(tmp_path/'base.json')}
    native = collector.collect_native_evidence(directory,'unused',tmp_path,tmp_path/'native',base_evidence_ref=ref)
    assert native['contact_measurements_collected'] and native['contact_collection_status']=='available'
    native_ref = {'path':'native/native-evidence.json','sha256':collector.digest(tmp_path/'native/native-evidence.json')}
    packet = collector.prepare_source_evidence(tmp_path,ref,tmp_path/'inputs',native_evidence_ref=native_ref)
    assert {'raw_state','native_contact'} <= {x['kind'] for x in packet['evidence']}


def test_missing_measurement_file_is_an_explicit_gap_without_a_measurement_query(tmp_path, monkeypatch):
    setup = _run(tmp_path)
    calls = _queries(monkeypatch,setup[-1])
    result = collector.collect_evidence(setup[0],'unused',tmp_path,tmp_path/'missing.json',include_native_measurements=True)
    assert result['facts']['contact_collection_status']=='unavailable'
    assert not any('FROM measurements' in x['sql'] for x in calls)


def test_substep_history_preserves_both_physical_geometry_times():
    rows,sources,runtime = contact_fixture()
    sources['2'].update(substep_dt=.05,history_capacity=2)
    change(rows,'sample_count',2.)
    change(rows,'generation',40.)
    change(rows,'geometry_time_s',1.95)
    original = [r for r in rows if '.sample.0.' in r['name']]
    rows += [dict(r,name=r['name'].replace('.sample.0.','.sample.1.')) for r in original]
    for i in (0,1):
        change(rows,f'sample.{i}.completed_substeps',39.+i)
        change(rows,f'sample.{i}.geometry_substep',38.+i)
        change(rows,f'sample.{i}.generation',39.+i)
        change(rows,f'sample.{i}.geometry_time_s',1.9+i*.05)
    got = decode(rows,sources,runtime)
    assert got['usable_sample_count']==2 and got['status']=='available'
    assert [x['geometry_time_s'] for x in got['records'][0]['samples']] == [1.9,1.95]


def test_relative_branch_clock_retains_its_original_step_and_time():
    rows,sources,runtime = contact_fixture()
    runtime.update(start_step=10,start_time=1.)
    got=decode(rows,sources,runtime)
    assert got['status']=='available' and got['records'][0]['record_step']==20


def test_corrupt_collection_cli_reports_an_error_not_an_unknown_judgment(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(sys.path))
    result=subprocess.run([sys.executable,'-X','utf8','-B','-m',collector.__name__,
        '--run-directory',str(tmp_path/'missing-run'),'--runtime-python',sys.executable,
        '--root',str(tmp_path),'--output',str(tmp_path/'never.json')],
        cwd=Path(collector.__file__).parents[2],env=env,capture_output=True,text=True,timeout=30)
    import json
    message=json.loads(result.stdout)
    assert result.returncode==1 and message['status']=='collection_failed'
    assert 'terminal' not in message and not (tmp_path/'never.json').exists()
