"""Compare real current-5 and legacy-1 Go2 actor inference outputs.

Run this script twice, once in ``geophys`` with ``--api current_5`` and once
in the supplied ``adamanip`` environment with ``--api legacy_1``.  The final
``--compare`` invocation only consumes JSON/tensor data and never imports a
simulator.  This keeps the checkpoint gate independent of Isaac Gym while
still exercising each installed ``OnPolicyRunner`` implementation.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


def _fixed_observation(num_envs: int):
    import torch

    return (torch.arange(int(num_envs) * 48, dtype=torch.float32).reshape(int(num_envs), 48) - 48.0) / 17.0


def _legacy_runner(*, num_envs: int, device: str, checkpoint: Path):
    import torch

    from task_env.diagnostics.go2.legacy_rsl_compat import (
        import_legacy_on_policy_runner,
    )

    OnPolicyRunner, runner_meta = import_legacy_on_policy_runner()

    class OracleVecEnv:
        def __init__(self):
            self.num_envs = int(num_envs)
            self.num_actions = 12
            self.max_episode_length = 1000
            self.step_dt = 0.02

        def get_observations(self):
            return torch.zeros((self.num_envs, 48), dtype=torch.float32), {"observations": {}}

        def step(self, actions):  # pragma: no cover - construction only
            del actions
            return self.get_observations()[0], torch.zeros(self.num_envs), torch.zeros(self.num_envs, dtype=torch.bool), {}

    cfg = {
        "seed": 0,
        "num_steps_per_env": 2,
        "save_interval": 100,
        "empirical_normalization": False,
        "policy": {
            "class_name": "ActorCritic",
            "actor_hidden_dims": [512, 256, 128],
            "critic_hidden_dims": [512, 256, 128],
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
            "entropy_coef": 0.0,
            "learning_rate": 1.0e-3,
            "max_grad_norm": 1.0,
            "use_clipped_value_loss": True,
            "schedule": "fixed",
        },
    }
    runner = OnPolicyRunner(OracleVecEnv(), copy.deepcopy(cfg), device=device)
    runner.load(str(checkpoint), load_optimizer=False)
    policy = runner.get_inference_policy(device=device)
    observation = _fixed_observation(num_envs).to(device=device)
    with torch.no_grad():
        action = policy(observation)
    return observation, action, runner_meta


def _current_runner(*, num_envs: int, device: str, checkpoint: Path):
    import torch
    from tensordict import TensorDict

    from task_env.alg.rsl_rl.runner import build_runner
    from task_env.alg.rsl_rl.training import current5_train_cfg

    class OracleVecEnv:
        def __init__(self):
            self.num_envs = int(num_envs)
            self.num_actions = 12
            self.max_episode_length = 1000
            self.step_dt = 0.02
            self.device = str(device)
            self.cfg = {}

        def get_observations(self):
            zeros = torch.zeros((self.num_envs, 48), dtype=torch.float32, device=self.device)
            return TensorDict({"policy": zeros}, batch_size=[self.num_envs], device=self.device)

        def step(self, actions):  # pragma: no cover - construction only
            del actions
            return self.get_observations(), torch.zeros(self.num_envs, device=self.device), torch.zeros(self.num_envs, dtype=torch.bool, device=self.device), {}

    runner = build_runner(
        OracleVecEnv(),
        current5_train_cfg(rollout_steps=2, save_interval=100),
        device=device,
    )
    runner.load(str(checkpoint))
    observation = _fixed_observation(num_envs).to(device=device)
    td = TensorDict({"policy": observation}, batch_size=[int(num_envs)], device=device)
    with torch.no_grad():
        # Current 5.x MLPModel.forward returns the deterministic actor mean.
        action = runner.alg.actor(td)
    return observation, action, {"current_runner": "rsl_rl.runners.OnPolicyRunner"}


def _write_capture(path: Path, *, api: str, checkpoint: Path, observation, action, metadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "task-env-go2-checkpoint-parity-v1",
                "api": api,
                "checkpoint": str(checkpoint),
                "observation": observation.detach().to("cpu").tolist(),
                "action": action.detach().to("cpu").tolist(),
                "metadata": metadata,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", choices=("current_5", "legacy_1"))
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("CURRENT_JSON", "LEGACY_JSON"))
    parser.add_argument("--num-envs", type=int, default=2)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--atol", type=float, default=1.0e-5)
    args = parser.parse_args()

    if args.compare is not None:
        current = json.loads(args.compare[0].read_text(encoding="utf-8"))
        legacy = json.loads(args.compare[1].read_text(encoding="utf-8"))
        if current.get("schema") != "task-env-go2-checkpoint-parity-v1" or legacy.get("schema") != "task-env-go2-checkpoint-parity-v1":
            raise AssertionError("unsupported checkpoint parity artifact schema")
        import numpy as np

        current_obs = np.asarray(current["observation"], dtype=np.float32)
        legacy_obs = np.asarray(legacy["observation"], dtype=np.float32)
        current_action = np.asarray(current["action"], dtype=np.float32)
        legacy_action = np.asarray(legacy["action"], dtype=np.float32)
        obs_error = float(np.max(np.abs(current_obs - legacy_obs)))
        action_error = float(np.max(np.abs(current_action - legacy_action)))
        if obs_error > float(args.atol) or action_error > float(args.atol):
            raise AssertionError(f"checkpoint parity exceeded atol={args.atol}: obs={obs_error}, action={action_error}")
        print(json.dumps({"status": "passed", "observation_max_abs": obs_error, "action_max_abs": action_error, "atol": float(args.atol)}, indent=2))
        return

    if args.api is None or args.checkpoint is None or args.output is None:
        parser.error("--api, --checkpoint and --output are required unless --compare is used")
    if int(args.num_envs) < 1:
        parser.error("--num-envs must be positive")
    if args.api == "legacy_1":
        observation, action, metadata = _legacy_runner(num_envs=args.num_envs, device=args.device, checkpoint=args.checkpoint)
    else:
        observation, action, metadata = _current_runner(num_envs=args.num_envs, device=args.device, checkpoint=args.checkpoint)
    if tuple(action.shape) != (int(args.num_envs), 12):
        raise AssertionError(f"Go2 checkpoint action must have shape ({args.num_envs}, 12), got {tuple(action.shape)}")
    _write_capture(args.output, api=args.api, checkpoint=args.checkpoint, observation=observation, action=action, metadata=metadata)
    print(json.dumps({"status": "captured", "api": args.api, "output": str(args.output), "action_shape": list(action.shape)}, indent=2))


if __name__ == "__main__":
    main()
