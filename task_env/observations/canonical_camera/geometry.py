"""Provider-free SI transforms, pinhole geometry and explicit legacy lowering."""
import math
import numpy as np
from ...utils.rotation import quat_wxyz_to_matrix
from .contracts import CameraGeometry, ResolvedCameraMetadata, MOUNT_FROM_CAMERA, rigid_transform


def matrix_tuple(value):
    return tuple(tuple(float(v) for v in row) for row in value)


def inverse_transform(value):
    matrix = rigid_transform(value)
    result = np.eye(4)
    result[:3,:3] = matrix[:3,:3].T
    result[:3,3] = -result[:3,:3] @ matrix[:3,3]
    return result


def intrinsics(camera):
    fy = .5 * camera.height / math.tan(camera.fov_y/2)
    return np.array([[fy,0,camera.width/2],[0,fy,camera.height/2],[0,0,1]], dtype=np.float64)


def fov_x(camera):
    return 2*math.atan(camera.width/camera.height*math.tan(camera.fov_y/2))


def resolve_camera(camera, state):
    parent = np.eye(4)
    if camera.parent_frame != 'world':
        pose = state.pose_world[camera.parent_frame]  # fail closed missing semantic frame
        parent[:3,:3] = quat_wxyz_to_matrix(pose.quaternion_wxyz)
        parent[:3,3] = pose.position
    mount = parent @ camera.T_parent_from_mount
    optical = mount @ camera.T_mount_from_camera
    return ResolvedCameraMetadata(camera, matrix_tuple(mount), matrix_tuple(optical),
        matrix_tuple(inverse_transform(optical)), matrix_tuple(intrinsics(camera)), fov_x(camera),
        state.control_step, state.simulation_time)


def project_world(metadata, points):
    points = np.asarray(points, dtype=np.float64)
    transform = np.array(metadata.T_camera_from_world)
    camera_points = points @ transform[:3,:3].T + transform[:3,3]
    if not np.isfinite(camera_points).all() or np.any(camera_points[:,2] <= 0):
        raise ValueError('projection requires finite points in front of camera')
    pixels = camera_points @ np.array(metadata.K).T
    return pixels[:,:2] / pixels[:,2,None]


def back_project_world(metadata, pixels, depth):
    pixels = np.asarray(pixels, dtype=np.float64)
    depth = np.asarray(depth, dtype=np.float64)
    if pixels.ndim != 2 or pixels.shape[1] != 2 or depth.shape != (len(pixels),) or not np.isfinite(pixels).all() or not np.isfinite(depth).all() or np.any(depth <= 0):
        raise ValueError('back-projection requires finite pixels and positive optical-Z')
    rays = np.c_[pixels,np.ones(len(pixels))] @ np.linalg.inv(metadata.K).T
    points = rays*depth[:,None]
    transform = np.array(metadata.T_world_from_camera)
    return points @ transform[:3,:3].T + transform[:3,3]


def optical_depth(native, metadata, *, native_convention):
    camera = metadata.camera
    values = np.asarray(native, dtype=np.float64)
    if values.shape != (camera.height,camera.width) or not np.isfinite(values).all():
        raise ValueError('invalid native depth')
    if native_convention == 'ray_distance_m':
        yy,xx = np.indices(values.shape)
        K = np.array(metadata.K)
        values = values / np.sqrt(1+((xx+.5-K[0,2])/K[0,0])**2+((yy+.5-K[1,2])/K[1,1])**2)
    elif native_convention != 'optical_z_m':
        raise ValueError('unknown native depth convention')
    values = np.where((values >= camera.near) & (values <= camera.far), values, 0)
    return np.ascontiguousarray(values, dtype=np.float32)


def lower_legacy_camera(spec, *, task_artifact_hash, parent_frame):
    """Caller explicitly binds legacy body/site names to canonical semantic frames."""
    if (spec.frame == 'world') != (parent_frame == 'world'):
        raise ValueError('legacy/semantic parent mismatch')
    local = np.eye(4)
    local[:3,:3] = quat_wxyz_to_matrix(spec.quaternion_wxyz)
    local[:3,3] = spec.position
    return CameraGeometry('camera-observation-v0', task_artifact_hash, spec.name, parent_frame,
        matrix_tuple(local), MOUNT_FROM_CAMERA, spec.width, spec.height, spec.fov_y,
        spec.near, spec.far, spec.rgb, spec.depth, spec.rgb_layout, spec.rgb_dtype)
