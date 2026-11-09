"""Common source-bound control commit owner for typed selected controls.

Position targets and physical effort batches retain different units and native
lowerings. This module owns the shared identity, episode/boundary/clock,
writer/resource, replay, and one-logical-submission checks immediately before a
provider write.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math


def _token(value, label):
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f'{label} must be a nonempty trimmed string')


def _digest(value, label):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'{label} must be a lowercase SHA-256')


def _validate_resource_intervals(claims, *, writer_resources, substeps):
    """Validate exclusive, source-authorized resource claims on half-open ticks.

    Claims are (writer, resource, start, end). A writer may submit several
    precomputed claims for the same resource when their ranges do not overlap.
    This is admission only; it neither schedules nor advances physics.
    """
    if type(substeps) is not int or substeps <= 0:
        raise ValueError('scene substep count must be a positive integer')
    if type(claims) is not tuple or not claims:
        raise ValueError('scene resource claims must be a nonempty tuple')
    authorized = {writer: frozenset(resources) for writer, resources in writer_resources}
    if len(authorized) != len(writer_resources):
        raise ValueError('scene resource authority contains duplicate writers')
    by_resource = {}
    for claim in claims:
        if type(claim) is not tuple or len(claim) != 4:
            raise TypeError('scene resource claim must be (writer, resource, start, end)')
        writer, resource, start, end = claim
        _token(writer, 'scene writer')
        _token(resource, 'scene resource')
        if resource not in authorized.get(writer, ()):
            raise ValueError('scene resource claim is not authorized by its binding')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= substeps:
            raise ValueError('scene resource claim requires an aligned half-open substep range')
        by_resource.setdefault(resource, []).append((start, end, writer))
    for intervals in by_resource.values():
        intervals.sort()
        if any(a[1] > b[0] for a, b in zip(intervals, intervals[1:])):
            raise ValueError('scene resource claims overlap')


@dataclass(frozen=True)
class SceneCommandContributionV1:
    """One typed command's binding and effective half-open substep range."""
    producer_kind: str
    command_kind: str
    units: tuple[str, ...]
    composition: str
    physical_effect_id: str | None
    writer_id: str | None
    controller_identity: str | None
    controller_generation: int | None
    command_sha256: str
    resources: tuple[str, ...]
    start_substep: int
    end_substep: int


@dataclass(frozen=True)
class SceneCommandIntervalV1:
    """Versioned source-bound outer interval, independent of inner hashes."""
    schema_version: str
    source_id: str
    source_closure_sha256: str
    artifact_sha256: str
    boundary: object
    sample_clock: object
    binding_sha256: str
    binding_revision: str | None
    materialization_receipt_sha256: str | None
    row: int | None
    physics_dt_s: float
    substeps: int
    contributions: tuple[SceneCommandContributionV1, ...]

    @property
    def identity_hash(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _validate_scene_contributions(interval):
    """Admit all outer claims together before consuming the one replay key."""
    if type(interval) is not SceneCommandIntervalV1 or interval.schema_version != 'scene-command-interval-v1':
        raise TypeError('scene submission requires a versioned SceneCommandIntervalV1')
    if (type(interval.substeps) is not int or interval.substeps <= 0
            or not math.isfinite(interval.physics_dt_s) or interval.physics_dt_s <= 0
            or type(interval.contributions) is not tuple or not interval.contributions):
        raise ValueError('scene interval requires a finite timebase and typed contributions')
    claims = {}
    effects = {}
    for item in interval.contributions:
        if type(item) is not SceneCommandContributionV1:
            raise TypeError('scene interval contains an untyped contribution')
        _token(item.producer_kind, 'scene producer')
        _token(item.command_kind, 'scene command kind')
        _digest(item.command_sha256, 'scene contribution command')
        if (item.composition not in {'exclusive', 'sum', 'controller-managed'}
                or type(item.units) is not tuple or not item.units
                or type(item.resources) is not tuple or not item.resources
                or len(item.resources) != len(set(item.resources))
                or type(item.start_substep) is not int or type(item.end_substep) is not int
                or not 0 <= item.start_substep < item.end_substep <= interval.substeps):
            raise ValueError('scene contribution has invalid composition, units, resources or substeps')
        for unit in item.units:
            _token(unit, 'scene unit')
        if item.physical_effect_id is not None:
            _token(item.physical_effect_id, 'scene physical effect')
        if item.composition == 'sum' and item.physical_effect_id is None:
            raise ValueError('summed scene contributions require physical effect identities')
        if item.physical_effect_id is not None:
            for prior in effects.setdefault(item.physical_effect_id, []):
                if (item.start_substep < prior.end_substep and prior.start_substep < item.end_substep
                        and item.command_kind != prior.command_kind):
                    raise ValueError('scene interval repeats a physical effect across command kinds')
            effects[item.physical_effect_id].append(item)
        for resource in item.resources:
            _token(resource, 'scene resource')
            for prior in claims.setdefault(resource, []):
                if item.start_substep < prior.end_substep and prior.start_substep < item.end_substep:
                    if item.composition != 'sum' or prior.composition != 'sum':
                        raise ValueError('scene resource has overlapping exclusive contributions')
                    if (item.command_kind, item.units) != (prior.command_kind, prior.units):
                        raise ValueError('summed scene contributions require matching command kinds and units')
                    if item.physical_effect_id == prior.physical_effect_id:
                        raise ValueError('scene resource repeats the same physical effect')
            claims[resource].append(item)


def prepare_position_scene_interval(*, session, plan, command, source_id,
                                    source_closure_sha256, artifact_sha256,
                                    boundary, sample_clock, resource_owners):
    """Bind existing Position targets to the session's active source-bound plan."""
    from ...controllers.canonical.contracts import PositionControlTargetV1
    from .control import ControlBindingPlanV1
    if type(plan) is not ControlBindingPlanV1 or not plan._compiled:
        raise TypeError('scene Position interval requires a compiled binding plan')
    targets = command.targets if type(command) is PositionControlBatchV1 else (command,)
    if not targets or any(type(item) is not PositionControlTargetV1 for item in targets):
        raise TypeError('scene Position interval requires typed Position targets')
    timebase = getattr(getattr(session, '_artifact', None), 'timebase', None)
    if timebase is None:
        raise ValueError('scene Position interval requires the bound artifact timebase')
    count, dt, control_dt = timebase.control_substeps, float(timebase.physics_dt), float(timebase.control_dt)
    if (type(count) is not int or count <= 0 or not math.isfinite(dt) or dt <= 0
            or not math.isfinite(control_dt)
            or not math.isclose(dt * count, control_dt, rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError('scene Position interval differs from the artifact timebase')
    if (plan.scene_identity_hash != boundary.scene_identity_hash
            or (plan.artifact_identity_hash is not None and plan.artifact_identity_hash != artifact_sha256)
            or (plan.source_closure_digest is not None and plan.source_closure_digest != source_closure_sha256)):
        raise ValueError('scene Position interval differs from the source-bound plan')
    owners = dict(resource_owners)
    profiles = getattr(session, '_position_profiles_by_writer', None)
    contributions = []
    for target in targets:
        target.validate()
        if (target.binding_identity_hash != plan.identity_hash
                or target.source_boundary != boundary or target.sample_clock != sample_clock
                or target.source_closure_digest != source_closure_sha256
                or target.target.task_artifact_hash != artifact_sha256):
            raise ValueError('scene Position contribution differs from the bound target')
        profile = profiles.get(target.writer_id) if isinstance(profiles, dict) else None
        if isinstance(profiles, dict):
            if profile is None or profile.identity != target.controller_identity:
                raise ValueError('scene Position Controller is not the admitted writer')
        elif (getattr(session, '_position_writer_id', None) != target.writer_id
              or getattr(session, '_position_profile_identity', None) != target.controller_identity):
            raise ValueError('scene Position Controller is not the admitted writer')
        generation = getattr(profile, 'generation', None) if profile is not None else None
        if generation is not None and (type(generation) is not int or generation < 0):
            raise ValueError('scene Position Controller generation must be nonnegative')
        admitted_generations = getattr(session, '_position_profile_generations', None)
        if admitted_generations is not None and (
                target.writer_id not in admitted_generations
                or admitted_generations[target.writer_id] != generation):
            raise ValueError('scene Position Controller generation differs from materialization')
        resources = owners.get(target.writer_id)
        if not resources:
            raise ValueError('scene Position writer has no bound resources')
        contributions.append(SceneCommandContributionV1('robot-controller', 'position-target',
            ('rad', 'm'), 'exclusive', None, target.writer_id, target.controller_identity,
            generation, target.identity_hash, resources, 0, count))
    authority = tuple((writer, tuple(sorted(f'{entity}/{actuator}'
        for entity, actuator, owner in plan.resource_writers if owner == writer)))
        for writer in sorted(owners))
    claims = tuple((item.writer_id, resource, item.start_substep, item.end_substep)
                   for item in contributions for resource in item.resources)
    _validate_resource_intervals(claims, writer_resources=authority, substeps=count)
    return SceneCommandIntervalV1('scene-command-interval-v1', source_id,
        source_closure_sha256, artifact_sha256, boundary, sample_clock, plan.identity_hash,
        None, None, None, dt, count, tuple(contributions))


def prepare_physical_scene_interval(*, session, execution, resolved):
    """Bind a preflighted physical batch to its live execution and typed effects."""
    from .physical_control import PhysicalControlExecutionV1, ResolvedPhysicalBatchV1
    if type(execution) is not PhysicalControlExecutionV1 or type(resolved) is not ResolvedPhysicalBatchV1:
        raise TypeError('scene physical interval requires its typed execution and resolved batch')
    port = getattr(session, '_physical_port', None)
    if port is None or getattr(port, 'execution', None) is not execution:
        raise ValueError('scene physical execution is not the materialized session binding')
    binding = execution.compiled.binding
    batch, context = resolved.input_batch, resolved.input_batch.context
    batch.validate()
    context.validate()
    if (resolved.binding_sha256 != binding.identity_hash
            or resolved.accepted_receipt.context != context
            or resolved.accepted_receipt.batch_sha256 != batch.identity_hash
            or resolved.accepted_receipt.stage != 'accepted'
            or (context.source_id, context.source_closure_sha256, context.artifact_sha256)
            != (binding.source_id, binding.source_closure_sha256, binding.artifact_sha256)
            or context.boundary.scene_identity_hash != binding.scene_sha256
            or type(context.row) is not int or context.row < 0
            or context.generation != execution.generation
            or len(resolved.mapping_provenance) != int(bool(resolved.joints)) + int(bool(resolved.body_wrenches))
            or any(value != 'native_build' for value in resolved.mapping_provenance)
            or getattr(session, 'physical_control_generation', None) != execution.generation):
        raise ValueError('scene physical interval differs from the bound batch or execution')
    timebase = getattr(getattr(session, '_artifact', None), 'timebase', None)
    if timebase is None:
        raise ValueError('scene physical interval requires the bound artifact timebase')
    count, dt, control_dt = timebase.control_substeps, float(timebase.physics_dt), float(timebase.control_dt)
    if (type(count) is not int or count <= 0 or not math.isfinite(dt) or dt <= 0
            or not math.isfinite(control_dt)
            or not math.isclose(dt * count, control_dt, rel_tol=1e-12, abs_tol=1e-12)
            or not math.isclose(context.duration_s, control_dt, rel_tol=1e-12, abs_tol=1e-12)
            or not math.isclose(context.cadence_s, control_dt, rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError('scene physical interval differs from the artifact timebase')
    if batch.extensions:
        raise ValueError('scene physical interval does not yet admit load extensions')
    controllers = {item.writer_id: item for item in execution.controllers}
    versions = execution.controller_versions()
    if getattr(session, '_physical_controller_versions', None) != versions:
        raise ValueError('scene physical Controller versions differ from materialization')
    generations = {writer: generation for writer, _identity, generation in versions}
    channels = {item.target_key: item for item in binding.channels}
    bodies = {(item.entity_id, item.body_id): item for item in binding.bodies}
    contributions, groups = [], {}
    for kind, items in (('joint-effort', batch.joint_efforts), ('body-wrench', batch.body_wrenches)):
        for item in items:
            writer = item.contribution.owner_id
            controller = controllers.get(writer)
            if controller is None:
                raise ValueError('scene physical writer is not an admitted Controller')
            if kind == 'joint-effort':
                bound = channels.get(item.target_key)
                resource = f'joint:{item.entity_id}/{item.joint_id}/{item.dof_id}'
                units = (item.unit,)
                basis = (item.unit, item.axis, item.axis_frame, item.sign, item.limit,
                         item.contribution.limit_order)
            else:
                bound = bodies.get((item.entity_id, item.body_id))
                resource = f'body:{item.entity_id}/{item.body_id}'
                units = ('N', 'N*m')
                # Existing physical preflight resolves each wrench into the
                # common world/body-origin basis before explicit summation.
                basis = ('world', 'body-origin')
            if bound is None or writer not in bound.owner_ids:
                raise ValueError('scene physical resource is not owned by its writer')
            item.validate()
            item.contribution.validate()
            if kind == 'joint-effort' and (
                    (item.joint_kind, item.axis, item.axis_frame, item.sign, item.unit, item.limit)
                    != (bound.kind, bound.axis, bound.axis_frame, bound.sign, bound.unit, bound.effort_range)
                    or (item.controller_law == 'explicit_full_pd'
                        and bound.native_drive not in {'disabled', 'passive'})):
                raise ValueError('scene physical joint differs from its bound channel')
            groups.setdefault(resource, []).append((item, basis))
            contributions.append(SceneCommandContributionV1('robot-controller', kind, units,
                item.contribution.composition, item.contribution.physical_effect_id,
                writer, controller.identity, generations[writer], item.identity_hash,
                (resource,), 0, count))
    for resource, members in groups.items():
        if len(members) > 1:
            if any(item.contribution.composition != 'sum' for item, _ in members):
                raise ValueError('scene physical resource has overlapping exclusive effects')
            if len({basis for _, basis in members}) != 1:
                raise ValueError('scene physical sums require the same basis and units')
            effects = [item.contribution.physical_effect_id for item, _ in members]
            if len(effects) != len(set(effects)):
                raise ValueError('scene physical resource contains a duplicate effect')
    return SceneCommandIntervalV1('scene-command-interval-v1', context.source_id,
        context.source_closure_sha256, context.artifact_sha256, context.boundary, context.clock,
        binding.identity_hash, None, None, context.row, dt, count, tuple(contributions))


def prepare_subject_position_scene_interval(*, session, target, source_id,
        source_closure_sha256, artifact_sha256, boundary, sample_clock,
        resource_owners, execution_mode):
    """Bind a legacy target through its admitted, source-owned subject plan."""
    from ...assembly.source_composition import PositionSubjectControlBindingV1
    from ...controllers.canonical.contracts import CanonicalControlTarget
    if type(target) is not CanonicalControlTarget:
        raise TypeError('scene subject interval requires a canonical Position target')
    if execution_mode not in {'boundary-hold', 'native-feedback'}:
        raise ValueError('scene subject interval requires an explicit execution mode')
    source = getattr(session, '_source', None)
    binding = getattr(source, 'position_subject_binding', None)
    if type(binding) is not PositionSubjectControlBindingV1:
        raise ValueError('scene subject interval requires its source-bound subject binding')
    plan = binding.plan
    boundary_scene = getattr(boundary, 'scene_identity_hash', None)
    if boundary_scene is None:
        # Legacy state publications have no canonical Scene identity. Bind the
        # real legacy artifact and closure instead of inventing a Scene field.
        if (getattr(boundary, 'artifact_identity_hash', None) != artifact_sha256
                or getattr(boundary, 'source_closure_digest', None) != source_closure_sha256):
            raise ValueError('legacy boundary differs from the bound artifact or closure')
    elif plan.scene_identity_hash != boundary_scene:
        raise ValueError('scene subject plan differs from the boundary Scene')
    if (not plan._compiled
            or plan.artifact_identity_hash != artifact_sha256
            or plan.source_closure_digest != source_closure_sha256
            or target.task_artifact_hash != artifact_sha256):
        raise ValueError('scene subject interval differs from its bound Controller or source')
    split_bundle = None
    if len(plan.controller_bindings) == 1:
        if plan.controller_bindings[0].controller_identity != target.controller_identity:
            raise ValueError('scene subject interval differs from its bound Controller')
    else:
        from ...controllers.canonical.split_panda_position import SplitPositionBundleV1
        split_bundle = getattr(session, '_subject_position_split_bundle', None)
        if type(split_bundle) is not SplitPositionBundleV1:
            raise ValueError('scene subject interval lacks its component outputs')
        split_bundle.validate_target(target, plan)
    expected = tuple(sorted((writer, tuple(sorted(f'{entity}/{actuator}'
        for entity, actuator, owner in plan.resource_writers if owner == writer)))
        for writer in {writer for _, _, writer in plan.resource_writers}))
    if tuple(sorted(resource_owners)) != expected:
        raise ValueError('scene subject resources differ from the bound writer')
    expected_boundary = (boundary.provider_materialization_id, boundary.episode_id,
                         boundary.state_revision, boundary.control_step)
    if getattr(session, '_subject_position_inflight', None) != (
            expected_boundary, target.identity_hash, target.controller_identity):
        raise ValueError('scene subject target is not authorized for this live boundary')
    composition = getattr(source, 'composition_runtime_input', None)
    if composition is not None and (
            plan.identity_hash != composition.plan.control_binding_identity_sha256
            or binding.subject_identity_sha256 != composition.plan.subject_binding_identity_sha256):
        raise ValueError('scene subject binding differs from its source composition')
    timebase = getattr(getattr(session, '_artifact', None), 'timebase', None)
    if timebase is None:
        raise ValueError('scene subject interval requires the bound artifact timebase')
    count, dt, control_dt = timebase.control_substeps, float(timebase.physics_dt), float(timebase.control_dt)
    if (type(count) is not int or count <= 0 or not math.isfinite(dt) or dt <= 0
            or not math.isfinite(control_dt)
            or not math.isclose(dt * count, control_dt, rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError('scene subject interval differs from the artifact timebase')
    _validate_resource_intervals(tuple((writer, resource, 0, count)
                                      for writer, resources in expected for resource in resources),
                                 writer_resources=expected, substeps=count)
    # The old canonical target does not carry source boundary, row or
    # generation. Its verified in-flight subject binding supplies the link;
    # it does not create values for those missing fields. Native feedback mode
    # represents a Controller-managed interval, not a held actuator setpoint.
    if split_bundle is None:
        writer, resources = expected[0]
        contributions = (SceneCommandContributionV1('robot-controller',
            'position-reference-native-feedback' if execution_mode == 'native-feedback' else 'position-target',
            ('rad', 'm'), 'controller-managed' if execution_mode == 'native-feedback' else 'exclusive',
            None, writer, target.controller_identity, None, target.identity_hash, resources, 0, count),)
    else:
        from ...controllers.canonical.split_panda_position import ARM_WRITER, HAND_WRITER
        if execution_mode != 'boundary-hold':
            raise ValueError('split Position owners require boundary-held output')
        owners = dict(expected)
        contributions = (
            SceneCommandContributionV1('robot-controller', 'arm-position-target', ('rad',),
                'exclusive', None, ARM_WRITER, split_bundle.arm_identity, None, split_bundle.arm_hash,
                owners[ARM_WRITER], 0, count),
            SceneCommandContributionV1('robot-controller', 'hand-position-target', ('m',),
                'exclusive', None, HAND_WRITER, split_bundle.hand_identity, None, split_bundle.hand_hash,
                owners[HAND_WRITER], 0, count),
        )
    return SceneCommandIntervalV1('scene-command-interval-v1', source_id,
        source_closure_sha256, artifact_sha256, boundary, sample_clock, binding.identity_hash,
        None, None, None, dt, count, contributions)


def prepare_leaf_scene_interval(*, plan, materialization, batch, source_id,
                                artifact_sha256, boundary, sample_clock):
    """Bind selected leaf contributions to the already admitted plan and receipt.

    Leaf V1 has neither a row number nor Controller generation. Keep those as
    None and bind the actual plan, leaf binding, and configuration revision;
    do not invent identities that the old commands do not carry.
    """
    from ...controllers.canonical.leaf_plan import EffectiveLeafPlanV1
    from .leaf_control import LeafMaterializationReceiptV1, LeafPreparedBatchV1
    if type(plan) is not EffectiveLeafPlanV1 or not plan._compiled:
        raise TypeError('scene leaf interval requires its compiled binding plan')
    if type(materialization) is not LeafMaterializationReceiptV1 or type(batch) is not LeafPreparedBatchV1:
        raise TypeError('scene leaf interval requires typed materialization and batch')
    batch.validate()
    _token(source_id, 'scene source')
    _digest(artifact_sha256, 'scene artifact')
    if (boundary.scene_identity_hash != plan.scene_identity_sha256
            or boundary.provider_materialization_id != materialization.materialization_id
            or sample_clock.sample_index != boundary.control_step
            or sample_clock.clock_domain != 'evaluation_boundary'
            or materialization.scene_identity_sha256 != plan.scene_identity_sha256
            or materialization.source_closure_sha256 != plan.source_closure_sha256
            or materialization.effective_plan_identity_sha256 != plan.identity_sha256):
        raise ValueError('scene leaf interval differs from its source-bound materialization')
    entries = {item.binding.writer_id: item for item in plan.leaves}
    authority = tuple((writer, tuple(sorted(f'{entity}/{actuator}'
        for entity, actuator, owner in plan.resource_writers if owner == writer)))
        for writer in sorted(entries))
    contributions = []
    for item in batch.commands:
        entry = entries.get(item.writer_id)
        if (entry is None or item.state_boundary != boundary
                or item.binding_identity_sha256 != entry.binding.identity_hash
                or item.effective_configuration_identity_sha256 != entry.effective_configuration_identity_sha256
                or item.effective_plan_identity_sha256 != plan.identity_sha256
                or item.materialization_identity_sha256 != materialization.identity_sha256
                or item.state_configuration_revision != materialization.configuration_revision
                or item.target.sample_clock != sample_clock
                or item.target.source_closure_sha256 != plan.source_closure_sha256
                or item.target.scene_identity_hash != plan.scene_identity_sha256):
            raise ValueError('scene leaf contribution differs from its bound command')
        resources = tuple(sorted(f'{slot.actuator.entity_id}/{slot.actuator.actuator_id}'
                                 for slot in item.slot_values))
        if resources != dict(authority)[item.writer_id]:
            raise ValueError('scene leaf contribution does not cover its bound resources')
        units = ('rad',) if item.profile_kind == 'arm_position' else ('m',)
        contributions.append(SceneCommandContributionV1('robot-controller', 'position-target', units,
            'exclusive', None, item.writer_id,
            item.binding_identity_sha256, None, item.command_identity_sha256,
            resources, 0, plan.control_substeps))
    if {item.writer_id for item in contributions} != set(entries):
        raise ValueError('scene leaf interval does not cover its bound writers')
    claims = tuple((item.writer_id, resource, item.start_substep, item.end_substep)
                   for item in contributions for resource in item.resources)
    _validate_resource_intervals(claims, writer_resources=authority, substeps=plan.control_substeps)
    if (not math.isfinite(plan.physics_dt_s) or plan.physics_dt_s <= 0
            or not math.isfinite(sample_clock.simulation_time_s)):
        raise ValueError('scene leaf interval clock is invalid')
    return SceneCommandIntervalV1('scene-command-interval-v1', source_id,
        plan.source_closure_sha256, artifact_sha256, boundary, sample_clock,
        plan.identity_sha256, materialization.configuration_revision,
        materialization.identity_sha256, None, plan.physics_dt_s,
        plan.control_substeps, tuple(contributions))


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
    from .physical_control import ResolvedPhysicalBatchV1, ResolvedPhysicalSequenceV1
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
    elif command_kind == 'physical-effort-sequence':
        from ...controllers.canonical.physical_sequence import PhysicalActionSequenceV1
        if (type(command) is not ResolvedPhysicalSequenceV1 or type(command.slices) is not tuple
                or not command.slices or type(command.action) is not PhysicalActionSequenceV1):
            raise TypeError('effort sequence requires admitted physical batches')
        if getattr(session, '_prepared_physical_sequence', None) is not command:
            raise ValueError('physical sequence is not prepared by this live session')
        _digest(command.action_sha256, 'physical sequence action')
        cursor = 0
        for start, end, resolved in command.slices:
            if (type(start) is not int or type(end) is not int or start != cursor or end <= start
                    or type(resolved) is not ResolvedPhysicalBatchV1
                    or resolved.body_wrenches or resolved.extensions):
                raise ValueError('effort sequence requires contiguous joint-only admitted slices')
            resolved.input_batch.validate()
            cursor = end
        timebase = getattr(getattr(session, '_artifact', None), 'timebase', None)
        if timebase is None or cursor != timebase.control_substeps:
            raise ValueError('effort sequence must cover the exact session timebase')
        command.action.validate(substeps=cursor, controller_identities=controller_identities)
        if tuple((x.start_substep, x.end_substep) for x in command.action.slices) != tuple(
                (start, end) for start, end, _ in command.slices):
            raise ValueError('physical sequence differs from its action slice ranges')
    else:
        raise ValueError('unsupported typed control command kind')
    if not callable(lower):
        raise TypeError('provider lowering must be callable')
    for value, label in ((command_sha256, 'command'), (source_closure_sha256, 'source closure'),
                         (artifact_sha256, 'artifact')):
        _digest(value, label)
    if command_sha256 != (command.input_batch.identity_hash if command_kind == 'physical-effort-batch'
                          else command.identity_hash):
        raise ValueError('control command identity differs from the typed command')
    # Validate identities carried by the typed payload against the outer
    # submission before consuming the boundary or touching a provider. The
    # legacy canonical target has no boundary/source fields; those remain
    # established by the already admitted source-bound caller.
    if command_kind in {'physical-effort-batch', 'physical-effort-sequence'}:
        batches = ((command.input_batch,) if command_kind == 'physical-effort-batch'
                   else tuple(item.input_batch for _, _, item in command.slices))
        for batch in batches:
            context = batch.context
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
    if command_kind in {'physical-effort-batch', 'physical-effort-sequence'}:
        resolved_items = ((command,) if command_kind == 'physical-effort-batch'
                          else tuple(item for _, _, item in command.slices))
        contributions = tuple(item for resolved in resolved_items for item in
            (*resolved.input_batch.joint_efforts, *resolved.input_batch.body_wrenches, *resolved.input_batch.extensions))
        payload_writers = {item.contribution.owner_id for item in contributions}
        payload_resources = {
            *(f'{item.entity_id}/{item.joint_id}' for resolved in resolved_items for item in resolved.joints),
            *(f'{item.entity_id}/{item.body_id}' for resolved in resolved_items for item in resolved.body_wrenches),
            *(str(getattr(item, 'target_key', type(item).__name__)) for resolved in resolved_items for item in resolved.extensions),
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
                timebase = getattr(getattr(session, '_artifact', None), 'timebase', None)
                if timebase is not None:
                    count = timebase.control_substeps
                    dt = float(timebase.physics_dt)
                    control_dt = float(timebase.control_dt)
                    if (type(count) is not int or count <= 0 or not math.isfinite(dt)
                            or dt <= 0 or not math.isfinite(control_dt)
                            or not math.isclose(dt * count, control_dt, rel_tol=1e-12, abs_tol=1e-12)):
                        raise ValueError('scene control interval is not aligned with the physics timebase')
                    claims = tuple((writer, resource, 0, count)
                                   for writer, resources in resource_owners for resource in resources)
                    _validate_resource_intervals(claims, writer_resources=expected, substeps=count)
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
                           submission_progress=None, scene_interval=None,
                           scene_plan=None, scene_materialization=None,
                           subject_execution_mode=None):
    """Commit one previously typed command under the existing replay key."""
    payload, identity, lifecycle = _preflight_control_command(
        session, command, command_kind=command_kind, command_sha256=command_sha256,
        source_id=source_id, source_closure_sha256=source_closure_sha256,
        artifact_sha256=artifact_sha256, boundary=boundary, sample_clock=sample_clock,
        controller_generation=controller_generation, controller_identities=controller_identities,
        writer_ids=writer_ids, resource_ids=resource_ids, units=units, lowering=lowering,
        lower=lower, resource_owners=resource_owners, submission_progress=submission_progress)
    if scene_interval is not None:
        if type(scene_interval) is not SceneCommandIntervalV1:
            raise TypeError('scene submission requires SceneCommandIntervalV1')
        if getattr(session, 'active_leaf_plan_identity', None) not in (None, getattr(scene_plan, 'identity_sha256', None)):
            raise ValueError('scene interval plan is not active in the RuntimeSession')
        check_materialization = getattr(session, 'validate_leaf_materialization', None)
        if not callable(check_materialization):
            raise ValueError('scene interval requires RuntimeSession materialization validation')
        check_materialization(scene_materialization, scene_plan)
        expected = prepare_leaf_scene_interval(plan=scene_plan, materialization=scene_materialization,
            batch=command, source_id=source_id, artifact_sha256=artifact_sha256,
            boundary=boundary, sample_clock=sample_clock)
        if scene_interval != expected:
            raise ValueError('scene interval differs from its bound inner commands')
        timebase = getattr(getattr(session, '_artifact', None), 'timebase', None)
        if timebase is not None and (timebase.control_substeps != scene_interval.substeps
                or not math.isclose(timebase.physics_dt, scene_interval.physics_dt_s, rel_tol=0, abs_tol=1e-12)
                or not math.isclose(timebase.control_dt, scene_interval.physics_dt_s * scene_interval.substeps,
                                    rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError('scene interval differs from the RuntimeSession timebase')
    elif scene_plan is not None or scene_materialization is not None:
        raise ValueError('scene binding and materialization require an interval')
    else:
        # Existing source-bound Position calls enter the same scene envelope
        # after the established preflight. Legacy canonical targets lack this
        # binding and remain on their existing route until explicitly bound.
        from ...controllers.canonical.contracts import CanonicalControlTarget, PositionControlTargetV1
        typed_position = (type(command) is PositionControlTargetV1
                          or type(command) is PositionControlBatchV1)
        plan = getattr(session, '_control_binding_plan', None)
        timebase = getattr(getattr(session, '_artifact', None), 'timebase', None)
        if typed_position and plan is not None and timebase is not None:
            scene_interval = prepare_position_scene_interval(session=session, plan=plan, command=command,
                source_id=source_id, source_closure_sha256=source_closure_sha256,
                artifact_sha256=artifact_sha256, boundary=boundary, sample_clock=sample_clock,
                resource_owners=payload['resource_owners'])
        elif command_kind == 'physical-effort-batch' and getattr(session, '_physical_port', None) is not None:
            scene_interval = prepare_physical_scene_interval(session=session,
                execution=session._physical_port.execution, resolved=command)
        elif command_kind == 'physical-effort-sequence' and getattr(session, '_physical_port', None) is not None:
            parts = tuple((start, end, prepare_physical_scene_interval(session=session,
                execution=session._physical_port.execution, resolved=resolved))
                for start, end, resolved in command.slices)
            base = parts[0][2]
            if any(replace(part, contributions=()) != replace(base, contributions=())
                   for _, _, part in parts[1:]):
                raise ValueError('physical sequence slices do not share one scene interval')
            scene_interval = replace(base, contributions=tuple(
                replace(item, start_substep=start, end_substep=end)
                for start, end, part in parts for item in part.contributions))
        elif (command_kind == 'position-target' and type(command) is CanonicalControlTarget
              and getattr(getattr(session, '_source', None), 'position_subject_binding', None) is not None):
            scene_interval = prepare_subject_position_scene_interval(session=session, target=command,
                source_id=source_id, source_closure_sha256=source_closure_sha256,
                artifact_sha256=artifact_sha256, boundary=boundary, sample_clock=sample_clock,
                resource_owners=payload['resource_owners'], execution_mode=subject_execution_mode)
    if scene_interval is None and (lifecycle is not None or command_kind == 'physical-effort-sequence'):
        # A selected lifecycle is a production dispatch, not the historical
        # standalone submission interface.  Do not consume its replay key or
        # invoke a provider unless the real source binding supplied an interval.
        raise ValueError('selected control submission requires a live source-bound scene interval')
    external = getattr(session, '_external_com_port', None)
    if external is not None:
        if scene_interval is None:
            raise ValueError('caller COM wrench requires a source-bound scene interval')
        external.verify(scene_interval)
        existing_resources = {resource for item in scene_interval.contributions for resource in item.resources}
        existing_effects = {item.physical_effect_id for item in scene_interval.contributions
                            if item.physical_effect_id is not None}
        from .mujoco_external_wrench import com_wrench_range
        added = []
        for request, _body_id in external.rows:
            resource = f'body:{request.source_body_key}'
            if resource in existing_resources or request.physical_effect_id in existing_effects:
                raise ValueError('caller COM wrench conflicts with another scene contribution')
            start, end = com_wrench_range(request, scene_interval.substeps)
            added.append(SceneCommandContributionV1('caller', 'body-com-wrench', ('N', 'N*m'),
                'exclusive', request.physical_effect_id, getattr(request, 'writer_id', None), None, None,
                request.identity_hash, (resource,), start, end))
        scene_interval = replace(scene_interval, contributions=(*scene_interval.contributions, *added))
    if scene_interval is not None:
        _validate_scene_contributions(scene_interval)
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
    if external is not None:
        external.authorized = True
    session._last_control_submission = {**payload, 'submission_id': identity, 'status': 'pending'}
    session._last_scene_control_submission = (None if scene_interval is None else {
        'schema_version': 'scene-control-submission-receipt-v1',
        'interval_sha256': scene_interval.identity_hash,
        'interval': asdict(scene_interval),
        'inner_submission_id': identity,
        'inner_command_sha256': command_sha256,
        'contribution_command_sha256': tuple(item.command_sha256
            for item in scene_interval.contributions),
        'status': 'pending',
    })
    if scene_interval is not None and command_kind == 'physical-effort-sequence':
        session._last_scene_control_submission['inner_batch_sha256'] = tuple(
            item.input_batch.identity_hash for _, _, item in command.slices)
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
        if scene_interval is not None:
            session._last_scene_control_submission = {
                'schema_version': 'scene-control-submission-receipt-v1',
                'interval_sha256': scene_interval.identity_hash,
                'interval': asdict(scene_interval),
                'inner_submission_id': receipt.submission_id,
                'inner_command_sha256': command_sha256,
                'contribution_command_sha256': tuple(item.command_sha256
                    for item in scene_interval.contributions),
                **({'inner_batch_sha256': tuple(item.input_batch.identity_hash for _, _, item in command.slices)}
                   if command_kind == 'physical-effort-sequence' else {}),
                'status': 'acknowledged',
            }
        if lifecycle is not None:
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
        if scene_interval is not None:
            session._last_scene_control_submission = {
                'schema_version': 'scene-control-submission-receipt-v1',
                'interval_sha256': scene_interval.identity_hash,
                'interval': asdict(scene_interval),
                'inner_submission_id': identity,
                'inner_command_sha256': command_sha256,
                'contribution_command_sha256': tuple(item.command_sha256
                    for item in scene_interval.contributions),
                **({'inner_batch_sha256': tuple(item.input_batch.identity_hash for _, _, item in command.slices)}
                   if command_kind == 'physical-effort-sequence' else {}),
                'status': status,
            }
        if lifecycle is not None:
            session._control_lifecycle_dispatch = replace(lifecycle, stage='failed')
        raise
    finally:
        if (command_kind == 'physical-effort-sequence'
                and getattr(session, '_prepared_physical_sequence', None) is command):
            session._prepared_physical_sequence = None
