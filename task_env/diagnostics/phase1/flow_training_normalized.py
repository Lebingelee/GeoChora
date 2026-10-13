"""Train and compare an additive P1.6 Flow z-score / q01-q99 policy variant."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
import random
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
from agent_factory.data.impl.geochora_canonical import CanonicalFlowDataset
from task_env.alg.state_bc.features import FEATURE_CONTRACT, ACTION_CONTRACT
from task_env.diagnostics.phase1 import flow_training as previous


BASELINE = 'cda511f49eb544dabe685ec1dbcc6345884d66c8'
ROOT = Path('workspace/qualification/phase1/p1_6_flow_training_q99_zscore_80ep')
EPOCHS = 80
TRAINING_SEED = 2026
PILOT_SEEDS = [1000, 1010, 1020, 1040, 1050, 1100]
Q_LOW = 0.01
Q_HIGH = 0.99


def sha(value):
    if isinstance(value, Path):
        value = value.read_bytes()
    elif isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f'refusing to overwrite new-variant Evidence: {path}')
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def check_provenance():
    head = git('rev-parse', 'HEAD')
    if subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE, 'HEAD']).returncode:
        raise ValueError(f'provenance_mismatch: missing finalized training ancestor {BASELINE}')
    link = git('rev-parse', 'HEAD:GeoPhys')
    provider_head = git('-C', 'GeoPhys', 'rev-parse', 'HEAD')
    provider_status = git('-C', 'GeoPhys', 'status', '--porcelain')
    if link != 'c665ce5028a12bb4d2afe49f05e015fa9b684a39' or provider_head != link or provider_status:
        raise ValueError('provenance_mismatch: GeoPhys gitlink/checkout changed')
    return {'geochora_head': head, 'required_ancestor': BASELINE,
            'geophys_gitlink': link, 'geophys_checkout_head': provider_head,
            'public_main': git('rev-parse', 'public/main')}


def seed_all(seed=TRAINING_SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def selected_config():
    cfg, _ = general_resolve(file_config=OmegaConf.load(previous.PROFILE))
    cfg.dataset.config = {'allow_failed_for_smoke': False}
    cfg.actor.obs_norm = {'type': 'mean_std', 'params': {}}
    cfg.actor.norm = {'type': 'quantile', 'params': {
        'q_low': Q_LOW, 'q_high': Q_HIGH, 'clip': True}}
    cfg.agent_sp.epoch_budget = EPOCHS
    cfg.agent_sp.steps_per_epoch = 81
    cfg.train.actor_iters = EPOCHS * 81
    cfg.train.save_root = str(ROOT / 'agent_run')
    cfg.train.exp_name = 'flow_vanilla_zscore_q01_q99_80ep'
    return cfg


def artifact_identity(cfg):
    return {
        'resolved_config_sha256': config_identity(cfg),
        'dataset_manifest_sha256': previous.EXPECTED_DATASET,
        'agent_type': 'Flow_Vanilla',
        'feature_contract_identity': digest(FEATURE_CONTRACT),
        'action_contract_identity': digest(ACTION_CONTRACT),
    }


def load_variant_config(path):
    """Resolve agent_factory's typed config, then restore this run's opt-in key."""
    raw = OmegaConf.load(path)
    obs_norm = OmegaConf.select(raw, 'actor.obs_norm', default=None)
    if obs_norm is not None:
        OmegaConf.set_struct(raw, False)
        del raw.actor['obs_norm']
    cfg, _ = general_resolve(file_config=raw)
    if obs_norm is not None:
        OmegaConf.set_struct(cfg, False)
        cfg.actor.obs_norm = obs_norm
    return cfg


def prepare():
    root = ROOT
    if root.exists() and any(p.name in {
        'training_spec.yaml', 'training_spec_lock.json', 'resolved_flow_config.yaml',
        'training_metrics.jsonl', 'training_failure.json'
    } for p in root.iterdir()):
        raise FileExistsError('new training variant has already been prepared; preserving Evidence')
    provenance = check_provenance()
    manifest, old_cfg, train_ds, val_ds = previous.verify_corpus()
    if train_ds.statistics['trajectory_count'] != 80 or val_ds.statistics['trajectory_count'] != 20:
        raise ValueError('training_provenance_mismatch: corpus counts')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable for the frozen Flow training route')

    cfg = selected_config()
    if cfg.agent_type != 'Flow_Vanilla' or cfg.train.batch_size != 512:
        raise ValueError('variant config unexpectedly changed architecture or batch size')
    if cfg.env.proprio_dim != 33 or cfg.env.action_dim != 8 or (cfg.env.obs_horizon,
            cfg.env.pred_horizon, cfg.env.act_horizon) != (2, 16, 8):
        raise ValueError('variant config changed the frozen state/action horizon contract')
    if cfg.actor.lr != 1e-4 or cfg.actor.weight_decay != 1e-6 or cfg.actor.num_inference_steps != 10:
        raise ValueError('variant config changed the frozen learner controls')
    identity = artifact_identity(cfg)
    cfg.agent_sp.artifact_identity = identity
    cfg_content = OmegaConf.to_container(cfg, resolve=True)
    cfg_content['agent_sp']['artifact_identity'] = identity
    cfg_content['dataset']['expert']['demo_path'] = str(previous.MANIFEST)
    cfg_content_sha = config_identity(cfg)
    if cfg_content_sha != identity['resolved_config_sha256']:
        raise ValueError('resolved config identity is not stable')

    # Seed before DataLoader construction; its own generator is derived from the
    # same frozen seed, keeping shuffle independent of model RNG consumption.
    seed_all()
    generator = torch.Generator(device='cpu')
    generator.manual_seed(TRAINING_SEED)
    loader = DataLoader(train_ds, batch_size=512, shuffle=True, drop_last=True,
                        num_workers=0, generator=generator)
    val_loader = DataLoader(val_ds, batch_size=512, shuffle=False, drop_last=False,
                            num_workers=0)
    if len(loader) != 81 or len(loader) * EPOCHS != 6480:
        raise ValueError('actual DataLoader semantics do not produce the frozen 80-epoch budget')

    state = train_ds.get_all_states().float()
    action = train_ds.get_all_actions().float()
    state_mean = state.mean(dim=0)
    state_std = state.std(dim=0)
    action_low = torch.quantile(action, Q_LOW, dim=0)
    action_high = torch.quantile(action, Q_HIGH, dim=0)
    if not torch.isfinite(state_mean).all() or not torch.isfinite(state_std).all() or (state_std <= 0).any():
        raise ValueError('training observations contain invalid/constant normalization dimensions')
    if not torch.isfinite(action_low).all() or not (action_high > action_low).all():
        raise ValueError('training actions contain invalid q01/q99 normalization bounds')

    root.mkdir(parents=True, exist_ok=True)
    lower_hashes = previous.frozen_source_hashes()
    status = git('status', '--short')
    spec = {
        'schema': 'p1_6-flow-zscore-q01-q99-80epoch-spec-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_baseline': provenance,
        'branch': git('branch', '--show-current'),
        'source_working_tree_status': status.splitlines(),
        'frozen_lower_layer_source_hashes': lower_hashes,
        'dataset': {'manifest': str(previous.MANIFEST),
                    'manifest_sha256': sha(previous.MANIFEST),
                    'logical_identity': previous.EXPECTED_DATASET,
                    'train_trajectory_count': 80, 'validation_trajectory_count': 20,
                    'train_samples': len(train_ds), 'validation_samples': len(val_ds),
                    'roles': {'training': manifest['selected_train_seeds'],
                              'validation': manifest['selected_validation_seeds']}},
        'learner': {'agent_type': 'Flow_Vanilla', 'backbone': 'ConditionalUnet1D',
                    'parameter_count': 19512264, 'device': 'cuda', 'precision': 'float32',
                    'training_seed': TRAINING_SEED, 'batch_size': 512,
                    'epoch_budget': EPOCHS, 'steps_per_epoch': len(loader),
                    'actor_iters': EPOCHS * len(loader), 'optimizer': 'AdamW',
                    'lr': 1e-4, 'weight_decay': 1e-6,
                    'validation_rng_seed': TRAINING_SEED,
                    'validation_schedule_steps': [0, *range(1000, 6001, 1000), 6480],
                    'train_loss_interval': 100,
                    'checkpoint_rule': 'minimum full validation loss; earlier step wins exact ties'},
        'policy_contract': {'observation': 'state-only canonical 33D', 'state_dim': 33,
                            'feature_contract_identity': identity['feature_contract_identity'],
                            'obs_horizon': 2, 'action': 'absolute_joint', 'action_dim': 8,
                            'pred_horizon': 16, 'act_horizon': 8,
                            'action_contract_identity': identity['action_contract_identity'],
                            'inference_steps': 10},
        'normalization': {
            'observation': {'type': 'per_feature_z_score', 'source': 'selected train trajectories only',
                            'fit_samples': int(state.shape[0]), 'std': 'torch.std default unbiased=True',
                            'epsilon': 1e-8, 'validation_in_fit': False,
                            'mean': state_mean.tolist(), 'std_values': state_std.tolist()},
            'action': {'type': 'per_dimension_quantile_affine', 'q_low': Q_LOW, 'q_high': Q_HIGH,
                       'mapped_range': [-1.0, 1.0], 'clip_outside_quantile_interval': True,
                       'source': 'selected train transition targets only',
                       'fit_samples': int(action.shape[0]), 'validation_in_fit': False,
                       'low': action_low.tolist(), 'high': action_high.tolist()},
        },
        'resolved_config_sha256': identity['resolved_config_sha256'],
        'artifact_identity': identity,
        'resolved_config': cfg_content,
        'selection_rule': 'minimum validation loss among steps 0,1000,...,6000,6480; no rollout-based selection',
        'policy_evaluation_scope': 'six fixed CPU GeoPhys pilot seeds only; no full train-support or validation rollout',
    }
    spec_path = root / 'training_spec.yaml'
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False))
    lock = {'sha256': sha(spec_path), 'locked_at': datetime.now(timezone.utc).isoformat(),
            'first_optimizer_update': 'not yet executed'}
    write_new(root / 'training_spec_lock.json', lock)
    cfg_path = root / 'resolved_flow_config.yaml'
    OmegaConf.save(cfg, cfg_path)
    write_new(root / 'preflight.json', {
        'pass': True, 'provenance': provenance, 'dataset_manifest_sha256': sha(previous.MANIFEST),
        'dataset_logical_identity': previous.EXPECTED_DATASET,
        'resolved_config_sha256': identity['resolved_config_sha256'],
        'training_spec_sha256': lock['sha256'],
        'actual_steps_per_epoch': len(loader), 'actor_iters': EPOCHS * len(loader),
        'training_statistics': {'samples': len(train_ds), 'states_shape': list(state.shape),
                                'actions_shape': list(action.shape),
                                'state_mean': state_mean.tolist(), 'state_std': state_std.tolist(),
                                'action_q01': action_low.tolist(), 'action_q99': action_high.tolist()},
        'lower_layer_source_hashes': lower_hashes,
    })
    return {'status': 'prepared', 'spec_sha256': lock['sha256'],
            'resolved_config_sha256': identity['resolved_config_sha256'],
            'train_samples': len(train_ds), 'validation_samples': len(val_ds),
            'steps_per_epoch': len(loader), 'actor_iters': EPOCHS * len(loader)}


def training_curve(train_rows):
    if not train_rows or any(not math.isfinite(row['loss']) for row in train_rows):
        return 'unstable/non-finite'
    first, last = train_rows[0]['loss'], train_rows[-1]['loss']
    if last < first:
        return 'decreasing'
    if last <= first * 1.05:
        return 'plateaued'
    return 'diverging'


def train():
    root = ROOT
    provenance = check_provenance()
    spec_path = root / 'training_spec.yaml'
    lock_path = root / 'training_spec_lock.json'
    if not spec_path.is_file() or not lock_path.is_file():
        raise FileNotFoundError('prepare and lock the variant before training')
    spec = yaml.safe_load(spec_path.read_text())
    lock = json.loads(lock_path.read_text())
    if sha(spec_path) != lock['sha256']:
        raise ValueError('training spec lock mismatch')
    if spec['resolved_config_sha256'] != spec['artifact_identity']['resolved_config_sha256']:
        raise ValueError('resolved config identity mismatch')
    cfg = load_variant_config(root / 'resolved_flow_config.yaml')
    identity = spec['artifact_identity']
    if config_identity(cfg) != spec['resolved_config_sha256']:
        raise ValueError('resolved config changed after lock')
    cfg.agent_sp.artifact_identity = identity
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable for frozen Flow training')
    if (root / 'metrics_run' / 'training_metrics.jsonl').exists() or (root / 'training_summary.json').exists():
        raise FileExistsError('training has already started; refusing to overwrite its evidence')

    manifest, old_cfg, train_ds, val_ds = previous.verify_corpus()
    if not train_ds.training_eligible or not val_ds.training_eligible:
        raise ValueError('frozen success-conditioned training/validation corpus is not eligible')
    seed_all()
    generator = torch.Generator(device='cpu')
    generator.manual_seed(TRAINING_SEED)
    train_loader = DataLoader(train_ds, batch_size=512, shuffle=True, drop_last=True,
                              num_workers=0, generator=generator)
    validation_loader = DataLoader(val_ds, batch_size=512, shuffle=False, drop_last=False,
                                  num_workers=0)
    if len(train_loader) != 81 or len(train_loader) * EPOCHS != 6480:
        raise ValueError('actual train loader does not match the locked epoch budget')
    agent = make_agent('Flow_Vanilla', cfg)
    if sum(p.numel() for p in agent.actor.parameters()) != 19512264:
        raise ValueError('Flow actor parameter count changed')
    if not isinstance(agent.actor_optimizer, torch.optim.AdamW):
        raise ValueError('optimizer changed from AdamW')
    optimizer = agent.actor_optimizer.param_groups[0]
    if optimizer['lr'] != 1e-4 or optimizer['weight_decay'] != 1e-6:
        raise ValueError('optimizer hyperparameters changed')

    train_actions = train_ds.get_all_actions().to(agent.device).float()
    train_states = train_ds.get_all_states().to(agent.device).float()
    agent.fit_action_normalizer(train_actions)
    agent.fit_obs_normalizer(train_states)
    action_state = {k: v.detach().cpu().clone() for k, v in agent.action_normalizer.state_dict().items()}
    obs_state = {k: v.detach().cpu().clone() for k, v in agent.obs_normalizer.state_dict().items()}
    if not torch.allclose(action_state['low_val'], torch.quantile(train_actions.cpu(), Q_LOW, dim=0)):
        raise ValueError('action q01 normalizer was not fitted from the selected train corpus')
    if not torch.allclose(action_state['high_val'], torch.quantile(train_actions.cpu(), Q_HIGH, dim=0)):
        raise ValueError('action q99 normalizer was not fitted from the selected train corpus')
    if not torch.allclose(obs_state['mean'], train_states.mean(0).cpu()) or not torch.allclose(obs_state['std'], train_states.std(0).cpu()):
        raise ValueError('observation z-score statistics do not match the selected train corpus')

    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    checkpoint_dir = root / 'checkpoints'
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    candidates = []

    def save_candidate(current, row):
        step = int(row['step'])
        path = checkpoint_dir / f'validation_step_{step:04d}.pth'
        current.save(str(path), meta={'purpose': 'fixed_validation_candidate', 'validation_step': step,
                                      'validation_loss': float(row['loss']),
                                      'validation_samples': row['samples'], 'validation_batches': row['batches'],
                                      'normalizer_identity': digest({'action': {k: v.tolist() for k, v in action_state.items()},
                                                                     'observation': {k: v.tolist() for k, v in obs_state.items()}})})
        candidates.append({'step': step, 'loss': float(row['loss']), 'samples': row['samples'],
                           'batches': row['batches'], 'file': str(path)})

    start_time = time.monotonic()
    training_started = datetime.now(timezone.utc).isoformat()
    try:
        result = agent.train_loop(train_loader, 6480, save_dir=str(root / 'metrics_run'),
                                  validation_loader=validation_loader, validation_callback=save_candidate)
        torch.cuda.synchronize()
        wall = time.monotonic() - start_time
        if agent.step != 6480 or [row['step'] for row in candidates] != [0, *range(1000, 6001, 1000), 6480]:
            raise ValueError('training update or validation schedule differs from frozen spec')
        metrics_path = root / 'metrics_run' / 'training_metrics.jsonl'
        rows = [json.loads(line) for line in metrics_path.read_text().splitlines()]
        train_rows = [row for row in rows if row['kind'] == 'train']
        val_rows = [row for row in rows if row['kind'] == 'validation']
        if [row['step'] for row in train_rows] != [*range(100, 6401, 100), 6480]:
            raise ValueError('train loss logging schedule differs from frozen spec')
        if [row['step'] for row in val_rows] != [0, *range(1000, 6001, 1000), 6480]:
            raise ValueError('validation schedule differs from frozen spec')
        if any(not math.isfinite(row['loss']) for row in rows):
            raise ValueError('flow_training_numerics: non-finite train/validation loss')
        if not all(bool(torch.isfinite(parameter).all()) for parameter in agent.parameters()):
            raise ValueError('flow_training_numerics: non-finite model parameter')

        val_by_step = {row['step']: row['loss'] for row in val_rows}
        best = min(val_rows, key=lambda row: (row['loss'], row['step']))
        final_train_loss = train_rows[-1]['loss']
        agent.save(str(checkpoint_dir / 'flow_final_step6480.pth'), meta={
            'purpose': 'flow_final_step6480', 'train_window_loss': final_train_loss,
            'validation_loss': val_by_step[6480], 'selected_training_spec_sha256': lock['sha256']})
        best_source = checkpoint_dir / f"validation_step_{best['step']:04d}.pth"
        (checkpoint_dir / 'flow_best_validation.pth').write_bytes(best_source.read_bytes())
        for path in (root / 'metrics_run').glob('step_*.pth'):
            (checkpoint_dir / ('periodic_' + path.name)).write_bytes(path.read_bytes())
            path.unlink()
        (root / 'training_metrics.jsonl').write_bytes(metrics_path.read_bytes())

        summary = {**result, 'schema': 'p1_6-flow-normalized-80epoch-summary-v1',
                   'training_spec_sha256': lock['sha256'],
                   'resolved_config_sha256': spec['resolved_config_sha256'],
                   'dataset_manifest_sha256': spec['dataset']['manifest_sha256'],
                   'total_optimizer_steps': 6480, 'effective_epochs': 80, 'epoch_budget': 80,
                   'steps_per_epoch': 81, 'actor_iters': 6480,
                   'training_wall_time_seconds': wall,
                   'training_started_at': training_started,
                   'training_finished_at': datetime.now(timezone.utc).isoformat(),
                   'gpu': torch.cuda.get_device_name(), 'torch_version': torch.__version__,
                   'cuda_version': torch.version.cuda,
                   'peak_cuda_memory_allocated_bytes': torch.cuda.max_memory_allocated(),
                   'peak_cuda_memory_reserved_bytes': torch.cuda.max_memory_reserved(),
                   'initial_validation_loss': val_by_step[0], 'step_1000_validation_loss': val_by_step[1000],
                   'final_validation_loss': val_by_step[6480], 'minimum_validation_loss': best['loss'],
                   'best_validation_step': best['step'],
                   'first_train_window_loss': train_rows[0]['loss'],
                   'final_train_window_loss': train_rows[-1]['loss'],
                   'minimum_train_window_loss': min(row['loss'] for row in train_rows),
                   'curve_classification': training_curve(train_rows),
                   'validation_candidates': candidates,
                   'normalizer_identity': digest({'action': {k: v.tolist() for k, v in action_state.items()},
                                                  'observation': {k: v.tolist() for k, v in obs_state.items()}}),
                   'normalizer_statistics': {'action_low_q01': action_state['low_val'].tolist(),
                                             'action_high_q99': action_state['high_val'].tolist(),
                                             'observation_mean': obs_state['mean'].tolist(),
                                             'observation_std': obs_state['std'].tolist()}}
        write_new(root / 'training_summary.json', summary)
        hashes_after = previous.frozen_source_hashes()
        if hashes_after != spec['frozen_lower_layer_source_hashes']:
            raise ValueError('lower_phase_recovery_required: frozen lower-layer sources changed')
        write_new(root / 'lower_layer_freeze_post.json', {'unchanged': True, 'after': hashes_after})

        records = []
        for name, step, validation_loss_value in (
            ('flow_final_step6480.pth', 6480, val_by_step[6480]),
            ('flow_best_validation.pth', int(best['step']), float(best['loss']))):
            path = checkpoint_dir / name
            records.append({'name': name, 'sha256': sha(path), 'optimizer_step': step,
                            'epoch_equivalent': step / 81,
                            'train_loss': next((r['loss'] for r in train_rows if r['step'] == step), None),
                            'validation_loss': validation_loss_value,
                            'resolved_config_sha256': spec['resolved_config_sha256'],
                            'dataset_manifest_sha256': spec['dataset']['manifest_sha256'],
                            'feature_contract_identity': identity['feature_contract_identity'],
                            'action_contract_identity': identity['action_contract_identity'],
                            'normalizer_identity': summary['normalizer_identity'],
                            'artifact_identity': identity})
        write_new(checkpoint_dir / 'checkpoint_manifest.json', {
            'schema': 'flow-checkpoint-manifest-v2', 'selected_rule': spec['learner']['checkpoint_rule'],
            'checkpoints': records, 'validation_candidates': candidates})
        return {'status': 'training_complete', 'summary': summary, 'checkpoint_records': records}
    except Exception as error:
        failure = {'status': 'partial_with_localized_failure', 'first_boundary': 'flow_training_numerics',
                   'error': str(error), 'traceback': traceback.format_exc(),
                   'last_optimizer_step': int(agent.step), 'pilot_started': False}
        if not (root / 'training_failure.json').exists():
            write_new(root / 'training_failure.json', failure)
        return failure


def cpu_check():
    root = ROOT
    spec = yaml.safe_load((root / 'training_spec.yaml').read_text())
    lock = json.loads((root / 'training_spec_lock.json').read_text())
    if sha(root / 'training_spec.yaml') != lock['sha256']:
        raise ValueError('training spec lock mismatch')
    if torch.cuda.is_initialized():
        raise ValueError('CPU check must run in a fresh process without initializing CUDA')
    cfg = load_variant_config(root / 'resolved_flow_config.yaml')
    cfg.device = 'cpu'
    cfg.train.device = 'cpu'
    cfg.agent_sp.artifact_identity = spec['artifact_identity']
    checkpoint = root / 'checkpoints' / 'flow_best_validation.pth'
    manifest = json.loads((root / 'checkpoints' / 'checkpoint_manifest.json').read_text())
    record = next(row for row in manifest['checkpoints'] if row['name'] == 'flow_best_validation.pth')
    if sha(checkpoint) != record['sha256']:
        raise ValueError('best checkpoint SHA mismatch')
    agent = make_agent('Flow_Vanilla', cfg)
    metadata = agent.load(str(checkpoint))
    payload = torch.load(checkpoint, map_location='cpu', weights_only=False)
    state_equal = all(torch.equal(value.cpu(), payload['model'][key].cpu())
                      for key, value in agent.state_dict().items())
    ds = CanonicalFlowDataset(previous.MANIFEST, 'validation')
    observation = {'state': ds[0]['observations']['state'].unsqueeze(0)}
    generator = torch.Generator(device='cpu')
    generator.manual_seed(2026)
    noise = torch.randn((1, 16, 8), generator=generator)
    started = time.monotonic()
    output = agent.sample_action(observation, initial_noise=noise)
    elapsed = time.monotonic() - started
    prepared = agent._prepare_flow_observation(observation)
    normalized = agent.actor.sample_action(prepared, initial_noise=noise)
    denormalized = torch.equal(output, agent.denormalize_action(normalized))
    result = {'pass': bool(output.shape == (1, 16, 8) and torch.isfinite(output).all()
                           and state_equal and denormalized and agent.step == record['optimizer_step']
                           and not torch.cuda.is_initialized()),
              'checkpoint_sha256': sha(checkpoint), 'checkpoint_metadata': metadata,
              'optimizer_step': agent.step, 'model_and_normalizer_state_parity': state_equal,
              'resolved_config_sha256': spec['resolved_config_sha256'],
              'dataset_manifest_sha256': spec['dataset']['manifest_sha256'],
              'normalizer_identity': record['normalizer_identity'],
              'input_shape': [1, 2, 33], 'output_shape': list(output.shape),
              'finite': bool(torch.isfinite(output).all()), 'denormalized': denormalized,
              'observation_normalizer_applied': agent.obs_normalizer is not None,
              'wall_time_seconds': elapsed,
              'cuda_initialized_during_cpu_inference': torch.cuda.is_initialized()}
    if not result['pass']:
        raise ValueError('checkpoint_cpu_compatibility failure')
    write_new(root / 'cpu_inference_check.json', result)
    return result


def cpu_check_final():
    root = ROOT
    spec = yaml.safe_load((root / 'training_spec.yaml').read_text())
    cfg = load_variant_config(root / 'resolved_flow_config.yaml')
    cfg.device = 'cpu'
    cfg.train.device = 'cpu'
    cfg.agent_sp.artifact_identity = spec['artifact_identity']
    checkpoint = root / 'checkpoints' / 'flow_final_step6480.pth'
    manifest = json.loads((root / 'checkpoints' / 'checkpoint_manifest.json').read_text())
    record = next(row for row in manifest['checkpoints'] if row['name'] == checkpoint.name)
    if sha(checkpoint) != record['sha256']:
        raise ValueError('final checkpoint SHA mismatch')
    agent = make_agent('Flow_Vanilla', cfg)
    metadata = agent.load(str(checkpoint))
    ds = CanonicalFlowDataset(previous.MANIFEST, 'validation')
    observation = {'state': ds[0]['observations']['state'].unsqueeze(0)}
    generator = torch.Generator(device='cpu')
    generator.manual_seed(2026)
    noise = torch.randn((1, 16, 8), generator=generator)
    started = time.monotonic()
    output = agent.sample_action(observation, initial_noise=noise)
    elapsed = time.monotonic() - started
    result = {'pass': bool(output.shape == (1, 16, 8) and torch.isfinite(output).all()
                           and agent.step == 6480),
              'checkpoint_sha256': sha(checkpoint), 'checkpoint_metadata': metadata,
              'optimizer_step': agent.step, 'normalizer_identity': record['normalizer_identity'],
              'input_shape': [1, 2, 33], 'output_shape': list(output.shape),
              'finite': bool(torch.isfinite(output).all()), 'denormalized': True,
              'observation_normalizer_applied': agent.obs_normalizer is not None,
              'wall_time_seconds': elapsed}
    if not result['pass']:
        raise ValueError('final checkpoint CPU inference failed')
    write_new(root / 'cpu_final_checkpoint_check.json', result)
    return result


def rollout_spec(checkpoint='checkpoints/flow_best_validation.pth'):
    return {'schema': 'p1_6-flow-zscore-q01-q99-pilot-rollout-v1', 'provider': 'geophys',
            'execution_device': 'cpu', 'dataset_manifest_sha256': previous.EXPECTED_DATASET,
            'checkpoint': checkpoint,
            'checkpoint_selection': 'minimum validation loss; earlier step wins exact ties',
            'task_success': 'cube_lift >= 0.10 m', 'max_control_steps_per_episode': 2500,
            'obs_horizon': 2, 'pred_horizon': 16, 'act_horizon': 8,
            'replan': 'observe latest two canonical state features, predict 16, execute first 8, replan',
            'policy_rng_rule': '100000 + task_seed',
            'pilot_seeds': PILOT_SEEDS, 'pilot_min_successes': 5,
            'same_task_artifact_reset_sample_controller': True,
            'expert_fallback': False,
            'normalization': 'checkpointed train-only 33D mean/std z-score and per-dimension q01-q99 action map'}


def lock_rollout():
    path = ROOT / 'rollout_spec.yaml'
    if path.exists() or (ROOT / 'rollout_spec_lock.json').exists():
        raise FileExistsError('rollout spec already exists; preserving it')
    value = rollout_spec()
    path.write_text(yaml.safe_dump(value, sort_keys=False))
    write_new(ROOT / 'rollout_spec_lock.json', {'sha256': sha(path),
                                                  'locked_at': datetime.now(timezone.utc).isoformat(),
                                                  'first_rollout': 'not yet executed'})


def lock_final_rollout():
    path = ROOT / 'rollout_spec_final.yaml'
    if path.exists() or (ROOT / 'rollout_spec_final_lock.json').exists():
        raise FileExistsError('final checkpoint rollout spec already exists; preserving it')
    path.write_text(yaml.safe_dump(
        rollout_spec('checkpoints/flow_final_step6480.pth'), sort_keys=False))
    write_new(ROOT / 'rollout_spec_final_lock.json', {
        'sha256': sha(path), 'locked_at': datetime.now(timezone.utc).isoformat(),
        'first_rollout': 'not yet executed'})


def run_pilot(checkpoint_kind='best'):
    root = ROOT
    summary = json.loads((root / 'training_summary.json').read_text())
    if summary.get('total_optimizer_steps') != 6480 or not math.isfinite(summary['final_validation_loss']):
        raise ValueError('pilot requires completed finite 80-epoch training')
    cpu_filename = 'cpu_inference_check.json' if checkpoint_kind == 'best' else 'cpu_final_checkpoint_check.json'
    cpu_result = json.loads((root / cpu_filename).read_text())
    if not cpu_result.get('pass'):
        raise ValueError('pilot requires CPU checkpoint/inference pass')
    suffix = '' if checkpoint_kind == 'best' else '_final'
    spec_path = root / f'rollout_spec{suffix}.yaml'
    lock_path = root / f'rollout_spec{suffix}_lock.json'
    if not spec_path.exists():
        if checkpoint_kind == 'best':
            lock_rollout()
        else:
            lock_final_rollout()
    lock = json.loads(lock_path.read_text())
    if sha(spec_path) != lock['sha256']:
        raise ValueError('rollout spec lock mismatch')
    output_root = root / ('pilot_train_support' if checkpoint_kind == 'best' else 'pilot_train_support_final')
    output_root.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'PYTHONPATH': 'GeoPhys/src:.', 'PYTHONDONTWRITEBYTECODE': '1'}
    results = []
    for seed in PILOT_SEEDS:
        directory = output_root / f'seed{seed:04d}'
        directory.mkdir()
        command = [sys.executable, '-m', 'task_env.diagnostics.phase1.flow_training_normalized',
                   '--stage', 'episode', '--seed', str(seed), '--checkpoint-kind', checkpoint_kind,
                   '--episode-output', str(directory)]
        (directory / 'command.txt').write_text(' '.join(command) + '\n')
        with (directory / 'stdout.log').open('w') as stdout, (directory / 'stderr.log').open('w') as stderr:
            proc = subprocess.run(command, env=env, stdout=stdout, stderr=stderr)
        report_path = directory / 'report.json'
        if proc.returncode or not report_path.exists():
            row = {'seed': seed, 'success': False, 'failure_reason': 'episode_worker_failed',
                   'process_return_code': proc.returncode}
        else:
            row = json.loads(report_path.read_text())
        results.append(row)
        (output_root / 'summary_progress.json').write_text(json.dumps(
            {'completed': len(results), 'target': len(PILOT_SEEDS), 'results': results},
            indent=2, sort_keys=True) + '\n')
        print(f"pilot {seed}: success={row.get('success')} steps={row.get('steps')} "
              f"lift={row.get('max_cube_lift')} reason={row.get('failure_reason')}", flush=True)
    successes = sum(bool(row.get('success')) for row in results)
    result = {'status': 'pilot_pass' if successes >= 5 else 'partial_with_localized_failure',
              'first_boundary': None if successes >= 5 else 'dataset_support_policy_behavior',
              'successes': successes, 'attempted': len(PILOT_SEEDS),
              'gate': successes >= 5, 'seeds': PILOT_SEEDS, 'results': results,
              'interpretation': 'fixed six-seed comparison only; no full support qualification'}
    write_new(output_root / 'pilot_summary.json', result)
    return result


def episode(seed, output, checkpoint_kind='best'):
    from task_env.diagnostics.phase1.flow_training import _episode_worker
    spec_path = ROOT / ('rollout_spec.yaml' if checkpoint_kind == 'best' else 'rollout_spec_final.yaml')
    return _episode_worker(seed, 'pilot_train_support', ROOT, output, spec_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['prepare', 'train', 'cpu-check', 'cpu-check-final', 'pilot', 'final-pilot', 'episode'])
    parser.add_argument('--seed', type=int)
    parser.add_argument('--checkpoint-kind', choices=['best', 'final'], default='best')
    parser.add_argument('--episode-output', type=Path)
    args = parser.parse_args()
    if args.stage == 'prepare':
        result = prepare()
    elif args.stage == 'train':
        result = train()
    elif args.stage == 'cpu-check':
        result = cpu_check()
    elif args.stage == 'cpu-check-final':
        result = cpu_check_final()
    elif args.stage == 'pilot':
        result = run_pilot('best')
    elif args.stage == 'final-pilot':
        result = run_pilot('final')
    else:
        if args.seed not in PILOT_SEEDS or args.episode_output is None:
            raise ValueError('episode worker needs one fixed pilot seed and output directory')
        result = episode(args.seed, args.episode_output, args.checkpoint_kind)
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == '__main__':
    main()
