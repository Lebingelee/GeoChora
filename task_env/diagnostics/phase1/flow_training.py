"""Locked source-domain Flow training and canonical closed-loop support evaluation."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import traceback

import numpy as np
import torch
from torch.utils.data import DataLoader
from omegaconf import OmegaConf
import yaml
import task_env.alg.agent_factory
from agent_factory.agents.registry import make_agent
from agent_factory.config.resolution import general_resolve
from agent_factory.training.identity import config_identity, digest
from task_env.alg.agent_factory.data.impl.geochora_canonical import logical_hash, CanonicalFlowDataset
from task_env.alg.agent_factory.data.impl.geochora_canonical.selection import validate_manifest
from task_env.alg.state_bc.features import FEATURE_CONTRACT, ACTION_CONTRACT, features, requested_action
from task_env.controllers.canonical import ProductionCanonicalPandaController
from task_env.controllers.canonical.kinematics import ARM
from task_env.diagnostics.phase1.p1_2_runtime import execution, write_json
from task_env.diagnostics.phase1.control.worker import observation
from task_env.runtime.sessions.control import materialize_control, ControlBinding
from task_env.artifacts.execution import ResetSample

BASELINE = '6df732658c8deaa370dc15f8d5c036d358124fa9'
ANCESTORS = ('9c5fcc26fa1164baccd72bfca450d79187b27470',
             '855586c6ba1e0bb5b3d82a97b6910561770cfad8',
             'ee39275cc906773221a5269d3e26e8ae203f9706',
             'f53a5cb1c51e46134aa084171651dd17d2036553', BASELINE)
ROOT = Path('workspace/qualification/phase1/p1_6_flow_training')
PREP = Path('workspace/qualification/phase1/p1_6_flow_preparation')
MANIFEST = PREP/'training_dataset_manifest_v1.json'
PROFILE = Path('task_env/alg/agent_factory/config/profiles/geochora_flow.yaml')
EXPECTED_DATASET = 'bbcc62834182565f84281cf2057803075ff80f53bfacda68943bfdc6aa187677'
EXPECTED_CONFIG = '1b080906fdcd172e23fc6e6cc003bfc7bcf5acd6a421b38177391194b71c3a39'
PILOT_SEEDS = [1000, 1010, 1020, 1040, 1050, 1100]
POLICY_RNG = '100000 + task_seed'
FROZEN_SOURCE_FILES = (
    'task_env/artifacts/contracts.py', 'task_env/artifacts/execution.py',
    'task_env/controllers/canonical/controller.py', 'task_env/controllers/canonical/feedback.py',
    'task_env/controllers/canonical/readiness.py', 'task_env/controllers/canonical/production.py',
    'task_env/tasks/pick_cube/readiness_solution.py', 'task_env/tasks/pick_cube/solution.py',
    'task_env/tasks/pick_cube/canonical_semantics.py', 'task_env/tasks/pick_cube/task.py',
    'task_env/planners/completion.py', 'task_env/trajectory/canonical/contracts.py',
    'task_env/trajectory/canonical/h5.py',
)


def sha(data):
    if isinstance(data, Path):
        return hashlib.sha256(data.read_bytes()).hexdigest()
    if isinstance(data, str):
        try:
            path = Path(data)
            if '\n' not in data and path.is_file():
                return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            pass
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def write_new(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('refusing to overwrite training Evidence: '+str(path))
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def check_ancestry():
    head = git('rev-parse', 'HEAD')
    if head != BASELINE:
        raise ValueError('training_provenance_mismatch: expected branch tip '+BASELINE+', got '+head)
    for ancestor in ANCESTORS:
        if subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, 'HEAD']).returncode:
            raise ValueError('training_provenance_mismatch: missing ancestor '+ancestor)
    link = git('rev-parse', 'HEAD:GeoPhys')
    gp_head = git('-C', 'GeoPhys', 'rev-parse', 'HEAD')
    if link != 'c665ce5028a12bb4d2afe49f05e015fa9b684a39' or gp_head != link or git('-C', 'GeoPhys', 'status', '--porcelain'):
        raise ValueError('training_provenance_mismatch: GeoPhys checkout/gitlink')
    return {'geochora_head':head,'geophys_gitlink':link,'geophys_checkout_head':gp_head,
            'public_main':git('rev-parse','public/main')}


def frozen_source_hashes():
    return {name: {'git_blob': git('rev-parse', f'HEAD:{name}'), 'working_sha256': sha(Path(name))}
            for name in FROZEN_SOURCE_FILES}


def verify_corpus():
    if sha(MANIFEST) != 'ebddea9e70b5c4dfc2fa546ce495dca56de7c08f540e7e9edeb39d6532e459c0':
        raise ValueError('training_provenance_mismatch: corpus manifest file changed')
    manifest = json.loads(MANIFEST.read_text())
    validate_manifest(manifest)
    if not manifest['full_training_authorized'] or len(manifest['selected_train_seeds']) != 80 or len(manifest['selected_validation_seeds']) != 20:
        raise ValueError('training_provenance_mismatch: selected split/authorization')
    if logical_hash(manifest) != EXPECTED_DATASET:
        raise ValueError('training_provenance_mismatch: selected logical dataset hash')
    profile = OmegaConf.load(PROFILE)
    if str(profile.dataset.expert.demo_path) != str(MANIFEST):
        raise ValueError('training_provenance_mismatch: default profile dataset path')
    cfg, _ = general_resolve(file_config=profile)
    cfg.dataset.config = {'allow_failed_for_smoke': False}
    cfg.agent_sp.steps_per_epoch = 81
    cfg.train.actor_iters = 1620
    identity = config_identity(cfg)
    if identity != EXPECTED_CONFIG:
        raise ValueError('training_provenance_mismatch: resolved Flow config '+identity)
    if (cfg.agent_type != 'Flow_Vanilla' or cfg.device != 'cuda' or cfg.train.device != 'cuda'
            or cfg.train.batch_size != 512 or cfg.env.proprio_dim != 33 or cfg.env.action_dim != 8
            or cfg.env.obs_horizon != 2 or cfg.env.pred_horizon != 16 or cfg.env.act_horizon != 8
            or cfg.agent_control_mode != 'absolute_joint' or cfg.env.env_control_mode != 'absolute_joint'
            or cfg.actor.num_inference_steps != 10 or cfg.actor.lr != 1e-4 or cfg.actor.weight_decay != 1e-6):
        raise ValueError('training_provenance_mismatch: Flow protocol/config field')
    if digest(FEATURE_CONTRACT) != '8b2a510ba0cd549480ddc431bfeff3a9d1d87ec1f93ae6d94504e5783e89b1c2' or digest(ACTION_CONTRACT) != '4888f67cacb175ad4bf41195c1c4dc9465e653485e05b53f5ca33a61ad93eba5':
        raise ValueError('training_provenance_mismatch: feature/action identity')
    # Constructing each selected dataset performs strict H5 decoding, SHA/logical identity,
    # metadata/provenance, expert endpoint, success, T+1/T and feature/action checks.
    train = CanonicalFlowDataset(MANIFEST, 'train')
    val = CanonicalFlowDataset(MANIFEST, 'validation')
    if not train.training_eligible or not val.training_eligible or train.failed_seeds or val.failed_seeds:
        raise ValueError('training_provenance_mismatch: ineligible selected trajectory')
    if train.statistics['trajectory_count'] != 80 or val.statistics['trajectory_count'] != 20:
        raise ValueError('training_provenance_mismatch: selected trajectory counts')
    return manifest, cfg, train, val


def resolved_config(cfg):
    content = OmegaConf.to_container(cfg, resolve=True)
    content['agent_sp']['artifact_identity'] = {
        'resolved_config_sha256': config_identity(cfg),
        'dataset_manifest_sha256': EXPECTED_DATASET,
        'agent_type': 'Flow_Vanilla',
        'feature_contract_identity': digest(FEATURE_CONTRACT),
        'action_contract_identity': digest(ACTION_CONTRACT),
    }
    return content, content['agent_sp']['artifact_identity']


def locked_specs(root, cfg, manifest, provenance):
    spec_path=root/'training_spec.yaml'; lock_path=root/'training_spec_lock.json'
    roll_path=root/'rollout_spec.yaml'; roll_lock_path=root/'rollout_spec_lock.json'
    if any(p.exists() for p in (spec_path,lock_path,roll_path,roll_lock_path)):
        raise FileExistsError('training or rollout spec Evidence already exists')
    cfg_map, identity=resolved_config(cfg)
    spec={'schema':'p1_6-flow-training-spec-v1','baseline_commit':BASELINE,'provenance':provenance,
          'dataset':{'manifest':'workspace/qualification/phase1/p1_6_flow_preparation/training_dataset_manifest_v1.json',
                     'logical_sha256':EXPECTED_DATASET,'train_seeds':manifest['selected_train_seeds'],
                     'validation_seeds':manifest['selected_validation_seeds'],'train_trajectories':80,'validation_trajectories':20,
                     'feature_contract_identity':identity['feature_contract_identity'],'action_contract_identity':identity['action_contract_identity']},
          'resolved_config_sha256':identity['resolved_config_sha256'],'resolved_config':cfg_map,
          'training_seed':2026,'device':'cuda','precision':'float32','deterministic_cuda_algorithms':torch.are_deterministic_algorithms_enabled(),
          'cudnn_deterministic':torch.backends.cudnn.deterministic,'cudnn_benchmark':torch.backends.cudnn.benchmark,
          'cuda_matmul_allow_tf32':torch.backends.cuda.matmul.allow_tf32,'cudnn_allow_tf32':torch.backends.cudnn.allow_tf32,
          'batch_size':512,'epoch_budget':20,'steps_per_epoch':81,'actor_iters':1620,
          'optimizer':'AdamW','lr':1e-4,'weight_decay':1e-6,
          'train_loss_interval':100,'validation_interval':1000,'initial_validation':True,'final_validation':True,
          'checkpoint_selection':'minimum validation loss at step 0/1000/1620; exact ties choose earlier step',
          'normalizer_fit':'min/max from selected 80 train trajectories only'}
    roll={'schema':'p1_6-flow-dataset-support-rollout-v1','provider':'geophys','execution_device':'cpu',
          'task_artifact_identity':manifest['identities']['task_artifact'],'reset_samples':'selected trajectory-v1 reset sample identities',
          'controller_identity':manifest['identities']['controller'],'action_mode':'absolute_joint','success':'canonical PickCube cube_lift >= 0.10m',
          'expert_collection_endpoint_not_used_for_gate_m':0.105,'obs_horizon':2,'pred_horizon':16,'act_horizon':8,
          'replan':'observe current two canonical state features, sample 16 actions, execute first8, repeat',
          'policy_rng_rule':POLICY_RNG,'inference_steps':10,'checkpoint':'checkpoints/flow_best_validation.pth',
          'pilot_seeds':PILOT_SEEDS,'pilot_min_successes':5,'train_seeds':manifest['selected_train_seeds'],
          'train_support_min_successes':72,'validation_seeds':manifest['selected_validation_seeds'],
          'validation_gate':'diagnostic_only','max_control_steps_per_episode':2500,
          'fallback_to_expert':False,'policy_inputs':['CanonicalStateView semantic features, last two boundaries'],
          'forbidden_inputs':['expert stage','expert action','readiness hold','future state'],
          'controller_and_environment':'unchanged ProductionCanonicalPandaController, GeoPhys CPU RuntimeSession'}
    spec_path.write_text(yaml.safe_dump(spec,sort_keys=False))
    roll_path.write_text(yaml.safe_dump(roll,sort_keys=False))
    lock={'sha256':sha(spec_path),'locked_at':datetime.now(timezone.utc).isoformat(),'first_optimizer_update':'not yet executed'}
    roll_lock={'sha256':sha(roll_path),'locked_at':datetime.now(timezone.utc).isoformat(),'first_rollout':'not yet executed'}
    write_new(lock_path,lock);write_new(roll_lock_path,roll_lock)
    return spec,lock,roll,roll_lock,identity


def seed_all(seed=2026):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)


def finite_parameters(agent):
    return all(bool(torch.isfinite(p).all()) for p in agent.parameters())


def train(root):
    root=Path(root)
    if root.exists() and any(root.iterdir()):
        # Existing folder may contain only a preparation handoff, never training run outputs.
        allowed={'preflight.json','corpus_preflight.json','design_note.md','regression',
                 'preflight_attempt_1.stdout.log','preflight_attempt_1.stderr.log'}
        unexpected=[str(p) for p in root.iterdir() if p.name not in allowed]
        if unexpected:raise FileExistsError('training Evidence collision: '+','.join(unexpected))
    provenance=check_ancestry()
    manifest,cfg,train_ds,val_ds=verify_corpus()
    if not torch.cuda.is_available():raise RuntimeError('flow_training_numerics: CUDA unavailable')
    seed_all(2026)
    root.mkdir(parents=True, exist_ok=True)
    spec,lock,roll,roll_lock,identity=locked_specs(root,cfg,manifest,provenance)
    write_new(root/'preflight.json',{'pass':True,'baseline':BASELINE,'provenance':provenance,
        'dataset_manifest_sha256':EXPECTED_DATASET,'resolved_config_sha256':identity['resolved_config_sha256'],
        'frozen_lower_layer_source_hashes':frozen_source_hashes(),
        'train_dataset_statistics':train_ds.statistics,'validation_dataset_statistics':val_ds.statistics,
        'validated_train_files':80,'validated_validation_files':20,'frozen_training_spec_sha256':lock['sha256'],
        'frozen_rollout_spec_sha256':roll_lock['sha256']})
    # Dedicated shuffle generator makes sampler order reproducible independently of model RNG consumption.
    generator=torch.Generator(device='cpu');generator.manual_seed(2026)
    train_loader=DataLoader(train_ds,batch_size=512,shuffle=True,drop_last=True,num_workers=0,generator=generator)
    val_loader=DataLoader(val_ds,batch_size=512,shuffle=False,drop_last=False,num_workers=0)
    if len(train_loader)!=81 or 20*len(train_loader)!=1620:raise ValueError('training_provenance_mismatch: final loader budget')
    cfg.agent_sp.artifact_identity=identity
    cfg.agent_sp.epoch_budget=20;cfg.agent_sp.steps_per_epoch=len(train_loader)
    cfg.train.batch_size=512;cfg.train.actor_iters=1620
    OmegaConf.save(cfg,root/'resolved_flow_config.yaml')
    agent=make_agent('Flow_Vanilla',cfg)
    if sum(p.numel() for p in agent.actor.parameters())!=19512264:
        raise ValueError('training_provenance_mismatch: Flow actor architecture')
    if not isinstance(agent.actor_optimizer,torch.optim.AdamW) or agent.actor_optimizer.param_groups[0]['lr']!=1e-4 or agent.actor_optimizer.param_groups[0]['weight_decay']!=1e-6:
        raise ValueError('training_provenance_mismatch: AdamW optimizer configuration')
    agent.fit_action_normalizer(train_ds.get_all_actions().to(agent.device))
    norm={k:v.detach().cpu().clone() for k,v in agent.action_normalizer.state_dict().items()}
    expected_actions=train_ds.get_all_actions()
    if (not torch.equal(norm['min_val'],expected_actions.amin(dim=0)) or not torch.equal(norm['max_val'],expected_actions.amax(dim=0))):
        raise ValueError('training_provenance_mismatch: train-only action normalizer')
    torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats()
    checkpoints=root/'checkpoints';checkpoints.mkdir()
    candidates=[]
    def save_validation_candidate(current,row):
        step=int(row['step']);path=checkpoints/f'validation_step_{step:04d}.pth'
        current.save(str(path),meta={'purpose':'fixed_validation_candidate','validation_step':step,
                                     'validation_loss':float(row['loss']),'validation_samples':row['samples'],
                                     'validation_batches':row['batches']})
        candidates.append({'step':step,'loss':float(row['loss']),'samples':row['samples'],'batches':row['batches'],'file':str(path)})
    started=datetime.now(timezone.utc).isoformat();start=time.monotonic()
    try:
        metrics_root=root/'metrics_run'
        result=agent.train_loop(train_loader,1620,str(metrics_root),validation_loader=val_loader,
                                validation_callback=save_validation_candidate)
        torch.cuda.synchronize();wall=time.monotonic()-start
        if agent.step!=1620 or [r['step'] for r in candidates]!=[0,1000,1620]:
            raise ValueError('flow_training_numerics: training update count/validation points mismatch')
        if result['total_optimizer_steps']!=1620 or result['epoch_equivalent_count']!=20:
            raise ValueError('flow_training_numerics: epoch-equivalent budget mismatch')
        metrics_path=metrics_root/'training_metrics.jsonl'
        metrics=[json.loads(x) for x in metrics_path.read_text().splitlines()]
        train_rows=[r for r in metrics if r['kind']=='train'];val_rows=[r for r in metrics if r['kind']=='validation']
        if [r['step'] for r in train_rows]!=list(range(100,1601,100))+[1620] or [r['step'] for r in val_rows]!=[0,1000,1620]:
            raise ValueError('flow_training_numerics: training/validation logging schedule')
        if any(not math.isfinite(r['loss']) for r in metrics):raise ValueError('flow_training_numerics: nonfinite loss')
        if not finite_parameters(agent):raise ValueError('flow_training_numerics: nonfinite final parameters')
        val_by_step={r['step']:r['loss'] for r in val_rows}
        best=min(val_rows,key=lambda r:(r['loss'],r['step']))
        final_loss=train_rows[-1]['loss']
        agent.save(str(checkpoints/'flow_final_step1620.pth'),meta={'purpose':'flow_final_step1620','train_window_loss':final_loss,'validation_loss':val_by_step[1620]})
        shutil.copyfile(checkpoints/f"validation_step_{best['step']:04d}.pth",checkpoints/'flow_best_validation.pth')
        # Preserve periodic logger snapshots under the requested checkpoint directory.
        for path in metrics_root.glob('step_*.pth'):
            shutil.move(str(path),str(checkpoints/('periodic_'+path.name)))
        shutil.copyfile(metrics_path,root/'training_metrics.jsonl')
        metric_by_step={r['step']:r['loss'] for r in train_rows}
        best_train=metric_by_step.get(best['step'])
        summary={**result,'schema':'p1_6-flow-training-summary-v1','validation_at_fixed_steps':candidates,
                 'total_optimizer_steps':1620,'effective_epochs':20,'epoch_budget':20,'steps_per_epoch':81,
                 'training_wall_time_seconds':wall,'training_started_at':started,'training_finished_at':datetime.now(timezone.utc).isoformat(),
                 'gpu':torch.cuda.get_device_name(),'torch_version':torch.__version__,'cuda_version':torch.version.cuda,
                 'peak_cuda_memory_allocated_bytes':torch.cuda.max_memory_allocated(),
                 'peak_cuda_memory_reserved_bytes':torch.cuda.max_memory_reserved(),
                 'first_logged_train_window_loss':train_rows[0]['loss'],'final_logged_train_window_loss':train_rows[-1]['loss'],
                 'minimum_train_window_loss':min(r['loss'] for r in train_rows),
                 'initial_validation_loss':val_by_step[0],'step1000_validation_loss':val_by_step[1000],
                 'final_validation_loss':val_by_step[1620],'best_validation_loss':best['loss'],'best_validation_step':best['step'],
                 'best_step_train_window_loss':best_train,
                 'curve_classification':('plateaued' if all(r['loss']==train_rows[0]['loss'] for r in train_rows) else
                     'decreasing' if train_rows[-1]['loss']<train_rows[0]['loss'] else 'diverging'),
                 'all_losses_finite':True,'final_parameters_finite':True,
                 'determinism':{'python_seed':2026,'numpy_seed':2026,'torch_cpu_seed':2026,'torch_cuda_seed':2026,
                    'dataloader_generator_seed':2026,'deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),
                    'cudnn_deterministic':torch.backends.cudnn.deterministic,'cudnn_benchmark':torch.backends.cudnn.benchmark,
                    'cuda_matmul_allow_tf32':torch.backends.cuda.matmul.allow_tf32,'cudnn_allow_tf32':torch.backends.cudnn.allow_tf32}}
        write_new(root/'training_summary.json',summary)
        (root/'training_metrics.jsonl').write_text((root/'training_metrics.jsonl').read_text())
        write_new(root/'curve_report.json',{'classification':summary['curve_classification'],'basis':'relative direction/flatness of first and last logged train windows; no absolute convergence threshold'})
        lower_hashes_after=frozen_source_hashes()
        lower_hashes_before=json.loads((root/'preflight.json').read_text())['frozen_lower_layer_source_hashes']
        write_new(root/'lower_layer_freeze_post.json',{'unchanged':lower_hashes_before==lower_hashes_after,
            'before':lower_hashes_before,'after':lower_hashes_after})
        if lower_hashes_before!=lower_hashes_after:
            raise ValueError('lower_phase_recovery_required: frozen lower-layer source changed')
        checkpoint_rows=[]
        train_at={r['step']:r['loss'] for r in train_rows}
        for name,step in (('flow_final_step1620.pth',1620),('flow_best_validation.pth',best['step'])):
            path=checkpoints/name;row={'name':name,'sha256':sha(path),'optimizer_step':step,'epoch_equivalent':step/81,
                'train_loss':train_at.get(step),'validation_loss':val_by_step.get(step),
                'resolved_config_sha256':identity['resolved_config_sha256'],'dataset_manifest_sha256':EXPECTED_DATASET,
                'feature_contract_identity':identity['feature_contract_identity'],'action_contract_identity':identity['action_contract_identity'],
                'normalizer_identity':digest({k:v.tolist() for k,v in norm.items()}),
                'artifact_identity':identity}
            checkpoint_rows.append(row)
        write_new(checkpoints/'checkpoint_manifest.json',{'schema':'flow-checkpoint-manifest-v1','selected_rule':spec['checkpoint_selection'],
                                                          'checkpoints':checkpoint_rows,'validation_candidates':candidates})
        return {'status':'training_complete','summary':summary,'checkpoint_manifest':checkpoint_rows}
    except Exception as error:
        state={'status':'partial_with_localized_failure','first_boundary':'flow_training_numerics',
               'error':str(error),'traceback':traceback.format_exc(),'full_training_started':True,
               'last_optimizer_step':int(agent.step),'full_rollout_started':False}
        if not (root/'training_failure.json').exists():write_new(root/'training_failure.json',state)
        return state


def cpu_check(root):
    from agent_factory.training.identity import config_identity
    from agent_factory.config.resolution import general_resolve
    from agent_factory.agents.registry import make_agent
    manifest=json.loads(MANIFEST.read_text());cfg,_=general_resolve(file_config=OmegaConf.load(PROFILE))
    cfg.dataset.config={'allow_failed_for_smoke':False};cfg.agent_sp.steps_per_epoch=81;cfg.train.actor_iters=1620
    cfg.device='cpu';cfg.train.device='cpu';identity=resolved_config(OmegaConf.load(root/'resolved_flow_config.yaml'))[1]
    cfg.agent_sp.artifact_identity=identity
    if config_identity(OmegaConf.load(root/'resolved_flow_config.yaml'))!=EXPECTED_CONFIG:raise ValueError('checkpoint_cpu_compatibility: saved resolved config identity')
    if torch.cuda.is_initialized():raise ValueError('checkpoint_cpu_compatibility: CUDA was initialized before CPU check')
    checkpoint=root/'checkpoints/flow_best_validation.pth';file_hash=sha(checkpoint)
    checkpoint_manifest=json.loads((root/'checkpoints/checkpoint_manifest.json').read_text())
    best_record=next(r for r in checkpoint_manifest['checkpoints'] if r['name']=='flow_best_validation.pth')
    if best_record['sha256']!=file_hash or best_record['dataset_manifest_sha256']!=EXPECTED_DATASET or best_record['resolved_config_sha256']!=EXPECTED_CONFIG:
        raise ValueError('checkpoint_cpu_compatibility: checkpoint manifest identity mismatch')
    cpu=make_agent('Flow_Vanilla',cfg)
    meta=cpu.load(str(checkpoint))
    payload=torch.load(checkpoint,map_location='cpu',weights_only=False)
    parity=all(torch.equal(v.cpu(),payload['model'][k].cpu()) for k,v in cpu.state_dict().items())
    normalizer=all(torch.equal(v.cpu(),payload['model'][f'action_normalizer.{k}'].cpu())
                    for k,v in cpu.action_normalizer.state_dict().items())
    ds=CanonicalFlowDataset(MANIFEST,'validation');obs={'state':ds[0]['observations']['state'].unsqueeze(0)}
    gen=torch.Generator(device='cpu');gen.manual_seed(2026);noise=torch.randn((1,16,8),generator=gen)
    start=time.monotonic();out=cpu.sample_action(obs,initial_noise=noise);elapsed=time.monotonic()-start
    normalized=cpu.actor.sample_action(cpu._preprocess_obs(obs),initial_noise=noise)
    denormalized=torch.equal(out,cpu.denormalize_action(normalized))
    best_step=int(json.loads((root/'training_summary.json').read_text())['best_validation_step'])
    result={'pass':bool(out.shape==(1,16,8) and torch.isfinite(out).all() and parity and normalizer and denormalized
                         and cpu.step==best_step
                         and not torch.cuda.is_initialized()),
            'checkpoint_sha256':file_hash,'metadata':meta,'step':cpu.step,'model_weights_parity':parity,
            'resolved_config_sha256':EXPECTED_CONFIG,'dataset_manifest_sha256':EXPECTED_DATASET,
            'normalizer_buffers_parity':normalizer,'input_shape':[1,2,33],'output_shape':list(out.shape),
            'finite':bool(torch.isfinite(out).all()),'denormalized':denormalized,'wall_time_seconds':elapsed,
            'cuda_initialized_during_cpu_load_inference':torch.cuda.is_initialized()}
    if not result['pass']:raise ValueError('checkpoint_cpu_compatibility: model/normalizer/inference mismatch')
    write_new(root/'cpu_inference_check.json',result)
    return result


def _episode_worker(seed,cohort,root,output_dir=None):
    from agent_factory.config.resolution import general_resolve
    from agent_factory.agents.registry import make_agent
    from agent_factory.training.identity import config_identity
    from task_env.diagnostics.phase1.state_policy.spec import context
    from task_env.alg.agent_factory.data.impl.geochora_canonical import logical_hash
    from task_env.artifacts.contracts import PoseWorld
    root=Path(root);out=Path(output_dir) if output_dir else root/cohort/f'seed{seed:04d}'
    out.mkdir(parents=True,exist_ok=True)
    if (out/'report.json').exists() or (out/'trace.json').exists():
        raise FileExistsError('rollout already exists; will not rerun seed')
    spec=yaml.safe_load((root/'rollout_spec.yaml').read_text());lock=json.loads((root/'rollout_spec_lock.json').read_text())
    rollout_path=root/'rollout_spec.yaml'
    if sha(rollout_path)!=lock['sha256']:raise ValueError('rollout_spec lock mismatch')
    m=json.loads(MANIFEST.read_text());allowed=m['selected_train_seeds'] if cohort in ('pilot_train_support','full_train_support') else m['selected_validation_seeds']
    if seed not in allowed:raise ValueError('unselected rollout seed')
    row=next(r for r in m['trajectories'] if r['seed']==seed)
    sample_spec=yaml.safe_load((PREP/'supplement_manifest.yaml').read_text())
    sample=ResetSample.from_mapping(sample_spec['samples'][str(seed)])
    if sample.identity_hash!=row['reset_sample_hash']:raise ValueError('rollout ResetSample identity mismatch')
    original_sample_mapping=sample.to_mapping()
    cfg,_=general_resolve(file_config=OmegaConf.load(root/'resolved_flow_config.yaml'))
    cfg.device='cpu';cfg.train.device='cpu';cfg.agent_sp.artifact_identity=yaml.safe_load((root/'training_spec.yaml').read_text())['resolved_config']['agent_sp']['artifact_identity']
    agent=make_agent('Flow_Vanilla',cfg);checkpoint=root/'checkpoints/flow_best_validation.pth'
    checkpoint_hash=sha(checkpoint);meta=agent.load(str(checkpoint))
    torch.set_num_threads(4)
    gen=torch.Generator(device='cpu');gen.manual_seed(100000+seed)
    artifact,source,_=context();session=None;trace=[]
    report={'seed':seed,'cohort':cohort,'provider':'geophys','checkpoint_sha256':checkpoint_hash,
            'policy_rng_seed':100000+seed,'sample_hash':sample.identity_hash,'success':False,'steps_to_success':None,
            'issued_policy_action_count':0,'replanning_count':0,'action_clipping_count':0,
            'per_dimension_clipping_count':[0]*8,'max_preclamp_violation_by_dimension':[0.]*8,
            'terminated':False,'truncated':False,'failure_reason':None,'exception':None}
    names=list(ARM)+['gripper_scalar'];history=[];max_lift=0.;finite_state=finite_action=True
    try:
        session=materialize_control(artifact,execution('geophys'),source=source,binding=ControlBinding('panda-v1/gripper',.08))
        session.reset(sample);state=session.snapshot();feedback=session.control_feedback(state)
        controller=ProductionCanonicalPandaController.from_source(artifact,source);controller.reset(state,feedback)
        _,info,_=observation(state,artifact);max_lift=float(info['task_metrics']['cube_lift'])
        history.append(features(state,feedback));task_success=bool(info['is_success']) and max_lift>=.10
        control_step=0
        while not task_success and control_step<int(spec['max_control_steps_per_episode']):
            if len(history)<2:obsarr=np.stack([history[0],history[0]])
            else:obsarr=np.stack(history[-2:])
            obs={'state':torch.from_numpy(obsarr.copy()).unsqueeze(0)}
            noise=torch.randn((1,16,8),generator=gen)
            agent.actor.eval()
            with torch.no_grad():values=agent.sample_action(obs,initial_noise=noise)
            if values.shape!=(1,16,8):raise ValueError('runner_action_boundary: Flow output shape')
            chunk=values[0].cpu().numpy();finite_action &= bool(np.isfinite(chunk).all())
            if not finite_action:raise ValueError('runner_action_boundary: nonfinite policy chunk')
            report['replanning_count']+=1
            for action in chunk[:8]:
                if control_step>=int(spec['max_control_steps_per_episode']):break
                request=requested_action(action);canonical,target=controller.compute(state,feedback,request)
                interpreted=np.asarray(canonical.interpreted_values,dtype=np.float64);raw=np.asarray(request.values,dtype=np.float64)
                violation=np.abs(raw-interpreted)
                report['issued_policy_action_count']+=1
                clipped=violation>0
                report['action_clipping_count']+=int(bool(clipped.any()))
                report['per_dimension_clipping_count']=[a+int(b) for a,b in zip(report['per_dimension_clipping_count'],clipped)]
                report['max_preclamp_violation_by_dimension']=[max(a,float(b)) for a,b in zip(report['max_preclamp_violation_by_dimension'],violation)]
                applied=session.apply_control(target);before=state;state=session.step()
                if state.control_step != before.control_step+1 or state.simulation_time <= before.simulation_time:
                    raise ValueError('runner_action_boundary: canonical control step/time did not advance once')
                feedback=session.control_feedback(state)
                control_step+=1
                feature=features(state,feedback);finite_state &= bool(np.isfinite(feature).all())
                if not finite_state:raise ValueError('runner_action_boundary: nonfinite canonical state')
                history.append(feature);_,info,_=observation(state,artifact);max_lift=max(max_lift,float(info['task_metrics']['cube_lift']))
                task_success=bool(info['is_success']) and float(info['task_metrics']['cube_lift'])>=.10
                trace.append({'control_step':state.control_step,'simulation_time':state.simulation_time,
                    'observation_state_33':feature.tolist(),'policy_action':raw.tolist(),'canonical_action':canonical.to_mapping(),
                    'controller_target':target.to_mapping(),'applied_control':applied.to_mapping(),
                    'task_metrics':info['task_metrics'],'task_success':task_success,
                    'preclamp_violation_by_dimension':violation.tolist()})
                if task_success:
                    report['success']=True;report['steps_to_success']=state.control_step;report['terminated']=True
                    break
            if task_success:break
        report.update(finite_state=finite_state,finite_action=finite_action,max_cube_lift=max_lift,
            actions_issued=report['issued_policy_action_count'],steps=control_step,
            action_clipping_rate=report['action_clipping_count']/max(1,report['issued_policy_action_count']),
            horizon_reached=control_step==int(spec['max_control_steps_per_episode']),
            task_success_threshold_m=.10,checkpoint_metadata_identity=meta.get('artifact_identity'),
            reset_sample_unchanged=sample.to_mapping()==original_sample_mapping,
            model_output_physical_action='checkpoint denormalized absolute-joint action')
        report['truncated']=bool(not task_success and report['horizon_reached'])
        report['failure_reason']=None if task_success else ('policy_control_horizon' if report['truncated'] else 'cube_lift_below_threshold')
    except Exception as error:
        report.update(exception=str(error),traceback=traceback.format_exc(),finite_state=finite_state,finite_action=finite_action,
                      max_cube_lift=max_lift,steps=len(trace),failure_reason='runner_action_boundary')
    finally:
        if session is not None:
            try:session.close()
            except Exception as error:
                report['close_error']=str(error);report['success']=False;report['failure_reason']='runtime_close_failure'
    report['trace_sha256']=sha(json.dumps(trace,sort_keys=True,separators=(',',':'),allow_nan=False))
    write_new(out/'trace.json',trace);write_new(out/'report.json',report)
    return report


def run_cohort(root,cohort,seeds,output_root=None):
    root=Path(root);output_root=Path(output_root) if output_root else root/cohort
    output_root.mkdir(parents=True,exist_ok=True)
    results=[];env={**os.environ,'PYTHONPATH':'GeoPhys/src:.','PYTHONDONTWRITEBYTECODE':'1'}
    for seed in seeds:
        directory=output_root/f'seed{seed:04d}';report_path=directory/'report.json'
        if report_path.exists():raise FileExistsError('rollout already exists; will not rerun seed')
        command=[sys.executable,'-m','task_env.diagnostics.phase1.flow_training','--stage','episode','--seed',str(seed),'--cohort',cohort,'--root',str(root),'--episode-output',str(directory)]
        directory.mkdir(parents=True,exist_ok=False)
        (directory/'command.txt').write_text(' '.join(command)+'\n')
        start=time.monotonic()
        with (directory/'stdout.log').open('w') as out,(directory/'stderr.log').open('w') as err:
            process=subprocess.run(command,env=env,stdout=out,stderr=err)
        report=json.loads(report_path.read_text()) if report_path.exists() else {'seed':seed,'success':False,'exception':'isolated episode report missing','return_code':process.returncode,'failure_reason':'runner_action_boundary'}
        report['wall_time_seconds']=time.monotonic()-start;results.append(report)
        (output_root/'summary_progress.json').write_text(json.dumps({'completed':len(results),'target':len(seeds),'results':results},indent=2)+'\n')
        print(cohort,seed,report.get('success'),report.get('steps'),report.get('failure_reason'),flush=True)
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['train','cpu-check','pilot','train-support','validation-support','episode'],required=True)
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--seed',type=int);p.add_argument('--cohort');p.add_argument('--episode-output',type=Path)
    a=p.parse_args();root=a.root
    if a.stage=='train':result=train(root)
    elif a.stage=='cpu-check':result=cpu_check(root)
    elif a.stage=='episode':result=_episode_worker(a.seed,a.cohort,root,a.episode_output)
    elif a.stage in ('pilot','train-support','validation-support'):
        report=json.loads((root/'training_summary.json').read_text())
        if report.get('total_optimizer_steps')!=1620:raise ValueError('rollout cannot start before exactly1620 completed updates')
        if a.stage=='pilot':cohort='pilot_train_support';seeds=PILOT_SEEDS
        elif a.stage=='train-support':
            gate=json.loads((root/'pilot_train_support_attempt2/pilot_summary.json').read_text())
            if gate['successes']<5:raise ValueError('pilot gate failed; no train-support evaluation')
            cohort='full_train_support';seeds=json.loads(MANIFEST.read_text())['selected_train_seeds']
        else:
            gate=json.loads((root/'competence_report.json').read_text())
            if gate['train_support']['successes']<72:raise ValueError('train support competence gate failed; no validation evaluation')
            cohort='validation_support';seeds=json.loads(MANIFEST.read_text())['selected_validation_seeds']
        output_root=(root/'pilot_train_support_attempt2') if a.stage=='pilot' else None
        results=run_cohort(root,cohort,seeds,output_root=output_root)
        successes=sum(bool(r.get('success')) for r in results)
        if a.stage=='pilot':
            result={'successes':successes,'attempted':len(results),'gate':successes>=5,'seeds':seeds,
                    'first_boundary':None if successes>=5 else 'dataset_support_policy_behavior','results':results}
            write_new(root/'pilot_train_support_attempt2/pilot_summary.json',result)
        elif a.stage=='train-support':
            good=[r['steps_to_success'] for r in results if r.get('success')]
            result={'train_support':{'successes':successes,'failures':len(results)-successes,'attempted':len(results),
                    'success_rate':successes/len(results),'steps_to_success':{'median':float(np.median(good)) if good else None,'mean':float(np.mean(good)) if good else None},
                    'max_cube_lift':{'min':float(min(r.get('max_cube_lift',0.) for r in results)),'max':float(max(r.get('max_cube_lift',0.) for r in results)),'mean':float(np.mean([r.get('max_cube_lift',0.) for r in results]))},
                    'action_clipping':{'actions':sum(r.get('issued_policy_action_count',0) for r in results),'clipped':sum(r.get('action_clipping_count',0) for r in results),
                       'per_dimension':np.sum([r.get('per_dimension_clipping_count',[0]*8) for r in results],axis=0).tolist()},
                    'results':results},'status':'ready_for_remote_review' if successes>=72 else 'partial_with_localized_failure',
                    'first_boundary':None if successes>=72 else 'dataset_support_policy_behavior'}
            write_new(root/'competence_report.json',result)
        else:
            result={'validation_support':{'successes':successes,'failures':len(results)-successes,'attempted':len(results),
                    'success_rate':successes/len(results),'steps_to_success':[r.get('steps_to_success') for r in results],
                    'max_cube_lift':[r.get('max_cube_lift') for r in results],'clipping_count':sum(r.get('action_clipping_count',0) for r in results),
                    'failure_reasons':{str(s):next((r.get('failure_reason') for r in results if r['seed']==s),None) for s in seeds},
                    'diagnostic_only':True},'training_support_gate_pass':True}
            if (root/'competence_report.json').exists():
                base=json.loads((root/'competence_report.json').read_text());base.update(result);result=base
            else:write_new(root/'competence_report.json',result)
            write_json(root/'competence_report.json',result)
    else:raise ValueError('unsupported phase')
    print(result.get('status',result.get('successes',result.get('status','done'))))


if __name__=='__main__':main()
