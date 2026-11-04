"""Run one scalar classic-control transition through the public factory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from examples._common import bootstrap_imports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True, choices=('empty-v1', 'pendulum-v1', 'two-wheel-balance-v1'))
    parser.add_argument('--seed', type=int, default=73)
    args = parser.parse_args(argv)
    bootstrap_imports()
    import numpy as np
    from task_env import make_env

    def shape_and_dtype(value):
        if isinstance(value, dict):
            return {key: shape_and_dtype(item) for key, item in value.items()}
        array = np.asarray(value)
        return {'shape': list(array.shape), 'dtype': str(array.dtype)}

    env = None
    result = None
    try:
        env = make_env(args.uid, config={'runtime': {'backend': 'cpu', 'prewarm': False}})
        observation, info = env.reset(seed=args.seed)
        if not env.observation_space.contains(observation):
            raise ValueError('reset observation is outside observation_space')
        reset_observation = shape_and_dtype(observation)
        size = {'empty-v1': 0, 'pendulum-v1': 1, 'two-wheel-balance-v1': 2}[args.uid]
        action = np.zeros(size, dtype=np.float32)
        if size:
            action = {'torque': action}
        observation, reward, terminated, truncated, info = env.step(action)
        if not env.observation_space.contains(observation):
            raise ValueError('step observation is outside observation_space')
        result = {'uid': args.uid, 'seed': args.seed, 'transitions': 1,
                  'action': shape_and_dtype(action), 'reset_observation': reset_observation,
                  'step_observation': shape_and_dtype(observation), 'reward': float(reward),
                  'terminated': bool(terminated), 'truncated': bool(truncated),
                  'success': bool(info.get('is_success', False))}
    finally:
        if env is not None:
            env.close()
    result['close_returned'] = True
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
