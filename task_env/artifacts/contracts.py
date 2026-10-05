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
    if isinstance(value, tuple):
        return [_encode(v) for v in value]
    return value


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
