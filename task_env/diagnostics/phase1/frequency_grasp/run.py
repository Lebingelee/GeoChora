"""Versioned, opt-in development runs; frozen G0/T1 gates stay unchanged."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET
from scipy.spatial.transform import Rotation
import numpy as np
from ...phase1.integration import loaded_episode
from ...phase1.integration.grasp_height_probe import context as frozen_context
from ...phase1.nutassembly_r5_architecture import tracking_worker as worker
from ....tasks.nut_assembly import canonical_artifact
from ....planners import AbsolutePosePlanner, AbsolutePosePlannerConfig
from .native import NativeObserver,canonical_digest
from ...phase1.integration.live_recording import LiveRecording
from ....artifacts import PoseWorld
from ....artifacts.execution import ResetSample


def context(rate,case):
    if rate==20:
        canonical_artifact.PROFILES={**canonical_artifact.PROFILES,'NA-TB20':(25,.05)}
    v=frozen_context(rate)
    if case=='candidate_noslip2':
        profile_path=Path(__file__).parent/'profiles/mujoco_noslip2_v1.json'
        profile=json.loads(profile_path.read_text())
        xml=ET.fromstring(v['source'].scene_source.xml)
        option=xml.find('option');option.set('noslip_iterations',str(profile['model_option_overrides']['noslip_iterations']))
        scene=replace(v['source'].scene_source,xml=ET.tostring(xml,encoding='unicode'))
        v['source']=replace(v['source'],scene_source=scene)
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'contact_profile':profile,
            'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest(),'source_xml_sha256':hashlib.sha256(scene.xml.encode()).hexdigest()})
        v['_contact_profile']=profile
        v['_source_xml_sha256']=hashlib.sha256(scene.xml.encode()).hexdigest()
    if case in ['slow_lift','airborne_hold','lateral']:
        # Only the emitted lift motion changes: same endpoint, duration doubled
        # within the unchanged 6s stage-plan budget. Acquisition remains exact.
        solution=v['solution'];old_plan=solution._plan
        def plan(obs):
            old_plan(obs)
            if solution.stage=='verify_lift':
                pose=solution._actions[0,:7].copy()
                base=solution._planner.config
                cfg=replace(base,max_translation_per_step=base.max_translation_per_step/2,
                    max_translation_acceleration_per_step=base.max_translation_acceleration_per_step/4)
                planner=AbsolutePosePlanner(cfg)
                hold=solution._actions[:solution._postclose_hold_ticks].copy()
                actions=planner.plan_to_pose(current_pose=pose,goal_pose=solution._goal,gripper=-1.)
                if case=='slow_lift':solution._actions=np.concatenate([hold,actions])
                elif case=='airborne_hold':
                    solution._actions=np.concatenate([solution._actions,np.tile(solution._actions[-1],(round(2.2/solution.control_dt),1))])
                elif case=='lateral':
                    goal=solution._goal.copy();goal[0]+=.05
                    lateral=solution._planner.plan_to_pose(current_pose=solution._goal,goal_pose=goal,gripper=-1.)
                    solution._actions=np.concatenate([solution._actions,lateral]);solution._goal=goal
                if len(solution._actions)*solution.control_dt>solution.config.max_stage_plan_s:
                    raise ValueError('diagnostic exceeds unchanged plan budget')
                # This cap belongs only to causal motion probes, never a repair PASS.
                v['recording_transition_limit']=solution._emitted+len(solution._actions)+solution._ticks(.1)
        solution._plan=plan
    if case in ['slow_lift','airborne_hold','lateral']:
        original=v['solution'].identity
        v['solution'].identity=canonical_digest({'baseline':original,'case':case,'diagnostic_version':'motion-intervention-v1'})
        v['solution_identity']=v['solution'].identity
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'solution':v['solution_identity']})
    if case=='noslip_lift':
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'intervention':'noslip-at-lift-v1','iterations':2})
    v['_diagnostic_case']=case
    return v


def main():
    p=argparse.ArgumentParser();p.add_argument('--rate',type=int,choices=[20,50,100,500],required=True)
    p.add_argument('--mode',choices=['G0','T1'],default='G0');p.add_argument('--case',choices=['frozen','slow_lift','airborne_hold','lateral','noslip_lift','candidate_noslip2'],default='frozen')
    p.add_argument('--sample',choices=['nominal','offset_a','offset_b'],default='nominal');p.add_argument('--causal-gate',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.case=='candidate_noslip2':
        if a.causal_gate is None:raise ValueError('StageB candidate requires explicit causal gate')
        gate=json.loads(a.causal_gate.read_text())
        if gate.get('decision')!='PASS_TO_ISOLATED_STAGE_B':raise ValueError('Causal gate did not pass')
    if a.output.exists():raise FileExistsError(a.output)
    a.output.mkdir(parents=True)
    observer=NativeObserver(a.output)
    orig_context=loaded_episode.context;orig_readback=worker._runtime_diagnostic_readback;orig_reset=worker._reset;orig_sample_reset=worker.sample_reset;orig_recording=loaded_episode.LiveRecording
    interventions=[]
    loaded_episode.context=lambda rate:context(rate,a.case)
    class DiagnosticRecording(LiveRecording):
        def __init__(self,v,*args,**kwargs):
            super().__init__(v,*args,**kwargs)
            recipe=self.recorder.value['recipe']
            recipe.update(factory='task_env.diagnostics.phase1.frequency_grasp.run.context',
                diagnostic_case=a.case,diagnostic_sample=a.sample,
                source_xml_sha256=hashlib.sha256(v['source'].scene_source.xml.encode()).hexdigest(),
                contact_profile=v.get('_contact_profile'),qualification=False)
    DiagnosticRecording.__module__='task_env.diagnostics.phase1.frequency_grasp.run'
    loaded_episode.LiveRecording=DiagnosticRecording
    if a.sample!='nominal':
        definitions=json.loads((Path(__file__).parent/'profiles/heldout_samples_v1.json').read_text())['samples']
        spec=definitions[a.sample]
        def heldout_reset(artifact,seed):
            base=orig_sample_reset(artifact,seed);poses=dict(base.poses_world)
            old=poses['square-nut-v1'];q=np.array(old.quaternion_wxyz)
            rot=Rotation.from_euler('z',spec['nut_world_yaw_delta_rad'])*Rotation.from_quat(q,scalar_first=True)
            poses['square-nut-v1']=PoseWorld(tuple(np.array(old.position)+spec['nut_translation_delta_m']),tuple(rot.as_quat(scalar_first=True)))
            return ResetSample.create(schema_version=base.schema_version,task_artifact_hash=artifact.identity_hash,
                sampler_id='nut-assembly-square-v1/frequency-grasp-heldout/'+a.sample,sampler_version='predefined-local-v1',
                task_seed=spec['provenance_seed'],joint_position=base.joint_position,poses_world=poses,
                velocity_policy=base.velocity_policy,control_policy=base.control_policy,settle_steps=0)
        worker.sample_reset=heldout_reset
    def diagnostic_reset(v,provider):
        result=orig_reset(v,provider)
        if a.case=='noslip_lift':
            session=result[0];old_step=session._step_physics_once;changed=False
            def step():
                nonlocal changed
                if v['solution']._lift_released and not changed:
                    interventions.append({'time_s':float(session._data.time),'factor':'noslip_iterations','old':int(session._model.opt.noslip_iterations),'new':2,'acquisition_unchanged':True})
                    session._model.opt.noslip_iterations=2;changed=True
                old_step()
            session._step_physics_once=step
        return result
    worker._reset=diagnostic_reset
    worker._runtime_diagnostic_readback=lambda session,provider,stage:observer.capture(session,stage)
    launch={'schema':'frequency-grasp-launch-v1','branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
            'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'dirty':subprocess.check_output(['git','status','--short'],text=True).splitlines(),
            'rate':a.rate,'case':a.case,'mode':a.mode,'sample':a.sample,'physics_dt_s':.002,'qualification':False,'causal_gate_sha256':hashlib.sha256(a.causal_gate.read_bytes()).hexdigest() if a.causal_gate else None,
            'module_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.glob('*.py')}}
    (a.output/'launch.json').write_text(json.dumps(launch,indent=2)+'\n')
    start=time.monotonic()
    try:
        report=loaded_episode.run(a.mode,'mujoco',a.rate,a.output/'canonical')
    finally:
        observer.close();loaded_episode.context=orig_context;worker._runtime_diagnostic_readback=orig_readback;worker._reset=orig_reset;worker.sample_reset=orig_sample_reset;loaded_episode.LiveRecording=orig_recording
    summary={k:report.get(k) for k in ['pass','failure_boundary','close_authorization','verify_lift_pass',
                'max_capture_position_drift_m','max_capture_rotation_drift_rad','live_recording','solution_events']}
    summary.update(wall_time_s=time.monotonic()-start,native_samples=observer.count,
                   model_hash=observer.model_hash,diagnostic_errors=observer.errors,
                   max_contact_projection_error=observer.max_projection_error,
                   case=a.case,rate=a.rate,mode=a.mode,qualified=False,interventions=interventions,sample=a.sample,reset_sample_hash=report.get('reset_sample_hash'),recipe_identity=report.get('recipe_identity'))
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    if observer.errors:raise SystemExit('Native diagnostic calibration failed')

if __name__=='__main__':main()
