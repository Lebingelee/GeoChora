"""R02b provider-neutral leaf preflight and dispatch owner.

Only the existing RuntimeSession/provider boundary may implement the protocol
below.  S1 uses a synthetic fixture implementation; no native model or
Provider-private storage is accessed here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import re
from typing import Protocol, runtime_checkable

from ...artifacts import (
    ActuatorReference,
    CanonicalStatePublicationV1,
    ExecutionSpecV1,
    FrameReference,
    JointReference,
    RendererSelectionV1,
    SceneDefinition,
    StateBoundaryIdentity,
    StateRequirements,
    StateSampleClock,
    TypedFrameStateValue,
    TypedJointStateValue,
)
from ...controllers.canonical.leaf_profiles import (
    ARM_POSITION_ACTION_SCHEMA,
    ARM_POSITION_PROFILE_ID,
    HAND_POSITION_ACTION_SCHEMA,
    HAND_POSITION_PROFILE_ID,
    ArmPositionActionV1,
    ArmPositionTargetV1,
    HandPositionActionV1,
    HandPositionTargetV1,
    LeafApplicationAckV1,
    LeafProfileBindingV1,
    validate_leaf_target_ack,
)
from ...controllers.canonical.leaf_plan import EffectiveLeafPlanV1, EffectiveLeafEntryV1
from ...artifacts.contracts import _name
from ...controllers.canonical.controller import absolute_joint_position_servo
from ...environment.types import ExecutionFaultV1, attach_execution_fault
from ...robots.gripper import (
    position_gripper_ctrl_for_opening,
    position_gripper_servo_opening,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _sha(value, label):
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")


def _token(value, label):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise ValueError(f"{label} must be a stable nonempty token")


def _stable_identity(value, label):
    if (type(value) is not str or not value or value.strip() != value
            or any(character.isspace() or ord(character) < 32 for character in value)):
        raise ValueError(f"{label} must be a stable nonempty identity string")


@dataclass(frozen=True)
class LeafNativeJointMappingV1:
    schema_version: str
    canonical_joint: JointReference
    native_name: str
    native_joint_id: int
    qpos_address: int
    dof_address: int
    position_unit: str

    def __post_init__(self):
        if self.schema_version != "leaf-native-joint-mapping-v1":
            raise ValueError("unsupported leaf native Joint mapping schema")
        if type(self.canonical_joint) is not JointReference:
            raise TypeError("native Joint mapping requires a canonical JointReference")
        _token(self.native_name, "native Joint name")
        if self.position_unit not in {"radian", "meter"}:
            raise ValueError("native Joint position unit must be radian or meter")
        for name in ("native_joint_id", "qpos_address", "dof_address"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class LeafNativeActuatorMappingV1:
    schema_version: str
    canonical_actuator: ActuatorReference
    native_name: str
    native_actuator_id: int
    ctrl_slot: int
    ctrlrange: tuple[float, float]
    command_unit: str
    transmission_target_kind: str
    transmission_target_id: str

    def __post_init__(self):
        if self.schema_version != "leaf-native-actuator-mapping-v1":
            raise ValueError("unsupported leaf native Actuator mapping schema")
        if type(self.canonical_actuator) is not ActuatorReference:
            raise TypeError("native Actuator mapping requires a canonical ActuatorReference")
        _token(self.native_name, "native Actuator name")
        if self.command_unit not in {"radian", "native_ctrl"}:
            raise ValueError("unsupported native actuator command unit")
        if self.transmission_target_kind not in {"joint", "tendon"}:
            raise ValueError("unsupported native actuator transmission kind")
        _stable_identity(self.transmission_target_id, "native transmission target")
        for name in ("native_actuator_id", "ctrl_slot"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if (type(self.ctrlrange) is not tuple or len(self.ctrlrange) != 2
                or any(type(value) not in (int, float) or isinstance(value, bool)
                       or not math.isfinite(value) for value in self.ctrlrange)
                or self.ctrlrange[0] >= self.ctrlrange[1]):
            raise ValueError("native actuator ctrlrange must contain two finite increasing values")


@dataclass(frozen=True)
class LeafNativeFrameMappingV1:
    schema_version: str
    canonical_frame: FrameReference
    native_name: str
    native_body_id: int

    def __post_init__(self):
        if self.schema_version != "leaf-native-frame-mapping-v1":
            raise ValueError("unsupported leaf native Frame mapping schema")
        if type(self.canonical_frame) is not FrameReference:
            raise TypeError("native Frame mapping requires a canonical FrameReference")
        _token(self.native_name, "native Frame name")
        if type(self.native_body_id) is not int or self.native_body_id < 0:
            raise ValueError("native body ID must be a non-negative integer")


@dataclass(frozen=True)
class LeafNativeTendonMappingV1:
    """Bind one logical Hand tendon identity to its exact native name."""

    schema_version: str
    tendon_identity: str
    native_name: str

    def __post_init__(self):
        if self.schema_version != "leaf-native-tendon-mapping-v1":
            raise ValueError("unsupported leaf native tendon mapping schema")
        _stable_identity(self.tendon_identity, "canonical tendon identity")
        _token(self.native_name, "native tendon name")


@dataclass(frozen=True)
class IsaacNamedPositionDriveV1:
    """One canonical scalar Joint mapped to a public named DOF position drive."""

    schema_version: str
    canonical_joint: JointReference
    native_dof_name: str
    native_dof_index: int
    position_unit: str
    lower_limit: float
    upper_limit: float

    def __post_init__(self):
        if self.schema_version != 'isaac-named-position-drive-v1':
            raise ValueError('unsupported Isaac named Position drive schema')
        if type(self.canonical_joint) is not JointReference:
            raise TypeError('Isaac named Position drive requires JointReference')
        self.canonical_joint.validate()
        _token(self.native_dof_name, 'native DOF name')
        if type(self.native_dof_index) is not int or self.native_dof_index < 0:
            raise ValueError('native DOF index must be a nonnegative integer')
        if self.position_unit not in {'radian', 'meter'}:
            raise ValueError('native position drive unit must be radian or meter')
        if (type(self.lower_limit) not in (int, float)
                or type(self.upper_limit) not in (int, float)
                or not math.isfinite(float(self.lower_limit))
                or not math.isfinite(float(self.upper_limit))
                or self.lower_limit >= self.upper_limit):
            raise ValueError('native DOF limits must be finite and increasing')


@dataclass(frozen=True)
class IsaacNamedPositionDriveReceiptV1:
    """Synthetic S1 receipt for named Panda DOF drives; not runtime admission."""

    schema_version: str
    provenance_kind: str
    scene_identity_sha256: str
    source_closure_sha256: str
    execution_identity_sha256: str
    provider_build_identity: str
    physics_profile: str
    backend: str
    device: str
    determinism_mode: str
    physics_dt_s: float
    control_substeps: int
    writer_id: str
    native_dof_count: int
    drives: tuple[IsaacNamedPositionDriveV1, ...]

    def __post_init__(self):
        if self.schema_version != 'isaac-named-position-drive-receipt-v1':
            raise ValueError('unsupported Isaac named Position drive receipt schema')
        if self.provenance_kind != 'synthetic_fixture':
            raise ValueError('F03 named Position drive receipt must remain synthetic_fixture')
        for value, label in (
            (self.scene_identity_sha256, 'Scene'),
            (self.source_closure_sha256, 'source closure'),
            (self.execution_identity_sha256, 'ExecutionSpec'),
        ):
            _sha(value, label)
        for value, label in (
            (self.provider_build_identity, 'provider build'),
            (self.physics_profile, 'physics profile'),
            (self.backend, 'backend'),
            (self.determinism_mode, 'determinism mode'),
        ):
            _token(value, label)
        # Canonical writer identities are Entity-qualified (for example
        # ``panda-main/position-servo-v1``), so they are stable identifiers,
        # not simple provider tokens.
        _stable_identity(self.writer_id, 'writer ID')
        if (type(self.physics_dt_s) not in (int, float)
                or isinstance(self.physics_dt_s, bool)
                or not math.isfinite(float(self.physics_dt_s))
                or float(self.physics_dt_s) != 0.002
                or type(self.control_substeps) is not int
                or self.control_substeps != 5):
            raise ValueError('F03 drive receipt requires the 2 ms / five-substep timebase')
        if (self.backend, self.device, self.determinism_mode) != ('cuda', 'cuda:0', 'best_effort'):
            raise ValueError('F03 target execution is Isaac CUDA cuda:0 with best_effort determinism')
        if type(self.device) is not str:
            raise TypeError('F03 target device must be a string')
        if self.provider_build_identity != 'isaacsim-6.2.0.0':
            raise ValueError('F03 target drive receipt requires Isaac Sim 6.2.0.0')
        if type(self.native_dof_count) is not int or self.native_dof_count != 9:
            raise ValueError('F03 Panda drive receipt requires exactly nine named scalar DOFs')
        if type(self.drives) is not tuple or any(type(item) is not IsaacNamedPositionDriveV1 for item in self.drives):
            raise TypeError('drive receipt requires an immutable tuple of exact named drive entries')
        expected = {
            JointReference('panda-main', f'joint{index}'): (f'panda_joint{index}', 'radian')
            for index in range(1, 8)
        }
        expected.update({
            JointReference('panda-main', 'finger_joint1'): ('panda_finger_joint1', 'meter'),
            JointReference('panda-main', 'finger_joint2'): ('panda_finger_joint2', 'meter'),
        })
        by_joint = {}
        for drive in self.drives:
            if drive.canonical_joint in by_joint:
                raise ValueError('duplicate canonical Joint in Isaac drive receipt')
            by_joint[drive.canonical_joint] = drive
        if set(by_joint) != set(expected):
            raise ValueError('Isaac drive receipt must exactly cover seven Arm and two finger Joints')
        if any((drive.native_dof_name, drive.position_unit) != expected[joint]
               for joint, drive in by_joint.items()):
            raise ValueError('Isaac native DOF name or unit differs from the F03 Panda mapping')
        indices = [drive.native_dof_index for drive in self.drives]
        names = [drive.native_dof_name for drive in self.drives]
        if sorted(indices) != list(range(9)) or len(names) != len(set(names)):
            raise ValueError('Isaac native DOF indices must be a permutation of nine unique named DOFs')

    @property
    def identity_sha256(self) -> str:
        payload = {
            'schema_version': self.schema_version,
            'provenance_kind': self.provenance_kind,
            'scene_identity_sha256': self.scene_identity_sha256,
            'source_closure_sha256': self.source_closure_sha256,
            'execution_identity_sha256': self.execution_identity_sha256,
            'provider_build_identity': self.provider_build_identity,
            'physics_profile': self.physics_profile,
            'backend': self.backend,
            'device': self.device,
            'determinism_mode': self.determinism_mode,
            'physics_dt_s': float(self.physics_dt_s),
            'control_substeps': self.control_substeps,
            'writer_id': self.writer_id,
            'native_dof_count': self.native_dof_count,
            'drives': [
                (item.canonical_joint.entity_id, item.canonical_joint.joint_id,
                 item.native_dof_name, item.native_dof_index, item.position_unit,
                 float(item.lower_limit), float(item.upper_limit))
                for item in self.drives
            ],
        }
        return _digest(payload)

    def commands(self, arm_position: Mapping[str, float], hand_opening_m: float):
        """Resolve by native name and return index-ordered per-DOF targets."""
        expected_arm = {f'panda-main/joint{index}' for index in range(1, 8)}
        if not isinstance(arm_position, Mapping) or set(arm_position) != expected_arm:
            raise ValueError('Arm Position request must exactly cover canonical joint1 through joint7')
        values = dict(arm_position)
        for name, value in values.items():
            if type(name) is not str or type(value) not in (int, float) or not math.isfinite(float(value)):
                raise ValueError('Arm Position targets must be finite non-boolean numbers')
        if type(hand_opening_m) not in (int, float) or not math.isfinite(float(hand_opening_m)):
            raise ValueError('Hand opening target must be a finite non-boolean number')
        if not 0.0 <= float(hand_opening_m) <= 0.08:
            raise ValueError('Hand opening target must be within [0, 0.08] metres')
        targets = {JointReference('panda-main', name.split('/', 1)[1]): float(value)
                   for name, value in values.items()}
        half_opening = float(hand_opening_m) / 2.0
        targets.update({
            JointReference('panda-main', 'finger_joint1'): half_opening,
            JointReference('panda-main', 'finger_joint2'): half_opening,
        })
        by_index = []
        for drive in self.drives:
            value = targets[drive.canonical_joint]
            if value < drive.lower_limit or value > drive.upper_limit:
                raise ValueError(f'native target exceeds the declared limit for {drive.native_dof_name}')
            by_index.append((drive.native_dof_index, drive.native_dof_name, float(value)))
        return tuple(sorted(by_index))


def compile_isaac_named_position_drive_receipt_v1(
    *, execution: ExecutionSpecV1, scene_identity_sha256: str,
    source_closure_sha256: str, provider_build_identity: str,
    writer_id: str, native_dof_names: tuple[str, ...],
    native_position_limits: Mapping[str, tuple[float, float]],
) -> IsaacNamedPositionDriveReceiptV1:
    """Compile an explicitly synthetic receipt from public-style DOF metadata."""
    if type(execution) is not ExecutionSpecV1:
        raise TypeError('named Isaac drive receipt requires ExecutionSpecV1')
    execution.validate()
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.determinism_mode) != ('isaacsim', 'cuda', 'cuda:0', 'best_effort'):
        raise ValueError('named Isaac drive receipt requires the declared CUDA 0 best_effort execution')
    if (type(execution.render_default) is not RendererSelectionV1
            or (execution.render_default.provider, execution.render_default.backend,
                execution.render_default.profile, execution.render_default.device)
            != ('none', 'cpu', 'none', None)):
        raise ValueError('F03 named drive receipt is state-only and does not admit rendering')
    if execution.camera_overrides:
        raise ValueError('F03 named drive receipt does not admit camera overrides')
    if type(native_dof_names) is not tuple or any(type(name) is not str or not name for name in native_dof_names):
        raise TypeError('public DOF metadata must be an immutable tuple of names')
    if len(native_dof_names) != 9 or len(set(native_dof_names)) != 9:
        raise ValueError('public DOF metadata must contain nine unique scalar names')
    limits = dict(native_position_limits)
    if set(limits) != set(native_dof_names):
        raise ValueError('public DOF limits must exactly cover the named DOF metadata')
    expected = [
        *((JointReference('panda-main', f'joint{index}'), f'panda_joint{index}', 'radian')
          for index in range(1, 8)),
        (JointReference('panda-main', 'finger_joint1'), 'panda_finger_joint1', 'meter'),
        (JointReference('panda-main', 'finger_joint2'), 'panda_finger_joint2', 'meter'),
    ]
    by_name = {name: (joint, unit) for joint, name, unit in expected}
    if set(native_dof_names) != set(by_name):
        raise ValueError('public DOF names differ from the exact Panda Arm+Hand name set')
    drives = []
    for index, name in enumerate(native_dof_names):
        limits_for_name = limits[name]
        if type(limits_for_name) not in (tuple, list) or len(limits_for_name) != 2:
            raise TypeError(f'public DOF limits for {name!r} must be a two-value tuple/list')
        joint, unit = by_name[name]
        drives.append(IsaacNamedPositionDriveV1(
            'isaac-named-position-drive-v1', joint, name, index, unit,
            limits_for_name[0], limits_for_name[1],
        ))
    return IsaacNamedPositionDriveReceiptV1(
        'isaac-named-position-drive-receipt-v1', 'synthetic_fixture',
        scene_identity_sha256, source_closure_sha256, execution.identity_hash,
        provider_build_identity, execution.physics_profile, execution.physics_backend,
        execution.physics_device, execution.determinism_mode, 0.002, 5,
        writer_id, len(native_dof_names), tuple(drives),
    )


@dataclass(frozen=True)
class LeafMaterializationReceiptV1:
    """Explicit ordered canonical/native map; synthetic receipts are S1 only."""

    schema_version: str
    provenance_kind: str
    scene_identity_sha256: str
    source_closure_sha256: str
    effective_plan_identity_sha256: str
    provider_name: str
    provider_version: str
    provider_build_sha256: str
    backend: str
    materialization_id: str
    configuration_revision: str
    nq: int
    nv: int
    nu: int
    njnt: int
    nbody: int
    neq: int
    ntendon: int
    joints: tuple[LeafNativeJointMappingV1, ...]
    actuators: tuple[LeafNativeActuatorMappingV1, ...]
    frames: tuple[LeafNativeFrameMappingV1, ...]
    tendons: tuple[LeafNativeTendonMappingV1, ...]
    equality_identities: tuple[str, ...]
    fixed_attachment_receipt_identity_sha256: str | None = None

    def __post_init__(self):
        if self.schema_version != "leaf-materialization-receipt-v1":
            raise ValueError("unsupported leaf materialization receipt schema")
        if self.provenance_kind not in {"synthetic_fixture", "provider_materialization"}:
            raise ValueError("materialization receipt provenance must be explicit")
        for value, label in ((self.scene_identity_sha256, "Scene"),
                             (self.source_closure_sha256, "source closure"),
                             (self.effective_plan_identity_sha256, "effective plan"),
                             (self.provider_build_sha256, "Provider build")):
            _sha(value, label)
        if self.fixed_attachment_receipt_identity_sha256 is not None:
            _sha(self.fixed_attachment_receipt_identity_sha256, "fixed Attachment model receipt")
        for value, label in ((self.provider_name, "Provider"),
                             (self.provider_version, "Provider version"),
                             (self.backend, "backend"),
                             (self.materialization_id, "materialization ID"),
                             (self.configuration_revision, "configuration revision")):
            _token(value, label)
        for name in ("nq", "nv", "nu", "njnt", "nbody", "neq", "ntendon"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"native dimension {name} must be a non-negative integer")
        for name, item_type in (("joints", LeafNativeJointMappingV1),
                                ("actuators", LeafNativeActuatorMappingV1),
                                ("frames", LeafNativeFrameMappingV1),
                                ("tendons", LeafNativeTendonMappingV1)):
            values = getattr(self, name)
            if type(values) is not tuple or any(type(item) is not item_type for item in values):
                raise TypeError(f"{name} must be an immutable tuple of exact mapping values")
        for name in ("equality_identities",):
            values = tuple(getattr(self, name))
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be unique")
            object.__setattr__(self, name, values)
            for value in values:
                _stable_identity(value, name)

    @property
    def identity_sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "provenance_kind": self.provenance_kind,
            "scene_identity_sha256": self.scene_identity_sha256,
            "source_closure_sha256": self.source_closure_sha256,
            "effective_plan_identity_sha256": self.effective_plan_identity_sha256,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "provider_build_sha256": self.provider_build_sha256,
            "backend": self.backend,
            "materialization_id": self.materialization_id,
            "configuration_revision": self.configuration_revision,
            "dimensions": (self.nq, self.nv, self.nu, self.njnt, self.nbody, self.neq, self.ntendon),
            "joints": [asdict(item) for item in self.joints],
            "actuators": [asdict(item) for item in self.actuators],
            "frames": [asdict(item) for item in self.frames],
            "tendons": [asdict(item) for item in self.tendons],
            "equality_identities": self.equality_identities,
        }
        if self.fixed_attachment_receipt_identity_sha256 is not None:
            payload["fixed_attachment_receipt_identity_sha256"] = self.fixed_attachment_receipt_identity_sha256
        return _digest(payload)

    def validate_against_plan(self, plan: EffectiveLeafPlanV1) -> None:
        if type(plan) is not EffectiveLeafPlanV1:
            raise TypeError("materialization mapping requires an EffectiveLeafPlanV1")
        if (self.scene_identity_sha256, self.source_closure_sha256,
                self.effective_plan_identity_sha256, self.provider_name,
                self.provider_version, self.provider_build_sha256, self.backend) != (
                plan.scene_identity_sha256, plan.source_closure_sha256,
                plan.identity_sha256, plan.provider_name, plan.provider_version,
                plan.provider_build_sha256, plan.backend):
            raise ValueError("materialization receipt is bound to another plan/source/provider")
        if (plan.fixed_attachment_plan_identity_sha256 is not None
                and self.fixed_attachment_receipt_identity_sha256 is None):
            raise ValueError("attached leaf receipt omits its model-bound Attachment receipt")
        if (plan.fixed_attachment_plan_identity_sha256 is None
                and self.fixed_attachment_receipt_identity_sha256 is not None):
            raise ValueError("non-attached leaf receipt cannot carry a fixed Attachment receipt")
        expected_joints = {ref for entry in plan.leaves for ref in entry.binding.joint_order}
        expected_actuators = {ref for entry in plan.leaves for ref in entry.binding.actuator_order}
        expected_frames = {entry.binding.tcp_frame for entry in plan.leaves}
        expected_tendons = {entry.binding.tendon_identity for entry in plan.leaves
                            if entry.binding.profile_kind == "hand_position"}
        expected_equalities = {entry.binding.equality_identity for entry in plan.leaves
                               if entry.binding.profile_kind == "hand_position"}
        joint_by_ref = {}
        for item in self.joints:
            key = item.canonical_joint
            if key in joint_by_ref:
                raise ValueError("duplicate canonical Joint in native mapping")
            joint_by_ref[key] = item
        actuator_by_ref = {}
        for item in self.actuators:
            key = item.canonical_actuator
            if key in actuator_by_ref:
                raise ValueError("duplicate canonical Actuator in native mapping")
            actuator_by_ref[key] = item
        frame_by_ref = {}
        for item in self.frames:
            key = item.canonical_frame
            if key in frame_by_ref:
                raise ValueError("duplicate canonical Frame in native mapping")
            frame_by_ref[key] = item
        if set(joint_by_ref) != expected_joints:
            raise ValueError("native Joint mapping must exactly cover plan Joint refs")
        if set(actuator_by_ref) != expected_actuators:
            raise ValueError("native Actuator mapping must exactly cover plan Actuator refs")
        if set(frame_by_ref) != expected_frames:
            raise ValueError("native Frame mapping must exactly cover plan TCP refs")
        joint_ids = [item.native_joint_id for item in self.joints]
        joint_names = [item.native_name for item in self.joints]
        qpos = [item.qpos_address for item in self.joints]
        dofs = [item.dof_address for item in self.joints]
        if any(len(values) != len(set(values)) for values in (joint_ids, joint_names, qpos, dofs)):
            raise ValueError("native Joint names, IDs and qpos/dof addresses must be unique")
        if any(item.native_joint_id >= self.njnt or item.qpos_address >= self.nq
               or item.dof_address >= self.nv for item in self.joints):
            raise ValueError("native Joint mapping exceeds model dimensions")
        for entry in plan.leaves:
            for ref in entry.binding.joint_order:
                if joint_by_ref[ref].position_unit != entry.binding.joint_position_unit:
                    raise ValueError("native Joint mapping unit differs from the canonical leaf unit")
        actuator_ids = [item.native_actuator_id for item in self.actuators]
        actuator_names = [item.native_name for item in self.actuators]
        slots = [item.ctrl_slot for item in self.actuators]
        if (len(actuator_ids) != len(set(actuator_ids))
                or len(actuator_names) != len(set(actuator_names))
                or len(slots) != len(set(slots))):
            raise ValueError("native Actuator names, IDs and writable ctrl slots must be unique")
        if any(item.native_actuator_id >= self.nu or item.ctrl_slot >= self.nu
               for item in self.actuators):
            raise ValueError("native Actuator mapping exceeds nu/ctrl dimensions")
        if len(actuator_by_ref) != self.nu:
            raise ValueError("native actuator mapping must cover every native actuator and ctrl slot")
        body_ids = [item.native_body_id for item in self.frames]
        frame_names = [item.native_name for item in self.frames]
        if (len(body_ids) != len(set(body_ids)) or len(frame_names) != len(set(frame_names))
                or any(body_id >= self.nbody for body_id in body_ids)):
            raise ValueError("native TCP Body IDs must be unique for the selected frames")
        tendon_ids = [item.tendon_identity for item in self.tendons]
        tendon_names = [item.native_name for item in self.tendons]
        if (len(tendon_ids) != len(set(tendon_ids))
                or len(tendon_names) != len(set(tendon_names))):
            raise ValueError("canonical and native tendon mappings must be unique")
        tendon_by_identity = {item.tendon_identity: item for item in self.tendons}
        if set(tendon_by_identity) != expected_tendons or set(self.equality_identities) != expected_equalities:
            raise ValueError("native Hand tendon/equality identities must exactly cover planned Hand leaves")
        for entry in plan.leaves:
            binding = entry.binding
            if binding.profile_kind == "hand_position":
                if binding.tendon_identity not in tendon_by_identity:
                    raise ValueError("native receipt omits the Hand split tendon identity")
                if binding.equality_identity not in self.equality_identities:
                    raise ValueError("native receipt omits the Hand finger equality identity")
                if self.neq < 1 or self.ntendon < 1:
                    raise ValueError("native dimensions omit the required Hand equality/tendon")
            for pair in binding.joint_actuator_bindings:
                actuator = actuator_by_ref[pair.actuator]
                native_joint_name = next(
                    item.native_name for item in self.joints if item.canonical_joint == pair.joint
                )
                if (actuator.command_unit, actuator.transmission_target_kind,
                        actuator.transmission_target_id) != (
                        "radian", "joint", native_joint_name):
                    raise ValueError("Arm Actuator transmission differs from its explicit Joint mapping")
                # Native actuator command ranges and canonical Joint position
                # limits are distinct source facts.  The provider adapter
                # verifies both against its compiled model; requiring equality
                # here incorrectly rejects Panda's inherited <general>
                # ctrlrange on joints whose authored Joint range is narrower.
            if binding.profile_kind == "hand_position":
                actuator = actuator_by_ref[binding.actuator_order[0]]
                if (actuator.command_unit, actuator.ctrlrange,
                        actuator.transmission_target_kind, actuator.transmission_target_id) != (
                        "native_ctrl", binding.native_ctrlrange, "tendon",
                        tendon_by_identity[binding.tendon_identity].native_name):
                    raise ValueError("Hand actuator map differs from its single tendon/ctrl contract")


@dataclass(frozen=True)
class LeafRuntimeClockV1:
    schema_version: str
    boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    configuration_revision: str

    def __post_init__(self):
        if self.schema_version != "leaf-runtime-clock-v1":
            raise ValueError("unsupported leaf runtime clock schema")
        if type(self.boundary) is not StateBoundaryIdentity or type(self.sample_clock) is not StateSampleClock:
            raise TypeError("leaf runtime clock requires typed boundary and sample clock")
        _token(self.configuration_revision, "runtime configuration revision")
        if (self.sample_clock.clock_domain != "evaluation_boundary"
                or self.sample_clock.sample_index != self.boundary.control_step):
            raise ValueError("runtime sample clock is not the named evaluation boundary")


@dataclass(frozen=True)
class LeafActionRequestV1:
    schema_version: str
    writer_id: str
    action: ArmPositionActionV1 | HandPositionActionV1

    def __post_init__(self):
        if self.schema_version != "leaf-action-request-v1":
            raise ValueError("unsupported leaf action request schema")
        _name(self.writer_id)
        if type(self.action) not in (ArmPositionActionV1, HandPositionActionV1):
            raise TypeError("leaf action request requires a Position Action v1 value")


@dataclass(frozen=True)
class LeafControlIntervalRequestV1:
    schema_version: str
    effective_plan_identity_sha256: str
    materialization: LeafMaterializationReceiptV1
    publication: CanonicalStatePublicationV1
    configuration_revision: str
    actions: tuple[LeafActionRequestV1, ...]
    phase: str = "evaluation_boundary"

    def __post_init__(self):
        if self.schema_version != "leaf-control-interval-request-v1":
            raise ValueError("unsupported leaf control interval request schema")
        _sha(self.effective_plan_identity_sha256, "effective plan")
        if type(self.materialization) is not LeafMaterializationReceiptV1:
            raise TypeError("leaf control request requires an explicit materialization receipt")
        if type(self.publication) is not CanonicalStatePublicationV1:
            raise TypeError("leaf control request requires CanonicalStatePublicationV1")
        _token(self.configuration_revision, "configuration revision")
        if type(self.actions) is not tuple or any(type(item) is not LeafActionRequestV1 for item in self.actions):
            raise TypeError("leaf actions must be an immutable tuple")
        if self.phase != "evaluation_boundary":
            raise ValueError("leaf control cannot dispatch during reset or an incomplete boundary")


@dataclass(frozen=True)
class LeafActuatorSlotValueV1:
    schema_version: str
    actuator: ActuatorReference
    ctrl_slot: int
    value: float

    def __post_init__(self):
        if self.schema_version != "leaf-actuator-slot-value-v1":
            raise ValueError("unsupported leaf slot value schema")
        if type(self.actuator) is not ActuatorReference:
            raise TypeError("leaf ctrl slot requires an ActuatorReference")
        if type(self.ctrl_slot) is not int or self.ctrl_slot < 0:
            raise ValueError("leaf ctrl slot must be a non-negative integer")
        if isinstance(self.value, bool) or not math.isfinite(self.value):
            raise ValueError("leaf ctrl command must be finite")

    @classmethod
    def from_mapping(cls, value):
        expected = {"schema_version", "actuator", "ctrl_slot", "value"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("leaf actuator slot mapping has unknown or missing fields")
        if type(value["ctrl_slot"]) is not int or isinstance(value["value"], bool) or type(value["value"]) not in (int, float):
            raise TypeError("leaf actuator slot mapping has invalid numeric types")
        return cls(
            value["schema_version"], ActuatorReference.from_mapping(value["actuator"]),
            value["ctrl_slot"], float(value["value"]),
        )


@dataclass(frozen=True)
class LeafPreparedCommandV1:
    schema_version: str
    writer_id: str
    profile_kind: str
    effective_plan_identity_sha256: str
    binding_identity_sha256: str
    effective_configuration_identity_sha256: str
    materialization_identity_sha256: str
    state_boundary: StateBoundaryIdentity
    state_configuration_revision: str
    target: ArmPositionTargetV1 | HandPositionTargetV1
    slot_values: tuple[LeafActuatorSlotValueV1, ...]
    requested_opening_m: float | None = None
    servo_opening_m: float | None = None
    native_ctrl: float | None = None

    def __post_init__(self):
        if self.schema_version != "leaf-prepared-command-v1":
            raise ValueError("unsupported prepared leaf command schema")
        _name(self.writer_id)
        _token(self.state_configuration_revision, "state_configuration_revision")
        for name in ("effective_plan_identity_sha256", "binding_identity_sha256",
                     "effective_configuration_identity_sha256", "materialization_identity_sha256"):
            _sha(getattr(self, name), name)
        if self.profile_kind not in {"arm_position", "hand_position"}:
            raise ValueError("prepared command must use an admitted Position leaf")
        if type(self.state_boundary) is not StateBoundaryIdentity:
            raise TypeError("prepared command requires its exact source boundary")
        if type(self.target) not in (ArmPositionTargetV1, HandPositionTargetV1):
            raise TypeError("prepared command requires an R02a Position Target")
        expected_target = ArmPositionTargetV1 if self.profile_kind == "arm_position" else HandPositionTargetV1
        if type(self.target) is not expected_target:
            raise ValueError("prepared command profile kind differs from its Target schema")
        if (self.target.writer_id != self.writer_id
                or self.target.binding_identity_hash != self.binding_identity_sha256
                or self.target.source_boundary != self.state_boundary):
            raise ValueError("prepared command identity differs from its Target/source boundary")
        if type(self.slot_values) is not tuple or not self.slot_values:
            raise TypeError("prepared command must own a nonempty immutable slot patch")
        if any(type(item) is not LeafActuatorSlotValueV1 for item in self.slot_values):
            raise TypeError("prepared command slot patch contains an unsupported value")
        slots = tuple(item.ctrl_slot for item in self.slot_values)
        if len(slots) != len(set(slots)):
            raise ValueError("prepared command cannot write a ctrl slot twice")
        if tuple(item.actuator for item in self.slot_values) != tuple(self.target.actuator_order):
            raise ValueError("prepared command slot order differs from its Target actuator order")
        optional = (self.requested_opening_m, self.servo_opening_m, self.native_ctrl)
        if self.profile_kind == "hand_position":
            if any(value is None or isinstance(value, bool) or not math.isfinite(value) for value in optional):
                raise ValueError("Hand prepared command must retain request, servo and native ctrl values")
            if not 0 <= self.requested_opening_m <= 0.08 or not 0 <= self.servo_opening_m <= 0.08:
                raise ValueError("Hand prepared opening values are outside the source range")
            if self.native_ctrl != self.slot_values[0].value:
                raise ValueError("Hand native ctrl value differs from the owned slot patch")
        elif any(value is not None for value in optional):
            raise ValueError("Arm command cannot carry Hand opening metadata")

    @classmethod
    def from_mapping(cls, value):
        expected = {
            "schema_version", "writer_id", "profile_kind", "effective_plan_identity_sha256",
            "binding_identity_sha256", "effective_configuration_identity_sha256",
            "materialization_identity_sha256", "state_boundary", "state_configuration_revision",
            "target", "slot_values", "requested_opening_m", "servo_opening_m", "native_ctrl",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("prepared leaf command mapping has unknown or missing fields")
        if type(value["slot_values"]) not in (list, tuple):
            raise TypeError("prepared leaf command slot_values must be an ordered array")
        if type(value["profile_kind"]) is not str:
            raise TypeError("prepared leaf command profile_kind must be a string")
        target_mapping = value["target"]
        if not isinstance(target_mapping, Mapping):
            raise TypeError("prepared leaf command target must be a mapping")
        from ...controllers.canonical.leaf_profiles import decode_leaf_target
        return cls(
            value["schema_version"], value["writer_id"], value["profile_kind"],
            value["effective_plan_identity_sha256"], value["binding_identity_sha256"],
            value["effective_configuration_identity_sha256"], value["materialization_identity_sha256"],
            StateBoundaryIdentity.from_mapping(value["state_boundary"]),
            value["state_configuration_revision"], decode_leaf_target(target_mapping),
            tuple(LeafActuatorSlotValueV1.from_mapping(item) for item in value["slot_values"]),
            value["requested_opening_m"], value["servo_opening_m"], value["native_ctrl"],
        )

    def to_mapping(self):
        # Keep the existing asdict payload shape and identity hash semantics.
        return asdict(self)

    @property
    def command_identity_sha256(self) -> str:
        return _digest({
            "schema_version": self.schema_version,
            "writer_id": self.writer_id,
            "profile_kind": self.profile_kind,
            "effective_plan_identity_sha256": self.effective_plan_identity_sha256,
            "binding_identity_sha256": self.binding_identity_sha256,
            "effective_configuration_identity_sha256": self.effective_configuration_identity_sha256,
            "materialization_identity_sha256": self.materialization_identity_sha256,
            "state_boundary": self.state_boundary.to_mapping(),
            "state_configuration_revision": self.state_configuration_revision,
            "target_identity_sha256": self.target.identity_hash,
            "slot_values": [asdict(item) for item in self.slot_values],
            "requested_opening_m": self.requested_opening_m,
            "servo_opening_m": self.servo_opening_m,
            "native_ctrl": self.native_ctrl,
        })


@dataclass(frozen=True)
class LeafActuatorPatchV1:
    schema_version: str
    writer_id: str
    command_identity_sha256: str
    target: ArmPositionTargetV1 | HandPositionTargetV1
    effective_plan_identity_sha256: str
    materialization_identity_sha256: str
    state_configuration_revision: str
    slot_values: tuple[LeafActuatorSlotValueV1, ...]

    def __post_init__(self):
        if self.schema_version != "leaf-actuator-patch-v1":
            raise ValueError("unsupported leaf actuator patch schema")
        _name(self.writer_id)
        for value in (self.command_identity_sha256, self.effective_plan_identity_sha256,
                      self.materialization_identity_sha256):
            _sha(value, "leaf patch identity")
        _token(self.state_configuration_revision, "leaf patch configuration revision")
        if type(self.target) not in (ArmPositionTargetV1, HandPositionTargetV1):
            raise TypeError("leaf actuator patch requires the exact prepared Target")
        if type(self.slot_values) is not tuple or not self.slot_values:
            raise TypeError("leaf actuator patch must be nonempty and immutable")
        if len({item.ctrl_slot for item in self.slot_values}) != len(self.slot_values):
            raise ValueError("leaf actuator patch contains duplicate ctrl slots")


@dataclass(frozen=True)
class LeafApplyResultV1:
    schema_version: str
    writer_id: str
    command_identity_sha256: str
    materialization_identity_sha256: str
    applied_slots: tuple[int, ...]
    ack: LeafApplicationAckV1

    def __post_init__(self):
        if self.schema_version != "leaf-apply-result-v1":
            raise ValueError("unsupported leaf apply result schema")
        _name(self.writer_id)
        _sha(self.command_identity_sha256, "applied command")
        _sha(self.materialization_identity_sha256, "apply materialization")
        if type(self.applied_slots) is not tuple or any(type(slot) is not int or slot < 0 for slot in self.applied_slots):
            raise TypeError("applied slots must be non-negative ordered native slots")
        if type(self.ack) is not LeafApplicationAckV1:
            raise TypeError("leaf apply result requires the actual typed application Ack")


@dataclass(frozen=True)
class LeafDispatchProgressV1:
    schema_version: str
    effective_plan_identity_sha256: str
    source_boundary_id: str
    attempted_writers: tuple[str, ...]
    applied_writers: tuple[str, ...]
    unknown_writers: tuple[str, ...]
    acknowledged_writers: tuple[str, ...]
    ack_identity_hashes: tuple[tuple[str, str], ...]
    command_identity_hashes: tuple[tuple[str, str], ...]
    prepared_commands: tuple[LeafPreparedCommandV1, ...]
    returned_apply_results: tuple[LeafApplyResultV1, ...]
    failed_writer: str | None
    failure_phase: str
    fault: ExecutionFaultV1

    def __post_init__(self):
        if self.schema_version != "leaf-dispatch-progress-v1":
            raise ValueError("unsupported leaf dispatch progress schema")
        _sha(self.effective_plan_identity_sha256, "dispatch plan")
        _token(self.source_boundary_id, "dispatch boundary")
        for name in ("attempted_writers", "applied_writers", "unknown_writers", "acknowledged_writers"):
            values = getattr(self, name)
            if type(values) is not tuple or len(values) != len(set(values)):
                raise ValueError(f"{name} must be a unique immutable tuple")
        if (type(self.prepared_commands) is not tuple
                or any(type(item) is not LeafPreparedCommandV1 for item in self.prepared_commands)):
            raise TypeError("fault progress must preserve the exact prepared leaf commands")
        if (type(self.returned_apply_results) is not tuple
                or any(type(item) is not LeafApplyResultV1 for item in self.returned_apply_results)):
            raise TypeError("fault progress must preserve every typed apply result returned by the runtime")
        if type(self.fault) is not ExecutionFaultV1:
            raise TypeError("dispatch progress requires the existing ExecutionFaultV1")


@dataclass(frozen=True)
class LeafControlIntervalResultV1:
    schema_version: str
    effective_plan_identity_sha256: str
    source_boundary: StateBoundaryIdentity
    prepared_commands: tuple[LeafPreparedCommandV1, ...]
    apply_results: tuple[LeafApplyResultV1, ...]
    next_publication: CanonicalStatePublicationV1
    interval_completed: bool

    def __post_init__(self):
        if self.schema_version != "leaf-control-interval-result-v1":
            raise ValueError("unsupported leaf control interval result schema")
        _sha(self.effective_plan_identity_sha256, "result plan")
        if type(self.source_boundary) is not StateBoundaryIdentity:
            raise TypeError("interval result requires its exact source boundary")
        if type(self.prepared_commands) is not tuple or type(self.apply_results) is not tuple:
            raise TypeError("interval result collections must be immutable tuples")
        if type(self.next_publication) is not CanonicalStatePublicationV1 or self.interval_completed is not True:
            raise ValueError("only a completed interval with next publication can be returned")


@runtime_checkable
class LeafControlRuntime(Protocol):
    """Typed extension point implemented by the existing RuntimeSession owner."""

    @property
    def leaf_control_fault(self) -> LeafDispatchProgressV1 | None: ...

    @property
    def active_leaf_plan_identity(self) -> str | None: ...

    def read_leaf_runtime_clock(self) -> LeafRuntimeClockV1: ...

    def validate_leaf_materialization(
        self, receipt: LeafMaterializationReceiptV1, plan: EffectiveLeafPlanV1,
    ) -> None: ...

    def validate_leaf_writer_available(
        self, writer_id: str, actuator_refs: tuple[ActuatorReference, ...],
        receipt: LeafMaterializationReceiptV1,
    ) -> None: ...

    def begin_leaf_control_interval(self, plan_identity: str, boundary_id: str) -> None: ...

    def apply_leaf_actuator_patch(self, patch: LeafActuatorPatchV1) -> LeafApplyResultV1: ...

    def step_leaf_control_interval(self, *, substeps: int) -> None: ...

    def publish_leaf_state(
        self, scene: SceneDefinition, requirements: StateRequirements,
    ) -> CanonicalStatePublicationV1: ...

    def latch_leaf_control_fault(
        self, progress: LeafDispatchProgressV1, error: BaseException,
    ) -> None: ...


def _entry_by_writer(plan: EffectiveLeafPlanV1) -> dict[str, EffectiveLeafEntryV1]:
    values = {entry.binding.writer_id: entry for entry in plan.leaves}
    if len(values) != len(plan.leaves):
        raise ValueError("effective leaf plan contains duplicate writers")
    return values


def _check_runtime_clock(clock, expected: LeafRuntimeClockV1, *, require_state_revision: bool) -> None:
    if type(clock) is not LeafRuntimeClockV1:
        raise TypeError("RuntimeSession must return a typed leaf public clock")
    source, current = expected.boundary, clock.boundary
    if (source.episode_id, source.reset_sample_id, source.scene_identity_hash,
            source.scene_instance_id, source.provider_materialization_id,
            source.control_step) != (
            current.episode_id, current.reset_sample_id, current.scene_identity_hash,
            current.scene_instance_id, current.provider_materialization_id,
            current.control_step):
        raise ValueError("RuntimeSession public clock is stale or left the requested evaluation boundary")
    if require_state_revision and source.state_revision != current.state_revision:
        raise ValueError("typed state publication is stale for the RuntimeSession revision")
    if (expected.sample_clock.clock_domain, expected.sample_clock.sample_index,
            expected.sample_clock.simulation_time_s) != (
            clock.sample_clock.clock_domain, clock.sample_clock.sample_index,
            clock.sample_clock.simulation_time_s):
        raise ValueError("RuntimeSession public clock disagrees with the typed sample clock")
    if expected.configuration_revision != clock.configuration_revision:
        raise ValueError("RuntimeSession configuration revision changed")


def _action_for(action: LeafActionRequestV1, entry: EffectiveLeafEntryV1) -> None:
    binding = entry.binding
    if action.writer_id != binding.writer_id:
        raise ValueError("action writer differs from the bound leaf")
    if binding.profile_kind == "arm_position":
        if type(action.action) is not ArmPositionActionV1:
            raise ValueError("Arm leaf requires ArmPositionActionV1")
        value = action.action
        if value.schema_version != ARM_POSITION_ACTION_SCHEMA or value.joint_order != binding.joint_order:
            raise ValueError("Arm action schema/order differs from the exact leaf binding")
        if len(value.position_rad) != 7:
            raise ValueError("Arm action must contain exactly seven radians")
        for item, limits in zip(value.position_rad, binding.joint_position_limits, strict=True):
            if type(item) not in (int, float) or isinstance(item, bool) or not math.isfinite(item):
                raise ValueError("Arm action values must be finite real radians")
            if not limits[0] <= item <= limits[1]:
                raise ValueError("Arm action exceeds its ordered canonical Joint limits")
    elif binding.profile_kind == "hand_position":
        if type(action.action) is not HandPositionActionV1:
            raise ValueError("Hand leaf requires HandPositionActionV1")
        value = action.action
        if value.schema_version != HAND_POSITION_ACTION_SCHEMA:
            raise ValueError("Hand action schema mismatch")
        if (type(value.opening_m) not in (int, float) or isinstance(value.opening_m, bool)
                or not math.isfinite(value.opening_m) or not 0 <= value.opening_m <= 0.08):
            raise ValueError("Hand action requires an in-range finite total opening in metres")
        if value.input_representation == "normalized_signed_scalar_v1":
            if (type(value.requested_normalized) not in (int, float)
                    or isinstance(value.requested_normalized, bool)
                    or not math.isfinite(value.requested_normalized)):
                raise ValueError("normalized Hand request must remain finite and explicit")
        elif value.input_representation != "opening_m" or value.requested_normalized is not None:
            raise ValueError("Hand input representation is ambiguous")
    else:
        raise ValueError("Force-aware leaf remains NOT_ADMITTED")


def _validate_single_leaf_publication(plan, entry, publication, receipt, configuration_revision, scene):
    receipt.validate_against_plan(plan)
    publication.validate()
    view = publication.view
    view.validate_against_scene(scene)
    view.validate_requirements(entry.binding.required_state.state_requirements)
    binding = entry.binding
    joint_map = {(value.entity_id, value.joint_id): value for value in view.joints}
    frame_map = {(value.frame.entity_id, value.frame.frame_id): value for value in view.frames}
    for reference, limits in zip(binding.joint_order, binding.joint_position_limits, strict=True):
        value = joint_map.get((reference.entity_id, reference.joint_id))
        if type(value) is not TypedJointStateValue:
            raise ValueError("required typed Joint position/velocity is missing")
        if (not all(math.isfinite(number) for number in (*value.position, *value.velocity))
                or len(value.position) != 1 or len(value.velocity) != 1):
            raise ValueError("Position leaf Joint state must be finite scalar qpos/qvel")
        if not limits[0] <= value.position[0] <= limits[1]:
            raise ValueError("typed Joint state is outside the bound leaf limits")
    frame = frame_map.get((binding.tcp_frame.entity_id, binding.tcp_frame.frame_id))
    if type(frame) is not TypedFrameStateValue:
        raise ValueError("required typed TCP Frame publication is missing")
    pose = frame.pose_world
    if (not all(math.isfinite(number) for number in (*pose.position, *pose.quaternion_wxyz))
            or math.sqrt(sum(number * number for number in pose.quaternion_wxyz)) < 1.0e-8):
        raise ValueError("typed TCP world pose must be finite with a nonzero wxyz quaternion")
    boundary = view.boundary
    clock = view.sample_clock
    if (boundary.scene_identity_hash != plan.scene_identity_sha256
            or boundary.provider_materialization_id != receipt.materialization_id
            or configuration_revision != receipt.configuration_revision
            or publication.lifetime.owner_id != receipt.materialization_id
            or publication.lifetime.generation != boundary.state_revision
            or clock.sample_index != boundary.control_step
            or clock.clock_domain != "evaluation_boundary"):
        raise ValueError("typed state/source/configuration/materialization identity mismatch")
    runtime_clock = LeafRuntimeClockV1(
        "leaf-runtime-clock-v1", boundary, clock, configuration_revision,
    )
    return runtime_clock


def _validate_publication(plan, request, scene):
    clocks = tuple(_validate_single_leaf_publication(
        plan, entry, request.publication, request.materialization,
        request.configuration_revision, scene,
    ) for entry in plan.leaves)
    if len(set(clock.boundary for clock in clocks)) != 1:
        raise ValueError("all Position leaves must share one exact typed state boundary")
    return clocks[0]


def preflight_leaf_control_interval(
    plan: EffectiveLeafPlanV1,
    request: LeafControlIntervalRequestV1,
    *,
    scene: SceneDefinition,
    runtime: LeafControlRuntime,
) -> tuple[tuple[LeafActionRequestV1, ...], LeafRuntimeClockV1]:
    """Validate the complete multi-leaf request before any compute or mutation."""
    if (type(plan) is not EffectiveLeafPlanV1 or plan._compiled is not True
            or type(request) is not LeafControlIntervalRequestV1):
        raise TypeError("leaf preflight requires an exact compiled effective plan and request")
    if type(scene) is not SceneDefinition or scene.identity_hash != plan.scene_identity_sha256:
        raise ValueError("leaf plan is bound to another exact Scene")
    if request.effective_plan_identity_sha256 != plan.identity_sha256:
        raise ValueError("leaf request names a different effective plan")
    if runtime.leaf_control_fault is not None:
        raise RuntimeError("leaf RuntimeSession is fault-latched; reset is required")
    if runtime.active_leaf_plan_identity not in (None, plan.identity_sha256):
        raise ValueError("leaf plan/preset cannot be switched during an active episode")
    entries = _entry_by_writer(plan)
    request.materialization.validate_against_plan(plan)
    runtime.validate_leaf_materialization(request.materialization, plan)
    actions = {item.writer_id: item for item in request.actions}
    if len(actions) != len(request.actions) or set(actions) != set(entries):
        raise ValueError("complete leaf request must cover every writer exactly once")
    # Validate every action before touching the first adapter.
    for writer_id, entry in entries.items():
        _action_for(actions[writer_id], entry)
        runtime.validate_leaf_writer_available(
            writer_id, entry.binding.actuator_order, request.materialization,
        )
    typed_clock = _validate_publication(plan, request, scene)
    current_clock = runtime.read_leaf_runtime_clock()
    _check_runtime_clock(current_clock, typed_clock, require_state_revision=True)
    return tuple(actions[writer] for writer in sorted(entries)), typed_clock


def _make_target(entry, action, state_boundary, sample_clock):
    binding = entry.binding
    if binding.profile_kind == "arm_position":
        return ArmPositionTargetV1(
            "arm-position-target-v1", binding.profile_id, binding.action_schema_id,
            binding.writer_id, binding.identity_hash, binding.source_closure_sha256,
            binding.scene_identity_hash, binding.joint_order, binding.actuator_order,
            state_boundary, sample_clock, action.action,
        )
    return HandPositionTargetV1(
        "hand-position-target-v1", binding.profile_id, binding.action_schema_id,
        binding.writer_id, binding.identity_hash, binding.source_closure_sha256,
        binding.scene_identity_hash, binding.joint_order, binding.actuator_order,
        state_boundary, sample_clock, action.action,
    )


def _compute_leaf(entry, action, publication, materialization, configuration_revision, plan):
    binding, section = entry.binding, entry.section
    view = publication.view
    values = section.values()
    joint_map = {(value.entity_id, value.joint_id): value for value in view.joints}
    actuator_map = {item.canonical_actuator: item for item in materialization.actuators}
    target = _make_target(entry, action, view.boundary, view.sample_clock)
    slot_values = []
    requested_opening = servo_opening = native_ctrl = None
    if binding.profile_kind == "arm_position":
        current = [joint_map[(ref.entity_id, ref.joint_id)].position[0]
                   for ref in binding.joint_order]
        desired, servo = absolute_joint_position_servo(
            action.action.position_rad, current, binding.joint_position_limits,
            values["joint_position_correction_gain"],
        )
        for pair, ctrl_value in zip(binding.joint_actuator_bindings, servo, strict=True):
            native = actuator_map[pair.actuator]
            slot_values.append(LeafActuatorSlotValueV1(
                "leaf-actuator-slot-value-v1", pair.actuator, native.ctrl_slot,
                float(ctrl_value),
            ))
    else:
        current = sum(joint_map[(ref.entity_id, ref.joint_id)].position[0]
                      for ref in binding.joint_order)
        requested_opening = float(action.action.opening_m)
        servo_opening = position_gripper_servo_opening(
            requested_opening, current, values["gripper_default_force_N"],
            values["gripper_position_stiffness_N_per_m"],
            values["gripper_opening_range_m"],
        )
        native_ctrl = position_gripper_ctrl_for_opening(
            servo_opening, values["gripper_opening_range_m"],
            values["gripper_close_ctrl"], values["gripper_open_ctrl"],
        )
        native = actuator_map[binding.actuator_order[0]]
        slot_values.append(LeafActuatorSlotValueV1(
            "leaf-actuator-slot-value-v1", binding.actuator_order[0],
            native.ctrl_slot, native_ctrl,
        ))
    command = LeafPreparedCommandV1(
        "leaf-prepared-command-v1", binding.writer_id, binding.profile_kind,
        plan.identity_sha256, binding.identity_hash,
        entry.effective_configuration_identity_sha256,
        materialization.identity_sha256, view.boundary,
        configuration_revision, target, tuple(slot_values),
        requested_opening, servo_opening, native_ctrl,
    )
    for item in command.slot_values:
        native = actuator_map[item.actuator]
        if item.ctrl_slot != native.ctrl_slot or not native.ctrlrange[0] <= item.value <= native.ctrlrange[1]:
            raise ValueError("prepared command is outside its explicit native slot/range mapping")
    return command


def prepare_leaf_command(
    plan: EffectiveLeafPlanV1,
    writer_id: str,
    action: ArmPositionActionV1 | HandPositionActionV1,
    publication: CanonicalStatePublicationV1,
    materialization: LeafMaterializationReceiptV1,
    configuration_revision: str,
    *,
    scene: SceneDefinition,
) -> LeafPreparedCommandV1:
    """Run one real stateless leaf adapter with only its own Required State."""
    if (type(plan) is not EffectiveLeafPlanV1 or plan._compiled is not True
            or type(scene) is not SceneDefinition):
        raise TypeError("leaf adapter requires a compiled effective plan and exact Scene")
    if scene.identity_hash != plan.scene_identity_sha256:
        raise ValueError("leaf adapter Scene differs from the effective plan")
    entry = _entry_by_writer(plan).get(writer_id)
    if entry is None:
        raise ValueError("leaf adapter writer is not in the effective plan")
    request_action = LeafActionRequestV1("leaf-action-request-v1", writer_id, action)
    _action_for(request_action, entry)
    _validate_single_leaf_publication(
        plan, entry, publication, materialization, configuration_revision, scene,
    )
    return _compute_leaf(
        entry, request_action, publication, materialization,
        configuration_revision, plan,
    )


def _fault_progress(plan, boundary, *, attempted, applied, unknown, acknowledged, ack_hashes,
                    command_hashes, prepared_commands=(), returned_apply_results=(),
                    failed_writer, phase, error, before_clock,
                    after_clock, interval_attempted, interval_completed=False,
                    readback_error=None):
    before = before_clock.boundary if before_clock is not None else None
    after = after_clock.boundary if after_clock is not None else None
    fault = ExecutionFaultV1.from_exception(
        phase, error,
        control_step_before=None if before is None else before.control_step,
        control_step_after=None if after is None else after.control_step,
        simulation_time_before_s=None if before_clock is None else before_clock.sample_clock.simulation_time_s,
        simulation_time_after_s=None if after_clock is None else after_clock.sample_clock.simulation_time_s,
        native_substeps_expected=plan.control_substeps,
        expected_control_dt_s=plan.physics_dt_s * plan.control_substeps,
        interval_attempted=interval_attempted,
        interval_completed=interval_completed,
        transition_status="incomplete" if interval_attempted else "not_recorded",
        readback_error=readback_error,
    )
    if readback_error is not None and fault.physical_progress != "unknown":
        fault = replace(fault, physical_progress="unknown")
    result = LeafDispatchProgressV1(
        "leaf-dispatch-progress-v1", plan.identity_sha256, boundary.boundary_id,
        tuple(attempted), tuple(applied), tuple(unknown), tuple(acknowledged),
        tuple(ack_hashes), tuple(command_hashes),
        tuple(prepared_commands), tuple(returned_apply_results),
        failed_writer, phase, fault,
    )
    attach_execution_fault(error, fault)
    try:
        setattr(error, "leaf_dispatch_progress", result)
    except (AttributeError, TypeError):
        pass
    return result


def _latch(runtime, progress, error):
    runtime.latch_leaf_control_fault(progress, error)


def _read_runtime_clock(runtime) -> LeafRuntimeClockV1:
    clock = runtime.read_leaf_runtime_clock()
    if type(clock) is not LeafRuntimeClockV1:
        raise TypeError("RuntimeSession public clock readback is not LeafRuntimeClockV1")
    return clock


def dispatch_leaf_control_interval(
    plan: EffectiveLeafPlanV1,
    request: LeafControlIntervalRequestV1,
    *,
    scene: SceneDefinition,
    runtime: LeafControlRuntime,
) -> LeafControlIntervalResultV1:
    """Preflight all leaves, prepare all commands, then apply and step once."""
    actions, before = preflight_leaf_control_interval(plan, request, scene=scene, runtime=runtime)
    entries = _entry_by_writer(plan)
    actions_by_writer = {item.writer_id: item for item in actions}
    prepared = tuple(prepare_leaf_command(
        plan, writer, actions_by_writer[writer].action, request.publication,
        request.materialization, request.configuration_revision, scene=scene,
    ) for writer in sorted(entries))
    requirements = StateRequirements(
        "state-requirements-v1", "controller", "r02c-independent-position-leaves-v1",
        tuple(requirement for entry in plan.leaves
              for requirement in entry.binding.required_state.state_requirements.requirements),
    )
    # No cursor, replay, apply or physics state has changed before this point.
    try:
        runtime.begin_leaf_control_interval(plan.identity_sha256, before.boundary.boundary_id)
    except BaseException as error:
        try:
            after = _read_runtime_clock(runtime)
            readback_error = None
        except BaseException as read_error:
            after, readback_error = None, f"{type(read_error).__name__}: {read_error}"
        progress = _fault_progress(
            plan, before.boundary, attempted=(), applied=(), unknown=(),
            acknowledged=(), ack_hashes=(), command_hashes=(),
            prepared_commands=prepared, returned_apply_results=(),
            failed_writer=None, phase="leaf-boundary-consume", error=error,
            before_clock=before, after_clock=after, interval_attempted=False,
            readback_error=readback_error,
        )
        _latch(runtime, progress, error)
        raise
    attempted, applied, unknown = [], [], []
    ack_hashes, acknowledged, command_hashes, apply_results = [], [], [], []
    for command in prepared:
        writer = command.writer_id
        attempted.append(writer)
        command_hashes.append((writer, command.command_identity_sha256))
        patch = LeafActuatorPatchV1(
            "leaf-actuator-patch-v1", writer, command.command_identity_sha256,
            command.target, plan.identity_sha256, request.materialization.identity_sha256,
            command.state_configuration_revision, command.slot_values,
        )
        try:
            result = runtime.apply_leaf_actuator_patch(patch)
        except BaseException as error:
            unknown.append(writer)
            try:
                after = _read_runtime_clock(runtime)
                readback_error = None
            except BaseException as read_error:
                after, readback_error = None, f"{type(read_error).__name__}: {read_error}"
            progress = _fault_progress(
                plan, before.boundary, attempted=attempted, applied=applied,
                unknown=unknown, acknowledged=acknowledged, ack_hashes=ack_hashes,
                command_hashes=command_hashes,
                prepared_commands=prepared, returned_apply_results=apply_results,
                failed_writer=writer, phase="leaf-apply", error=error,
                before_clock=before, after_clock=after, interval_attempted=False,
                readback_error=readback_error,
            )
            _latch(runtime, progress, error)
            raise
        # Returning from the runtime-owned write call means the write may have
        # happened even if its Ack is malformed. Preserve that fact.
        applied.append(writer)
        if type(result) is LeafApplyResultV1:
            apply_results.append(result)
            try:
                ack_hashes.append((writer, result.ack.identity_hash))
            except BaseException:
                pass
        try:
            if type(result) is not LeafApplyResultV1:
                raise TypeError("RuntimeSession apply must return LeafApplyResultV1")
            if (result.writer_id, result.command_identity_sha256,
                    result.materialization_identity_sha256, result.applied_slots) != (
                    writer, command.command_identity_sha256,
                    request.materialization.identity_sha256,
                    tuple(item.ctrl_slot for item in command.slot_values)):
                raise ValueError("RuntimeSession apply result differs from its exact owned patch")
            current_after_apply = _read_runtime_clock(runtime)
            _check_runtime_clock(current_after_apply, before, require_state_revision=False)
            validate_leaf_target_ack(
                entries[writer].binding, command.target, result.ack,
                expected_source_boundary=command.state_boundary,
                expected_source_clock=request.publication.view.sample_clock,
                expected_application_boundary=current_after_apply.boundary,
                expected_application_clock=current_after_apply.sample_clock,
            )
            if result.ack.identity_hash not in {value for name, value in ack_hashes if name == writer}:
                ack_hashes.append((writer, result.ack.identity_hash))
            acknowledged.append(writer)
        except BaseException as error:
            try:
                after = _read_runtime_clock(runtime)
                readback_error = None
            except BaseException as read_error:
                after, readback_error = None, f"{type(read_error).__name__}: {read_error}"
            progress = _fault_progress(
                plan, before.boundary, attempted=attempted, applied=applied,
                unknown=unknown, acknowledged=acknowledged, ack_hashes=ack_hashes,
                command_hashes=command_hashes,
                prepared_commands=prepared, returned_apply_results=apply_results,
                failed_writer=writer, phase="leaf-acknowledgement", error=error,
                before_clock=before, after_clock=after, interval_attempted=False,
                readback_error=readback_error,
            )
            _latch(runtime, progress, error)
            raise

    try:
        runtime.step_leaf_control_interval(substeps=plan.control_substeps)
        after_step = _read_runtime_clock(runtime)
        expected_step = before.boundary.control_step + 1
        expected_time = before.sample_clock.simulation_time_s + plan.physics_dt_s * plan.control_substeps
        tolerance = max(1.0e-12, 1.0e-9 * plan.physics_dt_s * plan.control_substeps)
        if (after_step.boundary.control_step != expected_step
                or after_step.sample_clock.sample_index != expected_step
                or not math.isclose(after_step.sample_clock.simulation_time_s,
                                    expected_time, rel_tol=1.0e-9, abs_tol=tolerance)
                or after_step.configuration_revision != request.configuration_revision):
            raise ValueError("public RuntimeSession clock did not complete exactly one outer interval")
    except BaseException as error:
        try:
            after = _read_runtime_clock(runtime)
            readback_error = None
        except BaseException as read_error:
            after, readback_error = None, f"{type(read_error).__name__}: {read_error}"
        progress = _fault_progress(
            plan, before.boundary, attempted=attempted, applied=applied,
            unknown=unknown, acknowledged=acknowledged, ack_hashes=ack_hashes,
            command_hashes=command_hashes,
            prepared_commands=prepared, returned_apply_results=apply_results,
            failed_writer=None, phase="leaf-physics-step", error=error,
            before_clock=before, after_clock=after, interval_attempted=True,
            readback_error=readback_error,
        )
        _latch(runtime, progress, error)
        raise

    try:
        publication = runtime.publish_leaf_state(scene, requirements)
        if type(publication) is not CanonicalStatePublicationV1:
            raise TypeError("RuntimeSession must return the next typed CanonicalStatePublicationV1")
        publication.validate()
        publication.view.validate_against_scene(scene)
        for entry in plan.leaves:
            next_clock = _validate_single_leaf_publication(
                plan, entry, publication, request.materialization,
                request.configuration_revision, scene,
            )
            _check_runtime_clock(after_step, next_clock, require_state_revision=True)
        next_boundary = publication.view.boundary
        if (next_boundary.episode_id != before.boundary.episode_id
                or next_boundary.reset_sample_id != before.boundary.reset_sample_id
                or next_boundary.scene_instance_id != before.boundary.scene_instance_id
                or next_boundary.control_step != after_step.boundary.control_step
                or publication.view.sample_clock != after_step.sample_clock
                or next_boundary.scene_identity_hash != plan.scene_identity_sha256
                or next_boundary.provider_materialization_id != request.materialization.materialization_id):
            raise ValueError("next typed publication is stale or belongs to another interval")
    except BaseException as error:
        progress = _fault_progress(
            plan, before.boundary, attempted=attempted, applied=applied,
            unknown=unknown, acknowledged=acknowledged, ack_hashes=ack_hashes,
            command_hashes=command_hashes,
            prepared_commands=prepared, returned_apply_results=apply_results,
            failed_writer=None, phase="leaf-state-publication", error=error,
            before_clock=before, after_clock=after_step, interval_attempted=True,
            interval_completed=False,
        )
        _latch(runtime, progress, error)
        raise
    return LeafControlIntervalResultV1(
        "leaf-control-interval-result-v1", plan.identity_sha256, before.boundary,
        prepared, tuple(apply_results), publication, True,
    )


__all__ = [
    "LeafNativeJointMappingV1", "LeafNativeActuatorMappingV1",
    "LeafNativeFrameMappingV1", "LeafNativeTendonMappingV1",
    "LeafMaterializationReceiptV1",
    "LeafRuntimeClockV1", "LeafActionRequestV1", "LeafControlIntervalRequestV1",
    "LeafActuatorSlotValueV1", "LeafPreparedCommandV1", "LeafActuatorPatchV1",
    "LeafApplyResultV1", "LeafDispatchProgressV1", "LeafControlIntervalResultV1",
    "LeafControlRuntime", "preflight_leaf_control_interval",
    "prepare_leaf_command", "dispatch_leaf_control_interval",
]
