"""Source- and boundary-bound physical control values.

These values do not assert native support.  Admission and the single session
submission authority remain in the runtime owner.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from ...artifacts.contracts import Contract, FrameReference, _SHA256, _choice, _name
from ...artifacts.state import StateBoundaryIdentity, StateSampleClock
from .contracts import digest


def _sha(value, label):
    if not _SHA256.fullmatch(value):
        raise ValueError(f'{label} must be lowercase SHA-256')


def _vector(value, label):
    if len(value) != 3 or not all(math.isfinite(x) for x in value):
        raise ValueError(f'{label} requires three finite values')


@dataclass(frozen=True)
class PhysicalCommandContextV1(Contract):
    """Identity of an interval in one episode and one environment row."""
    schema_version: str
    source_id: str
    source_closure_sha256: str
    artifact_sha256: str
    boundary: StateBoundaryIdentity
    clock: StateSampleClock
    row: int
    generation: int
    duration_s: float
    cadence_s: float

    def validate(self):
        _choice(self.schema_version, {'physical-command-context-v1'}, 'context schema')
        _name(self.source_id)
        _sha(self.source_closure_sha256, 'source closure')
        _sha(self.artifact_sha256, 'artifact')
        if self.row < 0 or self.generation < 0 or self.duration_s <= 0 or self.cadence_s <= 0:
            raise ValueError('row/generation must be nonnegative and duration/cadence positive')
        if self.clock.clock_domain != 'evaluation_boundary':
            raise ValueError('physical command requires evaluation boundary clock')
        if self.clock.sample_index != self.boundary.control_step:
            raise ValueError('clock and boundary control step differ')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class ContributionPolicyV1(Contract):
    schema_version: str
    contribution_id: str
    physical_effect_id: str
    owner_id: str
    composition: str
    limit_order: str
    persistence: str

    def validate(self):
        _choice(self.schema_version, {'physical-contribution-policy-v1'}, 'contribution policy schema')
        for value in (self.contribution_id, self.physical_effect_id, self.owner_id):
            _name(value)
        _choice(self.composition, {'exclusive', 'sum'}, 'composition')
        _choice(self.limit_order, {'reject_outside', 'clip_before_sum', 'clip_after_sum'}, 'limit order')
        _choice(self.persistence, {'one_interval', 'hold_reapply'}, 'persistence')


@dataclass(frozen=True)
class JointEffortV1(Contract):
    schema_version: str
    context: PhysicalCommandContextV1
    contribution: ContributionPolicyV1
    entity_id: str
    joint_id: str
    dof_id: str
    joint_kind: str
    axis: tuple[float, float, float]
    axis_frame: FrameReference
    sign: int
    unit: str
    value: float
    limit: tuple[float, float]
    controller_law: str

    def validate(self):
        _choice(self.schema_version, {'joint-effort-v1'}, 'joint effort schema')
        for value in (self.entity_id, self.joint_id, self.dof_id):
            _name(value)
        _choice(self.joint_kind, {'revolute', 'prismatic'}, 'joint kind')
        if self.unit != ('N*m' if self.joint_kind == 'revolute' else 'N'):
            raise ValueError('joint effort unit differs from joint kind')
        if self.axis_frame.entity_id != self.entity_id:
            raise ValueError('axis frame must belong to target entity')
        _vector(self.axis, 'axis')
        if not math.isclose(sum(x*x for x in self.axis), 1.0, abs_tol=1e-12, rel_tol=0):
            raise ValueError('axis must be unit length')
        if self.sign not in (-1, 1):
            raise ValueError('joint sign must be -1 or 1')
        if self.limit[0] > self.limit[1]:
            raise ValueError('effort limit is unordered')
        _choice(self.controller_law, {'direct_effort', 'explicit_full_pd', 'other_declared'}, 'controller law')

    @property
    def target_key(self):
        return self.entity_id, self.joint_id, self.dof_id

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class BodyWrenchV1(Contract):
    """Force at ``point`` and torque about ``moment_reference`` in expression frame."""
    schema_version: str
    context: PhysicalCommandContextV1
    contribution: ContributionPolicyV1
    entity_id: str
    body_id: str
    expressed_in: FrameReference
    point: tuple[float, float, float]
    point_frame: FrameReference
    moment_reference: tuple[float, float, float]
    moment_reference_frame: FrameReference
    force_N: tuple[float, float, float]
    torque_Nm: tuple[float, float, float]

    def validate(self):
        _choice(self.schema_version, {'body-wrench-v1'}, 'body wrench schema')
        _name(self.entity_id)
        _name(self.body_id)
        for value, label in ((self.point, 'point'), (self.moment_reference, 'moment reference'),
                             (self.force_N, 'force'), (self.torque_Nm, 'torque')):
            _vector(value, label)

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class ExternalComWrenchV1(Contract):
    """Caller-owned world wrench at the current COM for one control interval."""

    schema_version: str
    physical_effect_id: str
    source_body_key: str
    force_world_N: tuple[float, float, float]
    torque_com_world_Nm: tuple[float, float, float]

    def validate(self):
        _choice(self.schema_version, {'external-com-wrench-v1'}, 'external COM wrench schema')
        for value in (self.physical_effect_id, self.source_body_key):
            _name(value)
        _vector(self.force_world_N, 'world force')
        _vector(self.torque_com_world_Nm, 'world COM torque')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class ExternalComWrenchSegmentV1(Contract):
    """A precomputed caller-writer COM wrench on half-open native ticks."""

    schema_version: str
    writer_id: str
    physical_effect_id: str
    source_body_key: str
    start_substep: int
    end_substep: int
    force_world_N: tuple[float, float, float]
    torque_com_world_Nm: tuple[float, float, float]

    def validate(self):
        _choice(self.schema_version, {'external-com-wrench-segment-v1'}, 'external COM segment schema')
        for value in (self.writer_id, self.physical_effect_id, self.source_body_key):
            _name(value)
        if (type(self.start_substep) is not int or type(self.end_substep) is not int
                or not 0 <= self.start_substep < self.end_substep):
            raise ValueError('external COM segment requires a half-open substep range')
        _vector(self.force_world_N, 'world force')
        _vector(self.torque_com_world_Nm, 'world COM torque')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class ExternalComWrenchSumSegmentV1(Contract):
    """Explicitly summable caller contribution at the current world COM."""

    schema_version: str
    writer_id: str
    physical_effect_id: str
    source_body_key: str
    start_substep: int
    end_substep: int
    force_world_N: tuple[float, float, float]
    torque_com_world_Nm: tuple[float, float, float]

    def validate(self):
        _choice(self.schema_version, {'external-com-wrench-sum-segment-v1'}, 'external COM sum schema')
        for value in (self.writer_id, self.physical_effect_id, self.source_body_key):
            _name(value)
        if (type(self.start_substep) is not int or type(self.end_substep) is not int
                or not 0 <= self.start_substep < self.end_substep):
            raise ValueError('external COM sum requires a half-open substep range')
        _vector(self.force_world_N, 'world force')
        _vector(self.torque_com_world_Nm, 'world COM torque')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class TypedLoadExtensionV1(Contract):
    """Registered extension descriptor; payload is addressed, never an untyped object."""
    schema_version: str
    context: PhysicalCommandContextV1
    contribution: ContributionPolicyV1
    namespace: str
    extension_schema: str
    requiredness: str
    entity_id: str
    topology_sha256: str
    target_id: str
    shape: tuple[int, ...]
    unit: str
    frame: FrameReference
    payload_sha256: str

    def validate(self):
        _choice(self.schema_version, {'typed-load-extension-v1'}, 'load extension schema')
        for value in (self.namespace, self.extension_schema, self.entity_id, self.target_id):
            _name(value)
        _choice(self.requiredness, {'required', 'optional'}, 'requiredness')
        _sha(self.topology_sha256, 'topology')
        _sha(self.payload_sha256, 'payload')
        if not self.shape or any(x <= 0 for x in self.shape):
            raise ValueError('load shape must contain positive dimensions')
        if self.frame.entity_id != self.entity_id:
            raise ValueError('load frame must belong to target entity')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class PhysicalCommandBatchV1(Contract):
    """One complete interval, submitted as a unit rather than individual writes."""
    schema_version: str
    context: PhysicalCommandContextV1
    joint_efforts: tuple[JointEffortV1, ...]
    body_wrenches: tuple[BodyWrenchV1, ...]
    extensions: tuple[TypedLoadExtensionV1, ...]

    def validate(self):
        _choice(self.schema_version, {'physical-command-batch-v1'}, 'physical batch schema')
        items = (*self.joint_efforts, *self.body_wrenches, *self.extensions)
        if not items:
            raise ValueError('physical command batch must not be empty')
        if any(item.context != self.context for item in items):
            raise ValueError('all contributions must share the exact interval and row')
        ids = [item.contribution.contribution_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate contribution ID in interval')
        joint_effects = {x.contribution.physical_effect_id for x in self.joint_efforts}
        wrench_effects = {x.contribution.physical_effect_id for x in self.body_wrenches}
        if joint_effects & wrench_effects:
            raise ValueError('same physical effect cannot be submitted as both wrench and joint projection')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class PhysicalControlReceiptV1(Contract):
    """A distinct stage of a physical command; an ACK is not measurement."""
    schema_version: str
    context: PhysicalCommandContextV1
    batch_sha256: str
    stage: str
    contribution_ids: tuple[str, ...]
    producer_id: str
    unit: str
    reason: str | None = None

    def validate(self):
        _choice(self.schema_version, {'physical-control-receipt-v1'}, 'receipt schema')
        _sha(self.batch_sha256, 'batch identity')
        _choice(self.stage, {'submitted', 'accepted', 'native_write_ack'}, 'receipt stage')
        _name(self.producer_id)
        if not self.contribution_ids or len(set(self.contribution_ids)) != len(self.contribution_ids):
            raise ValueError('receipt requires unique contribution identities')
        for item in self.contribution_ids:
            _name(item)
        if self.reason is not None:
            raise ValueError('command receipts cannot represent measured or unavailable values')


@dataclass(frozen=True)
class PhysicalJointChannelV1(Contract):
    """One logical component's source-bound physical joint channel."""
    schema_version: str
    component_path: tuple[str, ...]
    owner_ids: tuple[str, ...]
    entity_id: str
    joint_id: str
    dof_id: str
    kind: str
    axis: tuple[float, float, float]
    axis_frame: FrameReference
    sign: int
    unit: str
    effort_range: tuple[float, float]
    native_actuator: str
    transmission_id: str
    transmission_coefficient: float
    native_range: tuple[float, float]
    native_drive: str

    def validate(self):
        _choice(self.schema_version, {'physical-joint-channel-v1'}, 'channel schema')
        if not self.component_path:
            raise ValueError('component path must not be empty')
        if not self.owner_ids or len(self.owner_ids) != len(set(self.owner_ids)):
            raise ValueError('channel owners must be nonempty and unique')
        for value in (*self.component_path, *self.owner_ids, self.entity_id, self.joint_id,
                      self.dof_id, self.native_actuator, self.transmission_id):
            _name(value)
        _choice(self.kind, {'revolute', 'prismatic'}, 'joint kind')
        if self.unit != ('N*m' if self.kind == 'revolute' else 'N'):
            raise ValueError('channel unit differs from joint kind')
        _vector(self.axis, 'axis')
        if abs(sum(x*x for x in self.axis) - 1.0) > 1e-9:
            raise ValueError('channel axis must be unit length')
        if self.axis_frame.entity_id != self.entity_id or self.sign not in (-1, 1):
            raise ValueError('channel axis frame or sign is invalid')
        if self.effort_range[0] > self.effort_range[1] or self.native_range[0] > self.native_range[1]:
            raise ValueError('channel ranges must be ordered')
        if self.transmission_coefficient == 0:
            raise ValueError('transmission coefficient must be nonzero')
        _choice(self.native_drive, {'disabled', 'passive', 'position', 'implicit_pd', 'unknown'}, 'native drive')

    @property
    def target_key(self):
        return self.entity_id, self.joint_id, self.dof_id


@dataclass(frozen=True)
class PhysicalJointBuildReceiptV1(Contract):
    """Session-supplied mapping and transmission facts for one build."""
    schema_version: str
    binding_sha256: str
    source_closure_sha256: str
    provider_materialization_id: str
    channels: tuple[PhysicalJointChannelV1, ...]
    provenance: str

    def validate(self):
        _choice(self.schema_version, {'physical-joint-build-receipt-v1'}, 'joint build receipt schema')
        _sha(self.binding_sha256, 'binding')
        _sha(self.source_closure_sha256, 'source closure')
        _name(self.provider_materialization_id)
        _choice(self.provenance, {'native_build', 'synthetic_fixture'}, 'joint mapping provenance')
        keys = [item.target_key for item in self.channels]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError('joint build receipt requires unique channel mappings')


@dataclass(frozen=True)
class PhysicalBodyBindingV1(Contract):
    """A Scene body and its source-bound reference frame."""
    schema_version: str
    entity_id: str
    body_id: str
    body_frame: FrameReference
    native_body: str
    owner_ids: tuple[str, ...]

    def validate(self):
        _choice(self.schema_version, {'physical-body-binding-v1'}, 'body binding schema')
        for value in (self.entity_id, self.body_id, self.native_body):
            _name(value)
        if not self.owner_ids or len(self.owner_ids) != len(set(self.owner_ids)):
            raise ValueError('body owners must be nonempty and unique')
        for value in self.owner_ids:
            _name(value)
        if self.body_frame.entity_id != self.entity_id:
            raise ValueError('body frame must belong to the target entity')


@dataclass(frozen=True)
class PhysicalBodyBuildReceiptV1(Contract):
    """Session-supplied build mapping; declarations alone do not prove a body."""
    schema_version: str
    binding_sha256: str
    source_closure_sha256: str
    provider_materialization_id: str
    bodies: tuple[PhysicalBodyBindingV1, ...]
    provenance: str

    def validate(self):
        _choice(self.schema_version, {'physical-body-build-receipt-v1'}, 'body build receipt schema')
        _sha(self.binding_sha256, 'binding')
        _sha(self.source_closure_sha256, 'source closure')
        _name(self.provider_materialization_id)
        _choice(self.provenance, {'native_build', 'synthetic_fixture'}, 'body mapping provenance')
        keys = [(item.entity_id, item.body_id) for item in self.bodies]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError('body build receipt requires unique body mappings')


@dataclass(frozen=True)
class PhysicalControlBindingV1(Contract):
    """Static logical and source closure, distinct from legacy V1 binding hashes."""
    schema_version: str
    scene_sha256: str
    artifact_sha256: str
    source_id: str
    source_closure_sha256: str
    logical_assembly_sha256: str
    channels: tuple[PhysicalJointChannelV1, ...]
    bodies: tuple[PhysicalBodyBindingV1, ...] = ()

    def validate(self):
        _choice(self.schema_version, {'physical-control-binding-v1'}, 'physical binding schema')
        for label, value in (('scene', self.scene_sha256), ('artifact', self.artifact_sha256),
                             ('source closure', self.source_closure_sha256),
                             ('logical assembly', self.logical_assembly_sha256)):
            _sha(value, label)
        _name(self.source_id)
        if not self.channels and not self.bodies:
            raise ValueError('physical control binding needs named channels or bodies')
        keys = [item.target_key for item in self.channels]
        if len(keys) != len(set(keys)):
            raise ValueError('physical control binding has duplicate joint channels')
        body_keys = [(x.entity_id, x.body_id) for x in self.bodies]
        if len(body_keys) != len(set(body_keys)):
            raise ValueError('physical control binding has duplicate bodies')
        by_transmission = {}
        for item in self.channels:
            by_transmission.setdefault((item.entity_id, item.transmission_id), []).append(item)
        for group in by_transmission.values():
            if len({(x.native_actuator, x.native_range) for x in group}) != 1:
                raise ValueError('one transmission must name one native actuator and range')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class PhysicalBufferPolicyV1(Contract):
    """Session-declared application strategy, not proof of native behavior."""
    schema_version: str
    binding_sha256: str
    provider_materialization_id: str
    operation: str
    cadence: str
    reset_action: str

    def validate(self):
        _choice(self.schema_version, {'physical-buffer-policy-v1'}, 'buffer policy schema')
        _sha(self.binding_sha256, 'binding')
        _name(self.provider_materialization_id)
        _choice(self.operation, {'replace', 'clear_then_add'}, 'buffer operation')
        _choice(self.cadence, {'each_native_step'}, 'buffer cadence')
        _choice(self.reset_action, {'clear_before_new_episode'}, 'buffer reset action')


@dataclass(frozen=True)
class PhysicalMeasurementV1(Contract):
    """Measurement/estimate or explicit unavailability, never a write ACK."""
    schema_version: str
    context: PhysicalCommandContextV1
    contribution_id: str
    producer_id: str
    kind: str
    value: tuple[float, ...]
    unit: str
    clock: StateSampleClock
    reason: str | None = None

    def validate(self):
        _choice(self.schema_version, {'physical-measurement-v1'}, 'measurement schema')
        _name(self.contribution_id)
        _name(self.producer_id)
        _choice(self.kind, {'measured', 'estimated', 'unavailable'}, 'measurement kind')
        if self.kind == 'unavailable':
            if self.value or not self.reason:
                raise ValueError('unavailable measurement requires reason and no value')
        elif not self.value or self.reason is not None:
            raise ValueError('measurement or estimate requires values and no unavailable reason')
        if self.clock.simulation_time_s < self.context.clock.simulation_time_s:
            raise ValueError('measurement clock precedes command interval')


def require_physical_measurement(value, *, context, contribution_id, required, expected_kind='measured'):
    """Validate measurement identity without promoting a write ACK to a sample."""
    if type(value) is not PhysicalMeasurementV1:
        raise TypeError('physical measurement requires a typed measurement value')
    if value.context != context or value.contribution_id != contribution_id:
        raise ValueError('measurement identity differs from requested contribution')
    _choice(expected_kind, {'measured', 'estimated'}, 'expected feedback kind')
    if required and value.kind == 'unavailable':
        raise ValueError(f'required physical measurement unavailable: {value.reason}')
    if value.kind != 'unavailable' and value.kind != expected_kind:
        raise ValueError('measurement and estimate are distinct feedback kinds')
    return value
