"""Locked 80-epoch Flow retraining for an alternate state/action chunk horizon."""
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
from agent_factory.training.identity import config_identity, digest
from task_env.alg.agent_factory.data.impl.geochora_canonical import CanonicalFlowDataset
from task_env.alg.state_bc.features import FEATURE_CONTRACT, ACTION_CONTRACT
from task_env.diagnostics.phase1 import flow_training as previous
from task_env.diagnostics.phase1 import flow_training_normalized as normalized

ROOT = Path('workspace/qualification/phase1/p1_6_flow_training_q99_zscore_80ep_h32_a24')
PRED_HORIZON = 32
ACT_HORIZON = 24
OBS_HORIZON = 2
EPOCHS = 80
BATCH_SIZE = 512
TRAINING_SEED = 2026
TRAIN_SAMPLES = 41658
VALIDATION_SAMPLES = 10252


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
        raise FileExistsError(f'refusing to overwrite locked Flow horizon evidence: {path}')
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def lock_yaml(path, value, schema):
    path = Path(path)
    if path.exists() or path.with_name(path.stem + '_lock.json').exists():
        raise FileExistsError(f'locked spec already exists: {path}')
    path.write_text(yaml.safe_dump(value, sort_keys=False))
    write_new(path.with_name(path.stem + '_lock.json'), {
        'schema': schema, 'sha256': sha(path), 'locked_at': datetime.now(timezone.utc).isoformat()})


def source_hashes():
    return previous.frozen_source_hashes()


def datasets():
    manifest, old_cfg, train, validation = previous.verify_corpus()
    if not train.training_eligible or not validation.training_eligible:
        raise ValueError('training_provenance_mismatch: finalized successful corpus is ineligible')
    # Reuse the strict, already-validated trajectory records and change only the
    # requested target-window length for this alternate Flow checkpoint.
    train.pred_horizon = PRED_HORIZON
    validation.pred_horizon = PRED_HORIZON
    if (train.statistics['trajectory_count'], validation.statistics['trajectory_count'],
            len(train), len(validation)) != (80, 20, TRAIN_SAMPLES, VALIDATION_SAMPLES):
        raise ValueError('training_provenance_mismatch: frozen corpus counts changed')
    if train[0]['action'].shape != (PRED_HORIZON, 8) or validation[len(validation) - 1]['action'].shape != (PRED_HORIZON, 8):
        raise ValueError('dataset_alignment: alternate prediction horizon was not applied')
    return manifest, train, validation


def selected_config():
    cfg = normalized.selected_config()
    cfg.env.obs_horizon = OBS_HORIZON
    cfg.actor.obs_horizon = OBS_HORIZON
    cfg.env.pred_horizon = PRED_HORIZON
    cfg.actor.pred_horizon = PRED_HORIZON
    cfg.env.act_horizon = ACT_HORIZON
    cfg.train.save_root = str(ROOT / 'agent_run')
    cfg.train.exp_name = f'flow_vanilla_zscore_q01_q99_80ep_h{PRED_HORIZON}_a{ACT_HORIZON}'
    return cfg


def _state_normalization(train):
    state = train.get_all_states().float()
    action = train.get_all_actions().float()
    state_mean = state.mean(0)
    state_std = state.std(0)
    low = torch.quantile(action, 0.01, dim=0)
    high = torch.quantile(action, 0.99, dim=0)
    if not torch.isfinite(state_mean).all() or not torch.isfinite(state_std).all() or (state_std <= 0).any():
        raise ValueError('training observations invalid for z-score')
    if not torch.isfinite(low).all() or not torch.isfinite(high).all() or not (high > low).all():
        raise ValueError('training actions invalid for q01-q99 normalization')
    return state, action, {'observation_mean': state_mean.tolist(), 'observation_std': state_std.tolist(),
                           'action_q01': low.tolist(), 'action_q99': high.tolist(),
                           'fit_trajectory_count': 80, 'fit_transition_count': len(train)}


def prepare():
    if ROOT.exists() and any(ROOT.iterdir()):
        raise FileExistsError(f'variant evidence root is nonempty: {ROOT}')
    provenance = normalized.check_provenance()
    manifest, train, validation = datasets()
    cfg = selected_config()
    if (cfg.agent_type != 'Flow_Vanilla' or cfg.train.batch_size != BATCH_SIZE
            or (cfg.env.obs_horizon, cfg.env.pred_horizon, cfg.env.act_horizon) != (OBS_HORIZON, PRED_HORIZON, ACT_HORIZON)
            or (cfg.actor.obs_horizon, cfg.actor.pred_horizon, cfg.env.action_dim, cfg.env.proprio_dim) != (OBS_HORIZON, PRED_HORIZON, 8, 33)):
        raise ValueError('variant configuration does not match frozen horizon contract')
    if cfg.actor.lr != 1e-4 or cfg.actor.weight_decay != 1e-6 or cfg.actor.num_inference_steps != 10:
        raise ValueError('learner configuration changed outside the horizon variables')
    identity = normalized.artifact_identity(cfg)
    cfg.agent_sp.artifact_identity = identity
    if config_identity(cfg) != identity['resolved_config_sha256']:
        raise ValueError('resolved config identity is unstable')

    generator = torch.Generator(device='cpu').manual_seed(TRAINING_SEED)
    train_loader = DataLoader(train, batch_size=BATCH_SIZE, shuffle=True, drop_last=True,
                              num_workers=0, generator=generator)
    validation_loader = DataLoader(validation, batch_size=BATCH_SIZE, shuffle=False,
                                   drop_last=False, num_workers=0)
    if len(train_loader) != 81 or len(train_loader) * EPOCHS != 6480:
        raise ValueError('actual DataLoader does not provide 80 x 81 optimizer steps')
    _, _, norm_stats = _state_normalization(train)
    root_hashes = source_hashes()
    summary = json.loads((normalized.ROOT / 'training_summary.json').read_text())
    h16_report = json.loads((normalized.ROOT / 'chunk16_act16_seed1000/episode/report.json').read_text())
    if h16_report['success'] or h16_report['max_cube_lift'] >= 0.10:
        raise ValueError('conditional retraining requires the locked 16/16 seed-1000 failure')

    ROOT.mkdir(parents=True, exist_ok=True)
    resolved_path = ROOT / 'resolved_flow_config.yaml'
    resolved_path.write_text(OmegaConf.to_yaml(cfg, resolve=True))
    spec = {
        'schema': 'p1_6-flow-zscore-q01-q99-h32-a24-80epoch-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'trigger': {'prior_test': 'final checkpoint, seed 1000, pred=16 act=16',
                    'success': False, 'max_cube_lift_m': h16_report['max_cube_lift'],
                    'task_success_threshold_m': 0.10,
                    'prior_checkpoint_sha256': h16_report['checkpoint_sha256']},
        'provenance': {**provenance, 'approved_corpus_identity': train.manifest_identity,
                       'source_training_config_sha256': summary['resolved_config_sha256']},
        'dataset': {'manifest': str(previous.MANIFEST),
                    'manifest_file_sha256': sha(previous.MANIFEST),
                    'logical_identity': train.manifest_identity,
                    'train_trajectory_count': 80, 'validation_trajectory_count': 20,
                    'train_transition_count': len(train), 'validation_transition_count': len(validation),
                    'train_seeds': json.loads(previous.MANIFEST.read_text())['selected_train_seeds'],
                    'validation_seeds': json.loads(previous.MANIFEST.read_text())['selected_validation_seeds']},
        'policy_contract': {'agent_type': 'Flow_Vanilla', 'backbone': 'ConditionalUnet1D',
                            'state_dim': 33, 'action_dim': 8, 'action_mode': 'absolute_joint',
                            'obs_horizon': OBS_HORIZON, 'pred_horizon': PRED_HORIZON,
                            'act_horizon': ACT_HORIZON, 'inference_steps': 10,
                            'feature_contract_identity': digest(FEATURE_CONTRACT),
                            'action_contract_identity': digest(ACTION_CONTRACT)},
        'learner': {'seed': TRAINING_SEED, 'device': 'cuda', 'precision': 'float32',
                    'batch_size': BATCH_SIZE, 'epoch_budget': EPOCHS,
                    'steps_per_epoch': len(train_loader), 'actor_iters': EPOCHS * len(train_loader),
                    'optimizer': 'AdamW', 'lr': 1e-4, 'weight_decay': 1e-6,
                    'train_loss_interval': 100,
                    'validation_steps': [0, 1000, 2000, 3000, 4000, 5000, 6000, 6480],
                    'validation_rng_seed': TRAINING_SEED,
                    'checkpoint_selection': 'minimum full validation loss; earlier step wins exact ties'},
        'normalization': {'observation': 'train-only per-feature mean/std, epsilon 1e-8',
                          'action': 'train-only per-dimension q01/q99 affine map to [-1,1], clipped',
                          'statistics': norm_stats, 'validation_in_fit': False},
        'resolved_config_sha256': identity['resolved_config_sha256'],
        'artifact_identity': identity,
        'resolved_config': OmegaConf.to_container(cfg, resolve=True),
        'frozen_lower_layer_source_hashes': root_hashes,
        'dataset_window': {'history_ends_at_boundary_i': True,
                           'actions_begin_at_transition_i': True,
                           'absolute_action_end_padding': 'repeat final valid action',
                           'readiness_holds_preserved': True},
    }
    spec_path = ROOT / 'training_spec.yaml'
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False))
    write_new(ROOT / 'training_spec_lock.json', {'schema': 'p1_6-training-spec-lock-v1',
        'sha256': sha(spec_path), 'locked_at': datetime.now(timezone.utc).isoformat(),
        'first_optimizer_update': 'not yet started'})
    rollout = {'schema': 'p1_6-flow-final-checkpoint-h32-a24-seed1000-v1',
        'provider': 'geophys', 'execution_device': 'cpu', 'checkpoint': 'checkpoints/flow_final_step6480.pth',
        'checkpoint_selection': 'final step 6480, no rollout selection',
        'dataset_manifest_sha256': train.manifest_identity,
        'task_seed': 1000,
        'reset_sample_hash': json.loads((normalized.ROOT / 'chunk16_act16_seed1000/episode/report.json').read_text())['sample_hash'],
        'policy_rng_rule': '100000 + task_seed', 'policy_rng_seed': 101000,
        'obs_horizon': OBS_HORIZON, 'pred_horizon': PRED_HORIZON, 'act_horizon': ACT_HORIZON,
        'max_control_steps_per_episode': 2500, 'task_success': 'cube_lift >= 0.10 m',
        'expert_fallback': False,
        'replan': 'sample 32 absolute_joint actions and execute first 24 before replanning',
        'one_governed_rollout_only': True}
    lock_yaml(ROOT / 'rollout_spec.yaml', rollout, 'p1_6-rollout-spec-lock-v1')
    write_new(ROOT / 'prepare_report.json', {'status': 'prepared_and_locked', 'training_spec_sha256': sha(spec_path),
        'rollout_spec_sha256': sha(ROOT / 'rollout_spec.yaml'), 'resolved_config_sha256': identity['resolved_config_sha256'],
        'steps_per_epoch': len(train_loader), 'actor_iters': EPOCHS * len(train_loader),
        'train_sample_count': len(train), 'validation_sample_count': len(validation),
        'train_action_shape': list(train[0]['action'].shape),
        'validation_action_shape': list(validation[len(validation) - 1]['action'].shape)})
    return {'status': 'prepared_and_locked', 'training_spec_sha256': sha(spec_path),
            'rollout_spec_sha256': sha(ROOT / 'rollout_spec.yaml'),
            'resolved_config_sha256': identity['resolved_config_sha256']}


def load_locked_spec():
    path = ROOT / 'training_spec.yaml'
    spec = yaml.safe_load(path.read_text())
    lock = json.loads((ROOT / 'training_spec_lock.json').read_text())
    if sha(path) != lock['sha256']:
        raise ValueError('training spec lock mismatch')
    roll_path = ROOT / 'rollout_spec.yaml'
    roll_lock = json.loads((ROOT / 'rollout_spec_lock.json').read_text())
    if sha(roll_path) != roll_lock['sha256']:
        raise ValueError('rollout spec lock mismatch')
    return spec, lock


def train():
    spec, lock = load_locked_spec()
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable for locked Flow horizon training')
    metrics_dir = ROOT / 'metrics_run'
    if (ROOT / 'training_summary.json').exists() or metrics_dir.exists():
        raise FileExistsError('training evidence exists; refusing to restart or overwrite')
    manifest, train, validation = datasets()
    if train.manifest_identity != spec['dataset']['logical_identity']:
        raise ValueError('training_provenance_mismatch: dataset logical identity changed')
    cfg = normalized.load_variant_config(ROOT / 'resolved_flow_config.yaml')
    if config_identity(cfg) != spec['resolved_config_sha256']:
        raise ValueError('resolved config changed after training lock')
    cfg.agent_sp.artifact_identity = spec['artifact_identity']
    normalized.seed_all(TRAINING_SEED)
    generator = torch.Generator(device='cpu').manual_seed(TRAINING_SEED)
    train_loader = DataLoader(train, batch_size=BATCH_SIZE, shuffle=True, drop_last=True,
                              num_workers=0, generator=generator)
    validation_loader = DataLoader(validation, batch_size=BATCH_SIZE, shuffle=False,
                                   drop_last=False, num_workers=0)
    if len(train_loader) != spec['learner']['steps_per_epoch']:
        raise ValueError('DataLoader length changed after specification lock')
    agent = make_agent('Flow_Vanilla', cfg)
    if sum(p.numel() for p in agent.actor.parameters()) != 19512264:
        raise ValueError('Flow actor architecture/parameter count changed')
    if not isinstance(agent.actor_optimizer, torch.optim.AdamW):
        raise ValueError('optimizer changed from AdamW')
    group = agent.actor_optimizer.param_groups[0]
    if group['lr'] != 1e-4 or group['weight_decay'] != 1e-6:
        raise ValueError('optimizer hyperparameters changed')
    actions = train.get_all_actions().to(agent.device).float()
    states = train.get_all_states().to(agent.device).float()
    agent.fit_action_normalizer(actions)
    agent.fit_obs_normalizer(states)
    action_stats = {k: v.detach().cpu().clone() for k, v in agent.action_normalizer.state_dict().items()}
    obs_stats = {k: v.detach().cpu().clone() for k, v in agent.obs_normalizer.state_dict().items()}
    norm_id = digest({'action': {k: v.tolist() for k, v in action_stats.items()},
                      'observation': {k: v.tolist() for k, v in obs_stats.items()}})
    if not torch.allclose(action_stats['low_val'], torch.quantile(actions.cpu(), .01, dim=0)):
        raise ValueError('action normalizer did not use selected train q01 values')
    if not torch.allclose(action_stats['high_val'], torch.quantile(actions.cpu(), .99, dim=0)):
        raise ValueError('action normalizer did not use selected train q99 values')
    if not torch.allclose(obs_stats['mean'], states.mean(0).cpu()) or not torch.allclose(obs_stats['std'], states.std(0).cpu()):
        raise ValueError('observation normalizer did not use selected train z-score values')

    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    checkpoint_dir = ROOT / 'checkpoints'; checkpoint_dir.mkdir(exist_ok=False)
    candidates = []
    def save_candidate(current, row):
        step = int(row['step'])
        path = checkpoint_dir / f'validation_step_{step:04d}.pth'
        current.save(str(path), meta={'purpose': 'fixed_validation_candidate', 'validation_step': step,
            'validation_loss': float(row['loss']), 'validation_samples': row['samples'],
            'validation_batches': row['batches'], 'normalizer_identity': norm_id,
            'training_spec_sha256': lock['sha256']})
        candidates.append({'step': step, 'loss': float(row['loss']), 'samples': row['samples'],
                           'batches': row['batches'], 'file': str(path)})
    started = time.monotonic(); timestamp = datetime.now(timezone.utc).isoformat()
    try:
        result = agent.train_loop(train_loader, EPOCHS * len(train_loader),
            save_dir=str(metrics_dir), validation_loader=validation_loader,
            validation_callback=save_candidate)
        torch.cuda.synchronize(); wall = time.monotonic() - started
        expected_val = [0, 1000, 2000, 3000, 4000, 5000, 6000, 6480]
        if agent.step != 6480 or [x['step'] for x in candidates] != expected_val:
            raise ValueError('optimizer update count or validation schedule mismatch')
        metrics_path = metrics_dir / 'training_metrics.jsonl'
        rows = [json.loads(line) for line in metrics_path.read_text().splitlines()]
        train_rows = [r for r in rows if r['kind'] == 'train']
        val_rows = [r for r in rows if r['kind'] == 'validation']
        if [r['step'] for r in train_rows] != [*range(100, 6401, 100), 6480]:
            raise ValueError('train logging schedule mismatch')
        if [r['step'] for r in val_rows] != expected_val:
            raise ValueError('validation logging schedule mismatch')
        if any(not math.isfinite(r['loss']) for r in rows) or not all(torch.isfinite(p).all() for p in agent.parameters()):
            raise ValueError('flow_training_numerics: non-finite loss or model parameter')
        val_at = {r['step']: r['loss'] for r in val_rows}
        best = min(val_rows, key=lambda r: (r['loss'], r['step']))
        train_final = train_rows[-1]['loss']
        final_path = checkpoint_dir / 'flow_final_step6480.pth'
        agent.save(str(final_path), meta={'purpose': 'flow_final_step6480', 'train_window_loss': train_final,
            'validation_loss': val_at[6480], 'training_spec_sha256': lock['sha256']})
        best_path = checkpoint_dir / 'flow_best_validation.pth'
        best_path.write_bytes((checkpoint_dir / f"validation_step_{best['step']:04d}.pth").read_bytes())
        (ROOT / 'training_metrics.jsonl').write_bytes(metrics_path.read_bytes())
        allocated = int(torch.cuda.max_memory_allocated()); reserved = int(torch.cuda.max_memory_reserved())
        summary = {'schema': 'p1_6-flow-h32-a24-80epoch-summary-v1', **result,
            'training_spec_sha256': lock['sha256'], 'resolved_config_sha256': spec['resolved_config_sha256'],
            'dataset_manifest_sha256': spec['dataset']['logical_identity'],
            'total_optimizer_steps': int(agent.step), 'epoch_budget': EPOCHS,
            'steps_per_epoch': len(train_loader), 'effective_epochs': agent.step / len(train_loader),
            'pred_horizon': PRED_HORIZON, 'act_horizon': ACT_HORIZON,
            'training_started_at': timestamp, 'training_finished_at': datetime.now(timezone.utc).isoformat(),
            'training_wall_time_seconds': wall, 'gpu': torch.cuda.get_device_name(),
            'torch_version': torch.__version__, 'cuda_version': torch.version.cuda,
            'peak_cuda_memory_allocated_bytes': allocated, 'peak_cuda_memory_reserved_bytes': reserved,
            'initial_validation_loss': val_at[0], 'step_1000_validation_loss': val_at[1000],
            'final_validation_loss': val_at[6480], 'minimum_validation_loss': best['loss'],
            'best_validation_step': best['step'], 'first_train_window_loss': train_rows[0]['loss'],
            'final_train_window_loss': train_final, 'minimum_train_window_loss': min(r['loss'] for r in train_rows),
            'normalizer_identity': norm_id,
            'normalizer_statistics': {'action_low_q01': action_stats['low_val'].tolist(),
                'action_high_q99': action_stats['high_val'].tolist(),
                'observation_mean': obs_stats['mean'].tolist(), 'observation_std': obs_stats['std'].tolist()},
            'validation_candidates': candidates}
        write_new(ROOT / 'training_summary.json', summary)
        after = source_hashes()
        unchanged = after == spec['frozen_lower_layer_source_hashes']
        write_new(ROOT / 'lower_layer_freeze_post.json', {'unchanged': unchanged, 'after': after})
        if not unchanged:
            raise ValueError('lower_phase_recovery_required: frozen sources changed')
        records = []
        for filename, step in (('flow_final_step6480.pth', 6480), ('flow_best_validation.pth', int(best['step']))):
            path = checkpoint_dir / filename
            records.append({'name': filename, 'sha256': sha(path), 'optimizer_step': step,
                'epoch_equivalent': step / len(train_loader), 'validation_loss': val_at[step] if step in val_at else best['loss'],
                'resolved_config_sha256': spec['resolved_config_sha256'],
                'dataset_manifest_sha256': spec['dataset']['logical_identity'],
                'feature_contract_identity': spec['artifact_identity']['feature_contract_identity'],
                'action_contract_identity': spec['artifact_identity']['action_contract_identity'],
                'normalizer_identity': norm_id, 'artifact_identity': spec['artifact_identity']})
        write_new(checkpoint_dir / 'checkpoint_manifest.json', {'schema': 'flow-checkpoint-manifest-v2',
            'selected_rule': spec['learner']['checkpoint_selection'], 'checkpoints': records,
            'validation_candidates': candidates})
        return {'status': 'training_complete', 'summary': summary, 'checkpoints': records}
    except Exception as exc:
        failure = {'status': 'partial_with_localized_failure', 'first_boundary': 'flow_training_numerics',
                   'error': str(exc), 'traceback': traceback.format_exc(), 'last_optimizer_step': int(agent.step)}
        write_new(ROOT / 'training_failure.json', failure)
        return failure


def cpu_check():
    spec, _ = load_locked_spec()
    if torch.cuda.is_initialized():
        raise ValueError('CPU check requires a fresh process before CUDA initialization')
    cfg = normalized.load_variant_config(ROOT / 'resolved_flow_config.yaml')
    cfg.device = 'cpu'; cfg.train.device = 'cpu'; cfg.agent_sp.artifact_identity = spec['artifact_identity']
    checkpoint = ROOT / 'checkpoints' / 'flow_final_step6480.pth'
    agent = make_agent('Flow_Vanilla', cfg); metadata = agent.load(str(checkpoint))
    val = CanonicalFlowDataset(previous.MANIFEST, 'validation', pred_horizon=PRED_HORIZON)
    observation = {'state': val[0]['observations']['state'].unsqueeze(0)}
    generator = torch.Generator(device='cpu').manual_seed(2026)
    noise = torch.randn((1, PRED_HORIZON, 8), generator=generator)
    started = time.monotonic(); output = agent.sample_action(observation, initial_noise=noise)
    result = {'pass': bool(agent.step == 6480 and output.shape == (1, PRED_HORIZON, 8)
        and torch.isfinite(output).all() and agent.obs_normalizer is not None),
        'checkpoint_sha256': sha(checkpoint), 'checkpoint_metadata': metadata, 'optimizer_step': agent.step,
        'input_shape': list(observation['state'].shape), 'output_shape': list(output.shape),
        'finite': bool(torch.isfinite(output).all()), 'denormalized': True,
        'observation_normalizer_applied': agent.obs_normalizer is not None,
        'wall_time_seconds': time.monotonic() - started, 'cuda_initialized': torch.cuda.is_initialized()}
    if not result['pass']:
        raise ValueError('checkpoint_cpu_compatibility failed for 32-step checkpoint')
    write_new(ROOT / 'cpu_inference_check.json', result)
    return result


def run_episode():
    spec, _ = load_locked_spec()
    rollout = ROOT / 'rollout_spec.yaml'
    lock = json.loads((ROOT / 'rollout_spec_lock.json').read_text())
    if sha(rollout) != lock['sha256']:
        raise ValueError('rollout spec lock mismatch')
    out = ROOT / 'episode_seed1000'
    command = [sys.executable, '-m',
        'task_env.diagnostics.phase1.flow_training', '--stage', 'episode', '--seed', '1000',
        '--cohort', 'pilot_train_support', '--root', str(ROOT), '--episode-output', str(out),
        '--rollout-spec', str(rollout)]
    if out.exists():
        raise FileExistsError('horizon-32 seed 1000 rollout already exists')
    out.mkdir(parents=True)
    (ROOT / 'rollout_command.txt').write_text('PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 ' + ' '.join(command) + '\n')
    env = {**os.environ, 'PYTHONPATH': 'GeoPhys/src:.', 'PYTHONDONTWRITEBYTECODE': '1'}
    with (ROOT / 'rollout_stdout.log').open('w') as stdout, (ROOT / 'rollout_stderr.log').open('w') as stderr:
        result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr)
    report_path = out / 'report.json'
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f'horizon-32 episode process failed ({result.returncode})')
    report = json.loads(report_path.read_text())
    write_new(ROOT / 'rollout_summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['prepare', 'train', 'cpu-check', 'episode'])
    args = parser.parse_args()
    if args.stage == 'prepare': result = prepare()
    elif args.stage == 'train': result = train()
    elif args.stage == 'cpu-check': result = cpu_check()
    else: result = run_episode()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == '__main__':
    main()
