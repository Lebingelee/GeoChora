"""Advanced additive camera geometry route; provider-free public values."""
from .contracts import CameraGeometry, ResolvedCameraMetadata, MOUNT_FROM_CAMERA
from .geometry import resolve_camera, intrinsics, fov_x, inverse_transform, project_world, back_project_world, lower_legacy_camera
from .images import (
    CanonicalCameraObservation,
    CanonicalEntityLabelV1,
    CanonicalEntityLabelMapV1,
    CanonicalEntityInstanceSegmentationV1,
)
from .consumer import (
    CAMERA_IDS,
    FIXED_CAMERA_ID,
    HAND_CAMERA_ID,
    MAX_CAMERA_HORIZON,
    CameraCaptureMetadataV1,
    CameraMountRequestV1,
    CameraObservationBoundaryV1,
    CameraObservationConfigV1,
)

__all__ = [
    'CameraGeometry', 'ResolvedCameraMetadata', 'MOUNT_FROM_CAMERA',
    'resolve_camera', 'intrinsics', 'fov_x', 'inverse_transform',
    'project_world', 'back_project_world', 'lower_legacy_camera',
    'CanonicalCameraObservation', 'CanonicalEntityLabelV1',
    'CanonicalEntityLabelMapV1', 'CanonicalEntityInstanceSegmentationV1',
    'CameraCaptureMetadataV1', 'CameraMountRequestV1',
    'CameraObservationBoundaryV1', 'CameraObservationConfigV1',
    'CAMERA_IDS', 'FIXED_CAMERA_ID', 'HAND_CAMERA_ID', 'MAX_CAMERA_HORIZON',
]
