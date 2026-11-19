"""Hash-bound observation views; selects recorded data, never task verdicts.

Full originals stay authoritative. Static units, reference points, identity,
solver limits and contact phases survive selection. Recording completeness is
kept separate from actual model delivery; hidden window statistics are omitted.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from validation.artifact_io import checked_ref, digest, read_json


_RECORD_METADATA = {'scope', 'selection', 'complete', 'source_window', 'source_grid_steps',
    'source_grid_complete', 'recorded_sample_grid_complete', 'expected_steps', 'sample_count',
    'recorded_sample_count', 'recorded_state_row_count', 'recorded_sample_dt_seconds',
    'sample_dt_seconds', 'measurement_row_count', 'native_sample_count', 'source_grid_sample_count',
    'original_row_count', 'delivered_row_count', 'original_frame_count', 'delivered_frame_count', 'completion',
    'observed_span_seconds', 'continuous_contact_or_stability_proven', 'native_physics_interval_coverage_known'}
_STATISTICS = {'body_pose_spread', 'terminal_window_pose_spread'}
_ASSET_PROPERTIES = ('collision_geometry', 'mass', 'material', 'joint_limits')
_ROW_CHANNELS = {
    'positions':'pose', 'positions_m':'pose', 'orientations':'pose', 'orientations_wxyz':'pose',
    'body_positions':'pose', 'body_orientations_wxyz':'pose', 'qpos':'pose', 'arm_qpos':'pose',
    'linear_velocities_m_s':'velocity', 'angular_velocities_rad_s':'velocity', 'qvel':'velocity', 'arm_qvel':'velocity',
    'ctrl':'controls', 'actuator_force':'controls', 'host_call_counts':'controls',
}
_NAMED_FIELDS = {'positions','positions_m','orientations','orientations_wxyz',
                 'linear_velocities_m_s','angular_velocities_rad_s'}


class EvidenceViewError(ValueError):
    """Malformed, changed, unsupported or over-budget delivery; not physical unknown."""


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _asset_value(value):
    """Deliver exact digests for large canonical values; retain raw files.

    Mesh vertices remain in the hash-bound original. Equality uses the entire
    value before this presentation step, with no tolerance or truncation.
    """
    raw = _encoded(value)
    return value if len(raw) <= 4096 else {'schema_version':'canonical-json-digest/0.1',
        'sha256':hashlib.sha256(raw).hexdigest(), 'utf8_bytes':len(raw)}


def _asset_row(row):
    return {**deepcopy(row), 'expected':_asset_value(row.get('expected')), 'observed':_asset_value(row.get('observed'))}


def _write(root, path, value):
    with path.open('xb') as stream:
        stream.write(_encoded(value))
    return {'path': path.relative_to(root).as_posix(), 'sha256': digest(path)}


def _body(value):
    return value.get('payload', value) if isinstance(value, dict) else value


def _time(row):
    return next((row[key] for key in ('time_s', 'time', 't', 'record_time_s') if key in row), None)


def _near(a, b):
    return type(a) in (int, float) and math.isfinite(a) and abs(a-b) <= 1e-8


def _columns(table):
    count = table['sample_count']
    if type(count) is not int or count < 0:
        raise EvidenceViewError('invalid column sample_count')
    result = {}
    for key, column in table['columns'].items():
        if set(column) == {'values'}:
            values = column['values']
        elif set(column) == {'constant'}:
            values = [column['constant']] * count
        else:
            raise EvidenceViewError('unknown recorded column encoding')
        if not isinstance(values, list) or len(values) != count:
            raise EvidenceViewError('recorded column length mismatch')
        result[key] = values
    return result


def _grid(payload):
    if isinstance(payload.get('source_grid_steps'), list):
        return payload['source_grid_steps']
    window = payload.get('terminal_window') or {}
    return window.get('grid_projection', {}).get('selected_steps')


def _layout(payload):
    if not isinstance(payload, dict): return None
    if payload.get('schema_version') == 'terminal-asset-properties/0.1': return 'assets'
    if isinstance(payload.get('samples'), dict) and isinstance(payload['samples'].get('entities'), dict): return 'columns'
    if isinstance(payload.get('samples'), list) and all(isinstance(x, dict) and _time(x) is not None for x in payload['samples']): return 'samples'
    if isinstance(payload.get('records'), list) and payload.get('schema_version') == 'recorded-native-contacts/0.1': return 'contacts'
    if all(key in payload for key in ('initial', 'terminal', 'identities')): return 'state'
    return None


def _entities(payload):
    names = set(payload.get('identities', {}))
    if _layout(payload) == 'assets':
        names.update(payload.get('observed_entities', []))
        names.update(row['entity'] for row in payload.get('comparisons', []))
    for mapping in payload.get('solver_mappings', {}).values():
        names.update(mapping.get('body_names', []))
    if _layout(payload) == 'columns': names.update(payload['samples']['entities'])
    for sample in payload.get('samples', []) if isinstance(payload.get('samples'), list) else []:
        for key in ('positions', 'positions_m', 'orientations', 'orientations_wxyz'):
            names.update(sample.get(key, {}))
    if isinstance(payload.get('body_mapping'), dict): names.update(payload['body_mapping'])
    for source in payload.get('sources', {}).values() if isinstance(payload.get('sources'), dict) else []:
        names.update(source.get('body_names', []))
    return sorted(names)


def _state_samples(payload):
    """Read the existing state formats through one observation-selection path.

    Recorded poses retain their full history under provenance, independently of
    a source-requested terminal grid. That history is data, not static metadata.
    """
    if (payload.get('schema_version') == 'terminal-evidence/0.3'
            and payload.get('capture', {}).get('owner') == 'recorded.world_pose_file'):
        rows = payload.get('provenance', {}).get('frames')
        if not isinstance(rows, list) or any(not isinstance(row, dict) or _time(row) is None for row in rows):
            raise EvidenceViewError('recorded state history lacks clocked frames')
        return rows
    rows = (payload.get('terminal_window') or {}).get('samples', [])
    times = {_time(row) for row in rows}
    boundaries = [payload['initial'], payload['terminal']]
    return sorted([*rows, *(row for row in boundaries if _time(row) not in times)], key=_time)


def _times(payload):
    kind = _layout(payload)
    if kind == 'assets': return [payload['endpoint']['time_s']]
    if kind == 'columns':
        return [time for table in payload['samples']['entities'].values() for key, values in _columns(table).items()
                if key in ('t', 'time', 'time_s') for time in values]
    if kind in ('samples', 'contacts'):
        return [_time(row) for row in payload['samples' if kind == 'samples' else 'records']]
    if kind == 'state':
        return [payload['initial']['time_s'], *[_time(row) for row in _state_samples(payload)], payload['terminal']['time_s']]
    return []


def _catalogue_entry(item, payload, endpoint):
    times = _times(payload)
    if any(type(time) not in (int, float) or not math.isfinite(time) for time in times):
        raise EvidenceViewError('invalid observation clock')
    kind = _layout(payload)
    channels = set()
    if kind == 'assets': channels.add('asset_properties')
    if kind == 'contacts': channels.add('contact')
    if kind == 'columns':
        keys = {key for table in payload['samples']['entities'].values() for key in table['columns']}
        if any(key.startswith(('pos_', 'quat_')) for key in keys): channels.add('pose')
        if any(key.startswith(('linvel_', 'angvel_')) for key in keys): channels.add('velocity')
    elif kind in ('samples', 'state'):
        rows = payload['samples'] if kind == 'samples' else [payload['initial'], *_state_samples(payload), payload['terminal']]
        keys = {key for row in rows for key in row}
        if keys & {'positions','positions_m','orientations','orientations_wxyz','solvers'}: channels.add('pose')
        if any('velocit' in key or key.endswith('qvel') for key in keys): channels.add('velocity')
        if any('solvers' in row for row in rows): channels.add('controls')
    clocks = sorted(set(times))
    time_range = [max(0, min(times)), min(max(times), endpoint['time_s'])] if times else [0, endpoint['time_s']]
    # Clipping only the upper bound can invert a singleton at endpoint + roundoff.
    # Keep raw clocks unchanged and retain rejection of genuinely future ranges.
    if time_range[0] > time_range[1] and _near(*time_range):
        time_range[0] = time_range[1]
    return {'id': item['id'], 'entities': _entities(payload), 'channels': sorted(channels),
        'time_range_s': time_range,
        'source_grid': _grid(payload) is not None or payload.get('source_grid_complete') is True,
        'availability': 'available' if kind else 'unavailable',
        'description': 'Archived observations, not delivered data. ' + json.dumps({
            'sample_count':len(clocks), 'recorded_times_s':clocks,
            'source_grid_steps':_grid(payload), 'recorded_sample_dt_seconds':payload.get('recorded_sample_dt_seconds')}, separators=(',',':'))}


def _select(rows, endpoint, query, grid=None):
    if query is None:
        return [deepcopy(row) for row in rows if _near(_time(row), 0) or _near(_time(row), endpoint['time_s'])]
    start, end = query['time_range_s']
    selected = [deepcopy(row) for row in rows if start-1e-8 <= _time(row) <= end+1e-8]
    if query['sampling'] == 'source_grid' and grid is not None:
        selected = [row for row in selected if row.get('step') in grid]
    return selected


def _requested_row(row, query):
    """Filter named observations and known channels; retain clocks/static context.

    Native solver arrays and joint layouts share positional indices, so retain
    their full mapping instead of silently renumbering coupled body/joint arrays.
    """
    for key in list(row):
        channel=_ROW_CHANNELS.get(key)
        if key.startswith(('linvel_','angvel_')): channel='velocity'
        elif key.startswith(('pos_','quat_')): channel='pose'
        if channel and channel not in query['channels']:
            row.pop(key)
        elif key in _NAMED_FIELDS and isinstance(row[key],dict):
            row[key]={name:value for name,value in row[key].items() if name in query['entities']}
    for solver in row.get('solvers',{}).values():
        _requested_row(solver,query)
    return row


def _delivered_times(projected):
    if _layout(projected) == 'assets': return [projected['endpoint']['time_s']]
    tables = projected.get('samples', {})
    if isinstance(tables,dict):
        rows = [row for table in tables.get('entities',{}).values() for row in table.get('observations',[])]
    else:
        rows = tables if isinstance(tables,list) else []
    rows += projected.get('records',[]) + projected.get('requested_window_samples',[])
    return sorted({_time(row) for row in rows if _time(row) is not None})


def _project(payload, endpoint, query=None):
    result = deepcopy(payload)
    metadata = {key: result.pop(key) for key in list(result) if key in _RECORD_METADATA}
    omitted = []
    for key in _STATISTICS:
        if key in result:
            result.pop(key); omitted.append('/'+key)
    facts = result.get('facts')
    if isinstance(facts, dict):
        for key in ('recording_coverage', 'native_measurements_collected'):
            if key in facts: metadata['facts/'+key] = facts.pop(key)
        for key in ('terminal_window_pose_spread',):
            if key in facts: facts.pop(key); omitted.append('/facts/'+key)
        if isinstance(facts.get('native_measurements'), list):
            rows = facts['native_measurements']
            facts['native_measurements'] = _select(rows, endpoint, query) if all(_time(x) is not None for x in rows) else []
            if rows: omitted.append('/facts/native_measurements/unselected_rows')
    kind = _layout(payload)
    if kind == 'assets' and query is not None:
        result['comparisons'] = [row for row in result.get('comparisons', []) if row['entity'] in query['entities']]
        result['uncompared_observations'] = {name: value for name, value in result.get('uncompared_observations', {}).items()
                                           if name in query['entities']}
    if kind == 'assets':
        result['comparisons'] = [_asset_row(row) for row in result.get('comparisons', [])]
        for body in result.get('uncompared_observations', {}).values():
            body['values'] = {key:_asset_value(value) for key,value in body['values'].items()}
    grid = _grid(payload)
    if kind == 'state':
        rows = _state_samples(payload)
        provenance = result.get('provenance', {})
        if 'frames' in provenance:
            provenance.pop('frames')
            omitted.append('/provenance/frames')
            if 'completion' in provenance:
                metadata['provenance/completion'] = provenance.pop('completion')
        window = result.pop('terminal_window', None)
        if window:
            metadata['terminal_window'] = {key: value for key, value in window.items() if key != 'samples'}
            omitted.append('/terminal_window/unselected_samples')
        if query is not None:
            result['requested_window_samples'] = [_requested_row(row,query) for row in _select(rows, endpoint, query, grid)]
    elif kind == 'columns':
        output = {}
        for name, table in payload['samples']['entities'].items():
            if query is not None and name not in query['entities']: continue
            columns = _columns(table)
            clock = next((key for key in ('t','time','time_s') if key in columns), None)
            if clock is None: raise EvidenceViewError('column observations have no clock')
            if query is None:
                indices = [i for i,time in enumerate(columns[clock]) if _near(time, payload.get('initial_time_s',0)) or _near(time,endpoint['time_s'])]
            else:
                indices = [i for i,time in enumerate(columns[clock]) if query['time_range_s'][0]-1e-8 <= time <= query['time_range_s'][1]+1e-8]
                if query['sampling'] == 'source_grid' and grid is not None:
                    indices = [i for i in indices if 'step' in columns and columns['step'][i] in grid]
            rows = [{key: deepcopy(values[i]) for key,values in columns.items()} for i in indices]
            if query is not None: rows=[_requested_row(row,query) for row in rows]
            output[name] = {'metadata': {key:deepcopy(value) for key,value in table.items() if key not in ('columns','sample_count')},
                'original_sample_count':table['sample_count'], 'observations': rows}
        result['samples'] = {'entities': output, 'encoding': 'Explicit selected rows, original values and clock order unchanged.'}
        omitted.append('/samples/unselected_rows')
    elif kind in ('samples','contacts'):
        key = 'samples' if kind == 'samples' else 'records'
        result[key] = _select(payload[key], endpoint, query, grid)
        if kind=='samples' and query is not None:
            result[key]=[_requested_row(row,query) for row in result[key]]
    if isinstance(payload.get('tracked_state_rows'), list):
        rows = _select(payload['tracked_state_rows'], endpoint, query, grid)
        result['tracked_state_rows'] = (rows if query is None else
            [_requested_row(row,query) for row in rows if row.get('entity') in query['entities']])
    if isinstance(payload.get('contact_samples'), list):
        rows = payload['contact_samples']
        result['contact_samples'] = _select(rows,endpoint,query,grid) if all(isinstance(row,dict) and _time(row) is not None for row in rows) else []
        omitted.append('/contact_samples/unselected_or_unclocked_rows')
    # Source dictionaries, solver_layouts (including incomplete actuator inventory),
    # limits, units, reference-point declarations and all boundary identities remain.
    return result, metadata, omitted


def _asset_receipt(root, evidence, endpoint, cache_directory):
    refs = [{'path':item['path'], 'sha256':item['sha256']} for item in evidence if not item.get('capture_verified')]
    identity = hashlib.sha256(_encoded({'endpoint':endpoint, 'inputs':refs, 'checker_revision':3})).hexdigest()
    directory = Path(cache_directory).resolve()
    if not directory.is_relative_to(root): raise EvidenceViewError('asset cache outside artifact root')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/(identity+'.json')
    checks = []
    for item in evidence:
        if item.get('capture_verified'): continue
        source = checked_ref(root, item)
        try: body = _body(read_json(source))
        except (ValueError, UnicodeError): continue
        if isinstance(body, dict) and body.get('schema_version') == 'terminal-asset-properties/0.1':
            if body.get('endpoint') != endpoint: raise EvidenceViewError('asset properties belong to another endpoint')
            for reference in body.get('source_refs', []): checked_ref(root, reference)
            for row in body.get('comparisons', []):
                if not isinstance(row, dict) or row.get('property') not in _ASSET_PROPERTIES or not isinstance(row.get('entity'), str):
                    raise EvidenceViewError('invalid recorded asset comparison')
                _encoded(row)  # Reject nonfinite/unserializable values.
                known = (row.get('native_binding_verified') is True and row.get('expected') is not None and row.get('observed') is not None)
                checks.append({**_asset_row(row), 'status': ('recorded_values_match' if _encoded(row['expected']) == _encoded(row['observed'])
                    else 'recorded_values_differ') if known else 'unverified', 'evidence_id':item['id']})
    summary = {status: sum(c['status'] == status for c in checks)
               for status in ('recorded_values_match', 'recorded_values_differ', 'unverified')}
    receipt = {'schema_version':'terminal-asset-check/0.1', 'endpoint':endpoint, 'input_digest':identity,
        'input_files':refs, 'input_files_hash_verified':True, 'checks':checks,
        'missing_properties':[key for key in _ASSET_PROPERTIES if not any(c['property']==key and c['status']=='recorded_values_match' for c in checks)],
        'comparison_summary': summary,
        'asset_integrity':None, 'scope':'Hash and supplied canonical-value checks, not an independent live readback. Differences require interpretation; missing properties remain unverified.'}
    if path.exists():
        if read_json(path) != receipt: raise EvidenceViewError('cached asset receipt differs from frozen inputs')
        return {'path':path.relative_to(root).as_posix(), 'sha256':digest(path)}
    return _write(root, path, receipt)


def prepare_evidence_views(root, evidence, endpoint, output_directory, *, mode='boundary', queries=(),
                           max_characters=250000, asset_cache=None):
    """Prepare boundary/full or one requested window, preserving source references.

    queries have already passed terminal_reviews admission. Missing archived data
    is returned as an availability result. Malformed, changed or over-budget
    evidence raises EvidenceViewError; it is not a model unknown opinion.
    """
    root, directory = Path(root).resolve(), Path(output_directory).resolve()
    if mode not in ('boundary','full','expanded') or directory.exists() or not directory.is_relative_to(root):
        raise EvidenceViewError('evidence view needs a supported mode and fresh in-root directory')
    if type(max_characters) is not int or max_characters <= 0: raise EvidenceViewError('invalid view budget')
    inputs, originals = deepcopy(evidence), []
    for item in inputs:
        path=checked_ref(root,item)
        if item.get('capture_verified') or item['kind']=='source_geometry':
            originals.append(item); continue
        try: value=read_json(path)
        except (ValueError,UnicodeError): value=None
        if isinstance(value,dict) and value.get('schema_version')=='terminal-evidence-view/0.1':
            if value['endpoint']!=endpoint or value['original_evidence_id']!=item['id']:
                raise EvidenceViewError('input view belongs to another source/endpoint')
            reference=value['original_evidence'];checked_ref(root,reference)
            originals.append({**item,**reference})
        elif isinstance(value,dict) and value.get('schema_version')=='terminal-asset-check/0.1' and item['id']=='asset_record_checks':
            if value['endpoint']!=endpoint:raise EvidenceViewError('asset receipt belongs to another endpoint')
            # A previous generated receipt is not another observation source.
            for reference in value.get('input_files',[]):checked_ref(root,reference)
        else: originals.append(item)
    registry = {item['id']: item for item in originals}
    bodies, entries = {}, []
    for item in originals:
        path = checked_ref(root, item)
        if item.get('capture_verified') or item['kind']=='source_geometry': continue
        try: payload = _body(read_json(path))
        except (ValueError, UnicodeError): continue
        bodies[item['id']] = payload
        if isinstance(payload, dict): entries.append(_catalogue_entry(item,payload,endpoint))
    catalogue = {'schema_version':'terminal-evidence-catalogue/0.1', 'episode_id':endpoint['episode_id'],
                 'endpoint_id':endpoint['endpoint_id'], 'entries':entries}
    planned, statuses = [], []
    if mode == 'expanded':
        by_id = {entry['id']:entry for entry in entries}
        for query in queries:
            identity = query['evidence_id']; entry = by_id.get(identity)
            if entry is None: raise EvidenceViewError('expansion refers to an unknown data source')
            start,end = query['time_range_s']
            reason = ('not_recorded' if entry['availability']!='available' or
                start < entry['time_range_s'][0]-1e-8 or end > entry['time_range_s'][1]+1e-8 else
                'source_grid_not_recorded' if query['sampling']=='source_grid' and not entry['source_grid'] else None)
            available = set(query['channels']) & set(entry['channels'])
            if not available: reason = 'requested_channels_not_recorded'
            if reason:
                statuses.append({'evidence_id':identity,'status':'unavailable','reason':reason,'request':query}); continue
            projected, metadata, omitted = _project(bodies[identity],endpoint,query)
            delivered_times = _delivered_times(projected)
            if not delivered_times:
                statuses.append({'evidence_id':identity,'status':'unavailable','reason':'no_recorded_samples_for_selection','request':query})
                continue
            planned.append((registry[identity],projected,metadata,omitted,query))
            statuses.append({'evidence_id':identity,'status':'delivered','request':query,
                'delivered_times_s':delivered_times,
                'missing_requested_boundaries_s':[t for t in query['time_range_s'] if not any(_near(x,t) for x in delivered_times)],
                'coverage':'Only listed recorded times, not a continuous-time guarantee; retain per-row missing/partial status.',
                'unavailable_channels':sorted(set(query['channels'])-set(entry['channels']))})
    elif mode == 'boundary':
        for item in originals:
            payload = bodies.get(item['id'])
            if isinstance(payload,dict) and _layout(payload):
                projected, metadata, omitted = _project(payload,endpoint)
                planned.append((item,projected,metadata,omitted,None))
            elif isinstance(payload,dict) and ('samples' in payload or any(key in payload for key in _STATISTICS | _RECORD_METADATA)):
                projected, metadata, omitted = _project(payload,endpoint)
                # Auxiliary numeric packets do not establish actual observations;
                # omit any unrecognized sample collection rather than reinterpret it.
                projected.pop('samples',None); projected.pop('contact_samples',None)
                planned.append((item,projected,metadata,omitted+['/samples','/contact_samples'],None))
    documents = []
    for item, projected, metadata, omitted, query in planned:
        document = {'schema_version':'terminal-evidence-view/0.1', 'original_evidence':{key:item[key] for key in ('path','sha256')},
            'original_evidence_id':item['id'], 'original_schema_version':projected.pop('schema_version',None),
            'endpoint':endpoint, 'delivery':{'mode':mode,'query':query,'omitted_fields':omitted,
                'expansion_outcomes':statuses if mode=='expanded' else [],
                'limits':'Only explicitly included observations are delivered. Original file references and recording completeness are not observed window coverage. Preserve contact geometry/availability clocks; body origins are not assumed source centers.'},
            'original_record_metadata':{'scope':'Archived original, not current context delivery', 'metadata':metadata},
            'observations':projected}
        documents.append((item,document))
    if sum(len(_encoded(document).decode('utf-8')) for _,document in documents) > max_characters:
        raise EvidenceViewError('evidence view budget exceeded; no silent truncation')
    directory.mkdir(parents=True)
    prepared = []
    replaced = {item['id'] for item,_ in documents}
    if mode != 'expanded': prepared = [deepcopy(item) for item in originals if item['id'] not in replaced]
    for index,(item,document) in enumerate(documents):
        reference = _write(root,directory/(str(index)+'-view.json'),document)
        prepared.append({**deepcopy(item), **reference})
    asset_ref = _asset_receipt(root, originals, endpoint, asset_cache or directory.parent/'asset-checks')
    asset_id = 'asset_record_checks'
    if mode != 'expanded' and asset_id not in registry:
        prepared.append({'id':asset_id,'kind':'measurement',**asset_ref,
                         'episode_id':endpoint['episode_id'],'endpoint_id':endpoint['endpoint_id']})
    result = {'schema_version':'terminal-evidence-view-index/0.1','mode':mode,'endpoint':endpoint,
        'input_evidence':inputs,'original_evidence':originals,'evidence':prepared,'catalogue':catalogue,'outcomes':statuses,
        'asset_checks':asset_ref,'projector_sha256':digest(Path(__file__))}
    _write(root,directory/'index.json',result)
    return result
