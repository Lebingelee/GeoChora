"""Regression tests for the shared Production R3 joint-rate limiter."""

import numpy as np

from task_env.controllers.canonical.production_r3 import (
    _limit_joint_velocity_direction_preserving,
)


def test_saturated_joint_rate_limit_preserves_joint_velocity_direction():
    raw = np.asarray([8.0, 4.0, -2.0])

    limited = _limit_joint_velocity_direction_preserving(raw, 4.0)

    # Independent explicit oracle: uniform scale 1/2. Component clipping would
    # yield [4, 4, -2] and change the resolved-rate direction.
    np.testing.assert_allclose(limited, [4.0, 2.0, -1.0], rtol=0.0, atol=1e-12)
    assert np.max(np.abs(limited)) <= 4.0
    np.testing.assert_allclose(limited / 4.0, raw / 8.0, rtol=0.0, atol=1e-12)


def test_unsaturated_and_zero_joint_velocity_vectors_are_unchanged():
    raw = np.asarray([0.5, -1.0, 0.25])

    np.testing.assert_array_equal(
        _limit_joint_velocity_direction_preserving(raw, 4.0), raw,
    )
    np.testing.assert_array_equal(
        _limit_joint_velocity_direction_preserving(np.zeros(3), 4.0), np.zeros(3),
    )
