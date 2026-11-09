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
class PositionControlBatchV1:
    """Complete, source-bound set of position writers for one outer interval."""

    targets: tuple

    @property
    def identity_hash(self):
        payload = tuple((target.writer_id, target.identity_hash) for target in self.targets)
        return hashlib.sha256(json.dumps(
            {'schema_version': 'position-control-batch-v1', 'targets': payload},
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def validate(self):
        from ...controllers.canonical.contracts import PositionControlTargetV1
        if type(self.targets) is not tuple or len(self.targets) < 2:
            raise ValueError('position batch requires at least two immutable writer targets')
        if any(type(target) is not PositionControlTargetV1 for target in self.targets):
            raise TypeError('position batch contains a noncanonical writer target')
        for target in self.targets:
            target.validate()
        writer_ids = tuple(target.writer_id for target in self.targets)
        if len(set(writer_ids)) != len(writer_ids):
            raise ValueError('position batch contains duplicate writers')
        first = self.targets[0]
        if any(target.source_boundary != first.source_boundary
               or target.sample_clock != first.sample_clock
               or target.source_closure_digest != first.source_closure_digest
               or target.target.task_artifact_hash != first.target.task_artifact_hash
               for target in self.targets[1:]):
            raise ValueError('position batch targets do not share one source-bound interval')


@dataclass(frozen=True)
class PositionControlBatchAcknowledgementV1:
    """One receipt value covering all provider acknowledgements in a batch."""

    acknowledgements: tuple
    identity_hash: str


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


@dataclass(frozen=True)
class ControlSubmissionReceiptV2:
    """Acknowledged logical submission with explicit writer/resource ownership."""

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
    resource_owners: tuple[tuple[str, tuple[str, ...]], ...]
    attempted_writer_ids: tuple[str, ...]
    completed_writer_ids: tuple[str, ...]
    units: tuple[str, ...]
    lowering: str
    status: str
    acknowledgement_type: str
    acknowledgement_sha256: str | None

    def validate(self):
        if self.schema_version != 'control-submission-receipt-v2':
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
        if self.status != 'acknowledged':
            raise ValueError('v2 receipt represents only an acknowledged submission')
        for name in ('attempted_writer_ids', 'completed_writer_ids'):
            if getattr(self, name) != self.writer_ids:
                raise ValueError(f'{name} must cover every acknowledged writer in order')
        owners = self.resource_owners
        if type(owners) is not tuple:
            raise ValueError('resource ownership must be an immutable tuple')
        if owners:
            owner_ids = []
            resources = []
            for row in owners:
                if type(row) is not tuple or len(row) != 2 or type(row[1]) is not tuple:
                    raise ValueError('resource ownership rows must be (writer, resource tuple)')
                _token(row[0], 'resource owner')
                owner_ids.append(row[0])
                for resource in row[1]:
                    _token(resource, 'resource ownership')
                resources.extend(row[1])
            if (len(owner_ids) != len(set(owner_ids)) or set(owner_ids) != set(self.writer_ids)
                    or len(resources) != len(set(resources))
                    or set(resources) != set(self.resource_ids)):
                raise ValueError('resource ownership is conflicting or incomplete')
        elif self.command_kind == 'position-target':
            raise ValueError('Position receipt requires explicit writer/resource ownership')
        if self.acknowledgement_sha256 is not None:
            _digest(self.acknowledgement_sha256, 'acknowledgement identity')

    def to_mapping(self):
        return asdict(self)


def _preflight_control_command(session, command, *, command_kind, command_sha256,
                           source_id, source_closure_sha256, artifact_sha256,
                           boundary, sample_clock, controller_generation,
                           controller_identities, writer_ids, resource_ids, units,
                           lowering, lower, resource_owners=None,
                           submission_progress=None):
    """Validate one typed submission without consuming its boundary or writing.

    A multi-Controller Position batch is preflighted as a whole and committed under
    one replay key. ``submission_progress`` must be empty before the lowerer
    records attempted and acknowledged writers.
    """
    from ...controllers.canonical.contracts import CanonicalControlTarget, PositionControlTargetV1
    from .physical_control import ResolvedPhysicalBatchV1
    from .leaf_control import LeafPreparedBatchV1
    is_position_batch = type(command) is PositionControlBatchV1
    is_leaf_batch = type(command) is LeafPreparedBatchV1

    if command_kind == 'position-target':
        if is_position_batch or is_leaf_batch:
            command.validate()
        elif type(command) not in {PositionControlTargetV1, CanonicalControlTarget}:
            raise TypeError('position lifecycle requires a typed canonical position target')
        else:
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
    # Validate identities carried by the typed payload against the outer
    # submission before consuming the boundary or touching a provider. The
    # legacy canonical target has no boundary/source fields; those remain
    # established by the already admitted source-bound caller.
    if command_kind == 'physical-effort-batch':
        context = command.input_batch.context
        if (context.source_id != source_id
                or context.source_closure_sha256 != source_closure_sha256
                or context.artifact_sha256 != artifact_sha256
                or context.boundary != boundary or context.clock != sample_clock
                or context.generation != controller_generation):
            raise ValueError('physical batch context differs from the control submission')
    elif not is_leaf_batch:
        targets = command.targets if is_position_batch else (command,)
        for item in targets:
            if type(item) is PositionControlTargetV1:
                if (item.source_boundary != boundary or item.sample_clock != sample_clock
                        or item.source_closure_digest != source_closure_sha256
                        or item.target.task_artifact_hash != artifact_sha256
                        or item.controller_identity not in controller_identities
                        or item.writer_id not in writer_ids):
                    raise ValueError('position target identity differs from the control submission')
            elif type(item) is CanonicalControlTarget:
                if (item.task_artifact_hash != artifact_sha256
                        or item.controller_identity not in controller_identities):
                    raise ValueError('canonical target identity differs from the control submission')
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
    if resource_owners is None:
        resource_owners = ((writer_ids[0], resource_ids),) if len(writer_ids) == 1 else ()
    if type(resource_owners) is not tuple:
        raise ValueError('resource ownership must be an immutable tuple')
    if resource_owners:
        owner_ids = []
        flattened_resources = []
        for row in resource_owners:
            if type(row) is not tuple or len(row) != 2 or type(row[1]) is not tuple:
                raise ValueError('resource ownership rows must be (writer, resource tuple)')
            owner_id, owned = row
            if owner_id not in writer_ids or type(owned) is not tuple or not owned:
                raise ValueError('resource ownership names an unknown writer or empty resource set')
            owner_ids.append(owner_id)
            for resource in owned:
                _token(resource, 'resource ownership')
            flattened_resources.extend(owned)
        if (len(owner_ids) != len(set(owner_ids)) or set(owner_ids) != set(writer_ids)
                or len(flattened_resources) != len(set(flattened_resources))
                or set(flattened_resources) != set(resource_ids)):
            raise ValueError('resource ownership conflicts or does not cover the complete batch')
    elif is_position_batch or is_leaf_batch:
        raise ValueError('multi-writer Position batch requires explicit resource ownership')
    if is_position_batch:
        target_writers = tuple(target.writer_id for target in command.targets)
        if target_writers != writer_ids:
            raise ValueError('position batch targets differ from the submitted writer set')
    if is_leaf_batch and tuple(item.writer_id for item in command.commands) != writer_ids:
        raise ValueError('leaf batch commands differ from the submitted writer set')
    if command_kind == 'physical-effort-batch':
        batch = command.input_batch
        contributions = (*batch.joint_efforts, *batch.body_wrenches, *batch.extensions)
        payload_writers = {item.contribution.owner_id for item in contributions}
        payload_resources = {
            *(f'{item.entity_id}/{item.joint_id}' for item in command.joints),
            *(f'{item.entity_id}/{item.body_id}' for item in command.body_wrenches),
            *(str(getattr(item, 'target_key', type(item).__name__)) for item in command.extensions),
        }
        if payload_writers != set(writer_ids) or payload_resources != set(resource_ids):
            raise ValueError('physical batch writers or resources differ from the submission')
    # For typed Position profiles the materialized session retains the
    # compiled source-bound plan. Caller-supplied ownership metadata must be
    # a projection of that plan, not merely a self-consistent list of names.
    if command_kind == 'position-target' and not is_leaf_batch:
        typed_targets = command.targets if is_position_batch else (command,)
        if all(type(item) is PositionControlTargetV1 for item in typed_targets):
            plan = getattr(session, '_control_binding_plan', None)
            if plan is not None:
                from .control import ControlBindingPlanV1
                if type(plan) is not ControlBindingPlanV1 or not plan._compiled:
                    raise TypeError('position submission requires its compiled binding plan')
                if (plan.scene_identity_hash != boundary.scene_identity_hash
                        or (plan.artifact_identity_hash is not None
                            and plan.artifact_identity_hash != artifact_sha256)
                        or (plan.source_closure_digest is not None
                            and plan.source_closure_digest != source_closure_sha256)
                        or any(item.binding_identity_hash != plan.identity_hash for item in typed_targets)):
                    raise ValueError('position target differs from the materialized binding plan')
                expected = tuple(sorted(
                    (writer, tuple(sorted(f'{entity}/{actuator}'
                                          for entity, actuator, owner in plan.resource_writers
                                          if owner == writer)))
                    for writer in writer_ids))
                if tuple(sorted(resource_owners)) != expected or any(not resources for _, resources in expected):
                    raise ValueError('position resources differ from the materialized binding plan')
    if submission_progress is not None:
        if (type(submission_progress) is not dict
                or type(submission_progress.get('attempted_writer_ids')) is not list
                or type(submission_progress.get('completed_writer_ids')) is not list
                or submission_progress['attempted_writer_ids']
                or submission_progress['completed_writer_ids']):
            raise ValueError('submission progress must start as empty attempted/completed lists')
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
                or set(controller_identities) != set(lifecycle.controller_identities)
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
        'resource_ids': resource_ids, 'resource_owners': resource_owners,
        'units': units, 'lowering': lowering,
    }
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return payload, identity, lifecycle


def submit_control_command(session, command, *, command_kind, command_sha256,
                           source_id, source_closure_sha256, artifact_sha256,
                           boundary, sample_clock, controller_generation,
                           controller_identities, writer_ids, resource_ids, units,
                           lowering, lower, resource_owners=None,
                           submission_progress=None):
    """Commit one previously typed command under the existing replay key."""
    payload, identity, lifecycle = _preflight_control_command(
        session, command, command_kind=command_kind, command_sha256=command_sha256,
        source_id=source_id, source_closure_sha256=source_closure_sha256,
        artifact_sha256=artifact_sha256, boundary=boundary, sample_clock=sample_clock,
        controller_generation=controller_generation, controller_identities=controller_identities,
        writer_ids=writer_ids, resource_ids=resource_ids, units=units, lowering=lowering,
        lower=lower, resource_owners=resource_owners, submission_progress=submission_progress)
    provider = payload['provider']
    materialization_id = payload['materialization_id']
    episode_id = payload['episode_id']
    resource_owners = payload['resource_owners']
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
        attempted = tuple(writer_ids)
        completed = tuple(writer_ids)
        if submission_progress is not None:
            attempted = tuple(submission_progress['attempted_writer_ids'])
            completed = tuple(submission_progress['completed_writer_ids'])
            if attempted != tuple(writer_ids) or completed != tuple(writer_ids):
                raise ValueError('provider lowerer returned before every Position writer was acknowledged')
        ack_identity = None
        for name in ('identity_hash', 'target_hash', 'batch_sha256'):
            candidate = getattr(ack, name, None)
            if isinstance(candidate, str) and len(candidate) == 64:
                ack_identity = candidate
                break
        receipt = ControlSubmissionReceiptV2(
            'control-submission-receipt-v2', identity, command_kind, command_sha256,
            provider, materialization_id, source_id, source_closure_sha256, artifact_sha256,
            episode_id, boundary.boundary_id, boundary.state_revision, boundary.control_step,
            sample_clock.sample_index, controller_generation, controller_identities, writer_ids,
            resource_ids, resource_owners, attempted, completed, units, lowering,
            'acknowledged', type(ack).__name__, ack_identity)
        receipt.validate()
        session._last_control_submission = receipt.to_mapping()
        if lifecycle is not None:
            from dataclasses import replace
            session._control_lifecycle_dispatch = replace(lifecycle, stage='committed')
        return ack
    except BaseException as error:
        attempted = (() if submission_progress is None else
                     tuple(submission_progress['attempted_writer_ids']))
        completed = (() if submission_progress is None else
                     tuple(submission_progress['completed_writer_ids']))
        status = 'failed_partial' if attempted else 'failed'
        session._last_control_submission = {**payload, 'submission_id': identity,
                                            'status': status, 'error_type': type(error).__name__,
                                            'attempted_writer_ids': attempted,
                                            'completed_writer_ids': completed}
        if lifecycle is not None:
            from dataclasses import replace
            session._control_lifecycle_dispatch = replace(lifecycle, stage='failed')
        raise
