"""Linked camera schema; never changes approved TaskArtifact v0 serialization."""
from dataclasses import dataclass
import hashlib
import json
import math
import re
import numpy as np
from ...artifacts.contracts import Contract, _choice, _name

Matrix4 = tuple[tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float, float, float]]
Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
IDENTITY = ((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))
MOUNT_FROM_CAMERA = ((0.,0.,1.,0.),(-1.,0.,0.,0.),(0.,-1.,0.,0.),(0.,0.,0.,1.))


def rigid_transform(value):
    matrix = np.asarray(value, dtype=np.float64)
    if (matrix.shape != (4,4) or not np.isfinite(matrix).all()
        or not np.array_equal(matrix[3], [0,0,0,1])
        or not np.allclose(matrix[:3,:3].T @ matrix[:3,:3], np.eye(3), atol=1e-6, rtol=0)
        or abs(np.linalg.det(matrix[:3,:3])-1) > 1e-6):
        raise ValueError('expected finite proper rigid transform')
    return matrix


@dataclass(frozen=True)
class CameraGeometry(Contract):
    schema_version: str
    task_artifact_hash: str
    camera_id: str
    parent_frame: str
    T_parent_from_mount: Matrix4
    T_mount_from_camera: Matrix4
    width: int
    height: int
    fov_y: float
    near: float
    far: float
    rgb: bool = True
    depth: bool = True
    rgb_layout: str = 'HWC'
    rgb_dtype: str = 'float32'
    pixel_convention: str = 'image_edges_pixel_centers_half'
    depth_convention: str = 'optical_z_m_float32'
    capture_phase: str = 'post_control_step'

    def validate(self):
        _choice(self.schema_version, {'camera-observation-v0'}, 'camera schema')
        if not re.fullmatch('[0-9a-f]{64}', self.task_artifact_hash):
            raise ValueError('camera must link a TaskArtifact SHA256')
        _name(self.camera_id); _name(self.parent_frame)
        rigid_transform(self.T_parent_from_mount); rigid_transform(self.T_mount_from_camera)
        if self.width < 1 or self.height < 1 or not 0 < self.fov_y < math.pi:
            raise ValueError('invalid resolution/FOV')
        if not 0 < self.near < self.far or not (self.rgb or self.depth):
            raise ValueError('invalid clipping/modalities')
        _choice(self.rgb_layout, {'HWC','CHW'}, 'RGB layout')
        _choice(self.rgb_dtype, {'float32','uint8'}, 'RGB dtype')
        _choice(self.pixel_convention, {'image_edges_pixel_centers_half'}, 'pixels')
        _choice(self.depth_convention, {'optical_z_m_float32'}, 'depth')
        _choice(self.capture_phase, {'post_control_step'}, 'capture timing')

    @property
    def identity_hash(self):
        return hashlib.sha256(json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ResolvedCameraMetadata(Contract):
    camera: CameraGeometry
    T_world_from_mount: Matrix4
    T_world_from_camera: Matrix4
    T_camera_from_world: Matrix4
    K: Matrix3
    fov_x: float
    capture_control_step: int
    capture_simulation_time: float

    def validate(self):
        for matrix in (self.T_world_from_mount,self.T_world_from_camera,self.T_camera_from_world):
            rigid_transform(matrix)
        if self.capture_control_step < 0 or self.capture_simulation_time < 0:
            raise ValueError('negative capture boundary')
        if not np.allclose(np.array(self.T_world_from_camera) @ self.T_camera_from_world, np.eye(4), atol=1e-6, rtol=0):
            raise ValueError('camera transforms are not inverses')
        from .geometry import intrinsics, fov_x
        if not np.array_equal(np.array(self.K), intrinsics(self.camera)) or self.fov_x != fov_x(self.camera):
            raise ValueError('metadata intrinsics inconsistent with camera')
        if not np.allclose(np.array(self.T_world_from_mount) @ self.camera.T_mount_from_camera, self.T_world_from_camera, atol=1e-6, rtol=0):
            raise ValueError('mount/camera composition inconsistent')
