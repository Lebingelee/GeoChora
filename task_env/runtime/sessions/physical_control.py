"""Preflight and combine physical commands at the existing session boundary.

The module is provider-free. A native adapter must independently admit its
public API and source mapping before implementing the session write method.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType

from ...artifacts import SceneDefinition, resolve_logical_assembly
from ...artifacts.contracts import CapabilityAssessmentV1
from ...artifacts.logical_assembly import LogicalAssemblySubcomponentReferenceV1
from ...artifacts.state import CanonicalStateViewV1, CanonicalStateViewV2
from ...controllers.canonical.physical_commands import (
    PhysicalControlBindingV1, PhysicalCommandBatchV1, PhysicalControlReceiptV1,
    PhysicalBodyBuildReceiptV1, PhysicalJointBuildReceiptV1, PhysicalBufferPolicyV1,
)


@dataclass(frozen=True)
class CompiledPhysicalBindingV1:
    """Declarations and inputs to be revalidated before every admission."""
    binding: PhysicalControlBindingV1
    scene: SceneDefinition
    root: object
    children: object


@dataclass(frozen=True)
class PhysicalControlExecutionV1:
    """Selected task's immutable control wiring, consumed by its existing Env."""
    compiled: CompiledPhysicalBindingV1
    controllers: tuple[object, ...]
    scene: SceneDefinition
    joint_bindings: object
    frame_bindings: object
    requirements: object
    generation: int

    def __post_init__(self):
        from collections.abc import Mapping
        from ...artifacts.state import StateRequirements
        _validate_compiled_binding(self.compiled)
        if type(self.scene) is not SceneDefinition or self.scene.identity_hash != self.compiled.binding.scene_sha256:
            raise ValueError('physical execution Scene differs from compiled binding')
        if (type(self.controllers) is not tuple or not self.controllers
                or any(not callable(getattr(controller, 'compute', None))
                       or getattr(controller, 'binding', None) != self.compiled.binding
                       or not isinstance(getattr(controller, 'identity', None), str)
                       or not isinstance(getattr(controller, 'writer_id', None), str)
                       or not controller.writer_id
                       for controller in self.controllers)):
            raise ValueError('physical execution Controllers differ from binding')
        if len({controller.identity for controller in self.controllers}) != len(self.controllers):
            raise ValueError('physical execution Controller identities must be unique')
        if len({controller.writer_id for controller in self.controllers}) != len(self.controllers):
            raise ValueError('physical execution Controller writers must be unique')
        if not isinstance(self.joint_bindings, Mapping) or not isinstance(self.frame_bindings, Mapping):
            raise TypeError('physical execution state bindings must be mappings')
        if type(self.requirements) is not StateRequirements:
            raise TypeError('physical execution requires typed state requirements')
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError('physical execution generation must be nonnegative')
        object.__setattr__(self, 'joint_bindings', MappingProxyType(dict(self.joint_bindings)))
        object.__setattr__(self, 'frame_bindings', MappingProxyType(dict(self.frame_bindings)))

    def action_space(self):
        """Expose the Controller-declared input shapes on the selected route."""
        import numpy as np
        from gymnasium.spaces import Box, Dict

        spaces = {}
        for controller in self.controllers:
            shape = getattr(controller, 'action_shape', None)
            if (type(shape) is not tuple or not shape
                    or any(type(n) is not int or n < 1 for n in shape)):
                raise ValueError('physical Controller requires a positive action shape')
            spaces[controller.identity] = Box(-np.inf, np.inf, shape=shape, dtype=np.float32)
        return next(iter(spaces.values())) if len(spaces) == 1 else Dict(spaces)

    def validate_source(self, *, scene, artifact_sha256, source_id, source_closure_sha256, source=None):
        """Recheck an execution selection against the actual task source."""
        _validate_compiled_binding(self.compiled)
        binding = self.compiled.binding
        if (type(scene) is not SceneDefinition or scene.identity_hash != self.scene.identity_hash
                or binding.artifact_sha256 != artifact_sha256
                or binding.source_id != source_id
                or binding.source_closure_sha256 != source_closure_sha256):
            raise ValueError('physical execution differs from selected Scene, Artifact, or source')
        if source is not None:
            joint_names = set(source.joints) | set(source.free_joints)
            frame_names = set(source.bodies) | set(source.frames)
            if (set(source.joints) & set(source.free_joints)
                    or set(source.bodies) & set(source.frames)
                    or set(self.joint_bindings) != joint_names
                    or set(self.frame_bindings) != frame_names):
                raise ValueError('physical state bindings must exactly cover selected source names')
        self.action_space()


def _validate_physical_binding(scene, root, children, binding):
    if type(scene) is not SceneDefinition or type(binding) is not PhysicalControlBindingV1:
        raise TypeError('physical binding requires a canonical Scene and typed binding')
    resolved = resolve_logical_assembly(root, scene, children)
    if (scene.identity_hash != binding.scene_sha256
            or resolved.root_logical_content_sha256 != binding.logical_assembly_sha256):
        raise ValueError('physical binding Scene or logical Assembly identity mismatch')
    leaves = {leaf.full_path: leaf.member for leaf in resolved.leaves}
    joints = {(a.entity_id, j.joint_id): j for a in scene.articulations or () for j in a.joints}
    for channel in binding.channels:
        member = leaves.get(channel.component_path)
        if (type(member) is not LogicalAssemblySubcomponentReferenceV1
                or member.target_kind != 'joint'
                or (member.target.entity_id, member.target.joint_id)
                != (channel.entity_id, channel.joint_id)):
            raise ValueError('component path does not resolve to its declared joint')
        joint = joints.get((channel.entity_id, channel.joint_id))
        if joint is None or joint.kind != channel.kind or joint.axis is None:
            raise ValueError('physical channel joint kind or source does not match Scene')
        if channel.axis_frame != joint.parent_frame:
            raise ValueError('physical channel axis must use the declared parent frame')
        parent_axis = _rotate(joint.pose_parent_from_joint.quaternion_wxyz, joint.axis)
        if any(abs(a-b) > 1e-9 for a, b in zip(parent_axis, channel.axis, strict=True)):
            raise ValueError('physical channel axis differs from Scene')
    frames = {(frame.entity_id, frame.frame_id) for frame in scene.frames or ()}
    for body in binding.bodies:
        if (body.body_frame.entity_id, body.body_frame.frame_id) not in frames:
            raise ValueError('physical body binding references unknown Scene frame')
    return resolved


def compile_physical_control_binding(scene, root, children, binding):
    _validate_physical_binding(scene, root, children, binding)
    from collections.abc import Mapping
    if not isinstance(children, Mapping):
        raise TypeError('physical binding child catalog must be a mapping')
    return CompiledPhysicalBindingV1(binding, scene, root, MappingProxyType(dict(children)))


def _validate_compiled_binding(compiled):
    if type(compiled) is not CompiledPhysicalBindingV1:
        raise ValueError('physical binding must be compiled against Scene and Assembly')
    _validate_physical_binding(compiled.scene, compiled.root, compiled.children, compiled.binding)


@dataclass(frozen=True)
class ResolvedJointEffortV1:
    entity_id: str
    joint_id: str
    dof_id: str
    unit: str
    value: float
    contribution_ids: tuple[str, ...]
    clipped_before_sum: bool
    clipped_after_sum: bool


@dataclass(frozen=True)
class ResolvedBodyWrenchV1:
    entity_id: str
    body_id: str
    force_world_N: tuple[float, float, float]
    torque_at_body_origin_world_Nm: tuple[float, float, float]
    body_origin_world_m: tuple[float, float, float]
    contribution_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPhysicalBatchV1:
    """Admission output, before adapter mapping and native write."""
    input_batch: PhysicalCommandBatchV1
    binding_sha256: str
    joints: tuple[ResolvedJointEffortV1, ...]
    body_wrenches: tuple
    extensions: tuple
    accepted_receipt: PhysicalControlReceiptV1
    mapping_provenance: tuple[str, ...]


def _clamp(value, bounds):
    return min(max(value, bounds[0]), bounds[1])


def _add(a, b):
    return tuple(x+y for x, y in zip(a, b, strict=True))


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b, strict=True))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _rotate(quat, vector):
    w, x, y, z = quat
    u = (x, y, z)
    uv = _cross(u, vector)
    uuv = _cross(u, uv)
    return tuple(v + 2*(w*a+b) for v, a, b in zip(vector, uv, uuv, strict=True))


def resolve_body_wrench_at_poses(item, body_frame, poses):
    """Resolve the declared total moment about its reference at current poses.

    The application point does not add a second moment to a torque already
    declared about another reference. It remains explicit for the equivalent
    point-wrench transformation and for validating the requested frame.
    """
    origin = poses[body_frame].position
    expression, point_frame = poses[item.expressed_in], poses[item.point_frame]
    reference_frame = poses[item.moment_reference_frame]
    force = _rotate(expression.quaternion_wxyz, item.force_N)
    torque_reference = _rotate(expression.quaternion_wxyz, item.torque_Nm)
    point = _add(point_frame.position, _rotate(point_frame.quaternion_wxyz, item.point))
    reference = _add(reference_frame.position,
                     _rotate(reference_frame.quaternion_wxyz, item.moment_reference))
    torque_point = _add(torque_reference, _cross(_sub(reference, point), force))
    torque_origin = _add(torque_point, _cross(_sub(point, origin), force))
    return origin, force, torque_origin


def prepare_physical_command_batch(compiled, batch, *, expected_context,
                                   assessment, registered_extensions=(),
                                   topology_sha256=None, state=None, body_build_receipt=None,
                                   joint_build_receipt=None, buffer_policy=None):
    """Admit the entire batch before any controller/session/provider write.

    Wrenches are transformed into world coordinates about the bound body
    origin using an exact-boundary immutable state publication.
    """
    _validate_compiled_binding(compiled)
    if type(batch) is not PhysicalCommandBatchV1:
        raise TypeError('physical command requires a typed batch')
    batch.validate()
    binding = compiled.binding
    context = batch.context
    if context != expected_context:
        raise ValueError('stale or foreign physical command context')
    if (context.boundary.scene_identity_hash != binding.scene_sha256
            or context.artifact_sha256 != binding.artifact_sha256
            or context.source_id != binding.source_id
            or context.source_closure_sha256 != binding.source_closure_sha256):
        raise ValueError('physical command differs from source-bound plan')
    if type(assessment) is not CapabilityAssessmentV1 or assessment.request_identity != binding.identity_hash:
        raise ValueError('physical command requires a binding-specific capability assessment')
    # Synthetic mappings can exercise pure admission, but cannot substantiate a
    # native-build/runtime capability declaration. Preserve that distinction in
    # the result instead of silently promoting a fixture into build evidence.
    receipts = tuple(x for x in (joint_build_receipt, body_build_receipt) if x is not None)
    if assessment.phase in {'native_build', 'runtime'} and any(
            getattr(x, 'provenance', None) != 'native_build' for x in receipts):
        raise ValueError('synthetic mapping cannot support native build or runtime assessment')
    capability_names = set()
    if batch.joint_efforts:
        capability_names.update(('joint_effort', 'transmission', 'native_drive_state'))
        if (type(joint_build_receipt) is not PhysicalJointBuildReceiptV1
                or joint_build_receipt.binding_sha256 != binding.identity_hash
                or joint_build_receipt.source_closure_sha256 != binding.source_closure_sha256
                or joint_build_receipt.provider_materialization_id != context.boundary.provider_materialization_id
                or set(joint_build_receipt.channels) != set(binding.channels)):
            raise ValueError('joint effort requires an exact session build mapping receipt')
    if batch.body_wrenches:
        capability_names.update(('body_force', 'body_torque', 'body_frame', 'body_offset_point'))
    if any(x.contribution.composition == 'sum' for x in (*batch.joint_efforts, *batch.body_wrenches)):
        capability_names.add('sum')
    if any(x.contribution.persistence == 'hold_reapply' for x in (*batch.joint_efforts, *batch.body_wrenches)):
        capability_names.add('hold_reapply')
        if (type(buffer_policy) is not PhysicalBufferPolicyV1
                or buffer_policy.binding_sha256 != binding.identity_hash
                or buffer_policy.provider_materialization_id != context.boundary.provider_materialization_id):
            raise ValueError('held load requires a source-bound clear/add or replace policy')
    capability_names.update(f'load_extension:{x.namespace}/{x.extension_schema}' for x in batch.extensions)
    rows = {r.capability_id: r for r in assessment.rows
            if r.requiredness == 'required' and r.object_ref == f'binding:{binding.identity_hash}'}
    if not capability_names <= rows.keys():
        raise ValueError('physical command capability assessment is incomplete')
    for name in capability_names:
        row = rows[name]
        if (row.provider_api != 'supported' or row.core_adapter != 'implemented'
                or row.dependency != 'available' or row.requirement_status != 'satisfied'
                or row.caller_restriction != 'none'):
            raise ValueError(f'physical command capability not admitted: {name}')
    for extension in batch.extensions:
        if extension.topology_sha256 != topology_sha256:
            raise ValueError('typed load extension topology is stale')
        if (extension.namespace, extension.extension_schema) not in registered_extensions:
            if extension.requiredness == 'required':
                raise ValueError('unknown required typed load extension')
            raise ValueError('optional extension is unavailable; it cannot be silently submitted')
    channels = {x.target_key: x for x in binding.channels}
    grouped = {}
    for item in batch.joint_efforts:
        channel = channels.get(item.target_key)
        if channel is None:
            raise ValueError('joint effort target is not source-bound')
        if (item.contribution.owner_id not in channel.owner_ids or
            (item.joint_kind, item.axis, item.axis_frame,
             item.sign, item.unit, item.limit)
                != (channel.kind, channel.axis, channel.axis_frame,
                    channel.sign, channel.unit, channel.effort_range)):
            raise ValueError('joint effort differs from its source-bound channel')
        if item.controller_law == 'explicit_full_pd' and channel.native_drive not in {'disabled', 'passive'}:
            raise ValueError('explicit PD overlaps an uncoordinated native drive')
        grouped.setdefault(item.target_key, []).append(item)
    results = []
    for key, items in sorted(grouped.items()):
        if len(items) > 1 and any(x.contribution.composition != 'sum' for x in items):
            raise ValueError('overlapping joint effort requires declared sum')
        orders = {x.contribution.limit_order for x in items}
        if len(orders) != 1:
            raise ValueError('summed joint contributions require the same limit order')
        order = next(iter(orders))
        bounds = channels[key].effort_range
        values = [x.value for x in items]
        if order == 'reject_outside' and any(not bounds[0] <= x <= bounds[1] for x in values):
            raise ValueError('joint effort exceeds pre-combination limit')
        pre = [_clamp(x, bounds) for x in values] if order == 'clip_before_sum' else values
        total = sum(pre)
        if order != 'clip_after_sum' and not bounds[0] <= total <= bounds[1]:
            raise ValueError('combined effort exceeds limit')
        final = _clamp(total, bounds) if order == 'clip_after_sum' else total
        results.append(ResolvedJointEffortV1(*key, channels[key].unit, final,
            tuple(x.contribution.contribution_id for x in items), pre != values, final != total))
    # A transmission is a scalar source-bound map, not an arbitrary independent
    # force vector. Every declared channel of a touched transmission is needed.
    result_map = {(x.entity_id, x.joint_id, x.dof_id): x for x in results}
    transmissions = {}
    for channel in binding.channels:
        transmissions.setdefault((channel.entity_id, channel.transmission_id), []).append(channel)
    for group in transmissions.values():
        touched = [x for x in group if x.target_key in result_map]
        if not touched:
            continue
        if len(touched) != len(group):
            raise ValueError('coupled transmission requires all named channels')
        # The source coefficient maps native actuator effort to its native
        # axis; sign maps that axis to the declared canonical direction.
        native = [x.sign * result_map[x.target_key].value / x.transmission_coefficient for x in group]
        if any(not math.isclose(x, native[0], rel_tol=0, abs_tol=1e-12) for x in native[1:]):
            raise ValueError('joint effort vector is not representable by source transmission')
        if not group[0].native_range[0] <= native[0] <= group[0].native_range[1]:
            raise ValueError('source transmission native range exceeded')
    body_results = []
    if batch.body_wrenches:
        if (type(body_build_receipt) is not PhysicalBodyBuildReceiptV1
                or body_build_receipt.binding_sha256 != binding.identity_hash
                or body_build_receipt.source_closure_sha256 != binding.source_closure_sha256
                or body_build_receipt.provider_materialization_id != context.boundary.provider_materialization_id):
            raise ValueError('body wrench requires an exact session build mapping receipt')
        if set(body_build_receipt.bodies) != set(binding.bodies):
            raise ValueError('body build mapping differs from declared source binding')
        if type(state) not in (CanonicalStateViewV1, CanonicalStateViewV2):
            raise TypeError('body wrench requires a typed canonical state snapshot')
        if state.boundary != context.boundary or state.sample_clock != context.clock:
            raise ValueError('body wrench frame state is stale or foreign')
        poses = {entry.frame: entry.pose_world for entry in state.frames}
        bindings = {(x.entity_id, x.body_id): x for x in binding.bodies}
        groups = {}
        for item in batch.body_wrenches:
            key = (item.entity_id, item.body_id)
            if key not in bindings:
                raise ValueError('body wrench target is not source-bound')
            if item.contribution.owner_id not in bindings[key].owner_ids:
                raise ValueError('body wrench owner is not bound to the target')
            groups.setdefault(key, []).append(item)
        for key, items in sorted(groups.items()):
            if len(items) > 1 and any(x.contribution.composition != 'sum' for x in items):
                raise ValueError('overlapping body wrenches require declared sum')
            body = bindings[key]
            try:
                origin = poses[body.body_frame].position
                force_total, torque_total = (0., 0., 0.), (0., 0., 0.)
                for item in items:
                    _origin, force, torque_origin = resolve_body_wrench_at_poses(item, body.body_frame, poses)
                    force_total, torque_total = _add(force_total, force), _add(torque_total, torque_origin)
            except KeyError as exc:
                raise ValueError(f'required body wrench frame is unavailable: {exc.args[0]}') from exc
            body_results.append(ResolvedBodyWrenchV1(*key, force_total, torque_total, origin,
                tuple(x.contribution.contribution_id for x in items)))
    ids = tuple(x.contribution.contribution_id for x in (*batch.joint_efforts, *batch.body_wrenches, *batch.extensions))
    receipt = PhysicalControlReceiptV1('physical-control-receipt-v1', context, batch.identity_hash,
                                       'accepted', ids, 'core-admission', 'per-channel')
    return ResolvedPhysicalBatchV1(batch, binding.identity_hash, tuple(results),
                                   tuple(body_results), batch.extensions, receipt,
                                   tuple(x.provenance for x in receipts))
