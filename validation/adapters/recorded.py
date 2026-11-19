"""Adapt already recorded world poses to the terminal diagnostic pipeline.

The caller verifies the referenced file bytes and faithfully extracts both the
normalized frames and independent completion claim from those files. This pure
data adapter cannot verify a file hash or certify the caller's extraction. It
does not infer contacts, source reference frames, or a source-requested grid.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from validation.protocol import _json, _keys, _text, _hash, _digest


_IMPLEMENTATION = {'path': 'validation/adapters/recorded.py',
                   'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
_SCHEMA = {'frame': 'world', 'position_unit': 'm', 'time_unit': 's', 'orientation_order': 'wxyz'}


def _ref(ref):
    _keys(ref, ('path', 'sha256'), 'recorded source reference')
    _text(ref['path'], 'recorded source path')
    _hash(ref['sha256'], 'recorded source hash')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def adapt_recorded_poses(frames, *, run_id, bodies, code_ref, trace_ref, completion_ref,
                         completion, pose_schema, source_refs=(), asset_family='recorded-world-poses'):
    """Build evidence from normalized frames and a separate source-bound claim.

    Frames have ``time`` and optional ``positions``/``orientations`` mappings
    from declared body names to world XYZ metres and world WXYZ quaternions.
    The explicit schema must equal world/m/s/wxyz. No interpolation is done.
    ``completion`` supplies the independent run, file, body and clock bindings;
    ``first_step=None`` preserves an unverified episode initial boundary.
    """
    return _build_record(frames, run_id=run_id, bodies=bodies, code_ref=code_ref, trace_ref=trace_ref,
        completion_ref=completion_ref, completion=completion, pose_schema=pose_schema,
        source_refs=source_refs, asset_family=asset_family, implementation=_IMPLEMENTATION)


def _build_record(frames, *, run_id, bodies, code_ref, trace_ref, completion_ref,
                  completion, pose_schema, source_refs, asset_family, implementation):
    frames, bodies, code_ref, trace_ref, completion_ref, completion, pose_schema, source_refs, implementation = _json(
        [frames, bodies, code_ref, trace_ref, completion_ref, completion, pose_schema, list(source_refs), implementation])
    _ref(implementation)
    # The former path identifies the same producer in frozen pre-move evidence.
    if implementation['path'] not in (_IMPLEMENTATION['path'],
                                      'task_env/diagnostics/qualification/terminal/recorded.py',
                                      'task_env/diagnostics/qualification/recorded_terminal.py'):
        raise ValueError('recorded evidence requires the recorded-pose adapter producer identity')
    _text(run_id, 'recorded run ID')
    _text(asset_family, 'recorded asset family')
    if pose_schema != _SCHEMA:
        raise ValueError('recorded poses require explicit world/m/s/wxyz schema')
    if (not isinstance(bodies, list) or not bodies or any(not isinstance(name, str) or not name.strip() for name in bodies)
            or len(set(bodies)) != len(bodies)):
        raise ValueError('recorded body identity names must be nonempty and unique')
    refs = [code_ref, trace_ref, completion_ref, *source_refs]
    for ref in refs:
        _ref(ref)
    if len({ref['path'] for ref in refs}) != len(refs):
        raise ValueError('recorded source references must identify distinct files')
    fields = ('run_id', 'code_ref', 'trace_ref', 'bodies', 'frame_count', 'last_recorded_time_s',
              'last_recorded_step', 'actual_final_time_s', 'actual_final_step', 'complete', 'first_step')
    _keys(completion, fields, 'independent completion claim')
    if (completion['run_id'] != run_id or completion['code_ref'] != code_ref
            or completion['trace_ref'] != trace_ref or completion['bodies'] != bodies):
        raise ValueError('independent claim differs from run, source or body identity')
    if not isinstance(frames, list) or not frames:
        raise ValueError('recorded frames must be a nonempty sequence')
    previous, seen = -1., set()
    for frame in frames:
        if (not isinstance(frame, dict) or set(frame) - {'time', 'positions', 'orientations'}
                or not _number(frame.get('time')) or frame['time'] < 0 or frame['time'] <= previous):
            raise ValueError('recorded timestamps must be finite, nonnegative and strictly increasing')
        previous = frame['time']
        for field, width in (('positions', 3), ('orientations', 4)):
            values = frame.get(field, {})
            if not isinstance(values, dict) or set(values) - set(bodies):
                raise ValueError('recorded pose names must belong to the declared body identities')
            for name, vector in values.items():
                if (not isinstance(vector, list) or len(vector) != width
                        or not all(_number(value) for value in vector)):
                    raise ValueError('recorded pose must contain finite XYZ or WXYZ values')
                if width == 4 and abs(math.sqrt(sum(value * value for value in vector)) - 1.) > 1e-4:
                    raise ValueError('recorded world quaternion must be unit WXYZ')
                seen.add(name)
    if seen != set(bodies):
        raise ValueError('declared body identity lacks a recorded pose')
    first_step, last_step = completion['first_step'], completion['last_recorded_step']
    final_time, final_step = completion['actual_final_time_s'], completion['actual_final_step']
    if (type(completion['frame_count']) is not int or completion['frame_count'] != len(frames)
            or not _number(completion['last_recorded_time_s']) or completion['last_recorded_time_s'] != frames[-1]['time']
            or type(last_step) is not int or last_step < 0 or type(completion['complete']) is not bool
            or first_step is not None and (type(first_step) is not int or not 0 <= first_step <= last_step)
            or first_step is not None and ((len(frames) == 1 and first_step != last_step)
                                           or (len(frames) > 1 and first_step == last_step))
            or (final_time is None) != (final_step is None)
            or final_time is not None and (not _number(final_time) or type(final_step) is not int
                                            or final_time < frames[-1]['time'] or final_step < last_step)):
        raise ValueError('independent claim has invalid or mismatched recorded/final clock')
    if completion['complete'] and (final_time != frames[-1]['time'] or final_step != last_step):
        raise ValueError('complete recording requires the actual final endpoint clock and step')

    provenance = {'code_ref': code_ref, 'trace_ref': trace_ref, 'completion_ref': completion_ref,
                  'completion': completion, 'pose_schema': pose_schema, 'frames': frames}
    episode = 'recorded-poses::' + _digest({'run_id': run_id, 'bodies': bodies, 'code_ref': code_ref,
        'trace_ref': trace_ref, 'completion_ref': completion_ref, 'pose_schema': pose_schema,
        'asset_family': asset_family, 'implementation': implementation}) + '::' + run_id
    endpoint_id = _digest({'episode': episode, 'completion': completion, 'completion_ref': completion_ref,
                           'trace_ref': trace_ref, 'frames_sha256': _digest(frames)})

    def snapshot(frame, step):
        return {'step': step, 'time_s': frame['time'], 'complete': step is not None,
                'positions': deepcopy(frame.get('positions', {})),
                'orientations_wxyz': deepcopy(frame.get('orientations', {}))}

    initial = snapshot(frames[0], first_step)
    initial_valid = first_step == 0 and frames[0]['time'] == 0
    initial.update(scope='episode_initial' if initial_valid else 'recorded_first_frame',
                   valid_for_task_initial=initial_valid)
    terminal = snapshot(frames[-1], last_step)
    valid = completion['complete']
    return {'schema_version': 'terminal-evidence/0.3', 'implementation': implementation,
        'run': {'run_id': run_id, 'kind': 'recorded', 'branch': None, 'code_sha256': code_ref['sha256']},
        'endpoint': {'episode_id': episode, 'endpoint_id': endpoint_id, 'asset_family': asset_family,
                     'valid': valid, 'step': last_step, 'time_s': frames[-1]['time'],
                     'reasons': [] if valid else ['recorded_last_frame_not_verified_actual_endpoint']},
        'identities': {name: episode + '::' + name for name in bodies},
        'initial': initial, 'terminal': terminal, 'terminal_window': None, 'facts': {},
        'capture': {'owner': 'recorded.world_pose_file', 'scope': 'recorded_world_poses_without_contacts'},
        'provenance': provenance, 'source_refs': refs, 'process': 'not_evaluated', 'task_success': None}


def read_recorded_poses(root, *, run_id, bodies, code_ref, trace_ref, completion_ref,
                        pose_schema, source_refs=(), asset_family='recorded-world-poses'):
    """Verify source bytes and load an already-normalized JSON trace and claim.

    The completion file must itself contain the claim accepted by the pure-data
    adapter. The source code is hashed only, never imported or executed.
    """
    from validation.artifact_io import checked_ref, read_json

    root, extra = Path(root), list(source_refs)
    refs = [code_ref, trace_ref, completion_ref, *extra]
    for ref in refs:
        _ref(ref)
    paths = [checked_ref(root, ref) for ref in refs]
    frames, completion = read_json(paths[1]), read_json(paths[2])
    for ref in refs:
        checked_ref(root, ref)
    return adapt_recorded_poses(frames, run_id=run_id, bodies=bodies, code_ref=code_ref,
        trace_ref=trace_ref, completion_ref=completion_ref, completion=completion,
        pose_schema=pose_schema, source_refs=extra, asset_family=asset_family)


def validate_recorded_evidence(evidence):
    """Rebuild with the captured producer; callers verify historical bytes."""
    try:
        provenance = evidence['provenance']
        refs = evidence['source_refs']
        rebuilt = _build_record(provenance['frames'], run_id=evidence['run']['run_id'],
            bodies=provenance['completion']['bodies'], code_ref=provenance['code_ref'],
            trace_ref=provenance['trace_ref'], completion_ref=provenance['completion_ref'],
            completion=provenance['completion'], pose_schema=provenance['pose_schema'],
            source_refs=refs[3:], asset_family=evidence['endpoint']['asset_family'],
            implementation=evidence['implementation'])
        if _digest(rebuilt) != _digest(evidence):
            raise ValueError('recorded evidence envelope differs from its source-bound inputs')
        return rebuilt
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError('recorded evidence has missing or invalid provenance') from error


def _refs(refs):
    if not isinstance(refs, list) or not refs:
        raise ValueError('nonempty verified evidence references required')
    for ref in refs:
        _keys(ref, ('path', 'sha256'), 'verified reference')
        _text(ref['path'], 'reference path')
        _hash(ref['sha256'], 'reference hash')

def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def _vector(value, count, *, quaternion=False, target=False):
    if not isinstance(value, list) or len(value) != count or not all(_finite(item) for item in value):
        return None
    if not quaternion:
        return value
    norm = math.sqrt(sum(item * item for item in value))
    if abs(norm - 1) > (1e-9 if target else 1e-4) or norm == 0:
        return None
    return [item / norm for item in value]

def validate_terminal_evidence(evidence):
    evidence = _json(evidence)
    if isinstance(evidence, dict) and evidence.get('schema_version') == 'terminal-evidence/0.3':
        evidence = validate_recorded_evidence(evidence)
        endpoint = evidence['endpoint']
        return evidence, {key: endpoint[key] for key in ('episode_id', 'endpoint_id', 'asset_family', 'valid', 'time_s')}
    native_mujoco = isinstance(evidence, dict) and evidence.get('schema_version') == 'terminal-evidence/0.2'
    expected_owner = 'mujoco.public_state_and_contact' if native_mujoco else 'physpi_runtime.cli.cmd_query'
    if (not isinstance(evidence, dict) or evidence.get('schema_version') not in ('terminal-evidence/0.1', 'terminal-evidence/0.2')
            or evidence.get('capture', {}).get('owner') != expected_owner
            or evidence.get('capture', {}).get('scope') != 'initial_terminal_and_source_requested_terminal_window_only'
            or evidence.get('process') != 'not_evaluated' or evidence.get('task_success') is not None):
        raise ValueError('unsupported collector version, owner or fact scope')
    _refs(evidence.get('source_refs'))
    _text(evidence.get('implementation', {}).get('path'), 'collector implementation path')
    _hash(evidence['implementation'].get('sha256'), 'collector implementation hash')
    run, endpoint, identities = evidence['run'], evidence['endpoint'], evidence['identities']
    _hash(run.get('code_sha256'), 'runtime source hash')
    _text(run.get('run_id'), 'run ID')
    if native_mujoco:
        producer = evidence['capture'].get('producer')
        _refs([producer])
        if (run.get('kind') != 'native' or run.get('provider') != 'mujoco' or run.get('branch') is not None
                or producer != evidence['implementation'] or producer not in evidence['source_refs']
                or run['code_sha256'] != producer['sha256']):
            raise ValueError('native MuJoCo capture requires its exact public producer/source identity')
    elif run.get('kind') not in ('batch', 'resident') or (run['kind'] == 'batch' and run.get('branch') is not None):
        raise ValueError('invalid collector run/branch identity')
    if run['kind'] == 'resident':
        _text(run.get('branch'), 'resident branch')
    # Native collector IDs use ASCII-escaped JSON, unlike specification hashes.
    # Preserve that producer protocol for Unicode source paths and branch names.
    source_binding = {'index': evidence['source_refs'][0], 'code_sha256': run['code_sha256'], 'branch': run.get('branch')}
    source_id = hashlib.sha256(json.dumps(source_binding, ensure_ascii=True, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    episode = (f"native-mujoco::{source_id}::{run['run_id']}::native" if native_mujoco else
               f"native-physpi::{source_id}::{run['run_id']}::{run.get('branch') or 'batch'}")
    if endpoint.get('episode_id') != episode:
        raise ValueError('collector episode does not match its source/run/branch')
    _hash(endpoint.get('endpoint_id'), 'endpoint ID')
    _text(endpoint.get('asset_family'), 'asset family')
    if (type(endpoint.get('valid')) is not bool or not isinstance(endpoint.get('reasons'), list)
            or any(not isinstance(reason, str) or not reason for reason in endpoint['reasons'])
            or endpoint['valid'] != (not endpoint['reasons'])):
        raise ValueError('collector endpoint validity/reasons are inconsistent')
    if (not isinstance(identities, dict) or not identities
            or any(not isinstance(name, str) or not name or value != episode + '::' + name
                   for name, value in identities.items()) or len(set(identities.values())) != len(identities)):
        raise ValueError('native identities must be unique, exact run-scoped trace names')
    for name in ('initial', 'terminal'):
        snapshot = evidence[name]
        if (not isinstance(snapshot, dict) or type(snapshot.get('complete')) is not bool
                or type(snapshot.get('step')) is not int or snapshot['step'] < 0
                or not _finite(snapshot.get('time_s')) or snapshot['time_s'] < 0
                or not isinstance(snapshot.get('positions'), dict) or not isinstance(snapshot.get('orientations_wxyz'), dict)):
            raise ValueError('invalid collector snapshot clock or pose structure')
        if any(set(snapshot[field]) - set(identities) for field in ('positions', 'orientations_wxyz')):
            raise ValueError('snapshot contains a body outside native identity scope')
    initial, final = evidence['initial'], evidence['terminal']
    if (endpoint.get('step') != final['step'] or endpoint.get('time_s') != final['time_s']
            or endpoint['valid'] and not final['complete'] or initial['step'] > final['step']
            or initial['time_s'] > final['time_s']):
        raise ValueError('collector endpoint and recorded boundary disagree')
    initial_valid = initial['complete'] and initial['step'] == 0 and initial['time_s'] == 0 and initial.get('scope') == 'episode_initial'
    if type(initial.get('valid_for_task_initial')) is not bool or initial['valid_for_task_initial'] != initial_valid:
        raise ValueError('initial-state admission is inconsistent')
    if not isinstance(evidence.get('facts'), dict):
        raise ValueError('collector numerical fact record required')
    projected = {key: endpoint[key] for key in ('episode_id', 'endpoint_id', 'asset_family', 'valid', 'time_s')}
    return evidence, projected
