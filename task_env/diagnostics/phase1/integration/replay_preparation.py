"""Opt-in preparation codecs, not a public schema or qualification runner.

Only canonical Python owner memory is accessed. No native state is captured.
Frozen owners are unchanged; source hashes bind this experimental restore ABI.
"""
import hashlib
import inspect
import json
import math
from pathlib import Path

import numpy as np

from ....controllers.canonical.contracts import CanonicalControlTarget, AppliedCanonicalControl, digest
from ....controllers.canonical.execution import BoundaryWait


FIELDS = {
    'arm_gripper': ('_joint_reference', '_previous_reference', '_previous_reference_step',
        '_expected_step', '_q_ref_reset_events', '_lead_clamp_events',
        '_joint_velocity_clip_events', '_reference_reset_event_pending',
        'last_arm_diagnostics', '_desired', '_commanded', '_force_mode', '_force_initialized'),
    'arm_hold': ('locked', 'fixed', 'last_target'),
    'stability': ('start', 'history'),
    'cadence': ('_last_control_step', '_last_target', '_last_diagnostics', 'update_count', 'held_count'),
    'coordinator': ('events', '_pose_wait_start', '_postclose_hold_ticks', '_lift_released',
        '_done', '_failed', '_failure_reason', '_stage_index', '_emitted', '_last_opening',
        '_opening_history', '_goal', '_index', '_hold_ticks', '_stable_ticks', '_actions',
        '_grasp_pose', '_captured_position', '_captured_rotation', '_close_gate'),
}


def _encode(x):
    if isinstance(x, np.ndarray):
        return {'kind': 'array', 'dtype': x.dtype.str, 'shape': list(x.shape), 'values': x.tolist()}
    if isinstance(x, tuple):
        return {'kind': 'tuple', 'values': [_encode(v) for v in x]}
    if isinstance(x, (CanonicalControlTarget,)):
        return {'kind': 'control_target', 'values': x.to_mapping()}
    # Gripper-only cadence target has a different contract.
    from ....controllers.canonical.contracts import GripperControlTarget
    if isinstance(x, GripperControlTarget):
        return {'kind': 'gripper_target', 'values': x.to_mapping()}
    if isinstance(x, BoundaryWait):
        return {'kind': 'wait', 'start_s': x.start_s, 'deadline_s': x.deadline_s}
    if isinstance(x, list):
        return [_encode(v) for v in x]
    if isinstance(x, dict):
        if 'kind' in x:
            raise ValueError('reserved codec key')
        return {k: _encode(v) for k, v in x.items()}
    if x is None or type(x) in (bool, int, float, str):
        return x
    raise TypeError('unsupported canonical owner memory: ' + type(x).__name__)


def _decode(x):
    if isinstance(x, list):
        return [_decode(v) for v in x]
    if not isinstance(x, dict):
        return x
    kind = x.get('kind')
    if kind == 'array':
        a = np.asarray(x['values'], dtype=x['dtype'])
        if list(a.shape) != x['shape'] or not np.isfinite(a).all():
            raise ValueError('invalid array')
        return a
    if kind == 'tuple':
        return tuple(_decode(v) for v in x['values'])
    if kind == 'control_target':
        return CanonicalControlTarget.from_mapping(x['values'])
    if kind == 'gripper_target':
        from ....controllers.canonical.contracts import GripperControlTarget
        return GripperControlTarget.from_mapping(x['values'])
    if kind == 'wait':
        return BoundaryWait(x['start_s'], x['deadline_s'])
    if kind is not None:
        raise ValueError('unsupported codec tag')
    return {k: _decode(v) for k, v in x.items()}


def _owners(value):
    c = value['controller']
    return {'arm_gripper': c.hold.controller, 'arm_hold': c.hold,
            'stability': value['solution']._stability, 'cadence': c.inner,
            'coordinator': value['solution']}


def _source(owner):
    return hashlib.sha256(Path(inspect.getfile(type(owner))).read_bytes()).hexdigest()


def snapshot(value, state, provider):
    """At completed boundaries, after coordinator.observe; never during substeps."""
    if value['controller']._expected_step != state.control_step:
        raise ValueError('snapshot must align with next compute boundary')
    owners = {}
    for name, owner in _owners(value).items():
        owners[name] = {'version': name + '-memory-prototype-v1', 'source_sha256': _source(owner),
            'fields': {k: {'present': k in vars(owner), 'value': _encode(vars(owner).get(k))}
                       for k in FIELDS[name]}}
    result = {'version': 'p18-owner-checkpoint-prototype-v1',
        'controller_identity': value['controller_identity'], 'solution_identity': value['solution_identity'],
        'artifact_hash': value['artifact'].identity_hash, 'provider': provider,
        'control_step': state.control_step, 'simulation_time': state.simulation_time,
        'timebase': value['artifact'].timebase.to_mapping(), 'owners': owners}
    result['integrity_hash'] = digest(result)
    return result


def restore(value, state, provider, record):
    """Validate complete record before mutating fresh same-config owners."""
    record = json.loads(json.dumps(record, allow_nan=False))
    integrity = record.pop('integrity_hash')
    if digest(record) != integrity:
        raise ValueError('checkpoint integrity mismatch')
    expected = snapshot(value, state, provider)
    for k in ('version', 'controller_identity', 'solution_identity', 'artifact_hash', 'provider',
              'control_step', 'simulation_time', 'timebase'):
        if record[k] != expected[k]:
            raise ValueError('checkpoint identity/alignment mismatch: ' + k)
    if set(record['owners']) != set(FIELDS):
        raise ValueError('missing owner history')
    decoded = {}
    for name, owner in _owners(value).items():
        payload = record['owners'][name]
        if payload['version'] != name + '-memory-prototype-v1' or payload['source_sha256'] != _source(owner):
            raise ValueError('owner version/source mismatch')
        if set(payload['fields']) != set(FIELDS[name]):
            raise ValueError('incomplete owner fields: ' + name)
        decoded[name] = {k: (v['present'], _decode(v['value'])) for k, v in payload['fields'].items()}
    arm = decoded['arm_gripper']
    if arm['_expected_step'][1] != state.control_step or not arm['_joint_reference'][0]:
        raise ValueError('missing/alignment-invalid controller history')
    for name, owner in _owners(value).items():
        for k, (present, val) in decoded[name].items():
            if present:
                setattr(owner, k, val)
            elif k in vars(owner):
                delattr(owner, k)
    value['solution']._pose_history = value['solution']._stability.history
    # Existing bound method remains bound to the fresh controller; never serialized.


def interval_record(targets, acknowledgments, updates, *, step, physics_dt, substeps, provider):
    r = {'version': 'p18-control-interval-prototype-v1', 'control_step': step,
         'physics_dt': physics_dt, 'control_substeps': substeps, 'provider': provider,
         'native_step_count': len(targets), 'updates': list(updates),
         'targets': [t.to_mapping() for t in targets],
         'target_hashes': [t.identity_hash for t in targets],
         'acknowledgments': [a.to_mapping() for a in acknowledgments],
         'canonical_start_time': step * physics_dt * substeps}
    decode_interval(r, physics_dt=physics_dt, substeps=substeps, provider=provider)
    return r


def decode_interval(r, *, physics_dt, substeps, provider):
    if r['version'] != 'p18-control-interval-prototype-v1' or r['provider'] != provider:
        raise ValueError('interval version/provider mismatch')
    if r['physics_dt'] != physics_dt or r['control_substeps'] != substeps:
        raise ValueError('interval timebase mismatch')
    if r['native_step_count'] != substeps or any(len(r[k]) != substeps for k in
          ('targets', 'acknowledgments', 'target_hashes', 'updates')):
        raise ValueError('missing/duplicate native substep')
    if r['updates'] != [True] + [False] * (substeps - 1):
        raise ValueError('equal-rate update schedule mismatch')
    targets = [CanonicalControlTarget.from_mapping(t) for t in r['targets']]
    for i, t in enumerate(targets):
        a = AppliedCanonicalControl.from_mapping(r['acknowledgments'][i])
        if t.identity_hash != r['target_hashes'][i] or a.target_hash != t.identity_hash:
            raise ValueError('corrupted target identity')
        # Acknowledgment is realized control, not necessarily bitwise requested
        # control (e.g. an existing adapter's float32 actuator storage). Preserve
        # it independently. Identity binds the request; do not invent a tolerance
        # or overwrite either representation to make them compare equal.
        if a.provider_name != provider or set(a.arm_servo_position) != set(t.arm_servo_position):
            raise ValueError('applied provider/binding mismatch')
        if a.gripper_force_limit_N != t.gripper.force_limit_N:
            raise ValueError('applied force cap mismatch')
        if t.arm_position != targets[0].arm_position or t.arm_servo_position != targets[0].arm_servo_position:
            raise ValueError('arm ZOH mismatch')
        if i and t.to_mapping() != targets[0].to_mapping():
            raise ValueError('equal-rate gripper target was not held')
    return targets


def clock_bound(native_steps, physics_dt):
    """Higham gamma_n bound for n positive binary64 additions, plus projection ULP."""
    nu = native_steps * 2.**-53
    if native_steps < 0 or nu >= 1:
        raise ValueError('unsupported step count')
    projected = native_steps * physics_dt
    return nu / (1 - nu) * abs(projected) + math.ulp(projected)
