"""Versioned NutAssembly solution with explicit lifecycle completion policy.

V1 remains the historical immediate-on-success implementation.  V2 adds a
provider-neutral lifecycle owner and can continue through a required terminal
expert stage after task success.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ...controllers.canonical.contracts import digest
from ...utils.rotation import (
    quat_angle_wxyz,
    quat_multiply_wxyz,
    quat_wxyz_to_matrix,
)
from ..canonical_solution_lifecycle import (
    CanonicalSolutionLifecycle,
    SolutionCompletionPolicy,
)
from .canonical_solution import NutAssemblyCanonicalSolutionV1
from .stable_grasp_candidate import NutAssemblyStableGraspCandidate


class _LifecycleV2Mixin:
    """Shared lifecycle adapter; task-specific readiness stays on the solution."""

    completion_policy = SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Legacy flags are initialized by V1 for compatibility with its methods.
        # V2 removes them after reset and owns terminal truth only in lifecycle.
        self._lifecycle = CanonicalSolutionLifecycle(self.completion_policy)
        self._last_observed_step = 0
        self._last_observed_time_s = 0.0
        self.lifecycle_source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity = digest({
            "base_identity": self.identity,
            "version": self.version,
            "completion_policy": self.completion_policy.value,
            "lifecycle_version": self._lifecycle.version,
            "lifecycle_source_sha256": self.lifecycle_source_sha256,
        })

    @property
    def done(self):
        return self._lifecycle.expert_complete

    @property
    def failed(self):
        return self._lifecycle.expert_failed

    @property
    def failure_reason(self):
        return self._lifecycle.failure_reason

    @property
    def lifecycle(self):
        """Read-only owner used by recorder/replay diagnostics."""
        return self._lifecycle

    def reset(self, observation, info, metadata):
        # Historical reset observes is_success as done.  V2 must first prepare
        # the stage plan, then separately record the actual initial outcome.
        preparatory_info = dict(info)
        preparatory_info["is_success"] = False
        preparatory_info["task_failure"] = False
        super().reset(observation, preparatory_info, metadata)
        for name in ("_done", "_failed", "_failure_reason"):
            vars(self).pop(name, None)
        self._lifecycle.reset()
        self._last_observed_step = 0
        self._last_observed_time_s = 0.0
        self._lifecycle.observe_task_outcome(
            task_success=bool(info.get("is_success", False)),
            task_failure=bool(info.get("task_failure", False)),
            control_step=0,
            simulation_time_s=0.0,
        )

    def _clock(self, info):
        step = info.get("control_step", self._emitted)
        time_s = info.get("simulation_time_s", float(step) * self.control_dt)
        if isinstance(step, bool) or not isinstance(step, (int, np.integer)):
            raise ValueError("Canonical Solution lifecycle requires an integer control_step")
        return int(step), float(time_s)

    def _fail(self, reason):
        self._lifecycle.fail(
            reason,
            control_step=self._last_observed_step,
            simulation_time_s=self._last_observed_time_s,
        )

    def observe(self, obs, reward, terminated, truncated, info, *, readiness=None):
        step, time_s = self._clock(info)
        self._last_observed_step, self._last_observed_time_s = step, time_s
        terminal = self._lifecycle.observe_task_outcome(
            task_success=bool(info.get("is_success", False)),
            task_failure=bool(info.get("task_failure", False)),
            terminated=bool(terminated),
            truncated=bool(truncated),
            control_step=step,
            simulation_time_s=time_s,
        )
        if terminal:
            return

        # Stable-grasp acquisition retains its original gates.  Feed the legacy
        # implementation a false success bit only after lifecycle recorded the
        # real semantic event, so its V1 early-return cannot end V2 execution.
        if isinstance(self, NutAssemblyStableGraspCandidate) and self.stage in {
            "descend_to_handle", "close_gripper"
        }:
            acquisition_info = dict(info)
            acquisition_info["is_success"] = False
            NutAssemblyStableGraspCandidate.observe(
                self, obs, reward, terminated, truncated, acquisition_info,
                readiness=readiness,
            )
            return

        self._observe_stage(obs, info, readiness)

    def _observe_stage(self, obs, info, readiness):
        if self._emitted > self._ticks(self.config.action_budget_s):
            self._fail("canonical_solution_action_budget")
            return
        metrics = info["task_metrics"]
        opening = float(metrics["gripper_opening"])
        opening_speed = abs(opening - self._last_opening) / self.control_dt
        self._last_opening = opening
        self._opening_history.append(opening)
        self._opening_history = self._opening_history[-self._ticks(self.config.readiness_stable_s):]
        if self._index < len(self._actions):
            return

        ee = self._ee(obs)
        config = self.config
        stage = self.stage
        pose_ready = (
            np.linalg.norm(ee[:3] - self._goal[:3]) <= config.pose_position_ready_m
            and quat_angle_wxyz(ee[3:], self._goal[3:]) <= config.pose_rotation_ready_rad
        )
        limit = config.max_pose_hold_s
        ready = pose_ready
        if stage == "close_gripper":
            force_ready = bool(readiness and readiness.gripper.close_ready)
            window_stable = (
                len(self._opening_history) == self._ticks(config.readiness_stable_s)
                and max(self._opening_history) - min(self._opening_history)
                <= config.opening_stable_range_m
            )
            contact_load = bool(
                readiness
                and readiness.gripper.closing_force_N >= config.grasp_min_closing_force_N
            )
            ready = bool(metrics["grasped_nut"]) and (
                force_ready or (window_stable and contact_load)
            )
            limit = config.max_close_hold_s
        elif stage == "verify_lift":
            nut = self._body(obs, "square_nut_v1")
            relative = quat_wxyz_to_matrix(ee[3:]).T @ (nut[:3] - ee[:3])
            inverse = ee[3:].copy()
            inverse[1:] *= -1
            rotation = quat_multiply_wxyz(inverse, nut[3:])
            capture_ready = (
                np.linalg.norm(relative - self._captured_position)
                <= config.capture_translation_slip_m
                and quat_angle_wxyz(rotation, self._captured_rotation)
                <= config.capture_rotation_slip_rad
            )
            ready = pose_ready and bool(metrics["lifted_nut"]) and capture_ready
        elif stage == "move_above_square_peg":
            ready = pose_ready and bool(metrics["hovered_over_peg"])
        elif stage == "lower_nut_to_table":
            ready = pose_ready and bool(metrics["inserted_on_peg"])
        elif stage == "open_gripper":
            ready = opening >= 0.065
            limit = config.max_release_hold_s

        self._stable_ticks = self._stable_ticks + 1 if ready else 0
        if self._stable_ticks >= self._ticks(config.readiness_stable_s):
            if stage == "release_retreat":
                step, time_s = self._clock(info)
                self._lifecycle.complete_expert(
                    terminal_stage_completed=True,
                    final_task_success=bool(info.get("is_success", False)),
                    control_step=step,
                    simulation_time_s=time_s,
                )
                return
            self._stage_index += 1
            self._plan(obs)
        elif self._hold_ticks >= self._ticks(limit):
            self._fail(stage + "_readiness_timeout")


class NutAssemblyCanonicalSolutionV2(_LifecycleV2Mixin, NutAssemblyCanonicalSolutionV1):
    """Versioned generic NutAssembly expert with terminal-stage completion."""

    version = "nut-assembly-canonical-solution-v2"


class NutAssemblyStableGraspCandidateV2(
    _LifecycleV2Mixin, NutAssemblyStableGraspCandidate
):
    """Stable-grasp candidate with a separately versioned lifecycle policy."""

    version = "nutassembly-r5-stable-grasp-10n-plus1mm-terminal-lifecycle-v2"
