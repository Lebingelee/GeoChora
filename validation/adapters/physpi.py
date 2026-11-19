"""Capture a source-bound terminal snapshot through PhysPi's public query API.

Run PhysPi normally first. Pass its returned manifest path and the Python
environment containing physpi_runtime. This adapter never steps physics, opens
private solver state, interprets phase strings, or assigns task success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

from validation.adapters import contacts as _contact_records
from validation.artifact_io import checked_ref, digest, read_json
from validation.adapters.contacts import CONTACT_PATTERN, decode_contact_records


_COLLECTOR_SOURCE_SHA256 = digest(Path(__file__))
_CONTACT_DECODER_PATH = Path(_contact_records.__file__)
_CONTACT_DECODER_SHA256 = digest(_CONTACT_DECODER_PATH)


def _artifact(directory, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError('relative runtime artifact reference required')
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError('runtime artifact missing or escapes its run directory')
    return path



_STATE_FIELDS = ('entity', 'step', 't', 'pos_x', 'pos_y', 'pos_z',
                 'quat_w', 'quat_x', 'quat_y', 'quat_z',
                 'linvel_x', 'linvel_y', 'linvel_z', 'angvel_x', 'angvel_y', 'angvel_z')
_MEASUREMENT_PATTERN = (
    r'solver[0-9]+\.body_(pos|quat)\.[0-9]+\.[0-3]|' + CONTACT_PATTERN + '|'
    # Legacy observations supplement the fields owned by the contact decoder.
    r'solver[0-9]+\.contact\.sample\.[0-9]+\.(known|phase|available_time_s|impulses_known)'
)
_QUERY_SCRIPT = '''import contextlib,io,json,sys
from types import SimpleNamespace
from physpi_runtime.cli import cmd_query
request=json.load(sys.stdin)
stream=io.StringIO()
with contextlib.redirect_stdout(stream):
    code=cmd_query(SimpleNamespace(run_id=request['run_id'],branch=request['branch'],query=json.dumps(request['query'])))
reply=json.loads(stream.getvalue())
if code or reply.get('ok') is not True:
    raise ValueError(reply.get('error', 'public query failed'))
print(json.dumps(reply,allow_nan=False))
'''


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()


def _public_query(directory, runtime_python, branch, query):
    """Use the same closed-branch admission as the public PhysPi query command."""
    env = dict(os.environ, PHYSPI_RUNS_ROOT=str(directory.parent))
    completed = subprocess.run([str(runtime_python), '-c', _QUERY_SCRIPT],
        input=json.dumps({'run_id': directory.name, 'branch': branch, 'query': query}),
        capture_output=True, text=True, check=True, env=env, timeout=60)
    reply = json.loads(completed.stdout)
    expected = directory if branch is None else directory / 'timeline' / branch
    if (reply.get('ok') is not True or Path(reply.get('run_dir', '')).resolve() != expected.resolve()
            or type(reply.get('truncated')) is not bool):
        raise ValueError('public query returned a different run/branch or malformed reply')
    return reply


def _public_rows(directory, runtime_python, branch, calls, sql, *, paged=False):
    result, offset = [], 0
    while True:
        request = {'kind': 'sql', 'row_cap': 5000,
                   'sql': sql + (f' LIMIT 5000 OFFSET {offset}' if paged else '')}
        reply = _public_query(directory, runtime_python, branch, request)
        columns, values = reply['result']['columns'], reply['result']['rows']
        if len(set(columns)) != len(columns) or reply['truncated']:
            raise ValueError('incomplete or ambiguous public evidence query')
        batch = [dict(zip(columns, row, strict=True)) for row in values]
        calls.append({'query': request, 'row_count': len(batch), 'reply_sha256': _json_digest(reply)})
        result.extend(batch)
        if not paged or len(batch) < 5000:
            return result
        offset += len(batch)
        if offset >= 200000:
            raise ValueError('requested terminal evidence exceeds bounded row budget')


def _source_pointer(source, pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('source requirement needs a JSON pointer')
    value = source
    try:
        for token in pointer.split('/')[1:]:
            if re.search(r'~(?:[^01]|$)', token):
                raise ValueError('invalid source pointer escape')
            token = token.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', token):
                    raise ValueError('invalid source pointer index')
                value = value[int(token)]
            else:
                value = value[token]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError('source requirement pointer does not exist') from error
    return value


def _window_request(root, window):
    if window is None:
        return None, []
    common = {'source_ref', 'pointer', 'sample_dt_seconds', 'sample_dt_pointer'}
    if not isinstance(window, dict) or set(window) - common - {'seconds', 'start_frame', 'end_frame'}:
        raise ValueError('unsupported terminal window fields')
    path = checked_ref(root, window['source_ref'])
    source = read_json(path)
    declared = _source_pointer(source, window['pointer'])
    if 'seconds' in window:
        seconds = window['seconds']
        if (set(window) & {'start_frame', 'end_frame'} or not _finite(seconds) or seconds <= 0
                or type(declared) not in (int, float) or declared != seconds):
            raise ValueError('terminal window seconds must equal the source requirement')
    elif (type(window.get('start_frame')) is not int or type(window.get('end_frame')) is not int
          or not 0 <= window['start_frame'] <= window['end_frame']
          or declared != [window['start_frame'], window['end_frame']]):
        raise ValueError('terminal frame window must equal the source requirement')
    if ('sample_dt_seconds' in window) != ('sample_dt_pointer' in window):
        raise ValueError('sample cadence requires its source pointer')
    if 'sample_dt_seconds' in window:
        cadence = window['sample_dt_seconds']
        original = _source_pointer(source, window['sample_dt_pointer'])
        if (not _finite(cadence) or cadence <= 0 or type(original) not in (int, float)
                or original != cadence):
            raise ValueError('sample cadence must equal the source requirement')
    elif 'start_frame' in window:
        raise ValueError('frame windows require source-bound sample cadence')
    return dict(window), [path]


def _runtime_source(directory, branch):
    """Resolve public artifacts; never execute or import the captured source."""
    if branch is not None and (not isinstance(branch, str) or not branch
                              or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', branch) is None
                              or branch in {'.', '..'}):
        raise ValueError('one explicit portable branch name required')
    index_path = directory / ('manifest.json' if branch is None else 'timeline/timeline.json')
    index = read_json(index_path)
    if index.get('run_id') != directory.name:
        raise ValueError('run directory/index identity mismatch')
    source_path = _artifact(directory, index['code_snapshot'])
    if digest(source_path) != index['code_sha256']:
        raise ValueError('runtime source snapshot mismatch')
    paths, reasons = [index_path, source_path], []
    if index.get('status') != 'completed':
        reasons.append('runtime_not_completed')
    if branch is None:
        job_path = _artifact(directory, index['job'])
        job = read_json(job_path)
        if (job.get('run_id') != index['run_id'] or not isinstance(job.get('code'), str)
                or hashlib.sha256(job['code'].encode('utf-8')).hexdigest() != index['code_sha256']):
            raise ValueError('runtime job/source identity mismatch')
        paths.append(job_path)
        trace = _artifact(directory, index['artifacts']['states'])
        if trace != (directory / 'trace/states.parquet').resolve():
            raise ValueError('manifest trace differs from public query location')
        dt = index.get('scene', {}).get('dt')
        end_step = job.get('simulation', {}).get('steps')
        if not _finite(dt) or dt <= 0 or type(end_step) is not int or end_step <= 0:
            raise ValueError('exact runtime recording timebase required')
        end_time, start_step, start_time = end_step * dt, 0, 0.0
        cadence = index.get('timing', {}).get('trace_sample_dt')
        if (job['simulation'].get('dt') != dt
                or job['simulation'].get('substeps', 1) != index['scene'].get('substeps')
                or not _finite(job.get('duration_s'))
                or not math.isclose(job['duration_s'], end_time, abs_tol=1e-9, rel_tol=0)):
            reasons.append('runtime_job_timebase_mismatch')
        if (index.get('exit_code') != 0 or index.get('engine_config', {}).get('dryrun') is not False
                or index.get('timing', {}).get('sim_steps') != end_step):
            reasons.append('runtime_execution_not_complete')
        names = [entity['name'] for entity in index.get('scene', {}).get('entities', [])]
        build_path = index.get('artifacts', {}).get('build_evidence')
        if build_path is not None:
            build_path = _artifact(directory, build_path)
            paths.append(build_path)
        build = read_json(build_path) if build_path else {}
        branch_meta = None
    else:
        branch_meta = index.get('branches', {}).get(branch)
        if not isinstance(branch_meta, dict):
            raise ValueError('branch not found in closed timeline')
        trace = _artifact(directory, branch_meta['trace'])
        if trace != (directory / 'timeline' / branch / 'trace/states.parquet').resolve():
            raise ValueError('branch trace differs from public query location')
        dt, start_step, start_time = index.get('dt'), branch_meta.get('start_step'), branch_meta.get('start_t')
        count = branch_meta.get('steps')
        if (not _finite(dt) or dt <= 0 or type(start_step) is not int or start_step < 0
                or not _finite(start_time) or start_time < 0 or type(count) is not int or count < 0):
            raise ValueError('closed branch recording timebase required')
        end_step, end_time = start_step + count, start_time + count * dt
        steps = branch_meta.get('trace_cadence_steps', [])
        cadence = dt * steps[0] if (isinstance(steps, list) and steps
            and all(type(step) is int and step > 0 for step in steps)
            and len(set(steps)) == 1) else None
        if branch_meta.get('aborted') is not None:
            reasons.append('branch_aborted')
        names, build = None, index.get('build_evidence', {})
        bundle = index.get('source_bundle')
        if bundle is not None:
            descriptor = bundle.get('descriptor', {})
            if descriptor.get('root') != 'runs':
                raise ValueError('source bundle requires its public runs-root locator')
            descriptor_path = _artifact(directory.parent, descriptor['path'])
            if digest(descriptor_path) != descriptor.get('sha256'):
                raise ValueError('source bundle descriptor hash mismatch')
            bundle_source = _artifact(descriptor_path.parent, bundle['source']['path'])
            if (digest(bundle_source) != bundle['source'].get('sha256')
                    or bundle['source']['sha256'] != index['code_sha256']):
                raise ValueError('timeline/source bundle identity mismatch')
            paths += [descriptor_path, bundle_source]
    paths.append(trace)
    asset_path = (index.get('asset_properties') if branch is not None
                  else index.get('artifacts', {}).get('asset_properties'))
    if asset_path is not None:
        paths.append(_artifact(directory, asset_path))
    # Other public views are lazy. Do not hash unused multi-gigabyte measurements
    # or imply that events/measurement contents were inspected by a state query.
    measurements_path = trace.parent / 'measurements.parquet'
    if names is not None and (not names or len(set(names)) != len(names)
                              or any(not isinstance(name, str) or not name for name in names)):
        raise ValueError('unambiguous declared entity identities required')
    return dict(index=index, index_path=index_path, paths=paths, measurements_path=measurements_path,
        branch_meta=branch_meta, trace=trace, names=names, build=build, dt=dt,
        start_step=start_step, start_time=start_time, end_step=end_step, end_time=end_time,
        sample_dt=cadence if _finite(cadence) and cadence > 0 else None, reasons=reasons)


def _snapshot(rows, names):
    if not rows:
        return {'complete': False, 'step': None, 'time_s': None, 'positions': {},
                'orientations_wxyz': {}, 'linear_velocities_m_s': {}, 'angular_velocities_rad_s': {}}
    step, time = rows[0]['step'], rows[0]['t']
    if type(step) is not int or step < 0 or not _finite(time) or time < 0:
        raise ValueError('invalid public state clock')
    if (len({r['entity'] for r in rows}) != len(rows)
            or any(r['step'] != step or r['t'] != time for r in rows)):
        raise ValueError('ambiguous snapshot rows or inconsistent entity clocks')
    output = {'step': step, 'time_s': time, 'complete': set(names) <= {r['entity'] for r in rows}}
    for target, columns in (
            ('positions', ('pos_x', 'pos_y', 'pos_z')),
            ('orientations_wxyz', ('quat_w', 'quat_x', 'quat_y', 'quat_z')),
            ('linear_velocities_m_s', ('linvel_x', 'linvel_y', 'linvel_z')),
            ('angular_velocities_rad_s', ('angvel_x', 'angvel_y', 'angvel_z'))):
        values = {}
        for row in rows:
            vector = [row.get(column) for column in columns]
            if row['entity'] not in names or not all(_finite(value) for value in vector):
                continue
            if target == 'orientations_wxyz' and abs(math.sqrt(sum(x*x for x in vector)) - 1) > 1e-4:
                continue
            values[row['entity']] = vector
        output[target] = values
    return output


def _pose_spread(samples, names, complete):
    """Numeric facts only; caller supplies source thresholds and interpretations."""
    result = {}
    for name in names:
        positions = [sample['positions'].get(name) for sample in samples]
        rotations = [sample['orientations_wxyz'].get(name) for sample in samples]
        known = bool(complete and samples and len(samples) <= 512 and all(p is not None for p in positions)
                     and all(q is not None for q in rotations))
        fact = {'available': known, 'sample_count': len(samples)}
        if len(samples) > 512:
            fact['reason'] = 'pairwise_sample_budget_exceeded'
        if known:
            fact['maximum_pairwise_center_distance_m'] = max(
                math.dist(a, b) for a in positions for b in positions)
            unit = [[v / math.sqrt(sum(x*x for x in q)) for v in q] for q in rotations]
            fact['maximum_pairwise_orientation_angle_deg'] = max(
                math.degrees(2 * math.acos(min(1.0, abs(sum(x*y for x, y in zip(a, b))))))
                for a in unit for b in unit)
        result[name] = fact
    return result


def _terminal_contacts(runtime, branch, terminal):
    """Admit only a sealed public current-geometry packet for this exact endpoint.

    Even a known packet establishes contacts/clearance, not static load support.
    Last-solve observations and contact_start/contact_end events are not promoted.
    """
    unknown = {'known': False, 'reason': 'current_terminal_contact_packet_unavailable'}
    packet = runtime['index'].get('terminal_contacts')
    if not isinstance(packet, dict) or packet.get('known') is not True:
        return unknown
    try:
        source_id = packet['source_id']
        if not isinstance(source_id, str) or re.fullmatch(r'solver[0-9]+', source_id) is None:
            return unknown
        source = runtime['build']['contact_observations'][source_id[6:]]
        if (packet['branch'] != branch or packet['step'] != terminal['step']
                or packet['t'] != terminal['time_s'] or packet.get('sealed') is not True
                or packet['source_bundle'] != runtime['index']['source_bundle']
                or packet['source'] != source or packet['owner'] != source['owner']
                or packet['episode'] != source['initial_episode']
                or packet['phase'] != 'terminal_geometry' or packet['impulses_known'] is not False
                or packet['geometry_substep'] != packet['completed_substeps']
                or packet['geometry_time_s'] != terminal['time_s']
                or packet['available_time_s'] != terminal['time_s']):
            return {**unknown, 'reason': 'terminal_contact_identity_time_or_phase_mismatch'}
        if (not isinstance(packet['owner'], str) or not packet['owner']
                or any(type(packet.get(key)) is not int or packet[key] < 0
                       for key in ('step', 'episode', 'generation', 'completed_substeps', 'geometry_substep'))):
            return unknown
        names = source['body_names']
        positions, rotations = packet['geometry_positions'], packet['geometry_orientations']
        if (not isinstance(names, list) or len(set(names)) != len(names)
                or len(positions) != len(names) or len(rotations) != len(names)):
            return unknown
        for values, width in ((positions, 3), (rotations, 4)):
            if any(not isinstance(row, list) or len(row) != width
                   or not all(_finite(value) for value in row) for row in values):
                return unknown
        if any(abs(math.sqrt(sum(value*value for value in q)) - 1) > 1e-4 for q in rotations):
            return unknown
        for field, data in (('positions', positions), ('orientations_wxyz', rotations)):
            for name, values in terminal[field].items():
                if name not in names or any(abs(a-b) > 1e-9 for a, b in zip(values, data[names.index(name)])):
                    return {**unknown, 'reason': 'terminal_contact_geometry_differs_from_trace'}
        capacity = packet['capacity']
        if (any(type(capacity.get(key)) is not int for key in ('count', 'capacity', 'required_count', 'max_contacts_per_pair'))
                or not 0 <= capacity['count'] <= capacity['capacity']
                or capacity['required_count'] < capacity['count'] or capacity['max_contacts_per_pair'] < 1
                or capacity.get('admitted') != 1 or capacity.get('required_count_exact') != 1
                or any(capacity.get(key) != 0 for key in ('overflow', 'overflow_stage',
                       'pair_index_overflow', 'truncated_candidate_count', 'stream_stopped',
                       'reservation_invariant_violation'))):
            return {**unknown, 'reason': 'terminal_contact_capacity_incomplete'}
        points = []
        for point in packet['points']:
            pair, distance, position = point['bodies'], point['distance'], point['position']
            if (not isinstance(pair, list) or len(pair) != 2 or any(name not in names for name in pair)
                    or not _finite(distance) or type(point.get('touching')) is not bool
                    or point['touching'] != (distance <= 0)
                    or not isinstance(position, list) or len(position) != 3
                    or not all(_finite(value) for value in position)):
                return unknown
            points.append({'bodies': pair, 'distance_m': distance, 'position_m': position,
                           'touching': point['touching']})
        if not capacity['count'] <= len(points) <= capacity['count'] * capacity['max_contacts_per_pair']:
            return {**unknown, 'reason': 'terminal_contact_point_coverage_not_established'}
        return {'known': True, 'source_id': source_id, 'owner': packet['owner'],
                'phase': 'terminal_geometry', 'time_s': terminal['time_s'],
                'body_names': names, 'points': points, 'impulses_known': False,
                'geometry_positions': dict(zip(names, positions)),
                'geometry_orientations_wxyz': dict(zip(names, rotations)),
                'interpretation': 'current contacts only; no solved support impulse'}
    except (KeyError, TypeError, ValueError, IndexError):
        return unknown


def collect_evidence(run_directory, runtime_python, root, output, *, branch=None,
                     window=None, source_refs=(), entities=None, asset_family='native-physpi',
                     include_native_measurements=False):
    """Collect source-bound initial, terminal and explicitly requested tail facts.

    ``window`` carries a hash-bound source JSON pointer to either ``seconds`` or
    ``[start_frame,end_frame]``. Optional ``sample_dt_seconds`` needs its own
    pointer in that same source document. Prose requirements remain in the
    original-task review; this collector does not compile them into a window.
    No unspecified stability window is
    invented. This is public native PhysPi evidence, never Core Entity identity,
    process acceptance or task success.
    """
    directory, root, output = Path(run_directory).resolve(), Path(root).resolve(), Path(output)
    output = output.resolve()
    contact_output = output.with_name(output.stem + '.contacts.json')
    if (digest(Path(__file__)) != _COLLECTOR_SOURCE_SHA256
            or digest(_CONTACT_DECODER_PATH) != _CONTACT_DECODER_SHA256):
        raise ValueError('collector source changed since this module was loaded')
    if output.exists():
        raise FileExistsError(f'refusing to overwrite evidence: {output}')
    if not output.is_relative_to(root):
        raise ValueError('evidence output must be inside the declared evidence root')
    if include_native_measurements and contact_output.exists():
        raise FileExistsError(f'refusing to overwrite contact evidence: {contact_output}')
    if not directory.is_relative_to(root) or not directory.is_dir():
        raise ValueError('runtime evidence must be inside the declared evidence root')
    if not isinstance(asset_family, str) or not asset_family.strip():
        raise ValueError('explicit nonempty asset family required')
    if type(include_native_measurements) is not bool:
        raise ValueError('native measurement collection must be an explicit boolean')
    requested, requirement_paths = _window_request(root, window)
    source_paths = [checked_ref(root, ref) for ref in source_refs]
    runtime = _runtime_source(directory, branch)
    paths = list(dict.fromkeys(runtime['paths'] + requirement_paths + source_paths))
    if include_native_measurements and runtime['measurements_path'].is_file():
        paths.append(runtime['measurements_path'])
    if any(not path.resolve().is_relative_to(root) for path in paths):
        raise ValueError('runtime/source binding escapes the declared evidence root')
    watched = list(dict.fromkeys(paths + ([runtime['measurements_path']] if include_native_measurements else [])))
    before = {path: digest(path) if path.is_file() else None for path in watched}
    if read_json(runtime['index_path']) != runtime['index']:
        raise ValueError('runtime index changed during source binding')
    for ref in [*source_refs, *([requested['source_ref']] if requested else [])]:
        checked_ref(root, ref)
    calls = []

    def query(sql, *, paged=False):
        return _public_rows(directory, runtime_python, branch, calls, sql, paged=paged)

    coverage = query('SELECT entity,COUNT(*) AS n,COUNT(DISTINCT step) AS distinct_steps,'
        'MIN(step) AS first_step,MAX(step) AS last_step,MIN(t) AS first_time,MAX(t) AS final_time '
        'FROM states GROUP BY entity ORDER BY entity')
    observed = [row['entity'] for row in coverage]
    if (not observed or len(set(observed)) != len(observed)
            or any(not isinstance(name, str) or not name for name in observed)):
        raise ValueError('public trace has no unambiguous entity identities')
    if runtime['names'] is not None and set(observed) - set(runtime['names']):
        raise ValueError('trace entities differ from the runtime declarations')
    if entities is not None and (not isinstance(entities, (list, tuple)) or not entities
            or any(not isinstance(name, str) or not name for name in entities)
            or len(set(entities)) != len(entities) or any(name not in observed for name in entities)):
        raise ValueError('requested entities missing, ambiguous or not exact trace names')
    names = sorted(entities if entities is not None else (runtime['names'] or observed))
    fields = ','.join(_STATE_FIELDS)
    first_rows = query(f'SELECT {fields} FROM states WHERE step=(SELECT MIN(step) FROM states) ORDER BY entity')
    final_rows = query(f'SELECT {fields} FROM states WHERE step=(SELECT MAX(step) FROM states) ORDER BY entity')
    initial, terminal = _snapshot(first_rows, names), _snapshot(final_rows, names)
    if terminal['time_s'] is None:
        raise ValueError('public trace has no terminal state')
    initial['scope'] = 'episode_initial' if initial['step'] == 0 and initial['time_s'] == 0 else 'branch_start'
    initial['valid_for_task_initial'] = bool(initial['complete'] and initial['scope'] == 'episode_initial')
    reasons = list(runtime['reasons'])
    if (not terminal['complete'] or terminal['step'] != runtime['end_step']
            or not _finite(terminal['time_s'])
            or not math.isclose(terminal['time_s'], runtime['end_time'], abs_tol=1e-9, rel_tol=0)):
        reasons.append('declared_terminal_boundary_not_recorded')
    if any(row['n'] != row['distinct_steps'] for row in coverage if row['entity'] in names):
        raise ValueError('duplicate entity/step rows in public trace')
    tail, start_time = None, terminal['time_s']
    if requested is not None:
        cadence = requested.get('sample_dt_seconds', runtime['sample_dt'])
        end_time = terminal['time_s']
        start_time = end_time - requested['seconds'] if 'seconds' in requested else requested['start_frame'] * cadence
        tail_reasons = list(reasons)
        if 'end_frame' in requested and not math.isclose(requested['end_frame'] * cadence, end_time, abs_tol=1e-9, rel_tol=0):
            tail_reasons.append('source_frame_window_does_not_end_at_runtime_terminal')
        ratio = cadence / runtime['sample_dt'] if cadence is not None and runtime['sample_dt'] is not None else None
        if (ratio is None or ratio < 1 or not math.isclose(ratio, round(ratio), abs_tol=1e-7, rel_tol=0)):
            tail_reasons.append('source_sample_cadence_not_established')
        rows = query(f'SELECT {fields} FROM states WHERE t>={start_time - 1e-9!r} '
                     f'AND t<={end_time + 1e-9!r} ORDER BY step,entity', paged=True)
        by_step = {}
        for row in rows:
            by_step.setdefault(row['step'], []).append(row)
        recorded = [_snapshot(by_step[step], names) for step in sorted(by_step)]
        times = [sample['time_s'] for sample in recorded]
        if (not times or not math.isclose(times[0], start_time, abs_tol=1e-9, rel_tol=0)
                or not math.isclose(times[-1], end_time, abs_tol=1e-9, rel_tol=0)
                or end_time < start_time):
            tail_reasons.append('requested_window_boundary_or_entity_samples_missing')
        samples, missing_grid = [], []
        if cadence is not None:
            intervals = (end_time - start_time) / cadence
            if not math.isfinite(intervals) or intervals > 20000:
                raise ValueError('requested terminal window exceeds bounded sample budget')
            if intervals < 0 or not math.isclose(intervals, round(intervals), abs_tol=1e-7, rel_tol=0):
                tail_reasons.append('requested_window_sample_grid_incomplete')
            # Match the original output grid exactly (apart from floating-point
            # clock serialization error). Never choose the nearest observation,
            # nor use intermediate dense poses to strengthen the source rule.
            for i in range(max(0, round(intervals)) + 1):
                required_time = start_time + i * cadence
                matches = [sample for sample in recorded if math.isclose(
                    sample['time_s'], required_time, abs_tol=1e-9, rel_tol=0)]
                if len(matches) != 1 or not matches[0]['complete']:
                    missing_grid.append(required_time)
                else:
                    samples.append(matches[0])
            if missing_grid:
                tail_reasons.append('requested_window_sample_grid_incomplete')
        if any(not math.isclose(sample['time_s'], runtime['start_time'] +
                (sample['step'] - runtime['start_step']) * runtime['dt'], abs_tol=1e-9, rel_tol=0)
               for sample in recorded):
            tail_reasons.append('recorded_step_time_mismatch')
        tail = {'requested': requested, 'start_time_s': start_time, 'end_time_s': end_time,
                'sample_dt_seconds': cadence, 'complete': not tail_reasons,
                'reasons': sorted(set(tail_reasons)), 'samples': samples,
                'recorded_sample_dt_seconds': runtime['sample_dt'],
                'recorded_sample_count': len(recorded), 'recorded_state_row_count': len(rows),
                'grid_projection': {'method': 'unique_exact_source_output_times',
                    'clock_roundoff_tolerance_s': 1e-9, 'recorded_cadences_per_source_sample': ratio,
                    'selected_steps': [sample['step'] for sample in samples],
                    'missing_or_ambiguous_required_times_s': missing_grid,
                    'excluded_intermediate_sample_count': len(recorded) - len(samples),
                    'proves_continuous_stability': False,
                    'interpretation': 'pose spread uses required sampled poses only; continuous contact obligations are separate'}}
    # Only public native numerical observations, never task-authored verdict,
    # controller phase, success/failed flags, or contact-event persistence guesses.
    measurements = query('SELECT step,t,name,value FROM measurements WHERE '
        f't>={start_time - 1e-9!r} AND t<={terminal["time_s"] + 1e-9!r} '
        f"AND regexp_full_match(name, '{_MEASUREMENT_PATTERN}') ORDER BY step,name", paged=True) if (
            include_native_measurements and runtime['measurements_path'].is_file()) else []
    for row in measurements:
        if (type(row['step']) is not int or not _finite(row['t']) or not _finite(row['value'])
                or re.fullmatch(_MEASUREMENT_PATTERN, row['name']) is None):
            raise ValueError('malformed public native measurement')
    if len({(row['step'], row['name']) for row in measurements}) != len(measurements):
        raise ValueError('ambiguous native measurements')
    if before != {path: digest(path) if path.is_file() else None for path in watched}:
        raise ValueError('runtime or requirement evidence changed while querying')
    rebound = _runtime_source(directory, branch)
    if (rebound['index'] != runtime['index'] or rebound['build'] != runtime['build']
            or rebound['reasons'] != runtime['reasons']):
        raise ValueError('runtime source binding changed while querying')
    if (digest(Path(__file__)) != _COLLECTOR_SOURCE_SHA256
            or digest(_CONTACT_DECODER_PATH) != _CONTACT_DECODER_SHA256):
        raise ValueError('collector source changed while querying')
    refs = [{'path': path.relative_to(root).as_posix(), 'sha256': before[path]} for path in paths]
    source_identity = _json_digest({'index': refs[0], 'code_sha256': runtime['index']['code_sha256'],
                                  'branch': branch})
    episode_id = f'native-physpi::{source_identity}::{directory.name}::{branch or "batch"}'
    endpoint = {'episode_id': episode_id,
                'endpoint_id': _json_digest({'episode': episode_id, 'step': terminal['step'],
                                            'time_s': terminal['time_s'], 'trace': digest(runtime['trace'])}),
                'asset_family': asset_family, 'valid': not reasons,
                'step': terminal['step'], 'time_s': terminal['time_s'], 'reasons': reasons}
    contact_sources = runtime['build'].get('contact_observations', {})
    contact_sources = {key: {field: value[field] for field in (
        'owner', 'body_names', 'body_indices', 'phase', 'phase_code', 'substep_dt',
        'history_capacity', 'initial_episode') if field in value}
        for key, value in contact_sources.items() if isinstance(value, dict)}
    evidence = {'schema_version': 'terminal-evidence/0.1',
        'implementation': {'path': str(Path(__file__).resolve()), 'sha256': _COLLECTOR_SOURCE_SHA256},
        'run': {'run_id': directory.name, 'kind': 'batch' if branch is None else 'resident',
                'branch': branch, 'code_sha256': runtime['index']['code_sha256']},
        'endpoint': endpoint, 'identities': {name: episode_id + '::' + name for name in names},
        'initial': initial, 'terminal': terminal, 'terminal_window': tail,
        'facts': {'recording_coverage': coverage, 'native_measurements': measurements,
                  'native_measurements_collected': include_native_measurements,
                  'contact_sources': contact_sources,
                  'terminal_contact': _terminal_contacts(runtime, branch, terminal),
                  'terminal_window_pose_spread': _pose_spread(tail['samples'], names, tail['complete']) if tail else {},
                  'actual_collision_geometry': {'known': False, 'reason': 'explicit_source_geometry_binding_required'},
                  'actual_support': None, 'robot_release': None},
        'capture': {'owner': 'physpi_runtime.cli.cmd_query', 'queries': calls,
                    'scope': 'initial_terminal_and_source_requested_terminal_window_only'},
        'source_refs': refs, 'process': 'not_evaluated', 'task_success': None}
    if include_native_measurements:
        contact_rows = [row for row in measurements if re.fullmatch(CONTACT_PATTERN, row['name'])]
        contacts = decode_contact_records(contact_rows, contact_sources, runtime, start_time, terminal['time_s'])
        contacts.update(endpoint=endpoint, run=evidence['run'], source_refs=refs,
                        capture={'owner': 'physpi_runtime.cli.cmd_query', 'queries': calls},
                        implementation=evidence['implementation'],
                        decoder={'path': str(_CONTACT_DECODER_PATH), 'sha256': _CONTACT_DECODER_SHA256})
        contact_output.parent.mkdir(parents=True, exist_ok=True)
        with contact_output.open('x', encoding='utf-8') as stream:
            json.dump(contacts, stream, ensure_ascii=False, indent=2, allow_nan=False)
        evidence['facts']['native_contacts'] = {'path': contact_output.relative_to(root).as_posix(),
                                               'sha256': digest(contact_output)}
        evidence['facts']['contact_collection_status'] = contacts['status']
    else:
        evidence['facts'].update(native_contacts=None, contact_collection_status='not_requested')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return evidence


_NATIVE_STATE_PATTERN = (
    r'solver[0-9]+\.(body_pos\.[0-9]+\.[0-2]|body_quat\.[0-9]+\.[0-3]|'
    r'(qpos|ctrl|actuator_force)\.[0-9]+|host_calls\.'
    r'(set_ctrl|set_qfrc_applied|write_positions|write_orientations|write_qpos|write_qvel))'
)


def _native_solver_mappings(build):
    """Use recorded attachment/name maps, never reconstruct a native model."""
    imports, compositions = build.get('imports', []), build.get('compositions', [])
    mappings = {}

    def qpos_count(kind, index, active=()):
        key = (kind, index)
        if key in active or type(index) is not int or index < 0:
            raise ValueError('invalid native composition reference')
        records = imports if kind == 'import' else compositions if kind == 'composition' else []
        if index >= len(records):
            raise ValueError('native composition reference missing')
        record = records[index]
        if kind == 'import':
            value = record.get('joint_layout', {}).get('qpos0')
            return len(value) if isinstance(value, list) else None
        counts = [qpos_count(ref['kind'], ref['index'], active + (key,)) for ref in record['inputs']]
        return sum(counts) if counts and all(n is not None for n in counts) else None

    for kind, records in (('import', imports), ('composition', compositions)):
        for index, record in enumerate(records):
            for solver in record.get('attached_solver_indices', []):
                if type(solver) is not int or solver < 0 or solver in mappings:
                    raise ValueError('ambiguous native solver attachment')
                contact = build.get('contact_observations', {}).get(str(solver), {})
                if kind == 'import':
                    bodies = record.get('bodies', [])
                    if [b.get('index') for b in bodies] != list(range(len(bodies))):
                        raise ValueError('native body indices are not contiguous')
                    names = [b.get('key') for b in bodies]
                    basis = 'native_import_attached_solver_indices'
                else:
                    names = contact.get('body_names', [])
                    basis = 'native_frozen_contact_source_body_map_for_attached_composition'
                if (not names or len(set(names)) != len(names)
                        or any(not isinstance(n, str) or not n for n in names)):
                    raise ValueError('native solver has no unambiguous recorded body map')
                if contact and (contact.get('body_names') != names or contact.get('body_indices') !=
                                {name: i for i, name in enumerate(names)}):
                    raise ValueError('native import/contact source body maps disagree')
                mappings[str(solver)] = {'solver_index': solver, 'body_names': names,
                    'body_map_basis': basis, 'build_record': {'kind': kind, 'index': index},
                    'qpos_count': qpos_count(kind, index),
                    'qpos_count_basis': 'recorded_import_qpos0' if kind == 'import' else 'sum_of_recorded_composition_input_qpos0_lengths',
                    'joint_layout': record.get('joint_layout') if kind == 'import' else None,
                    'global_joint_layout_known': kind == 'import' and bool(record.get('joint_layout'))}
    if not mappings:
        raise ValueError('no source-qualified native solver mapping')
    return mappings


def _native_samples(rows, mappings, runtime, start_time, end_time):
    """Validate the recorded numeric channel grid; absence stays explicit."""
    values, inventories = {}, {key: {} for key in mappings}
    for row in rows:
        if (type(row.get('step')) is not int or not _finite(row.get('t')) or not _finite(row.get('value'))
                or re.fullmatch(_NATIVE_STATE_PATTERN, row.get('name', '')) is None):
            raise ValueError('malformed native state/control measurement')
        step, name = row['step'], row['name']
        if not math.isclose(row['t'], runtime['start_time'] + (step-runtime['start_step'])*runtime['dt'], abs_tol=1e-9, rel_tol=0):
            raise ValueError('native measurement step/time mismatch')
        if not start_time-1e-9 <= row['t'] <= end_time+1e-9:
            raise ValueError('native measurement outside requested scope')
        solver, field, *channel = name.split('.')
        key = solver[6:]
        if key not in mappings:
            raise ValueError('observed solver lacks native build mapping')
        if (step, name) in values:
            raise ValueError('duplicate native measurement channel at step')
        values[step, name] = row['value']
        inventories[key].setdefault(field, set()).add(tuple(channel))
    cadence = runtime['sample_dt']
    reasons = []
    if cadence is None:
        reasons.append('recorded_native_cadence_unknown')
        times = sorted({r['t'] for r in rows})
    else:
        intervals = (end_time-start_time)/cadence
        if intervals < 0 or intervals > 20000 or not math.isclose(intervals, round(intervals), abs_tol=1e-7, rel_tol=0):
            raise ValueError('native requested window is not on declared trace grid')
        times = [start_time+i*cadence for i in range(round(intervals)+1)]
    expected_steps = []
    for time in times:
        raw = runtime['start_step'] + (time-runtime['start_time'])/runtime['dt']
        if not math.isclose(raw, round(raw), abs_tol=1e-7, rel_tol=0):
            raise ValueError('native trace grid is not on declared physical step grid')
        expected_steps.append(round(raw))
    if set(r['step'] for r in rows) - set(expected_steps):
        raise ValueError('native samples differ from declared trace cadence')
    layouts, expected_names = {}, set()
    for key, mapping in mappings.items():
        inventory = inventories[key]
        nbody = len(mapping['body_names'])
        layout = {'body_count': nbody, 'qpos_count': mapping['qpos_count'], 'fields': {}}
        expected = {
            'body_pos': {(str(i), str(a)) for i in range(nbody) for a in range(3)},
            'body_quat': {(str(i), str(a)) for i in range(nbody) for a in range(4)}}
        for field in ('qpos', 'ctrl', 'actuator_force'):
            observed = inventory.get(field, set())
            indices = {int(c[0]) for c in observed}
            count = mapping['qpos_count'] if field == 'qpos' else (max(indices)+1 if indices else 0)
            if count is None:
                count = max(indices)+1 if indices else 0
                reasons.append(f'solver{key}_declared_qpos_count_unknown')
            if indices and indices != set(range(max(indices)+1)):
                reasons.append(f'solver{key}_{field}_channel_indices_incomplete')
            expected[field] = {(str(i),) for i in range(count)}
            layout[field+'_count'] = count
        if expected['ctrl'] != expected['actuator_force']:
            reasons.append(f'solver{key}_control_force_channel_mismatch')
        # Counters are optional recording diagnostics, not proof of arbitrary
        # device activity. Never infer their absence means zero calls.
        expected['host_calls'] = {(name,) for name in (
            'set_ctrl', 'set_qfrc_applied', 'write_positions', 'write_orientations', 'write_qpos', 'write_qvel')}
        for field, channels in expected.items():
            if inventory.get(field, set()) - channels:
                raise ValueError('native channel index exceeds recorded model layout')
            names = {f'solver{key}.{field}.'+'.'.join(c) for c in channels}
            missing = sum((step, name) not in values for step in expected_steps for name in names)
            layout['fields'][field] = {'recorded_channel_count': len(inventory.get(field, set())),
                'expected_channel_count': len(channels), 'missing_scalar_samples': missing,
                'recorded_channel_grid_complete': missing == 0}
            if missing:
                reasons.append(f'solver{key}_{field}_sample_grid_incomplete')
            expected_names |= names
        layout['actuator_inventory_scope'] = 'contiguous recorded ctrl/force channels; native total actuator count not recorded in build evidence'
        layout['full_native_actuator_inventory_known'] = False
        layouts[key] = layout
    samples = []
    for step, time in zip(expected_steps, times):
        sample = {'step': step, 'time_s': time, 'solvers': {}}
        for key, layout in layouts.items():
            def get(field, *indices):
                return values.get((step, f'solver{key}.{field}.'+'.'.join(map(str, indices))))
            item = {'body_positions': [[get('body_pos', i,a) for a in range(3)] for i in range(layout['body_count'])],
                    'body_orientations_wxyz': [[get('body_quat',i,a) for a in range(4)] for i in range(layout['body_count'])]}
            for field in ('qpos', 'ctrl', 'actuator_force'):
                item[field] = [get(field,i) for i in range(layout[field+'_count'])]
            item['host_call_counts'] = {name: get('host_calls', name) for name in (
                'set_ctrl', 'set_qfrc_applied', 'write_positions', 'write_orientations', 'write_qpos', 'write_qvel')}
            for q in item['body_orientations_wxyz']:
                if all(x is not None for x in q) and sum(x*x for x in q) == 0:
                    raise ValueError('zero native body quaternion')
            sample['solvers'][key] = item
        samples.append(sample)
    return {'samples': samples, 'solver_layouts': layouts,
            'recorded_sample_grid_complete': bool(samples) and not reasons,
            'reasons': sorted(set(reasons)), 'recorded_sample_dt_seconds': cadence,
            'measurement_row_count': len(rows), 'expected_steps': expected_steps}


def collect_native_evidence(run_directory, runtime_python, root, output_directory, *,
                            base_evidence_ref, branch=None, window=None, source_refs=(),
                            asset_family='native-physpi'):
    """Supplement an existing endpoint with source-mapped native numeric facts.

    No window means endpoint only. A source window retains every recorded native
    state sample and separately identifies the exact source-required grid. This
    does not claim complete continuous contact or an actuator/force ledger.
    """
    root, directory, output = Path(root).resolve(), Path(run_directory).resolve(), Path(output_directory).resolve()
    base_path = checked_ref(root, base_evidence_ref)
    base = read_json(base_path)
    if not output.is_relative_to(root) or output.exists():
        raise ValueError('native supplement requires a fresh output directory inside root')
    output.mkdir(parents=True)
    capture = collect_evidence(directory, runtime_python, root, output/'state-capture.json',
        branch=branch, window=window, source_refs=source_refs, asset_family=asset_family,
        include_native_measurements=True)
    if (not capture['endpoint']['valid'] or capture['endpoint'] != base['endpoint']
            or capture['run'] != base['run']
            or (capture['terminal_window'] and not capture['terminal_window']['complete'])):
        raise ValueError('native supplement source/endpoint/window differs from admitted base evidence')
    runtime = _runtime_source(directory, branch)
    mappings = _native_solver_mappings(runtime['build'])
    tail = capture['terminal_window']
    start = tail['start_time_s'] if tail else capture['endpoint']['time_s']
    end = capture['endpoint']['time_s']
    path = runtime['measurements_path']
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError('public native measurements unavailable')
    watched = list(dict.fromkeys([*runtime['paths'], path, base_path,
        *(checked_ref(root, ref) for ref in source_refs),
        *([checked_ref(root, tail['requested']['source_ref'])] if tail else [])]))
    before = {p: digest(p) for p in watched}
    calls = []
    rows = _public_rows(directory, runtime_python, branch, calls,
        f'SELECT step,t,name,value FROM measurements WHERE t>={start-1e-9!r} AND t<={end+1e-9!r} '
        f"AND regexp_full_match(name, '{_NATIVE_STATE_PATTERN}') ORDER BY step,name", paged=True)
    native = _native_samples(rows, mappings, runtime, start, end)
    tracked_rows = _public_rows(directory, runtime_python, branch, calls,
        f'SELECT {",".join(_STATE_FIELDS)} FROM states WHERE t>={start-1e-9!r} AND t<={end+1e-9!r} ORDER BY step,entity', paged=True)
    samples = {s['step']: s for s in native['samples']}
    matching, unbound = 0, set()
    for row in tracked_rows:
        matches = [(key, m['body_names'].index(row['entity'])) for key,m in mappings.items() if row['entity'] in m['body_names']]
        if len(matches) != 1:
            unbound.add(row['entity'])
            continue
        key, index = matches[0]
        sample = samples.get(row['step'], {}).get('solvers', {}).get(key, {})
        if (not math.isclose(row['t'], samples.get(row['step'], {}).get('time_s', -1), abs_tol=1e-9, rel_tol=0)
                or sample.get('body_positions', [])[index] != [row[f'pos_{a}'] for a in 'xyz']
                or sample.get('body_orientations_wxyz', [])[index] != [row[f'quat_{a}'] for a in 'wxyz']):
            raise ValueError('source-named native/tracked pose mismatch')
        matching += 1
    if (before != {p: digest(p) for p in watched}
            or digest(Path(__file__)) != _COLLECTOR_SOURCE_SHA256
            or read_json(runtime['index_path']) != runtime['index']):
        raise ValueError('native evidence source changed while querying')
    native.update({'schema_version': 'native-samples/0.2', 'endpoint': capture['endpoint'],
        'solver_mappings': mappings, 'source_grid_steps': tail['grid_projection']['selected_steps'] if tail else [capture['endpoint']['step']],
        'scope': 'source_requested_window' if tail else 'terminal_only',
        'tracked_state_rows': tracked_rows, 'exact_name_pose_matches': matching,
        'tracked_aliases_without_native_identity_binding': sorted(unbound),
        'native_physics_interval_coverage_known': False,
        'continuous_contact_or_stability_proven': False})
    with (output/'native-samples.json').open('x', encoding='utf-8') as stream:
        json.dump(native, stream, ensure_ascii=False, indent=2, allow_nan=False)
    result = {'schema_version': 'native-evidence/0.2', 'endpoint': capture['endpoint'],
        'base_evidence_ref': base_evidence_ref, 'run': capture['run'],
        'implementation': capture['implementation'], 'scope': native['scope'],
        'source_window': tail['requested'] if tail else None,
        'native_sample_count': len(native['samples']), 'source_grid_sample_count': len(native['source_grid_steps']),
        'recorded_sample_grid_complete': native['recorded_sample_grid_complete'], 'reasons': native['reasons'],
        'native_samples': {'path': (output/'native-samples.json').relative_to(root).as_posix(), 'sha256': digest(output/'native-samples.json')},
        'native_build_evidence': runtime['build'],
        'runtime_configuration': runtime['index'].get('engine_config'),
        'capture': {'owner': 'physpi_runtime.cli.cmd_query', 'queries': calls},
        'source_refs': [{'path': p.relative_to(root).as_posix(), 'sha256': before[p]} for p in watched],
        'task_verdict': None,
        'contact_measurements_collected': read_json(checked_ref(root, capture['facts']['native_contacts']))['measurement_row_count'] > 0,
        'contact_collection_status': capture['facts']['contact_collection_status'],
        'native_contacts': capture['facts']['native_contacts']}
    with (output/'native-evidence.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result


def collect_native_pose_measurements(root, native_evidence_ref, *, body_names=None):
    """Project verified native body poses onto the original source sample grid.

    This is a compact measurement artifact for a structured reviewer, including
    USD and dynamically authored imports with recorded body maps. It establishes
    body origins, not source object centers, collision geometry or task success.
    Missing control/counter channels do not invalidate independently present poses.
    All input file hashes are checked; no task script or simulator is executed.
    """
    from validation.adapters.recorded import validate_terminal_evidence as _record, _vector

    root = Path(root).resolve()
    native_path = checked_ref(root, native_evidence_ref)
    native = read_json(native_path)
    if native.get('schema_version') != 'native-evidence/0.2' or native.get('capture', {}).get('owner') != 'physpi_runtime.cli.cmd_query':
        raise ValueError('native pose projection requires public native evidence')
    refs = [native_evidence_ref, native['base_evidence_ref'], native['native_samples']]
    paths = [checked_ref(root, ref) for ref in refs]
    record, _ = _record(read_json(paths[1]))
    samples = read_json(paths[2])
    mappings = _native_solver_mappings(native['native_build_evidence'])
    if (samples.get('schema_version') != 'native-samples/0.2'
            or samples.get('endpoint') != native.get('endpoint') or native.get('endpoint') != record['endpoint']
            or native.get('run') != record['run'] or samples.get('solver_mappings') != mappings):
        raise ValueError('native pose source, body map or endpoint differs')
    by_name = {}
    for solver, mapping in mappings.items():
        for index, name in enumerate(mapping['body_names']):
            if name in by_name:
                raise ValueError('native body name is ambiguous across solvers')
            by_name[name] = (solver, index)
    if body_names is not None and not isinstance(body_names, (list, tuple)):
        raise ValueError('native pose body names must be an explicit sequence')
    names = sorted(by_name) if body_names is None else list(body_names)
    if (not names or len(names) > 256 or any(not isinstance(n, str) for n in names)
            or len(set(names)) != len(names) or not set(names) <= set(by_name)):
        raise ValueError('native pose scope requires 1 to 256 unique recorded body names')
    window = record['terminal_window']
    expected = window['samples'] if window else [record['terminal']]
    source_grid_known_complete = window is None or window['complete']
    grid = samples.get('source_grid_steps')
    if (not isinstance(grid, list) or not 1 <= len(grid) <= 512
            or grid != [s['step'] for s in expected] or len(set(grid)) != len(grid)):
        raise ValueError('native pose projection differs from the source-requested grid')
    raw = {}
    for sample in samples['samples']:
        step = sample.get('step')
        if type(step) is not int or step in raw:
            raise ValueError('duplicate or invalid native pose sample step')
        raw[step] = sample
    projected = []
    for original in expected:
        sample = raw.get(original['step'])
        if sample is not None and (not _finite(sample.get('time_s'))
                or not math.isclose(sample['time_s'], original['time_s'], rel_tol=0, abs_tol=1e-9)):
            raise ValueError('native pose sample clock differs from source state')
        item = {'step': original['step'], 'time_s': original['time_s'], 'positions': {}, 'orientations_wxyz': {}}
        for name in names:
            solver, index = by_name[name]
            state = sample.get('solvers', {}).get(solver, {}) if sample is not None else {}
            for field, native_field, width in (('positions', 'body_positions', 3),
                                              ('orientations_wxyz', 'body_orientations_wxyz', 4)):
                values = state.get(native_field, [])
                value = values[index] if index < len(values) else None
                if value is not None and _vector(value, width, quaternion=width == 4) is not None:
                    prior = original[field].get(name)
                    if prior is not None and value != prior:
                        raise ValueError('native pose differs from the same named tracked body')
                    item[field][name] = list(value)
        item['complete'] = all(set(item[field]) == set(names) for field in ('positions', 'orientations_wxyz'))
        projected.append(item)
    facts = _pose_spread(projected, names, source_grid_known_complete)
    for fact in facts.values():
        if 'maximum_pairwise_center_distance_m' in fact:
            fact['maximum_pairwise_body_origin_distance_m'] = fact.pop('maximum_pairwise_center_distance_m')
        if not fact['available'] and 'reason' not in fact:
            fact['reason'] = ('native_pose_sample_unavailable' if source_grid_known_complete
                              else 'source_sample_grid_incomplete')
    if (any(digest(path) != ref['sha256'] for path, ref in zip(paths, refs))
            or digest(Path(__file__)) != _COLLECTOR_SOURCE_SHA256):
        raise ValueError('native pose evidence changed during projection')
    return {'schema_version': 'native-pose-measurements/0.1', 'endpoint': record['endpoint'],
        'body_names': names, 'body_mapping': {name: {'solver_index': int(by_name[name][0]),
            'body_index': by_name[name][1]} for name in names},
        'samples': projected, 'body_pose_spread': facts,
        'source_grid_complete': source_grid_known_complete and all(s['complete'] for s in projected),
        'source_window': window['requested'] if window else None,
        'observed_span_seconds': projected[-1]['time_s'] - projected[0]['time_s'],
        'source_refs': refs, 'producer': {'path': str(Path(__file__).resolve()),
                                        'sha256': _COLLECTOR_SOURCE_SHA256},
        'coordinate_frame': 'world_native_body_origin_not_source_object_center',
        'scope': 'source_requested_sample_grid_not_continuous_stability_or_contact',
        'geometry_or_support_inferred': False, 'task_verdict': None}


def collect_boundary_images(root, state_evidence_ref, boundary_views_ref):
    """Admit PhysPi initial/final captures against the same retained run/clock.

    This reads public immutable artifacts only. Native provenance remains a
    runtime claim, not proof of visibility or image-model accuracy. Failed or
    incomplete state comparisons are reported and supply no admissible images.
    """
    import struct

    root = Path(root).resolve()
    state = read_json(checked_ref(root, state_evidence_ref))
    if state.get('schema_version') != 'terminal-evidence/0.1':
        raise ValueError('PhysPi terminal evidence is required for boundary images')
    run, endpoint = state['run'], state['endpoint']
    index_path = checked_ref(root, state['source_refs'][0])
    directory = index_path.parent if run['branch'] is None else index_path.parent.parent
    runtime = _runtime_source(directory, run['branch'])
    bound_paths = {str(checked_ref(root, item)) for item in state['source_refs']}
    if any(str(item.resolve()) not in bound_paths for item in runtime['paths']):
        raise ValueError('boundary runtime source files are not bound to the collected state')
    index = read_json(index_path)
    path = checked_ref(root, boundary_views_ref)
    declared = (index.get('artifacts', {}).get('boundary_views') if run['branch'] is None
                else index.get('boundary_views'))
    if (not declared or _artifact(directory, declared) != path
            or index['run_id'] != run['run_id'] or index['code_sha256'] != run['code_sha256']):
        raise ValueError('boundary capture is not bound to this runtime source')
    packet = read_json(path)
    if (packet.get('schema_version') != 'boundary-views/1' or packet.get('run_id') != run['run_id']
            or packet.get('code_sha256') != run['code_sha256']
            or packet.get('source_bundle') != index.get('source_bundle')):
        raise ValueError('boundary capture source identity mismatch')
    groups = packet.get('groups')
    if not isinstance(groups, list) or len(groups) > 2:
        raise ValueError('bounded initial/final capture groups required')
    images, notes, seen = [], [], set()
    for group in groups:
        boundary = group.get('boundary')
        if boundary not in ('initial', 'final') or boundary in seen:
            raise ValueError('duplicate or unknown capture boundary')
        seen.add(boundary)
        sample = state['initial'] if boundary == 'initial' else state['terminal']
        valid_initial = boundary != 'initial' or state['initial'].get('valid_for_task_initial') is True
        same = group.get('state_before_sha256')
        if (endpoint.get('valid') is not True or not valid_initial
                or group.get('branch') != run['branch']
                or group.get('step') != sample['step'] or not _finite(group.get('t'))
                or not math.isclose(group['t'], sample['time_s'], abs_tol=1e-9, rel_tol=0)
                or group.get('clock_valid') is not True or group.get('same_observed_state') is not True
                or group.get('camera_restored') is not True or group.get('status') not in ('complete', 'partial')
                or not isinstance(same, str) or re.fullmatch(r'[0-9a-f]{64}', same) is None
                or same != group.get('state_after_sha256')
                or (boundary == 'final' and (group['step'] != runtime['end_step']
                                             or not math.isclose(group['t'], runtime['end_time'], abs_tol=1e-9, rel_tol=0)))):
            notes.append({'boundary': boundary, 'reason': 'capture_state_clock_or_branch_not_admissible'})
            continue
        captures = group.get('images')
        if not isinstance(captures, list) or not 1 <= len(captures) <= 8:
            raise ValueError('bounded nonempty capture image list required')
        views = set()
        for capture in captures:
            view = capture.get('view')
            if not isinstance(view, str) or not view or view in views:
                raise ValueError('unique boundary view names required')
            views.add(view)
            image_path = _artifact(directory, capture['path'])
            image_ref = {'path': image_path.relative_to(root).as_posix(), 'sha256': capture['sha256']}
            data = checked_ref(root, image_ref).read_bytes()
            if (data[:8] != b'\x89PNG\r\n\x1a\n' or len(data) < 24
                    or struct.unpack('>II', data[16:24]) != (capture['width'], capture['height'])):
                raise ValueError('boundary PNG dimensions differ from runtime metadata')
            images.append({'id': f'{boundary}_{view}', 'kind': 'native_context_image' if boundary == 'initial' else 'native_image',
                **image_ref, 'episode_id': endpoint['episode_id'], 'endpoint_id': endpoint['endpoint_id'],
                'time_s': sample['time_s'], 'view_id': view, 'capture_verified': True})
    return {'schema_version': 'terminal-boundary-images/0.1', 'images': images, 'diagnostics': notes,
            'state_evidence': dict(state_evidence_ref), 'boundary_views': dict(boundary_views_ref),
            'scope': 'verified_native_boundary_artifact_bindings_not_visibility_or_task_success'}


def prepare_source_evidence(root, state_evidence_ref, output_directory, *,
                            native_evidence_ref=None, boundary_views_ref=None, source_documents=(),
                            asset_baseline_ref=None, asset_entity_map=None,
                            model_view=None, max_view_characters=250000, asset_cache=None):
    """Freeze compact, readable evidence for prepare_source_review; no model call.

    Raw files and hashes remain retained. The state projection omits duplicated
    scalar measurements; checked decoded contacts are a separate native_contact
    input. Contact availability is reported independently of any task judgment.
    model_view='boundary' selects initial/actual-final rows for model delivery;
    full originals and a requestable catalogue remain in evidence_view. None
    preserves the legacy package. View selection never replays physics.
    """
    from copy import deepcopy
    from validation.adapters.recorded import validate_terminal_evidence as _record

    root, output = Path(root).resolve(), Path(output_directory).resolve()
    if model_view not in (None, 'boundary', 'full'):
        raise ValueError('model_view must be boundary, full or None')
    if not output.is_relative_to(root) or output == root or output.exists():
        raise ValueError('source evidence requires a fresh output directory inside root')
    retained = []

    def checked(reference):
        path = checked_ref(root, reference)
        retained.append(dict(reference))
        return path

    state_path = checked(state_evidence_ref)
    state, endpoint = _record(read_json(state_path))
    for item in state['source_refs']:
        checked(item)
    prepared, missing = [], []

    def add(identity, kind, reference):
        checked(reference)
        prepared.append({'id': identity, 'kind': kind, **dict(reference),
                         'episode_id': endpoint['episode_id'], 'endpoint_id': endpoint['endpoint_id']})

    contact_ref = state.get('facts', {}).get('native_contacts')
    if native_evidence_ref is not None:
        native = read_json(checked(native_evidence_ref))
        if (native.get('schema_version') != 'native-evidence/0.2'
                or native.get('base_evidence_ref') != state_evidence_ref
                or native.get('endpoint') != state['endpoint'] or native.get('run') != state['run']):
            raise ValueError('native supplement differs from the same base/source/endpoint')
        for reference in native['source_refs']:
            checked(reference)
        samples = read_json(checked(native['native_samples']))
        if samples.get('endpoint') != state['endpoint']:
            raise ValueError('native samples differ from the requested endpoint')
        if native.get('native_contacts') is not None:
            contact_ref = native['native_contacts']
    if contact_ref is not None:
        contacts = read_json(checked(contact_ref))
        if (contacts.get('schema_version') != 'recorded-native-contacts/0.1'
                or contacts.get('endpoint') != state['endpoint'] or contacts.get('run') != state['run']
                or contacts.get('status') not in ('available', 'partial', 'unavailable')):
            raise ValueError('recorded contacts differ from the same run/endpoint')
        for reference in contacts['source_refs']:
            checked(reference)
        if contacts['status'] != 'available':
            missing.extend(contacts['reasons'])
    else:
        missing.append('contact_observations_not_collected')
    for i, reference in enumerate(source_documents):
        path = checked(reference)
        if path.suffix.lower() not in ('.json', '.xml'):
            raise ValueError('source review documents must be readable JSON or XML')
        path.read_text(encoding='utf-8-sig')
        add(f'source_document_{i}', 'source_geometry', reference)
    from .assets import collect_asset_properties
    assets = collect_asset_properties(root, state_evidence_ref,
        baseline_state_ref=asset_baseline_ref, entity_map=asset_entity_map)
    for reference in assets['source_refs']:
        checked(reference)
    if assets['reason']:
        missing.append(assets['reason'])
    images = collect_boundary_images(root, state_evidence_ref, boundary_views_ref) if boundary_views_ref else None
    if images:
        prepared.extend(images['images'])
        checked(boundary_views_ref)
        for item in images['images']:
            checked(item)
    compact = deepcopy(state)
    raw = compact['facts'].pop('native_measurements', [])
    compact['facts']['raw_native_measurement_count'] = len(raw)
    compact['original_state_evidence'] = dict(state_evidence_ref)
    # Complete validation before publishing any derived files.
    for item in retained:
        checked_ref(root, item)
    if digest(Path(__file__)) != _COLLECTOR_SOURCE_SHA256:
        raise ValueError('collector source changed while packaging')
    output.mkdir(parents=True)
    projection = output / 'observed-state.json'
    with projection.open('x', encoding='utf-8') as stream:
        json.dump(compact, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    add('observed_state', 'raw_state', {'path': projection.relative_to(root).as_posix(), 'sha256': digest(projection)})
    projections = []
    # Actual native model readback is endpoint state. Keep the derived receipt
    # and missing-only inventories auxiliary; neither can stand in for a read.
    projections.append(('asset_properties', 'raw_state' if assets['observed_entities'] else 'measurement',
                        'asset-properties.json', assets, state_evidence_ref))
    if native_evidence_ref is not None:
        projections.append(('native_states', 'raw_state', 'native-states.json', samples, native['native_samples']))
    if contact_ref is not None:
        projections.append(('native_contacts', 'native_contact', 'recorded-contacts.json', contacts, contact_ref))
    for identity, kind, name, payload, original in projections:
        path = output / name
        with path.open('x', encoding='utf-8') as stream:
            json.dump({**payload, 'original_evidence': original}, stream,
                      ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        add(identity, kind, {'path': path.relative_to(root).as_posix(), 'sha256': digest(path)})
    result = {'schema_version': 'terminal-source-evidence/0.1', 'endpoint': endpoint,
        'implementation': {'path': str(Path(__file__)), 'sha256': _COLLECTOR_SOURCE_SHA256},
        'evidence': prepared, 'state_evidence': dict(state_evidence_ref),
        'native_evidence': native_evidence_ref, 'boundary_views': boundary_views_ref,
        'missing_structured_evidence': sorted(set(missing)),
        'contact_collection_status': contacts['status'] if contact_ref is not None else 'not_requested',
        'asset_collection_status': assets['collection_status'], 'asset_collection_reason': assets['reason'],
        'image_diagnostics': images['diagnostics'] if images else [], 'task_success': None}
    if model_view is not None:
        from validation.terminal.evidence_views import prepare_evidence_views
        view = prepare_evidence_views(root, prepared, endpoint, output / 'model-view', mode=model_view,
            max_characters=max_view_characters, asset_cache=asset_cache)
        result.update(evidence=view['evidence'], evidence_view=view)
    with (output / 'source-evidence.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-directory', type=Path, required=True, help='source-bound initial/terminal evidence route')
    parser.add_argument('--runtime-python', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--branch', help='explicit closed resident timeline branch')
    parser.add_argument('--window', type=Path, help='JSON source-bound terminal window request')
    parser.add_argument('--source-refs', type=Path, help='JSON array of source path/sha256 references')
    parser.add_argument('--entities', nargs='+', help='exact public trace names; default complete declared set')
    parser.add_argument('--asset-family', default='native-physpi')
    parser.add_argument('--include-native-measurements', action='store_true',
                        help='query/hash the native numerical measurement file; may be large')
    parser.add_argument('--source-evidence-output', type=Path, help='fresh directory for compact source-review inputs')
    parser.add_argument('--boundary-views-ref', type=Path, help='JSON path/sha256 reference to recorded boundary views')
    parser.add_argument('--asset-baseline-ref', type=Path,
                        help='JSON reference to collected state of an independent original-asset reference run')
    parser.add_argument('--asset-entity-map', type=Path,
                        help='optional JSON mapping reference solver/body identities to this run; defaults to exact names')
    args = parser.parse_args()
    if args.boundary_views_ref is not None and args.source_evidence_output is None:
        parser.error('--boundary-views-ref requires --source-evidence-output')
    if (args.asset_baseline_ref or args.asset_entity_map) and not args.source_evidence_output:
        parser.error('asset options require --source-evidence-output')
    evidence = collect_evidence(args.run_directory, args.runtime_python, args.root, args.output,
        branch=args.branch, window=read_json(args.window) if args.window else None,
        source_refs=read_json(args.source_refs) if args.source_refs else (),
        entities=args.entities, asset_family=args.asset_family,
        include_native_measurements=args.include_native_measurements)
    source_packet = None
    if args.source_evidence_output:
        source_packet = prepare_source_evidence(args.root,
            {'path': args.output.resolve().relative_to(args.root.resolve()).as_posix(), 'sha256': digest(args.output)},
            args.source_evidence_output,
            asset_baseline_ref=read_json(args.asset_baseline_ref) if args.asset_baseline_ref else None,
            asset_entity_map=read_json(args.asset_entity_map) if args.asset_entity_map else None,
            boundary_views_ref=read_json(args.boundary_views_ref) if args.boundary_views_ref else None)
    print(json.dumps({'evidence': str(args.output), 'endpoint_valid': evidence['endpoint']['valid'],
        'terminal_window_complete': evidence['terminal_window']['complete'] if evidence['terminal_window'] else None,
        'objects': len(evidence['identities']), 'task_success': None, 'status': 'collection_completed',
        'contact_collection_status': evidence['facts']['contact_collection_status'],
        'source_evidence': str(args.source_evidence_output / 'source-evidence.json') if source_packet else None}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'collection_failed', 'error_type': type(error).__name__, 'reason': str(error)}))
        raise SystemExit(1)
