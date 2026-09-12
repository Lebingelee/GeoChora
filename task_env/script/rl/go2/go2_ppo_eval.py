"""Evaluate a current-RSL Go2 checkpoint on a held-out TaskEnv rollout.

This is a private Stage 16 report script.  It deliberately constructs the
same public task factory path as ``rsl_ppo.py`` and only owns evaluation
bookkeeping; it does not add a task-specific runtime or alter reward/done
semantics.  A report with positive return is necessary, but not sufficient,
for the final Isaac/MuJoCo/GeoPhys walking gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import time

import numpy as np

from task_env.utils._device_stack import preload_device_stack


class _ProgressLogger:
    """Small flush-on-event logger for separating setup from rollout cost."""

    def __init__(self, path: Path | None, *, interval: int) -> None:
        self.path = path
        self.interval = max(1, int(interval))
        self.started = time.perf_counter()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, **fields: object) -> None:
        record = {
            "elapsed_s": round(time.perf_counter() - self.started, 6),
            "event": str(event),
            **fields,
        }
        line = json.dumps(record, sort_keys=True, default=str)
        print(f"[go2_ppo_eval] {line}", flush=True)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def _batch_numpy(value, batch_size: int, *, dtype=np.float64) -> np.ndarray:
    """Read one named evaluator metric at the diagnostic boundary."""

    if hasattr(value, "detach"):
        value = value.detach().to("cpu").numpy()
    array = np.asarray(value, dtype=dtype)
    if array.ndim == 0:
        array = np.full(batch_size, array.item(), dtype=dtype)
    if array.shape != (batch_size,):
        array = np.asarray(array).reshape(batch_size)
    return array


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--env-id", default="go2-walk-v1")
    parser.add_argument("--env-config", type=Path, default=None, metavar="YAML")
    parser.add_argument("--num-env", type=int, default=32)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--sim-device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--rl-device", default="cuda:0")
    parser.add_argument("--output-dir", type=Path, default=Path("temp_outputs/task_env/go2_eval"))
    parser.add_argument("--output", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--progress-log", type=Path, default=None, help="write flush-on-event JSONL timing diagnostics")
    parser.add_argument("--progress-interval", type=int, default=10, help="rollout steps between progress events")
    args = parser.parse_args()
    progress = _ProgressLogger(args.progress_log, interval=int(args.progress_interval))
    progress.emit("parsed_args", checkpoint=str(args.checkpoint), num_env=int(args.num_env), steps=int(args.steps), sim_device=str(args.sim_device), rl_device=str(args.rl_device))
    if int(args.num_env) < 1 or int(args.steps) < 1:
        parser.error("--num-env and --steps must be positive")
    if not args.checkpoint.is_file():
        parser.error(f"checkpoint does not exist: {args.checkpoint}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_output = args.output or (args.output_dir / "eval.json")
    h5_output = args.output_dir / "eval.h5"
    progress.emit("validated_paths", json_output=str(json_output), h5_output=str(h5_output))

    preload = preload_device_stack(request_triton=str(args.sim_device) == "cuda")
    import torch
    progress.emit("learner_dependencies_imported", torch_version=str(torch.__version__))
    progress.emit("device_stack_preloaded", **preload.to_dict())

    from task_env import make_parallel_env
    from task_env.alg.rsl_rl import (
        TaskEnvRslVecAdapter,
        resolve_learner_profile,
        resolve_task_action_profile,
    )
    from task_env.alg.rsl_rl.runner import build_runner
    from task_env.alg.rsl_rl.training import current5_train_cfg
    from task_env.environment.configuration import load_yaml_mapping

    torch.manual_seed(int(args.seed))
    np.random.seed(int(args.seed))
    env_config = (
        dict(load_yaml_mapping(args.env_config)) if args.env_config is not None else {}
    )
    env_config["base_seed"] = int(args.seed)
    raw_env = make_parallel_env(
        str(args.env_id),
        env_config=env_config,
        num_env=int(args.num_env),
        backend=args.sim_device,
        execution="local",
    )
    raw_metadata = getattr(raw_env, "metadata", {})
    if not isinstance(raw_metadata, dict):
        raw_metadata = {}
    progress.emit("raw_env_created", num_env=int(args.num_env), backend=str(args.sim_device), metadata_keys=sorted(raw_metadata))
    layout = str(raw_metadata.get("batch_physics_layout", "unknown"))
    transfer_mode = (
        "device" if callable(getattr(raw_env, "step_device", None)) else "host_numpy"
    )
    resolved_config = raw_env.get_record_metadata().get("resolved_config", {})
    runtime_config = (
        resolved_config.get("runtime", {})
        if isinstance(resolved_config, dict)
        else {}
    )
    learner_profile = resolve_learner_profile(
        resolve_task_action_profile(str(args.env_id), config=env_config)
    )
    action_profile = learner_profile.action
    adapter = TaskEnvRslVecAdapter(
        raw_env,
        device=args.rl_device,
        transfer_mode=transfer_mode,
        action_profile=action_profile,
        observation_profile=learner_profile.observation,
    )
    progress.emit("adapter_created", contract=adapter.contract.manifest(), transfer_mode=str(transfer_mode), action_profile=action_profile.manifest())
    # Isaac/legged_gym exports policy_*.pt as a TorchScript actor-only
    # archive.  Current RSL-RL model_N.pt remains on the normal public runner
    # load path; the actor-only branch avoids inventing a critic/optimizer just
    # to evaluate a foreign inference artifact.
    torchscript_policy = None
    checkpoint_format = "rsl_rl_state_dict"
    try:
        torchscript_policy = torch.jit.load(
            str(args.checkpoint), map_location=args.rl_device
        )
        torchscript_policy.eval()
    except RuntimeError:
        torchscript_policy = None
    if torchscript_policy is not None:
        checkpoint_format = "torchscript_actor"
        progress.emit("checkpoint_loaded", checkpoint=str(args.checkpoint), checkpoint_format=checkpoint_format)
        policy = None
    else:
        runner = build_runner(
            adapter,
            current5_train_cfg(
                rollout_steps=2,
                save_interval=100,
                observation_groups={
                    "actor": list(adapter.actor_observation_groups),
                    "critic": list(adapter.critic_observation_groups),
                },
            ),
            device=args.rl_device,
        )
        progress.emit("runner_created", rsl_api="current_5", device=str(args.rl_device))
        # Do not require a foreign optimizer state: the evaluation runner
        # creates a fresh optimizer and loads inference weights through the
        # public RSL-RL load boundary.
        runner.load(
            str(args.checkpoint),
            load_cfg={
                "actor": True,
                # Evaluation only needs the actor.  Keeping the critic
                # optional also lets old actor-compatible checkpoints be
                # inspected after a privileged-critic profile change.
                "critic": False,
                "optimizer": False,
                "iteration": False,
                "rnd": False,
            },
            strict=True,
        )
        progress.emit("checkpoint_loaded", checkpoint=str(args.checkpoint), checkpoint_format=checkpoint_format)
        policy = runner.get_inference_policy(device=args.rl_device)
    progress.emit("policy_ready")
    returns = np.zeros(int(args.num_env), dtype=np.float64)
    lengths = np.zeros(int(args.num_env), dtype=np.int64)
    completed_returns: list[float] = []
    completed_lengths: list[int] = []
    terminated_count = 0
    truncated_count = 0
    reward_sum = 0.0
    reward_samples: list[np.ndarray] = []
    metric_samples: dict[str, list[np.ndarray]] = defaultdict(list)
    reward_term_samples: dict[str, list[np.ndarray]] = defaultdict(list)
    episode_metric_sums: dict[str, np.ndarray] = {}
    completed_episode_metrics: dict[str, list[float]] = defaultdict(list)
    try:
        rollout_started = time.perf_counter()
        for step_index in range(int(args.steps)):
            observation = adapter.get_observations()
            with torch.no_grad():
                if torchscript_policy is not None:
                    policy_observation = (
                        observation["policy"]
                        if hasattr(observation, "keys") and "policy" in observation.keys()
                        else observation
                    )
                    action = torchscript_policy(policy_observation)
                else:
                    action = policy(observation)
            next_observation, reward, done, extras = adapter.step(action)
            reward_np = reward.detach().to("cpu").numpy().astype(np.float64, copy=False)
            done_np = done.detach().to("cpu").numpy().astype(np.bool_, copy=False)
            if isinstance(extras, dict):
                info_list = list(extras.get("infos", ()))
                terminated_extra = extras.get("terminated")
                truncated_extra = extras.get("truncated")
                terminated_np = (
                    terminated_extra.detach().to("cpu").numpy().astype(np.bool_, copy=False)
                    if hasattr(terminated_extra, "detach")
                    else np.asarray(terminated_extra if terminated_extra is not None else done_np, dtype=np.bool_)
                )
                truncated_np = (
                    truncated_extra.detach().to("cpu").numpy().astype(np.bool_, copy=False)
                    if hasattr(truncated_extra, "detach")
                    else np.asarray(truncated_extra if truncated_extra is not None else np.zeros_like(done_np), dtype=np.bool_)
                )
            else:
                info_list = list(extras)
                terminated_np = done_np.copy()
                truncated_np = np.zeros_like(done_np)

            # Keep diagnostic metrics separate from the learner contract.
            # They are read back only by this held-out report, never by the
            # training adapter's physics path.
            transition_metrics = extras.get("metrics", {}) if isinstance(extras, dict) else {}
            transition_terms = extras.get("reward_terms", {}) if isinstance(extras, dict) else {}
            named_metrics: dict[str, np.ndarray] = {}
            for name, value in transition_metrics.items():
                named_metrics[str(name)] = _batch_numpy(value, int(args.num_env))
            for name, value in transition_terms.items():
                reward_term_samples[str(name)].append(
                    _batch_numpy(value, int(args.num_env))
                )

            # The 48-d Go2 policy layout contains scaled local velocity at
            # [0:3] and scaled command at [9:12].  This reconstruction is
            # diagnostic-only and does not feed back into the task.
            policy_observation = (
                next_observation["policy"]
                if hasattr(next_observation, "keys") and "policy" in next_observation.keys()
                else next_observation
            )
            policy_values = np.asarray(
                policy_observation.detach().to("cpu").numpy()
                if hasattr(policy_observation, "detach")
                else policy_observation,
                dtype=np.float32,
            )
            if policy_values.ndim == 2 and policy_values.shape[1] >= 12:
                local_velocity = policy_values[:, :3] * 0.5
                command = policy_values[:, 9:12] / np.asarray((2.0, 2.0, 0.25), dtype=np.float32)
                named_metrics["forward_velocity"] = local_velocity[:, 0].astype(np.float64)
                named_metrics["command_velocity_x"] = command[:, 0].astype(np.float64)
                named_metrics["command_velocity_y"] = command[:, 1].astype(np.float64)
                named_metrics["command_yaw_rate"] = command[:, 2].astype(np.float64)
                named_metrics["velocity_error_x"] = (command[:, 0] - local_velocity[:, 0]).astype(np.float64)
                named_metrics["velocity_error_y"] = (command[:, 1] - local_velocity[:, 1]).astype(np.float64)
                named_metrics["command_tracking_error"] = np.linalg.norm(
                    command[:, :2] - local_velocity[:, :2], axis=-1
                ).astype(np.float64)

            for name, values in named_metrics.items():
                metric_samples[name].append(values.copy())
                if name not in episode_metric_sums:
                    episode_metric_sums[name] = np.zeros(int(args.num_env), dtype=np.float64)
                episode_metric_sums[name] += values
            returns += reward_np
            lengths += 1
            reward_sum += float(reward_np.sum())
            reward_samples.append(reward_np.copy())
            for index, is_done in enumerate(done_np):
                if not is_done:
                    continue
                info = info_list[index] if index < len(info_list) else {}
                is_truncated = bool(truncated_np[index]) or bool(info.get("TimeLimit.truncated", False)) or bool(info.get("truncated", False))
                is_terminated = bool(terminated_np[index]) or bool(info.get("terminated", False))
                truncated_count += int(is_truncated)
                terminated_count += int(is_terminated and not is_truncated)
                completed_returns.append(float(returns[index]))
                completed_lengths.append(int(lengths[index]))
                for name, values in episode_metric_sums.items():
                    completed_episode_metrics[name].append(
                        float(values[index] / max(int(lengths[index]), 1))
                    )
                    values[index] = 0.0
                returns[index] = 0.0
                lengths[index] = 0
            if (step_index + 1) % progress.interval == 0 or step_index + 1 == int(args.steps):
                elapsed = max(time.perf_counter() - rollout_started, 1.0e-9)
                progress.emit("rollout_progress", step=step_index + 1, total_steps=int(args.steps), steps_per_second=round((step_index + 1) * int(args.num_env) / elapsed, 3), completed_episodes=len(completed_returns))
    finally:
        adapter.close()
        progress.emit("adapter_closed")

    reward_values = (
        np.concatenate(reward_samples, axis=0)
        if reward_samples
        else np.zeros(0, dtype=np.float64)
    )

    def _summary(samples: dict[str, list[np.ndarray]]) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for name, values in samples.items():
            if not values:
                continue
            flattened = np.concatenate(values, axis=0)
            result[name] = {
                "mean": float(np.mean(flattened)),
                "min": float(np.min(flattened)),
                "max": float(np.max(flattened)),
            }
        return result

    episode_metric_summary = {
        name: {
            "mean": float(np.mean(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
        }
        for name, values in completed_episode_metrics.items()
        if values
    }
    metric_summary = _summary(metric_samples)
    reward_term_summary = _summary(reward_term_samples)
    report = {
        "schema": "task-env-go2-ppo-eval-v2",
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "checkpoint_format": checkpoint_format,
        "env_id": str(args.env_id),
        "runtime": runtime_config,
        "num_env": int(args.num_env),
        "steps": int(args.steps),
        "seed": int(args.seed),
        "sim_device": str(args.sim_device),
        "rl_device": str(args.rl_device),
        "batch_physics_layout": layout,
        "transfer_mode": transfer_mode,
        "execution": "local",
        "learner_contract": adapter.contract.manifest(),
        "rsl_action_profile": action_profile.manifest(),
        "runtime_resource_summary": raw_metadata.get("runtime_resource_summary"),
        "reward_sum": reward_sum,
        "mean_reward_per_env_step": reward_sum / max(1, int(args.num_env) * int(args.steps)),
        "reward_min": float(np.min(reward_values)) if reward_values.size else None,
        "reward_max": float(np.max(reward_values)) if reward_values.size else None,
        "reward_std": float(np.std(reward_values)) if reward_values.size else None,
        "reward_percentiles": {
            str(percentile): float(np.percentile(reward_values, percentile))
            for percentile in (10, 50, 90)
        } if reward_values.size else None,
        "completed_episodes": len(completed_returns),
        "mean_episode_return": float(np.mean(completed_returns)) if completed_returns else None,
        "max_episode_return": float(np.max(completed_returns)) if completed_returns else None,
        "completed_episode_return_gt_0_01_fraction": (
            float(np.mean(np.asarray(completed_returns) > 0.01))
            if completed_returns else None
        ),
        "mean_episode_length": float(np.mean(completed_lengths)) if completed_lengths else None,
        "termination_count": int(terminated_count),
        "truncated_count": int(truncated_count),
        "unfinished_envs": int(np.count_nonzero(lengths)),
        "walking_metrics": {
            "step": metric_summary,
            "reward_terms": reward_term_summary,
            "completed_episode": episode_metric_summary,
            "base_collision_fraction": (
                metric_summary.get("base_contact", {}).get("mean")
            ),
            "mean_base_height": (
                metric_summary.get("base_height", {}).get("mean")
            ),
            "mean_forward_velocity": (
                metric_summary.get("forward_velocity", {}).get("mean")
            ),
            "mean_command_tracking_error": (
                metric_summary.get("command_tracking_error", {}).get("mean")
            ),
        },
        "interpretation": "held-out learner report; not final three-engine walking acceptance",
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    from task_env.alg.rsl_rl.artifacts import write_h5_artifact

    metric_arrays = {
        f"metrics/{name}": np.stack(values, axis=0)
        for name, values in metric_samples.items()
        if values
    }
    term_arrays = {
        f"reward_terms/{name}": np.stack(values, axis=0)
        for name, values in reward_term_samples.items()
        if values
    }
    write_h5_artifact(
        h5_output,
        schema="task-env-go2-ppo-eval-v2",
        manifest={
            "checkpoint": str(args.checkpoint),
            "checkpoint_sha256": report["checkpoint_sha256"],
            "checkpoint_format": checkpoint_format,
            "num_env": int(args.num_env),
            "steps": int(args.steps),
            "seed": int(args.seed),
            "env_id": str(args.env_id),
            "batch_physics_layout": layout,
            "runtime": runtime_config,
            "sim_device": str(args.sim_device),
            "rl_device": str(args.rl_device),
            "transfer_mode": transfer_mode,
            "execution": "local",
            "rsl_action_profile": action_profile.manifest(),
        },
        arrays={
            "reward": np.stack(reward_samples, axis=0) if reward_samples else np.zeros((0, int(args.num_env))),
            **metric_arrays,
            **term_arrays,
        },
        report=report,
    )
    progress.emit("artifacts_written", json_output=str(json_output), h5_output=str(h5_output), completed_episodes=len(completed_returns))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
