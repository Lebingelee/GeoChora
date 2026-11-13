"""Free-body velocity reference points: synthetic math, not provider qualification."""
import numpy as np
import pytest
from task_env.diagnostics.tasks.physical_contract_fixtures import _readback
from task_env.runtime.sessions.free_joint_state import (
    PublicRigidBodyReadbackV1, body_origin_local_twist_to_world_com,
    world_com_twist_to_body_origin_local,
)


def test_world_com_twist_conversion_roundtrips_nonidentity_pose_and_com_offset():
    value = _readback()
    value.validate()
    local_linear, local_angular = world_com_twist_to_body_origin_local(
        position_world_m=value.position_world_m,
        orientation_world_from_body_wxyz=value.orientation_world_from_body_wxyz,
        com_offset_body_m=value.com_offset_body_m,
        linear_velocity_world_at_com_m_s=value.linear_velocity_world_at_com_m_s,
        angular_velocity_world_rad_s=value.angular_velocity_world_rad_s,
        velocity_frame=value.velocity_frame,
        linear_reference_point=value.linear_reference_point,
    )
    world_linear, world_angular = body_origin_local_twist_to_world_com(
        position_world_m=value.position_world_m,
        orientation_world_from_body_wxyz=value.orientation_world_from_body_wxyz,
        com_offset_body_m=value.com_offset_body_m,
        linear_velocity_body_origin_local_m_s=local_linear,
        angular_velocity_body_local_rad_s=local_angular,
    )
    np.testing.assert_allclose(world_linear, value.linear_velocity_world_at_com_m_s, atol=1e-12)
    np.testing.assert_allclose(world_angular, value.angular_velocity_world_rad_s, atol=1e-12)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"velocity_frame": "body"}, "world frame"),
        ({"linear_reference_point": "body_origin"}, "center_of_mass"),
        ({"com_offset_body_m": (True, 0.0, 0.0)}, "finite number"),
        ({"linear_velocity_world_at_com_m_s": (0.0, float("nan"), 0.0)}, "finite"),
        ({"orientation_world_from_body_wxyz": (2.0, 0.0, 0.0, 0.0)}, "normalized"),
    ],
)
def test_public_velocity_sample_rejects_ambiguous_or_invalid_conventions(changes, message):
    payload = _readback().to_mapping()
    payload.update(changes)
    with pytest.raises((TypeError, ValueError), match=message):
        PublicRigidBodyReadbackV1.from_mapping(payload)


def test_com_velocity_oracle_uses_rotated_offset_and_world_angular_velocity():
    q = (float(np.sqrt(.5)), 0., 0., float(np.sqrt(.5)))
    linear, angular = body_origin_local_twist_to_world_com(
        position_world_m=(0., 0., 0.), orientation_world_from_body_wxyz=q,
        com_offset_body_m=(.1, -.2, .05),
        linear_velocity_body_origin_local_m_s=(2., -1., 3.),
        angular_velocity_body_local_rad_s=(0., 0., 2.))
    np.testing.assert_allclose(linear, (.8, 2.4, 3.), atol=1e-12)
    np.testing.assert_allclose(angular, (0., 0., 2.), atol=1e-12)
