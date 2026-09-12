"""Capture one deterministic Unitree ``legged_gym`` Go2 reference tick.

This script is intentionally an external oracle.  It is run with the supplied
``adamanip`` Python 3.8 environment, imports Isaac Gym before Torch, and never
imports ``task_env``.  The JSON artifact contains canonical state/action
inputs and the legacy environment's observation/reward/done output so the
GeoPhys and MuJoCo reports can compare the same transform without sharing
implementation code.

Example::

    PATH=/home/zyf/anaconda3/envs/adamanip/bin:$PATH \
    PYTHONPATH=temp_outputs/unitree_rl_gym \
    /home/zyf/anaconda3/envs/adamanip/bin/python \
      python -m task_env.diagnostics.go2.isaac_oracle \
      --output temp_outputs/task_env/go2_isaac_oracle.json \
      --sim-device cuda:0 --rl-device cuda:0
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


from ...utils._paths import REPO_ROOT

LEGACY_ROOT = REPO_ROOT / "temp_outputs" / "unitree_rl_gym"
def _array(value):
    if hasattr(value, "detach"):
        value = value.detach().to("cpu").numpy()
    return np.asarray(value).tolist()


def _jsonable(value):
    if hasattr(value, "detach"):
        return _array(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.generic,)):
        return value.item()
    return value


def _canonical_root_state(root_state):
    """Convert Isaac Gym ``xyzw`` root quaternion to canonical ``wxyz``."""

    value = np.asarray(root_state, dtype=np.float32).copy()
    if value.shape[-1] != 13:
        raise ValueError(f"Isaac root state must end in 13 values, got {value.shape}")
    result = value.copy()
    result[..., 3:7] = value[..., (6, 3, 4, 5)]
    return result


def _refresh_derived_state(env, torch, quat_rotate_inverse):
    """Refresh the exact tensors consumed by legacy obs/reward functions."""

    env.gym.refresh_actor_root_state_tensor(env.sim)
    env.gym.refresh_dof_state_tensor(env.sim)
    env.gym.refresh_net_contact_force_tensor(env.sim)
    env.base_pos[:] = env.root_states[:, 0:3]
    env.base_quat[:] = env.root_states[:, 3:7]
    env.base_lin_vel[:] = quat_rotate_inverse(env.base_quat, env.root_states[:, 7:10])
    env.base_ang_vel[:] = quat_rotate_inverse(env.base_quat, env.root_states[:, 10:13])
    env.projected_gravity[:] = quat_rotate_inverse(env.base_quat, env.gravity_vec)
    # Keep rpy in sync for a possible termination check, although the default
    # canonical state is upright and does not terminate.
    from legged_gym.utils.isaacgym_utils import get_euler_xyz as get_euler_xyz_in_tensor

    env.rpy[:] = get_euler_xyz_in_tensor(env.base_quat)
    env.compute_observations()
    del torch


def capture(args) -> dict[str, object]:
    # Isaac Gym's gymtorch extension must be initialized before Torch/RSL-RL in
    # this legacy process.  This ordering is intentionally local to the oracle.
    import isaacgym  # noqa: F401

    from task_env.diagnostics.go2.legacy_rsl_compat import (
        import_legacy_on_policy_runner,
    )

    _, runner_meta = import_legacy_on_policy_runner()
    from isaacgym import gymtorch
    import torch
    from isaacgym.torch_utils import quat_rotate_inverse
    # Register the legacy tasks before importing the utility module that
    # re-exports the global task registry; reversing this order triggers the
    # legacy package's known utils↔envs circular import.
    import legged_gym.envs  # noqa: F401
    from legged_gym.utils.helpers import get_args
    from legged_gym.utils.task_registry import task_registry

    # ``get_args`` uses Isaac Gym's argparse helper; all options below are
    # standard legacy options, so the script remains compatible with the
    # original registry without constructing a second config path.
    sys.argv = [
        "go2_isaac_oracle",
        "--task", "go2",
        "--headless",
        "--num_envs", str(int(args.num_envs)),
        "--sim_device", str(args.sim_device),
        "--rl_device", str(args.rl_device),
    ]
    legacy_args = get_args()
    env, env_cfg = task_registry.make_env(name="go2", args=legacy_args)
    # The reference config enables observation noise by default.  Disable it
    # for a deterministic cross-engine transform comparison and record that
    # choice in the artifact rather than silently comparing random noise.
    env.add_noise = False
    env.cfg.noise.add_noise = False

    action = torch.as_tensor(
        np.asarray(args.action, dtype=np.float32).reshape(int(args.num_envs), 12),
        dtype=torch.float32,
        device=env.device,
    )
    command = torch.zeros((int(args.num_envs), 4), dtype=torch.float32, device=env.device)
    command[:, :3] = torch.as_tensor(args.command, dtype=torch.float32, device=env.device)

    # Reset once to let Isaac allocate all tensors, then overwrite the state
    # with the canonical upright reference state used by MuJoCo/GeoPhys.
    env.reset()
    env.root_states[:] = 0.0
    env.root_states[:, 0:3] = torch.as_tensor((0.0, 0.0, 0.42), device=env.device)
    # Isaac Gym stores quaternions as xyzw; identity is therefore [0,0,0,1].
    env.root_states[:, 6] = 1.0
    env.root_states[:, 7:13] = 0.0
    env.dof_pos[:] = torch.as_tensor(
        np.asarray((0.1, 0.8, -1.5, -0.1, 0.8, -1.5,
                    0.1, 1.0, -1.5, -0.1, 1.0, -1.5), dtype=np.float32),
        device=env.device,
    )
    env.dof_vel[:] = 0.0
    env.commands[:] = command
    env.actions[:] = 0.0
    env.last_actions[:] = 0.0
    env.last_dof_vel[:] = 0.0
    env.episode_length_buf[:] = 0
    env.reset_buf[:] = 0
    env.gym.set_actor_root_state_tensor(env.sim, gymtorch.unwrap_tensor(env.root_states))
    env.gym.set_dof_state_tensor(env.sim, gymtorch.unwrap_tensor(env.dof_state))
    _refresh_derived_state(env, torch, quat_rotate_inverse)

    initial_obs = env.obs_buf.clone()
    initial_root = env.root_states.clone()
    initial_dof_pos = env.dof_pos.clone()
    initial_dof_vel = env.dof_vel.clone()
    initial_command = env.commands.clone()
    torque = env._compute_torques(action).clone()
    # The legacy callback may recompute heading-based yaw; the selected state
    # has identity heading, so command[:3] remains the requested x/y/yaw input.
    obs, _, reward, done, extras = env.step(action)
    post_root = env.root_states.clone()
    post_dof_pos = env.dof_pos.clone()
    post_dof_vel = env.dof_vel.clone()

    return {
        "schema": "task-env-go2-isaac-oracle-v1",
        "source": "unitree_rl_gym/legged_gym + Isaac Gym legacy",
        "legacy_runner": runner_meta,
        "config": {
            "num_envs": int(args.num_envs),
            "num_observations": int(env_cfg.env.num_observations),
            "num_actions": int(env_cfg.env.num_actions),
            "physics_dt": float(env_cfg.sim.dt),
            "control_decimation": int(env_cfg.control.decimation),
            "policy_dt": float(env.dt),
            "noise_enabled": bool(env.add_noise),
            "device": str(env.device),
            "dof_names": list(env.dof_names),
            "asset_file_sha256": hashlib.sha256(
                Path(env_cfg.asset.file.format(LEGGED_GYM_ROOT_DIR=str(LEGACY_ROOT))).read_bytes()
            ).hexdigest() if Path(env_cfg.asset.file.format(LEGGED_GYM_ROOT_DIR=str(LEGACY_ROOT))).is_file() else None,
        },
        "input": {
            "root_state_xyzw": _array(initial_root),
            "root_state_wxyz": _array(_canonical_root_state(initial_root.detach().cpu().numpy())),
            "dof_pos": _array(initial_dof_pos),
            "dof_vel": _array(initial_dof_vel),
            "command": _array(initial_command),
            "action": _array(action),
            "previous_action": _array(torch.zeros_like(action)),
            "pd_torque": _array(torque),
        },
        "initial": {"observation": _array(initial_obs)},
        "transition": {
            "observation": _array(obs),
            "reward": _array(reward),
            "terminated_or_done": _array(done),
            "truncated": _array(env.time_out_buf),
            "post_root_state_xyzw": _array(post_root),
            "post_root_state_wxyz": _array(_canonical_root_state(post_root.detach().cpu().numpy())),
            "post_dof_pos": _array(post_dof_pos),
            "post_dof_vel": _array(post_dof_vel),
            "torque_applied": _array(env.torques),
            "extras": _jsonable(extras),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "temp_outputs/task_env/go2_isaac_oracle.json")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--sim-device", default="cuda:0")
    parser.add_argument("--rl-device", default="cuda:0")
    # Legacy GO2RoughCfg uses heading-command mode.  A zero yaw command keeps
    # the heading callback from rewriting the third policy command during the
    # one-tick comparison; nonzero-heading captures should explicitly provide
    # the matching fourth heading value in a future oracle schema.
    parser.add_argument("--command", type=float, nargs=3, default=(0.35, -0.1, 0.0))
    parser.add_argument("--action", type=float, nargs=12, default=(0.0,) * 12)
    args = parser.parse_args()
    if int(args.num_envs) < 1:
        parser.error("--num-envs must be positive")
    result = capture(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "num_envs": result["config"]["num_envs"],
        "observation_shape": [len(result["transition"]["observation"]), 48],
        "action_shape": [len(result["input"]["action"]), 12],
        "reward": result["transition"]["reward"],
        "done": result["transition"]["terminated_or_done"],
    }, indent=2))


if __name__ == "__main__":
    main()
