"""Explicit free-body velocity conversion at the RuntimeSession adapter seam.

This module is provider-free. Provider adapters must name the frame and point
used by public velocity readback before handing data to the canonical state
projection. It does not inspect provider-private solver/view state.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...artifacts import FrameReference
from ...artifacts.contracts import Contract


def _vector3(value, name):
    if type(value) not in (tuple, list) or len(value) != 3:
        raise TypeError(f'{name} must be a three-component tuple/list')
    if any(type(item) not in (int, float) or not math.isfinite(float(item)) for item in value):
        raise ValueError(f'{name} must contain finite non-boolean numbers')
    return np.asarray(tuple(float(item) for item in value), dtype=np.float64)


def _quaternion_wxyz(value):
    if type(value) not in (tuple, list) or len(value) != 4:
        raise TypeError('orientation_world_from_body_wxyz must have four components')
    if any(type(item) not in (int, float) or not math.isfinite(float(item)) for item in value):
        raise ValueError('orientation_world_from_body_wxyz must be finite non-boolean numbers')
    q = np.asarray(tuple(float(item) for item in value), dtype=np.float64)
    norm = float(np.linalg.norm(q))
    if norm < 1e-12 or not math.isfinite(norm):
        raise ValueError('orientation quaternion is invalid')
    if abs(float(q @ q) - 1.0) > 1.0e-6:
        raise ValueError('orientation quaternion must be normalized')
    w, x, y, z = q / norm
    return np.asarray((
        (1.0 - 2.0 * (y*y + z*z), 2.0 * (x*y - z*w), 2.0 * (x*z + y*w)),
        (2.0 * (x*y + z*w), 1.0 - 2.0 * (x*x + z*z), 2.0 * (y*z - x*w)),
        (2.0 * (x*z - y*w), 2.0 * (y*z + x*w), 1.0 - 2.0 * (x*x + y*y)),
    ), dtype=np.float64)


@dataclass(frozen=True)
class PublicRigidBodyReadbackV1(Contract):
    """Public rigid-body pose and world-frame twist measured at its COM."""

    schema_version: str
    body_frame: FrameReference
    position_world_m: tuple[float, float, float]
    orientation_world_from_body_wxyz: tuple[float, float, float, float]
    com_offset_body_m: tuple[float, float, float]
    linear_velocity_world_at_com_m_s: tuple[float, float, float]
    angular_velocity_world_rad_s: tuple[float, float, float]
    velocity_frame: str
    linear_reference_point: str

    def validate(self):
        if self.schema_version != 'public-rigid-body-readback-v1':
            raise ValueError('unsupported public rigid-body readback schema')
        if type(self.body_frame) is not FrameReference:
            raise TypeError('public rigid-body readback requires a typed body FrameReference')
        self.body_frame.validate()
        if self.velocity_frame != 'world':
            raise ValueError('public rigid-body velocity sample must explicitly use world frame')
        if self.linear_reference_point != 'center_of_mass':
            raise ValueError('public rigid-body linear velocity must explicitly name center_of_mass')
        _vector3(self.position_world_m, 'position_world_m')
        _quaternion_wxyz(self.orientation_world_from_body_wxyz)
        _vector3(self.com_offset_body_m, 'com_offset_body_m')
        _vector3(self.linear_velocity_world_at_com_m_s, 'linear_velocity_world_at_com_m_s')
        _vector3(self.angular_velocity_world_rad_s, 'angular_velocity_world_rad_s')


def world_com_twist_to_body_origin_local(
    *, position_world_m, orientation_world_from_body_wxyz, com_offset_body_m,
    linear_velocity_world_at_com_m_s, angular_velocity_world_rad_s,
    velocity_frame='world', linear_reference_point='center_of_mass',
):
    """Convert a world-frame COM twist to body-origin components in body axes."""
    if velocity_frame != 'world':
        raise ValueError('velocity_frame must be world')
    if linear_reference_point != 'center_of_mass':
        raise ValueError('linear_reference_point must be center_of_mass')
    _vector3(position_world_m, 'position_world_m')
    rotation = _quaternion_wxyz(orientation_world_from_body_wxyz)
    offset_world = rotation @ _vector3(com_offset_body_m, 'com_offset_body_m')
    linear_com_world = _vector3(linear_velocity_world_at_com_m_s, 'linear_velocity_world_at_com_m_s')
    angular_world = _vector3(angular_velocity_world_rad_s, 'angular_velocity_world_rad_s')
    # v_COM = v_origin + omega × (p_COM - p_origin).
    linear_origin_world = linear_com_world - np.cross(angular_world, offset_world)
    return (
        tuple(float(item) for item in rotation.T @ linear_origin_world),
        tuple(float(item) for item in rotation.T @ angular_world),
    )


def body_origin_local_twist_to_world_com(
    *, position_world_m, orientation_world_from_body_wxyz, com_offset_body_m,
    linear_velocity_body_origin_local_m_s, angular_velocity_body_local_rad_s,
    target_frame='world', target_reference_point='center_of_mass',
):
    """Inverse of :func:`world_com_twist_to_body_origin_local` for a named COM."""
    if target_frame != 'world':
        raise ValueError('target_frame must be world')
    if target_reference_point != 'center_of_mass':
        raise ValueError('target_reference_point must be center_of_mass')
    _vector3(position_world_m, 'position_world_m')
    rotation = _quaternion_wxyz(orientation_world_from_body_wxyz)
    offset_world = rotation @ _vector3(com_offset_body_m, 'com_offset_body_m')
    linear_origin_local = _vector3(
        linear_velocity_body_origin_local_m_s, 'linear_velocity_body_origin_local_m_s',
    )
    angular_local = _vector3(angular_velocity_body_local_rad_s, 'angular_velocity_body_local_rad_s')
    angular_world = rotation @ angular_local
    linear_origin_world = rotation @ linear_origin_local
    linear_com_world = linear_origin_world + np.cross(angular_world, offset_world)
    return tuple(float(item) for item in linear_com_world), tuple(float(item) for item in angular_world)


__all__ = [
    'PublicRigidBodyReadbackV1',
    'world_com_twist_to_body_origin_local',
    'body_origin_local_twist_to_world_com',
]
