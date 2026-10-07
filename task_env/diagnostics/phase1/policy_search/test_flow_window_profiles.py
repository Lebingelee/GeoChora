"""Backward-compatible learner windows for canonical PickCube trajectories."""
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.alg.agent_factory.data.impl.geochora_canonical import (
    _validate_flow_window_config,
    window,
)
from task_env.diagnostics.phase1.policy_search.flow100_data import (
    observation_contract,
    select_observation_features,
)


def _config(*, pred=16, act=8):
    return SimpleNamespace(
        env=SimpleNamespace(
            proprio_dim=33,
            action_dim=8,
            obs_horizon=2,
            pred_horizon=pred,
            act_horizon=act,
        ),
        actor=SimpleNamespace(obs_horizon=2, pred_horizon=pred),
    )


def test_historical_h2_p16_a8_window_is_bytewise_unchanged():
    states = np.arange(7 * 33, dtype=np.float32).reshape(7, 33)
    actions = np.arange(7 * 8, dtype=np.float32).reshape(7, 8)
    historical = window(states, actions, 4)
    explicit = window(states, actions, 4, pred_horizon=16)
    assert np.array_equal(historical["observations"]["state"].numpy(),
                          explicit["observations"]["state"].numpy())
    assert np.array_equal(historical["action"].numpy(), explicit["action"].numpy())
    _validate_flow_window_config(_config())


def test_h50_a36_repeats_final_absolute_action_at_trajectory_end():
    states = np.arange(7 * 33, dtype=np.float32).reshape(7, 33)
    actions = np.arange(7 * 8, dtype=np.float32).reshape(7, 8)
    historical = window(states, actions, 6)
    long_window = window(states, actions, 6, pred_horizon=50)
    assert long_window["action"].shape == (50, 8)
    assert np.array_equal(long_window["action"][0].numpy(), historical["action"][0].numpy())
    assert np.array_equal(long_window["action"].numpy(),
                          np.repeat(actions[-1:], 50, axis=0))
    _validate_flow_window_config(_config(pred=50, act=36))


@pytest.mark.parametrize("pred,act", [(0, 1), (16, 17), (50, 0)])
def test_invalid_execution_horizon_is_rejected(pred, act):
    with pytest.raises(ValueError, match="act_horizon"):
        _validate_flow_window_config(_config(pred=pred, act=act))


def test_actor_and_environment_prediction_horizons_must_match():
    cfg = _config(pred=50, act=36)
    cfg.actor.pred_horizon = 16
    with pytest.raises(ValueError, match="horizons must match"):
        _validate_flow_window_config(cfg)


def test_semantic_no_qvel_selector_retains_other_fields_in_contract_order():
    raw = np.arange(33, dtype=np.float32)
    selected = select_observation_features(raw, excluded_fields=("arm_velocity7",))
    contract = observation_contract(("arm_velocity7",))
    assert selected.shape == (26,)
    assert contract["state_dim"] == 26
    assert contract["excluded_fields"] == ["arm_velocity7"]
    assert np.array_equal(selected, np.concatenate((raw[:7], raw[14:])))
    assert len(set((observation_contract()["identity"], contract["identity"]))) == 2
