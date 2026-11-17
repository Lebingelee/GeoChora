"""One source-bound PickCube scene load alongside a normal effort action.

Example: python examples/tasks/scene_body_wrench.py --provider mujoco --output episode.h5
Isaac also requires --isaac-python and --delivery for the admitted desktop USD.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from task_env import make_env
from task_env.controllers.canonical.physical_commands import BodyWrenchV1, ContributionPolicyV1
from task_env.recorders import load_physical_recording_h5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=('mujoco', 'geophys', 'isaacsim'), default='mujoco')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--isaac-python')
    parser.add_argument('--delivery')
    args = parser.parse_args()
    execution = {'physics_provider': args.provider}
    if args.provider == 'isaacsim':
        if not args.isaac_python or not args.delivery:
            parser.error('Isaac requires --isaac-python and --delivery')
        execution.update(physics_backend='cuda', physics_device='cuda:0',
                         deployment='isolated_worker', interpreter=args.isaac_python,
                         source_delivery_manifest=args.delivery)
    else:
        execution.update(physics_backend='cpu',
                         deployment='in_process' if args.provider == 'mujoco' else 'isolated_worker')
    body_id = 'cube' if args.provider == 'isaacsim' else 'PickCube'
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': execution,
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'robot': {'native_drive': 'disabled'},
        'episode': {'horizon': 8},
        'scene_body_producers': [{'writer_id': 'example-load', 'producer_kind': 'caller',
                                  'body_keys': [['cube-v1', body_id]]}],
    })
    try:
        env.reset(seed=31)
        context, bodies = env.physical_scene_context()
        body = next(item for item in bodies if (item.entity_id, item.body_id) == ('cube-v1', body_id))
        frame = body.body_frame
        policy = ContributionPolicyV1('physical-contribution-policy-v1', 'example-load-1',
            'example-effect-1', 'example-load', 'exclusive', 'reject_outside', 'one_interval')
        wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'cube-v1', body_id,
            frame, (0., 0., 0.), frame, (0., 0., 0.), frame, (0., 0., 1.), (0., 0., 0.))
        env.start_recording(args.output)
        env.step(np.zeros(8, dtype=np.float32), scene_body_wrenches=(wrench,))
        env.finish_recording('external_stop')
    finally:
        env.close()
    recording = load_physical_recording_h5(args.output)
    print(f"Recorded {recording['transition_count']} transition(s) and "
          f"{recording['observation_count']} observations to {args.output}")


if __name__ == '__main__':
    main()
