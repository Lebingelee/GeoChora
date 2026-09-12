"""Explicit target-controller replay and universal-action verification."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

import h5py
import numpy as np
import yaml

from task_env.registry import make_env
from .metadata import load_metadata


class ReplayVerificationError(ValueError):
    """Replay evidence is missing, clipped, or differs from the recorded target."""

    category = "replay_failure"

    def __init__(self, message: str, *, category: str | None = None):
        super().__init__(message)
        if category is not None:
            self.category = category


def _text(dataset) -> str:
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _public_config(env_cfg: dict, protocol: dict, backend: str | None) -> dict:
    config = {
        key: env_cfg[key]
        for key in ("runtime", "robot", "observation", "render", "episode")
        if key in env_cfg
    }
    runtime = dict(config.get("runtime", {}))
    runtime["prewarm"] = False
    if backend is not None:
        runtime["backend"] = backend
    config["runtime"] = runtime
    robot = dict(config.get("robot", {}))
    controller = dict(robot.get("controller", {}))
    arm_mode = protocol.get("mode", {}).get("arm")
    if arm_mode == "absolute_joint":
        controller["kind"] = "absolute_joint"
        controller.pop("reference", None)
        controller.pop("rotation_representation", None)
    elif arm_mode == "delta":
        controller["kind"] = "delta_pose"
        controller["reference"] = protocol.get("reference")
        controller["rotation_representation"] = "quaternion_wxyz"
    elif arm_mode == "absolute":
        controller["kind"] = "absolute_pose"
        controller["reference"] = protocol.get("reference")
        controller["rotation_representation"] = "quaternion_wxyz"
    else:
        raise ReplayVerificationError(
            f"unsupported action protocol arm mode: {arm_mode!r}", category="replay_failure"
        )
    robot["controller"] = controller
    config["robot"] = robot
    return config


def _contexts(env_meta: dict, root, episode_count: int) -> list[dict]:
    merge = env_meta.get("merge")
    if isinstance(merge, dict) and isinstance(merge.get("contexts"), list):
        contexts = [item for item in merge["contexts"] if isinstance(item, dict)]
        if len(contexts) == episode_count:
            return contexts
    context = env_meta.get("replay_context")
    if isinstance(context, dict) and "seed" in context:
        return [context] * episode_count
    if "meta/episode_meta" in root:
        # Backward-compatible source reader.  Stage 11 outputs store this in env_meta.
        episode = yaml.safe_load(_text(root["meta/episode_meta"])) or {}
        reset = episode.get("reset_info", {})
        if isinstance(reset, dict) and "seed" in reset:
            return [{"seed": reset["seed"], "options": reset.get("options", {})}] * episode_count
    raise ReplayVerificationError(
        "replay requires replay_context.seed", category="missing_observation"
    )


def replay_and_verify_universal_action(
    path: str | Path,
    *,
    backend: str | None = None,
    require_exact: bool = True,
    mode: str = "strict",
    interpolation: bool | None = None,
) -> dict[str, object]:
    """Replay target actions and compare recorded universal targets.

    Strict mode checks every transition.  Interpolation mode still replays all
    transitions and reports every mismatch, but accepts replay completion while
    exposing endpoint/strict mismatch fields because inserted rows are
    controller-state-dependent.
    """
    if mode not in {"strict", "interpolation"}:
        raise ReplayVerificationError(f"unsupported replay mode: {mode}")
    if interpolation is not None:
        mode = "interpolation" if interpolation else "strict"
    with h5py.File(Path(path), "r") as root:
        if "meta/env_meta" not in root or "meta/env_cfg" not in root:
            raise ReplayVerificationError("replay requires meta/env_meta and meta/env_cfg", category="missing_observation")
        env_meta = load_metadata(_text(root["meta/env_meta"]))
        env_cfg = yaml.safe_load(_text(root["meta/env_cfg"])) or {}
        protocol = env_meta.get("action_protocol")
        if not isinstance(protocol, dict):
            raise ReplayVerificationError("replay requires action_protocol", category="missing_observation")
        task_uid = str(env_cfg.get("task", {}).get("task_uid", ""))
        if not task_uid:
            raise ReplayVerificationError("env_cfg.task.task_uid is required for replay", category="missing_observation")
        order = list(env_meta.get("action_order", []))
        if not order:
            schema = env_meta.get("action_schema", {})
            order = list(schema.get("order", [])) if isinstance(schema, dict) else []
        if not order:
            raise ReplayVerificationError("env_meta.action.order is required for replay", category="missing_observation")
        try:
            actions = np.stack([np.asarray(root[f"action/{name}"]).reshape(-1) for name in order], axis=1).astype(np.float32)
            expected = np.concatenate(
                [np.asarray(root["universal_action/arm_joint_position"]), np.asarray(root["universal_action/gripper"])],
                axis=1,
            ).astype(np.float32)
        except KeyError as exc:
            raise ReplayVerificationError(f"missing replay dataset: {exc}", category="missing_observation") from exc
        if expected.shape != (actions.shape[0], 8):
            raise ReplayVerificationError("universal_action and action transition counts differ", category="data_bounds")
        merge = env_meta.get("merge", {})
        boundaries = merge.get("episode_boundaries") if isinstance(merge, dict) else None
        if not isinstance(boundaries, list) or not boundaries:
            boundaries = [0, int(actions.shape[0])]
        if boundaries and isinstance(boundaries[0], dict):
            boundaries = [0] + [int(item["merged_transition_end"]) for item in boundaries]
        boundaries = [int(item) for item in boundaries]
        if boundaries[0] != 0 or boundaries[-1] != actions.shape[0] or any(b1 > b2 for b1, b2 in zip(boundaries, boundaries[1:])):
            raise ReplayVerificationError("invalid merged episode boundaries", category="data_bounds")
        contexts = _contexts(env_meta, root, len(boundaries) - 1)
        if any("seed" not in context for context in contexts):
            raise ReplayVerificationError(
                "replay context is missing seed for one or more episodes",
                category="missing_observation",
            )
    try:
        env = make_env(task_uid, config=_public_config(env_cfg, protocol, backend))
    except (ValueError, KeyError, RuntimeError) as exc:
        raise ReplayVerificationError(
            f"target controller/configuration could not be constructed: {exc}",
            category="controller_boundary",
        ) from exc
    mismatches: list[dict[str, object]] = []
    compared = 0
    endpoint_indices: list[int] = []
    final_success = False
    final_info: dict[str, object] = {}
    try:
        for episode_index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            observation, info = env.reset(seed=contexts[episode_index]["seed"], options=contexts[episode_index].get("options") or None)
            del observation, info
            for index in range(start, end):
                try:
                    _, _, terminated, truncated, info = env.step(actions[index])
                    final_success = bool(info.get("is_success", False))
                    final_info = dict(info)
                except (ValueError, RuntimeError) as exc:
                    raise ReplayVerificationError(
                        f"controller rejected transition {index}: {exc}", category="controller_boundary"
                    ) from exc
                actual = np.asarray(info["universal_action"], dtype=np.float32).reshape(1, -1)
                wanted = expected[index : index + 1]
                compared += 1
                error = float(np.max(np.abs(actual - wanted)))
                if index == end - 1:
                    endpoint_indices.append(index)
                if not np.allclose(actual, wanted, rtol=0.0, atol=1.0e-4):
                    mismatches.append({
                        "index": index,
                        "max_abs_error": error,
                        "actual": actual.reshape(-1).tolist(),
                        "expected": wanted.reshape(-1).tolist(),
                    })
                if (terminated or truncated) and index + 1 < end:
                    raise ReplayVerificationError(
                        f"target episode ended before transition {end}", category="replay_failure"
                    )
    finally:
        env.close()
    endpoint_mismatches = [item for item in mismatches if int(item["index"]) in endpoint_indices]
    # Interpolation explicitly permits controller-state-dependent universal
    # differences at inserted rows (and at the replayed endpoint after a
    # long chain).  The converted H5 endpoint invariant is checked by the
    # transform provenance; this report keeps the replay mismatch visible and
    # never labels it strict-equivalent.
    accepted = not mismatches if mode == "strict" else True
    report = {
        "compared": compared,
        "match": accepted,
        "strict_match": not mismatches,
        "endpoint_match": not endpoint_mismatches,
        "replay_completed": True,
        "final_is_success": final_success,
        "final_info": final_info,
        "final_lift": float(
            dict(final_info.get("task_metrics", {})).get("cube_lift", 0.0)
        ) if isinstance(final_info.get("task_metrics", {}), Mapping) else 0.0,
        "final_cube_pose": [
            float(dict(final_info.get("task_metrics", {})).get(key, 0.0))
            for key in ("cube_x", "cube_y", "cube_z")
        ] if isinstance(final_info.get("task_metrics", {}), Mapping) else [],
        "mode": mode,
        "mismatch": mismatches[0] if mismatches else None,
        "mismatch_count": len(mismatches),
        "endpoint_indices": endpoint_indices,
    }
    if require_exact and mode == "strict" and not accepted:
        raise ReplayVerificationError(
            f"universal_action mismatch: {report['mismatch']}", category="replay_failure"
        )
    return report


def _replay_single_trajectory(
    path: str | Path,
    name: str,
    *,
    backend: str | None = None,
    require_exact: bool = False,
) -> dict[str, object]:
    """Replay one trajectory in one short-lived simulator process."""

    from task_env.registry import make_env

    source = Path(path)
    with h5py.File(source, "r") as root:
        if name not in root:
            raise ReplayVerificationError(f"missing trajectory group: {name}")
        group = root[name]
        env_meta = load_metadata(_text(group["meta/env_meta"]))
        env_cfg = yaml.safe_load(_text(group["meta/env_cfg"])) or {}
        order = list(env_meta.get("action_order", []))
        if not order:
            schema = env_meta.get("action_schema", {})
            order = list(schema.get("order", [])) if isinstance(schema, dict) else []
        actions = np.stack(
            [np.asarray(group[f"action/{item}"]).reshape(-1) for item in order], axis=1
        ).astype(np.float32)
        expected = np.concatenate(
            [np.asarray(group["universal_action/arm_joint_position"]), np.asarray(group["universal_action/gripper"])],
            axis=1,
        ).astype(np.float32)
        if expected.shape[0] != actions.shape[0]:
            raise ReplayVerificationError(f"{name}: action/universal_action T mismatch")
        context = env_meta.get("replay_context", {})
        if not isinstance(context, dict) or "seed" not in context:
            raise ReplayVerificationError(f"{name}: replay_context.seed is required")
        task_uid = str(env_cfg.get("task", {}).get("task_uid", ""))
        if not task_uid:
            raise ReplayVerificationError(f"{name}: env_cfg.task.task_uid is required")

    replay_config = _public_config(env_cfg, env_meta["action_protocol"], backend)
    render = dict(replay_config.get("render", {}))
    render["camera_obs"] = False
    render["cameras"] = ()
    replay_config["render"] = render
    episode = dict(replay_config.get("episode", {}))
    episode["ignore_done"] = True
    replay_config["episode"] = episode
    env = make_env(task_uid, config=replay_config)
    try:
        _, info = env.reset(seed=context["seed"], options=context.get("options") or None)
        del info
        mismatches: list[dict[str, object]] = []
        max_abs_error = 0.0
        final_info: dict[str, object] = {}
        endpoint = max(0, len(actions) - 1)
        for index, action in enumerate(actions):
            _, _, terminated, truncated, info = env.step(action)
            final_info = dict(info)
            actual = np.asarray(info["universal_action"], dtype=np.float32).reshape(1, -1)
            wanted = expected[index : index + 1]
            max_abs_error = max(max_abs_error, float(np.max(np.abs(actual - wanted))))
            if not np.allclose(actual, wanted, rtol=0.0, atol=1.0e-4):
                mismatches.append({
                    "index": index,
                    "max_abs_error": float(np.max(np.abs(actual - wanted))),
                    "actual": actual.reshape(-1).tolist(),
                    "expected": wanted.reshape(-1).tolist(),
                })
            if (terminated or truncated) and index < endpoint:
                raise ReplayVerificationError(f"{name}: episode ended before T", category="replay_failure")
        metrics = final_info.get("task_metrics", {})
        metrics = dict(metrics) if isinstance(metrics, Mapping) else {}
        report = {
            "name": name,
            "compared": int(len(actions)),
            "transition_count": int(len(actions)),
            "match": not mismatches,
            "strict_match": not mismatches,
            "endpoint_match": not mismatches or not any(item["index"] == endpoint for item in mismatches),
            "replay_completed": True,
            "final_is_success": bool(final_info.get("is_success", False)),
            "final_info": final_info,
            "final_lift": float(metrics.get("cube_lift", 0.0)),
            "final_cube_pose": [float(metrics.get(key, 0.0)) for key in ("cube_x", "cube_y", "cube_z")],
            "mode": "strict",
            "mismatch": mismatches[0] if mismatches else None,
            "mismatch_count": len(mismatches),
            "max_universal_action_abs_error": max_abs_error,
            "universal_action_atol": 1.0e-4,
        }
        if require_exact and mismatches:
            raise ReplayVerificationError(f"{name}: universal_action mismatch", category="replay_failure")
        return report
    finally:
        env.close()


def replay_and_verify_collection(
    path: str | Path,
    *,
    backend: str | None = None,
    require_exact: bool = False,
) -> list[dict[str, object]]:
    """Replay every grouped trajectory through its declared target controller."""

    source = Path(path)
    with h5py.File(source, "r") as root:
        if str(root.attrs.get("container_type", "")) != "trajectory_collection":
            raise ReplayVerificationError("expected a trajectory_collection H5")
        names = sorted(name for name in root if str(name).startswith("traj_"))
        if not names:
            raise ReplayVerificationError("trajectory collection is empty")
        first = root[names[0]]
        first_meta = load_metadata(_text(first["meta/env_meta"]))
        first_cfg = yaml.safe_load(_text(first["meta/env_cfg"])) or {}
        task_uid = str(first_cfg.get("task", {}).get("task_uid", ""))
        if not task_uid:
            raise ReplayVerificationError("collection env_cfg.task.task_uid is required")
        for name in names:
            env_meta = load_metadata(_text(root[name]["meta/env_meta"]))
            if env_meta.get("action_protocol") != first_meta.get("action_protocol"):
                raise ReplayVerificationError(f"{name}: action protocol differs within collection")

    # Every worker owns exactly one simulator and then exits.  This is the
    # replay isolation boundary required by the current Taichi CPU runtime:
    # reset caches cannot leak between trajectories, and repeated runtime
    # construction cannot accumulate in one process.  Four independent workers
    # keep the wall time bounded without sharing simulator state.
    worker_code = (
        "import json, sys\n"
        "from task_env.trajectory.replay import _replay_single_trajectory\n"
        "path, name, backend, output, exact = sys.argv[1:]\n"
        "try:\n"
        "    report = _replay_single_trajectory(path, name, backend=backend or None, require_exact=exact == '1')\n"
        "    payload = {'ok': True, 'report': report}\n"
        "except Exception as exc:\n"
        "    payload = {'ok': False, 'error': repr(exc)}\n"
        "with open(output, 'w', encoding='utf-8') as stream:\n"
        "    json.dump(payload, stream, default=str)\n"
    )
    reports: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="geophys_replay_") as temporary:
        for wave_start in range(0, len(names), 4):
            processes: list[tuple[str, Path, subprocess.Popen[bytes]]] = []
            for name in names[wave_start : wave_start + 4]:
                output = Path(temporary) / f"{name}.json"
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        worker_code,
                        str(source.resolve()),
                        name,
                        backend or "",
                        str(output),
                        "1" if require_exact else "0",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                processes.append((name, output, process))
            for name, output, process in processes:
                return_code = process.wait()
                if return_code != 0 or not output.exists():
                    raise ReplayVerificationError(
                        f"{name}: isolated replay worker failed with exit code {return_code}",
                        category="replay_failure",
                    )
                payload = json.loads(output.read_text(encoding="utf-8"))
                if not payload.get("ok"):
                    raise ReplayVerificationError(
                        f"{name}: {payload.get('error', 'isolated replay failed')}",
                        category="replay_failure",
                    )
                reports.append(dict(payload["report"]))
    return sorted(reports, key=lambda item: str(item["name"]))


__all__ = [
    "ReplayVerificationError",
    "replay_and_verify_collection",
    "replay_and_verify_universal_action",
]
