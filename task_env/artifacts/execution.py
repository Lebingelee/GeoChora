"""Provider-neutral P1.2 execution values, separate from TaskArtifact identity."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json

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
