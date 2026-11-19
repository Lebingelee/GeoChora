"""References to original diagnostic executions, kept outside the runtime path."""

from __future__ import annotations

from pathlib import Path

from .task import _check_file, _read, _source, get_task


def reference_files(task_id: str, simdatakit_root) -> dict[str, Path]:
    """Resolve and verify a selected v2 preview's code, recordings and task snapshot.

    The previews use a direct GeoPhys/Flora runner. This function reads the
    pinned artifact bytes and verifies the snapshot against the frozen task.
    """
    task = get_task(task_id)
    root = Path(simdatakit_root).resolve()
    references = _source()["tasks"][task_id]["reference"]
    if not references:
        raise FileNotFoundError(f"no recorded reference execution for {task_id!r}")
    files = {name: _check_file(root / item["path"], item["sha256"])
             for name, item in references.items()}
    if _read(files["task_snapshot"]) != task:
        raise ValueError("reference execution belongs to a different task record")
    return files
