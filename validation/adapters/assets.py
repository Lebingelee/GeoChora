"""Bind archived public model observations to a terminal and reference assets.

The caller selects an independent reference run of the original assets. A
candidate's own build snapshot is never promoted to an authoritative baseline.
No source script is executed and no object or dataset names are hardcoded.
"""
from copy import deepcopy
import math
from pathlib import Path

from validation.artifact_io import checked_ref, digest, read_json

PROPERTIES = ('collision_geometry', 'mass', 'material', 'joint_limits')


def _observation(root, state_ref, boundary):
    from .recorded import validate_terminal_evidence as _record
    from .physpi import _runtime_source, _artifact

    state, endpoint = _record(read_json(checked_ref(root, state_ref)))
    refs = [state_ref, *state['source_refs']]
    for ref in refs:
        checked_ref(root, ref)
    if endpoint['valid'] is not True:
        return state, endpoint, None, refs, 'asset_runtime_endpoint_unverified'
    run = state.get('run', {})
    if state.get('capture', {}).get('owner') != 'physpi_runtime.cli.cmd_query':
        return state, endpoint, None, refs, 'runtime_asset_record_not_available'
    index_ref = state['source_refs'][0]
    index_path = checked_ref(root, index_ref)
    directory = index_path.parent if run['branch'] is None else index_path.parent.parent
    runtime = _runtime_source(directory, run['branch'])
    if runtime['index']['code_sha256'] != run['code_sha256']:
        raise ValueError('asset runtime source differs from collected state')
    index = runtime['index']
    relative = (index.get('asset_properties') if run['branch'] is not None
                else index.get('artifacts', {}).get('asset_properties'))
    if relative is None:
        return state, endpoint, None, refs, 'runtime_asset_record_not_available'
    path = _artifact(directory, relative)
    ref = {'path': path.relative_to(root).as_posix(), 'sha256': digest(path)}
    refs.append(ref)
    packet = read_json(path)
    if packet.get('schema_version') != 'runtime-asset-properties/0.1':
        raise ValueError('unsupported runtime asset record')
    target = state['terminal' if boundary == 'final' else 'initial']
    matches = [row for row in packet.get('snapshots', []) if row.get('boundary') == boundary
               and row.get('branch') == (run['branch'] if boundary == 'final' else None)]
    if not matches:
        return state, endpoint, None, refs, 'asset_boundary_not_recorded'
    if len(matches) != 1:
        raise ValueError('ambiguous asset boundary')
    row = matches[0]
    if (row.get('schema_version') != 'engine-asset-properties/0.1'
            or row.get('run_id') != run['run_id'] or row.get('code_sha256') != run['code_sha256']
            or row.get('step') != target['step'] or type(row.get('t')) not in (float, int)
            or not math.isclose(row['t'], target['time_s'], rel_tol=0, abs_tol=1e-9)
            or type(row.get('known')) is not bool):
        raise ValueError('asset boundary run/source/clock mismatch')
    if row['known'] is False:
        return state, endpoint, None, refs, row.get('reason', 'asset_observation_failed')
    observed = row.get('observed', {})
    if observed.get('engine') != row.get('engine'):
        raise ValueError('asset observation engine mismatch')
    if row['engine'] == 'geophys' and not isinstance(observed.get('engine_source'), dict):
        return state, endpoint, None, refs, 'runtime_asset_engine_identity_not_recorded'
    bodies = {}
    for solver in observed.get('solvers', []):
        index = solver.get('solver_index')
        if type(index) is not int or index < 0:
            raise ValueError('invalid asset solver identity')
        props = solver.get('properties')
        if props is None:
            continue
        if props.get('schema_version') != 'rigid-asset-properties/0.1' or props.get('units') != 'SI':
            raise ValueError('unsupported asset property representation/units')
        for body in props['bodies']:
            name = body.get('name')
            key = f'solver{index}/{name}'
            if not isinstance(name, str) or not name or key in bodies:
                raise ValueError('ambiguous native asset identity')
            values = body.get('properties')
            if not isinstance(values, dict) or set(values) != set(PROPERTIES):
                raise ValueError('incomplete asset property record')
            bodies[key] = {'values': deepcopy(values), 'representation': props['representation'],
                           'missing': deepcopy(body.get('missing', {}))}
    return state, endpoint, {**row, 'bodies': bodies}, refs, None if bodies else 'native_rigid_assets_not_recorded'


def collect_asset_properties(root, state_evidence_ref, *, baseline_state_ref=None, entity_map=None):
    """Compare current final readback with a selected original reference initial.

    ``baseline_state_ref`` is a normal collected terminal-evidence reference;
    its independently recorded initial model is supplied as the source baseline.
    Exact values are compared only within the same native representation. Any
    source-equivalent import adaptation needs its own reviewed reference run.
    """
    root = Path(root).resolve()
    state, endpoint, actual, refs, reason = _observation(root, state_evidence_ref, 'final')
    expected = None
    if baseline_state_ref is not None:
        baseline, _, expected, baseline_refs, baseline_reason = _observation(root, baseline_state_ref, 'initial')
        refs.extend(baseline_refs)
        if baseline.get('run', {}).get('run_id') == state.get('run', {}).get('run_id'):
            raise ValueError('candidate run cannot certify its own original asset baseline')
        if baseline['initial'].get('valid_for_task_initial') is not True:
            raise ValueError('asset baseline needs an actual episode initial observation')
        reason = reason or baseline_reason
        if actual and expected and (any(actual.get(k) != expected.get(k) for k in
                ('engine', 'engine_version', 'backend', 'device', 'adapter_version'))
                or actual['observed'].get('engine_source') != expected['observed'].get('engine_source')):
            raise ValueError('asset baseline uses a different engine/version/backend')
    else:
        reason = reason or 'original_asset_baseline_not_provided'
    actual_bodies = actual['bodies'] if actual else {}
    expected_bodies = expected['bodies'] if expected else {}
    mapping = dict(entity_map or {name: name for name in expected_bodies})
    if (set(mapping) != set(expected_bodies) or any(not isinstance(v, str) or not v for v in mapping.values())
            or len(set(mapping.values())) != len(mapping)):
        raise ValueError('asset mapping must bind every reference body exactly once')
    comparisons = []
    for source_name, target_name in mapping.items():
        left, right = expected_bodies[source_name], actual_bodies.get(target_name)
        if right and left['representation'] != right['representation']:
            raise ValueError('asset baseline native representations differ')
        for key in PROPERTIES:
            a, b = left['values'][key], right['values'][key] if right else None
            comparisons.append({'entity': target_name, 'source_entity': source_name, 'property': key,
                'expected': a, 'observed': b, 'native_binding_verified': right is not None,
                'reason': None if a is not None and b is not None else
                    (right or {}).get('missing', {}).get(key, 'native_property_or_body_unavailable')})
    unique_refs = list({(r['path'], r['sha256']): r for r in refs}.values())
    for ref in unique_refs:
        checked_ref(root, ref)
    return {'schema_version': 'terminal-asset-properties/0.1', 'endpoint': endpoint,
        'source_refs': unique_refs, 'comparisons': comparisons,
        'baseline_state_evidence': baseline_state_ref, 'actual_state_evidence': state_evidence_ref,
        'observed_entities': sorted(actual_bodies), 'reference_entities': sorted(expected_bodies),
        'unmapped_observed_entities': sorted(set(actual_bodies) - set(mapping.values())),
        'uncompared_observations': {name: value for name, value in actual_bodies.items() if name not in mapping.values()},
        'collection_status': 'available' if actual and expected and not reason else 'partial' if actual else 'unavailable',
        'reason': reason, 'asset_integrity': None,
        'scope': 'Independent reference initial versus this final model; original-source authority is caller supplied. Does not prove continuous invariance or task success.'}
