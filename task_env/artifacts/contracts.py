"""Additive Phase-I data contracts. No simulator construction or storage ABI.

All physical values use SI, right-handed Z-up world coordinates and wxyz
unit quaternions. Schemas reject unknown fields at every typed boundary.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
import hashlib
import json
import math
import re
from types import MappingProxyType, UnionType
from typing import Union, get_type_hints, get_origin, get_args


_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]*\Z")
_SOURCE_REFERENCE = re.compile(r"[a-z][a-z0-9+.-]*:[^\s\\]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CAPABILITY_NAMES = frozenset({
    'rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation',
    'joint_state_query', 'body_pose_query', 'frame_pose_query', 'rgb_camera',
    'depth_camera', 'contact_detection', 'contact_impulse',
})
SUPPORTED_STATUSES = frozenset({'implemented', 'tested', 'qualified'})
# Eight float32 epsilons cover normalization and four-component norm-squared
# rounding. Adapters normalize before output; this is representation sanity,
# never a task/physics tolerance. The codec preserves values for roundtrip.
QUATERNION_NORM_SQ_ATOL = 8 * 2**-23


def _name(value: str) -> None:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError(f'invalid semantic name: {value!r}')


def _choice(value, choices, label):
    if value not in choices:
        raise ValueError(f'unsupported {label}: {value!r}')


def _nonempty(values, label):
    if not values or len(set(values)) != len(values):
        raise ValueError(f'{label} must be nonempty and unique')


def _decode(annotation, value):
    origin, args = get_origin(annotation), get_args(annotation)
    if annotation is object:
        return _decode_json_value(value)
    if origin in (UnionType, Union) and len(args) == 2 and type(None) in args:
        if value is None:
            return None
        return _decode(next(t for t in args if t is not type(None)), value)
    if isinstance(annotation, type) and issubclass(annotation, Contract):
        return value if isinstance(value, annotation) else annotation.from_mapping(value)
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise TypeError('expected sequence')
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], v) for v in value)
        if len(args) != len(value):
            raise ValueError('wrong vector length')
        return tuple(_decode(t, v) for t, v in zip(args, value, strict=True))
    if origin is Mapping:
        if not isinstance(value, Mapping):
            raise TypeError('expected mapping')
        return MappingProxyType({_decode(args[0], k): _decode(args[1], v) for k, v in value.items()})
    if annotation is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('expected finite number')
        return float(value)
    if annotation is int:
        if type(value) is not int:
            raise TypeError('expected integer (not bool)')
    elif annotation is str:
        if type(value) is not str or not value.strip():
            raise ValueError('expected nonempty string')
    elif annotation is bool:
        if type(value) is not bool:
            raise TypeError('expected bool')
    else:
        raise TypeError(f'unsupported contract type {annotation}')
    return value


def _encode(value):
    if isinstance(value, Contract):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return {k: _encode(v) for k, v in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    return value


def _decode_json_value(value):
    """Freeze one strict JSON value used by versioned Source snapshots."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('JSON snapshot numbers must be finite')
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError('JSON snapshot object keys must be strings')
        return MappingProxyType({key: _decode_json_value(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_decode_json_value(item) for item in value)
    raise TypeError(f'unsupported JSON snapshot value: {type(value).__name__}')


class Contract:
    """Shared strict constructor and deterministic JSON/YAML mapping codec."""

    def __post_init__(self):
        for name, annotation in get_type_hints(type(self)).items():
            object.__setattr__(self, name, _decode(annotation, getattr(self, name)))
        self.validate()

    def validate(self):
        pass

    @classmethod
    def from_mapping(cls, values):
        if not isinstance(values, Mapping):
            raise TypeError(f'{cls.__name__} requires mapping')
        allowed = {f.name for f in fields(cls)}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f'unknown {cls.__name__} fields: {sorted(unknown, key=str)}')
        return cls(**dict(values))

    def to_mapping(self):
        return {f.name: _encode(getattr(self, f.name)) for f in fields(self)}


@dataclass(frozen=True)
class PoseWorld(Contract):
    position: tuple[float, float, float]
    quaternion_wxyz: tuple[float, float, float, float]

    def validate(self):
        if abs(sum(v * v for v in self.quaternion_wxyz) - 1.0) > QUATERNION_NORM_SQ_ATOL:
            raise ValueError('quaternion_wxyz must be normalized before canonical output')


@dataclass(frozen=True)
class EntityDefinition(Contract):
    semantic_id: str
    kind: str
    asset_reference: str
    frames: tuple[str, ...]
    joints: tuple[str, ...]
    geometry: str
    collision_intent: str
    parameters_si: Mapping[str, float]

    def validate(self):
        _name(self.semantic_id)
        _choice(self.kind, {'scene', 'static', 'movable', 'embodiment'}, 'entity kind')
        for names in (self.frames, self.joints):
            if len(set(names)) != len(names):
                raise ValueError('duplicate semantic names')
            for n in names:
                _name(n)
        for n in self.parameters_si:
            _name(n)


@dataclass(frozen=True)
class AssetDefinition(Contract):
    """Provider-neutral asset identity and source provenance, without native state."""

    schema_version: str
    asset_id: str
    asset_version: str
    source_reference: str
    source_revision: str | None = None
    source_content_sha256: str | None = None
    license_id: str | None = None

    def validate(self):
        _choice(self.schema_version, {'asset-definition-v1'}, 'asset definition schema')
        _name(self.asset_id)
        _name(self.asset_version)
        if (
            not isinstance(self.source_reference, str)
            or not _SOURCE_REFERENCE.fullmatch(self.source_reference)
        ):
            raise ValueError('source_reference must be a stable URI, not a local path')
        if self.source_reference.split(':', 1)[0] == 'file':
            raise ValueError('file URI is not stable asset provenance')
        if any(part == '..' for part in self.source_reference.split(':', 1)[1].split('/')):
            raise ValueError('source_reference cannot traverse parent paths')
        if self.source_revision is not None:
            if (
                type(self.source_revision) is not str
                or not self.source_revision.strip()
                or self.source_revision != self.source_revision.strip()
                or '\\' in self.source_revision
                or any(part == '..' for part in self.source_revision.split('/'))
                or self.source_revision.startswith('/')
                or re.match(r'^[A-Za-z]:/', self.source_revision)
            ):
                raise ValueError('source_revision must be a stable nonempty token')
        if self.source_content_sha256 is not None and not _SHA256.fullmatch(self.source_content_sha256):
            raise ValueError('source_content_sha256 must be lowercase SHA-256 hex')
        if self.license_id is not None:
            _name(self.license_id)

    @property
    def identity_hash(self):
        canonical = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class EntityInstance(Contract):
    """Scene-scoped instance identity pinned to one declared asset version."""

    schema_version: str
    entity_id: str
    asset_id: str
    asset_version: str

    def validate(self):
        _choice(self.schema_version, {'entity-instance-v1'}, 'entity instance schema')
        _name(self.entity_id)
        _name(self.asset_id)
        _name(self.asset_version)


@dataclass(frozen=True)
class FrameReference(Contract):
    """An entity-qualified, scene-local frame name."""

    entity_id: str
    frame_id: str

    def validate(self):
        _name(self.entity_id)
        _name(self.frame_id)


@dataclass(frozen=True)
class JointReference(Contract):
    """An entity-qualified identity for one canonical Scene joint."""

    entity_id: str
    joint_id: str

    def validate(self):
        _name(self.entity_id)
        _name(self.joint_id)


@dataclass(frozen=True)
class FrameDefinition(Contract):
    """An authored fixed frame or a runtime-owned dynamic frame anchor."""

    schema_version: str
    entity_id: str
    frame_id: str
    frame_kind: str
    parent: FrameReference | None
    pose_parent: PoseWorld | None

    def validate(self):
        _choice(self.schema_version, {'frame-definition-v1'}, 'frame schema')
        _name(self.entity_id)
        _name(self.frame_id)
        _choice(self.frame_kind, {'authored_fixed', 'runtime'}, 'frame kind')
        if self.frame_kind == 'runtime':
            if self.parent is not None or self.pose_parent is not None:
                raise ValueError('runtime link frame pose belongs to runtime state')
        elif self.pose_parent is None:
            raise ValueError('authored fixed frame requires a parent-relative pose')
        if self.parent == FrameReference(self.entity_id, self.frame_id):
            raise ValueError('frame cannot parent itself')


_JOINT_COORDINATES = {
    'fixed': (None, 'none', 'none', 0, 0),
    'revolute': ('axis', 'radian', 'radian_per_second', 1, 1),
    'continuous': ('axis', 'radian', 'radian_per_second', 1, 1),
    'prismatic': ('axis', 'meter', 'meter_per_second', 1, 1),
    'spherical': (None, 'quaternion_wxyz', 'angular_xyz_radian_per_second', 4, 3),
    'floating': (None, 'xyz_meter_quaternion_wxyz',
                 'linear_xyz_meter_per_second_angular_xyz_radian_per_second', 7, 6),
}


@dataclass(frozen=True)
class JointDefinition(Contract):
    """Provider-neutral joint topology and canonical position/velocity layout."""

    schema_version: str
    joint_id: str
    parent_frame: FrameReference
    child_frame: FrameReference
    pose_parent_from_joint: PoseWorld
    pose_child_from_joint: PoseWorld
    kind: str
    axis: tuple[float, float, float] | None
    position_representation: str
    velocity_representation: str
    position_size: int
    velocity_size: int

    def validate(self):
        _choice(self.schema_version, {'joint-definition-v1'}, 'joint schema')
        _name(self.joint_id)
        if self.parent_frame == self.child_frame:
            raise ValueError('joint parent and child frames must differ')
        if self.parent_frame.entity_id != self.child_frame.entity_id:
            raise ValueError('joint endpoints must belong to the same entity articulation')
        if self.kind not in _JOINT_COORDINATES:
            raise ValueError(f'unsupported joint kind: {self.kind!r}')
        axis_rule, position, velocity, position_size, velocity_size = _JOINT_COORDINATES[self.kind]
        _choice(self.position_representation, {position}, 'joint position representation')
        _choice(self.velocity_representation, {velocity}, 'joint velocity representation')
        if (self.position_size, self.velocity_size) != (position_size, velocity_size):
            raise ValueError('joint position/velocity sizes do not match the canonical representation')
        if axis_rule == 'axis':
            if self.axis is None or abs(sum(value * value for value in self.axis) - 1.0) > 1e-9:
                raise ValueError('revolute and prismatic joints require a unit axis')
        elif self.axis is not None:
            raise ValueError(f'{self.kind} joint does not use a scalar axis')


@dataclass(frozen=True)
class ArticulationDefinition(Contract):
    """A tree of runtime link frames joined by entity-local joints."""

    schema_version: str
    entity_id: str
    root_frame_id: str
    link_frame_ids: tuple[str, ...]
    joints: tuple[JointDefinition, ...]

    def validate(self):
        _choice(self.schema_version, {'articulation-definition-v1'}, 'articulation schema')
        _name(self.entity_id)
        _name(self.root_frame_id)
        _nonempty(self.link_frame_ids, 'articulation link frames')
        for frame_id in self.link_frame_ids:
            _name(frame_id)
        if self.root_frame_id not in self.link_frame_ids:
            raise ValueError('articulation root must name a declared link frame')
        joint_ids = tuple(joint.joint_id for joint in self.joints)
        if len(set(joint_ids)) != len(joint_ids):
            raise ValueError('duplicate entity-local joint IDs')

        incoming = {}
        outgoing = {frame_id: [] for frame_id in self.link_frame_ids}
        for joint in self.joints:
            if joint.parent_frame.entity_id != self.entity_id or joint.child_frame.entity_id != self.entity_id:
                raise ValueError('joint endpoints must match the articulation entity')
            parent, child = joint.parent_frame.frame_id, joint.child_frame.frame_id
            if parent not in outgoing or child not in outgoing:
                raise ValueError('joint references an undeclared articulation link')
            if child in incoming:
                raise ValueError('articulation link has more than one parent joint')
            incoming[child] = parent
            outgoing[parent].append(child)
        if self.root_frame_id in incoming:
            raise ValueError('articulation root cannot have a parent joint')
        if set(incoming) != set(self.link_frame_ids) - {self.root_frame_id}:
            raise ValueError('every non-root articulation link requires one parent joint')

        reached = set()
        pending = [self.root_frame_id]
        while pending:
            current = pending.pop()
            if current in reached:
                raise ValueError('articulation joint graph contains a cycle')
            reached.add(current)
            pending.extend(outgoing[current])
        if reached != set(self.link_frame_ids):
            raise ValueError('articulation joint graph is disconnected or cyclic')

        object.__setattr__(self, 'link_frame_ids', tuple(sorted(self.link_frame_ids)))
        object.__setattr__(self, 'joints', tuple(sorted(self.joints, key=lambda joint: joint.joint_id)))


@dataclass(frozen=True)
class RobotInstance(Contract):
    """A Scene entity explicitly used as one robot instance."""

    schema_version: str
    entity_id: str
    articulation_roots: tuple[FrameReference, ...]

    def validate(self):
        _choice(self.schema_version, {'robot-instance-v1'}, 'robot instance schema')
        _name(self.entity_id)
        _nonempty(self.articulation_roots, 'robot articulation roots')
        if any(root.entity_id != self.entity_id for root in self.articulation_roots):
            raise ValueError('robot articulation roots must belong to the robot entity')
        object.__setattr__(
            self,
            'articulation_roots',
            tuple(sorted(self.articulation_roots, key=lambda root: (root.entity_id, root.frame_id))),
        )


@dataclass(frozen=True)
class ActuatorReference(Contract):
    """An entity-qualified identity for a declared control resource."""

    entity_id: str
    actuator_id: str

    def validate(self):
        _name(self.entity_id)
        _name(self.actuator_id)


@dataclass(frozen=True)
class ActuatorResourceDefinition(Contract):
    """An entity-owned actuator identity without a joint or command projection."""

    schema_version: str
    entity_id: str
    actuator_id: str

    def validate(self):
        _choice(self.schema_version, {'actuator-resource-v1'}, 'actuator resource schema')
        _name(self.entity_id)
        _name(self.actuator_id)


@dataclass(frozen=True)
class ControlGroup(Contract):
    """A robot-local, statically declared set of actuator resources."""

    schema_version: str
    entity_id: str
    group_id: str
    actuator_refs: tuple[ActuatorReference, ...]

    def validate(self):
        _choice(self.schema_version, {'control-group-v1'}, 'control group schema')
        _name(self.entity_id)
        _name(self.group_id)
        _nonempty(self.actuator_refs, 'control group actuator references')
        if any(reference.entity_id != self.entity_id for reference in self.actuator_refs):
            raise ValueError('control group actuator references must belong to its robot entity')
        object.__setattr__(
            self,
            'actuator_refs',
            tuple(sorted(self.actuator_refs, key=lambda ref: (ref.entity_id, ref.actuator_id))),
        )


@dataclass(frozen=True)
class SceneDefinition(Contract):
    """Versioned scene identity and static structure; materialization is out of scope."""

    schema_version: str
    scene_id: str
    assets: tuple[AssetDefinition, ...]
    entities: tuple[EntityInstance, ...]
    frames: tuple[FrameDefinition, ...] | None = None
    articulations: tuple[ArticulationDefinition, ...] | None = None
    robots: tuple[RobotInstance, ...] | None = None
    actuator_resources: tuple[ActuatorResourceDefinition, ...] | None = None
    control_groups: tuple[ControlGroup, ...] | None = None

    @classmethod
    def from_mapping(cls, values):
        if not isinstance(values, Mapping):
            raise TypeError('SceneDefinition requires mapping')
        schema_version = values.get('schema_version')
        v1_fields = {'schema_version', 'scene_id', 'assets', 'entities'}
        v2_fields = v1_fields | {'frames', 'articulations'}
        v3_fields = v2_fields | {'robots', 'actuator_resources', 'control_groups'}
        fields_by_version = {
            'scene-definition-v1': v1_fields,
            'scene-definition-v2': v2_fields,
            'scene-definition-v3': v3_fields,
        }
        allowed = fields_by_version.get(schema_version)
        if allowed is None:
            raise ValueError(f'unsupported scene definition schema: {schema_version!r}')
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f'unknown SceneDefinition fields for {schema_version}: {sorted(unknown, key=str)}')
        missing = allowed - set(values)
        if missing:
            raise ValueError(f'missing SceneDefinition fields for {schema_version}: {sorted(missing)}')
        return cls(**dict(values))

    def to_mapping(self):
        values = super().to_mapping()
        fields_by_version = {
            'scene-definition-v1': ('schema_version', 'scene_id', 'assets', 'entities'),
            'scene-definition-v2': (
                'schema_version', 'scene_id', 'assets', 'entities', 'frames', 'articulations',
            ),
            'scene-definition-v3': (
                'schema_version', 'scene_id', 'assets', 'entities', 'frames', 'articulations',
                'robots', 'actuator_resources', 'control_groups',
            ),
        }
        names = fields_by_version.get(self.schema_version)
        if names is None:
            raise ValueError(f'unsupported scene definition schema: {self.schema_version!r}')
        return {name: values[name] for name in names}

    def validate(self):
        _choice(
            self.schema_version,
            {'scene-definition-v1', 'scene-definition-v2', 'scene-definition-v3'},
            'scene definition schema',
        )
        _name(self.scene_id)
        asset_keys = tuple((asset.asset_id, asset.asset_version) for asset in self.assets)
        entity_ids = tuple(entity.entity_id for entity in self.entities)
        _nonempty(asset_keys, 'scene asset identities')
        _nonempty(entity_ids, 'scene entity IDs')
        declared_assets = set(asset_keys)
        referenced_assets = {(entity.asset_id, entity.asset_version) for entity in self.entities}
        missing = referenced_assets - declared_assets
        if missing:
            raise ValueError(f'entities reference undeclared asset definitions: {sorted(missing)}')
        unused = declared_assets - referenced_assets
        if unused:
            raise ValueError(f'scene contains unused asset definitions: {sorted(unused)}')
        object.__setattr__(
            self,
            'assets',
            tuple(sorted(self.assets, key=lambda asset: (asset.asset_id, asset.asset_version))),
        )
        object.__setattr__(
            self,
            'entities',
            tuple(sorted(self.entities, key=lambda entity: entity.entity_id)),
        )
        if self.schema_version == 'scene-definition-v1':
            if any(value is not None for value in (
                self.frames, self.articulations, self.robots, self.actuator_resources,
                self.control_groups,
            )):
                raise ValueError('scene-definition-v1 does not accept structure or composition fields')
            return
        if self.schema_version == 'scene-definition-v2' and any(value is not None for value in (
            self.robots, self.actuator_resources, self.control_groups,
        )):
            raise ValueError('scene-definition-v2 does not accept robot or control fields')
        self._validate_structure()
        if self.schema_version == 'scene-definition-v3':
            self._validate_robot_control()

    def _validate_structure(self):
        if self.frames is None or self.articulations is None:
            raise ValueError(f'{self.schema_version} requires frames and articulations fields')
        _nonempty(tuple((frame.entity_id, frame.frame_id) for frame in self.frames), 'scene frame identities')
        entities = {entity.entity_id for entity in self.entities}
        frames = {FrameReference(frame.entity_id, frame.frame_id): frame for frame in self.frames}
        if any(frame.entity_id not in entities for frame in self.frames):
            raise ValueError('frame references an undeclared scene entity')
        for frame in self.frames:
            if frame.parent is not None and frame.parent not in frames:
                raise ValueError(f'frame references missing parent: {frame.parent}')

        visit_state = {}

        def visit(reference):
            state = visit_state.get(reference, 0)
            if state == 1:
                raise ValueError('scene frame graph contains a cycle')
            if state == 2:
                return
            visit_state[reference] = 1
            parent = frames[reference].parent
            if parent is not None:
                visit(parent)
            visit_state[reference] = 2

        for reference in frames:
            visit(reference)

        articulated_links = set()
        entity_joint_ids = set()
        for articulation in self.articulations:
            if articulation.entity_id not in entities:
                raise ValueError('articulation references an undeclared scene entity')
            for frame_id in articulation.link_frame_ids:
                reference = FrameReference(articulation.entity_id, frame_id)
                definition = frames.get(reference)
                if definition is None or definition.frame_kind != 'runtime':
                    raise ValueError('articulation links must reference runtime frames')
                if reference in articulated_links:
                    raise ValueError('runtime link frame belongs to multiple articulations')
                articulated_links.add(reference)
            for joint in articulation.joints:
                identity = (articulation.entity_id, joint.joint_id)
                if identity in entity_joint_ids:
                    raise ValueError('duplicate entity-local joint IDs across articulations')
                entity_joint_ids.add(identity)

        object.__setattr__(
            self,
            'frames',
            tuple(sorted(self.frames, key=lambda frame: (frame.entity_id, frame.frame_id))),
        )
        object.__setattr__(
            self,
            'articulations',
            tuple(sorted(self.articulations,
                         key=lambda articulation: (articulation.entity_id, articulation.root_frame_id))),
        )

    def _validate_robot_control(self):
        if self.robots is None or self.actuator_resources is None or self.control_groups is None:
            raise ValueError(
                'scene-definition-v3 requires robots, actuator_resources, and control_groups fields'
            )

        entities = {entity.entity_id for entity in self.entities}
        articulations = {
            (articulation.entity_id, articulation.root_frame_id)
            for articulation in self.articulations or ()
        }
        robot_entity_ids = tuple(robot.entity_id for robot in self.robots)
        if robot_entity_ids:
            _nonempty(robot_entity_ids, 'scene robot entity IDs')
        if any(entity_id not in entities for entity_id in robot_entity_ids):
            raise ValueError('robot references an undeclared scene entity')

        for robot in self.robots:
            expected_roots = {
                FrameReference(entity_id, root_frame_id)
                for entity_id, root_frame_id in articulations
                if entity_id == robot.entity_id
            }
            actual_roots = set(robot.articulation_roots)
            if actual_roots != expected_roots:
                raise ValueError(
                    'robot articulation roots must exactly identify its entity articulations'
                )
            if not actual_roots:
                raise ValueError('robot entity must own at least one articulation')

        resource_keys = tuple(
            (resource.entity_id, resource.actuator_id) for resource in self.actuator_resources
        )
        if resource_keys:
            if len(set(resource_keys)) != len(resource_keys):
                raise ValueError('duplicate entity-qualified actuator resource IDs')
        resources = set(resource_keys)
        for resource in self.actuator_resources:
            if resource.entity_id not in entities:
                raise ValueError('actuator resource references an undeclared scene entity')
            if resource.entity_id not in robot_entity_ids:
                raise ValueError('actuator resources must belong to a RobotInstance entity')

        group_keys = tuple((group.entity_id, group.group_id) for group in self.control_groups)
        if group_keys and len(set(group_keys)) != len(group_keys):
            raise ValueError('duplicate entity-qualified control group IDs')
        writers = set()
        for group in self.control_groups:
            if group.entity_id not in robot_entity_ids:
                raise ValueError('control group references an entity without a RobotInstance')
            for reference in group.actuator_refs:
                key = (reference.entity_id, reference.actuator_id)
                if key not in resources:
                    raise ValueError(f'control group references an unknown actuator: {reference}')
                if key in writers:
                    raise ValueError(f'actuator has more than one statically declared writer: {reference}')
                writers.add(key)

        object.__setattr__(self, 'robots', tuple(sorted(self.robots, key=lambda robot: robot.entity_id)))
        object.__setattr__(
            self,
            'actuator_resources',
            tuple(sorted(self.actuator_resources, key=lambda item: (item.entity_id, item.actuator_id))),
        )
        object.__setattr__(
            self,
            'control_groups',
            tuple(sorted(self.control_groups, key=lambda group: (group.entity_id, group.group_id))),
        )

    def _require_v3(self):
        if self.schema_version != 'scene-definition-v3':
            raise ValueError('robot/control resolution requires scene-definition-v3')

    def resolve_robot(self, entity_id: str) -> RobotInstance:
        self._require_v3()
        for robot in self.robots or ():
            if robot.entity_id == entity_id:
                return robot
        raise KeyError(f'unknown RobotInstance entity: {entity_id}')

    def resolve_control_group(self, entity_id: str, group_id: str) -> ControlGroup:
        self._require_v3()
        key = (entity_id, group_id)
        for group in self.control_groups or ():
            if (group.entity_id, group.group_id) == key:
                return group
        raise KeyError(f'unknown entity-qualified ControlGroup: {key}')

    def resolve_actuator(self, reference: ActuatorReference) -> ActuatorResourceDefinition:
        self._require_v3()
        if not isinstance(reference, ActuatorReference):
            raise TypeError('actuator resolution requires ActuatorReference')
        key = (reference.entity_id, reference.actuator_id)
        for resource in self.actuator_resources or ():
            if (resource.entity_id, resource.actuator_id) == key:
                return resource
        raise KeyError(f'unknown entity-qualified actuator: {reference}')

    def resolve_frame_pose(self, frame: FrameReference, *, relative_to: FrameReference | None = None) -> PoseWorld:
        """Resolve authored fixed transforms; runtime link anchors require D02 state."""
        if self.schema_version not in {'scene-definition-v2', 'scene-definition-v3'} or self.frames is None:
            raise ValueError('frame resolution requires scene-definition-v2 or scene-definition-v3')
        frames = {FrameReference(item.entity_id, item.frame_id): item for item in self.frames}
        if frame not in frames:
            raise ValueError(f'unknown frame: {frame}')

        identity = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        if relative_to is not None:
            if relative_to not in frames:
                raise ValueError(f'unknown reference frame: {relative_to}')
            chain = []
            current = frame
            while current != relative_to:
                definition = frames[current]
                if definition.frame_kind != 'authored_fixed' or definition.pose_parent is None:
                    raise ValueError('relative transform crosses an unresolved runtime link frame')
                chain.append(definition.pose_parent)
                if definition.parent is None:
                    raise ValueError('reference frame is not an ancestor of target frame')
                current = definition.parent
            result = identity
            for local in reversed(chain):
                result = _compose_pose(result, local)
            return result

        def resolve_world(reference, visiting):
            if reference in visiting:
                raise ValueError('scene frame graph contains a cycle')
            definition = frames[reference]
            if definition.frame_kind == 'runtime' or definition.pose_parent is None:
                raise ValueError('runtime link pose requires D02 canonical state')
            if definition.parent is None:
                return definition.pose_parent
            visiting.add(reference)
            parent_pose = resolve_world(definition.parent, visiting)
            visiting.remove(reference)
            return _compose_pose(parent_pose, definition.pose_parent)

        return resolve_world(frame, set())

    @property
    def identity_hash(self):
        canonical = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


def _compose_pose(parent: PoseWorld, child: PoseWorld) -> PoseWorld:
    """Return ``T_world_from_child`` from a parent-world and child-parent pose."""
    from ..utils.rotation import quat_multiply_wxyz, rotate_vector_wxyz

    rotated_position = rotate_vector_wxyz(parent.quaternion_wxyz, child.position)
    position = tuple(float(parent.position[index] + rotated_position[index]) for index in range(3))
    quaternion = quat_multiply_wxyz(parent.quaternion_wxyz, child.quaternion_wxyz)
    return PoseWorld(
        position,
        tuple(float(value) for value in quaternion),
    )


@dataclass(frozen=True)
class ActionIntent(Contract):
    mode: str
    reference: str | None
    rotation_representation: str
    controller_target: str

    def validate(self):
        _choice(self.mode, {'absolute_pose', 'delta_pose', 'absolute_joint'}, 'action mode')
        # Compatibility source: Core ActionModeSpec.__post_init__.
        allowed_references = {
            'absolute_joint': {None},
            'absolute_pose': {'world', 'base'},
            'delta_pose': {'world', 'base', 'ee'},
        }
        _choice(self.reference, allowed_references[self.mode], 'action reference')
        _choice(self.rotation_representation, {'quaternion_wxyz', 'rotvec', 'none'}, 'rotation')
        if self.mode == 'absolute_joint' and self.rotation_representation != 'none':
            raise ValueError('joint action has no rotation representation')
        if self.mode != 'absolute_joint' and self.rotation_representation == 'none':
            raise ValueError('pose action requires rotation representation')
        _choice(self.controller_target, {'arm_joint_position_and_gripper'}, 'controller target')


@dataclass(frozen=True)
class WorldDefinition(Contract):
    schema_version: str
    convention: str
    entities: tuple[EntityDefinition, ...]
    action: ActionIntent
    observation_requirements: tuple[str, ...]
    randomization_dimensions: tuple[str, ...]

    @property
    def semantic_names(self):
        return frozenset(n for e in self.entities for n in (e.semantic_id, *e.frames))

    @property
    def joint_names(self):
        return frozenset(n for e in self.entities for n in e.joints)

    def validate(self):
        _choice(self.schema_version, {'world-v0'}, 'world schema')
        _choice(self.convention, {'SI_right_handed_z_up_wxyz'}, 'world convention')
        _nonempty(tuple(e.semantic_id for e in self.entities), 'entity IDs')
        all_names = tuple(n for e in self.entities for n in (e.semantic_id, *e.frames, *e.joints))
        _nonempty(all_names, 'world semantic names')
        _nonempty(self.observation_requirements, 'observations')
        for n in (*self.observation_requirements, *self.randomization_dimensions):
            _name(n)
        if len(set(self.randomization_dimensions)) != len(self.randomization_dimensions):
            raise ValueError('duplicate randomization dimensions')


@dataclass(frozen=True)
class UniformDimension(Contract):
    name: str
    hard_bounds: tuple[float, float]
    training_bounds: tuple[float, float]
    feasibility_bounds: tuple[float, float]
    evaluation_bounds: tuple[float, float]
    distribution: str = 'uniform'

    def validate(self):
        _name(self.name)
        _choice(self.distribution, {'uniform'}, 'distribution')
        lo, hi = self.hard_bounds
        if lo >= hi:
            raise ValueError('hard bounds must increase')
        for a, b in (self.training_bounds, self.feasibility_bounds, self.evaluation_bounds):
            if not lo <= a < b <= hi:
                raise ValueError('distribution outside hard bounds')


@dataclass(frozen=True)
class InitializationContract(Contract):
    schema_version: str
    poses_world: Mapping[str, PoseWorld]
    joint_position: Mapping[str, float]
    randomization: tuple[UniformDimension, ...]
    inherited_state_policy: str
    reset_validity: str
    settle_steps: int

    def validate(self):
        _choice(self.schema_version, {'initialization-v0'}, 'initialization schema')
        for n in (*self.poses_world, *self.joint_position):
            _name(n)
        names = tuple(d.name for d in self.randomization)
        if len(set(names)) != len(names):
            raise ValueError('duplicate randomization names')
        if self.settle_steps < 0:
            raise ValueError('settle_steps must be nonnegative')


@dataclass(frozen=True)
class SemanticDefinition(Contract):
    schema_version: str
    evaluator: str
    required_poses: tuple[str, ...]
    required_joints: tuple[str, ...]
    parameters_si: Mapping[str, float]
    success_definition: str

    def validate(self):
        _choice(self.schema_version, {'semantics-v0'}, 'semantic schema')
        _name(self.evaluator)
        _name(self.success_definition)
        for names in (self.required_poses, self.required_joints):
            if len(set(names)) != len(names):
                raise ValueError('duplicate semantic requirements')
            for n in names:
                _name(n)
        for n in self.parameters_si:
            _name(n)

    def require_state(self, state: CanonicalStateView):
        missing = (set(self.required_poses) - set(state.pose_world)) | (set(self.required_joints) - set(state.joint_position))
        if missing:
            raise ValueError(f'missing semantic state: {sorted(missing)}')


@dataclass(frozen=True)
class Timebase(Contract):
    physics_dt: float
    control_substeps: int
    control_dt: float
    action_hold: str = 'zero_order_hold'
    observation_sampling: str = 'post_control_step'
    semantic_sampling: str = 'post_control_step'

    def validate(self):
        if self.physics_dt <= 0 or self.control_substeps < 1:
            raise ValueError('invalid physics_dt/control_substeps')
        # Permit at most one ULP for equivalent decimal/JSON representations.
        expected = self.physics_dt * self.control_substeps
        if not math.isfinite(expected) or abs(self.control_dt - expected) > math.ulp(expected):
            raise ValueError('control_dt must equal physics_dt * control_substeps')
        _choice(self.action_hold, {'zero_order_hold'}, 'action hold')
        for v in (self.observation_sampling, self.semantic_sampling):
            _choice(v, {'post_control_step'}, 'sampling')


@dataclass(frozen=True)
class RequiredCapabilitySet(Contract):
    names: tuple[str, ...]

    def validate(self):
        for n in self.names:
            _choice(n, CAPABILITY_NAMES, 'capability')
        object.__setattr__(self, 'names', tuple(sorted(set(self.names))))


@dataclass(frozen=True)
class TaskArtifact(Contract):
    schema_version: str
    artifact_id: str
    task_id: str
    artifact_version: str
    world: WorldDefinition
    initialization: InitializationContract
    semantics: SemanticDefinition
    timebase: Timebase
    required_capabilities: RequiredCapabilitySet

    def validate(self):
        _choice(self.schema_version, {'task-artifact-v0'}, 'artifact schema')
        for n in (self.artifact_id, self.task_id, self.artifact_version):
            _name(n)
        if not set(self.initialization.poses_world) <= self.world.semantic_names:
            raise ValueError('initialization references undeclared pose')
        if not set(self.initialization.joint_position) <= self.world.joint_names:
            raise ValueError('initialization references undeclared joint')
        if not set(self.semantics.required_poses) <= self.world.semantic_names:
            raise ValueError('semantics references undeclared pose')
        if not set(self.semantics.required_joints) <= self.world.joint_names:
            raise ValueError('semantics references undeclared joint')
        if set(self.world.randomization_dimensions) != {d.name for d in self.initialization.randomization}:
            raise ValueError('world/initialization randomization mismatch')

    @property
    def identity_hash(self):
        canonical = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class TaskArtifactV1(Contract):
    """Compiled task declaration that references the canonical Scene by identity.

    This value deliberately retains only the task-facing contracts from the
    legacy artifact. The imported Scene remains owned and serialized by
    ``SceneDefinition``; provider execution provenance remains outside task
    semantic identity.
    """

    schema_version: str
    artifact_id: str
    task_id: str
    artifact_version: str
    source_artifact_schema_version: str
    source_artifact_identity_hash: str
    source_retained_v0_fields: tuple[str, ...]
    scene_schema_version: str
    scene_id: str
    scene_identity_hash: str
    legacy_frame_bindings: Mapping[str, FrameReference]
    legacy_joint_bindings: Mapping[str, JointReference]
    task_source_schema_version: str
    task_source: Mapping[str, object]
    task_source_identity_hash: str
    action: ActionIntent
    world_convention: str
    observation_requirements: tuple[str, ...]
    initialization: InitializationContract
    semantics: SemanticDefinition
    timebase: Timebase
    required_capabilities: RequiredCapabilitySet

    def validate(self):
        _choice(self.schema_version, {'task-artifact-v1'}, 'artifact schema')
        for value in (self.artifact_id, self.task_id, self.artifact_version, self.scene_id):
            _name(value)
        _choice(self.source_artifact_schema_version, {'task-artifact-v0'}, 'source Artifact schema')
        if not _SHA256.fullmatch(self.source_artifact_identity_hash):
            raise ValueError('TaskArtifact source requires a lowercase v0 Artifact identity')
        if not self.source_retained_v0_fields or len(set(self.source_retained_v0_fields)) != len(self.source_retained_v0_fields):
            raise ValueError('TaskArtifact v1 must explicitly retain each unmapped v0 World field')
        if any(
            type(pointer) is not str or not pointer.startswith('/world/entities/')
            for pointer in self.source_retained_v0_fields
        ):
            raise ValueError('source-retained v0 field pointers must identify legacy World Entities')
        _choice(
            self.scene_schema_version,
            {'scene-definition-v1', 'scene-definition-v2', 'scene-definition-v3'},
            'TaskArtifact Scene reference schema',
        )
        _choice(self.task_source_schema_version, {'task-source-v1'}, 'Task Source schema')
        if not _SHA256.fullmatch(self.scene_identity_hash):
            raise ValueError('TaskArtifact Scene reference requires a lowercase SHA-256 identity')
        for legacy_name, reference in (*self.legacy_frame_bindings.items(), *self.legacy_joint_bindings.items()):
            _name(legacy_name)
            if not isinstance(reference, (FrameReference, JointReference)):
                raise TypeError('legacy Scene bindings require typed FrameReference/JointReference values')
        if not _SHA256.fullmatch(self.task_source_identity_hash):
            raise ValueError('TaskArtifact Source reference requires a lowercase SHA-256 identity')
        _choice(self.world_convention, {'SI_right_handed_z_up_wxyz'}, 'world convention')
        if not isinstance(self.task_source, Mapping) or not self.task_source:
            raise ValueError('TaskArtifact Source snapshot must be a nonempty mapping')
        try:
            source = _encode(self.task_source)
            canonical_source = json.dumps(
                source, sort_keys=True, separators=(',', ':'), allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError('TaskArtifact Source snapshot must be strict JSON data') from exc
        if hashlib.sha256(canonical_source.encode('utf-8')).hexdigest() != self.task_source_identity_hash:
            raise ValueError('TaskArtifact Source snapshot identity mismatch')
        if source.get('schema_version') != self.task_source_schema_version:
            raise ValueError('TaskArtifact Source snapshot schema mismatch')
        identity, scene_reference = source.get('identity'), source.get('scene')
        if not isinstance(identity, Mapping) or identity.get('task_id') != self.task_id:
            raise ValueError('TaskArtifact Source snapshot task identity mismatch')
        if identity.get('version') != self.artifact_version:
            raise ValueError('TaskArtifact Source snapshot version mismatch')
        if not isinstance(scene_reference, Mapping) or scene_reference.get('ref') != self.scene_id:
            raise ValueError('TaskArtifact Source snapshot Scene reference mismatch')
        _nonempty(self.observation_requirements, 'observations')
        if len(set(self.observation_requirements)) != len(self.observation_requirements):
            raise ValueError('duplicate observation requirements')
        for name in self.observation_requirements:
            _name(name)

    @property
    def identity_hash(self):
        canonical = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def task_source_mapping(self) -> Mapping:
        """Return a fresh mapping; callers re-decode it through TaskSourceV1."""
        return json.loads(json.dumps(_encode(self.task_source), sort_keys=True, separators=(',', ':')))


def decode_task_artifact(values: Mapping | TaskArtifact | TaskArtifactV1) -> TaskArtifact | TaskArtifactV1:
    """Decode the one TaskArtifact version domain by its exact discriminator.

    ``TaskArtifact.from_mapping`` remains the frozen v0-only codec. This
    dispatcher never infers versions from field shape or upgrades input.
    """
    if isinstance(values, (TaskArtifact, TaskArtifactV1)):
        return values
    if not isinstance(values, Mapping):
        raise TypeError('TaskArtifact decoder requires a mapping or typed TaskArtifact')
    schema_version = values.get('schema_version')
    codecs = {
        'task-artifact-v0': TaskArtifact,
        'task-artifact-v1': TaskArtifactV1,
    }
    codec = codecs.get(schema_version)
    if codec is None:
        raise ValueError(f'unsupported TaskArtifact schema: {schema_version!r}')
    return codec.from_mapping(values)


@dataclass(frozen=True)
class ExecutionSpec(Contract):
    physics_provider: str
    physics_profile: str
    render_provider: str
    backend: str
    provider_seed: int
    determinism_mode: str

    def validate(self):
        for n in (self.physics_provider, self.physics_profile, self.render_provider, self.backend):
            _name(n)
        if self.provider_seed < 0:
            raise ValueError('provider_seed must be nonnegative')
        _choice(self.determinism_mode, {'strict', 'best_effort', 'none'}, 'determinism')


@dataclass(frozen=True)
class RendererSelectionV1(Contract):
    """One fully named renderer choice; selection is not provider admission."""

    schema_version: str
    provider: str
    backend: str
    profile: str
    device: str | None = None

    def validate(self):
        _choice(self.schema_version, {'renderer-selection-v1'}, 'renderer selection schema')
        for value in (self.provider, self.backend, self.profile):
            _name(value)
        if self.device is not None:
            _name(self.device)

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class CameraRendererOverrideV1(Contract):
    """An explicit, complete renderer selection for one declared camera ID."""

    schema_version: str
    camera_id: str
    renderer: RendererSelectionV1

    def validate(self):
        _choice(self.schema_version, {'camera-renderer-override-v1'}, 'camera renderer override schema')
        _name(self.camera_id)


@dataclass(frozen=True)
class ExecutionSpecV1(Contract):
    """Versioned static physics/render selection, before admission or materialization."""

    schema_version: str
    physics_provider: str
    physics_backend: str
    physics_profile: str
    provider_seed: int
    determinism_mode: str
    render_default: RendererSelectionV1
    physics_device: str | None = None
    camera_overrides: tuple[CameraRendererOverrideV1, ...] = ()

    def validate(self):
        _choice(self.schema_version, {'execution-spec-v1'}, 'execution schema')
        for value in (self.physics_provider, self.physics_backend, self.physics_profile):
            _name(value)
        if self.physics_device is not None:
            _name(self.physics_device)
        if type(self.provider_seed) is not int or self.provider_seed < 0:
            raise ValueError('provider_seed must be a nonnegative integer')
        _choice(self.determinism_mode, {'strict', 'best_effort', 'none'}, 'determinism')
        camera_ids = tuple(item.camera_id for item in self.camera_overrides)
        if len(camera_ids) != len(set(camera_ids)):
            raise ValueError('duplicate per-camera renderer override')
        object.__setattr__(
            self,
            'camera_overrides',
            tuple(sorted(self.camera_overrides, key=lambda item: item.camera_id)),
        )

    def renderer_for_camera(self, camera_id: str) -> RendererSelectionV1:
        """Resolve an explicit camera override or the declared default selection."""

        _name(camera_id)
        for override in self.camera_overrides:
            if override.camera_id == camera_id:
                return override.renderer
        return self.render_default

    def resolve_camera_renderers(
        self, camera_ids: tuple[str, ...] | list[str]
    ) -> tuple[tuple[str, RendererSelectionV1], ...]:
        """Resolve a known camera set and reject dangling overrides."""

        normalized = tuple(camera_ids)
        for camera_id in normalized:
            _name(camera_id)
        if len(normalized) != len(set(normalized)):
            raise ValueError('duplicate declared camera ID')
        unknown = {item.camera_id for item in self.camera_overrides} - set(normalized)
        if unknown:
            raise ValueError(f'per-camera renderer override references unknown camera IDs: {sorted(unknown)}')
        return tuple(
            (camera_id, self.renderer_for_camera(camera_id))
            for camera_id in sorted(normalized)
        )

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode()).hexdigest()


def decode_execution_spec(values: Mapping | ExecutionSpec | ExecutionSpecV1) -> ExecutionSpec | ExecutionSpecV1:
    """Dispatch only exact legacy-v0 (missing discriminator) or declared v1 mappings."""

    if isinstance(values, (ExecutionSpec, ExecutionSpecV1)):
        return values
    if not isinstance(values, Mapping):
        raise TypeError('execution spec decoder requires a validated spec or mapping')
    version = values.get('schema_version')
    if version is None:
        return ExecutionSpec.from_mapping(values)
    if version == 'execution-spec-v1':
        return ExecutionSpecV1.from_mapping(values)
    raise ValueError(f'unsupported execution spec schema: {version!r}')


@dataclass(frozen=True)
class CapabilityClaim(Contract):
    name: str
    status: str
    evidence_reference: str

    def validate(self):
        _choice(self.name, CAPABILITY_NAMES, 'capability')
        _choice(self.status, SUPPORTED_STATUSES | {'planned', 'unknown', 'unsupported'}, 'status')


@dataclass(frozen=True)
class ProviderCapabilityManifest(Contract):
    schema_version: str
    provider_name: str
    provider_version: str
    adapter_version: str
    backend: str
    physics_profile: str
    render_profile: str
    determinism_mode: str
    capabilities: tuple[CapabilityClaim, ...]
    known_unsupported: tuple[str, ...]
    evidence_reference: str

    def validate(self):
        _choice(self.schema_version, {'provider-capability-v0'}, 'manifest schema')
        for n in (self.provider_name, self.backend, self.physics_profile, self.render_profile):
            _name(n)
        _choice(self.determinism_mode, {'strict', 'best_effort', 'none'}, 'determinism')
        names = tuple(c.name for c in self.capabilities)
        if len(set(names)) != len(names):
            raise ValueError('duplicate capability claims')
        for n in self.known_unsupported:
            _choice(n, CAPABILITY_NAMES, 'unsupported capability')
        if any(c.name in self.known_unsupported and c.status in SUPPORTED_STATUSES for c in self.capabilities):
            raise ValueError('contradictory capability claims')
        object.__setattr__(self, 'capabilities', tuple(sorted(self.capabilities, key=lambda c: c.name)))
        object.__setattr__(self, 'known_unsupported', tuple(sorted(set(self.known_unsupported))))

    @property
    def identity_hash(self) -> str:
        """Identity of the exact existing manifest mapping, with no schema change."""

        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode()).hexdigest()


class CapabilityAdmissionError(ValueError):
    """A named missing capability or execution mismatch; never a fallback."""


def admit_capabilities(required: RequiredCapabilitySet, manifest: ProviderCapabilityManifest,
                       execution: ExecutionSpec | None = None) -> None:
    if not isinstance(required, RequiredCapabilitySet) or not isinstance(manifest, ProviderCapabilityManifest):
        raise TypeError('admission requires validated contracts')
    supported = {c.name for c in manifest.capabilities if c.status in SUPPORTED_STATUSES}
    missing = set(required.names) - supported
    if missing:
        raise CapabilityAdmissionError(f'missing supported capabilities: {sorted(missing)}')
    if execution is not None:
        if not isinstance(execution, ExecutionSpec):
            raise TypeError('execution must be ExecutionSpec')
        for n in ('physics_profile', 'backend', 'determinism_mode'):
            if getattr(execution, n) != getattr(manifest, n):
                raise CapabilityAdmissionError(f'execution mismatch: {n}')
        if execution.physics_provider != manifest.provider_name:
            raise CapabilityAdmissionError('execution mismatch: physics_provider')


@dataclass(frozen=True)
class CanonicalStateView(Contract):
    schema_version: str
    convention: str
    control_step: int
    simulation_time: float
    joint_position: Mapping[str, float]
    joint_velocity: Mapping[str, float]
    pose_world: Mapping[str, PoseWorld]

    def validate(self):
        _choice(self.schema_version, {'canonical-state-v0'}, 'state schema')
        _choice(self.convention, {'SI_right_handed_z_up_wxyz'}, 'state convention')
        if self.control_step < 0 or self.simulation_time < 0:
            raise ValueError('negative time/step')
        for n in (*self.joint_position, *self.joint_velocity, *self.pose_world):
            _name(n)
        if set(self.joint_position) != set(self.joint_velocity):
            raise ValueError('joint position/velocity names must match')
