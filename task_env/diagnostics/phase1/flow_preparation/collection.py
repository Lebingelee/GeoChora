"""Frozen 100-seed GeoPhys expert collection, preserving every attempted outcome."""
from pathlib import Path
from datetime import datetime,timezone
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import yaml
from task_env.diagnostics.phase1.state_policy.spec import verify,context
from task_env.tasks.pick_cube.reset import sample_reset


def freeze(root):
    root=Path(root)
    if root.exists():
        raise FileExistsError('refusing collection evidence collision')
    source_root=Path('workspace/qualification/phase1/p1_6_state_policy')
    spec,old_lock=verify(source_root/'p1_6_spec.yaml')
    spec=copy.deepcopy(spec)
    artifact,_,_=context()
    spec['schema']='p1_6-flow-collection-manifest-v0'
    spec['sample_sets']={'train':list(range(1000,1080)), 'validation':list(range(1080,1100)), 'evaluation':[]}
    spec['samples']={str(s):sample_reset(artifact,s).to_mapping() for s in range(1000,1100)}
    spec['sample_hashes']={k:v['sample_id'].removeprefix('reset-') for k,v in spec['samples'].items()}
    spec['source_provider']='geophys'
    spec['flow_contract']={'obs_horizon':2,'pred_horizon':16,'act_horizon':8,'state_dim':33,'action_dim':8,
                           'agent_control_mode':'absolute_joint','normalization':'min_max','readiness_holds':'all_equal_weight'}
    root.mkdir(parents=True)
    path=root/'dataset_manifest.yaml';path.write_text(yaml.safe_dump(spec,sort_keys=False))
    lock={**old_lock,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
          'locked_at':datetime.now(timezone.utc).isoformat(), 'purpose':'100-seed collection only; legacy learner field unused'}
    for name in ('dataset_manifest_lock.json','p1_6_spec_lock.json'):
        (root/name).write_text(json.dumps(lock,indent=2)+'\n')
    (root/'provenance.json').write_bytes((source_root/'provenance.json').read_bytes())
    return lock


def collect(root):
    root=Path(root);spec,lock=verify(root/'dataset_manifest.yaml')
    if spec['sample_sets']!={'train':list(range(1000,1080)),'validation':list(range(1080,1100)),'evaluation':[]}:
        raise ValueError('frozen split changed')
    if (root/'collection_report.json').exists():
        raise FileExistsError('collection has already begun; no automatic replacement/retry')
    rows=[]
    environment={**os.environ,'PYTHONPATH':'GeoPhys/src:.','PYTHONDONTWRITEBYTECODE':'1'}
    for seed in range(1000,1100):
        role='train' if seed<1080 else 'validation'
        directory=root/'trajectories'/f'seed{seed}';directory.mkdir(parents=True)
        command=[sys.executable,'-m','task_env.diagnostics.phase1.p1_6_state_policy',
                 '--oracle',str(root/'dataset_manifest.yaml'),'--output',str(directory/'report.json'),
                 '--provider','geophys','--route','collect','--seed',str(seed),'--role',role]
        (directory/'command.json').write_text(json.dumps(command))
        start=time.monotonic()
        with (directory/'stdout.log').open('w') as out,(directory/'stderr.log').open('w') as err:
            result=subprocess.run(command,stdout=out,stderr=err,env=environment)
        row=json.loads((directory/'report.json').read_text()) if (directory/'report.json').exists() else {'seed':seed,'pass':False,'error':'worker report missing'}
        row.update(wall_time=time.monotonic()-start,exit_code=result.returncode)
        rows.append(row)
        (root/'collection_report.json').write_text(json.dumps({'attempts':len(rows),'successes':sum(bool(v.get('pass')) for v in rows),'rows':rows},indent=2)+'\n')
        print(seed,row.get('pass'),row.get('T'),row.get('first_boundary'),flush=True)
    return rows
