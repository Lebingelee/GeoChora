"""Additive control readback; canonical-state-v0 and task identity stay unchanged."""
from dataclasses import dataclass
import math
from ...artifacts.contracts import Contract, _name
from ...environment.types import ActuatorForceMeasurementV1


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
        if measurement.force_unit != 'N' or measurement.actuator_id != 'actuator8':
            raise ValueError('selected NutAssembly native Guard requires the Panda actuator8 sample in N')
        expected_force = max(0.0, -float(measurement.signed_force_N))
        if feedback.gripper.closing_force_N != expected_force:
            raise ValueError('canonical feedback differs from the measured signed actuator force')
        dt = 0.002
        native_index = measurement.native_step_index
        sample_time = measurement.native_sample_time_s
        evaluation_time = feedback.simulation_time
        if sample_time is None or not math.isfinite(sample_time):
            raise ValueError('native force sample must carry its measurement time')
        if measurement.phase == 'reset_forward':
            if native_index != 0 or sample_time != 0.0 or abs(evaluation_time) > 1e-10:
                raise ValueError('reset-forward feedback must identify the exact reset state at t=0')
        elif measurement.phase == 'native_step_pre_integration':
            if (native_index < 1
                    or not math.isclose(sample_time, (native_index - 1) * dt, rel_tol=0.0, abs_tol=1e-10)
                    or not math.isclose(evaluation_time, native_index * dt, rel_tol=0.0, abs_tol=1e-10)
                    or not math.isclose(evaluation_time - sample_time, dt, rel_tol=0.0, abs_tol=1e-10)):
                raise ValueError('native feedback sample phase/time/freshness is not one completed 2 ms step')
        else:
            raise ValueError('native Guard does not admit this force sample phase')
        if measurement.evaluation_control_step != native_index // 5:
            raise ValueError('native feedback sample outer control step differs from its native index')

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
