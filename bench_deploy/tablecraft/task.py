"""Read the frozen TableCraft task collection without a SimDataKit dependency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from validation.inputs import validate_task


PACKAGE = Path(__file__).resolve().parent


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check_file(path, sha256):
    path = Path(path)
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != sha256:
        raise ValueError(f"source bytes changed: {path}")
    return path


def _source():
    return _read(PACKAGE / "source.json")


def _tasks():
    source = _source()
    path = _check_file(PACKAGE / "tasks.jsonl", source["source_tasks_sha256"])
    return [validate_task(json.loads(line), label=f"{path}:{number}")
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()]


def get_task(task_id: str) -> dict:
    """Return an independent copy of the full source task, including private truth."""
    for task in _tasks():
        if task["task_id"] == task_id:
            return task
    raise KeyError(f"unknown TableCraft task: {task_id!r}")


def list_tasks() -> list[dict]:
    """Return task IDs, titles and families in the frozen release order."""
    return [{"task_id": task_id, "title": item["title"], "family": item["family"]}
            for task_id, item in _source()["tasks"].items()]


def model_prompt(task_id: str) -> dict:
    """Public model input; never include truth, reference executions or judgments."""
    task = get_task(task_id)
    return {key: value for key, value in task.items() if key != "truth"}


def task_source(task_id: str) -> dict:
    """Freeze original requirements and their public text dependencies for review."""
    task = get_task(task_id)
    dependencies = {}
    source = _source()
    for resource in task["resources"]:
        resource_format = resource["format"]
        if resource_format in {"json", "yaml"}:
            resource_id = resource["id"]
            path = _check_file(PACKAGE / resource["path"], source["resources"][resource_id]["sha256"])
            dependencies[resource_id] = _read(path) if resource_format == "json" else path.read_bytes().decode("utf-8")
    return {"task": task, "dependencies": dependencies}
