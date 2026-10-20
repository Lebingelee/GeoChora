"""场景资产契约出口与有限的声明/来源摘要转换。"""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Mapping

from ..artifacts import AssetDefinition
from ..environment import AssetManifest


def _asset_definition_from_manifest(manifest: AssetManifest) -> AssetDefinition:
    """Convert an existing component manifest to its canonical declaration.

    The source URI remains authored by the asset owner. Local paths and
    importer hashes are deliberately not guessed into stable asset identity.
    """

    if not manifest.source_reference:
        raise ValueError(
            f"asset manifest {manifest.owner_uid!r} has no stable source_reference"
        )
    return AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id=manifest.owner_uid,
        asset_version=manifest.asset_version,
        source_reference=manifest.source_reference,
        source_revision=manifest.source_revision,
    )


def _source_closure_manifest(files: Mapping[str, bytes]) -> tuple[dict[str, object], ...]:
    """Describe an immutable file snapshot by logical paths and exact bytes.

    Callers must supply bytes from the same snapshot passed to the importer.
    Absolute checkout paths are rejected so equivalent source trees hash the
    same across roots.
    """

    if not isinstance(files, Mapping):
        raise TypeError("source closure files must map logical paths to bytes")
    entries = []
    seen = set()
    for raw_path, raw_content in files.items():
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("source closure paths must be nonempty relative strings")
        if "\\" in raw_path or raw_path.startswith("/") or (len(raw_path) >= 2 and raw_path[1] == ":"):
            raise ValueError(f"source closure path must be root-relative POSIX: {raw_path!r}")
        path = PurePosixPath(raw_path)
        if any(part in {"", ".", ".."} for part in raw_path.split("/")) or path.as_posix() != raw_path:
            raise ValueError(f"source closure path is not canonical: {raw_path!r}")
        logical_path = path.as_posix()
        if logical_path in seen:
            raise ValueError(f"duplicate source closure path: {logical_path!r}")
        if not isinstance(raw_content, bytes):
            raise TypeError(f"source closure content for {logical_path!r} must be bytes")
        seen.add(logical_path)
        entries.append(
            {
                "path": logical_path,
                "size_bytes": len(raw_content),
                "sha256": hashlib.sha256(raw_content).hexdigest(),
            }
        )
    if not entries:
        raise ValueError("source closure must contain at least one file")
    return tuple(sorted(entries, key=lambda entry: str(entry["path"])))


def _source_closure_digest(files: Mapping[str, bytes]) -> str:
    """Hash an immutable file snapshot by logical paths and exact bytes."""

    payload = {
        "schema_version": "source-closure-v1",
        "files": list(_source_closure_manifest(files)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

__all__ = ["AssetManifest"]
