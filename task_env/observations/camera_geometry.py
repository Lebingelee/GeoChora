"""Camera sensor geometry helpers shared by observation providers."""

from __future__ import annotations

import numpy as np

from ..utils.rotation import (
    normalize_quat_wxyz as _normalize_quat_wxyz,
    quat_multiply_wxyz as _quat_multiply_wxyz,
    quat_wxyz_to_matrix,
    rotate_vector_wxyz as _rotate_vector_wxyz,
)


def normalize_quat_wxyz(value) -> np.ndarray:
    return _normalize_quat_wxyz(value).astype(np.float32)


def quat_multiply_wxyz(lhs, rhs) -> np.ndarray:
    return _quat_multiply_wxyz(lhs, rhs).astype(np.float32)


def quat_to_matrix_wxyz(value) -> np.ndarray:
    return quat_wxyz_to_matrix(value).astype(np.float32)


def rotate_vector_wxyz(quaternion, vector) -> np.ndarray:
    return _rotate_vector_wxyz(quaternion, vector).astype(np.float32)


def transform_matrix(position, quaternion_wxyz) -> np.ndarray:
    matrix = np.eye(4, dtype=np.float32)
    matrix[:3, :3] = quat_to_matrix_wxyz(quaternion_wxyz)
    matrix[:3, 3] = np.asarray(position, dtype=np.float32).reshape(3)
    return matrix
