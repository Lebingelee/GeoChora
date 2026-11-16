"""Switch one CUDA batch Isaac -> MuJoCo Warp -> Isaac with public reset.

Supply the Python interpreter for each provider's existing environment.  The
same environment object is used for all three episodes.
"""
from __future__ import annotations

import argparse
import math

import torch

from task_env import make_parallel_env


def run(task, isaac_interpreter, mujoco_interpreter, *, window=False):
    uid = {'pendulum': 'pendulum-v1',
           'pick-cube': 'pick-cube-p16-reference-v1'}[task]
    config = {'execution': {'physics_provider': 'isaacsim',
                            'interpreter': isaac_interpreter},
              'episode': {'seed': 31, 'horizon': 64}}
    if task == 'pick-cube':
        config.update({
            'controller': {'profile_id': 'panda-direct-effort-v1'},
            'robot': {'native_drive': 'disabled'},
            'render': {'backend': 'rasterizer', 'camera_obs': True, 'cameras': [
                {'name': 'base', 'frame': 'body', 'parent': 'panda-v1/link0',
                 'width': 128, 'height': 128, 'rgb_dtype': 'uint8',
                 'position': [-.35, -.4, .8],
                 'quaternion_wxyz': [math.cos(.45/2)*math.cos(.30/2),
                                     -math.sin(.45/2)*math.sin(.30/2),
                                     math.cos(.45/2)*math.sin(.30/2),
                                     math.sin(.45/2)*math.cos(.30/2)],
                 'near': .01, 'far': 3.},
                {'name': 'hand', 'frame': 'body', 'parent': 'panda-v1/hand',
                 'width': 128, 'height': 128, 'rgb_dtype': 'uint8',
                 'position': [.075, 0., -.15],
                 'quaternion_wxyz': [math.sqrt(.5), 0., -math.sqrt(.5), 0.],
                 'near': .01, 'far': 3.}]},
        })
    env = make_parallel_env(uid, env_config=config, num_env=3, backend='cuda',
                            execution='device', render_mode='human' if window else None)
    try:
        for index, (provider, interpreter) in enumerate((
            ('isaacsim', isaac_interpreter), ('mujoco_warp', mujoco_interpreter),
            ('isaacsim', isaac_interpreter),
        )):
            options = None if index == 0 else {'execution': {
                'physics_provider': provider, 'interpreter': interpreter}}
            observation, info = env.reset(seed=31 if index == 0 else None, options=options)
            key = 'torque' if task == 'pendulum' else 'effort'
            shape = env.single_action_space[key].shape
            actions = torch.linspace(-.1, .1, 3, device='cuda').reshape(3, *([1] * len(shape)))
            actions = actions.expand(3, *shape).contiguous()
            for _ in range(3):
                observation, reward, terminated, truncated, info = env.step({key: actions})
                if window:
                    env.render()
            state = env.read_device_state(('qpos', 'qvel'))
            print(provider, 'generation', state.identity.generation,
                  'episodes', info['episode_id'].tolist(), 'native step', state.identity.native_step)
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', choices=('pendulum', 'pick-cube'), required=True)
    parser.add_argument('--isaac-interpreter', required=True)
    parser.add_argument('--mujoco-interpreter', required=True)
    parser.add_argument('--window', action='store_true')
    args = parser.parse_args()
    run(args.task, args.isaac_interpreter, args.mujoco_interpreter, window=args.window)


if __name__ == '__main__':
    main()
