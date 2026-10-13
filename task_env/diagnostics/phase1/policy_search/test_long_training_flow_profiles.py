from task_env.diagnostics.phase1.policy_search.flow_pilot_rollout import pilot_gate_passes
from task_env.diagnostics.phase1.policy_search.flow100_data import observation_contract
from task_env.diagnostics.phase1.policy_search.flow_variants import VARIANTS, validation_steps_for_budget


def test_long_flow_profiles_freeze_budget_and_final_checkpoint_pilot():
    for name, expected_dim, expected_params in (
        ("v1a", 33, 19_512_264),
        ("v2a", 26, 19_510_472),
    ):
        profile = VARIANTS[name]
        assert profile["actor_iters"] == 15_000
        assert profile["expected_parameter_count"] == expected_params
        assert profile["pred_horizon"] == 50 and profile["act_horizon"] == 36
        assert profile["rollout_checkpoint_role"] == "final"
        assert profile["pilot_first"] is True
        assert observation_contract(profile["excluded_fields"])["state_dim"] == expected_dim


def test_validation_schedule_supports_15000_updates_and_final_partial_boundary():
    assert validation_steps_for_budget(15_000) == [0, *range(1_000, 15_000, 1_000), 15_000]
    assert validation_steps_for_budget(1_360) == [0, 1_000, 1_360]


def test_long_flow_pilot_requires_both_seeds_before_full_cohort():
    assert not pilot_gate_passes([
        {"seed": 1000, "task_success": True},
        {"seed": 1010, "task_success": False},
    ])
    assert not pilot_gate_passes([{"seed": 1000, "task_success": True}])
    assert pilot_gate_passes([
        {"seed": 1010, "task_success": True},
        {"seed": 1000, "task_success": True},
    ])
