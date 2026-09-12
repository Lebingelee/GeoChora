"""Small, dependency-free pose operations used by trajectory conversion."""

from __future__ import annotations

import numpy as np


def normalize_quaternion(quaternion: np.ndarray) -> np.ndarray:
    value = np.asarray(quaternion, dtype=np.float64).reshape(4)
    if not np.isfinite(value).all():
        raise ValueError("quaternion must be finite")
    norm = float(np.linalg.norm(value))
    if norm <= 1.0e-12:
        raise ValueError("quaternion cannot be zero")
    return value / norm


def quaternion_slerp(first: np.ndarray, second: np.ndarray, fraction: float) -> np.ndarray:
    """Interpolate two wxyz quaternions while keeping a continuous hemisphere."""
    left = normalize_quaternion(first)
    right = normalize_quaternion(second)
    dot = float(np.dot(left, right))
    if dot < 0.0:
        right = -right
        dot = -dot
    dot = float(np.clip(dot, -1.0, 1.0))
    t = float(np.clip(fraction, 0.0, 1.0))
    if dot > 1.0 - 1.0e-8:
        return normalize_quaternion((1.0 - t) * left + t * right)
    angle = float(np.arccos(dot))
    sine = float(np.sin(angle))
    return normalize_quaternion(
        (np.sin((1.0 - t) * angle) / sine) * left
        + (np.sin(t * angle) / sine) * right
    )


def interpolate_pose(first: np.ndarray, second: np.ndarray, fraction: float) -> np.ndarray:
    """Linearly interpolate translation and slerp a wxyz orientation."""
    left = np.asarray(first, dtype=np.float64).reshape(7)
    right = np.asarray(second, dtype=np.float64).reshape(7)
    t = float(np.clip(fraction, 0.0, 1.0))
    return np.concatenate(
        [((1.0 - t) * left[:3] + t * right[:3]), quaternion_slerp(left[3:], right[3:], t)]
    )


def quat_to_matrix(quaternion: np.ndarray) -> np.ndarray:
    w, x, y, z = normalize_quaternion(quaternion)
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def matrix_to_quat(matrix: np.ndarray) -> np.ndarray:
    value = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    trace = float(np.trace(value))
    if trace > 0.0:
        scale = 2.0 * np.sqrt(trace + 1.0)
        quaternion = np.array(
            [0.25 * scale, (value[2, 1] - value[1, 2]) / scale,
             (value[0, 2] - value[2, 0]) / scale, (value[1, 0] - value[0, 1]) / scale]
        )
    else:
        diagonal = np.diag(value)
        index = int(np.argmax(diagonal))
        if index == 0:
            scale = 2.0 * np.sqrt(max(1.0e-16, 1.0 + value[0, 0] - value[1, 1] - value[2, 2]))
            quaternion = np.array(
                [(value[2, 1] - value[1, 2]) / scale, 0.25 * scale,
                 (value[0, 1] + value[1, 0]) / scale, (value[0, 2] + value[2, 0]) / scale]
            )
        elif index == 1:
            scale = 2.0 * np.sqrt(max(1.0e-16, 1.0 + value[1, 1] - value[0, 0] - value[2, 2]))
            quaternion = np.array(
                [(value[0, 2] - value[2, 0]) / scale, (value[0, 1] + value[1, 0]) / scale,
                 0.25 * scale, (value[1, 2] + value[2, 1]) / scale]
            )
        else:
            scale = 2.0 * np.sqrt(max(1.0e-16, 1.0 + value[2, 2] - value[0, 0] - value[1, 1]))
            quaternion = np.array(
                [(value[1, 0] - value[0, 1]) / scale, (value[0, 2] + value[2, 0]) / scale,
                 (value[1, 2] + value[2, 1]) / scale, 0.25 * scale]
            )
    quaternion = normalize_quaternion(quaternion)
    if quaternion[0] < 0.0:
        quaternion = -quaternion
    return quaternion


def pose_matrix(pose: np.ndarray) -> np.ndarray:
    value = np.asarray(pose, dtype=np.float64).reshape(7)
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = quat_to_matrix(value[3:])
    result[:3, 3] = value[:3]
    return result


def matrix_pose(matrix: np.ndarray) -> np.ndarray:
    value = np.asarray(matrix, dtype=np.float64).reshape(4, 4)
    return np.concatenate([value[:3, 3], matrix_to_quat(value[:3, :3])])


def transform_absolute_world_to_target(
    target_world: np.ndarray,
    current_ee_world: np.ndarray,
    *,
    target_reference: str,
    base_world: np.ndarray | None = None,
    target_mode: str,
) -> np.ndarray:
    """Convert one world absolute target to an absolute/delta target action."""
    target = pose_matrix(target_world)
    current = pose_matrix(current_ee_world)
    if target_mode == "absolute_pose":
        if target_reference == "world":
            return matrix_pose(target)
        if target_reference == "base" and base_world is not None:
            return matrix_pose(np.linalg.inv(pose_matrix(base_world)) @ target)
    if target_mode == "delta_pose":
        if target_reference == "world":
            return matrix_pose(target @ np.linalg.inv(current))
        if target_reference == "ee":
            return matrix_pose(np.linalg.inv(current) @ target)
        if target_reference == "base" and base_world is not None:
            base = pose_matrix(base_world)
            return matrix_pose(np.linalg.inv(base) @ target @ np.linalg.inv(current) @ base)
    raise ValueError(f"unsupported target mode/reference: {target_mode}/{target_reference}")
