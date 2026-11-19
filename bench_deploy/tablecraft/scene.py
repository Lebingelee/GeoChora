"""Prepare one shared, hash-pinned internal asset bundle; no physics is started."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from .task import PACKAGE, _check_file, _read, _source, get_task


def prepare_assets(source_release, output_directory) -> Path:
    """Copy the required source resources into a fresh portable resource directory.

    The release must be the pinned franka-scene-50@2.0.0. Binary assets are
    copied from the internal release.
    Relative resource paths in the original prompts work from this directory.
    """
    source = _source()
    release = Path(source_release).resolve()
    output = Path(output_directory).resolve()
    if output.exists():
        raise FileExistsError(f"asset output must be a fresh directory: {output}")
    _check_file(release / "manifest.json", source["manifest_sha256"])
    _check_file(release / "tasks.jsonl", source["source_tasks_sha256"])
    files = {item["path"]: item["sha256"] for item in source["resources"].values()}
    files["LICENSE.txt"] = source["license_sha256"]
    for relative, sha256 in files.items():
        _check_file(release / relative, sha256)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tablecraft-", dir=output.parent) as temporary:
        bundle = Path(temporary) / "bundle"
        bundle.mkdir()
        for relative, sha256 in files.items():
            target = bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release / relative, target)
            _check_file(target, sha256)
        shutil.copyfile(PACKAGE / "tasks.jsonl", bundle / "tasks.jsonl")
        _check_file(bundle / "tasks.jsonl", source["source_tasks_sha256"])
        bundle.rename(output)
    return output


def scene_resources(task_id: str, asset_directory) -> dict:
    """Resolve exact source assets and authored setup for a task consumer.

    The caller uses these preparation inputs to preserve source geometry,
    fixed robot setup, object identities and authored initial state.
    """
    task = get_task(task_id)
    source = _source()
    directory = Path(asset_directory).resolve()
    paths = {item["id"]: _check_file(directory / item["path"],
                                    source["resources"][item["id"]]["sha256"])
             for item in task["resources"]}
    setup_id = next(item["id"] for item in task["resources"] if item["type"] == "initial_state")
    return {"task_id": task_id, "paths": paths,
            "scene_contract": _read(paths["scene_contract"]), "setup": _read(paths[setup_id]),
            "object_manifest": _read(paths["object_manifest"]),
            "predicate_vocabulary": paths["predicate_vocabulary"].read_bytes().decode("utf-8")}
