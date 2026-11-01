#!/usr/bin/env python3
"""Reproducible, local-only LIBERO pilot source installation and verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

TOOL_VERSION = "r07b-libero-source-bundle-v1"
MANIFEST_SCHEMA = "libero-pilot-source-manifest-v1"
INSTALL_SCHEMA = "libero-pilot-source-install-receipt-v1"
VERIFY_SCHEMA = "libero-pilot-source-verify-receipt-v1"
TASK_UID = "libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate"
LIBERO_REV = "8f1084e3132a39270c3a13ebe37270a43ece2a01"
ROBOSUITE_REV = "fbee5844ff5632f5b5698e204ec5357ca50be0df"
FIXED_REVISIONS = {"libero": LIBERO_REV, "robosuite": ROBOSUITE_REV}
ALLOWED_PILOT_FAMILIES = {
    "LIBERO-authored or bundled fixture source",
    "LIBERO selected scene texture/background fixture",
    "Google Scanned Objects / scanned-object collection",
    "HOPE object collection",
    "robosuite repository / Panda, mount, gripper, or arena assets",
}
REWRITE_SCENE = "libero:libero/libero/assets/scenes/libero_tabletop_base_style.xml"


class BundleError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob_sha1(value: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(value)).encode("ascii") + b"\0" + value).hexdigest()


def reject_constant(value: str):
    raise BundleError("non-finite JSON constant is forbidden: " + value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BundleError("duplicate JSON object key: " + key)
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError("cannot read JSON " + str(path) + ": " + str(exc)) from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    path.write_bytes(payload)


def validate_relpath(value: Any, field: str) -> str:
    if type(value) is not str or not value or "\\" in value:
        raise BundleError(field + " must be a nonempty canonical POSIX relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or any(part in {"", ".", ".."} for part in value.split("/")):
        raise BundleError(field + " is unsafe or noncanonical: " + repr(value))
    return value


def parse_source_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for item in values:
        if "=" not in item:
            raise BundleError("source root must use ID=PATH syntax")
        root_id, raw_path = item.split("=", 1)
        if not root_id or not raw_path or root_id in roots:
            raise BundleError("duplicate or empty source root: " + repr(root_id))
        path = Path(raw_path)
        if path.is_symlink() or not path.is_dir():
            raise BundleError("source root must be an existing non-symlink directory: " + str(path))
        roots[root_id] = path.resolve()
    return roots


def path_no_symlink(root: Path, relpath: str) -> Path:
    relpath = validate_relpath(relpath, "path")
    current = root
    for part in PurePosixPath(relpath).parts:
        current = current / part
        if current.is_symlink():
            raise BundleError("symlink source or destination path is forbidden: " + str(current))
    resolved = current.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise BundleError("path escaped configured root: " + relpath) from exc
    return current


def read_checked(root: Path, relpath: str, *, expected_size: int, expected_sha256: str, expected_git_blob_sha1: str) -> bytes:
    path = path_no_symlink(root, relpath)
    if not path.is_file():
        raise BundleError("source file is missing: " + relpath)
    content = path.read_bytes()
    if len(content) != expected_size:
        raise BundleError("source byte size mismatch: " + relpath)
    if sha256_bytes(content) != expected_sha256:
        raise BundleError("source SHA-256 mismatch: " + relpath)
    if git_blob_sha1(content) != expected_git_blob_sha1:
        raise BundleError("source Git blob SHA-1 mismatch: " + relpath)
    return content


def _repo_id(row: dict) -> str:
    value = row.get("repository") or row.get("repo")
    if value not in FIXED_REVISIONS:
        raise BundleError("unexpected upstream repository: " + repr(value))
    return value


def _license_record(
    notice_id: str, status: str, attribution: str, redistribution_approved: bool,
    source_group: str, *, family_id: str | None = None, first_use_disposition: str | None = None,
) -> dict:
    return {
        "notice_id": notice_id,
        "license_status": status,
        "attribution": attribution,
        "redistribution_approved": redistribution_approved,
        "pilot_source_family": source_group,
        "pilot_family_id": family_id,
        "first_use_disposition": first_use_disposition,
        "local_install_disposition": "LOCAL_SOURCE_AUDIT_ONLY; does not grant runtime use, redistribution, or release rights",
    }


def _source_id(repo: str, path: str) -> str:
    return repo + ":" + path


def _tree_index(path: Path, repo: str) -> dict[str, dict]:
    value = read_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("tree"), list):
        raise BundleError("pinned tree index is malformed: " + str(path))
    expected_tree_commit = LIBERO_REV if repo == "libero" else None
    if repo == "libero" and value.get("sha") != expected_tree_commit:
        raise BundleError("LIBERO tree metadata has the wrong pinned revision")
    if repo == "robosuite" and value.get("sha") != "81dc0e1649a610baa76458b6e01ea5add73a8f1f":
        raise BundleError("robosuite tree metadata has the wrong fixed tree")
    return {row["path"]: row for row in value["tree"] if isinstance(row, dict) and isinstance(row.get("path"), str)}


def _choose_source(root_map: dict[str, Path], repo: str, relpath: str, preferred: list[str]) -> tuple[str, Path]:
    for root_id in preferred:
        if root_id not in root_map:
            continue
        candidate = path_no_symlink(root_map[root_id], relpath)
        if candidate.is_file():
            return root_id, candidate
    raise BundleError("no configured source root contains " + repo + ":" + relpath)


def _entry_from_bytes(
    *,
    repo: str,
    revision: str,
    source_root_id: str,
    source_path: str,
    install_path: str,
    role: str,
    content: bytes,
    git_blob: str,
    license_record: dict,
    task_binding: str = TASK_UID,
    xml_source: bool = False,
    asset_kind: str | None = None,
) -> dict:
    return {
        "entry_id": _source_id(repo, source_path),
        "repository": repo,
        "revision": revision,
        "source_root_id": source_root_id,
        "source_path": source_path,
        "install_path": install_path,
        "role": role,
        "asset_kind": asset_kind,
        "xml_source": xml_source,
        "size_bytes": len(content),
        "sha256": sha256_bytes(content),
        "git_blob_sha1": git_blob,
        "task_binding": task_binding,
        "license": license_record,
    }


def _code_reference(
    *,
    repo: str,
    revision: str,
    source_path: str,
    root_map: dict[str, Path],
    tree_index: dict[str, dict],
    preferred_roots: list[str],
    role: str,
    expected_sha256: str | None = None,
    expected_blob: str | None = None,
) -> dict:
    validate_relpath(source_path, "source code path")
    tree_row = tree_index.get(source_path, {})
    blob = expected_blob or tree_row.get("sha")
    size = tree_row.get("size")
    root_id = None
    content_hash = expected_sha256
    content_size = size
    if expected_sha256 is not None:
        for candidate_id in preferred_roots:
            if candidate_id in root_map and path_no_symlink(root_map[candidate_id], source_path).is_file():
                root_id = candidate_id
                content = path_no_symlink(root_map[candidate_id], source_path).read_bytes()
                if sha256_bytes(content) != expected_sha256:
                    raise BundleError("construction code cache differs from its pinned SHA-256: " + source_path)
                if blob and git_blob_sha1(content) != blob:
                    raise BundleError("construction code cache differs from its pinned Git blob: " + source_path)
                content_size = len(content)
                break
    else:
        for candidate_id in preferred_roots:
            if candidate_id in root_map and path_no_symlink(root_map[candidate_id], source_path).is_file():
                root_id = candidate_id
                content = path_no_symlink(root_map[candidate_id], source_path).read_bytes()
                content_hash = sha256_bytes(content)
                content_size = len(content)
                measured_blob = git_blob_sha1(content)
                if blob and measured_blob != blob:
                    raise BundleError("construction code cache differs from tree metadata: " + source_path)
                blob = measured_blob
                break
    if not isinstance(blob, str) or len(blob) != 40:
        raise BundleError("pinned Git tree hash is missing for source code reference: " + source_path)
    return {
        "repository": repo,
        "revision": revision,
        "path": source_path,
        "role": role,
        "size_bytes": content_size,
        "sha256": content_hash,
        "git_blob_sha1": blob,
        "bytes_verified_from_cache": root_id is not None,
        "source_root_id": root_id,
        "source_cache_path": source_path if root_id is not None else None,
    }


def _scene_rewrite_rule(scene_source: dict, style_code: dict, table_code: dict) -> dict:
    if scene_source.get("style_properties") != {"floor_style": "light-gray", "wall_style": "light-gray-plaster"}:
        raise BundleError("pilot tabletop scene style selection differs from the frozen source audit")
    return {
        "source_xml": {"repository": "libero", "path": scene_source["path"], "sha256": scene_source["sha256"]},
        "owner_code": [
            {"path": "libero/libero/envs/arenas/table_arena.py", "sha256": table_code["sha256"], "git_blob_sha1": table_code["git_blob_sha1"]},
            {"path": "libero/libero/envs/arenas/style.py", "sha256": style_code["sha256"], "git_blob_sha1": style_code["git_blob_sha1"]},
        ],
        "properties": scene_source["style_properties"],
        "rules": [
            {
                "element": "texture",
                "name": "texplane",
                "declared_ref": "../textures/tile_grigia_caldera_porcelain_floor.png",
                "effective_ref": "../textures/light-gray-floor-tile.png",
            },
            {
                "element": "texture",
                "name": "tex-wall",
                "declared_ref": "../textures/smooth_light_gray_plaster.png",
                "effective_ref": "../textures/light-gray-plaster.png",
            },
        ],
        "implementation": "LIBERO TableArena replaces the basename for texplane and tex-wall using style.py; unchanged table and table-leg texture paths remain source-authored.",
    }


def build_manifest(args) -> dict:
    root_map = parse_source_roots(args.source_root)
    asset_input = read_json(Path(args.asset_input))
    inventory = read_json(Path(args.task_inventory))
    scene_closure = read_json(Path(args.scene_closure))
    license_scope = read_json(Path(args.license_scope))
    sol_review_path = Path(args.sol_review)
    if not sol_review_path.is_file():
        raise BundleError("R07a004 Sol review source is missing")
    if asset_input.get("schema") != "r07b-pilot-asset-input-v1" or asset_input.get("task") != TASK_UID:
        raise BundleError("pilot asset input schema or task id is unexpected")
    if scene_closure.get("schema") != "r07a002-dynamic-scene-asset-closure-v1":
        raise BundleError("dynamic scene closure source schema is unexpected")
    if license_scope.get("schema") != "r07a002-license-scope-v1" and "asset_path_rows" not in license_scope:
        raise BundleError("license scope source is not the R07a002 asset receipt")
    task_rows = [row for row in inventory.get("tasks", []) if row.get("task_id") == TASK_UID]
    if len(task_rows) != 1:
        raise BundleError("pinned task source inventory must contain exactly one pilot task")
    task = task_rows[0]
    if inventory.get("source_revisions", {}).get("LIBERO") != LIBERO_REV:
        raise BundleError("task source inventory LIBERO revision differs from the fixed pin")
    if inventory.get("source_revisions", {}).get("robosuite") != ROBOSUITE_REV:
        raise BundleError("task source inventory robosuite revision differs from the fixed pin")
    license_rows = {(_repo_id(row), row["path"]): row for row in license_scope.get("asset_path_rows", [])}
    pilot_decision = read_json(Path(args.pilot_decision))
    if pilot_decision.get("schema") != "r07a004-source-family-disposition-v2":
        raise BundleError("pilot decision input is not the accepted R07a004 family disposition")
    if pilot_decision.get("gate") != "R07A_FINAL_BLOCKED_EXTERNAL_SOURCE_INPUT":
        raise BundleError("pilot decision no longer records the bounded source-only gate")
    if pilot_decision.get("scope", {}).get("asset_or_data_redistribution") != "Not authorized and not assessed in this package.":
        raise BundleError("pilot decision has an unexpected redistribution scope")
    pilot_family_tasks = [row for row in pilot_decision.get("families", []) if TASK_UID in row.get("tasks", [])]
    if not pilot_family_tasks:
        raise BundleError("pilot source decision does not identify any family used by the selected task")
    family_by_path = {}
    for family in pilot_family_tasks:
        for family_path in family.get("paths", []):
            key = (family_path.get("repo"), family_path.get("path"))
            if key in family_by_path:
                raise BundleError("source decision assigns a pilot asset path to multiple families: " + repr(key))
            family_by_path[key] = family

    def asset_license_record(key: tuple[str, str], row: dict) -> dict:
        family = family_by_path.get(key)
        if family is None:
            raise BundleError("selected asset lacks an exact R07a004 first-use family record: " + repr(key))
        if family.get("family_id") != row.get("family_id") or family.get("source_group") != row.get("source_group"):
            raise BundleError("asset input family identity differs from the accepted first-use decision: " + repr(key))
        if family.get("first_use_disposition") in (None, "") or "BLOCKED" in family["first_use_disposition"]:
            raise BundleError("selected asset family is not eligible for this local source pilot: " + family["family_id"])
        return _license_record(
            "family-review-" + hashlib.sha256(family["family_id"].encode()).hexdigest()[:12],
            row["license_status"],
            row.get("reuse_disposition", "No file-specific attribution or permission is inferred."),
            bool(row.get("redistribution_approved", False)), row["source_group"],
            family_id=family["family_id"], first_use_disposition=family["first_use_disposition"],
        )
    review_bytes = sol_review_path.read_bytes()

    tree_libero = _tree_index(Path(args.libero_tree_index), "libero")
    tree_robosuite = _tree_index(Path(args.robosuite_tree_index), "robosuite")
    tree_indexes = {"libero": tree_libero, "robosuite": tree_robosuite}

    def add_from_root(repo: str, revision: str, source_path: str, root_id: str, install_path: str,
                      role: str, *, xml_source: bool = False, asset_kind=None, license_row=None,
                      notice_id: str | None = None):
        validate_relpath(source_path, "source path")
        validate_relpath(install_path, "install path")
        tree_row = tree_indexes[repo].get(source_path)
        if not tree_row:
            raise BundleError("pinned tree lacks file path: " + repo + ":" + source_path)
        if root_id not in root_map:
            raise BundleError("required source root not configured: " + root_id)
        content = read_checked(
            root_map[root_id], source_path,
            expected_size=int(tree_row["size"]),
            expected_sha256=sha256_bytes(path_no_symlink(root_map[root_id], source_path).read_bytes()),
            expected_git_blob_sha1=tree_row["sha"],
        )
        if license_row is None:
            if repo == "libero":
                license_row = _license_record(
                    "libero-root-license-context", "LIBERO_ROOT_LICENSE_MIT; FILE_SPECIFIC_ASSET_TERMS_NOT_INFERRED",
                    "LIBERO root LICENSE is included as source context; it does not establish third-party asset terms.",
                    False, "LIBERO source",
                )
            else:
                license_row = _license_record(
                    "robosuite-root-license-context", "ROBOSUITE_ROOT_LICENSE_MIT; FILE_SPECIFIC_ASSET_TERMS_NOT_INFERRED",
                    "robosuite root LICENSE is included as source context; it does not establish third-party asset terms.",
                    False, "robosuite source",
                )
        if notice_id:
            license_row = dict(license_row, notice_id=notice_id)
        entry = _entry_from_bytes(
            repo=repo, revision=revision, source_root_id=root_id,
            source_path=source_path, install_path=install_path, role=role, content=content,
            git_blob=tree_row["sha"], license_record=license_row, xml_source=xml_source,
            asset_kind=asset_kind,
        )
        return entry, content

    files: list[dict] = []
    source_contents: dict[str, bytes] = {}
    entry_keys: set[tuple[str, str]] = set()
    install_paths: set[str] = set()

    def add_entry(entry: dict, content: bytes):
        key = (entry["repository"], entry["source_path"])
        if key in entry_keys:
            if entry["role"] == "asset_dependency":
                return
            raise BundleError("duplicate source file entry: " + repr(key))
        if entry["install_path"] in install_paths:
            raise BundleError("duplicate logical installation path: " + entry["install_path"])
        entry_keys.add(key)
        install_paths.add(entry["install_path"])
        files.append(entry)
        source_contents[entry["entry_id"]] = content

    input_asset_map = {(_repo_id(row), row["path"]): row for row in asset_input["rows"]}
    if len(input_asset_map) != len(asset_input["rows"]):
        raise BundleError("duplicate path in pilot asset input")
    task_dependency_map = {(_repo_id(row), row["path"]): row for row in task["unique_file_dependencies"]}
    dynamic = scene_closure["scene_sources"].get("libero/libero/assets/scenes/libero_tabletop_base_style.xml")
    if not isinstance(dynamic, dict) or TASK_UID not in dynamic.get("task_ids", []):
        raise BundleError("active LIBERO tabletop scene source is missing from prior closure")

    active_xml_specs = []
    excluded_xml_specs = []
    for item in task["selected_xml_closure"]:
        src = item["source_xml"]
        repo = _repo_id(src)
        path = src["path"]
        if repo == "robosuite" and path == "robosuite/models/assets/arenas/table_arena.xml":
            excluded_xml_specs.append(src)
            continue
        active_xml_specs.append(src)
    active_xml_specs.append({
        "repo": "libero",
        "path": "libero/libero/assets/scenes/libero_tabletop_base_style.xml",
        "bytes": dynamic["tree_bytes"],
        "sha256": dynamic["sha256"],
        "git_blob_sha": dynamic["tree_git_blob_sha"],
        "license": {"source_group": "LIBERO source", "status": "LIBERO_ROOT_LICENSE_MIT; FILE_SPECIFIC_ASSET_TERMS_NOT_INFERRED"},
    })
    if len(active_xml_specs) != 10:
        raise BundleError("actual active XML input set must contain six task objects, Panda, gripper, mount, and LIBERO scene")

    xml_entries: dict[tuple[str, str], dict] = {}
    for src in active_xml_specs:
        repo = _repo_id(src)
        revision = FIXED_REVISIONS[repo]
        path = src["path"]
        root_id = "libero-tree" if repo == "libero" else "robosuite-tree"
        if repo == "libero" and path == "libero/libero/assets/scenes/libero_tabletop_base_style.xml":
            root_id = "libero-readback"
        tree_row = tree_indexes[repo].get(path)
        if not tree_row:
            raise BundleError("active XML not present in pinned tree metadata: " + path)
        if int(src.get("bytes", src.get("tree_bytes", -1))) != int(tree_row["size"]):
            raise BundleError("active XML byte count differs from pinned tree: " + path)
        if src.get("sha256") != sha256_bytes(path_no_symlink(root_map[root_id], path).read_bytes()):
            raise BundleError("active XML SHA-256 differs from source index: " + path)
        role = "scene_xml" if path.endswith("libero_tabletop_base_style.xml") else (
            "robot_xml" if "/robots/panda/" in path else "gripper_xml" if "/grippers/panda_gripper.xml" in path
            else "mount_xml" if "/mounts/rethink_mount.xml" in path else "object_xml"
        )
        notice_id = "libero-root-license-context" if repo == "libero" else "robosuite-root-license-context"
        license_rec = _license_record(
            notice_id,
            "ROOT_CODE_LICENSE_MIT; ASSET_ORIGIN_TERMS_NOT_SEPARATELY_VERIFIED",
            "Root code license is source context only; no separate asset redistribution or robot-origin grant is inferred.",
            False,
            "LIBERO source" if repo == "libero" else "robosuite source",
        )
        entry, content = add_from_root(
            repo, revision, path, root_id, "upstream/" + repo + "/" + path, role,
            xml_source=True, license_row=license_rec,
        )
        add_entry(entry, content)
        xml_entries[(repo, path)] = entry

    bddl = task["bddl"]
    init = task["selected_pruned_init"]
    for row, role in ((bddl, "task_bddl"), (init, "native_pruned_init_bytes")):
        path = row["path"]
        source_row = next((x for x in task["semantic_source_files"] if x["path"] == path), None)
        if source_row is None:
            raise BundleError("task source inventory lacks BDDL or selected init identity")
        expected_sha = row.get("sha256") or source_row["sha256"]
        expected_size = row.get("bytes", source_row.get("bytes"))
        expected_blob = source_row.get("git_blob_sha")
        if not expected_blob:
            raise BundleError("task input has no pinned Git blob identity: " + path)
        data = read_checked(
            root_map["libero-tree"], path, expected_size=expected_size,
            expected_sha256=expected_sha, expected_git_blob_sha1=expected_blob,
        )
        license_rec = _license_record(
            "libero-root-license-context",
            "LIBERO_ROOT_LICENSE_MIT; TASK_SOURCE_BYTES_ONLY",
            "Pinned task source bytes are included for local audit only; init data is not deserialized.",
            False, "LIBERO source",
        )
        entry = _entry_from_bytes(
            repo="libero", revision=LIBERO_REV, source_root_id="libero-tree",
            source_path=path, install_path="upstream/libero/" + path, role=role, content=data,
            git_blob=expected_blob, license_record=license_rec,
        )
        add_entry(entry, data)

    # Only XML-resolved assets from the actual selected assembly are installed.
    scene_ref_edges = []
    asset_refs = set()
    rewrite_rule = {
        "source_xml": {"repository": "libero", "path": "libero/libero/assets/scenes/libero_tabletop_base_style.xml", "sha256": dynamic["sha256"]},
        "rules": [
            {"element": "texture", "name": "texplane", "declared_ref": "../textures/tile_grigia_caldera_porcelain_floor.png", "effective_ref": "../textures/light-gray-floor-tile.png"},
            {"element": "texture", "name": "tex-wall", "declared_ref": "../textures/smooth_light_gray_plaster.png", "effective_ref": "../textures/light-gray-plaster.png"},
        ],
    }
    # Use all declared task dependencies except the unselected robosuite table arena,
    # then add the effective LIBERO style references parsed from the selected scene XML.
    for key in task_dependency_map:
        if key[0] == "robosuite" and key[1].startswith("robosuite/models/assets/textures/"):
            continue
        if key not in input_asset_map:
            raise BundleError("task source dependency is missing from pilot asset input: " + repr(key))
        row = input_asset_map[key]
        root_id = "libero-assets" if key[0] == "libero" else "robosuite-assets"
        source_data = read_checked(
            root_map[root_id], row["path"],
            expected_size=int(row["expected_bytes"]),
            expected_sha256=row["sha256"],
            expected_git_blob_sha1=row["tree_git_blob_sha"],
        )
        source_group = row["source_group"]
        if source_group not in ALLOWED_PILOT_FAMILIES:
            raise BundleError("asset family is not eligible for this local pilot: " + source_group)
        license_rec = asset_license_record(key, row)
        entry = _entry_from_bytes(
            repo=key[0], revision=row["revision"], source_root_id=root_id,
            source_path=row["path"], install_path="upstream/" + key[0] + "/" + row["path"],
            role="asset_dependency", content=source_data, git_blob=row["tree_git_blob_sha"],
            license_record=license_rec, asset_kind=row.get("kind"),
        )
        add_entry(entry, source_data)
        asset_refs.add(key)

    # Resolve effective scene references using the exact style values selected by the task source.
    for rule in rewrite_rule["rules"]:
        scene_ref_edges.append({
            "source_xml": rewrite_rule["source_xml"],
            "element": rule["element"],
            "name": rule["name"],
            "declared_ref": rule["declared_ref"],
            "effective_ref": rule["effective_ref"],
            "resolved_source_path": posixpath.normpath(posixpath.join("libero/libero/assets/scenes", rule["effective_ref"])),
        })
    for edge in dynamic["file_edges"]:
        # The accepted dynamic closure records the effective style path for
        # these two texture elements; install that path, not the source XML's
        # obsolete declared basename.
        key = ("libero", edge["repo_path"])
        if key not in input_asset_map:
            raise BundleError("effective LIBERO scene dependency missing from fixed asset input: " + repr(key))
        row = input_asset_map[key]
        root_id = "libero-assets"
        data = read_checked(root_map[root_id], row["path"], expected_size=int(row["expected_bytes"]),
                            expected_sha256=row["sha256"], expected_git_blob_sha1=row["tree_git_blob_sha"])
        source_group = row["source_group"]
        if source_group not in ALLOWED_PILOT_FAMILIES:
            raise BundleError("scene asset family is not eligible for this local pilot")
        license_rec = asset_license_record(key, row)
        if key not in asset_refs:
            entry = _entry_from_bytes(
                repo=key[0], revision=row["revision"], source_root_id=root_id,
                source_path=row["path"], install_path="upstream/libero/" + row["path"],
                role="asset_dependency", content=data, git_blob=row["tree_git_blob_sha"],
                license_record=license_rec, asset_kind=row.get("kind"),
            )
            add_entry(entry, data)
            asset_refs.add(key)
    excluded_files = []
    for key, row in input_asset_map.items():
        if key in asset_refs:
            continue
        if key[0] == "robosuite" and key[1].startswith("robosuite/models/assets/textures/"):
            source_root_id = "robosuite-assets"
            data = read_checked(root_map[source_root_id], row["path"],
                                expected_size=int(row["expected_bytes"]), expected_sha256=row["sha256"],
                                expected_git_blob_sha1=row["tree_git_blob_sha"])
            excluded_files.append({
                "repository": key[0], "revision": row["revision"], "path": row["path"],
                "size_bytes": len(data), "sha256": sha256_bytes(data), "git_blob_sha1": git_blob_sha1(data),
                "source_root_id": source_root_id, "source_path": row["path"],
                "source_group": row["source_group"], "license_status": row["license_status"],
                "family_id": row.get("family_id"),
                "attribution": row.get("reuse_disposition"),
                "redistribution_approved": bool(row.get("redistribution_approved", False)),
                "reason": "The task source sets _arena_xml to the LIBERO tabletop style scene before TableArena construction; the robosuite default table_arena.xml is not selected, so its four texture paths are not consumed by this pilot.",
            })
            continue
        raise BundleError("pilot asset row is neither in active XML closure nor a specifically excluded arena candidate: " + repr(key))

    # Include the two root license texts as notices; these are provenance, not asset grants.
    notices = [
        {"notice_id": "libero-root-license-context", "kind": "repository-license-text", "repository": "libero",
         "description": "LIBERO root LICENSE text for source context only; does not establish third-party mesh/texture terms."},
        {"notice_id": "robosuite-root-license-context", "kind": "repository-license-text", "repository": "robosuite",
         "description": "robosuite root LICENSE text for source context only; does not establish robot/asset-origin rights."},
    ]
    family_records = {
        row["license"]["pilot_family_id"]: row["license"]
        for row in files if row["role"] == "asset_dependency"
    }
    for family_id, license_info in sorted(family_records.items()):
        notice_id = "family-review-" + hashlib.sha256(family_id.encode()).hexdigest()[:12]
        notices.append({
            "notice_id": notice_id,
            "kind": "source-family-review-context",
            "source_family_id": family_id,
            "source_family": license_info["pilot_source_family"],
            "first_use_disposition": license_info["first_use_disposition"],
            "description": "R07a004 first-use source review context for local noncommercial research only; no redistribution or broader license approval is inferred.",
            "decision_sha256": sha256_bytes(Path(args.pilot_decision).read_bytes()),
            "sol_review_sha256": sha256_bytes(review_bytes),
        })
    for repo, root_id, revision, notice_id, install_name in (
        ("libero", "libero-readback", LIBERO_REV, "libero-root-license-context", "notices/LIBERO-LICENSE.txt"),
        ("robosuite", "robosuite-audit", ROBOSUITE_REV, "robosuite-root-license-context", "notices/robosuite-LICENSE.txt"),
    ):
        entry, content = add_from_root(
            repo, revision, "LICENSE", root_id, install_name, "notice",
            license_row=_license_record(notice_id, "ROOT_LICENSE_TEXT; NOT_A_PER_ASSET_GRANT",
                                        "License text included for attribution context only.", False,
                                        repo + " source"),
        )
        add_entry(entry, content)

    # Fingerprint the source code which selects task, scene, style, robot and object owners.
    code_refs = []
    for row in task["semantic_source_files"]:
        path = row["path"]
        if not path.endswith(".py"):
            continue
        repo = _repo_id(row)
        preferred = ["libero-tree", "libero-readback"] if repo == "libero" else ["robosuite-tree", "robosuite-audit"]
        code_refs.append(_code_reference(
            repo=repo, revision=FIXED_REVISIONS[repo], source_path=path,
            root_map=root_map, tree_index=tree_indexes[repo], preferred_roots=preferred,
            role="task construction/evaluation source",
            expected_sha256=row["sha256"], expected_blob=row.get("git_blob_sha"),
        ))
    extra_code = [
        ("libero", "libero/libero/benchmark/libero_suite_task_map.py", "task UID and original robot selection", ["libero-readback"]),
        ("libero", "libero/libero/benchmark/mu_creation.py", "task-to-problem scene construction", ["libero-readback"]),
        ("libero", "libero/libero/envs/textures.py", "asset texture source mapping", ["libero-readback"]),
        ("libero", "libero/libero/envs/arenas/table_arena.py", "active scene XML path and style transformation", ["libero-readback"]),
        ("libero", "libero/libero/envs/arenas/style.py", "active scene style filename mapping", ["libero-readback"]),
        ("robosuite", "robosuite/models/robots/manipulators/panda_robot.py", "Panda robot owner", ["robosuite-tree", "robosuite-audit"]),
        ("robosuite", "robosuite/models/grippers/panda_gripper.py", "Panda gripper owner", ["robosuite-tree", "robosuite-audit"]),
        ("robosuite", "robosuite/models/mounts/rethink_mount.py", "Rethink mount owner", ["robosuite-tree", "robosuite-audit"]),
    ]
    seen_code = {(row["repository"], row["path"]) for row in code_refs}
    for repo, path, role, preferred in extra_code:
        if (repo, path) in seen_code:
            continue
        code_refs.append(_code_reference(
            repo=repo, revision=FIXED_REVISIONS[repo], source_path=path,
            root_map=root_map, tree_index=tree_indexes[repo], preferred_roots=preferred, role=role,
        ))
        seen_code.add((repo, path))
    code_refs.sort(key=lambda row: (row["repository"], row["path"]))

    code_ref_by_path = {row["path"]: row for row in code_refs if row["repository"] == "libero"}
    table_owner = code_ref_by_path.get("libero/libero/envs/arenas/table_arena.py")
    style_owner = code_ref_by_path.get("libero/libero/envs/arenas/style.py")
    if table_owner is None or style_owner is None:
        raise BundleError("pinned LIBERO scene-style owner sources are incomplete")
    rewrite_rule = _scene_rewrite_rule({
        "path": "libero/libero/assets/scenes/libero_tabletop_base_style.xml",
        "sha256": dynamic["sha256"],
        "style_properties": {"floor_style": "light-gray", "wall_style": "light-gray-plaster"},
    }, style_owner, table_owner)

    bddl_goal = task["bddl"]["goal"]
    if bddl_goal != [["And", ["On", "akita_black_bowl_1", "plate_1"]]]:
        raise BundleError("pilot original goal expression differs from the approved source inventory")
    if len(asset_refs) != 89:
        raise BundleError("active source XML closure did not resolve to the measured pilot asset set")
    active = sorted(
        (entry["repository"], entry["source_path"], entry["sha256"], entry["size_bytes"])
        for entry in files if entry["role"] == "asset_dependency"
    )
    closure_payload = [{"repository": repo, "path": path, "size_bytes": size, "sha256": sha}
                       for repo, path, sha, size in active]
    closure_sha = sha256_bytes(canonical_json({"schema_version": "libero-pilot-asset-closure-v1", "files": closure_payload}))
    selected_xml = [{
        "repository": src["repo"], "path": src["path"], "sha256": src["sha256"],
        "git_blob_sha1": src["git_blob_sha"], "selected_by": "LIBERO tabletop task source",
    } for src in active_xml_specs]
    excluded_xml = [{
        "repository": src["repo"], "path": src["path"], "sha256": src["sha256"],
        "git_blob_sha1": src["git_blob_sha"],
        "reason": "BDDLBaseDomain receives the LIBERO scene_xml selected by Libero_Tabletop_Manipulation; this robosuite default table arena XML is not selected.",
    } for src in excluded_xml_specs]
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "manifest_id": "libero-spatial-bowl-to-plate-r07b-pilot-v1",
        "manifest_status": "PILOT_LOCAL_SOURCE_INSTALL_CANDIDATE",
        "source_revisions": {"libero": LIBERO_REV, "robosuite": ROBOSUITE_REV},
        "task": {
            "task_uid": TASK_UID,
            "suite": task["suite"],
            "native_filename": task["native_filename"],
            "language": task["language"],
            "bddl": {"path": bddl["path"], "sha256": bddl["sha256"], "goal_expression": bddl_goal, "init_predicates": bddl["init"]},
            "selected_pruned_init": {
                "path": init["path"], "sha256": init["sha256"], "size_bytes": init["bytes"],
                "format": init["format"], "shape_from_prior_safe_opcode_audit": init["shape_from_prior_opcode_audit"],
                "deserialized_by_this_package": False, "reset_realization": "NOT_RUN",
            },
            "objects_instance_to_type": task["objects_instance_to_type"],
            "fixtures_instance_to_type": task["fixtures_instance_to_type"],
            "type_to_source_and_xml": task["type_to_source_and_xml"],
        },
        "source_review": {
            "scope": "R07a004 allowed local source-level progress for the first pilot",
            "sol_review_sha256": sha256_bytes(review_bytes),
            "sol_review_path": "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07a_004/sol_review.md",
            "permission_boundary": "local source install/verify and recipe only; no general license approval, runtime qualification, or redistribution",
        },
        "source_inputs": {
            "pilot_asset_inputs_file_sha256": sha256_bytes(Path(args.asset_input).read_bytes()),
            "asset_path_reference_sha256": asset_input["source_index_sha256"],
            "source_inventory_sha256": sha256_bytes(Path(args.task_inventory).read_bytes()),
            "dynamic_scene_closure_sha256": sha256_bytes(Path(args.scene_closure).read_bytes()),
            "license_scope_receipt_sha256": sha256_bytes(Path(args.license_scope).read_bytes()),
            "excluded_input_asset_rows": len(excluded_files),
            "excluded_asset_paths": sorted(row["repository"] + ":" + row["path"] for row in excluded_files),
            "input_rows": len(input_asset_map),
        },
        "source_resolution": {
            "xml_parent_relative_paths": True,
            "compiler_meshdir_and_texturedir_applied": True,
            "include_recursion": "unsupported references are rejected unless pinned and declared; current active source XML closure has no include edge",
            "active_scene_xml": selected_xml[-1],
            "scene_style_properties": {"floor_style": "light-gray", "wall_style": "light-gray-plaster"},
            "scene_style_rewrite_rules": rewrite_rule["rules"],
            "scene_style_owner_code": rewrite_rule["owner_code"],
            "libero_table_arena_path_owner": "libero/libero/envs/bddl_base_domain.py::_load_model and libero/libero/envs/problems/libero_tabletop_manipulation.py",
            "style_path_owner": "libero/libero/envs/arenas/table_arena.py plus libero/libero/envs/arenas/style.py",
        },
        "selected_xml_sources": selected_xml,
        "excluded_xml_sources": excluded_xml,
        "files": sorted(files, key=lambda row: row["install_path"]),
        "excluded_asset_candidates": sorted(excluded_files, key=lambda row: row["repository"] + ":" + row["path"]),
        "source_code_references": code_refs,
        "notices": notices,
        "asset_closure": {
            "schema_version": "libero-pilot-asset-closure-v1",
            "file_count": len(closure_payload),
            "total_bytes": sum(row["size_bytes"] for row in closure_payload),
            "sha256": closure_sha,
            "files": closure_payload,
        },
        "xml_dependency_map": {},
        "scope_limits": {
            "source_install_ready_means": "Manifest-declared bytes can be installed locally and independently verified.",
            "does_not_mean": [
                "LIBERO/robosuite dependency compatibility",
                "safe .pruned_init decoding or reset realization",
                "Core TaskArtifact registration or native admission",
                "license/attribution clearance for redistribution",
                "task success, P99, or qualification",
            ],
            "network_downloaded_assets": 0,
            "binary_or_model_distribution_in_git": False,
        },
    }
    # Validate the active source bytes against the same manifest path resolution before return.
    source_payloads = {row["install_path"]: source_contents[row["entry_id"]] for row in files}
    manifest["xml_dependency_map"] = resolve_xml_dependencies(manifest, source_payloads)
    validate_manifest(manifest, source_payloads=source_payloads)
    return manifest


def validate_manifest(manifest: dict, *, source_payloads: dict[str, bytes] | None = None) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise BundleError("unsupported source manifest schema")
    if manifest.get("manifest_status") != "PILOT_LOCAL_SOURCE_INSTALL_CANDIDATE":
        raise BundleError("manifest status is not a local pilot source candidate")
    if manifest.get("source_revisions") != FIXED_REVISIONS:
        raise BundleError("source repository revisions do not match the fixed pilot pins")
    task = manifest.get("task")
    if not isinstance(task, dict) or task.get("task_uid") != TASK_UID:
        raise BundleError("manifest task UID is not the fixed LIBERO spatial pilot")
    bddl = task.get("bddl", {})
    init = task.get("selected_pruned_init", {})
    if bddl.get("path") is None or init.get("path") is None:
        raise BundleError("manifest is missing exact BDDL or selected init identity")
    ids = set()
    paths = set()
    path_to_entry = {}
    repo_source_to_entry = {}
    for row in manifest.get("files", []):
        if not isinstance(row, dict):
            raise BundleError("manifest file row must be an object")
        for field in ("entry_id", "repository", "revision", "source_root_id", "source_path", "install_path", "role", "sha256", "git_blob_sha1"):
            if field not in row:
                raise BundleError("manifest file row is missing " + field)
        repo = row["repository"]
        if repo not in FIXED_REVISIONS or row["revision"] != FIXED_REVISIONS[repo]:
            raise BundleError("manifest file has an unexpected repository or revision")
        validate_relpath(row["source_path"], "source_path")
        install_path = validate_relpath(row["install_path"], "install_path")
        if install_path in paths:
            raise BundleError("duplicate manifest install path: " + install_path)
        if row["entry_id"] in ids:
            raise BundleError("duplicate manifest entry id")
        ids.add(row["entry_id"])
        paths.add(install_path)
        path_to_entry[install_path] = row
        repo_source_to_entry[(repo, row["source_path"])] = row
        if type(row.get("size_bytes")) is not int or row["size_bytes"] < 0:
            raise BundleError("manifest size_bytes must be a nonnegative integer")
        if type(row["sha256"]) is not str or len(row["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in row["sha256"]):
            raise BundleError("manifest SHA-256 is malformed")
        if type(row["git_blob_sha1"]) is not str or len(row["git_blob_sha1"]) != 40 or any(c not in "0123456789abcdef" for c in row["git_blob_sha1"]):
            raise BundleError("manifest Git blob SHA-1 is malformed")
        license_info = row.get("license")
        if not isinstance(license_info, dict) or not all(type(license_info.get(key)) is str and license_info[key] for key in ("notice_id", "license_status", "attribution", "local_install_disposition")):
            raise BundleError("manifest file is missing license/notice disposition")
        notice_ids = {notice.get("notice_id") for notice in manifest.get("notices", []) if isinstance(notice, dict)}
        if license_info["notice_id"] not in notice_ids:
            raise BundleError("manifest file references an undeclared notice: " + license_info["notice_id"])
        if type(license_info.get("redistribution_approved")) is not bool:
            raise BundleError("redistribution_approved must be a boolean")
        if row["role"] == "asset_dependency":
            if license_info.get("pilot_source_family") not in ALLOWED_PILOT_FAMILIES:
                raise BundleError("asset belongs to a source family outside the pilot allowlist")
            family_id = license_info.get("pilot_family_id")
            disposition = license_info.get("first_use_disposition")
            if type(family_id) is not str or not family_id or type(disposition) is not str or not disposition or "BLOCKED" in disposition:
                raise BundleError("asset is missing an eligible exact first-use family disposition")
            notice = next((item for item in manifest.get("notices", [])
                           if isinstance(item, dict) and item.get("notice_id") == license_info["notice_id"]), None)
            if (notice is None or notice.get("source_family_id") != family_id
                    or notice.get("first_use_disposition") != disposition):
                raise BundleError("asset family notice does not bind the exact first-use disposition")
            if license_info["redistribution_approved"] is not False:
                raise BundleError("pilot local source manifest must not claim redistribution approval")
    if not isinstance(manifest.get("notices"), list) or not manifest["notices"]:
        raise BundleError("source manifest requires declared source notices")
    if not any(row.get("role") == "task_bddl" and row["source_path"] == bddl["path"] and row["sha256"] == bddl.get("sha256") for row in manifest["files"]):
        raise BundleError("exact BDDL identity is missing from installed file list")
    if not any(row.get("role") == "native_pruned_init_bytes" and row["source_path"] == init["path"] and row["sha256"] == init.get("sha256") for row in manifest["files"]):
        raise BundleError("exact selected .pruned_init identity is missing from installed file list")
    asset_rows = [row for row in manifest["files"] if row["role"] == "asset_dependency"]
    if not asset_rows:
        raise BundleError("active source asset closure is empty")
    closure = manifest.get("asset_closure")
    if not isinstance(closure, dict) or closure.get("schema_version") != "libero-pilot-asset-closure-v1":
        raise BundleError("active asset closure schema is missing or unsupported")
    expected_closure_files = [
        {"repository": row["repository"], "path": row["source_path"],
         "size_bytes": row["size_bytes"], "sha256": row["sha256"]}
        for row in sorted(asset_rows, key=lambda item: (item["repository"], item["source_path"]))
    ]
    expected_closure_sha = sha256_bytes(canonical_json({
        "schema_version": "libero-pilot-asset-closure-v1", "files": expected_closure_files,
    }))
    if (closure.get("files") != expected_closure_files
            or closure.get("file_count") != len(expected_closure_files)
            or closure.get("total_bytes") != sum(row["size_bytes"] for row in expected_closure_files)
            or closure.get("sha256") != expected_closure_sha):
        raise BundleError("asset closure listing, count, bytes, or digest differs from manifest file rows")
    excluded = manifest.get("excluded_asset_candidates")
    if not isinstance(excluded, list):
        raise BundleError("excluded asset candidates must be explicit")
    excluded_keys = set()
    for row in excluded:
        if not isinstance(row, dict):
            raise BundleError("excluded asset candidate must be an object")
        repo = row.get("repository")
        if repo not in FIXED_REVISIONS or row.get("revision") != FIXED_REVISIONS[repo]:
            raise BundleError("excluded asset candidate has wrong revision")
        validate_relpath(row.get("path"), "excluded asset path")
        if type(row.get("reason")) is not str or not row["reason"]:
            raise BundleError("excluded asset candidate requires an exact exclusion reason")
        key = (repo, row["path"])
        if key in excluded_keys or key in repo_source_to_entry:
            raise BundleError("excluded candidate duplicates another source path")
        excluded_keys.add(key)
        if type(row.get("redistribution_approved")) is not bool:
            raise BundleError("excluded candidate requires explicit redistribution disposition")
        if len(row.get("sha256", "")) != 64 or len(row.get("git_blob_sha1", "")) != 40:
            raise BundleError("excluded candidate identity is malformed")
    if source_payloads is not None:
        for row in manifest["files"]:
            payload = source_payloads.get(row["install_path"])
            if payload is None:
                raise BundleError("source payload missing: " + row["install_path"])
            if len(payload) != row["size_bytes"] or sha256_bytes(payload) != row["sha256"] or git_blob_sha1(payload) != row["git_blob_sha1"]:
                raise BundleError("source payload identity mismatch: " + row["install_path"])
        computed = resolve_xml_dependencies(manifest, source_payloads)
        if computed != manifest.get("xml_dependency_map"):
            raise BundleError("manifest XML dependency map differs from parsed source bytes")
        expected_asset_edges = {
            (row["repository"], row["source_path"]) for row in asset_rows
        }
        actual_asset_edges = {
            (edge["repository"], edge["path"])
            for rows in computed.values() for edge in rows if edge["edge_type"] == "file"
        }
        if expected_asset_edges != actual_asset_edges:
            missing = sorted(expected_asset_edges - actual_asset_edges)
            undeclared = sorted(actual_asset_edges - expected_asset_edges)
            raise BundleError("asset closure edge mismatch: missing=" + repr(missing[:5]) + " undeclared=" + repr(undeclared[:5]))


def resolve_xml_dependencies(manifest: dict, payloads: dict[str, bytes]) -> dict[str, list[dict]]:
    rows = manifest.get("files", [])
    xml_rows = [row for row in rows if row.get("xml_source") is True]
    by_repo_source = {(row["repository"], row["source_path"]): row for row in rows}
    by_install = {row["install_path"]: row for row in rows}
    if not xml_rows:
        raise BundleError("manifest declares no XML source inputs")
    rules = manifest.get("source_resolution", {}).get("scene_style_rewrite_rules", [])
    active_scene_path = manifest.get("source_resolution", {}).get("active_scene_xml", {}).get("path")
    rule_map = {(active_scene_path, rule.get("name"), rule.get("declared_ref")): rule.get("effective_ref") for rule in rules}
    dependencies: dict[str, list[dict]] = {}
    xml_queue = list(xml_rows)
    visited = set()
    while xml_queue:
        row = xml_queue.pop(0)
        source_key = (row["repository"], row["source_path"])
        if source_key in visited:
            continue
        visited.add(source_key)
        content = payloads.get(row["install_path"])
        if content is None:
            raise BundleError("XML source payload is missing: " + row["install_path"])
        try:
            document = ET.fromstring(content)
        except ET.ParseError as exc:
            raise BundleError("malformed pinned XML " + row["source_path"] + ": " + str(exc)) from exc
        repo = row["repository"]
        parent = posixpath.dirname(row["source_path"])
        compiler = document.find("compiler")
        meshdir = "" if compiler is None else compiler.get("meshdir", "")
        texturedir = "" if compiler is None else compiler.get("texturedir", "")
        edges = []
        for node in document.iter():
            raw = node.get("file")
            if raw is None:
                continue
            name = node.get("name")
            effective = rule_map.get((row["source_path"], name, raw), raw)
            if effective != raw and row["repository"] + ":" + row["source_path"] != REWRITE_SCENE:
                raise BundleError("style rewrite rule applied to the wrong XML source")
            if raw != effective and (node.tag != "texture" or not name):
                raise BundleError("scene style path rewrite does not match an exact texture element")
            directory = meshdir if node.tag in {"mesh", "skin"} else texturedir if node.tag == "texture" else ""
            resolved = posixpath.normpath(posixpath.join(parent, directory, effective.replace("\\", "/")))
            if resolved.startswith("/") or resolved == ".." or resolved.startswith("../") or (len(resolved) > 1 and resolved[1] == ":"):
                raise BundleError("XML file reference escapes its pinned repository: " + repr(effective))
            target_key = (repo, resolved)
            target = by_repo_source.get(target_key)
            if node.tag == "include":
                if target is None or target.get("xml_source") is not True:
                    raise BundleError("XML include is not declared as a pinned XML source: " + resolved)
                xml_queue.append(target)
                edge_type = "include"
            else:
                if target is None or target.get("role") != "asset_dependency":
                    raise BundleError("XML file reference is not in the declared active asset closure: " + repo + ":" + resolved)
                edge_type = "file"
            edges.append({
                "edge_type": edge_type,
                "element": node.tag,
                "name": name,
                "declared_ref": raw,
                "effective_ref": effective,
                "repository": repo,
                "path": resolved,
                "install_path": target["install_path"],
                "sha256": target["sha256"],
            })
        dependencies[row["entry_id"]] = sorted(edges, key=lambda edge: (edge["edge_type"], edge["path"], edge["element"], str(edge["name"])))
    return {key: dependencies[key] for key in sorted(dependencies)}


def _read_install_payload(manifest: dict, target: Path) -> dict[str, bytes]:
    payloads = {}
    for row in manifest["files"]:
        path = path_no_symlink(target, row["install_path"])
        if not path.is_file():
            raise BundleError("installed file is missing: " + row["install_path"])
        data = path.read_bytes()
        if len(data) != row["size_bytes"]:
            raise BundleError("installed file size mismatch: " + row["install_path"])
        if sha256_bytes(data) != row["sha256"]:
            raise BundleError("installed file SHA-256 mismatch: " + row["install_path"])
        if git_blob_sha1(data) != row["git_blob_sha1"]:
            raise BundleError("installed file Git blob SHA-1 mismatch: " + row["install_path"])
        payloads[row["install_path"]] = data
    return payloads


def _check_target_tree(target: Path, manifest: dict) -> None:
    if target.is_symlink() or not target.is_dir():
        raise BundleError("installation target must be an existing non-symlink directory")
    expected = {row["install_path"] for row in manifest["files"]} | {"install_receipt.json"}
    actual = set()
    for path in target.rglob("*"):
        if path.is_symlink():
            raise BundleError("installed tree contains a symlink: " + str(path))
        if path.is_file():
            actual.add(path.relative_to(target).as_posix())
    if actual != expected:
        raise BundleError("installed file set differs from manifest: missing=" + repr(sorted(expected - actual)[:10]) +
                          " extra=" + repr(sorted(actual - expected)[:10]))
    # Empty unlisted directories are also rejected, so verification cannot hide extra content in nested namespaces.
    expected_dirs = set()
    for value in expected:
        parent = PurePosixPath(value).parent
        while parent.as_posix() != ".":
            expected_dirs.add(parent.as_posix())
            parent = parent.parent
    actual_dirs = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_dir()}
    if actual_dirs != expected_dirs:
        raise BundleError("installed directory set differs from the manifest")


def _safe_target_path(raw_target: Path) -> Path:
    target = raw_target.absolute()
    current = Path(target.anchor)
    for part in target.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise BundleError("installation target path contains a symlink: " + str(current))
    return target


def _checked_receipt(target: Path, manifest_sha: str) -> dict:
    receipt_path = target / "install_receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise BundleError("matching producer install receipt is missing")
    receipt = read_json(receipt_path)
    if receipt.get("schema_version") != INSTALL_SCHEMA:
        raise BundleError("producer install receipt schema mismatch")
    claimed = receipt.get("receipt_sha256")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    if claimed != sha256_bytes(canonical_json(unsigned)):
        raise BundleError("producer receipt self-hash mismatch")
    if receipt.get("manifest_sha256") != manifest_sha:
        raise BundleError("producer receipt does not bind this manifest")
    if receipt.get("status") != "INSTALLED":
        raise BundleError("producer receipt is not an install success record")
    if receipt.get("target") != str(target):
        raise BundleError("producer receipt belongs to a different installation target")
    expected_id = sha256_bytes((manifest_sha + "\0" + str(target)).encode("utf-8"))[:24]
    if receipt.get("installation_id") != expected_id:
        raise BundleError("producer receipt installation identity does not match this target")
    return receipt


def _manifest_and_bytes(manifest_path: Path, source_roots: dict[str, Path] | None = None) -> tuple[dict, str, dict[str, bytes]]:
    raw = manifest_path.read_bytes()
    manifest_sha = sha256_bytes(raw)
    manifest = read_json(manifest_path)
    validate_manifest(manifest)
    payloads = {}
    if source_roots is not None:
        for row in manifest["files"]:
            root_id = row["source_root_id"]
            if root_id not in source_roots:
                raise BundleError("manifest source root was not supplied: " + root_id)
            payloads[row["install_path"]] = read_checked(
                source_roots[root_id], row["source_path"], expected_size=row["size_bytes"],
                expected_sha256=row["sha256"], expected_git_blob_sha1=row["git_blob_sha1"],
            )
        validate_manifest(manifest, source_payloads=payloads)
    return manifest, manifest_sha, payloads


def install(manifest_path: Path, target_raw: Path, source_roots: dict[str, Path]) -> dict:
    manifest, manifest_sha, payloads = _manifest_and_bytes(manifest_path, source_roots)
    target = _safe_target_path(target_raw)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_dir() or target.is_symlink():
            raise BundleError("existing target is not a safe directory")
        receipt = _checked_receipt(target, manifest_sha)
        _check_target_tree(target, manifest)
        installed = _read_install_payload(manifest, target)
        validate_manifest(manifest, source_payloads=installed)
        return {
            "schema_version": INSTALL_SCHEMA, "status": "ALREADY_PRESENT_VERIFIED",
            "manifest_sha256": manifest_sha, "installation_id": receipt["installation_id"],
            "target": str(target.resolve()), "file_count": len(manifest["files"]),
            "total_bytes": sum(row["size_bytes"] for row in manifest["files"]),
            "idempotent": True, "created_at_utc": receipt["created_at_utc"],
        }
    stage = Path(tempfile.mkdtemp(prefix=".libero-install-", dir=str(target.parent)))
    try:
        for row in manifest["files"]:
            out = path_no_symlink(stage, row["install_path"])
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists():
                raise BundleError("duplicate staged file path")
            out.write_bytes(payloads[row["install_path"]])
        payload_summary = {
            "file_count": len(manifest["files"]),
            "total_bytes": sum(row["size_bytes"] for row in manifest["files"]),
            "asset_file_count": sum(row["role"] == "asset_dependency" for row in manifest["files"]),
            "asset_bytes": sum(row["size_bytes"] for row in manifest["files"] if row["role"] == "asset_dependency"),
            "asset_closure_sha256": manifest["asset_closure"]["sha256"],
        }
        receipt = {
            "schema_version": INSTALL_SCHEMA, "tool_version": TOOL_VERSION,
            "status": "INSTALLED", "manifest_id": manifest["manifest_id"],
            "manifest_sha256": manifest_sha,
            "task_uid": manifest["task"]["task_uid"],
            "source_revisions": manifest["source_revisions"],
            "target": str(target),
            "installation_id": sha256_bytes((manifest_sha + "\0" + str(target)).encode("utf-8"))[:24],
            "payload": payload_summary,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "producer_verification": "INSTALL_BYTES_COPIED_AND_HASHED; independent verify command remains required",
        }
        receipt["receipt_sha256"] = sha256_bytes(canonical_json(receipt))
        (stage / "install_receipt.json").write_bytes(json.dumps(receipt, sort_keys=True, indent=2).encode("utf-8") + b"\n")
        _check_target_tree(stage, manifest)
        installed = _read_install_payload(manifest, stage)
        validate_manifest(manifest, source_payloads=installed)
        os.rename(stage, target)
        return receipt
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def verify(manifest_path: Path, target_raw: Path) -> dict:
    manifest, manifest_sha, _ = _manifest_and_bytes(manifest_path)
    target = _safe_target_path(target_raw)
    _check_target_tree(target, manifest)
    producer_receipt = _checked_receipt(target, manifest_sha)
    installed = _read_install_payload(manifest, target)
    validate_manifest(manifest, source_payloads=installed)
    payload_rows = [
        {"install_path": row["install_path"], "size_bytes": row["size_bytes"], "sha256": row["sha256"], "git_blob_sha1": row["git_blob_sha1"]}
        for row in manifest["files"]
    ]
    result = {
        "schema_version": VERIFY_SCHEMA, "tool_version": TOOL_VERSION,
        "status": "VERIFIED_INDEPENDENT_REREAD",
        "manifest_sha256": manifest_sha,
        "manifest_id": manifest["manifest_id"],
        "task_uid": manifest["task"]["task_uid"],
        "installation_id": producer_receipt["installation_id"],
        "target": str(target.resolve()),
        "file_count": len(payload_rows),
        "total_bytes": sum(row["size_bytes"] for row in payload_rows),
        "asset_file_count": sum(row["role"] == "asset_dependency" for row in manifest["files"]),
        "asset_bytes": sum(row["size_bytes"] for row in manifest["files"] if row["role"] == "asset_dependency"),
        "asset_closure_sha256": manifest["asset_closure"]["sha256"],
        "xml_file_edges": sum(len(edges) for edges in manifest["xml_dependency_map"].values()),
        "xml_sources_checked": len(manifest["xml_dependency_map"]),
        "payload_files": payload_rows,
        "producer_receipt_sha256": producer_receipt["receipt_sha256"],
        "independent_reader": "source_bundle.py verify; reopened each installed file, exact tree and symlink checks, recomputed XML closure",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    result["result_sha256"] = sha256_bytes(canonical_json(result))
    return result


def validate_task_input(task_input: dict, manifest: dict, install_receipt: dict) -> None:
    if not isinstance(task_input, dict) or task_input.get("schema_version") != "libero-pilot-deployment-input-v1":
        raise BundleError("unsupported deployment task input schema")
    if task_input.get("task_uid") != TASK_UID:
        raise BundleError("deployment input has a different task UID")
    if task_input.get("source_manifest_sha256") != install_receipt.get("manifest_sha256"):
        raise BundleError("deployment input source manifest hash differs from install receipt")
    if task_input.get("bddl") != manifest["task"]["bddl"]:
        raise BundleError("deployment BDDL identity/goal differs from pinned task manifest")
    if task_input.get("selected_pruned_init") != manifest["task"]["selected_pruned_init"]:
        raise BundleError("deployment init identity differs from pinned task manifest")
    if task_input.get("source_revisions") != FIXED_REVISIONS:
        raise BundleError("deployment task input revisions differ from fixed source pins")
    native = task_input.get("native_reference", {})
    robot = native.get("robot", {})
    if robot.get("robot_name") != "MountedPanda" or robot.get("base_robot_name") != "Panda":
        raise BundleError("deployment input changes the pinned MountedPanda robot identity")
    if robot.get("mount_name") != "RethinkMount" or robot.get("gripper_name") != "PandaGripper":
        raise BundleError("deployment input changes the pinned mount or gripper")
    if robot.get("arm_joint_names") != [f"joint{i}" for i in range(1, 8)]:
        raise BundleError("deployment input arm slot order differs from the selected Panda joints")
    if robot.get("arm_actuator_types") != ["motor"] * 7 or robot.get("finger_actuator_types") != ["position"] * 2:
        raise BundleError("deployment input changes the authentic MountedPanda actuator types")
    expected_arm = [
        {"name": f"torq_j{i}", "type": "motor", "joint": f"joint{i}",
         "control_range": [-80.0, 80.0] if i <= 5 else [-12.0, 12.0], "unit": "N*m", "role": "arm"}
        for i in range(1, 8)
    ]
    expected_fingers = [
        {"name": "gripper_finger_joint1", "type": "position", "joint": "finger_joint1",
         "control_range_m": [0.0, 0.04], "force_range_N": [-20.0, 20.0], "unit": "m", "role": "finger"},
        {"name": "gripper_finger_joint2", "type": "position", "joint": "finger_joint2",
         "control_range_m": [-0.04, 0.0], "force_range_N": [-20.0, 20.0], "unit": "m", "role": "finger"},
    ]
    if robot.get("actuators") != expected_arm + expected_fingers:
        raise BundleError("deployment input changes the ordered actuator slot/type/range mapping")
    if robot.get("native_end_effector_body") != "eef" or robot.get("frames") != {
        "source_frame_name": "eef", "core_frame_reference_status": "UNRESOLVED_CORE_MAPPING"
    }:
        raise BundleError("deployment input invents or changes a Core robot frame mapping")
    if robot.get("units") != {"joint_position": "rad", "arm_effort": "N*m", "finger_position": "m", "translation": "m", "rotation": "rad"}:
        raise BundleError("deployment input changes the pinned robot units")
    controller = native.get("controller", {})
    if controller.get("name") != "OSC_POSE" or controller.get("control_frequency_hz") != 20 or controller.get("control_timestep_seconds") != 0.05:
        raise BundleError("deployment input changes the pinned native reference frequency")
    if controller.get("physics_timestep_seconds") is not None or controller.get("physics_timestep_status") != "UNRESOLVED_SOURCE_CONSTANT; Robosuite BaseEnv reads macros.SIMULATION_TIMESTEP, not compiled here":
        raise BundleError("deployment input asserts an uncompiled native physics clock")
    if controller.get("core_equivalence") != "NOT_ESTABLISHED" or not controller.get("hold_policy"):
        raise BundleError("deployment input invents native controller equivalence or omits hold semantics")
    candidate = task_input.get("requested_core_candidate", {})
    if candidate.get("control_frequency_hz") != 100 or candidate.get("control_period_seconds") != 0.01:
        raise BundleError("deployment input changes the declared Core candidate clock")
    if candidate.get("frame_mapping_status") != "UNRESOLVED" or "Not mapped" not in candidate.get("drive_or_hold_semantics", ""):
        raise BundleError("deployment input falsely supplies a drive or frame mapping")
    if native.get("active_scene_xml") != manifest["source_resolution"]["active_scene_xml"]:
        raise BundleError("deployment input changes the selected LIBERO scene and style")
    if native.get("problem_class") != "Libero_Tabletop_Manipulation":
        raise BundleError("deployment input changes the selected tabletop problem class")
    if task_input.get("requested_core_candidate", {}).get("observation_profile") != "state-only":
        raise BundleError("pilot candidate must remain state-only")
    if task_input.get("requested_core_candidate", {}).get("core_native_admission_ready") is not False:
        raise BundleError("pilot recipe cannot claim Core native admission")
    semantics = task_input.get("semantics", {})
    if semantics.get("contact_evidence") != "UNAVAILABLE_UNTIL_PUBLIC_PROVIDER_STATE_EXISTS" or semantics.get("unavailable_is_not_false") is not True:
        raise BundleError("contact semantics cannot be defaulted to true or false")
    if semantics.get("goal_predicate") != "On(akita_black_bowl_1, plate_1)" or semantics.get("goal_threshold_m") != 0.03:
        raise BundleError("deployment input changes the pinned bowl-on-plate goal predicate")
    required_evidence = {"object-object geom-group contact", "vertical ordering", "strict XY body-centre distance < 0.03 m"}
    if set(semantics.get("required_evidence", [])) != required_evidence:
        raise BundleError("deployment input omits or changes a required On predicate evidence component")
    cost = task_input.get("cost_protocol_binding", {})
    if cost.get("protocol_sha256") != "a6f5836b65498d23e0dfb53568bdd8dee69f60f020c579957990b6a6bc59987e" or cost.get("measurement_baseline_commit") != "0309d73bb5b60f9989907c3eede8c0cd2893f29f":
        raise BundleError("deployment input cost protocol binding differs from the frozen R07a003 v2.1 record")


def compile_recipe(manifest_path: Path, target: Path, task_input_path: Path) -> dict:
    independent = verify(manifest_path, target)
    manifest = read_json(manifest_path)
    install_receipt = read_json(target / "install_receipt.json")
    task_input = read_json(task_input_path)
    validate_task_input(task_input, manifest, install_receipt)
    code_refs = {(row["repository"], row["path"]) for row in manifest["source_code_references"]}
    required_code = {
        ("libero", "libero/libero/envs/env_wrapper.py"),
        ("libero", "libero/libero/envs/bddl_base_domain.py"),
        ("libero", "libero/libero/envs/problems/libero_tabletop_manipulation.py"),
        ("libero", "libero/libero/envs/arenas/table_arena.py"),
        ("libero", "libero/libero/envs/arenas/style.py"),
        ("libero", "libero/libero/envs/robots/mounted_panda.py"),
    }
    if not required_code.issubset(code_refs):
        raise BundleError("deployment recipe lacks source references for real LIBERO task/robot owners")
    repository_root = Path(__file__).resolve().parents[4]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from bench_deploy.libero.artifacts.recipe import compose_recipe
    binding = {
        "source_manifest_id": manifest["manifest_id"],
        "source_manifest_sha256": independent["manifest_sha256"],
        "asset_closure_sha256": independent["asset_closure_sha256"],
        "install_receipt_sha256": install_receipt["receipt_sha256"],
        "independent_verify_sha256": independent["result_sha256"],
        "task_uid": TASK_UID,
        "source_revisions": FIXED_REVISIONS,
    }
    return compose_recipe(manifest, task_input, binding)

def _manifest_command(args) -> int:
    manifest = build_manifest(args)
    write_json(Path(args.output), manifest)
    print(json.dumps({
        "status": "BUILT_AND_SOURCE_HASH_VERIFIED",
        "manifest_path": str(Path(args.output)),
        "manifest_sha256": sha256_bytes(Path(args.output).read_bytes()),
        "file_count": len(manifest["files"]),
        "asset_file_count": manifest["asset_closure"]["file_count"],
        "asset_bytes": manifest["asset_closure"]["total_bytes"],
        "asset_closure_sha256": manifest["asset_closure"]["sha256"],
        "excluded_input_rows": len(manifest["excluded_asset_candidates"]),
        "xml_sources": len(manifest["selected_xml_sources"]),
        "xml_file_edges": sum(len(rows) for rows in manifest["xml_dependency_map"].values()),
    }, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-manifest", help="build and source-hash a versioned pilot manifest")
    for name in ("asset-input", "task-inventory", "scene-closure", "license-scope", "sol-review", "pilot-decision", "libero-tree-index", "robosuite-tree-index", "output"):
        build.add_argument("--" + name, required=True)
    build.add_argument("--source-root", action="append", default=[], metavar="ID=PATH")
    install_parser = sub.add_parser("install", help="install checked bytes into a fresh local target")
    install_parser.add_argument("--manifest", required=True)
    install_parser.add_argument("--target", required=True)
    install_parser.add_argument("--source-root", action="append", default=[], metavar="ID=PATH")
    verify_parser = sub.add_parser("verify", help="independently reread and verify a local installation")
    verify_parser.add_argument("--manifest", required=True)
    verify_parser.add_argument("--target", required=True)
    verify_parser.add_argument("--receipt-out", required=True)
    verify_parser.add_argument("--source-roots-file", default=None, help=argparse.SUPPRESS)
    recipe_parser = sub.add_parser("recipe", help="compile the versioned pilot deployment recipe from a verified installation")
    recipe_parser.add_argument("--manifest", required=True)
    recipe_parser.add_argument("--target", required=True)
    recipe_parser.add_argument("--task-input", required=True)
    recipe_parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build-manifest":
            return _manifest_command(args)
        if args.command == "install":
            result = install(Path(args.manifest), Path(args.target), parse_source_roots(args.source_root))
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "verify":
            result = verify(Path(args.manifest), Path(args.target))
            write_json(Path(args.receipt_out), result)
            print(json.dumps({k: v for k, v in result.items() if k != "payload_files"}, sort_keys=True))
            return 0
        if args.command == "recipe":
            result = compile_recipe(Path(args.manifest), Path(args.target), Path(args.task_input))
            write_json(Path(args.output), result)
            print(json.dumps({
                "status": "RECIPE_COMPILED",
                "recipe_id": result["recipe_id"],
                "recipe_sha256": result["recipe_sha256"],
                "task_uid": result["task"]["uid"],
                "accepted_scope_status": result["accepted_scope"]["status"],
                "qualification": result["accepted_scope"]["qualification"],
                "output": str(Path(args.output)),
            }, sort_keys=True))
            return 0
    except (BundleError, OSError, KeyError, TypeError, ValueError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
