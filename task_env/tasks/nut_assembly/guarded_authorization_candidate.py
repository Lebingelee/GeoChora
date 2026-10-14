"""Versioned NutAssembly primary/alternative close authorization candidate.

This task-local candidate preserves R3's 10 N force regulation and uses a
provider-neutral native-sample guard to authorize the existing close-to-lift
transition. It is opt-in and does not replace the historical 9 N contract.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ...controllers.canonical.contracts import digest
from ...utils.rotation import quat_angle_wxyz
from ..guarded_transition import GuardedTransitionEvaluator, TransitionGuardSpec
from .canonical_solution_v2 import NutAssemblyStableGraspCandidateV2, _LifecycleV2Mixin


class NutAssemblyGuardedAuthorizationCandidateV1(NutAssemblyStableGraspCandidateV2):
    """R5/V2 full-task candidate with explicitly versioned 9 N / 8 N guards."""

    version = "nutassembly-r5-primary-readiness-alternative-8n-guarded-v1"
    primary_guard_id = "primary_controller_close_ready"
    alternative_guard_id = "alternative_force_8n"
    alternative_force_threshold_N = 8.0
    authorization_dwell_s = 0.1
    authorization_deadline_s = 1.5
    early_alternative_authorization = True

    def __init__(self, *, config, control_dt, arm_hold, physics_dt_s):
        self.physics_dt_s = float(physics_dt_s)
        if not np.isfinite(self.physics_dt_s) or self.physics_dt_s <= 0:
            raise ValueError("positive native physics timestep required")
        self._close_action_completed_at_s = None
        self._transition_guard_state = None
        self._close_authorization = None
        self._last_guard_decision = None
        super().__init__(config=config, control_dt=control_dt, arm_hold=arm_hold)
        self.policy_mapping = {
            "schema": "nutassembly-close-authorization-primary-alternative-v1",
            "primary_guard": {
                "guard_id": self.primary_guard_id,
                "conditions": ["controller_close_ready", "grasped_nut", "pose_ready"],
                "meaning": "historical canonical Controller Readiness",
            },
            "alternative_guard": {
                "guard_id": self.alternative_guard_id,
                "conditions": ["measured_force_at_least_threshold", "force_mode_active",
                               "force_mode_initialized", "grasped_nut", "pose_ready"],
                "threshold_N": self.alternative_force_threshold_N,
                "meaning": "task-facing alternative authorization; never relabeled as Controller Readiness",
            },
            "selection": {
                "allow_early_alternative": self.early_alternative_authorization,
                "same_sample_tie_break": "primary_controller_readiness_first",
            },
            "required_continuous_dwell_s": self.authorization_dwell_s,
            "deadline_from_close_stage_entry_s": self.authorization_deadline_s,
            "sampling": {
                "clock": "native-physics-state-and-canonical-controller-feedback",
                "sample_period_s": self.physics_dt_s,
                "sample_interval": "measured-left-closed-right-open",
                "missing_samples": "break-continuity; no interpolation",
                "decision_boundary": "next-outer-control-boundary",
            },
            "post_authorization_hold_s": self.postclose_hold_s,
            "physical_force_regulation": {"target_N": 10.0, "cap_N": 10.0,
                                          "controller_law": "unchanged R3"},
        }
        self.policy_identity = digest({
            "policy": self.policy_mapping,
            "evaluator": GuardedTransitionEvaluator.version,
            "evaluator_source_sha256": hashlib.sha256(
                Path(__import__(GuardedTransitionEvaluator.__module__, fromlist=["__file__"]).__file__).read_bytes()
            ).hexdigest(),
        })
        self.identity = digest({
            "base_identity": self.identity,
            "version": self.version,
            "policy_identity": self.policy_identity,
            "candidate_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        })

    def reset(self, observation, info, metadata):
        self._close_action_completed_at_s = None
        self._transition_guard_state = None
        self._close_authorization = None
        self._last_guard_decision = None
        super().reset(observation, info, metadata)

    def _evaluator(self, start_time_s):
        guards = (
            TransitionGuardSpec(
                self.primary_guard_id, "close_gripper", "verify_lift",
                ("controller_close_ready", "grasped_nut", "pose_ready"), 0,
            ),
            TransitionGuardSpec(
                self.alternative_guard_id, "close_gripper", "verify_lift",
                ("measured_force_at_least_threshold", "force_mode_active",
                 "force_mode_initialized", "grasped_nut", "pose_ready"), 1,
            ),
        )
        evaluator = GuardedTransitionEvaluator(
            source_stage="close_gripper", guards=guards,
            required_duration_s=self.authorization_dwell_s,
            start_time_s=float(start_time_s),
            deadline_s=float(start_time_s) + self.authorization_deadline_s,
            sample_period_s=self.physics_dt_s,
            allow_early_alternative=self.early_alternative_authorization,
        )
        if self._transition_guard_state is not None:
            evaluator.restore_state(self._transition_guard_state)
        return evaluator

    def _plan(self, observation):
        super()._plan(observation)
        if self.stage == "close_gripper":
            self._transition_guard_state = self._evaluator(self._close_gate.start_s).to_mapping()
            self._close_action_completed_at_s = None
            self._close_authorization = None

    def make_native_guard_sample(self, state, info, diagnostics):
        """Map canonical state/task facts and controller-owned diagnostics to guard evidence."""
        if self.stage != "close_gripper":
            raise ValueError("close authorization samples are only valid in close_gripper")
        ee_pose = state.pose_world["panda-v1/ee"]
        ee = np.asarray([*ee_pose.position, *ee_pose.quaternion_wxyz], dtype=float)
        pose_ready = bool(
            np.linalg.norm(ee[:3] - self._goal[:3]) <= self.config.pose_position_ready_m
            and quat_angle_wxyz(ee[3:], self._goal[3:]) <= self.config.pose_rotation_ready_rad
        )
        force_N = float(diagnostics["closing_force_N"])
        force_mode_active = bool(diagnostics["force_mode_active"])
        force_mode_initialized = bool(diagnostics["force_mode_initialized"])
        controller_ready = bool(diagnostics["controller_close_ready"])
        grasped = bool(info["task_metrics"].get("grasped_nut", False))
        conditions = {
            "controller_close_ready": controller_ready,
            "measured_force_at_least_threshold": force_N >= self.alternative_force_threshold_N,
            "force_mode_active": force_mode_active,
            "force_mode_initialized": force_mode_initialized,
            "grasped_nut": grasped,
            "pose_ready": pose_ready,
        }
        return {
            "sample_time_s": float(state.simulation_time),
            "sample_duration_s": self.physics_dt_s,
            "conditions": conditions,
            "values": {
                "control_step": int(state.control_step),
                "closing_force_N": force_N,
                "force_mode_active": force_mode_active,
                "force_mode_initialized": force_mode_initialized,
                "controller_close_ready": controller_ready,
                "grasped_nut": grasped,
                "pose_ready": pose_ready,
                "finger_opening_m": float(diagnostics["measured_opening_m"]),
            },
        }

    def _observe_guarded_close(self, obs, terminated, truncated, info,
                               transition_samples=None):
        if terminated or truncated:
            self._fail("environment_terminated")
            return
        if self._emitted > self._ticks(self.config.action_budget_s):
            self._fail("canonical_solution_action_budget")
            return
        if self._index < len(self._actions):
            if self._close_gate.wait_until(self._last_observed_time_s, False) == "timeout":
                self._fail("close_gripper_authorization_deadline")
            return

        now_s = float(self._last_observed_time_s)
        if self._close_action_completed_at_s is None:
            self._close_action_completed_at_s = now_s
            # The final commanded close interval predates this completion
            # boundary; only subsequent native observations can start dwell.
            self._transition_guard_state = self._evaluator(self._close_gate.start_s).to_mapping()

        evaluator = self._evaluator(self._close_gate.start_s)
        for sample in transition_samples or ():
            if float(sample["sample_time_s"]) < self._close_action_completed_at_s - 1e-10:
                continue
            decision = evaluator.observe(sample)
            self._last_guard_decision = decision.to_mapping()
            self._transition_guard_state = evaluator.to_mapping()
            if decision.outcome == "RECOVERY_REQUIRED":
                self.events.append({
                    "event": "close_authorization_guard_recovery_required",
                    "t": decision.simulation_time_s,
                    "evidence": decision.evidence,
                })
            if decision.outcome == "AUTHORIZED":
                self._close_authorization = {
                    "authorization_guard_id": decision.selected_guard_id,
                    "authorization_time_s": decision.simulation_time_s,
                    "transition_consumed_at_outer_boundary_s": now_s,
                    "source_stage": decision.source_stage,
                    "target_stage": decision.target_stage,
                    "required_stable_duration_s": self.authorization_dwell_s,
                    **decision.evidence,
                    "policy_identity": self.policy_identity,
                }
                self.events.append({
                    "event": "close_transition_authorized",
                    "t": decision.simulation_time_s,
                    **self._close_authorization,
                    "controller_close_ready": bool(
                        decision.evidence["conditions"]["controller_close_ready"]
                    ),
                    "fallback_used": False,
                })
                self._stage_index += 1
                self._plan(obs)
                return
            if decision.outcome == "FAILED":
                self._fail("close_gripper_authorization_deadline")
                return

        deadline = self._close_gate.start_s + self.authorization_deadline_s
        if now_s >= deadline - 1e-10:
            self._fail("close_gripper_authorization_deadline")

    def observe_guarded_transition(self, obs, reward, terminated, truncated, info,
                                   *, readiness=None, transition_samples=None):
        """Task-specific close edge; shared Lifecycle V2 owns task outcomes."""
        del reward, readiness
        self._observe_guarded_close(obs, terminated, truncated, info, transition_samples)

