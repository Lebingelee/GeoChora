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
    if value['recipe'].get('clock_contract') != SCHEMA:
        raise ValueError('clock contract version required')
    tb=value['metadata']['timebase'];dt=tb['physics_dt'];sub=tb['control_substeps']
    if type(sub) is not int or sub <= 0 or tb['control_dt'] != dt*sub:
        raise ValueError('clock timebase identity')
    previous=-1.
    for k,b in enumerate(value['boundaries']):
        n=b['native_step_index']
        if type(n) is not int or n != k*sub or type(b['record']['control_step']) is not int:
            raise ValueError('integer boundary clock index')
        _check(b['native_time'],n,dt)
        # Public control time may be accumulated native time or k*control_dt.
        # One extra projection ULP accounts for the alternate multiplication.
        t=b['record']['simulation_time'];limit=accumulated_bound(n,dt)+math.ulp(k*tb['control_dt'])
        if not math.isfinite(t) or abs(t-n*dt)>limit or t<previous:
            raise ValueError('public boundary clock bound/order')
        previous=t
    for k,t in enumerate(value['transitions']):
        interval=t['interval']
        audit=t['native_audit']
        if type(audit['observed_native_substeps']) is not int or type(audit['control_step']) is not int:
            raise ValueError('integer audited count/boundary required')
        if type(interval['native_step_count']) is not int or interval['native_step_count'] != sub:
            raise ValueError('integer interval count')
        for j,s in enumerate(interval['substeps']):
            n=s['native_step_index']
            if type(n) is not int or n != k*sub+j+1:
                raise ValueError('integer native application ordering')
            _check(s['native_start_time'],n-1,dt)
    return value
