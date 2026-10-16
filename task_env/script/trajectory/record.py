"""Record the selected 100Hz task-owned route; canonical execution H5, no D0 claim."""
from pathlib import Path
import argparse
import json


def main(argv=None):
    from task_env import make_env
    from task_env.script.trajectory._task_plans import SELECTED_ENV_IDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-id', choices=SELECTED_ENV_IDS, default=SELECTED_ENV_IDS[1])
    parser.add_argument('--provider', choices=('geophys', 'mujoco'), required=True)
    parser.add_argument('--horizon', type=int, default=6000)
    parser.add_argument('--seed', type=int, default=19)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    env = make_env(args.env_id, config={'provider': args.provider, 'horizon': args.horizon})
    try:
        env.reset(seed=args.seed)
        env.start_recording(args.output)
        while not env._stopped:
            env.step_expert()
        verification = env.finish_recording(env.solution.failure_reason or 'selected_policy_completed')
        print(json.dumps({'verification': verification, 'info': env.info}, default=str))
    finally:
        env.close()


if __name__ == '__main__':
    main()
