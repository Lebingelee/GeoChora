"""
 python -m agent_factory.script.prepare_pi0_lerobot_train\
    --dataset-root data/lerobot/can \
    --save-root outputs/pi0\
    --exp-name can_100_pi0 \
    --video-backend pyav \
    --steps 30000\
    --save-freq 10000\
    --batch-size 24\
    --num-workers 20
"""
import argparse
import json
import shlex
from pathlib import Path
from typing import Optional

import pandas as pd

from agent_factory.data.impl.pi0.policy_dataset import (
    infer_lerobot_repo_id,
    load_lerobot_policy_dataset,
)
from agent_factory.modules.actors.pi0 import PI0_NORMALIZATION_SOURCE_LEROBOT


def _format_command(parts: list[str]) -> str:
    lines = []
    idx = 0
    while idx < len(parts):
        part = shlex.quote(str(parts[idx]))
        if idx + 1 < len(parts) and str(parts[idx]).startswith("-") and not str(parts[idx + 1]).startswith("-"):
            value = shlex.quote(str(parts[idx + 1]))
            lines.append(f"{part} {value}")
            idx += 2
        else:
            lines.append(part)
            idx += 1
    return " \\\n  ".join(lines)


def _format_single_gpu_command(command: list[str], cuda_visible_devices: str = "0") -> str:
    return f"CUDA_VISIBLE_DEVICES={shlex.quote(cuda_visible_devices)} " + _format_command(command)


def _format_multi_gpu_command(command: list[str], cuda_visible_devices: str = "0,1", num_processes: int = 2) -> str:
    if len(command) < 3 or command[1] != "-m":
        return (
            f"CUDA_VISIBLE_DEVICES={shlex.quote(cuda_visible_devices)} "
            f"accelerate launch --num_processes {int(num_processes)} "
            + _format_command(command)
        )
    accelerate_command = [
        "accelerate",
        "launch",
        "--num_processes",
        str(int(num_processes)),
        "-m",
        command[2],
        *command[3:],
    ]
    return f"CUDA_VISIBLE_DEVICES={shlex.quote(cuda_visible_devices)} " + _format_command(accelerate_command)


def _read_episode_lengths(dataset_root: Path) -> list[int]:
    episodes_dir = dataset_root / "meta" / "episodes"
    if not episodes_dir.exists():
        return []

    lengths: list[int] = []
    for parquet_path in sorted(episodes_dir.glob("chunk-*/file-*.parquet")):
        table = pd.read_parquet(parquet_path, columns=["length"])
        lengths.extend(int(value) for value in table["length"].tolist())
    return lengths


def _sample_summary(dataset, sample_indices: list[int]) -> list[dict[str, object]]:
    rows = []
    for idx in sample_indices:
        item = dataset[idx]
        rows.append(
            {
                "index": idx,
                "episode_index": int(item["episode_index"]),
                "frame_index": int(item["frame_index"]),
                "timestamp": float(item["timestamp"]),
                "state_shape": tuple(item["observation.state"].shape),
                "action_shape": tuple(item["action"].shape),
                "image_keys": sorted(
                    key for key in item.keys() if str(key).startswith("observation.images.")
                ),
                "task": item.get("task"),
            }
        )
    return rows


def build_lerobot_train_command(
    *,
    python_executable: str,
    dataset_root: str,
    repo_id: str,
    output_dir: str,
    policy_path: Optional[str],
    video_backend: str,
    steps: int,
    save_freq: int,
    batch_size: int,
    num_workers: int,
    chunk_size: int,
    n_action_steps: int,
    dtype: str,
    device: Optional[str],
    gradient_checkpointing: bool,
    train_expert_only: bool,
    use_relative_actions: bool,
    return_uint8: bool,
    normalization_source: str,
) -> list[str]:
    if normalization_source != PI0_NORMALIZATION_SOURCE_LEROBOT:
        raise ValueError(
            "Phase B pi0 training must use normalization_source='lerobot'. "
            "agent_factory action normalization is not part of the LeRobot training route."
        )
    command = [
        python_executable,
        "-m",
        "lerobot.scripts.lerobot_train",
        "--dataset.repo_id",
        repo_id,
        "--dataset.root",
        dataset_root,
        "--dataset.video_backend",
        video_backend,
        "--dataset.return_uint8",
        str(return_uint8).lower(),
        "--output_dir",
        output_dir,
        "--job_name",
        Path(output_dir).name,
        "--steps",
        str(int(steps)),
        "--save_freq",
        str(int(save_freq)),
        "--batch_size",
        str(int(batch_size)),
        "--num_workers",
        str(int(num_workers)),
        "--env_eval_freq",
        "0",
        "--wandb.enable",
        "false",
    ]

    if policy_path:
        command.extend(["--policy", policy_path])
    else:
        command.extend(["--policy.type", "pi0"])

    command.extend(
        [
            "--policy.chunk_size",
            str(int(chunk_size)),
            "--policy.n_action_steps",
            str(int(n_action_steps)),
            "--policy.dtype",
            dtype,
            "--policy.gradient_checkpointing",
            str(gradient_checkpointing).lower(),
            "--policy.train_expert_only",
            str(train_expert_only).lower(),
            "--policy.use_relative_actions",
            str(use_relative_actions).lower(),
        ]
    )
    if device:
        command.extend(["--policy.device", device])
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a local LeRobotDataset and print the preferred pi0 training command.",
        epilog=(
            "GPU 使用说明：本脚本生成训练主体命令。单卡训练通常在命令前加 "
            "`CUDA_VISIBLE_DEVICES=0`；多卡训练通常使用 "
            "`CUDA_VISIBLE_DEVICES=0,1 accelerate launch --num_processes 2 -m lerobot.scripts.lerobot_train ...`。"
            "LeRobot 本身不提供每张卡显存上限参数，显存主要通过 batch-size、bf16、gradient checkpointing、"
            "以及 accelerate/FSDP/DeepSpeed 配置控制。"
        ),
    )
    parser.add_argument("--dataset-root", required=True, help="Local LeRobotDataset root.")
    parser.add_argument("--repo-id", default=None, help="LeRobot repo_id. Defaults to conversion manifest repo_id.")
    parser.add_argument(
        "--save-root",
        default="outputs/pi0",
        help="Root directory used to construct the LeRobot training output_dir.",
    )
    parser.add_argument("--exp-name", default="pi0_can", help="Experiment directory name under save-root.")
    parser.add_argument(
        "--policy-path",
        default=None,
        help="Optional existing pi0 pretrained/checkpoint directory. If omitted, --policy.type pi0 is used.",
    )
    parser.add_argument("--video-backend", default="pyav")
    parser.add_argument("--steps", type=int, default=30000)
    parser.add_argument("--save-freq", type=int, default=10000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--n-action-steps", type=int, default=50)
    parser.add_argument("--dtype", choices=["float32", "bfloat16"], default="bfloat16")
    parser.add_argument("--device", default=None)
    parser.add_argument("--no-gradient-checkpointing", action="store_true")
    parser.add_argument("--train-expert-only", action="store_true")
    relative_group = parser.add_mutually_exclusive_group(required=True)
    relative_group.add_argument(
        "--use-relative-actions",
        dest="use_relative_actions",
        action="store_true",
        help="Train pi0 with relative actions. Required to make the action convention explicit.",
    )
    relative_group.add_argument(
        "--no-use-relative-actions",
        dest="use_relative_actions",
        action="store_false",
        help="Train pi0 without relative actions. Required to make the action convention explicit.",
    )
    parser.add_argument(
        "--normalization-source",
        choices=[PI0_NORMALIZATION_SOURCE_LEROBOT],
        default=PI0_NORMALIZATION_SOURCE_LEROBOT,
        help="Phase B pi0 training delegates action/state normalization to LeRobot.",
    )
    parser.add_argument("--return-uint8", action="store_true", default=True)
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable summary.")
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    dataset_root = Path(args.dataset_root)
    if not dataset_root.exists():
        raise FileNotFoundError(f"LeRobotDataset root does not exist: {dataset_root}")

    repo_id = args.repo_id or infer_lerobot_repo_id(str(dataset_root))
    dataset = load_lerobot_policy_dataset(
        str(dataset_root),
        repo_id=repo_id,
        video_backend=args.video_backend,
        return_uint8=True,
    )
    sample_indices = sorted({0, min(max(len(dataset) - 1, 0), 1), max(len(dataset) - 1, 0)})
    lengths = _read_episode_lengths(dataset_root)
    output_dir = str(Path(args.save_root) / args.exp_name)
    command = build_lerobot_train_command(
        python_executable=args.python_executable,
        dataset_root=str(dataset_root),
        repo_id=repo_id,
        output_dir=output_dir,
        policy_path=args.policy_path,
        video_backend=args.video_backend,
        steps=args.steps,
        save_freq=args.save_freq,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        chunk_size=args.chunk_size,
        n_action_steps=args.n_action_steps,
        dtype=args.dtype,
        device=args.device,
        gradient_checkpointing=not args.no_gradient_checkpointing,
        train_expert_only=args.train_expert_only,
        use_relative_actions=args.use_relative_actions,
        return_uint8=args.return_uint8,
        normalization_source=args.normalization_source,
    )

    warnings = []
    if lengths and min(lengths) < args.chunk_size:
        warnings.append(
            f"min episode length {min(lengths)} is shorter than pi0 chunk_size {args.chunk_size}; "
            "this is fine for smoke readback but not for full pi0 training."
        )

    summary = {
        "repo_id": repo_id,
        "dataset_root": str(dataset_root),
        "num_frames": int(dataset.num_frames),
        "num_episodes": int(dataset.num_episodes),
        "fps": int(dataset.fps),
        "episode_length_min": min(lengths) if lengths else None,
        "episode_length_max": max(lengths) if lengths else None,
        "samples": _sample_summary(dataset, sample_indices),
        "output_dir": output_dir,
        "checkpoint_pretrained_dir_example": str(
            Path(output_dir) / "checkpoints" / f"{args.steps:06d}" / "pretrained_model"
        ),
        "resume_note": (
            "恢复训练时，在训练命令中额外添加 `--resume true "
            "--config_path=<用户自己填写的 train_config.json 路径>`。"
            "例如 20000 step checkpoint 通常对应 "
            f"`{Path(output_dir) / 'checkpoints' / '020000' / 'pretrained_model' / 'train_config.json'}`，"
            "但请以服务器实际存在的路径为准。"
        ),
        "normalization_source": args.normalization_source,
        "normalization_note": (
            "LeRobot PI0Policy owns STATE/ACTION normalization through dataset stats and policy "
            "pre/postprocessors; agent_factory action normalization is intentionally disabled."
        ),
        "warnings": warnings,
        "command": command,
    }

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    print(f"[pi0-b1] repo_id={summary['repo_id']} root={summary['dataset_root']}")
    print(
        "[pi0-b1] dataset "
        f"frames={summary['num_frames']} episodes={summary['num_episodes']} fps={summary['fps']}"
    )
    print(
        "[pi0-b1] episode_length "
        f"min={summary['episode_length_min']} max={summary['episode_length_max']}"
    )
    print(f"[pi0-b1] normalization_source={summary['normalization_source']}")
    print(f"[pi0-b1] normalization_note={summary['normalization_note']}")
    for warning in warnings:
        print(f"[pi0-b1] WARNING: {warning}")
    print("[pi0-b1] sample getitem:")
    for sample in summary["samples"]:
        print(f"  {sample}")
    print("[pi0-b1] checkpoint pretrained dir example:")
    print(f"  {summary['checkpoint_pretrained_dir_example']}")
    print("[pi0-b1] resume training note:")
    print(f"  {summary['resume_note']}")
    print("[pi0-b1] server train command:")
    print(_format_command(command))
    print("[pi0-b1] 单卡训练示例（只使用第 0 张 GPU）：")
    print("CUDA_VISIBLE_DEVICES=0 " + _format_command(command))
    print("[pi0-b1] 恢复训练示例（在训练命令末尾额外添加；config_path 需要用户自己填写）：")
    print("  --resume true \\")
    print("  --config_path=<path/to/checkpoint/pretrained_model/train_config.json>")
    print("[pi0-b1] 多卡训练示例（使用第 0,1 张 GPU；batch_size 通常是每卡/每进程 batch）：")
    print(
        "CUDA_VISIBLE_DEVICES=0,1 accelerate \\\n"
        "  launch \\\n"
        "  --num_processes 2 \\\n"
        "  -m lerobot.scripts.lerobot_train \\"
    )
    print(
        "[pi0-b1] 说明：LeRobot 主要通过 CUDA_VISIBLE_DEVICES/accelerate 选择 GPU；"
        "没有类似每卡 max_memory 的 pi0 CLI 参数。OOM 时优先降低 --batch_size。"
    )


if __name__ == "__main__":
    main()
