"""Probe the supplied legacy RSL-RL runner without Isaac Gym.

Run this script with ``/home/zyf/anaconda3/envs/adamanip/bin/python``.  It
constructs the real legacy ``OnPolicyRunner`` around a minimal VecEnv-shaped
oracle, saves a genuine legacy model container, reloads it, and checks the
48-d observation -> 12-d inference policy contract.  No external package is
modified and no Isaac Gym import is required.
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
import tempfile


def _load_legacy_runner():
    from task_env.diagnostics.go2.legacy_rsl_compat import (
        import_legacy_on_policy_runner,
    )

    return import_legacy_on_policy_runner()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe legacy rsl_rl 1.0.x runner load/inference")
    parser.add_argument("--obs-dim", type=int, default=48)
    parser.add_argument("--action-dim", type=int, default=12)
    parser.add_argument("--num-envs", type=int, default=2)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    import torch

    OnPolicyRunner, probe = _load_legacy_runner()

    class _OracleVecEnv:
        num_envs = int(args.num_envs)
        num_actions = int(args.action_dim)
        max_episode_length = 1000
        step_dt = 0.005

        def get_observations(self):
            return torch.zeros((self.num_envs, args.obs_dim), dtype=torch.float32), {
                "observations": {}
            }

        def step(self, actions):  # pragma: no cover - runner construction does not step
            del actions
            return self.get_observations()[0], torch.zeros(self.num_envs), torch.zeros(self.num_envs, dtype=torch.bool), {}

    cfg = {
        "seed": 0,
        "num_steps_per_env": 2,
        "save_interval": 100,
        "empirical_normalization": False,
        "policy": {
            "class_name": "ActorCritic",
            "actor_hidden_dims": [64, 64],
            "critic_hidden_dims": [64, 64],
            "activation": "elu",
            "init_noise_std": 1.0,
        },
        "algorithm": {
            "class_name": "PPO",
            "num_learning_epochs": 1,
            "num_mini_batches": 1,
            "clip_param": 0.2,
            "gamma": 0.99,
            "lam": 0.95,
            "value_loss_coef": 1.0,
            "entropy_coef": 0.0,
            "learning_rate": 1.0e-3,
            "max_grad_norm": 1.0,
            "use_clipped_value_loss": True,
            "schedule": "fixed",
        },
    }
    env = _OracleVecEnv()
    runner = OnPolicyRunner(env, copy.deepcopy(cfg), device=args.device)
    runner.logger_type = "tensorboard"
    runner.disable_logs = True
    policy = runner.get_inference_policy(device=args.device)
    action = policy(torch.zeros((args.num_envs, args.obs_dim), dtype=torch.float32))
    if tuple(action.shape) != (args.num_envs, args.action_dim):
        raise AssertionError(f"legacy inference shape mismatch: {tuple(action.shape)}")

    with tempfile.TemporaryDirectory(prefix="task_env_legacy_probe_") as tmp:
        path = str(Path(tmp) / "legacy.pt")
        runner.save(path, infos={"probe": True})
        restored = OnPolicyRunner(_OracleVecEnv(), copy.deepcopy(cfg), device=args.device)
        restored.load(path, load_optimizer=False)
        restored_policy = restored.get_inference_policy(device=args.device)
        restored_action = restored_policy(torch.zeros((args.num_envs, args.obs_dim), dtype=torch.float32))
        if tuple(restored_action.shape) != tuple(action.shape):
            raise AssertionError("restored legacy inference shape mismatch")

    print({
        "status": "passed",
        "obs_dim": args.obs_dim,
        "action_dim": args.action_dim,
        "num_envs": args.num_envs,
        **probe,
    })


if __name__ == "__main__":
    main()
