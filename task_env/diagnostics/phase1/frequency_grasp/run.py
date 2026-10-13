"""Versioned, opt-in development runs; frozen G0/T1 gates stay unchanged."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import MethodType
import xml.etree.ElementTree as ET
from scipy.spatial.transform import Rotation
import numpy as np
from ...phase1.integration import loaded_episode
from ...phase1.integration.grasp_height_probe import context as frozen_context
from ...phase1.nutassembly_r5_architecture import tracking_worker as worker
from ....tasks.nut_assembly import canonical_artifact
from ....planners import AbsolutePosePlanner, AbsolutePosePlannerConfig
from .mechanics import set_freejoint_armature
from .native import NativeObserver, AppliedStepObserver,canonical_digest
from .arm_schedule import ramped_control_interval,RampedArmAudit,ArmRampMemory
from .cadence import NativeRateGripperServo,validate_native_cadence
from ...phase1.integration import live_recording as recording_module
from ...phase1.integration.live_recording import LiveRecording
from ....artifacts import PoseWorld
from ....artifacts.execution import ResetSample

# Explicit experiment memberships keep unrelated interventions disjoint.
NOSLIP_FROM_RESET={'candidate_noslip2','candidate_noslip4','candidate_native500','elliptic_lift','arm_ramp_lift','armature_zero_lift','arm_ramp_native_grip','damping_zero_lift','candidate_airborne_hold','grip_adjust_zero_descend'}
ARM_RAMP_CASES={'arm_ramp_lift','arm_ramp_frozen_lift','noslip_arm_ramp_lift','armature_zero_lift','arm_ramp_native_grip','damping_zero_lift','candidate_airborne_hold','grip_adjust_zero_descend'}
NATIVE_GRIP_CASES={'candidate_native500','arm_ramp_native_grip'}
NATIVE_GRIP_EXECUTION_CASES=NATIVE_GRIP_CASES|{'damping_zero_lift','candidate_airborne_hold','grip_adjust_zero_descend'}
LIFT_INTERVENTION_CASES={'noslip_lift','elliptic_lift','noslip_arm_ramp_lift','armature_zero_lift','damping_zero_lift'}
CANDIDATE_CASES=NOSLIP_FROM_RESET|ARM_RAMP_CASES


def context(rate,case):
    if rate==20:
        canonical_artifact.PROFILES={**canonical_artifact.PROFILES,'NA-TB20':(25,.05)}
    v=frozen_context(rate)
    if case in NOSLIP_FROM_RESET:
        profile_path=Path(__file__).parent/'profiles'/('mujoco_noslip4_v2.json' if case=='candidate_noslip4' else 'mujoco_noslip2_v1.json')
        profile=json.loads(profile_path.read_text())
        xml=ET.fromstring(v['source'].scene_source.xml)
        option=xml.find('option');option.set('noslip_iterations',str(profile['model_option_overrides']['noslip_iterations']))
        scene=replace(v['source'].scene_source,xml=ET.tostring(xml,encoding='unicode'))
        v['source']=replace(v['source'],scene_source=scene)
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'contact_profile':profile,
            'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest(),'source_xml_sha256':hashlib.sha256(scene.xml.encode()).hexdigest()})
        v['_contact_profile']=profile
        v['_source_xml_sha256']=hashlib.sha256(scene.xml.encode()).hexdigest()
    if case in NATIVE_GRIP_EXECUTION_CASES:
        base=v['controller'].hold.controller
        v['controller'].inner=NativeRateGripperServo(base,500,v['artifact'].timebase.control_dt)
        base.identity=canonical_digest({'baseline':base.identity,'cadence':NativeRateGripperServo.version})
        v['controller_identity']=base.identity
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'cadence':NativeRateGripperServo.version})
    if case in ['slow_lift','airborne_hold','lateral','candidate_airborne_hold']:
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
                elif case in ['airborne_hold','candidate_airborne_hold']:
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
    if case in ['slow_lift','airborne_hold','lateral','candidate_airborne_hold']:
        original=v['solution'].identity
        v['solution'].identity=canonical_digest({'baseline':original,'case':case,'diagnostic_version':'motion-intervention-v1'})
        v['solution_identity']=v['solution'].identity
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'solution':v['solution_identity']})
    if case in ['noslip_lift','elliptic_lift','noslip_arm_ramp_lift']:
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'intervention':case+'-at-lift-v1','iterations':2})
    if case in ARM_RAMP_CASES:
        v['_arm_schedule_memory']=ArmRampMemory()
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'arm_schedule':'linear-native-ramp-after-lift-v2-public-ack-memory'})
    if case=='armature_zero_lift':
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'mechanical_intervention':'nut-freejoint-armature-zero-at-lift-v2-consistent-constants'})
    if case=='damping_zero_lift':
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'mechanical_intervention':'nut-freejoint-damping-zero-at-lift-v1'})
    if case=='grip_adjust_zero_descend':
        v['recipe_identity']=canonical_digest({'baseline':v['recipe_identity'],'gripper_intervention':'open-loop-target-hold-from-descend-v1'})
    v['_diagnostic_case']=case
    return v


def main():
    p=argparse.ArgumentParser();p.add_argument('--rate',type=int,choices=[20,50,100,500],required=True)
    p.add_argument('--mode',choices=['G0','T1'],default='G0');p.add_argument('--case',choices=['frozen','slow_lift','airborne_hold','lateral','noslip_lift','candidate_noslip2','candidate_noslip4','candidate_native500','elliptic_lift','arm_ramp_lift','arm_ramp_frozen_lift','noslip_arm_ramp_lift','armature_zero_lift','arm_ramp_native_grip','damping_zero_lift','candidate_airborne_hold','grip_adjust_zero_descend'],default='frozen')
    p.add_argument('--sample',choices=['nominal','offset_a','offset_b'],default='nominal');p.add_argument('--causal-gate',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.case in CANDIDATE_CASES:
        if a.causal_gate is None:raise ValueError('StageB candidate requires explicit causal gate')
        gate=json.loads(a.causal_gate.read_text())
        if gate.get('decision')!='PASS_TO_ISOLATED_STAGE_B':raise ValueError('Causal gate did not pass')
    if a.output.exists():raise FileExistsError(a.output)
    a.output.mkdir(parents=True)
    observer=NativeObserver(a.output)
    orig_snapshot=recording_module.snapshot
    def diagnostic_snapshot(value,state,provider):
        snap=orig_snapshot(value,state,provider)
        if '_arm_schedule_memory' in value:
            snap.pop('integrity_hash')
            snap['owners']['arm_schedule']={'version':'arm-schedule-public-ack-memory-v2','source_sha256':hashlib.sha256((Path(__file__).parent/'arm_schedule.py').read_bytes()).hexdigest(),'fields':{'last_applied_arm':{'present':True,'value':value['_arm_schedule_memory'].last_applied_arm}}}
            snap['integrity_hash']=canonical_digest(snap)
        return snap
    recording_module.snapshot=diagnostic_snapshot
    orig_native_audit=worker.NativeAudit
    if a.case in ARM_RAMP_CASES:worker.NativeAudit=RampedArmAudit
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
                contact_profile=v.get('_contact_profile'),qualification=False,arm_schedule='linear-native-ramp-after-lift-v2-public-ack-memory' if a.case in ARM_RAMP_CASES else 'outer-ZOH')
            if a.case in NATIVE_GRIP_EXECUTION_CASES:
                recipe['cadence']='fixed-native-500hz-v1'
        def finish(self,report):
            if a.case in NATIVE_GRIP_EXECUTION_CASES:validate_native_cadence(self.recorder.value)
            return super().finish(report)
    DiagnosticRecording.__module__='task_env.diagnostics.phase1.frequency_grasp.run'
    loaded_episode.LiveRecording=DiagnosticRecording
    if a.sample!='nominal':
        definitions=json.loads((Path(__file__).parent/'profiles/heldout_samples_v1.json').read_text())['samples']
        spec=definitions[a.sample]
        def heldout_reset(artifact,seed):
            base=orig_sample_reset(artifact,seed);poses=dict(base.poses_world)
            old=poses['square-nut-v1'];q=np.array(old.quaternion_wxyz)
            rot=Rotation.from_euler('z',spec['nut_world_yaw_delta_rad'])*Rotation.from_quat(q,scalar_first=True)
            poses['square-nut-v1']=PoseWorld(tuple(map(float,np.array(old.position)+spec['nut_translation_delta_m'])),tuple(map(float,rot.as_quat(scalar_first=True))))
            return ResetSample.create(schema_version=base.schema_version,task_artifact_hash=artifact.identity_hash,
                sampler_id='nut-assembly-square-v1/frequency-grasp-heldout/'+a.sample,sampler_version='predefined-local-v1',
                task_seed=spec['provenance_seed'],joint_position=base.joint_position,poses_world=poses,
                velocity_policy=base.velocity_policy,control_policy=base.control_policy,settle_steps=0)
        worker.sample_reset=heldout_reset
    def diagnostic_reset(v,provider):
        result=orig_reset(v,provider)
        session=result[0]
        session._mj=AppliedStepObserver(session._mj,session,observer,lambda:v["solution"].stage)
        if a.case=='grip_adjust_zero_descend':
            original_step=session._step_physics_once;hold_started=False
            def target_hold_step():
                nonlocal hold_started
                if v['solution'].stage=='descend_to_peg_top' and not hold_started:
                    base=v['controller'].hold.controller
                    old=base.physical_profile['gripper']['force_adjust_rate_m_s']
                    base.physical_profile['gripper']['force_adjust_rate_m_s']=0.
                    interventions.append({'time_s':float(session._data.time),'factor':'force_adjust_rate_m_s','old':old,'new':0.,'role':'open-loop constant gripper target diagnostic after normal acquisition','held_servo_opening_m':base._commanded})
                    hold_started=True
                original_step()
            session._step_physics_once=target_hold_step
        if a.case in ARM_RAMP_CASES:
            session._diagnostic_arm_ramp_active=lambda:v['solution']._lift_released
            session._diagnostic_arm_ramp_memory=v['_arm_schedule_memory']
            session.step_control_interval=MethodType(ramped_control_interval,session)
        if a.case in LIFT_INTERVENTION_CASES:
            session=result[0];old_step=session._step_physics_once;changed=False
            def step():
                nonlocal changed
                if v['solution']._lift_released and not changed:
                    if a.case=='damping_zero_lift':
                        j=int(session._model.body_jntadr[session._bodies['square-nut-v1']]);adr=int(session._model.jnt_dofadr[j])
                        factor='nut_freejoint_damping';old=session._model.dof_damping[adr:adr+6].tolist();new=[0.]*6
                        session._model.dof_damping[adr:adr+6]=0.
                    elif a.case=='armature_zero_lift':
                        j=int(session._model.body_jntadr[session._bodies['square-nut-v1']]);adr=int(session._model.jnt_dofadr[j])
                        factor='nut_freejoint_armature';old=session._model.dof_armature[adr:adr+6].tolist();new=[0.]*6
                        detail=set_freejoint_armature(session._model,session._data,adr,0.)
                        interventions.append({'time_s':float(session._data.time),'factor':'model_derived_constant_recompute',**detail})
                    elif a.case in ['noslip_lift','noslip_arm_ramp_lift']:
                        factor='noslip_iterations';old=int(session._model.opt.noslip_iterations);new=2
                    else:factor='cone';old=int(session._model.opt.cone);new=1
                    interventions.append({'time_s':float(session._data.time),'factor':factor,'old':old,'new':new,'acquisition_unchanged':True})
                    if a.case not in ['armature_zero_lift','damping_zero_lift']:setattr(session._model.opt,factor,new)
                    changed=True
                old_step()
            session._step_physics_once=step
        return result
    worker._reset=diagnostic_reset
    def capture_required(session,provider,stage):
        try:return session._mj.latest
        except Exception as exc:
            observer.errors.append({'time_s':float(session._data.time),'required_contact_capture_error':repr(exc)})
            return {'available':False,'error':repr(exc)}
    worker._runtime_diagnostic_readback=capture_required
    launch={'schema':'frequency-grasp-launch-v1','branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
            'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'dirty':subprocess.check_output(['git','status','--short'],text=True).splitlines(),
            'rate':a.rate,'case':a.case,'mode':a.mode,'sample':a.sample,'physics_dt_s':.002,'qualification':False,'causal_gate_sha256':hashlib.sha256(a.causal_gate.read_bytes()).hexdigest() if a.causal_gate else None,
            'module_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.glob('*.py')}}
    (a.output/'launch.json').write_text(json.dumps(launch,indent=2)+'\n')
    # Preserve actual uncommitted diagnostic source, not just its digest.
    snapshot_dir=a.output/'source_snapshot';snapshot_dir.mkdir()
    for source_file in sorted(Path(__file__).parent.rglob('*')):
        if source_file.is_file() and source_file.suffix in ['.py','.json']:
            destination=snapshot_dir/source_file.relative_to(Path(__file__).parent)
            destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(source_file.read_bytes())
    (snapshot_dir/'working_tree.patch').write_bytes(subprocess.check_output(['git','diff','--binary']))
    start=time.monotonic()
    try:
        report=loaded_episode.run(a.mode,'mujoco',a.rate,a.output/'canonical')
    finally:
        observer.close();recording_module.snapshot=orig_snapshot;worker.NativeAudit=orig_native_audit;loaded_episode.context=orig_context;worker._runtime_diagnostic_readback=orig_readback;worker._reset=orig_reset;worker.sample_reset=orig_sample_reset;loaded_episode.LiveRecording=orig_recording
    expected_samples=(report.get('live_recording') or {}).get('T')
    if expected_samples is not None:expected_samples*=500//a.rate
    capture_pass=not observer.errors and observer.count>0 and (not report.get('pass') or observer.count==expected_samples)
    if report.get('pass') and not capture_pass:
        observer.errors.append({'native_capture_admission':False,'observed':observer.count,'expected':expected_samples})
    summary={k:report.get(k) for k in ['pass','failure_boundary','close_authorization','verify_lift_pass',
                'max_capture_position_drift_m','max_capture_rotation_drift_rad','live_recording','solution_events','error','recording_error']}
    summary.update(canonical_pass=bool(report.get('pass')),native_capture_pass=capture_pass,expected_native_samples=expected_samples,wall_time_s=time.monotonic()-start,native_samples=observer.count,
                   model_hash=observer.model_hash,diagnostic_errors=observer.errors,
                   max_contact_projection_error=observer.max_projection_error,
                   case=a.case,rate=a.rate,mode=a.mode,qualified=False,interventions=interventions,sample=a.sample,reset_sample_hash=report.get('reset_sample_hash'),recipe_identity=report.get('recipe_identity'))
    summary['pass']=bool(report.get('pass') and capture_pass)
    summary['normal_gripper_feedback_law_active_during_motion']=a.case!='grip_adjust_zero_descend'
    summary['normal_controller_qualification_eligible']=False
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    if observer.errors:raise SystemExit('Native diagnostic calibration failed')
    if not report.get('pass'):raise SystemExit(1)

if __name__=='__main__':main()
