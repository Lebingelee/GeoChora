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
import subprocess
from pathlib import Path
from types import MappingProxyType
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
    """Bound named-drive metadata for F03 synthetic S1 or F04 native runtime."""

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
        if self.provenance_kind not in {'synthetic_fixture', 'native_runtime'}:
            raise ValueError('named Position drive receipt provenance must be explicit')
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
            raise ValueError('Panda drive receipt requires the 2 ms / five-substep timebase')
        if (self.backend, self.device, self.determinism_mode) != ('cuda', 'cuda:0', 'best_effort'):
            raise ValueError('Isaac target execution is CUDA cuda:0 with best_effort determinism')
        if type(self.device) is not str:
            raise TypeError('Isaac target device must be a string')
        if self.provider_build_identity != 'isaacsim-6.2.0.0':
            raise ValueError('Isaac target drive receipt requires Isaac Sim 6.2.0.0')
        if type(self.native_dof_count) is not int or self.native_dof_count != 9:
            raise ValueError('Panda drive receipt requires exactly nine named scalar DOFs')
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
        observed_mapping = {joint: (drive.native_dof_name, drive.position_unit)
                            for joint, drive in by_joint.items()}
        allowed_mappings = [expected]
        # Both fixed F04 source families retain their own authored DOF names.
        # S1 may exercise either mapping through a synthetic low-level I/O
        # fixture; provenance classifies execution, not the source namespace.
        menagerie = {
            JointReference('panda-main', f'joint{index}'): (f'joint{index}', 'radian')
            for index in range(1, 8)
        }
        menagerie.update({
            JointReference('panda-main', 'finger_joint1'): ('finger_joint1', 'meter'),
            JointReference('panda-main', 'finger_joint2'): ('finger_joint2', 'meter'),
        })
        allowed_mappings.append(menagerie)
        if observed_mapping not in allowed_mappings:
            raise ValueError('Isaac native DOF name or unit differs from the Panda mapping')
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
        finger_upper = {
            drive.canonical_joint.joint_id: float(drive.upper_limit)
            for drive in self.drives
            if drive.canonical_joint.joint_id in {'finger_joint1', 'finger_joint2'}
        }
        if set(finger_upper) != {'finger_joint1', 'finger_joint2'}:
            raise ValueError('named-drive receipt is missing one of the two canonical finger limits')
        max_common_opening = 2.0 * min(finger_upper.values())
        requested_opening = float(hand_opening_m)
        # The fixed USD source encodes 0.04 m as a float32 limit, which reads
        # back as 0.03999999910593033. Accept only that sub-2 nm encoding
        # difference at the canonical 0.08 m endpoint, then issue the exact
        # metadata-bounded target. Larger requests remain fail-closed.
        if requested_opening > max_common_opening + 2e-9:
            raise ValueError('Hand opening target exceeds the two native finger limits')
        half_opening = min(requested_opening / 2.0, min(finger_upper.values()))
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


@dataclass(frozen=True)
class IsaacNativeMimicPositionDriveReceiptV1:
    """Versioned PhysX leader-drive/passive-mimic mapping for DG04."""

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
    native_dof_names: tuple[str, ...]
    native_position_limits: Mapping[str, tuple[float, float]]
    drives: tuple[IsaacNamedPositionDriveV1, ...]
    mimic_follower_joint: str = 'finger_joint2'
    mimic_reference_joint: str = 'finger_joint1'
    mimic_gearing: float = 1.0
    mimic_offset_m: float = 0.0
    mimic_natural_frequency_hz: float = 25.0
    mimic_damping_ratio: float = 1.0
    gripper_drive_stiffness_N_m: float = 2000.0
    gripper_drive_damping_N_s_m: float = 100.0
    gripper_force_limit_N: float = 100.0
    native_mimic_api: str = 'PhysxMimicJointAPI:transX'
    native_drive_api: str = 'PhysicsDriveAPI:linear'

    def __post_init__(self):
        if self.schema_version != 'isaac-native-mimic-position-drive-receipt-v1':
            raise ValueError('unsupported Isaac native mimic drive receipt schema')
        if self.provenance_kind not in {'synthetic_fixture', 'native_runtime'}:
            raise ValueError('native mimic drive receipt provenance must be explicit')
        for value, label in (
            (self.scene_identity_sha256, 'Scene'),
            (self.source_closure_sha256, 'source closure'),
            (self.execution_identity_sha256, 'ExecutionSpec'),
        ):
            _sha(value, label)
        f06_profile = self.physics_profile == 'isaac-gpu-physx-pickcube-f06-v1'
        expected_profile = (
            'isaac-gpu-physx-pickcube-f06-v1' if f06_profile
            else 'isaac-gpu-physx-f05-dg04-native-mimic-v1'
        )
        if (self.provider_build_identity, self.physics_profile, self.backend,
                self.device, self.determinism_mode, self.physics_dt_s,
                self.control_substeps) != (
                'isaacsim-6.2.0.0', expected_profile,
                'cuda', 'cuda:0', 'best_effort', 0.002, 5):
            raise ValueError('native mimic receipt differs from its fixed Isaac 6.2 CUDA PhysX profile')
        _stable_identity(self.writer_id, 'writer ID')
        names = tuple(self.native_dof_names)
        expected_names = {f'joint{index}' for index in range(1, 8)} | {
            'finger_joint1', 'finger_joint2',
        }
        if len(names) != 9 or len(set(names)) != 9 or set(names) != expected_names:
            raise ValueError('DG04 receipt requires the exact nine named Menagerie Panda DOFs')
        limits = {name: tuple(values) for name, values in dict(self.native_position_limits).items()}
        if set(limits) != set(names):
            raise ValueError('DG04 public DOF limits must cover all nine mapped joints')
        for name, values in limits.items():
            if (len(values) != 2 or any(type(value) not in (int, float) or isinstance(value, bool)
                                        or not math.isfinite(float(value)) for value in values)
                    or float(values[0]) >= float(values[1])):
                raise ValueError(f'DG04 position limits for {name} are invalid')
            limits[name] = (float(values[0]), float(values[1]))
        object.__setattr__(self, 'native_dof_names', names)
        object.__setattr__(self, 'native_position_limits', MappingProxyType(limits))
        rows = tuple(self.drives)
        entities = {row.canonical_joint.entity_id for row in rows}
        if len(entities) != 1:
            raise ValueError('native mimic receipt must bind one canonical Panda Entity')
        entity_id = next(iter(entities))
        expected_entity_id = 'panda-v1' if f06_profile else 'panda-main'
        if entity_id != expected_entity_id:
            raise ValueError('native mimic receipt canonical Panda identity differs from its admitted profile')
        expected_driven_joints = {
            JointReference(entity_id, f'joint{index}') for index in range(1, 8)
        } | {JointReference(entity_id, 'finger_joint1')}
        if (len(rows) != 8 or any(type(row) is not IsaacNamedPositionDriveV1 for row in rows)
                or {row.canonical_joint for row in rows} != expected_driven_joints):
            raise ValueError('DG04 drive receipt must contain seven Arm drives and one leading-finger drive')
        if any(names[row.native_dof_index] != row.native_dof_name
               or (float(row.lower_limit), float(row.upper_limit)) != limits[row.native_dof_name]
               or row.position_unit != ('radian' if row.canonical_joint.joint_id.startswith('joint') else 'meter')
               for row in rows):
            raise ValueError('DG04 active drive index/unit/limit differs from public articulation metadata')
        if len({row.native_dof_index for row in rows}) != 8:
            raise ValueError('DG04 active drive indices must be unique')
        expected_gripper_profile = (
            (5000.0, 120.0, 5.0) if f06_profile else (2000.0, 100.0, 100.0)
        )
        if (self.mimic_follower_joint, self.mimic_reference_joint,
                float(self.mimic_gearing), float(self.mimic_offset_m),
                float(self.mimic_natural_frequency_hz), float(self.mimic_damping_ratio),
                float(self.gripper_drive_stiffness_N_m), float(self.gripper_drive_damping_N_s_m),
                float(self.gripper_force_limit_N), self.native_mimic_api, self.native_drive_api) != (
                'finger_joint2', 'finger_joint1', 1.0, 0.0, 25.0, 1.0,
                *expected_gripper_profile,
                'PhysxMimicJointAPI:transX', 'PhysicsDriveAPI:linear'):
            raise ValueError('native mimic receipt differs from its explicitly versioned drive adaptation')
        expected_finger_high = 0.04 if f06_profile else 0.04
        expected_force = 5.0 if f06_profile else 100.0
        if (self.gripper_force_limit_N != expected_force
                or limits['finger_joint1'][0] > 2e-9
                or limits['finger_joint1'][1] < expected_finger_high - 2e-9
                or limits['finger_joint2'][0] > 2e-9
                or limits['finger_joint2'][1] < expected_finger_high - 2e-9):
            raise ValueError('native hand profile cannot represent its exact admitted opening/force-cap contract')

    @property
    def native_dof_count(self) -> int:
        return len(self.native_dof_names)

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_mapping(include_identity=False))

    def to_mapping(self, *, include_identity: bool = True) -> dict[str, object]:
        result = {
            'schema_version': self.schema_version,
            'provenance_kind': self.provenance_kind,
            'scene_identity_sha256': self.scene_identity_sha256,
            'source_closure_sha256': self.source_closure_sha256,
            'execution_identity_sha256': self.execution_identity_sha256,
            'provider_build_identity': self.provider_build_identity,
            'physics_profile': self.physics_profile,
            'backend': self.backend, 'device': self.device,
            'determinism_mode': self.determinism_mode,
            'physics_dt_s': float(self.physics_dt_s),
            'control_substeps': self.control_substeps,
            'writer_id': self.writer_id,
            'native_dof_names': list(self.native_dof_names),
            'native_position_limits': {
                name: list(values) for name, values in self.native_position_limits.items()
            },
            'active_drive_joints': [
                {'entity_id': row.canonical_joint.entity_id,
                 'joint_id': row.canonical_joint.joint_id,
                 'native_dof_name': row.native_dof_name,
                 'native_dof_index': row.native_dof_index,
                 'position_unit': row.position_unit}
                for row in self.drives
            ],
            'passive_mimic': {
                'follower_joint': self.mimic_follower_joint,
                'reference_joint': self.mimic_reference_joint,
                'gearing': float(self.mimic_gearing), 'offset_m': float(self.mimic_offset_m),
                'natural_frequency_hz': float(self.mimic_natural_frequency_hz),
                'damping_ratio': float(self.mimic_damping_ratio),
                'api': self.native_mimic_api,
            },
            'leader_drive': {
                'joint': 'finger_joint1', 'api': self.native_drive_api,
                'stiffness_N_m': float(self.gripper_drive_stiffness_N_m),
                'damping_N_s_m': float(self.gripper_drive_damping_N_s_m),
                'force_limit_N': float(self.gripper_force_limit_N),
                'canonical_opening_mapping': 'opening_m_to_leader_position_m = opening_m / 2',
            },
        }
        if include_identity:
            result['identity_sha256'] = _digest(result)
        return result

    def commands(self, arm_position: Mapping[str, float], hand_opening_m: float):
        expected_arm = {f'panda-main/joint{index}' for index in range(1, 8)}
        if not isinstance(arm_position, Mapping) or set(arm_position) != expected_arm:
            raise ValueError('DG04 Arm Position request must cover the exact seven canonical joints')
        if any(type(name) is not str or type(value) not in (int, float)
               or isinstance(value, bool) or not math.isfinite(float(value))
               for name, value in arm_position.items()):
            raise ValueError('DG04 Arm Position targets must be finite non-boolean numbers')
        if (type(hand_opening_m) not in (int, float) or isinstance(hand_opening_m, bool)
                or not math.isfinite(float(hand_opening_m))
                or not 0.0 <= float(hand_opening_m) <= 0.08):
            raise ValueError('DG04 hand opening must be finite and in [0, 0.08] metres')
        if float(hand_opening_m) > 2.0 * min(
                self.native_position_limits['finger_joint1'][1],
                self.native_position_limits['finger_joint2'][1]) + 2e-9:
            raise ValueError('DG04 hand opening exceeds the exact native two-finger limits')
        positions = {
            JointReference('panda-main', key.split('/', 1)[1]): float(value)
            for key, value in arm_position.items()
        }
        positions[JointReference('panda-main', 'finger_joint1')] = min(
            float(hand_opening_m) / 2.0,
            self.native_position_limits['finger_joint1'][1],
        )
        targets = []
        for row in self.drives:
            value = positions[row.canonical_joint]
            if not row.lower_limit <= value <= row.upper_limit:
                raise ValueError(f'DG04 target exceeds native limit for {row.native_dof_name}')
            targets.append((row.native_dof_index, row.native_dof_name, float(value)))
        return tuple(sorted(targets))


@dataclass(frozen=True)
class GeoPhysUsdPositionDriveV1:
    """One public GeoPhys USD force-drive bound to a named canonical Joint."""

    schema_version: str
    canonical_joint: JointReference
    native_dof_name: str
    native_dof_index: int
    native_actuator_name: str
    native_actuator_index: int
    position_unit: str
    lower_limit: float
    upper_limit: float
    gain: float
    bias0: float
    stiffness: float
    damping: float
    desired_velocity: float
    coordinate_offset: float
    joint_q0: float
    control_limited: bool
    control_lower: float
    control_upper: float
    force_limited: bool
    force_lower: float
    force_upper: float

    def __post_init__(self):
        if self.schema_version != 'geophys-usd-position-drive-v1':
            raise ValueError('unsupported GeoPhys USD Position drive schema')
        if type(self.canonical_joint) is not JointReference:
            raise TypeError('GeoPhys USD drive requires JointReference')
        self.canonical_joint.validate()
        _token(self.native_dof_name, 'GeoPhys native DOF name')
        _stable_identity(self.native_actuator_name, 'GeoPhys native actuator name')
        if (type(self.native_dof_index) is not int or self.native_dof_index < 0
                or type(self.native_actuator_index) is not int or self.native_actuator_index < 0):
            raise ValueError('GeoPhys native joint and actuator indices must be nonnegative integers')
        if self.position_unit not in {'radian', 'meter'}:
            raise ValueError('GeoPhys native Position unit must be radian or meter')
        numeric = (
            self.lower_limit, self.upper_limit, self.gain, self.bias0,
            self.stiffness, self.damping, self.desired_velocity,
            self.coordinate_offset, self.joint_q0,
            self.control_lower, self.control_upper,
            self.force_lower, self.force_upper,
        )
        if any(type(value) not in (int, float) or isinstance(value, bool)
               or not math.isfinite(float(value)) for value in numeric):
            raise ValueError('GeoPhys USD drive numeric metadata must be finite non-boolean values')
        if (self.lower_limit >= self.upper_limit or self.gain == 0.0
                or self.stiffness < 0.0 or self.damping < 0.0
                or self.control_lower > self.control_upper
                or self.force_lower > self.force_upper
                or type(self.control_limited) is not bool
                or type(self.force_limited) is not bool):
            raise ValueError('GeoPhys USD drive limits or affine control law are invalid')


@dataclass(frozen=True)
class GeoPhysHostModelProducerIdentityV1:
    """F05-only identity for the source tree that actually lowered a public USD host model."""

    schema_version: str
    requested_target_build_identity: str
    repository_root: str
    origin_url: str
    commit_sha: str
    worktree_clean: bool
    module_sources: tuple[tuple[str, str, str], ...]

    def __post_init__(self):
        if self.schema_version != 'geophys-host-model-producer-identity-v1':
            raise ValueError('unsupported GeoPhys host-model producer identity schema')
        _token(self.requested_target_build_identity, 'requested target build identity')
        root = Path(self.repository_root)
        if not root.is_absolute() or str(root.resolve()) != self.repository_root:
            raise ValueError('host-model producer repository root must be canonical and absolute')
        _stable_identity(self.origin_url, 'provider origin URL')
        if (type(self.commit_sha) is not str or not re.fullmatch(r'[0-9a-f]{40,64}', self.commit_sha)):
            raise ValueError('provider producer commit must be lowercase Git SHA-1/SHA-256 hex')
        if self.worktree_clean is not True:
            raise ValueError('F05 producer identity must describe a clean committed provider tree')
        rows = tuple(self.module_sources)
        if not rows or any(type(row) is not tuple or len(row) != 3 for row in rows):
            raise ValueError('host-model producer identity requires module source rows')
        names = [row[0] for row in rows]
        if len(names) != len(set(names)) or names != sorted(names):
            raise ValueError('provider module source rows must be unique and sorted by module name')
        for module_name, origin, source_sha256 in rows:
            _stable_identity(module_name, 'provider module name')
            path = Path(origin)
            if not path.is_absolute() or str(path.resolve()) != origin:
                raise ValueError(f'provider module origin must be canonical and absolute: {module_name}')
            _sha(source_sha256, f'provider module content hash {module_name}')
            try:
                path.resolve().relative_to((root / 'src').resolve())
            except ValueError as exc:
                raise ValueError(f'provider module origin escapes the declared source root: {module_name}') from exc
        if not {'scene', 'geometry'} <= set(names):
            raise ValueError('GeoPhys host producer identity must include public scene and geometry package origins')
        object.__setattr__(self, 'module_sources', rows)

    def _identity_payload(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'requested_target_build_identity': self.requested_target_build_identity,
            'repository_root': self.repository_root,
            'origin_url': self.origin_url,
            'commit_sha': self.commit_sha,
            'worktree_clean': self.worktree_clean,
            'module_sources': [list(row) for row in self.module_sources],
        }

    @property
    def identity_sha256(self) -> str:
        return _digest(self._identity_payload())

    @property
    def actual_provider_build_identity(self) -> str:
        """Identity of the committed checkout that actually lowered the host model."""
        return f'geophys-{self.commit_sha}'

    def to_mapping(self) -> dict[str, object]:
        return {**self._identity_payload(), 'identity_sha256': self.identity_sha256}

    def validate_current_tree(self) -> None:
        """Recheck the actual checkout and bytes rather than trusting supplied strings."""
        root = Path(self.repository_root)
        try:
            commit = subprocess.check_output(
                ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True, timeout=5,
            ).strip()
            origin = subprocess.check_output(
                ['git', '-C', str(root), 'remote', 'get-url', 'origin'], text=True, timeout=5,
            ).strip()
            status = subprocess.check_output(
                ['git', '-C', str(root), 'status', '--porcelain=v1', '--untracked-files=all'],
                text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f'cannot independently read the GeoPhys producer checkout: {exc}') from exc
        if (commit, origin, status) != (self.commit_sha, self.origin_url, ''):
            raise ValueError('actual GeoPhys producer HEAD/origin/clean state differs from its identity')
        for module_name, raw_origin, expected_sha in self.module_sources:
            path = Path(raw_origin)
            try:
                path.resolve().relative_to((root / 'src').resolve())
                actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, ValueError) as exc:
                raise ValueError(f'cannot verify actual provider module bytes for {module_name}: {exc}') from exc
            if actual_sha != expected_sha:
                raise ValueError(f'actual provider module content changed for {module_name}')


@dataclass(frozen=True)
class GeoPhysUsdPositionDriveReceiptV1:
    """Model-bound USD drive facts; it does not admit GeoPhys production runtime."""

    schema_version: str
    provenance_kind: str
    scene_identity_sha256: str
    source_closure_sha256: str
    public_model_identity_sha256: str
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
    drives: tuple[GeoPhysUsdPositionDriveV1, ...]
    host_model_producer_identity_sha256: str | None = None

    def __post_init__(self):
        if self.schema_version != 'geophys-usd-position-drive-receipt-v1':
            raise ValueError('unsupported GeoPhys USD Position drive receipt schema')
        if self.provenance_kind not in {'synthetic_fixture', 'native_runtime'}:
            raise ValueError('GeoPhys drive receipt provenance must be explicit')
        for value, label in (
            (self.scene_identity_sha256, 'Scene'),
            (self.source_closure_sha256, 'source closure'),
            (self.public_model_identity_sha256, 'public model'),
            (self.execution_identity_sha256, 'ExecutionSpec'),
        ):
            _sha(value, label)
        for value, label in (
            (self.provider_build_identity, 'provider build'),
            (self.physics_profile, 'physics profile'),
            (self.backend, 'backend'),
            (self.device, 'device'),
            (self.determinism_mode, 'determinism mode'),
        ):
            _token(value, label)
        _stable_identity(self.writer_id, 'writer ID')
        if self.host_model_producer_identity_sha256 is not None:
            _sha(self.host_model_producer_identity_sha256, 'host-model producer identity')
        if (type(self.physics_dt_s) not in (int, float) or isinstance(self.physics_dt_s, bool)
                or not math.isfinite(float(self.physics_dt_s)) or float(self.physics_dt_s) != 0.002
                or type(self.control_substeps) is not int or self.control_substeps != 5):
            raise ValueError('GeoPhys Panda drive receipt requires five 2 ms control substeps')
        if type(self.native_dof_count) is not int or self.native_dof_count != 9:
            raise ValueError('GeoPhys Panda drive receipt requires exactly nine scalar DOFs')
        if type(self.drives) is not tuple or any(type(item) is not GeoPhysUsdPositionDriveV1 for item in self.drives):
            raise TypeError('GeoPhys drive receipt requires exact immutable drive rows')
        expected = {
            JointReference('panda-main', f'joint{index}') for index in range(1, 8)
        } | {
            JointReference('panda-main', 'finger_joint1'),
            JointReference('panda-main', 'finger_joint2'),
        }
        joints = [row.canonical_joint for row in self.drives]
        dofs = [row.native_dof_name for row in self.drives]
        actuators = [row.native_actuator_name for row in self.drives]
        dof_indices = [row.native_dof_index for row in self.drives]
        actuator_indices = [row.native_actuator_index for row in self.drives]
        if (set(joints) != expected or len(joints) != len(set(joints))
                or len(dofs) != len(set(dofs)) or len(actuators) != len(set(actuators))
                or sorted(dof_indices) != list(range(9))
                or len(actuator_indices) != len(set(actuator_indices))):
            raise ValueError('GeoPhys Panda drive rows must exactly bind nine unique named DOF/actuator channels')

    @property
    def identity_sha256(self) -> str:
        payload = {
            'schema_version': self.schema_version,
            'provenance_kind': self.provenance_kind,
            'scene_identity_sha256': self.scene_identity_sha256,
            'source_closure_sha256': self.source_closure_sha256,
            'public_model_identity_sha256': self.public_model_identity_sha256,
            'execution_identity_sha256': self.execution_identity_sha256,
            'provider_build_identity': self.provider_build_identity,
            'physics_profile': self.physics_profile,
            'backend': self.backend, 'device': self.device,
            'determinism_mode': self.determinism_mode,
            'physics_dt_s': float(self.physics_dt_s),
            'control_substeps': self.control_substeps,
            'writer_id': self.writer_id,
            'drives': [(
                row.canonical_joint.entity_id, row.canonical_joint.joint_id,
                row.native_dof_name, row.native_dof_index,
                row.native_actuator_name, row.native_actuator_index,
                row.position_unit, float(row.lower_limit), float(row.upper_limit),
                float(row.gain), float(row.bias0), float(row.stiffness),
                float(row.damping), float(row.desired_velocity),
                float(row.coordinate_offset), float(row.joint_q0),
                row.control_limited, float(row.control_lower), float(row.control_upper),
                row.force_limited, float(row.force_lower), float(row.force_upper),
            ) for row in self.drives],
        }
        if self.host_model_producer_identity_sha256 is not None:
            payload['host_model_producer_identity_sha256'] = self.host_model_producer_identity_sha256
        return _digest(payload)

    def commands(self, arm_position: Mapping[str, float], hand_opening_m: float):
        expected_arm = {f'panda-main/joint{index}' for index in range(1, 8)}
        if not isinstance(arm_position, Mapping) or set(arm_position) != expected_arm:
            raise ValueError('Arm Position request must exactly cover canonical joint1 through joint7')
        if any(type(name) is not str or type(value) not in (int, float)
               or isinstance(value, bool) or not math.isfinite(float(value))
               for name, value in arm_position.items()):
            raise ValueError('Arm Position targets must be finite non-boolean numbers')
        if (type(hand_opening_m) not in (int, float) or isinstance(hand_opening_m, bool)
                or not math.isfinite(float(hand_opening_m)) or not 0.0 <= float(hand_opening_m) <= 0.08):
            raise ValueError('Hand opening target must be a finite value in [0, 0.08] metres')
        finger_upper = {row.canonical_joint.joint_id: float(row.upper_limit) for row in self.drives
                        if row.canonical_joint.joint_id in {'finger_joint1', 'finger_joint2'}}
        if set(finger_upper) != {'finger_joint1', 'finger_joint2'}:
            raise ValueError('GeoPhys receipt is missing one of the two finger limits')
        if float(hand_opening_m) > 2.0 * min(finger_upper.values()) + 2e-9:
            raise ValueError('Hand opening target exceeds the two GeoPhys native finger limits')
        positions = {JointReference('panda-main', key.split('/', 1)[1]): float(value)
                     for key, value in arm_position.items()}
        half = min(float(hand_opening_m) / 2.0, min(finger_upper.values()))
        positions[JointReference('panda-main', 'finger_joint1')] = half
        positions[JointReference('panda-main', 'finger_joint2')] = half
        result = []
        for row in self.drives:
            value = positions[row.canonical_joint]
            if not row.lower_limit <= value <= row.upper_limit:
                raise ValueError(f'Position target exceeds native limit for {row.native_dof_name}')
            result.append((row.native_dof_index, row.native_dof_name, value))
        return tuple(sorted(result))

    def control_inputs(self, targets: tuple[tuple[int, str, float], ...]):
        """Map canonical q targets to the public model's affine force-drive ctrl."""
        by_name = {row.native_dof_name: row for row in self.drives}
        if (type(targets) is not tuple or len(targets) != 9
                or {name for _index, name, _value in targets} != set(by_name)):
            raise ValueError('GeoPhys control mapping requires the exact nine named Position targets')
        controls = []
        for index, name, target in targets:
            row = by_name[name]
            if (type(index) is not int or index != row.native_dof_index
                    or type(target) not in (int, float) or isinstance(target, bool)
                    or not math.isfinite(float(target))):
                raise ValueError('GeoPhys Position target index/value differs from its model-bound receipt')
            native_target = float(target) + row.coordinate_offset
            value = (row.stiffness * native_target + row.damping * row.desired_velocity - row.bias0) / row.gain
            if not math.isfinite(value):
                raise ValueError('GeoPhys affine Position control is non-finite')
            if row.control_limited and not row.control_lower <= value <= row.control_upper:
                raise ValueError(f'GeoPhys Position control exceeds native ctrl range for {name}')
            controls.append((row.native_actuator_index, row.native_actuator_name, value))
        return tuple(sorted(controls))


@dataclass(frozen=True)
class GeoPhysUsdSourceActuationReceiptV2:
    """Model-bound 9-DOF/8-actuator receipt with one shared fixed-tendon drive.

    The seven arm joints have independent actuators.  The two finger DOFs share
    one tendon actuator and one source equality; callers still speak in the
    existing nine named Position coordinates.
    """

    schema_version: str
    provenance_kind: str
    scene_identity_sha256: str
    source_closure_sha256: str
    public_model_identity_sha256: str
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
    drives: tuple[GeoPhysUsdPositionDriveV1, ...]
    tendon_name: str
    tendon_joint_names: tuple[str, str]
    tendon_coefficients: tuple[float, float]
    equality_name: str
    equality_solref: tuple[float, ...]
    equality_solimp: tuple[float, ...]
    host_model_producer_identity_sha256: str | None = None

    def __post_init__(self):
        if self.schema_version != 'geophys-usd-source-actuation-receipt-v2':
            raise ValueError('unsupported GeoPhys USD source-actuation receipt schema')
        if self.provenance_kind not in {'synthetic_fixture', 'native_runtime'}:
            raise ValueError('GeoPhys source-actuation provenance must be explicit')
        for value, label in (
            (self.scene_identity_sha256, 'Scene'),
            (self.source_closure_sha256, 'source closure'),
            (self.public_model_identity_sha256, 'public model'),
            (self.execution_identity_sha256, 'ExecutionSpec'),
        ):
            _sha(value, label)
        for value, label in (
            (self.provider_build_identity, 'provider build'),
            (self.physics_profile, 'physics profile'),
            (self.backend, 'backend'),
            (self.device, 'device'),
            (self.determinism_mode, 'determinism mode'),
            (self.tendon_name, 'tendon name'),
            (self.equality_name, 'equality name'),
        ):
            _token(value, label)
        _stable_identity(self.writer_id, 'writer ID')
        if self.host_model_producer_identity_sha256 is not None:
            _sha(self.host_model_producer_identity_sha256, 'host-model producer identity')
        if (type(self.physics_dt_s) not in (int, float) or isinstance(self.physics_dt_s, bool)
                or not math.isfinite(float(self.physics_dt_s)) or float(self.physics_dt_s) != 0.002
                or type(self.control_substeps) is not int or self.control_substeps != 5
                or type(self.native_dof_count) is not int or self.native_dof_count != 9):
            raise ValueError('GeoPhys source-actuation receipt requires nine scalar DOFs at five 2 ms steps')
        if type(self.drives) is not tuple or len(self.drives) != 9 or any(
                type(item) is not GeoPhysUsdPositionDriveV1 for item in self.drives):
            raise TypeError('GeoPhys source-actuation receipt requires nine immutable named DOF rows')
        expected = {
            JointReference('panda-main', f'joint{index}') for index in range(1, 8)
        } | {
            JointReference('panda-main', 'finger_joint1'),
            JointReference('panda-main', 'finger_joint2'),
        }
        if ({row.canonical_joint for row in self.drives} != expected
                or len({row.native_dof_name for row in self.drives}) != 9
                or sorted(row.native_dof_index for row in self.drives) != list(range(9))):
            raise ValueError('GeoPhys source-actuation receipt must bind all nine unique Panda DOFs')
        fingers = [row for row in self.drives if row.canonical_joint.joint_id.startswith('finger_joint')]
        arm = [row for row in self.drives if not row.canonical_joint.joint_id.startswith('finger_joint')]
        if (len(fingers) != 2 or len(arm) != 7
                or fingers[0].native_actuator_name != fingers[1].native_actuator_name
                or fingers[0].native_actuator_index != fingers[1].native_actuator_index
                or len({row.native_actuator_name for row in arm}) != 7
                or {row.native_actuator_name for row in arm} & {fingers[0].native_actuator_name}
                or len({row.native_actuator_index for row in (*arm, fingers[0])}) != 8):
            raise ValueError('GeoPhys source actuation must bind seven arm actuators and one shared tendon actuator')
        if (type(self.tendon_joint_names) is not tuple or self.tendon_joint_names != ('finger_joint1', 'finger_joint2')
                or type(self.tendon_coefficients) is not tuple or len(self.tendon_coefficients) != 2
                or any(type(value) not in (int, float) or isinstance(value, bool)
                       or not math.isfinite(float(value)) for value in self.tendon_coefficients)
                or tuple(float(value) for value in self.tendon_coefficients) != (0.5, 0.5)):
            raise ValueError('GeoPhys source tendon must bind both fingers with the authored 0.5/0.5 coefficients')
        if (type(self.equality_solref) is not tuple or len(self.equality_solref) != 2
                or type(self.equality_solimp) is not tuple or len(self.equality_solimp) != 3
                or any(type(value) not in (int, float) or isinstance(value, bool)
                       or not math.isfinite(float(value)) for value in (*self.equality_solref, *self.equality_solimp))):
            raise ValueError('GeoPhys source equality receipt requires finite solref(2) and solimp(3) values')

    @property
    def identity_sha256(self) -> str:
        payload = {
            'schema_version': self.schema_version,
            'provenance_kind': self.provenance_kind,
            'scene_identity_sha256': self.scene_identity_sha256,
            'source_closure_sha256': self.source_closure_sha256,
            'public_model_identity_sha256': self.public_model_identity_sha256,
            'execution_identity_sha256': self.execution_identity_sha256,
            'provider_build_identity': self.provider_build_identity,
            'physics_profile': self.physics_profile,
            'backend': self.backend, 'device': self.device,
            'determinism_mode': self.determinism_mode,
            'physics_dt_s': float(self.physics_dt_s),
            'control_substeps': self.control_substeps,
            'writer_id': self.writer_id,
            'drives': [(
                row.canonical_joint.entity_id, row.canonical_joint.joint_id,
                row.native_dof_name, row.native_dof_index,
                row.native_actuator_name, row.native_actuator_index,
                row.position_unit, float(row.lower_limit), float(row.upper_limit),
                float(row.gain), float(row.bias0), float(row.stiffness),
                float(row.damping), float(row.desired_velocity),
                float(row.coordinate_offset), float(row.joint_q0),
                row.control_limited, float(row.control_lower), float(row.control_upper),
                row.force_limited, float(row.force_lower), float(row.force_upper),
            ) for row in self.drives],
            'tendon_name': self.tendon_name,
            'tendon_joint_names': self.tendon_joint_names,
            'tendon_coefficients': self.tendon_coefficients,
            'equality_name': self.equality_name,
            'equality_solref': self.equality_solref,
            'equality_solimp': self.equality_solimp,
        }
        if self.host_model_producer_identity_sha256 is not None:
            payload['host_model_producer_identity_sha256'] = self.host_model_producer_identity_sha256
        return _digest(payload)

    def commands(self, arm_position: Mapping[str, float], hand_opening_m: float):
        expected_arm = {f'panda-main/joint{index}' for index in range(1, 8)}
        if not isinstance(arm_position, Mapping) or set(arm_position) != expected_arm:
            raise ValueError('Arm Position request must exactly cover canonical joint1 through joint7')
        if any(type(name) is not str or type(value) not in (int, float)
               or isinstance(value, bool) or not math.isfinite(float(value))
               for name, value in arm_position.items()):
            raise ValueError('Arm Position targets must be finite non-boolean numbers')
        if (type(hand_opening_m) not in (int, float) or isinstance(hand_opening_m, bool)
                or not math.isfinite(float(hand_opening_m)) or not 0.0 <= float(hand_opening_m) <= 0.08):
            raise ValueError('Hand opening target must be a finite value in [0, 0.08] metres')
        finger_rows = {row.canonical_joint.joint_id: row for row in self.drives
                       if row.canonical_joint.joint_id in self.tendon_joint_names}
        if set(finger_rows) != set(self.tendon_joint_names):
            raise ValueError('source-actuation receipt must bind both tendon finger joints')
        finger_upper = tuple(float(row.upper_limit) for row in finger_rows.values())
        max_common_opening = 2.0 * min(finger_upper)
        requested_opening = float(hand_opening_m)
        # USD-authored 0.04 m limits are read through the provider's float32
        # model. Preserve the canonical 0.08 m opening endpoint when its only
        # excess is that sub-2 nm encoding difference, then issue the exact
        # source-bounded per-finger target. Larger requests remain rejected.
        if requested_opening > max_common_opening + 2e-9:
            raise ValueError('Hand opening target exceeds a source finger-joint limit')
        half = min(requested_opening / 2.0, min(finger_upper))
        entity_id = self.drives[0].canonical_joint.entity_id
        positions = {JointReference(entity_id, name.split('/', 1)[1]): float(value)
                     for name, value in arm_position.items()}
        positions[JointReference(entity_id, 'finger_joint1')] = half
        positions[JointReference(entity_id, 'finger_joint2')] = half
        result = []
        for row in self.drives:
            target = positions[row.canonical_joint]
            if not row.lower_limit <= target <= row.upper_limit:
                raise ValueError(f'Position target exceeds native limit for {row.native_dof_name}')
            result.append((row.native_dof_index, row.native_dof_name, target))
        return tuple(sorted(result))

    def control_inputs(self, targets: tuple[tuple[int, str, float], ...]):
        by_name = {row.native_dof_name: row for row in self.drives}
        if (type(targets) is not tuple or len(targets) != 9
                or {name for _index, name, _value in targets} != set(by_name)):
            raise ValueError('GeoPhys control mapping requires the exact nine named Position targets')
        target_by_name = {}
        for index, name, target in targets:
            row = by_name.get(name)
            if (row is None or type(index) is not int or index != row.native_dof_index
                    or type(target) not in (int, float) or isinstance(target, bool)
                    or not math.isfinite(float(target))
                    or not row.lower_limit <= float(target) <= row.upper_limit):
                raise ValueError('GeoPhys Position target differs from its source-bound DOF receipt')
            target_by_name[name] = float(target)
        controls = []
        for row in self.drives:
            if row.canonical_joint.joint_id in self.tendon_joint_names:
                continue
            target = target_by_name[row.native_dof_name] + row.coordinate_offset
            value = (row.stiffness * target + row.damping * row.desired_velocity - row.bias0) / row.gain
            if not math.isfinite(value) or (row.control_limited and not row.control_lower <= value <= row.control_upper):
                raise ValueError(f'GeoPhys Position control exceeds source limits for {row.native_dof_name}')
            controls.append((row.native_actuator_index, row.native_actuator_name, value))
        fingers = [by_name[name] for name in ('finger_joint1', 'finger_joint2')]
        q1, q2 = (target_by_name[row.native_dof_name] for row in fingers)
        if abs(q1 - q2) > 1e-9:
            raise ValueError('shared tendon Position control requires equal source finger targets')
        tendon_length = sum(float(c) * q for c, q in zip(self.tendon_coefficients, (q1, q2)))
        row = fingers[0]
        value = (row.stiffness * tendon_length + row.damping * row.desired_velocity - row.bias0) / row.gain
        if not math.isfinite(value) or (row.control_limited and not row.control_lower <= value <= row.control_upper):
            raise ValueError('GeoPhys tendon Position control exceeds the source actuator ctrl range')
        controls.append((row.native_actuator_index, row.native_actuator_name, value))
        if len({index for index, _name, _value in controls}) != 8:
            raise ValueError('GeoPhys source control mapping did not produce eight unique actuator channels')
        return tuple(sorted(controls))


def compile_isaac_named_position_drive_receipt_v1(
    *, execution: ExecutionSpecV1, scene_identity_sha256: str,
    source_closure_sha256: str, provider_build_identity: str,
    writer_id: str, native_dof_names: tuple[str, ...],
    native_position_limits: Mapping[str, tuple[float, float]],
    canonical_native_names: Mapping[str, str] | None = None,
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
    canonical_joint_ids = tuple(f'panda-main/joint{index}' for index in range(1, 8)) + (
        'panda-main/finger_joint1', 'panda-main/finger_joint2',
    )
    default_names = {key: key.replace('panda-main/', 'panda_') for key in canonical_joint_ids}
    native_names = default_names if canonical_native_names is None else dict(canonical_native_names)
    if set(native_names) != set(canonical_joint_ids) or len(set(native_names.values())) != 9:
        raise ValueError('canonical-to-native mapping must cover the nine Panda joints bijectively')
    allowed_name_sets = (
        {key: key.replace('panda-main/', 'panda_') for key in canonical_joint_ids},
        {key: key.split('/', 1)[1] for key in canonical_joint_ids},
    )
    if native_names not in allowed_name_sets:
        raise ValueError('canonical-to-native mapping is outside the two frozen Panda name profiles')
    by_name = {
        native_names[f'panda-main/{joint_id}']: (
            JointReference('panda-main', joint_id),
            'meter' if joint_id.startswith('finger_joint') else 'radian',
        )
        for joint_id in (f'joint{index}' for index in range(1, 8))
    }
    by_name.update({
        native_names[f'panda-main/{joint_id}']: (JointReference('panda-main', joint_id), 'meter')
        for joint_id in ('finger_joint1', 'finger_joint2')
    })
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


def compile_isaac_named_position_drive_receipt_from_native_metadata_v1(
    *, execution: ExecutionSpecV1, source, scene_identity_sha256: str,
    native_metadata, writer_id: str,
) -> IsaacNamedPositionDriveReceiptV1:
    """Compile a production receipt only after the public articulation view exists."""
    from .native_io import NativeRuntimeIOMetadataV1
    from .source import UsdRuntimeSourceV1

    if type(execution) is not ExecutionSpecV1 or type(source) is not UsdRuntimeSourceV1:
        raise TypeError('native drive receipt requires exact versioned Core contracts')
    if type(native_metadata) is not NativeRuntimeIOMetadataV1:
        raise TypeError('native drive receipt requires actual NativeRuntimeIOMetadataV1')
    source.validate()
    execution.validate()
    if not (source.scene_source.source_verified or source.scene_source.locally_validated):
        raise ValueError('native drive receipt requires an upstream-validated or fixed locally validated F04 USD source')
    native_metadata.validate_binding(source.task_artifact, execution, source)
    if (native_metadata.provider_build_identity, native_metadata.physics_provider,
            native_metadata.backend, native_metadata.device, native_metadata.determinism_mode) != (
            'isaacsim-6.2.0.0', 'isaacsim', 'cuda', 'cuda:0', 'best_effort'):
        raise ValueError('native drive receipt metadata differs from the exact F04 execution')
    base = compile_isaac_named_position_drive_receipt_v1(
        execution=execution, scene_identity_sha256=scene_identity_sha256,
        source_closure_sha256=source.source_closure_digest,
        provider_build_identity=native_metadata.provider_build_identity,
        writer_id=writer_id, native_dof_names=native_metadata.native_dof_names,
        native_position_limits=native_metadata.native_position_limits,
        canonical_native_names=dict(source.joint_targets),
    )
    expected_targets = {
        f'{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}': item.native_dof_name
        for item in base.drives
    }
    if dict(source.joint_targets) != expected_targets:
        raise ValueError('verified USD RuntimeSource targets do not bind actual native DOF names')
    return replace(base, provenance_kind='native_runtime')


def compile_isaac_native_mimic_position_receipt_v1(
    *, execution: ExecutionSpecV1, source, native_metadata, writer_id: str,
    native_drive_witness: Mapping[str, object], provenance_kind: str = 'native_runtime',
) -> IsaacNativeMimicPositionDriveReceiptV1:
    """Bind the fixed DG04 PhysX mimic/leader-drive configuration to live public views."""
    from .native_io import NativeRuntimeIOMetadataV1
    from .source import UsdRuntimeSourceV1

    if type(execution) is not ExecutionSpecV1 or type(source) is not UsdRuntimeSourceV1:
        raise TypeError('DG04 receipt compiler requires exact versioned Core contracts')
    if type(native_metadata) is not NativeRuntimeIOMetadataV1:
        raise TypeError('DG04 receipt compiler requires public NativeRuntimeIOMetadataV1')
    if provenance_kind not in {'synthetic_fixture', 'native_runtime'}:
        raise ValueError('DG04 receipt compiler requires explicit execution provenance')
    source.validate()
    execution.validate()
    native_metadata.validate_binding(source.task_artifact, execution, source)
    f06_profile = execution.physics_profile == 'isaac-gpu-physx-pickcube-f06-v1'
    expected_profile = (
        'isaac-gpu-physx-pickcube-f06-v1' if f06_profile
        else 'isaac-gpu-physx-f05-dg04-native-mimic-v1'
    )
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.determinism_mode, execution.physics_profile) != (
            'isaacsim', 'cuda', 'cuda:0', 'best_effort', expected_profile):
        raise ValueError('native mimic receipt compiler refuses a different Isaac execution profile')
    if (native_metadata.provider_build_identity, native_metadata.physics_provider,
            native_metadata.backend, native_metadata.device, native_metadata.determinism_mode) != (
            'isaacsim-6.2.0.0', 'isaacsim', 'cuda', 'cuda:0', 'best_effort'):
        raise ValueError('DG04 receipt compiler refuses a different public Isaac build/device')
    expected_entity = 'panda-v1' if f06_profile else 'panda-main'
    expected_targets = {
        **{f'{expected_entity}/joint{index}': f'joint{index}' for index in range(1, 8)},
        f'{expected_entity}/finger_joint1': 'finger_joint1',
        f'{expected_entity}/finger_joint2': 'finger_joint2',
    }
    if dict(source.joint_targets) != expected_targets or dict(source.joints) != expected_targets:
        raise ValueError('DG04 source joint map differs from its exact nine-DOF Menagerie map')
    if not isinstance(native_drive_witness, Mapping):
        raise TypeError('DG04 receipt requires the exact public native drive/mimic witness')
    expected_active = [f'joint{index}' for index in range(1, 8)] + ['finger_joint1']
    expected_witness = {
        'schema_version': (
            'isaac-f06-pickcube-native-mimic-drive-witness-v1' if f06_profile
            else 'isaac-dg04-native-mimic-drive-witness-v1'
        ),
        'active_drive_dofs': expected_active,
        'passive_mimic_dof': 'finger_joint2',
        'leader_stiffness_N_m': 5000.0 if f06_profile else 2000.0,
        'leader_damping_N_s_m': 120.0 if f06_profile else 100.0,
        'leader_max_effort_N': 5.0 if f06_profile else 100.0,
        'leader_drive_type': 'force',
        'follower_stiffness_N_m': 0.0,
        'follower_damping_N_s_m': 0.0,
        'follower_drive_type': 'none',
        'mimic_api': 'PhysxMimicJointAPI:transX',
        'drive_api': 'PhysicsDriveAPI:linear',
        'mimic_reference_joint': 'finger_joint1',
        'mimic_follower_joint': 'finger_joint2',
        'mimic_gearing': 1.0,
        'mimic_offset_m': 0.0,
        'mimic_natural_frequency_hz': 25.0,
        'mimic_damping_ratio': 1.0,
        'passive_mimic_constraint_authored': True,
    }
    if any(native_drive_witness.get(key) != value for key, value in expected_witness.items()):
        raise ValueError('DG04 public drive/mimic witness differs from the fixed native profile')
    if (type(native_metadata.native_dof_names) is not tuple
            or set(native_metadata.native_dof_names) != set(expected_targets.values())
            or len(native_metadata.native_dof_names) != 9):
        raise ValueError('DG04 public articulation metadata differs from the exact nine source DOFs')
    limits = dict(native_metadata.native_position_limits)
    native_to_canonical = {value: key for key, value in expected_targets.items()}
    active_set = set(expected_active)
    drives = []
    for index, native_name in enumerate(native_metadata.native_dof_names):
        if native_name not in active_set:
            continue
        canonical = native_to_canonical[native_name]
        low, high = limits[native_name]
        drives.append(IsaacNamedPositionDriveV1(
            'isaac-named-position-drive-v1',
            JointReference(*canonical.split('/', 1)), native_name, index,
            'meter' if native_name == 'finger_joint1' else 'radian',
            float(low), float(high),
        ))
    return IsaacNativeMimicPositionDriveReceiptV1(
        'isaac-native-mimic-position-drive-receipt-v1', provenance_kind,
        source.scene_definition.identity_hash, source.source_closure_digest,
        execution.identity_hash, native_metadata.provider_build_identity,
        execution.physics_profile, execution.physics_backend, execution.physics_device,
        execution.determinism_mode, float(source.task_artifact.timebase.physics_dt),
        int(source.task_artifact.timebase.control_substeps), writer_id,
        tuple(native_metadata.native_dof_names), limits, tuple(drives),
        gripper_drive_stiffness_N_m=5000.0 if f06_profile else 2000.0,
        gripper_drive_damping_N_s_m=120.0 if f06_profile else 100.0,
        gripper_force_limit_N=5.0 if f06_profile else 100.0,
    )


@dataclass(frozen=True)
class IsaacSourceEqualityComplianceV1:
    """Source-bound MuJoCo solimp/solref mapping for a PhysX mimic joint.

    The MJCF three-value solimp form is expanded with MuJoCo's documented
    midpoint/power defaults.  The supported source is deliberately the exact
    Menagerie Panda affine finger equality; this does not implement a general
    constraint solver.
    """

    schema_version: str
    reference_joint: str
    follower_joint: str
    source_solref: tuple[float, float]
    source_solimp_raw: tuple[float, float, float]
    source_solimp_effective: tuple[float, float, float, float, float]
    mapping_algorithm: str = 'mujoco-3.8.1-solimp-reference-to-physx-mimic-v4-homogeneous'

    def __post_init__(self):
        if self.schema_version != 'isaac-source-equality-compliance-v1':
            raise ValueError('unsupported Isaac source equality-compliance schema')
        if (self.reference_joint, self.follower_joint) != ('finger_joint1', 'finger_joint2'):
            raise ValueError('DG03 compliance must bind the exact source finger equality pair')
        if self.mapping_algorithm != 'mujoco-3.8.1-solimp-reference-to-physx-mimic-v4-homogeneous':
            raise ValueError('DG03 compliance mapping must identify the pinned MuJoCo algorithm')
        if (tuple(self.source_solref) != (0.005, 1.0)
                or tuple(self.source_solimp_raw) != (0.95, 0.99, 0.001)
                or tuple(self.source_solimp_effective) != (0.95, 0.99, 0.001, 0.5, 2.0)):
            raise ValueError('DG03 equality-compliance values differ from the exact pinned MJCF profile')

    def impedance(self, residual_m: float) -> float:
        """Return MuJoCo 3.8.1 getimpedance(solimp, residual, margin=0)."""
        if (type(residual_m) not in (int, float) or isinstance(residual_m, bool)
                or not math.isfinite(float(residual_m))):
            raise ValueError('DG03 equality residual must be a finite non-boolean scalar')
        d0, dwidth, width, midpoint, power = self.source_solimp_effective
        x = abs(float(residual_m)) / width
        if x >= 1.0:
            return dwidth
        if x <= 0.0:
            return d0
        if power == 1.0:
            y = x
        elif x <= midpoint:
            y = x ** power / midpoint ** (power - 1.0)
        else:
            y = 1.0 - (1.0 - x) ** power / (1.0 - midpoint) ** (power - 1.0)
        return d0 + y * (dwidth - d0)

    def natural_frequency_hz(self, residual_m: float) -> float:
        """Map the source homogeneous equality term to a PhysX spring frequency.

        MuJoCo 3.8.1 uses aref=-B*v-K0*d(r)*r and blends it as
        a1=(1-d(r))*a0+d(r)*aref.  Under the declared single-constraint,
        a0=0 approximation, the effective stiffness is d(r)^2*K0.  This
        does not represent the unconstrained-acceleration blend, effective
        mass, or interactions with other constraints.
        """
        d = self.impedance(residual_m)
        _d0, dwidth, _width, _midpoint, _power = self.source_solimp_effective
        timeconst, dampratio = self.source_solref
        omega = d / (dwidth * timeconst * dampratio)
        return omega / (2.0 * math.pi)

    def damping_ratio_for_residual(self, residual_m: float) -> float:
        """Return the source homogeneous damping ratio, after validating residual."""
        self.impedance(residual_m)
        return self.source_solref[1]

    def to_mapping(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'reference_joint': self.reference_joint,
            'follower_joint': self.follower_joint,
            'source_solref': list(self.source_solref),
            'source_solimp_raw': list(self.source_solimp_raw),
            'source_solimp_effective': list(self.source_solimp_effective),
            'mapping_algorithm': self.mapping_algorithm,
            'physx_natural_frequency_rule':
                'd(abs(follower_q-reference_q))/(2*pi*dwidth*timeconst*dampratio)',
            'physx_damping_ratio_rule': 'solref_dampratio',
            'source_reference_acceleration': 'aref=-B*v-K0*d(r)*r; a1=(1-d(r))*a0+d(r)*aref',
            'homogeneous_single_constraint_coefficients': {
                'assumption': 'a0=0; one equality constraint; no effective-mass or other-constraint interaction',
                'omega_squared': 'd(r)^2*K0',
                'effective_damping': 'd(r)*B',
                'natural_frequency_hz': 'd(r)/(2*pi*dwidth*timeconst*dampratio)',
                'damping_ratio': 'dampratio',
                'excluded_terms': '(1-d(r))*a0; effective mass; coupling to other constraints',
            },
        }


@dataclass(frozen=True)
class IsaacSourceTendonDriveReceiptV1:
    """Model-bound Isaac receipt for seven arm drives and a source tendon."""

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
    native_dof_names: tuple[str, ...]
    native_position_limits: Mapping[str, tuple[float, float]]
    arm_drives: tuple[IsaacNamedPositionDriveV1, ...]
    mimic_follower_joint: str = 'finger_joint2'
    mimic_reference_joint: str = 'finger_joint1'
    mimic_gearing: float = 1.0
    mimic_offset_m: float = 0.0
    mimic_natural_frequency_hz: float = 31.830988618379067
    mimic_damping_ratio: float = 1.0
    mimic_source_solref: tuple[float, float] = (0.005, 1.0)
    mimic_source_solimp: tuple[float, float, float] = (0.95, 0.99, 0.001)
    tendon_name: str = 'split'
    tendon_joint_names: tuple[str, str] = (
        'panda-main/finger_joint1', 'panda-main/finger_joint2',
    )
    tendon_native_joint_names: tuple[str, str] = ('finger_joint1', 'finger_joint2')
    tendon_coefficients: tuple[float, float] = (0.5, 0.5)
    actuator_name: str = 'actuator8'
    actuator_gain: float = 0.01568627451
    actuator_length_bias: float = -100.0
    actuator_rate_bias: float = -10.0
    actuator_control_range: tuple[float, float] = (0.0, 255.0)
    actuator_force_range: tuple[float, float] = (-100.0, 100.0)
    canonical_opening_range_m: float = 0.08
    equality_compliance: IsaacSourceEqualityComplianceV1 | None = None
    arm_control_ranges: Mapping[str, tuple[float, float]] | None = None
    arm_stiffnesses: Mapping[str, float] | None = None
    arm_dampings: Mapping[str, float] | None = None
    arm_max_efforts: Mapping[str, float] | None = None

    def __post_init__(self):
        if self.schema_version != 'isaac-source-tendon-drive-receipt-v1':
            raise ValueError('unsupported Isaac source tendon receipt schema')
        if self.provenance_kind not in {'synthetic_fixture', 'native_runtime'}:
            raise ValueError('Isaac tendon receipt provenance must be explicit')
        for value, label in (
            (self.scene_identity_sha256, 'Scene'),
            (self.source_closure_sha256, 'source closure'),
            (self.execution_identity_sha256, 'ExecutionSpec'),
        ):
            _sha(value, label)
        if (self.provider_build_identity, self.physics_profile, self.backend,
                self.device, self.determinism_mode, self.physics_dt_s,
                self.control_substeps) != (
                'isaacsim-6.2.0.0', 'isaac-gpu-physx-f05-dg03-usd-v1',
                'cuda', 'cuda:0', 'best_effort', 0.002, 5):
            raise ValueError('DG03 tendon receipt differs from the frozen Isaac execution profile')
        _stable_identity(self.writer_id, 'writer ID')
        names = tuple(self.native_dof_names)
        expected_names = {f'joint{index}' for index in range(1, 8)} | {
            'finger_joint1', 'finger_joint2',
        }
        if len(names) != 9 or len(set(names)) != 9 or set(names) != expected_names:
            raise ValueError('DG03 receipt requires the exact nine named Menagerie Panda DOFs')
        limits = {name: tuple(value) for name, value in dict(self.native_position_limits).items()}
        if set(limits) != set(names):
            raise ValueError('DG03 public DOF limits must cover all nine mapped DOFs')
        for name, value in limits.items():
            if (len(value) != 2 or any(type(x) not in (int, float) or isinstance(x, bool)
                                       or not math.isfinite(float(x)) for x in value)
                    or float(value[0]) >= float(value[1])):
                raise ValueError(f'DG03 position limits for {name} are invalid')
            limits[name] = (float(value[0]), float(value[1]))
        object.__setattr__(self, 'native_dof_names', names)
        object.__setattr__(self, 'native_position_limits', MappingProxyType(limits))
        drives = tuple(self.arm_drives)
        expected_arm = {JointReference('panda-main', f'joint{index}') for index in range(1, 8)}
        if (len(drives) != 7 or any(type(row) is not IsaacNamedPositionDriveV1 for row in drives)
                or {row.canonical_joint for row in drives} != expected_arm):
            raise ValueError('DG03 requires exactly seven typed canonical Arm position drives')
        if any(row.position_unit != 'radian' or names[row.native_dof_index] != row.native_dof_name
               or (float(row.lower_limit), float(row.upper_limit)) != limits[row.native_dof_name]
               for row in drives):
            raise ValueError('DG03 Arm drive name/index/unit/limits differ from public DOF metadata')
        if len({row.native_dof_index for row in drives}) != 7:
            raise ValueError('DG03 Arm native indices must be unique')
        if (self.mimic_follower_joint, self.mimic_reference_joint,
                float(self.mimic_gearing), float(self.mimic_offset_m),
                float(self.mimic_damping_ratio), tuple(self.mimic_source_solref),
                tuple(self.mimic_source_solimp), self.tendon_name, tuple(self.tendon_joint_names),
                tuple(self.tendon_native_joint_names), tuple(self.tendon_coefficients),
                self.actuator_name, float(self.actuator_gain),
                float(self.actuator_length_bias), float(self.actuator_rate_bias),
                tuple(self.actuator_control_range), tuple(self.actuator_force_range),
                float(self.canonical_opening_range_m)) != (
                'finger_joint2', 'finger_joint1', 1.0, 0.0, 1.0, (0.005, 1.0),
                (0.95, 0.99, 0.001),
                'split', ('panda-main/finger_joint1', 'panda-main/finger_joint2'),
                ('finger_joint1', 'finger_joint2'), (0.5, 0.5), 'actuator8',
                0.01568627451, -100.0, -10.0, (0.0, 255.0), (-100.0, 100.0), 0.08):
            raise ValueError('DG03 receipt does not encode the exact source tendon/actuator law')
        if (type(self.mimic_natural_frequency_hz) not in (int, float)
                or isinstance(self.mimic_natural_frequency_hz, bool)
                or not math.isclose(float(self.mimic_natural_frequency_hz),
                                    1.0 / (2.0 * math.pi * self.mimic_source_solref[0]
                                           * self.mimic_source_solref[1]),
                                    rel_tol=0.0, abs_tol=1e-12)):
            raise ValueError('DG03 mimic frequency must be derived from the exact MJCF solref/solimp')
        if any(names.index(name) in {row.native_dof_index for row in drives}
               for name in self.tendon_native_joint_names):
            raise ValueError('DG03 tendon finger DOFs must remain state-only, outside Arm drives')
        if (self.equality_compliance is not None
                and (type(self.equality_compliance) is not IsaacSourceEqualityComplianceV1
                     or self.equality_compliance.source_solref != tuple(self.mimic_source_solref)
                     or self.equality_compliance.source_solimp_raw != tuple(self.mimic_source_solimp))):
            raise ValueError('DG03 equality-compliance component differs from the tendon receipt source identity')
        arm_names = {f'joint{index}' for index in range(1, 8)}
        if any(value is not None for value in (
                self.arm_control_ranges, self.arm_stiffnesses,
                self.arm_dampings, self.arm_max_efforts)):
            if any(value is None for value in (
                    self.arm_control_ranges, self.arm_stiffnesses,
                    self.arm_dampings, self.arm_max_efforts)):
                raise ValueError('DG03 Arm source law must bind controls, gains, damping and force limits together')
            ranges = {name: tuple(values) for name, values in dict(self.arm_control_ranges).items()}
            stiffnesses = {name: float(value) for name, value in dict(self.arm_stiffnesses).items()}
            dampings = {name: float(value) for name, value in dict(self.arm_dampings).items()}
            efforts = {name: float(value) for name, value in dict(self.arm_max_efforts).items()}
            if any(set(value) != arm_names for value in (ranges, stiffnesses, dampings, efforts)):
                raise ValueError('DG03 source Arm law must cover exactly joints1 through joint7')
            expected_source = {
                'joint1': ((-2.8973, 2.8973), 4500.0, 450.0, 87.0),
                'joint2': ((-1.7628, 1.7628), 4500.0, 450.0, 87.0),
                'joint3': ((-2.8973, 2.8973), 3500.0, 350.0, 87.0),
                'joint4': ((-3.0718, -0.0698), 3500.0, 350.0, 87.0),
                'joint5': ((-2.8973, 2.8973), 2000.0, 200.0, 12.0),
                'joint6': ((-0.0175, 3.7525), 2000.0, 200.0, 12.0),
                'joint7': ((-2.8973, 2.8973), 2000.0, 200.0, 12.0),
            }
            for name, (control_range, kp, kd, max_effort) in expected_source.items():
                values = ranges[name]
                if (len(values) != 2 or any(not math.isfinite(float(x)) for x in values)
                        or tuple(float(x) for x in values) != control_range
                        or stiffnesses[name] != kp or dampings[name] != kd
                        or efforts[name] != max_effort):
                    raise ValueError(f'DG03 source Arm drive law differs from pinned actuator {name}')
                ranges[name] = control_range
            object.__setattr__(self, 'arm_control_ranges', MappingProxyType(ranges))
            object.__setattr__(self, 'arm_stiffnesses', MappingProxyType(stiffnesses))
            object.__setattr__(self, 'arm_dampings', MappingProxyType(dampings))
            object.__setattr__(self, 'arm_max_efforts', MappingProxyType(efforts))
        elif self.equality_compliance is not None:
            raise ValueError('DG03 source-bound receipt requires the exact source Arm actuator law')
        object.__setattr__(self, 'arm_drives', drives)

    @property
    def drives(self):
        """The seven position-driven Arm joints; finger joints are state-only."""
        return self.arm_drives

    @property
    def joint_targets(self) -> dict[str, str]:
        result = {
            f'{row.canonical_joint.entity_id}/{row.canonical_joint.joint_id}': row.native_dof_name
            for row in self.arm_drives
        }
        result.update(dict(zip(self.tendon_joint_names, self.tendon_native_joint_names, strict=True)))
        return result

    @property
    def identity_sha256(self) -> str:
        return _digest({
            'schema_version': self.schema_version, 'provenance_kind': self.provenance_kind,
            'scene_identity_sha256': self.scene_identity_sha256,
            'source_closure_sha256': self.source_closure_sha256,
            'execution_identity_sha256': self.execution_identity_sha256,
            'provider_build_identity': self.provider_build_identity,
            'physics_profile': self.physics_profile, 'backend': self.backend,
            'device': self.device, 'determinism_mode': self.determinism_mode,
            'physics_dt_s': float(self.physics_dt_s), 'control_substeps': self.control_substeps,
            'writer_id': self.writer_id, 'native_dof_names': list(self.native_dof_names),
            'native_position_limits': {name: list(self.native_position_limits[name])
                                       for name in self.native_dof_names},
            'arm_drives': [(row.canonical_joint.entity_id, row.canonical_joint.joint_id,
                            row.native_dof_name, row.native_dof_index, row.position_unit,
                            float(row.lower_limit), float(row.upper_limit)) for row in self.arm_drives],
            'mimic_follower_joint': self.mimic_follower_joint,
            'mimic_reference_joint': self.mimic_reference_joint,
            'mimic_gearing': float(self.mimic_gearing),
            'mimic_offset_m': float(self.mimic_offset_m),
            'mimic_natural_frequency_hz': float(self.mimic_natural_frequency_hz),
            'mimic_damping_ratio': float(self.mimic_damping_ratio),
            'mimic_source_solref': list(self.mimic_source_solref),
            'mimic_source_solimp': list(self.mimic_source_solimp),
            'tendon_name': self.tendon_name, 'tendon_joint_names': list(self.tendon_joint_names),
            'tendon_native_joint_names': list(self.tendon_native_joint_names),
            'tendon_coefficients': list(self.tendon_coefficients),
            'actuator_name': self.actuator_name, 'actuator_gain': float(self.actuator_gain),
            'actuator_length_bias': float(self.actuator_length_bias),
            'actuator_rate_bias': float(self.actuator_rate_bias),
            'actuator_control_range': list(self.actuator_control_range),
            'actuator_force_range': list(self.actuator_force_range),
            'canonical_opening_range_m': float(self.canonical_opening_range_m),
            'equality_compliance': (
                None if self.equality_compliance is None else self.equality_compliance.to_mapping()
            ),
            'arm_control_ranges': (
                None if self.arm_control_ranges is None else
                {name: list(self.arm_control_ranges[name]) for name in sorted(self.arm_control_ranges)}
            ),
            'arm_stiffnesses': None if self.arm_stiffnesses is None else dict(self.arm_stiffnesses),
            'arm_dampings': None if self.arm_dampings is None else dict(self.arm_dampings),
            'arm_max_efforts': None if self.arm_max_efforts is None else dict(self.arm_max_efforts),
        })

    def mimic_frequency_for_residual(self, residual_m: float) -> float:
        if type(self.equality_compliance) is not IsaacSourceEqualityComplianceV1:
            raise RuntimeError('DG03 source equality compliance was not bound to this model receipt')
        return self.equality_compliance.natural_frequency_hz(residual_m)

    def mimic_damping_ratio_for_residual(self, residual_m: float) -> float:
        if type(self.equality_compliance) is not IsaacSourceEqualityComplianceV1:
            raise RuntimeError('DG03 source equality compliance was not bound to this model receipt')
        return self.equality_compliance.damping_ratio_for_residual(residual_m)

    def arm_commands(self, arm_position: Mapping[str, float]):
        expected = {f'panda-main/joint{index}' for index in range(1, 8)}
        if not isinstance(arm_position, Mapping) or set(arm_position) != expected:
            raise ValueError('DG03 Arm command must cover exactly canonical joint1 through joint7')
        by_joint = {f'{row.canonical_joint.entity_id}/{row.canonical_joint.joint_id}': row
                    for row in self.arm_drives}
        rows = []
        for key, raw in arm_position.items():
            if (type(raw) not in (int, float) or isinstance(raw, bool)
                    or not math.isfinite(float(raw))):
                raise ValueError('DG03 Arm target must be a finite non-boolean scalar')
            row = by_joint[key]
            value = float(raw)
            if not row.lower_limit <= value <= row.upper_limit:
                raise ValueError(f'DG03 Arm target is outside public limits for {key}')
            if self.arm_control_ranges is not None:
                control_low, control_high = self.arm_control_ranges[row.native_dof_name]
                value = min(control_high, max(control_low, value))
            rows.append((row.native_dof_index, row.native_dof_name, value))
        return tuple(sorted(rows))

    def tendon_control(self, opening_m: float, force_limit_N: float) -> tuple[float, float]:
        for value, label in ((opening_m, 'opening'), (force_limit_N, 'force limit')):
            if (type(value) not in (int, float) or isinstance(value, bool)
                    or not math.isfinite(float(value))):
                raise ValueError(f'DG03 tendon {label} must be finite')
        opening, force_limit = float(opening_m), float(force_limit_N)
        if not 0.0 <= opening <= self.canonical_opening_range_m:
            raise ValueError('DG03 tendon opening is outside the canonical 0..0.08 m range')
        if not 0.0 <= force_limit <= self.actuator_force_range[1]:
            raise ValueError('DG03 requested scalar force limit is outside the source actuator range')
        ctrl = self.actuator_control_range[1] * opening / self.canonical_opening_range_m
        return (float(min(self.actuator_control_range[1], max(self.actuator_control_range[0], ctrl))),
                force_limit)


def compile_isaac_source_tendon_receipt_v1(
    *, execution: ExecutionSpecV1, source, native_metadata, writer_id: str,
    provenance_kind: str = 'native_runtime',
) -> IsaacSourceTendonDriveReceiptV1:
    """Bind the exact DG03 source law to public Isaac Articulation metadata."""
    from .native_io import NativeRuntimeIOMetadataV1
    from .source import UsdRuntimeSourceV1

    if type(execution) is not ExecutionSpecV1 or type(source) is not UsdRuntimeSourceV1:
        raise TypeError('DG03 receipt compiler requires exact versioned Execution/RuntimeSource contracts')
    if type(native_metadata) is not NativeRuntimeIOMetadataV1:
        raise TypeError('DG03 receipt compiler requires public NativeRuntimeIOMetadataV1')
    source.validate()
    execution.validate()
    native_metadata.validate_binding(source.task_artifact, execution, source)
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.determinism_mode, execution.physics_profile) != (
            'isaacsim', 'cuda', 'cuda:0', 'best_effort', 'isaac-gpu-physx-f05-dg03-usd-v1'):
        raise ValueError('DG03 receipt compiler refuses a different Isaac execution profile')
    if (native_metadata.provider_build_identity, native_metadata.physics_provider,
            native_metadata.backend, native_metadata.device, native_metadata.determinism_mode) != (
            'isaacsim-6.2.0.0', 'isaacsim', 'cuda', 'cuda:0', 'best_effort'):
        raise ValueError('DG03 receipt compiler refuses a different public Isaac build/device')
    expected_targets = {
        **{f'panda-main/joint{index}': f'joint{index}' for index in range(1, 8)},
        'panda-main/finger_joint1': 'finger_joint1',
        'panda-main/finger_joint2': 'finger_joint2',
    }
    if dict(source.joint_targets) != expected_targets or dict(source.joints) != expected_targets:
        raise ValueError('DG03 source joint map differs from its exact nine-DOF Menagerie map')
    if set(native_metadata.native_dof_names) != set(expected_targets.values()):
        raise ValueError('DG03 public articulation names differ from the exact source map')
    drives = []
    for index, native_name in enumerate(native_metadata.native_dof_names):
        canonical = next(key for key, value in expected_targets.items() if value == native_name)
        if '/joint' not in canonical:
            continue
        lower, upper = native_metadata.native_position_limits[native_name]
        drives.append(IsaacNamedPositionDriveV1(
            'isaac-named-position-drive-v1',
            JointReference('panda-main', canonical.split('/', 1)[1]),
            native_name, index, 'radian', float(lower), float(upper),
        ))
    source_xml = source.scene_source.loaded_delivery.source_input_bytes.get('panda.xml')
    if type(source_xml) is not bytes:
        raise ValueError('DG03 source tendon receipt requires the exact source MJCF bytes')
    import xml.etree.ElementTree as ET
    root = ET.fromstring(source_xml)
    equality_rows = root.findall('./equality/joint')
    if len(equality_rows) != 1:
        raise ValueError('DG03 source tendon receipt requires its exact one joint equality')
    equality = equality_rows[0]
    if (equality.get('joint1'), equality.get('joint2'), equality.get('active', 'true')) != (
            'finger_joint1', 'finger_joint2', 'true'):
        raise ValueError('DG03 source tendon receipt equality differs from its source finger pair')
    polycoef = tuple(float(x) for x in equality.get('polycoef', '0 1 0 0 0').split())
    solref = tuple(float(x) for x in equality.get('solref', '0.02 1').split())
    solimp = tuple(float(x) for x in equality.get('solimp', '0.9 0.95 0.001').split())
    if (polycoef != (0.0, 1.0, 0.0, 0.0, 0.0)
            or solref != (0.005, 1.0) or solimp != (0.95, 0.99, 0.001)):
        raise ValueError('DG03 source equality is outside its exact affine/compliance profile')
    default_actuator = root.find("./default/default[@class='panda']/general")
    if default_actuator is None:
        raise ValueError('DG03 source omits exact Panda default actuator ranges')
    default_ctrlrange = tuple(float(x) for x in default_actuator.get('ctrlrange', '').split())
    default_forcerange = tuple(float(x) for x in default_actuator.get('forcerange', '').split())
    if len(default_ctrlrange) != 2 or len(default_forcerange) != 2:
        raise ValueError('DG03 source default actuator ranges must contain two values')
    actuator_by_joint = {}
    for actuator in root.findall('./actuator/general'):
        joint = actuator.get('joint')
        if joint is None:
            continue
        gain = tuple(float(x) for x in actuator.get('gainprm', '').split())
        bias = tuple(float(x) for x in actuator.get('biasprm', '').split())
        ctrlrange = tuple(float(x) for x in actuator.get('ctrlrange', '').split()) or default_ctrlrange
        forcerange = tuple(float(x) for x in actuator.get('forcerange', '').split()) or default_forcerange
        if (len(gain) != 1 or len(bias) != 3 or len(ctrlrange) != 2 or len(forcerange) != 2
                or bias[0] != 0.0 or gain[0] != -bias[1]):
            raise ValueError(f'DG03 source actuator law is outside the exact affine PD subset: {joint}')
        if joint in actuator_by_joint:
            raise ValueError(f'DG03 source has duplicate Arm actuator for {joint}')
        actuator_by_joint[joint] = {
            'control_range': ctrlrange,
            'stiffness': gain[0],
            'damping': -bias[2],
            'max_effort': max(abs(forcerange[0]), abs(forcerange[1])),
        }
    expected_joint_names = {f'joint{index}' for index in range(1, 8)}
    if set(actuator_by_joint) != expected_joint_names:
        raise ValueError('DG03 source actuator set differs from exact Arm joints1 through joint7')
    native_by_joint = {row.canonical_joint.joint_id: row.native_dof_name for row in drives}
    arm_control_ranges = {
        native_by_joint[joint]: actuator_by_joint[joint]['control_range'] for joint in expected_joint_names
    }
    arm_stiffnesses = {
        native_by_joint[joint]: actuator_by_joint[joint]['stiffness'] for joint in expected_joint_names
    }
    arm_dampings = {
        native_by_joint[joint]: actuator_by_joint[joint]['damping'] for joint in expected_joint_names
    }
    arm_max_efforts = {
        native_by_joint[joint]: actuator_by_joint[joint]['max_effort'] for joint in expected_joint_names
    }
    return IsaacSourceTendonDriveReceiptV1(
        'isaac-source-tendon-drive-receipt-v1', provenance_kind,
        source.scene_definition.identity_hash, source.source_closure_digest,
        execution.identity_hash, native_metadata.provider_build_identity,
        execution.physics_profile, execution.physics_backend, execution.physics_device,
        execution.determinism_mode, float(source.task_artifact.timebase.physics_dt),
        int(source.task_artifact.timebase.control_substeps), writer_id,
        tuple(native_metadata.native_dof_names), native_metadata.native_position_limits,
        tuple(drives),
        mimic_natural_frequency_hz=1.0 / (2.0 * math.pi * solref[0] * solref[1]),
        mimic_damping_ratio=solref[1], mimic_source_solref=solref,
        mimic_source_solimp=solimp,
        equality_compliance=IsaacSourceEqualityComplianceV1(
            'isaac-source-equality-compliance-v1', 'finger_joint1', 'finger_joint2',
            solref, solimp, (*solimp, 0.5, 2.0),
        ),
        arm_control_ranges=arm_control_ranges,
        arm_stiffnesses=arm_stiffnesses,
        arm_dampings=arm_dampings,
        arm_max_efforts=arm_max_efforts,
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
