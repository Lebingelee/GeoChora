"""Success-conditioned selection gates: pure fixtures plus actual selected file windows."""
from pathlib import Path
import copy
import json
import torch
from torch.utils.data import DataLoader
import task_env.alg.agent_factory
from agent_factory.data.impl.geochora_canonical import CanonicalFlowDataset, window
from agent_factory.data.impl.geochora_canonical.selection import INITIAL, POOLS, select, authorized, validate_manifest
from .supplement import verify_preserved, FAILED
from .checks import run as import_alignment_checks
from .prepare import write


def run(root):
    root=Path(root);checks={}
    rows=[{'seed':s,'role':role,'pass':s not in FAILED,'success':s not in FAILED,'endpoint':s not in FAILED,'roundtrip':True} for role in INITIAL for s in INITIAL[role]]
    for role, count in [('train',7),('validation',1)]:
        rows.extend({'seed':s,'role':role,'pass':True,'success':True,'endpoint':True,'roundtrip':True} for s in POOLS[role][:count])
    chosen=select(rows)
    checks['exact80_20']=len(chosen['train'])==80 and len(chosen['validation'])==20
    checks['failures_excluded']=not set(FAILED)&{r['seed'] for v in chosen.values() for r in v}
    checks['preserved_failed_attempts_do_not_disqualify']=authorized(chosen) and sum(not r['pass'] for r in rows)==8
    changed=copy.deepcopy(rows)
    for row in changed:row.update(xy=[float(row['seed']),-99],T=1,holds=1,loss=-10)
    checks['selection_independent_of_coverage_length_holds_loss']={k:[r['seed'] for r in v] for k,v in select(changed).items()}=={k:[r['seed'] for r in v] for k,v in chosen.items()}
    try:select(rows+[{'seed':1107,'role':'train','pass':True}])
    except ValueError:checks['stop_immediately_at_target']=True
    else:checks['stop_immediately_at_target']=False
    reordered=copy.deepcopy(rows);i=next(i for i,r in enumerate(reordered) if r['seed']==1100);reordered[i],reordered[i+1]=reordered[i+1],reordered[i]
    try:select(reordered)
    except ValueError:checks['ascending_order_required']=True
    else:checks['ascending_order_required']=False
    exhausted=[r for r in rows if r['seed'] in range(1000,1100)]+[{'seed':s,'role':role,'pass':False} for role in POOLS for s in POOLS[role]]
    checks['candidate_exhaustion_fails_closed']=not authorized(select(exhausted))
    mixed=[r for r in rows if 1000 <= r['seed'] < 1100]
    for role,count in [('train',8),('validation',2)]:
        mixed.extend({'seed':seed,'role':role,'pass':index>0,'endpoint':index>0,'success':index>0,'roundtrip':True} for index,seed in enumerate(POOLS[role][:count]))
    ordered=select(mixed)
    checks['first_successes_skip_failed_candidates_only']=authorized(ordered) and [r['seed'] for r in ordered['train']][-7:]==list(range(1101,1108)) and ordered['validation'][-1]['seed']==1201
    checks['previous_failed_attempts_preserved']=verify_preserved(root)
    manifest=json.loads((root/'training_dataset_manifest_v1.json').read_text())
    bad=copy.deepcopy(manifest)
    bad['trajectories'][0]=next(r for r in bad['attempts'] if r['seed']==1034)
    rejected=False
    try:validate_manifest(bad)
    except ValueError:rejected=True
    checks['failed_attempt_in_learner_manifest_rejected']=rejected
    train=CanonicalFlowDataset(root/'training_dataset_manifest_v1.json');val=train.validation_dataset()
    checks['real_selected_only']=train.training_eligible and val.training_eligible and not train.failed_seeds and not val.failed_seeds and train.statistics['trajectory_count']==80 and val.statistics['trajectory_count']==20
    checks['selected_count_statistics']=len(train)==sum(r['T'] for r in manifest['trajectories'] if r['role']=='train') and len(val)==sum(r['T'] for r in manifest['trajectories'] if r['role']=='validation')
    checks['selected_holds_preserved']=train.statistics['readiness_hold_count']==sum(r['holds'] for r in manifest['trajectories'] if r['role']=='train')
    checks['real_all_trajectory_alignment']=True
    for ds in (train,val):
        offset=0
        for x,y in ds.records:
            for i in (0,1,len(y)-1):
                got=ds[offset+i];expect=window(x,y,i)
                checks['real_all_trajectory_alignment'] &= torch.equal(got['action'],expect['action']) and torch.equal(got['observations']['state'],expect['observations']['state'])
            offset+=len(y)
    loader=DataLoader(train,batch_size=512,shuffle=True,drop_last=True,num_workers=0)
    checks['actor_iters_uses_selected_loader']=len(loader)==len(train)//512 and 20*len(loader)!=20
    from agent_factory.agents.impl.flow_vanilla import FlowVanillaAgent
    from omegaconf import OmegaConf
    class AdmittedWithoutTraining(Exception):
        pass
    class Probe:
        cfg=OmegaConf.create({'dataset':{'dataset_type':'geochora_canonical_flow'}})
        def _resolve_save_dir(self):
            return str(root/'supplement/regression/admission_only'), 'admission_only'
        def _fit_action_normalizer_from_dataset(self, dataset):
            raise AdmittedWithoutTraining()
    admitted=False
    try:FlowVanillaAgent.start_train(Probe(),{'offline':train,'validation':val})
    except AdmittedWithoutTraining:admitted=True
    checks['real_success_corpus_admitted_despite_old_failures']=admitted and bool(manifest['failed_train_seeds']) and bool(manifest['failed_validation_seeds'])
    base=import_alignment_checks(root/'supplement/regression/flow_checks')
    checks['flow_import_alignment_instrumentation']=base['pass']
    report={'pass':all(checks.values()),'checks':checks,'steps_per_epoch512':len(loader),'actor_iters512':20*len(loader)}
    write(root/'supplement/regression/selection_checks.json',report)
    if not report['pass']:raise ValueError('supplement selection regression failed')
    return report
