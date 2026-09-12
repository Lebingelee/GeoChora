"""Bounded, schema-checked merge of TaskEnv H5 v2 trajectories.

The merge operation is deliberately a data operation: it never constructs an
environment and never changes an action.  Input episodes are concatenated in
file order.  The first episode contributes all ``T+1`` observations; for
subsequent episodes the reset observation is omitted so the merged raw tree
retains the v2 root invariant ``observation_count == transition_count + 1``.
The omitted reset frames and the original episode ranges are recorded in
``meta/env_meta.merge``.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np
import yaml

from ..metadata import dump_metadata, load_metadata


DEFAULT_MAX_EPISODES = 1024
DEFAULT_MAX_TRANSITIONS = 1_000_000
_COPY_BLOCK = 64


class TrajectoryMergeError(ValueError):
    """Input trajectories cannot be materialized as one v2 stream."""


def _text(dataset: h5py.Dataset) -> str:
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True)


def _dataset_paths(root: h5py.File) -> tuple[str, ...]:
    paths: list[str] = []

    def visit(name: str, item: h5py.Dataset | h5py.Group) -> None:
        if isinstance(item, h5py.Dataset) and not name.startswith("meta/"):
            paths.append(name)

    root.visititems(visit)
    return tuple(paths)


def _schema_projection(env_meta: dict[str, Any]) -> dict[str, Any]:
    """Keep semantic compatibility fields and exclude per-output provenance."""

    keys = (
        "schema",
        "environment",
        "timebase",
        "obs",
        "action",
        "universal_action",
        "conversion_capabilities",
        "trajectory",
        "action_protocol",
    )
    return {key: env_meta.get(key) for key in keys if key in env_meta}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class _SourceInfo:
    path: Path
    transition_count: int
    observation_count: int
    env_meta: dict[str, Any]
    env_cfg: dict[str, Any]
    dataset_paths: tuple[str, ...]
    # Leading time dimension is intentionally excluded: compatible episodes
    # may have different T, while the leaf tail shape and dtype must match.
    dataset_specs: dict[str, tuple[tuple[int, ...], str]]
    source_id: str


def _fail(path: Path, message: str) -> TrajectoryMergeError:
    return TrajectoryMergeError(f"merge input {path}: {message}")


def _inspect_source(path: Path) -> _SourceInfo:
    if not path.exists():
        raise _fail(path, "file does not exist")
    if not path.is_file():
        raise _fail(path, "input is not a regular file")
    try:
        root = h5py.File(path, "r")
    except Exception as exc:  # pragma: no cover - h5py error text is backend-specific
        raise _fail(path, f"cannot open H5: {exc}") from exc
    with root:
        if str(root.attrs.get("schema_id", "")) != "task-env-h5":
            raise _fail(path, "schema_id must be task-env-h5")
        if str(root.attrs.get("schema_version", "")) != "v2":
            raise _fail(path, "schema_version must be v2")
        try:
            transitions = int(root.attrs["transition_count"])
            observations = int(root.attrs["observation_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _fail(path, "root transition_count/observation_count are required integers") from exc
        if transitions < 0 or observations != transitions + 1:
            raise _fail(path, "root must satisfy observation_count == transition_count + 1")
        if "meta/env_meta" not in root or "meta/env_cfg" not in root:
            raise _fail(path, "meta/env_meta and meta/env_cfg are required")
        try:
            env_meta = load_metadata(_text(root["meta/env_meta"]))
            env_cfg = yaml.safe_load(_text(root["meta/env_cfg"])) or {}
        except Exception as exc:
            raise _fail(path, f"metadata is not readable: {exc}") from exc
        if not isinstance(env_meta, dict):
            raise _fail(path, "meta/env_meta must contain a JSON object")
        if not isinstance(env_cfg, dict):
            raise _fail(path, "meta/env_cfg must contain a mapping")
        if "merge" in env_meta:
            raise _fail(path, "nested merged collections are not accepted")
        dataset_paths = _dataset_paths(root)
        if not dataset_paths:
            raise _fail(path, "no raw datasets found outside meta/")
        specs: dict[str, tuple[tuple[int, ...], str]] = {}
        for dataset_path in dataset_paths:
            dataset = root[dataset_path]
            shape = tuple(int(dim) for dim in dataset.shape)
            if not shape or shape[0] != (observations if dataset_path.startswith("obs/") else transitions):
                expected = observations if dataset_path.startswith("obs/") else transitions
                raise _fail(path, f"{dataset_path} must have leading dimension {expected}, got {shape}")
            if not (
                np.issubdtype(dataset.dtype, np.number)
                or np.issubdtype(dataset.dtype, np.bool_)
            ):
                raise _fail(path, f"{dataset_path} has unsupported dtype {dataset.dtype}")
            specs[dataset_path] = (shape[1:], str(dataset.dtype))
        for required in ("reward", "terminated", "truncated"):
            if required not in specs:
                raise _fail(path, f"missing required dataset {required}")
        if "universal_action/episode_id" in specs:
            raise _fail(path, "universal_action/episode_id is reserved for merge output")
        terminated = np.asarray(root["terminated"], dtype=bool)
        truncated = np.asarray(root["truncated"], dtype=bool)
        terminal = np.flatnonzero(terminated | truncated)
        if terminal.size and int(terminal[-1]) != transitions - 1:
            raise _fail(path, "terminal flag occurs before the final transition")
        if "universal_action/arm_joint_position" not in root or "universal_action/gripper" not in root:
            raise _fail(path, "universal_action arm_joint_position and gripper datasets are required")
        return _SourceInfo(
            path=path,
            transition_count=transitions,
            observation_count=observations,
            env_meta=env_meta,
            env_cfg=env_cfg,
            dataset_paths=dataset_paths,
            dataset_specs=specs,
            source_id=_sha256(path),
        )


def _validate_compatibility(reference: _SourceInfo, candidate: _SourceInfo) -> None:
    if reference.dataset_paths != candidate.dataset_paths:
        missing = sorted(set(reference.dataset_paths) - set(candidate.dataset_paths))
        extra = sorted(set(candidate.dataset_paths) - set(reference.dataset_paths))
        raise _fail(candidate.path, f"dataset paths incompatible; missing={missing}, extra={extra}")
    if _canonical(reference.env_cfg) != _canonical(candidate.env_cfg):
        raise _fail(candidate.path, "meta/env_cfg is incompatible with the first input")
    if _canonical(_schema_projection(reference.env_meta)) != _canonical(_schema_projection(candidate.env_meta)):
        raise _fail(candidate.path, "env_meta schema/action/observation contract is incompatible with the first input")
    for dataset_path in reference.dataset_paths:
        if reference.dataset_specs[dataset_path] != candidate.dataset_specs[dataset_path]:
            raise _fail(
                candidate.path,
                f"dataset tail shape/dtype incompatible at {dataset_path}: "
                f"expected {reference.dataset_specs[dataset_path]}, got {candidate.dataset_specs[dataset_path]}",
            )


def _ensure_parent(root: h5py.File, dataset_path: str) -> None:
    parent = dataset_path.rpartition("/")[0]
    if parent:
        root.require_group(parent)


def _create_dataset_like(out: h5py.File, source: h5py.Dataset, path: str, leading_dim: int) -> h5py.Dataset:
    _ensure_parent(out, path)
    shape = (leading_dim, *tuple(int(dim) for dim in source.shape[1:]))
    chunks = source.chunks
    if chunks is None or chunks[0] > max(1, leading_dim):
        chunks = (min(_COPY_BLOCK, max(1, leading_dim)), *shape[1:])
    kwargs: dict[str, Any] = {"shape": shape, "dtype": source.dtype, "chunks": chunks}
    if source.compression is not None:
        kwargs["compression"] = source.compression
        if source.compression_opts is not None:
            kwargs["compression_opts"] = source.compression_opts
    result = out.create_dataset(path, **kwargs)
    for key, value in source.attrs.items():
        result.attrs[key] = value
    return result


def _copy_rows(source: h5py.Dataset, target: h5py.Dataset, source_start: int, source_stop: int, target_start: int) -> None:
    count = source_stop - source_start
    for offset in range(0, count, _COPY_BLOCK):
        stop = min(count, offset + _COPY_BLOCK)
        target[target_start + offset : target_start + stop] = source[source_start + offset : source_start + stop]


def merge_trajectories(
    source_paths: Sequence[str | os.PathLike[str]],
    output_path: str | os.PathLike[str],
    *,
    max_episodes: int = DEFAULT_MAX_EPISODES,
    max_transitions: int = DEFAULT_MAX_TRANSITIONS,
) -> Path:
    """Merge compatible v2 trajectories into one bounded raw H5 stream.

    Input files remain immutable.  Files are validated before the output is
    created, so incompatible schema, shape, terminal, or metadata errors carry
    the offending filename in their diagnostic.
    """

    paths = tuple(Path(path) for path in source_paths)
    target = Path(output_path)
    if not paths:
        raise TrajectoryMergeError("merge requires at least one input trajectory")
    if max_episodes < 1 or max_transitions < 1:
        raise TrajectoryMergeError("merge bounds must be positive")
    if len(paths) > max_episodes:
        raise TrajectoryMergeError(f"merge exceeds max_episodes={max_episodes}: got {len(paths)}")
    if any(path.resolve() == target.resolve() for path in paths):
        raise TrajectoryMergeError("source and output H5 paths must differ")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")

    infos = tuple(_inspect_source(path) for path in paths)
    reference = infos[0]
    for info in infos[1:]:
        _validate_compatibility(reference, info)
    total_transitions = sum(info.transition_count for info in infos)
    if total_transitions > max_transitions:
        raise TrajectoryMergeError(
            f"merge exceeds max_transitions={max_transitions}: got {total_transitions}"
        )
    total_observations = total_transitions + 1
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")

    boundaries: list[dict[str, Any]] = []
    transition_cursor = 0
    observation_cursor = 0
    for index, info in enumerate(infos):
        boundaries.append(
            {
                "episode_index": index,
                "episode_id": index,
                "source_file": str(info.path),
                "source_file_id": info.source_id,
                "source_transition_count": info.transition_count,
                "source_observation_count": info.observation_count,
                "merged_transition_start": transition_cursor,
                "merged_transition_end": transition_cursor + info.transition_count,
                "merged_observation_start": observation_cursor,
                "merged_observation_end": observation_cursor + (info.observation_count if index == 0 else info.transition_count),
                "reset_observation_dropped": index != 0,
            }
        )
        transition_cursor += info.transition_count
        observation_cursor += info.observation_count if index == 0 else info.transition_count

    try:
        with h5py.File(temporary, "w") as out:
            with h5py.File(reference.path, "r") as first:
                for key, value in first.attrs.items():
                    out.attrs[key] = value
                out.attrs.update(
                    transition_count=total_transitions,
                    observation_count=total_observations,
                    episode_count=len(infos),
                    episode_complete=True,
                    stop_reason="merged",
                )
                output_datasets: dict[str, h5py.Dataset] = {}
                for dataset_path in reference.dataset_paths:
                    source_dataset = first[dataset_path]
                    leading = total_observations if dataset_path.startswith("obs/") else total_transitions
                    output_datasets[dataset_path] = _create_dataset_like(out, source_dataset, dataset_path, leading)

            transition_cursor = 0
            observation_cursor = 0
            for index, info in enumerate(infos):
                with h5py.File(info.path, "r") as src:
                    for dataset_path in info.dataset_paths:
                        source = src[dataset_path]
                        target_dataset = output_datasets[dataset_path]
                        if dataset_path.startswith("obs/"):
                            source_start = 0 if index == 0 else 1
                            target_start = observation_cursor
                            _copy_rows(source, target_dataset, source_start, info.observation_count, target_start)
                        else:
                            _copy_rows(source, target_dataset, 0, info.transition_count, transition_cursor)
                observation_cursor += info.observation_count if index == 0 else info.transition_count
                transition_cursor += info.transition_count

            universal_group = out.require_group("universal_action")
            episode_ids = universal_group.create_dataset(
                "episode_id", shape=(total_transitions,), dtype=np.int32,
                chunks=(min(_COPY_BLOCK, max(1, total_transitions)),),
            )
            cursor = 0
            for index, info in enumerate(infos):
                if info.transition_count:
                    episode_ids[cursor : cursor + info.transition_count] = np.full(
                        info.transition_count, index, dtype=np.int32
                    )
                cursor += info.transition_count

            meta_group = out.require_group("meta")
            merged_meta = dict(reference.env_meta)
            merged_meta["merge"] = {
                "schema_version": "task-env-trajectory-merge-v1",
                "episode_count": len(infos),
                "transition_count": total_transitions,
                "observation_count": total_observations,
                "reset_observations_dropped": len(infos) - 1,
                "episode_id_path": "universal_action/episode_id",
                "episode_boundaries": [0]
                + [item["merged_transition_end"] for item in boundaries],
                "episodes": boundaries,
                "contexts": [
                    dict(item.env_meta.get("replay_context", {}))
                    for item in infos
                ],
                "source_files": [item["source_file"] for item in boundaries],
                "source_file_ids": [item["source_file_id"] for item in boundaries],
            }
            merged_meta["trajectory"] = {
                **dict(merged_meta.get("trajectory", {})),
                "observation_count_semantics": "T+1 (reset observations omitted between merged episodes)",
                "transition_count_semantics": "T",
            }
            meta_group.create_dataset(
                "env_meta",
                data=np.asarray(dump_metadata(merged_meta), dtype=h5py.string_dtype("utf-8")),
            )
            meta_group.create_dataset(
                "env_cfg",
                data=np.asarray(yaml.safe_dump(reference.env_cfg, sort_keys=True, allow_unicode=True), dtype=h5py.string_dtype("utf-8")),
            )
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


__all__ = ["TrajectoryMergeError", "merge_trajectories"]
