"""Versioned canonical state values and provider-neutral state requirements.

These contracts live beside TaskArtifact contracts but do not enter frozen
TaskArtifact v0 identity.  They describe values/read views only; providers
remain the owners of native state and lifetime enforcement.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math

from .contracts import (
    CanonicalStateView,
    Contract,
    FrameReference,
    JointDefinition,
    PoseWorld,
    SceneDefinition,
    _JOINT_COORDINATES,
    _SHA256,
    _choice,
    _name,
)


_STATE_FIELD_UNITS = {
    "joint_position": "joint-definition",
    "joint_velocity": "joint-definition",
    "frame_pose_world": "meter+quaternion_wxyz",
    "contact_force": "newton",
    "contact_impulse": "newton_second",
    # Generic actuator output units belong to the provider. An audited
    # transmission may request a specific unit (the bounded Panda tendon
    # contract below names N explicitly).
    "actuator_force": "provider-native-actuator-output",
}
_ACTUATOR_FORCE_UNITS = {
    "provider-native-actuator-output",
    "newton",  # accepted legacy requirement spelling
    "N",       # explicit bounded Panda tendon unit
}
_STATE_SUBJECTS = {
    "joint_position": "joint",
    "joint_velocity": "joint",
    "frame_pose_world": "frame",
    "contact_force": "entity",
    "contact_impulse": "entity",
    "actuator_force": "actuator",
}
_STATE_FIELD_CAPABILITIES = {
    "joint_position": "joint_state_query",
    "joint_velocity": "joint_state_query",
    "frame_pose_world": "frame_pose_query",
    "contact_force": "contact_detection",
    "contact_impulse": "contact_impulse",
    # This is a requirement identifier only. Current v0 provider manifests do
    # not claim it, so admission remains fail-closed until a manifest can.
    "actuator_force": "actuator_force_query",
}


def _near_one_ulp(left: float, right: float) -> bool:
    return abs(left - right) <= max(math.ulp(left), math.ulp(right))


def _state_field_key(field_name, subject_kind, entity_id, subject_id):
    return field_name, subject_kind, entity_id, subject_id


def _validate_state_target(field_name, subject_kind, entity_id, subject_id):
    if field_name not in _STATE_FIELD_UNITS:
        raise ValueError(f"unsupported state field: {field_name!r}")
    if subject_kind != _STATE_SUBJECTS[field_name]:
        raise ValueError(f"state field {field_name!r} requires subject kind {_STATE_SUBJECTS[field_name]!r}")
    _name(entity_id)
    _name(subject_id)


def _validate_state_unit(field_name, unit):
    if field_name == "actuator_force":
        if unit not in _ACTUATOR_FORCE_UNITS:
            raise ValueError("actuator-force unit must be provider-native or explicitly declared")
    elif unit != _STATE_FIELD_UNITS[field_name]:
        raise ValueError(
            f"state field {field_name!r} requires unit contract {_STATE_FIELD_UNITS[field_name]!r}"
        )


@dataclass(frozen=True)
class StateBoundaryIdentity(Contract):
    """Identity for one visible state publication, including same-step writes."""

    schema_version: str
    episode_id: str
    reset_sample_id: str
    scene_identity_hash: str
    scene_instance_id: str
    provider_materialization_id: str
    control_step: int
    state_revision: int

    def validate(self):
        _choice(self.schema_version, {"state-boundary-identity-v1"}, "state boundary schema")
        for value in (self.episode_id, self.reset_sample_id, self.scene_instance_id,
                      self.provider_materialization_id):
            _name(value)
        if not self.reset_sample_id.startswith("reset-") or not _SHA256.fullmatch(self.reset_sample_id[6:]):
            raise ValueError("state boundary requires a ResetSample identity")
        if not _SHA256.fullmatch(self.scene_identity_hash):
            raise ValueError("state boundary requires a canonical scene SHA-256")
        if self.control_step < 0 or self.state_revision < 0:
            raise ValueError("negative state boundary step/revision")

    @property
    def boundary_id(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return "state-boundary-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StateSampleClock(Contract):
    """A timestamp in an explicitly named evaluation or native clock domain."""

    schema_version: str
    clock_domain: str
    sample_index: int
    simulation_time_s: float

    def validate(self):
        _choice(self.schema_version, {"state-sample-clock-v1"}, "state sample clock schema")
        _choice(self.clock_domain, {"evaluation_boundary", "native_step"}, "state clock domain")
        if self.sample_index < 0 or self.simulation_time_s < 0:
            raise ValueError("negative state sample index/time")


@dataclass(frozen=True)
class TypedJointStateValue(Contract):
    """One entity-qualified joint value using the layout declared by A02."""

    schema_version: str
    entity_id: str
    joint_id: str
    kind: str
    position_representation: str
    position: tuple[float, ...]
    velocity_representation: str
    velocity: tuple[float, ...]
    velocity_expressed_in: FrameReference | None = None
    velocity_reference_point: FrameReference | None = None

    def validate(self):
        _choice(self.schema_version, {"typed-joint-state-v1"}, "typed joint state schema")
        _name(self.entity_id)
        _name(self.joint_id)
        if self.kind not in _JOINT_COORDINATES:
            raise ValueError(f"unsupported joint kind: {self.kind!r}")
        _, position_repr, velocity_repr, position_size, velocity_size = _JOINT_COORDINATES[self.kind]
        if self.kind == "fixed":
            raise ValueError("fixed joints do not publish dynamic position/velocity state")
        if (self.position_representation, self.velocity_representation) != (position_repr, velocity_repr):
            raise ValueError("typed joint representations disagree with the A02 joint layout")
        if len(self.position) != position_size or len(self.velocity) != velocity_size:
            raise ValueError("typed joint position/velocity dimensions disagree with the A02 joint layout")
        if self.kind in {"spherical", "floating"}:
            if self.velocity_expressed_in is None:
                raise ValueError("multi-DOF angular velocity requires an explicit expression frame")
            if self.velocity_expressed_in.entity_id != self.entity_id:
                raise ValueError("joint velocity expression frame must belong to the joint entity")
        elif self.velocity_expressed_in is not None:
            raise ValueError("scalar joint velocity uses its declared joint axis, not an expression frame")
        if self.kind == "floating":
            if self.velocity_reference_point is None:
                raise ValueError("floating-joint twist requires an explicit reference point")
            if self.velocity_reference_point.entity_id != self.entity_id:
                raise ValueError("joint velocity reference point must belong to the joint entity")
        elif self.velocity_reference_point is not None:
            raise ValueError("only a floating-joint twist has a spatial reference point")

    def validate_against(self, definition: JointDefinition) -> None:
        if not isinstance(definition, JointDefinition):
            raise TypeError("typed joint state requires an A02 JointDefinition")
        if (self.entity_id, self.joint_id, self.kind, self.position_representation,
                self.velocity_representation, len(self.position), len(self.velocity)) != (
                definition.parent_frame.entity_id, definition.joint_id, definition.kind,
                definition.position_representation, definition.velocity_representation,
                definition.position_size, definition.velocity_size):
            raise ValueError("typed joint state does not match its A02 JointDefinition")


@dataclass(frozen=True)
class TypedFrameStateValue(Contract):
    """A world pose for one declared Entity-qualified frame."""

    schema_version: str
    frame: FrameReference
    pose_world: PoseWorld

    def validate(self):
        _choice(self.schema_version, {"typed-frame-state-v1"}, "typed frame state schema")


@dataclass(frozen=True)
class StateFieldRequirement(Contract):
    """One consumer's typed state requirement; unavailable is never numeric zero."""

    schema_version: str
    field_name: str
    subject_kind: str
    entity_id: str
    subject_id: str
    requiredness: str
    sample_domain: str
    unit: str
    required_capability: str
    reference_frame: FrameReference | None = None

    def validate(self):
        _choice(self.schema_version, {"state-field-requirement-v1"}, "state requirement schema")
        _validate_state_target(self.field_name, self.subject_kind, self.entity_id, self.subject_id)
        _choice(self.requiredness, {"required", "optional"}, "state requirement requiredness")
        _choice(self.sample_domain, {"evaluation_boundary", "native_step_interval"}, "state requirement sample domain")
        if (self.sample_domain == "native_step_interval"
                and self.field_name not in {"contact_force", "contact_impulse", "actuator_force"}):
            raise ValueError(f"native interval requirement is not supported for {self.field_name!r}")
        _validate_state_unit(self.field_name, self.unit)
        _name(self.required_capability)
        if self.required_capability != _STATE_FIELD_CAPABILITIES[self.field_name]:
            raise ValueError(
                f"state field {self.field_name!r} requires capability identifier "
                f"{_STATE_FIELD_CAPABILITIES[self.field_name]!r}"
            )
        if self.field_name in {"contact_force", "contact_impulse"}:
            if self.reference_frame is None or self.reference_frame.entity_id != self.entity_id:
                raise ValueError("contact state requirements require an Entity-local expression frame")
            expected_capability = (
                "contact_detection" if self.field_name == "contact_force" else "contact_impulse"
            )
            if self.required_capability != expected_capability:
                raise ValueError(
                    f"state field {self.field_name!r} requires capability {expected_capability!r}"
                )
        elif self.reference_frame is not None:
            raise ValueError("reference_frame is only valid for contact vector requirements")

    @property
    def field_key(self):
        return _state_field_key(self.field_name, self.subject_kind, self.entity_id, self.subject_id)


@dataclass(frozen=True)
class StateRequirements(Contract):
    """Requirements owned by one task, controller, observation, or renderer consumer."""

    schema_version: str
    consumer_kind: str
    consumer_id: str
    requirements: tuple[StateFieldRequirement, ...]

    def validate(self):
        _choice(self.schema_version, {"state-requirements-v1"}, "state requirements collection schema")
        _choice(self.consumer_kind, {"task", "controller", "observation", "renderer"}, "state consumer kind")
        _name(self.consumer_id)
        keys = tuple((item.field_key, item.sample_domain) for item in self.requirements)
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate state field requirement")
        object.__setattr__(self, "requirements", tuple(sorted(
            self.requirements, key=lambda item: (item.sample_domain, item.field_key)
        )))


@dataclass(frozen=True)
class UnavailableStateValue(Contract):
    """Explicitly unavailable field marker; it carries no fabricated value."""

    schema_version: str
    field_name: str
    subject_kind: str
    entity_id: str
    subject_id: str
    sample_domain: str
    reason: str

    def validate(self):
        _choice(self.schema_version, {"unavailable-state-value-v1"}, "unavailable state schema")
        _validate_state_target(self.field_name, self.subject_kind, self.entity_id, self.subject_id)
        _choice(self.sample_domain, {"evaluation_boundary", "native_step_interval"}, "unavailable state sample domain")
        if not self.reason.strip():
            raise ValueError("unavailable state value requires a reason")

    @property
    def field_key(self):
        return _state_field_key(self.field_name, self.subject_kind, self.entity_id, self.subject_id)


@dataclass(frozen=True)
class CanonicalStateViewV1(Contract):
    """Typed immutable state publication; Entity views are projections of these tuples."""

    schema_version: str
    convention: str
    boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    joints: tuple[TypedJointStateValue, ...]
    frames: tuple[TypedFrameStateValue, ...]
    unavailable: tuple[UnavailableStateValue, ...] = ()

    def validate(self):
        _choice(self.schema_version, {"canonical-state-v1"}, "state schema")
        _choice(self.convention, {"SI_right_handed_z_up_wxyz"}, "state convention")
        if self.sample_clock.clock_domain != "evaluation_boundary":
            raise ValueError("canonical state view must name an evaluation boundary clock")
        if self.sample_clock.sample_index != self.boundary.control_step:
            raise ValueError("state sample and control boundary index disagree")
        joint_keys = tuple((value.entity_id, value.joint_id) for value in self.joints)
        frame_keys = tuple((value.frame.entity_id, value.frame.frame_id) for value in self.frames)
        if len(joint_keys) != len(set(joint_keys)) or len(frame_keys) != len(set(frame_keys)):
            raise ValueError("duplicate entity-qualified state value")
        unavailable_keys = tuple((value.field_key, value.sample_domain) for value in self.unavailable)
        if len(unavailable_keys) != len(set(unavailable_keys)):
            raise ValueError("duplicate unavailable state value")
        available = {
            (("joint_position", "joint", entity, joint), "evaluation_boundary")
            for entity, joint in joint_keys
        } | {
            (("joint_velocity", "joint", entity, joint), "evaluation_boundary")
            for entity, joint in joint_keys
        } | {
            (("frame_pose_world", "frame", entity, frame), "evaluation_boundary")
            for entity, frame in frame_keys
        }
        if available & set(unavailable_keys):
            raise ValueError("state value cannot be both available and unavailable")
        object.__setattr__(self, "joints", tuple(sorted(self.joints, key=lambda item: (item.entity_id, item.joint_id))))
        object.__setattr__(self, "frames", tuple(sorted(self.frames, key=lambda item: (item.frame.entity_id, item.frame.frame_id))))
        object.__setattr__(self, "unavailable", tuple(sorted(
            self.unavailable, key=lambda item: (item.sample_domain, item.field_key)
        )))

    def joints_for_entity(self, entity_id: str) -> tuple[TypedJointStateValue, ...]:
        """Return a read-only projection over the one stored joint tuple."""
        _name(entity_id)
        return tuple(value for value in self.joints if value.entity_id == entity_id)

    def frames_for_entity(self, entity_id: str) -> tuple[TypedFrameStateValue, ...]:
        """Return a read-only projection over the one stored frame tuple."""
        _name(entity_id)
        return tuple(value for value in self.frames if value.frame.entity_id == entity_id)

    def validate_against_scene(self, scene: SceneDefinition) -> None:
        """Check entity-qualified state bindings against the exact A02 scene."""
        if not isinstance(scene, SceneDefinition):
            raise TypeError("canonical state validation requires SceneDefinition")
        if scene.schema_version not in {"scene-definition-v2", "scene-definition-v3"}:
            raise ValueError("typed canonical state requires scene-definition-v2/v3")
        if self.boundary.scene_identity_hash != scene.identity_hash:
            raise ValueError("canonical state scene identity mismatch")
        joint_definitions = {
            (articulation.entity_id, joint.joint_id): joint
            for articulation in (scene.articulations or ())
            for joint in articulation.joints
        }
        frame_references = {(item.entity_id, item.frame_id) for item in (scene.frames or ())}
        entity_ids = {item.entity_id for item in scene.entities}
        actuator_references = {
            (item.entity_id, item.actuator_id) for item in (scene.actuator_resources or ())
        }
        for value in self.joints:
            key = (value.entity_id, value.joint_id)
            definition = joint_definitions.get(key)
            if definition is None:
                raise ValueError(f"state references undeclared scene joint: {key}")
            value.validate_against(definition)
            for reference in (value.velocity_expressed_in, value.velocity_reference_point):
                if reference is not None and (reference.entity_id, reference.frame_id) not in frame_references:
                    raise ValueError(f"joint state references undeclared velocity frame: {reference}")
        for value in self.frames:
            reference = value.frame
            if (reference.entity_id, reference.frame_id) not in frame_references:
                raise ValueError(f"state references undeclared scene frame: {reference}")
        for value in self.unavailable:
            if value.subject_kind == "entity" and value.entity_id not in entity_ids:
                raise ValueError(f"unavailable state references undeclared entity: {value.entity_id}")
            if value.subject_kind == "joint" and (value.entity_id, value.subject_id) not in joint_definitions:
                raise ValueError(f"unavailable state references undeclared joint: {value.subject_id}")
            if value.subject_kind == "frame" and (value.entity_id, value.subject_id) not in frame_references:
                raise ValueError(f"unavailable state references undeclared frame: {value.subject_id}")
            if value.subject_kind == "actuator" and (value.entity_id, value.subject_id) not in actuator_references:
                raise ValueError(f"unavailable state references undeclared actuator: {value.subject_id}")

    def validate_requirements(self, requirements: StateRequirements) -> None:
        if not isinstance(requirements, StateRequirements):
            raise TypeError("state requirements must be StateRequirements")
        unavailable = {(item.field_key, item.sample_domain): item for item in self.unavailable}
        available = {
            (("joint_position", "joint", value.entity_id, value.joint_id), "evaluation_boundary")
            for value in self.joints
        } | {
            (("joint_velocity", "joint", value.entity_id, value.joint_id), "evaluation_boundary")
            for value in self.joints
        } | {
            (("frame_pose_world", "frame", value.frame.entity_id, value.frame.frame_id), "evaluation_boundary")
            for value in self.frames
        }
        for item in requirements.requirements:
            key = (item.field_key, item.sample_domain)
            if item.sample_domain != "evaluation_boundary":
                raise ValueError("native interval requirements need NativeIntervalEvidence, not a boundary snapshot")
            if key in available:
                continue
            if key not in unavailable:
                raise ValueError(f"state field omitted without unavailable evidence: {item.field_key}")
            if item.requiredness == "required":
                raise ValueError(f"required state field unavailable: {item.field_key}: {unavailable[key].reason}")

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TypedActuatorForceStateValue(Contract):
    """One signed actuator output with source, phase and boundary provenance.

    The unit is explicit. Generic actuator output retains a provider-owned
    unit; N is used only when an audited source/transmission names it.
    Invalid samples carry no numeric value and fail required consumers.
    """

    schema_version: str
    entity_id: str
    actuator_id: str
    unit: str
    signed_value: float | None
    actuator_control_value: float | None
    valid: bool
    invalid_reason: str | None
    source_generation: int
    sample_sequence: int
    source_state_revision: int
    configuration_revision: int
    source_closure_digest: str
    provider_materialization_id: str
    sample_phase: str
    native_step_index: int
    native_step_dt_s: float
    native_sample_time_s: float
    episode_id: str
    reset_sample_id: str
    evaluation_boundary_id: str
    evaluation_control_step: int
    evaluation_simulation_time_s: float

    def validate(self):
        _choice(self.schema_version, {"typed-actuator-force-state-v1"}, "typed actuator force schema")
        _name(self.entity_id)
        _name(self.actuator_id)
        _validate_state_unit("actuator_force", self.unit)
        if self.sample_phase not in {
            "uninitialized", "state_restore_forward", "reset_forward",
            "native_step_pre_integration",
        }:
            raise ValueError(f"unsupported actuator-force sample phase: {self.sample_phase!r}")
        if type(self.valid) is not bool:
            raise TypeError("actuator-force validity must be boolean")
        for name in (
            "source_generation", "sample_sequence", "source_state_revision",
            "configuration_revision", "native_step_index", "evaluation_control_step",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not _SHA256.fullmatch(self.source_closure_digest):
            raise ValueError("actuator-force value requires its source closure SHA-256")
        _name(self.provider_materialization_id)
        for name in ("native_step_dt_s", "native_sample_time_s", "evaluation_simulation_time_s"):
            value = float(getattr(self, name))
            if (not math.isfinite(value) or value < 0.0
                    or (name == "native_step_dt_s" and value <= 0.0)):
                raise ValueError(f"{name} must be finite and non-negative (positive for dt)")
            object.__setattr__(self, name, value)
        _name(self.episode_id)
        _name(self.reset_sample_id)
        if not self.reset_sample_id.startswith("reset-") or not _SHA256.fullmatch(self.reset_sample_id[6:]):
            raise ValueError("actuator-force value requires a ResetSample identity")
        if not self.evaluation_boundary_id.startswith("state-boundary-"):
            raise ValueError("actuator-force value requires a state boundary identity")
        if self.valid:
            if self.sample_sequence == 0:
                raise ValueError("valid actuator-force sample requires a published sample sequence")
            if self.signed_value is None or self.actuator_control_value is None:
                raise ValueError("valid actuator-force sample requires raw force and actuator input")
            force = float(self.signed_value)
            control = float(self.actuator_control_value)
            if not math.isfinite(force) or not math.isfinite(control):
                raise ValueError("valid actuator-force sample values must be finite")
            object.__setattr__(self, "signed_value", force)
            object.__setattr__(self, "actuator_control_value", control)
            if self.invalid_reason:
                raise ValueError("valid actuator-force sample cannot have an invalid reason")
        else:
            if self.signed_value is not None or self.actuator_control_value is not None:
                raise ValueError("invalid actuator-force sample cannot carry numeric values")
            if not self.invalid_reason or not self.invalid_reason.strip():
                raise ValueError("invalid actuator-force sample requires a reason")

    @property
    def field_key(self):
        return _state_field_key("actuator_force", "actuator", self.entity_id, self.actuator_id)

    def validate_against_boundary(
        self, boundary: StateBoundaryIdentity, sample_clock: StateSampleClock,
        *, require_supported_phase: bool = True,
    ) -> None:
        if not isinstance(boundary, StateBoundaryIdentity) or not isinstance(sample_clock, StateSampleClock):
            raise TypeError("typed actuator force requires state boundary and sample clock")
        if (self.episode_id, self.reset_sample_id, self.provider_materialization_id,
                self.evaluation_boundary_id,
                self.evaluation_control_step, self.evaluation_simulation_time_s) != (
                boundary.episode_id, boundary.reset_sample_id,
                boundary.provider_materialization_id, boundary.boundary_id,
                boundary.control_step, sample_clock.simulation_time_s):
            raise ValueError("actuator-force sample identity does not match its typed state boundary")
        if (sample_clock.clock_domain != "evaluation_boundary"
                or sample_clock.sample_index != self.evaluation_control_step):
            raise ValueError("actuator-force evaluation clock is not the publication boundary")
        if not self.valid:
            return
        native_ratio = sample_clock.simulation_time_s / self.native_step_dt_s
        native_index = round(native_ratio)
        if abs(native_ratio - native_index) > 1.0e-7:
            raise ValueError("actuator-force evaluation boundary is not on a native-step clock")
        if self.sample_phase == "reset_forward":
            if (self.evaluation_control_step != 0 or native_index != 0
                    or self.native_step_index != 0 or self.native_sample_time_s != 0.0
                    or sample_clock.simulation_time_s != 0.0):
                raise ValueError("reset-forward force must describe the current zero-time boundary")
        elif self.sample_phase == "native_step_pre_integration":
            if self.evaluation_control_step < 1 or self.native_step_index != native_index:
                raise ValueError("completed-step force index differs from its evaluation boundary")
            expected_sample_time = (self.native_step_index - 1) * self.native_step_dt_s
            if not _near_one_ulp(self.native_sample_time_s, expected_sample_time):
                raise ValueError("pre-integration force sample time differs from its native index")
        elif require_supported_phase:
            raise ValueError("required actuator-force consumer does not support this sample phase")


@dataclass(frozen=True)
class CanonicalStateViewV2(Contract):
    """Canonical state v2 adds typed raw actuator output without changing v1."""

    schema_version: str
    convention: str
    boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    joints: tuple[TypedJointStateValue, ...]
    frames: tuple[TypedFrameStateValue, ...]
    actuator_forces: tuple[TypedActuatorForceStateValue, ...]
    unavailable: tuple[UnavailableStateValue, ...] = ()

    def validate(self):
        _choice(self.schema_version, {"canonical-state-v2"}, "state schema")
        _choice(self.convention, {"SI_right_handed_z_up_wxyz"}, "state convention")
        if self.sample_clock.clock_domain != "evaluation_boundary":
            raise ValueError("canonical state view must name an evaluation boundary clock")
        if self.sample_clock.sample_index != self.boundary.control_step:
            raise ValueError("state sample and control boundary index disagree")
        joint_keys = tuple((value.entity_id, value.joint_id) for value in self.joints)
        frame_keys = tuple((value.frame.entity_id, value.frame.frame_id) for value in self.frames)
        force_keys = tuple((value.entity_id, value.actuator_id) for value in self.actuator_forces)
        if (len(joint_keys) != len(set(joint_keys)) or len(frame_keys) != len(set(frame_keys))
                or len(force_keys) != len(set(force_keys))):
            raise ValueError("duplicate entity-qualified state value")
        unavailable_keys = tuple((value.field_key, value.sample_domain) for value in self.unavailable)
        if len(unavailable_keys) != len(set(unavailable_keys)):
            raise ValueError("duplicate unavailable state value")
        available = {
            (("joint_position", "joint", entity, joint), "evaluation_boundary")
            for entity, joint in joint_keys
        } | {
            (("joint_velocity", "joint", entity, joint), "evaluation_boundary")
            for entity, joint in joint_keys
        } | {
            (("frame_pose_world", "frame", entity, frame), "evaluation_boundary")
            for entity, frame in frame_keys
        } | {
            (("actuator_force", "actuator", entity, actuator), "evaluation_boundary")
            for entity, actuator in force_keys
        }
        if available & set(unavailable_keys):
            raise ValueError("state value cannot be both available and unavailable")
        for value in self.actuator_forces:
            value.validate_against_boundary(
                self.boundary, self.sample_clock, require_supported_phase=False,
            )
        object.__setattr__(self, "joints", tuple(sorted(
            self.joints, key=lambda item: (item.entity_id, item.joint_id),
        )))
        object.__setattr__(self, "frames", tuple(sorted(
            self.frames, key=lambda item: (item.frame.entity_id, item.frame.frame_id),
        )))
        object.__setattr__(self, "actuator_forces", tuple(sorted(
            self.actuator_forces, key=lambda item: (item.entity_id, item.actuator_id),
        )))
        object.__setattr__(self, "unavailable", tuple(sorted(
            self.unavailable, key=lambda item: (item.sample_domain, item.field_key),
        )))

    def joints_for_entity(self, entity_id: str) -> tuple[TypedJointStateValue, ...]:
        _name(entity_id)
        return tuple(value for value in self.joints if value.entity_id == entity_id)

    def frames_for_entity(self, entity_id: str) -> tuple[TypedFrameStateValue, ...]:
        _name(entity_id)
        return tuple(value for value in self.frames if value.frame.entity_id == entity_id)

    def actuator_forces_for_entity(self, entity_id: str) -> tuple[TypedActuatorForceStateValue, ...]:
        _name(entity_id)
        return tuple(value for value in self.actuator_forces if value.entity_id == entity_id)

    def validate_against_scene(self, scene: SceneDefinition) -> None:
        base = CanonicalStateViewV1(
            "canonical-state-v1", self.convention, self.boundary, self.sample_clock,
            self.joints, self.frames, self.unavailable,
        )
        base.validate_against_scene(scene)
        actuator_references = {
            (item.entity_id, item.actuator_id) for item in (scene.actuator_resources or ())
        }
        for value in self.actuator_forces:
            if (value.entity_id, value.actuator_id) not in actuator_references:
                raise ValueError(
                    "typed actuator-force value references an undeclared Scene actuator: "
                    f"{(value.entity_id, value.actuator_id)}"
                )

    def validate_requirements(self, requirements: StateRequirements) -> None:
        if not isinstance(requirements, StateRequirements):
            raise TypeError("state requirements must be StateRequirements")
        unavailable = {(item.field_key, item.sample_domain): item for item in self.unavailable}
        available = {
            (("joint_position", "joint", value.entity_id, value.joint_id), "evaluation_boundary")
            for value in self.joints
        } | {
            (("joint_velocity", "joint", value.entity_id, value.joint_id), "evaluation_boundary")
            for value in self.joints
        } | {
            (("frame_pose_world", "frame", value.frame.entity_id, value.frame.frame_id), "evaluation_boundary")
            for value in self.frames
        }
        force_values = {(value.field_key, "evaluation_boundary"): value for value in self.actuator_forces}
        available.update(force_values)
        for requirement in requirements.requirements:
            if requirement.sample_domain != "evaluation_boundary":
                raise ValueError("native interval requirements need NativeIntervalEvidence, not a boundary snapshot")
            key = (requirement.field_key, requirement.sample_domain)
            if key in available:
                force = force_values.get(key)
                if force is not None:
                    if force.unit != requirement.unit:
                        raise ValueError(f"typed actuator-force unit disagrees with requirement: {key}")
                    force.validate_against_boundary(
                        self.boundary, self.sample_clock,
                        require_supported_phase=requirement.requiredness == "required",
                    )
                    if not force.valid and requirement.requiredness == "required":
                        raise ValueError(
                            f"required state field invalid: {key}: {force.invalid_reason}"
                        )
                continue
            marker = unavailable.get(key)
            if marker is None:
                raise ValueError(f"state field omitted without unavailable evidence: {requirement.field_key}")
            if requirement.requiredness == "required":
                raise ValueError(
                    f"required state field unavailable: {requirement.field_key}: {marker.reason}"
                )

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NativeSignalValue(Contract):
    """One typed signal measured over a native physics-step interval."""

    schema_version: str
    field_name: str
    subject_kind: str
    entity_id: str
    subject_id: str
    values: tuple[float, ...]
    unit: str
    reference_frame: FrameReference | None = None

    def validate(self):
        _choice(self.schema_version, {"native-signal-value-v1"}, "native signal schema")
        _validate_state_target(self.field_name, self.subject_kind, self.entity_id, self.subject_id)
        if self.field_name in {"joint_position", "joint_velocity", "frame_pose_world"}:
            raise ValueError("native interval evidence requires interval-capable physical signal fields")
        _validate_state_unit(self.field_name, self.unit)
        if not self.values:
            raise ValueError("native signal value cannot be empty")
        if self.field_name in {"contact_force", "contact_impulse"}:
            if self.reference_frame is None or self.reference_frame.entity_id != self.entity_id:
                raise ValueError("contact signal requires an Entity-local expression frame")
            if len(self.values) != 3:
                raise ValueError("contact force/impulse signal must be a 3D vector")
        elif self.reference_frame is not None:
            raise ValueError("reference_frame is only valid for contact vector signals")
        elif self.field_name == "actuator_force" and len(self.values) != 1:
            raise ValueError("actuator force signal must be scalar")

    @property
    def field_key(self):
        return _state_field_key(self.field_name, self.subject_kind, self.entity_id, self.subject_id)


@dataclass(frozen=True)
class NativeIntervalSample(Contract):
    """Measurements over one half-open native interval ``[t, t + physics_dt)``."""

    schema_version: str
    native_step_index: int
    interval_start_s: float
    interval_end_s: float
    signals: tuple[NativeSignalValue, ...]
    unavailable: tuple[UnavailableStateValue, ...] = ()

    def validate(self):
        _choice(self.schema_version, {"native-interval-sample-v1"}, "native interval sample schema")
        if self.native_step_index < 0 or self.interval_start_s < 0 or self.interval_end_s <= self.interval_start_s:
            raise ValueError("invalid native interval sample bounds")
        keys = tuple(signal.field_key for signal in self.signals)
        unavailable_keys = tuple(value.field_key for value in self.unavailable)
        if any(value.sample_domain != "native_step_interval" for value in self.unavailable):
            raise ValueError("native interval unavailable values must name the native sample domain")
        combined = keys + unavailable_keys
        if not combined or len(combined) != len(set(combined)):
            raise ValueError("native interval sample requires unique measured or explicitly unavailable signals")


@dataclass(frozen=True)
class NativeIntervalEvidence(Contract):
    """Complete native-rate evidence for exactly one control interval."""

    schema_version: str
    interval_id: str
    boundary_before: StateBoundaryIdentity
    boundary_after: StateBoundaryIdentity
    evaluation_start: StateSampleClock
    evaluation_end: StateSampleClock
    physics_dt: float
    control_substeps: int
    native_step_start: int
    samples: tuple[NativeIntervalSample, ...]
    evidence_reference: str

    def validate(self):
        _choice(self.schema_version, {"native-interval-evidence-v1"}, "native interval evidence schema")
        _name(self.interval_id)
        if not self.evidence_reference.strip():
            raise ValueError("native interval evidence requires a raw evidence reference")
        if (not math.isfinite(self.physics_dt) or self.physics_dt <= 0
                or self.control_substeps < 1 or self.native_step_start < 0):
            raise ValueError("invalid native interval timebase")
        before, after = self.boundary_before, self.boundary_after
        same_owner = (
            before.episode_id == after.episode_id
            and before.reset_sample_id == after.reset_sample_id
            and before.scene_identity_hash == after.scene_identity_hash
            and before.scene_instance_id == after.scene_instance_id
            and before.provider_materialization_id == after.provider_materialization_id
        )
        if not same_owner or after.control_step != before.control_step + 1:
            raise ValueError("native interval must connect adjacent boundaries in one materialization")
        if after.state_revision <= before.state_revision:
            raise ValueError("native interval end must publish a newer state revision")
        start, end = self.evaluation_start, self.evaluation_end
        if (start.clock_domain != "evaluation_boundary" or end.clock_domain != "evaluation_boundary"
                or start.sample_index != before.control_step or end.sample_index != after.control_step):
            raise ValueError("native interval evaluation clocks must identify its boundary pair")
        control_dt = self.physics_dt * self.control_substeps
        if not _near_one_ulp(end.simulation_time_s - start.simulation_time_s, control_dt):
            raise ValueError("native interval evaluation boundaries do not match its native timebase")
        if len(self.samples) != self.control_substeps:
            raise ValueError("native interval evidence must include every control substep")
        expected_keys = None
        for index, sample in enumerate(self.samples):
            if sample.native_step_index != self.native_step_start + index:
                raise ValueError("native interval samples are missing, duplicated, or out of order")
            expected_start = start.simulation_time_s + index * self.physics_dt
            expected_end = expected_start + self.physics_dt
            if not (_near_one_ulp(sample.interval_start_s, expected_start)
                    and _near_one_ulp(sample.interval_end_s, expected_end)):
                raise ValueError("native evidence must preserve contiguous half-open physics intervals")
            keys = {signal.field_key for signal in sample.signals}
            keys.update(value.field_key for value in sample.unavailable)
            if expected_keys is None:
                expected_keys = keys
            elif keys != expected_keys:
                raise ValueError("native interval signal availability changed or went missing within one interval")

    def validate_requirements(self, requirements: StateRequirements) -> None:
        """Require every native field per step or an explicit unavailable marker."""
        if not isinstance(requirements, StateRequirements):
            raise TypeError("state requirements must be StateRequirements")
        signal_by_sample = [
            {signal.field_key: signal for signal in sample.signals}
            for sample in self.samples
        ]
        unavailable_by_sample = [
            {value.field_key: value for value in sample.unavailable}
            for sample in self.samples
        ]
        for requirement in requirements.requirements:
            if requirement.sample_domain != "native_step_interval":
                continue
            for signals, unavailable in zip(signal_by_sample, unavailable_by_sample, strict=True):
                signal = signals.get(requirement.field_key)
                if signal is not None:
                    if signal.unit != requirement.unit or signal.reference_frame != requirement.reference_frame:
                        raise ValueError(f"native signal metadata disagrees with requirement: {requirement.field_key}")
                    continue
                marker = unavailable.get(requirement.field_key)
                if marker is None:
                    raise ValueError(f"native state field omitted without unavailable evidence: {requirement.field_key}")
                if requirement.requiredness == "required":
                    raise ValueError(f"required native state field unavailable: {requirement.field_key}: {marker.reason}")


@dataclass(frozen=True)
class StateViewLifetime(Contract):
    """Lifetime declaration for an owned snapshot or a borrowed provider alias."""

    schema_version: str
    owner_id: str
    boundary: StateBoundaryIdentity
    generation: int
    storage_kind: str
    valid_until: str

    def validate(self):
        _choice(self.schema_version, {"state-view-lifetime-v1"}, "state view lifetime schema")
        _name(self.owner_id)
        if self.generation != self.boundary.state_revision:
            raise ValueError("state view generation must match its published boundary revision")
        _choice(self.storage_kind, {"owned_snapshot", "provider_alias"}, "state view storage kind")
        if self.storage_kind == "owned_snapshot":
            _choice(self.valid_until, {"retained"}, "owned snapshot lifetime")
        else:
            _choice(self.valid_until, {"next_mutation", "reset", "close"}, "provider alias lifetime")

    @property
    def may_be_retained(self) -> bool:
        return self.storage_kind == "owned_snapshot" and self.valid_until == "retained"


@dataclass(frozen=True)
class CanonicalStatePublicationV1(Contract):
    """Bind one canonical state view to the owner and lifetime of its storage."""

    schema_version: str
    view: CanonicalStateViewV1
    lifetime: StateViewLifetime

    def validate(self):
        _choice(self.schema_version, {"canonical-state-publication-v1"}, "state publication schema")
        if self.lifetime.boundary != self.view.boundary:
            raise ValueError("state publication view and lifetime must share one boundary")
        if self.lifetime.owner_id != self.view.boundary.provider_materialization_id:
            raise ValueError("state publication lifetime owner must match its provider materialization")


@dataclass(frozen=True)
class CanonicalStatePublicationV2(Contract):
    """Owned publication envelope for the additive canonical-state-v2 view."""

    schema_version: str
    view: CanonicalStateViewV2
    lifetime: StateViewLifetime

    def validate(self):
        _choice(self.schema_version, {"canonical-state-publication-v2"}, "state publication schema")
        if self.lifetime.boundary != self.view.boundary:
            raise ValueError("state publication view and lifetime must share one boundary")
        if self.lifetime.owner_id != self.view.boundary.provider_materialization_id:
            raise ValueError("state publication lifetime owner must match its provider materialization")


def decode_canonical_state_view(values: Mapping):
    """Dispatch only by an exact canonical state schema discriminator."""
    if not isinstance(values, Mapping):
        raise TypeError("canonical state requires mapping")
    schema = values.get("schema_version")
    if schema == "canonical-state-v0":
        return CanonicalStateView.from_mapping(values)
    if schema == "canonical-state-v1":
        return CanonicalStateViewV1.from_mapping(values)
    if schema == "canonical-state-v2":
        return CanonicalStateViewV2.from_mapping(values)
    raise ValueError(f"unsupported canonical state schema: {schema!r}")


def decode_canonical_state_publication(values: Mapping):
    """Decode only exact, versioned publication envelopes."""
    if not isinstance(values, Mapping):
        raise TypeError("canonical state publication requires mapping")
    schema = values.get("schema_version")
    if schema == "canonical-state-publication-v1":
        return CanonicalStatePublicationV1.from_mapping(values)
    if schema == "canonical-state-publication-v2":
        return CanonicalStatePublicationV2.from_mapping(values)
    raise ValueError(f"unsupported canonical state publication schema: {schema!r}")


def project_canonical_state_v0(
    state: CanonicalStateView,
    *,
    scene: SceneDefinition,
    boundary: StateBoundaryIdentity,
    sample_clock: StateSampleClock,
    joint_bindings: Mapping[str, JointDefinition],
    frame_bindings: Mapping[str, FrameReference],
) -> CanonicalStateViewV1:
    """Explicitly project scalar v0 names through an A02 scene and caller bindings.

    This deliberately refuses to guess Entity/Frame/Joint identity or promote
    a scalar v0 coordinate into spherical/free-base state.
    """
    if not isinstance(state, CanonicalStateView):
        raise TypeError("v0 projection requires CanonicalStateView")
    if not isinstance(scene, SceneDefinition) or scene.schema_version not in {
        "scene-definition-v2", "scene-definition-v3"
    }:
        raise ValueError("v0 typed projection requires an A02 scene-definition-v2/v3")
    if boundary.scene_identity_hash != scene.identity_hash:
        raise ValueError("state boundary and A02 scene identity disagree")
    if boundary.control_step != state.control_step:
        raise ValueError("v0 state and supplied boundary control step disagree")
    if (sample_clock.clock_domain != "evaluation_boundary"
            or sample_clock.sample_index != state.control_step
            or sample_clock.simulation_time_s != state.simulation_time):
        raise ValueError("v0 state requires an explicit matching evaluation boundary clock")

    scene_joints = {
        (articulation.entity_id, joint.joint_id): joint
        for articulation in (scene.articulations or ())
        for joint in articulation.joints
    }
    scene_frames = {(frame.entity_id, frame.frame_id) for frame in (scene.frames or ())}
    if set(joint_bindings) != set(state.joint_position) or set(joint_bindings) != set(state.joint_velocity):
        raise ValueError("explicit v0 joint bindings must cover both scalar maps exactly")
    if set(frame_bindings) != set(state.pose_world):
        raise ValueError("explicit v0 frame bindings must cover the pose map exactly")

    joint_values = []
    for old_name in sorted(joint_bindings):
        definition = joint_bindings[old_name]
        key = (definition.parent_frame.entity_id, definition.joint_id)
        if scene_joints.get(key) != definition:
            raise ValueError(f"v0 joint binding is not declared by the supplied scene: {old_name}")
        if definition.position_size != 1 or definition.velocity_size != 1:
            raise ValueError(f"scalar v0 cannot represent multi-DOF joint: {old_name}")
        value = TypedJointStateValue(
            "typed-joint-state-v1", key[0], key[1], definition.kind,
            definition.position_representation, (state.joint_position[old_name],),
            definition.velocity_representation, (state.joint_velocity[old_name],),
        )
        value.validate_against(definition)
        joint_values.append(value)

    frame_values = []
    for old_name in sorted(frame_bindings):
        reference = frame_bindings[old_name]
        if (reference.entity_id, reference.frame_id) not in scene_frames:
            raise ValueError(f"v0 frame binding is not declared by the supplied scene: {old_name}")
        frame_values.append(TypedFrameStateValue(
            "typed-frame-state-v1", reference, state.pose_world[old_name]
        ))

    result = CanonicalStateViewV1(
        "canonical-state-v1", state.convention, boundary, sample_clock,
        tuple(joint_values), tuple(frame_values), (),
    )
    result.validate_against_scene(scene)
    return result
