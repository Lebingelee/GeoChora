"""P0 reset/time/feedback prerequisite, fixed representation bounds."""
import argparse
import json
from pathlib import Path
import traceback
from ....tasks.pick_cube.reset import sample_reset
from ....runtime.sessions.control import materialize_control,ControlBinding
from ....controllers.canonical import ProductionCanonicalPandaController,RequestedAction
from ....controllers.canonical.kinematics import ARM
from ..p1_2_runtime import execution
from .golden import context


def run(root,provider,attempt):
    root=Path(root)
    folder=root/'prerequisites'/provider/'lifecycle'/attempt
    if (folder/'report.json').exists():raise FileExistsError('lifecycle Evidence collision')
    artifact,source,_=context(root);sample=sample_reset(artifact,31);original=sample.to_mapping()
    report={'provider':provider,'pass':False,'first_boundary':'materialization','checks':{}};session=None
    try:
        session=materialize_control(artifact,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08))
        report['first_boundary']='reset';a=session.reset(sample).measured_state;b=session.reset(sample).measured_state
        joint=max(abs(b.joint_position[n]-v) for n,v in sample.joint_position.items())
        position=max(abs(x-y) for n,p in sample.poses_world.items() for x,y in zip(b.pose_world[n].position,p.position))
        quaternion=max(abs(x-y) for n,p in sample.poses_world.items() for x,y in zip(b.pose_world[n].quaternion_wxyz,p.quaternion_wxyz))
        report['errors']={'joint_max_abs':joint,'position_max_abs':position,'quaternion_max_abs':quaternion}
        checks=report['checks'];checks['reset_state']=max(joint,position,quaternion)<=1e-5
        checks['repeat_reset']=a.to_mapping()==b.to_mapping()
        checks['zero_velocity']=max(abs(v) for v in b.joint_velocity.values())<=1e-5
        checks['reset_time']=b.control_step==0 and b.simulation_time==0.
        checks['semantic_fields']=set(b.joint_position)==set(source.joints) and set(b.pose_world)==set(source.bodies)|set(source.frames)
        report['first_boundary']='timebase';after=session.step()
        checks['one_step']=after.control_step==1 and after.simulation_time==artifact.timebase.control_dt
        report['one_step_state']=after.to_mapping()
        report['first_boundary']='canonical_gripper_feedback'
        state=session.reset(sample).measured_state;feedback=session.control_feedback(state)
        controller=ProductionCanonicalPandaController.from_source(artifact,source);controller.reset(state,feedback)
        measured=[]
        for scalar in (1.,-1.):
            for _ in range(50):
                request=RequestedAction('absolute_joint',None,'none',tuple([sample.joint_position[n] for n in ARM]+[scalar]))
                _,target=controller.compute(state,feedback,request);session.apply_control(target);state=session.step();feedback=session.control_feedback(state)
                measured.append(feedback.to_mapping())
        checks['feedback_alignment']=all(x['control_step']==i+1 for i,x in enumerate(measured))
        checks['open_close_motion']=measured[-1]['gripper']['opening_m']<measured[49]['gripper']['opening_m']
        checks['nonnegative_force']=all(x['gripper']['closing_force_N']>=0 for x in measured)
        checks['sample_unchanged']=sample.to_mapping()==original
        report['feedback']=measured;report['pass']=all(checks.values())
        report['first_boundary']=None if report['pass'] else next(k for k,v in checks.items() if not v)
    except Exception as error:report.update(error=str(error),traceback=traceback.format_exc())
    finally:
        if session is not None:session.close()
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--provider',choices=['genesis'],required=True)
    p.add_argument('--attempt',required=True);a=p.parse_args();r=run(a.root,a.provider,a.attempt);print(r['pass'],r['first_boundary'],r.get('error',''));raise SystemExit(0 if r['pass'] else 1)
