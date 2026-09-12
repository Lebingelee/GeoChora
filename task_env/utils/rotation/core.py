"""TaskEnv 的 NumPy 旋转工具。

全部函数使用右手系 local-to-world 旋转矩阵和 ``(w, x, y, z)`` 四元数。
计算在 ``float64`` 中完成，调用边界自行转换所需 dtype。
"""

from __future__ import annotations

import math

import numpy as np


_EPSILON = 1.0e-12


def normalize_quat_wxyz(quaternion: np.ndarray) -> np.ndarray:
    """返回单位 WXYZ 四元数；零范数输入无有效旋转语义。"""
    value = np.asarray(quaternion, dtype=np.float64).reshape(4)
    norm = float(np.linalg.norm(value))
    if not np.isfinite(value).all() or norm <= _EPSILON:
        raise ValueError("quaternion must be finite with positive norm")
    return value / norm


def quat_multiply_wxyz(lhs: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """返回 Hamilton 积 ``lhs * rhs``，结果为单位 WXYZ 四元数。"""
    lw, lx, ly, lz = normalize_quat_wxyz(lhs)
    rw, rx, ry, rz = normalize_quat_wxyz(rhs)
    return normalize_quat_wxyz(np.array((
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    ), dtype=np.float64))


def quat_wxyz_to_matrix(quaternion: np.ndarray) -> np.ndarray:
    """将单位化的 WXYZ 四元数转换为 3×3 local-to-world 旋转矩阵。"""
    w, x, y, z = normalize_quat_wxyz(quaternion)
    return np.array((
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    ), dtype=np.float64)


def matrix_to_quat_wxyz(rotation: np.ndarray) -> np.ndarray:
    """将旋转矩阵转为规范化、符号稳定（``w >= 0``）的 WXYZ 四元数。"""
    matrix = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    if not np.isfinite(matrix).all():
        raise ValueError("rotation matrix must contain only finite values")
    trace = float(np.trace(matrix))
    if trace > 0.0:
        scale = 2.0 * math.sqrt(max(trace + 1.0, 0.0))
        quaternion = np.array((0.25 * scale, (matrix[2, 1] - matrix[1, 2]) / scale,
                               (matrix[0, 2] - matrix[2, 0]) / scale,
                               (matrix[1, 0] - matrix[0, 1]) / scale), dtype=np.float64)
    else:
        index = int(np.argmax(np.diag(matrix)))
        if index == 0:
            scale = 2.0 * math.sqrt(max(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2], 0.0))
            quaternion = np.array(((matrix[2, 1] - matrix[1, 2]) / scale, 0.25 * scale,
                                   (matrix[0, 1] + matrix[1, 0]) / scale,
                                   (matrix[0, 2] + matrix[2, 0]) / scale), dtype=np.float64)
        elif index == 1:
            scale = 2.0 * math.sqrt(max(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2], 0.0))
            quaternion = np.array(((matrix[0, 2] - matrix[2, 0]) / scale,
                                   (matrix[0, 1] + matrix[1, 0]) / scale, 0.25 * scale,
                                   (matrix[1, 2] + matrix[2, 1]) / scale), dtype=np.float64)
        else:
            scale = 2.0 * math.sqrt(max(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1], 0.0))
            quaternion = np.array(((matrix[1, 0] - matrix[0, 1]) / scale,
                                   (matrix[0, 2] + matrix[2, 0]) / scale,
                                   (matrix[1, 2] + matrix[2, 1]) / scale, 0.25 * scale), dtype=np.float64)
    quaternion = normalize_quat_wxyz(quaternion)
    return quaternion if quaternion[0] >= 0.0 else -quaternion


def rotvec_to_matrix(rotvec: np.ndarray) -> np.ndarray:
    """将弧度旋转向量转换为旋转矩阵。"""
    vector = np.asarray(rotvec, dtype=np.float64).reshape(3)
    angle = float(np.linalg.norm(vector))
    if not np.isfinite(vector).all():
        raise ValueError("rotation vector must contain only finite values")
    if angle <= _EPSILON:
        return np.eye(3, dtype=np.float64)
    axis = vector / angle
    skew = np.array(((0.0, -axis[2], axis[1]), (axis[2], 0.0, -axis[0]),
                     (-axis[1], axis[0], 0.0)), dtype=np.float64)
    return np.eye(3, dtype=np.float64) + math.sin(angle) * skew + (1.0 - math.cos(angle)) * (skew @ skew)


def matrix_to_rotvec(rotation: np.ndarray) -> np.ndarray:
    """返回旋转矩阵的最短弧度旋转向量。"""
    matrix = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    cosine = float(np.clip((np.trace(matrix) - 1.0) * 0.5, -1.0, 1.0))
    angle = math.acos(cosine)
    if angle <= 1.0e-10:
        return np.zeros(3, dtype=np.float64)
    skew_vector = np.array((matrix[2, 1] - matrix[1, 2], matrix[0, 2] - matrix[2, 0],
                            matrix[1, 0] - matrix[0, 1]), dtype=np.float64)
    sine = math.sin(angle)
    if abs(sine) > 1.0e-8:
        return angle * skew_vector / (2.0 * sine)
    axis = np.sqrt(np.maximum((np.diag(matrix) + 1.0) * 0.5, 0.0))
    axis[int(np.argmax(np.abs(axis)))] *= np.sign(skew_vector[int(np.argmax(np.abs(axis)))]) or 1.0
    norm = float(np.linalg.norm(axis))
    return angle * (axis / norm if norm > _EPSILON else np.array((1.0, 0.0, 0.0)))


def rotation_vector_error(current: np.ndarray, target: np.ndarray) -> np.ndarray:
    """返回将 ``current`` 左乘到 ``target`` 的最短世界系旋转向量。"""
    return matrix_to_rotvec(np.asarray(target, dtype=np.float64).reshape(3, 3) @ np.asarray(current, dtype=np.float64).reshape(3, 3).T)


def rotate_vector_wxyz(quaternion: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """将局部向量旋转到世界系。"""
    return quat_wxyz_to_matrix(quaternion) @ np.asarray(vector, dtype=np.float64).reshape(3)


def quat_angle_wxyz(start: np.ndarray, goal: np.ndarray) -> float:
    """返回两单位四元数所表示姿态间的最短夹角。"""
    dot = abs(float(np.dot(normalize_quat_wxyz(start), normalize_quat_wxyz(goal))))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def slerp_quat_wxyz(start: np.ndarray, goal: np.ndarray, fraction: float) -> np.ndarray:
    """沿最短弧插值 WXYZ 四元数。"""
    q0 = normalize_quat_wxyz(start)
    q1 = normalize_quat_wxyz(goal)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1, dot = -q1, -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        return normalize_quat_wxyz((1.0 - fraction) * q0 + fraction * q1)
    theta_0 = math.acos(dot)
    theta = theta_0 * fraction
    scale_0 = math.cos(theta) - dot * math.sin(theta) / math.sin(theta_0)
    scale_1 = math.sin(theta) / math.sin(theta_0)
    return normalize_quat_wxyz(scale_0 * q0 + scale_1 * q1)


def look_at_quat_wxyz(position: np.ndarray, target: np.ndarray) -> tuple[float, float, float, float]:
    """构造 local +X 指向 ``target``、local +Z 尽量向上的相机 WXYZ 姿态。"""
    origin = np.asarray(position, dtype=np.float64).reshape(3)
    forward = np.asarray(target, dtype=np.float64).reshape(3) - origin
    forward_norm = float(np.linalg.norm(forward))
    if not np.isfinite(forward).all() or forward_norm <= _EPSILON:
        raise ValueError("camera position and target must be distinct finite points")
    forward /= forward_norm
    reference_up = np.array((0.0, 0.0, 1.0), dtype=np.float64)
    right = np.cross(forward, reference_up)
    if float(np.linalg.norm(right)) <= _EPSILON:
        reference_up = np.array((0.0, 1.0, 0.0), dtype=np.float64)
        right = np.cross(forward, reference_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    up /= np.linalg.norm(up)
    quaternion = matrix_to_quat_wxyz(np.column_stack((forward, np.cross(up, forward), up)))
    return tuple(float(value) for value in quaternion)
