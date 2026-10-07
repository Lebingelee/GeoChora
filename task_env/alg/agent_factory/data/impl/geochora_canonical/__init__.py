"""Strict canonical trajectory windows for state-only absolute-joint Flow BC."""
from bisect import bisect_right
from collections import Counter
from pathlib import Path
import hashlib
import json

import numpy as np
import torch
from torch.utils.data import Dataset
from task_env.trajectory.canonical import load
from task_env.alg.state_bc.features import examples, FEATURE_CONTRACT, ACTION_CONTRACT
from agent_factory.data.registry import register_dataset_type


def logical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def window(states, actions, index, pred_horizon=16):
    """History ends at boundary i; targets begin at transition i; edge repetition."""
    if not 0 <= index < len(actions) or len(states) != len(actions) or pred_horizon < 1:
        raise ValueError('invalid window index/alignment')
    history = states[[max(0, index-1), index]]
    future = actions[np.minimum(np.arange(index, index+pred_horizon), len(actions)-1)]
    return {'observations': {'state': torch.from_numpy(history.copy())},
            'action': torch.from_numpy(future.copy())}


class CanonicalFlowDataset(Dataset):
    def __init__(self, manifest_path, role='train', *, allow_failed_for_smoke=False, pred_horizon=16):
        self.manifest_path = str(manifest_path)
        manifest = json.loads(Path(manifest_path).read_text())
        if manifest['schema'] not in ('geochora-canonical-flow-dataset-v0', 'geochora-canonical-flow-dataset-v1') or role not in ('train', 'validation'):
            raise ValueError('unsupported canonical Flow dataset manifest')
        if manifest['feature_contract'] != FEATURE_CONTRACT or manifest['action_contract'] != ACTION_CONTRACT:
            raise ValueError('feature/action contract mismatch')
        if manifest['schema'] == 'geochora-canonical-flow-dataset-v1':
            from .selection import validate_manifest
            selected = validate_manifest(manifest)
            expected = [r['seed'] for r in selected[role]]
        else:
            expected = list(range(1000, 1080)) if role == 'train' else list(range(1080, 1100))
        rows = [row for row in manifest['trajectories'] if row['role'] == role]
        if [row['seed'] for row in rows] != expected:
            raise ValueError('frozen trajectory split mismatch')
        self.allow_failed_for_smoke = allow_failed_for_smoke
        self.pred_horizon = int(pred_horizon)
        if self.pred_horizon < 1:
            raise ValueError('pred_horizon must be positive')
        self.training_eligible = True
        self.failed_seeds = []
        self.role = role
        self.manifest_identity = logical_hash(manifest)
        self.records = []
        self.ends = []
        total = holds = 0
        stages = Counter()
        for row in rows:
            path = Path(row['file'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['file_sha256']:
                raise ValueError('trajectory file hash mismatch')
            trajectory = load(path)
            m = trajectory.metadata
            if (trajectory.identity_hash != row['logical_hash'] or m.task_seed != row['seed']
                    or m.sample_role != role or m.execution.physics_provider != 'geophys'
                    or m.reset_sample.identity_hash != row['reset_sample_hash']
                    or any(getattr(m, name + '_identity') != manifest['identities'][name]
                           for name in ('controller', 'expert', 'readiness'))
                    or m.task_artifact_hash != manifest['identities']['task_artifact']):
                raise ValueError('trajectory provenance mismatch')
            eligible = (trajectory.stop_reason == 'expert_endpoint' and trajectory.boundaries[-1].is_success
                        and not trajectory.boundaries[-1].task_failure
                        and trajectory.boundaries[-1].task_metrics['cube_lift'] >= .105)
            if not eligible:
                self.training_eligible = False
                self.failed_seeds.append(m.task_seed)
                if not allow_failed_for_smoke or manifest['schema'] == 'geochora-canonical-flow-dataset-v1':
                    raise ValueError('required successful expert trajectory missing')
            x, y = examples(trajectory)  # frozen owner of feature/action ordering
            if len(y) != row['T'] or trajectory.hold_count != row['holds']:
                raise ValueError('trajectory count/hold mismatch')
            self.records.append((x, y))
            total += len(y)
            self.ends.append(total)
            holds += trajectory.hold_count
            stages.update(t.expert_stage for t in trajectory.transitions)
        self.statistics = {'trajectory_count': len(rows), 'sample_count': total,
                           'planned_transition_count': total-holds, 'readiness_hold_count': holds,
                           'hold_fraction': holds/total, 'per_stage_counts': dict(stages)}

    def __len__(self):
        return self.ends[-1]

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        record = bisect_right(self.ends, index)
        start = self.ends[record-1] if record else 0
        return window(*self.records[record], index-start, pred_horizon=self.pred_horizon)

    def get_all_actions(self):
        return torch.from_numpy(np.concatenate([y for x, y in self.records]))

    def get_all_states(self):
        return torch.from_numpy(np.concatenate([x for x, y in self.records]))

    def validation_dataset(self):
        return type(self)(self.manifest_path, 'validation', allow_failed_for_smoke=self.allow_failed_for_smoke,
                          pred_horizon=self.pred_horizon)


def _validate_flow_window_config(cfg):
    """Validate the shared state/action contract and learner-selected windows.

    Prediction and execution horizons belong to the learner profile.  Keep the
    historical 2/16/8 profile as the defaults, while allowing explicit longer
    action chunks without changing CanonicalTrajectory v0.
    """
    if (int(cfg.env.proprio_dim), int(cfg.env.action_dim)) != (33, 8):
        raise ValueError('canonical Flow requires the frozen 33D state / 8D action contract')
    obs_horizon = int(cfg.env.obs_horizon)
    pred_horizon = int(cfg.env.pred_horizon)
    act_horizon = int(cfg.env.act_horizon)
    if obs_horizon != 2 or pred_horizon < 1 or not 1 <= act_horizon <= pred_horizon:
        raise ValueError('canonical Flow requires obs_horizon=2 and 1 <= act_horizon <= pred_horizon')
    if (int(cfg.actor.obs_horizon), int(cfg.actor.pred_horizon)) != (obs_horizon, pred_horizon):
        raise ValueError('canonical Flow actor and environment horizons must match')


def _build(cfg, required_keys=None, expert_path=None):
    _validate_flow_window_config(cfg)
    if (cfg.dataset.include_rgb or cfg.dataset.include_depth
            or cfg.agent_control_mode != 'absolute_joint'
            or cfg.env.env_control_mode != 'absolute_joint'):
        raise ValueError('canonical Flow requires state-only absolute_joint')
    return CanonicalFlowDataset(expert_path, allow_failed_for_smoke=bool(cfg.dataset.config.get('allow_failed_for_smoke', False)),
                                pred_horizon=int(cfg.env.pred_horizon))


register_dataset_type('geochora_canonical_flow', _build)
