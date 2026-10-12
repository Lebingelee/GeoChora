"""Opt-in R5 development grasp procedure; no production route is migrated.

This candidate removes force fallback, stabilizes the achieved arm before
closing, and holds the grasp for physical 0.1 s before verification.
Only close + verify-lift have development evidence; full task is unqualified.
"""
from dataclasses import replace
import hashlib
from pathlib import Path
import numpy as np
from ...controllers.canonical.contracts import digest
from ...utils.rotation import quat_angle_wxyz
from .canonical_solution import NutAssemblyCanonicalSolutionV1
from ...controllers.canonical.execution import StableArmTargetHold, PoseStabilityWindow, BoundaryWait




class NutAssemblyStableGraspCandidate(NutAssemblyCanonicalSolutionV1):
    """Provider-neutral candidate, explicitly selected outside legacy profiles."""
    version = 'nutassembly-r5-stable-grasp-10n-v1'
    minimum_pose_wait_s = .5
    pose_window_s = .2
    pose_span_m = .0001
    pose_speed_m_s = .002
    postclose_hold_s = .1
    servo_height_compensation_m = .0006514767471602623
    stable_height_tolerance_m = .0001
    close_authorization_deadline_s = 1.5

    def __init__(self, *, config, control_dt, arm_hold):
        self.arm_hold = arm_hold
        self.events = []
        self._stability = PoseStabilityWindow()
        self._pose_history = self._stability.history
        self._pose_wait_start = None
        self._postclose_hold_ticks = 0
        self._lift_released = False
        super().__init__(config=config, control_dt=control_dt)
        self.identity = digest({'base': self.identity, 'version': self.version,
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'close_authorization': 'controller_close_ready_only_continuous_0p1s',
            'force_fallback': None, 'minimum_pose_wait_s': self.minimum_pose_wait_s,
            'pose_window_s': self.pose_window_s, 'pose_span_m': self.pose_span_m,
            'pose_speed_m_s': self.pose_speed_m_s, 'postclose_hold_s': self.postclose_hold_s,
            'servo_height_compensation_m': self.servo_height_compensation_m})

    def reset(self, observation, info, metadata):
        self.events = []
        self._stability = PoseStabilityWindow()
        self._pose_history = self._stability.history
        self._pose_wait_start = None
        self._lift_released = False
        self.arm_hold.locked = False
        super().reset(observation, info, metadata)

    def _plan(self, observation):
        super()._plan(observation)
        if self.stage == 'close_gripper':
            pose = self._ee(observation)
            self._goal = pose.copy()
            self._actions[:, :7] = pose.astype(np.float32)
            self._close_gate = BoundaryWait(self._emitted * self.control_dt, self.close_authorization_deadline_s)
            self.events.append({'event': 'close_start', 't': self._emitted * self.control_dt,
                                'stable_pose': pose.tolist()})
        elif self.stage == 'verify_lift':
            pose = self._ee(observation)
            self._postclose_hold_ticks = self._ticks(self.postclose_hold_s)
            hold = np.tile(np.array([*pose, -1.], dtype=np.float32), (self._postclose_hold_ticks, 1))
            self._actions = np.concatenate((hold, self._actions))
            if len(self._actions) * self.control_dt > self.config.max_stage_plan_s:
                raise ValueError('hold + lift exceeds unchanged stage plan budget')
            self.events.append({'event': 'authorized_hold_start', 't': self._emitted * self.control_dt,
                                'duration_s': self._postclose_hold_ticks * self.control_dt})

    def act(self):
        if self.stage == 'verify_lift' and self._index >= self._postclose_hold_ticks and not self._lift_released:
            self.arm_hold.locked = False
            self._lift_released = True
            self.events.append({'event': 'verify_lift_motion_start', 't': self._emitted * self.control_dt})
        return super().act()

    def _stable_height_ready(self, achieved_z, expected_z):
        """Task-local absolute-height check; distinct from measured stability."""
        return abs(achieved_z - expected_z) <= self.stable_height_tolerance_m

    def observe(self, obs, reward, terminated, truncated, info, *, readiness=None):
        if self.stage == 'descend_to_handle' and self._index >= len(self._actions):
            t = self._emitted * self.control_dt
            pose = self._ee(obs)
            if self._pose_wait_start is None:
                self._pose_wait_start = t
                self.arm_hold.lock()
            stable, span, speeds = self._stability.is_stable(
                t, pose, minimum_wait_s=self.minimum_pose_wait_s, window_s=self.pose_window_s,
                minimum_samples=self._ticks(self.pose_window_s),
                axis_span_m=self.pose_span_m, speed_m_s=self.pose_speed_m_s)
            if stable:
                desired_z = self._goal[2] - self.servo_height_compensation_m
                if not self._stable_height_ready(pose[2], desired_z):
                    self._fail('stable_height_mismatch')
                    return
                self.events.append({'event': 'pose_stable', 't': t, 'pose': pose.tolist(),
                    'wait_s': t-self._pose_wait_start, 'position_span_m': span.tolist(),
                    'maximum_speed_m_s': max(speeds), 'stable_height_goal_m': desired_z})
                self._grasp_pose = pose.copy()
                self._stable_ticks = self._ticks(self.config.readiness_stable_s) - 1
            elif t - self._pose_wait_start >= self.config.max_pose_hold_s:
                self._fail('preclose_motion_stability_timeout')
                return
            else:
                return
        if self.stage != 'close_gripper':
            return super().observe(obs, reward, terminated, truncated, info, readiness=readiness)
        if terminated or truncated:
            self._fail('environment_terminated')
            return
        if self._emitted > self._ticks(self.config.action_budget_s):
            self._fail('canonical_solution_action_budget')
            return
        if self._emitted*self.control_dt - self._close_gate.start_s > self.close_authorization_deadline_s + 1e-8:
            self._fail('close_gripper_authorization_deadline')
            return
        if self._index < len(self._actions):
            if self._close_gate.wait_until(self._emitted*self.control_dt, False) == 'timeout':
                self._fail('close_gripper_authorization_deadline')
            return
        ee = self._ee(obs)
        pose_ready = (np.linalg.norm(ee[:3] - self._goal[:3]) <= self.config.pose_position_ready_m and
                      quat_angle_wxyz(ee[3:], self._goal[3:]) <= self.config.pose_rotation_ready_rad)
        ready = (pose_ready and bool(info['task_metrics']['grasped_nut']) and
                 bool(readiness and readiness.gripper.close_ready))
        self._stable_ticks = self._stable_ticks + 1 if ready else 0
        if self._stable_ticks >= self._ticks(self.config.readiness_stable_s):
            self.events.append({'event': 'controller_close_authorized', 't': self._emitted*self.control_dt,
                                'force_N': readiness.gripper.closing_force_N,
                                'stable_window_s': self._ticks(self.config.readiness_stable_s)*self.control_dt,
                                'fallback_used': False})
            self._stage_index += 1
            self._plan(obs)
        elif self._close_gate.wait_until(self._emitted*self.control_dt, False) == 'timeout':
            self._fail('close_gripper_authorization_deadline')
