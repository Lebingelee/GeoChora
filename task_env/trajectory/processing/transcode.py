"""Offline, command-preserving H5 action conversion for TaskEnv Stage 11.

The converter never opens a simulator.  It consumes only the public H5 v2
tree and writes a new file, retaining the source action under
``source_action``.  ``mode='strict'`` is the default; ``mode='interpolation'``
inserts pose waypoints when a target delta controller would clip a command.
"""

from __future__ import annotations

import copy
import math
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .poses import (
    interpolate_pose,
    transform_absolute_world_to_target,
)
from ..metadata import dump_metadata, load_metadata


class TrajectoryValidationError(ValueError):
    """Source trajectory violates its public H5 contract."""

    category = "data_bounds"

    def __init__(self, message: str, *, category: str | None = None):
        super().__init__(message)
        if category is not None:
            self.category = category


class ActionTransformError(ValueError):
    """Requested action conversion lacks evidence or has invalid geometry."""

    category = "replay_failure"

    def __init__(self, message: str, *, category: str | None = None):
        super().__init__(message)
        if category is not None:
            self.category = category


def _materialize_group(group, target_path: Path) -> None:
    """Write one grouped trajectory as a single-trajectory H5 root."""

    import h5py

    with h5py.File(target_path, "w") as output:
        for key in group:
            group.copy(key, output, name=key)
        for key, value in group.attrs.items():
            output.attrs[key] = value


def _text(dataset) -> str:
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _leaf(root, path: str) -> np.ndarray:
    try:
        return np.asarray(root[f"obs/{path.replace('.', '/')}"])
    except KeyError as exc:
        raise TrajectoryValidationError(
            f"missing observation evidence: {path}", category="missing_observation"
        ) from exc


def _action_order(env_meta: dict[str, Any], root) -> list[str]:
    action = env_meta.get("action", {})
    order = env_meta.get("action_order")
    if not order:
        schema = env_meta.get("action_schema", {})
        order = schema.get("order") if isinstance(schema, dict) else None
    if not order and isinstance(action, dict):
        order = action.get("order") or action.get("components")
    if isinstance(order, list) and order and isinstance(order[0], dict):
        order = [item["name"] for item in order]
    if not order:
        order = sorted(root["action"].keys())
    return [str(name) for name in order]


def _action_matrix(root, order: list[str]) -> np.ndarray:
    values = []
    for name in order:
        if f"action/{name}" not in root:
            raise TrajectoryValidationError(f"missing action component: {name}")
        values.append(np.asarray(root[f"action/{name}"]).reshape(-1))
    if not values:
        return np.empty((0, 0), dtype=np.float32)
    return np.stack(values, axis=1).astype(np.float32, copy=False)


def _universal_matrix(root, transition_count: int) -> np.ndarray:
    paths = ("universal_action/arm_joint_position", "universal_action/gripper")
    if any(path not in root for path in paths):
        raise TrajectoryValidationError(
            "missing universal_action evidence for joint conversion",
            category="missing_observation",
        )
    arm = np.asarray(root[paths[0]])
    gripper = np.asarray(root[paths[1]])
    if arm.shape != (transition_count, 7) or gripper.shape != (transition_count, 1):
        raise TrajectoryValidationError(
            "universal_action must have shapes (T,7) and (T,1)",
            category="missing_observation",
        )
    result = np.concatenate([arm, gripper], axis=1).astype(np.float32, copy=False)
    if not np.isfinite(result).all():
        raise TrajectoryValidationError("universal_action contains non-finite values", category="data_bounds")
    return result


def _source_contract(env_meta: dict[str, Any]) -> dict[str, Any]:
    schema = env_meta.get("action_schema", {})
    action = env_meta.get("action", {})
    contract = schema.get("contract") if isinstance(schema, dict) else None
    if not isinstance(contract, dict) and isinstance(action, dict):
        contract = action.get("contract", action)
    if not isinstance(contract, dict):
        raise TrajectoryValidationError("env_meta.action contract must be a mapping")
    return contract


def _target_names(mode: str) -> list[str]:
    if mode == "absolute_joint":
        return ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7", "gripper"]
    if mode == "absolute_pose":
        return ["x", "y", "z", "qw", "qx", "qy", "qz", "gripper"]
    if mode == "delta_pose":
        return ["dx", "dy", "dz", "dqw", "dqx", "dqy", "dqz", "gripper"]
    raise ActionTransformError(f"unsupported target controller kind: {mode}")


def _target_contract(mode: str, reference: str | None, env_cfg: dict[str, Any]) -> dict[str, Any]:
    controller = env_cfg.get("robot", {}).get("controller", {})
    if not isinstance(controller, dict):
        controller = {}
    names = _target_names(mode)
    if mode == "absolute_joint":
        low = [-float("inf")] * 7 + [-1.0]
        high = [float("inf")] * 7 + [1.0]
        return {
            "schema_id": "task-env.absolute_joint.v1",
            "schema_version": "task-env-action-v2",
            "controller_kind": mode,
            "reference": None,
            "dimension": 8,
            "components": names,
            "low": low,
            "high": high,
            "joint_order": names[:7],
            "gripper_convention": "normalized_signed_scalar",
            "actuator_control_mode": "position",
            "controller_backend": "absolute_joint_position_servo",
        }
    if mode == "absolute_pose":
        low = [-float("inf")] * 7 + [-1.0]
        high = [float("inf")] * 7 + [1.0]
        return {
            "schema_id": "task-env.absolute_pose.quaternion_wxyz.v1",
            "schema_version": "task-env-action-v2",
            "controller_kind": mode,
            "reference": reference,
            "dimension": 8,
            "components": names,
            "low": low,
            "high": high,
            "rotation_representation": "quaternion_wxyz",
            "quaternion_convention": "wxyz",
            "gripper_convention": "normalized_signed_scalar",
            "actuator_control_mode": "position",
            "controller_backend": "dls_ik_pose_target",
        }
    translation = float(controller.get("max_translation_delta_m", 0.03))
    rotation = float(controller.get("max_rotation_delta_rad", 0.20))
    return {
        "schema_id": f"task-env.delta_pose.quaternion_wxyz.v1",
        "schema_version": "task-env-action-v2",
        "controller_kind": mode,
        "reference": reference,
        "dimension": 8,
        "components": names,
        "low": [-translation] * 3 + [-1.0] * 4 + [-1.0],
        "high": [translation] * 3 + [1.0] * 4 + [1.0],
        "rotation_representation": "quaternion_wxyz",
        "quaternion_convention": "wxyz",
        "translation_unit": "meters",
        "max_translation_delta_m": translation,
        "max_rotation_delta_rad": rotation,
        "gripper_convention": "normalized_signed_scalar",
        "actuator_control_mode": "position",
        "controller_backend": "dls_ik_pose_target",
    }


def _protocol(mode: str, reference: str | None) -> dict[str, Any]:
    return {
        "mode": {
            "arm": "absolute_joint" if mode == "absolute_joint" else ("delta" if mode == "delta_pose" else "absolute"),
            "gripper": "absolute",
        },
        "reference": reference,
    }


def _replay_context(env_meta: dict[str, Any], src) -> dict[str, Any]:
    context = env_meta.get("replay_context")
    if isinstance(context, dict) and "seed" in context:
        return context
    if "meta/episode_meta" in src:
        import yaml

        episode = yaml.safe_load(_text(src["meta/episode_meta"])) or {}
        reset = episode.get("reset_info", {})
        if isinstance(reset, dict) and "seed" in reset:
            return {"seed": reset["seed"], "options": reset.get("options", {})}
    return {}


def inspect_trajectory(path: str | os.PathLike[str]) -> dict[str, Any]:
    import h5py

    with h5py.File(Path(path), "r") as root:
        if str(root.attrs.get("container_type", "")) == "trajectory_collection":
            trajectories = []
            for name in sorted(key for key in root if str(key).startswith("traj_")):
                group = root[name]
                item = {
                    "name": name,
                    "transition_count": int(group.attrs.get("transition_count", 0)),
                    "observation_count": int(group.attrs.get("observation_count", 0)),
                    "env_meta": load_metadata(_text(group["meta/env_meta"])),
                    "env_cfg": load_metadata(_text(group["meta/env_cfg"])),
                }
                trajectories.append(item)
            return {
                "schema_id": str(root.attrs.get("schema_id", "")),
                "schema_version": str(root.attrs.get("schema_version", "")),
                "container_type": "trajectory_collection",
                "trajectory_count": len(trajectories),
                "trajectories": trajectories,
            }
        result = {
            "schema_id": str(root.attrs.get("schema_id", "")),
            "schema_version": str(root.attrs.get("schema_version", "")),
            "transition_count": int(root.attrs.get("transition_count", 0)),
            "observation_count": int(root.attrs.get("observation_count", 0)),
        }
        if "meta/env_meta" in root:
            result["env_meta"] = load_metadata(_text(root["meta/env_meta"]))
        if "meta/env_cfg" in root:
            import yaml

            result["env_cfg"] = yaml.safe_load(_text(root["meta/env_cfg"])) or {}
        if "meta/episode_meta" in root:
            import yaml

            result["episode_meta"] = yaml.safe_load(_text(root["meta/episode_meta"])) or {}
        return result


def validate_trajectory(path: str | os.PathLike[str]) -> dict[str, Any]:
    import h5py

    with h5py.File(Path(path), "r") as root:
        if str(root.attrs.get("schema_id", "")) != "task-env-h5" or str(root.attrs.get("schema_version", "")) != "v2":
            raise TrajectoryValidationError("Stage 11 conversion requires task-env-h5/v2")
        transition_count = int(root.attrs.get("transition_count", -1))
        observation_count = int(root.attrs.get("observation_count", -1))
        if transition_count < 0 or observation_count != transition_count + 1:
            raise TrajectoryValidationError(
                "trajectory must satisfy observation_count == transition_count + 1",
                category="data_bounds",
            )
        if "meta/env_meta" not in root or "meta/env_cfg" not in root:
            raise TrajectoryValidationError("v2 trajectory requires meta/env_meta and meta/env_cfg")
        env_meta = load_metadata(_text(root["meta/env_meta"]))
        if not isinstance(env_meta, dict):
            raise TrajectoryValidationError("meta/env_meta must contain a JSON object")
        order = _action_order(env_meta, root)
        action = _action_matrix(root, order)
        if action.shape[0] != transition_count or not np.isfinite(action).all():
            raise TrajectoryValidationError("action datasets must be finite and have T rows", category="data_bounds")
        for path_name in ("reward", "terminated", "truncated"):
            if path_name not in root or np.asarray(root[path_name]).shape != (transition_count,):
                raise TrajectoryValidationError(f"{path_name} must have shape ({transition_count},)")
        _universal_matrix(root, transition_count)
        return {"env_meta": env_meta, "action_order": order, "transition_count": transition_count}


def validate_trajectory_collection(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Validate every member of a grouped H5 without changing its bytes."""

    import tempfile
    import h5py

    source = Path(path)
    with h5py.File(source, "r") as root:
        if str(root.attrs.get("container_type", "")) != "trajectory_collection":
            raise TrajectoryValidationError("expected a trajectory_collection H5")
        schema_id = str(root.attrs.get("schema_id", ""))
        schema_version = str(root.attrs.get("schema_version", ""))
        names = sorted(name for name in root if str(name).startswith("traj_"))
        if not names:
            raise TrajectoryValidationError("trajectory collection is empty")
        reports: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="task-env-validate-") as directory:
            for name in names:
                single = Path(directory) / f"{name}.h5"
                _materialize_group(root[name], single)
                report = validate_trajectory(single)
                reports.append({"name": name, **report})
    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "container_type": "trajectory_collection",
        "trajectory_count": len(reports),
        "trajectories": reports,
    }


def _dataset_paths(root, prefix: str) -> list[str]:
    paths: list[str] = []
    root[prefix].visititems(lambda name, node: paths.append(f"{prefix}/{name}") if hasattr(node, "shape") else None)
    return paths


def _rotation_angle(quaternion: np.ndarray) -> float:
    value = np.asarray(quaternion, dtype=np.float64).reshape(4)
    norm = float(np.linalg.norm(value))
    if norm <= 1.0e-12:
        raise ActionTransformError("target quaternion cannot be zero", category="data_bounds")
    w = float(np.clip(abs(value[0] / norm), -1.0, 1.0))
    return 2.0 * float(np.arccos(w))


def _substeps_for_delta(action: np.ndarray, contract: dict[str, Any], *, interpolation: bool) -> int:
    if not interpolation:
        return 1
    translation_limit = float(contract.get("max_translation_delta_m", 0.03))
    rotation_limit = float(contract.get("max_rotation_delta_rad", 0.20))
    translation_steps = int(math.ceil(float(np.linalg.norm(action[:3])) / translation_limit))
    rotation_steps = int(math.ceil(_rotation_angle(action[3:7]) / rotation_limit))
    return max(1, translation_steps, rotation_steps)


def _target_env_cfg(env_cfg: dict[str, Any], mode: str, reference: str | None) -> dict[str, Any]:
    result = copy.deepcopy(env_cfg)
    robot = result.setdefault("robot", {})
    controller = robot.setdefault("controller", {})
    controller["kind"] = mode
    if mode == "absolute_joint":
        controller.pop("reference", None)
        controller.pop("rotation_representation", None)
    else:
        controller["reference"] = reference
        controller["rotation_representation"] = "quaternion_wxyz"
    return result


def _source_pose_action(source_action: np.ndarray, order: list[str]) -> np.ndarray:
    indices = {name: i for i, name in enumerate(order)}
    try:
        pose = np.stack([source_action[:, indices[name]] for name in ("x", "y", "z", "qw", "qx", "qy", "qz")], axis=1)
    except KeyError as exc:
        raise ActionTransformError("source absolute pose action is missing a component", category="missing_observation") from exc
    return pose


def _transcode_single_actions(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    target_mode: str,
    target_reference: str | None = None,
    mode: str = "strict",
    interpolation: bool | None = None,
) -> Path:
    """Convert one absolute-pose/world H5 to another explicit action schema.

    ``mode='strict'`` emits one target control tick per source transition and
    rejects controller-boundary violations.  ``mode='interpolation'`` inserts
    waypoints for bounded delta actions; first and last universal actions are
    copied bit-for-bit from the source.
    """
    import h5py
    import yaml

    source = Path(source_path)
    target = Path(output_path)
    if source.resolve() == target.resolve():
        raise ActionTransformError("source and output H5 paths must differ")
    validate_trajectory(source)
    interpolation_enabled = bool(interpolation) if interpolation is not None else mode == "interpolation"
    if mode not in {"strict", "interpolation"}:
        raise ActionTransformError(f"unsupported conversion mode: {mode}")
    if target_mode == "absolute_pose" and target_reference not in {"world", "base"}:
        raise ActionTransformError("absolute_pose reference must be world or base")
    if target_mode == "delta_pose" and target_reference not in {"world", "base", "ee"}:
        raise ActionTransformError("delta_pose reference must be world, base, or ee")
    if target_mode == "absolute_joint" and target_reference is not None:
        raise ActionTransformError("absolute_joint reference must be null")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        with h5py.File(source, "r") as src, h5py.File(temporary, "w") as out:
            env_meta = load_metadata(_text(src["meta/env_meta"]))
            env_cfg = yaml.safe_load(_text(src["meta/env_cfg"])) or {}
            contract = _source_contract(env_meta)
            if contract.get("controller_kind") != "absolute_pose" or contract.get("reference") != "world":
                raise ActionTransformError("source must be absolute_pose/world")
            order = _action_order(env_meta, src)
            source_action = _action_matrix(src, order)
            transition_count = source_action.shape[0]
            if len(order) != 8 or order[-1] != "gripper":
                raise ActionTransformError("source absolute pose action must have 8 components ending in gripper")
            universal = _universal_matrix(src, transition_count)
            target_contract = _target_contract(target_mode, target_reference, env_cfg)
            target_names = list(target_contract["components"])
            ee = _leaf(src, "state.ee_pose_world")
            if ee.shape != (transition_count + 1, 7):
                raise TrajectoryValidationError("state.ee_pose_world must have shape (T+1, 7)", category="missing_observation")
            base = None
            if target_reference == "base":
                base = _leaf(src, "private_state.robot_base_pose_world")
                if base.shape != (transition_count + 1, 7):
                    raise TrajectoryValidationError("robot_base_pose_world must have shape (T+1, 7)", category="missing_observation")
            if target_mode == "absolute_joint":
                target_action = universal.copy()
                substeps = [1] * transition_count
            else:
                pose_actions = _source_pose_action(source_action, order)
                target_rows: list[np.ndarray] = []
                expected_rows: list[np.ndarray] = []
                substeps = []
                for index in range(transition_count):
                    current_pose = ee[index]
                    target_pose = pose_actions[index]
                    one = transform_absolute_world_to_target(
                        target_pose,
                        current_pose,
                        target_reference=target_reference or "world",
                        base_world=None if base is None else base[index],
                        target_mode=target_mode,
                    )
                    count = _substeps_for_delta(one, target_contract, interpolation=interpolation_enabled)
                    if not interpolation_enabled:
                        if target_mode == "delta_pose":
                            translation_limit = float(target_contract["max_translation_delta_m"])
                            if float(np.linalg.norm(one[:3])) > translation_limit + 1.0e-7:
                                raise ActionTransformError(
                                    f"transition {index} exceeds delta translation controller boundary",
                                    category="controller_boundary",
                                )
                            limit = float(target_contract["max_rotation_delta_rad"])
                            if _rotation_angle(one[3:7]) > limit + 1.0e-7:
                                raise ActionTransformError(
                                    f"transition {index} exceeds delta rotation controller boundary",
                                    category="controller_boundary",
                                )
                        count = 1
                    substeps.append(count)
                    for substep in range(1, count + 1):
                        alpha = float(substep / count)
                        previous = interpolate_pose(current_pose, target_pose, (substep - 1) / count)
                        goal = interpolate_pose(current_pose, target_pose, alpha)
                        row_pose = transform_absolute_world_to_target(
                            goal,
                            previous,
                            target_reference=target_reference or "world",
                            base_world=None if base is None else base[index],
                            target_mode=target_mode,
                        )
                        row = np.concatenate([row_pose[:7], [source_action[index, -1]]]).astype(np.float32)
                        target_rows.append(row)
                        if substep == count:
                            expected_rows.append(universal[index].copy())
                        elif index == 0:
                            expected_rows.append(universal[index].copy())
                        else:
                            expected_rows.append(((1.0 - alpha) * universal[index - 1] + alpha * universal[index]).astype(np.float32))
                target_action = np.stack(target_rows).astype(np.float32) if target_rows else np.empty((0, 8), dtype=np.float32)
                expected_universal = np.stack(expected_rows).astype(np.float32) if expected_rows else np.empty((0, 8), dtype=np.float32)
            if target_mode == "absolute_joint":
                expected_universal = universal.copy()
            low = np.asarray(target_contract["low"], dtype=np.float64)
            high = np.asarray(target_contract["high"], dtype=np.float64)
            if np.any(target_action < low) or np.any(target_action > high) or not np.isfinite(target_action).all():
                raise ActionTransformError("converted action exceeds target controller data bounds", category="data_bounds")

            # Copy immutable source data except time-series groups which are rewritten below.
            skip = {"action", "obs", "universal_action", "reward", "success", "terminated", "truncated", "info", "meta"}
            for name in src:
                if name not in skip:
                    src.copy(name, out, name=name)
            src.copy("action", out, name="source_action")

            source_obs_paths = _dataset_paths(src, "obs")
            source_obs = {path: np.asarray(src[path]) for path in source_obs_paths}
            output_obs: dict[str, list[np.ndarray]] = {path: [] for path in source_obs_paths}
            output_transition: dict[str, list[np.ndarray]] = {}
            transition_paths = ["reward", "success", "terminated", "truncated"]
            transition_paths += _dataset_paths(src, "info") if "info" in src else []
            source_transition = {path: np.asarray(src[path]) for path in transition_paths}
            if not interpolation_enabled or target_mode == "absolute_joint":
                for path, values in source_obs.items():
                    output_obs[path] = [np.asarray(v).copy() for v in values]
                for path, values in source_transition.items():
                    output_transition[path] = [np.asarray(v).copy() for v in values]
            else:
                output_obs = {path: [] for path in source_obs_paths}
                for index, count in enumerate(substeps):
                    current_pose = ee[index]
                    target_pose = pose_actions[index]
                    for substep in range(1, count + 1):
                        alpha = float(substep / count)
                        for path, values in source_obs.items():
                            if substep == count:
                                value = values[index + 1].copy()
                            else:
                                value = values[index].copy()
                                if path in {"obs/state/ee_pose", "obs/state/ee_pose_world"}:
                                    value = interpolate_pose(current_pose, target_pose, alpha).astype(value.dtype)
                            output_obs[path].append(value)
                        for path, values in source_transition.items():
                            value = values[index].copy()
                            if substep != count and path in {"success", "terminated", "truncated"}:
                                value = np.asarray(False, dtype=values.dtype)
                            output_transition.setdefault(path, []).append(value)

            # For non-interpolated output all source observations are already present;
            # for interpolated output the loop above emitted one post-action frame per row.
            if not interpolation_enabled or target_mode == "absolute_joint":
                pass
            else:
                # The first observation is not emitted by the post-action loop.
                for path in output_obs:
                    output_obs[path].insert(0, source_obs[path][0].copy())
            obs_group = out.create_group("obs")
            for path, values in output_obs.items():
                relative = path[len("obs/"):]
                parent = obs_group
                parts = relative.split("/")
                for part in parts[:-1]:
                    parent = parent.require_group(part)
                data = np.stack(values)
                parent.create_dataset(parts[-1], data=data)
            action_group = out.create_group("action")
            for column, name in enumerate(target_names):
                action_group.create_dataset(name, data=target_action[:, column : column + 1])
            universal_group = out.create_group("universal_action")
            universal_group.create_dataset("arm_joint_position", data=expected_universal[:, :7])
            universal_group.create_dataset("gripper", data=expected_universal[:, 7:8])
            for path, values in output_transition.items():
                parent = out
                parts = path.split("/")
                for part in parts[:-1]:
                    parent = parent.require_group(part)
                parent.create_dataset(parts[-1], data=np.asarray(values))
            # In the non-interpolated path, transition data was not copied yet.
            if not output_transition:
                for path, values in source_transition.items():
                    parent = out
                    parts = path.split("/")
                    for part in parts[:-1]:
                        parent = parent.require_group(part)
                    parent.create_dataset(parts[-1], data=values)

            out.attrs.update(
                schema_id="task-env-h5",
                schema_version="v2",
                transition_count=int(target_action.shape[0]),
                observation_count=int(target_action.shape[0] + 1),
                episode_complete=bool(src.attrs.get("episode_complete", True)),
                stop_reason=str(src.attrs.get("stop_reason", "manual")),
            )
            output_meta = dict(env_meta)
            output_meta["source_action_protocol"] = env_meta.get("action_protocol", _protocol("absolute_pose", "world"))
            output_meta["action_protocol"] = _protocol(target_mode, target_reference)
            context = _replay_context(env_meta, src)
            if context:
                output_meta["replay_context"] = context
            output_meta["action"] = {name: [1] for name in target_names}
            output_meta["action_order"] = target_names
            output_meta["action_schema"] = {
                "schema_id": target_contract["schema_id"],
                "schema_version": target_contract["schema_version"],
                "controller_kind": target_mode,
                "reference": target_reference,
                "order": target_names,
                "components": [{"name": name, "shape": [1], "dtype": "float32", "index": i} for i, name in enumerate(target_names)],
                "contract": target_contract,
            }
            output_meta["transform"] = {
                "kind": "command_preserving_pose_target" if target_mode != "absolute_joint" else "universal_action_joint_target",
                "source_action_path": "source_action",
                "target_action_path": "action",
                "source_schema_id": contract.get("schema_id", ""),
                "target_schema_id": target_contract["schema_id"],
                "mode": mode,
                "interpolated_transition_count": int(target_action.shape[0]),
                "source_transition_count": int(transition_count),
                "universal_action_endpoint_exact": bool(
                    np.array_equal(expected_universal[0], universal[0])
                    and np.array_equal(expected_universal[-1], universal[-1])
                ) if transition_count else True,
                "universal_action_verified": target_mode == "absolute_joint" or not interpolation_enabled,
            }
            meta_group = out.require_group("meta")
            _yaml_dataset = lambda group, name, value: group.create_dataset(
                name, data=np.asarray(yaml.safe_dump(value, sort_keys=True, allow_unicode=True), dtype=h5py.string_dtype("utf-8"))
            )
            _yaml_dataset(meta_group, "env_cfg", _target_env_cfg(env_cfg, target_mode, target_reference))
            meta_group.create_dataset(
                "env_meta",
                data=np.asarray(dump_metadata(output_meta), dtype=h5py.string_dtype("utf-8")),
            )
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


def transcode_trajectory_collection(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    target_mode: str,
    target_reference: str | None = None,
) -> Path:
    """Strictly convert every trajectory in one grouped source H5.

    Grouped Stage 11 conversion is intentionally one-to-one: interpolation,
    frame deletion, and silent clipping are rejected before any output is
    created.  Each member is converted through the single-trajectory path so
    its source action, metadata, and exact T/T+1 contract remain local.
    """

    import h5py
    import tempfile

    source = Path(source_path)
    target = Path(output_path)
    if source.resolve() == target.resolve():
        raise ActionTransformError("source and output H5 paths must differ")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    validate_trajectory_collection(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        with h5py.File(source, "r") as src, h5py.File(temporary, "w") as out:
            names = sorted(name for name in src if str(name).startswith("traj_"))
            out.attrs.update(
                schema_id="task-env-h5",
                schema_version="v2",
                container_type="trajectory_collection",
                container_version="v1",
                trajectory_count=len(names),
                transform_mode="strict",
                target_mode=target_mode,
                target_reference="" if target_reference is None else target_reference,
            )
            with tempfile.TemporaryDirectory(prefix="task-env-transcode-") as directory:
                for name in names:
                    single_source = Path(directory) / f"{name}-source.h5"
                    single_target = Path(directory) / f"{name}-target.h5"
                    _materialize_group(src[name], single_source)
                    _transcode_single_actions(
                        single_source,
                        single_target,
                        target_mode=target_mode,
                        target_reference=target_reference,
                        mode="strict",
                        interpolation=False,
                    )
                    with h5py.File(single_target, "r") as converted:
                        group = out.create_group(name)
                        for key in converted:
                            converted.copy(key, group, name=key)
                        for key, value in converted.attrs.items():
                            group.attrs[key] = value
                        group.attrs["source_group"] = name
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


def transcode_actions(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    target_mode: str,
    target_reference: str | None = None,
    mode: str = "strict",
    interpolation: bool | None = None,
) -> Path:
    """Convert a single or grouped source, with grouped input forced strict."""

    import h5py

    with h5py.File(Path(source_path), "r") as source:
        grouped = str(source.attrs.get("container_type", "")) == "trajectory_collection"
    if grouped:
        interpolation_enabled = bool(interpolation) if interpolation is not None else mode == "interpolation"
        if mode != "strict" or interpolation_enabled:
            raise ActionTransformError(
                "grouped Stage 11 conversion only supports strict one-to-one transcode",
                category="controller_boundary",
            )
        return transcode_trajectory_collection(
            source_path,
            output_path,
            target_mode=target_mode,
            target_reference=target_reference,
        )
    return _transcode_single_actions(
        source_path,
        output_path,
        target_mode=target_mode,
        target_reference=target_reference,
        mode=mode,
        interpolation=interpolation,
    )


__all__ = [
    "ActionTransformError",
    "TrajectoryValidationError",
    "inspect_trajectory",
    "transcode_actions",
    "transcode_trajectory_collection",
    "validate_trajectory",
    "validate_trajectory_collection",
]
