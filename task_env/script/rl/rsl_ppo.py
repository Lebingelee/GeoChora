"""Unified RSL-RL 5.4.2 PPO entry point for registered TaskEnv environments."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from task_env.utils._device_stack import get_device_stack_provenance, preload_device_stack


LOGGER = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-id", default="go2-walk-v1")
    parser.add_argument("--num-env", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=1500)
    parser.add_argument("--rollout-steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--sim-device", default="cuda", choices=("cpu", "cuda"))
    parser.add_argument("--rl-device", default="cuda:0")
    render_group = parser.add_mutually_exclusive_group()
    render_group.add_argument(
        "--render",
        action="store_true",
        help="render up to 256 parallel worlds using the configured render backend",
    )
    render_group.add_argument(
        "--hard-render",
        action="store_true",
        help="render Go2 visual assets in a bounded 16/32/64/96/128/256-world parallel view",
    )
    parser.add_argument(
        "--hard-render-num",
        type=int,
        choices=(16, 32, 64, 96, 128, 256),
        default=16,
        help="number of asset worlds for --hard-render (default: 16; try 64, 128, or 256 explicitly)",
    )
    parser.add_argument(
        "--hard-render-bypass-budget",
        action="store_true",
        help=(
            "diagnostic only: bypass conservative hard-render preflight; "
            "actual GPU allocation may fail"
        ),
    )
    parser.add_argument(
        "--env-config",
        type=Path,
        default=None,
        metavar="YAML",
        help="optional public TaskEnv YAML overlay; omitted uses the task default.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("temp_outputs/task_env/rsl_ppo"),
    )
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--save-interval", type=int, default=50)
    parser.add_argument("--checkpoint-out", type=Path, default=None)
    parser.add_argument(
        "--resume",
        nargs="?",
        const="auto",
        default=None,
        metavar="CHECKPOINT_OR_RUN_DIR",
        help="resume current-RSL actor/critic/optimizer state",
    )
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if int(args.num_env) < 1 or int(args.iterations) < 1 or int(args.rollout_steps) < 1:
        parser.error("num-env, iterations, and rollout-steps must be positive")
    if int(args.hard_render_num) not in (16, 32, 64, 96, 128, 256):
        parser.error("hard-render-num must be 16, 32, 64, 96, 128, or 256")
    if int(args.hard_render_num) != 16 and not args.hard_render:
        parser.error("--hard-render-num requires --hard-render")
    if args.hard_render_bypass_budget and not args.hard_render:
        parser.error("--hard-render-bypass-budget requires --hard-render")
    # Task registration can import the fused runtime before this module's
    # ``main`` executes.  Respect that immutable process-level preload rather
    # than issuing a conflicting CPU-only request after Triton is already
    # established for the runtime.
    if get_device_stack_provenance() is None:
        preload_device_stack()
    from task_env.alg.runner import canonical_ppo_env_id, train_registered_ppo

    args.env_id = canonical_ppo_env_id(args.env_id)
    try:
        summary = train_registered_ppo(env_id=args.env_id, args=args)
    except (FileNotFoundError, RuntimeError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    else:
        LOGGER.info("saved current-RSL checkpoint: %s", summary["checkpoint"])


if __name__ == "__main__":
    main()
