"""Prepare immutable dataset/config identities and single-batch CPU/CUDA readiness.

No full-training or policy-rollout entry is exposed by this preparation driver.
"""
from pathlib import Path
from collections import Counter
import gc
import hashlib
import importlib.metadata
import json
import time
import numpy as np
import torch
from torch.utils.data import DataLoader
from omegaconf import OmegaConf
import yaml
import task_env.alg.agent_factory
from agent_factory.agents.registry import make_agent
from agent_factory.config.resolution import general_resolve
from agent_factory.data.registry import build_training_bundle
from agent_factory.data.impl.geochora_canonical import logical_hash, window
from agent_factory.training.identity import config_identity, digest
from task_env.alg.state_bc.features import FEATURE_CONTRACT, ACTION_CONTRACT
from task_env.diagnostics.phase1.state_policy.spec import context, verify

PROFILE = Path('task_env/alg/agent_factory/config/profiles/geochora_flow.yaml')


def write(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        raise FileExistsError('refusing preparation evidence overwrite: '+str(path))
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def summary(array):
    return {key:getattr(array,key)(axis=0).tolist() for key in ('min','max','mean','std')}


def dataset_manifest(root):
    root=Path(root)
    spec, lock=verify(root/'dataset_manifest.yaml')
    if hashlib.sha256((root/'dataset_manifest.yaml').read_bytes()).hexdigest()!=json.loads((root/'dataset_manifest_lock.json').read_text())['sha256']:
        raise ValueError('collection manifest lock changed')
    artifact,_,_=context()
    xy=np.array([spec['samples'][str(s)]['poses_world']['cube-v1']['position'][:2] for s in range(1000,1100)])
    distances=np.linalg.norm(xy[:,None,:]-xy[None,:,:],axis=-1);np.fill_diagonal(distances,np.inf)
    nn=distances.min(axis=1)
    bounds=[d.training_bounds for d in artifact.initialization.randomization]
    occupancy,_,_=np.histogram2d(xy[:,0],xy[:,1],bins=10,range=bounds)
    write(root/'coverage_report.json',{'xy':summary(xy),'authored_bounds':bounds,'occupancy_10x10':occupancy.astype(int).tolist(),
          'occupied_cells':int(np.count_nonzero(occupancy)),'nearest_neighbor_m':{'min':float(nn.min()),'max':float(nn.max()),'mean':float(nn.mean()),'median':float(np.median(nn))},'diagnostic_only':True})
    report=json.loads((root/'collection_report.json').read_text());rows=report['rows']
    if len(rows)!=100 or [v['seed'] for v in rows]!=list(range(1000,1100)):
        raise ValueError('100 required collection attempts not completed')
    failed=[v['seed'] for v in rows if not v.get('pass')]
    manifest={'schema':'geochora-canonical-flow-dataset-v0','collection_manifest_sha256':lock['sha256'],
              'feature_contract':FEATURE_CONTRACT,'action_contract':ACTION_CONTRACT,'identities':spec['identities'],
              'window_contract':spec['flow_contract'],'normalizer_source':'train1000..1079 transitions only; unpadded desired canonical action8; min_max',
              'trajectories':[{'seed':v['seed'],'role':v['role'],'file':v['file'],'file_sha256':v['file_sha256'],
                               'logical_hash':v['logical_hash'],'reset_sample_hash':v['sample_hash'],'T':v['T'],'holds':v['holds']} for v in rows],
              'split':spec['sample_sets'],'statistics':{},'failed_seeds':failed,'full_training_authorized':not failed}
    for role in ('train','validation'):
        selected=[v for v in rows if v['role']==role];stages=Counter(s for v in selected for s in v['expert_stage_sequence'])
        total=sum(v['T'] for v in selected);holds=sum(v['holds'] for v in selected)
        manifest['statistics'][role]={'trajectories':len(selected),'samples':total,'holds':holds,'planned':total-holds,'hold_fraction':holds/total,'stages':dict(stages)}
    write(root/'training_dataset_manifest.json',manifest)
    return manifest


def run(root):
    root=Path(root)
    manifest=dataset_manifest(root)
    user=OmegaConf.load(PROFILE)
    user.dataset.expert.demo_path=str(root/'training_dataset_manifest.json')
    user.dataset.config.allow_failed_for_smoke=True # no failed seed is discarded; start_train fails closed
    OmegaConf.save(user,root/'flow_config.yaml')
    cfg,_=general_resolve(file_config=user)
    bundle=build_training_bundle(cfg,required_keys=['observations','action'])
    train,val=bundle['offline'],bundle['validation']
    report={'pass':True,'full_training_authorized':train.training_eligible and val.training_eligible,'failed_seeds':train.failed_seeds+val.failed_seeds,'train':train.statistics,'validation':val.statistics,
            'train_state_statistics':summary(train.get_all_states().numpy()),'validation_state_statistics':summary(val.get_all_states().numpy()),
            'train_action_statistics':summary(train.get_all_actions().numpy()),'validation_action_statistics':summary(val.get_all_actions().numpy()),
            'dataset_manifest_sha256':logical_hash(manifest),'window_checks':{}}
    for ds in (train,val):
        offset=0
        for x,y in ds.records:
            for i in (0,1,len(y)-1):
                sample=ds[offset+i];expected=window(x,y,i)
                if not torch.equal(sample['action'],expected['action']) or not torch.equal(sample['observations']['state'],expected['observations']['state']):
                    raise ValueError('real dataset window alignment mismatch')
            offset+=len(y)
        report['window_checks'][ds.role]=True
    if not report['full_training_authorized']:
        class GuardProbe:
            cfg = cfg_placeholder = None
            normalize_calls = 0
            def _resolve_save_dir(self):
                return str(root/'guard_probe_no_training'), 'guard_probe'
            def _fit_action_normalizer_from_dataset(self, dataset):
                self.normalize_calls += 1
                raise AssertionError('failed corpus reached normalization/training')
        from agent_factory.agents.impl.flow_vanilla import FlowVanillaAgent
        probe = GuardProbe(); probe.cfg = cfg
        rejected = False
        try:
            FlowVanillaAgent.start_train(probe, bundle)
        except ValueError as error:
            rejected = 'full training forbidden' in str(error)
        if not rejected or probe.normalize_calls:
            raise ValueError('failed corpus training admission did not fail closed')
        report['failed_corpus_training_rejected_before_update'] = True
    write(root/'dataset_report.json',report)
    versions={m:importlib.metadata.version(m) for m in ['torch','numpy','h5py','omegaconf','einops','tqdm','PyYAML','antlr4-python3-runtime']}
    write(root/'dependency_report.json',{'versions':versions,'installed_only':['omegaconf2.3.0','einops0.8.1','tqdm4.67.1','antlr4-python3-runtime4.9.3'],'optional_not_installed':['diffusers','transformers','lerobot','mani_skill','pynput','agent_infra']})
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    attempts=[]
    for batch_size in (512,256,128):
        cfg.train.batch_size=batch_size
        loader=DataLoader(train,batch_size=batch_size,shuffle=True,drop_last=True,num_workers=0)
        cfg.agent_sp.steps_per_epoch=len(loader);cfg.train.actor_iters=20*len(loader)
        if not len(loader):raise ValueError('training loader is empty')
        identity={'resolved_config_sha256':config_identity(cfg),'dataset_manifest_sha256':logical_hash(manifest),
                  'agent_type':'Flow_Vanilla','feature_contract_identity':digest(FEATURE_CONTRACT),'action_contract_identity':digest(ACTION_CONTRACT)}
        cfg.agent_sp.artifact_identity=identity
        agent=None
        try:
            torch.manual_seed(2026);torch.cuda.manual_seed(2026)
            agent=make_agent('Flow_Vanilla',cfg)
            agent.fit_action_normalizer(train.get_all_actions().to(agent.device))
            batch=next(iter(loader));torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats();start=time.monotonic()
            result=agent.update_actor(batch);torch.cuda.synchronize();elapsed=time.monotonic()-start
            finite=all(torch.isfinite(p).all().item() and (p.grad is None or torch.isfinite(p.grad).all().item()) for p in agent.parameters())
            if not finite or not np.isfinite(result['loss_actor']):raise ValueError('nonfinite CUDA step')
            attempts.append({'batch_size':batch_size,'pass':True})
            cuda_report={'pass':True,'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,'cuda':torch.version.cuda,
                         'attempts':attempts,'selected_batch_size':batch_size,'peak_allocated':torch.cuda.max_memory_allocated(),
                         'peak_reserved':torch.cuda.max_memory_reserved(),'loss':result['loss_actor'],'wall_time':elapsed,
                         'parameter_count':sum(p.numel() for p in agent.parameters()),'optimizer_steps':1,'precision':'float32','full_training_authorized':report['full_training_authorized'],'dataset_mode':'all80 declared training trajectories; failed episodes retained; diagnostic only',
                         'epoch_budget':20,'steps_per_epoch':len(loader),'actor_iters':cfg.train.actor_iters}
            break
        except torch.cuda.OutOfMemoryError as e:
            attempts.append({'batch_size':batch_size,'pass':False,'error':'CUDA OOM'})
            del agent;gc.collect();torch.cuda.empty_cache()
            if batch_size==128:raise
    OmegaConf.save(cfg,root/'resolved_flow_config.yaml')
    write(root/'cuda_smoke/report.json',cuda_report)
    file=root/'cuda_smoke/flow_smoke_checkpoint.pth'
    norm={k:v.detach().cpu().clone() for k,v in agent.action_normalizer.state_dict().items()}
    agent.save(str(file),meta={'purpose':'one_optimizer_step_smoke_not_trained_or_qualified_policy','optimizer_steps':1})
    file_sha=hashlib.sha256(file.read_bytes()).hexdigest()
    del agent;gc.collect();torch.cuda.empty_cache()
    restored=make_agent('Flow_Vanilla',cfg);metadata=restored.load(str(file))
    cuda_load=all(torch.equal(v.cpu(),norm[k]) for k,v in restored.action_normalizer.state_dict().items())
    del restored;gc.collect();torch.cuda.empty_cache()
    cpu_cfg=OmegaConf.create(cfg);cpu_cfg.device=cpu_cfg.train.device='cpu'
    torch.set_num_threads(4)
    cpu=make_agent('Flow_Vanilla',cpu_cfg);cpu_meta=cpu.load(str(file));cpu_load=all(torch.equal(v,norm[k]) for k,v in cpu.action_normalizer.state_dict().items())
    obs={'state':val[0]['observations']['state'].unsqueeze(0)}
    start=time.monotonic();out=cpu.sample_action(obs);elapsed=time.monotonic()-start
    torch.manual_seed(2026)
    noise=torch.randn(1,16,8)
    direct=cpu.actor.sample_action(cpu._preprocess_obs(obs),initial_noise=noise)
    actual=cpu.sample_action(obs,initial_noise=noise)
    denormalized=torch.equal(actual,cpu.denormalize_action(direct))
    good=out.shape==(1,16,8) and bool(torch.isfinite(out).all()) and cpu_load and cuda_load and denormalized
    if not good:raise ValueError('checkpoint/inference smoke failed')
    write(root/'cpu_smoke/report.json',{'pass':good,'input_shape':[1,2,33],'output_shape':list(out.shape),'finite':bool(torch.isfinite(out).all()),'denormalized':denormalized,'wall_time':elapsed,'cpu_load':cpu_load})
    write(root/'cuda_smoke/smoke_checkpoint_identity.json',{'checkpoint_file_sha256':file_sha,'artifact_identity':identity,'cuda_load':cuda_load,'cpu_load':cpu_load,'metadata_preserved':metadata==cpu_meta,'purpose':metadata['purpose']})
    # Compatibility failure is exercised without executing a rollout or optimizer step.
    cpu.cfg.agent_sp.artifact_identity.dataset_manifest_sha256='0'*64
    rejected=False
    try:cpu.load(str(file))
    except ValueError:rejected=True
    if not rejected:raise ValueError('checkpoint identity mismatch not rejected')
    return {'status':'ready_for_remote_review' if report['full_training_authorized'] else 'partial_with_localized_failure','first_boundary':None if report['full_training_authorized'] else 'expert_data_collection','dataset':report,'cuda':cuda_report,'config_identity':identity,'checkpoint_sha256':file_sha,'identity_negative_path':True,'full_training_executed':False,'policy_rollout_executed':False}
