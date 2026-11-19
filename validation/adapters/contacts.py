"""Decode recorded public rigid-contact scalars; no physics, files or verdicts.

Last-solve geometry/impulses retain their original clock and phase. Incomplete
observations never establish absence, current endpoint contact or load support.
"""
from collections import defaultdict
import math
import re


CONTACT_PATTERN = (
    r'solver[0-9]+\.contact\.(known|phase|available_time_s|geometry_time_s|episode|generation|sample_count|'
    r'sample\.[0-9]+\.(episode|generation|completed_substeps|geometry_substep|geometry_time_s|'
    r'capacity\.(count|capacity|required_count|required_count_exact|admitted|overflow|overflow_stage|'
    r'pair_index_overflow|truncated_candidate_count|stream_stopped|reservation_invariant_violation|max_contacts_per_pair)|'
    r'point_count|geometry_qpos\.[0-9]+|geometry_positions\.[0-9]+\.[012]|'
    r'geometry_orientations\.[0-9]+\.[0123]|'
    r'point\.[0-9]+\.(body\.[01]|geom\.[01]|distance|normal_impulse|position\.[012])))'
)
_CAPACITY = ('count', 'capacity', 'required_count', 'required_count_exact', 'admitted',
             'overflow', 'overflow_stage', 'pair_index_overflow', 'truncated_candidate_count',
             'stream_stopped', 'reservation_invariant_violation', 'max_contacts_per_pair')


class _MissingField(Exception):
    pass


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('contact measurement must be a finite number')
    return value


def _integer(value):
    value = _number(value)
    if value < 0 or value != int(value) or value > 2**53:
        raise ValueError('contact ordinal/index must be a nonnegative exact integer')
    return int(value)


def _get(fields, key):
    if key not in fields:
        raise _MissingField(key)
    return fields[key]


def _same(a, b):
    return math.isclose(a, b, abs_tol=1e-8, rel_tol=0)


def _source(source):
    names = source.get('body_names')
    if (not isinstance(source.get('owner'), str) or not source['owner']
            or not isinstance(names, list) or not names
            or any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names)
            or source.get('body_indices') != {n: i for i, n in enumerate(names)}
            or _number(source.get('substep_dt')) <= 0
            or not 1 <= _integer(source.get('history_capacity')) <= 1024):
        raise ValueError('contact source needs an unambiguous recorded body map and clock')
    return names


def _sample(fields, prefix, source, names):
    def get(key):
        return _get(fields, prefix + key)
    sample = {key: _integer(get(key)) for key in
              ('episode', 'generation', 'completed_substeps', 'geometry_substep')}
    geometry_time = _number(get('geometry_time_s'))
    if (sample['completed_substeps'] < 1 or sample['generation'] < 1
            or sample['geometry_substep'] != sample['completed_substeps'] - 1
            or not _same(geometry_time, sample['geometry_substep'] * source['substep_dt'])):
        raise ValueError('contact geometry phase/substep clock mismatch')
    sample.update(geometry_time_s=geometry_time, phase='pre_qpos_integration', impulses_known=True)
    capacity = {key: _integer(get('capacity.' + key)) for key in _CAPACITY}
    count = _integer(get('point_count'))
    sample['capacity'] = capacity
    if (capacity['admitted'] != 1 or capacity['required_count_exact'] != 1
            or any(capacity[k] != 0 for k in _CAPACITY[5:11])
            or capacity['count'] > capacity['capacity']
            or capacity['required_count'] < capacity['count'] or capacity['max_contacts_per_pair'] < 1):
        return {**sample, 'known': False, 'reason': 'contact_capacity_incomplete', 'points': []}
    if count > capacity['count'] * capacity['max_contacts_per_pair'] or count > 200000:
        raise ValueError('contact point count exceeds recorded capacity')
    indices = {int(m.group(1)) for key in fields
               if (m := re.fullmatch(re.escape(prefix) + r'point\.([0-9]+)\..+', key))}
    if indices - set(range(count)):
        raise ValueError('contact point index exceeds declared point count')
    points = []
    for i in range(count):
        base = f'point.{i}.'
        bodies = [_integer(get(base + f'body.{side}')) for side in (0, 1)]
        if bodies[0] == bodies[1] or any(b >= len(names) for b in bodies):
            raise ValueError('contact body index outside the recorded source map')
        distance = _number(get(base + 'distance'))
        points.append({'bodies': [names[b] for b in bodies], 'body_indices': bodies,
            'geoms': [_integer(get(base + f'geom.{side}')) for side in (0, 1)],
            'distance_m': distance, 'touching': distance <= 0,
            'normal_impulse': _number(get(base + 'normal_impulse')),
            'position_world_m': [_number(get(base + f'position.{axis}')) for axis in range(3)]})
    # Preserve the geometry at manifold generation, separately from integrated states.
    geometry = {}
    for field, width in (('geometry_positions', 3), ('geometry_orientations', 4)):
        if any(key.startswith(prefix + field + '.') for key in fields):
            expected = {f'{prefix}{field}.{body}.{axis}' for body in range(len(names)) for axis in range(width)}
            if {key for key in fields if key.startswith(prefix + field + '.')} - expected:
                raise ValueError('contact geometry index outside the recorded body map')
            geometry[field] = [[_number(get(f'{field}.{body}.{axis}')) for axis in range(width)]
                               for body in range(len(names))]
    qpos = {int(key.rsplit('.', 1)[1]): value for key, value in fields.items()
            if key.startswith(prefix + 'geometry_qpos.')}
    if qpos:
        if set(qpos) != set(range(len(qpos))):
            raise _MissingField('geometry_qpos channels')
        geometry['geometry_qpos'] = [qpos[i] for i in range(len(qpos))]
    return {**sample, **geometry, 'known': True, 'reason': None, 'points': points}


def decode_contact_records(rows, sources, runtime, start_time, end_time):
    """Normalize whitelisted public records; invalid inputs raise ValueError.

    Missing/disabled/overflowed observations are evidence gaps, not parse errors
    or zero contact. Coverage refers to recorded observations, not continuous
    physical-time coverage. No impulses are converted into invented forces.
    """
    if not isinstance(sources, dict) or not isinstance(rows, list):
        raise ValueError('recorded contacts require a row list and frozen source map')
    groups, stamps = defaultdict(dict), {}
    for row in rows:
        name, step = row.get('name'), row.get('step')
        if (type(step) is not int or step < 0 or not isinstance(name, str)
                or re.fullmatch(CONTACT_PATTERN, name) is None):
            raise ValueError('malformed recorded contact channel')
        time, value = _number(row.get('t')), _number(row.get('value'))
        if (not start_time - 1e-9 <= time <= end_time + 1e-9
                or not _same(time, runtime['start_time'] + (step-runtime['start_step'])*runtime['dt'])):
            raise ValueError('recorded contact step/time/scope mismatch')
        solver, _, field = name.split('.', 2)
        key = solver[6:]
        if key not in sources:
            raise ValueError('recorded contacts lack their frozen source/body map')
        if field in groups[key, step] or (step in stamps and not _same(stamps[step], time)):
            raise ValueError('duplicate contact channel or inconsistent clock')
        groups[key, step][field], stamps[step] = value, time
    cadence = runtime.get('sample_dt')
    if cadence is None:
        steps = sorted(stamps)
    else:
        if _number(cadence) <= 0:
            raise ValueError('contact recording cadence must be positive')
        intervals = (end_time-start_time)/cadence
        if not _same(intervals, round(intervals)) or not 0 <= intervals <= 20000:
            raise ValueError('contact scope is not on the recorded sample grid')
        steps = []
        for i in range(round(intervals)+1):
            step = runtime['start_step'] + (start_time+i*cadence-runtime['start_time'])/runtime['dt']
            if not _same(step, round(step)):
                raise ValueError('contact sample is not on the physical step grid')
            steps.append(round(step))
        if set(stamps) - set(steps):
            raise ValueError('contact observations differ from recorded cadence')
    records = []
    reasons = set()
    if cadence is None:
        reasons.add('recorded_contact_cadence_unknown')
    for key, source in sources.items():
        if not isinstance(key, str) or re.fullmatch(r'[0-9]+', key) is None:
            raise ValueError('contact source has invalid solver identity')
        names = _source(source)
        for step in steps:
            fields = groups.get((key, step), {})
            time = runtime['start_time'] + (step-runtime['start_step'])*runtime['dt']
            record = {'source_id': 'solver'+key, 'owner': source['owner'],
                      'record_step': step, 'record_time_s': time, 'known': False, 'samples': []}
            try:
                known = _integer(_get(fields, 'known'))
                if known not in (0, 1):
                    raise ValueError('contact known flag must be zero or one')
                if not known:
                    record['reason'] = 'contact_observation_unavailable'
                elif (source.get('phase') != 'pre_qpos_integration'
                      or source.get('phase_code') != 1 or _get(fields, 'phase') != 1):
                    record['reason'] = 'unsupported_recorded_contact_phase'
                else:
                    episode, generation, count = (_integer(_get(fields, k)) for k in
                                                   ('episode', 'generation', 'sample_count'))
                    if count != source['history_capacity']:
                        raise _MissingField('complete native substep history')
                    observed_indices = {int(m.group(1)) for field in fields
                                        if (m := re.match(r'sample\.([0-9]+)\.', field))}
                    if observed_indices - set(range(count)):
                        raise ValueError('contact history index exceeds sample count')
                    samples = [_sample(fields, f'sample.{i}.', source, names) for i in range(count)]
                    for i, sample in enumerate(samples):
                        if (sample['episode'] != episode
                                or sample['generation'] != generation-count+i+1
                                or (i and sample['completed_substeps'] != samples[i-1]['completed_substeps']+1)):
                            raise ValueError('contact history episode/generation/substep mismatch')
                    if (not _same(_get(fields, 'available_time_s'), time)
                            or not _same(samples[-1]['completed_substeps'] * source['substep_dt'], time)
                            or not _same(_get(fields, 'geometry_time_s'), samples[-1]['geometry_time_s'])):
                        raise ValueError('contact availability and geometry clocks disagree')
                    record.update(episode=episode, generation=generation, samples=samples,
                                  known=all(s['known'] for s in samples))
                    record['reason'] = None if record['known'] else 'contact_capacity_incomplete'
            except _MissingField as error:
                record['reason'] = 'contact_fields_missing:' + str(error)
            if not record['known']:
                reasons.add(record['reason'])
            records.append(record)
    usable = sum(s['known'] for r in records for s in r['samples'])
    complete = bool(records) and all(r['known'] for r in records) and cadence is not None
    if not rows:
        reasons.add('contact_channels_not_recorded')
    status = 'available' if complete else 'partial' if usable else 'unavailable'
    return {'schema_version': 'recorded-native-contacts/0.1', 'status': status,
        'recorded_grid_complete': complete, 'usable_sample_count': usable,
        'measurement_row_count': len(rows), 'expected_record_steps': steps,
        'scope': {'record_start_time_s': start_time, 'record_end_time_s': end_time},
        'sources': sources, 'records': records, 'reasons': sorted(reasons),
        'units': {'distance': 'm', 'position': 'world m', 'normal_impulse': 'N s'},
        'current_endpoint_geometry_proven': False, 'continuous_contact_coverage_proven': False,
        'actual_support': None, 'robot_release': None, 'task_success': None}
