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


def test_actual_v3_oracle_preserves_external_stop():
    directory=native_fixture()
    result=check(directory)
    assert result.status=='pass'
    assert result.details['verification']['outcome']['end_reason']=='external_stop'
    assert result.details['verification']['outcome']['solution_completed'] is None
    assert result.details['episode']['solution_done'] is True


@pytest.mark.parametrize('mutation', ('seed','reset','provider','close','retirement','outcome','snapshot'))
def test_v3_oracle_rejects_foreign_or_incomplete_evidence(tmp_path,mutation):
    source=native_fixture()
    directory=tmp_path/'oracle'
    shutil.copytree(source,directory,copy_function=shutil.copy2)
    report_path=directory/'oracle.check.json'
    worker_path=directory/'native/worker_receipt.json'
    native_path=directory/'native/native_run_receipt.json'
    report=json.loads(report_path.read_text())
    worker=json.loads(worker_path.read_text())
    native=json.loads(native_path.read_text())
    if mutation=='seed':
        report['details']['seed']=999
    elif mutation=='reset':
        worker['facts']['recording_identity']['profile']['reset_sample_id']='foreign'
    elif mutation=='provider':
        worker['facts']['recording_identity']['profile']['provider']='mujoco'
    elif mutation=='close':
        worker['facts']['close_succeeded']=False
    elif mutation=='retirement':
        native['process_group_retired']=False
        report['details']['native_run']=native
    elif mutation=='outcome':
        worker['facts']['verification']['outcome']['solution_completed']=True
        report['details']['verification']=worker['facts']['verification']
    elif mutation=='snapshot':
        (directory/'source_snapshot/oracle_candidate.py').write_text('tampered\n')
    report_path.write_text(json.dumps(report))
    worker_path.write_text(json.dumps(worker))
    native_path.write_text(json.dumps(native))
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
