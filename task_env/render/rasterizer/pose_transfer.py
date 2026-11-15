"""Synchronous device copy from batch pose tensors into renderer fields."""
import taichi as ti


@ti.kernel
def _copy_pose_fields(positions: ti.types.ndarray(dtype=ti.f32, ndim=2),
                      orientations: ti.types.ndarray(dtype=ti.f32, ndim=2),
                      target_positions: ti.template(), target_orientations: ti.template()):
    for index in range(positions.shape[0]):
        target_positions[index] = ti.Vector([positions[index, 0], positions[index, 1], positions[index, 2]])
        target_orientations[index] = ti.Vector([orientations[index, 0], orientations[index, 1],
                                                orientations[index, 2], orientations[index, 3]])


def copy_pose_fields(positions, orientations, target_positions, target_orientations):
    """Retire explicit CUDA DLPack leases on the caller after completion."""
    with ti.interop.from_dlpack(positions) as source_positions, \
            ti.interop.from_dlpack(orientations) as source_orientations:
        _copy_pose_fields(source_positions, source_orientations, target_positions, target_orientations)
        ti.sync()
