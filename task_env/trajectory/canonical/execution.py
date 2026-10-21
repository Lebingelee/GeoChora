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
from ...controllers.canonical.contracts import CanonicalControlTarget, AppliedCanonicalControl, RequestedAction, CanonicalAction, digest
from .episode import BoundaryEventV1,EpisodeOutcomeV1,StructuredControlTransitionV1,validate_episode_records,single_writer_training_actions

SCHEMA = 'canonical-execution-trajectory-v2'
STRUCTURED_SCHEMA = 'canonical-execution-trajectory-v3'
LEGACY_SCHEMA = 'canonical-execution-trajectory-v1'
FILE_SCHEMA = 'task-env-canonical-execution-v2'
STRUCTURED_FILE_SCHEMA = 'task-env-canonical-execution-v3'
LEGACY_FILE_SCHEMA = 'task-env-canonical-execution-v1'


def validate(value):
    import hashlib
    from .streaming import _json_bytes
    base_keys={'schema','metadata','recipe','boundaries','transitions','blobs','stop_reason'}
    schema=value.get('schema')
    expected_keys=base_keys | {'structured_controls','events','outcome'} if schema==STRUCTURED_SCHEMA else base_keys
    if set(value) != expected_keys or schema not in (SCHEMA, STRUCTURED_SCHEMA, LEGACY_SCHEMA):
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
        validate_boundary_record(boundary, i, metadata, value['recipe'], value['blobs'], encoded_blobs)
    initial = BoundaryRecord.from_mapping(boundaries[0]['record'])
    if initial.state != metadata.realized_initial_state.measured_state or initial.control_step != 0 or initial.simulation_time != 0.:
        raise ValueError('realized reset mismatch')
    for i, transition in enumerate(transitions):
        validate_transition_record(transition, i, len(transitions), metadata, value['recipe'])
    if schema in (SCHEMA,STRUCTURED_SCHEMA):
        from .clock import validate_clock
        validate_clock(value)
    if schema==STRUCTURED_SCHEMA:
        controls=tuple(StructuredControlTransitionV1.from_mapping(item) for item in value['structured_controls'])
        events=tuple(BoundaryEventV1.from_mapping(item) for item in value['events'])
        outcome=EpisodeOutcomeV1.from_mapping(value['outcome'])
        if len(controls)!=len(transitions):raise ValueError('structured control T alignment')
        validate_episode_records(events,outcome,len(transitions))
        if outcome.end_reason!=value['stop_reason']:raise ValueError('outcome/stop reason mismatch')
        for control,transition in zip(controls,transitions,strict=True):
            if len(control.writer_controls)!=1:raise ValueError('execution trajectory v3 requires the existing single Controller writer route')
            writer=control.writer_controls[0]
            record=TransitionRecord.from_mapping(transition['record'])
            if RequestedAction.from_mapping(writer['requested_action'])!=record.requested_action:raise ValueError('structured/execution requested action mismatch')
            if CanonicalAction.from_mapping(writer['canonical_action'])!=record.canonical_action:raise ValueError('structured/execution canonical action mismatch')
            target=writer['controller_target']
            applied=writer['applied_control']
            if target['identity_hash']!=record.controller_target.identity_hash or CanonicalControlTarget.from_mapping(target['payload'])!=record.controller_target:raise ValueError('structured/execution target mismatch')
            if applied['target_hash']!=record.applied_control.target_hash or AppliedCanonicalControl.from_mapping(applied['payload'])!=record.applied_control:raise ValueError('structured/execution applied control mismatch')
    return value


def validate_boundary_record(boundary, index, metadata, recipe, blobs, encoded_blobs):
    """Validate one boundary; shared by resident and streaming validators."""
    from .streaming import snapshot_digest
    if set(boundary) != {'record','owners','stage','native_step_index','task_metrics_raw','native_time'}:
        raise ValueError('boundary fields')
    record = BoundaryRecord.from_mapping(boundary['record'])
    if record.control_step != index or boundary['native_step_index'] != index*metadata.timebase.control_substeps:
        raise ValueError('boundary ordering/native index')
    snap = _resolve_snapshot_readonly(boundary['owners'], blobs)
    integrity = snap['integrity_hash']
    if snapshot_digest(boundary['owners'], encoded_blobs) != integrity or snap['control_step'] != index or snap['simulation_time'] != record.simulation_time:
        raise ValueError('owner integrity/alignment')
    for name, payload in snap['owners'].items():
        expected = recipe['owner_schema'].get(name)
        if expected is None or payload['version'] != expected['version'] or payload['source_sha256'] != expected['source_sha256'] or set(payload['fields']) != set(expected['fields']):
            raise ValueError('owner schema/source/fields')
    if set(snap['owners']) != set(recipe['owner_schema']):
        raise ValueError('missing owner')
    stage_index = snap['owners']['coordinator']['fields']['_stage_index']['value']
    if recipe['stages'][stage_index] != boundary['stage']:
        raise ValueError('coordinator stage mismatch')
    if snap['artifact_hash'] != metadata.task_artifact_hash or snap['controller_identity'] != metadata.controller_identity or snap['solution_identity'] != metadata.expert_identity or snap['provider'] != metadata.execution.physics_provider:
        raise ValueError('owner identity mismatch')
    return record, snap


def validate_transition_record(transition, index, transition_count, metadata, recipe):
    """Validate one executed interval; shared by resident and streaming validators."""
    if set(transition) != {'record','interval','native_audit'}:
        raise ValueError('transition fields')
    record = TransitionRecord.from_mapping(transition['record'])
    interval = transition['interval']
    count = metadata.timebase.control_substeps
    if interval['control_step'] != index or len(interval['substeps']) != count or interval['native_step_count'] != count:
        raise ValueError('missing/skipped native substep')
    if interval['physics_dt'] != metadata.timebase.physics_dt or interval['control_substeps'] != count:
        raise ValueError('interval timebase')
    if recipe['cadence'] == 'outer-equal-rate' and [s['updated'] for s in interval['substeps']] != [True] + [False]*(count-1):
        raise ValueError('equal-rate cadence')
    for j, substep in enumerate(interval['substeps']):
        if substep['index'] != j or substep['native_step_index'] != index*count+j+1 or type(substep['updated']) is not bool:
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
    audit = transition['native_audit']
    if audit['observed_native_substeps'] != count or audit['control_step'] != index+1:
        raise ValueError('independent native count mismatch')
    if index < transition_count-1 and (record.terminated or record.truncated):
        raise ValueError('after terminal')
    return record


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
    def __init__(self, metadata, recipe, *, content_fields=None, owner_content_fields=None, schema=SCHEMA):
        if schema not in (SCHEMA,STRUCTURED_SCHEMA):raise ValueError('unsupported execution recorder schema')
        self.content_fields = frozenset(('_actions',) if content_fields is None else content_fields)
        if not self.content_fields or any(type(field) is not str for field in self.content_fields):
            raise ValueError('named content-addressed owner fields required')
        scoped = tuple(() if owner_content_fields is None else owner_content_fields)
        if any(not isinstance(pair, (tuple, list)) or len(pair) != 2 or
               any(type(part) is not str or not part for part in pair) for pair in scoped):
            raise ValueError('named owner/field content-addressed selectors required')
        self.owner_content_fields = frozenset(tuple(pair) for pair in scoped)
        self.value={'schema':schema,'metadata':metadata.to_mapping(),'recipe':copy.deepcopy(recipe),
                    'boundaries':[],'transitions':[],'blobs':{},'stop_reason':''}
        if schema==STRUCTURED_SCHEMA:
            self.value.update(structured_controls=[],events=[],outcome=None)
        from .clock import SCHEMA as CLOCK_SCHEMA
        self.value['recipe']['clock_contract']=CLOCK_SCHEMA
        self.pending=None
        self.frozen=False

    def _prepare_boundary(self, record, owners, stage, task_metrics=None, native_time=None):
        for owner_name, field in self.owner_content_fields:
            if owner_name not in owners['owners'] or field not in owners['owners'][owner_name]['fields']:
                raise ValueError('unknown content-addressed owner field')
        snap=copy.deepcopy(owners)
        blobs={}
        # Lossless content-addressed stage plans; no duplicated mutable owner.
        for owner_name, owner in snap['owners'].items():
            for field,entry in owner['fields'].items():
                if (field in self.content_fields or
                        (owner_name, field) in self.owner_content_fields) and entry['present']:
                    h=digest(entry['value'])
                    if h not in self.value['blobs']:
                        blobs[h]=entry['value']
                    entry['value']={'kind':'content-ref','sha256':h}
        entry={'record':record.to_mapping(),'owners':snap,'stage':stage,
            'native_step_index':record.control_step*self.value['metadata']['timebase']['control_substeps'],
            'task_metrics_raw':copy.deepcopy(task_metrics if task_metrics is not None else dict(record.task_metrics)),
            'native_time':float(record.simulation_time if native_time is None else native_time)}
        return entry, blobs

    def boundary(self, record, owners, stage, task_metrics=None, native_time=None):
        entry, blobs = self._prepare_boundary(record, owners, stage, task_metrics, native_time)
        self.value['blobs'].update(blobs)
        self.value['boundaries'].append(entry)

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

    def event(self,event):
        if self.frozen:raise RuntimeError('recorder frozen')
        if self.value['schema']!=STRUCTURED_SCHEMA:raise ValueError('BoundaryEvent requires execution trajectory v3')
        if not isinstance(event,BoundaryEventV1) or event.boundary_index!=len(self.value['boundaries'])-1:raise ValueError('event must reference the current completed boundary')
        same=[item for item in self.value['events'] if item['boundary_index']==event.boundary_index]
        if event.event_sequence!=len(same):raise ValueError('boundary event sequence')
        if self.value['events'] and event.episode_id!=self.value['events'][0]['episode_id']:raise ValueError('event episode identity mismatch')
        self.value['events'].append(event.to_mapping())

    def append(self, transition, boundary, owners, stage, audit, task_metrics=None, native_time=None, *, structured_control=None):
        if self.pending is None or len(self.value['boundaries'])!=len(self.value['transitions'])+1:
            raise ValueError('recording alignment')
        if self.value['schema']==STRUCTURED_SCHEMA:
            if not isinstance(structured_control,StructuredControlTransitionV1):raise ValueError('execution trajectory v3 requires structured control evidence for each transition')
        elif structured_control is not None:raise ValueError('structured control requires execution trajectory v3')
        transition_entry={'record':transition.to_mapping(),'interval':copy.deepcopy(self.pending),'native_audit':copy.deepcopy(audit)}
        structured_entry=(structured_control.to_mapping() if self.value['schema']==STRUCTURED_SCHEMA else None)
        boundary_entry, blobs = self._prepare_boundary(boundary,owners,stage,task_metrics,native_time)
        transitions=self.value.get('transitions')
        boundaries=self.value.get('boundaries')
        stored_blobs=self.value.get('blobs')
        controls=self.value.get('structured_controls') if self.value['schema']==STRUCTURED_SCHEMA else None
        if not isinstance(transitions,list) or not isinstance(boundaries,list) or not isinstance(stored_blobs,dict):
            raise ValueError('execution recorder storage containers')
        if self.value['schema']==STRUCTURED_SCHEMA and not isinstance(controls,list):
            raise ValueError('execution recorder structured control storage')
        # Prepare all serialized rows before mutating the stream. A rejected
        # boundary must leave the observed interval pending and uncommitted.
        stored_blobs.update(blobs)
        transitions.append(transition_entry)
        if controls is not None:controls.append(structured_entry)
        boundaries.append(boundary_entry)
        self.pending=None

    def freeze(self, stop_reason, *, outcome=None):
        if self.pending is not None:raise ValueError('incomplete effective interval')
        self.value['stop_reason']=stop_reason
        if self.value['schema']==STRUCTURED_SCHEMA:
            if not isinstance(outcome,EpisodeOutcomeV1):raise ValueError('execution trajectory v3 requires EpisodeOutcomeV1')
            if outcome.end_reason!=stop_reason:raise ValueError('outcome/stop reason mismatch')
            self.value['outcome']=outcome.to_mapping()
        elif outcome is not None:raise ValueError('EpisodeOutcome requires execution trajectory v3')
        validate(self.value);self.frozen=True
        return self.value


def save(path, value):
    import h5py
    validate(value);path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    if path.exists() or temporary.exists():raise FileExistsError('no overwrite')
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    file_schema={SCHEMA:FILE_SCHEMA,STRUCTURED_SCHEMA:STRUCTURED_FILE_SCHEMA,LEGACY_SCHEMA:LEGACY_FILE_SCHEMA}[value['schema']]
    try:
        with h5py.File(temporary,'x') as h:
            h.attrs['schema']=file_schema;h.attrs['logical_hash']=digest(value)
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
        if set(h)!={'logical_json_utf8','control_step','native_step_index'} or h.attrs['schema'] not in (FILE_SCHEMA,STRUCTURED_FILE_SCHEMA,LEGACY_FILE_SCHEMA):
            raise ValueError('H5 execution schema')
        value=json.loads(h['logical_json_utf8'][:].tobytes());validate(value)
        expected_schema={SCHEMA:FILE_SCHEMA,STRUCTURED_SCHEMA:STRUCTURED_FILE_SCHEMA,LEGACY_SCHEMA:LEGACY_FILE_SCHEMA}[value['schema']]
        if h.attrs['schema']!=expected_schema:raise ValueError('H5/logical version mismatch')
        if h.attrs['logical_hash']!=digest(value):raise ValueError('logical hash')
        for name,expected in [('control_step',np.arange(len(value['boundaries']),dtype=np.int64)),('native_step_index',np.asarray([b['native_step_index'] for b in value['boundaries']],dtype=np.int64))]:
            if h[name].dtype!=expected.dtype or not np.array_equal(h[name][:],expected):raise ValueError('numeric projection')
    return value


def training_actions(value,*,action_schema_id,components):
    """Create a lossless legacy-vector projection only for an exact one-writer route."""
    validate(value)
    if value['schema']!=STRUCTURED_SCHEMA:raise ValueError('structured training conversion requires execution trajectory v3')
    controls=tuple(StructuredControlTransitionV1.from_mapping(item) for item in value['structured_controls'])
    return single_writer_training_actions(controls,action_schema_id=action_schema_id,components=components)
