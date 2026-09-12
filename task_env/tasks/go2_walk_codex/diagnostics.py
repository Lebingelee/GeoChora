"""Scalar Go2 Codex diagnostics for host-side evaluation and recorders."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..go2_walk.task import _quat_rotate_inverse


def _batch_array(value: Any, *, name: str, width: int | None = None) -> np.ndarray:
    result = np.asarray(value, dtype=np.float32)
    if result.ndim == 1:
        result = result[None, :]
    if result.ndim != 2:
        raise ValueError(f"{name} must have shape (B, D), got {result.shape}")
    if width is not None and result.shape[1] != width:
        raise ValueError(f"{name} must have width {width}, got {result.shape[1]}")
    return result


def scalar_diagnostics(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    commands: np.ndarray,
    body_xquat: np.ndarray | None = None,
    body_xpos: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Compute finite scalar metrics without exposing batched tensor fields."""

    qpos_value = _batch_array(qpos, name="qpos")
    qvel_value = _batch_array(qvel, name="qvel")
    command_value = _batch_array(commands, name="commands", width=4)
    if qpos_value.shape[0] != qvel_value.shape[0] or qpos_value.shape[0] != command_value.shape[0]:
        raise ValueError("qpos, qvel, and commands must have the same batch size")
    if body_xquat is None:
        root_quat = qpos_value[:, 3:7]
    else:
        quat_value = np.asarray(body_xquat, dtype=np.float32)
        if quat_value.ndim == 3:
            root_quat = quat_value[:, 0]
        elif quat_value.ndim == 2 and quat_value.shape == (qpos_value.shape[0], 4):
            root_quat = quat_value
        elif quat_value.ndim == 2 and qpos_value.shape[0] == 1 and quat_value.shape[1] == 4:
            root_quat = quat_value[0][None, :]
        else:
            raise ValueError(f"body_xquat must contain a base quaternion, got {quat_value.shape}")
    gravity = np.zeros_like(qvel_value[:, :3])
    gravity[:, 2] = -1.0
    lin = _quat_rotate_inverse(root_quat, qvel_value[:, :3])
    projected = _quat_rotate_inverse(root_quat, gravity)
    w, x, y, z = [root_quat[:, index] for index in range(4)]
    roll = np.arctan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2.0 * (w * y - z * x), -1.0, 1.0))
    if body_xpos is None:
        base_height = qpos_value[:, 2]
    else:
        position_value = np.asarray(body_xpos, dtype=np.float32)
        if position_value.ndim == 3 and position_value.shape[0] == qpos_value.shape[0]:
            base_height = position_value[:, 0, 2]
        elif position_value.ndim == 2 and qpos_value.shape[0] == 1 and position_value.shape[1] == 3:
            base_height = position_value[0, 2][None]
        else:
            raise ValueError(f"body_xpos must have shape (B, bodies, 3), got {position_value.shape}")
    height_error = base_height - command_value[:, 3]
    values = {
        "command_velocity_x": command_value[:, 0],
        "forward_velocity": lin[:, 0],
        "velocity_error_x": command_value[:, 0] - lin[:, 0],
        "command_velocity_y": command_value[:, 1],
        "lateral_velocity": lin[:, 1],
        "velocity_error_y": command_value[:, 1] - lin[:, 1],
        "abs_vz": np.abs(lin[:, 2]),
        "base_height": base_height,
        "base_height_error": height_error,
        "projected_gravity_x": projected[:, 0],
        "projected_gravity_y": projected[:, 1],
        "projected_gravity_xy_norm": np.linalg.norm(projected[:, :2], axis=1),
        "roll_abs": np.abs(roll),
        "pitch_abs": np.abs(pitch),
    }
    for name, value in values.items():
        if not np.isfinite(value).all():
            raise ValueError(f"Go2 Codex diagnostic {name} contains non-finite values")
    return {name: np.asarray(value, dtype=np.float32) for name, value in values.items()}


__all__ = ["scalar_diagnostics"]
