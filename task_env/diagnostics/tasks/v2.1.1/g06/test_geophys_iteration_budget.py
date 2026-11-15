"""Real task-to-worker budget check; requires the shared native supervisor."""
import json
import os
import sys

import torch

from task_env import make_parallel_env


def test_pickcube_contact_budget_reaches_materialized_cuda_solver():
    config = {
        'execution': {'physics_provider': 'geophys', 'interpreter': sys.executable,
                      'geophys_contact_mode': 'discrete'},
        'runtime': {'body_contact_solver_iterations': 37},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'robot': {'native_drive': 'disabled'},
        'episode': {'seed': 31, 'horizon': 20},
    }
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=3,
                            backend='cuda', execution='device', worker_directory=os.getcwd())
    try:
        env.reset(seed=31)
        facts = env.resource_summary()['device_transition']['physical_layout_facts']
        assert facts['solver_iterations_requested'] == 37
        assert facts['solver_iterations_resolved']['contact'] == 37
        assert facts['solver_iterations_resolved']['coupled_constraints'] >= 37
        assert facts['contact_mode_resolved'] == 'discrete'
        action = {'effort': torch.zeros((3, *env.single_action_space['effort'].shape), device='cuda')}
        env.step(action)
        torch.cuda.synchronize()
        print(json.dumps({'configuration': config, 'physical_layout_facts': facts}, sort_keys=True), flush=True)
    finally:
        env.close()
