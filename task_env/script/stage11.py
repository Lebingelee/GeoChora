"""GeoPhys-local Stage 11 collection, conversion, replay, and training gates.

The command is deliberately orchestration-only.  GeoPhys owns the environment
and H5/replay evidence; agent_factory is imported only by ``train`` and
``client`` subcommands and receives files under this repository's
``temp_outputs`` tree.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
import hashlib
import json
import math
import os
from typing import Any

import h5py
import numpy as np
import yaml

if __package__ in (None, ""):
    from _bootstrap import configure_imports
else:
    from ._bootstrap import configure_imports

configure_imports()

MODE_TO_TARGET = {
    "absolute_joint": ("absolute_joint", None),
    "delta_pose_base": ("delta_pose", "base"),
    "delta_pose_ee": ("delta_pose", "ee"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_meta(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with h5py.File(path, "r") as root:
        group = root["traj_000"] if "traj_000" in root else root
        env_meta = yaml.safe_load(group["meta/env_meta"][()].decode("utf-8")) or {}
        env_cfg = yaml.safe_load(group["meta/env_cfg"][()].decode("utf-8")) or {}
    return env_meta, env_cfg


def _state_dim(path: Path) -> int:
    with h5py.File(path, "r") as root:
        group = root["traj_000"] if "traj_000" in root else root
        return sum(int(np.prod(group["obs/state"][key].shape[1:])) for key in group["obs/state"])


def collect(args: argparse.Namespace) -> None:
    """Collect RGB trajectories with one environment and deterministic resets."""

    from task_env.trajectory.processing import (
        validate_trajectory_collection,
    )
    from task_env.script.trajectory import _collect

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite source collection: {args.output}")
    _collect(args)

    report = validate_trajectory_collection(args.output)
    trajectories = list(report["trajectories"])
    if len(trajectories) != int(args.num_traj):
        raise RuntimeError(f"Stage 11 source collection count mismatch: {len(trajectories)}")
    with h5py.File(args.output, "r") as root:
        expected_names = [f"traj_{index:03d}" for index in range(int(args.num_traj))]
        names = sorted(name for name in root if name.startswith("traj_"))
        if names != expected_names:
            raise RuntimeError(f"Stage 11 source trajectory names are invalid: {names}")
        collected_seeds: set[int] = set()
        for index, name in enumerate(names):
            group = root[name]
            transition_count = int(group.attrs["transition_count"])
            if not 80 <= transition_count <= 120:
                raise RuntimeError(f"{name}: T={transition_count} is outside [80, 120]")
            if not bool(group["success"][-1]):
                raise RuntimeError(f"{name}: final transition is not successful")
            metrics = group["info/task_metrics"]
            if float(metrics["cube_lift"][-1]) < 0.10:
                raise RuntimeError(f"{name}: final cube lift is below 10 cm")
            env_meta = yaml.safe_load(group["meta/env_meta"][()].decode("utf-8")) or {}
            context = env_meta.get("replay_context", {})
            seed = int(context.get("seed", -1))
            if seed < int(args.seed) or seed in collected_seeds:
                raise RuntimeError(f"{name}: replay seed is missing, duplicated, or outside the collection range")
            collected_seeds.add(seed)
            reset = context.get("reset_parameters", {})
            if not isinstance(reset.get("cube_position_world_m"), list):
                raise RuntimeError(f"{name}: sampled cube pose is missing from YAML metadata")
            rgb = group["obs/rgb"]
            if sorted(rgb) != ["base_camera", "hand_camera"] or any(
                tuple(rgb[camera].shape[1:]) != (3, int(args.camera_size), int(args.camera_size))
                or rgb[camera].dtype != np.uint8
                for camera in rgb
            ):
                raise RuntimeError(f"{name}: dual RGB CHW uint8 contract failed")


def reset_smoke(args: argparse.Namespace) -> None:
    """Prove that repeated TaskEnv resets do not alter PickCube outcomes."""

    from task_env import make_env
    from task_env.script.recorder import _build_plan

    config, _ = _build_plan(
        args.env_id,
        args.backend,
        args.horizon,
        camera_obs=False,
        force_limit_N=args.gripper_force,
        camera_size=args.camera_size,
    )
    env = make_env(args.env_id, config=config)
    rows: list[dict[str, Any]] = []
    try:
        for seed in range(int(args.seed), int(args.seed) + int(args.num_traj)):
            _, solution = _build_plan(
                args.env_id,
                args.backend,
                args.horizon,
                camera_obs=False,
                force_limit_N=args.gripper_force,
                camera_size=args.camera_size,
            )
            observation, info = env.reset(seed=seed)
            solution.reset(observation, info, env.metadata)
            last_action = None
            transition_count = 0
            while not solution.done and not solution.failed:
                decision = solution.act(observation, info)
                last_action = decision.action
                observation, reward, terminated, truncated, info = env.step(last_action)
                transition_count += 1
                solution.observe(observation, reward, terminated, truncated, info)
            if solution.done and not solution.failed and last_action is not None:
                for _ in range(10):
                    observation, _, _, _, info = env.step(last_action)
                    transition_count += 1
            metrics = dict(info.get("task_metrics", {}))
            rows.append(
                {
                    "seed": seed,
                    "success": bool(solution.done and not solution.failed and info.get("is_success", False)),
                    "transition_count": transition_count,
                    "final_lift_m": float(metrics.get("cube_lift", 0.0)),
                    "failure_reason": solution.failure_reason,
                }
            )
    finally:
        env.close()
    report = {"backend": args.backend, "camera_obs": False, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    failed = [row for row in rows if not row["success"]]
    if failed:
        raise RuntimeError(f"reset smoke failed; see {args.output}: {failed[0]}")


def transcode(args: argparse.Namespace) -> None:
    from task_env.trajectory.processing import (
        transcode_actions,
        validate_trajectory_collection,
    )

    validate_trajectory_collection(args.source)
    for directory_name, (target_mode, reference) in MODE_TO_TARGET.items():
        output_dir = args.root / f"pick-cube-v1_{directory_name}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "trajectory_collection.h5"
        transcode_actions(
            args.source,
            output,
            target_mode=target_mode,
            target_reference=reference,
        )
        report = validate_trajectory_collection(output)
        if report["trajectory_count"] != 50:
            raise RuntimeError(f"{directory_name}: expected 50 trajectories")


def replay(args: argparse.Namespace) -> None:
    from task_env.trajectory import replay_and_verify_collection

    report = replay_and_verify_collection(args.input, backend=args.backend, require_exact=args.require_exact)
    output = args.input.parent / "metrics" / "replay.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if len(report) != 50 or any(
        not item.get("replay_completed") or not item.get("final_is_success")
        or int(item.get("transition_count", -1)) < 80
        or int(item.get("transition_count", -1)) > 120
        for item in report
    ):
        raise RuntimeError(f"simulator replay gate failed; see {output}")


def _train_config(mode: str, data_path: Path, output_dir: Path, state_dim: int, windows: int) -> dict[str, Any]:
    action_mode = "absolute_joint" if mode == "absolute_joint" else "delta_pose"
    epoch_count = 18
    batch_size = 16
    return {
        "agent_type": "Flow_Vanilla",
        "agent_control_mode": action_mode,
        "device": "cuda:0",
        "seed": 42,
        "env": {
            "env_id": "pick-cube-v1",
            "library": "geophys",
            "obs_horizon": 2,
            "pred_horizon": 16,
            "act_horizon": 8,
            "max_episode_steps": 120,
            "action_dim": 8,
            "proprio_dim": state_dim,
            "num_cameras": 2,
            "env_control_mode": action_mode,
            "control_mode": action_mode,
            "flatten_obs_obj": ["all"],
            "flatten_action": True,
        },
        "train": {
            "device": "cuda:0",
            "batch_size": batch_size,
            "num_workers": 0,
            "save_interval": max(1, math.ceil(epoch_count * windows / batch_size / 4)),
            "train_object": "actor",
            "dataset_key": "expert_dataset",
            "critic_iters": 0,
            "actor_iters": math.ceil(epoch_count * windows / batch_size),
            "finetune": False,
            "save_root": str(output_dir),
            "exp_name": "flow_matching",
        },
        "dataset": {
            "dataset_type": "cpiql",
            "include_rgb": True,
            "include_depth": False,
            "expert": {
                "demo_path": str(data_path.resolve()),
                "num_traj": None,
                "format": "structured",
                "success_only": True,
            },
            "replaybuffer": {"max_traj_num": 0, "folder_path": "", "replaybuffer_path": ""},
        },
        "runner": {"type": "base", "control_hz": 30, "buffer_capacity": 100},
        "actor": {
            "type": "flow_matching",
            "obs_horizon": 2,
            "pred_horizon": 16,
            "require_env_action_dim_match": True,
            "norm": {"type": "min_max", "params": {}},
            "lr": 0.0001,
            "weight_decay": 0.000001,
            "num_inference_steps": 10,
            "time_beta_alpha": 1.5,
            "time_beta_beta": 1.0,
            "time_eps": 0.001,
            "time_embed_scale": 100.0,
            "clip_sample": True,
            "unet": {"down_dims": [128, 256, 512], "diffusion_step_embed_dim": 64, "n_groups": 8},
            "encoder": {
                "type": "CNN_state_encoder",
                "include_rgb": True,
                "visual": {"in_channels": 3, "out_dim": 256, "backbone_type": "resnet", "pool_feature_map": True, "use_group_norm": True},
                "proprio_dim": state_dim,
                "out_dim": 256,
                "hidden_dims": [256],
                "num_cameras": 2,
                "view_fusion": "concat",
            },
        },
        "critic": None,
        "agent_sp": {"iters": 0, "save_dir": str(output_dir), "exp_name": "flow_matching"},
    }


def train(args: argparse.Namespace) -> None:
    """Resolve and train through agent_factory's public Flow_Vanilla API."""

    from omegaconf import OmegaConf
    from agent_factory.config.resolution import general_resolve
    from agent_factory.data.impl.cpiql.expert_dataset import CPIQLExpertDataset

    mode_dir = args.input.parent
    state_dim = _state_dim(args.input)
    probe = _train_config(args.mode, args.input, mode_dir, state_dim, 1)
    probe_cfg = general_resolve(file_config=probe, override_config={})[0]
    dataset = CPIQLExpertDataset(probe_cfg, h5_path=str(args.input), required_keys=["observations", "action"])
    windows = len(dataset)
    dataset.close()
    raw = _train_config(args.mode, args.input, mode_dir, state_dim, windows)
    config_path = mode_dir / "train.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    from agent_factory.script.train_universal import train_universal

    result = train_universal(config_path=str(config_path), finetune=False)
    config_path.write_text(OmegaConf.to_yaml(result["cfg"], resolve=True), encoding="utf-8")
    mapping = {
        "dataset_epoch_count": 18,
        "valid_training_windows": windows,
        "batch_size": int(result["cfg"].train.batch_size),
        "actor_iters": int(result["cfg"].train.actor_iters),
        "formula": "ceil(epoch_count * valid_training_windows / batch_size)",
        "input_h5_sha256": _sha256(args.input),
        "state_dim": state_dim,
        "action_dim": 8,
    }
    (mode_dir / "metrics").mkdir(exist_ok=True)
    (mode_dir / "metrics" / "epoch_iteration_mapping.yaml").write_text(
        yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("--env_id", default="pick-cube-v1")
    collect_parser.add_argument("--env_config", type=Path)
    collect_parser.add_argument("--output", type=Path, required=True)
    collect_parser.add_argument("--num-traj", type=int, default=50)
    collect_parser.add_argument("--seed", type=int, default=0)
    collect_parser.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    collect_parser.add_argument("--horizon", type=int, default=120)
    collect_parser.add_argument("--gripper-force", type=float, default=30.0)
    collect_parser.add_argument("--vis", action="store_true")
    collect_parser.add_argument("--no-render", action="store_true")
    collect_parser.add_argument("--camera-size", type=int, default=64)
    collect_parser.add_argument("--max-attempts", type=int, default=200)
    collect_parser.set_defaults(handler=collect)

    reset_parser = sub.add_parser("reset-smoke")
    reset_parser.add_argument("--env_id", default="pick-cube-v1")
    reset_parser.add_argument("--output", type=Path, required=True)
    reset_parser.add_argument("--num-traj", type=int, default=50)
    reset_parser.add_argument("--seed", type=int, default=0)
    reset_parser.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    reset_parser.add_argument("--horizon", type=int, default=120)
    reset_parser.add_argument("--gripper-force", type=float, default=30.0)
    reset_parser.add_argument("--camera-size", type=int, default=64)
    reset_parser.set_defaults(handler=reset_smoke)

    transcode_parser = sub.add_parser("transcode")
    transcode_parser.add_argument("--source", type=Path, required=True)
    transcode_parser.add_argument("--root", type=Path, required=True)
    transcode_parser.set_defaults(handler=transcode)

    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("--input", type=Path, required=True)
    replay_parser.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    replay_parser.add_argument("--require-exact", action="store_true")
    replay_parser.set_defaults(handler=replay)

    train_parser = sub.add_parser("train")
    train_parser.add_argument("--mode", choices=tuple(MODE_TO_TARGET), required=True)
    train_parser.add_argument("--input", type=Path, required=True)
    train_parser.set_defaults(handler=train)
    return parser


if __name__ == "__main__":
    arguments = _parser().parse_args()
    arguments.handler(arguments)
