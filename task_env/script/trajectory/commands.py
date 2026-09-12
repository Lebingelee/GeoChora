"""Collect, replay and merge grouped TaskEnv trajectory containers.

The command intentionally keeps the public surface small.  Collection creates
absolute-pose/world source trajectories; replay applies an optional YAML
override and records the target controller's observations into the same
``traj_000`` container layout; merge packs all H5 files in a directory.
"""

from __future__ import annotations

import argparse
import copy
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import h5py
import numpy as np
import yaml

if __package__ in (None, ""):
    from pathlib import Path as _Path
    import sys as _sys

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import configure_imports
else:
    from .._bootstrap import configure_imports

configure_imports()

from task_env.utils.runtime_support import get_task_env_logger
from task_env import make_env
from task_env.recorders import (
    RecorderConfig,
    TransitionRecordWrapper,
    append_trajectory_collection_h5,
    save_trajectory_collection_h5,
)
from ._task_plans import _build_plan
from task_env.trajectory.metadata import load_metadata
from task_env.trajectory.processing import (
    merge_trajectory_collections,
    transcode_actions,
)
from task_env.trajectory.replay import _public_config


logger = get_task_env_logger("simulation", module="task-env-trajectory")


def _load_mapping(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"configuration root must be a mapping: {path}")
    return dict(value)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _trajectory_names(root: h5py.File) -> list[str | None]:
    if str(root.attrs.get("container_type", "")) == "trajectory_collection":
        names = sorted(name for name in root if str(name).startswith("traj_"))
        if not names:
            raise ValueError("trajectory collection is empty")
        return names
    return [None]


def _copy_trajectory_to_file(source: Path, group_name: str | None, target: Path) -> None:
    with h5py.File(source, "r") as src, h5py.File(target, "w") as out:
        source_group = src[group_name] if group_name is not None else src
        for name in source_group:
            source_group.copy(name, out, name=name)
        for key, value in source_group.attrs.items():
            out.attrs[key] = value


def _read_metadata(path: Path, group_name: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    with h5py.File(path, "r") as root:
        group = root[group_name] if group_name is not None else root
        env_meta = load_metadata(_text(group["meta/env_meta"]))
        env_cfg = load_metadata(_text(group["meta/env_cfg"]))
        if not isinstance(env_meta, dict) or not isinstance(env_cfg, dict):
            raise ValueError("trajectory metadata must be mappings")
        return env_meta, env_cfg


def _text(dataset: h5py.Dataset) -> str:
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _actions(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as root:
        env_meta = load_metadata(_text(root["meta/env_meta"]))
        order = list(env_meta.get("action_order", []))
        if not order:
            schema = env_meta.get("action_schema", {})
            order = list(schema.get("order", [])) if isinstance(schema, dict) else []
        if not order:
            raise ValueError("env_meta.action.order is required")
        return np.stack([np.asarray(root[f"action/{name}"]).reshape(-1) for name in order], axis=1).astype(np.float32)


def _context(env_meta: dict[str, Any], path: Path) -> dict[str, Any]:
    context = env_meta.get("replay_context")
    if isinstance(context, dict) and "seed" in context:
        return context
    with h5py.File(path, "r") as root:
        if "meta/episode_meta" in root:
            episode = load_metadata(_text(root["meta/episode_meta"]))
            reset = episode.get("reset_info", {}) if isinstance(episode, dict) else {}
            if isinstance(reset, dict) and "seed" in reset:
                return {"seed": reset["seed"], "options": reset.get("options", {})}
    raise ValueError("trajectory requires replay_context.seed")


def _source_protocol(env_meta: dict[str, Any]) -> tuple[str, str | None]:
    protocol = env_meta.get("action_protocol", {})
    mode = protocol.get("mode", {}).get("arm") if isinstance(protocol, dict) else None
    reference = protocol.get("reference") if isinstance(protocol, dict) else None
    if mode == "absolute":
        return "absolute_pose", reference or "world"
    if mode == "delta":
        return "delta_pose", reference
    if mode == "absolute_joint":
        return "absolute_joint", None
    action = env_meta.get("action", {})
    return str(action.get("controller_kind", "absolute_pose")), action.get("reference", "world")


def _target_protocol(config: Mapping[str, Any], source: tuple[str, str | None]) -> tuple[str, str | None]:
    controller = config.get("target_controller", config.get("controller", {}))
    if not isinstance(controller, Mapping) or not controller:
        return source
    kind = str(controller.get("kind", source[0]))
    reference = controller.get("reference", source[1])
    if kind == "absolute_joint":
        reference = None
    return kind, None if reference is None else str(reference)


def _reward_mode(config: Mapping[str, Any]) -> str:
    mode = str(config.get("reward_mode", "defined"))
    if mode not in {"defined", "sparse"}:
        raise ValueError("replay.reward_mode must be defined or sparse")
    return mode


def _apply_reward_mode(trajectory, mode: str):
    if mode == "defined":
        return trajectory
    # The first replay contract deliberately uses the minimal sparse reward:
    # one on a successful transition and zero otherwise.  Task-specific dense
    # terms remain available in info/reward_terms.
    return replace(
        trajectory,
        rewards=tuple(1.0 if success else 0.0 for success in trajectory.successes),
    )


def _select_observation(value: Any, keys: list[str], prefix: str = "") -> Any:
    """Keep selected dotted leaf/group paths from a nested observation tree."""

    if not keys:
        return copy.deepcopy(value)
    if isinstance(value, Mapping):
        selected: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if path in keys:
                selected[str(key)] = copy.deepcopy(child)
                continue
            if any(item.startswith(f"{path}.") for item in keys):
                nested = _select_observation(child, keys, path)
                if isinstance(nested, Mapping) and nested:
                    selected[str(key)] = nested
        return selected
    return copy.deepcopy(value) if prefix in keys else None


def _apply_observation_selection(trajectory, keys: list[str] | None):
    if not keys:
        return trajectory
    observations = tuple(_select_observation(item, keys) for item in trajectory.observations)
    if not observations or not isinstance(observations[0], Mapping) or not observations[0]:
        raise ValueError("replay observation.keys selected no recorded observation leaves")
    return replace(trajectory, observations=observations)


def _validate_collect_config(config: Mapping[str, Any]) -> None:
    controller = config.get("robot", {}).get("controller", {})
    if controller.get("kind") != "absolute_pose" or controller.get("reference") != "world":
        raise ValueError("collect requires robot.controller kind=absolute_pose and reference=world")


def _collect(args: argparse.Namespace) -> Path:
    config, _ = _build_plan(
        args.env_id,
        args.backend,
        args.horizon,
        camera_obs=bool(not args.no_render),
        force_limit_N=args.gripper_force,
        camera_size=args.camera_size,
    )
    config = _deep_merge(config, _load_mapping(args.env_config))
    _validate_collect_config(config)
    recorder_config = RecorderConfig(max_transitions=args.horizon, meta_only=True)
    env = TransitionRecordWrapper(make_env(args.env_id, config=config), recorder_config)
    try:
        success_index = 0
        attempt_index = 0
        max_attempts = int(getattr(args, "max_attempts", args.num_traj))
        while success_index < args.num_traj:
            if attempt_index >= max_attempts:
                raise RuntimeError(
                    f"collect exhausted {max_attempts} seeds with only "
                    f"{success_index}/{args.num_traj} successful trajectories"
                )
            seed = args.seed + attempt_index
            attempt_index += 1
            _, solution = _build_plan(
                args.env_id,
                args.backend,
                args.horizon,
                camera_obs=bool(not args.no_render),
                force_limit_N=args.gripper_force,
                camera_size=args.camera_size,
            )
            observation, info = env.reset(seed=seed)
            env.start_record()
            solution.reset(observation, info, env.metadata)
            last_action = None
            while not solution.done and not solution.failed:
                decision = solution.act(observation, info)
                last_action = decision.action
                observation, reward, terminated, truncated, info = env.step(decision.action)
                solution.observe(observation, reward, terminated, truncated, info)
            # Keep the successful absolute pose for a short, recorded hold.
            # This is collection-only stabilization; task success remains the
            # environment's 10 cm ``is_success`` predicate.
            if solution.done and not solution.failed and last_action is not None:
                for _ in range(10):
                    observation, reward, terminated, truncated, info = env.step(last_action)
            if env.recorder.active:
                env.end_record()
            if not (solution.done and not solution.failed and bool(info.get("is_success", False))):
                logger.warning(
                    "Skipping unsuccessful collection seed",
                    seed=seed,
                    failure_reason=solution.failure_reason,
                    final_lift=float(info.get("task_metrics", {}).get("cube_lift", 0.0)),
                )
                continue
            if env.recorder.frozen is None:
                raise RuntimeError("collect did not produce a frozen trajectory")
            transition_count = env.recorder.frozen.transition_count
            if not 80 <= transition_count <= 120:
                raise RuntimeError(
                    f"collect rejected seed {seed}: T={transition_count} is outside [80, 120]"
                )
            append_trajectory_collection_h5(
                env.recorder.frozen,
                recorder_config,
                path=args.output.parent,
                name=args.output.name,
                index=success_index,
            )
            success_index += 1
    finally:
        env.close()
    output = args.output
    logger.success("TaskEnv trajectory collection recorded", output=str(output), trajectory_count=args.num_traj, attempts=attempt_index)
    return output


def _replay_one(source_path: Path, group_name: str | None, replay_config: dict[str, Any], args: argparse.Namespace):
    reward_mode = _reward_mode(replay_config)
    with tempfile.TemporaryDirectory(prefix="task-env-replay-") as directory:
        source = Path(directory) / "source.h5"
        _copy_trajectory_to_file(source_path, group_name, source)
        env_meta, env_cfg = _read_metadata(source, None)
        source_protocol = _source_protocol(env_meta)
        target_protocol = _target_protocol(replay_config, source_protocol)
        observation_override = replay_config.get("observation") or replay_config.get("env_overrides", {}).get("observation")
        if observation_override and not isinstance(observation_override, Mapping):
            raise ValueError("replay observation override must be a mapping")
        observation_keys = None
        if isinstance(observation_override, Mapping) and observation_override.get("keys") is not None:
            observation_keys = [str(item) for item in observation_override["keys"]]
        simulator = str(replay_config.get("simulator", "auto"))
        if simulator not in {"auto", "always", "never"}:
            raise ValueError("replay.simulator must be auto, always, or never")
        changed = target_protocol != source_protocol or bool(observation_override)
        if changed and simulator == "never":
            raise ValueError("simulator=never is invalid when controller or observation changes")
        target = source
        if target_protocol != source_protocol:
            converted = Path(directory) / "converted.h5"
            transcode_actions(
                source,
                converted,
                target_mode=target_protocol[0],
                target_reference=target_protocol[1],
                mode=str(replay_config.get("conversion_mode", "strict")),
            )
            target = converted
            env_meta, env_cfg = _read_metadata(target, None)
        context = _context(env_meta, target)
        protocol = env_meta.get("action_protocol", {})
        config = _public_config(env_cfg, protocol, args.backend)
        overrides = replay_config.get("env_overrides", {})
        if isinstance(overrides, Mapping):
            config = _deep_merge(config, overrides)
        if isinstance(observation_override, Mapping):
            env_observation_override = {
                key: value
                for key, value in observation_override.items()
                if key in {"schema_version", "include_privileged_state"}
            }
            params = observation_override.get("params")
            if isinstance(params, Mapping):
                env_observation_override = _deep_merge(
                    env_observation_override,
                    {
                        key: value
                        for key, value in params.items()
                        if key in {"schema_version", "include_privileged_state"}
                    },
                )
            config["observation"] = _deep_merge(config.get("observation", {}), env_observation_override)
        if args.vis:
            config.setdefault("render", {})["camera_obs"] = True
        actions = _actions(target)
        episode = dict(config.get("episode", {}))
        episode["horizon"] = max(int(episode.get("horizon", 1)), int(actions.shape[0]))
        config["episode"] = episode
        env = TransitionRecordWrapper(
            make_env(str(env_cfg.get("task", {}).get("task_uid", "")), config=config),
            RecorderConfig(max_transitions=max(1, actions.shape[0]), meta_only=True),
        )
        failed = False
        try:
            observation, info = env.reset(seed=context["seed"], options=context.get("options") or None)
            env.start_record()
            for action in actions:
                observation, reward, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    break
            if env.recorder.active:
                env.end_record()
            if env.recorder.frozen is None:
                raise RuntimeError("replay did not produce a frozen trajectory")
            trajectory = _apply_observation_selection(env.recorder.frozen, observation_keys)
            trajectory = _apply_reward_mode(trajectory, reward_mode)
            failed = bool(info.get("task_failure", False))
            report = {
                "failed": failed,
                "source_protocol": source_protocol,
                "target_protocol": target_protocol,
                "simulator": simulator,
                "reward_mode": reward_mode,
            }
            env_metadata = trajectory.record_metadata.get("env_metadata", {})
            if isinstance(env_metadata, dict):
                env_metadata["replay_request"] = report
            if failed and not bool(replay_config.get("save_failures", False)):
                return None, report
            return trajectory, report
        except Exception as exc:
            failed = True
            if env.recorder.active:
                try:
                    env.end_record()
                except Exception:
                    pass
            if not bool(replay_config.get("save_failures", False)):
                raise
            if env.recorder.frozen is None:
                raise RuntimeError(f"replay failed before a trajectory could be saved: {exc}") from exc
            trajectory = _apply_observation_selection(env.recorder.frozen, observation_keys)
            trajectory = _apply_reward_mode(trajectory, reward_mode)
            report = {
                "failed": failed,
                "error": str(exc),
                "source_protocol": source_protocol,
                "target_protocol": target_protocol,
                "simulator": simulator,
                "reward_mode": reward_mode,
            }
            env_metadata = trajectory.record_metadata.get("env_metadata", {})
            if isinstance(env_metadata, dict):
                env_metadata["replay_request"] = report
            return trajectory, report
        finally:
            env.close()


def _replay(args: argparse.Namespace) -> Path:
    replay_config = _load_mapping(args.replay_config)
    env_overrides = replay_config.get("env_overrides", {})
    if not isinstance(env_overrides, Mapping):
        raise ValueError("replay.env_overrides must be a mapping")
    simulator = str(replay_config.get("simulator", "auto"))
    if simulator not in {"auto", "always", "never"}:
        raise ValueError("replay.simulator must be auto, always, or never")
    has_target_override = bool(
        replay_config.get("target_controller")
        or replay_config.get("controller")
        or replay_config.get("observation")
        or env_overrides.get("observation")
        or replay_config.get("reward_mode")
        or args.vis
    )
    if simulator == "never" and has_target_override:
        raise ValueError("simulator=never requires no controller, observation, reward, or visualization override")
    if simulator == "auto" and not has_target_override:
        output = args.output or args.trajectory.with_name(f"{args.trajectory.stem}-replay.h5")
        merge_trajectory_collections([args.trajectory], output)
        logger.success("TaskEnv trajectory replay copied without simulator", output=str(output))
        return output
    trajectories = []
    reports = []
    with h5py.File(args.trajectory, "r") as root:
        names = _trajectory_names(root)
    for name in names:
        trajectory, report = _replay_one(args.trajectory, name, replay_config, args)
        if trajectory is not None:
            trajectories.append(trajectory)
        reports.append(report)
    if not trajectories:
        raise RuntimeError("replay produced no trajectories; all failures were filtered")
    output = args.output or args.trajectory.with_name(f"{args.trajectory.stem}-replay.h5")
    save_trajectory_collection_h5(
        trajectories,
        RecorderConfig(max_transitions=max(1, max(item.transition_count for item in trajectories)), meta_only=True),
        path=output.parent,
        name=output.name,
    )
    logger.success("TaskEnv trajectory replay completed", output=str(output), trajectory_count=len(trajectories), reports=reports)
    return output


def _merge(args: argparse.Namespace) -> Path:
    paths = sorted(path for path in args.input_dir.glob("*.h5") if path.resolve() != args.output.resolve())
    if not paths:
        raise ValueError(f"no H5 files found in {args.input_dir}")
    output = merge_trajectory_collections(paths, args.output)
    logger.success("TaskEnv trajectory collections merged", output=str(output), source_count=len(paths))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="collect source trajectories")
    collect.add_argument("--env_id", required=True)
    collect.add_argument("--env_config", type=Path)
    collect.add_argument("--output", type=Path, default=Path("trajectories.h5"))
    collect.add_argument("--num-traj", type=int, default=1)
    collect.add_argument("--seed", type=int, default=19)
    collect.add_argument("--backend", choices=("cpu", "vulkan", "cuda"), default="cpu")
    collect.add_argument("--horizon", type=int, default=600)
    collect.add_argument("--gripper-force", type=float, default=30.0)
    collect.add_argument("--vis", action="store_true")
    collect.add_argument("--no-render", action="store_true")
    collect.add_argument("--camera-size", type=int, default=64)
    collect.add_argument("--max-attempts", type=int, default=200)
    collect.set_defaults(handler=_collect)

    replay = subparsers.add_parser("replay", help="replay a trajectory collection")
    replay.add_argument("--trajectory", type=Path, required=True)
    replay.add_argument("--replay_config", type=Path)
    replay.add_argument("--output", type=Path)
    replay.add_argument("--backend", choices=("cpu", "vulkan", "cuda"), default="cpu")
    replay.add_argument("--vis", action="store_true")
    replay.set_defaults(handler=_replay)

    merge = subparsers.add_parser("merge", help="merge all H5 files in a directory")
    merge.add_argument("--input_dir", type=Path, required=True)
    merge.add_argument("--output", type=Path)
    merge.set_defaults(handler=_merge)

    args = parser.parse_args()
    if args.command == "collect":
        if args.num_traj < 1:
            parser.error("--num-traj must be positive")
        if args.output.suffix != ".h5":
            parser.error("--output must end with .h5")
    elif args.command == "merge":
        if args.output is None:
            args.output = args.input_dir.with_name(f"{args.input_dir.name}-merged.h5")
    args.handler(args)


if __name__ == "__main__":
    main()
