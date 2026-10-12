"""Opt-in R5 execution adapter: coordinator owns its memory, recorder observes."""
import argparse
import hashlib
import json
from pathlib import Path
from .grasp_height_probe import context
from .stable_grasp import worker
from .replay_preparation import snapshot
from ..p1_2_runtime import execution
from ....trajectory.canonical.contracts import EpisodeMetadata, BoundaryRecord, TransitionRecord
from ....trajectory.canonical.execution import ExecutionRecorder, save, load
from ....controllers.canonical.contracts import digest


class LiveRecording:
    def __init__(self, value, provider, session, audit, sample, realized, state, feedback, info, *, output):
        self.value,self.provider,self.audit,self.output=value,provider,audit,output
        self.session=session
        metadata=EpisodeMetadata('canonical-trajectory-metadata-v0',value['artifact'].identity_hash,
            sample,realized,execution(provider),{'build':json.dumps(worker.provider_build_identity(provider),sort_keys=True)},
            {'recipe':value['recipe_identity']},value['artifact'].timebase,value['controller_identity'],
            value['solution_identity'],digest({'controller':value['controller_identity'],'readiness':'close_only'}),
            digest({'control':'absolute_pose/world/wxyz','interval':'equal_rate'}),sample.task_seed,'regression')
        initial_snapshot=snapshot(value,state,provider)
        owner_schema={name:{'version':p['version'],'source_sha256':p['source_sha256'],'fields':list(p['fields'])} for name,p in initial_snapshot['owners'].items()}
        self.recorder=ExecutionRecorder(metadata,{'schema':'r5-execution-recipe-v1',
            'recorder_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'factory':'task_env.diagnostics.phase1.integration.grasp_height_probe.context',
            'artifact':value['artifact'].to_mapping(),'recipe_identity':value['recipe_identity'],
            'cadence':'outer-equal-rate','owner_schema':owner_schema,'stages':list(value['solution'].STAGES),'grasp_offset_z_m':.045895,'absolute_height_gate':False,
            'force_limit_N':10.,'authorization_deadline_s':1.5,'fallback':False})
        self.recorder.value['recipe']['episode_role'] = value.get('_recording_role', 'regression')
        self.recorder.boundary(self.boundary(state,feedback,info),snapshot(value,state,provider),value['solution'].stage,info['task_metrics'],self.native_time())

    def native_time(self):
        if self.provider=='mujoco':
            return float(self.session._data.time)
        from ....environment import SnapshotRequest
        return float(self.session._boundary.read_snapshot(SnapshotRequest(qacc=False,ctrl=False,body_pose=False,site_pose=False,simulation_time=True)).simulation_time)

    def boundary(self, state, feedback, info):
        readiness=self.value['controller'].readiness(state,feedback)
        metrics=info['task_metrics']
        return BoundaryRecord(state.control_step,state.simulation_time,state,feedback,readiness,
            {k:float(v) for k,v in metrics.items()},bool(metrics.get('task_success',False)),self.value['solution'].failed)

    def begin(self, state, request, stage, diagnostics):
        self.request,self.stage,self.diagnostics=request,stage,dict(diagnostics)
        self.recorder.begin(state.control_step,self.value['artifact'].timebase.physics_dt,
            self.value['artifact'].timebase.control_substeps)

    def complete(self, state, feedback, info, evaluation, row):
        planned=not bool(self.diagnostics.get('readiness_hold',False))
        transition=TransitionRecord(self.request,self.canonical,self.target,self.applied,
            float(evaluation.reward),False,False,self.stage,
            {k:json.dumps(v,sort_keys=True) for k,v in self.diagnostics.items()},planned,not planned)
        self.recorder.append(transition,self.boundary(state,feedback,info),
            snapshot(self.value,state,self.provider),self.value['solution'].stage,self.audit.boundaries[-1],info['task_metrics'],self.native_time())
        # Same live values must agree; no post-hoc invention of applied inputs.
        last=self.recorder.value['transitions'][-1]
        assert last['record']['requested_action']==row['requested_action']
        assert last['record']['controller_target']['arm_position']==row['joint_target']
        assert last['record']['applied_control']==row['applied_control']
        assert len(last['interval']['substeps'])==len(row['gripper_inner_trace'])
        for a,b in zip(last['interval']['substeps'],row['gripper_inner_trace']):
            assert a['applied']==b['applied_control'] and digest(a['target'])==b['target_hash']
            assert a['updated']==b['inner_update_performed']
        assert self.recorder.value['boundaries'][-1]['record']['feedback']==row['feedback']
        assert self.recorder.value['boundaries'][-1]['record']['readiness']==row['readiness']

    def finish(self, report):
        probe = report.get('probe')
        if probe == 'FULL':
            stop_reason = ('canonical_task_success' if report.get('pass') and report.get('canonical_task_success')
                           else report.get('failure_boundary') or 'full_expert_incomplete')
        elif probe == 'T1':
            stop_reason = ('t1_loaded_transport_complete' if report.get('pass')
                           else report.get('failure_boundary') or 't1_incomplete')
        else:
            stop_reason = ('g0_verified' if report.get('pass')
                           else report.get('failure_boundary') or 'bounded_recording')
        value=self.recorder.freeze(stop_reason)
        path=self.output/'execution.h5';save(path,value);loaded=load(path)
        if loaded!=value:raise AssertionError('H5 first logical divergence')
        return {'schema':value['schema'],'pass':True,'path':str(path),
            'logical_hash':digest(value),'T':len(value['transitions']),'boundaries':len(value['boundaries']),
            'trace_exact':True,'roundtrip_exact':True,'first_divergence':None}


def main():
    p=argparse.ArgumentParser();p.add_argument('--provider',choices=('geophys','mujoco'),required=True)
    p.add_argument('--rate',type=int,choices=(500,100,50),required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);v=context(a.rate)
    v['live_recording_factory']=lambda *args:LiveRecording(*args,output=a.output)
    if a.limit:v['recording_transition_limit']=a.limit
    worker.CLOSE_TIME_LIMIT_S=1.5
    report=worker.run_loaded(v,a.provider,a.output,'G0');report['solution_events']=v['solution'].events
    worker._write(a.output/'report.json',report)
    print(json.dumps({k:report.get(k) for k in ('pass','failure_boundary','recording_error','live_recording')}),flush=True)
    if not report.get('live_recording',{}).get('pass') or (not a.limit and not report['pass']):raise SystemExit(1)

if __name__=='__main__':main()
