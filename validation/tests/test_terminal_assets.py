"""Asset readback provenance and the actual collector -> review-view seam.

Synthetic public runtime records protect wiring and negative controls; native
engine executions are retained separately and are not implied by these tests.
"""
from copy import deepcopy
import json
import pytest

from validation.tests.fixtures.runtime import _run, _queries, _write
from validation.adapters import physpi
from validation.adapters.assets import collect_asset_properties, PROPERTIES
from validation.terminal.evidence_views import prepare_evidence_views


def reference(path, root):
    return {'path': path.relative_to(root).as_posix(), 'sha256': physpi.digest(path)}


def capture(tmp_path, monkeypatch, name, *, changed=None, corrupt=None, recorded=True):
    base = tmp_path / name
    base.mkdir()
    setup = _run(base)
    old = setup[0]
    directory = old.rename(base / name)
    index_path = directory / 'manifest.json'
    index = physpi.read_json(index_path)
    index['run_id'] = name
    job = physpi.read_json(directory / 'job.json')
    job['run_id'] = name
    _write(directory / 'job.json', job)
    props = {'collision_geometry': [{'kind': 'box', 'half_extents_m': [.02, .03, .04]}],
             'mass': {'mass_kg': .2}, 'material': {'friction': .5}, 'joint_limits': []}
    if changed:
        props[changed] = {'deliberately_changed': True}
    bodies = [{'body_index': 0, 'name': 'unseen-widget', 'properties': props, 'missing': {}}]
    snapshots = []
    for boundary, step, time in [('initial', 0, 0.), ('final', 20, 2.)]:
        snapshots.append({'schema_version': 'engine-asset-properties/0.1', 'run_id': name,
            'code_sha256': index['code_sha256'], 'boundary': boundary, 'branch': None,
            'step': step, 't': time, 'known': True, 'engine': 'geophys', 'engine_version': 'fixture', 'backend': 'cpu',
            'observed': {'engine': 'geophys', 'engine_source': {'base_commit': '1'*40, 'local_files_sha256': {}},
                'solvers': [{'solver_index': 0, 'properties': {
                'schema_version': 'rigid-asset-properties/0.1', 'units': 'SI',
                'representation': 'independent-fixture/0.1', 'bodies': deepcopy(bodies)}}]}})
    if corrupt:
        corrupt(snapshots)
    if recorded:
        index['artifacts']['asset_properties'] = 'asset-properties.json'
        _write(directory / 'asset-properties.json', {'schema_version': 'runtime-asset-properties/0.1', 'snapshots': snapshots})
    _write(index_path, index)
    _queries(monkeypatch, setup[-1])
    path = tmp_path / (name + '-state.json')
    physpi.collect_evidence(directory, 'unused', tmp_path, path)
    return reference(path, tmp_path)


@pytest.mark.parametrize('changed', [None, *PROPERTIES])
def test_actual_readback_comparison_reaches_review_and_counts_each_property(tmp_path, monkeypatch, changed):
    baseline = capture(tmp_path, monkeypatch, 'original')
    candidate = capture(tmp_path, monkeypatch, 'candidate', changed=changed)
    packet = physpi.prepare_source_evidence(tmp_path, candidate, tmp_path/'review', asset_baseline_ref=baseline,
                                             model_view='boundary')
    assert packet['asset_collection_status'] == 'available'
    view = packet['evidence_view']
    catalogue = next(e for e in view['catalogue']['entries'] if e['id'] == 'asset_properties')
    assert catalogue['channels'] == ['asset_properties']
    assert catalogue['entities'] == ['solver0/unseen-widget']
    receipt = physpi.read_json(tmp_path / view['asset_checks']['path'])
    assert receipt['comparison_summary']['recorded_values_match'] == (3 if changed else 4)
    assert receipt['comparison_summary']['recorded_values_differ'] == bool(changed)
    assert receipt['asset_integrity'] is None
    query = {'evidence_id': 'asset_properties', 'entities': ['solver0/unseen-widget'], 'channels': ['asset_properties'],
             'source_pointers': ['/requirements/0'], 'time_range_s': [2., 2.], 'sampling': 'recorded', 'reason': 'source preservation'}
    expanded = prepare_evidence_views(tmp_path, view['original_evidence'], packet['endpoint'], tmp_path/'expanded',
                                      mode='expanded', queries=[query])
    assert expanded['outcomes'][0]['status'] == 'delivered'
    assert expanded['outcomes'][0]['delivered_times_s'] == [2.]
    body = physpi.read_json(tmp_path/expanded['evidence'][0]['path'])['observations']
    assert len(body['comparisons']) == 4


@pytest.mark.parametrize('recorded', [False, True])
def test_missing_historical_capture_or_baseline_stays_unknown(tmp_path, monkeypatch, recorded):
    candidate = capture(tmp_path, monkeypatch, 'candidate', recorded=recorded)
    packet = collect_asset_properties(tmp_path, candidate)
    assert packet['comparisons'] == [] and packet['asset_integrity'] is None
    assert packet['reason'] == ('original_asset_baseline_not_provided' if recorded else 'runtime_asset_record_not_available')


def test_native_asset_counterexample_is_endpoint_observation_but_receipt_alone_is_not(tmp_path, monkeypatch):
    from validation.terminal.reviews import prepare_source_review, admit_source_review
    from validation.tests.fixtures.source_reviews import PROFILE, dispatch
    baseline = capture(tmp_path, monkeypatch, 'original')
    candidate = capture(tmp_path, monkeypatch, 'candidate', changed='mass')
    packet = physpi.prepare_source_evidence(tmp_path, candidate, tmp_path/'inputs', asset_baseline_ref=baseline,
                                             model_view='boundary')
    assert next(e for e in packet['evidence'] if e['id']=='asset_properties')['kind']=='raw_state'
    assert next(e for e in packet['evidence'] if e['id']=='asset_record_checks')['kind']=='measurement'
    request = prepare_source_review({'requirements':['Preserve the original asset mass at the endpoint.']},
        packet['endpoint'], required_source_pointers=['/requirements/0'], evidence=packet['evidence'], model_profile=PROFILE)
    answer = {'schema_version':'terminal-source-review-response/0.1','request_sha256':request['request_sha256'],
        'terminal':False,'reason':'Native mass differs from the independent original baseline.',
        'requirements':[{'id':'mass','category':'asset_integrity','scope':'terminal','source_pointers':['/requirements/0'],
            'text':'Preserve original mass','value':False,'reason':'Actual and original mass records differ.',
            'evidence_ids':['asset_properties']}]}
    admitted = admit_source_review(request, answer, dispatch=dispatch(request, answer))
    assert admitted['candidate_terminal'] is False and admitted['terminal'] is None
    answer['requirements'][0]['evidence_ids'] = ['asset_record_checks']
    with pytest.raises(ValueError, match='native endpoint observations'):
        admit_source_review(request, answer, dispatch=dispatch(request, answer))


def test_missing_only_asset_inventory_does_not_gain_native_observation_authority(tmp_path, monkeypatch):
    candidate = capture(tmp_path, monkeypatch, 'candidate', recorded=False)
    packet = physpi.prepare_source_evidence(tmp_path, candidate, tmp_path/'inputs')
    assert next(e for e in packet['evidence'] if e['id']=='asset_properties')['kind']=='measurement'


@pytest.mark.parametrize('field,value', [('run_id','other'),('code_sha256','0'*64),('step',19),('t',1.9)])
def test_wrong_run_source_or_clock_rejected(tmp_path, monkeypatch, field, value):
    candidate = capture(tmp_path, monkeypatch, 'candidate', corrupt=lambda rows: rows[-1].update({field:value}))
    with pytest.raises(ValueError, match='mismatch'):
        collect_asset_properties(tmp_path, candidate)


def test_candidate_cannot_self_certify_original_assets(tmp_path, monkeypatch):
    candidate = capture(tmp_path, monkeypatch, 'candidate')
    with pytest.raises(ValueError, match='own original asset baseline'):
        collect_asset_properties(tmp_path, candidate, baseline_state_ref=candidate)


def test_missing_native_property_and_body_never_match(tmp_path, monkeypatch):
    baseline = capture(tmp_path, monkeypatch, 'original')
    def missing(rows):
        props = rows[-1]['observed']['solvers'][0]['properties']['bodies'][0]['properties']
        props['mass'] = None
    candidate = capture(tmp_path, monkeypatch, 'candidate', corrupt=missing)
    packet = collect_asset_properties(tmp_path, candidate, baseline_state_ref=baseline)
    assert next(c for c in packet['comparisons'] if c['property']=='mass')['observed'] is None
    packet = collect_asset_properties(tmp_path, candidate, baseline_state_ref=baseline,
                                      entity_map={'solver0/unseen-widget':'solver7/absent'})
    assert all(c['observed'] is None and not c['native_binding_verified'] for c in packet['comparisons'])


def test_asset_bytes_are_frozen_when_state_is_collected(tmp_path, monkeypatch):
    candidate = capture(tmp_path, monkeypatch, 'candidate')
    path = tmp_path/'candidate/candidate/asset-properties.json'
    packet = physpi.read_json(path)
    packet['snapshots'][-1]['observed']['solvers'][0]['properties']['bodies'][0]['properties']['mass'] = 999
    _write(path, packet)
    with pytest.raises(ValueError, match='hash mismatch'):
        collect_asset_properties(tmp_path, candidate)


def test_engine_source_change_requires_a_matching_reference(tmp_path, monkeypatch):
    baseline = capture(tmp_path, monkeypatch, 'original')
    def changed(rows):
        rows[-1]['observed']['engine_source']['local_files_sha256']['reader.py'] = 'f'*64
    candidate = capture(tmp_path, monkeypatch, 'candidate', corrupt=changed)
    with pytest.raises(ValueError, match='different engine'):
        collect_asset_properties(tmp_path, candidate, baseline_state_ref=baseline)


def test_explicit_native_mapping_reuses_comparison_for_renamed_scene(tmp_path, monkeypatch):
    baseline = capture(tmp_path, monkeypatch, 'original')
    def rename(rows):
        for row in rows:
            row['observed']['solvers'][0]['solver_index'] = 7
            row['observed']['solvers'][0]['properties']['bodies'][0]['name'] = 'renamed-other-asset'
    candidate = capture(tmp_path, monkeypatch, 'candidate', corrupt=rename)
    packet = collect_asset_properties(tmp_path, candidate, baseline_state_ref=baseline,
        entity_map={'solver0/unseen-widget':'solver7/renamed-other-asset'})
    assert packet['collection_status']=='available'
    assert all(c['expected']==c['observed'] and c['native_binding_verified'] for c in packet['comparisons'])


def test_large_mesh_values_fit_adaptive_budget_and_one_changed_vertex_is_detected(tmp_path, monkeypatch):
    def mesh(rows):
        for row in rows:
            row['observed']['solvers'][0]['properties']['bodies'][0]['properties']['collision_geometry'] = {
                'native_vertices_m':[[i/10000, .2, .3] for i in range(30000)]}
    baseline = capture(tmp_path, monkeypatch, 'original', corrupt=mesh)
    def changed(rows):
        mesh(rows)
        rows[-1]['observed']['solvers'][0]['properties']['bodies'][0]['properties']['collision_geometry']['native_vertices_m'][-1][0] += .0001
    candidate = capture(tmp_path, monkeypatch, 'candidate', corrupt=changed)
    packet = physpi.prepare_source_evidence(tmp_path, candidate, tmp_path/'inputs', asset_baseline_ref=baseline,
                                             model_view='boundary')
    view = packet['evidence_view']
    receipt = physpi.read_json(tmp_path/view['asset_checks']['path'])
    check = next(c for c in receipt['checks'] if c['property']=='collision_geometry')
    assert check['status']=='recorded_values_differ'
    assert check['expected']['schema_version']=='canonical-json-digest/0.1'
    assert check['expected']['sha256']!=check['observed']['sha256']
    assert sum((tmp_path/item['path']).stat().st_size for item in view['evidence'])<250000
    original = next(item for item in view['original_evidence'] if item['id']=='asset_properties')
    assert len(physpi.read_json(tmp_path/original['path'])['comparisons'][0]['expected']['native_vertices_m'])==30000


def test_source_run_exposes_asset_receipt_without_promoting_comparison_to_judgment(tmp_path, monkeypatch):
    from validation.terminal.reviews import prepare_source_review
    from validation.terminal.source_run import prepare_source_run, execute_source_run
    from validation.terminal.dispatch import make_terminal_result
    from validation.tests.fixtures.source_reviews import PROFILE
    baseline = capture(tmp_path, monkeypatch, 'original')
    candidate = capture(tmp_path, monkeypatch, 'candidate')
    packet = physpi.prepare_source_evidence(tmp_path, candidate, tmp_path/'inputs', asset_baseline_ref=baseline)
    request = prepare_source_review({'requirements':['Reach the target and preserve original asset parameters.']},
        packet['endpoint'], required_source_pointers=['/requirements/0'], evidence=packet['evidence'], model_profile=PROFILE)
    run = tmp_path/'run'
    prepare_source_run(request, tmp_path, run, verification_model_profile=PROFILE, evidence_mode='adaptive')
    def host(input_path, output_path):
        job = physpi.read_json(input_path)['job']
        req = job['request']
        answer = {'schema_version':'terminal-source-review-response/0.2','request_sha256':req['request_sha256'],
                  'terminal':None,'reason':'Synthetic unknown goal; matching assets do not establish the goal.',
                  'requirements':[{'id':'goal','scope':'terminal','category':'goal','source_pointers':['/requirements/0'],
                    'text':'Target reached','value':None,'reason':'Not evaluated by this fixture.','evidence_ids':[]}],
                  'evidence_requests':[]}
        result = make_terminal_result(job, json.dumps(answer), dispatch_id=job['job_id']+'/fixture',
                    context_id=job['context_id'], model_profile=job['model_profile'], image_receipts=[])
        output_path.write_text(json.dumps(result),encoding='utf-8')
    result = execute_source_run(run, host)
    assert result['status']=='judgment_unknown', result
    assert result['terminal'] is None and result['review_status']=='unknown_not_reviewed'
    assert result['asset_comparison_summary']['recorded_values_match']==4
    assert result['requirement_summary']['authority']=='candidate_checklist_not_independent_verification'
