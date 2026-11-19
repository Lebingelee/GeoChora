"""Explicit, source-bound numeric measurements for original-task review.

Callers supply measurement requests and verify referenced file bytes. Outputs
describe individual measurements, never an AST, terminal verdict or task success.
The original-task judge still checks parameter interpretation and applicability.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import numpy as np

from validation.geometry import box_piece, hull2, interior_margin2, separation
from validation.protocol import _json, _keys, _text, _digest, _pointer
from validation.adapters.recorded import validate_terminal_evidence, _refs, _vector, _finite
from validation.geometry import quat_wxyz_to_matrix

_METHODS = {
    'center_ordered/v1': {'arity': 2, 'parameters': {'window_seconds': {'type': 'number', 'minimum': 0}, 'axis': {'enum': ['x', 'y', 'z']}, 'minimum_gap_m': {'type': 'number', 'minimum': 0}}, 'required': ['axis', 'minimum_gap_m']},
    'initial_displacement_within/v1': {'arity': 1, 'parameters': {'maximum_translation_m': {'type': 'number', 'minimum': 0}}, 'required': ['maximum_translation_m']},
    'sampled_pose_stable/v1': {'arity': 1, 'parameters': {'window_seconds': {'type': 'number', 'exclusiveMinimum': 0}, 'maximum_translation_m': {'type': 'number', 'minimum': 0}, 'maximum_rotation_deg': {'type': 'number', 'minimum': 0, 'maximum': 180}}, 'required': ['window_seconds', 'maximum_translation_m', 'maximum_rotation_deg']},
    'orientation_matches/v1': {'arity': 1, 'parameters': {'window_seconds': {'type': 'number', 'minimum': 0}, 'target_w': {'type': 'number'}, 'target_x': {'type': 'number'}, 'target_y': {'type': 'number'}, 'target_z': {'type': 'number'}, 'maximum_angle_deg': {'type': 'number', 'minimum': 0, 'maximum': 180}}, 'required': ['target_w', 'target_x', 'target_y', 'target_z', 'maximum_angle_deg']},
    'orientation_unchanged/v1': {'arity': 1, 'parameters': {'maximum_angle_deg': {'type': 'number', 'minimum': 0, 'maximum': 180}}, 'required': ['maximum_angle_deg']},
    'world_coordinate_bound/v1': {'arity': 1, 'parameters': {'feature': {'enum': ['source_object_center', 'collision_min', 'collision_max']}, 'axis': {'enum': ['x', 'y', 'z']}, 'bound': {'enum': ['lower', 'upper']}, 'value_m': {'type': 'number'}, 'inclusive': {'type': 'boolean'}, 'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': ['feature', 'axis', 'bound', 'value_m', 'inclusive']},
    'axis_angle_to_world/v1': {'arity': 1, 'parameters': {'object_axis': {'enum': ['x', 'y', 'z', '-x', '-y', '-z']}, 'world_axis': {'enum': ['x', 'y', 'z', '-x', '-y', '-z']}, 'direction': {'enum': ['directed', 'undirected']}, 'maximum_angle_deg': {'type': 'number', 'minimum': 0, 'maximum': 180}, 'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': ['object_axis', 'world_axis', 'direction', 'maximum_angle_deg']},
    'axis_parallel/v1': {'arity': 2, 'parameters': {'window_seconds': {'type': 'number', 'minimum': 0}, 'object_axis': {'enum': ['x', 'y', 'z']}, 'region_axis': {'enum': ['x', 'y', 'z']}, 'maximum_angle_deg': {'type': 'number', 'minimum': 0, 'maximum': 90}}, 'required': ['object_axis', 'region_axis', 'maximum_angle_deg']},
    'collision_footprint_inside_region/v1': {'arity': 2, 'parameters': {'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': []},
    'collision_footprint_inside_region/v2': {'arity': 2, 'parameters': {'boundary': {'enum': ['open', 'closed']}, 'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': ['boundary']},
    'no_robot_contact/v1': {'arity': 2, 'parameters': {'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': []},
    'no_contact_between/v1': {'arity': 2, 'parameters': {'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': []},
    'released_from_gripper/v1': {'arity': 2, 'parameters': {}, 'required': []},
    'physically_supported_by/v1': {'arity': 2, 'parameters': {}, 'required': []},
    'physically_supported_by/v2': {'arity': 2, 'parameters': {'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': []},
    'not_supported_by/v1': {'arity': 2, 'parameters': {'support_path': {'enum': ['direct', 'any']}, 'window_seconds': {'type': 'number', 'minimum': 0}}, 'required': ['support_path']},
}

POSE_METHODS = frozenset(['center_ordered/v1', 'initial_displacement_within/v1', 'sampled_pose_stable/v1', 'orientation_matches/v1', 'orientation_unchanged/v1'])
SUPPORTED_METHODS = frozenset(_METHODS)

_REFERENCE_KINDS = {
    'center_ordered/v1': {'source_object_center'},
    'sampled_pose_stable/v1': {'source_object_center', 'source_pose_origin'},
    'orientation_matches/v1': {'source_orientation'},
    'initial_displacement_within/v1': {'source_object_center', 'source_pose_origin'},
}


def _admit_numeric_evidence(context, evidence, supplied, documents, evidence_refs, scope):
    """Validate loaded evidence. File hashes and importer truth remain caller-owned.

    Every derived body, region and entity scope cites a frozen source pointer
    and native evidence. A hashed producer and all cited files must be in the
    caller-verified closure. Unknown fields are rejected, not silently ignored.
    """
    if supplied is None:
        return None
    packet = _json(supplied)
    _keys(packet, ('schema_version', 'requests_sha256', 'source_sha256', 'episode_id', 'endpoint_id',
                  'producer', 'basis_refs', 'bodies', 'scopes', 'regions', 'samples', 'contact_samples'), 'numeric evidence')
    if (packet['schema_version'] != 'terminal-numeric-evidence/0.2'
            or packet['requests_sha256'] != context['requests_sha256']
            or packet['source_sha256'] != context['source_ref']['record_sha256']
            or any(packet[key] != evidence['endpoint'][key] for key in ('episode_id', 'endpoint_id'))):
        raise ValueError('numeric evidence differs from source/requests/endpoint')
    _refs([packet['producer']])
    closure = {(r['path'], r['sha256']) for r in [*evidence['source_refs'], *evidence_refs]}
    dependencies = {r['path']: r['file_sha256'] for r in context['source_ref']['dependencies']}
    source_path = context['source_ref']['path']
    frozen = set(dependencies.items()) | {r for r in closure if r[0] == source_path}
    native = closure - frozen - {(packet['producer'].get('path'), packet['producer'].get('sha256'))}

    def refs(items):
        _refs(items)
        pairs = {(r['path'], r['sha256']) for r in items}
        if (len(pairs) != len(items) or len({p for p, _ in pairs}) != len(pairs)
                or not pairs <= closure):
            raise ValueError('numeric references must be unique and inside verified closure')
        return pairs

    refs([packet['producer']])
    packet_refs = refs(packet['basis_refs'])
    if not packet_refs & native:
        raise ValueError('numeric evidence requires current native evidence')

    def basis(item):
        bound_refs = refs(item['basis_refs'])
        if not bound_refs <= packet_refs or not bound_refs & native:
            raise ValueError('derived numeric binding lacks its native basis')
        if not isinstance(item['source_basis'], list) or not item['source_basis']:
            raise ValueError('numeric binding requires frozen source pointers')
        for pointer in item['source_basis']:
            _keys(pointer, ('path', 'pointer'), 'numeric source basis')
            path = pointer['path']
            if not any(p == path and (p, sha) in frozen for p, sha in bound_refs):
                raise ValueError('numeric source pointer lacks its frozen file reference')
            document = context['source'] if path == source_path else documents.get(path, {}).get('document')
            if document is None:
                raise ValueError('numeric source dependency must be loaded')
            _pointer(document, pointer['pointer'])

    for field in ('bodies', 'scopes', 'regions'):
        if not isinstance(packet[field], dict):
            raise ValueError('numeric bindings must be mappings')
    allowed_ids = {identity for key in scope.values() for identity in key['arguments'] if isinstance(identity, str)}
    for name, body in packet['bodies'].items():
        _text(name, 'native body name')
        _keys(body, ('source_basis', 'basis_refs', 'boxes', 'enclosing_radius_m',
                     'source_center_body_m', 'source_orientation_body_wxyz'), 'numeric body')
        basis(body)
        if not isinstance(body['boxes'], list):
            raise ValueError('collision boxes must be a list')
        for box in body['boxes']:
            _keys(box, ('half_extents_m', 'center_body_m', 'orientation_body_wxyz'), 'collision box')
            if (_vector(box['half_extents_m'], 3) is None or min(box['half_extents_m']) <= 0
                    or _vector(box['center_body_m'], 3) is None
                    or _vector(box['orientation_body_wxyz'], 4, quaternion=True, target=True) is None):
                raise ValueError('collision box requires explicit finite metric shape/frame')
        radius = body['enclosing_radius_m']
        if radius is not None and (not _finite(radius) or radius <= 0):
            raise ValueError('collision enclosure must have positive finite radius')
        for field, width in (('source_center_body_m', 3), ('source_orientation_body_wxyz', 4)):
            if body[field] is not None and _vector(body[field], width, quaternion=width == 4, target=True) is None:
                raise ValueError('invalid explicit source reference frame')
    for identity, binding in packet['scopes'].items():
        _keys(binding, ('body_names', 'complete', 'contact_only_retention', 'source_basis', 'basis_refs'), 'native entity scope')
        basis(binding)
        names = binding['body_names']
        if (identity not in allowed_ids or not isinstance(names, list) or not names or len(set(names)) != len(names)
                or any(name not in packet['bodies'] for name in names) or type(binding['complete']) is not bool):
            raise ValueError('numeric scope has foreign/duplicate bodies or unresolved completeness')
        if binding['contact_only_retention'] is not None and type(binding['contact_only_retention']) is not bool:
            raise ValueError('retention mechanism scope must be explicit true/false or unknown')
        tracked = {value: name for name, value in evidence['identities'].items()}
        if identity in tracked and names != [tracked[identity]]:
            raise ValueError('tracked native body cannot be rebound to another scope')
    for identity, region in packet['regions'].items():
        _keys(region, ('native_body', 'origin_m', 'orientation_wxyz', 'half_extents_xy_m',
                       'source_basis', 'basis_refs'), 'numeric region')
        basis(region)
        if (identity not in allowed_ids or region['native_body'] is not None and region['native_body'] not in packet['bodies']
                or _vector(region['origin_m'], 3) is None
                or _vector(region['orientation_wxyz'], 4, quaternion=True, target=True) is None
                or _vector(region['half_extents_xy_m'], 2) is None or min(region['half_extents_xy_m']) <= 0):
            raise ValueError('region requires explicit source frame and positive rectangular bounds')
    if not isinstance(packet['samples'], list) or len(packet['samples']) > 512:
        raise ValueError('numeric samples must be bounded')
    clocks = set()
    for sample in packet['samples']:
        _keys(sample, ('step', 'time_s', 'positions', 'orientations_wxyz'), 'numeric pose sample')
        if (type(sample['step']) is not int or sample['step'] < 0 or not _finite(sample['time_s'])
                or sample['time_s'] < 0 or sample['step'] in clocks):
            raise ValueError('numeric pose sample clock is invalid or duplicate')
        clocks.add(sample['step'])
        for field, size in (('positions', 3), ('orientations_wxyz', 4)):
            if (not isinstance(sample[field], dict) or set(sample[field]) - set(packet['bodies'])
                    or any(_vector(value, size, quaternion=size == 4) is None for value in sample[field].values())):
                raise ValueError('numeric poses require bound bodies and finite unit-WXYZ values')
    if not isinstance(packet['contact_samples'], list) or len(packet['contact_samples']) > 512:
        raise ValueError('numeric contacts must be bounded')
    seen = set()
    for sample in packet['contact_samples']:
        _keys(sample, ('step', 'time_s', 'phase', 'body_names', 'complete', 'points',
                       'force_scope', 'support_paths_complete', 'gravity_world_m_s2'), 'contact sample')
        if (type(sample['step']) is not int or sample['step'] < 0 or sample['step'] in seen
                or not _finite(sample['time_s']) or sample['time_s'] < 0
                or sample['phase'] not in ('current_geometry', 'current_solved_state')
                or type(sample['complete']) is not bool or type(sample['support_paths_complete']) is not bool
                or sample['force_scope'] not in ('unavailable', 'all_contact_forces')
                or sample['support_paths_complete'] and (not sample['complete'] or sample['force_scope'] != 'all_contact_forces')
                or sample['phase'] != 'current_solved_state' and sample['force_scope'] != 'unavailable'
                or not isinstance(sample['body_names'], list) or len(set(sample['body_names'])) != len(sample['body_names'])
                or set(sample['body_names']) - set(packet['bodies'])
                or not isinstance(sample['points'], list)):
            raise ValueError('invalid current contact phase, identity, completeness or clock')
        if sample['support_paths_complete'] and (set(sample['body_names']) != set(packet['bodies'])
                or not set(evidence['identities']) <= set(sample['body_names'])):
            raise ValueError('complete support paths cannot omit a bound or recorded native body')
        seen.add(sample['step'])
        gravity = sample['gravity_world_m_s2']
        if gravity is not None and (_vector(gravity, 3) is None or np.linalg.norm(gravity) == 0):
            raise ValueError('load inference needs finite nonzero gravity')
        for point in sample['points']:
            _keys(point, ('bodies', 'distance_m', 'position_m', 'force_on_first_world_n'), 'current contact point')
            if (not isinstance(point['bodies'], list) or len(point['bodies']) != 2
                    or len(set(point['bodies'])) != 2 or any(n not in sample['body_names'] for n in point['bodies'])
                    or not _finite(point['distance_m']) or _vector(point['position_m'], 3) is None
                    or point['force_on_first_world_n'] is not None and _vector(point['force_on_first_world_n'], 3) is None
                    or sample['force_scope'] == 'all_contact_forces' and point['force_on_first_world_n'] is None
                    or sample['force_scope'] == 'unavailable' and point['force_on_first_world_n'] is not None):
                raise ValueError('contact point has incomplete identity/position/current force')
    return packet

def _source_documents(context, evidence, supplied):
    """Admit caller-verified loaded documents, without claiming to hash file bytes."""
    if not isinstance(supplied, (list, tuple)):
        raise ValueError('source_documents must be a sequence of verified loaded documents')
    source = context['source_ref']
    dependencies = {item['path']: item['file_sha256'] for item in source['dependencies']}
    result = {}
    for item in _json(list(supplied)):
        _keys(item, ('path', 'sha256', 'document'), 'loaded source document')
        ref = {key: item[key] for key in ('path', 'sha256')}
        _refs([ref])
        if item['path'] in result or ref not in evidence['source_refs']:
            raise ValueError('loaded source document is duplicate or absent from collector source references')
        if item['path'] == source['path']:
            if _digest(item['document']) != source['record_sha256']:
                raise ValueError('loaded original source differs from the source record')
        elif dependencies.get(item['path']) != item['sha256']:
            raise ValueError('loaded resource document is outside the exact frozen source dependencies')
        result[item['path']] = item
    return result

def _reference_bindings(context, evidence, supplied, documents, evidence_refs, scope):
    """Check caller-derived rigid references against this source, run and atom scope.

    The outer adapter verifies file bytes and derives the rigid offset/frame from
    source/import evidence. This function checks the closed references and source
    pointers; it does not reinterpret asset geometry or certify that derivation.
    """
    if supplied is None:
        return None, {}
    packet = _json(supplied)
    _keys(packet, ('requests_sha256', 'source_sha256', 'episode_id', 'entries'), 'reference bindings')
    source = context['source_ref']
    if (packet['requests_sha256'] != context['requests_sha256'] or packet['source_sha256'] != source['record_sha256']
            or packet['episode_id'] != evidence['endpoint']['episode_id'] or not isinstance(packet['entries'], list)):
        raise ValueError('reference bindings differ from the source/requests/episode')
    dependencies = {item['path']: item['file_sha256'] for item in source['dependencies']}
    closure = {(ref['path'], ref['sha256']) for ref in [*evidence['source_refs'], *evidence_refs]}
    frozen = set(dependencies.items()) | {ref for ref in closure if ref[0] == source['path']}
    native_refs = {ref for ref in closure if ref[0] != source['path'] and ref[0] not in dependencies}
    native_ids = set(evidence['identities'].values())
    allowed = {(key['request_id'], identity): key['predicate'] for key in scope.values()
               if key['predicate'] in _REFERENCE_KINDS for identity in key['arguments'] if isinstance(identity, str)}
    bound = {}
    for entry in packet['entries']:
        if not isinstance(entry, dict):
            raise ValueError('reference binding entry must be an object')
        orientation = entry.get('reference_kind') == 'source_orientation'
        field = 'orientation_body_wxyz' if orientation else 'offset_body_m'
        _keys(entry, ('request_id', 'entity_id', 'reference_kind', 'source_basis', 'basis_refs', field), 'reference binding entry')
        _text(entry['request_id'], 'reference node ID')
        _text(entry['entity_id'], 'reference native entity ID')
        identity = entry['request_id'], entry['entity_id']
        predicate_id = allowed.get(identity)
        if (identity in bound or entry['entity_id'] not in native_ids or predicate_id is None
                or not isinstance(entry['reference_kind'], str)
                or entry['reference_kind'] not in _REFERENCE_KINDS[predicate_id]):
            raise ValueError('reference binding has duplicate or foreign node/entity/reference meaning')
        if _vector(entry[field], 4 if orientation else 3, quaternion=orientation, target=orientation) is None:
            raise ValueError('reference offset must be finite XYZ meters or an explicit unit WXYZ orientation')
        _refs(entry['basis_refs'])
        refs = {(ref['path'], ref['sha256']) for ref in entry['basis_refs']}
        if (len(refs) != len(entry['basis_refs']) or len({path for path, _ in refs}) != len(refs)
                or not refs <= closure | frozen or not refs & native_refs
                or any(path in dependencies and sha != dependencies[path] for path, sha in refs)):
            raise ValueError('reference basis must use exact frozen source and current native evidence references')
        basis = entry['source_basis']
        if not isinstance(basis, list) or not basis:
            raise ValueError('reference binding requires explicit source basis pointers')
        seen = set()
        for item in basis:
            _keys(item, ('path', 'pointer'), 'reference source basis')
            _text(item['path'], 'reference source path')
            _text(item['pointer'], 'reference source pointer')
            key = item['path'], item['pointer']
            if key in seen or not any(path == item['path'] and (path, sha) in frozen for path, sha in refs):
                raise ValueError('reference source basis is duplicate or lacks its frozen document reference')
            seen.add(key)
            if item['path'] == source['path']:
                document = context['source']
            elif item['path'] in dependencies and item['path'] in documents:
                document = documents[item['path']]['document']
            else:
                raise ValueError('reference source basis requires the original source or a loaded frozen dependency')
            _pointer(document, item['pointer'])
        bound[identity] = entry
    return packet, bound

def _angle(first, second):
    sign = 1 if sum(a * b for a, b in zip(first, second)) >= 0 else -1
    second = [sign * value for value in second]
    return math.degrees(4 * math.atan2(math.dist(first, second), math.sqrt(sum((a + b) ** 2 for a, b in zip(first, second)))))

def _quaternion_product(first, second):
    w, x, y, z = first
    a, b, c, d = second
    return [w*a-x*b-y*c-z*d, w*b+x*a+y*d-z*c,
            w*c-x*d+y*a+z*b, w*d+x*c-y*b+z*a]

def _reference_position(sample, name, entry):
    position = _vector(sample.get('positions', {}).get(name), 3)
    if position is None:
        return None
    offset = entry['offset_body_m']
    if any(offset):
        orientation = _vector(sample.get('orientations_wxyz', {}).get(name), 4, quaternion=True)
        if orientation is None:
            return None
        conjugate = [orientation[0], *[-value for value in orientation[1:]]]
        offset = _quaternion_product(_quaternion_product(orientation, [0., *offset]), conjugate)[1:]
    return _vector([value + delta for value, delta in zip(position, offset)], 3)

def _samples(context, evidence, seconds, source_documents):
    if seconds == 0:
        return [evidence['terminal']], None
    tail = evidence.get('terminal_window')
    if not isinstance(tail, dict) or tail.get('complete') is not True or tail.get('reasons') != []:
        return [], 'complete_source_requested_window_unavailable'
    requested, cadence = tail.get('requested', {}), tail.get('sample_dt_seconds')
    if not isinstance(requested, dict) or requested.get('source_ref') not in evidence['source_refs']:
        return [], 'window_source_reference_unavailable'
    ref = requested['source_ref']
    source = context['source_ref']
    if ref['path'] == source['path']:
        document = context['source']
        loaded = source_documents.get(ref['path'])
        if loaded is not None and loaded['sha256'] != ref['sha256']:
            return [], 'window_source_document_hash_mismatch'
    else:
        dependencies = {item['path']: item['file_sha256'] for item in source['dependencies']}
        if dependencies.get(ref['path']) != ref['sha256']:
            return [], 'window_reference_outside_frozen_dependencies'
        loaded = source_documents.get(ref['path'])
        if loaded is None or loaded['sha256'] != ref['sha256']:
            return [], 'window_source_document_unavailable'
        document = loaded['document']
    try:
        original = _pointer(document, requested['pointer'])
        if 'seconds' in requested:
            duration = requested['seconds']
            matches = _finite(original) and original == duration == seconds
        else:
            duration = (requested['end_frame'] - requested['start_frame']) * requested['sample_dt_seconds']
            matches = original == [requested['start_frame'], requested['end_frame']] and math.isclose(duration, seconds, abs_tol=1e-9, rel_tol=0)
        if 'sample_dt_seconds' in requested:
            matches = matches and _pointer(document, requested['sample_dt_pointer']) == requested['sample_dt_seconds'] == cadence
    except (KeyError, TypeError, ValueError):
        return [], 'window_source_requirement_unavailable'
    if not matches:
        return [], 'window_differs_from_frozen_source_requirement'
    if not _finite(cadence) or cadence <= 0:
        return [], 'original_sample_grid_unavailable'
    native_fallback = 'sample_dt_seconds' not in requested
    if native_fallback:
        recorded_cadence = tail.get('recorded_sample_dt_seconds')
        if not _finite(recorded_cadence) or recorded_cadence != cadence:
            return [], 'native_fallback_cadence_mismatch'
        if 'sample_dt_pointer' in requested:
            return [], 'window_source_requirement_unavailable'
    start, end = tail.get('start_time_s'), tail.get('end_time_s')
    if (not _finite(start) or not _finite(end) or start < 0 or end != evidence['terminal']['time_s']
            or not math.isclose(end - start, seconds, abs_tol=1e-9, rel_tol=0)):
        return [], 'requested_terminal_window_boundary_mismatch'
    samples, intervals = tail.get('samples'), seconds / cadence
    if (not isinstance(samples, list) or not 2 <= len(samples) <= 512
            or not math.isclose(intervals, round(intervals), abs_tol=1e-7, rel_tol=0)
            or len(samples) != round(intervals) + 1):
        return [], 'requested_sample_grid_incomplete_or_over_budget'
    steps = []
    for index, sample in enumerate(samples):
        if (not isinstance(sample, dict) or sample.get('complete') is not True or type(sample.get('step')) is not int
                or not isinstance(sample.get('positions'), dict) or not isinstance(sample.get('orientations_wxyz'), dict)
                or not _finite(sample.get('time_s'))
                or not math.isclose(sample['time_s'], start + index * cadence, abs_tol=1e-9, rel_tol=0)):
            return [], 'requested_sample_grid_incomplete'
        steps.append(sample['step'])
    if (steps[-1] != evidence['terminal']['step'] or steps[0] < 0
            or any(b <= a or b - a != steps[1] - steps[0] for a, b in zip(steps, steps[1:]))
            or samples[-1].get('positions') != evidence['terminal']['positions']
            or samples[-1].get('orientations_wxyz') != evidence['terminal']['orientations_wxyz']):
        return [], 'sampled_endpoint_or_step_grid_mismatch'
    if native_fallback:
        projection = tail.get('grid_projection')
        # With no explicit source cadence, the native output grid is the only
        # admitted fallback. It cannot be silently thinned or interpolated.
        if (not isinstance(projection, dict)
                or projection.get('method') != 'unique_exact_source_output_times'
                or projection.get('clock_roundoff_tolerance_s') != 1e-9
                or projection.get('recorded_cadences_per_source_sample') != 1
                or projection.get('selected_steps') != steps
                or projection.get('missing_or_ambiguous_required_times_s') != []
                or projection.get('excluded_intermediate_sample_count') != 0
                or projection.get('proves_continuous_stability') is not False
                or tail.get('recorded_sample_count') != len(samples)):
            return [], 'native_fallback_grid_projection_unavailable_or_inconsistent'
    return samples, None

def _measure_pose(request, context, evidence, source_documents, reference_bindings):
    predicate_id, args, params = request['predicate'], request['arguments'], request['params']
    native = {identity: name for name, identity in evidence['identities'].items()}
    if any(identity not in native for identity in args):
        return None, {'reason': 'runtime_identity_unverified'}
    names = [native[identity] for identity in args]
    samples, reason = _samples(context, evidence, params.get('window_seconds', 0), source_documents)
    if reason:
        return None, {'reason': reason}
    references = [reference_bindings.get((request['request_id'], identity)) for identity in args]
    if predicate_id in _REFERENCE_KINDS and any(entry is None for entry in references):
        return None, {'reason': 'source_reference_binding_unavailable'}
    if predicate_id == 'center_ordered/v1':
        positions = [[_reference_position(sample, name, entry) for name, entry in zip(names, references)] for sample in samples]
        if any(any(value is None for value in row) for row in positions):
            return None, {'reason': 'world_center_samples_unavailable'}
        axis, gap = 'xyz'.index(params['axis']), params['minimum_gap_m']
        measured = [row[1][axis] - row[0][axis] for row in positions]
        return all(value > 0 if gap == 0 else value >= gap for value in measured), {
            'minimum_measured_gap_m': min(measured), 'source_minimum_gap_m': gap, 'world_axis': params['axis'], 'sample_count': len(samples)}
    if predicate_id == 'initial_displacement_within/v1':
        if evidence['initial']['valid_for_task_initial'] is not True:
            return None, {'reason': 'same_episode_initial_pose_unavailable'}
        initial = _reference_position(evidence['initial'], names[0], references[0])
        terminal = _reference_position(evidence['terminal'], names[0], references[0])
        if initial is None or terminal is None:
            return None, {'reason': 'initial_or_terminal_reference_position_unavailable'}
        distance = math.dist(initial, terminal)
        return distance <= params['maximum_translation_m'], {
            'initial_displacement_m': distance, 'source_maximum_translation_m': params['maximum_translation_m'],
            'initial_reference_position_m': initial, 'terminal_reference_position_m': terminal,
            'scope': 'endpoint_displacement_only_not_movement_history'}
    quaternions = [_vector(sample.get('orientations_wxyz', {}).get(names[0]), 4, quaternion=True) for sample in samples]
    if any(value is None for value in quaternions):
        return None, {'reason': 'unit_world_quaternion_samples_unavailable'}
    if predicate_id == 'sampled_pose_stable/v1':
        positions = [_reference_position(sample, names[0], references[0]) for sample in samples]
        if any(value is None for value in positions):
            return None, {'reason': 'world_position_samples_unavailable'}
        translation = max(math.dist(a, b) for a in positions for b in positions)
        rotation = max(_angle(a, b) for a in quaternions for b in quaternions)
        return translation <= params['maximum_translation_m'] and rotation <= params['maximum_rotation_deg'], {
            'maximum_pairwise_translation_m': translation, 'maximum_pairwise_rotation_deg': rotation,
            'source_limits': deepcopy(params), 'sample_count': len(samples), 'scope': 'sampled_stability_only'}
    if predicate_id == 'orientation_matches/v1':
        target = _vector([params['target_' + axis] for axis in 'wxyz'], 4, quaternion=True, target=True)
        if target is None:
            return None, {'reason': 'source_target_quaternion_is_not_unit_wxyz'}
        local = _vector(references[0]['orientation_body_wxyz'], 4, quaternion=True, target=True)
        quaternions = [_quaternion_product(value, local) for value in quaternions]
    else:
        if evidence['initial']['valid_for_task_initial'] is not True:
            return None, {'reason': 'same_episode_initial_pose_unavailable'}
        target = _vector(evidence['initial']['orientations_wxyz'].get(names[0]), 4, quaternion=True)
        if target is None:
            return None, {'reason': 'initial_unit_world_quaternion_unavailable'}
    angle = max(_angle(value, target) for value in quaternions)
    return angle <= params['maximum_angle_deg'], {'maximum_angle_deg': angle,
        'source_maximum_angle_deg': params['maximum_angle_deg'], 'sample_count': len(samples), 'quaternion_order': 'wxyz'}

def _rotation(q):
    return quat_wxyz_to_matrix(np.asarray(q, dtype=float))

def _pose(sample, name):
    p, q = sample['positions'].get(name), sample['orientations_wxyz'].get(name)
    return None if p is None or q is None else (np.asarray(p, float), _rotation(q))

def _pieces(packet, sample, names):
    pieces = []
    for name in names:
        pose, body = _pose(sample, name), packet['bodies'][name]
        if pose is None or not body['boxes']:
            return None
        p, r = pose
        for box in body['boxes']:
            half = np.asarray(box['half_extents_m'])
            pieces.append(box_piece([-half, half]).transformed(
                r @ _rotation(box['orientation_body_wxyz']), p + r @ box['center_body_m']))
    return pieces

def _axis(name):
    v = np.zeros(3)
    v['xyz'.index(name[-1])] = -1 if name.startswith('-') else 1
    return v

def _region_pose(packet, sample, identity):
    region = packet['regions'].get(identity)
    if region is None:
        return None
    p, r = np.asarray(region['origin_m']), _rotation(region['orientation_wxyz'])
    if region['native_body'] is not None:
        pose = _pose(sample, region['native_body'])
        if pose is None:
            return None
        origin, orientation = pose
        p, r = origin + orientation @ p, orientation @ r
    return p, r

def _source_pose(packet, sample, names):
    if len(names) != 1:
        return None
    pose, body = _pose(sample, names[0]), packet['bodies'][names[0]]
    if pose is None:
        return None
    return pose, body

def _clearance(packet, sample, first, second):
    """Positive conservative enclosure/SAT gap proves separation, overlap does not."""
    margins = []
    for a in first:
        for b in second:
            if a == b:
                return None
            pa, pb = _pose(sample, a), _pose(sample, b)
            if pa is None or pb is None:
                return None
            aa, bb = _pieces(packet, sample, [a]), _pieces(packet, sample, [b])
            if aa is not None and bb is not None:
                margins.append(min(separation(x, y) for x in aa for y in bb))
            else:
                ra, rb = packet['bodies'][a]['enclosing_radius_m'], packet['bodies'][b]['enclosing_radius_m']
                if ra is None or rb is None:
                    return None
                margins.append(float(np.linalg.norm(pa[0] - pb[0]) - ra - rb))
    return min(margins) if margins else None

def _pair_contacts(contact, first, second):
    return [] if contact is None else [point for point in contact['points'] if
        point['bodies'][0] in first and point['bodies'][1] in second or
        point['bodies'][1] in first and point['bodies'][0] in second]

def _nonzero_force(point):
    force = point['force_on_first_world_n']
    return force is not None and any(value != 0 for value in force)

def _contact_value(predicate_id, params, contact, first, second):
    pairs = _pair_contacts(contact, first, second)
    touching = any(point['distance_m'] <= 0 for point in pairs)
    force_without_touch = any(point['distance_m'] > 0 and _nonzero_force(point) for point in pairs)
    if predicate_id in ('no_contact_between/v1', 'no_robot_contact/v1', 'released_from_gripper/v1'):
        # One observed touch refutes absence even if the contact inventory is
        # partial. It need not retain the object, so release remains unknown.
        if touching:
            return None if predicate_id == 'released_from_gripper/v1' else False, 'current_contact_geometry'
        if force_without_touch:
            return None, 'current_force_without_touch_semantics_unavailable'
    if (contact is None or not contact['complete']
            or not set(first + second) <= set(contact['body_names'])):
        return None, 'complete_current_contact_evidence_unavailable'
    if predicate_id in ('no_contact_between/v1', 'no_robot_contact/v1', 'released_from_gripper/v1'):
        return True, 'current_contact_geometry'
    if (contact['phase'] != 'current_solved_state' or contact['force_scope'] != 'all_contact_forces'
            or contact['gravity_world_m_s2'] is None):
        return None, 'current_load_evidence_unavailable'
    if force_without_touch:
        return None, 'current_force_without_touch_semantics_unavailable'
    up = -np.asarray(contact['gravity_world_m_s2'], float)
    up /= np.linalg.norm(up)
    # Collapse the complete source entity scopes before summing forces. Splitting
    # one support (or target) across native bodies must not change net bearing.
    target, support = ('target',), ('support',)
    def entity(name):
        return target if name in first else support if name in second else ('body', name)
    loads = {}
    for point in contact['points']:
        if point['distance_m'] > 0:
            continue  # Unknown force semantics are checked before proving absence below.
        a, b = map(entity, point['bodies'])
        if a == b:
            continue
        load = float(np.dot(point['force_on_first_world_n'], up))
        if a > b:
            a, b, load = b, a, -load
        loads[a, b] = loads.get((a, b), 0.) + load
    edges = set()
    for (a, b), load in loads.items():
        if load > 0:
            edges.add((b, a))  # Force on a from b opposes gravity.
        elif load < 0:
            edges.add((a, b))
    direct = (support, target) in edges
    if predicate_id == 'not_supported_by/v1' and params['support_path'] == 'direct':
        return not direct, 'current_direct_contact_load'
    if direct:
        return predicate_id != 'not_supported_by/v1', 'current_direct_contact_load'
    if any(point['distance_m'] > 0 and _nonzero_force(point) for point in contact['points']):
        return None, 'current_force_without_touch_path_semantics_unavailable'
    # An upward contact graph only establishes possible indirect paths, not load
    # attribution. Absence can exclude them only with an explicit full load scope.
    reached, pending = {support}, [support]
    while pending:
        body = pending.pop()
        for lower, upper in edges:
            if lower == body and upper not in reached:
                reached.add(upper)
                pending.append(upper)
    if target not in reached and contact['support_paths_complete']:
        return predicate_id == 'not_supported_by/v1', 'complete_contact_load_path_absence'
    return None, 'indirect_load_attribution_or_complete_scope_unavailable'

def _measure_numeric(request, packet, source_samples):
    if packet is None:
        return None, {'reason': 'source_bound_numeric_evidence_unavailable'}
    predicate_id, params, args = request['predicate'], request['params'], request['arguments']
    scopes = [packet['scopes'].get(identity) for identity in args]
    if scopes[0] is None or not scopes[0]['complete']:
        return None, {'reason': 'complete_object_collision_scope_unavailable'}
    first = scopes[0]['body_names']
    regions = predicate_id.startswith('collision_footprint_inside_region/') or predicate_id == 'axis_parallel/v1'
    if len(args) > 1 and not regions and (scopes[1] is None or not scopes[1]['complete']):
        return None, {'reason': 'complete_other_object_or_robot_scope_unavailable'}
    second = scopes[1]['body_names'] if len(args) > 1 and scopes[1] is not None else []
    if second and set(first) & set(second):
        return None, {'reason': 'overlapping_object_scopes'}
    if predicate_id == 'released_from_gripper/v1' and scopes[1]['contact_only_retention'] is not True:
        return None, {'reason': 'complete_contact_only_retention_scope_unavailable'}
    by_step = {s['step']: s for s in packet['samples']}
    contacts = {s['step']: s for s in packet['contact_samples']}
    values, observations = [], []
    for original in source_samples:
        sample = by_step.get(original['step'])
        if sample is None or not math.isclose(sample['time_s'], original['time_s'], rel_tol=0, abs_tol=1e-9):
            return None, {'reason': 'numeric_source_sample_grid_incomplete'}
        for field in ('positions', 'orientations_wxyz'):
            for name, value in sample[field].items():
                expected = original[field].get(name)
                if expected is not None and any(abs(a-b) > 1e-9 for a, b in zip(value, expected)):
                    raise ValueError('numeric native pose differs from the same source-grid sample')
        value, measured = None, {}
        source = _source_pose(packet, sample, first)
        if predicate_id == 'world_coordinate_bound/v1':
            axis = 'xyz'.index(params['axis'])
            if params['feature'] == 'source_object_center':
                if source is not None and source[1]['source_center_body_m'] is not None:
                    (p, r), body = source
                    measured['coordinate_m'] = float((p + r @ body['source_center_body_m'])[axis])
            else:
                pieces = _pieces(packet, sample, first)
                if pieces:
                    vertices = np.concatenate([piece.vertices for piece in pieces])
                    measured['coordinate_m'] = float((vertices.min(0) if params['feature'] == 'collision_min' else vertices.max(0))[axis])
            if 'coordinate_m' in measured:
                margin = (measured['coordinate_m'] - params['value_m']) * (1 if params['bound'] == 'lower' else -1)
                value = margin >= 0 if params['inclusive'] else margin > 0
        elif predicate_id in ('axis_angle_to_world/v1', 'axis_parallel/v1'):
            if source is not None and source[1]['source_orientation_body_wxyz'] is not None:
                (_, r), body = source
                axis = r @ _rotation(body['source_orientation_body_wxyz']) @ _axis(params['object_axis'])
                other = _axis(params['world_axis']) if predicate_id == 'axis_angle_to_world/v1' else None
                if predicate_id == 'axis_parallel/v1':
                    region_pose = _region_pose(packet, sample, args[1])
                    if region_pose is not None:
                        other = region_pose[1] @ _axis(params['region_axis'])
                if other is not None:
                    dot = float(np.clip(np.dot(axis, other), -1, 1))
                    if predicate_id == 'axis_parallel/v1' or params['direction'] == 'undirected':
                        dot = abs(dot)
                    measured['angle_deg'] = math.degrees(math.acos(dot))
                    value = measured['angle_deg'] <= params['maximum_angle_deg']
        elif predicate_id.startswith('collision_footprint_inside_region/'):
            pieces, region_pose = _pieces(packet, sample, first), _region_pose(packet, sample, args[1])
            if pieces and region_pose is not None:
                origin, r = region_pose
                hx, hy = packet['regions'][args[1]]['half_extents_xy_m']
                corners = np.asarray([[-hx,-hy,0.], [hx,-hy,0.], [hx,hy,0.], [-hx,hy,0.]]) @ r.T + origin
                polygon = hull2(corners[:, :2])
                margins = [interior_margin2(v[:2], polygon) for piece in pieces for v in piece.vertices]
                if all(m is not None for m in margins):
                    measured['minimum_footprint_margin_m'] = min(margins)
                    value = min(margins) > 0 if params.get('boundary', 'closed') == 'open' else min(margins) >= 0
        else:
            contact = contacts.get(original['step'])
            if contact is not None and not math.isclose(contact['time_s'], original['time_s'], rel_tol=0, abs_tol=1e-9):
                raise ValueError('current contact clock differs from the source-grid sample')
            value, reason = _contact_value(predicate_id, params, contact, first, second)
            measured['basis'] = reason
            if predicate_id in ('physically_supported_by/v1', 'physically_supported_by/v2', 'not_supported_by/v1'):
                measured['support_geometry'] = {
                    'conservative_enclosure_gap_m': _clearance(packet, sample, first, second),
                    'scope': 'positive_excludes_direct_contact_nonpositive_does_not_establish_contact_or_support',
                }
            # A current touch or force contradicts a separation-only inference,
            # including when the contact list is incomplete or load is unknown.
            interaction = any(point['distance_m'] <= 0 or _nonzero_force(point)
                              for point in _pair_contacts(contact, first, second))
            if value is None and not interaction and predicate_id in ('no_robot_contact/v1', 'no_contact_between/v1', 'released_from_gripper/v1'):
                margin = _clearance(packet, sample, first, second)
                measured['minimum_enclosure_separation_m'] = margin
                if margin is not None and margin > 0:
                    value, measured['basis'] = True, 'complete_collision_enclosures_strictly_separated'
            if value is None and not interaction and predicate_id == 'not_supported_by/v1' and params['support_path'] == 'direct':
                margin = _clearance(packet, sample, first, second)
                measured['minimum_enclosure_separation_m'] = margin
                if margin is not None and margin > 0:
                    value, measured['basis'] = True, 'direct_contact_excluded_by_complete_collision_enclosures'
        values.append(value)
        observations.append({'step': original['step'], 'time_s': original['time_s'], 'value': value, **measured})
    value = False if False in values else None if None in values else True
    return value, {'reason': None if value is not None else 'required_numeric_fact_unavailable',
                   'samples': observations, 'source_limits': deepcopy(params), 'sample_count': len(values),
                   'scope': 'source_requested_sample_grid_not_continuous_interpolation'}


def _requests(requests, max_requests):
    if type(max_requests) is not int or not 1 <= max_requests <= 20000:
        raise ValueError('numeric request budget must be an integer from 1 to 20000')
    requests = _json(requests)
    if not isinstance(requests, list) or not requests or len(requests) > max_requests:
        raise ValueError('numeric requests must be a nonempty bounded list')
    seen = set()
    for request in requests:
        _keys(request, ('request_id', 'method', 'arguments', 'params', 'source_basis'), 'numeric request')
        _text(request['request_id'], 'numeric request ID')
        if request['request_id'] in seen:
            raise ValueError('duplicate numeric request ID')
        seen.add(request['request_id'])
        method = request['method']
        if not isinstance(method, str) or method not in _METHODS:
            raise ValueError('unsupported numeric method')
        contract = _METHODS[method]
        if not isinstance(request['arguments'], list) or len(request['arguments']) != contract['arity']:
            raise ValueError('numeric method argument count differs from its contract')
        for argument in request['arguments']:
            _text(argument, 'bound numeric entity ID')
        params = request['params']
        if (not isinstance(params, dict) or set(params) - set(contract['parameters'])
                or not set(contract['required']) <= set(params)):
            raise ValueError('numeric parameters have unknown or missing fields')
        for name, value in params.items():
            rule = contract['parameters'][name]
            if 'enum' in rule and value not in rule['enum']:
                raise ValueError('numeric parameter has an unsupported enum value')
            if rule.get('type') == 'boolean' and type(value) is not bool:
                raise ValueError('numeric boolean parameter must be boolean')
            if rule.get('type') == 'number':
                if not _finite(value):
                    raise ValueError('numeric parameters must be finite numbers, not booleans')
                if ('minimum' in rule and value < rule['minimum']
                        or 'maximum' in rule and value > rule['maximum']
                        or 'exclusiveMinimum' in rule and value <= rule['exclusiveMinimum']):
                    raise ValueError('numeric parameter is outside its supported range')
        if method == 'orientation_matches/v1' and _vector(
                [params['target_' + axis] for axis in 'wxyz'], 4, quaternion=True, target=True) is None:
            raise ValueError('target orientation must be a unit WXYZ quaternion')
        if not isinstance(request['source_basis'], list) or not request['source_basis']:
            raise ValueError('numeric request requires original source basis')
        for basis in request['source_basis']:
            _keys(basis, ('path', 'pointer'), 'numeric request source basis')
            _text(basis['path'], 'numeric source path')
            _text(basis['pointer'], 'numeric source pointer')
    return requests


def numeric_request_digest(requests, *, max_requests=2000):
    """Bind geometry/reference packets to the exact explicit measurement requests."""
    return _digest(_requests(requests, max_requests))


def measure_source_requests(source, *, source_ref, dependencies=(), evidence, evidence_refs,
                            requests, source_documents=(), reference_bindings=None,
                            numeric_evidence=None, max_requests=2000):
    """Measure explicit source-bound conditions without constructing a task verdict.

    source_ref and dependency hashes are caller-verified file-byte identities.
    Source pointers establish provenance, not correctness of the caller's chosen
    method/threshold. The original-task review independently checks that meaning.
    Missing observations return null; malformed or conflicting identities raise.
    """
    source = _json(source)
    if not isinstance(source, dict) or not source:
        raise ValueError('numeric measurements require the original nonempty source')
    requests = _requests(requests, max_requests)
    source_ref, dependencies, refs = _json([source_ref, list(dependencies), list(evidence_refs)])
    _refs([source_ref, *dependencies])
    _refs(refs)
    source_files = [source_ref, *dependencies]
    if len({r['path'] for r in source_files}) != len(source_files):
        raise ValueError('numeric source/dependency paths must be unique')
    evidence, endpoint = validate_terminal_evidence(evidence)
    closure = {(r['path'], r['sha256']) for r in [*evidence['source_refs'], *refs]}
    if not {(r['path'], r['sha256']) for r in source_files} <= closure:
        raise ValueError('numeric source files are outside the verified evidence closure')
    digest = _digest(requests)
    context = {'source': source, 'requests_sha256': digest, 'source_ref': {
        'path': source_ref['path'], 'record_sha256': _digest(source),
        'dependencies': [{'path': r['path'], 'file_sha256': r['sha256']} for r in dependencies]}}
    documents = _source_documents(context, evidence, source_documents)
    for request in requests:
        for basis in request['source_basis']:
            if basis['path'] == source_ref['path']:
                document = source
            elif basis['path'] in documents:
                document = documents[basis['path']]['document']
            else:
                raise ValueError('numeric request source basis requires a loaded frozen source dependency')
            _pointer(document, basis['pointer'])
    prepared = []
    scope = {}
    for request in requests:
        key = {'request_id': request['request_id'], 'predicate': request['method'],
               'arguments': request['arguments']}
        scope[_digest(key)] = key
        prepared.append({**key, 'key': key, 'params': request['params']})
    reference_packet, references = _reference_bindings(context, evidence, reference_bindings, documents, refs, scope)
    packet = _admit_numeric_evidence(context, evidence, numeric_evidence, documents, refs, scope)
    measurements = []
    for supplied, request in zip(requests, prepared):
        if not endpoint['valid']:
            value, diagnostic = None, {'reason': 'completed_record_end_not_established'}
        elif request['predicate'] in POSE_METHODS:
            value, diagnostic = _measure_pose(request, context, evidence, documents, references)
        else:
            samples, reason = _samples(context, evidence, request['params'].get('window_seconds', 0), documents)
            if reason or not samples:
                value, diagnostic = None, {'reason': reason or 'source_samples_unavailable'}
            else:
                value, diagnostic = _measure_numeric(request, packet, samples)
        measurements.append({'request_id': request['request_id'], 'method': request['predicate'],
            'arguments': deepcopy(request['arguments']), 'params': deepcopy(request['params']),
            'source_basis': deepcopy(supplied['source_basis']), 'value': value,
            'diagnostics': diagnostic})
    path = Path(__file__)
    return {'schema_version': 'terminal-numeric-measurements/0.1',
        'source_sha256': _digest(source), 'source_ref': source_ref, 'dependencies': dependencies,
        'requests_sha256': digest, 'endpoint': endpoint, 'evidence_refs': refs,
        'reference_bindings': reference_packet,
        'numeric_evidence_sha256': _digest(packet) if packet is not None else None,
        'producer': {'path': 'validation/terminal/numeric.py',
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
        'units': {'length': 'm', 'angle': 'deg', 'time': 's', 'force': 'N', 'orientation_order': 'wxyz'},
        'measurements': measurements,
        'scope': 'caller_selected_source_bound_measurements_not_terminal_or_task_success'}
