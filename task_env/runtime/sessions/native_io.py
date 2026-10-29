"""Core-owned RuntimeSession over a narrow public native-I/O boundary.

The adapter below owns no task lifecycle, control policy, typed projection or
recording. Provider implementations only describe resources and perform the
small set of reads/writes represented by :class:`NativeRuntimeIOV1`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Protocol

from ...artifacts import CanonicalStateView, ExecutionSpecV1, PoseWorld, TaskArtifactV1
from ...artifacts.execution import RealizedInitialState, ResetSample
from ...controllers.canonical.contracts import AppliedCanonicalControl
from .common import _SessionValues, pose
from .free_joint_state import PublicRigidBodyReadbackV1
from .source import UsdRuntimeSourceV1


def _finite_tuple(value, width: int, label: str) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != width:
        raise ValueError(f'{label} must contain exactly {width} values')
    if any(type(item) not in (int, float) or isinstance(item, bool)
           or not math.isfinite(float(item)) for item in value):
        raise ValueError(f'{label} must contain finite non-boolean numbers')
    return tuple(float(item) for item in value)


@dataclass(frozen=True)
class NativeRuntimeIOMetadataV1:
    """Immutable resource and execution facts read from a native adapter."""

    schema_version: str
    source_id: str
    source_closure_sha256: str
    scene_identity_sha256: str
    task_artifact_identity_sha256: str
    execution_identity_sha256: str
    physics_provider: str
    provider_build_identity: str
    backend: str
    device: str
    determinism_mode: str
    physics_dt_s: float
    control_substeps: int
    native_dof_names: tuple[str, ...]
    native_position_limits: Mapping[str, tuple[float, float]]

    def __post_init__(self):
        if self.schema_version != 'native-runtime-io-metadata-v1':
            raise ValueError('unsupported native Runtime I/O metadata schema')
        for name in ('source_id', 'physics_provider', 'provider_build_identity',
                     'backend', 'device', 'determinism_mode'):
            value = getattr(self, name)
            if type(value) is not str or not value or value.strip() != value:
                raise ValueError(f'native Runtime I/O metadata {name} must be a nonempty string')
        for name in ('source_closure_sha256', 'scene_identity_sha256',
                     'task_artifact_identity_sha256', 'execution_identity_sha256'):
            value = getattr(self, name)
            if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError(f'native Runtime I/O metadata {name} must be lowercase SHA-256')
        if (type(self.physics_dt_s) not in (int, float) or isinstance(self.physics_dt_s, bool)
                or not math.isfinite(float(self.physics_dt_s)) or float(self.physics_dt_s) <= 0):
            raise ValueError('native Runtime I/O physics dt must be finite and positive')
        if type(self.control_substeps) is not int or self.control_substeps < 1:
            raise ValueError('native Runtime I/O control_substeps must be a positive integer')
        names = tuple(self.native_dof_names)
        if (not names or any(type(name) is not str or not name.strip() for name in names)
                or len(names) != len(set(names))):
            raise ValueError('native DOF metadata must contain unique named scalar DOFs')
        limits = dict(self.native_position_limits)
        if set(limits) != set(names):
            raise ValueError('native position limits must exactly cover named DOFs')
        normalized = {}
        for name, raw in limits.items():
            values = _finite_tuple(raw, 2, f'position limits for {name!r}')
            if values[0] >= values[1]:
                raise ValueError(f'position limits for {name!r} must be increasing')
            normalized[name] = values
        object.__setattr__(self, 'native_dof_names', names)
        object.__setattr__(self, 'native_position_limits', MappingProxyType(normalized))

    def validate_binding(self, artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                         source: UsdRuntimeSourceV1) -> None:
        source.validate()
        if (self.source_id, self.source_closure_sha256, self.scene_identity_sha256,
                self.task_artifact_identity_sha256, self.execution_identity_sha256,
                self.physics_provider, self.backend, self.device, self.determinism_mode,
                self.physics_dt_s, self.control_substeps) != (
                source.source_id, source.source_closure_digest,
                source.scene_definition.identity_hash, artifact.identity_hash,
                execution.identity_hash, execution.physics_provider,
                execution.physics_backend, execution.physics_device,
                execution.determinism_mode, artifact.timebase.physics_dt,
                artifact.timebase.control_substeps):
            raise ValueError('native Runtime I/O metadata differs from source/artifact/execution identity')

    def to_mapping(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'source_id': self.source_id,
            'source_closure_sha256': self.source_closure_sha256,
            'scene_identity_sha256': self.scene_identity_sha256,
            'task_artifact_identity_sha256': self.task_artifact_identity_sha256,
            'execution_identity_sha256': self.execution_identity_sha256,
            'physics_provider': self.physics_provider,
            'provider_build_identity': self.provider_build_identity,
            'backend': self.backend, 'device': self.device,
            'determinism_mode': self.determinism_mode,
            'physics_dt_s': float(self.physics_dt_s),
            'control_substeps': self.control_substeps,
            'native_dof_names': list(self.native_dof_names),
            'native_position_limits': {key: list(value) for key, value in self.native_position_limits.items()},
        }


@dataclass(frozen=True)
class NativeRuntimeReadbackV1:
    """One non-advancing, owned read of named Core state and body frames."""

    schema_version: str
    joint_position: Mapping[str, float]
    joint_velocity: Mapping[str, float]
    frame_pose_world: Mapping[str, PoseWorld]
    free_joint_readback: Mapping[str, PublicRigidBodyReadbackV1]
    simulation_time_s: float

    def __post_init__(self):
        if self.schema_version != 'native-runtime-readback-v1':
            raise ValueError('unsupported native Runtime readback schema')
        for field in ('joint_position', 'joint_velocity'):
            values = dict(getattr(self, field))
            for name, value in values.items():
                if type(name) is not str or not name.strip():
                    raise TypeError(f'{field} names must be nonempty strings')
                if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(float(value)):
                    raise ValueError(f'{field} values must be finite non-boolean numbers')
            object.__setattr__(self, field, MappingProxyType({k: float(v) for k, v in values.items()}))
        frames = dict(self.frame_pose_world)
        if any(type(name) is not str or not isinstance(value, PoseWorld)
               for name, value in frames.items()):
            raise TypeError('native frame poses must map semantic names to PoseWorld values')
        object.__setattr__(self, 'frame_pose_world', MappingProxyType(frames))
        free = dict(self.free_joint_readback)
        if any(type(name) is not str or type(value) is not PublicRigidBodyReadbackV1
               for name, value in free.items()):
            raise TypeError('native free-body readback must map names to PublicRigidBodyReadbackV1')
        for value in free.values():
            value.validate()
        object.__setattr__(self, 'free_joint_readback', MappingProxyType(free))
        if (type(self.simulation_time_s) not in (int, float) or isinstance(self.simulation_time_s, bool)
                or not math.isfinite(float(self.simulation_time_s)) or self.simulation_time_s < 0):
            raise ValueError('native simulation time must be finite and nonnegative')
        object.__setattr__(self, 'simulation_time_s', float(self.simulation_time_s))


@dataclass(frozen=True)
class NativeResetWriteReceiptV1:
    schema_version: str
    reset_sample_id: str
    written_joint_names: tuple[str, ...]
    written_free_joint_names: tuple[str, ...]
    reset_target_names: tuple[str, ...]
    velocities_zeroed: bool
    partial: bool = False

    def to_mapping(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'reset_sample_id': self.reset_sample_id,
            'written_joint_names': list(self.written_joint_names),
            'written_free_joint_names': list(self.written_free_joint_names),
            'reset_target_names': list(self.reset_target_names),
            'velocities_zeroed': self.velocities_zeroed,
            'partial': self.partial,
        }

    def validate(self, sample: ResetSample, source: UsdRuntimeSourceV1, target_names: tuple[str, ...]):
        if self.schema_version != 'native-reset-write-receipt-v1':
            raise ValueError('unsupported native reset write receipt schema')
        if self.partial or not self.velocities_zeroed:
            raise ValueError('native reset writes must be complete and zero inherited velocities')
        if (self.reset_sample_id, set(self.written_joint_names), set(self.written_free_joint_names),
                tuple(self.reset_target_names)) != (
                sample.sample_id, set(source.joints), set(source.free_joints), tuple(target_names)):
            raise ValueError('native reset receipt does not cover exact source joints, free roots and targets')


@dataclass(frozen=True)
class NativePositionWriteAckV1:
    schema_version: str
    target_identity_sha256: str
    native_names: tuple[str, ...]
    applied_values: tuple[float, ...]
    partial: bool = False
    attempted_count: int | None = None

    def to_mapping(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'target_identity_sha256': self.target_identity_sha256,
            'native_names': list(self.native_names),
            'applied_values': list(self.applied_values),
            'partial': self.partial,
            'attempted_count': self.attempted_count,
        }

    def validate(self, target_identity: str, expected: tuple[tuple[int, str, float], ...]):
        if self.schema_version != 'native-position-write-ack-v1':
            raise ValueError('unsupported native Position write Ack schema')
        if (type(self.target_identity_sha256) is not str
                or len(self.target_identity_sha256) != 64
                or any(char not in '0123456789abcdef' for char in self.target_identity_sha256)
                or type(self.native_names) is not tuple
                or any(type(name) is not str or not name.strip() for name in self.native_names)
                or type(self.applied_values) is not tuple
                or any(type(value) not in (int, float) or isinstance(value, bool)
                       or not math.isfinite(float(value)) for value in self.applied_values)
                or type(self.partial) is not bool):
            raise TypeError('native Position write Ack must use exact typed finite named values')
        if self.partial:
            raise ValueError('native Position write Ack reports partial apply')
        names = tuple(name for _index, name, _value in expected)
        values = tuple(float(value) for _index, _name, value in expected)
        if (self.target_identity_sha256, tuple(self.native_names), tuple(self.applied_values)) != (
                target_identity, names, values):
            raise ValueError('native Position write Ack differs from the exact named Target')
        if self.attempted_count is not None and self.attempted_count != len(expected):
            raise ValueError('native Position write Ack attempt count differs from complete Target')


@dataclass(frozen=True)
class NativeAdvanceReceiptV1:
    schema_version: str
    completed_count: int
    native_step_index: int
    simulation_time_s: float

    def to_mapping(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'completed_count': self.completed_count,
            'native_step_index': self.native_step_index,
            'simulation_time_s': float(self.simulation_time_s),
        }

    def validate(self, expected_index: int, expected_time: float):
        if (self.schema_version != 'native-advance-receipt-v1'
                or type(self.completed_count) is not int or self.completed_count != 1
                or type(self.native_step_index) is not int or self.native_step_index != expected_index
                or type(self.simulation_time_s) not in (int, float)
                or isinstance(self.simulation_time_s, bool)
                or not math.isfinite(float(self.simulation_time_s))
                or abs(float(self.simulation_time_s) - expected_time) > 1e-12):
            raise ValueError('native advance must acknowledge exactly one expected timed step')


class NativeRuntimeIOV1(Protocol):
    """Only the native resource boundary; it does not own Core lifecycle."""

    def metadata(self) -> NativeRuntimeIOMetadataV1: ...
    def write_reset(self, sample: ResetSample, position_targets: tuple[tuple[int, str, float], ...]) -> NativeResetWriteReceiptV1: ...
    def read_state(self) -> NativeRuntimeReadbackV1: ...
    def write_position_targets(self, target_identity_sha256: str,
                               targets: tuple[tuple[int, str, float], ...]) -> NativePositionWriteAckV1: ...
    def advance(self) -> NativeAdvanceReceiptV1: ...
    def close(self) -> None: ...


class F03CoreRuntimeSession(_SessionValues):
    """The ordinary Core session lifecycle backed only by a native-I/O port."""

    def __init__(self, artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                 source: UsdRuntimeSourceV1, native_io: NativeRuntimeIOV1,
                 drive_receipt):
        if type(artifact) is not TaskArtifactV1 or type(execution) is not ExecutionSpecV1:
            raise TypeError('F03 Core RuntimeSession requires TaskArtifactV1 and ExecutionSpecV1')
        if type(source) is not UsdRuntimeSourceV1:
            raise TypeError('F03 Core RuntimeSession requires the exact UsdRuntimeSourceV1')
        from .leaf_control import IsaacNamedPositionDriveReceiptV1
        if type(drive_receipt) is not IsaacNamedPositionDriveReceiptV1:
            raise TypeError('F03 Core RuntimeSession requires the existing named-drive receipt owner')
        self._initialize_values(artifact, source, execution.physics_provider)
        self._execution_spec_v1 = execution
        self._native_io = native_io
        self._native_io_metadata = native_io.metadata()
        if type(self._native_io_metadata) is not NativeRuntimeIOMetadataV1:
            raise TypeError('native Runtime I/O metadata() must return NativeRuntimeIOMetadataV1')
        self._native_io_metadata.validate_binding(artifact, execution, source)
        if (self._native_io_metadata.provider_build_identity != drive_receipt.provider_build_identity
                or self._native_io_metadata.native_dof_names != tuple(
                    item.native_dof_name for item in sorted(drive_receipt.drives, key=lambda item: item.native_dof_index)
                )):
            raise ValueError('native I/O DOF/build metadata differs from the admitted named-drive receipt')
        if dict(self._native_io_metadata.native_position_limits) != {
                item.native_dof_name: (float(item.lower_limit), float(item.upper_limit))
                for item in drive_receipt.drives}:
            raise ValueError('native I/O named DOF limits differ from the named-drive receipt')
        self._drive_receipt = drive_receipt
        self._target_actuators = {
            f'{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}': item.native_dof_name
            for item in drive_receipt.drives if item.canonical_joint.joint_id.startswith('joint')
        }
        self._open_actuators = ()
        self._native_step_count = 0
        self._reset_write_receipt: NativeResetWriteReceiptV1 | None = None
        self._last_native_position_ack: NativePositionWriteAckV1 | None = None
        self._last_interval_advances: tuple[dict[str, object], ...] = ()
        self._last_interval_advance_attempts = 0
        self._last_readback: NativeRuntimeReadbackV1 | None = None
        self._position_applied_boundary_ids = set()

    def _assert_native_identity(self):
        self._source.assert_fresh()
        current = self._native_io.metadata()
        if current != self._native_io_metadata:
            raise ValueError('native Runtime I/O metadata changed after materialization')
        current.validate_binding(self._artifact, self._execution_spec_v1, self._source)

    def reset(self, sample: ResetSample) -> RealizedInitialState:
        self._begin_reset()
        self._validate_sample(sample)
        self._assert_native_identity()
        arm = {f'panda-main/joint{index}': sample.joint_position[f'panda-main/joint{index}']
               for index in range(1, 8)}
        opening = sum(sample.joint_position[f'panda-main/finger_joint{index}'] for index in (1, 2))
        targets = self._drive_receipt.commands(arm, opening)
        receipt = self._native_io.write_reset(sample, targets)
        # Keep the returned fact even when its contract is invalid. A provider
        # may have written some channels before reporting a partial/malformed
        # receipt; Core must not erase that evidence while closing the reset
        # gate.
        self._reset_write_receipt = receipt if type(receipt) is NativeResetWriteReceiptV1 else None
        if type(receipt) is not NativeResetWriteReceiptV1:
            raise TypeError('native reset must return NativeResetWriteReceiptV1')
        target_names = tuple(name for _index, name, _value in targets)
        receipt.validate(sample, self._source, target_names)
        self._native_step_count = 0
        self._position_applied_boundary_ids.clear()
        self._last_native_position_ack = None
        self._last_interval_advances = ()
        self._last_interval_advance_attempts = 0
        return self._realized(sample)

    def _snapshot_with_native_free_joints(self):
        self._require_reset()
        self._assert_native_identity()
        readback = self._native_io.read_state()
        if type(readback) is not NativeRuntimeReadbackV1:
            raise TypeError('native read_state() must return NativeRuntimeReadbackV1')
        expected_joint_names = set(self._source.joints)
        expected_frame_names = set(self._source.bodies) | set(self._source.frames)
        if (set(readback.joint_position) != expected_joint_names
                or set(readback.joint_velocity) != expected_joint_names
                or set(readback.frame_pose_world) != expected_frame_names
                or set(readback.free_joint_readback) != set(self._source.free_joints)):
            raise ValueError('native state mapping names differ from exact USD RuntimeSource bindings')
        expected_time = self._control_step * self._artifact.timebase.control_dt
        if abs(readback.simulation_time_s - expected_time) > 1e-12:
            raise ValueError('native time readback differs from the Core evaluation-boundary clock')
        self._last_readback = readback
        state = self._state(
            dict(readback.joint_position), dict(readback.joint_velocity),
            dict(readback.frame_pose_world), readback.simulation_time_s,
        )
        return state, dict(readback.free_joint_readback)

    def snapshot(self) -> CanonicalStateView:
        return self._snapshot_with_native_free_joints()[0]

    def apply_control(self, target):
        from .control import validate_target
        validate_target(self, target)
        expected = self._drive_receipt.commands(target.arm_servo_position, target.gripper.servo_opening_m)
        acknowledgement = self._native_io.write_position_targets(target.identity_hash, expected)
        if type(acknowledgement) is not NativePositionWriteAckV1:
            raise TypeError('native Position write must return NativePositionWriteAckV1')
        self._last_native_position_ack = acknowledgement
        acknowledgement.validate(target.identity_hash, expected)
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        realized = {
            f'{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}': float(value)
            for item in self._drive_receipt.drives
            if item.canonical_joint.joint_id.startswith('joint')
            for name, value in zip(acknowledgement.native_names, acknowledgement.applied_values, strict=True)
            if name == item.native_dof_name
        }
        if set(realized) != set(target.arm_joint_order):
            raise ValueError('native Position Ack did not cover all seven named Arm Targets')
        return AppliedCanonicalControl(
            'applied-canonical-control-v0', target.identity_hash, 'synthetic_fixture',
            realized, float(target.gripper.servo_opening_m), float(target.gripper.force_limit_N),
            False, 'synthetic_named_dof_position_targets_no_physics',
        )

    def step(self) -> CanonicalStateView:
        self._require_reset()
        self._assert_native_identity()
        dt = float(self._artifact.timebase.physics_dt)
        self._last_interval_advances = ()
        self._last_interval_advance_attempts = 0
        accepted_advances = []
        for _ in range(self._artifact.timebase.control_substeps):
            expected_index = self._native_step_count + 1
            expected_time = expected_index * dt
            self._last_interval_advance_attempts += 1
            receipt = self._native_io.advance()
            if type(receipt) is not NativeAdvanceReceiptV1:
                raise TypeError('native advance() must return NativeAdvanceReceiptV1')
            accepted_advances.append(receipt.to_mapping())
            self._last_interval_advances = tuple(accepted_advances)
            receipt.validate(expected_index, expected_time)
            self._native_step_count = expected_index
        self._control_step += 1
        self._state_revision += 1
        return self.snapshot()

    def close(self) -> None:
        if not self._closed:
            try:
                self._native_io.close()
            finally:
                self._closed = True


__all__ = [
    'F03CoreRuntimeSession', 'NativeAdvanceReceiptV1', 'NativePositionWriteAckV1',
    'NativeResetWriteReceiptV1', 'NativeRuntimeIOV1', 'NativeRuntimeIOMetadataV1',
    'NativeRuntimeReadbackV1',
]
