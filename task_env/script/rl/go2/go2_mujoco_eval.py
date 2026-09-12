"""Run a trained current-RSL Go2 actor in the independent MuJoCo oracle.

This evaluator is deliberately separate from ``go2_mujoco.py``: the latter
is a fixed-action oracle smoke, while this entry point loads only the actor
weights and performs a policy rollout.  It does not import the GeoPhys Go2
task, so the MuJoCo trajectory remains an independent sim-to-sim reference.
The report is a physics/policy trace; GeoPhys reward and termination are not
silently reconstructed here.
example
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.go2.go2_mujoco_eval \
  --checkpoint temp_outputs/task_env/go2_b1024_25iter/tensorboard/model_24.pt \
  --steps 1000 \
  --command 0.2 0.0 0.0 \
  --platform-box \
  --viewer \
  --realtime \
  --device cpu \
  --output-dir temp_outputs/task_env/go2_mujoco_eval
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
import time

import numpy as np

from task_env.diagnostics.go2.mujoco_oracle import (
    GO2_DEPLOY_ENV_ID,
    GO2_DEPLOY_HEIGHT_ENV_ID,
    GO2_WALK_ENV_ID,
    Go2MujocoOracle,
    resolve_go2_mujoco_observation_contract,
)
from task_env.alg.rsl_rl import resolve_action_profile


ACTION_DIM = 12
HIDDEN_DIMS = (512, 256, 128)
GO2_ENV_IDS = (GO2_WALK_ENV_ID, GO2_DEPLOY_ENV_ID, GO2_DEPLOY_HEIGHT_ENV_ID)


class _Go2Actor:
    """Framework-neutral deterministic actor matching current RSL-RL MLPModel."""

    def __init__(self, torch, *, device: str, observation_dim: int, action_profile):
        self.torch = torch
        self.module = torch.nn.Sequential(
            torch.nn.Linear(int(observation_dim), HIDDEN_DIMS[0]),
            torch.nn.ELU(),
            torch.nn.Linear(HIDDEN_DIMS[0], HIDDEN_DIMS[1]),
            torch.nn.ELU(),
            torch.nn.Linear(HIDDEN_DIMS[1], HIDDEN_DIMS[2]),
            torch.nn.ELU(),
            torch.nn.Linear(HIDDEN_DIMS[2], ACTION_DIM),
        ).to(device=device, dtype=torch.float32)
        self.device = str(device)
        self.action_profile = action_profile

    def load_state(self, state: Mapping[str, object]) -> None:
        tensor_state = {}
        for name, value in state.items():
            key = str(name)
            if key.startswith("actor."):
                key = key[len("actor."):]
            if key.startswith("mlp."):
                tensor_state[key[len("mlp."):]] = value
        expected = {name for name, _ in self.module.state_dict().items()}
        if set(tensor_state) != expected:
            missing = sorted(expected.difference(tensor_state))
            unexpected = sorted(set(tensor_state).difference(expected))
            raise ValueError(
                "checkpoint actor architecture mismatch: "
                f"missing={missing}, unexpected={unexpected}"
            )
        self.module.load_state_dict(tensor_state, strict=True)
        self.module.eval()

    def __call__(self, observation: np.ndarray) -> np.ndarray:
        tensor = self.torch.as_tensor(observation, dtype=self.torch.float32, device=self.device)
        with self.torch.no_grad():
            action = self.module(tensor[None, :])[0]
        raw = action.detach().cpu().numpy().astype(np.float32)
        return self.action_profile.apply_numpy(raw, fallback_low=-1.0, fallback_high=1.0).astype(np.float32, copy=False)


class _TorchScriptGo2Actor:
    """Inference wrapper for Isaac/legged_gym's exported actor archive."""

    def __init__(self, torch, module, *, device: str, action_profile):
        self.torch = torch
        self.module = module.to(device=device)
        self.module.eval()
        self.device = str(device)
        self.action_profile = action_profile

    def __call__(self, observation: np.ndarray) -> np.ndarray:
        tensor = self.torch.as_tensor(
            observation, dtype=self.torch.float32, device=self.device
        )
        with self.torch.no_grad():
            action = self.module(tensor[None, :])[0]
        raw = action.detach().cpu().numpy().astype(np.float32)
        return self.action_profile.apply_numpy(
            raw, fallback_low=-1.0, fallback_high=1.0
        ).astype(np.float32, copy=False)


def _validate_checkpoint_observation_dim(
    state: Mapping[str, object], *, expected_observation_dim: int
) -> None:
    """Fail with a task-specific message before PyTorch's generic size mismatch."""

    for name, value in state.items():
        key = str(name)
        if key.startswith("actor."):
            key = key[len("actor."):]
        if key == "mlp.0.weight" or key == "0.weight":
            shape = tuple(int(item) for item in getattr(value, "shape", ()))
            if len(shape) != 2:
                raise ValueError(f"checkpoint actor first layer must be a matrix, got {shape}")
            if shape[1] != int(expected_observation_dim):
                raise ValueError(
                    "checkpoint observation dimension mismatch: "
                    f"checkpoint={shape[1]}, requested={expected_observation_dim}; "
                    "pass the matching --env-id"
                )
            return
    raise ValueError("checkpoint actor_state_dict has no mlp.0.weight input layer")


def _load_actor(
    path: Path,
    *,
    device: str,
    observation_dim: int,
    action_profile,
):
    try:
        import torch
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("MuJoCo checkpoint evaluation requires PyTorch") from exc
    # Probe the actor-only format first.  This avoids asking torch.load() to
    # inspect a TorchScript zip as a state-dict archive (and avoids its noisy
    # weights_only warning); current RSL-RL checkpoints fall through quickly.
    try:
        module = torch.jit.load(path, map_location=device)
    except RuntimeError:
        module = None
    if module is not None:
        # Isaac/legged_gym's policy_*.pt contains the actor only, which is
        # exactly the state required by this inference-only evaluator.
        _validate_checkpoint_observation_dim(
            module.state_dict(), expected_observation_dim=int(observation_dim)
        )
        return _TorchScriptGo2Actor(
            torch, module, device=device, action_profile=action_profile
        ), torch, "torchscript_actor"
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except RuntimeError as load_error:
        raise load_error
    except TypeError as exc:  # pragma: no cover - old Torch lacks safe loading
        raise RuntimeError("this PyTorch version must support weights_only checkpoint loading") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("checkpoint root must be a mapping")
    state = payload.get("actor_state_dict")
    if not isinstance(state, Mapping):
        raise ValueError("current RSL-RL checkpoint must contain actor_state_dict")
    _validate_checkpoint_observation_dim(
        state, expected_observation_dim=int(observation_dim)
    )
    actor = _Go2Actor(
        torch,
        device=device,
        observation_dim=int(observation_dim),
        action_profile=action_profile,
    )
    actor.load_state(state)
    return actor, torch, "rsl_rl_state_dict"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--env-id",
        choices=GO2_ENV_IDS,
        default=GO2_WALK_ENV_ID,
        help=(
            "Go2 policy observation contract. The default preserves the legacy "
            "48D go2-walk evaluator; use the deploy env id for 45D/46D checkpoints."
        ),
    )
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument(
        "--command",
        type=float,
        nargs="+",
        default=None,
        metavar="VALUE",
        help="VX VY WZ; height-deploy also accepts HEIGHT as a fourth value",
    )
    parser.add_argument("--platform-box", action="store_true")
    parser.add_argument("--viewer", action="store_true", help="open mujoco.viewer.launch_passive")
    parser.add_argument("--realtime", action="store_true", help="pace viewer at the 0.02 s Go2 policy period")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "cuda:0"))
    parser.add_argument(
        "--rsl-action-profile",
        default="unitree_go2_reference",
        metavar="PROFILE",
        help="learner action semantics; defaults to the Unitree Go2 clip_actions=100 profile",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("temp_outputs/task_env/go2_mujoco_eval"))
    parser.add_argument("--output", type=Path, default=None, help="override the JSON output path")
    args = parser.parse_args()
    if int(args.steps) < 1:
        parser.error("--steps must be positive")
    if not args.checkpoint.is_file():
        parser.error(f"checkpoint does not exist: {args.checkpoint}")
    if args.device.startswith("cuda"):
        import torch
        if not torch.cuda.is_available():
            parser.error("CUDA device requested but CUDA is unavailable")

    try:
        observation_contract = resolve_go2_mujoco_observation_contract(
            env_id=str(args.env_id)
        )
    except ValueError as exc:  # pragma: no cover - argparse choices cover env ids
        parser.error(str(exc))
    action_profile = resolve_action_profile(args.rsl_action_profile)
    actor, _torch, checkpoint_format = _load_actor(
        args.checkpoint,
        device=args.device,
        observation_dim=observation_contract.observation_dim,
        action_profile=action_profile,
    )
    if args.command is None:
        command = np.zeros(observation_contract.command_dim, dtype=np.float32)
        if observation_contract.default_height_command is not None:
            command[-1] = observation_contract.default_height_command
    else:
        command = np.asarray(args.command, dtype=np.float32)
        if (
            observation_contract.command_dim == 4
            and command.shape == (3,)
            and observation_contract.default_height_command is not None
        ):
            command = np.concatenate(
                (
                    command,
                    np.asarray(
                        (observation_contract.default_height_command,), dtype=np.float32
                    ),
                )
            )
        if command.shape != (observation_contract.command_dim,):
            parser.error(
                f"{observation_contract.env_id} requires "
                f"{observation_contract.command_dim} command values; got {command.size}"
            )
    native_clip = action_profile.native_high
    oracle = Go2MujocoOracle(
        platform_box=bool(args.platform_box),
        action_clip=1.0 if native_clip is None else native_clip,
        env_id=observation_contract.env_id,
    )
    oracle.reset()
    rows: list[dict[str, object]] = []
    viewer = None
    if args.viewer:
        try:
            import mujoco.viewer
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("--viewer requires the mujoco viewer dependencies") from exc
        viewer = mujoco.viewer.launch_passive(oracle.model, oracle.data)
    try:
        for tick in range(int(args.steps)):
            if viewer is not None and not viewer.is_running():
                break
            observation = oracle.observation(command=command, action=oracle.previous_action)
            action = actor(observation)
            row = oracle.step(action, command=command)
            row["policy_observation"] = observation.tolist()
            row["policy_action"] = action.tolist()
            row["tick"] = tick + 1
            rows.append(row)
            if viewer is not None:
                viewer.sync()
            if args.realtime:
                time.sleep(0.02)
    finally:
        if viewer is not None:
            viewer.close()

    actions = np.asarray([row["policy_action"] for row in rows], dtype=np.float32)
    observations = np.asarray([row["policy_observation"] for row in rows], dtype=np.float32)
    torques = np.asarray([row["torque"] for row in rows], dtype=np.float32)
    qpos = np.asarray([row["qpos"] for row in rows], dtype=np.float32)
    qvel = np.asarray([row["qvel"] for row in rows], dtype=np.float32)
    report = {
        "schema": "task-env-go2-mujoco-policy-eval-v1",
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "steps_requested": int(args.steps),
        "steps_executed": int(len(rows)),
        "command": command.tolist(),
        "platform_box": bool(args.platform_box),
        "rsl_action_profile": action_profile.manifest(),
        "viewer": bool(args.viewer),
        "env_id": observation_contract.env_id,
        "policy": {"observation_dim": observation_contract.observation_dim, "action_dim": ACTION_DIM, "hidden_dims": list(HIDDEN_DIMS), "activation": "elu", "normalization": "none", "checkpoint_format": checkpoint_format},
        "mean_abs_action": float(np.mean(np.abs(actions))) if actions.size else None,
        "max_abs_action": float(np.max(np.abs(actions))) if actions.size else None,
        "mean_abs_torque": float(np.mean(np.abs(torques))) if torques.size else None,
        "final_qpos": qpos[-1].tolist() if qpos.size else None,
        "final_qvel": qvel[-1].tolist() if qvel.size else None,
        "interpretation": "independent MuJoCo actor rollout; GeoPhys reward/terminated/truncated are not reconstructed",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_output = args.output or (args.output_dir / "eval.json")
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    from task_env.alg.rsl_rl.artifacts import write_h5_artifact
    write_h5_artifact(
        args.output_dir / "eval.h5",
        schema="task-env-go2-mujoco-policy-eval-v1",
        manifest={"checkpoint": str(args.checkpoint), "checkpoint_sha256": report["checkpoint_sha256"], "steps": int(args.steps), "steps_executed": int(len(rows)), "command": command.tolist(), "platform_box": bool(args.platform_box), "env_id": observation_contract.env_id, "rsl_action_profile": action_profile.manifest(), "policy": report["policy"]},
        arrays={"observation": observations, "action": actions, "torque": torques, "qpos": qpos, "qvel": qvel},
        report=report,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
