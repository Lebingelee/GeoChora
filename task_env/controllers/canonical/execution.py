"""Additive control-boundary coordination; never steps a provider.

Arm hold preserves R3 reference memory; gripper hold continues force regulation.
Stability uses achieved canonical EE positions and physical simulation times.
These advanced owner APIs do not enlarge task_env root exports.
"""
from dataclasses import replace
import numpy as np

class StableArmTargetHold:
    """Task-local arm hold wrapper; the underlying R3 source is unchanged."""
    def __init__(self, controller):
        self.controller = controller
        self.locked = False
        self.fixed = None
        self.last_target = None

    def __getattr__(self, name):
        return getattr(self.controller, name)

    def lock(self):
        if self.last_target is None:
            raise RuntimeError('arm target unavailable before stable hold')
        self.fixed = dict(self.last_target.arm_servo_position)
        self.locked = True

    def compute(self, state, feedback, requested):
        prior = self.controller._joint_reference.copy()
        canonical, target = self.controller.compute(state, feedback, requested)
        if self.locked:
            self.controller._joint_reference = prior
            target = replace(target, arm_position=dict(self.fixed), arm_servo_position=dict(self.fixed))
            self.controller.last_arm_diagnostics.update(
                experimental_joint_target_hold=True,
                raw_integrated_target_not_applied=True,
                held_arm_target=dict(self.fixed), q_ref_next_rad=prior.tolist())
        else:
            self.controller.last_arm_diagnostics['experimental_joint_target_hold'] = False
        self.last_target = target
        return canonical, target


class PoseStabilityWindow:
    """Exact R5 sampled window: per-axis span plus adjacent Euclidean speed."""
    def __init__(self):
        self.history = []
        self.start = None

    def is_stable(self, t, pose, *, minimum_wait_s, window_s, minimum_samples,
                  axis_span_m, speed_m_s):
        if self.start is None:
            self.start = t
        self.history.append((t, pose.copy()))
        window = [x for x in self.history if x[0] >= t - window_s - 1e-8]
        span = np.ptp(np.array([x[1][:3] for x in window]), axis=0)
        speeds = [np.linalg.norm(window[j][1][:3] - window[j-1][1][:3]) /
                  (window[j][0] - window[j-1][0]) for j in range(1, len(window))]
        stable = (t - self.start >= minimum_wait_s and len(window) >= minimum_samples
                  and max(span) <= axis_span_m and max(speeds, default=1.) <= speed_m_s)
        return stable, span, speeds

    def to_mapping(self):
        return {'start_s': self.start, 'history': [(t, p.tolist()) for t, p in self.history]}


class BoundaryWait:
    """A simulation-time predicate gate; caller advances ordinary public boundaries.

    No native stepping, sleeping or hidden trajectory transitions. hold_for uses
    the same gate with a duration predicate; held actions remain caller-owned.
    """
    def __init__(self, start_s, deadline_s):
        self.start_s = float(start_s)
        self.deadline_s = float(deadline_s)

    def wait_until(self, simulation_time_s, predicate):
        elapsed = simulation_time_s - self.start_s
        if elapsed > self.deadline_s + 1e-8:
            return 'timeout'
        if predicate:
            return 'ready'
        return 'timeout' if elapsed >= self.deadline_s - 1e-8 else 'waiting'

    def hold_for(self, simulation_time_s, duration_s):
        return self.wait_until(simulation_time_s,
                               simulation_time_s - self.start_s >= duration_s - 1e-8)
