"""Real recorded-boundary canonical reconstruction; not formal D0/D2."""
import argparse
import copy
import json
from dataclasses import replace
from pathlib import Path
from .grasp_height_probe import context
from .replay_preparation import restore, snapshot, _decode
from ..nutassembly.common import observation, METADATA
from ....artifacts.contracts import CanonicalStateView
from ....controllers.canonical import RequestedAction
from ....controllers.canonical.feedback import CanonicalControlFeedback
from ....controllers.canonical.contracts import digest
from ....trajectory.canonical.execution import load, expand_snapshot
from ....tasks.nut_assembly.canonical_reset import sample_reset


def checkpoints(x):
    bs=x['boundaries'];ss=[expand_snapshot(b['owners'],x['blobs']) for b in bs]
    def field(i,owner,name):return _decode(ss[i]['owners'][owner]['fields'][name]['value'])
    p5=next(i for i,b in enumerate(bs) if b['stage']=='verify_lift')
    p7=next(i for i in range(p5,len(bs)) if field(i,'coordinator','_lift_released'))
    p3=next(i for i in range(len(bs)) if field(i,'arm_hold','locked'))
    p2=max(i for i in range(p5) if bs[i]['stage']=='descend_to_handle' and len(field(i,'stability','history'))>=2)
    force=[i for i in range(p5) if bs[i]['stage']=='close_gripper' and field(i,'arm_gripper','_force_mode')]
    p4=force[max(0,len(force)-6)]
    return {'P0':0,'P1':max(1,p3//2),'P2':p2,'P3':p3,'P4':p4,'P5':p5,
            'P6':max(p5+1,p7-3),'P7':p7,'P8':min(len(bs)-2,p7+max(2,(len(bs)-p7)//2))}


def initialized(x,hz):
    v=context(hz);s=CanonicalStateView.from_mapping(x['boundaries'][0]['record']['state'])
    f=CanonicalControlFeedback.from_mapping(x['boundaries'][0]['record']['feedback'])
    expected=sample_reset(v['artifact'],int(v['profile']['reset']['seed']))
    recorded=x['metadata']['reset_sample']
    if expected.to_mapping()!=recorded:raise ValueError('ResetSample mismatch before restoration')
    if v['artifact'].to_mapping()!=x['recipe']['artifact']:raise ValueError('artifact recipe mismatch')
    v['controller'].reset(s,f);obs,info,_=observation(s,v['artifact']);v['solution'].reset(obs,info,METADATA)
    return v


def restore_boundary(v,x,k,provider):
    b=x['boundaries'][k];s=CanonicalStateView.from_mapping(b['record']['state'])
    restore(v,s,provider,expand_snapshot(b['owners'],x['blobs']))
    assert snapshot(v,s,provider)==expand_snapshot(b['owners'],x['blobs'])
    return s,CanonicalControlFeedback.from_mapping(b['record']['feedback'])


def one(v,x,k,provider):
    b=x['boundaries'][k];t=x['transitions'][k];expected=x['boundaries'][k+1]
    s=CanonicalStateView.from_mapping(b['record']['state']);f=CanonicalControlFeedback.from_mapping(b['record']['feedback'])
    public=v['solution'].act();request=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
    if request.to_mapping()!=t['record']['requested_action']:raise AssertionError('RequestedAction')
    canonical,outer=v['controller'].compute(s,f,request)
    if canonical.to_mapping()!=t['record']['canonical_action']:raise AssertionError('CanonicalAction')
    expected_owners=expand_snapshot(expected['owners'],x['blobs'])
    saved_outer=_decode(expected_owners['owners']['arm_hold']['fields']['last_target']['value'])
    if outer.to_mapping()!=saved_outer.to_mapping():raise AssertionError('outer target')
    for sub in t['interval']['substeps']:
        ss=CanonicalStateView.from_mapping(sub['state']);ff=CanonicalControlFeedback.from_mapping(sub['feedback'])
        grip,diagnostics=v['controller'].inner_gripper_step(ss,ff)
        actual=replace(outer,gripper=grip)
        if actual.to_mapping()!=sub['target']:raise AssertionError('substep target')
        if diagnostics['inner_update_performed']!=sub['updated']:raise AssertionError('cadence')
        if actual.identity_hash!=sub['applied']['target_hash']:raise AssertionError('application identity')
    post=CanonicalStateView.from_mapping(expected['record']['state']);pf=CanonicalControlFeedback.from_mapping(expected['record']['feedback'])
    readiness=v['controller'].readiness(post,pf)
    if readiness.to_mapping()!=expected['record']['readiness']:raise AssertionError('readiness')
    obs,info,evaluation=observation(post,v['artifact'])
    v['solution'].observe(obs,evaluation.reward,False,False,info,readiness=readiness)
    if snapshot(v,post,provider)!=expected_owners:raise AssertionError('owner update')
    return post,pf


def validate_cell(path,provider,hz,output,steps=12):
    x=load(path);points=checkpoints(x);results=[]
    for name,k in points.items():
        v=initialized(x,hz);row={'checkpoint':name,'control_step':k,'stage':x['boundaries'][k]['stage'],'steps':min(steps,len(x['transitions'])-k)}
        try:
            restore_boundary(v,x,k,provider)
            for j in range(k,k+row['steps']):one(v,x,j,provider)
            row.update(passed=True,first_divergence=None)
        except Exception as e:row.update(passed=False,first_divergence={'boundary':locals().get('j',k),'error':str(e)})
        results.append(row);print(provider,hz,name,row['passed'],row.get('first_divergence'),flush=True)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps({'provider':provider,'rate':hz,'level':'canonical_real_boundary','checkpoint_locations':points,'results':results,'passed':all(z['passed'] for z in results)},indent=2))
    return all(z['passed'] for z in results)


def main():
    p=argparse.ArgumentParser();p.add_argument('--provider',required=True);p.add_argument('--rate',type=int,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not validate_cell(a.input,a.provider,a.rate,a.output):raise SystemExit(1)

if __name__=='__main__':main()
