"""Explicit transfer conversion for native framebuffer values."""
from __future__ import annotations

import numpy as np


def rgb_to_uint8(frame):
    """Export a normalized host RGB frame for the Gymnasium render boundary."""
    return np.array(np.rint(np.clip(frame, 0, 1) * 255), dtype=np.uint8,
                    order='C', copy=True)


def gamma22_to_srgb(native):
    """Convert bounded gamma-2.2 encoded RGB to the standard sRGB transfer.

    This converts the transfer curve only. It does not establish input asset
    color spaces, display calibration, or the renderer's color primaries.
    """
    value = np.asarray(native)
    if (value.dtype != np.float32 or value.ndim != 3 or value.shape[-1] != 3
            or not np.isfinite(value).all() or np.any(value < 0) or np.any(value > 1)):
        raise ValueError('gamma-2.2 RGB must be finite HWC float32 in [0, 1]')
    linear = np.power(value, np.float32(2.2))
    encoded = np.where(linear <= np.float32(.0031308),
                       np.float32(12.92) * linear,
                       np.float32(1.055) * np.power(linear, np.float32(1.0 / 2.4))
                       - np.float32(.055))
    return np.ascontiguousarray(np.clip(encoded, 0., 1.), dtype=np.float32)
