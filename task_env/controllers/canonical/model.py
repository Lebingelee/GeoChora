"""Provider-neutral, snapshot-only Controller model contract and bounded model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...artifacts.contracts import Contract, _SHA256, _choice, _name
from ...artifacts.state import CanonicalStateViewV1, CanonicalStateViewV2, StateBoundaryIdentity, StateSampleClock
from .contracts import digest


@dataclass(frozen=True)
class ControllerModelRequirementV1(Contract):
    schema_version: str
    profile_id: str
    library_id: str
    library_version: str
    dependency_identity: str
    source_id: str
    source_closure_sha256: str
    joint_names: tuple[str, ...]
    joint_units: tuple[str, ...]
    output_quantity: str
    output_units: tuple[str, ...]
    output_frame: str
    clock_domain: str
    cadence_s: float
    max_age_s: float
    computation: str
    resource_owner: str
    internal_state_owner: str
    requiredness: str

    def validate(self):
        _choice(self.schema_version, {'controller-model-requirement-v1'}, 'model requirement schema')
        for item in (self.profile_id, self.library_id, self.library_version, self.dependency_identity,
                     self.source_id, self.output_frame, self.resource_owner, self.internal_state_owner):
            _name(item)
        if not _SHA256.fullmatch(self.source_closure_sha256):
            raise ValueError('model source closure must be SHA-256')
        if not self.joint_names or len(set(self.joint_names)) != len(self.joint_names):
            raise ValueError('model needs unique ordered joint names')
        for item in self.joint_names:
            _name(item)
        if len(self.joint_units) != len(self.joint_names) or len(self.output_units) != len(self.joint_names):
            raise ValueError('model units must cover the ordered joints')
        if any(unit not in {'rad', 'm'} for unit in self.joint_units):
            raise ValueError('model input units are unsupported')
        if any(unit not in {'N*m', 'N'} for unit in self.output_units):
            raise ValueError('model output units are unsupported')
        _choice(self.output_quantity, {'joint_bias', 'operational_space_dynamics'}, 'model output quantity')
        _choice(self.clock_domain, {'evaluation_boundary'}, 'model clock')
        _choice(self.computation, {'pure_no_physics_step'}, 'model computation')
        _choice(self.requiredness, {'required', 'optional'}, 'model requiredness')
        if self.cadence_s <= 0 or self.max_age_s < 0:
            raise ValueError('model cadence and max age are invalid')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class ModelOutputV1(Contract):
    schema_version: str
    requirement_sha256: str
    model_sha256: str
    source_closure_sha256: str
    boundary: StateBoundaryIdentity
    clock: StateSampleClock
    joint_names: tuple[str, ...]
    values: tuple[float, ...]
    units: tuple[str, ...]
    frame: str

    def validate(self):
        _choice(self.schema_version, {'controller-model-output-v1'}, 'model output schema')
        for value in (self.requirement_sha256, self.model_sha256, self.source_closure_sha256):
            if not _SHA256.fullmatch(value):
                raise ValueError('model output requires SHA-256 identities')
        if not self.joint_names or len(self.values) != len(self.joint_names) or len(self.units) != len(self.values):
            raise ValueError('model output names, values, and units must align')
        if self.clock.clock_domain != 'evaluation_boundary' or self.clock.sample_index != self.boundary.control_step:
            raise ValueError('model output clock differs from boundary')
        _name(self.frame)


class JointBiasModel(Protocol):
    @property
    def requirement(self) -> ControllerModelRequirementV1: ...
    @property
    def identity_hash(self) -> str: ...
    def evaluate(self, state: CanonicalStateViewV1 | CanonicalStateViewV2) -> ModelOutputV1: ...


@dataclass(frozen=True)
class AffineJointBiasModelV1(Contract):
    """Explicit per-joint affine model; coefficients are authored, not measured.

    This bounded pure model is replaceable and makes no claim to be a rigid-body
    dynamics model or to reproduce a provider's bias force.
    """
    schema_version: str
    requirement: ControllerModelRequirementV1
    offsets: tuple[float, ...]
    position_coefficients: tuple[float, ...]
    velocity_coefficients: tuple[float, ...]

    def validate(self):
        _choice(self.schema_version, {'affine-joint-bias-model-v1'}, 'model schema')
        n = len(self.requirement.joint_names)
        if any(len(values) != n for values in (self.offsets, self.position_coefficients, self.velocity_coefficients)):
            raise ValueError('affine model coefficients must match ordered joints')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())

    def evaluate(self, state):
        if type(state) not in (CanonicalStateViewV1, CanonicalStateViewV2):
            raise TypeError('model requires an immutable canonical state snapshot')
        joints = {f'{x.entity_id}/{x.joint_id}': x for x in state.joints}
        values = []
        for index, name in enumerate(self.requirement.joint_names):
            joint = joints.get(name)
            if joint is None or len(joint.position) != 1 or len(joint.velocity) != 1:
                raise ValueError(f'required named scalar joint state unavailable: {name}')
            expected_kind = 'revolute' if self.requirement.joint_units[index] == 'rad' else 'prismatic'
            if joint.kind != expected_kind:
                raise ValueError(f'model input unit differs from joint kind: {name}')
            values.append(self.offsets[index] + self.position_coefficients[index]*joint.position[0]
                          + self.velocity_coefficients[index]*joint.velocity[0])
        return ModelOutputV1('controller-model-output-v1', self.requirement.identity_hash,
            self.identity_hash, self.requirement.source_closure_sha256, state.boundary, state.sample_clock,
            self.requirement.joint_names, tuple(values), self.requirement.output_units,
            self.requirement.output_frame)
