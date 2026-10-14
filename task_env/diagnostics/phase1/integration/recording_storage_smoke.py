"""Bounded 500 Hz recorder acceptance subprocess; not FULL qualification.

Run as a module from the repository root. The 2500-transition limit exercises
preclose history and initial native Arm Ramp while retaining incomplete-task
status. Patches are process-local; never run alongside another worker in this
same Python process.
"""
import argparse,json,time,resource
from pathlib import Path
from task_env.diagnostics.phase1.integration import lifecycle_full as full
from task_env.diagnostics.phase1.integration.checkpoint_validation import initialized,restore_boundary,one
from task_env.diagnostics.phase1.integration.replay_preparation import snapshot
from task_env.trajectory.canonical.execution import load as legacy_load,expand_snapshot
from task_env.trajectory.canonical.streaming import load_streaming,validate_streaming
from task_env.artifacts.contracts import CanonicalStateView


def main():
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=('owner-fields-v1','stability-history-refs-v2'),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    original=full.context
    limit=2500
    def bounded_context(*args,**kwargs):
     v=original(*args,**kwargs);v['recording_transition_limit']=limit;return v
    full.context=bounded_context;t=time.perf_counter()
    try:
     report=full.run(provider='mujoco',rate=500,output=a.output,
        trajectory_candidate='guarded-primary-readiness-alternative-8n-v2-v5-clearance',
        recording_storage_variant=a.variant)
    finally:full.context=original
    path=a.output/'execution.h5';x=load_streaming(path)
    assert legacy_load(path)==x
    assert report['live_recording']['roundtrip_exact']
    assert len(x['transitions'])==limit
    v=initialized(x,500)
    for i in (0,1500,1750,2000,2499,2500):restore_boundary(v,x,i,'mujoco')
    v=initialized(x,500)
    s=CanonicalStateView.from_mapping(x['boundaries'][0]['record']['state'])
    assert snapshot(v,s,'mujoco')==expand_snapshot(x['boundaries'][0]['owners'],x['blobs'])
    for i in range(limit):s,f=one(v,x,i,'mujoco')
    assert snapshot(v,s,'mujoco')==expand_snapshot(x['boundaries'][-1]['owners'],x['blobs'])
    summary=validate_streaming(path)
    assert summary['semantic_validation']=='PASS'
    refs=[b['owners']['owners']['stability']['fields']['history']['value'] for b in x['boundaries']]
    if a.variant=='stability-history-refs-v2':assert all(v.get('kind')=='content-ref' for v in refs)
    result={'status':'PASS','scope':'2500-transition 500 Hz real native-ramp prefix recording; NOT FULL or formal D0/D1/D2','variant':a.variant,'transitions':limit,'boundaries':len(x['boundaries']),'physical_duration_s':x['boundaries'][-1]['record']['simulation_time'],'stage_sequence':list(dict.fromkeys(b['stage'] for b in x['boundaries'])),'roundtrip_exact':True,'legacy_reader_exact':True,'sampled_owner_restores_exact':True,'prefix_canonical_reconstruction_exact':True,'semantic_validation':'PASS','logical_hash':report['live_recording']['logical_hash'],'storage_recipe':{k:x['recipe'][k] for k in ('recording_storage_variant','owner_scoped_blob_fields','owner_blob_fields','recorder_source_sha256')},'total_s':time.perf_counter()-t,'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'full_expert_status':'NOT_RUN'}
    with (a.output/'recorder_acceptance.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
