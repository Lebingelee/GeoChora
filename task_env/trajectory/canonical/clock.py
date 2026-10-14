"""Explicit binary64 accumulated-native-clock contract; v0 remains unchanged."""
import math

SCHEMA = 'canonical-integer-native-clock-v1'


def accumulated_bound(n, dt):
    if type(n) is not int or n < 0 or not math.isfinite(dt) or dt <= 0:
        raise ValueError('invalid native clock operands')
    nu = n * 2.**-53
    if nu >= 1:
        raise ValueError('unsupported binary64 accumulation length')
    projected = n * dt
    return nu / (1 - nu) * abs(projected) + math.ulp(projected)


def _check(raw, n, dt):
    if type(raw) not in (float, int) or not math.isfinite(raw):
        raise ValueError('nonfinite native clock')
    if abs(raw-n*dt) > accumulated_bound(n, dt):
        raise ValueError('native clock exceeds derived accumulation bound')


def validate_clock(value):
    validator = ClockStreamValidator(value['metadata'], value['recipe'])
    for k,b in enumerate(value['boundaries']):
        validator.boundary(k, b)
    for k,t in enumerate(value['transitions']):
        validator.transition(k, t)
    return value


class ClockStreamValidator:
    """Incremental equivalent of validate_clock for one-record-at-a-time audits."""
    def __init__(self, metadata, recipe):
        if recipe.get('clock_contract') != SCHEMA:
            raise ValueError('clock contract version required')
        tb = metadata['timebase']
        self.dt = tb['physics_dt']
        self.substeps = tb['control_substeps']
        self.control_dt = tb['control_dt']
        if type(self.substeps) is not int or self.substeps <= 0 or self.control_dt != self.dt*self.substeps:
            raise ValueError('clock timebase identity')
        self.previous = -1.

    def boundary(self, index, boundary):
        n = boundary['native_step_index']
        if type(n) is not int or n != index*self.substeps or type(boundary['record']['control_step']) is not int:
            raise ValueError('integer boundary clock index')
        _check(boundary['native_time'], n, self.dt)
        # Public time may use accumulated native time or k*control_dt.
        limit = accumulated_bound(n, self.dt) + math.ulp(index*self.control_dt)
        t = boundary['record']['simulation_time']
        if not math.isfinite(t) or abs(t-n*self.dt) > limit or t < self.previous:
            raise ValueError('public boundary clock bound/order')
        self.previous = t

    def transition(self, index, transition):
        interval = transition['interval']
        audit = transition['native_audit']
        if type(audit['observed_native_substeps']) is not int or type(audit['control_step']) is not int:
            raise ValueError('integer audited count/boundary required')
        if type(interval['native_step_count']) is not int or interval['native_step_count'] != self.substeps:
            raise ValueError('integer interval count')
        for j, substep in enumerate(interval['substeps']):
            n = substep['native_step_index']
            if type(n) is not int or n != index*self.substeps+j+1:
                raise ValueError('integer native application ordering')
            _check(substep['native_start_time'], n-1, self.dt)
