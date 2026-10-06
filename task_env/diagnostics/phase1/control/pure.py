"""Provider-free action, numerical Jacobian and admission detector."""
from dataclasses import replace
import json,os,subprocess,sys
from unittest.mock import patch
import numpy as np
from ....utils.rotation import quat_wxyz_to_matrix,rotvec_to_matrix
from ....artifacts import CapabilityAdmissionError
from ....controllers.canonical import RequestedAction,CanonicalAction,CanonicalControlTarget
from ....controllers.canonical.kinematics import ARM
from ....tasks.pick_cube.reset import sample_reset
from ....runtime.sessions.control import materialize_control,ControlBinding
from ....runtime.sessions import provider_manifest
from ..p1_2_runtime import execution
from .spec import context,virtual_state


def checks():
    artifact,source,model,controller=context();state=virtual_state(artifact,model,sample_reset(artifact,31))
    q=np.array([state.joint_position[n] for n in ARM]);_,J=model.fk_jacobian(q);eps=1e-6
    numerical=np.column_stack([(model.fk_jacobian(q+np.eye(7)[i]*eps)[0][:3,3]-model.fk_jacobian(q-np.eye(7)[i]*eps)[0][:3,3])/(2*eps) for i in range(7)])
    result={'Jacobian_max_abs':float(np.max(np.abs(J[:3]-numerical))),'checks':{}}
    result['checks']['shared_Jacobian_finite_difference']=result['Jacobian_max_abs']<1e-7
    requests=[RequestedAction('absolute_joint',None,'none',tuple(map(float,np.r_[q,2]))),
        RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,np.r_[state.pose_world['panda-v1/ee'].position,2*np.array(state.pose_world['panda-v1/ee'].quaternion_wxyz),1])))]
    requests += [RequestedAction('delta_pose',ref,'rotvec',(.01,0.,0.,0.,.01,0.,-2.)) for ref in ('world','base','ee')]
    for request in requests:
        action,target=controller.compute(state,request);again=controller.compute(state,request)
        key=request.mode+'_'+str(request.reference)
        result['checks'][key+'_deterministic']=action==again[0] and target==again[1]
        result['checks'][key+'_roundtrip']=CanonicalAction.from_mapping(json.loads(json.dumps(action.to_mapping())))==action and CanonicalControlTarget.from_mapping(json.loads(json.dumps(target.to_mapping())))==target
        result['checks'][key+'_finite_semantic']=target.arm_joint_order==ARM and np.isfinite(list(target.arm_position.values())).all() and 0<=target.gripper.opening_m<=.08
    # Independent reference-composition fixtures; the rotated base distinguishes base from world.
    original_base=model.base_transform.copy();model.base_transform[:3,:3]=rotvec_to_matrix(np.array([0.,0.,.4]))
    delta=np.array([.01,0.,0.]);dR=rotvec_to_matrix(np.array([0.,.01,0.]));current=state.pose_world['panda-v1/ee'];R=quat_wxyz_to_matrix(current.quaternion_wxyz);B=model.base_transform[:3,:3]
    for ref,expected_position,expected_rotation in (
        ('world',np.array(current.position)+delta,dR@R),
        ('base',np.array(current.position)+B@delta,B@dR@B.T@R),
        ('ee',np.array(current.position)+R@delta,R@dR)):
        action,_=controller.compute(state,RequestedAction('delta_pose',ref,'rotvec',(.01,0.,0.,0.,.01,0.,1.)))
        pose=action.resolved_world_pose
        result['checks']['delta_'+ref+'_composition']=bool(np.max(abs(np.array(pose.position)-expected_position))<1e-12 and np.max(abs(quat_wxyz_to_matrix(pose.quaternion_wxyz)-expected_rotation))<1e-12)
    model.base_transform=original_base
    normalized,_=controller.compute(state,requests[1]);result['checks']['normalized_public_quaternion']=bool(abs(np.linalg.norm(normalized.interpreted_values[3:7])-1)<1e-12)
    _,immutable=controller.compute(state,requests[0])
    try:immutable.arm_position[ARM[0]]=0.
    except TypeError:result['checks']['immutable_target']=True
    else:result['checks']['immutable_target']=False
    for name,values in [('shape',(0.,)),('nonfinite',tuple([float('nan')]*8))]:
        try:RequestedAction('absolute_joint',None,'none',values)
        except (ValueError,TypeError):result['checks']['reject_'+name]=True
        else:result['checks']['reject_'+name]=False
    for provider in ('geophys','mujoco'):
        manifest=provider_manifest(provider);restricted=replace(manifest,capabilities=tuple(c for c in manifest.capabilities if c.name!='joint_position_actuation'))
        with patch('task_env.runtime.sessions.api._materialize_admitted') as native:
            try:materialize_control(artifact,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08),manifest=restricted)
            except CapabilityAdmissionError:rejected=True
            else:rejected=False
        result['checks'][provider+'_negative_admission']=rejected and native.call_count==0
    result['pass']=all(result['checks'].values());return result


def guard():
    code="""import sys,json
from task_env.diagnostics.phase1.control.spec import context,virtual_state
from task_env.tasks.pick_cube.reset import sample_reset
from task_env.controllers.canonical import RequestedAction
from task_env.controllers.canonical.kinematics import ARM
a,s,m,c=context();state=virtual_state(a,m,sample_reset(a,31));c.compute(state,RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(state.pose_world['panda-v1/ee'].position)+tuple(state.pose_world['panda-v1/ee'].quaternion_wxyz)+(1.,)))
forbidden=[n for n in sys.modules if n.split('.')[0] in {'geophys','mujoco','sapien','genesis','taichi'}]
print(json.dumps({'pass':not forbidden,'forbidden':forbidden}));sys.exit(bool(forbidden))"""
    run=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,env=os.environ.copy())
    return {'pass':run.returncode==0,'stdout':run.stdout,'stderr':run.stderr,'returncode':run.returncode}
