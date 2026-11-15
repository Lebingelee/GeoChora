"""Run the registered Pendulum task with a selected CUDA batch provider."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from task_env import make_parallel_env


def run(interpreter, *, output=None, seed=73, steps=20, provider='mujoco_warp', num_env=3, window=False):
    if steps < 1 or num_env < 1:
        raise ValueError('steps and num_env must be positive')
    execution = {'physics_provider': provider}
    if interpreter is not None:
        execution['interpreter'] = interpreter
    config = {'execution': execution,
              'episode': {'seed': seed, 'horizon': steps}}
    directory = None if output is None else str(Path(output).resolve().parent)
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=num_env, backend='cuda',
                            execution='device', render_mode='human' if window else None,
                            worker_directory=directory)
    try:
        observation, _ = env.reset(seed=seed)
        actions = {'torque': torch.linspace(-1.5, 1.5, num_env, device='cuda').reshape(-1, 1)}
        for _ in range(steps):
            observation, reward, terminated, truncated, info = env.step(actions)
            if window:
                env.render()
        state = env.read_device_state(('qpos', 'qvel'))
        result = {'task': 'pendulum-v1', 'provider': provider, 'num_envs': env.num_envs,
                  'steps': steps, 'seed': seed, 'device': str(reward.device),
                  'observation_shape': list(observation['state']['proprioception'].shape),
                  'reward': reward.cpu().tolist(), 'terminated': terminated.cpu().tolist(),
                  'truncated': truncated.cpu().tolist(), 'episode_id': info['episode_id'].cpu().tolist(),
                  'final_observation_mask': info['_final_observation'].cpu().tolist(),
                  'native_step': state.identity.native_step, 'native_time_s': state.identity.native_time_s}
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
    parser.add_argument('--num-env', type=int, default=3)
    parser.add_argument('--window', action='store_true')
    parser.add_argument('--output')
    parser.add_argument('--seed', type=int, default=73)
    parser.add_argument('--steps', type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(run(args.interpreter, output=args.output, seed=args.seed, steps=args.steps,
                         provider=args.provider, num_env=args.num_env, window=args.window)))


if __name__ == '__main__':
    main()
