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


def window(states, actions, index):
    """History ends at boundary i; targets begin at transition i; edge repetition."""
    if not 0 <= index < len(actions) or len(states) != len(actions):
        raise ValueError('invalid window index/alignment')
    history = states[[max(0, index-1), index]]
    future = actions[np.minimum(np.arange(index, index+16), len(actions)-1)]
    return {'observations': {'state': torch.from_numpy(history.copy())},
            'action': torch.from_numpy(future.copy())}


class CanonicalFlowDataset(Dataset):
    def __init__(self, manifest_path, role='train'):
        self.manifest_path = str(manifest_path)
        manifest = json.loads(Path(manifest_path).read_text())
        if manifest['schema'] != 'geochora-canonical-flow-dataset-v0' or role not in ('train', 'validation'):
            raise ValueError('unsupported canonical Flow dataset manifest')
        if manifest['feature_contract'] != FEATURE_CONTRACT or manifest['action_contract'] != ACTION_CONTRACT:
            raise ValueError('feature/action contract mismatch')
        expected = list(range(1000, 1080)) if role == 'train' else list(range(1080, 1100))
        rows = [row for row in manifest['trajectories'] if row['role'] == role]
        if [row['seed'] for row in rows] != expected:
            raise ValueError('frozen trajectory split mismatch')
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
            if (trajectory.stop_reason != 'expert_endpoint' or not trajectory.boundaries[-1].is_success
                    or trajectory.boundaries[-1].task_failure
                    or trajectory.boundaries[-1].task_metrics['cube_lift'] < .105):
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
        return window(*self.records[record], index-start)

    def get_all_actions(self):
        return torch.from_numpy(np.concatenate([y for x, y in self.records]))

    def get_all_states(self):
        return torch.from_numpy(np.concatenate([x for x, y in self.records]))

    def validation_dataset(self):
        return type(self)(self.manifest_path, 'validation')


def _build(cfg, required_keys=None, expert_path=None):
    if (cfg.env.proprio_dim, cfg.env.action_dim, cfg.env.obs_horizon,
            cfg.env.pred_horizon, cfg.env.act_horizon) != (33, 8, 2, 16, 8):
        raise ValueError('canonical Flow dimensions/horizons are frozen')
    if (cfg.dataset.include_rgb or cfg.dataset.include_depth
            or cfg.agent_control_mode != 'absolute_joint'
            or cfg.env.env_control_mode != 'absolute_joint'):
        raise ValueError('canonical Flow requires state-only absolute_joint')
    return CanonicalFlowDataset(expert_path)


register_dataset_type('geochora_canonical_flow', _build)
