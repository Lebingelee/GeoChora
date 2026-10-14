"""Provider-free contract tests for native-sampled guarded transitions."""

import copy

import pytest

from task_env.tasks.guarded_transition import (
    GuardedTransitionEvaluator,
    TransitionGuardSpec,
)


def _evaluator(*, early=True, start=0.0, deadline=1.5):
    return GuardedTransitionEvaluator(
        source_stage="close_gripper",
        guards=(
            TransitionGuardSpec("primary", "close_gripper", "verify_lift",
                                ("controller_ready", "grasped", "pose_ready"), 0),
            TransitionGuardSpec("alternative", "close_gripper", "verify_lift",
                                ("force_at_least_8n", "force_mode", "initialized",
                                 "grasped", "pose_ready"), 1),
        ),
        required_duration_s=0.1,
        start_time_s=start,
        deadline_s=deadline,
        sample_period_s=0.002,
        allow_early_alternative=early,
    )


def _sample(index, *, primary=False, alternative=True, start=0.0, period=0.002):
    conditions = {
        "controller_ready": primary,
        "force_at_least_8n": alternative,
        "force_mode": alternative,
        "initialized": alternative,
        "grasped": True,
        "pose_ready": True,
    }
    return {
        "sample_time_s": start + index * period,
        "sample_duration_s": period,
        "conditions": conditions,
        "values": {"sample_index": index},
    }


def test_native_500hz_sample_clock_authorizes_after_exact_100ms_and_priority_is_deterministic():
    evaluator = _evaluator()
    decision = None
    for index in range(50):
        decision = evaluator.observe(_sample(index, primary=True))
    assert decision.outcome == "AUTHORIZED"
    assert decision.selected_guard_id == "primary"
    assert decision.evidence["observed_stable_duration_s"] == 0.1
    assert decision.evidence["native_sample_count"] == 50
    assert len(decision.evidence["sample_history_sha256"]) == 64


def test_alternative_can_authorize_early_without_claiming_primary_readiness():
    evaluator = _evaluator()
    decision = None
    for index in range(50):
        decision = evaluator.observe(_sample(index))
    assert decision.outcome == "AUTHORIZED"
    assert decision.selected_guard_id == "alternative"
    assert not decision.evidence["conditions"]["controller_ready"]


def test_false_sample_requires_recovery_and_restarts_full_dwell():
    evaluator = _evaluator()
    for index in range(30):
        evaluator.observe(_sample(index))
    decision = evaluator.observe(_sample(30, alternative=False))
    assert decision.outcome == "RECOVERY_REQUIRED"
    for index in range(31, 81):
        decision = evaluator.observe(_sample(index))
    assert decision.outcome == "AUTHORIZED"
    assert decision.evidence["native_sample_count"] == 50
    assert decision.evidence["window_start_s"] == pytest.approx(0.062)


def test_missing_native_sample_breaks_continuity_without_interpolation():
    evaluator = _evaluator()
    for index in range(30):
        evaluator.observe(_sample(index))
    decision = evaluator.observe(_sample(31))
    assert decision.outcome == "RECOVERY_REQUIRED"
    for index in range(32, 82):
        decision = evaluator.observe(_sample(index))
    assert decision.outcome == "AUTHORIZED"
    assert decision.evidence["native_sample_count"] == 50


def test_snapshot_restore_preserves_partial_dwell_exactly():
    first = _evaluator()
    for index in range(23):
        first.observe(_sample(index))
    state = copy.deepcopy(first.to_mapping())
    restored = _evaluator()
    restored.restore_state(state)
    for index in range(23, 50):
        left = first.observe(_sample(index))
        right = restored.observe(_sample(index))
    assert left.to_mapping() == right.to_mapping()
    assert first.to_mapping() == restored.to_mapping()


def test_no_early_alternative_policy_waits_for_primary_then_fails_closed_at_deadline():
    evaluator = _evaluator(early=False, deadline=0.2)
    decision = None
    for index in range(100):
        decision = evaluator.observe(_sample(index))
    assert decision.outcome == "FAILED"
    assert decision.selected_guard_id is None


def test_rejects_duplicate_or_wrong_period_samples():
    evaluator = _evaluator()
    evaluator.observe(_sample(0))
    with pytest.raises(ValueError, match="strictly time ordered"):
        evaluator.observe(_sample(0))
    with pytest.raises(ValueError, match="duration differs"):
        _evaluator().observe(_sample(0, period=0.01))


def test_full_candidate_composes_guard_policy_with_v5_clearance_path():
    from task_env.tasks.nut_assembly.clearance_candidate_v5 import (
        NutAssemblyHandClearanceCandidateV5,
    )
    from task_env.tasks.nut_assembly.guarded_authorization_candidate import (
        NutAssemblyGuardedAuthorizationCandidateV1,
    )
    from task_env.tasks.nut_assembly.guarded_authorization_candidate_v2 import (
        NutAssemblyGuardedAuthorizationCandidateV2,
    )

    assert issubclass(NutAssemblyGuardedAuthorizationCandidateV2,
                      NutAssemblyGuardedAuthorizationCandidateV1)
    assert issubclass(NutAssemblyGuardedAuthorizationCandidateV2,
                      NutAssemblyHandClearanceCandidateV5)
    assert NutAssemblyGuardedAuthorizationCandidateV1.version.endswith("guarded-v1")
    assert "v5-clearance" in NutAssemblyGuardedAuthorizationCandidateV2.version
    assert NutAssemblyHandClearanceCandidateV5.descend_endpoint_command_bias_m == 0.0001605
