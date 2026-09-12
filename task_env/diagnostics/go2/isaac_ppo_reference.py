"""Run the supplied legacy Unitree Go2 PPO reference for a bounded probe.

This entry point is intentionally executed in ``adamanip``.  It follows the
original ``legged_gym/scripts/train.py`` construction path and only adds an
in-memory Python 3.8 annotation shim for the installed rsl_rl 1.0.2 package;
neither the reference checkout nor the external environment is modified.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time



from ...utils._paths import REPO_ROOT

LEGACY_ROOT = REPO_ROOT / "temp_outputs" / "unitree_rl_gym"
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--num-envs", type=int, default=4096)
    parser.add_argument("--rollout-steps", type=int, default=25)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--sim-device", default="cuda:0")
    parser.add_argument("--rl-device", default="cuda:0")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "temp_outputs/task_env/go2_isaac_ppo_25iter.pt")
    parser.add_argument("--log-dir", type=Path, default=REPO_ROOT / "temp_outputs/task_env/go2_isaac_ppo_25iter_log")
    args = parser.parse_args()
    if int(args.iterations) < 1 or int(args.num_envs) < 1 or int(args.rollout_steps) < 1:
        parser.error("--iterations, --num-envs, and --rollout-steps must be positive")

    # Isaac Gym's extension must be imported before Torch.  The legacy RSL
    # package then needs the same in-memory annotation shim used by the
    # checkpoint/inference probe because adamanip is Python 3.8.
    import isaacgym  # noqa: F401

    from task_env.diagnostics.go2.legacy_rsl_compat import (
        import_legacy_on_policy_runner,
    )

    OnPolicyRunner, runner_meta = import_legacy_on_policy_runner()
    import sys
    sys.path.insert(0, str(LEGACY_ROOT))
    import legged_gym.envs  # noqa: F401
    from legged_gym.utils.helpers import class_to_dict, get_args, set_seed
    from legged_gym.utils.task_registry import task_registry

    class _CurrentRslVecEnvAdapter:
        """Bridge the checked-out legged_gym VecEnv to rsl_rl 1.0.2.

        The reference checkout returns the five-value Isaac Gym tuple, while
        the installed 1.0.2 runner consumes the newer ``(obs, extras)`` reset
        and four-value step contract.  This adapter changes only the boundary
        shape and forwards all physics/reward/configuration unchanged.
        """

        def __init__(self, env):
            self._env = env
            self.num_envs = int(env.num_envs)
            self.num_actions = int(env.num_actions)
            self.max_episode_length = int(env.max_episode_length)
            self.step_dt = float(env.dt)
            self.device = env.device
            self.cfg = getattr(env, "cfg", None)
            self.step_seconds = 0.0
            self.step_calls = 0
            self.step_times = []

        @property
        def episode_length_buf(self):
            return self._env.episode_length_buf

        @episode_length_buf.setter
        def episode_length_buf(self, value):
            self._env.episode_length_buf = value

        def get_observations(self):
            return self._env.get_observations(), {"observations": {}}

        def step(self, actions):
            started = time.perf_counter()
            observation, _privileged, reward, done, extras = self._env.step(actions)
            elapsed = time.perf_counter() - started
            self.step_seconds += elapsed
            self.step_calls += 1
            self.step_times.append(elapsed)
            info = dict(extras) if isinstance(extras, dict) else {}
            info.setdefault("observations", {})
            info.setdefault("time_outs", self._env.time_out_buf)
            return observation, reward, done, info

        def __getattr__(self, name):
            return getattr(self._env, name)

    # Reuse the reference argument parser/config path.  The only overrides are
    # the explicitly requested bounded probe values.
    sys.argv = [
        "go2_isaac_ppo_reference",
        "--task", "go2",
        "--headless",
        "--num_envs", str(int(args.num_envs)),
        "--seed", str(int(args.seed)),
        "--max_iterations", str(int(args.iterations)),
        "--sim_device", str(args.sim_device),
        "--rl_device", str(args.rl_device),
    ]
    legacy_args = get_args()
    set_seed(int(args.seed))
    env_cfg, reference_cfg = task_registry.get_cfgs("go2")
    env_cfg.seed = int(args.seed)
    env, env_cfg = task_registry.make_env(name="go2", args=legacy_args, env_cfg=env_cfg)
    # The checked-out project uses the pre-1.0 nested config object, while the
    # installed 1.0.2 runner expects the same values in its current flat
    # ``algorithm``/``policy`` sections.  Preserve every reference scalar and
    # only perform this mechanical schema adaptation; no learning parameter is
    # changed.
    train_cfg = class_to_dict(reference_cfg)
    train_cfg["seed"] = int(args.seed)
    train_cfg.update({
        "algorithm": {
            "class_name": "PPO",
            "value_loss_coef": 1.0,
            "use_clipped_value_loss": True,
            "clip_param": 0.2,
            "entropy_coef": 0.01,
            "num_learning_epochs": 5,
            "num_mini_batches": 4,
            "learning_rate": 1.0e-3,
            "schedule": "adaptive",
            "gamma": 0.99,
            "lam": 0.95,
            "desired_kl": 0.01,
            "max_grad_norm": 1.0,
        },
        "policy": {
            "class_name": "ActorCritic",
            "actor_hidden_dims": [512, 256, 128],
            "critic_hidden_dims": [512, 256, 128],
            "activation": "elu",
            "init_noise_std": 1.0,
        },
        "num_steps_per_env": int(args.rollout_steps),
        "save_interval": 50,
        "empirical_normalization": False,
        "logger": "tensorboard",
    })
    vec_env = _CurrentRslVecEnvAdapter(env)
    runner = OnPolicyRunner(
        vec_env,
        train_cfg,
        log_dir=str(args.log_dir),
        device=args.rl_device,
    )
    runner.learn(
        num_learning_iterations=int(args.iterations),
        init_at_random_ep_len=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    runner.save(str(args.output), infos={
        "source": "temp_outputs/unitree_rl_gym/legged_gym/scripts/train.py",
        "reference_task": "go2",
        "iterations": int(args.iterations),
        "num_envs": int(args.num_envs),
        "seed": int(args.seed),
        "sim_device": str(args.sim_device),
        "rl_device": str(args.rl_device),
        "runner_meta": runner_meta,
        "config": {
            "num_steps_per_env": int(train_cfg["num_steps_per_env"]),
            "num_learning_epochs": int(train_cfg["algorithm"]["num_learning_epochs"]),
            "num_mini_batches": int(train_cfg["algorithm"]["num_mini_batches"]),
            "learning_rate": float(train_cfg["algorithm"]["learning_rate"]),
            "gamma": float(train_cfg["algorithm"]["gamma"]),
            "lam": float(train_cfg["algorithm"]["lam"]),
            "clip_param": float(train_cfg["algorithm"]["clip_param"]),
            "entropy_coef": float(train_cfg["algorithm"]["entropy_coef"]),
        },
    })
    print(json.dumps({
        "status": "passed",
        "checkpoint": str(args.output),
        "log_dir": str(args.log_dir),
        "iterations": int(args.iterations),
        "num_envs": int(env_cfg.env.num_envs),
        "seed": int(args.seed),
        "sim_device": str(args.sim_device),
        "rl_device": str(args.rl_device),
        "num_steps_per_env": int(train_cfg["num_steps_per_env"]),
        "sim_step_calls": int(vec_env.step_calls),
        "sim_step_seconds": float(vec_env.step_seconds),
        "sim_step_seconds_mean": float(vec_env.step_seconds / max(1, vec_env.step_calls)),
        "sim_step_hz": float(vec_env.step_calls / max(1.0e-12, vec_env.step_seconds)),
    }, indent=2))


if __name__ == "__main__":
    main()
