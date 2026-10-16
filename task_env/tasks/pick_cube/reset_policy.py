"""PickCube reset distribution constants shared by both current adapters."""
import numpy as np


# Keep float32 construction identical to the historical ResetSampler metadata
# and PCG64-v0 distribution.
TABLE_CENTER_XY = np.asarray((0.5545, 0.0), dtype=np.float32)
RESET_HALF_EXTENT_M = 0.10


__all__ = ["RESET_HALF_EXTENT_M", "TABLE_CENTER_XY"]
