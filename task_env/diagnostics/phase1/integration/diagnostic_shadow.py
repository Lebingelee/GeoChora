"""Opt-in shadow stage progression for physical diagnostic observations.

The canonical Expert remains authoritative for its original gate result. This
coordinator owns only a private planning copy after a non-runtime failure and
never changes the Expert lifecycle or task semantics.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


POLICY_ID = "nutassembly-full-trajectory-observation-v1"
SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class DiagnosticShadowCoordinator:
    """Continue authored stage plans after failed readiness gates.

    Runtime termination/truncation and the canonical action budget remain hard
    stops. Stage-local readiness failures are recorded and may advance only the
    private shadow copy to the next declared stage.
    """

    def __init__(self, expert):
        self.expert = expert
        self.shadow = None
        self.events = []
        self.stop_reason = None
        self.initial_stage = expert.stage
        self.stage_sequence = [expert.stage]

    @property
    def active(self):
        return self.shadow if self.shadow is not None else self.expert

    @property
    def using_shadow(self):
        return self.shadow is not None

    def state_mapping(self, actor=None):
        actor = self.active if actor is None else actor
        return {
            "policy_id": POLICY_ID,
            "owner": "diagnostic_shadow" if actor is self.shadow else "canonical_expert",
            "stage": actor.stage,
            "stage_index": int(actor._stage_index),
            "action_index": int(actor._index),
            "planned_action_count": int(len(actor._actions)),
            "emitted_action_count": int(actor._emitted),
            "hold_ticks": int(actor._hold_ticks),
            "lift_motion_released": bool(getattr(actor, "_lift_released", False)),
            "expert_failure_preserved": bool(self.expert.failed),
            "expert_failure_reason": self.expert.failure_reason,
        }

    def record(self, event, *, time_s, control_step, **details):
        item = {"event": event, "simulation_time_s": float(time_s),
                "control_step": int(control_step), **details}
        self.events.append(item)
        return item

    def ordered_events(self):
        priority = {
            "stage_actions_executed": 0,
            "stage_readiness_passed": 1,
            "stage_readiness_failed": 1,
            "task_failure_observed_diagnostic_continuation": 1,
            "stage_advanced_by_diagnostic_override": 2,
            "stage_entered": 3,
            "diagnostic_sequence_completed": 4,
            "diagnostic_stop": 4,
        }
        return sorted(self.events, key=lambda event: (
            event["control_step"], priority.get(event["event"], 5)
        ))

    def observe_shadow(self, obs, reward, info, readiness, *, control_step, time_s,
                       transition_samples=None):
        """Observe real state while keeping non-terminal task failure physical."""
        actor = self.shadow
        if actor is None:
            raise RuntimeError("shadow coordinator is not active")
        metrics = info.get("task_metrics", {})
        if info.get("task_failure", False):
            self.record("task_failure_observed_diagnostic_continuation",
                        time_s=time_s, control_step=control_step,
                        task_metrics=dict(metrics))
        diagnostic_info = dict(info)
        # Task failure remains in the recorded canonical outcome. It is not a
        # runtime terminal signal, so it cannot stop physical observation.
        diagnostic_info["task_failure"] = False
        actor.observe(obs, reward, False, False, diagnostic_info,
                      readiness=readiness,
                      transition_samples=transition_samples)

    def advance_after_failure(self, *, reason, obs, info, control_step, time_s,
                              terminated=False, truncated=False):
        """Record a gate failure and prepare the next existing stage plan."""
        current = self.active
        stage = current.stage
        if terminated or truncated or reason in {
            "environment_terminated", "environment_truncated",
            "environment_terminated_before_expert_completion",
            "environment_truncated_before_expert_completion",
            "canonical_solution_action_budget",
        }:
            self.stop_reason = (
                "ENVIRONMENT_TERMINATED" if terminated or "terminated" in str(reason)
                else "ENVIRONMENT_TRUNCATED" if truncated or "truncated" in str(reason)
                else "ACTION_BUDGET_EXHAUSTED"
            )
            self.record("diagnostic_stop", time_s=time_s, control_step=control_step,
                        reason=self.stop_reason, original_failure_reason=reason,
                        stage=stage)
            return False

        self.record("stage_readiness_failed", time_s=time_s, control_step=control_step,
                    stage=stage, gate_failure_reason=str(reason),
                    expert_gate_pass=False)
        next_index = int(current._stage_index) + 1
        if next_index >= len(current.STAGES):
            self.stop_reason = "DIAGNOSTIC_SEQUENCE_COMPLETED"
            self.record("diagnostic_sequence_completed", time_s=time_s,
                        control_step=control_step, final_stage=stage,
                        final_stage_gate_pass=False)
            return False

        source = current
        init_kwargs = {
            "config": source.config,
            "control_dt": source.control_dt,
            "arm_hold": source.arm_hold,
        }
        if hasattr(source, "physics_dt_s"):
            init_kwargs["physics_dt_s"] = source.physics_dt_s
        try:
            candidate = type(source)(**init_kwargs)
        except Exception as exc:
            self.stop_reason = "PLAN_UNAVAILABLE"
            self.record("diagnostic_stop", time_s=time_s, control_step=control_step,
                        reason=self.stop_reason, stage=stage,
                        next_stage=source.STAGES[next_index],
                        error=f"shadow owner construction: {type(exc).__name__}: {exc}")
            return False
        # Carry only task-plan memory needed to express the next authored stage.
        # Controller state remains owned by the live controller, and the
        # original Expert's lifecycle is never reset or copied over.
        candidate._emitted = int(source._emitted)
        candidate._last_opening = float(source._last_opening)
        for field in ("_grasp_pose", "_captured_position", "_captured_rotation"):
            if hasattr(source, field):
                value = getattr(source, field)
                setattr(candidate, field, np.array(value, copy=True)
                        if isinstance(value, np.ndarray) else value)
        for field in ("_pose_wait_start", "_postclose_hold_ticks", "_lift_released"):
            if hasattr(source, field):
                setattr(candidate, field, getattr(source, field))
        if hasattr(candidate, "events"):
            candidate.events = list(getattr(source, "events", []))
        candidate._last_observed_step = int(control_step)
        candidate._last_observed_time_s = float(time_s)
        candidate._stage_index = next_index
        try:
            candidate._plan(obs)
        except Exception as exc:
            self.stop_reason = "PLAN_UNAVAILABLE"
            self.record("diagnostic_stop", time_s=time_s, control_step=control_step,
                        reason=self.stop_reason, stage=stage,
                        next_stage=candidate.STAGES[next_index],
                        error=f"{type(exc).__name__}: {exc}")
            return False
        self.shadow = candidate
        next_stage = candidate.stage
        self.stage_sequence.append(next_stage)
        self.record("stage_advanced_by_diagnostic_override", time_s=time_s,
                    control_step=control_step, from_stage=stage, to_stage=next_stage,
                    transition_reason="diagnostic_continuation",
                    expert_qualification_pass=False)
        self.record("stage_entered", time_s=time_s, control_step=control_step,
                    stage=next_stage, entered_by="diagnostic_override")
        return True


def replay_policy_identity(solution_identity: str) -> str:
    """Stable identity for the source Expert plus diagnostic progression law."""
    raw = f"{POLICY_ID}:{SOURCE_SHA256}:{solution_identity}"
    return hashlib.sha256(raw.encode()).hexdigest()
