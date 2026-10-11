"""Integration regression: exact physical trace comparison, owner APIs, deadline."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from dataclasses import replace
import numpy as np
from ....controllers.canonical.execution import BoundaryWait, PoseStabilityWindow
from ....planners.references import MotionReferences
from ....planners.cartesian import CartesianPosePlanner
from .stable_grasp import context

FIELDS=('requested_action','actual_ee_pose','joint_target','servo_target','joint_achieved',
        'feedback','readiness','controller_memory','controller_reference_state',
        'measured_gripper_opening_m','closing_force_N','servo_gripper_opening_m',
        'simulation_time_s','control_step','task_metrics')

def compare(before,after):
    a=json.loads((before/'trace.json').read_text());b=json.loads((after/'trace.json').read_text())
    first=None;count=0
    for i,(x,y) in enumerate(zip(a,b)):
        for field in FIELDS:
            if x.get(field)!=y.get(field):
                first={'boundary':i,'field':field,'before':x.get(field),'after':y.get(field)};break
        if first:break
        count+=1
    ra=json.loads((before/'report.json').read_text());rb=json.loads((after/'report.json').read_text())
    # Only source/controller identity metadata should change in materialization.
    applied=[]
    for x,y in zip(a,b):
        xa=dict(x['applied_control']);ya=dict(y['applied_control'])
        for k in ('target_hash','controller_identity'):xa.pop(k,None);ya.pop(k,None)
        applied.append(xa==ya)
    return {'exact_physical_boundaries':count,'reference_boundaries':len(a),'integrated_boundaries':len(b),
            'first_physical_divergence':first,'physical_exact':first is None and len(a)==len(b),
            'applied_except_target_identity_exact':all(applied),
            'identity_divergence':'source-based controller/solution and applied target hash at boundary 0',
            'reference_pass':ra['pass'],'integrated_pass':rb['pass']}


def pure():
    result={}
    p=np.array([0.,0.,.5,1.,0.,0.,0.]);g=p.copy();g[2]+=.1
    planner=CartesianPosePlanner();short=MotionReferences(planner)
    result['planner_move_exact']=np.array_equal(short.move(current_pose=p,goal_pose=g,steps=10),planner.plan_to_pose(current_pose=p,goal_pose=g,steps=10))
    result['planner_hold_exact']=np.array_equal(short.hold(pose=p,steps=10,gripper=-1),planner.hold_pose(pose=p,steps=10,gripper=-1))
    window=PoseStabilityWindow();r=None
    for i in range(61):r=window.is_stable(i*.01,p,minimum_wait_s=.5,window_s=.2,minimum_samples=20,axis_span_m=.0001,speed_m_s=.002)
    result['stable_achieved_pose']=bool(r[0])
    q=p.copy();q[2]+=.001
    result['motion_rejects_stability']=not window.is_stable(.61,q,minimum_wait_s=.5,window_s=.2,minimum_samples=20,axis_span_m=.0001,speed_m_s=.002)[0]
    gate=BoundaryWait(2.,1.5)
    result['deadline_no_bypass']=gate.wait_until(3.5,False)=='timeout' and gate.wait_until(3.51,True)=='timeout'
    value=context(100);s=value['solution'];s._stage_index=s.STAGES.index('close_gripper');s._emitted=151;s._close_gate=BoundaryWait(0.,1.5)
    s._index=0;s._actions=np.zeros((1000,8));s.observe({},0.,False,False,{},readiness=None)
    result['candidate_deadline_fail_closed_before_plan_exhaustion']=s.failed and s.failure_reason=='close_gripper_authorization_deadline'
    protected=['task_env/controllers/canonical/production.py','task_env/controllers/canonical/production_r3.py','task_env/planners/cartesian.py',
               'task_env/tasks/nut_assembly/canonical_solution.py','task_env/tasks/nut_assembly/assets.py',
               'task_env/tasks/pick_cube/readiness_solution.py','task_env/runtime/sessions/mujoco.py']
    for path in protected:
        old=subprocess.check_output(['git','show','8e914da:'+path]);result['unchanged:'+path]=old==Path(path).read_bytes()
    result['pass']=all(result.values());return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--reference-root',type=Path,required=True);p.add_argument('--integrated-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result={'pure':pure(),'cells':{}}
    for hz in (500,100,50):result['cells'][str(hz)]=compare(args.reference_root/f'tb{hz}',args.integrated_root/f'integrated_tb{hz}')
    result['pass']=result['pure']['pass'] and all(v['physical_exact'] and v['applied_except_target_identity_exact'] and v['integrated_pass'] for v in result['cells'].values())
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(0 if result['pass'] else 1)
if __name__=='__main__':main()
