"""Semantic control readiness, separate from task metrics and canonical state v0."""
from dataclasses import dataclass
from ...artifacts.contracts import Contract, _name


@dataclass(frozen=True)
class GripperReadiness(Contract):
    semantic_id: str
    close_ready: bool
    closing_force_N: float
    force_limit_N: float
    force_error_N: float

    def validate(self):
        _name(self.semantic_id)
        if self.closing_force_N < 0 or self.force_limit_N <= 0:
            raise ValueError('invalid physical closing force')
        if self.force_error_N != self.force_limit_N - self.closing_force_N:
            raise ValueError('inconsistent force error')


@dataclass(frozen=True)
class CanonicalControlReadiness(Contract):
    schema_version: str
    control_step: int
    simulation_time: float
    gripper: GripperReadiness

    def validate(self):
        if self.schema_version != 'canonical-control-readiness-v1':
            raise ValueError('unsupported readiness schema')
        if self.control_step < 0 or self.simulation_time < 0:
            raise ValueError('invalid readiness boundary')

    def require_boundary(self, step, time):
        if self.control_step != step or self.simulation_time != time:
            raise ValueError('stale control readiness boundary')
