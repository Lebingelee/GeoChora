"""Real v3 Oracle readback and source-closure tamper checks; no physics launch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_package as judge
from harness_spec_schema import CandidateSpec

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT/'workspace/harness/isaac-core-repair-20261104-002'


def native_fixture():
    if not (FIXTURE/'oracle-seed0/oracle.h5').is_file():
        pytest.skip('requires the preserved real Isaac Oracle fixture')
    return FIXTURE/'oracle-seed0'


def check(directory):
    report=json.loads((directory/'oracle.check.json').read_text())
    return judge.check_oracle(directory,report['spec_sha256'],report['artifact_hash'],
                              report['core_commit'],'isaacsim')


def test_legacy_v3_storage_is_readable_but_cannot_be_promoted():
    directory=native_fixture()
    report=json.loads((directory/'oracle.check.json').read_text())
    from task_env.recorders import load_structured_control_records_h5
    records=load_structured_control_records_h5(directory/'oracle.h5')
    assert records['outcome'].end_reason=='external_stop'
    assert records['outcome'].solution_completed is None
    assert report['details']['episode']['solution_done'] is True
    with pytest.raises(ValueError,match='recorded replay provenance missing'):
        check(directory)



@pytest.mark.parametrize('mutation',('none','seed','core_revision','source_bytes','reset_plan','execution'))
def test_v3_recorded_provenance_binds_typed_h5_data(tmp_path,mutation):
    from types import SimpleNamespace
    from unittest.mock import patch
    from dataclasses import replace
    from catalog_query import build_catalog
    from harness_compiler import compile_candidate
    import catalog_query
    fixture=native_fixture()
    spec=CandidateSpec.load(fixture/'candidate.spec.json')
    delivery=json.loads((fixture/'catalog.json').read_text())['isaac_route']['delivery_manifest']
    context=catalog_query.core_context(ROOT)
    clean={**context,'core_dirty':False}
    with patch.object(catalog_query,'core_context',return_value=clean):
        catalog=build_catalog(ROOT,providers=['isaacsim'],isaac_delivery_manifest=delivery)
        catalog['core_dirty']=False
        compiled=compile_candidate(spec,catalog,provider='isaacsim')
    initial=compiled.initial_value
    runtime=initial['f06_pickcube_isaac_input']
    plan=runtime.reset_plan
    execution=runtime.execution
    sha=hashlib.sha256(b'committed source').hexdigest()
    c={'artifact_hash':compiled.artifact_hash,'source_sha256':{'task_env/example.py':sha},
       'route':compiled.route}
    d={'seed':plan.reset_sample.task_seed,'tool_sha256':{}}
    profile={'recording_provenance_schema':'pickcube-isaac-replay-provenance-v1',
        'task_seed':d['seed'],'reset_plan_v1':plan.to_mapping(),
        'execution_spec_v1':execution.to_mapping(),'reset_plan_identity_hash':plan.identity_hash,
        'reset_sample_id':plan.reset_sample.sample_id,'scene_identity_hash':plan.role_binding.scene_identity_hash,
        'execution_identity_sha256':execution.identity_hash,'provider':'isaacsim','backend':'cuda','device':'cuda:0',
        'source_revision':context['core_commit'],'source_sha256':c['source_sha256'],
        'task_recipe':initial['resolved_configuration']['task_recipe']}
    commit=context['core_commit']
    if mutation=='seed':
        d['seed']+=1
    elif mutation=='core_revision':
        commit='f'*40
    elif mutation=='source_bytes':
        c['source_sha256']={'task_env/example.py':'0'*64}
        profile['source_sha256']=c['source_sha256']
    elif mutation=='reset_plan':
        profile['reset_plan_identity_hash']='0'*64
    elif mutation=='execution':
        profile['execution_identity_sha256']='0'*64
    shutil.copy2(fixture/'candidate.spec.json',tmp_path/'candidate.spec.json')
    result=SimpleNamespace(returncode=0,stdout=b'committed source')
    with patch.object(judge.subprocess,'run',return_value=result):
        if mutation=='none':
            judge.check_v3_recorded_provenance(tmp_path,profile,d,c,spec.spec_sha256(),commit)
        else:
            with pytest.raises(ValueError,match='Oracle'):
                judge.check_v3_recorded_provenance(tmp_path,profile,d,c,spec.spec_sha256(),commit)


@pytest.mark.parametrize('mutation',('seed','reset','provider','close','retirement','outcome','snapshot'))
def test_v3_native_closure_and_storage_checks_remain_independent(tmp_path,mutation):
    from unittest.mock import patch
    source=native_fixture()
    directory=tmp_path/'oracle'
    shutil.copytree(source,directory,copy_function=shutil.copy2)
    rp=directory/'oracle.check.json';wp=directory/'native/worker_receipt.json'
    np=directory/'native/native_run_receipt.json'
    report=json.loads(rp.read_text());worker=json.loads(wp.read_text());native=json.loads(np.read_text())
    if mutation=='seed': report['details']['seed']=999
    elif mutation=='reset': worker['facts']['recording_identity']['profile']['reset_sample_id']='foreign'
    elif mutation=='provider': worker['facts']['recording_identity']['profile']['provider']='mujoco'
    elif mutation=='close': worker['facts']['close_succeeded']=False
    elif mutation=='retirement':
        native['process_group_retired']=False;report['details']['native_run']=native
    elif mutation=='outcome':
        worker['facts']['verification']['outcome']['solution_completed']=True
        report['details']['verification']=worker['facts']['verification']
    elif mutation=='snapshot': (directory/'source_snapshot/oracle_candidate.py').write_text('tampered')
    rp.write_text(json.dumps(report));wp.write_text(json.dumps(worker));np.write_text(json.dumps(native))
    # Legacy bytes exercise only the independent native/storage checks. The
    # stronger recorded-provenance boundary is tested separately with real contracts.
    with patch.object(judge,'check_v3_recorded_provenance'):
        with pytest.raises(ValueError,match='Oracle'):
            check(directory)


def test_synthetic_binding_keeps_original_identity(tmp_path):
    asset=tmp_path/'box.xml';asset.write_bytes(b'<mujoco/>')
    sha=hashlib.sha256(asset.read_bytes()).hexdigest()
    (tmp_path/'asset_bundle.json').write_text(json.dumps({'synthetic':True,'assets':[
        {'uid':'mock-box','path':'box.xml','sha256':sha,'source_request_uid':'original'}]}))
    from types import SimpleNamespace
    spec=SimpleNamespace(object_config={'object_uid':'mock-box','asset_sha256':sha})
    binding=judge.check_asset_binding(spec,tmp_path,'mujoco')
    assert binding['synthetic'] is True and binding['original_request_uid']=='original'
    asset.write_bytes(b'foreign')
    with pytest.raises(ValueError,match='asset bytes'):
        judge.check_asset_binding(spec,tmp_path,'mujoco')


def test_builtin_source_requires_pinned_manifest(tmp_path):
    spec_path=FIXTURE/'check20/candidate.spec.json'
    if not spec_path.is_file():
        pytest.skip('requires preserved candidate spec')
    (tmp_path/'delivery.json').write_text('{}')
    (tmp_path/'asset_bundle.json').write_text(json.dumps({
        'schema_version':'harness-builtin-source-bundle-v1','synthetic':False,'assets':[
            {'uid':'cube-v1','source_kind':'core-builtin-pinned-usd',
             'delivery_manifest':'delivery.json','sha256':'0'*64}]}))
    with pytest.raises(ValueError,match='pin mismatch'):
        judge.check_asset_binding(CandidateSpec.load(spec_path),tmp_path,'isaacsim')
