"""Run the registered PickCube task with explicit device-batch options.

GeoPhys requires explicitly selecting discrete contact for this source. Its
verified scope and loaded-contact limitations are described in the current API.

For the verified GeoPhys configuration, from the repository root run::

    PYTHONPATH="$PWD:$PWD/GeoPhys/src" python examples/parallel/pick_cube_device.py --provider geophys \
        --geophys-contact-mode discrete --geophys-contact-iterations 32
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch

from task_env import make_parallel_env


def run(interpreter, *, provider='mujoco_warp', num_env=3, seed=31, steps=20,
        sensor=False, window=False, output=None, geophys_contact_mode='provider_default',
        geophys_contact_iterations=None):
    if num_env < 1 or steps < 1:
        raise ValueError('num_env and steps must be positive')
    execution = {'physics_provider': provider}
    if interpreter is not None:
        execution['interpreter'] = interpreter
    if geophys_contact_mode != 'provider_default':
        if provider != 'geophys':
            raise ValueError('GeoPhys contact mode requires the GeoPhys provider')
        execution['geophys_contact_mode'] = geophys_contact_mode
    config = {'execution': execution, 'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': seed, 'horizon': steps}}
    if geophys_contact_iterations is not None:
        if provider != 'geophys':
            raise ValueError('GeoPhys contact iterations require the GeoPhys provider')
        config['runtime'] = {'body_contact_solver_iterations': geophys_contact_iterations}
    if sensor:
        yaw, pitch = .45, .30
        cy, sy, cp, sp = (math.cos(yaw / 2), math.sin(yaw / 2),
                          math.cos(pitch / 2), math.sin(pitch / 2))
        config['render'] = {'backend': 'rasterizer', 'camera_obs': True, 'cameras': [
            {'name': 'base', 'frame': 'body', 'parent': 'panda-v1/link0',
             'width': 128, 'height': 128, 'rgb_dtype': 'uint8', 'position': [-.35, -.4, .8],
             'quaternion_wxyz': [cy * cp, -sy * sp, cy * sp, sy * cp], 'near': .01, 'far': 3.},
            {'name': 'hand', 'frame': 'body', 'parent': 'panda-v1/hand',
             'width': 128, 'height': 128, 'rgb_dtype': 'uint8', 'position': [.075, 0., -.15],
             'quaternion_wxyz': [math.sqrt(.5), 0., -math.sqrt(.5), 0.], 'near': .01, 'far': 3.}]}
    directory = None if output is None else str(Path(output).resolve().parent)
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config,
                            num_env=num_env, backend='cuda', execution='device',
                            render_mode='human' if window else None, worker_directory=directory)
    try:
        observation, _ = env.reset(seed=seed)
        shape = env.single_action_space['effort'].shape
        effort = torch.zeros((num_env, *shape), dtype=torch.float32, device='cuda')
        for _ in range(steps):
            observation, reward, terminated, truncated, info = env.step({'effort': effort})
        state = env.read_device_state(('qpos', 'qvel'))
        result = {'task': 'pick-cube-p16-reference-v1', 'provider': provider, 'num_envs': num_env,
                  'steps': steps, 'seed': seed, 'device': str(reward.device),
                  'state_fields': sorted(observation['state']),
                  'camera_shapes': {name: list(camera['rgb'].shape)
                                    for name, camera in observation.get('cameras', {}).items()},
                  'reward': reward.cpu().tolist(), 'terminated': terminated.cpu().tolist(),
                  'truncated': truncated.cpu().tolist(), 'episode_id': info['episode_id'].cpu().tolist(),
                  'native_step': state.identity.native_step}
        if provider == 'geophys':
            facts = env.resource_summary()['device_transition']['physical_layout_facts']
            result['contact_mode_requested'] = facts['contact_mode_requested']
            result['contact_mode_resolved'] = facts['contact_mode_resolved']
            result['solver_iterations_requested'] = facts['solver_iterations_requested']
            result['solver_iterations_resolved'] = facts['solver_iterations_resolved']
    finally:
        env.close()
    result['closed'] = True
    if output is not None:
        Path(output).write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interpreter')
    parser.add_argument('--provider', choices=('mujoco_warp', 'geophys', 'isaacsim'), default='mujoco_warp')
    parser.add_argument('--geophys-contact-mode', choices=('provider_default', 'discrete', 'continuous'),
                        default='provider_default')
    parser.add_argument('--geophys-contact-iterations', type=int)
    parser.add_argument('--num-env', type=int, default=3)
    parser.add_argument('--seed', type=int, default=31)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--sensor', action='store_true')
    parser.add_argument('--window', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    print(json.dumps(run(args.interpreter, provider=args.provider, num_env=args.num_env,
                         seed=args.seed, steps=args.steps, sensor=args.sensor,
                         window=args.window, output=args.output,
                         geophys_contact_mode=args.geophys_contact_mode,
                         geophys_contact_iterations=args.geophys_contact_iterations)))


if __name__ == '__main__':
    main()
