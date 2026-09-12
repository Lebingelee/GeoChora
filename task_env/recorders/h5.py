"""Versioned HDF5 writers for frozen public TaskEnv trajectories."""

from __future__ import annotations

import os
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from collections.abc import Sequence

import numpy as np
import yaml

from .contracts import RecorderConfig
from .trajectory import FrozenTrajectory
from task_env.trajectory.metadata import dump_metadata, load_metadata, plain_metadata


def h5_string_dtype():
    import h5py

    return h5py.string_dtype(encoding="utf-8")


def _text_dataset(group, name: str, text: str) -> None:
    group.create_dataset(name, data=np.asarray(text, dtype=h5_string_dtype()))


def _json_dataset(group, name: str, value: Any) -> None:
    import json

    _text_dataset(group, name, json.dumps(plain_metadata(value), sort_keys=True))


def _yaml_dataset(group, name: str, value: Any) -> None:
    _text_dataset(group, name, dump_metadata(value))


def _leaves(value: Any, prefix: str = "", *, flat_leaf: str = "state/pendulum"):
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}/{key}" if prefix else str(key)
            yield from _leaves(item, child, flat_leaf=flat_leaf)
    else:
        # A state-only Box observation has no mapping root.  Give it the
        # stable generic state leaf used by the Pendulum schema instead of
        # attempting to create an H5 dataset with an empty name.
        yield (prefix or flat_leaf), np.asarray(value)


def _action_schema(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    env_metadata = metadata.get("env_metadata", {})
    if not isinstance(env_metadata, Mapping):
        raise ValueError("record metadata env_metadata must be a mapping")
    schema = env_metadata.get("action_schema", {})
    if not isinstance(schema, Mapping):
        raise ValueError("record metadata action_schema must be a mapping")
    components = schema.get("components")
    if not isinstance(components, (tuple, list)):
        raise ValueError("record metadata action_schema lacks components")
    names = tuple(str(name) for name in components)
    if not names or len(set(names)) != len(names):
        raise ValueError("action_schema components must be non-empty and unique")
    return schema


def _universal_action_schema(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the task-family-specific runtime-facing action schema."""

    schema = metadata.get("universal_action_schema")
    if not schema:
        env_metadata = metadata.get("env_metadata", {})
        if isinstance(env_metadata, Mapping):
            schema = env_metadata.get("universal_action_schema")
    if schema:
        if not isinstance(schema, Mapping):
            raise ValueError("record metadata universal_action_schema must be a mapping")
        return schema
    # A small compatibility fallback for pre-Stage-12 synthetic/Panda
    # metadata that predates the public schema projection.
    return {
        "version": "panda-universal-action-v1",
        "dimension": 8,
        "components": (
            "joint1", "joint2", "joint3", "joint4",
            "joint5", "joint6", "joint7", "gripper",
        ),
    }


def _stable_scalars(infos: tuple[dict[str, Any], ...], group_name: str) -> dict[str, np.ndarray]:
    if not infos:
        return {}
    expected = set(infos[0].get(group_name, {}).keys())
    result = {key: [] for key in expected}
    for info in infos:
        values = info.get(group_name, {})
        if set(values.keys()) != expected:
            raise ValueError(f"{group_name} keys changed within trajectory")
        for key, value in values.items():
            if not isinstance(value, (bool, int, float, np.bool_, np.number)):
                raise ValueError(f"{group_name}.{key} must be a scalar")
            result[key].append(value)
    return {key: np.asarray(values) for key, values in result.items()}


def _flat_observation_leaf_path(metadata: Mapping[str, Any]) -> str:
    raw = metadata.get("env_metadata", {})
    schema = raw.get("observation_schema", {}) if isinstance(raw, Mapping) else {}
    specs = schema.get("leaf_specs", ()) if isinstance(schema, Mapping) else ()
    if len(specs) == 1 and isinstance(specs[0], Mapping):
        path = str(specs[0].get("path", ""))
        if path:
            return path.replace(".", "/")
    return "state/pendulum"


def _write_raw_observations(
    root,
    observations: tuple[Any, ...],
    config: RecorderConfig,
    metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    flat_leaf = _flat_observation_leaf_path(metadata)
    first_paths = [path for path, _ in _leaves(observations[0], flat_leaf=flat_leaf)]
    for observation in observations[1:]:
        if [path for path, _ in _leaves(observation, flat_leaf=flat_leaf)] != first_paths:
            raise ValueError("observation leaf paths must stay fixed within a trajectory")
    leaves: list[dict[str, Any]] = []
    for path in first_paths:
        values = [
            dict(_leaves(current, flat_leaf=flat_leaf))[path]
            for current in observations
        ]
        first = values[0]
        if any(value.shape != first.shape or value.dtype != first.dtype for value in values):
            raise ValueError(f"observation leaf {path} shape/dtype changed within a trajectory")
        data = np.stack(values)
        root.create_dataset(
            f"obs/{path}", data=data, compression=config.h5_compression,
            compression_opts=config.h5_compression_level, chunks=(1, *data.shape[1:]),
        )
        leaves.append({"path": path, "shape": list(first.shape), "dtype": str(first.dtype)})
    return leaves


def _write_action(root, actions: tuple[np.ndarray, ...], schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    components = tuple(str(name) for name in schema["components"])
    data = np.stack(actions) if actions else np.empty((0, len(components)), dtype=np.float32)
    if data.ndim != 2 or data.shape[1] != len(components):
        raise ValueError("recorded action shape does not match action_schema components")
    result = []
    for index, component in enumerate(components):
        root.create_dataset(f"action/{component}", data=data[:, index : index + 1])
        result.append({"name": component, "shape": [1], "dtype": str(data.dtype), "index": index})
    return result


def _env_meta(trajectory: FrozenTrajectory, observation_leaves: list[dict[str, Any]], action_leaves: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = trajectory.record_metadata
    raw = metadata.get("env_metadata", {})
    if not isinstance(raw, Mapping):
        raise ValueError("record metadata env_metadata must be a mapping")
    schema_metadata = raw.get("observation_schema", {})
    field_specs = (
        schema_metadata.get("leaf_specs", ())
        if isinstance(schema_metadata, Mapping)
        else ()
    )
    semantics = {
        str(spec.get("path")): str(spec.get("semantic", ""))
        for spec in field_specs if isinstance(spec, Mapping)
    }
    grouped: dict[str, dict[str, Any]] = {}
    for leaf in observation_leaves:
        root, _, name = leaf["path"].partition("/")
        group = grouped.setdefault(root, {"order": [], "leaves": {}})
        group["order"].append(name)
        group["leaves"][name] = {"shape": leaf["shape"], "dtype": leaf["dtype"], "semantic": semantics.get(leaf["path"].replace("/", "."), "")}
    source_action_schema = _action_schema(metadata)
    controller_kind = source_action_schema.get("controller_kind")
    reference = source_action_schema.get("reference")
    if controller_kind == "absolute_joint":
        arm_mode = "absolute_joint"
        reference = None
    elif controller_kind == "delta_pose":
        arm_mode = "delta"
    elif source_action_schema.get("mode") not in (None, "no_op"):
        arm_mode = "native"
        reference = None
    else:
        arm_mode = "absolute"
    for spec in raw.get("camera_specs", ()):
        if not isinstance(spec, Mapping) or not spec.get("rgb"):
            continue
        name = str(spec["name"])
        if "rgb" in grouped and name in grouped["rgb"]["leaves"]:
            source_layout = spec.get("rgb_layout", "HWC")
            grouped["rgb"]["leaves"][name].update({
                "layout": "CHW",
                "source_layout": source_layout,
                "semantic": "rgb",
            })
    rich_observation = {"order": list(grouped), "camera_order": list(raw.get("camera_names", ())), **grouped}
    observation_shapes = {
        group: {name: leaf["shape"] for name, leaf in value.get("leaves", {}).items()}
        for group, value in grouped.items()
    }
    action_order = [leaf["name"] for leaf in action_leaves]
    action_schema = {
        "schema_id": source_action_schema.get("schema_id"),
        "schema_version": source_action_schema.get("schema_version"),
        "reference": source_action_schema.get("reference"),
        "controller_kind": source_action_schema.get("controller_kind"),
        "contract": dict(source_action_schema),
        "order": action_order,
        "components": [{**leaf, "semantic": leaf["name"]} for leaf in action_leaves],
    }
    for key in (
        "kind",
        "mode",
        "shape",
        "dtype",
        "low",
        "high",
        "bounds",
        "unit",
        "actuator_interpretation",
        "task_family",
    ):
        if key in source_action_schema:
            action_schema[key] = source_action_schema[key]
    universal_schema = _universal_action_schema(metadata)
    action_protocol = (
        {
            "mode": {"native": source_action_schema.get("mode")},
            "reference": None,
            "action_equals_universal_action": True,
        }
        if controller_kind is None and source_action_schema.get("mode") not in (None, "no_op")
        else {
            "mode": {"arm": arm_mode, "gripper": "absolute"},
            "reference": reference,
        }
    )
    result = {
        "schema": {"id": "task-env-h5", "version": "v2"},
        "environment": {"name": raw.get("env_name"), "task_name": raw.get("task_name"), "task_version": raw.get("task_version"), "scene_uid": raw.get("scene_uid"), "agent_uids": raw.get("agent_uids", ())},
        "timebase": {
            "physics_dt": raw.get("physics_dt"), "control_substeps": raw.get("control_substeps"),
            "control_frequency": raw.get("control_frequency"),
        },
        # ``obs`` and ``action`` are shape maps consumed by agent_factory's
        # resolver.  Rich semantics live beside them so JSON/YAML readers do
        # not have to guess whether a metadata value is a shape or a schema.
        "obs": {"order": list(grouped), "camera_order": list(raw.get("camera_names", ())), **observation_shapes},
        "observation_schema": rich_observation,
        "observation_order": {group: value.get("order", []) for group, value in grouped.items()},
        "action": {leaf["name"]: leaf["shape"] for leaf in action_leaves},
        "action_order": action_order,
        "action_schema": action_schema,
        "action_protocol": action_protocol,
        "replay_context": ({
            "seed": trajectory.reset_info.get("seed"),
            "options": trajectory.reset_info.get("options", {}),
            "reset_parameters": trajectory.reset_info.get("reset_parameters", {}),
        } if isinstance(trajectory.reset_info, Mapping) and "seed" in trajectory.reset_info else {}),
        "universal_action": universal_schema,
        "batch_provenance": metadata.get("batch_provenance", {}),
        "batch_physics_layout": raw.get("batch_physics_layout"),
        "runtime_resource_summary": raw.get("runtime_resource_summary", {}),
        "reference_profile": raw.get("reference_profile", {}),
        "conversion_capabilities": raw.get("conversion_capabilities", {}),
        "trajectory": {"observation_count_semantics": "T+1", "transition_count_semantics": "T"},
    }
    return result


def _write_common_transition_data(root, trajectory: FrozenTrajectory) -> None:
    schema = _universal_action_schema(trajectory.record_metadata)
    dimension = int(schema.get("dimension", 0))
    universal = (
        np.stack(trajectory.universal_actions).astype(np.float32, copy=False)
        if trajectory.universal_actions
        else np.empty((0, dimension), dtype=np.float32)
    )
    if universal.ndim != 2 or universal.shape[1] != dimension:
        raise ValueError("universal_action shape does not match universal_action_schema")
    is_panda_v1 = schema.get("version") == "panda-universal-action-v1" or (
        dimension == 8 and not schema.get("components")
    )
    if is_panda_v1:
        if dimension != 8:
            raise ValueError("Panda v1 universal_action must have shape (T, 8)")
        root.create_dataset("universal_action/arm_joint_position", data=universal[:, :7])
        root.create_dataset("universal_action/gripper", data=universal[:, 7:8])
    else:
        components = tuple(str(name) for name in schema.get("components", ()))
        if len(components) != dimension or len(set(components)) != dimension:
            raise ValueError("universal_action_schema components must match its dimension")
        for index, component in enumerate(components):
            root.create_dataset(
                f"universal_action/{component}",
                data=universal[:, index : index + 1],
            )
    root.create_dataset("reward", data=np.asarray(trajectory.rewards, dtype=np.float32))
    root.create_dataset("success", data=np.asarray(trajectory.successes, dtype=np.bool_))
    root.create_dataset("terminated", data=np.asarray(trajectory.terminated, dtype=np.bool_))
    root.create_dataset("truncated", data=np.asarray(trajectory.truncated, dtype=np.bool_))
    for group_name, h5_group in (("task_metrics", "info/task_metrics"), ("reward_terms", "info/reward_terms")):
        for key, values in _stable_scalars(trajectory.infos, group_name).items():
            root.create_dataset(f"{h5_group}/{key}", data=values)


def _save_v2(root, trajectory: FrozenTrajectory, config: RecorderConfig) -> None:
    root.attrs.update(schema_id="task-env-h5", schema_version="v2", transition_count=trajectory.transition_count, observation_count=len(trajectory.observations), episode_complete=True, stop_reason=trajectory.stop_reason)
    leaves = _write_raw_observations(
        root,
        trajectory.observations,
        config,
        trajectory.record_metadata,
    )
    action_leaves = _write_action(root, trajectory.actions, _action_schema(trajectory.record_metadata))
    _write_common_transition_data(root, trajectory)
    meta = root.require_group("meta")
    env_meta = _env_meta(trajectory, leaves, action_leaves)
    _yaml_dataset(meta, "env_meta", env_meta)
    _yaml_dataset(meta, "env_cfg", trajectory.record_metadata.get("resolved_config", {}))
    if not config.meta_only:
        _yaml_dataset(meta, "episode_meta", {
            "reset_info": trajectory.reset_info, "stop_reason": trajectory.stop_reason,
            "transition_count": trajectory.transition_count, "observation_count": len(trajectory.observations),
        })


def _save_v1(root, trajectory: FrozenTrajectory, config: RecorderConfig) -> None:
    """Historical writer retained for its fixed v1 regression fixture only."""
    root.attrs.update(schema_id=config.schema_id, schema_version=config.schema_version, transition_count=trajectory.transition_count, observation_count=len(trajectory.observations), episode_complete=True, stop_reason=trajectory.stop_reason)
    layout = {"leaves": [], "flatten_observation_paths": list(config.flatten_observation_paths)}
    first_paths = [path for path, _ in _leaves(trajectory.observations[0])]
    selected = tuple(config.flatten_observation_paths)
    for group in selected:
        paths = [path for path in first_paths if path == group or path.startswith(f"{group}/")]
        if not paths:
            raise ValueError(f"flatten observation path does not exist: {group}")
        rows = [np.concatenate([dict(_leaves(obs))[path].reshape(-1) for path in paths]).astype(np.float32) for obs in trajectory.observations]
        root.create_dataset(f"obs/{group}", data=np.stack(rows))
    for path in first_paths:
        if any(path == group or path.startswith(f"{group}/") for group in selected):
            continue
        values = [dict(_leaves(obs))[path] for obs in trajectory.observations]
        first = values[0]
        data = np.stack(values)
        if path.startswith("vision/rgb/") and np.issubdtype(first.dtype, np.floating):
            data = np.rint(np.clip(data, 0.0, 1.0) * 255.0).astype(np.uint8)
        root.create_dataset(f"obs/{path}", data=data, compression=config.h5_compression, compression_opts=config.h5_compression_level, chunks=(1, *data.shape[1:]))
    _write_action(root, trajectory.actions, _action_schema(trajectory.record_metadata))
    _write_common_transition_data(root, trajectory)
    meta = root.require_group("meta")
    _json_dataset(meta, "env_metadata_json", trajectory.record_metadata)
    _json_dataset(meta, "reset_info_json", trajectory.reset_info)
    _json_dataset(meta, "recorder_config_json", config.__dict__)
    _json_dataset(meta, "layout_json", layout)


def save_trajectory_h5(trajectory: FrozenTrajectory, config: RecorderConfig, *, path: Path | str | None, name: str | None, index: int) -> Path:
    import h5py

    trajectory.validate()
    directory = Path.cwd() if path is None else Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    filename = name or f"traj_{index:03d}_{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%m%d%H%M')}.h5"
    if not filename.endswith(".h5"):
        filename += ".h5"
    target = directory / filename
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    temporary = directory / f".{filename}.tmp"
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    try:
        with h5py.File(temporary, "w") as root:
            if config.schema_version == "v2":
                _save_v2(root, trajectory, config)
            else:
                _save_v1(root, trajectory, config)
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


def save_trajectory_collection_h5(
    trajectories: Sequence[FrozenTrajectory],
    config: RecorderConfig,
    *,
    path: Path | str | None,
    name: str | None,
) -> Path:
    """Write multiple trajectories into one ``traj_000``-grouped H5 file."""

    import h5py

    if config.schema_version != "v2":
        raise ValueError("trajectory collections support only task-env-h5/v2")
    if not trajectories:
        raise ValueError("trajectory collection requires at least one trajectory")
    directory = Path.cwd() if path is None else Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    filename = name or "trajectories.h5"
    if not filename.endswith(".h5"):
        filename += ".h5"
    target = directory / filename
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    temporary = directory / f".{filename}.tmp"
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    try:
        with h5py.File(temporary, "w") as root:
            root.attrs.update(
                schema_id="task-env-h5",
                schema_version="v2",
                container_type="trajectory_collection",
                container_version="v1",
                trajectory_count=len(trajectories),
            )
            for index, trajectory in enumerate(trajectories):
                trajectory.validate()
                group = root.create_group(f"traj_{index:03d}")
                _save_v2(group, trajectory, config)
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


def append_trajectory_collection_h5(
    trajectory: FrozenTrajectory,
    config: RecorderConfig,
    *,
    path: Path | str | None,
    name: str | None,
    index: int,
) -> Path:
    """Append one completed v2 trajectory and flush its grouped H5 container.

    This is intentionally episode-granular: a successful trajectory is durable
    before the next ``env.reset()`` begins, while observations remain buffered
    only for the current episode.
    """

    import h5py

    if config.schema_version != "v2":
        raise ValueError("trajectory collections support only task-env-h5/v2")
    if index < 0:
        raise ValueError("trajectory collection index must be non-negative")
    trajectory.validate()
    directory = Path.cwd() if path is None else Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    filename = name or "trajectories.h5"
    if not filename.endswith(".h5"):
        filename += ".h5"
    target = directory / filename
    group_name = f"traj_{index:03d}"
    created = not target.exists()
    with h5py.File(target, "x" if created else "r+") as root:
        if created:
            root.attrs.update(
                schema_id="task-env-h5",
                schema_version="v2",
                container_type="trajectory_collection",
                container_version="v1",
                trajectory_count=0,
            )
        elif (
            str(root.attrs.get("schema_id", "")) != "task-env-h5"
            or str(root.attrs.get("schema_version", "")) != "v2"
            or str(root.attrs.get("container_type", "")) != "trajectory_collection"
        ):
            raise ValueError(f"not a task-env-h5/v2 trajectory collection: {target}")
        if group_name in root:
            raise FileExistsError(f"trajectory group already exists: {target}:{group_name}")
        group = root.create_group(group_name)
        try:
            _save_v2(group, trajectory, config)
        except Exception:
            del root[group_name]
            raise
        root.attrs["trajectory_count"] = int(index) + 1
        root.flush()
    return target


def _read_text(root, path: str) -> str:
    value = root[path][()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _inspect_v2_group(group) -> dict[str, Any]:
    result = {
        "schema_id": str(group.attrs.get("schema_id", "")),
        "schema_version": str(group.attrs.get("schema_version", "")),
        "transition_count": int(group.attrs.get("transition_count", 0)),
        "observation_count": int(group.attrs.get("observation_count", 0)),
    }
    result["env_meta"] = load_metadata(_read_text(group, "meta/env_meta"))
    result["env_cfg"] = load_metadata(_read_text(group, "meta/env_cfg"))
    if "meta/episode_meta" in group:
        result["episode_meta"] = load_metadata(_read_text(group, "meta/episode_meta"))
    return result


def inspect_trajectory_h5(path: Path | str) -> dict[str, Any]:
    """Inspect a v1 or v2 container without interpreting action values."""
    import h5py

    with h5py.File(Path(path), "r") as root:
        if str(root.attrs.get("container_type", "")) == "trajectory_collection":
            trajectories = []
            for name in sorted(key for key in root if str(key).startswith("traj_")):
                trajectories.append({"name": name, **_inspect_v2_group(root[name])})
            return {
                "schema_id": str(root.attrs.get("schema_id", "")),
                "schema_version": str(root.attrs.get("schema_version", "")),
                "container_type": "trajectory_collection",
                "trajectory_count": len(trajectories),
                "trajectories": trajectories,
            }
        result = {"schema_id": str(root.attrs.get("schema_id", "")), "schema_version": str(root.attrs.get("schema_version", "")), "transition_count": int(root.attrs.get("transition_count", 0)), "observation_count": int(root.attrs.get("observation_count", 0))}
        if result["schema_version"] == "v2":
            result.update(_inspect_v2_group(root))
        elif "meta/layout_json" in root:
            result["layout"] = json.loads(_read_text(root, "meta/layout_json"))
        return result


__all__ = [
    "append_trajectory_collection_h5",
    "inspect_trajectory_h5",
    "save_trajectory_collection_h5",
    "save_trajectory_h5",
]
