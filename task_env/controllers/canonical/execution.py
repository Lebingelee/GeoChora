"""Additive control-boundary coordination; never steps a provider.

Arm hold preserves R3 reference memory; gripper hold continues force regulation.
Stability uses achieved canonical EE positions and physical simulation times.
These advanced owner APIs do not enlarge task_env root exports.
"""
from dataclasses import dataclass, replace
from collections.abc import Mapping
import math
import numpy as np


@dataclass(frozen=True)
class ArmTargetExecutionRequestV1:
    """Versioned task request consumed by the existing arm Controller owner."""

    schema_version: str
    profile_id: str
    mode: str

    def validate(self):
        if (self.schema_version, self.profile_id) != (
            "arm-target-execution-request-v1", "nutassembly-r3-hold-ramp-v1",
        ):
            raise ValueError("unsupported arm target execution request")
        if self.mode not in {"track", "hold_last_applied", "ramp_from_last_applied"}:
            raise ValueError("unsupported arm target execution mode")

class StableArmTargetHold:
    """Task-local arm hold wrapper; the underlying R3 source is unchanged."""
    def __init__(self, controller):
        self.controller = controller
        self.locked = False
        self.fixed = None
        self.last_target = None
        self.last_applied_arm = None
        self._request = ArmTargetExecutionRequestV1(
            "arm-target-execution-request-v1", "nutassembly-r3-hold-ramp-v1", "track",
        )
        self._ramp_initial = None

    def reset(self, state, feedback):
        """Reset Controller and its single owner of hold/ramp acknowledgement state."""
        self.locked = False
        self.fixed = None
        self.last_target = None
        self.last_applied_arm = None
        self._ramp_initial = None
        self._request = ArmTargetExecutionRequestV1(
            "arm-target-execution-request-v1", "nutassembly-r3-hold-ramp-v1", "track",
        )
        return self.controller.reset(state, feedback)

    def __getattr__(self, name):
        return getattr(self.controller, name)

    def lock(self):
        if self.last_target is None:
            raise RuntimeError('arm target unavailable before stable hold')
        self.fixed = dict(self.last_target.arm_servo_position)
        self.locked = True

    def validate_execution_request(self, request):
        if not isinstance(request, ArmTargetExecutionRequestV1):
            raise TypeError("arm execution requires ArmTargetExecutionRequestV1")
        request.validate()
        if request.mode in {"hold_last_applied", "ramp_from_last_applied"}:
            if self.last_applied_arm is None:
                raise ValueError("arm hold/ramp requires a preceding applied acknowledgement")

    def request_execution(self, request):
        self.validate_execution_request(request)
        self._request = request
        if request.mode == "hold_last_applied":
            if not self.locked:
                self.fixed = dict(self.last_applied_arm)
            self.locked = True
            self._ramp_initial = None
        elif request.mode == "ramp_from_last_applied":
            self.locked = False
            self.fixed = None
        else:
            self.locked = False
            self.fixed = None
            self._ramp_initial = None

    def begin(self, target):
        self._ramp_initial = None
        if self._request.mode == "ramp_from_last_applied":
            initial = dict(self.last_applied_arm or {})
            endpoint = dict(target.arm_servo_position)
            if not initial or set(initial) != set(endpoint):
                raise ValueError("arm ramp acknowledgement does not match target resources")
            if not all(math.isfinite(float(value)) for value in (*initial.values(), *endpoint.values())):
                raise ValueError("arm ramp requires finite acknowledged and requested targets")
            self._ramp_initial = initial

    def target(self, target, index, count):
        if type(index) is not int or type(count) is not int or count < 1 or not 0 <= index < count:
            raise ValueError("invalid native arm target substep")
        if self._request.mode == "hold_last_applied":
            if self.fixed is None:
                raise RuntimeError("arm hold has no applied target")
            return replace(target, arm_position=dict(self.fixed), arm_servo_position=dict(self.fixed))
        if self._request.mode != "ramp_from_last_applied":
            return target
        if self._ramp_initial is None:
            raise RuntimeError("arm ramp was not initialized at the interval boundary")
        fraction = (index + 1) / count
        arm = {key: self._ramp_initial[key] + fraction * (value - self._ramp_initial[key])
               for key, value in target.arm_servo_position.items()}
        return replace(target, arm_position=arm, arm_servo_position=arm)

    def applied(self, acknowledgement):
        arm = getattr(acknowledgement, "arm_servo_position", None)
        if not isinstance(arm, Mapping) or not arm:
            raise ValueError("arm execution requires a real applied acknowledgement")
        values = {str(name): float(value) for name, value in arm.items()}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("arm acknowledgement must be finite")
        if self.last_applied_arm is not None and set(values) != set(self.last_applied_arm):
            raise ValueError("arm acknowledgement resource identity changed")
        self.last_applied_arm = values

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
