"""Provider-owned diagnostic sidecars and bounded native restore assessment."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .live_recording import LiveRecording
from .grasp_height_probe import context
from .stable_grasp import worker
from .checkpoint_validation import checkpoints, restore_boundary
from .replay_preparation import snapshot
from ..nutassembly.common import observation, METADATA
from ....trajectory.canonical.execution import load, expand_snapshot
from ....artifacts.contracts import CanonicalStateView


def capture(session,provider,path):
    arrays={}
    if provider=='mujoco':
        mj=session._mj;spec=mj.mjtState.mjSTATE_INTEGRATION
        vector=np.empty(mj.mj_stateSize(session._model,spec));mj.mj_getState(session._model,session._data,vector,spec)
        arrays={'integration':vector,'completed_actuator_force':session._completed_actuator_force.copy(),
                'actuator_forcerange':session._model.actuator_forcerange.copy(),
                'actuator_forcelimited':session._model.actuator_forcelimited.copy()}
        api='MuJoCo public mjSTATE_INTEGRATION/getState/setState + mj_forward; session completed-force cache'
    else:
        arrays={k:np.asarray(v).copy() for k,v in session._boundary.snapshot_state().arrays.items()}
        api='GeoPhysRuntimeBoundary public snapshot_state/restore_state'
    arrays['session_control_step']=np.array([session._control_step],dtype=np.int64)
    arrays['session_native_steps']=np.array([getattr(session,'_native_steps',session._control_step*session._artifact.timebase.control_substeps)],dtype=np.int64)
    np.savez_compressed(path,**arrays)
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'api':api,
            'arrays':{k:{'dtype':v.dtype.str,'shape':list(v.shape)} for k,v in arrays.items()}}


def restore_native(session,provider,path):
    with np.load(path,allow_pickle=False) as data:arrays={k:data[k].copy() for k in data.files}
    step=int(arrays.pop('session_control_step')[0]);native=int(arrays.pop('session_native_steps')[0])
    if provider=='mujoco':
        mj=session._mj;session._model.actuator_forcerange[:]=arrays['actuator_forcerange'];session._model.actuator_forcelimited[:]=arrays['actuator_forcelimited']
        mj.mj_setState(session._model,session._data,arrays['integration'],mj.mjtState.mjSTATE_INTEGRATION)
        mj.mj_forward(session._model,session._data)
        session._completed_actuator_force=arrays['completed_actuator_force'].copy();session._native_steps=native
    else:
        from ....environment import PhysicsStateSnapshot
        session._boundary.restore_state(PhysicsStateSnapshot(arrays=arrays))
    session._control_step=step;session._inner_interval_active=False


def state_error(a,b):
    delta=max(abs(a.joint_position[k]-b.joint_position[k]) for k in a.joint_position)
    pose=max(float(np.linalg.norm(np.array(a.pose_world[k].position)-b.pose_world[k].position)) for k in a.pose_world)
    return {'max_joint_position_error_rad_or_m':delta,'max_world_position_error_m':pose,'exact':a.to_mapping()==b.to_mapping()}


class NativeRecording(LiveRecording):
    def __init__(self,*args,points,**kwargs):
        self.points=points;self.captured={}
        super().__init__(*args,**kwargs);self.capture_due(0)
    def capture_due(self,k):
        for name,step in self.points.items():
            if step==k:
                path=self.output/f'{name}_native.npz';self.captured[name]=capture(self.session,self.provider,path)
    def complete(self,*args):
        super().complete(*args);self.capture_due(len(self.recorder.value['transitions']))
    def finish(self,report):
        base=super().finish(report)
        x=self.recorder.value;self.audit.close()
        payload=assess_native(x,self.points,self.captured,self.provider,round(1/self.value['artifact'].timebase.control_dt))
        (self.output/'native_restoration.json').write_text(json.dumps(payload,indent=2));base['native_restore_report']=str(self.output/'native_restoration.json');return base


def assess_native(x,points,captured,provider,hz):
    value=context(hz)
    session,audit,sample,realized,s,f,c=worker._reset(value,provider)
    obs,info,_=observation(s,value['artifact']);value['solution'].reset(obs,info,METADATA)
    results=[]
    try:
        for name,k in points.items():
            row={'checkpoint':name,'control_step':k,'native_sidecar':captured[name],'steps':min(12,len(x['transitions'])-k)}
            restore_native(session,provider,Path(captured[name]['path']))
            audit.count=k*value['artifact'].timebase.control_substeps
            # Restore canonical owners against the recorded canonical boundary, separately.
            reference,_=restore_boundary(value,x,k,provider)
            actual=session.snapshot();feedback=session.control_feedback(actual)
            row['immediate_state']=state_error(actual,reference)
            row['first_physical_divergence']=None if row['immediate_state']['exact'] else {'boundary':k,'phase':'restore'}
            row['first_target_divergence']=None;row['max_world_position_error_m']=row['immediate_state']['max_world_position_error_m']
            row['next_target_exact']=True;row['owner_continuation_exact']=True
            for j in range(k,k+row['steps']):
                public=value['solution'].act();before=value['solution'].stage
                obs,info,_=observation(actual,value['artifact'])
                actual,feedback,obs,info,evaluation,trace=worker._execute(value,provider,session,audit,c,actual,feedback,public.action,before,dict(public.diagnostics),info)
                expected=x['transitions'][j]
                if trace['requested_action']!=expected['record']['requested_action'] and row['first_target_divergence'] is None:
                    row['first_target_divergence']={'boundary':j,'phase':'action'}
                target_equal=(trace['final_inner_target_hash']==expected['record']['applied_control']['target_hash'] and
                    len(trace['gripper_inner_trace'])==len(expected['interval']['substeps']) and
                    all(a['target_hash']==b['applied']['target_hash'] and a['applied_control']==b['applied'] for a,b in zip(trace['gripper_inner_trace'],expected['interval']['substeps'])))
                if not target_equal:
                    row['next_target_exact']=False
                    if row['first_target_divergence'] is None:row['first_target_divergence']={'boundary':j,'phase':'target'}
                value['solution'].observe(obs,evaluation.reward,False,False,info,readiness=c.readiness(actual,feedback))
                expected_state=CanonicalStateView.from_mapping(x['boundaries'][j+1]['record']['state']);error=state_error(actual,expected_state)
                row['max_world_position_error_m']=max(row['max_world_position_error_m'],error['max_world_position_error_m'])
                if not error['exact'] and row['first_physical_divergence'] is None:row['first_physical_divergence']={'boundary':j+1,'phase':'physics'}
                if snapshot(value,actual,provider)!=expand_snapshot(x['boundaries'][j+1]['owners'],x['blobs']):row['owner_continuation_exact']=False
            row['physical_continuation_exact']=row['first_physical_divergence'] is None
            results.append(row);print(provider,name,row['physical_continuation_exact'],row['first_target_divergence'],row['max_world_position_error_m'],flush=True)
    finally:audit.close();session.close()
    payload={'provider':provider,'points':points,'canonical_level_separately_tested':True,'results':results,
             'all_native_exact':all(z['physical_continuation_exact'] for z in results),'scope':'same-provider public integration-state diagnostic; no private solver state',
             'diagnostic_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return payload



def main():
    p=argparse.ArgumentParser();p.add_argument('--provider',required=True);p.add_argument('--rate',type=int,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--restore-only',action='store_true');a=p.parse_args()
    x=load(a.reference);points=checkpoints(x)
    if a.restore_only:
        captured={name:{'path':str(a.output/f'{name}_native.npz'),'sha256':hashlib.sha256((a.output/f'{name}_native.npz').read_bytes()).hexdigest()} for name in points}
        result=assess_native(x,points,captured,a.provider,a.rate)
        (a.output/'native_restoration.json').write_text(json.dumps(result,indent=2));return
    del x
    a.output.mkdir(parents=True,exist_ok=False);v=context(a.rate)
    v['live_recording_factory']=lambda *args:NativeRecording(*args,output=a.output,points=points)
    worker.CLOSE_TIME_LIMIT_S=1.5;report=worker.run_loaded(v,a.provider,a.output,'G0')
    worker._write(a.output/'report.json',report)
    print(json.dumps({k:report.get(k) for k in ('pass','recording_error','live_recording')}),flush=True)
    if not report.get('live_recording',{}).get('pass'):raise SystemExit(1)
if __name__=='__main__':main()
