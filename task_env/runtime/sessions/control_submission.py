"""Common source-bound control commit owner for typed selected controls.

Position targets and physical effort batches retain different units and native
lowerings. This module owns the shared identity, episode/boundary/clock,
writer/resource, replay, and one-logical-submission checks immediately before a
provider write.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math


def _token(value, label):
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f'{label} must be a nonempty trimmed string')


def _digest(value, label):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'{label} must be a lowercase SHA-256')


@dataclass(frozen=True)
class ControlSubmissionReceiptV1:
    schema_version: str
    submission_id: str
    command_kind: str
    command_sha256: str
    provider: str
    materialization_id: str
    source_id: str
    source_closure_sha256: str
    artifact_sha256: str
    episode_id: str
    state_boundary_id: str
    state_revision: int
    control_step: int
    sample_index: int
    controller_generation: int
    controller_identities: tuple[str, ...]
    writer_ids: tuple[str, ...]
    resource_ids: tuple[str, ...]
    units: tuple[str, ...]
    lowering: str
    status: str
    acknowledgement_type: str
    acknowledgement_sha256: str | None

    def validate(self):
        if self.schema_version != 'control-submission-receipt-v1':
            raise ValueError('unsupported control submission receipt')
        for name in ('submission_id', 'command_sha256', 'source_closure_sha256', 'artifact_sha256'):
            _digest(getattr(self, name), name)
        for name in ('command_kind', 'provider', 'materialization_id', 'source_id', 'episode_id',
                     'state_boundary_id', 'lowering', 'status', 'acknowledgement_type'):
            _token(getattr(self, name), name)
        for name in ('state_revision', 'control_step', 'sample_index', 'controller_generation'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f'{name} must be a nonnegative integer')
        if self.control_step != self.sample_index:
            raise ValueError('control submission clock must identify its boundary')
        for name in ('controller_identities', 'writer_ids', 'resource_ids', 'units'):
            values = getattr(self, name)
            if type(values) is not tuple or not values:
                raise ValueError(f'{name} must be a nonempty immutable tuple')
            for value in values:
                _token(value, name)
            if len(set(values)) != len(values):
                raise ValueError(f'{name} must not contain duplicates')
        if self.status not in {'acknowledged', 'failed'}:
            raise ValueError('invalid control submission status')
        if self.acknowledgement_sha256 is not None:
            _digest(self.acknowledgement_sha256, 'acknowledgement identity')

    def to_mapping(self):
        return asdict(self)


def submit_control_command(session, command, *, command_kind, command_sha256,
                           source_id, source_closure_sha256, artifact_sha256,
                           boundary, sample_clock, controller_generation,
                           controller_identities, writer_ids, resource_ids, units,
                           lowering, lower):
    """Validate one common commit envelope and perform exactly one provider write.

    The consumed key is installed before ``lower`` so an interrupted or partial
    provider write cannot be replayed against the same outer control interval.
    """
    from ...controllers.canonical.contracts import CanonicalControlTarget, PositionControlTargetV1
    from .physical_control import ResolvedPhysicalBatchV1

    if command_kind == 'position-target':
        if type(command) not in {PositionControlTargetV1, CanonicalControlTarget}:
            raise TypeError('position lifecycle requires a typed canonical position target')
        command.validate()
    elif command_kind == 'physical-effort-batch':
        if type(command) is not ResolvedPhysicalBatchV1:
            raise TypeError('effort lifecycle requires ResolvedPhysicalBatchV1')
        if type(command.input_batch).__name__ != 'PhysicalCommandBatchV1':
            raise TypeError('effort lifecycle requires a typed physical command batch')
        command.input_batch.validate()
    else:
        raise ValueError('unsupported typed control command kind')
    if not callable(lower):
        raise TypeError('provider lowering must be callable')
    for value, label in ((command_sha256, 'command'), (source_closure_sha256, 'source closure'),
                         (artifact_sha256, 'artifact')):
        _digest(value, label)
    if command_sha256 != (command.identity_hash if command_kind == 'position-target'
                          else command.input_batch.identity_hash):
        raise ValueError('control command identity differs from the typed command')
    provider = getattr(session, '_provider', 'test-double')
    materialization_id = getattr(session, 'provider_materialization_id',
                                 getattr(boundary, 'provider_materialization_id', None))
    if type(provider) is not str or not provider or type(materialization_id) is not str or not materialization_id:
        raise ValueError('control commit requires the live provider materialization identity')
    boundary_reader = getattr(session, 'state_boundary_identity', None)
    if callable(boundary_reader):
        active_boundary = boundary_reader()
        if active_boundary != boundary:
            raise ValueError('control commit state boundary is stale')
    else:
        state_reader = getattr(session, 'snapshot', None)
        state = state_reader() if callable(state_reader) else None
        publication = getattr(session, 'publication', None)
        published_view = getattr(publication, 'view', None)
        published_boundary = getattr(published_view, 'boundary', None)
        published_clock = getattr(published_view, 'sample_clock', None)
        if state is not None:
            valid_boundary = getattr(state, 'control_step', None) == getattr(boundary, 'control_step', None)
        else:
            valid_boundary = published_boundary == boundary and published_clock == sample_clock
        if not valid_boundary:
            raise ValueError('control commit state boundary cannot be verified')
    episode_id = getattr(boundary, 'episode_id', None)
    active_episode = getattr(session, 'episode_id', episode_id)
    if episode_id != active_episode:
        raise ValueError('control commit belongs to an old episode')
    if getattr(boundary, 'provider_materialization_id', None) != materialization_id:
        raise ValueError('control commit boundary belongs to another provider materialization')
    if getattr(boundary, 'control_step', None) != getattr(sample_clock, 'sample_index', None):
        raise ValueError('control commit sample clock differs from its boundary')
    if type(controller_generation) is not int or controller_generation < 0:
        raise ValueError('Controller generation must be nonnegative')
    session_generation = getattr(session, 'physical_control_generation', None)
    if session_generation is not None and session_generation != controller_generation:
        raise ValueError('control commit Controller generation is stale')
    source = getattr(session, '_source', None)
    artifact = getattr(session, '_artifact', None)
    source_mismatch = (source is not None and (
        getattr(source, 'source_id', None) != source_id
        or getattr(source, 'source_closure_digest', None) != source_closure_sha256))
    artifact_mismatch = (artifact is not None
                         and getattr(artifact, 'identity_hash', None) != artifact_sha256)
    if source_mismatch or artifact_mismatch:
        raise ValueError('control commit source or Artifact identity is stale')

    for values, label in ((controller_identities, 'Controller identities'),
                          (writer_ids, 'writer identities'), (resource_ids, 'resource identities'),
                          (units, 'typed units')):
        if type(values) is not tuple or not values:
            raise ValueError(f'{label} must be a nonempty immutable tuple')
        if any(type(value) is not str or not value.strip() for value in values):
            raise ValueError(f'{label} must contain names')
        if len(set(values)) != len(values):
            raise ValueError(f'{label} must be unique within one submission')
    if any(not math.isfinite(float(getattr(sample_clock, name)))
           for name in ('simulation_time_s',)):
        raise ValueError('control commit sample clock is nonfinite')

    lifecycle = getattr(session, '_control_lifecycle_dispatch', None)
    if lifecycle is not None:
        from .control_lifecycle import ControlLifecycleDispatchV1
        if (type(lifecycle) is not ControlLifecycleDispatchV1
                or lifecycle.schema_version != 'control-lifecycle-dispatch-v1'
                or lifecycle.command_kind != command_kind
                or lifecycle.source_id != source_id
                or lifecycle.source_closure_sha256 != source_closure_sha256
                or lifecycle.artifact_sha256 != artifact_sha256
                or lifecycle.episode_id != episode_id
                or lifecycle.state_boundary_id != boundary.boundary_id
                or lifecycle.control_step != boundary.control_step
                or lifecycle.controller_generation != controller_generation
                or not set(controller_identities) <= set(lifecycle.controller_identities)
                or lifecycle.stage not in {'preparing', 'prepared'}):
            raise ValueError('control submission differs from the shared lifecycle dispatch')

    payload = {
        'schema_version': 'control-submission-receipt-v1', 'command_kind': command_kind,
        'command_sha256': command_sha256, 'provider': provider,
        'materialization_id': materialization_id, 'source_id': source_id,
        'source_closure_sha256': source_closure_sha256, 'artifact_sha256': artifact_sha256,
        'episode_id': episode_id, 'state_boundary_id': boundary.boundary_id,
        'state_revision': boundary.state_revision, 'control_step': boundary.control_step,
        'sample_index': sample_clock.sample_index, 'controller_generation': controller_generation,
        'controller_identities': controller_identities, 'writer_ids': writer_ids,
        'resource_ids': resource_ids, 'units': units, 'lowering': lowering,
    }
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    consumed = getattr(session, '_control_submission_consumed', None)
    if consumed is None:
        consumed = set()
        session._control_submission_consumed = consumed
    replay_key = (episode_id, boundary.boundary_id)
    if replay_key in consumed:
        raise ValueError('control interval already has a logical submission')
    consumed.add(replay_key)
    session._last_control_submission = {**payload, 'submission_id': identity, 'status': 'pending'}
    ack = None
    try:
        ack = lower()
        ack_identity = None
        for name in ('identity_hash', 'target_hash', 'batch_sha256'):
            candidate = getattr(ack, name, None)
            if isinstance(candidate, str) and len(candidate) == 64:
                ack_identity = candidate
                break
        receipt = ControlSubmissionReceiptV1(
            'control-submission-receipt-v1', identity, command_kind, command_sha256,
            provider, materialization_id, source_id, source_closure_sha256, artifact_sha256,
            episode_id, boundary.boundary_id, boundary.state_revision, boundary.control_step,
            sample_clock.sample_index, controller_generation, controller_identities, writer_ids,
            resource_ids, units, lowering, 'acknowledged', type(ack).__name__, ack_identity)
        receipt.validate()
        session._last_control_submission = receipt.to_mapping()
        if lifecycle is not None:
            from dataclasses import replace
            session._control_lifecycle_dispatch = replace(lifecycle, stage='committed')
        return ack
    except BaseException as error:
        session._last_control_submission = {**payload, 'submission_id': identity,
                                            'status': 'failed', 'error_type': type(error).__name__}
        if lifecycle is not None:
            from dataclasses import replace
            session._control_lifecycle_dispatch = replace(lifecycle, stage='failed')
        raise
