"""Complete bounded route; preserve mandatory failures and never tune on eval."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess,sys,traceback,shutil
import numpy as np
from ..p1_2_runtime import write_json
from .spec import verify


def command(cmd,out,*,timeout=1200):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise FileExistsError('preserve first Evidence: '+str(out))
    (out.parent/'command.txt').write_text('PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 '+' '.join(cmd)+'\n')
    with (out.parent/'stdout.log').open('w') as stdout,(out.parent/'stderr.log').open('w') as stderr:
        try:run=subprocess.run(cmd,stdout=stdout,stderr=stderr,env=os.environ.copy(),timeout=timeout);rc=run.returncode
        except subprocess.TimeoutExpired:rc=124
    return json.loads(out.read_text()) if out.exists() else {'pass':False,'error':'worker_process','returncode':rc}


def worker_command(oracle,out,provider,*,seed=None,role=None,route='collect',input=None):
    cmd=[sys.executable,'-m','task_env.diagnostics.phase1.p1_6_state_policy','--oracle',str(oracle),'--output',str(out),'--provider',provider,'--route',route]
    if seed is not None:cmd+=['--seed',str(seed)]
    if role is not None:cmd+=['--role',role]
    if input is not None:cmd+=['--input',str(input)]
    return command(cmd,out)


def regressions(root):
    rows={}
    # Approved R4 smoke is an unchanged reusable reproduction of accepted R5 anchor semantics.
    cases=[('p1_5_readiness','workspace/qualification/phase1/p1_5_expert/recovery/r4/readiness_oracle.yaml'),
        ('p1_4_camera','workspace/qualification/phase1/p1_4_camera/camera_oracle.yaml'),
        ('p1_3_conformance','workspace/qualification/phase1/p1_3_conformance/oracle_spec.yaml'),('p1_2_runtime',None),('p1_1_contracts',None)]
    for name,oracle in cases:
        out=root/'regression'/name/'report.json';cmd=[sys.executable,'-m','task_env.diagnostics.phase1.'+name,'--output',str(out)]
        if oracle:cmd+=['--oracle',oracle]
        report=command(cmd,out,timeout=1800)
        passed=report.get('pass',report.get('status')=='ready_for_human_review')
        if name=='p1_1_contracts':passed=all(c['result']=='pass' for c in report.get('checks',[])) and bool(report.get('checks'))
        rows[name]={'pass':bool(passed),'report':str(out)};print('regression',name,passed,flush=True)
    # Readiness provider-free smoke is owned by the existing R4 checks.
    original=Path('workspace/qualification/phase1/p1_5_expert/recovery/r4/pure.py')
    copied=root/'regression/readiness_pure.py';shutil.copyfile(original,copied)
    (copied.parent/'provider_free').mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,str(copied)]
    run=subprocess.run(cmd,capture_output=True,text=True,env=os.environ.copy())
    (root/'regression/provider_free_stdout.log').write_text(run.stdout);(root/'regression/provider_free_stderr.log').write_text(run.stderr)
    rows['P1_5_provider_free']={'pass':run.returncode==0,'stdout':run.stdout,'stderr':run.stderr,'approved_fixture_source_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'copied_fixture_same_hash':original.read_bytes()==copied.read_bytes()}
    write_json(root/'regression/summary.json',rows);return rows


def run(oracle,output,*,use_collected=False):
    spec,lock=verify(oracle);root=Path(output).parent;root.mkdir(parents=True,exist_ok=True)
    if Path(output).exists():raise FileExistsError('preserve pipeline Evidence')
    report={'schema':'p1_6-bounded-route-v0','status':'partial_with_localized_failure','oracle_sha256':lock['sha256'],'started_at':datetime.now(timezone.utc).isoformat(),
        'collection':[],'replay':{},'learner':{},'evaluation':[],'first_boundary':None,'fix_attempts':0}
    stage='expert_data_collection'
    with ThreadPoolExecutor(max_workers=1) as executor:
        regression=executor.submit(regressions,root)
        try:
            for provider in ('geophys','mujoco'):
                for seed in (11,17,23,47):
                    role='validation' if seed==47 else 'train';out=root/'trajectories'/provider/f'seed{seed}'/'report.json'
                    r=json.loads(out.read_text()) if use_collected else worker_command(oracle,out,provider,seed=seed,role=role)
                    report['collection'].append(r)
            if not all(r.get('pass',False) for r in report['collection']):raise ValueError('mandatory frozen collection sample failed')
            from ....trajectory.canonical import load
            from ....alg.state_bc.learner import dataset,learner_smoke,train
            stage='serialization_roundtrip'
            for r in report['collection']:
                t=load(r['file'])
                if t.identity_hash!=r['logical_hash'] or t.hold_count!=r['holds'] or len(t.transitions)!=r['T']:raise ValueError('collection logical receipt mismatch')
            stage='replay_contract';path=root/'trajectories/geophys/seed11/trajectory.h5'
            for p in ('geophys','mujoco'):report['replay'][p]=worker_command(oracle,root/'replay'/p/'report.json',p,route='replay',input=path)
            if not all(r.get('pass') for r in report['replay'].values()):raise ValueError('frozen replay failed')
            g=report['replay']['geophys'];m=report['replay']['mujoco']
            report['replay_pairwise']={'same_hashes':g['target_hashes']==m['target_hashes'],
                'joint_max_abs':max(abs(g['final_state']['joint_position'][n]-m['final_state']['joint_position'][n]) for n in g['final_state']['joint_position'])}
            if not report['replay_pairwise']['same_hashes']:raise ValueError('replay target inputs differ')
            stage='dataset_adapter';paths={}
            for p in ('geophys','mujoco'):
                paths[p]=([root/'trajectories'/p/f'seed{s}/trajectory.h5' for s in (11,17,23)],[root/'trajectories'/p/'seed47/trajectory.h5'])
                x,y,manifest=dataset(paths[p][0]);vx,vy,val=dataset(paths[p][1]);dest=root/'datasets'/p;dest.mkdir(parents=True,exist_ok=True)
                np.savez(dest/'examples.npz',features=x,actions=y,validation_features=vx,validation_actions=vy)
                write_json(dest/'manifest.json',{'training':manifest,'validation':val,'no_hold_filter':True,'examples_exact_from_loaded_files':True})
            stage='checkpoint_portability';report['learner_smoke']={}
            for p in paths:
                report['learner_smoke'][p]=learner_smoke(*paths[p],spec['learner'],root/'learner'/p/'smoke/checkpoint.pt',provider_provenance=spec['providers'][p],parity_tolerance=spec['checkpoint_parity_max_abs'])
            stage='learner';report['training_started_at']=datetime.now(timezone.utc).isoformat()
            for p in paths:
                r=train(*paths[p],spec['learner'],root/'learner'/p/'checkpoint.pt',provider_provenance=spec['providers'][p],parity_tolerance=spec['checkpoint_parity_max_abs'])
                report['learner'][p]=r;write_json(root/'learner'/p/'report.json',r);print('train',p,r['selected_epoch'],r['validation_loss'],flush=True)
            stage='cross_provider_policy_behavior';report['evaluation_started_at']=datetime.now(timezone.utc).isoformat()
            for source,p in (('geophys','geophys'),('geophys','mujoco'),('mujoco','mujoco'),('mujoco','geophys')):
                for seed in (31,73):
                    checkpoint=root/'learner'/source/'checkpoint.pt';out=root/'evaluation'/f'train_{source}_eval_{p}'/f'seed{seed}/report.json'
                    r=worker_command(oracle,out,p,seed=seed,route='evaluate',input=checkpoint);r['training_source']=source;report['evaluation'].append(r)
                    write_json(output,report);print('eval',source,p,seed,r.get('success'),r.get('max_cube_lift'),r.get('error'),flush=True)
            if not all(r.get('pass') for r in report['evaluation']):
                stage=next(r.get('first_boundary') or 'cross_provider_policy_behavior' for r in report['evaluation'] if not r.get('pass'))
                raise ValueError('frozen policy matrix task-success gate failed')
        except Exception as error:report.update(first_boundary=stage,error=str(error),traceback=traceback.format_exc())
        report['regressions']=regression.result()
    if report['first_boundary'] is None and not all(r['pass'] for r in report['regressions'].values()):report['first_boundary']='lower_phase_regression'
    if report['first_boundary'] is None:report['status']='ready_for_human_review'
    verify(oracle);write_json(output,report);return report
