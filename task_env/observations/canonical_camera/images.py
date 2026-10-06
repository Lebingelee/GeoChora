"""Strict provider-independent image normalization and canonical observation."""
from dataclasses import dataclass
import numpy as np
from .contracts import ResolvedCameraMetadata


def normalize_rgb(native, camera):
    values = np.asarray(native)
    if values.shape != (camera.height,camera.width,3):
        raise ValueError('native RGB must be HWC with declared resolution')
    if values.dtype == np.uint8:
        values = values.astype(np.float32)/np.float32(255)
    elif values.dtype == np.float32:
        if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
            raise ValueError('native float32 RGB outside [0,1]')
    else:
        raise ValueError('native RGB must be float32 or uint8')
    if camera.rgb_dtype == 'uint8':
        values = np.rint(values*255).astype(np.uint8)
    if camera.rgb_layout == 'CHW':
        values = values.transpose(2,0,1)
    return np.ascontiguousarray(values)


@dataclass(frozen=True)
class CanonicalCameraObservation:
    rgb: np.ndarray | None
    depth: np.ndarray | None
    metadata: ResolvedCameraMetadata

    def __post_init__(self):
        c = self.metadata.camera
        if c.rgb != (self.rgb is not None) or c.depth != (self.depth is not None):
            raise ValueError('requested modalities not honored')
        for name in ('rgb','depth'):
            values = getattr(self,name)
            if values is None:
                continue
            values = np.array(values,copy=True)
            if not np.isfinite(values).all():
                raise ValueError('non-finite image')
            if name == 'rgb':
                shape = (c.height,c.width,3) if c.rgb_layout == 'HWC' else (3,c.height,c.width)
                if values.shape != shape or values.dtype != np.dtype(c.rgb_dtype) or values.min() < 0 or values.max() > (1 if c.rgb_dtype == 'float32' else 255):
                    raise ValueError('RGB schema mismatch')
            elif values.shape != (c.height,c.width) or values.dtype != np.float32 or np.any(values < 0):
                raise ValueError('depth schema mismatch')
            values.setflags(write=False)
            object.__setattr__(self,name,values)
