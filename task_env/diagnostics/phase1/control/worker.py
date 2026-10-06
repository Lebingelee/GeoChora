"""Isolated provider execution of frozen semantic controls/expert."""
from dataclasses import replace
from pathlib import Path
import json,traceback
import numpy as np
from ....artifacts.execution import ResetSample
from ....controllers.canonical import RequestedAction,CanonicalControlTarget
from ....controllers.canonical.kinematics import ARM,FINGERS
from ....tasks.pick_cube.canonical_semantics import evaluate
from ....tasks.pick_cube.solution import PickCubeSolution,PickCubeSolutionConfig
from ....runtime.sessions.control import materialize_control,ControlBinding
from ..p1_2_runtime import execution,write_json
from .spec import context,free_space_source,verify


def positions(state):return np.array([state.joint_position[n] for n in ARM])

def observation(state,artifact):
    ee=state.pose_world['panda-v1/ee'];cube=state.pose_world['cube-v1'];e=evaluate(state,artifact.semantics)
    obs={'state':{'ee_pose':np.array((*ee.position,*ee.quaternion_wxyz),dtype=np.float32)},
        'privileged_state':{'cube_v1_body_pose':np.array([(*cube.position,*cube.quaternion_wxyz)],dtype=np.float32)}}
    info={'is_success':bool(e.success),'task_failure':False,'task_metrics':dict(e.metrics)}
    return obs,info,e


def tick(session,artifact,target,requested=None,canonical=None,expert=None):
    before=target.identity_hash;applied=session.apply_control(target);state=session.step();_,info,e=observation(state,artifact)
    if before!=target.identity_hash:raise ValueError('provider mutated canonical target')
    row={'control_step':state.control_step,'simulation_time':state.simulation_time,'requested_action':None if requested is None else requested.to_mapping(),
        'canonical_action':None if canonical is None else canonical.to_mapping(),'controller_target':target.to_mapping(),'applied_control':applied.to_mapping(),
        'arm_joint_position':dict(state.joint_position),'arm_joint_velocity':dict(state.joint_velocity),
        'EE_world_pose':state.pose_world['panda-v1/ee'].to_mapping(),'cube_world_pose':state.pose_world['cube-v1'].to_mapping(),
        'gripper_target':target.gripper.to_mapping(),'gripper_opening_m':float(sum(state.joint_position[n] for n in FINGERS)),
        'task_metrics':info['task_metrics'],'is_success':info['is_success'],'task_failure':info['task_failure'],
        'expert_stage':None if expert is None else expert.stage,'expert_diagnostics':{} if expert is None else dict(expert.diagnostics)}
    return state,row


def replay(session,artifact,model,sample,sequence,bound,goal=None):
    session.reset(sample);initial=session.snapshot();trace=[];targets=[CanonicalControlTarget.from_mapping(t) for t in sequence]
    for target in targets:
        state,row=tick(session,artifact,target);trace.append(row)
    q=positions(state);target=np.array([targets[-1].arm_position[n] for n in ARM]);trajectory=np.array([[r['arm_joint_position'][n] for n in ARM] for r in trace])
    margin=min(float(np.min(trajectory-model.limits[:,0])),float(np.min(model.limits[:,1]-trajectory)))
    delta=target-positions(initial);measured=q-positions(initial);mask=np.abs(delta)>1e-4
    direction=bool(np.all(measured[mask]*delta[mask]>0))
    result={'final_joint_error':float(np.max(np.abs(q-target))),'joint_limit_margin':margin,'correct_direction':direction,
        'final_joint':q.tolist(),'final_EE':list(state.pose_world['panda-v1/ee'].position),'finite':bool(np.isfinite(trajectory).all()),
        'input_sequence_hashes':[t.identity_hash for t in targets],'sample_hash_before':sample.identity_hash,'sample_hash_after':sample.identity_hash,
        'task_failure':any(r['task_failure'] for r in trace)}
    if goal is not None:
        start=np.linalg.norm(np.array(initial.pose_world['panda-v1/ee'].position)-goal);end=np.linalg.norm(np.array(result['final_EE'])-goal)
        result.update(initial_EE_distance=float(start),final_EE_distance=float(end),EE_progress=bool(end<start))
    result['pass']=result['final_joint_error']<=bound and margin>=-1e-5 and direction and result['finite'] and not result['task_failure'] and result.get('EE_progress',True)
    return result,trace


def run(provider,route,oracle,output):
    spec,lock=verify(oracle);artifact,source,model,controller=context();samples=[ResetSample.from_mapping(s) for s in spec['samples']]
    result={'provider':provider,'route':route,'oracle_sha256':lock['sha256'],'first_boundary':None,'closed':False};session=None;stage='materialization'
    try:
        session=materialize_control(artifact,execution(provider),source=free_space_source(source) if route in ('C1_A','gripper') else source,binding=ControlBinding('panda-v1/gripper',.08))
        session.reset(samples[0]);state=session.snapshot();shared=model.pose(positions(state));native=state.pose_world['panda-v1/ee']
        qp=np.array(shared.quaternion_wxyz);qn=np.array(native.quaternion_wxyz)
        result['FK_position_error']=float(np.max(np.abs(np.array(shared.position)-native.position)))
        result['FK_quaternion_error']=float(min(np.max(np.abs(qp-qn)),np.max(np.abs(qp+qn))))
        result['FK_pass']=result['FK_position_error']<=spec['bounds']['FK_position_m'] and result['FK_quaternion_error']<=spec['bounds']['FK_rotation']
        if not result['FK_pass']:raise ValueError('shared FK disagrees with measured semantic EE pose')
        if route in ('C1_A','C1_B'):
            stage=route
            result['metrics'],trace=replay(session,artifact,model,samples[0],spec[route],spec['bounds'][route+'_joint_error'],np.array(spec['C1_B_goal_world']) if route=='C1_B' else None)
            write_json(output.parent/'trace.json',trace);result['pass']=result['metrics']['pass']
        elif route=='gripper':
            stage='gripper';trace=[];rows=[];q=[samples[0].joint_position[n] for n in ARM]
            for mode,scalar in (('open',1.),('close',-1.),('reopen',1.)):
                for _ in range(spec['gripper_smoke'][mode+'_ticks']):
                    request=RequestedAction('absolute_joint',None,'none',tuple(q)+(scalar,));canonical,target=controller.compute(state,request)
                    state,row=tick(session,artifact,target,request,canonical);trace.append(row)
                opening=row['gripper_opening_m'];passed=opening<=spec['bounds']['gripper_close_max_m'] if mode=='close' else opening>=spec['bounds']['gripper_open_min_m']
                rows.append({'mode':mode,'opening_m':opening,'canonical_target':target.gripper.to_mapping(),'applied_control':row['applied_control'],'pass':passed})
            result['rows']=rows;result['pass']=all(r['pass'] for r in rows);write_json(output.parent/'trace.json',trace)
        else:
            stage='C2';rows=[]
            metadata={'action_schema':{'controller_kind':'absolute_pose','reference':'world','rotation_representation':'quaternion_wxyz','dimension':8}}
            for sample in samples:
                stage=f'C2/seed{sample.task_seed}';session.reset(sample);state=session.snapshot();obs,info,e=observation(state,artifact);expert=PickCubeSolution(config=PickCubeSolutionConfig());expert.reset(obs,info,metadata);trace=[]
                for _ in range(spec['action_budget']):
                    if expert.done or expert.failed:break
                    public=expert.act(obs,info);request=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
                    canonical,target=controller.compute(state,request);state,row=tick(session,artifact,target,request,canonical,public);trace.append(row)
                    obs,info,e=observation(state,artifact);expert.observe(obs,e.reward,False,False,info)
                rows.append({'seed':sample.task_seed,'sample_id':sample.sample_id,'sample_hash':sample.identity_hash,'ticks':len(trace),
                    'task_success':info['is_success'],'expert_done':expert.done,'expert_failed':expert.failed,'failure_reason':expert.failure_reason,
                    'stage':expert.stage,'cube_lift':float(info['task_metrics']['cube_lift']),'pass':bool(info['is_success'] and expert.done),
                    'sample_unchanged':sample.to_mapping()==spec['samples'][samples.index(sample)]})
                write_json(output.parent/f'seed_{sample.task_seed}_trace.json',trace)
            result['rows']=rows;result['pass']=all(r['pass'] and r['sample_unchanged'] for r in rows)
        if not result['pass']:result['first_boundary']=stage
    except Exception as error:
        result.update({'pass':False,'first_boundary':stage,'error':str(error),'traceback':traceback.format_exc()})
    finally:
        if session is not None:
            try:session.close();result['closed']=True
            except Exception as error:result['close_error']=str(error);result['pass']=False
    write_json(output,result)
