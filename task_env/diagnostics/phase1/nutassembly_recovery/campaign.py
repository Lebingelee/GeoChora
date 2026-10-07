"""Isolated paired candidate runs with source snapshots and complete outcomes."""
import argparse
from dataclasses import asdict
import hashlib,json,os,subprocess,sys
from pathlib import Path
from ....tasks.nut_assembly.canonical_solution import CanonicalNutAssemblyConfig,NutAssemblyCanonicalSolutionV1


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--iteration',type=int,required=True);p.add_argument('--profiles',nargs='+',default=['NA-TB100']);p.add_argument('--hypothesis',required=True);args=p.parse_args();root=Path(args.root);folder=root/'optimization/candidates'/f'iteration{args.iteration:02d}';folder.mkdir(parents=True,exist_ok=True)
    cfg=CanonicalNutAssemblyConfig();source=Path('task_env/tasks/nut_assembly/canonical_solution.py');sha=hashlib.sha256(source.read_bytes()).hexdigest()
    if not (folder/'source.py').exists():
        (folder/'source.py').write_bytes(source.read_bytes());(folder/'config.json').write_text(json.dumps(asdict(cfg),indent=2)+'\n')
    if hashlib.sha256((folder/'source.py').read_bytes()).hexdigest()!=sha:raise ValueError('candidate source changed')
    log=root/'optimization/optimization_log.jsonl';entry={'iteration':args.iteration,'event':'begin','hypothesis':args.hypothesis,'source_sha256':sha,'config':asdict(cfg),'expert_identity':NutAssemblyCanonicalSolutionV1(config=cfg,control_dt=.01).identity,'profiles':args.profiles}
    with log.open('a') as f:f.write(json.dumps(entry)+'\n')
    for profile in args.profiles:
        processes=[]
        for provider in ['geophys','mujoco']:
            f=folder/profile.lower().replace('na-','')/provider
            if (f/'report.json').exists():raise FileExistsError('candidate collision')
            f.mkdir(parents=True,exist_ok=True);cmd=[sys.executable,'-m','task_env.diagnostics.phase1.nutassembly_recovery.worker','--root',str(root),'--folder',str(f),'--profile',profile,'--provider',provider,'--solution','canonical','--config',str(folder/'config.json')]
            (f/'command.txt').write_text('PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 GEOPHYS_HEADLESS=1 '+' '.join(cmd)+'\n');out=open(f/'stdout.log','w');err=open(f/'stderr.log','w');processes.append((provider,subprocess.Popen(cmd,env=os.environ,stdout=out,stderr=err),f,out,err))
        reports={}
        for provider,process,f,out,err in processes:
            rc=process.wait();out.close();err.close();reports[provider]=json.loads((f/'report.json').read_text()) if (f/'report.json').exists() else {'worker_exit':rc,'success':False}
        if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:raise ValueError('source mutated during governed candidate run')
        outcome={'iteration':args.iteration,'event':'result','profile':profile,'results':reports}
        with log.open('a') as f:f.write(json.dumps(outcome)+'\n')
        print(json.dumps({k:{j:r.get(j) for j in ['success','T','failure_reason','stage','max_nut_lift_m','error']} for k,r in reports.items()}),flush=True)

if __name__=='__main__':main()
