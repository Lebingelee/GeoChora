"""Provider-neutral P1.2 execution values, separate from TaskArtifact identity."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType

from typing import get_type_hints

from .contracts import (
    CanonicalStateView,
    Contract,
    PoseWorld,
    _SHA256,
    _choice,
    _decode,
    _encode,
    _name,
)


def canonical_json(value: Mapping) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class ResetSample(Contract):
    schema_version: str
    sample_id: str
    task_artifact_hash: str
    sampler_id: str
    sampler_version: str
    task_seed: int
    joint_position: Mapping[str, float]
    poses_world: Mapping[str, PoseWorld]
    velocity_policy: str
    control_policy: str
    settle_steps: int

    def validate(self):
        if self.schema_version != 'reset-sample-v0':
            raise ValueError('unsupported reset schema')
        if self.task_seed < 0 or self.settle_steps < 0:
            raise ValueError('negative seed/settle steps')
        if len(self.task_artifact_hash) != 64 or any(c not in '0123456789abcdef' for c in self.task_artifact_hash):
            raise ValueError('invalid artifact hash')
        for name in (*self.joint_position, *self.poses_world, self.sampler_id, self.sampler_version):
            _name(name)
        if self.velocity_policy != 'zero_named_joint_and_entity_velocities':
            raise ValueError('unsupported velocity policy')
        if self.control_policy != 'arm_targets_at_initial_joints_gripper_open':
            raise ValueError('unsupported control policy')
        if self.sample_id != 'reset-' + self.identity_hash:
            raise ValueError('sample identity mismatch')

    @property
    def identity_hash(self) -> str:
        mapping = self.to_mapping()
        del mapping['sample_id']
        return hashlib.sha256(canonical_json(mapping).encode()).hexdigest()

    @classmethod
    def create(cls, **values) -> ResetSample:
        # Normalize through the strict codec before hashing (e.g. int -> float
        # physical values), so constructor and mapping identity always agree.
        annotations = get_type_hints(cls)
        payload = {k: _encode(_decode(annotations[k], v))
                   for k, v in values.items() if k != 'sample_id'}
        digest = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        return cls.from_mapping({**payload, 'sample_id': 'reset-' + digest})


@dataclass(frozen=True)
class ResetSampleV1(Contract):
    """Versioned source-bound reset values with explicit time and velocities.

    ``ResetSample`` v0 remains the default zero-velocity contract. This value is
    only admitted by an exact RuntimeSession profile that understands its
    source closure and reset ordering.
    """

    schema_version: str
    sample_id: str
    task_artifact_hash: str
    source_id: str
    source_closure_digest: str
    sampler_id: str
    sampler_version: str
    task_seed: int
    init_row_index: int
    init_row_sha256: str
    joint_position: Mapping[str, float]
    joint_velocity: Mapping[str, float]
    sampled_poses_world: Mapping[str, PoseWorld]
    poses_world: Mapping[str, PoseWorld]
    free_joint_velocity: Mapping[str, tuple[float, ...]]
    free_joint_velocity_frame: str
    fixture_pose_world: Mapping[str, PoseWorld]
    simulation_time_s: float
    velocity_policy: str
    control_policy: str
    initialization_order: tuple[str, ...]
    settle_steps: int = 0

    def validate(self):
        if self.schema_version != 'reset-sample-v1':
            raise ValueError('unsupported ResetSampleV1 schema')
        for name in ('task_artifact_hash', 'source_closure_digest', 'init_row_sha256'):
            if type(getattr(self, name)) is not str or not _SHA256.fullmatch(getattr(self, name)):
                raise ValueError(f'{name} must be a lowercase SHA-256')
        for name in ('source_id', 'sampler_id', 'sampler_version'):
            _name(getattr(self, name))
        if (type(self.task_seed) is not int or self.task_seed < 0
                or type(self.init_row_index) is not int or self.init_row_index < 0
                or type(self.settle_steps) is not int or self.settle_steps != 0):
            raise ValueError('ResetSampleV1 seed, row, and settle count are invalid')
        if self.sample_id != 'reset-' + self.identity_hash:
            raise ValueError('ResetSampleV1 sample identity mismatch')
        if not math.isfinite(float(self.simulation_time_s)) or self.simulation_time_s < 0:
            raise ValueError('ResetSampleV1 simulation time must be finite and non-negative')
        if self.velocity_policy != 'named_qvel_and_free_joint_qvel_v1':
            raise ValueError('unsupported ResetSampleV1 velocity policy')
        if self.free_joint_velocity_frame != 'mujoco_world_linear_local_angular_v1':
            raise ValueError('unsupported MuJoCo free-joint qvel frame')
        if self.control_policy not in {
            'named_torque_and_finger_position_by_source_v1',
            'named_mixed_actuator_channels_by_source_v1',
        }:
            raise ValueError('unsupported ResetSampleV1 control policy')
        order = tuple(self.initialization_order)
        legacy_order = (
            'sample_object_properties', 'mj_step1', 'sample_fixtures_and_objects',
            'restore_selected_init_row', 'mj_forward',
        )
        generic_order = (
            'sample_source_properties', 'native_preprocess', 'sample_task_placements',
            'restore_source_bound_state', 'forward_derived_state',
        )
        if order not in {legacy_order, generic_order}:
            raise ValueError('ResetSampleV1 initialization order is unsupported')
        joint_position = dict(self.joint_position)
        joint_velocity = dict(self.joint_velocity)
        sampled_poses = dict(self.sampled_poses_world)
        poses_world = dict(self.poses_world)
        free_velocity = dict(self.free_joint_velocity)
        fixture_pose = dict(self.fixture_pose_world)
        if not joint_position or set(joint_position) != set(joint_velocity):
            raise ValueError('ResetSampleV1 named joint position/velocity sets must match')
        if (not poses_world or set(poses_world) != set(free_velocity)
                or set(sampled_poses) != set(poses_world)):
            raise ValueError('ResetSampleV1 free-body pose/velocity sets must match')
        if set(poses_world) & set(fixture_pose):
            raise ValueError('ResetSampleV1 free-body and fixture roots must be distinct')
        for name in (*joint_position, *poses_world, *fixture_pose):
            _name(name)
        for name in joint_position:
            value = float(joint_position[name])
            velocity = float(joint_velocity[name])
            if not math.isfinite(value) or not math.isfinite(velocity):
                raise ValueError('ResetSampleV1 scalar joint state must be finite')
            joint_position[name] = value
            joint_velocity[name] = velocity
        for name, pose in (*sampled_poses.items(), *poses_world.items(), *fixture_pose.items()):
            if not isinstance(pose, PoseWorld):
                raise TypeError(f'ResetSampleV1 pose for {name!r} must be PoseWorld')
            pose.validate()
        for name, velocity in free_velocity.items():
            values = tuple(float(value) for value in velocity)
            if len(values) != 6 or any(not math.isfinite(value) for value in values):
                raise ValueError(f'ResetSampleV1 free velocity for {name!r} must contain six finite values')
            free_velocity[name] = values
        object.__setattr__(self, 'simulation_time_s', float(self.simulation_time_s))
        object.__setattr__(self, 'joint_position', MappingProxyType(joint_position))
        object.__setattr__(self, 'joint_velocity', MappingProxyType(joint_velocity))
        object.__setattr__(self, 'sampled_poses_world', MappingProxyType(sampled_poses))
        object.__setattr__(self, 'poses_world', MappingProxyType(poses_world))
        object.__setattr__(self, 'free_joint_velocity', MappingProxyType(free_velocity))
        object.__setattr__(self, 'fixture_pose_world', MappingProxyType(fixture_pose))

    @property
    def identity_hash(self) -> str:
        mapping = self.to_mapping()
        del mapping['sample_id']
        return hashlib.sha256(canonical_json(mapping).encode()).hexdigest()

    @classmethod
    def create(cls, **values) -> 'ResetSampleV1':
        annotations = get_type_hints(cls)
        payload = {key: _encode(_decode(annotations[key], value))
                   for key, value in values.items() if key != 'sample_id'}
        digest = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        result = cls.from_mapping({**payload, 'sample_id': 'reset-' + digest})
        result.validate()
        return result


@dataclass(frozen=True)
class ResetPlanV1(Contract):
    """Source-bound public plan for one reset, including bounded diagnostics.

    The plan does not own reset execution. It binds one already validated
    ResetSampleV1 and its declared use to the existing RuntimeSession reset
    owner.
    """

    schema_version: str
    reset_sample: ResetSampleV1
    purpose: str

    def validate(self):
        if self.schema_version != 'reset-plan-v1':
            raise ValueError('unsupported ResetPlanV1 schema')
        if type(self.reset_sample) is not ResetSampleV1:
            raise TypeError('ResetPlanV1 requires the source-bound ResetSampleV1 contract')
        if self.purpose not in {'task_episode', 'diagnostic_contact_endpoint'}:
            raise ValueError('ResetPlanV1 purpose must name a task episode or diagnostic contact endpoint')
        self.reset_sample.validate()

    @property
    def identity_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.to_mapping()).encode()).hexdigest()

    def to_provider_sample(self) -> ResetSampleV1:
        self.validate()
        return self.reset_sample

    def validate_realization_identity(self, realized: 'RealizedInitialState') -> None:
        if not isinstance(realized, RealizedInitialState):
            raise TypeError('ResetPlanV1 realization must be RealizedInitialState')
        if realized.reset_sample_id != self.reset_sample.sample_id:
            raise ValueError('realized state does not belong to this ResetPlanV1')


@dataclass(frozen=True)
class RoleBindingV1(Contract):
    """Immutable Core selection result for one source and canonical Scene."""

    schema_version: str
    task_source_identity_hash: str
    scene_identity_hash: str
    task_seed: int
    selection_policy_id: str
    selection_policy_version: str
    bindings: Mapping[str, str]

    def validate(self):
        _choice(self.schema_version, {'role-binding-v1'}, 'RoleBinding schema')
        if not _SHA256.fullmatch(self.task_source_identity_hash):
            raise ValueError('RoleBinding requires a Task Source identity hash')
        if not _SHA256.fullmatch(self.scene_identity_hash):
            raise ValueError('RoleBinding requires a canonical Scene identity hash')
        if type(self.task_seed) is not int or self.task_seed < 0:
            raise ValueError('RoleBinding task_seed must be a nonnegative integer')
        _name(self.selection_policy_id)
        _name(self.selection_policy_version)
        if len(set(self.bindings.values())) != len(self.bindings):
            raise ValueError('RoleBinding requires exclusive Entity bindings')
        for role_id, entity_id in self.bindings.items():
            _name(role_id)
            _name(entity_id)

    @property
    def identity_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.to_mapping()).encode()).hexdigest()


@dataclass(frozen=True)
class EpisodeResetPlanV1(Contract):
    """Bind a Core Role selection to the existing provider-facing v0 ResetSample."""

    schema_version: str
    role_binding: RoleBindingV1
    reset_sample: ResetSample
    sampling_domain: str

    def validate(self):
        _choice(self.schema_version, {'episode-reset-plan-v1'}, 'episode reset plan schema')
        _choice(self.sampling_domain, {'training', 'feasibility', 'evaluation'}, 'sampling domain')
        if self.role_binding.task_seed != self.reset_sample.task_seed:
            raise ValueError('RoleBinding and ResetSample must use the same task_seed')

    @property
    def identity_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.to_mapping()).encode()).hexdigest()

    def to_provider_sample(self) -> ResetSample:
        """Pass the exact existing v0 sample to RuntimeSession; no provider rewrite."""

        return self.reset_sample

    def validate_realization_identity(self, realized: 'RealizedInitialState') -> None:
        if not isinstance(realized, RealizedInitialState):
            raise TypeError('EpisodeResetPlan realization must be RealizedInitialState')
        if realized.reset_sample_id != self.reset_sample.sample_id:
            raise ValueError('realized state does not belong to this EpisodeResetPlanV1')


@dataclass(frozen=True)
class RealizedInitialState(Contract):
    schema_version: str
    reset_sample_id: str
    provider_name: str
    measured_state: CanonicalStateView
    actual_settle_steps: int

    def validate(self):
        if self.schema_version != 'realized-initial-state-v0' or self.actual_settle_steps < 0:
            raise ValueError('invalid realized initial state')
        _name(self.provider_name)
        _name(self.reset_sample_id)


@dataclass(frozen=True)
class ResetReadbackV1(Contract):
    """Public measured reset receipt for versioned time/velocity reset plans."""

    schema_version: str
    source_id: str
    source_closure_digest: str
    provider_materialization_id: str
    episode_id: str
    reset_sample_id: str
    simulation_time_s: float
    joint_position: Mapping[str, float]
    joint_velocity: Mapping[str, float]
    poses_world: Mapping[str, PoseWorld]
    free_joint_velocity: Mapping[str, tuple[float, ...]]
    free_joint_velocity_frame: str
    fixture_pose_world: Mapping[str, PoseWorld]
    native_step_count: int
    preprocess_call_count: int
    forward_call_count: int

    def validate(self):
        if self.schema_version != 'runtime-reset-readback-v1':
            raise ValueError('unsupported Runtime ResetReadback schema')
        _name(self.source_id)
        for name in ('source_closure_digest',):
            if type(getattr(self, name)) is not str or not _SHA256.fullmatch(getattr(self, name)):
                raise ValueError(f'{name} must be a lowercase SHA-256')
        for name in ('provider_materialization_id', 'episode_id', 'reset_sample_id'):
            _name(getattr(self, name))
        if (not math.isfinite(float(self.simulation_time_s)) or self.simulation_time_s < 0
                or type(self.native_step_count) is not int or self.native_step_count != 0
                or self.free_joint_velocity_frame != 'mujoco_world_linear_local_angular_v1'
                or type(self.preprocess_call_count) is not int or self.preprocess_call_count != 1
                or type(self.forward_call_count) is not int or self.forward_call_count != 1):
            raise ValueError('Runtime ResetReadback clock or reset counters are invalid')
        if (set(self.joint_position) != set(self.joint_velocity)
                or set(self.poses_world) != set(self.free_joint_velocity)):
            raise ValueError('Runtime ResetReadback state-name sets are inconsistent')
        for mapping in (self.joint_position, self.joint_velocity):
            if any(not math.isfinite(float(value)) for value in mapping.values()):
                raise ValueError('Runtime ResetReadback scalar state must be finite')
        for mapping in (self.poses_world, self.fixture_pose_world):
            for pose in mapping.values():
                if not isinstance(pose, PoseWorld):
                    raise TypeError('Runtime ResetReadback poses require PoseWorld')
                pose.validate()
        for velocity in self.free_joint_velocity.values():
            if len(velocity) != 6 or any(not math.isfinite(float(value)) for value in velocity):
                raise ValueError('Runtime ResetReadback free velocity requires six finite values')
