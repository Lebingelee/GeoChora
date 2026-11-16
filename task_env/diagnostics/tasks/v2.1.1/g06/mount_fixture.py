"""Resolve representative CameraSpec mounts from real scalar CUDA poses.

Called only by the g06 runner. This checks the public pose composition and
layout offset without claiming that a task-camera image was captured.
"""
from __future__ import annotations

import math


def prepare(body_names):
    import torch
    from task_env.assembly.references import SceneNameTable, TaskReferences
    from task_env.environment.config import CameraSpec
    from task_env.observations.camera import CameraSensor
    from task_env.render.providers.parallel import ParallelRenderLayout

    yaw, pitch = .45, .25
    cy, sy, cp, sp = math.cos(yaw / 2), math.sin(yaw / 2), math.cos(pitch / 2), math.sin(pitch / 2)
    specs = (
        CameraSpec(name='base', frame='body', parent='panda-v1/link0', width=128, height=128,
                   rgb_dtype='uint8', position=(-.35, -.4, .8),
                   quaternion_wxyz=(cy * cp, -sy * sp, cy * sp, sy * cp), near=.01, far=3.),
        CameraSpec(name='hand', frame='body', parent='panda-v1/hand', width=128, height=128,
                   rgb_dtype='uint8', position=(.04, 0., .08),
                   quaternion_wxyz=(math.sqrt(.5), 0., math.sqrt(.5), 0.), near=.01, far=3.),
    )
    names = SceneNameTable(bodies={name: index for index, name in enumerate(body_names)},
                           joints={}, sites={}, geoms={}, actuators={})
    references = TaskReferences(names, {}, {})
    sensors = tuple(CameraSensor(spec=spec, references=references) for spec in specs)
    offset = torch.tensor([[1.25, -.75, .2]], dtype=torch.float32, device='cuda')
    layout = ParallelRenderLayout(cell_width=1., cell_depth=1., columns=2, padding=.25)
    transforms = layout.transforms_for((0, 1, 2))
    grid_offsets = torch.tensor([[item[3], item[7], item[11]] for item in transforms],
                                dtype=torch.float32, device='cuda')
    return specs, sensors, offset, grid_offsets


def capture(sensors, offset, grid_offsets, state):
    import torch
    from task_env.runtime.contracts import DeviceBatchState

    torch.cuda.current_stream(device=state.device).synchronize()
    stream = torch.cuda.Stream()
    with torch.cuda.stream(stream):
        local = torch.stack([sensor.resolve_device_pose(state) for sensor in sensors])
        placed = torch.stack([sensor.resolve_device_pose(state, world_offsets=offset) for sensor in sensors])
        # Repeat one scalar pose only as renderer input. Physics remains B=1.
        repeated = DeviceBatchState({name: value.expand(3, *value.shape[1:]).clone()
                                     for name, value in state.arrays.items()},
                                    state.device, 3, state.identity, 'owned_snapshot')
        grid = torch.stack([sensor.resolve_device_pose(repeated, world_offsets=grid_offsets)
                            for sensor in sensors])
    stream.synchronize()
    if (str(local.device) != 'cuda:0' or local.dtype != torch.float32 or tuple(local.shape) != (2, 1, 3, 3)
            or not torch.allclose(placed[:, :, :2], local[:, :, :2] + offset[None, :, None, :])
            or not torch.equal(placed[:, :, 2], local[:, :, 2])):
        raise AssertionError('camera mount shape, device or single layout offset differs')
    directions = local[:, 0, 1] - local[:, 0, 0]
    if float(torch.linalg.vector_norm(directions[0] - directions[1]).item()) < .2:
        raise AssertionError('base and hand camera directions are not distinguishable')
    expected = local.expand(-1, 3, -1, -1).clone()
    expected[:, :, :2] += grid_offsets[None, :, None, :]
    if tuple(grid.shape) != (2, 3, 3, 3) or not torch.allclose(grid, expected, atol=2e-6, rtol=0.):
        raise AssertionError('B=3 camera layout order or offsets differ')
    return local, placed, grid


def save(specs, offset, grid_offsets, first, last, initial, final):
    import numpy as np
    import torch

    initial_local, initial_placed, initial_grid = initial
    final_local, final_placed, final_grid = final
    base_change = float(torch.max(torch.abs(final_local[0] - initial_local[0])).item())
    hand_change = float(torch.linalg.vector_norm(final_local[1, 0, 0] - initial_local[1, 0, 0]).item())
    if base_change > 1e-5 or hand_change < 1e-4:
        raise AssertionError(f'fixed base or moving hand mount differs: {base_change}, {hand_change}')
    np.savez('camera_mount_values.npz', initial_local=initial_local.cpu().numpy(),
             initial_placed=initial_placed.cpu().numpy(), final_local=final_local.cpu().numpy(),
             final_placed=final_placed.cpu().numpy(), offset=offset.cpu().numpy(),
             initial_grid=initial_grid.cpu().numpy(), final_grid=final_grid.cpu().numpy(),
             grid_offsets=grid_offsets.cpu().numpy(),
             initial_parent_position=first.arrays['body_position'].cpu().numpy(),
             initial_parent_quaternion=first.arrays['body_orientation'].cpu().numpy(),
             final_parent_position=last.arrays['body_position'].cpu().numpy(),
             final_parent_quaternion=last.arrays['body_orientation'].cpu().numpy(),
             spec_position=np.asarray([spec.position for spec in specs]),
             spec_quaternion=np.asarray([spec.quaternion_wxyz for spec in specs]))
    return {'camera_names': [spec.name for spec in specs], 'parents': [spec.parent for spec in specs],
            'shape': [2, 1, 3, 3], 'device': 'cuda:0', 'base_max_change': base_change,
            'hand_position_change_m': hand_change, 'layout_offset_m': offset[0].cpu().tolist(),
            'grid_shape': [2, 3, 3, 3], 'grid_scope': 'one scalar pose repeated for layout; not batch physics',
            'frame_capture': 'NOT_RUN; this probe resolves poses without capturing sensor frames'}
