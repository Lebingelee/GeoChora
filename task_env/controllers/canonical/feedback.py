"""Additive control readback; canonical-state-v0 and task identity stay unchanged."""
from dataclasses import dataclass
from ...artifacts.contracts import Contract, _name


@dataclass(frozen=True)
class CanonicalGripperFeedback(Contract):
    semantic_id: str
    opening_m: float
    closing_force_N: float

    def validate(self):
        _name(self.semantic_id)
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
class CanonicalGripperMemory(Contract):
    desired_opening_m: float
    commanded_opening_m: float
    force_limit_N: float
    force_mode_active: bool
    force_mode_initialized: bool
