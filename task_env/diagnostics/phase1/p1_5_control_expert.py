"""Reusable bounded canonical-control qualification detector (CPU, isolated workers)."""
import argparse,json,os,subprocess,sys
from pathlib import Path
import numpy as np
from .p1_2_runtime import write_json
from .control.spec import verify,identities
from .control.pure import checks,guard


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--oracle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',choices=['geophys','mujoco']);parser.add_argument('--route',choices=['C1_A','C1_B','gripper','C2']);args=parser.parse_args()
    if args.worker:
        from .control.worker import run
        run(args.worker,args.route,args.oracle,args.output);return
    spec,lock=verify(args.oracle);root=args.output.parent;root.mkdir(parents=True,exist_ok=True)
    report={'oracle_sha256':lock['sha256'],'provenance':identities(),'provider_free':checks(),'provider_free_guard':guard(),'providers':{},'pairwise':{}}
    if not report['provider_free']['pass'] or not report['provider_free_guard']['pass']:raise ValueError('provider-free prerequisite failure')
    for route in ('C1_A','gripper','C1_B','C2'):
        for provider in ('geophys','mujoco'):
            report['providers'].setdefault(provider,{})
            # C2 prerequisites are native free-space and physical gripper correctness, not optimistic rollout expansion.
            if route=='C2' and not all(report['providers'][provider][r].get('pass',False) for r in ('C1_A','gripper')):
                report['providers'][provider][route]={'pass':False,'not_run':'G2 free-space/gripper prerequisite failed; operator Goal forbids C2 before these pass',
                    'rows':[{'seed':sample['task_seed'],'sample_id':sample['sample_id'],'sample_hash':sample['sample_id'].removeprefix('reset-'), 'status':'not_run'} for sample in spec['samples']]};continue
            output=root/route/provider/'report.json';output.parent.mkdir(parents=True,exist_ok=True)
            cmd=[sys.executable,'-m','task_env.diagnostics.phase1.p1_5_control_expert','--oracle',str(args.oracle),'--output',str(output),'--worker',provider,'--route',route]
            (output.parent/'command.txt').write_text('PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 '+' '.join(cmd)+'\n')
            with (output.parent/'stdout.log').open('w') as out,(output.parent/'stderr.log').open('w') as err:
                try:run=subprocess.run(cmd,stdout=out,stderr=err,timeout=600,env=os.environ.copy());rc=run.returncode
                except subprocess.TimeoutExpired:rc=124
            report['providers'][provider][route]=json.loads(output.read_text()) if output.exists() else {'pass':False,'returncode':rc,'first_boundary':'worker_process'}
            write_json(args.output,report)
        if route in ('C1_A','C1_B'):
            a=report['providers']['geophys'][route].get('metrics');b=report['providers']['mujoco'][route].get('metrics')
            if a and b:
                joint=float(np.max(np.abs(np.array(a['final_joint'])-b['final_joint'])));ee=float(np.linalg.norm(np.array(a['final_EE'])-b['final_EE']))
                report['pairwise'][route]={'joint_max_abs':joint,'EE_distance_m':ee,'pass':joint<=spec['bounds'][route+'_pairwise_joint'] and (route=='C1_A' or ee<=spec['bounds']['C1_B_pairwise_EE_m'])}
            else:report['pairwise'][route]={'pass':False,'not_comparable':'provider route failed before measurement'}
    report['first_failing_boundary']=next((provider+'/'+route+'/'+str(report['providers'][provider][route].get('first_boundary') or 'gate') for route in ('C1_A','gripper','C1_B','C2') for provider in ('geophys','mujoco') if not report['providers'][provider][route].get('pass',False)),None)
    report['pass']=all(v.get('pass',False) for routes in report['providers'].values() for v in routes.values()) and all(v['pass'] for v in report['pairwise'].values())
    report['status']='ready_for_human_review' if report['pass'] else 'partial_with_localized_failure';write_json(args.output,report)
    print(json.dumps({'status':report['status'],'provider_routes':{p:{r:v.get('pass') for r,v in rows.items()} for p,rows in report['providers'].items()},'pairwise':report['pairwise']},indent=2))
    sys.exit(0 if report['pass'] else 1)


if __name__=='__main__':main()
