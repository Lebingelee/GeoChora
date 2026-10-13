"""Provider-free checks for configurable Flow prediction/execution chunks."""
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.alg.agent_factory.data.impl.geochora_canonical import window
from task_env.diagnostics.phase1.flow_training import flow_rollout_horizons


def test_window_supports_pred_horizon_32_with_absolute_action_edge_repeat():
    states = np.arange(6 * 33, dtype=np.float32).reshape(6, 33)
    actions = np.arange(6 * 8, dtype=np.float32).reshape(6, 8)
    sample = window(states, actions, 4, pred_horizon=32)
    chunk = sample['action'].numpy()
    assert chunk.shape == (32, 8)
    assert np.array_equal(chunk[:2], actions[4:6])
    assert np.array_equal(chunk[2:], np.repeat(actions[-1:], 30, axis=0))


def test_execution_horizon_can_use_full_existing_prediction_chunk():
    cfg = SimpleNamespace(env=SimpleNamespace(obs_horizon=2, pred_horizon=16, act_horizon=8))
    assert flow_rollout_horizons({'obs_horizon': 2, 'pred_horizon': 16, 'act_horizon': 16}, cfg) == (2, 16, 16)


def test_execution_horizon_cannot_exceed_checkpoint_prediction_horizon():
    cfg = SimpleNamespace(env=SimpleNamespace(obs_horizon=2, pred_horizon=16, act_horizon=8))
    with pytest.raises(ValueError, match='act_horizon'):
        flow_rollout_horizons({'obs_horizon': 2, 'pred_horizon': 16, 'act_horizon': 17}, cfg)


def test_prediction_horizon_must_match_checkpoint_shape():
    cfg = SimpleNamespace(env=SimpleNamespace(obs_horizon=2, pred_horizon=16, act_horizon=8))
    with pytest.raises(ValueError, match='mismatches checkpoint'):
        flow_rollout_horizons({'obs_horizon': 2, 'pred_horizon': 32, 'act_horizon': 24}, cfg)
