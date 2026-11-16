"""Additive control readback; canonical-state-v0 and task identity stay unchanged."""
from dataclasses import dataclass
import math
from ...artifacts.contracts import Contract, _name
from ...environment.types import ActuatorForceMeasurementV1


def boundary_interval_clock_tolerance(start_time_s, end_time_s, expected_dt_s,
                                      physics_dt_s, native_steps):
    """Bound binary clock drift from native increments and boundary subtraction."""
    clock_ulp = max(
        math.ulp(float(start_time_s)), math.ulp(float(end_time_s)),
        math.ulp(float(expected_dt_s)), math.ulp(float(physics_dt_s)),
    )
    return (int(native_steps) + 2) * clock_ulp


def selected_control_application_receipt(*, request, canonical, target, applied,
                                         request_boundary, read_evaluation_boundary,
                                         artifact, controller_identity,
                                         provider, source_id, reset_sample_id):
    """Validate and project one applied control over a completed selected interval."""
    if target.identity_hash != applied.target_hash:
        raise ValueError('applied acknowledgement does not match the computed target')
    if target.task_artifact_hash != artifact.identity_hash:
        raise ValueError('applied target belongs to another TaskArtifact')
    if target.controller_identity != controller_identity:
        raise ValueError('applied target belongs to another Controller')
    if applied.provider_name != provider:
        raise ValueError('applied acknowledgement belongs to another Provider')
    current_step, evaluation_boundary = read_evaluation_boundary()
    if request_boundary is None:
        raise ValueError('control application acknowledgement requires its source boundary')
    receipt = {
        'schema_version': 'selected-control-application-v1',
        'task_artifact_hash': artifact.identity_hash,
        'source_id': source_id,
        'controller_identity': controller_identity,
        'reset_sample_id': reset_sample_id,
        'request_boundary': dict(request_boundary),
        'evaluation_boundary': evaluation_boundary,
        'requested_action': request.to_mapping(),
        'canonical_action': canonical.to_mapping(),
        'target': target.to_mapping(),
        'target_identity_hash': target.identity_hash,
        'applied': applied.to_mapping(),
        'applied_target_hash': applied.target_hash,
    }
    if (receipt['request_boundary']['control_step'] + 1 != current_step
            or receipt['evaluation_boundary']['control_step'] != current_step):
        raise ValueError('control acknowledgement does not span exactly one completed boundary')
    expected_dt = artifact.timebase.control_dt
    actual_dt = (receipt['evaluation_boundary']['simulation_time_s']
                 - receipt['request_boundary']['simulation_time_s'])
    tolerance = boundary_interval_clock_tolerance(
        receipt['request_boundary']['simulation_time_s'],
        receipt['evaluation_boundary']['simulation_time_s'],
        expected_dt, artifact.timebase.physics_dt, artifact.timebase.control_substeps,
    )
    if abs(actual_dt - expected_dt) > tolerance:
        raise ValueError('control acknowledgement does not match the selected control timebase')
    return receipt


def validate_native_interval_boundaries(before, after, *, episode_id, reset_sample_id,
                                        provider_materialization_id, interval_s, tolerance_s=1e-10):
    """Check the identity and measured clock of one completed native interval."""
    if (before.get('control_step', -2) + 1 != after.get('control_step', -1)
            or before.get('episode_id') != episode_id or after.get('episode_id') != episode_id
            or before.get('reset_sample_id') != reset_sample_id
            or after.get('reset_sample_id') != reset_sample_id
            or before.get('provider_materialization_id') != provider_materialization_id
            or after.get('provider_materialization_id') != provider_materialization_id
            or not before.get('identity_hash') or not after.get('identity_hash')):
        raise ValueError('native interval boundary identity or reset lineage changed')
    start_time = float(before['simulation_time_s'])
    end_time = float(after['simulation_time_s'])
    if (not math.isfinite(start_time) or not math.isfinite(end_time)
            or not math.isfinite(interval_s) or interval_s <= 0
            or abs((end_time - start_time) - interval_s) > tolerance_s):
        raise ValueError('native interval did not complete the declared control interval')
    return start_time, end_time


@dataclass(frozen=True)
class CanonicalGripperFeedback(Contract):
    semantic_id: str
    opening_m: float
    closing_force_N: float

    def validate(self):
        _name(self.semantic_id)
        if not math.isfinite(self.opening_m) or not math.isfinite(self.closing_force_N):
            raise ValueError('control feedback values must be finite')
        if self.opening_m < 0 or self.closing_force_N < 0:
            raise ValueError('nonnegative physical opening/closing-force magnitude required')


@dataclass(frozen=True)
class CanonicalControlFeedback(Contract):
    schema_version: str
    control_step: int
    simulation_time: float
    gripper: CanonicalGripperFeedback

    def validate(self):
        if self.schema_version != 'canonical-control-feedback-v0':
            raise ValueError('unsupported feedback schema')
        if not math.isfinite(self.simulation_time):
            raise ValueError('feedback simulation time must be finite')
        if self.control_step < 0 or self.simulation_time < 0:
            raise ValueError('invalid feedback boundary')

    def require_state(self, state, semantic_id, finger_names):
        if (self.control_step != state.control_step or self.simulation_time != state.simulation_time
                or self.gripper.semantic_id != semantic_id):
            raise ValueError('control feedback must match canonical state boundary/binding')
        opening = max(0., sum(state.joint_position[n] for n in finger_names))
        if self.gripper.opening_m != opening:
            raise ValueError('feedback opening differs from measured canonical joints')


@dataclass(frozen=True)
class NativeControlFeedbackSampleV1(Contract):
    """The exact native force sample projected into canonical Controller feedback.

    ``feedback`` remains the Controller input. This wrapper adds the Provider
    sample provenance needed by native-rate task Guards; it is not a second
    feedback store or a second force conversion path.
    """

    schema_version: str
    provider_name: str
    provider_materialization_id: str
    source_id: str
    source_closure_digest: str | None
    episode_id: str
    reset_sample_id: str
    feedback: CanonicalControlFeedback
    actuator_force_measurement: ActuatorForceMeasurementV1

    def __post_init__(self):
        # ActuatorForceMeasurementV1 is an environment/runtime receipt, not an
        # artifacts.Contract. Keep this wrapper's boundary explicit instead
        # of sending that typed object through the generic artifact codec.
        if not isinstance(self.feedback, CanonicalControlFeedback):
            raise TypeError('native feedback sample requires CanonicalControlFeedback')
        if not isinstance(self.actuator_force_measurement, ActuatorForceMeasurementV1):
            raise TypeError('native feedback sample requires ActuatorForceMeasurementV1')
        self.validate()

    def validate(self):
        if self.schema_version != 'native-control-feedback-sample-v1':
            raise ValueError('unsupported native Controller feedback sample')
        for name in ('provider_name', 'provider_materialization_id', 'source_id',
                     'episode_id', 'reset_sample_id'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f'native Controller feedback sample requires {name}')
        if self.source_closure_digest is not None and (
                len(self.source_closure_digest) != 64
                or any(c not in '0123456789abcdef' for c in self.source_closure_digest)):
            raise ValueError('native feedback source closure must be a SHA-256')
        if not isinstance(self.feedback, CanonicalControlFeedback):
            raise TypeError('native feedback sample requires CanonicalControlFeedback')
        if not isinstance(self.actuator_force_measurement, ActuatorForceMeasurementV1):
            raise TypeError('native feedback sample requires ActuatorForceMeasurementV1')
        feedback = self.feedback
        measurement = self.actuator_force_measurement
        feedback.validate()
        if (not measurement.valid or measurement.signed_force_N is None
                or measurement.actuator_ctrl is None or measurement.actuator_id is None
                or measurement.episode_id != self.episode_id
                or measurement.reset_sample_id != self.reset_sample_id
                or measurement.evaluation_control_step != feedback.control_step
                or measurement.evaluation_simulation_time_s != feedback.simulation_time):
            raise ValueError('native force measurement is invalid or belongs to another feedback boundary')
        if measurement.force_unit != 'N':
            raise ValueError('native Controller force sample must be measured in N')
        expected_force = max(0.0, -float(measurement.signed_force_N))
        if feedback.gripper.closing_force_N != expected_force:
            raise ValueError('canonical feedback differs from the measured signed actuator force')
        sample_time = measurement.native_sample_time_s
        if sample_time is None or not math.isfinite(sample_time):
            raise ValueError('native force sample must carry its measurement time')
        if measurement.phase == 'reset_forward':
            if (measurement.native_step_index != 0 or sample_time != 0.0
                    or abs(feedback.simulation_time) > 1e-10):
                raise ValueError('reset-forward feedback must identify the exact reset state')
        elif measurement.phase == 'native_step_pre_integration':
            if measurement.native_step_index < 1 or sample_time >= feedback.simulation_time:
                raise ValueError('native force sample must precede its completed feedback boundary')
        else:
            raise ValueError('native feedback does not admit this force sample phase')

    def to_mapping(self):
        self.validate()
        from dataclasses import asdict
        return {
            'schema_version': self.schema_version,
            'provider_name': self.provider_name,
            'provider_materialization_id': self.provider_materialization_id,
            'source_id': self.source_id,
            'source_closure_digest': self.source_closure_digest,
            'episode_id': self.episode_id,
            'reset_sample_id': self.reset_sample_id,
            'feedback': self.feedback.to_mapping(),
            'actuator_force_measurement': asdict(self.actuator_force_measurement),
        }

    @classmethod
    def from_mapping(cls, value):
        feedback_value = value['feedback']
        gripper_value = feedback_value['gripper']
        feedback = CanonicalControlFeedback(
            feedback_value['schema_version'], feedback_value['control_step'],
            feedback_value['simulation_time'], CanonicalGripperFeedback(
                gripper_value['semantic_id'], gripper_value['opening_m'],
                gripper_value['closing_force_N']),
        )
        return cls(
            value['schema_version'], value['provider_name'],
            value['provider_materialization_id'], value['source_id'],
            value.get('source_closure_digest'), value['episode_id'],
            value['reset_sample_id'], feedback,
            ActuatorForceMeasurementV1(**value['actuator_force_measurement']),
        )


@dataclass(frozen=True)
class CanonicalGripperMemory(Contract):
    desired_opening_m: float
    commanded_opening_m: float
    force_limit_N: float
    force_mode_active: bool
    force_mode_initialized: bool
