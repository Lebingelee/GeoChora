"""Independent runtime factories; no reference labels or model calls."""
import hashlib
import json
import re
from validation.adapters import physpi as collector


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def _run(tmp_path, *, resident=False):
    directory = tmp_path / 'observed-run'
    directory.mkdir()
    code = '# inert synthetic source; never imported\n'
    (directory / 'sim_script.py').write_bytes(code.encode('utf-8'))
    source_sha = hashlib.sha256(code.encode()).hexdigest()
    branch = 'main' if resident else None
    trace = directory / ('timeline/main/trace/states.parquet' if resident else 'trace/states.parquet')
    trace.parent.mkdir(parents=True)
    trace.write_bytes(b'immutable public query fixture')
    if resident:
        index_path = directory / 'timeline/timeline.json'
        index = {'run_id': directory.name, 'status': 'completed', 'code_snapshot': 'sim_script.py',
                 'code_sha256': source_sha, 'dt': 0.01, 'build_evidence': {}, 'branches': {
                     'main': {'start_step': 200, 'start_t': 2.0, 'steps': 100,
                              'trace_cadence_steps': [10], 'trace': 'timeline/main/trace/states.parquet',
                              'aborted': None}}}
        steps, dt = list(range(200, 301, 10)), 0.01
    else:
        index_path = directory / 'manifest.json'
        index = {'run_id': directory.name, 'status': 'completed', 'code_snapshot': 'sim_script.py',
                 'code_sha256': source_sha, 'job': 'job.json', 'exit_code': 0,
                 'engine_config': {'dryrun': False}, 'artifacts': {'states': 'trace/states.parquet'},
                 'scene': {'dt': 0.1, 'substeps': 1, 'entities': [{'name': 'cube'}, {'name': 'table'}]},
                 'timing': {'sim_steps': 20, 'trace_sample_dt': 0.1}}
        _write(directory / 'job.json', {'run_id': directory.name, 'code': code,
            'duration_s': 2.0, 'simulation': {'dt': 0.1, 'steps': 20, 'substeps': 1}})
        steps, dt = list(range(21)), 0.1
    _write(index_path, index)
    requirement = _write(tmp_path / 'requirement.json', {'window_seconds': 1.0, 'frame_dt': 0.1})
    source_ref = {'path': requirement.relative_to(tmp_path).as_posix(), 'sha256': collector.digest(requirement)}
    window = {'seconds': 1.0, 'source_ref': source_ref, 'pointer': '/window_seconds',
              'sample_dt_seconds': 0.1, 'sample_dt_pointer': '/frame_dt'}
    rows = []
    for step in steps:
        for name in ('cube', 'table'):
            row = dict.fromkeys(collector._STATE_FIELDS, 0.0)
            row.update(entity=name, step=step, t=step*dt, pos_x=step*0.001 if name == 'cube' else 0.,
                       quat_w=-1. if step % 2 else 1.)
            rows.append(row)
    return directory, branch, index_path, window, rows


def _queries(monkeypatch, rows, *, mutate=None):
    calls = []

    def query(directory, runtime_python, branch, query):
        if mutate and not calls:
            mutate()
        calls.append(query)
        sql = query['sql']
        if 'GROUP BY entity' in sql:
            output = []
            for entity in sorted({r['entity'] for r in rows}):
                selected = [r for r in rows if r['entity'] == entity]
                output.append(dict(entity=entity, n=len(selected), distinct_steps=len({r['step'] for r in selected}),
                    first_step=min(r['step'] for r in selected), last_step=max(r['step'] for r in selected),
                    first_time=min(r['t'] for r in selected), final_time=max(r['t'] for r in selected)))
        elif 'MIN(step)' in sql or 'MAX(step)' in sql:
            step = (min if 'MIN(step)' in sql else max)(r['step'] for r in rows)
            output = [r for r in rows if r['step'] == step]
        elif 'FROM measurements' in sql:
            output = []
        else:
            lower = float(re.search(r't>=([^ ]+)', sql).group(1))
            upper = float(re.search(r't<=([^ ]+)', sql).group(1))
            output = [r for r in rows if lower <= r['t'] <= upper]
        columns = list(output[0]) if output else []
        return {'ok': True, 'run_dir': str(directory if branch is None else directory / 'timeline' / branch),
                'result': {'columns': columns, 'rows': [[r[k] for k in columns] for r in output]},
                'row_count': len(output), 'truncated': False}
    monkeypatch.setattr(collector, '_public_query', query)
    return calls


def _collect(tmp_path, setup, **kwargs):
    directory, branch, _, window, _ = setup
    return collector.collect_evidence(directory, 'unused-python', tmp_path, tmp_path / 'evidence.json',
                                      branch=branch, window=window, asset_family='fixture-boxes', **kwargs)


def _boundary_fixture(tmp_path, monkeypatch, *, resident=False, count=None):
    import base64
    setup = _run(tmp_path, resident=resident)
    index = collector.read_json(setup[2])
    if resident:
        index['boundary_views'] = 'boundary-views.json'
        index.update(dt=0.1)
        index['branches']['main'].update(start_step=0, start_t=0., steps=count, trace_cadence_steps=[1])
        rows = []
        for step in range(count + 1):
            for name in ('cube', 'table'):
                row = dict.fromkeys(collector._STATE_FIELDS, 0.)
                row.update(entity=name, step=step, t=round(step * .1, 9), quat_w=1.)
                rows.append(row)
    else:
        index['artifacts']['boundary_views'] = 'boundary-views.json'
        rows = setup[-1]
    _queries(monkeypatch, rows)
    _write(setup[2], index)
    state = collector.collect_evidence(setup[0], 'unused-python', tmp_path, tmp_path / 'evidence.json',
        branch=setup[1], asset_family='fixture-boxes') if resident else _collect(tmp_path, setup)
    image = setup[0] / 'view.png'
    image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII='))
    groups = []
    for boundary, sample in [('initial', state['initial']), ('final', state['terminal'])]:
        groups.append({'boundary': boundary, 'branch': setup[1], 'step': sample['step'], 't': sample['time_s'],
            'clock_valid': True, 'same_observed_state': True, 'camera_restored': True, 'status': 'complete',
            'state_before_sha256': 'a' * 64, 'state_after_sha256': 'a' * 64,
            'images': [{'view': 'overview', 'camera': 'main', 'path': 'view.png',
                        'sha256': collector.digest(image), 'width': 1, 'height': 1}]})
    packet = {'schema_version': 'boundary-views/1', 'run_id': index['run_id'],
              'code_sha256': index['code_sha256'], 'source_bundle': None, 'groups': groups}
    path = setup[0] / 'boundary-views.json'
    _write(path, packet)
    def refs():
        return [{'path': str(p.relative_to(tmp_path)), 'sha256': collector.digest(p)}
                for p in (tmp_path / 'evidence.json', path)]
    return setup, packet, path, refs
