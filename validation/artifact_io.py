"""Shared read-only artifact IO for offline qualification diagnostics."""
import hashlib
import json
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checked_ref(root, ref):
    path = (root / ref["path"]).resolve()
    if Path(ref["path"]).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("artifact reference escapes input root")
    if digest(path) != ref["sha256"]:
        raise ValueError(f"artifact hash mismatch: {ref['path']}")
    return path
