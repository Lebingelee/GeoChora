"""Isolated paired candidate runs with source snapshots and complete outcomes."""
import argparse
from dataclasses import asdict
import hashlib,json,os,subprocess,sys
from pathlib import Path
from ....tasks.nut_assembly.canonical_solution import CanonicalNutAssemblyConfig,NutAssemblyCanonicalSolutionV1


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--iteration',type=int,required=True);p.add_argument('--profiles',nargs='+',default=['NA-TB100']);p.add_argument('--hypothesis',required=True);p.add_argument('--scope',choices=['full','grasp_lift'],default='full');p.add_argument('--summarize-only',action='store_true');args=p.parse_args();root=Path(args.root);folder=root/'optimization/candidates'/f'iteration{args.iteration:02d}'
    if args.summarize_only:
        checks={}
        for profile in args.profiles:
            for provider in ['geophys','mujoco']:
                path=folder/(profile.lower().replace('na-','')+('_grasp_lift' if args.scope=='grasp_lift' else ''))/provider/'report.json'
                report=json.loads(path.read_text())
                checks[profile+'/'+provider]=bool(report.get('grasp_lift_gate_passed') if args.scope=='grasp_lift' else report.get('success'))
        print(json.dumps({'provider_execution':False,'scope':args.scope,'checks':checks,'pass':all(checks.values())}))
        return 0 if all(checks.values()) else 1
    folder.mkdir(parents=True,exist_ok=True)
    cfg=CanonicalNutAssemblyConfig();source=Path('task_env/tasks/nut_assembly/canonical_solution.py');sha=hashlib.sha256(source.read_bytes()).hexdigest()
    if not (folder/'source.py').exists():
        (folder/'source.py').write_bytes(source.read_bytes());(folder/'config.json').write_text(json.dumps(asdict(cfg),indent=2)+'\n')
        provenance={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('task_env/diagnostics/phase1/nutassembly_recovery').glob('*.py')}
        (folder/'diagnostic_source_hashes.json').write_text(json.dumps(provenance,indent=2)+'\n')
        (folder/'driver_sources').mkdir(exist_ok=True)
        for p in Path('task_env/diagnostics/phase1/nutassembly_recovery').glob('*.py'):(folder/'driver_sources'/p.name).write_bytes(p.read_bytes())
    if hashlib.sha256((folder/'source.py').read_bytes()).hexdigest()!=sha:raise ValueError('candidate source changed')
    log=root/'optimization/optimization_log.jsonl';entry={'iteration':args.iteration,'event':'begin','hypothesis':args.hypothesis,'source_sha256':sha,'config':asdict(cfg),'expert_identity':NutAssemblyCanonicalSolutionV1(config=cfg,control_dt=.01).identity,'profiles':args.profiles,'scope':args.scope}
    with log.open('a') as f:f.write(json.dumps(entry)+'\n')
    all_passed=True
    for profile in args.profiles:
        processes=[]
        for provider in ['geophys','mujoco']:
            f=folder/(profile.lower().replace('na-','')+('_grasp_lift' if args.scope=='grasp_lift' else ''))/provider
            if (f/'report.json').exists():raise FileExistsError('candidate collision')
            f.mkdir(parents=True,exist_ok=True);cmd=[sys.executable,'-m','task_env.diagnostics.phase1.nutassembly_recovery.worker','--root',str(root),'--folder',str(f),'--profile',profile,'--provider',provider,'--solution','canonical','--config',str(folder/'config.json'),'--scope',args.scope]
            (f/'command.txt').write_text('PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 GEOPHYS_HEADLESS=1 '+' '.join(cmd)+'\n');out=open(f/'stdout.log','w');err=open(f/'stderr.log','w');processes.append((provider,subprocess.Popen(cmd,env=os.environ,stdout=out,stderr=err),f,out,err))
        reports={}
        for provider,process,f,out,err in processes:
            rc=process.wait();out.close();err.close();reports[provider]=json.loads((f/'report.json').read_text()) if (f/'report.json').exists() else {'worker_exit':rc,'success':False}
        if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:raise ValueError('source mutated during governed candidate run')
        outcome={'iteration':args.iteration,'event':'result','profile':profile,'scope':args.scope,'results':reports}
        with log.open('a') as f:f.write(json.dumps(outcome)+'\n')
        print(json.dumps({k:{j:r.get(j) for j in ['success','grasp_lift_gate_passed','T','failure_reason','stage','max_nut_lift_m','error']} for k,r in reports.items()}),flush=True)
        all_passed=all_passed and all(bool(r.get('grasp_lift_gate_passed') if args.scope=='grasp_lift' else r.get('success')) for r in reports.values())
    return 0 if all_passed else 1

if __name__=='__main__':raise SystemExit(main())
