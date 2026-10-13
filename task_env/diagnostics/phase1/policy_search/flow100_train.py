"""Frozen 80-epoch Flow baseline over the P1.6 100 Hz diagnostic corpus."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, random, shutil, time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from omegaconf import OmegaConf
import yaml

import task_env.alg.agent_factory
from agent_factory.agents.registry import make_agent
from agent_factory.training.identity import config_identity, digest
from task_env.alg.state_bc.features import FEATURE_CONTRACT, ACTION_CONTRACT
from task_env.diagnostics.phase1 import flow_training_normalized as baseline
from .flow100_data import Flow100Dataset

ROOT=Path('workspace/experiments/p1_6_policy_search/100hz_gpu_flow')
RUN=ROOT/'flow_training'
MANIFEST=ROOT/'training_dataset_manifest_100hz.json'
MANIFEST_LOCK=ROOT/'training_dataset_manifest_100hz_lock.json'
BASELINE_ROOT=Path('workspace/qualification/phase1/p1_6_flow_training_q99_zscore_80ep')
EPOCHS=80
BATCH_SIZE=512
SEED=2026
DEVICE='cuda'


def sha_bytes(value: bytes): return hashlib.sha256(value).hexdigest()
def sha(path): return sha_bytes(Path(path).read_bytes())

def write_new(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): raise FileExistsError(f'refusing to overwrite P1.6 100Hz Flow Evidence: {path}')
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')

def normalized_state(agent):
    return {'action':{k:v.detach().cpu().clone() for k,v in agent.action_normalizer.state_dict().items()},
            'observation':{k:v.detach().cpu().clone() for k,v in agent.obs_normalizer.state_dict().items()}}

def normalizer_payload(state):
    return {part:{k:v.tolist() for k,v in row.items()} for part,row in state.items()}

def _config_and_identity(dataset_sha, steps_per_epoch):
    baseline_cfg=baseline.load_variant_config(BASELINE_ROOT/'resolved_flow_config.yaml')
    baseline_summary=json.loads((BASELINE_ROOT/'training_summary.json').read_text())
    base_identity=config_identity(baseline_cfg)
    if base_identity != baseline_summary['resolved_config_sha256']:
        raise ValueError('baseline Flow config identity differs from reviewed training report')
    cfg=baseline_cfg
    cfg.dataset.expert.demo_path=str(MANIFEST)
    cfg.dataset.config={'allow_failed_for_smoke':False}
    cfg.agent_sp.epoch_budget=EPOCHS
    cfg.agent_sp.steps_per_epoch=int(steps_per_epoch)
    cfg.train.actor_iters=EPOCHS*int(steps_per_epoch)
    cfg.train.batch_size=BATCH_SIZE
    cfg.train.device=DEVICE
    cfg.device=DEVICE
    cfg.train.save_root=str(RUN/'agent_run')
    cfg.train.exp_name='flow_vanilla_100hz_gpu_zscore_q01_q99_80ep'
    identity={'resolved_config_sha256':config_identity(cfg),
              'dataset_manifest_sha256':dataset_sha,
              'agent_type':'Flow_Vanilla',
              'feature_contract_identity':digest(FEATURE_CONTRACT),
              'action_contract_identity':digest(ACTION_CONTRACT)}
    cfg.agent_sp.artifact_identity=identity
    if config_identity(cfg)!=identity['resolved_config_sha256']:
        raise ValueError('resolved Flow config identity is not stable')
    expected=(cfg.agent_type=='Flow_Vanilla' and cfg.device=='cuda' and cfg.train.device=='cuda'
              and cfg.train.batch_size==512 and cfg.env.proprio_dim==33 and cfg.env.action_dim==8
              and (cfg.env.obs_horizon,cfg.env.pred_horizon,cfg.env.act_horizon)==(2,16,8)
              and cfg.agent_control_mode=='absolute_joint' and cfg.env.env_control_mode=='absolute_joint'
              and cfg.actor.num_inference_steps==10 and cfg.actor.lr==1e-4 and cfg.actor.weight_decay==1e-6
              and cfg.actor.obs_norm.type=='mean_std' and cfg.actor.norm.type=='quantile'
              and cfg.actor.norm.params.q_low==0.01 and cfg.actor.norm.params.q_high==0.99
              and cfg.actor.norm.params.clip is True)
    if not expected: raise ValueError('Flow baseline config diverges from locked 100Hz experiment contract')
    return cfg,identity,base_identity


def prepare():
    for path in (RUN/'training_spec.yaml',RUN/'training_spec_lock.json',RUN/'resolved_flow_config.yaml',RUN/'dataset_stats.json'):
        if path.exists(): raise FileExistsError(f'preparation Evidence collision: {path}')
    if sha(MANIFEST)!=json.loads(MANIFEST_LOCK.read_text())['sha256']:
        raise ValueError('100Hz final dataset manifest lock mismatch')
    manifest=json.loads(MANIFEST.read_text())
    if not manifest['full_training_authorized'] or len(manifest['selected_train_seeds'])!=80 or len(manifest['selected_validation_seeds'])!=20:
        raise ValueError('100Hz selected corpus is incomplete')
    train=Flow100Dataset(MANIFEST,'train',pred_horizon=16)
    val=Flow100Dataset(MANIFEST,'validation',pred_horizon=16)
    train_loader=DataLoader(train,batch_size=BATCH_SIZE,shuffle=True,drop_last=True,num_workers=0)
    val_loader=DataLoader(val,batch_size=BATCH_SIZE,shuffle=False,drop_last=False,num_workers=0)
    steps_per_epoch=len(train_loader)
    if steps_per_epoch<1: raise ValueError('empty 100Hz training loader')
    dataset_sha=sha(MANIFEST)
    cfg,identity,baseline_config_sha=_config_and_identity(dataset_sha,steps_per_epoch)
    if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable for frozen Flow training')
    # Validate fitted statistics before any optimizer update; fit only on selected train trajectories.
    train_actions=train.get_all_actions().float()
    train_states=train.get_all_states().float()
    if train_actions.shape!=(len(train),8) or train_states.shape!=(len(train),33):
        raise ValueError('canonical Flow data shape mismatch')
    action_low=torch.quantile(train_actions,0.01,dim=0)
    action_high=torch.quantile(train_actions,0.99,dim=0)
    state_mean=train_states.mean(dim=0)
    state_std=train_states.std(dim=0)
    if not (torch.isfinite(action_low).all() and torch.isfinite(action_high).all() and (action_high>action_low).all()
            and torch.isfinite(state_mean).all() and torch.isfinite(state_std).all() and (state_std>0).all()):
        raise ValueError('selected training normalization statistics are invalid')
    data_stats={'train':train.statistics,'validation':val.statistics,
        'normalizer_fit_source':'selected successful train trajectories only',
        'state_mean':state_mean.tolist(),'state_std_unbiased':state_std.tolist(),
        'action_q01':action_low.tolist(),'action_q99':action_high.tolist(),
        'features':{'shape':list(train_states.shape),'dtype':str(train_states.dtype)},
        'actions':{'shape':list(train_actions.shape),'dtype':str(train_actions.dtype)}}
    RUN.mkdir(parents=True,exist_ok=True)
    OmegaConf.save(cfg,RUN/'resolved_flow_config.yaml',resolve=True)
    (RUN/'dataset_stats.json').write_text(json.dumps(data_stats,sort_keys=True,indent=2,allow_nan=False)+'\n')
    source_files=['task_env/diagnostics/phase1/policy_search/flow100_data.py',
                  'task_env/diagnostics/phase1/policy_search/flow100_train.py',
                  'task_env/diagnostics/phase1/flow_training_normalized.py',
                  'task_env/alg/agent_factory/agents/impl/flow_vanilla.py',
                  'task_env/alg/agent_factory/agents/mixins/actor/flow_matching.py',
                  'task_env/alg/agent_factory/agents/mixins/normalization_mixins.py',
                  'task_env/alg/agent_factory/data/normalization/quantile.py',
                  'task_env/alg/agent_factory/training/flow_metrics.py']
    source_hashes={name:sha(name) for name in source_files}
    spec={'schema':'p1_6-100hz-flow-training-spec-v0','locked_before_first_optimizer_update':True,
      'created_at':datetime.now(timezone.utc).isoformat(),'branch':'codex/p1.6-policy-search-100hz-gpu',
      'starting_head':'cda511f49eb544dabe685ec1dbcc6345884d66c8',
      'working_tree_status_at_lock':__import__('subprocess').check_output(['git','status','--short'],text=True).splitlines(),
      'historical_profile':{'physics_dt_s':0.002,'control_substeps':1,'control_dt_s':0.002,'physics_hz':500,'control_hz':500},
      'experimental_profile':{'task_artifact_sha256':manifest['identities']['task_artifact'],'physics_dt_s':0.002,
                              'control_substeps':5,'control_dt_s':0.010,'physics_hz':500,'control_hz':100},
      'provider':{'name':'geophys','collection_backend':'cuda','training_device':'cuda','inference_device':'cuda',
                  'diagnostic_only':True,'provider_qualification_claim':False},
      'baseline_config_sha256':baseline_config_sha,
      'dataset':{'manifest':str(MANIFEST),'manifest_file_sha256':dataset_sha,
                 'manifest_logical_identity':manifest['logical_identity'],
                 'candidate_manifest_sha256':manifest['collection_manifest_sha256'],
                 'train_trajectory_count':80,'validation_trajectory_count':20,
                 'train_samples':len(train),'validation_samples':len(val),
                 'train_seeds':manifest['selected_train_seeds'],'validation_seeds':manifest['selected_validation_seeds'],
                 'failed_train_attempts_preserved':manifest['failed_train_seeds'],'failed_validation_attempts_preserved':manifest['failed_validation_seeds'],
                 'statistics':str(RUN/'dataset_stats.json')},
      'learner':{'agent_type':'Flow_Vanilla','backbone':'ConditionalUnet1D','parameter_count':19512264,
                 'state_dim':33,'includes_qvel':True,'action_dim':8,'action_mode':'absolute_joint',
                 'obs_horizon':2,'pred_horizon':16,'act_horizon':8,
                 'prediction_duration_s':0.160,'open_loop_chunk_duration_s':0.080,'replan_frequency_hz':12.5,
                 'observation_normalization':'mean/std z-score, train-only, std uses torch.std default unbiased=True',
                 'action_normalization':'per-dimension q01-q99 mapped to [-1,1], clip=True, train-only',
                 'inference_steps':10,'device':'cuda','precision':'float32','seed':SEED,
                 'batch_size':BATCH_SIZE,'epoch_budget':EPOCHS,'steps_per_epoch':steps_per_epoch,
                 'actor_iters':EPOCHS*steps_per_epoch,'optimizer':'AdamW','lr':1e-4,'weight_decay':1e-6,
                 'dataloader':{'shuffle':True,'drop_last':True,'num_workers':0,'generator_seed':SEED},
                 'deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),
                 'cudnn_deterministic':torch.backends.cudnn.deterministic,
                 'cudnn_benchmark':torch.backends.cudnn.benchmark},
      'loss_instrumentation':{'train_interval':100,'validation_interval':1000,'validation_rng_seed':SEED,
                              'validation_rng_isolated_and_restored':True,'validation_steps':[0,1000,EPOCHS*steps_per_epoch],
                              'checkpoint_selection':'minimum validation loss; earlier step wins exact ties'},
      'identities':identity,'resolved_config_file':str(RUN/'resolved_flow_config.yaml'),
      'resolved_config_sha256':identity['resolved_config_sha256'],'dataset_manifest_sha256':dataset_sha,
      'feature_contract':FEATURE_CONTRACT,'action_contract':ACTION_CONTRACT,
      'frozen_source_file_sha256':source_hashes,
      'scope':'only 100Hz opt-in task timebase and CUDA execution route; no model/normalization/action/horizon tuning'}
    spec_path=RUN/'training_spec.yaml'; spec_path.write_text(yaml.safe_dump(spec,sort_keys=False,allow_unicode=True))
    spec_sha=sha(spec_path)
    lock={'schema':'p1_6-100hz-flow-training-spec-lock-v0','training_spec_sha256':spec_sha,
          'resolved_config_sha256':identity['resolved_config_sha256'],'dataset_manifest_sha256':dataset_sha,
          'locked_before_training':True}
    (RUN/'training_spec_lock.json').write_text(json.dumps(lock,sort_keys=True,indent=2)+'\n')
    # The canonical import restores this file's optional state-normalizer extension.
    reloaded=baseline.load_variant_config(RUN/'resolved_flow_config.yaml')
    if config_identity(reloaded)!=identity['resolved_config_sha256']:
        raise ValueError('resolved config SHA failed save/load canonicalization')
    return {'training_spec_sha256':spec_sha,'resolved_config_sha256':identity['resolved_config_sha256'],
            'dataset_manifest_sha256':dataset_sha,'train_samples':len(train),'validation_samples':len(val),
            'steps_per_epoch':steps_per_epoch,'actor_iters':EPOCHS*steps_per_epoch,'train_batches':len(train_loader),
            'validation_batches':len(val_loader),'train_stats':train.statistics,'validation_stats':val.statistics,
            'flow_config_baseline_sha256':baseline_config_sha,'spec_path':str(spec_path)}


def _seed_all():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED); torch.cuda.manual_seed_all(SEED)


def train():
    spec_path=RUN/'training_spec.yaml'; lock_path=RUN/'training_spec_lock.json'
    spec=yaml.safe_load(spec_path.read_text()); lock=json.loads(lock_path.read_text())
    if sha(spec_path)!=lock['training_spec_sha256'] or not lock['locked_before_training']:
        raise ValueError('training spec lock mismatch')
    if sha(MANIFEST)!=spec['dataset_manifest_sha256'] or not json.loads(MANIFEST_LOCK.read_text())['sha256']==sha(MANIFEST):
        raise ValueError('frozen dataset manifest identity mismatch')
    if sha(RUN/'resolved_flow_config.yaml')!=spec['resolved_config_file_sha256'] if 'resolved_config_file_sha256' in spec else False:
        raise ValueError('resolved config file bytes changed')
    if config_identity(baseline.load_variant_config(RUN/'resolved_flow_config.yaml'))!=spec['resolved_config_sha256']:
        raise ValueError('resolved config semantic identity mismatch')
    if (RUN/'training_metrics.jsonl').exists() or (RUN/'training_summary.json').exists() or (RUN/'checkpoints').exists():
        raise FileExistsError('training has started; preserving prior run Evidence')
    train_ds=Flow100Dataset(MANIFEST,'train',pred_horizon=16)
    val_ds=Flow100Dataset(MANIFEST,'validation',pred_horizon=16)
    _seed_all()
    generator=torch.Generator(device='cpu'); generator.manual_seed(SEED)
    train_loader=DataLoader(train_ds,batch_size=BATCH_SIZE,shuffle=True,drop_last=True,num_workers=0,generator=generator)
    val_loader=DataLoader(val_ds,batch_size=BATCH_SIZE,shuffle=False,drop_last=False,num_workers=0)
    if len(train_loader)!=spec['learner']['steps_per_epoch']:
        raise ValueError('DataLoader length changed after training lock')
    cfg=baseline.load_variant_config(RUN/'resolved_flow_config.yaml')
    cfg.agent_sp.artifact_identity=spec['identities']
    agent=make_agent('Flow_Vanilla',cfg)
    parameters=sum(p.numel() for p in agent.actor.parameters())
    if parameters!=spec['learner']['parameter_count']:
        raise ValueError(f'Flow architecture parameter count changed: {parameters}')
    if not isinstance(agent.actor_optimizer,torch.optim.AdamW): raise ValueError('optimizer not AdamW')
    op=agent.actor_optimizer.param_groups[0]
    if op['lr']!=1e-4 or op['weight_decay']!=1e-6: raise ValueError('optimizer differs from baseline lock')
    if next(agent.actor.parameters()).device.type!='cuda': raise ValueError('Flow actor did not initialize on CUDA')
    actions=train_ds.get_all_actions().to(agent.device).float()
    states=train_ds.get_all_states().to(agent.device).float()
    agent.fit_action_normalizer(actions); agent.fit_obs_normalizer(states)
    norm_state=normalized_state(agent)
    expected_qlo=torch.quantile(actions.cpu(),.01,dim=0); expected_qhi=torch.quantile(actions.cpu(),.99,dim=0)
    if not (torch.allclose(norm_state['action']['low_val'],expected_qlo) and torch.allclose(norm_state['action']['high_val'],expected_qhi)):
        raise ValueError('action normalizer is not q01-q99 from selected training corpus')
    if not (torch.allclose(norm_state['observation']['mean'],states.mean(0).cpu())
            and torch.allclose(norm_state['observation']['std'],states.std(0).cpu())):
        raise ValueError('observation normalizer is not train-only z-score')
    normalizer_id=digest(normalizer_payload(norm_state))
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    checkpoints=RUN/'checkpoints'; checkpoints.mkdir(parents=True)
    candidates=[]
    def save_validation_candidate(current,row):
        step=int(row['step']); path=checkpoints/f'validation_step_{step:04d}.pth'
        current.save(str(path),meta={'purpose':'100hz_fixed_validation_candidate','validation_step':step,
           'validation_loss':float(row['loss']),'validation_samples':row['samples'],'validation_batches':row['batches'],
           'normalizer_identity':normalizer_id,'resolved_config_sha256':spec['resolved_config_sha256'],
           'dataset_manifest_sha256':spec['dataset_manifest_sha256']})
        candidates.append({'step':step,'loss':float(row['loss']),'samples':int(row['samples']),
                           'batches':int(row['batches']),'file':str(path)})
    started=time.monotonic(); wall_start=datetime.now(timezone.utc).isoformat()
    n_steps=int(spec['learner']['actor_iters'])
    result=agent.train_loop(train_loader,n_steps,save_dir=str(RUN/'metrics_run'),
                            validation_loader=val_loader,validation_callback=save_validation_candidate)
    torch.cuda.synchronize(); wall=time.monotonic()-started
    if agent.step!=n_steps: raise ValueError(f'optimizer update count changed: {agent.step}/{n_steps}')
    expected_val=[0,1000,n_steps]
    if [r['step'] for r in candidates]!=expected_val:
        raise ValueError(f'fixed validation schedule mismatch: {[r["step"] for r in candidates]}')
    metric_path=RUN/'metrics_run'/'training_metrics.jsonl'
    metric_rows=[json.loads(s) for s in metric_path.read_text().splitlines()]
    train_rows=[r for r in metric_rows if r['kind']=='train']; val_rows=[r for r in metric_rows if r['kind']=='validation']
    expected_train=[*range(100,n_steps+1,100)]
    if n_steps%100: expected_train.append(n_steps)
    if [r['step'] for r in train_rows]!=expected_train: raise ValueError('train metric schedule mismatch')
    if not all(np.isfinite(r['loss']) for r in train_rows+val_rows): raise ValueError('flow_training_numerics: nonfinite metric')
    best=min(candidates,key=lambda r:(r['loss'],r['step']))
    best_src=Path(best['file']); best_path=checkpoints/'flow_best_validation.pth'; shutil.copy2(best_src,best_path)
    final_path=checkpoints/f'flow_final_100hz_step{n_steps}.pth'
    agent.save(str(final_path),meta={'purpose':'final_100hz_flow_checkpoint','optimizer_step':n_steps,
       'epoch_equivalent':EPOCHS,'normalizer_identity':normalizer_id,
       'resolved_config_sha256':spec['resolved_config_sha256'],'dataset_manifest_sha256':spec['dataset_manifest_sha256']})
    gpu=torch.cuda.get_device_properties(torch.cuda.current_device())
    peak_alloc=int(torch.cuda.max_memory_allocated()); peak_reserved=int(torch.cuda.max_memory_reserved())
    summary={'schema':'p1_6-100hz-flow-training-summary-v0','training_started_at':wall_start,
       'training_finished_at':datetime.now(timezone.utc).isoformat(),'training_wall_time_s':wall,
       'total_optimizer_steps':n_steps,'epoch_budget':EPOCHS,'effective_epochs':n_steps/len(train_loader),
       'steps_per_epoch':len(train_loader),'train_samples':len(train_ds),'validation_samples':len(val_ds),
       'initial_train_loss':train_rows[0]['loss'],'final_train_loss':train_rows[-1]['loss'],
       'minimum_train_window_loss':min(r['loss'] for r in train_rows),'first_train_window_step':train_rows[0]['step'],
       'initial_validation_loss':val_rows[0]['loss'],'step1000_validation_loss':next(r['loss'] for r in val_rows if r['step']==1000),
       'final_validation_loss':val_rows[-1]['loss'],'minimum_validation_loss':best['loss'],'best_validation_step':best['step'],
       'validation_rows':val_rows,'curve_classification':baseline.classify_curve([r['loss'] for r in train_rows],[r['loss'] for r in val_rows]),
       'gpu':gpu.name,'torch_version':torch.__version__,'torch_cuda_version':torch.version.cuda,
       'precision':'float32','deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),
       'peak_cuda_memory_allocated_bytes':peak_alloc,'peak_cuda_memory_reserved_bytes':peak_reserved,
       'normalizer_identity':normalizer_id,'normalizer_statistics':normalizer_payload(norm_state),
       'resolved_config_sha256':spec['resolved_config_sha256'],'dataset_manifest_sha256':spec['dataset_manifest_sha256'],
       'training_spec_sha256':lock['training_spec_sha256']}
    write_new(RUN/'training_summary.json',summary)
    cp_rows=[]
    for label,path,step,vloss in [('flow_final_100hz',final_path,n_steps,next((r['loss'] for r in val_rows if r['step']==n_steps),None)),
                                  ('flow_best_validation',best_path,best['step'],best['loss'])]:
        cp_rows.append({'name':path.name,'sha256':sha(path),'optimizer_step':step,'epoch_equivalent':step/len(train_loader),
          'validation_loss':vloss,'resolved_config_sha256':spec['resolved_config_sha256'],
          'dataset_manifest_sha256':spec['dataset_manifest_sha256'],'agent_type':'Flow_Vanilla',
          'feature_contract_identity':spec['identities']['feature_contract_identity'],
          'action_contract_identity':spec['identities']['action_contract_identity'],'normalizer_identity':normalizer_id,
          'artifact_identity':spec['identities']})
    write_new(checkpoints/'checkpoint_manifest.json',{'schema':'p1_6-100hz-flow-checkpoint-manifest-v0',
        'selected_rule':'minimum validation loss; earlier step wins exact ties','validation_candidates':candidates,'checkpoints':cp_rows})
    return summary


def main():
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--prepare',action='store_true'); p.add_argument('--train',action='store_true')
    args=p.parse_args()
    if args.prepare==args.train: raise SystemExit('choose exactly one of --prepare or --train')
    result=prepare() if args.prepare else train()
    print(json.dumps(result,sort_keys=True,indent=2,allow_nan=False))
if __name__=='__main__': main()
