"""Provider-free contract checks for diagnostic-only stage continuation."""

from task_env.diagnostics.phase1.integration.diagnostic_shadow import (
    DiagnosticShadowCoordinator,
    POLICY_ID,
)


class _Lifecycle:
    def __init__(self, terminal=False, reason=None):
        self.status = "failed" if terminal else "active"
        self.failure_reason = reason
        self.reset_count = 0

    @property
    def terminal(self):
        return self.status != "active"

    def reset(self):
        self.status = "active"
        self.failure_reason = None
        self.reset_count += 1


class _Solution:
    STAGES = ("approach_nut", "descend_to_handle", "close_gripper")

    def __init__(self, config=None, control_dt=0.02, arm_hold=None,
                 stage_index=0, *, failed=False, reason=None):
        self.config = config
        self.control_dt = control_dt
        self.arm_hold = arm_hold
        self._stage_index = stage_index
        self._index = 0
        self._actions = [1, 2]
        self._emitted = 4
        self._last_opening = 0.05
        self._hold_ticks = 0
        self._lift_released = False
        self._done = False
        self._failed = failed
        self._failure_reason = reason
        self.lifecycle = _Lifecycle(terminal=failed, reason=reason)
        self._lifecycle = self.lifecycle
        self.planned = []

    @property
    def stage(self):
        return self.STAGES[self._stage_index]

    @property
    def done(self):
        return self._done

    @property
    def failed(self):
        return self.lifecycle.status == "failed"

    @property
    def failure_reason(self):
        return self.lifecycle.failure_reason or self._failure_reason

    def _plan(self, obs):
        self.planned.append((self.stage, obs))
        self._index = 0
        self._actions = [3]
        self._hold_ticks = 0


def test_readiness_failure_advances_private_shadow_without_clearing_expert_failure():
    expert = _Solution(stage_index=1, failed=True, reason="stable_height_mismatch")
    coordinator = DiagnosticShadowCoordinator(expert)

    continued = coordinator.advance_after_failure(
        reason=expert.failure_reason, obs={"ee": 1}, info={},
        control_step=182, time_s=3.64,
    )

    assert continued is True
    assert coordinator.active is coordinator.shadow
    assert coordinator.shadow.stage == "close_gripper"
    assert coordinator.shadow.planned == [("close_gripper", {"ee": 1})]
    assert expert.failed is True
    assert expert.failure_reason == "stable_height_mismatch"
    assert coordinator.events[0]["event"] == "stage_readiness_failed"
    assert coordinator.events[1]["event"] == "stage_advanced_by_diagnostic_override"
    assert coordinator.state_mapping()["policy_id"] == POLICY_ID
    assert coordinator.state_mapping()["expert_failure_preserved"] is True


def test_action_budget_failure_is_a_hard_diagnostic_stop():
    expert = _Solution(stage_index=1, failed=True,
                       reason="canonical_solution_action_budget")
    coordinator = DiagnosticShadowCoordinator(expert)

    assert coordinator.advance_after_failure(
        reason=expert.failure_reason, obs={}, info={}, control_step=9, time_s=1.0
    ) is False
    assert coordinator.shadow is None
    assert coordinator.stop_reason == "ACTION_BUDGET_EXHAUSTED"


def test_final_stage_gate_failure_completes_diagnostic_sequence_without_expert_pass():
    expert = _Solution(stage_index=2, failed=True, reason="release_retreat_readiness_timeout")
    coordinator = DiagnosticShadowCoordinator(expert)

    assert coordinator.advance_after_failure(
        reason=expert.failure_reason, obs={}, info={}, control_step=20, time_s=2.0
    ) is False
    assert coordinator.stop_reason == "DIAGNOSTIC_SEQUENCE_COMPLETED"
    assert expert.failed is True
