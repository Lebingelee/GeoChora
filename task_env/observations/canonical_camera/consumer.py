"""Versioned opt-in contract for the bounded D04 camera observation consumer.

The value layer is provider-free.  It describes two CameraGeometry values and
the metadata needed to verify each boundary; renderer construction remains in
``task_env.render.camera`` and is deliberately deferred until an explicit
environment reset.
"""

from dataclasses import dataclass
import hashlib
import math
from typing import Any
from collections.abc import Mapping

import numpy as np

from ...artifacts.contracts import Contract, _choice, _name
from ...artifacts.state import StateBoundaryIdentity
from ...render.camera.source import CameraCaptureIdentityV1
from .contracts import CameraGeometry, Matrix4, MOUNT_FROM_CAMERA, ResolvedCameraMetadata, rigid_transform
from .images import CanonicalEntityLabelMapV1


FIXED_CAMERA_ID = "d04-fixed-square-peg-calibration-v1"
HAND_CAMERA_ID = "d04-panda-hand-mounted-camera-v1"
CAMERA_IDS = (FIXED_CAMERA_ID, HAND_CAMERA_ID)
CAMERA_WIDTH = 321
CAMERA_HEIGHT = 241
CAMERA_FOV_Y = math.pi / 2
CAMERA_NEAR_M = 0.01
CAMERA_FAR_M = 3.0
PUBLIC_MODALITIES = ("rgb", "depth", "entity_instance_segmentation")
MAX_CAMERA_HORIZON = 16
PUBLIC_BYTES_PER_BOUNDARY = 3_094_440
RECORDED_BYTES_PER_BOUNDARY = 1_701_942
DEFAULT_PUBLIC_BUFFER_BYTES = 64 * 1024 * 1024
DEFAULT_RECORDING_BUFFER_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class CameraMountRequestV1(Contract):
    """Caller-authored parent-to-mount transform for one D04 camera."""

    schema_version: str
    camera_id: str
    parent_frame: str
    T_parent_from_mount: Matrix4

    def validate(self):
        _choice(self.schema_version, {"camera-mount-request-v1"}, "camera mount request")
        _name(self.camera_id)
        _name(self.parent_frame)
        rigid_transform(self.T_parent_from_mount)
        expected_parent = "world" if self.camera_id == FIXED_CAMERA_ID else "hand"
        if self.camera_id not in CAMERA_IDS or self.parent_frame != expected_parent:
            raise ValueError("R04a cameras require the fixed world mount and Panda hand mount identities")


@dataclass(frozen=True)
class CameraObservationConfigV1(Contract):
    """Exact bounded opt-in contract; never selected by the state-only default."""

    schema_version: str
    cameras: tuple[CameraMountRequestV1, ...]
    width: int = CAMERA_WIDTH
    height: int = CAMERA_HEIGHT
    fov_y: float = CAMERA_FOV_Y
    near_m: float = CAMERA_NEAR_M
    far_m: float = CAMERA_FAR_M
    required_modalities: tuple[str, ...] = PUBLIC_MODALITIES
    recorded_rgb_layout: str = "CHW"
    recorded_rgb_dtype: str = "uint8"
    rgb_quantization: str = "float32_x255_np_rint_v1"
    max_public_buffer_bytes: int = DEFAULT_PUBLIC_BUFFER_BYTES
    max_recording_buffer_bytes: int = DEFAULT_RECORDING_BUFFER_BYTES

    def validate(self):
        _choice(self.schema_version, {"camera-observation-consumer-v1"}, "camera observation config")
        cameras = tuple(self.cameras)
        if any(not isinstance(item, CameraMountRequestV1) for item in cameras):
            raise TypeError("camera observation config requires CameraMountRequestV1 values")
        if tuple(item.camera_id for item in cameras) != CAMERA_IDS:
            raise ValueError("camera observation config requires the fixed and hand-mounted cameras in canonical order")
        for item in cameras:
            item.validate()
        if (type(self.width) is not int or type(self.height) is not int
                or not 1 <= self.width <= CAMERA_WIDTH
                or not 1 <= self.height <= CAMERA_HEIGHT):
            raise ValueError("camera resolution must be positive and no larger than the 321×241 R04a envelope")
        if (not math.isclose(float(self.fov_y), CAMERA_FOV_Y, rel_tol=0, abs_tol=1e-12)
                or not math.isclose(float(self.near_m), CAMERA_NEAR_M, rel_tol=0, abs_tol=1e-12)
                or not math.isclose(float(self.far_m), CAMERA_FAR_M, rel_tol=0, abs_tol=1e-12)):
            raise ValueError("R04a D04 FOV and clipping planes are fixed by the accepted camera source contract")
        modalities = tuple(self.required_modalities)
        if modalities != PUBLIC_MODALITIES:
            raise ValueError("R04a requires RGB, optical-Z depth, and canonical Entity mask on every camera")
        if (self.recorded_rgb_layout != "CHW" or self.recorded_rgb_dtype != "uint8"
                or self.rgb_quantization != "float32_x255_np_rint_v1"):
            raise ValueError("camera recording must preserve the existing CHW uint8 np.rint quantization route")
        if (type(self.max_public_buffer_bytes) is not int
                or type(self.max_recording_buffer_bytes) is not int
                or self.max_public_buffer_bytes < 1 or self.max_recording_buffer_bytes < 1):
            raise ValueError("camera observation byte budgets must be positive integers")
        if (self.max_public_buffer_bytes > DEFAULT_PUBLIC_BUFFER_BYTES
                or self.max_recording_buffer_bytes > DEFAULT_RECORDING_BUFFER_BYTES):
            raise ValueError("R04a camera observation budgets may not exceed the frozen 64/128 MiB limits")

    def validate_production_envelope(self):
        self.validate()
        if self.width != CAMERA_WIDTH or self.height != CAMERA_HEIGHT:
            raise ValueError("the R04a Position candidate requires exactly 321×241 cameras")

    def geometries(self, task_artifact_hash: str) -> tuple[CameraGeometry, ...]:
        """Bind authored mounts to the exact TaskArtifact without guessing an identity."""

        result = tuple(CameraGeometry(
            schema_version="camera-observation-v0",
            task_artifact_hash=task_artifact_hash,
            camera_id=mount.camera_id,
            parent_frame=mount.parent_frame,
            T_parent_from_mount=mount.T_parent_from_mount,
            T_mount_from_camera=MOUNT_FROM_CAMERA,
            width=self.width,
            height=self.height,
            fov_y=float(self.fov_y),
            near=float(self.near_m),
            far=float(self.far_m),
            rgb=True,
            depth=True,
            rgb_layout="HWC",
            rgb_dtype="float32",
            pixel_convention="image_edges_pixel_centers_half",
            depth_convention="optical_z_m_float32",
            capture_phase="post_control_step",
        ) for mount in self.cameras)
        for item in result:
            item.validate()
        return result

    def capacity(self, horizon: int) -> dict[str, int]:
        if type(horizon) is not int or not 1 <= horizon <= MAX_CAMERA_HORIZON:
            raise ValueError(f"camera observation horizon must be an integer in [1, {MAX_CAMERA_HORIZON}]")
        boundaries = horizon + 1
        pixels = len(self.cameras) * self.width * self.height
        public_per_boundary = pixels * (3 * np.dtype(np.float32).itemsize + np.dtype(np.float32).itemsize + np.dtype(np.uint32).itemsize)
        recorded_per_boundary = pixels * (3 * np.dtype(np.uint8).itemsize + np.dtype(np.float32).itemsize + np.dtype(np.uint32).itemsize)
        public_bytes = boundaries * public_per_boundary
        recorded_bytes = boundaries * recorded_per_boundary
        if public_bytes > self.max_public_buffer_bytes:
            raise MemoryError("camera public observation buffer exceeds its declared byte budget")
        if recorded_bytes > self.max_recording_buffer_bytes:
            raise MemoryError("camera recording buffer exceeds its declared byte budget")
        return {
            "boundary_count": boundaries,
            "public_bytes_per_boundary": public_per_boundary,
            "recorded_bytes_per_boundary": recorded_per_boundary,
            "public_total_bytes": public_bytes,
            "recorded_total_bytes": recorded_bytes,
            "public_budget_bytes": self.max_public_buffer_bytes,
            "recording_budget_bytes": self.max_recording_buffer_bytes,
            "combined_payload_bytes": public_bytes + recorded_bytes,
        }


@dataclass(frozen=True)
class CameraCaptureMetadataV1(Contract):
    """Calibration and canonical label map tied to one successful capture."""

    schema_version: str
    camera_id: str
    boundary_index: int
    capture_identity: CameraCaptureIdentityV1
    calibration: ResolvedCameraMetadata
    # CanonicalEntityLabelMapV1 predates Contract and has its own strict
    # codec. Store its JSON mapping here so this wrapper's strict Contract
    # codec does not need to change the established image value type.
    label_map: Mapping[str, object]
    mask_sha256: str

    def validate(self):
        _choice(self.schema_version, {"camera-capture-metadata-v1"}, "camera capture metadata")
        _name(self.camera_id)
        if type(self.boundary_index) is not int or self.boundary_index < 0:
            raise ValueError("camera capture metadata boundary index must be non-negative")
        if not isinstance(self.capture_identity, CameraCaptureIdentityV1):
            raise TypeError("camera metadata requires CameraCaptureIdentityV1")
        if not isinstance(self.calibration, ResolvedCameraMetadata):
            raise TypeError("camera metadata requires ResolvedCameraMetadata calibration")
        label_map = self.canonical_label_map
        identity = self.capture_identity
        identity.validate()
        self.calibration.validate()
        label_map.validate()
        if len(self.mask_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.mask_sha256):
            raise ValueError("camera mask requires a lowercase SHA-256 digest")
        boundary = identity.state_boundary
        if (identity.camera_id != self.camera_id
                or self.calibration.camera.camera_id != self.camera_id
                or self.calibration.camera.identity_hash != identity.camera_geometry_identity_hash
                or boundary.control_step != self.boundary_index
                or self.calibration.capture_control_step != self.boundary_index
                or self.calibration.capture_simulation_time != identity.sample_clock.simulation_time_s):
            raise ValueError("camera capture identity, calibration, and boundary disagree")
        if set(identity.modalities) != set(PUBLIC_MODALITIES):
            raise ValueError("R04a camera capture must include RGB, depth, and Entity segmentation")
        if (label_map.capture_identity_hash != identity.identity_hash
                or label_map.task_artifact_hash != identity.task_artifact_hash
                or label_map.scene_identity_hash != boundary.scene_identity_hash
                or label_map.render_source_identity_hash != identity.render_source_identity_hash
                or label_map.camera_id != identity.camera_id
                or label_map.scene_instance_id != boundary.scene_instance_id
                or label_map.provider_materialization_id != boundary.provider_materialization_id
                or label_map.episode_id != boundary.episode_id
                or label_map.reset_sample_id != boundary.reset_sample_id
                or label_map.state_boundary_id != boundary.boundary_id
                or label_map.state_revision != boundary.state_revision
                or label_map.control_step != boundary.control_step
                or label_map.simulation_time_s != identity.sample_clock.simulation_time_s):
            raise ValueError("camera Entity label map is stale or belongs to another capture")

    @property
    def canonical_label_map(self) -> CanonicalEntityLabelMapV1:
        """Decode the established strict label-map value from its JSON tree."""

        if not isinstance(self.label_map, Mapping):
            raise TypeError("camera metadata requires a canonical Entity label-map mapping")
        values = dict(self.label_map)
        labels = values.get("labels")
        if not isinstance(labels, (list, tuple)):
            raise ValueError("canonical Entity label-map labels must be an array")
        values["labels"] = [dict(item) if isinstance(item, Mapping) else item for item in labels]
        return CanonicalEntityLabelMapV1.from_mapping(values)

    @classmethod
    def from_mapping(cls, values):
        if not isinstance(values, dict) or set(values) != {
            "schema_version", "camera_id", "boundary_index", "capture_identity", "calibration", "label_map",
            "mask_sha256",
        }:
            raise ValueError("camera capture metadata has unknown or missing fields")
        return cls(
            schema_version=values["schema_version"],
            camera_id=values["camera_id"],
            boundary_index=values["boundary_index"],
            capture_identity=CameraCaptureIdentityV1.from_mapping(values["capture_identity"]),
            calibration=ResolvedCameraMetadata.from_mapping(values["calibration"]),
            label_map=values["label_map"],
            mask_sha256=values["mask_sha256"],
        )


@dataclass(frozen=True)
class CameraObservationBoundaryV1(Contract):
    """Strict semantic metadata for both camera captures at one state boundary."""

    schema_version: str
    boundary_index: int
    state_boundary_id: str
    simulation_time_s: float
    captures: tuple[CameraCaptureMetadataV1, ...]

    def validate(self):
        _choice(self.schema_version, {"camera-observation-boundary-v1"}, "camera observation boundary")
        if type(self.boundary_index) is not int or self.boundary_index < 0:
            raise ValueError("camera observation boundary index must be non-negative")
        _name(self.state_boundary_id)
        if isinstance(self.simulation_time_s, bool) or not math.isfinite(float(self.simulation_time_s)) or self.simulation_time_s < 0:
            raise ValueError("camera observation simulation clock must be finite and non-negative")
        captures = tuple(self.captures)
        if tuple(item.camera_id for item in captures) != CAMERA_IDS:
            raise ValueError("camera observation must contain both canonical cameras in order")
        boundaries: set[StateBoundaryIdentity] = set()
        common = None
        for capture in captures:
            if not isinstance(capture, CameraCaptureMetadataV1):
                raise TypeError("camera observation capture entries must use CameraCaptureMetadataV1")
            capture.validate()
            identity = capture.capture_identity
            if (capture.boundary_index != self.boundary_index
                    or identity.state_boundary.boundary_id != self.state_boundary_id
                    or identity.sample_clock.simulation_time_s != self.simulation_time_s):
                raise ValueError("fixed and hand-mounted captures do not share the declared boundary")
            shared = (
                identity.task_artifact_hash,
                identity.render_source_identity_hash,
                identity.execution_spec_identity_hash,
                identity.provider_manifest_identity_hash,
                identity.renderer_selection.to_mapping(),
            )
            if common is None:
                common = shared
            elif shared != common:
                raise ValueError("camera captures do not share one TaskArtifact/source/execution/renderer contract")
            boundaries.add(identity.state_boundary)
        if len(boundaries) != 1:
            raise ValueError("camera captures do not share one typed state publication")

    @classmethod
    def from_mapping(cls, values):
        if not isinstance(values, dict) or set(values) != {
            "schema_version", "boundary_index", "state_boundary_id", "simulation_time_s", "captures",
        }:
            raise ValueError("camera observation boundary has unknown or missing fields")
        if not isinstance(values["captures"], list):
            raise ValueError("camera observation boundary captures must be a list")
        return cls(
            schema_version=values["schema_version"],
            boundary_index=values["boundary_index"],
            state_boundary_id=values["state_boundary_id"],
            simulation_time_s=values["simulation_time_s"],
            captures=tuple(CameraCaptureMetadataV1.from_mapping(item) for item in values["captures"]),
        )


def camera_observation_boundary_from_captures(captures: tuple[Any, ...]) -> CameraObservationBoundaryV1:
    if len(captures) != 2:
        raise ValueError("R04a requires exactly two camera captures per boundary")
    metadata = []
    for camera_id, observation in zip(CAMERA_IDS, captures):
        if observation.capture_identity is None or observation.segmentation is None:
            raise ValueError("required camera capture identity or Entity mask is missing")
        identity = observation.capture_identity
        boundary = identity.state_boundary
        metadata.append(CameraCaptureMetadataV1(
            "camera-capture-metadata-v1", camera_id, boundary.control_step,
            identity, observation.metadata, observation.segmentation.label_map.to_mapping(),
            observation.segmentation.mask_sha256,
        ))
    first = metadata[0].capture_identity
    return CameraObservationBoundaryV1(
        "camera-observation-boundary-v1",
        first.state_boundary.control_step,
        first.state_boundary.boundary_id,
        first.sample_clock.simulation_time_s,
        tuple(metadata),
    )


def validate_camera_observation_boundaries(values, *, expected_count: int) -> tuple[CameraObservationBoundaryV1, ...]:
    if not isinstance(values, list) or len(values) != expected_count:
        raise ValueError("camera metadata count must match the stored T+1 observation count")
    result = tuple(CameraObservationBoundaryV1.from_mapping(item) for item in values)
    for index, boundary in enumerate(result):
        if boundary.boundary_index != index:
            raise ValueError("camera metadata boundaries must be contiguous from reset boundary zero")
    return result


__all__ = [
    "CAMERA_FAR_M", "CAMERA_FOV_Y", "CAMERA_HEIGHT", "CAMERA_IDS",
    "CAMERA_NEAR_M", "CAMERA_WIDTH", "DEFAULT_PUBLIC_BUFFER_BYTES",
    "DEFAULT_RECORDING_BUFFER_BYTES", "FIXED_CAMERA_ID", "HAND_CAMERA_ID",
    "MAX_CAMERA_HORIZON", "PUBLIC_BYTES_PER_BOUNDARY", "PUBLIC_MODALITIES",
    "RECORDED_BYTES_PER_BOUNDARY", "CameraCaptureMetadataV1",
    "CameraMountRequestV1", "CameraObservationBoundaryV1",
    "CameraObservationConfigV1", "camera_observation_boundary_from_captures",
    "validate_camera_observation_boundaries",
]
