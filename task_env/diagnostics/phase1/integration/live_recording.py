"""Opt-in R5 execution adapter: coordinator owns its memory, recorder observes."""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter
from .grasp_height_probe import context
from .stable_grasp import worker
from .replay_preparation import snapshot
from ..p1_2_runtime import execution
from ....trajectory.canonical.contracts import EpisodeMetadata, BoundaryRecord, TransitionRecord
from ....trajectory.canonical.execution import ExecutionRecorder
from ....trajectory.canonical.streaming import (
    VERIFICATION_VERSION, save_streaming, verify_roundtrip,
)
from ....controllers.canonical.contracts import digest


class LiveRecording:
    def __init__(self, value, provider, session, audit, sample, realized, state, feedback, info, *, output):
        self.value,self.provider,self.audit,self.output=value,provider,audit,output
        self.session=session
        lifecycle = getattr(value['solution'], 'lifecycle', None)
        self._lifecycle_event_cursor = len(lifecycle.events) if lifecycle is not None else 0
        native_gripper = (getattr(value['controller'].inner, 'version', None)
                          == 'native-gripper-500hz-v1')
        cadence_identity = 'fixed-native-500hz-v1' if native_gripper else 'equal_rate'
        metadata=EpisodeMetadata('canonical-trajectory-metadata-v0',value['artifact'].identity_hash,
            sample,realized,execution(provider),{'build':json.dumps(worker.provider_build_identity(provider),sort_keys=True)},
            {'recipe':value['recipe_identity']},value['artifact'].timebase,value['controller_identity'],
            value['solution_identity'],digest({'controller':value['controller_identity'],
                'readiness_policy':value.get('close_authorization_policy','close_only')}),
            digest({'control':'absolute_pose/world/wxyz','interval':cadence_identity}),sample.task_seed,'regression')
        initial_snapshot=snapshot(value,state,provider)
        owner_schema={name:{'version':p['version'],'source_sha256':p['source_sha256'],'fields':list(p['fields'])} for name,p in initial_snapshot['owners'].items()}
        owner_blob_fields = ('_actions', '_transition_guard_state', '_close_authorization',
                             '_last_guard_decision', 'events', 'lifecycle_state')
        self.recorder=ExecutionRecorder(metadata,{'schema':'r5-execution-recipe-v1',
            'recorder_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'recording_io_contract':VERIFICATION_VERSION,
            'owner_blob_fields':list(owner_blob_fields),
            'factory':'task_env.diagnostics.phase1.integration.grasp_height_probe.context',
            'artifact':value['artifact'].to_mapping(),'recipe_identity':value['recipe_identity'],
            'cadence':cadence_identity,'owner_schema':owner_schema,'stages':list(value['solution'].STAGES),'grasp_offset_z_m':.045895,'absolute_height_gate':False,
            'force_limit_N':10.,'authorization_deadline_s':1.5,'fallback':False,
            'completion_policy':(lifecycle.completion_policy.value if lifecycle is not None else 'implicit_legacy_on_success'),
            'lifecycle_version':(lifecycle.version if lifecycle is not None else None),
            'solution_version':getattr(value['solution'],'version',None),
            'close_authorization_policy':value.get('close_authorization_policy'),
            'allowed_close_authorization_guards':value.get('allowed_close_authorization_guards',
                ['controller_close_ready'])}, content_fields=owner_blob_fields)
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
            {k:float(v) for k,v in metrics.items()},bool(metrics.get('task_success',False)),
            bool(info.get('task_failure',False)))

    def begin(self, state, request, stage, diagnostics):
        self.request,self.stage,self.diagnostics=request,stage,dict(diagnostics)
        self.recorder.begin(state.control_step,self.value['artifact'].timebase.physics_dt,
            self.value['artifact'].timebase.control_substeps)

    def complete(self, state, feedback, info, evaluation, row):
        planned=not bool(self.diagnostics.get('readiness_hold',False))
        diagnostics = dict(self.diagnostics)
        lifecycle = getattr(self.value['solution'], 'lifecycle', None)
        if lifecycle is not None:
            new_events = lifecycle.events[self._lifecycle_event_cursor:]
            if new_events:
                diagnostics['solution_lifecycle_events'] = new_events
            self._lifecycle_event_cursor = len(lifecycle.events)
        transition=TransitionRecord(self.request,self.canonical,self.target,self.applied,
            float(evaluation.reward),False,False,self.stage,
            {k:json.dumps(v,sort_keys=True) for k,v in diagnostics.items()},planned,not planned)
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
            stop_reason = (report.get('completion_reason')
                           if report.get('pass') and report.get('completion_reason')
                           else report.get('failure_boundary') or 'full_expert_incomplete')
        elif probe == 'T1':
            stop_reason = ('t1_loaded_transport_complete' if report.get('pass')
                           else report.get('failure_boundary') or 't1_incomplete')
        else:
            stop_reason = ('g0_verified' if report.get('pass')
                           else report.get('failure_boundary') or 'bounded_recording')
        started = perf_counter()
        value=self.recorder.freeze(stop_reason)
        freeze_s = perf_counter() - started
        path=self.output/'execution.h5'
        saved = save_streaming(path, value)
        verified = verify_roundtrip(path, value)
        if saved['logical_hash'] != verified['logical_hash']:
            raise AssertionError('saved/verified logical hash mismatch')
        return {'schema':value['schema'],'pass':True,'path':str(path),
            'logical_hash':verified['logical_hash'],'T':len(value['transitions']),'boundaries':len(value['boundaries']),
            'verification':verified,
            'io_profile':{'freeze_validate_s':freeze_s,**saved,
                          'read_compare_hash_s':verified['read_compare_hash_s']},
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
