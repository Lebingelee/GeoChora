"""Coordinate and transform helpers for the TaskEnv Flora boundary."""

from __future__ import annotations

import numpy as np


# GeoPhys uses right-handed Z-up; Flora/Donut uses right-handed Y-up.
_GEOPHYS_TO_FLORA = np.asarray(
    (
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, -1.0, 0.0),
    ),
    dtype=np.float32,
)
_GEOPHYS_TO_FLORA_4 = np.eye(4, dtype=np.float32)
_GEOPHYS_TO_FLORA_4[:3, :3] = _GEOPHYS_TO_FLORA


def geophys_to_flora_points(values: object) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    if array.shape[-1] != 3:
        raise ValueError("coordinate conversion requires a final dimension of 3")
    return np.ascontiguousarray(array @ _GEOPHYS_TO_FLORA.T)


def geophys_to_flora_matrix(matrix: object) -> np.ndarray:
    source = np.asarray(matrix, dtype=np.float32)
    if source.shape != (4, 4):
        raise ValueError("transform conversion requires a 4x4 matrix")
    return np.ascontiguousarray(
        _GEOPHYS_TO_FLORA_4 @ source @ _GEOPHYS_TO_FLORA_4.T
    )


def wxyz_to_matrix(quaternion: object) -> np.ndarray:
    quat = np.asarray(quaternion, dtype=np.float32).reshape(4)
    norm = float(np.linalg.norm(quat))
    if norm <= 1.0e-12:
        raise ValueError("quaternion norm must be positive")
    w, x, y, z = quat / norm
    return np.asarray(
        (
            (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
            (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
            (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
        ),
        dtype=np.float32,
    )


def pose_matrix(position: object, orientation_wxyz: object) -> np.ndarray:
    matrix = np.eye(4, dtype=np.float32)
    matrix[:3, :3] = wxyz_to_matrix(orientation_wxyz)
    matrix[:3, 3] = np.asarray(position, dtype=np.float32).reshape(3)
    return matrix


def matrix_to_flora_scene_fields(matrix: object) -> tuple[list[float], list[float], list[float]]:
    """Convert a GeoPhys local matrix to SceneFile translation/rotation/scale."""

    converted = geophys_to_flora_matrix(matrix)
    rotation = np.asarray(converted[:3, :3], dtype=np.float64)
    scale = np.linalg.norm(rotation, axis=0)
    scale = np.where(scale > 1.0e-12, scale, 1.0)
    rotation = rotation / scale
    trace = float(np.trace(rotation))
    if trace > 0.0:
        s = float(np.sqrt(trace + 1.0) * 2.0)
        w = 0.25 * s
        x = float((rotation[2, 1] - rotation[1, 2]) / s)
        y = float((rotation[0, 2] - rotation[2, 0]) / s)
        z = float((rotation[1, 0] - rotation[0, 1]) / s)
    elif rotation[0, 0] > rotation[1, 1] and rotation[0, 0] > rotation[2, 2]:
        s = float(np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2.0)
        w = float((rotation[2, 1] - rotation[1, 2]) / s)
        x = 0.25 * s
        y = float((rotation[0, 1] + rotation[1, 0]) / s)
        z = float((rotation[0, 2] + rotation[2, 0]) / s)
    elif rotation[1, 1] > rotation[2, 2]:
        s = float(np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2.0)
        w = float((rotation[0, 2] - rotation[2, 0]) / s)
        x = float((rotation[0, 1] + rotation[1, 0]) / s)
        y = 0.25 * s
        z = float((rotation[1, 2] + rotation[2, 1]) / s)
    else:
        s = float(np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2.0)
        w = float((rotation[1, 0] - rotation[0, 1]) / s)
        x = float((rotation[0, 2] + rotation[2, 0]) / s)
        y = float((rotation[1, 2] + rotation[2, 1]) / s)
        z = 0.25 * s
    return (
        [float(value) for value in converted[:3, 3]],
        [x, y, z, w],
        [float(value) for value in scale],
    )


def _field_to_numpy(value: object, *, reason: str) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return np.asarray(value)
    from visualization.readback_probe import explicit_to_numpy

    return np.asarray(explicit_to_numpy(value, reason=reason))


def read_rigid_provider_arrays(provider: object) -> tuple[np.ndarray, np.ndarray]:
    """Read a typed rigid provider into world-major host arrays.

    The source contract remains authoritative: positions are ``(W,L,3)`` or
    ``(W*L,3)`` and orientations are WXYZ.  This helper is outside the
    simulation loop and is therefore the explicit host readback boundary.
    """

    from visualization.rigid_transform_provider import (
        validate_rigid_render_transform_provider,
    )

    provider = validate_rigid_render_transform_provider(provider)
    schema = provider.schema
    state = provider.state
    positions = _field_to_numpy(state.positions, reason="task_env.flora.positions")
    orientations = _field_to_numpy(
        state.orientations,
        reason="task_env.flora.orientations",
    )
    if state.slot_indexed:
        slot = int(
            _field_to_numpy(
                state.snapshot_read_slot,
                reason="task_env.flora.snapshot_read_slot",
            ).reshape(-1)[0]
        )
        positions = positions[slot]
        orientations = orientations[slot]
    elif state.world_major:
        positions = positions.reshape(schema.world_count, schema.local_capacity, 3)
        orientations = orientations.reshape(schema.world_count, schema.local_capacity, 4)
    else:
        positions = positions.reshape(1, schema.capacity, 3)
        orientations = orientations.reshape(1, schema.capacity, 4)
    count = int(schema.body_count)
    positions = np.ascontiguousarray(positions.reshape(-1, 3)[:count], dtype=np.float32)
    orientations = np.ascontiguousarray(orientations.reshape(-1, 4)[:count], dtype=np.float32)
    if positions.shape != (count, 3) or orientations.shape != (count, 4):
        raise ValueError(
            "rigid provider readback has incompatible shapes: "
            f"positions={positions.shape}, orientations={orientations.shape}, count={count}"
        )
    if not np.isfinite(positions).all() or not np.isfinite(orientations).all():
        raise ValueError("rigid provider readback contains non-finite values")
    return positions, orientations


__all__ = [
    "geophys_to_flora_matrix",
    "geophys_to_flora_points",
    "matrix_to_flora_scene_fields",
    "pose_matrix",
    "read_rigid_provider_arrays",
    "wxyz_to_matrix",
]
