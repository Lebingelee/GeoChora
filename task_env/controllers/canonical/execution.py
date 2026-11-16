"""Additive control-boundary coordination; never steps a provider.

Arm hold preserves R3 reference memory; gripper hold continues force regulation.
Stability uses achieved canonical EE positions and physical simulation times.
These advanced owner APIs do not enlarge task_env root exports.
"""
from dataclasses import dataclass, replace
from collections.abc import Mapping
import math
import numpy as np

from .gripper_execution import EqualRateGripperServo, NativeRateGripperServo


R3_REFERENCE_POSITION_PROFILES = frozenset(('r3_continuous_v1',))
REFERENCE_POSITION_CONTROLLER_PROFILES = R3_REFERENCE_POSITION_PROFILES | frozenset(('r1', 'r1_split'))
ARM_HOLD_RAMP_PROFILE = 'r3-hold-ramp-v1'


def build_reference_position_controller(artifact, source, *, profile_id, dynamic_profile=None,
                                        force_limit_N=10.0, gripper_rate_hz=500,
                                        joint_velocity_limit_rad_s=2.0, execution=None,
                                        action_config=None, entity_id=None, hand_frame_id=None,
                                        tcp_profile=None, kinematics_model=None):
    """Construct the selected Panda position Controller from its bound source."""
    from ...runtime.sessions.source import UsdRuntimeSourceV1

    if isinstance(source, UsdRuntimeSourceV1):
        if profile_id not in R3_REFERENCE_POSITION_PROFILES or dynamic_profile is None:
            raise ValueError('USD Position requires the declared R3 Controller profile')
        from .position_profile import PandaPositionServoProfileV1
        return PandaPositionServoProfileV1.from_usd_source(
            artifact, source, execution=execution, kinematics_source_xml=source.scene_source.xml,
            config=action_config, pose_target_method='achieved_state_dls_v1',
            arm_tracking_method='production_r3_continuous_v1', arm_tracking_profile=dynamic_profile,
            arm_joint_velocity_limit_rad_s=joint_velocity_limit_rad_s,
            entity_id=entity_id, hand_frame_id=hand_frame_id, tcp_profile=tcp_profile)
    if profile_id == 'r1':
        from .production import ProductionCanonicalPandaController
        return ProductionCanonicalPandaController.from_source(artifact, source)
    if profile_id == 'r1_split':
        from .split_panda_position import SplitPandaPositionControllerV1
        return SplitPandaPositionControllerV1(artifact, source)
    if profile_id in R3_REFERENCE_POSITION_PROFILES:
        if dynamic_profile is None:
            raise ValueError('R3 Controller requires its declared dynamic profile')
        return ReferenceExecutionController.from_source(
            artifact, source, profile=dynamic_profile, force_limit_N=force_limit_N,
            gripper_rate_hz=gripper_rate_hz,
            joint_velocity_limit_rad_s=joint_velocity_limit_rad_s, model=kinematics_model)
    raise ValueError(f'unsupported reference Position Controller profile: {profile_id!r}')


def bind_reference_position_identity(controller, *, profile_id, construction_id):
    """Bind execution provenance and describe the selected Controller owners."""
    if profile_id in R3_REFERENCE_POSITION_PROFILES:
        base_identity = controller.hold.controller.identity
        execution_profile = controller.identity_profile()
        controller.bind_identity_provenance({
            'construction_id': construction_id,
            'base_controller_identity': base_identity,
            **execution_profile,
        })
        return {
            'base_controller_identity': base_identity,
            **execution_profile,
            'controller_identity': controller.identity,
            'controller_profile': profile_id,
            'resolved_controller_profile': controller.rate_profile_mapping(),
        }
    if profile_id == 'r1_split':
        return {'controller_profile': profile_id, 'controller_owners': (
            {'writer_id': controller.arm.writer_id, 'identity': controller.arm.identity},
            {'writer_id': controller.hand.writer_id, 'identity': controller.hand.identity},
        )}
    return {}


@dataclass(frozen=True)
class ArmTargetExecutionRequestV1:
    """Versioned task request consumed by the existing arm Controller owner."""

    schema_version: str
    profile_id: str
    mode: str

    def validate(self):
        if (self.schema_version != "arm-target-execution-request-v1"
                or self.profile_id != ARM_HOLD_RAMP_PROFILE):
            raise ValueError("unsupported arm target execution request")
        if self.mode not in {"track", "hold_last_applied", "ramp_from_last_applied"}:
            raise ValueError("unsupported arm target execution mode")

class StableArmTargetHold:
    """Own arm hold and ramp state for the R3 Controller."""
    def __init__(self, controller):
        self.controller = controller
        self.locked = False
        self.fixed = None
        self.last_target = None
        self.last_applied_arm = None
        self._request = ArmTargetExecutionRequestV1(
            "arm-target-execution-request-v1", ARM_HOLD_RAMP_PROFILE, "track",
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
            "arm-target-execution-request-v1", ARM_HOLD_RAMP_PROFILE, "track",
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
        # R3's merged implementation owns the persistent reference in its
        # arm-reference helper; earlier R3 layouts kept it on the controller.
        # The hold adapter snapshots/restores the state owner while leaving
        # the controller's outer step and gripper feedback lifecycle intact.
        reference_owner = getattr(self.controller, "_arm_reference", self.controller)
        joint_reference = getattr(reference_owner, "_joint_reference", None)
        if joint_reference is None:
            raise RuntimeError("R3 arm reference is unavailable for stable hold")
        prior = np.array(joint_reference, dtype=float, copy=True)
        canonical, target = self.controller.compute(state, feedback, requested)
        if self.locked:
            reference_owner._joint_reference = prior
            target = replace(target, arm_position=dict(self.fixed), arm_servo_position=dict(self.fixed))
            self.controller.last_arm_diagnostics.update(
                experimental_joint_target_hold=True,
                raw_integrated_target_not_applied=True,
                held_arm_target=dict(self.fixed), q_ref_next_rad=prior.tolist())
        else:
            self.controller.last_arm_diagnostics['experimental_joint_target_hold'] = False
        self.last_target = target
        return canonical, target


class ReferenceExecutionController:
    """Compose the shared R3 arm hold and gripper cadence owners."""

    @classmethod
    def from_source(cls, artifact, source, *, profile, force_limit_N,
                    gripper_rate_hz=500, joint_velocity_limit_rad_s=2.0, model=None):
        """Bind the declared source and compose the R3 execution owners."""
        from .production_r3 import ProductionCanonicalPandaControllerR3

        controller = ProductionCanonicalPandaControllerR3.from_source(
            artifact, source, profile=profile, model=model,
            joint_velocity_limit_rad_s=joint_velocity_limit_rad_s)
        controller.gripper_config = replace(controller.gripper_config, force_limit_N=force_limit_N)
        return cls(StableArmTargetHold(controller), artifact.timebase.control_dt,
                   gripper_rate_hz=gripper_rate_hz)

    def __init__(self, hold, control_dt, *, gripper_rate_hz=500):
        self.hold = hold
        if gripper_rate_hz == 500:
            self.inner = NativeRateGripperServo(hold.controller, 500, control_dt)
        elif gripper_rate_hz == 100:
            self.inner = EqualRateGripperServo(hold.controller, 100, control_dt)
        else:
            raise ValueError('R3 reference gripper cadence must be 100 or 500 Hz')
        self.gripper_rate_hz = int(gripper_rate_hz)

    def __getattr__(self, name):
        return getattr(self.hold, name)

    def identity_profile(self):
        """Describe the execution owners and cadence included in R3 identity."""
        import hashlib
        import inspect
        from pathlib import Path

        if self.gripper_rate_hz != 500:
            raise ValueError('R3 reference identity requires the native 500 Hz gripper')
        def source_hash(owner):
            return hashlib.sha256(Path(inspect.getsourcefile(owner)).read_bytes()).hexdigest()
        return {
            'arm_execution_profile': 'controller-owned-hold-and-linear-native-ramp-v1',
            'arm_execution_request_profile': ARM_HOLD_RAMP_PROFILE,
            'gripper_cadence': 'native-gripper-500hz-v1',
            'gripper_control_hz': 500, 'gripper_feedback_hz': 500,
            'outer_controller_hz': 100,
            'execution_support_sha256': {
                'arm_and_execution_wrapper': source_hash(type(self.hold)),
                'execution_controller': source_hash(type(self)),
                'gripper_servo': source_hash(type(self.inner)),
            },
        }

    def bind_identity_provenance(self, provenance):
        """Bind task-provided provenance to this execution's base Controller."""
        from .contracts import digest
        base = self.hold.controller
        if provenance.get('base_controller_identity') != base.identity:
            raise ValueError('execution provenance differs from its base Controller')
        base.identity = digest(provenance)
        return base.identity

    def reset(self, state, feedback):
        self.inner.reset()
        return self.hold.reset(state, feedback)

    def compute(self, *args):
        return self.hold.compute(*args)

    def inner_gripper_step(self, *args):
        return self.inner.inner_gripper_step(*args)

    def validate_arm_execution_request(self, request):
        return self.hold.validate_execution_request(request)

    def request_arm_execution(self, request):
        self.hold.request_execution(request)

    def begin(self, target):
        self.hold.begin(target)

    def target(self, target, index, count):
        return self.hold.target(target, index, count)

    def applied(self, acknowledgement):
        self.hold.applied(acknowledgement)


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
