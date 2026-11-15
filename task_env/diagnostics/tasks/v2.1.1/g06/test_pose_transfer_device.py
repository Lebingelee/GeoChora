"""Verify the renderer-owned pose copy and its external-storage lifetime."""
import numpy as np
import pytest
import weakref


def test_cuda_pose_copy_owns_no_automatically_adapted_torch_views(monkeypatch):
    import torch
    import taichi as ti
    from taichi_forge.interop import _dlpack
    from task_env.render.rasterizer.pose_transfer import copy_pose_fields

    if not torch.cuda.is_available():
        pytest.skip('CUDA is unavailable')
    ti.init(arch=ti.cuda, device_memory_GB=.5, offline_cache=False)
    try:
        adapted = []
        original = _dlpack._adapt_external_array

        def record(source, *args, **kwargs):
            if isinstance(source, torch.Tensor):
                adapted.append(source)
            return original(source, *args, **kwargs)

        monkeypatch.setattr(_dlpack, '_adapt_external_array', record)
        positions = ti.Vector.field(3, ti.f32, shape=3)
        orientations = ti.Vector.field(4, ti.f32, shape=3)
        expected_positions = np.array([[1., 2., 3.], [-1., 0., 1.], [4., 5., 6.]], np.float32)
        expected_orientations = np.array([[1., 0., 0., 0.], [0., 1., 0., 0.],
                                          [0., 0., 1., 0.]], np.float32)
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            source_positions = torch.as_tensor(expected_positions, device='cuda')
            source_orientations = torch.as_tensor(expected_orientations, device='cuda')
            # The caller establishes Torch-to-Taichi ordering before the copy.
            stream.synchronize()
            copy_pose_fields(source_positions, source_orientations, positions, orientations)
        np.testing.assert_array_equal(positions.to_numpy(), expected_positions)
        np.testing.assert_array_equal(orientations.to_numpy(), expected_orientations)
        assert not adapted, 'pose copy must explicitly retire Torch DLPack views'
        references = (weakref.ref(source_positions), weakref.ref(source_orientations))
        del source_positions, source_orientations
        assert all(reference() is None for reference in references), 'pose inputs outlived the completed copy'
    finally:
        ti.reset()
