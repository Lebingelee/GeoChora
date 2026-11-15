"""Run the registered Pendulum task as a three-world CUDA batch.

Use a Python 3.12 interpreter with the documented MJWarp dependency profile.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from task_env import make_parallel_env


def run(interpreter, *, output=None, seed=73, steps=20):
    if steps < 1:
        raise ValueError('steps must be positive')
    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': interpreter},
              'episode': {'seed': seed, 'horizon': steps}}
    directory = None if output is None else str(Path(output).resolve().parent)
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', worker_directory=directory)
    try:
        observation, _ = env.reset(seed=seed)
        actions = {'torque': torch.tensor([[-1.5], [0.5], [1.5]], device='cuda', dtype=torch.float32)}
        for _ in range(steps):
            observation, reward, terminated, truncated, info = env.step(actions)
        state = env.read_device_state(('qpos', 'qvel'))
        result = {'task': 'pendulum-v1', 'provider': 'mujoco_warp', 'num_envs': env.num_envs,
                  'steps': steps, 'seed': seed, 'device': str(reward.device),
                  'observation_shape': list(observation['state']['proprioception'].shape),
                  'reward': reward.cpu().tolist(), 'terminated': terminated.cpu().tolist(),
                  'truncated': truncated.cpu().tolist(), 'episode_id': info['episode_id'].cpu().tolist(),
                  'native_step': state.identity.native_step, 'native_time_s': state.identity.native_time_s}
    finally:
        env.close()
    result['closed'] = True
    if output is not None:
        Path(output).write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interpreter', required=True)
    parser.add_argument('--output')
    parser.add_argument('--seed', type=int, default=73)
    parser.add_argument('--steps', type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(run(args.interpreter, output=args.output, seed=args.seed, steps=args.steps)))


if __name__ == '__main__':
    main()
