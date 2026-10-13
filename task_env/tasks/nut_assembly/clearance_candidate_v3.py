"""Task-local grasp variant placing the hand at the outer end of the Nut handle.

This development candidate keeps Lifecycle V2, R3, the 10 N gripper cap,
controller gains, task predicates and all scene collision geometry unchanged.
Its only behavior change is a 24 mm outward shift along the existing square-Nut
handle axis during approach and grasp acquisition. The shift is derived from
the compiled hand/peg overlap and remains within the authored handle collision
extent. It is not a production default or a qualification claim.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ...controllers.canonical.contracts import digest
from ...utils.rotation import rotate_vector_wxyz
from .assets import NUT_HANDLE_LOCAL_X
from .canonical_solution_v2 import NutAssemblyStableGraspCandidateV2


class NutAssemblyHandClearanceCandidateV3(NutAssemblyStableGraspCandidateV2):
    """Lifecycle-V2 stable grasp using the handle's outboard contact region."""

    version = "nutassembly-r5-stable-grasp-10n-lifecycle-v2-handle-clearance-v3"
    outward_handle_offset_m = 0.024

    def __init__(self, *, config, control_dt, arm_hold):
        super().__init__(config=config, control_dt=control_dt, arm_hold=arm_hold)
        self.source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity = digest({
            "base_identity": self.identity,
            "version": self.version,
            "source_sha256": self.source_sha256,
            "handle_center_local_x_m": NUT_HANDLE_LOCAL_X,
            "outward_handle_offset_m": self.outward_handle_offset_m,
            "planning": "existing-physical-time-absolute-pose-planner",
            "behavior_change": "approach_and_descend_grasp_point_outboard_on_square_nut_handle",
            "preserved": {
                "lifecycle": "v2",
                "gripper_force_cap_N": 10.0,
                "controller": "R3-existing-gains",
                "task_success_semantics": "canonical-unchanged",
                "collision_geometry": "unchanged",
            },
        })

    def _plan(self, observation):
        super()._plan(observation)
        stage = self.stage
        if stage not in {"approach_nut", "descend_to_handle"}:
            return

        ee = self._ee(observation)
        nut = self._body(observation, "square_nut_v1")
        handle_x = NUT_HANDLE_LOCAL_X + self.outward_handle_offset_m
        handle = nut[:3] + rotate_vector_wxyz(
            nut[3:], np.array([handle_x, 0.0, 0.0], dtype=float)
        )
        goal = self._goal.copy()
        if stage == "approach_nut":
            goal[:3] = handle + np.array([0.0, 0.0, self.config.approach_height_m])
            gripper = 1.0
        else:
            goal[:3] = handle + np.asarray(self.config.grasp_offset, dtype=float)
            gripper = 1.0
        self._goal = goal
        self._actions = self._planner.plan_to_pose(
            current_pose=ee,
            goal_pose=goal,
            gripper=gripper,
        )
