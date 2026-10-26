"""Versioned, provider-free Position leaf contracts for the R02a boundary.

These immutable values describe bindings and requests.  They do not create a
Controller, compile an effective plan, access native state, or admit a
Provider.  The existing complete-Panda controller remains the only executable
canonical Controller in this module family until a later slice adds adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

from ...artifacts.contracts import (
    ActuatorReference,
    Contract,
    FrameReference,
    JointReference,
    PoseWorld,
    SceneDefinition,
    _name,
)
from ...artifacts.logical_assembly import (
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblySubcomponentReferenceV1,
)
from ...artifacts.logical_assembly_resolution import ResolvedLogicalAssemblyV1
from ...artifacts.state import (
    StateBoundaryIdentity,
    StateFieldRequirement,
    StateRequirements,
    StateSampleClock,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")
_VERSION_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
_IDENTITY_FIELDS = (
    "scene_identity_hash",
    "assembly_identity_sha256",
    "source_closure_sha256",
    "binding_identity_hash",
    "reset_sample_id",
    "episode_id",
    "scene_instance_id",
    "provider_materialization_id",
    "state_boundary_id",
    "sample_clock",
)

ARM_POSITION_PROFILE_ID = "panda-arm-position-leaf-v1"
HAND_POSITION_PROFILE_ID = "panda-hand-position-leaf-v1"
HAND_FORCE_AWARE_PROFILE_ID = "panda-hand-force-aware-leaf-v1"

ARM_POSITION_ACTION_SCHEMA = "arm-position-action-v1"
HAND_POSITION_ACTION_SCHEMA = "hand-position-action-v1"
HAND_FORCE_AWARE_ACTION_SCHEMA = "hand-force-aware-action-v1"
HAND_FORCE_AWARE_DEPENDENCY_SCHEMA = "hand-force-aware-dependency-v1"

PANDA_ARM_JOINT_IDS = tuple(f"joint{index}" for index in range(1, 8))
PANDA_ARM_JOINT_LIMITS_RAD = (
    (-2.8973, 2.8973),
    (-1.7628, 1.7628),
    (-2.8973, 2.8973),
    (-3.0718, -0.0698),
    (-2.8973, 2.8973),
    (-0.0175, 3.7525),
    (-2.8973, 2.8973),
)
PANDA_HAND_FINGER_JOINT_IDS = ("finger_joint1", "finger_joint2")
PANDA_HAND_FINGER_LIMITS_M = ((0.0, 0.04), (0.0, 0.04))
PANDA_HAND_TENDON_COEFFICIENTS = (0.5, 0.5)
PANDA_HAND_TENDON_IDENTITY = "hand.xml/tendon/split"
PANDA_HAND_EQUALITY_IDENTITY = "hand.xml/equality/finger_joint1=finger_joint2"
PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M = 3187.5
PANDA_HAND_ACTUATOR_GAINPRM = (0.01568627451, 0.0, 0.0)
PANDA_HAND_ACTUATOR_BIASPRM = (0.0, -100.0, -10.0)


def _require_sha256(value: str, label: str) -> None:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")


def _canonical_hash(value) -> str:
    mapping = value.to_mapping() if isinstance(value, Contract) else value
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _member_path(value) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not value:
        raise ValueError("member_path must be a nonempty segment sequence")
    result = tuple(value)
    if any(type(segment) is not str or not _PATH_SEGMENT.fullmatch(segment)
           or segment in {".", ".."} for segment in result):
        raise ValueError("member_path contains an invalid or ambiguous segment")
    return result


def _ordered_unique(values, label: str) -> None:
    if not values or len(set(values)) != len(values):
        raise ValueError(f"{label} must be nonempty and unique")


def _position_requirements(
    profile_id: str,
    entity_id: str,
    joint_ids: tuple[str, ...],
    tcp_frame: FrameReference,
    actuator_ids: tuple[str, ...] = (),
) -> StateRequirements:
    requirements = []
    for joint_id in joint_ids:
        requirements.extend((
            StateFieldRequirement(
                "state-field-requirement-v1", "joint_position", "joint",
                entity_id, joint_id, "required", "evaluation_boundary",
                "joint-definition", "joint_state_query",
            ),
            StateFieldRequirement(
                "state-field-requirement-v1", "joint_velocity", "joint",
                entity_id, joint_id, "required", "evaluation_boundary",
                "joint-definition", "joint_state_query",
            ),
        ))
    requirements.append(StateFieldRequirement(
        "state-field-requirement-v1", "frame_pose_world", "frame",
        entity_id, tcp_frame.frame_id, "required", "evaluation_boundary",
        "meter+quaternion_wxyz", "frame_pose_query",
    ))
    for actuator_id in actuator_ids:
        requirements.append(StateFieldRequirement(
            "state-field-requirement-v1", "actuator_force", "actuator",
            entity_id, actuator_id, "required", "native_step_interval", "N",
            "actuator_force_query",
        ))
    return StateRequirements(
        "state-requirements-v1", "controller", profile_id, tuple(requirements),
    )


@dataclass(frozen=True)
class LeafRequiredStateV1(Contract):
    """Typed state contract plus the lifecycle identities every sample needs."""

    schema_version: str
    profile_kind: str
    state_requirements: StateRequirements
    required_identity_fields: tuple[str, ...]
    required_sample_clock_domain: str

    def validate(self):
        if self.schema_version != "leaf-required-state-v1":
            raise ValueError("unsupported leaf Required State schema")
        if self.profile_kind not in {"arm_position", "hand_position", "hand_force_aware"}:
            raise ValueError("unsupported leaf Required State profile kind")
        if not isinstance(self.state_requirements, StateRequirements):
            raise TypeError("leaf Required State requires typed StateRequirements")
        if self.state_requirements.consumer_kind != "controller":
            raise ValueError("leaf state requirements must be Controller-owned")
        if tuple(self.required_identity_fields) != _IDENTITY_FIELDS:
            raise ValueError("leaf state requires the complete source/boundary identity set")
        if self.required_sample_clock_domain != "evaluation_boundary":
            raise ValueError("Position leaf state requires an evaluation-boundary clock")
        fields = {item.field_name for item in self.state_requirements.requirements}
        if self.profile_kind == "hand_force_aware":
            if "actuator_force" not in fields:
                raise ValueError("Force-aware Required State must require force samples")
        elif "actuator_force" in fields:
            raise ValueError("Position Required State must not require or synthesize force")


@dataclass(frozen=True)
class LeafJointActuatorBindingV1(Contract):
    """One ordered scalar Joint-to-actuator relation for an Arm leaf."""

    schema_version: str
    joint: JointReference
    actuator: ActuatorReference

    def validate(self):
        if self.schema_version != "leaf-joint-actuator-binding-v1":
            raise ValueError("unsupported leaf Joint/Actuator binding schema")
        if not isinstance(self.joint, JointReference) or not isinstance(self.actuator, ActuatorReference):
            raise TypeError("leaf Joint/Actuator binding requires typed references")
        if self.joint.entity_id != self.actuator.entity_id:
            raise ValueError("Joint and actuator binding must share the same Entity owner")


@dataclass(frozen=True)
class LeafProfileBindingV1(Contract):
    """One concrete, ordered static leaf binding to existing Scene resources.

    ``provenance_kind`` distinguishes real declared identities from synthetic
    provider-free fixtures.  A synthetic binding is useful for contract tests
    and must never be reported as a native/runtime identity.
    """

    schema_version: str
    provenance_kind: str
    profile_kind: str
    profile_id: str
    action_schema_id: str
    scene_identity_hash: str
    assembly_id: str
    assembly_revision: str
    assembly_identity_sha256: str
    member_path: tuple[str, ...]
    member_kind: str
    member_target_kind: str
    member_target_id: str
    entity_id: str
    asset_id: str
    asset_version: str
    source_closure_sha256: str
    algorithm_id: str
    configuration_identity_sha256: str
    writer_id: str
    control_group_id: str
    provider_name: str
    provider_version: str
    provider_build_sha256: str
    backend: str
    physics_dt_s: float
    control_substeps: int
    joint_order: tuple[JointReference, ...]
    joint_position_unit: str
    joint_position_limits: tuple[tuple[float, float], ...]
    actuator_order: tuple[ActuatorReference, ...]
    joint_actuator_bindings: tuple[LeafJointActuatorBindingV1, ...]
    tcp_frame: FrameReference
    tcp_transform_direction: str
    tcp_pose_parent: PoseWorld
    required_state: LeafRequiredStateV1
    tendon_identity: str | None = None
    tendon_coefficients: tuple[float, ...] = ()
    equality_identity: str | None = None
    actuator_command_scale_ctrl_per_opening_m: float | None = None
    hand_opening_definition: str | None = None
    native_command_definition: str | None = None
    native_ctrlrange: tuple[float, float] | None = None
    actuator_gainprm: tuple[float, ...] = ()
    actuator_biasprm: tuple[float, ...] = ()

    def validate(self):
        if self.schema_version != "leaf-profile-binding-v1":
            raise ValueError("unsupported leaf binding schema")
        if self.provenance_kind not in {"declared", "synthetic_fixture"}:
            raise ValueError("binding provenance must be explicit")
        if self.profile_kind not in {"arm_position", "hand_position", "hand_force_aware"}:
            raise ValueError("unsupported leaf profile kind")
        expected_profile = {
            "arm_position": ARM_POSITION_PROFILE_ID,
            "hand_position": HAND_POSITION_PROFILE_ID,
            "hand_force_aware": HAND_FORCE_AWARE_PROFILE_ID,
        }[self.profile_kind]
        expected_action = {
            "arm_position": ARM_POSITION_ACTION_SCHEMA,
            "hand_position": HAND_POSITION_ACTION_SCHEMA,
            "hand_force_aware": HAND_FORCE_AWARE_ACTION_SCHEMA,
        }[self.profile_kind]
        if (self.profile_id, self.action_schema_id) != (expected_profile, expected_action):
            raise ValueError("leaf profile/action schema identity mismatch")
        for value, label in (
            (self.scene_identity_hash, "Scene identity"),
            (self.assembly_identity_sha256, "Assembly identity"),
            (self.source_closure_sha256, "source closure"),
            (self.configuration_identity_sha256, "configuration identity"),
            (self.provider_build_sha256, "Provider build identity"),
        ):
            _require_sha256(value, label)
        for value, label in (
            (self.assembly_id, "Assembly ID"), (self.assembly_revision, "Assembly revision"),
            (self.member_target_id, "member target"), (self.entity_id, "Entity ID"),
            (self.asset_id, "Asset ID"), (self.asset_version, "Asset version"),
            (self.algorithm_id, "algorithm ID"), (self.writer_id, "writer ID"),
            (self.control_group_id, "ControlGroup ID"), (self.provider_name, "Provider name"),
            (self.backend, "backend"),
        ):
            _name(value)
        if type(self.provider_version) is not str or not _VERSION_TOKEN.fullmatch(self.provider_version):
            raise ValueError("Provider version must be an explicit stable version token")
        object.__setattr__(self, "member_path", _member_path(self.member_path))
        if self.member_kind == "entity_member":
            if self.member_target_kind != "entity" or self.member_target_id != self.entity_id:
                raise ValueError("Entity-owning selector must identify its exact Entity")
        elif self.member_kind == "existing_entity_subcomponent_ref":
            if self.member_target_kind != "control_group" or self.member_target_id != self.control_group_id:
                raise ValueError("reference-only selector must identify the bound ControlGroup")
        else:
            raise ValueError("unsupported logical member selector kind")
        if self.physics_dt_s <= 0 or self.control_substeps <= 0:
            raise ValueError("leaf binding timebase must be positive")
        if self.physics_dt_s != 0.002 or self.control_substeps != 5:
            raise ValueError("R02a Panda Position candidate requires 2 ms / five substeps")
        if not isinstance(self.required_state, LeafRequiredStateV1):
            raise TypeError("leaf binding requires versioned Required State")
        if self.required_state.profile_kind != self.profile_kind:
            raise ValueError("leaf binding and Required State profile kinds disagree")
        requirements = self.required_state.state_requirements.requirements
        required_joint_fields = {
            (field_name, reference.entity_id, reference.joint_id)
            for reference in self.joint_order
            for field_name in ("joint_position", "joint_velocity")
        }
        actual_joint_fields = {
            (item.field_name, item.entity_id, item.subject_id)
            for item in requirements
            if item.subject_kind == "joint"
        }
        if not required_joint_fields.issubset(actual_joint_fields):
            raise ValueError("Required State must include position and velocity for every bound Joint")
        if not any(
            item.field_name == "frame_pose_world"
            and item.entity_id == self.tcp_frame.entity_id
            and item.subject_id == self.tcp_frame.frame_id
            for item in requirements
        ):
            raise ValueError("Required State must include the exact Entity-qualified TCP parent Frame")
        if self.tcp_frame.entity_id != self.entity_id:
            raise ValueError("leaf TCP frame must belong to the bound Entity")
        if self.tcp_transform_direction != "T_parent_from_tcp":
            raise ValueError("TCP transform direction must explicitly be T_parent_from_tcp")
        refs = tuple(self.joint_order)
        actuators = tuple(self.actuator_order)
        _ordered_unique(refs, "ordered Joint refs")
        _ordered_unique(actuators, "ordered Actuator refs")
        if any(reference.entity_id != self.entity_id for reference in refs):
            raise ValueError("leaf joints must belong to the bound Entity")
        if any(reference.entity_id != self.entity_id for reference in actuators):
            raise ValueError("leaf actuators must belong to the bound Entity")
        if any(type(pair) is not LeafJointActuatorBindingV1 for pair in self.joint_actuator_bindings):
            raise TypeError("leaf Joint/Actuator order requires typed pair bindings")
        if len(refs) != len(self.joint_position_limits):
            raise ValueError("ordered joint limits must align one-to-one with Joint refs")
        for lower, upper in self.joint_position_limits:
            if lower >= upper:
                raise ValueError("joint limit bounds must be strictly ordered")
        if self.profile_kind == "arm_position":
            if (tuple(ref.joint_id for ref in refs) != PANDA_ARM_JOINT_IDS
                    or self.joint_position_unit != "radian"
                    or tuple(ref.actuator_id for ref in actuators) != tuple(f"actuator{i}" for i in range(1, 8))
                    or len(actuators) != 7 or self.tendon_identity is not None
                    or len(self.joint_actuator_bindings) != 7
                    or self.tendon_coefficients or self.equality_identity is not None
                    or self.actuator_command_scale_ctrl_per_opening_m is not None
                    or self.hand_opening_definition is not None
                    or self.native_command_definition is not None or self.native_ctrlrange is not None
                    or self.actuator_gainprm or self.actuator_biasprm):
                raise ValueError("Arm-only Position requires ordered Panda arm joints/actuators")
            if tuple(tuple(limit) for limit in self.joint_position_limits) != PANDA_ARM_JOINT_LIMITS_RAD:
                raise ValueError("Arm-only Position limits must match the declared Panda order")
            expected_pairs = tuple(zip(refs, actuators, strict=True))
            if tuple((pair.joint, pair.actuator) for pair in self.joint_actuator_bindings) != expected_pairs:
                raise ValueError("Arm Position Joint/Actuator pairs must preserve the exact canonical order")
        else:
            if (tuple(ref.joint_id for ref in refs) != PANDA_HAND_FINGER_JOINT_IDS
                    or tuple(ref.actuator_id for ref in actuators) != ("actuator8",)
                    or self.joint_position_unit != "meter" or len(actuators) != 1
                    or self.tendon_identity != PANDA_HAND_TENDON_IDENTITY
                    or self.equality_identity != PANDA_HAND_EQUALITY_IDENTITY
                    or tuple(self.tendon_coefficients) != PANDA_HAND_TENDON_COEFFICIENTS
                    or self.joint_actuator_bindings
                    or self.actuator_command_scale_ctrl_per_opening_m
                    != PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M
                    or self.hand_opening_definition != "opening_m = finger_joint1_q_m + finger_joint2_q_m"
                    or self.native_command_definition != "ctrl = 3187.5 * opening_m"
                    or self.native_ctrlrange != (0.0, 255.0)
                    or tuple(self.actuator_gainprm) != PANDA_HAND_ACTUATOR_GAINPRM
                    or tuple(self.actuator_biasprm) != PANDA_HAND_ACTUATOR_BIASPRM
                    or tuple(tuple(limit) for limit in self.joint_position_limits)
                    != PANDA_HAND_FINGER_LIMITS_M):
                raise ValueError("Hand leaf requires two ordered fingers and one coupled tendon actuator")
            if self.profile_kind == "hand_force_aware":
                force_fields = [
                    item for item in self.required_state.state_requirements.requirements
                    if item.field_name == "actuator_force"
                ]
                if len(force_fields) != 1 or force_fields[0].subject_id != actuators[0].actuator_id:
                    raise ValueError("Force-aware Required State must bind its single tendon actuator")
        _name(self.member_target_kind)

    @property
    def identity_hash(self) -> str:
        """Hash the canonical payload without storing the hash in that payload."""
        return _canonical_hash(self)


@dataclass(frozen=True)
class ArmPositionActionV1(Contract):
    schema_version: str
    joint_order: tuple[JointReference, ...]
    position_rad: tuple[float, ...]

    def validate(self):
        if self.schema_version != ARM_POSITION_ACTION_SCHEMA:
            raise ValueError("unsupported Arm Position Action schema")
        _ordered_unique(self.joint_order, "Arm Position Action joint order")
        if len(self.joint_order) != 7 or len(self.position_rad) != 7:
            raise ValueError("Arm Position Action requires exactly seven ordered radian values")


@dataclass(frozen=True)
class HandPositionActionV1(Contract):
    schema_version: str
    opening_m: float
    input_representation: str = "opening_m"
    requested_normalized: float | None = None

    def validate(self):
        if self.schema_version != HAND_POSITION_ACTION_SCHEMA:
            raise ValueError("unsupported Hand Position Action schema")
        if not 0.0 <= self.opening_m <= 0.08:
            raise ValueError("Hand Position opening_m must be within [0, 0.08]")
        if self.input_representation == "opening_m":
            if self.requested_normalized is not None:
                raise ValueError("direct metre action cannot carry a normalized request")
        elif self.input_representation == "normalized_signed_scalar_v1":
            if self.requested_normalized is None or not -1.0 <= self.requested_normalized <= 1.0:
                raise ValueError("normalized adapter requires a value in [-1, 1]")
            if self.opening_m != 0.04 * (self.requested_normalized + 1.0):
                raise ValueError("normalized-to-metre mapping must be explicit and exact")
        else:
            raise ValueError("unknown Hand Position input representation")

    @classmethod
    def from_normalized_signed_scalar(cls, value: float) -> "HandPositionActionV1":
        if type(value) not in (int, float) or not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError("legacy normalized gripper scalar must be finite and within [-1, 1]")
        return cls(
            HAND_POSITION_ACTION_SCHEMA,
            0.04 * (float(value) + 1.0),
            "normalized_signed_scalar_v1",
            float(value),
        )


@dataclass(frozen=True)
class ArmPositionTargetV1(Contract):
    schema_version: str
    profile_id: str
    action_schema_id: str
    writer_id: str
    binding_identity_hash: str
    source_closure_sha256: str
    scene_identity_hash: str
    joint_order: tuple[JointReference, ...]
    actuator_order: tuple[ActuatorReference, ...]
    source_boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    action: ArmPositionActionV1

    def validate(self):
        if self.schema_version != "arm-position-target-v1":
            raise ValueError("unsupported Arm Position Target schema")
        if self.profile_id != ARM_POSITION_PROFILE_ID:
            raise ValueError("Arm Position Target profile identity mismatch")
        _name(self.writer_id)
        for value, label in ((self.binding_identity_hash, "binding"),
                             (self.source_closure_sha256, "source closure"),
                             (self.scene_identity_hash, "Scene")):
            _require_sha256(value, label)
        if not isinstance(self.source_boundary, StateBoundaryIdentity) or not isinstance(self.sample_clock, StateSampleClock):
            raise TypeError("Arm Position Target requires typed boundary and clock")
        if not isinstance(self.action, ArmPositionActionV1):
            raise TypeError("Arm Position Target requires ArmPositionActionV1")
        if self.action_schema_id != ARM_POSITION_ACTION_SCHEMA or self.action.schema_version != self.action_schema_id:
            raise ValueError("Arm Position Target action schema mismatch")
        _ordered_unique(self.joint_order, "Arm Position Target joints")
        _ordered_unique(self.actuator_order, "Arm Position Target actuators")
        if len(self.joint_order) != 7 or len(self.actuator_order) != 7 or self.joint_order != self.action.joint_order:
            raise ValueError("Arm Position Target resource order must match its action")
        _validate_source_clock(self.scene_identity_hash, self.source_boundary, self.sample_clock)

    @property
    def identity_hash(self) -> str:
        return _canonical_hash(self)


@dataclass(frozen=True)
class HandPositionTargetV1(Contract):
    schema_version: str
    profile_id: str
    action_schema_id: str
    writer_id: str
    binding_identity_hash: str
    source_closure_sha256: str
    scene_identity_hash: str
    joint_order: tuple[JointReference, ...]
    actuator_order: tuple[ActuatorReference, ...]
    source_boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    action: HandPositionActionV1

    def validate(self):
        if self.schema_version != "hand-position-target-v1":
            raise ValueError("unsupported Hand Position Target schema")
        if self.profile_id != HAND_POSITION_PROFILE_ID:
            raise ValueError("Hand Position Target profile identity mismatch")
        _name(self.writer_id)
        for value, label in ((self.binding_identity_hash, "binding"),
                             (self.source_closure_sha256, "source closure"),
                             (self.scene_identity_hash, "Scene")):
            _require_sha256(value, label)
        if not isinstance(self.source_boundary, StateBoundaryIdentity) or not isinstance(self.sample_clock, StateSampleClock):
            raise TypeError("Hand Position Target requires typed boundary and clock")
        if not isinstance(self.action, HandPositionActionV1):
            raise TypeError("Hand Position Target requires HandPositionActionV1")
        if self.action_schema_id != HAND_POSITION_ACTION_SCHEMA or self.action.schema_version != self.action_schema_id:
            raise ValueError("Hand Position Target action schema mismatch")
        _ordered_unique(self.joint_order, "Hand Position Target joints")
        _ordered_unique(self.actuator_order, "Hand Position Target actuators")
        if len(self.joint_order) != 2 or len(self.actuator_order) != 1:
            raise ValueError("Hand Position Target requires two fingers and one actuator")
        _validate_source_clock(self.scene_identity_hash, self.source_boundary, self.sample_clock)

    @property
    def identity_hash(self) -> str:
        return _canonical_hash(self)


def _validate_source_clock(scene_hash, boundary, clock):
    boundary.validate()
    clock.validate()
    if (boundary.scene_identity_hash != scene_hash or clock.clock_domain != "evaluation_boundary"
            or clock.sample_index != boundary.control_step):
        raise ValueError("Target source boundary, Scene and evaluation clock disagree")


@dataclass(frozen=True)
class LeafApplicationAckV1(Contract):
    """A typed static application receipt; it is not a measured state/result."""

    schema_version: str
    profile_kind: str
    profile_id: str
    action_schema_id: str
    target_identity_hash: str
    writer_id: str
    binding_identity_hash: str
    source_closure_sha256: str
    scene_identity_hash: str
    joint_order: tuple[JointReference, ...]
    actuator_order: tuple[ActuatorReference, ...]
    source_boundary: StateBoundaryIdentity
    source_sample_clock: StateSampleClock
    application_boundary: StateBoundaryIdentity
    application_sample_clock: StateSampleClock

    def validate(self):
        if self.schema_version != "leaf-application-ack-v1":
            raise ValueError("unsupported leaf application Ack schema")
        if self.profile_kind not in {"arm_position", "hand_position"}:
            raise ValueError("Force-aware leaf Ack is not admitted")
        expected_profile = ARM_POSITION_PROFILE_ID if self.profile_kind == "arm_position" else HAND_POSITION_PROFILE_ID
        expected_action_schema = ARM_POSITION_ACTION_SCHEMA if self.profile_kind == "arm_position" else HAND_POSITION_ACTION_SCHEMA
        if (self.profile_id, self.action_schema_id) != (expected_profile, expected_action_schema):
            raise ValueError("leaf Ack profile identity mismatch")
        _name(self.writer_id)
        for value, label in ((self.target_identity_hash, "target"),
                             (self.binding_identity_hash, "binding"),
                             (self.source_closure_sha256, "source closure"),
                             (self.scene_identity_hash, "Scene")):
            _require_sha256(value, label)
        if len(self.joint_order) != (7 if self.profile_kind == "arm_position" else 2):
            raise ValueError("leaf Ack joint resources do not match its profile")
        if len(self.actuator_order) != (7 if self.profile_kind == "arm_position" else 1):
            raise ValueError("leaf Ack actuator resources do not match its profile")
        _ordered_unique(self.joint_order, "leaf Ack joints")
        _ordered_unique(self.actuator_order, "leaf Ack actuators")
        _validate_source_clock(self.scene_identity_hash, self.source_boundary, self.source_sample_clock)
        _validate_source_clock(self.scene_identity_hash, self.application_boundary, self.application_sample_clock)
        _same_episode_boundary(self.source_boundary, self.application_boundary)
        if self.source_sample_clock != self.application_sample_clock:
            raise ValueError("Ack source and application clocks must identify the same evaluation boundary")

    @property
    def identity_hash(self) -> str:
        return _canonical_hash(self)


def _same_episode_boundary(source, application):
    identity_fields = (
        "episode_id", "reset_sample_id", "scene_identity_hash", "scene_instance_id",
        "provider_materialization_id", "control_step",
    )
    if any(getattr(source, field) != getattr(application, field) for field in identity_fields):
        raise ValueError("Ack application must remain on the target's explicit evaluation boundary")


@dataclass(frozen=True)
class HandForceAwareDependencyV1(Contract):
    """Dependency/refusal contract only; no force algorithm or writer exists."""

    schema_version: str
    profile_id: str
    action_schema_id: str
    admission_status: str
    required_state: LeafRequiredStateV1
    required_evidence_fields: tuple[str, ...]
    raw_signed_force_unit: str
    canonical_closing_force_unit: str
    sign_mapping_status: str
    sample_phase_status: str
    position_profiles_independent: bool
    reason: str

    def validate(self):
        if self.schema_version != HAND_FORCE_AWARE_DEPENDENCY_SCHEMA:
            raise ValueError("unsupported Force-aware dependency schema")
        if self.profile_id != HAND_FORCE_AWARE_PROFILE_ID or self.action_schema_id != HAND_FORCE_AWARE_ACTION_SCHEMA:
            raise ValueError("Force-aware dependency identity mismatch")
        if self.admission_status != "NOT_ADMITTED":
            raise ValueError("R02a Force-aware profile must remain NOT_ADMITTED")
        if not isinstance(self.required_state, LeafRequiredStateV1) or self.required_state.profile_kind != "hand_force_aware":
            raise TypeError("Force-aware dependency requires Force-aware Required State")
        expected = (
            "raw_signed_force_N", "canonical_closing_force_N", "source_transmission_identity",
            "unit", "sign_convention", "validity", "sample_phase", "native_sample_index",
            "sequence", "state_revision", "configuration_revision", "episode_id",
            "reset_sample_id", "evaluation_boundary_id", "provider_identity",
            "provider_build_identity", "backend", "sample_cadence",
        )
        if tuple(self.required_evidence_fields) != expected:
            raise ValueError("Force-aware evidence checklist is incomplete or reordered")
        if (self.raw_signed_force_unit, self.canonical_closing_force_unit) != ("N", "N"):
            raise ValueError("Force-aware raw and canonical force units are both explicitly N")
        if self.sign_mapping_status != "NOT_AUDITED" or self.sample_phase_status != "NOT_AUDITED":
            raise ValueError("Force-aware sign and phase mapping have not been audited")
        if type(self.position_profiles_independent) is not bool or not self.position_profiles_independent:
            raise ValueError("Force-aware absence must not block Position-only profiles")
        if type(self.reason) is not str or not self.reason.strip():
            raise ValueError("Force-aware refusal requires a concrete reason")


@dataclass(frozen=True)
class LeafCapabilityCatalogEntryV1(Contract):
    schema_version: str
    profile_kind: str
    profile_id: str
    contract_schema: str
    action_schema_id: str
    contract_status: str
    admission_status: str
    execution_status: str
    required_capabilities: tuple[str, ...]
    force_feedback_required: bool
    reason: str

    def validate(self):
        if self.schema_version != "leaf-capability-catalog-entry-v1":
            raise ValueError("unsupported leaf catalog schema")
        if self.profile_kind not in {"arm_position", "hand_position", "hand_force_aware"}:
            raise ValueError("unsupported catalog profile kind")
        if self.contract_status != "CONTRACT_ONLY" or self.admission_status != "NOT_ADMITTED" or self.execution_status != "NOT_RUN":
            raise ValueError("R02a catalog cannot claim admission or execution")
        _name(self.profile_id)
        _name(self.contract_schema)
        _name(self.action_schema_id)
        if type(self.force_feedback_required) is not bool:
            raise TypeError("force_feedback_required must be bool")
        if not self.required_capabilities or len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("catalog capabilities must be nonempty and unique")
        if type(self.reason) is not str or not self.reason.strip():
            raise ValueError("catalog entry requires a limitation")


LEAF_PROFILE_CATALOG_V1 = (
    LeafCapabilityCatalogEntryV1(
        "leaf-capability-catalog-entry-v1", "arm_position", ARM_POSITION_PROFILE_ID,
        "leaf-profile-binding-v1", ARM_POSITION_ACTION_SCHEMA, "CONTRACT_ONLY",
        "NOT_ADMITTED", "NOT_RUN", ("joint_position_actuation", "joint_state_query", "frame_pose_query"),
        False, "Static Arm leaf contract only; R02b adapter and R02c execution are not implemented.",
    ),
    LeafCapabilityCatalogEntryV1(
        "leaf-capability-catalog-entry-v1", "hand_position", HAND_POSITION_PROFILE_ID,
        "leaf-profile-binding-v1", HAND_POSITION_ACTION_SCHEMA, "CONTRACT_ONLY",
        "NOT_ADMITTED", "NOT_RUN", ("joint_position_actuation", "joint_state_query", "frame_pose_query"),
        False, "Static Hand leaf contract only; one tendon actuator and coupled fingers require later adapter/execution evidence.",
    ),
    LeafCapabilityCatalogEntryV1(
        "leaf-capability-catalog-entry-v1", "hand_force_aware", HAND_FORCE_AWARE_PROFILE_ID,
        "leaf-profile-binding-v1", HAND_FORCE_AWARE_ACTION_SCHEMA, "CONTRACT_ONLY",
        "NOT_ADMITTED", "NOT_RUN", ("actuator_force_query", "joint_state_query"),
        True, "Force source/sign/phase/freshness are not audited; no Force-aware compute/apply route exists.",
    ),
)


def leaf_profile_catalog_v1() -> tuple[LeafCapabilityCatalogEntryV1, ...]:
    """Return the immutable finite contract-only catalog; this is not a registry."""
    return LEAF_PROFILE_CATALOG_V1


def decode_leaf_profile_binding(values) -> LeafProfileBindingV1:
    """Strictly decode one versioned static leaf binding."""
    result = LeafProfileBindingV1.from_mapping(values)
    if result.schema_version != "leaf-profile-binding-v1":
        raise ValueError("unsupported leaf binding version")
    return result


def decode_leaf_action(values):
    """Dispatch only the two Position action schemas; Force-aware is refused."""
    if not hasattr(values, "get"):
        raise TypeError("leaf Action requires a mapping")
    schema = values.get("schema_version")
    if schema == ARM_POSITION_ACTION_SCHEMA:
        return ArmPositionActionV1.from_mapping(values)
    if schema == HAND_POSITION_ACTION_SCHEMA:
        return HandPositionActionV1.from_mapping(values)
    if schema == HAND_FORCE_AWARE_ACTION_SCHEMA:
        raise ValueError("Force-aware dependency is not an executable Action schema")
    raise ValueError(f"unsupported leaf Action schema: {schema!r}")


def decode_leaf_target(values):
    if not hasattr(values, "get"):
        raise TypeError("leaf Target requires a mapping")
    schema = values.get("schema_version")
    if schema == "arm-position-target-v1":
        return ArmPositionTargetV1.from_mapping(values)
    if schema == "hand-position-target-v1":
        return HandPositionTargetV1.from_mapping(values)
    raise ValueError(f"unsupported leaf Target schema: {schema!r}")


def decode_leaf_application_ack(values) -> LeafApplicationAckV1:
    result = LeafApplicationAckV1.from_mapping(values)
    if result.schema_version != "leaf-application-ack-v1":
        raise ValueError("unsupported leaf application Ack version")
    return result


def decode_force_aware_dependency(values) -> HandForceAwareDependencyV1:
    result = HandForceAwareDependencyV1.from_mapping(values)
    if result.schema_version != HAND_FORCE_AWARE_DEPENDENCY_SCHEMA:
        raise ValueError("unsupported Force-aware dependency version")
    return result


def validate_leaf_binding(
    scene: SceneDefinition,
    binding: LeafProfileBindingV1,
    resolved_assembly: ResolvedLogicalAssemblyV1 | None = None,
) -> LeafProfileBindingV1:
    """Validate exact Scene resources and, when supplied, Assembly selector provenance."""
    if type(scene) is not SceneDefinition or scene.schema_version != "scene-definition-v3":
        raise ValueError("leaf bindings require an exact Scene v3 value")
    if type(binding) is not LeafProfileBindingV1:
        raise TypeError("leaf binding validation requires LeafProfileBindingV1")
    if binding.scene_identity_hash != scene.identity_hash:
        raise ValueError("leaf binding pins a different Scene identity")
    entity = next((value for value in scene.entities if value.entity_id == binding.entity_id), None)
    if entity is None or (entity.asset_id, entity.asset_version) != (binding.asset_id, binding.asset_version):
        raise ValueError("leaf binding Asset/Entity identity is not declared by the Scene")
    joint_map = {
        (joint.parent_frame.entity_id, joint.joint_id): joint
        for articulation in scene.articulations or () for joint in articulation.joints
    }
    if any((ref.entity_id, ref.joint_id) not in joint_map for ref in binding.joint_order):
        raise ValueError("leaf binding references a Joint outside the Scene")
    expected_kind, expected_position_repr = (
        ("revolute", "radian") if binding.profile_kind == "arm_position" else ("prismatic", "meter")
    )
    for reference in binding.joint_order:
        definition = joint_map[(reference.entity_id, reference.joint_id)]
        if (definition.kind, definition.position_representation, definition.position_size) != (
            expected_kind, expected_position_repr, 1
        ):
            raise ValueError("ordered Scene Joint kind/unit does not match the leaf profile")
        expected_axis = (0.0, 0.0, 1.0) if binding.profile_kind == "arm_position" else (0.0, 1.0, 0.0)
        if definition.axis != expected_axis:
            raise ValueError("ordered Scene Joint axis does not match the Panda leaf contract")
    if FrameReference(binding.tcp_frame.entity_id, binding.tcp_frame.frame_id) not in {
        FrameReference(frame.entity_id, frame.frame_id) for frame in scene.frames or ()
    }:
        raise ValueError("leaf binding TCP parent Frame is not declared by the Scene")
    group = scene.resolve_control_group(binding.entity_id, binding.control_group_id)
    if set(group.actuator_refs) != set(binding.actuator_order):
        raise ValueError("leaf binding ordered Actuators do not exactly cover its ControlGroup")
    if set(binding.actuator_order) - {
        resource_ref for resource_ref in (
            ActuatorReference(resource.entity_id, resource.actuator_id)
            for resource in scene.actuator_resources or ()
        )
    }:
        raise ValueError("leaf binding Actuator is not declared by the Scene")
    if binding.member_kind == "existing_entity_subcomponent_ref":
        if binding.member_target_id != group.group_id:
            raise ValueError("reference-only selector does not resolve to the bound ControlGroup")
    elif binding.member_target_id != entity.entity_id:
        raise ValueError("owning selector does not resolve to the bound Entity")
    if resolved_assembly is not None:
        _validate_assembly_selector(binding, scene, resolved_assembly)
    return binding


def _validate_assembly_selector(binding, scene, assembly):
    if type(assembly) is not ResolvedLogicalAssemblyV1:
        raise TypeError("Assembly selector validation requires resolved Logical Assembly")
    if (assembly.root_assembly_id, assembly.root_revision, assembly.root_logical_content_sha256,
            assembly.scene_id, assembly.scene_schema_version, assembly.scene_identity_sha256) != (
            binding.assembly_id, binding.assembly_revision,
            binding.assembly_identity_sha256, scene.scene_id, scene.schema_version, scene.identity_hash):
        raise ValueError("leaf binding Assembly/Scene identity does not match the resolved closure")
    leaves = [leaf for leaf in assembly.leaves if leaf.full_path == binding.member_path]
    if len(leaves) != 1:
        raise ValueError("leaf selector path must resolve to exactly one Assembly member")
    member = leaves[0].member
    if binding.member_kind == "entity_member":
        if type(member) is not LogicalAssemblyEntityMemberV1 or (
            member.entity_id, member.asset_id, member.asset_version
        ) != (binding.entity_id, binding.asset_id, binding.asset_version):
            raise ValueError("owning selector is not the exact Entity/Asset member")
    elif (type(member) is not LogicalAssemblySubcomponentReferenceV1
          or member.target_kind != "control_group"
          or member.target.entity_id != binding.entity_id
          or member.target.group_id != binding.control_group_id):
        raise ValueError("reference-only selector is not the exact typed ControlGroup view")


def validate_leaf_bindings(
    scene: SceneDefinition,
    bindings: tuple[LeafProfileBindingV1, ...],
    resolved_assembly: ResolvedLogicalAssemblyV1 | None = None,
) -> tuple[LeafProfileBindingV1, ...]:
    """Validate a static set of leaves without creating writers or adapters."""
    if type(bindings) is not tuple or not bindings:
        raise TypeError("leaf binding set must be a nonempty immutable tuple")
    writers = [binding.writer_id for binding in bindings]
    if len(writers) != len(set(writers)):
        raise ValueError("duplicate leaf writer identity")
    owned_resources = []
    for binding in bindings:
        validate_leaf_binding(scene, binding, resolved_assembly)
        owned_resources.extend(binding.actuator_order)
    if len(owned_resources) != len(set(owned_resources)):
        raise ValueError("leaf bindings overlap an owned Actuator resource")
    return bindings


def validate_leaf_target_ack(
    binding: LeafProfileBindingV1,
    target: ArmPositionTargetV1 | HandPositionTargetV1,
    ack: LeafApplicationAckV1,
    *,
    expected_source_boundary: StateBoundaryIdentity,
    expected_source_clock: StateSampleClock,
    expected_application_boundary: StateBoundaryIdentity,
    expected_application_clock: StateSampleClock,
) -> LeafApplicationAckV1:
    """Cross-check a static Target/Ack against an explicit external context."""
    if type(binding) is not LeafProfileBindingV1:
        raise TypeError("Target/Ack validation requires LeafProfileBindingV1")
    if type(target) not in (ArmPositionTargetV1, HandPositionTargetV1):
        raise TypeError("Target/Ack validation requires a Position leaf Target")
    if type(ack) is not LeafApplicationAckV1:
        raise TypeError("Target/Ack validation requires LeafApplicationAckV1")
    target.validate()
    ack.validate()
    profile_kind = "arm_position" if type(target) is ArmPositionTargetV1 else "hand_position"
    if binding.profile_kind != profile_kind or ack.profile_kind != profile_kind:
        raise ValueError("Target/Ack profile kind differs from the bound leaf")
    expected_identity = (
        binding.profile_id, binding.action_schema_id, binding.writer_id,
        binding.identity_hash, binding.source_closure_sha256, binding.scene_identity_hash,
        binding.joint_order, binding.actuator_order,
    )
    target_identity = (
        target.profile_id, target.action_schema_id, target.writer_id,
        target.binding_identity_hash, target.source_closure_sha256, target.scene_identity_hash,
        target.joint_order, target.actuator_order,
    )
    ack_identity = (
        ack.profile_id, ack.action_schema_id, ack.writer_id, ack.binding_identity_hash,
        ack.source_closure_sha256, ack.scene_identity_hash, ack.joint_order, ack.actuator_order,
    )
    if target_identity != expected_identity:
        raise ValueError("Target profile/source/writer/ordered resources differ from its binding")
    if ack_identity != (binding.profile_id, binding.action_schema_id, binding.writer_id, binding.identity_hash,
                        binding.source_closure_sha256, binding.scene_identity_hash,
                        binding.joint_order, binding.actuator_order):
        raise ValueError("Ack profile/source/writer/ordered resources differ from its binding")
    if ack.target_identity_hash != target.identity_hash:
        raise ValueError("Ack does not reference the exact Target identity")
    if type(target) is ArmPositionTargetV1:
        for value, (lower, upper) in zip(
            target.action.position_rad, binding.joint_position_limits, strict=True,
        ):
            if not lower <= value <= upper:
                raise ValueError("Arm Position target exceeds its ordered joint limits")
    if (target.source_boundary, target.sample_clock) != (expected_source_boundary, expected_source_clock):
        raise ValueError("Target source boundary/clock differs from explicit context")
    if (ack.source_boundary, ack.source_sample_clock) != (expected_source_boundary, expected_source_clock):
        raise ValueError("Ack source boundary/clock differs from explicit context")
    if (ack.application_boundary, ack.application_sample_clock) != (
        expected_application_boundary, expected_application_clock
    ):
        raise ValueError("Ack application boundary/clock differs from explicit context")
    _same_episode_boundary(expected_source_boundary, expected_application_boundary)
    return ack


def panda_arm_required_state(entity_id: str, tcp_frame: FrameReference) -> LeafRequiredStateV1:
    return LeafRequiredStateV1(
        "leaf-required-state-v1", "arm_position",
        _position_requirements(ARM_POSITION_PROFILE_ID, entity_id,
                               PANDA_ARM_JOINT_IDS, tcp_frame),
        _IDENTITY_FIELDS, "evaluation_boundary",
    )


def panda_hand_required_state(
    entity_id: str, tcp_frame: FrameReference, *, force_aware: bool = False,
    actuator_id: str = "actuator8",
) -> LeafRequiredStateV1:
    profile_kind = "hand_force_aware" if force_aware else "hand_position"
    profile_id = HAND_FORCE_AWARE_PROFILE_ID if force_aware else HAND_POSITION_PROFILE_ID
    requirements = _position_requirements(
        profile_id, entity_id, PANDA_HAND_FINGER_JOINT_IDS,
        tcp_frame, (actuator_id,) if force_aware else (),
    )
    return LeafRequiredStateV1(
        "leaf-required-state-v1", profile_kind, requirements,
        _IDENTITY_FIELDS, "evaluation_boundary",
    )


def panda_hand_force_aware_dependency(
    entity_id: str,
    tcp_frame: FrameReference,
    *,
    actuator_id: str = "actuator8",
) -> HandForceAwareDependencyV1:
    return HandForceAwareDependencyV1(
        HAND_FORCE_AWARE_DEPENDENCY_SCHEMA,
        HAND_FORCE_AWARE_PROFILE_ID,
        HAND_FORCE_AWARE_ACTION_SCHEMA,
        "NOT_ADMITTED",
        panda_hand_required_state(entity_id, tcp_frame, force_aware=True, actuator_id=actuator_id),
        (
            "raw_signed_force_N", "canonical_closing_force_N", "source_transmission_identity",
            "unit", "sign_convention", "validity", "sample_phase", "native_sample_index",
            "sequence", "state_revision", "configuration_revision", "episode_id",
            "reset_sample_id", "evaluation_boundary_id", "provider_identity",
            "provider_build_identity", "backend", "sample_cadence",
        ),
        "N", "N", "NOT_AUDITED", "NOT_AUDITED", True,
        "No leaf force source/sign/phase/freshness audit or R02b force adapter exists; this refusal is independent of Position.",
    )
