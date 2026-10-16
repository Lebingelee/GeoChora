"""Task-owned square-nut orientation helpers shared by versioned solutions."""
import numpy as np

from ...utils.rotation import normalize_quat_wxyz


def square_yaw_correction(quaternion_wxyz: np.ndarray) -> float:
    """Return the shortest yaw correction modulo the square nut's 90° symmetry."""
    w, x, y, z = normalize_quat_wxyz(quaternion_wxyz)
    yaw = float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))
    period = 0.5 * np.pi
    return -float((yaw + 0.5 * period) % period - 0.5 * period)


__all__ = ["square_yaw_correction"]
