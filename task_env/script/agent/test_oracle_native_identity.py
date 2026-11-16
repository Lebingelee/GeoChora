"""V3 Oracle identity must bind the recorded source and reset to the request."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle_candidate as oracle

@pytest.mark.parametrize('field', ['seed','execution_identity_sha256','reset_plan_identity_hash','reset_sample_id','source_id','source_closure_digest','delivery_manifest_sha256','provider','backend','device'])
def test_v3_oracle_rejects_foreign_recording(tmp_path, field):
    profile={k:'correct' for k in ('execution_identity_sha256','reset_plan_identity_hash','reset_sample_id','source_id','source_closure_digest','delivery_manifest_sha256','provider','backend','device')}
    actual=copy.deepcopy(profile)
    worker={'seed':7,'core_commit':'commit','core_dirty':False,'compiled':{'spec_sha256':'spec','artifact_hash':'artifact'},'facts':{'recording_identity':{'seed':7,'profile':profile}}}
    details={'seed':7,'episode':{'transitions':1},'controller_identity':'controller','expert_identity':'expert','tool_sha256':{}}
    if field=='seed': worker['seed']=999
    else: actual[field]='foreign'
    summary={'schema':oracle.GENERIC_V3_SCHEMA,'status':'PASS','t_plus_one_valid':True,'task_artifact_sha256':'artifact','controller_identity':'controller','expert_identity':'expert','transitions':1,'provider_provenance_present':True,'source_provenance_present':True,'storage_roundtrip':'PASS'}
    h5=tmp_path/'oracle.h5';h5.write_bytes(b'test')
    with patch.object(oracle,'_inspect',return_value=(SimpleNamespace(returncode=0),summary)), patch.object(oracle,'_snapshot_sources',return_value={}), patch('task_env.recorders.load_structured_control_records_h5',return_value={'env_meta':{'reference_profile':actual}}):
        with pytest.raises(ValueError,match='storage/identity'):
            oracle._storage_checks(h5,tmp_path,ctx={'core_commit':'commit'},spec=SimpleNamespace(spec_sha256=lambda:'spec'),artifact_hash='artifact',details=details,deadline=0,worker=worker)
