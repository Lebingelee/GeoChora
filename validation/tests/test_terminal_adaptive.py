"""Independent recorded-value fixtures for adaptive delivery and call admission.

No SDK or physical reference labels. Counterexamples inside a source grid are
retained unchanged; authored model responses only exercise protocol and routing.
"""
from copy import deepcopy
import hashlib
import json

import pytest

from validation.terminal.evidence_views import prepare_evidence_views, EvidenceViewError
from validation.terminal.source_run import prepare_source_run, execute_source_run
from validation.terminal.dispatch import make_terminal_result
from validation.tests.fixtures.source_reviews import inputs, candidate, verification, dispatch, PROFILE
from validation.terminal.reviews import prepare_source_review, admit_source_review
from validation.protocol import InvalidGenerationProtocol


def save(root, name, body, *, kind='raw_state', identity='recorded'):
    path = root / name
    path.write_text(json.dumps(body),encoding='utf-8')
    return {'id':identity,'kind':kind,'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'episode_id':'fixture-run','endpoint_id':'actual-end'}


def recording():
    return {'schema_version':'native-samples/0.2','source_grid_steps':list(range(0,101,10)),
        'recorded_sample_grid_complete':True,'expected_steps':list(range(101)),
        'limits':['Body origins are not source centers.'], 'units':{'position':'m'},
        'solver_layouts':{'0':{'full_native_actuator_inventory_known':False}},
        'solver_mappings':{'0':{'body_names':['A','B','unselected-drawer']}},
        'samples':[{'step':i,'time_s':3*i/100,'solvers':{'0':{
            'body_positions':[[i/100,0,1],[0,0,1],[0,0,.2 if i==50 else 0]],'ctrl':[.3]}}} for i in range(101)]}


def prepare(root, *, mode='boundary', body=None):
    request = inputs(root,image=True)
    request = prepare_source_review(request['source'],request['endpoint'],required_source_pointers=request['required_source_pointers'],
        model_profile=PROFILE,evidence=[save(root,'recorded.json',body or recording()),request['evidence'][-1]])
    view = prepare_evidence_views(root,request['evidence'],request['endpoint'],root/'views',mode=mode)
    adaptive = prepare_source_review(request['source'],request['endpoint'],required_source_pointers=request['required_source_pointers'],
        model_profile=PROFILE,evidence=view['evidence'],evidence_catalogue=view['catalogue'])
    return request,view,adaptive


def query(identity='recorded', **changes):
    return {'evidence_id':identity,'source_pointers':['/requirements/0'],'entities':['A','B'],
        'channels':['pose'],'time_range_s':[0,3],'sampling':'source_grid','reason':'Check the requested sampled relation.',**changes}


def response(request,value=None,queries=()):
    answer=candidate(request,value)
    answer.update(schema_version='terminal-source-review-response/0.2',evidence_requests=list(queries))
    return answer


def test_boundary_preserves_all_entities_semantic_limits_and_real_final_values(tmp_path):
    original,view,request = prepare(tmp_path)
    selected=json.loads((tmp_path/view['evidence'][-2]['path']).read_text(encoding='utf-8'))['observations']
    assert [row['step'] for row in selected['samples']]==[0,100]
    assert selected['samples'][-1]==recording()['samples'][-1]
    assert selected['solver_mappings']['0']['body_names']==['A','B','unselected-drawer']
    assert selected['solver_layouts']==recording()['solver_layouts']
    assert selected['limits']==recording()['limits'] and selected['units']=={'position':'m'}
    assert 'recorded_sample_grid_complete' not in selected
    assert view['evidence'][0]==original['evidence'][-1] # every original image retained
    assert request['source']==original['source']


def test_window_uses_exact_source_grid_and_retains_intermediate_counterexample(tmp_path):
    original,_,_=prepare(tmp_path)
    expanded=prepare_evidence_views(tmp_path,original['evidence'],original['endpoint'],tmp_path/'expanded',mode='expanded',queries=[query()])
    selected=json.loads((tmp_path/expanded['evidence'][0]['path']).read_text(encoding='utf-8'))['observations']['samples']
    assert [r['step'] for r in selected]==list(range(0,101,10))
    assert selected[5]['solvers']['0']['body_positions'][2][2]==.2
    assert [r['solvers']['0']['body_positions'] for r in selected]==[r['solvers']['0']['body_positions'] for r in recording()['samples'][::10]]
    assert all('ctrl' not in r['solvers']['0'] for r in selected)
    assert expanded['outcomes'][0]['missing_requested_boundaries_s']==[]


def test_boundary_does_not_leak_hidden_spread_or_contact_window(tmp_path):
    body=recording()
    body.update(body_pose_spread={'A':{'max_translation':17}},contact_samples=[{'time_s':i,'contact':True} for i in range(4)])
    _,view,_=prepare(tmp_path,body=body)
    selected=json.loads((tmp_path/view['evidence'][-2]['path']).read_text(encoding='utf-8'))
    assert 'max_translation' not in json.dumps(selected)
    assert [r['time_s'] for r in selected['observations']['contact_samples']]==[0,3]


def test_contact_phase_and_available_geometry_clocks_remain_unchanged(tmp_path):
    base=inputs(tmp_path)
    rows=[{'record_time_s':t,'record_step':int(t*10),'phase':'pre_qpos_integration',
        'geometry_time_s':t-.01,'available_time_s':t,'known':True,'points':[]} for t in (0.,1.,3.)]
    evidence=[save(tmp_path,'contacts.json',{'schema_version':'recorded-native-contacts/0.1','records':rows,
        'sources':{'0':{'body_names':['A','B']}}},kind='native_contact')]
    view=prepare_evidence_views(tmp_path,evidence,base['endpoint'],tmp_path/'contacts')
    document=json.loads((tmp_path/view['evidence'][0]['path']).read_text(encoding='utf-8'))
    assert document['observations']['records']==[rows[0],rows[-1]]


@pytest.mark.parametrize('record_time,admitted', [(3.5500000000000003, True), (3.56, False)])
def test_adaptive_contact_catalogue_endpoint_roundoff_keeps_raw_clock(tmp_path, record_time, admitted):
    base = inputs(tmp_path)
    endpoint = {**base['endpoint'], 'time_s': 3.55}
    row = {'record_time_s': record_time, 'record_step': 355, 'phase': 'pre_qpos_integration',
           'geometry_time_s': 3.549, 'available_time_s': record_time, 'known': True, 'points': []}
    reference = save(tmp_path, 'contacts.json', {
        'schema_version': 'recorded-native-contacts/0.1', 'records': [row],
        'sources': {'0': {'body_names': ['A', 'B']}}}, kind='native_contact')
    original_bytes = (tmp_path / 'contacts.json').read_bytes()
    request = prepare_source_review(base['source'], endpoint,
        required_source_pointers=base['required_source_pointers'], model_profile=PROFILE, evidence=[reference])
    if not admitted:
        with pytest.raises(InvalidGenerationProtocol, match='data range'):
            prepare_source_run(request, tmp_path, tmp_path / 'run',
                verification_model_profile=PROFILE, evidence_mode='adaptive')
        return
    prepare_source_run(request, tmp_path, tmp_path / 'run',
        verification_model_profile=PROFILE, evidence_mode='adaptive')
    job = json.loads((tmp_path / 'run/judge/job.json').read_text(encoding='utf-8'))
    assert job['request']['evidence_catalogue']['entries'][0]['time_range_s'] == [3.55, 3.55]
    document = json.loads((tmp_path / 'run/evidence-initial/0-view.json').read_text(encoding='utf-8'))
    assert document['observations']['records'] == [row]
    assert (tmp_path / 'contacts.json').read_bytes() == original_bytes
    assert not (tmp_path / 'run/execution.claim').exists()


@pytest.mark.parametrize('changes',[{'entities':['foreign']},{'evidence_id':'foreign'},
    {'source_pointers':['/requirements/99']},{'time_range_s':[0,4]},{'channels':['predicate']},{'sampling':'interpolate'}])
def test_invalid_requests_fail_admission_before_any_data_delivery(tmp_path,changes):
    _,_,request=prepare(tmp_path)
    answer=response(request,queries=[query(**changes)])
    with pytest.raises(InvalidGenerationProtocol):
        admit_source_review(request,answer,dispatch=dispatch(request,answer))


def test_unavailable_channel_is_explicit_and_no_clamping(tmp_path):
    original,_,_=prepare(tmp_path)
    missing=prepare_evidence_views(tmp_path,original['evidence'],original['endpoint'],tmp_path/'missing',mode='expanded',queries=[query(channels=['contact'])])
    assert missing['evidence']==[] and missing['outcomes'][0]['reason']=='requested_channels_not_recorded'
    sparse=prepare_evidence_views(tmp_path,original['evidence'],original['endpoint'],tmp_path/'partial',mode='expanded',queries=[query(time_range_s=[.01,2.99])])
    assert sparse['outcomes'][0]['missing_requested_boundaries_s']==[.01,2.99]
    assert sparse['outcomes'][0]['delivered_times_s']==[3*i/100 for i in range(10,100,10)]


def test_assets_cache_binds_real_supplied_values_without_inventing_missing_properties(tmp_path):
    original,first,_=prepare(tmp_path)
    record={'schema_version':'terminal-asset-properties/0.1','endpoint':original['endpoint'],
        'source_refs':[],'comparisons':[{'entity':'A','property':'mass','expected':1.,'observed':1.,'native_binding_verified':True}]}
    evidence=[*original['evidence'],save(tmp_path,'properties.json',record,kind='measurement',identity='asset-properties')]
    second=prepare_evidence_views(tmp_path,evidence,original['endpoint'],tmp_path/'with-assets',asset_cache=tmp_path/'shared-cache')
    third=prepare_evidence_views(tmp_path,evidence,original['endpoint'],tmp_path/'reuse',asset_cache=tmp_path/'shared-cache')
    assert second['asset_checks']==third['asset_checks'] and first['asset_checks']!=second['asset_checks']
    receipt=json.loads((tmp_path/second['asset_checks']['path']).read_text(encoding='utf-8'))
    assert receipt['checks'][0]['status']=='recorded_values_match'
    assert receipt['asset_integrity'] is None and 'material' in receipt['missing_properties']
    (tmp_path/second['asset_checks']['path']).write_text('{}')
    with pytest.raises(EvidenceViewError,match='cached asset'):
        prepare_evidence_views(tmp_path,evidence,original['endpoint'],tmp_path/'tampered-cache',asset_cache=tmp_path/'shared-cache')


def test_asset_receipt_upgrade_keeps_legacy_cache_immutable(tmp_path):
    import hashlib
    original, first, _ = prepare(tmp_path)
    current = json.loads((tmp_path/first['asset_checks']['path']).read_text(encoding='utf-8'))
    legacy = {key:value for key,value in current.items() if key != 'comparison_summary'}
    identity = hashlib.sha256(json.dumps({'endpoint':original['endpoint'],'inputs':legacy['input_files']},
        ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
    legacy['input_digest'] = identity
    cache = tmp_path/'legacy-cache'
    cache.mkdir()
    path = cache/(identity+'.json')
    path.write_text(json.dumps(legacy),encoding='utf-8')
    before = path.read_bytes()
    upgraded = prepare_evidence_views(tmp_path, original['evidence'], original['endpoint'], tmp_path/'upgraded', asset_cache=cache)
    assert upgraded['asset_checks']['path'] != path.relative_to(tmp_path).as_posix()
    assert path.read_bytes() == before


def host(calls, *, channel='pose', final=True):
    def invoke(input_path,output_path):
        job=json.loads(input_path.read_text(encoding='utf-8'))['job']; calls.append(job)
        request=job['request']
        if job['kind']=='terminal-source-verification':
            answer=verification(request);answer['schema_version']='terminal-source-verification-response/0.2'
        elif request['evidence_round']==0:
            answer=response(request,queries=[query(channels=[channel])])
        else:
            answer=response(request,final)
        result=make_terminal_result(job,json.dumps(answer),dispatch_id=job['job_id']+'/actual',
            context_id=job['context_id'],model_profile=PROFILE,image_receipts=[{
                'evidence_id':r['evidence_id'],'sha256':r['sha256'],'method':'external_image_content','reference':'test-image'} for r in job['required_images']])
        output_path.write_text(json.dumps(result),encoding='utf-8')
    return invoke


@pytest.mark.parametrize('value',[True,False,None])
def test_one_expansion_fresh_judgment_independent_release_and_no_fourth_call(tmp_path,value):
    original,_,_=prepare(tmp_path)
    directory=tmp_path/'run'
    prepare_source_run(original,tmp_path,directory,verification_model_profile=PROFILE,evidence_mode='adaptive')
    calls=[]
    result=execute_source_run(directory,host(calls,final=value))
    assert result['terminal'] is value and result['status']!='execution_failed',result
    assert result['requirement_summary']['authority'] == 'candidate_checklist_not_independent_verification'
    assert result['requirement_summary']['terminal_categories']['unclassified']['candidate_value'] is value
    assert result['requirements'] == response(calls[1]['request'], value)['requirements']
    assert len(calls)==(2 if value is None else 3)
    assert len({j['context_id'] for j in calls})==len(calls)
    assert 'judgment_response' not in calls[1]['request']
    assert calls[1]['request']['evidence_round']==1
    if value is not None: assert calls[2]['request']['judgment_request']==calls[1]['request']
    assert execute_source_run(directory,lambda *_:pytest.fail('no repeated payment'))==result


def test_unrecorded_evidence_stops_unknown_without_additional_model_calls(tmp_path):
    original,_,_=prepare(tmp_path)
    directory=tmp_path/'run'
    prepare_source_run(original,tmp_path,directory,verification_model_profile=PROFILE,evidence_mode='adaptive')
    calls=[];result=execute_source_run(directory,host(calls,channel='contact'))
    assert result['status']=='judgment_unknown' and len(calls)==1
    assert result['evidence_expansion'][0]['status']=='unavailable'


def test_view_budget_and_tamper_are_errors_not_unknown(tmp_path):
    original,_,_=prepare(tmp_path)
    with pytest.raises(EvidenceViewError,match='budget'):
        prepare_evidence_views(tmp_path,original['evidence'],original['endpoint'],tmp_path/'small',max_characters=1)
    assert not (tmp_path/'small').exists()
    (tmp_path/'recorded.json').write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):
        prepare_evidence_views(tmp_path,original['evidence'],original['endpoint'],tmp_path/'changed')


def test_collector_boundary_package_can_expand_original_records_in_runner(tmp_path):
    original,_,boundary=prepare(tmp_path)
    directory=tmp_path/'composed'
    plan=prepare_source_run(boundary,tmp_path,directory,verification_model_profile=PROFILE,evidence_mode='adaptive')
    assert {r['id']:r for r in plan['original_request']['evidence']}=={r['id']:r for r in original['evidence']}
    calls=[];result=execute_source_run(directory,host(calls))
    assert result['terminal'] is True and len(calls)==3,result
    document=json.loads((directory/'evidence-expanded/0-view.json').read_text(encoding='utf-8'))
    assert [r['step'] for r in document['observations']['samples']]==list(range(0,101,10))


def test_recorded_sampling_keeps_off_grid_counterexample_and_static_mapping_metadata_is_archival(tmp_path):
    body=recording();body['samples'][51]['solvers']['0']['body_positions'][2][2]=9
    original,_,_=prepare(tmp_path,body=body)
    expanded=prepare_evidence_views(tmp_path,original['evidence'],original['endpoint'],tmp_path/'full-grid',mode='expanded',queries=[query(sampling='recorded')])
    document=json.loads((tmp_path/expanded['evidence'][0]['path']).read_text(encoding='utf-8'))
    assert len(document['observations']['samples'])==101
    assert document['observations']['samples'][51]['solvers']['0']['body_positions'][2][2]==9
    mapping=save(tmp_path,'mapping.json',{'recorded_sample_grid_complete':True,'source_window':{'sample_dt':.03},
        'limits':['Eight recorded controls are not a full actuator inventory.']},kind='measurement',identity='mapping')
    selected=prepare_evidence_views(tmp_path,[mapping],original['endpoint'],tmp_path/'mapping-view')
    document=json.loads((tmp_path/selected['evidence'][0]['path']).read_text(encoding='utf-8'))
    assert 'recorded_sample_grid_complete' not in document['observations']
    assert document['observations']['limits']==['Eight recorded controls are not a full actuator inventory.']


def test_requested_named_entities_and_channels_fit_without_thinning_time_grid(tmp_path):
    base=inputs(tmp_path)
    names=['A',*[f'other-{i}' for i in range(29)]]
    body={'limits':['Positions are body origins.'],'samples':[{'time':i/10,
        'positions':{name:[i/10,0,1] for name in names},'orientations':{name:[1,0,0,0] for name in names},
        'arm_qpos':[.4],'arm_qvel':[.1],'capture_phase':'original_record'} for i in range(31)]}
    before=deepcopy(body)
    evidence=[save(tmp_path,'named.json',body)]
    view=prepare_evidence_views(tmp_path,evidence,base['endpoint'],tmp_path/'requested-only',mode='expanded',
        queries=[query(entities=['A'],sampling='recorded')],max_characters=10000)
    document=json.loads((tmp_path/view['evidence'][0]['path']).read_text(encoding='utf-8'))
    samples=document['observations']['samples']
    assert [row['time'] for row in samples]==[i/10 for i in range(31)]
    assert all(row['positions']=={'A':[row['time'],0,1]} and set(row['orientations'])=={'A'} for row in samples)
    assert all('arm_qvel' not in row and row['arm_qpos']==[.4] and row['capture_phase']=='original_record' for row in samples)
    assert document['observations']['limits']==before['limits'] and body==before


def test_state_window_and_native_tracked_rows_apply_same_requested_scope(tmp_path):
    base=inputs(tmp_path)
    rows=[{'step':i,'time_s':3*i/100,'positions':{'A':[i/100,0,1],'B':[2,0,1]},
        'orientations_wxyz':{'A':[1,0,0,0],'B':[1,0,0,0]},
        'linear_velocities_m_s':{'A':[1,0,0],'B':[0,0,0]}} for i in range(101)]
    state={'initial':rows[0],'terminal':rows[-1],'identities':{'A':{},'B':{}},
           'terminal_window':{'samples':rows,'grid_projection':{'selected_steps':list(range(0,101,10))}}}
    native=recording()
    native['tracked_state_rows']=[{'step':i,'t':3*i/100,'entity':name,'pos_x':i/100,'linvel_x':1.} for i in range(101) for name in ('A','B')]
    evidence=[save(tmp_path,'state.json',state,identity='state'),save(tmp_path,'native.json',native,identity='native')]
    view=prepare_evidence_views(tmp_path,evidence,base['endpoint'],tmp_path/'all-paths',mode='expanded',
        queries=[query('state',entities=['A']),query('native',entities=['A'])])
    first=json.loads((tmp_path/view['evidence'][0]['path']).read_text(encoding='utf-8'))['observations']
    assert first['initial']==rows[0] and first['terminal']==rows[-1] # all boundary objects preserved
    selected=first['requested_window_samples']
    assert [r['step'] for r in selected]==list(range(0,101,10))
    assert all(set(r['positions'])=={'A'} and 'linear_velocities_m_s' not in r for r in selected)
    second=json.loads((tmp_path/view['evidence'][1]['path']).read_text(encoding='utf-8'))['observations']['tracked_state_rows']
    assert [r['step'] for r in second]==list(range(0,101,10))
    assert all(r['entity']=='A' and 'linvel_x' not in r for r in second)


def test_boundary_only_state_delivers_available_boundaries_without_claiming_middle_samples(tmp_path):
    base = inputs(tmp_path)
    state = {'initial': {'time_s': 0., 'positions': {'A': [0., 0., 0.]}},
             'terminal': {'time_s': 3., 'positions': {'A': [1., 0., 0.]}},
             'identities': {'A': 'actual-body'}, 'terminal_window': None}
    evidence = [save(tmp_path, 'state.json', state, identity='state')]
    view = prepare_evidence_views(tmp_path, evidence, base['endpoint'], tmp_path / 'expanded',
        mode='expanded', queries=[query('state', entities=['A'], sampling='recorded')])
    assert view['outcomes'][0]['status'] == 'delivered'
    assert view['outcomes'][0]['delivered_times_s'] == [0., 3.]
    rows = json.loads((tmp_path / view['evidence'][0]['path']).read_text())['observations']['requested_window_samples']
    assert rows == [state['initial'], state['terminal']]
    middle = prepare_evidence_views(tmp_path, evidence, base['endpoint'], tmp_path / 'missing-middle',
        mode='expanded', queries=[query('state', entities=['A'], sampling='recorded', time_range_s=[1., 2.])])
    assert middle['outcomes'][0]['reason'] == 'no_recorded_samples_for_selection'
