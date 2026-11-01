"""场景资产契约出口与有限的声明/来源摘要转换。"""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable, Mapping

from ..artifacts import AssetDefinition
from ..environment import AssetManifest


_MAX_CLOSURE_ARCHIVE_BYTES = 128 * 1024 * 1024
_MAX_CLOSURE_ARCHIVE_MEMBERS = 1024
_MAX_CLOSURE_EXPANDED_BYTES = 128 * 1024 * 1024


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


def _read_source_closure_archive(path: Path, expected_manifest: Iterable[Mapping[str, object]]) -> dict[str, bytes]:
    """Read a bounded ``closure/`` tar and verify every member against its receipt."""
    archive_path = Path(path)
    if archive_path.is_symlink():
        raise ValueError("source closure archive must not be a symlink")
    archive_path = archive_path.resolve(strict=True)
    if not archive_path.is_file() or archive_path.stat().st_size > _MAX_CLOSURE_ARCHIVE_BYTES:
        raise ValueError("source closure archive is not a bounded regular file")

    expected = {}
    for row in expected_manifest:
        if not isinstance(row, Mapping):
            raise ValueError("source closure archive manifest row is malformed")
        logical, size, sha = row.get("path"), row.get("size_bytes"), row.get("sha256")
        if (type(logical) is not str or not logical or logical in expected
                or logical.startswith("/") or "\\" in logical
                or any(part in {"", ".", ".."} for part in logical.split("/"))):
            raise ValueError("source closure archive manifest has an unsafe or duplicate path")
        if (type(size) is not int or size < 0 or type(sha) is not str
                or len(sha) != 64 or any(char not in "0123456789abcdef" for char in sha)):
            raise ValueError("source closure archive manifest has invalid byte identity")
        expected[logical] = (size, sha)
    if not expected:
        raise ValueError("source closure archive manifest is empty")

    expected_dirs = {"closure"}
    for logical in expected:
        parts = PurePosixPath("closure", logical).parts
        expected_dirs.update("/".join(parts[:index]) for index in range(1, len(parts)))
    files, seen, expanded = {}, set(), 0
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) > _MAX_CLOSURE_ARCHIVE_MEMBERS:
                raise ValueError("source closure archive has too many members")
            for member in members:
                name = member.name
                if (type(name) is not str or not name or name.startswith("/") or "\\" in name
                        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))):
                    raise ValueError("source closure archive has an unsafe member path")
                if name in seen:
                    raise ValueError("source closure archive has duplicate members")
                seen.add(name)
                normalized = name.rstrip("/")
                if member.isdir():
                    if normalized not in expected_dirs or member.size != 0:
                        raise ValueError("source closure archive has an unlisted directory")
                    continue
                logical = name.removeprefix("closure/")
                if (not member.isfile() or not name.startswith("closure/")
                        or logical not in expected or logical in files):
                    raise ValueError("source closure archive member set differs from its manifest")
                size, sha = expected[logical]
                if member.size != size:
                    raise ValueError("source closure archive member size differs from its manifest")
                expanded += size
                if expanded > _MAX_CLOSURE_EXPANDED_BYTES:
                    raise ValueError("source closure archive exceeds the expanded byte limit")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("source closure archive member could not be read")
                content = stream.read(size + 1)
                if len(content) != size or hashlib.sha256(content).hexdigest() != sha:
                    raise ValueError("source closure archive member bytes differ from its manifest")
                files[logical] = content
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("source closure archive is not a valid bounded tar.gz") from exc
    if set(files) != set(expected):
        raise ValueError("source closure archive is missing manifest members")
    _source_closure_manifest(files)
    return files

__all__ = ["AssetManifest"]
