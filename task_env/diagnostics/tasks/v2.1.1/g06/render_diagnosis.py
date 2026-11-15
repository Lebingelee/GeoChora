"""Frozen public-pose setup for diagnosing the batch rasterizer."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from pathlib import Path

import numpy as np
import torch


def capture_snapshot(worker_python, *, count, steps=20):
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 2000},
              'render': {'width': 640, 'height': 480}}
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=count,
                            backend='cuda', execution='device', worker_directory=os.getcwd())
    try:
        env.reset(seed=31)
        action = torch.zeros((count, *env.single_action_space['effort'].shape), device='cuda')
        action[:, 0] = torch.linspace(-5., 5., count, device='cuda')
        action[:, -1] = torch.linspace(-4., 4., count, device='cuda')
        series = []
        for tick in range(steps):
            env.step({'effort': action})
            state = env.read_device_state(('body_position', 'body_orientation'))
            series.append({name: value.cpu().numpy() for name, value in state.arrays.items()})
            print(f'completed snapshot {tick + 1}/{steps}', flush=True)
        summary = env.resource_summary()['device_transition']
        names = ('qpos', 'qvel', 'body_position', 'body_orientation')
        state = env.read_device_state(names)
        np.savez_compressed('public-pose.npz', **{name: value.cpu().numpy() for name, value in state.arrays.items()})
        np.savez_compressed('public-pose-series.npz', **{
            name: np.stack([boundary[name] for boundary in series]) for name in ('body_position', 'body_orientation')})
        metadata = {'configuration': config, 'batch': count, 'identity': asdict(state.identity),
                    'body_names': list(summary['body_names']), 'frame_names': list(summary['frame_names']),
                    'snapshot': 'public-pose.npz', 'series': 'public-pose-series.npz', 'physics_intervals': steps,
                    'rendering_during_capture': False}
        Path('public-pose.json').write_text(json.dumps(metadata, indent=2) + '\n')
        return metadata
    finally:
        env.close()


def render_snapshot(worker_python, snapshot_dir, *, sequence, camera_config, count, iterations):
    """Render a retained public snapshot without a physics worker or IPC."""
    import faulthandler
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.render.providers.parallel import ParallelRenderProvider
    from task_env.render.rasterizer.device import DeviceBatchRasterSource
    from task_env.runtime.contracts import DeviceBatchState, DeviceStateIdentity
    from task_env.runtime.sessions.source import close_source_and_task_resources
    from visualization.rasterizer.scene_visualizer import RasterSceneVisualizer

    snapshot_dir = Path(snapshot_dir).resolve(strict=True)
    metadata = json.loads((snapshot_dir / 'public-pose.json').read_text())
    if count not in (3, 16) or count > metadata['batch']:
        raise ValueError('render snapshot diagnostic accepts B=3 or B=16')
    with np.load(snapshot_dir / metadata['snapshot']) as arrays:
        fields = {name: torch.as_tensor(arrays[name][:count].copy(), device='cuda') for name in arrays.files}
    state = DeviceBatchState(fields, 'cuda:0', count, DeviceStateIdentity(**metadata['identity']), 'owned_snapshot')
    series_path = snapshot_dir / metadata.get('series', 'missing')
    series = None
    if series_path.exists():
        with np.load(series_path) as arrays:
            series = {name: arrays[name][:, :count].copy() for name in arrays.files}

    class FrozenRuntime:
        current = state
        def read_device_state(self, fields):
            return DeviceBatchState({name: self.current.arrays[name] for name in fields}, 'cuda:0',
                                    count, self.current.identity, 'owned_snapshot')
        def resource_summary(self):
            return {'device_transition': {'body_names': metadata['body_names'],
                                           'frame_names': metadata['frame_names']}}

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 2000},
              'render': {**camera_config, 'width': 640, 'height': 480}}
    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    resolved = resolve_task_env_config(task, config, execution_scope='device_batch')
    binding = task._build_selected_binding(resolved)
    built = binding.build_for_request('mujoco_warp', 'cuda', 31, 2000)
    source = built['source']
    if source.source_closure_digest != state.identity.source_closure_sha256:
        raise ValueError('render source differs from retained public state')
    runtime = FrozenRuntime()
    raster = DeviceBatchRasterSource(runtime=runtime, source=source,
        body_names=metadata['body_names'], frame_names=metadata['frame_names'],
        cameras=resolved.environment.render.cameras)
    provider = ParallelRenderProvider(num_envs=count, render_source=raster, width=640, height=480)
    provider.enable_device_cameras()
    original_capture = RasterSceneVisualizer.write_task_camera_rgb8
    def traced_capture(visualizer, destination, *, camera_id=None):
        original_capture(visualizer, destination, camera_id=camera_id)
        print(f'completed render camera {camera_id}', flush=True)
    RasterSceneVisualizer.write_task_camera_rgb8 = traced_capture
    faulthandler.dump_traceback_later(45, repeat=True)
    results = []
    try:
        for tick in range(iterations):
            if series is not None and len(series['body_position']) > 20:
                if tick >= len(series['body_position']):
                    raise ValueError('render replay exceeds frozen pose series')
                fields = {**state.arrays, **{name: torch.as_tensor(value[tick], device='cuda')
                                              for name, value in series.items()}}
                remaining = metadata['physics_intervals'] - tick - 1
                substeps = metadata['identity']['native_step'] // metadata['physics_intervals']
                identity = replace(DeviceStateIdentity(**metadata['identity']),
                    revision=metadata['identity']['revision'] - remaining,
                    native_step=metadata['identity']['native_step'] - substeps * remaining,
                    native_time_s=metadata['identity']['native_time_s'] - metadata['identity']['control_dt_s'] * remaining)
                state = DeviceBatchState(fields, 'cuda:0', count, identity, 'owned_snapshot')
                runtime.current = state
            if sequence in ('sensor', 'mixed', 'mixed-present'):
                print(f'begin sensor {tick}', flush=True)
                frames = provider.capture_cameras(state=state)
                if any(tuple(frames[name]['rgb'].shape) != (count, 128, 128, 3)
                       for name in ('base', 'hand')):
                    raise AssertionError('sensor output shape differs')
                print(f'completed render sensor {tick}', flush=True)
            if sequence in ('observer', 'mixed', 'mixed-present'):
                print(f'begin observer {tick}', flush=True)
                if sequence == 'mixed-present':
                    provider.render(mode='human')
                else:
                    frame = provider.render(mode='rgb_array')
                    if tuple(frame.shape) != (480, 640, 3) or frame.dtype != torch.uint8:
                        raise AssertionError('observer output shape differs')
                print(f'completed render observer {tick}', flush=True)
            results.append(tick)
        return {'scope': 'frozen public poses; renderer only, no physics or IPC',
                'batch': count, 'sequence': sequence, 'iterations': results,
                'poses': 'frozen sequence' if series is not None and len(series['body_position']) > 20 else 'fixed snapshot',
                'identity': asdict(state.identity), 'source_closure_sha256': source.source_closure_digest,
                'observer': [640, 480], 'sensors': [128, 128], 'present': sequence == 'mixed-present'}
    finally:
        faulthandler.cancel_dump_traceback_later()
        RasterSceneVisualizer.write_task_camera_rgb8 = original_capture
        raster.close()
        error = close_source_and_task_resources(source, binding)
        if error is not None:
            raise error


def live_pipeline(worker_python, *, camera_config, count, steps):
    """Exercise actual public step/camera/present ordering with progress marks."""
    import faulthandler
    import math
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 2000},
              'render': {**camera_config, 'width': 640, 'height': 480,
                         'parallel': {'columns': math.ceil(math.sqrt(count))}}}
    faulthandler.dump_traceback_later(45, repeat=True)
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=count,
                            backend='cuda', execution='device', render_mode='human',
                            worker_directory=os.getcwd())
    try:
        observation, _ = env.reset(seed=31)
        env.set_parallel_render_num(count)
        action = torch.zeros((count, *env.single_action_space['effort'].shape), device='cuda')
        action[:, 0] = torch.linspace(-5., 5., count, device='cuda')
        action[:, -1] = torch.linspace(-4., 4., count, device='cuda')
        print('completed render reset', flush=True)
        for tick in range(steps):
            print(f'begin step {tick}', flush=True)
            observation, _, terminated, truncated, _ = env.step({'effort': action})
            if tick >= 20:
                torch.cuda.synchronize()
            print(f'completed render step {tick}', flush=True)
            print(f'begin observer {tick}', flush=True)
            env.render()
            if tick >= 20:
                torch.cuda.synchronize()
            print(f'completed render observer {tick}', flush=True)
            if tick == 19:
                before = env.read_device_state(('qpos',)).identity
                frame = env.render(mode='rgb_array')
                if tuple(frame.shape) != (480, 640, 3):
                    raise AssertionError('warmup observer size differs')
                env.render(mode='human')
                if env.read_device_state(('qpos',)).identity != before:
                    raise AssertionError('warmup observer changed physics identity')
                print('completed render warmup-witness', flush=True)
        env.close_render()
        env.close_render()
        if bool(terminated.any() or truncated.any()):
            raise AssertionError('final measured step terminated')
        observation, _, _, _, _ = env.step({'effort': action})
        if any(tuple(observation['cameras'][name]['rgb'].shape) != (count, 128, 128, 3)
               for name in ('base', 'hand')):
            raise AssertionError('sensor output failed after window close')
        print('completed render close-and-sensor', flush=True)
        return {'scope': 'public MJWarp step, two sensors and Rasterizer presentation',
                'batch': count, 'steps': steps, 'observer': [640, 480],
                'sensors': [128, 128], 'close_twice_then_sensor': True}
    finally:
        faulthandler.cancel_dump_traceback_later()
        env.close()


def nondefault_stream(worker_python, *, camera_config):
    """Check device images and state boundaries on a nondefault Torch stream."""
    import faulthandler
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 20},
              'render': {**camera_config, 'width': 640, 'height': 480}}
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=3,
                            backend='cuda', execution='device', render_mode='human',
                            worker_directory=os.getcwd())
    stream = torch.cuda.Stream()
    faulthandler.dump_traceback_later(45, repeat=True)
    try:
        with torch.cuda.stream(stream):
            obs, _ = env.reset(seed=31)
            print('completed render nondefault-reset', flush=True)
            action = torch.zeros((3, *env.single_action_space['effort'].shape), device='cuda')
            action[:, 0] = torch.tensor([5., 0., -5.], device='cuda')
            for _ in range(5):
                obs, _, _, _, _ = env.step({'effort': action})
                print('completed render nondefault-step', flush=True)
            before = env.read_device_state(('qpos',)).identity
            frame = env.render(mode='rgb_array')
            stream.synchronize()
        default_frame = env.render(mode='rgb_array')
        print('completed render nondefault-frame', flush=True)
        if not torch.equal(frame, default_frame) or env.read_device_state(('qpos',)).identity != before:
            raise AssertionError('cross-stream same-boundary render differs')
        if any(tuple(obs['cameras'][name]['rgb'].shape) != (3, 128, 128, 3)
               or obs['cameras'][name]['rgb'].dtype != torch.uint8 for name in ('base', 'hand')):
            raise AssertionError('nondefault-stream camera output differs')
        env.render(mode='human')
        env.close_render()
        env.close_render()
        with torch.cuda.stream(stream):
            obs, _, _, _, _ = env.step({'effort': action})
            stream.synchronize()
        if any(obs['cameras'][name]['rgb'].device.type != 'cuda' for name in ('base', 'hand')):
            raise AssertionError('nondefault-stream sensors failed after window close')
        return {'scope': 'public MJWarp PickCube B3, nondefault stream, same-boundary frame and sensors',
                'observer_shape': list(frame.shape), 'sensor_shape': [3, 128, 128, 3],
                'same_boundary_frames_equal': True, 'close_twice_then_sensor': True}
    finally:
        faulthandler.cancel_dump_traceback_later()
        env.close()
