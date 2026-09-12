"""Collection-container operations for grouped TaskEnv H5 trajectories."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import h5py

from ..metadata import load_metadata


class TrajectoryCollectionError(ValueError):
    """Trajectory files cannot be combined into one grouped container."""


@dataclass(frozen=True)
class _Entry:
    path: Path
    group_name: str | None
    env_cfg: dict[str, Any]
    env_meta: dict[str, Any]


def _text(dataset: h5py.Dataset) -> str:
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True)


def _schema_projection(env_meta: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema", "environment", "timebase", "obs", "action",
        "universal_action", "conversion_capabilities", "trajectory",
        "action_protocol",
    )
    return {key: env_meta.get(key) for key in keys if key in env_meta}


def _read_metadata(group: h5py.Group | h5py.File, path: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if str(group.attrs.get("schema_id", "")) != "task-env-h5" or str(group.attrs.get("schema_version", "")) != "v2":
        raise TrajectoryCollectionError(f"{path}: {label} must be task-env-h5/v2")
    for required in ("obs", "action", "universal_action", "reward", "terminated", "truncated"):
        if required not in group:
            raise TrajectoryCollectionError(f"{path}: {label} is missing {required}")
    if "meta/env_meta" not in group or "meta/env_cfg" not in group:
        raise TrajectoryCollectionError(f"{path}: {label} requires meta/env_meta and meta/env_cfg")
    env_meta = load_metadata(_text(group["meta/env_meta"]))
    env_cfg = load_metadata(_text(group["meta/env_cfg"]))
    if not isinstance(env_meta, dict) or not isinstance(env_cfg, dict):
        raise TrajectoryCollectionError(f"{path}: {label} metadata must be mappings")
    return env_cfg, env_meta


def _entries(path: Path) -> list[_Entry]:
    if not path.is_file() or path.suffix.lower() != ".h5":
        raise TrajectoryCollectionError(f"input is not an H5 file: {path}")
    result: list[_Entry] = []
    with h5py.File(path, "r") as root:
        if str(root.attrs.get("container_type", "")) == "trajectory_collection":
            names = sorted(name for name in root if str(name).startswith("traj_"))
            if not names:
                raise TrajectoryCollectionError(f"{path}: trajectory collection is empty")
            for name in names:
                env_cfg, env_meta = _read_metadata(root[name], path, name)
                result.append(_Entry(path, name, env_cfg, env_meta))
        else:
            env_cfg, env_meta = _read_metadata(root, path, "single trajectory")
            result.append(_Entry(path, None, env_cfg, env_meta))
    return result


def _copy_entry(entry: _Entry, output: h5py.File, target_name: str) -> None:
    with h5py.File(entry.path, "r") as source:
        target = output.create_group(target_name)
        source_group = source[entry.group_name] if entry.group_name is not None else source
        for key in source_group:
            source_group.copy(key, target, name=key)
        for key, value in source_group.attrs.items():
            target.attrs[key] = value
        target.attrs["source_file"] = str(entry.path)
        if entry.group_name is not None:
            target.attrs["source_group"] = entry.group_name


def merge_trajectory_collections(
    source_paths: Sequence[str | os.PathLike[str]],
    output_path: str | os.PathLike[str],
) -> Path:
    """Pack all source trajectories into one ``traj_000``-grouped H5."""

    paths = tuple(Path(path) for path in source_paths)
    target = Path(output_path)
    if not paths:
        raise TrajectoryCollectionError("merge requires at least one H5 file")
    if any(path.resolve() == target.resolve() for path in paths):
        raise TrajectoryCollectionError("source and output paths must differ")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")

    entries: list[_Entry] = []
    for path in paths:
        entries.extend(_entries(path))
    reference = entries[0]
    for entry in entries[1:]:
        if _canonical(entry.env_cfg) != _canonical(reference.env_cfg):
            raise TrajectoryCollectionError(f"{entry.path}: env_cfg is incompatible with the first trajectory")
        if _canonical(_schema_projection(entry.env_meta)) != _canonical(_schema_projection(reference.env_meta)):
            raise TrajectoryCollectionError(f"{entry.path}: static env_meta is incompatible with the first trajectory")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    try:
        with h5py.File(temporary, "w") as output:
            output.attrs.update(
                schema_id="task-env-h5",
                schema_version="v2",
                container_type="trajectory_collection",
                container_version="v1",
                trajectory_count=len(entries),
            )
            for index, entry in enumerate(entries):
                _copy_entry(entry, output, f"traj_{index:03d}")
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


__all__ = ["TrajectoryCollectionError", "merge_trajectory_collections"]
