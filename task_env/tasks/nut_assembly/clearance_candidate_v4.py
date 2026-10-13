"""Task-local clearance candidate that settles R3 before locking the grasp pose.

The 20 Hz diagnostic exposed a small stable-height error after the Cartesian
plan ended.  The previous candidate locked R3's final joint reference before
the existing 0.5 s pose-stability window, so the controller could not continue
correcting that residual.  This version keeps the same target, path, gates,
deadlines, R3 gains, gripper cap, assets, and collision model; it only defers
the task-local arm hold lock until the existing stable-pose event.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ...controllers.canonical.contracts import digest
from .clearance_candidate_v3 import NutAssemblyHandClearanceCandidateV3


class NutAssemblyHandClearanceCandidateV4(NutAssemblyHandClearanceCandidateV3):
    """Clearance grasp with live R3 settling during the existing pose window."""

    version = "nutassembly-r5-stable-grasp-10n-lifecycle-v2-handle-clearance-v4-live-settle"

    def __init__(self, *, config, control_dt, arm_hold):
        super().__init__(config=config, control_dt=control_dt, arm_hold=arm_hold)
        source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity = digest({
            "base_identity": self.identity,
            "version": self.version,
            "source_sha256": source_sha256,
            "behavior_change": "defer_task_local_arm_hold_until_pose_stability_event",
            "deferred_lock_window": "existing_descend_to_handle_pose_stability_window",
            "preserved": {
                "trajectory": "handle-clearance-v3",
                "pose_gate": self.stable_height_tolerance_m,
                "pose_stability_window_s": self.minimum_pose_wait_s,
                "pose_span_m": self.pose_span_m,
                "pose_speed_m_s": self.pose_speed_m_s,
                "stage_deadlines": "unchanged",
                "r3_gains": "unchanged",
                "gripper_force_cap_N": 10.0,
                "task_success_semantics": "canonical-unchanged",
                "collision_geometry": "unchanged",
                "contact_solver": "unchanged-NoSlip2",
            },
        })

    def observe(self, obs, reward, terminated, truncated, info, *, readiness=None):
        if self.stage != "descend_to_handle" or self._index < len(self._actions):
            return super().observe(
                obs, reward, terminated, truncated, info, readiness=readiness
            )

        # The parent candidate normally locks the last joint reference as soon
        # as the planned actions end.  During its existing stability window,
        # suppress only that early lock so R3 keeps tracking the final pose.
        # Once the stable-pose event advances the stage, lock the last acknowledged
        # R3 target exactly once before the close-gripper stage runs.
        lock = self.arm_hold.lock
        stage_before = self.stage
        locked_before = self.arm_hold.locked
        self.arm_hold.lock = lambda: None
        try:
            super().observe(
                obs, reward, terminated, truncated, info, readiness=readiness
            )
        finally:
            self.arm_hold.lock = lock

        if stage_before == "descend_to_handle" and self.stage != stage_before and not locked_before:
            lock()
