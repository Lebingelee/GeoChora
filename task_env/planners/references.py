"""Optional concise vocabulary over the unchanged Cartesian pose planner.

These functions generate references only. Actual pose stability belongs to the
feedback window/coordinator, and force readiness to the canonical controller.
"""
from .cartesian import CartesianPosePlanner

class MotionReferences:
    def __init__(self, planner=None):
        self.planner = planner if planner is not None else CartesianPosePlanner()
    def move(self, **kwargs):
        return self.planner.plan_to_pose(**kwargs)
    def hold(self, **kwargs):
        return self.planner.hold_pose(**kwargs)
    def gripper_transition(self, **kwargs):
        return self.planner.plan_gripper_transition(**kwargs)
