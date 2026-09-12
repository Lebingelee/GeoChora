"""Isaac Gym Go2 contact-onset trace for sim-to-sim diagnosis.

This probe deliberately uses the reference ``unitree_rl_gym`` environment and
does not import ``task_env``.  It places the robot at the same low base height
used by the MuJoCo/GeoPhys contact experiment, applies zero actions for a
number of policy ticks (4 Isaac Gym substeps per tick), and records root
motion and net contact forces.  The resulting trace is evidence about the
Isaac-vs-MuJoCo contact law; it is not a training benchmark.

Run with the supplied legacy environment, for example::

    PATH=/home/zyf/anaconda3/envs/adamanip/bin:$PATH \\
    PYTHONPATH=temp_outputs/unitree_rl_gym \\
    /home/zyf/anaconda3/envs/adamanip/bin/python \\
      python -m task_env.diagnostics.go2.isaac_contact_oracle \\
      --root-z 0.35 --ticks 8 --sim-device cuda:0 --rl-device cuda:0
"""

from __future__ import annotations

import argparse
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
    if isinstance(value, np.generic):
        return value.item()
    return value


def _contact_summary(env, torch):
    forces = env.contact_forces.detach()
    magnitudes = torch.linalg.vector_norm(forces, dim=-1)
    # PhysX can leave very small numerical residuals on inactive bodies.  Use
    # a conservative threshold for the contact-onset count and retain the raw
    # force vector in the artifact for later re-analysis.
    active = magnitudes > 1.0e-4
    return {
        "active_body_count": int(active[0].sum().item()),
        "total_force_norm": float(torch.linalg.vector_norm(forces[0]).item()),
        "max_body_force_norm": float(magnitudes[0].max().item()),
        "active_body_indices": [int(i) for i in active[0].nonzero(as_tuple=False).flatten().tolist()],
        "net_contact_forces": _array(forces[0]),
    }


def capture(args) -> dict[str, object]:
    # Isaac Gym's extension must load before Torch/RSL-RL in this Python 3.8
    # process.  Keep this oracle isolated from GeoPhys imports.
    import isaacgym  # noqa: F401

    from task_env.diagnostics.go2.legacy_rsl_compat import (
        import_legacy_on_policy_runner,
    )

    _, runner_meta = import_legacy_on_policy_runner()
    from isaacgym import gymtorch
    import torch
    from isaacgym.torch_utils import quat_rotate_inverse
    import legged_gym.envs  # noqa: F401
    from legged_gym.utils.helpers import get_args
    from legged_gym.utils.task_registry import task_registry
    from legged_gym.utils.isaacgym_utils import get_euler_xyz as get_euler_xyz_in_tensor

    sys.argv = [
        "go2_isaac_contact_oracle",
        "--task", "go2",
        "--headless",
        "--num_envs", str(int(args.num_envs)),
        "--sim_device", str(args.sim_device),
        "--rl_device", str(args.rl_device),
    ]
    legacy_args = get_args()
    env, env_cfg = task_registry.make_env(name="go2", args=legacy_args)
    env.add_noise = False
    env.cfg.noise.add_noise = False
    env.cfg.domain_rand.push_robots = False

    action = torch.zeros((int(args.num_envs), 12), dtype=torch.float32, device=env.device)
    env.reset()
    env.root_states[:] = 0.0
    env.root_states[:, 0:3] = torch.as_tensor((0.0, 0.0, float(args.root_z)), device=env.device)
    # Isaac Gym root quaternions are xyzw.
    env.root_states[:, 6] = 1.0
    env.root_states[:, 7:13] = 0.0
    env.dof_pos[:] = torch.as_tensor(
        np.asarray((0.1, 0.8, -1.5, -0.1, 0.8, -1.5,
                    0.1, 1.0, -1.5, -0.1, 1.0, -1.5), dtype=np.float32),
        device=env.device,
    )
    env.dof_vel[:] = 0.0
    env.commands[:] = 0.0
    env.actions[:] = 0.0
    env.last_actions[:] = 0.0
    env.last_dof_vel[:] = 0.0
    env.episode_length_buf[:] = 0
    env.reset_buf[:] = 0
    env.gym.set_actor_root_state_tensor(env.sim, gymtorch.unwrap_tensor(env.root_states))
    env.gym.set_dof_state_tensor(env.sim, gymtorch.unwrap_tensor(env.dof_state))
    env.gym.refresh_actor_root_state_tensor(env.sim)
    env.gym.refresh_dof_state_tensor(env.sim)
    env.gym.refresh_net_contact_force_tensor(env.sim)
    env.base_pos[:] = env.root_states[:, 0:3]
    env.base_quat[:] = env.root_states[:, 3:7]
    env.base_lin_vel[:] = quat_rotate_inverse(env.base_quat, env.root_states[:, 7:10])
    env.base_ang_vel[:] = quat_rotate_inverse(env.base_quat, env.root_states[:, 10:13])
    env.projected_gravity[:] = quat_rotate_inverse(env.base_quat, env.gravity_vec)
    env.rpy[:] = get_euler_xyz_in_tensor(env.base_quat)
    env.compute_observations()

    trace = []
    for tick in range(int(args.ticks) + 1):
        if tick > 0:
            _, _, reward, done, extras = env.step(action)
        else:
            reward = torch.zeros(int(args.num_envs), device=env.device)
            done = torch.zeros(int(args.num_envs), dtype=torch.bool, device=env.device)
            extras = {}
        env.gym.refresh_actor_root_state_tensor(env.sim)
        env.gym.refresh_dof_state_tensor(env.sim)
        env.gym.refresh_net_contact_force_tensor(env.sim)
        trace.append({
            "policy_tick": tick,
            "root_state_xyzw": _array(env.root_states),
            "root_z": float(env.root_states[0, 2].item()),
            "root_vz": float(env.root_states[0, 9].item()),
            "dof_pos": _array(env.dof_pos),
            "dof_vel": _array(env.dof_vel),
            "reward": _array(reward),
            "terminated_or_done": _array(done),
            "timeout": _array(env.time_out_buf),
            "contact": _contact_summary(env, torch),
            "extras": _jsonable(extras),
        })

    return {
        "schema": "task-env-go2-isaac-contact-oracle-v1",
        "source": "unitree_rl_gym/legged_gym + Isaac Gym PhysX",
        "legacy_runner": runner_meta,
        "config": {
            "num_envs": int(args.num_envs),
            "physics_engine": "PhysX",
            "physics_dt": float(env_cfg.sim.dt),
            "control_decimation": int(env_cfg.control.decimation),
            "policy_dt": float(env.dt),
            "substeps": int(env_cfg.sim.substeps),
            "solver_type": int(env_cfg.sim.physx.solver_type),
            "position_iterations": int(env_cfg.sim.physx.num_position_iterations),
            "velocity_iterations": int(env_cfg.sim.physx.num_velocity_iterations),
            "contact_offset": float(env_cfg.sim.physx.contact_offset),
            "rest_offset": float(env_cfg.sim.physx.rest_offset),
            "max_depenetration_velocity": float(env_cfg.sim.physx.max_depenetration_velocity),
            "device": str(env.device),
            "root_z": float(args.root_z),
        },
        "trace": trace,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "temp_outputs/task_env/go2_isaac_contact_oracle.json")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--ticks", type=int, default=8)
    parser.add_argument("--root-z", type=float, default=0.35)
    parser.add_argument("--sim-device", default="cuda:0")
    parser.add_argument("--rl-device", default="cuda:0")
    args = parser.parse_args()
    if int(args.num_envs) < 1:
        parser.error("--num-envs must be positive")
    if int(args.ticks) < 1:
        parser.error("--ticks must be positive")
    result = capture(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "config": result["config"],
        "trace": [
            {
                "policy_tick": row["policy_tick"],
                "root_z": row["root_z"],
                "root_vz": row["root_vz"],
                "active_body_count": row["contact"]["active_body_count"],
                "total_force_norm": row["contact"]["total_force_norm"],
            }
            for row in result["trace"]
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
