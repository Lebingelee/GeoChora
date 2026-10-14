"""Opt-in executed-interval trajectories; original v0 types/readers stay unchanged.

Provider-neutral logical data only. Owner snapshots are supplied by the
explicit coordinator adapter. Native contact/state belongs in sidecars.
"""
import copy
import json
import os
from pathlib import Path
import numpy as np
from .contracts import EpisodeMetadata, BoundaryRecord, TransitionRecord
from ...controllers.canonical.contracts import CanonicalControlTarget, AppliedCanonicalControl, digest

SCHEMA = 'canonical-execution-trajectory-v2'
LEGACY_SCHEMA = 'canonical-execution-trajectory-v1'
FILE_SCHEMA = 'task-env-canonical-execution-v2'
LEGACY_FILE_SCHEMA = 'task-env-canonical-execution-v1'


def validate(value):
    import hashlib
    from .streaming import _json_bytes, snapshot_digest
    if set(value) != {'schema','metadata','recipe','boundaries','transitions','blobs','stop_reason'} or value['schema'] not in (SCHEMA, LEGACY_SCHEMA):
        raise ValueError('execution trajectory schema')
    metadata = EpisodeMetadata.from_mapping(value['metadata'])
    boundaries, transitions = value['boundaries'], value['transitions']
    if not boundaries or len(boundaries) != len(transitions)+1:
        raise ValueError('T+1/T invariant')
    if not value['recipe'] or not value['stop_reason']:
        raise ValueError('recipe/stop provenance required')
    encoded_blobs = {}
    for h, blob in value['blobs'].items():
        encoded = _json_bytes(blob)
        if hashlib.sha256(encoded).hexdigest() != h:
            raise ValueError('corrupted owner blob')
        encoded_blobs[h] = encoded
    for i, boundary in enumerate(boundaries):
        if set(boundary) != {'record','owners','stage','native_step_index','task_metrics_raw','native_time'}:
            raise ValueError('boundary fields')
        record = BoundaryRecord.from_mapping(boundary['record'])
        if record.control_step != i or boundary['native_step_index'] != i*metadata.timebase.control_substeps:
            raise ValueError('boundary ordering/native index')
        snap = _resolve_snapshot_readonly(boundary['owners'], value['blobs'])
        integrity = snap['integrity_hash']
        if snapshot_digest(boundary['owners'], encoded_blobs) != integrity or snap['control_step'] != i or snap['simulation_time'] != record.simulation_time:
            raise ValueError('owner integrity/alignment')
        for name, payload in snap['owners'].items():
            expected=value['recipe']['owner_schema'].get(name)
            if expected is None or payload['version']!=expected['version'] or payload['source_sha256']!=expected['source_sha256'] or set(payload['fields'])!=set(expected['fields']):
                raise ValueError('owner schema/source/fields')
        if set(snap['owners'])!=set(value['recipe']['owner_schema']):
            raise ValueError('missing owner')
        stage_index=snap['owners']['coordinator']['fields']['_stage_index']['value']
        if value['recipe']['stages'][stage_index]!=boundary['stage']:
            raise ValueError('coordinator stage mismatch')
        if snap['artifact_hash'] != metadata.task_artifact_hash or snap['controller_identity'] != metadata.controller_identity or snap['solution_identity'] != metadata.expert_identity or snap['provider'] != metadata.execution.physics_provider:
            raise ValueError('owner identity mismatch')
    initial = BoundaryRecord.from_mapping(boundaries[0]['record'])
    if initial.state != metadata.realized_initial_state.measured_state or initial.control_step != 0 or initial.simulation_time != 0.:
        raise ValueError('realized reset mismatch')
    for i, transition in enumerate(transitions):
        if set(transition) != {'record','interval','native_audit'}:
            raise ValueError('transition fields')
        record = TransitionRecord.from_mapping(transition['record'])
        interval = transition['interval']; count=metadata.timebase.control_substeps
        if interval['control_step'] != i or len(interval['substeps']) != count or interval['native_step_count'] != count:
            raise ValueError('missing/skipped native substep')
        if interval['physics_dt'] != metadata.timebase.physics_dt or interval['control_substeps'] != count:
            raise ValueError('interval timebase')
        if value['recipe']['cadence']=='outer-equal-rate' and [s['updated'] for s in interval['substeps']]!=[True]+[False]*(count-1):
            raise ValueError('equal-rate cadence')
        for j, substep in enumerate(interval['substeps']):
            if substep['index'] != j or substep['native_step_index'] != i*count+j+1 or type(substep['updated']) is not bool:
                raise ValueError('substep order/update')
            target = CanonicalControlTarget.from_mapping(substep['target'])
            ack = AppliedCanonicalControl.from_mapping(substep['applied'])
            if ack.target_hash != target.identity_hash or ack.provider_name != metadata.execution.physics_provider or target.controller_identity != metadata.controller_identity or target.task_artifact_hash != metadata.task_artifact_hash:
                raise ValueError('applied/target identity')
            if ack.gripper_force_limit_N != target.gripper.force_limit_N:
                raise ValueError('applied cap')
        # Last effective target is the boundary-level projection, not a fabricated ZOH.
        if interval['substeps'][-1]['target'] != record.controller_target.to_mapping() or interval['substeps'][-1]['applied'] != record.applied_control.to_mapping():
            raise ValueError('final interval projection')
        audit=transition['native_audit']
        if audit['observed_native_substeps'] != count or audit['control_step'] != i+1:
            raise ValueError('independent native count mismatch')
        if i<len(transitions)-1 and (record.terminated or record.truncated):
            raise ValueError('after terminal')
    if value['schema'] == SCHEMA:
        from .clock import validate_clock
        validate_clock(value)
    return value


def _resolve_snapshot_readonly(snapshot, blobs):
    """Resolve owner-field references without copying large immutable field values.

    Used only by read-only validation. Replay retains expand_snapshot's owned
    deep copies, so restored mutable owners cannot alias the stored blobs.
    """
    result = dict(snapshot)
    result['owners'] = {}
    for name, owner in snapshot['owners'].items():
        fields = {}
        for field, entry in owner['fields'].items():
            v = entry['value']
            if isinstance(v, dict) and v.get('kind') == 'content-ref':
                fields[field] = {**entry, 'value': blobs[v['sha256']]}
            else:
                fields[field] = entry
        result['owners'][name] = {**owner, 'fields': fields}
    return result


def expand_snapshot(snapshot, blobs):
    result=copy.deepcopy(snapshot)
    for owner in result['owners'].values():
        for entry in owner['fields'].values():
            v=entry['value']
            if isinstance(v,dict) and v.get('kind')=='content-ref':
                entry['value']=copy.deepcopy(blobs[v['sha256']])
    return result


class ExecutionRecorder:
    """Own the opt-in episode data; receive actual completed application events."""
    def __init__(self, metadata, recipe, *, content_fields=None):
        self.content_fields = frozenset(('_actions',) if content_fields is None else content_fields)
        if not self.content_fields or any(type(field) is not str for field in self.content_fields):
            raise ValueError('named content-addressed owner fields required')
        self.value={'schema':SCHEMA,'metadata':metadata.to_mapping(),'recipe':copy.deepcopy(recipe),
                    'boundaries':[],'transitions':[],'blobs':{},'stop_reason':''}
        from .clock import SCHEMA as CLOCK_SCHEMA
        self.value['recipe']['clock_contract']=CLOCK_SCHEMA
        self.pending=None
        self.frozen=False

    def boundary(self, record, owners, stage, task_metrics=None, native_time=None):
        snap=copy.deepcopy(owners)
        # Lossless content-addressed stage plans; no duplicated mutable owner.
        for owner in snap['owners'].values():
            for field,entry in owner['fields'].items():
                if field in self.content_fields and entry['present']:
                    h=digest(entry['value'])
                    if h not in self.value['blobs']:
                        self.value['blobs'][h]=entry['value']
                    entry['value']={'kind':'content-ref','sha256':h}
        self.value['boundaries'].append({'record':record.to_mapping(),'owners':snap,'stage':stage,
            'native_step_index':record.control_step*self.value['metadata']['timebase']['control_substeps'],
            'task_metrics_raw':copy.deepcopy(task_metrics if task_metrics is not None else dict(record.task_metrics)),
            'native_time':float(record.simulation_time if native_time is None else native_time)})

    def begin(self, step, physics_dt, substeps):
        if self.pending is not None or self.frozen:raise RuntimeError('pending/frozen interval')
        self.pending={'control_step':step,'physics_dt':physics_dt,'control_substeps':substeps,'native_step_count':0,'substeps':[]}

    def applied_substep(self, index, state, feedback, target, applied, diagnostics):
        p=self.pending
        if p is None or index!=len(p['substeps']):raise ValueError('unobserved/out-of-order application')
        p['substeps'].append({'index':index,'native_step_index':p['control_step']*p['control_substeps']+index+1,
            'native_start_time':state.simulation_time,'state':state.to_mapping(),'feedback':feedback.to_mapping(),'target':target.to_mapping(),'applied':applied.to_mapping(),
            'updated':bool(diagnostics['inner_update_performed'])})
        p['native_step_count']+=1

    def append(self, transition, boundary, owners, stage, audit, task_metrics=None, native_time=None):
        if self.pending is None or len(self.value['boundaries'])!=len(self.value['transitions'])+1:
            raise ValueError('recording alignment')
        self.value['transitions'].append({'record':transition.to_mapping(),'interval':self.pending,'native_audit':copy.deepcopy(audit)})
        self.pending=None
        self.boundary(boundary,owners,stage,task_metrics,native_time)

    def freeze(self, stop_reason):
        if self.pending is not None:raise ValueError('incomplete effective interval')
        self.value['stop_reason']=stop_reason;validate(self.value);self.frozen=True
        return self.value


def save(path, value):
    import h5py
    validate(value);path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    if path.exists() or temporary.exists():raise FileExistsError('no overwrite')
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    try:
        with h5py.File(temporary,'x') as h:
            h.attrs['schema']=FILE_SCHEMA if value['schema']==SCHEMA else LEGACY_FILE_SCHEMA;h.attrs['logical_hash']=digest(value)
            h.create_dataset('logical_json_utf8',data=np.frombuffer(raw,dtype=np.uint8),compression='gzip',compression_opts=4)
            h.create_dataset('control_step',data=np.arange(len(value['boundaries']),dtype=np.int64))
            h.create_dataset('native_step_index',data=np.asarray([b['native_step_index'] for b in value['boundaries']],dtype=np.int64))
        os.replace(temporary,path)
    except Exception:
        if temporary.exists():temporary.unlink()
        raise
    return path


def load(path):
    import h5py
    with h5py.File(path,'r') as h:
        if set(h)!={'logical_json_utf8','control_step','native_step_index'} or h.attrs['schema'] not in (FILE_SCHEMA,LEGACY_FILE_SCHEMA):
            raise ValueError('H5 execution schema')
        value=json.loads(h['logical_json_utf8'][:].tobytes());validate(value)
        expected_schema=FILE_SCHEMA if value['schema']==SCHEMA else LEGACY_FILE_SCHEMA
        if h.attrs['schema']!=expected_schema:raise ValueError('H5/logical version mismatch')
        if h.attrs['logical_hash']!=digest(value):raise ValueError('logical hash')
        for name,expected in [('control_step',np.arange(len(value['boundaries']),dtype=np.int64)),('native_step_index',np.asarray([b['native_step_index'] for b in value['boundaries']],dtype=np.int64))]:
            if h[name].dtype!=expected.dtype or not np.array_equal(h[name][:],expected):raise ValueError('numeric projection')
    return value
