import argparse
import os
import sys
import tempfile
from typing import Any, Dict, Optional

if __package__ in {None, ""}:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _REPO_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "matplotlib"))

import torch
from omegaconf import OmegaConf

from agent_factory.agents.registry import make_agent
from agent_factory.config.resolution import general_resolve
from agent_factory.env.env_factories import create_env
from agent_factory.runner import Pi0Runner


def _load_raw_config(config_path: str) -> Dict[str, Any]:
    loaded = OmegaConf.load(config_path)
    value = OmegaConf.to_container(loaded, resolve=False)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a mapping config, got {type(value).__name__}: {config_path}")
    return value


def _set_if_provided(cfg: Any, path: str, value: Optional[Any]):
    if value is None or value == "":
        return
    OmegaConf.update(cfg, path, value, merge=False)


def parse_args():
    parser = argparse.ArgumentParser(description="Collect pi0 rollout trajectories with agent_factory.")
    parser.add_argument("--config", required=True, help="Path to a pi0 rollout config YAML.")
    parser.add_argument(
        "--pretrained-path",
        "--pretrained_path",
        default="",
        help="Override actor.pretrained_path. Should point to checkpoints/<step>/pretrained_model/.",
    )
    parser.add_argument("--save-dir", "--save_dir", default="", help="Override runner.save_dir.")
    parser.add_argument(
        "--num-trajectories",
        "--num_trajectories",
        type=int,
        default=0,
        help="Override runner.config.num_rollout_trajectories.",
    )
    parser.add_argument("--device", default="", help="Override device, e.g. cuda:0 or cpu.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve config and exit before env/model creation.")
    return parser.parse_args()


def main():
    args = parse_args()
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    cfg, _runtime_spec = general_resolve(
        file_config=_load_raw_config(args.config),
        override_config={"device": device},
        finetune=False,
    )
    cfg.device = device
    cfg.train.device = device
    _set_if_provided(cfg, "actor.pretrained_path", args.pretrained_path)
    _set_if_provided(cfg, "actor.checkpoint_path", args.pretrained_path)
    _set_if_provided(cfg, "runner.save_dir", args.save_dir)
    if int(args.num_trajectories) > 0:
        OmegaConf.update(
            cfg,
            "runner.config.num_rollout_trajectories",
            int(args.num_trajectories),
            merge=False,
        )

    print(f"[Pi0Rollout] config={os.path.abspath(args.config)}")
    print(f"[Pi0Rollout] device={cfg.device}")
    print(f"[Pi0Rollout] env_config_path={cfg.env.env_config_path}")
    print(f"[Pi0Rollout] env_control_mode={cfg.env.env_control_mode}")
    print(f"[Pi0Rollout] agent_control_mode={cfg.agent_control_mode}")
    print(f"[Pi0Rollout] save_dir={cfg.runner.save_dir}")
    print(f"[Pi0Rollout] num_rollout_trajectories={cfg.runner.config.num_rollout_trajectories}")
    print(f"[Pi0Rollout] pretrained_path={cfg.actor.pretrained_path}")

    if args.dry_run:
        print("[Pi0Rollout] dry-run OK; exiting before env/model creation.")
        return

    os.makedirs(str(cfg.runner.save_dir), exist_ok=True)
    env = create_env(cfg.env)
    agent = make_agent("pi0", cfg)
    agent.to(device)
    agent.eval()

    runner = Pi0Runner(cfg=cfg, agent=agent, env=env)
    try:
        runner.collect(
            num_trajectories=int(cfg.runner.config.num_rollout_trajectories),
            sleep_between=float(cfg.runner.config.get("sleep_between_trajectories", 0.0)),
        )
    finally:
        runner.stop_worker()
        env.close()
        print("[Pi0Rollout] Done.")


if __name__ == "__main__":
    main()
