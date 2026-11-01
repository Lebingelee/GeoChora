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

import numpy as np

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


def _native_public_float_readback_matches(
    actual: object, expected: float, *, abs_tol: float, rel_tol: float = 0.0,
) -> bool:
    """Compare public float-backed API readbacks at their declared precision."""
    if (type(actual) not in (int, float) or isinstance(actual, bool)
            or not math.isfinite(float(actual))):
        return False
    return math.isclose(float(actual), float(expected), rel_tol=rel_tol, abs_tol=abs_tol)


def _is_sha256_identity(value: object) -> bool:
    return (type(value) is str and len(value) == 64
            and all(char in '0123456789abcdef' for char in value))


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
    host_model_producer_identity_sha256: str | None = None

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
        if self.host_model_producer_identity_sha256 is not None:
            value = self.host_model_producer_identity_sha256
            if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('native Runtime I/O host-model producer identity must be lowercase SHA-256')
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
        result = {
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
        if self.host_model_producer_identity_sha256 is not None:
            result['host_model_producer_identity_sha256'] = self.host_model_producer_identity_sha256
        return result


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
        if (not _is_sha256_identity(self.target_identity_sha256)
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
        if (self.target_identity_sha256, tuple(self.native_names)) != (target_identity, names):
            raise ValueError('native Position write Ack differs from the exact named Target')
        for actual, requested in zip(self.applied_values, values, strict=True):
            quantization = max(1e-12, abs(float(np.spacing(np.float32(requested)))) * 1.5)
            if abs(float(actual) - requested) > quantization:
                raise ValueError('native Position write Ack differs beyond float32 control quantization')
        if self.attempted_count is not None and self.attempted_count != len(expected):
            raise ValueError('native Position write Ack attempt count differs from complete Target')


@dataclass(frozen=True)
class NativeSourceTendonWriteAckV1:
    """Acknowledgement that Core's source tendon target was installed in native I/O."""

    schema_version: str
    target_identity_sha256: str
    receipt_identity_sha256: str
    actuator_name: str
    control_value: float
    scalar_force_limit_N: float
    partial: bool = False

    def to_mapping(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'target_identity_sha256': self.target_identity_sha256,
            'receipt_identity_sha256': self.receipt_identity_sha256,
            'actuator_name': self.actuator_name,
            'control_value': float(self.control_value),
            'scalar_force_limit_N': float(self.scalar_force_limit_N),
            'partial': self.partial,
        }

    def validate(self, *, target_identity_sha256: str, receipt_identity_sha256: str,
                 actuator_name: str, control_value: float, scalar_force_limit_N: float) -> None:
        values = (self.control_value, self.scalar_force_limit_N)
        if (self.schema_version != 'native-source-tendon-write-ack-v1'
                or not _is_sha256_identity(self.target_identity_sha256)
                or not _is_sha256_identity(self.receipt_identity_sha256)
                or not _is_sha256_identity(target_identity_sha256)
                or not _is_sha256_identity(receipt_identity_sha256)
                or type(self.actuator_name) is not str or not self.actuator_name.strip()
                or type(actuator_name) is not str or not actuator_name.strip()
                or self.target_identity_sha256 != target_identity_sha256
                or self.receipt_identity_sha256 != receipt_identity_sha256
                or self.actuator_name != actuator_name
                or type(self.partial) is not bool or self.partial
                or any(type(value) not in (int, float) or isinstance(value, bool)
                       or not math.isfinite(float(value)) for value in values)
                or float(self.control_value) != float(control_value)
                or float(self.scalar_force_limit_N) != float(scalar_force_limit_N)):
            raise ValueError('native source tendon Ack differs from the exact Core target/receipt')


@dataclass(frozen=True)
class NativeAdvanceReceiptV1:
    schema_version: str
    completed_count: int
    native_step_index: int
    simulation_time_s: float
    source_tendon_application: Mapping[str, object] | None = None
    native_adaptation_application: Mapping[str, object] | None = None

    def to_mapping(self) -> dict[str, object]:
        result = {
            'schema_version': self.schema_version,
            'completed_count': self.completed_count,
            'native_step_index': self.native_step_index,
            'simulation_time_s': float(self.simulation_time_s),
        }
        if self.source_tendon_application is not None:
            result['source_tendon_application'] = dict(self.source_tendon_application)
        if self.native_adaptation_application is not None:
            result['native_adaptation_application'] = dict(self.native_adaptation_application)
        return result

    def validate(self, expected_index: int, expected_time: float):
        if (self.schema_version != 'native-advance-receipt-v1'
                or type(self.completed_count) is not int or self.completed_count != 1
                or type(self.native_step_index) is not int or self.native_step_index != expected_index
                or type(self.simulation_time_s) not in (int, float)
                or isinstance(self.simulation_time_s, bool)
                or not math.isfinite(float(self.simulation_time_s))
                or abs(float(self.simulation_time_s) - expected_time) > 1e-12):
            raise ValueError('native advance must acknowledge exactly one expected timed step')
        if self.source_tendon_application is not None:
            application = self.source_tendon_application
            if (not isinstance(application, Mapping)
                    or application.get('schema_version') != 'native-source-tendon-substep-v1'
                    or application.get('native_step_index') != expected_index
                    or any(type(application.get(key)) not in (int, float)
                           or isinstance(application.get(key), bool)
                           or not math.isfinite(float(application[key]))
                           for key in ('tendon_length_m', 'tendon_rate_m_s',
                                       'unclipped_scalar_force_N', 'scalar_force_N'))
                    or type(application.get('dof_efforts_N')) is not tuple
                    or len(application['dof_efforts_N']) != 2
                    or any(type(value) not in (int, float) or isinstance(value, bool)
                           or not math.isfinite(float(value))
                           for value in application['dof_efforts_N'])):
                raise ValueError('native source tendon substep receipt is incomplete or malformed')
        if self.source_tendon_application is not None and self.native_adaptation_application is not None:
            raise ValueError('native advance cannot claim two different gripper adaptation receipts')
        if self.native_adaptation_application is not None:
            application = self.native_adaptation_application
            numeric_fields = (
                'reference_position_m', 'follower_position_m',
                'reference_velocity_m_s', 'follower_velocity_m_s',
                'relation_error_m', 'reference_target_m',
                'reference_effort_N', 'maximum_effort_N',
            )
            if (not isinstance(application, Mapping)
                    or application.get('schema_version') != 'native-physx-mimic-substep-application-v1'
                    or application.get('native_step_index') != expected_index
                    or application.get('profile_id') != 'isaacsim-6.2-physx-native-mimic-leader-drive-v1'
                    or application.get('provenance_kind') not in {'synthetic_fixture', 'native_runtime'}
                    or application.get('reference_joint') != 'finger_joint1'
                    or application.get('follower_joint') != 'finger_joint2'
                    or application.get('public_effort_api') != (
                        'Articulation.get_dof_projected_joint_forces'
                        if application.get('provenance_kind') == 'native_runtime'
                        else 'synthetic-no-physics'
                    )
                    or application.get('effort_measurement_semantics') != (
                        'projected_active_joint_force'
                        if application.get('provenance_kind') == 'native_runtime'
                        else 'synthetic-no-physics'
                    )
                    or application.get('native_mimic_api') != 'PhysxMimicJointAPI:transX'
                    or application.get('native_drive_api') != 'PhysicsDriveAPI:linear'
                    or not _is_sha256_identity(application.get('drive_receipt_identity_sha256'))
                    or not _is_sha256_identity(application.get('target_identity_sha256'))
                    or any(type(application.get(key)) not in (int, float)
                           or isinstance(application.get(key), bool)
                           or not math.isfinite(float(application[key]))
                           for key in numeric_fields)
                    or not isinstance(application.get('public_contact_witness'), Mapping)
                    or application['public_contact_witness'].get('schema_version')
                       != 'f05-dg04-native-contact-witness-v1'
                    or application['public_contact_witness'].get('provenance_kind')
                       != application.get('provenance_kind')
                    or type(application['public_contact_witness'].get('contact_present')) is not bool):
                raise ValueError('native PhysX mimic substep receipt is incomplete or malformed')
            if (abs(float(application['relation_error_m'])) > 0.002
                    or float(application['maximum_effort_N']) != 100.0
                    or abs(float(application['reference_effort_N'])) > 100.0 + 1e-6):
                raise ValueError('native PhysX mimic relation or declared effort cap failed')
            witness = application['public_contact_witness']
            raw_count = witness.get('raw_contact_count')
            raw_paths = witness.get('raw_contact_actor_paths')
            raw_forces = witness.get('raw_contact_normal_forces_N')
            raw_signed_forces = witness.get('raw_contact_signed_normal_force_scalars_N')
            raw_normals = witness.get('raw_contact_normals_world')
            raw_separations = witness.get('raw_contact_separations_m')
            if application.get('provenance_kind') == 'native_runtime' and (
                    type(raw_count) is not int or raw_count < 0 or raw_count > 32
                    or type(raw_paths) is not list or len(raw_paths) != raw_count
                    or type(raw_forces) is not list or len(raw_forces) != raw_count
                    or type(raw_signed_forces) is not list or len(raw_signed_forces) != raw_count
                    or type(raw_normals) is not list or len(raw_normals) != raw_count
                    or type(raw_separations) is not list or len(raw_separations) != raw_count
                    or any(type(path) is not str or not path.startswith('/') for path in raw_paths)
                    or any(type(value) not in (int, float) or isinstance(value, bool)
                           or not math.isfinite(float(value)) or float(value) < 0.0
                           for value in raw_forces)):
                raise ValueError('native PhysX mimic receipt lacks aligned raw actor/contact evidence')
            if application.get('provenance_kind') == 'native_runtime' and (
                    witness.get('force_magnitude_mapping')
                    != 'abs(raw_signed_normal_force_scalar_N)'
                    or any(type(value) not in (int, float) or isinstance(value, bool)
                           or not math.isfinite(float(value))
                           for value in raw_signed_forces)
                    or any(not math.isclose(float(magnitude), abs(float(value)),
                                            rel_tol=0.0, abs_tol=1e-7)
                           for magnitude, value in zip(raw_forces, raw_signed_forces, strict=True))
                    or any(type(row) is not list or len(row) != 3
                           or any(type(value) not in (int, float) or isinstance(value, bool)
                                  or not math.isfinite(float(value)) for value in row)
                           for row in raw_normals)
                    or any(type(value) not in (int, float) or isinstance(value, bool)
                           or not math.isfinite(float(value)) for value in raw_separations)):
                raise ValueError('native PhysX mimic receipt has malformed signed-force/magnitude contact mapping')
            if application.get('provenance_kind') == 'synthetic_fixture' and (
                    witness.get('raw_contact_count') != 0
                    or witness.get('raw_contact_actor_paths') != []
                    or witness.get('raw_contact_normal_forces_N') != []
                    or witness.get('raw_contact_signed_normal_force_scalars_N') != []
                    or witness.get('raw_contact_normals_world') != []
                    or witness.get('raw_contact_separations_m') != []
                    or witness.get('force_magnitude_mapping') != 'synthetic-no-physics'):
                raise ValueError('synthetic PhysX mimic fixture cannot claim raw physical contact evidence')


class NativeRuntimeIOV1(Protocol):
    """Only the native resource boundary; it does not own Core lifecycle."""

    def metadata(self) -> NativeRuntimeIOMetadataV1: ...
    def write_reset(self, sample: ResetSample, position_targets: tuple[tuple[int, str, float], ...]) -> NativeResetWriteReceiptV1: ...
    def read_state(self) -> NativeRuntimeReadbackV1: ...
    def write_position_targets(self, target_identity_sha256: str,
                               targets: tuple[tuple[int, str, float], ...]) -> NativePositionWriteAckV1: ...
    def advance(self) -> NativeAdvanceReceiptV1: ...
    def close(self) -> None: ...


class NativeSourceTendonRuntimeIOV1(Protocol):
    """DG03-only extension for writing a source tendon actuator target."""

    def write_source_tendon_target(
        self, target_identity_sha256: str, receipt_identity_sha256: str,
        actuator_name: str, control_value: float, scalar_force_limit_N: float,
    ) -> NativeSourceTendonWriteAckV1: ...


class UsdCoreRuntimeSession(_SessionValues):
    """Shared Core session lifecycle backed only by the native-I/O port."""

    def __init__(self, artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                 source: UsdRuntimeSourceV1, native_io: NativeRuntimeIOV1,
                 drive_receipt=None):
        if type(artifact) is not TaskArtifactV1 or type(execution) is not ExecutionSpecV1:
            raise TypeError('F03 Core RuntimeSession requires TaskArtifactV1 and ExecutionSpecV1')
        if type(source) is not UsdRuntimeSourceV1:
            raise TypeError('F03 Core RuntimeSession requires the exact UsdRuntimeSourceV1')
        from .leaf_control import (
            GeoPhysUsdPositionDriveReceiptV1,
            GeoPhysUsdSourceActuationReceiptV2,
            IsaacNamedPositionDriveReceiptV1,
            IsaacNativeMimicPositionDriveReceiptV1,
            IsaacSourceTendonDriveReceiptV1,
            compile_isaac_named_position_drive_receipt_from_native_metadata_v1,
        )
        self._initialize_values(artifact, source, execution.physics_provider)
        self._execution_spec_v1 = execution
        self._native_io = native_io
        self._native_io_metadata = native_io.metadata()
        if type(self._native_io_metadata) is not NativeRuntimeIOMetadataV1:
            raise TypeError('native Runtime I/O metadata() must return NativeRuntimeIOMetadataV1')
        self._native_io_metadata.validate_binding(artifact, execution, source)
        # The low-level I/O owner, rather than source validation, determines
        # whether this execution crossed a real provider boundary. This lets
        # provider-free S1 replace only native I/O and keep its Recorder
        # evidence explicitly synthetic. Older F03 ports do not declare the
        # marker and retain their source-derived behavior.
        execution_provenance = getattr(native_io, 'execution_provenance_kind', None)
        if execution_provenance is None:
            execution_provenance = (
                'native_runtime'
                if source.scene_source.source_verified or source.scene_source.locally_validated
                else 'synthetic_fixture'
            )
        if execution_provenance not in {'native_runtime', 'synthetic_fixture'}:
            raise ValueError('native I/O owner reported an unsupported execution provenance')
        if drive_receipt is None:
            if execution.physics_provider != 'isaacsim':
                raise ValueError('only the exact admitted Isaac route can defer named-drive receipt compilation')
            drive_receipt = compile_isaac_named_position_drive_receipt_from_native_metadata_v1(
                execution=execution, source=source,
                scene_identity_sha256=source.scene_definition.identity_hash,
                native_metadata=self._native_io_metadata,
                writer_id='panda-main/position-servo-v1',
            )
            if execution_provenance == 'synthetic_fixture':
                from dataclasses import replace
                drive_receipt = replace(drive_receipt, provenance_kind='synthetic_fixture')
        if type(drive_receipt) not in (
                IsaacNamedPositionDriveReceiptV1,
                IsaacNativeMimicPositionDriveReceiptV1,
                IsaacSourceTendonDriveReceiptV1,
                GeoPhysUsdPositionDriveReceiptV1,
                GeoPhysUsdSourceActuationReceiptV2):
            raise TypeError('Core RuntimeSession requires a supported named-drive receipt owner')
        if ((type(drive_receipt) in (IsaacNamedPositionDriveReceiptV1,
                                     IsaacNativeMimicPositionDriveReceiptV1,
                                     IsaacSourceTendonDriveReceiptV1)
             and execution.physics_provider != 'isaacsim')
                or (type(drive_receipt) in (GeoPhysUsdPositionDriveReceiptV1, GeoPhysUsdSourceActuationReceiptV2)
                    and execution.physics_provider != 'geophys')):
            raise ValueError('named-drive receipt provider differs from the declared ExecutionSpec')
        if drive_receipt.provenance_kind != execution_provenance:
            raise ValueError('named-drive receipt provenance does not match the loaded USD source')
        receipt_native_names = (
            drive_receipt.native_dof_names
            if type(drive_receipt) in (IsaacSourceTendonDriveReceiptV1,
                                       IsaacNativeMimicPositionDriveReceiptV1)
            else tuple(item.native_dof_name for item in sorted(
                drive_receipt.drives, key=lambda item: item.native_dof_index,
            ))
        )
        if (self._native_io_metadata.provider_build_identity != drive_receipt.provider_build_identity
                or self._native_io_metadata.native_dof_names != tuple(receipt_native_names)):
            raise ValueError('native I/O DOF/build metadata differs from the admitted named-drive receipt')
        receipt_limits = (
            dict(drive_receipt.native_position_limits)
            if type(drive_receipt) in (IsaacSourceTendonDriveReceiptV1,
                                       IsaacNativeMimicPositionDriveReceiptV1)
            else {item.native_dof_name: (float(item.lower_limit), float(item.upper_limit))
                  for item in drive_receipt.drives}
        )
        if dict(self._native_io_metadata.native_position_limits) != receipt_limits:
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
        self._last_native_source_tendon_ack: NativeSourceTendonWriteAckV1 | None = None
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
        if type(self._drive_receipt).__name__ == 'IsaacSourceTendonDriveReceiptV1':
            targets = self._drive_receipt.arm_commands(arm)
        else:
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
        self._last_native_source_tendon_ack = None
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

    def read_contact_observation(self) -> dict[str, object]:
        """Read the provider's last DG02 diagnostic contact sample without advancing time."""
        self._assert_native_identity()
        reader = getattr(self._native_io, 'read_contact_observation', None)
        if not callable(reader):
            raise RuntimeError('the admitted native Runtime I/O does not expose contact observations')
        observation = reader()
        if (not isinstance(observation, Mapping)
                or observation.get('schema_version') != 'f05-dg02-public-contact-observation-v1'
                or type(observation.get('known')) is not bool):
            raise TypeError('native contact observation must use the exact DG02 public schema')
        return dict(observation)

    def apply_control(self, target):
        from .control import validate_target
        validate_target(self, target)
        from .leaf_control import IsaacSourceTendonDriveReceiptV1
        if type(self._drive_receipt) is IsaacSourceTendonDriveReceiptV1:
            expected = self._drive_receipt.arm_commands(target.arm_servo_position)
        else:
            if (type(self._drive_receipt).__name__ == 'IsaacNativeMimicPositionDriveReceiptV1'
                    and not math.isclose(
                        float(target.gripper.force_limit_N),
                        float(self._drive_receipt.gripper_force_limit_N),
                        rel_tol=0.0, abs_tol=1e-9)):
                raise ValueError('DG04 canonical gripper force limit differs from the fixed native drive cap')
            expected = self._drive_receipt.commands(target.arm_servo_position, target.gripper.servo_opening_m)
        acknowledgement = self._native_io.write_position_targets(target.identity_hash, expected)
        if type(acknowledgement) is not NativePositionWriteAckV1:
            raise TypeError('native Position write must return NativePositionWriteAckV1')
        self._last_native_position_ack = acknowledgement
        acknowledgement.validate(target.identity_hash, expected)
        if type(self._drive_receipt) is IsaacSourceTendonDriveReceiptV1:
            writer = getattr(self._native_io, 'write_source_tendon_target', None)
            if not callable(writer):
                raise TypeError('DG03 native I/O lacks the source tendon target operation')
            ctrl, scalar_force_limit = self._drive_receipt.tendon_control(
                target.gripper.servo_opening_m, target.gripper.force_limit_N,
            )
            tendon_ack = writer(
                target.identity_hash, self._drive_receipt.identity_sha256,
                self._drive_receipt.actuator_name, ctrl, scalar_force_limit,
            )
            if type(tendon_ack) is not NativeSourceTendonWriteAckV1:
                raise TypeError('DG03 tendon target write must return NativeSourceTendonWriteAckV1')
            tendon_ack.validate(
                target_identity_sha256=target.identity_hash,
                receipt_identity_sha256=self._drive_receipt.identity_sha256,
                actuator_name=self._drive_receipt.actuator_name,
                control_value=ctrl, scalar_force_limit_N=scalar_force_limit,
            )
            self._last_native_source_tendon_ack = tendon_ack
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
            'applied-canonical-control-v0', target.identity_hash,
            'native_runtime' if self._drive_receipt.provenance_kind == 'native_runtime' else 'synthetic_fixture',
            realized, float(target.gripper.servo_opening_m), float(target.gripper.force_limit_N),
            False,
            ('native_source_tendon_and_arm_targets_acknowledged; per_substep_tendon_effort_required'
             if type(self._drive_receipt) is IsaacSourceTendonDriveReceiptV1
             and self._drive_receipt.provenance_kind == 'native_runtime'
             else 'synthetic_source_tendon_and_arm_targets_no_physics'
             if type(self._drive_receipt) is IsaacSourceTendonDriveReceiptV1
             else 'native_physx_mimic_leader_drive_and_arm_targets_acknowledged_no_motion_claim'
             if type(self._drive_receipt).__name__ == 'IsaacNativeMimicPositionDriveReceiptV1'
             and self._drive_receipt.provenance_kind == 'native_runtime'
             else 'synthetic_physx_mimic_leader_drive_targets_no_physics'
             if type(self._drive_receipt).__name__ == 'IsaacNativeMimicPositionDriveReceiptV1'
             else 'native_named_dof_position_target_acknowledged_no_motion_claim'
             if self._drive_receipt.provenance_kind == 'native_runtime'
             else 'synthetic_named_dof_position_targets_no_physics'),
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
            from .leaf_control import IsaacSourceTendonDriveReceiptV1
            from .leaf_control import IsaacNativeMimicPositionDriveReceiptV1
            if type(self._drive_receipt) is IsaacSourceTendonDriveReceiptV1:
                application = receipt.source_tendon_application
                ack = self._last_native_source_tendon_ack
                if (application is None or ack is None
                        or application.get('target_identity_sha256') != ack.target_identity_sha256
                        or application.get('receipt_identity_sha256') != ack.receipt_identity_sha256
                        or application.get('actuator_name') != ack.actuator_name
                        or application.get('control_value') != ack.control_value
                        or application.get('scalar_force_limit_N') != ack.scalar_force_limit_N
                        or application.get('tendon_coefficients') != self._drive_receipt.tendon_coefficients):
                    raise ValueError('DG03 accepted substep is not bound to its target/source tendon effort receipt')
                self._validate_source_tendon_application(application, ack, expected_index)
            elif type(self._drive_receipt) is IsaacNativeMimicPositionDriveReceiptV1:
                application = receipt.native_adaptation_application
                ack = self._last_native_position_ack
                if (application is None or ack is None
                        or application.get('drive_receipt_identity_sha256') != self._drive_receipt.identity_sha256
                        or application.get('provenance_kind') != self._drive_receipt.provenance_kind
                        or application.get('target_identity_sha256') != ack.target_identity_sha256
                        or application.get('native_step_index') != expected_index):
                    raise ValueError('DG04 accepted substep is not bound to its current target and native drive receipt')
                try:
                    target_index = ack.native_names.index('finger_joint1')
                except ValueError as error:
                    raise ValueError('DG04 position Ack omits its active leader finger target') from error
                if not math.isclose(
                        float(application['reference_target_m']),
                        float(ack.applied_values[target_index]), rel_tol=0.0, abs_tol=1e-6):
                    raise ValueError('DG04 physical substep receipt differs from the acknowledged leader target')
            self._native_step_count = expected_index
        self._control_step += 1
        self._state_revision += 1
        return self.snapshot()

    def _validate_source_tendon_application(self, application, ack, expected_index):
        """Recompute the exact DG03 affine tendon law from each public readback row."""
        from .leaf_control import IsaacSourceEqualityComplianceV1, IsaacSourceTendonDriveReceiptV1

        receipt = self._drive_receipt
        if type(receipt) is not IsaacSourceTendonDriveReceiptV1:
            raise TypeError('DG03 source tendon validation requires its exact typed receipt')
        positions = _finite_tuple(application.get('finger_positions_m'), 2,
                                  'DG03 native tendon finger positions')
        velocities = _finite_tuple(application.get('finger_velocities_m_s'), 2,
                                   'DG03 native tendon finger velocities')
        efforts = _finite_tuple(application.get('dof_efforts_N'), 2,
                                'DG03 native tendon DOF efforts')
        indices = application.get('native_finger_dof_indices')
        names = application.get('native_finger_joint_names')
        if (type(application.get('native_step_index')) is not int
                or application['native_step_index'] != expected_index
                or names != receipt.tendon_native_joint_names
                or type(indices) is not tuple
                or indices != tuple(self._native_io_metadata.native_dof_names.index(name)
                                    for name in receipt.tendon_native_joint_names)
                or application.get('tendon_coefficients') != receipt.tendon_coefficients
                or type(application.get('effort_write_attempted_count')) is not int
                or application['effort_write_attempted_count'] != 2
                or type(application.get('effort_write_completed_count')) is not int
                or application['effort_write_completed_count'] != 2):
            raise ValueError('DG03 substep did not write both exact source tendon DOFs in source order')
        expected_length = sum(a * b for a, b in zip(receipt.tendon_coefficients, positions, strict=True))
        expected_rate = sum(a * b for a, b in zip(receipt.tendon_coefficients, velocities, strict=True))
        expected_raw = (
            receipt.actuator_gain * ack.control_value
            + receipt.actuator_length_bias * expected_length
            + receipt.actuator_rate_bias * expected_rate
        )
        force_low, force_high = receipt.actuator_force_range
        scalar_limit = min(float(ack.scalar_force_limit_N), force_high)
        expected_force = min(
            scalar_limit,
            max(-scalar_limit, min(force_high, max(force_low, expected_raw))),
        )
        expected_efforts = tuple(
            coefficient * expected_force for coefficient in receipt.tendon_coefficients
        )
        applied_efforts = _finite_tuple(
            application.get('public_applied_efforts_N'), 2,
            'DG03 public applied tendon effort readback',
        )
        equality_residual = positions[1] - positions[0]
        compliance = receipt.equality_compliance
        if type(compliance) is not IsaacSourceEqualityComplianceV1:
            raise TypeError('DG03 receipt lacks the exact source-bound equality compliance mapping')
        if compliance.mapping_algorithm != 'mujoco-3.8.1-solimp-reference-to-physx-mimic-v4-homogeneous':
            raise ValueError('DG03 typed tendon application requires the corrected v4 homogeneous source mapping')
        expected_impedance = compliance.impedance(equality_residual)
        expected_frequency = compliance.natural_frequency_hz(equality_residual)
        expected_damping_ratio = compliance.damping_ratio_for_residual(equality_residual)
        def agrees(actual, expected):
            return _native_public_float_readback_matches(
                actual, expected, rel_tol=1e-10, abs_tol=1e-10,
            )

        source_checks = {
            'tendon_length_m': (application.get('tendon_length_m'), expected_length),
            'tendon_rate_m_s': (application.get('tendon_rate_m_s'), expected_rate),
            'unclipped_scalar_force_N': (application.get('unclipped_scalar_force_N'), expected_raw),
            'scalar_force_N': (application.get('scalar_force_N'), expected_force),
            'source_equality_residual_m': (
                application.get('source_equality_residual_m'), equality_residual,
            ),
            'source_equality_impedance': (
                application.get('source_equality_impedance'), expected_impedance,
            ),
            'source_mimic_natural_frequency_hz': (
                application.get('source_mimic_natural_frequency_hz'), expected_frequency,
            ),
            'source_mimic_damping_ratio': (
                application.get('source_mimic_damping_ratio'), expected_damping_ratio,
            ),
        }
        mismatches = {
            name: {'actual': actual, 'expected': expected}
            for name, (actual, expected) in source_checks.items()
            if not agrees(actual, expected)
        }
        for index, (actual, expected) in enumerate(zip(efforts, expected_efforts, strict=True)):
            if not agrees(actual, expected):
                mismatches[f'dof_efforts_N[{index}]'] = {'actual': actual, 'expected': expected}
        for index, (actual, expected) in enumerate(zip(applied_efforts, expected_efforts, strict=True)):
            # Articulation tensor readback is float-backed; match the producer's public
            # getter tolerance while keeping source-side J^T arithmetic at 1e-10.
            if not _native_public_float_readback_matches(
                actual, expected, rel_tol=1e-7, abs_tol=1e-7,
            ):
                mismatches[f'public_applied_efforts_N[{index}]'] = {
                    'actual': actual, 'expected': expected,
                }
        for name, actual, expected in (
            ('public_mimic_frequency_readback_hz',
             application.get('public_mimic_frequency_readback_hz'), expected_frequency),
            ('public_mimic_damping_ratio_readback',
             application.get('public_mimic_damping_ratio_readback'), expected_damping_ratio),
        ):
            # PhysX mimic attrs are USD `custom float` values, whose public readback
            # uses float32 precision. Match the native writer's existing 1e-6 check.
            if not _native_public_float_readback_matches(
                actual, expected, rel_tol=0.0, abs_tol=1e-6,
            ):
                mismatches[name] = {'actual': actual, 'expected': expected}
        if mismatches:
            raise ValueError(f'DG03 source tendon application differs from source/API tolerances: {mismatches!r}')
        expected_effort_api = (
            'Articulation.set_dof_efforts'
            if receipt.provenance_kind == 'native_runtime' else 'synthetic-no-physics'
        )
        expected_readback_api = (
            'Articulation.get_dof_efforts'
            if receipt.provenance_kind == 'native_runtime' else 'synthetic-no-physics'
        )
        expected_mimic_api = (
            'Usd.Prim.GetAttribute(...).Set/Get'
            if receipt.provenance_kind == 'native_runtime' else 'synthetic-no-physics'
        )
        contact_witness = application.get('public_contact_witness')
        if not isinstance(contact_witness, Mapping):
            raise TypeError('DG03 substep requires a typed public contact witness')
        if receipt.provenance_kind == 'native_runtime':
            contact_count = contact_witness.get('contact_count')
            contact_force = contact_witness.get('normal_force_sum_N')
            raw_contact_count = contact_witness.get('raw_contact_count')
            actor_paths = contact_witness.get('raw_contact_actor_paths')
            support_forces = contact_witness.get('support_contact_normal_forces_N')
            support_path = '/F05Scene/support/collision'
            if (contact_witness.get('schema_version') != 'f05-dg03-public-contact-witness-v2'
                    or contact_witness.get('provenance_kind') != 'native_runtime'
                    or contact_witness.get('api') != 'RigidPrim.get_raw_contact_data'
                    or contact_witness.get('sensor_path') != '/F05Scene/free_cube'
                    or contact_witness.get('support_path') != support_path
                    or type(raw_contact_count) is not int or raw_contact_count < 0 or raw_contact_count > 32
                    or type(actor_paths) is not list or len(actor_paths) != raw_contact_count
                    or any(type(path) is not str or not path.startswith('/') for path in actor_paths)
                    or type(contact_count) is not int or contact_count < 0 or contact_count > raw_contact_count
                    or type(support_forces) is not list or len(support_forces) != contact_count
                    or any(type(value) not in (int, float) or isinstance(value, bool)
                           or not math.isfinite(float(value)) or float(value) < 0.0
                           for value in support_forces)
                    or type(contact_force) not in (int, float) or isinstance(contact_force, bool)
                    or not math.isfinite(float(contact_force)) or float(contact_force) < 0.0
                    or not math.isclose(math.fsum(float(value) for value in support_forces),
                                        float(contact_force), rel_tol=1e-7, abs_tol=1e-7)
                    or sum(path == '/F05Scene/support' or path == support_path
                           or path.startswith(support_path + '/') for path in actor_paths) != contact_count
                    or contact_witness.get('contact_present') is not (contact_count > 0)):
                raise ValueError('DG03 public cube/support contact witness is malformed or mismapped')
        elif (contact_witness.get('schema_version') != 'f05-dg03-public-contact-witness-v2'
              or contact_witness.get('provenance_kind') != 'synthetic_fixture'
              or contact_witness.get('api') != 'synthetic-no-physics'
              or contact_witness.get('contact_count') != 0
              or contact_witness.get('raw_contact_count') != 0
              or contact_witness.get('raw_contact_actor_paths') != []
              or contact_witness.get('support_contact_normal_forces_N') != []
              or contact_witness.get('normal_force_sum_N') != 0.0
              or contact_witness.get('physical_contact_checked') is not False):
            raise ValueError('DG03 synthetic S1 cannot claim a physical contact measurement')
        if (application.get('public_effort_api') != expected_effort_api
                or application.get('public_effort_readback_api') != expected_readback_api
                or application.get('public_mimic_frequency_api') != expected_mimic_api):
            raise ValueError('DG03 substep effort/mimic provenance does not match its native/synthetic receipt')

    def close(self) -> None:
        if not self._closed:
            try:
                self._native_io.close()
            finally:
                self._closed = True

    def close_runtime_owner(self) -> None:
        """Close process-scoped provider resources only when the Env is done."""
        close_owner = getattr(self._native_io, 'close_runtime_owner', None)
        if callable(close_owner):
            close_owner()


# Backward compatibility for F03 synthetic S1 tests; both names share one
# lifecycle implementation and no second RuntimeSession owner is created.
F03CoreRuntimeSession = UsdCoreRuntimeSession


__all__ = [
    'F03CoreRuntimeSession', 'UsdCoreRuntimeSession', 'NativeAdvanceReceiptV1', 'NativePositionWriteAckV1',
    'NativeResetWriteReceiptV1', 'NativeRuntimeIOV1', 'NativeRuntimeIOMetadataV1',
    'NativeRuntimeReadbackV1',
]
