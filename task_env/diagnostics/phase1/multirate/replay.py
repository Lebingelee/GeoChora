"""Within-profile D0 and frozen D1/D2; targets are not regenerated across rates."""
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
from .common import context,identities,label,verify,write,NativeAudit
from ..p1_2_runtime import execution
from ....trajectory.canonical import load
from ....controllers.canonical import ProductionCanonicalPandaController,RequestedAction
from ....controllers.canonical.kinematics import ARM,FINGERS
from ....controllers.canonical.contracts import digest
from ....runtime.sessions.control import materialize_control,ControlBinding
from ....tasks.pick_cube.canonical_semantics import evaluate


def golden(root,profile,seed):
    folder=Path(root)/'golden'/label(profile)/f'seed{seed}'
    ref=json.loads((folder/'reference.json').read_text());trajectory=load(ref['path'])
    if not ref['success'] or trajectory.identity_hash!=ref['logical_hash'] or hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['h5_sha256']:raise ValueError('golden mismatch')
    return ref,trajectory


def d0(root,profile,seed):
    root=Path(root);verify(root);ref,tr=golden(root,profile,seed);a,source,_=context(root,profile)
    c=ProductionCanonicalPandaController.from_source(a,source);c.reset(tr.boundaries[0].state,tr.boundaries[0].feedback)
    actions=[];mismatches=[]
    for i,t in enumerate(tr.transitions):
        target=t.controller_target;request=RequestedAction('absolute_joint',None,'none',tuple([target.arm_position[n] for n in ARM]+[2.*target.gripper.opening_m/.08-1.]))
        _,new=c.compute(tr.boundaries[i].state,tr.boundaries[i].feedback,request)
        if new.to_mapping()!=target.to_mapping() or new.identity_hash!=target.identity_hash:mismatches.append(i)
        actions.append(request.to_mapping())
    folder=root/'d0'/label(profile)/f'seed{seed}'
    if (folder/'report.json').exists():raise FileExistsError('D0 Evidence collision')
    report={'profile':profile,'seed':seed,'pass':not mismatches,'exact_matches':len(actions)-len(mismatches),'T':len(actions),'mismatches':mismatches,'action_sequence_identity':digest(actions),'controller_identity':c.identity,'golden_logical_hash':tr.identity_hash}
    write(folder/'actions.json',actions);write(folder/'report.json',report);verify(root);return report


def run(root,profile,seed,provider,route):
    root=Path(root);verify(root);ref,tr=golden(root,profile,seed);a,source,_=context(root,profile)
    folder=root/route.lower()/label(profile)/provider/f'seed{seed}'
    if (folder/'report.json').exists():raise FileExistsError('replay Evidence collision')
    d0folder=root/'d0'/label(profile)/f'seed{seed}';d0ref=json.loads((d0folder/'report.json').read_text());actions=json.loads((d0folder/'actions.json').read_text())
    if not d0ref['pass'] or digest(actions)!=d0ref['action_sequence_identity']:raise ValueError('D0 sequence mismatch')
    report={'profile':profile,'seed':seed,'provider':provider,'route':route,'execution_valid':False,'task_valid':False,'first_success_control_step':None,'first_success_simulation_time_s':None,'final_lift_m':None,'max_lift_m':None,'failure_boundary':None,'golden_logical_hash':tr.identity_hash,'action_sequence_identity':digest(actions)}
    session=None;audit=None;trace=[];stage='materialization'
    try:
        session=materialize_control(a,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08));audit=NativeAudit(session,provider,a.timebase)
        stage='reset';sample=tr.metadata.reset_sample;before=sample.to_mapping();session.reset(sample);state=session.snapshot()
        if audit.count:raise ValueError('hidden reset step')
        c=None
        if route=='D2':
            c=ProductionCanonicalPandaController.from_source(a,source)
            if c.identity!=tr.metadata.controller_identity:raise ValueError('controller identity mismatch')
            c.reset(state,session.control_feedback(state))
        stage='replay';peak=float(evaluate(state,a.semantics).metrics['cube_lift'])
        for i,t in enumerate(tr.transitions):
            feedback=session.control_feedback(state);stored=t.controller_target
            if route=='D1':target=stored;request=None;canonical=None
            elif route=='D2':request=RequestedAction.from_mapping(actions[i]);canonical,target=c.compute(state,feedback,request)
            else:raise ValueError('unknown replay route')
            old_hash=target.identity_hash;applied=session.apply_control(target);old=state;state=audit.step(target)
            if target.identity_hash!=old_hash or applied.target_hash!=old_hash:raise ValueError('target linkage changed')
            if set(state.joint_position)!=set(old.joint_position) or set(state.pose_world)!=set(old.pose_world):raise ValueError('semantic names changed')
            evaluation=evaluate(state,a.semantics);lift=float(evaluation.metrics['cube_lift']);peak=max(peak,lift)
            if evaluation.success and report['first_success_control_step'] is None:report.update(first_success_control_step=state.control_step,first_success_simulation_time_s=state.simulation_time)
            reference=tr.boundaries[i+1].state
            diff={'arm_joint_max_abs':max(abs(state.joint_position[n]-reference.joint_position[n]) for n in ARM),
                'ee_position_norm_m':float(np.linalg.norm(np.array(state.pose_world['panda-v1/ee'].position)-reference.pose_world['panda-v1/ee'].position)),
                'cube_position_norm_m':float(np.linalg.norm(np.array(state.pose_world['cube-v1'].position)-reference.pose_world['cube-v1'].position)),
                'cube_quaternion_max_abs':max(abs(x-y) for x,y in zip(state.pose_world['cube-v1'].quaternion_wxyz,reference.pose_world['cube-v1'].quaternion_wxyz)),
                'arm_desired_target_max_abs':max(abs(target.arm_position[n]-stored.arm_position[n]) for n in ARM),
                'arm_servo_target_max_abs':max(abs(target.arm_servo_position[n]-stored.arm_servo_position[n]) for n in ARM),
                'gripper_desired_delta_m':abs(target.gripper.opening_m-stored.gripper.opening_m),
                'gripper_servo_delta_m':abs(target.gripper.servo_opening_m-stored.gripper.servo_opening_m)}
            trace.append({'state':state.to_mapping(),'feedback_before':feedback.to_mapping(),'requested_action':request.to_mapping() if request else None,'canonical_action':canonical.to_mapping() if canonical else None,
                'controller_target':target.to_mapping(),'applied_control':applied.to_mapping(),'cube_lift':lift,'is_success':evaluation.success,'divergence':diff,
                'gripper_opening_m':sum(state.joint_position[n] for n in FINGERS)})
        report.update(execution_valid=sample.to_mapping()==before,task_valid=bool(evaluation.success and report['first_success_control_step'] is not None),final_lift_m=lift,max_lift_m=peak,
            native_substep_count_valid=audit.count==len(tr.transitions)*a.timebase.control_substeps,observed_native_steps=audit.count,expected_native_steps=len(tr.transitions)*a.timebase.control_substeps,
            total_boundaries=len(tr.transitions),total_rollout_duration_s=len(tr.transitions)*a.timebase.control_dt,sample_unchanged=sample.to_mapping()==before,
            target_match_count=sum(row['controller_target']==t.controller_target.to_mapping() for row,t in zip(trace,tr.transitions)),
            final_divergence=trace[-1]['divergence'],maximum_divergence={k:max(row['divergence'][k] for row in trace) for k in trace[-1]['divergence']})
        report['failure_boundary']=None if report['task_valid'] else ('d1_provider_replay_task_behavior' if route=='D1' else 'd2_feedback_controller_interaction')
    except Exception as e:report.update(failure_boundary=stage+':'+str(e),error=str(e),traceback=traceback.format_exc(),completed_boundaries=len(trace))
    finally:
        if audit:write(folder/'native_audit.json',audit.boundaries);audit.close()
        if session:session.close()
        write(folder/'trace.json',trace);write(folder/'report.json',report);verify(root)
    return report
