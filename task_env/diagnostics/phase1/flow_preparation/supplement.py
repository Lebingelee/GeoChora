"""Additive bounded expert supplementation; never trains or evaluates a learned policy."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import yaml
import numpy as np
import task_env.alg.agent_factory
from agent_factory.data.impl.geochora_canonical.selection import INITIAL, POOLS, TARGETS, select, authorized, successful
from task_env.diagnostics.phase1.state_policy.spec import verify, context
from task_env.tasks.pick_cube.reset import sample_reset
from task_env.trajectory.canonical import load
from .prepare import write, summary

FAILED = [1034, 1060, 1063, 1065, 1069, 1074, 1079, 1096]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_prior(root):
    root = Path(root)
    spec, lock = verify(root/'dataset_manifest.yaml')
    index = json.loads((root/'evidence_index.json').read_text())
    for item in index['files']:
        if sha(root/item['path']) != item['sha256']:
            raise ValueError('prior_collection_evidence_mismatch: '+item['path'])
    report = json.loads((root/'collection_report.json').read_text())
    rows = report['rows']
    if (report['attempts'] != 100 or report['successes'] != 92
            or [r['seed'] for r in rows] != list(range(1000,1100))
            or [r['seed'] for r in rows if not r['pass']] != FAILED
            or spec['sample_sets'] != {'train':INITIAL['train'], 'validation':INITIAL['validation'], 'evaluation':[]}):
        raise ValueError('prior_collection_evidence_mismatch: split/status')
    for row in rows:
        expected_role = 'train' if row['seed'] < 1080 else 'validation'
        t = load(row['file'])
        if (row['role'] != expected_role or row['sample_hash'] != spec['sample_hashes'][str(row['seed'])]
                or sha(row['file']) != row['file_sha256'] or t.identity_hash != row['logical_hash']
                or len(t.transitions) != row['T'] or t.hold_count != row['holds'] or not row['roundtrip']
                or (not row['pass'] and row['failure_reason'] != 'above_pose_readiness_timeout')):
            raise ValueError('prior_collection_evidence_mismatch: seed'+str(row['seed']))
    value = {'pass':True, 'verified_attempts':100, 'train_successes':73, 'validation_successes':19,
             'failed_seeds':FAILED, 'prior_files_sha256':{v['path']:v['sha256'] for v in index['files']},
             'prior_evidence_index_sha256':sha(root/'evidence_index.json')}
    write(root/'supplement_prior_verification.json', value)
    return spec, lock, rows


def freeze(root, spec, old_lock):
    root = Path(root); spec = copy.deepcopy(spec)
    spec['schema'] = 'p1_6-flow-supplement-manifest-v1'
    spec['collection_policy'] = {'name':'deterministic_success_conditioned_v1', 'initial':INITIAL,
                                'candidates':POOLS, 'targets':TARGETS, 'stop':'immediately_when_target_reached',
                                'reserved_evaluation_seeds':[31,73], 'selection':'first successful in authored ascending stream',
                                'success':'expert endpoint + task success + strict canonical load + logical roundtrip'}
    artifact,_,_=context()
    for role in POOLS:
        for seed in POOLS[role]:
            spec['samples'][str(seed)] = sample_reset(artifact,seed).to_mapping()
            spec['sample_hashes'][str(seed)] = spec['samples'][str(seed)]['sample_id'].removeprefix('reset-')
    path = root/'supplement_manifest.yaml'
    if path.exists() or (root/'supplement_manifest_lock.json').exists():
        raise FileExistsError('supplement manifest already exists')
    path.write_text(yaml.safe_dump(spec, sort_keys=False))
    lock = {**old_lock, 'sha256':sha(path), 'locked_at':datetime.now(timezone.utc).isoformat(),
            'starting_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'original_collection_sha256':sha(root/'dataset_manifest.yaml')}
    write(root/'supplement_manifest_lock.json',lock)
    # The frozen lower-phase worker expects these filenames beside its oracle.
    # Isolate its compatibility files instead of mutating the historical lock.
    bridge=root/'supplement/worker_oracle';bridge.mkdir(parents=True)
    (bridge/'supplement_manifest.yaml').write_bytes(path.read_bytes())
    (bridge/'provenance.json').write_bytes((root/'provenance.json').read_bytes())
    write(bridge/'p1_6_spec_lock.json',lock)
    return spec,lock


def collect(root, original):
    root=Path(root)
    spec=yaml.safe_load((root/'supplement_manifest.yaml').read_text())
    lock=json.loads((root/'supplement_manifest_lock.json').read_text())
    if sha(root/'supplement_manifest.yaml')!=lock['sha256'] or spec['collection_policy']['candidates']!=POOLS:
        raise ValueError('supplement candidate lock mismatch')
    dest=root/'supplement_collection_report.json'
    if dest.exists():raise FileExistsError('supplement attempts already exist; no retry or overwrite')
    oracle=root/'supplement/worker_oracle/supplement_manifest.yaml';verify(oracle)
    rows=[]
    env={**os.environ,'PYTHONPATH':'GeoPhys/src:.','PYTHONDONTWRITEBYTECODE':'1'}
    for role in TARGETS:
        count=sum(successful(r) for r in original if r['role']==role)
        for seed in POOLS[role]:
            if count==TARGETS[role]:break
            directory=root/'supplement'/role/f'seed{seed}';directory.mkdir(parents=True,exist_ok=False)
            command=[sys.executable,'-m','task_env.diagnostics.phase1.p1_6_state_policy','--oracle',str(oracle),
                     '--output',str(directory/'report.json'),'--provider','geophys','--route','collect','--seed',str(seed),'--role',role]
            write(directory/'command.json',command);start=time.monotonic()
            with (directory/'stdout.log').open('w') as out,(directory/'stderr.log').open('w') as err:
                process=subprocess.run(command,env=env,stdout=out,stderr=err)
            row=json.loads((directory/'report.json').read_text()) if (directory/'report.json').exists() else {'seed':seed,'role':role,'pass':False,'first_boundary':'worker_report','error':'worker report missing','sample_hash':spec['sample_hashes'][str(seed)]}
            row.update(wall_time=time.monotonic()-start,exit_code=process.returncode)
            rows.append(row);count+=successful(row)
            chosen=select(original+rows)
            # Only this NEW progress report is updated; individual attempt outputs stay immutable.
            dest.write_text(json.dumps({'rows':rows,'attempts':len(rows),'selected_counts':{k:len(v) for k,v in chosen.items()},'full_training_authorized':authorized(chosen)},indent=2)+'\n')
            print(role,seed,row.get('pass'),count,'/',TARGETS[role],flush=True)
    return rows


def compact(row):
    keys=('seed','role','file','file_sha256','logical_hash','T','holds','pass','endpoint','success','roundtrip','first_boundary','failure_reason','max_cube_lift')
    return {**{k:row.get(k) for k in keys},'reset_sample_hash':row['sample_hash']}


def coverage(samples, bounds):
    xy=np.array([v['poses_world']['cube-v1']['position'][:2] for v in samples],dtype=float)
    if not len(xy):return {'count':0}
    hist,xe,ye=np.histogram2d(xy[:,0],xy[:,1],bins=10,range=bounds)
    result={'count':len(xy),'xy':summary(xy),'occupancy_10x10':hist.astype(int).tolist(),'occupied_cells':int(np.count_nonzero(hist))}
    if len(xy)>1:
        delta=np.linalg.norm(xy[:,None]-xy[None,:],axis=-1);np.fill_diagonal(delta,np.inf);nn=delta.min(axis=1)
        result['nearest_neighbor_m']={'min':float(nn.min()),'max':float(nn.max()),'mean':float(nn.mean()),'median':float(np.median(nn))}
    distance=np.minimum(xy-np.array(bounds)[:,0],np.array(bounds)[:,1]-xy).min(axis=1)
    result['distance_to_nearest_authored_boundary_m']={'min':float(distance.min()),'max':float(distance.max()),'mean':float(distance.mean()),'median':float(np.median(distance))}
    result['occupied_grid_cells']=[[int(x),int(y)] for x,y in np.argwhere(hist>0)]
    return result


def finalize(root, original, additions):
    root=Path(root);spec=yaml.safe_load((root/'supplement_manifest.yaml').read_text())
    chosen=select(original+additions);attempts=[compact(r) for r in original+additions]
    selected=[compact(r) for role in TARGETS for r in chosen[role]]
    manifest={'schema':'geochora-canonical-flow-dataset-v1','collection_policy':spec['collection_policy'],
              'collection_manifest_sha256':sha(root/'dataset_manifest.yaml'),'supplement_manifest_sha256':sha(root/'supplement_manifest.yaml'),
              'feature_contract':spec['feature_contract'],'action_contract':spec['action_contract'],'identities':spec['identities'],
              'window_contract':spec['flow_contract'],'attempts':attempts,'trajectories':selected,
              'full_training_authorized':authorized(chosen),'normalizer_source':'selected train transitions only; unpadded desired canonical absolute_joint actions; min_max'}
    for role in TARGETS:
        rows=[r for r in attempts if r['role']==role]
        for label,values in [('attempted',rows),('successful',[r for r in rows if successful(r)]),('failed',[r for r in rows if not successful(r)]),('selected',[r for r in selected if r['role']==role])]:
            manifest[label+'_'+role+'_seeds']=[r['seed'] for r in values]
        manifest['selected_'+role+'_trajectory_hashes']=[r['logical_hash'] for r in selected if r['role']==role]
        manifest['target_'+role+'_success_count']=TARGETS[role]
    write(root/'training_dataset_manifest_v1.json',manifest)
    artifact,_,_=context();bounds=[d.training_bounds for d in artifact.initialization.randomization]
    groups={'attempted':original+additions,'successful':[r for r in original+additions if successful(r)],
            'selected_train':chosen['train'],'selected_validation':chosen['validation'],'failed':[r for r in original+additions if not successful(r)]}
    write(root/'selected_coverage_report.json',{'authored_bounds':bounds,'diagnostic_only':True,
        'groups':{name:coverage([spec['samples'][str(r['seed'])] for r in rows],bounds) for name,rows in groups.items()}})
    return manifest


def verify_preserved(root):
    root=Path(root);old=json.loads((root/'supplement_prior_verification.json').read_text())
    if any(sha(root/p)!=v for p,v in old['prior_files_sha256'].items()) or sha(root/'evidence_index.json')!=old['prior_evidence_index_sha256']:
        raise ValueError('prior_collection_evidence_mismatch: historical bytes changed')
    return True
