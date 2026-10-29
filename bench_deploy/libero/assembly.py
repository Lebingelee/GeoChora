"""Pinned source binding and source-to-Core assembly owners.

The R07c helper below verifies a deterministic composition declaration against
an already independently verified local source installation. It deliberately
does not claim to emit the native MJCF: LIBERO builds arena, robot, fixture,
object, site and placement pieces through upstream Python model owners.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


_COMPOSITION_SCHEMA = "libero-source-composition-declaration-v1"
_MAX_SOURCE_BYTES = 128 * 1024 * 1024


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_install(manifest: dict, install_root: Path) -> tuple[dict[str, bytes], int]:
    root = Path(install_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("LIBERO composition requires an existing non-symlink verified install")
    root = root.resolve()
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("source manifest must contain the frozen install file list")
    expected: dict[str, bytes] = {}
    total = 0
    for row in files:
        if not isinstance(row, dict):
            raise ValueError("source manifest file rows must be objects")
        rel = row.get("install_path")
        if type(rel) is not str or not rel or "\\" in rel:
            raise ValueError("source install path must be canonical POSIX relative text")
        path = PurePosixPath(rel)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"unsafe install path in source manifest: {rel!r}")
        target = root.joinpath(*path.parts)
        current = root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"source install symlink is forbidden: {rel!r}")
        resolved = target.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"source install path escaped root: {rel!r}") from exc
        data = resolved.read_bytes()
        if len(data) != row.get("size_bytes") or _sha(data) != row.get("sha256"):
            raise ValueError(f"installed source bytes differ from manifest: {rel}")
        total += len(data)
        if total > _MAX_SOURCE_BYTES:
            raise ValueError("verified LIBERO install exceeds the composition read cap")
        if rel in expected:
            raise ValueError(f"duplicate installed path in source manifest: {rel}")
        expected[rel] = data

    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"source install contains an unexpected symlink: {path}")
        if path.is_file() and path.name != "install_receipt.json":
            actual.add(path.relative_to(root).as_posix())
    if actual != set(expected):
        raise ValueError(
            f"source install tree differs from manifest: missing={sorted(set(expected)-actual)}, "
            f"extra={sorted(actual-set(expected))}"
        )
    return expected, total


def _source_rows(
    manifest: dict,
    payloads: dict[str, bytes],
    *,
    source_text_root: Path | None,
    source_text_receipt: dict | None,
) -> list[dict[str, Any]]:
    rows_by_key = {
        (row.get("repository"), row.get("source_path", row.get("path"))): row
        for row in manifest.get("files", ())
        if isinstance(row, dict)
    }
    selected: list[dict[str, Any]] = []
    sources = list(manifest.get("selected_xml_sources", ()))
    for type_source in manifest.get("task", {}).get("type_to_source_and_xml", {}).values():
        if not isinstance(type_source, dict):
            continue
        # TableArena is constructed with the task's explicit LIBERO scene XML;
        # the robosuite table_arena.xml listed as an upstream default is not used.
        if type_source.get("class") is None and type_source.get("owner_source", "").endswith("table_arena.py"):
            continue
        source_path = type_source.get("asset_source", type_source.get("xml_source"))
        if not isinstance(source_path, str):
            continue
        repository = "robosuite" if source_path.startswith("robosuite/") else "libero"
        source_row = rows_by_key.get((repository, source_path))
        if source_row is None:
            raise ValueError(f"task object/arena source is not installed: {(repository, source_path)}")
        sources.append({
            "repository": repository,
            "path": source_path,
            "sha256": source_row.get("sha256"),
            "role": "task_type_xml_source",
        })
    sources.extend(manifest.get("source_code_references", ()))
    seen: set[tuple[str, str]] = set()
    for source in sources:
        key = (source.get("repository"), source.get("path"))
        if key in seen:
            continue
        seen.add(key)
        row = rows_by_key.get(key)
        if row is not None:
            data = payloads.get(row.get("install_path"))
            source_origin = "verified_install"
        else:
            if source_text_root is None or not isinstance(source_text_receipt, dict):
                raise ValueError(f"composition source is neither installed nor bound by the source-text receipt: {key}")
            receipt_index = {
                (item.get("repository"), item.get("source_path")): item
                for item in source_text_receipt.get("files", ())
                if isinstance(item, dict)
            }
            receipt_row = receipt_index.get(key)
            if receipt_row is None or receipt_row.get("sha256") != source.get("sha256"):
                raise ValueError(f"pinned source-code receipt does not bind bytes: {key}")
            root = Path(source_text_root).resolve(strict=True)
            source_file = Path(source_text_root) / str(key[0]) / str(key[1])
            current = source_file
            while current != Path(source_text_root).parent and current != root.parent:
                if current.is_symlink():
                    raise ValueError(f"pinned source-text path contains a symlink: {key}")
                if current == root:
                    break
                current = current.parent
            source_file = source_file.resolve(strict=True)
            try:
                source_file.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"pinned source-text path escaped its root: {key}") from exc
            data = source_file.read_bytes()
            source_origin = "pinned_source_text_receipt"
        if data is None:
            raise ValueError(f"composition source bytes are missing: {key}")
        if _sha(data) != source.get("sha256"):
            raise ValueError(f"composition source reference hash differs: {key}")
        selected.append({
            "repository": key[0],
            "path": key[1],
            "sha256": _sha(data),
            "origin": source_origin,
            "role": source.get("role", source.get("purpose", "pinned_source")),
        })
    return sorted(selected, key=lambda row: (row["repository"], row["path"]))


def _verify_source_text_tree(source_text_root: Path, receipt: dict) -> None:
    root_input = Path(source_text_root)
    if root_input.is_symlink() or not root_input.is_dir():
        raise ValueError("pinned source-text root must be an existing non-symlink directory")
    root = root_input.resolve(strict=True)
    rows = receipt.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("pinned source-text receipt must enumerate its text inputs")
    expected: set[str] = set()
    total_bytes = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("pinned source-text receipt rows must be objects")
        repository, source_path = row.get("repository"), row.get("source_path")
        if repository not in {"libero", "robosuite"} or type(source_path) is not str:
            raise ValueError("pinned source-text receipt has an invalid source identity")
        rel = PurePosixPath(source_path)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts or "\\" in source_path:
            raise ValueError("pinned source-text path is unsafe")
        key = f"{repository}/{rel.as_posix()}"
        if key in expected:
            raise ValueError("pinned source-text receipt contains duplicate files")
        expected.add(key)
        target = root / repository / Path(*rel.parts)
        current = target
        while current != root:
            if current.is_symlink():
                raise ValueError(f"pinned source-text tree contains a symlink: {key}")
            current = current.parent
        resolved = target.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"pinned source-text path escaped its root: {key}") from exc
        data = resolved.read_bytes()
        size_bytes = row.get("size_bytes")
        digest = row.get("sha256")
        if type(size_bytes) is not int or size_bytes < 0 or len(data) != size_bytes:
            raise ValueError(f"pinned source-text byte count mismatch: {key}")
        if type(digest) is not str or _sha(data) != digest:
            raise ValueError(f"pinned source-text bytes differ from receipt: {key}")
        expected_digest = row.get("expected_sha256")
        if expected_digest is not None and expected_digest != digest:
            raise ValueError(f"pinned source-text digest differs from expected blob: {key}")
        total_bytes += len(data)
    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"pinned source-text tree contains an unexpected symlink: {path}")
        if path.is_file() and path.name != "receipt.json":
            actual.add(path.relative_to(root).as_posix())
    if actual != expected or receipt.get("total_bytes") != total_bytes:
        raise ValueError(
            "pinned source-text tree differs from its receipt: "
            f"missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
        )


def build_source_composition_plan(
    task_input: dict,
    manifest: dict,
    *,
    task_input_bytes: bytes,
    manifest_bytes: bytes,
    install_root: Path,
    verification_receipt: dict,
    source_text_root: Path | None = None,
    source_text_receipt: dict | None = None,
) -> dict:
    """Verify fixed install bytes and emit a deterministic, non-native plan.

    The plan carries exact source identities and semantic object/fixture names.
    Compiled MJCF names and output XML stay null until the upstream model
    composition steps are implemented and independently checked.
    """
    if task_input.get("schema_version") != "libero-pilot-deployment-input-v1":
        raise ValueError("unsupported LIBERO pilot task input")
    manifest_sha = _sha(manifest_bytes)
    task_input_sha = _sha(task_input_bytes)
    if task_input.get("source_manifest_sha256") != manifest_sha:
        raise ValueError("task input source manifest identity differs from exact manifest bytes")
    if task_input.get("task_uid") != manifest.get("task", {}).get("task_uid"):
        raise ValueError("task input and source manifest task identities differ")
    if (verification_receipt.get("schema_version") != "libero-pilot-source-verify-receipt-v1"
            or verification_receipt.get("status") != "VERIFIED_INDEPENDENT_REREAD"
            or verification_receipt.get("manifest_sha256") != manifest_sha
            or verification_receipt.get("task_uid") != task_input.get("task_uid")):
        raise ValueError("source composition requires the matching independent install verification")
    unsigned_receipt = dict(verification_receipt)
    receipt_hash = unsigned_receipt.pop("result_sha256", None)
    if type(receipt_hash) is not str or _sha(_canonical(unsigned_receipt)) != receipt_hash:
        raise ValueError("source verification receipt self-hash mismatch")

    payloads, payload_bytes = _read_install(manifest, install_root)
    asset_rows = manifest.get("asset_closure", {}).get("files", ())
    manifest_rows = manifest.get("files", ())
    if not isinstance(asset_rows, list) or not isinstance(manifest_rows, list):
        raise ValueError("source manifest asset closure must contain a file list")
    if any(
        not isinstance(row, dict)
        or type(row.get("size_bytes")) is not int
        or row["size_bytes"] < 0
        for row in (*asset_rows, *manifest_rows)
    ):
        raise ValueError("source manifest byte-count rows must contain non-negative integers")
    expected_payloads = sorted(
        (
            {
                "install_path": row.get("install_path"),
                "sha256": row.get("sha256"),
                "size_bytes": row.get("size_bytes"),
            }
            for row in manifest_rows
            if isinstance(row, dict)
        ),
        key=lambda row: row["install_path"],
    )
    receipt_payloads = verification_receipt.get("payload_files")
    if not isinstance(receipt_payloads, list):
        raise ValueError("source verification receipt must enumerate every installed payload")
    try:
        receipt_payloads = sorted(
            (
                {
                    "install_path": row["install_path"],
                    "sha256": row["sha256"],
                    "size_bytes": row["size_bytes"],
                }
                for row in receipt_payloads
                if isinstance(row, dict)
            ),
            key=lambda row: row["install_path"],
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("source verification receipt has malformed payload rows") from exc
    expected_asset_bytes = sum(
        row.get("size_bytes", -1) for row in asset_rows if isinstance(row, dict)
    )
    expected_total_bytes = sum(
        row.get("size_bytes", -1)
        for row in manifest_rows if isinstance(row, dict)
    )
    if (
        verification_receipt.get("manifest_id") != manifest.get("manifest_id")
        or verification_receipt.get("asset_closure_sha256")
        != manifest.get("asset_closure", {}).get("sha256")
        or verification_receipt.get("file_count") != len(payloads)
        or verification_receipt.get("asset_file_count") != len(asset_rows)
        or verification_receipt.get("asset_bytes") != expected_asset_bytes
        or verification_receipt.get("total_bytes") != expected_total_bytes
        or receipt_payloads != expected_payloads
    ):
        raise ValueError("source verification receipt payload/count facts disagree with the manifest")
    if source_text_receipt is not None:
        if (source_text_receipt.get("schema_version") != "r07c-pinned-source-text-receipt-v1"
                or source_text_receipt.get("native_or_engine_imports") != 0
                or source_text_receipt.get("revisions") != manifest.get("source_revisions")):
            raise ValueError("pinned source-text receipt does not match the source revisions")
        if source_text_root is None:
            raise ValueError("pinned source-text receipt requires its source tree")
        _verify_source_text_tree(source_text_root, source_text_receipt)
    source_rows = _source_rows(
        manifest, payloads,
        source_text_root=source_text_root,
        source_text_receipt=source_text_receipt,
    )
    task = manifest["task"]
    type_sources = task.get("type_to_source_and_xml", {})
    semantic_rows = []
    names: set[str] = set()
    for role, instances in (
        ("object", task.get("objects_instance_to_type", {})),
        ("fixture", task.get("fixtures_instance_to_type", {})),
    ):
        if not isinstance(instances, dict):
            raise ValueError(f"LIBERO {role} instance map must be an object")
        for instance_name, type_name in sorted(instances.items()):
            if type(instance_name) is not str or not instance_name.strip() or instance_name in names:
                raise ValueError("LIBERO source composition has duplicate/invalid semantic instance names")
            names.add(instance_name)
            type_source = type_sources.get(type_name)
            if not isinstance(type_source, dict):
                raise ValueError(f"LIBERO object type has no pinned XML source: {type_name}")
            if type_name == "table":
                # Libero_Tabletop_Manipulation passes its selected scene_xml
                # directly into TableArena(xml=...), so the robosuite default
                # table_arena.xml is deliberately not an effective input.
                scene_ref = task_input["native_reference"]["active_scene_xml"]
                source_path = scene_ref["path"]
                source_repository = scene_ref["repository"]
            else:
                source_path = type_source.get("asset_source", type_source.get("xml_source"))
                source_repository = "robosuite" if isinstance(source_path, str) and source_path.startswith("robosuite/") else "libero"
            if not any(row["repository"] == source_repository and row["path"] == source_path for row in source_rows):
                raise ValueError(f"LIBERO type source is absent from selected source bytes: {source_path}")
            semantic_rows.append({
                "role": role,
                "instance_name": instance_name,
                "type_name": type_name,
                "upstream_class": type_source.get("class", "TableArena" if type_name == "table" else None),
                "upstream_class_source": type_source.get("class_source", type_source.get("owner_source")),
                "source_repository": source_repository,
                "source_xml": source_path,
                "source_xml_repository": source_repository,
                "source_binding_rule": "task_active_scene_xml_override" if type_name == "table" else "pinned_type_asset_xml",
                "core_object_reference": f"object:{instance_name}",
                "compiled_body_name": None,
                "status": "SEMANTIC_NAME_BOUND_COMPILED_NAME_UNVERIFIED",
            })

    active_scene = task_input.get("native_reference", {}).get("active_scene_xml", {})
    if not any(row["repository"] == active_scene.get("repository")
               and row["path"] == active_scene.get("path")
               and row["sha256"] == active_scene.get("sha256") for row in source_rows):
        raise ValueError("active scene XML is not bound to the exact verified source bytes")

    source_resolution = manifest.get("source_resolution", {})
    composition = {
        "schema_version": _COMPOSITION_SCHEMA,
        "status": "DECLARATION_ONLY_UPSTREAM_MERGE_NOT_EXECUTED",
        "identity": {
            "task_uid": task_input["task_uid"],
            "manifest_id": manifest.get("manifest_id"),
            "manifest_sha256": manifest_sha,
            "task_input_sha256": task_input_sha,
            "verification_receipt_sha256": receipt_hash,
            "source_text_receipt_sha256": (
                _sha(_canonical(source_text_receipt)) if source_text_receipt is not None else None
            ),
            "asset_closure_sha256": manifest.get("asset_closure", {}).get("sha256"),
            "source_revisions": manifest.get("source_revisions"),
        },
        "verified_install": {
            "file_count": verification_receipt.get("file_count"),
            "asset_file_count": verification_receipt.get("asset_file_count"),
            "asset_bytes": verification_receipt.get("asset_bytes"),
            "reread_bytes": payload_bytes,
        },
        "source_inputs": source_rows,
        "ordered_upstream_composition": [
            {
                "owner": "LIBERO Libero_Tabletop_Manipulation.__init__",
                "operation": "select table arena; preserve full task table dimensions, offset, and style properties",
                "evidence": [row for row in manifest.get("source_code_references", ())
                             if row.get("path", "").endswith("libero_tabletop_manipulation.py")],
            },
            {
                "owner": "LIBERO BDDLBaseDomain._load_model / TableArena / ManipulationTask",
                "operation": "apply origin/camera/style; add every fixture and movable object; merge task arena, MountedPanda, assets, sites, and object assets",
                "active_scene_xml": active_scene,
                "style_properties": source_resolution.get("scene_style_properties"),
                "style_rewrite_rules": source_resolution.get("scene_style_rewrite_rules"),
                "status": "SOURCE_RULES_BOUND_NOT_REPLAYED",
            },
            {
                "owner": "LIBERO BDDLBaseDomain._load_fixtures_in_arena / _load_objects_in_arena",
                "operation": "instantiate frozen instance-to-type maps with upstream object classes and names",
                "semantic_name_mapping": sorted(semantic_rows, key=lambda row: (row["role"], row["instance_name"])),
            },
            {
                "owner": "robosuite MountedPanda model composition",
                "operation": "compose Panda + RethinkMount + PandaGripper with source torque-arm and signed finger-position actuators",
                "robot_sources": [row for row in source_rows if row["repository"] == "robosuite"],
                "compiled_joint_actuator_slots": None,
                "status": "SOURCE_BYTES_BOUND_COMPILED_LAYOUT_UNVERIFIED",
            },
        ],
        "core_seam": {
            "candidate_owner": "BaseTaskEnv TaskDefinitionBase.create_action_adapter and resolve_task_references",
            "factory_route": "no LIBERO source composer/Scene-v3 RuntimeSource consumer is currently admitted by make_env",
            "compiled_scene_xml_sha256": None,
            "importable_by_task_env": False,
            "core_native_admission_ready": False,
        },
        "output": {
            "composed_mjcf_sha256": None,
            "compiled_scene_identity": None,
            "status": "NOT_COMPOSED",
        },
    }
    composition["composition_plan_sha256"] = _sha(_canonical(composition))
    return composition


def build_assembly(task_input: dict, manifest: dict) -> dict:
    return {
        "native_problem": task_input["native_reference"]["problem_class"],
        "native_arena_xml": task_input["native_reference"]["active_scene_xml"],
        "source_manifest_id": manifest["manifest_id"],
        "asset_closure": manifest["asset_closure"],
        "source_consumption": "R07c binds a deterministic verified-source composition declaration; upstream Python model merge is not replayed and no composed XML is emitted.",
        "factory_owner": "task_env.registry.py::make_env has no admitted arbitrary LIBERO source-composition route",
        "task_source_owner": "task_env/environment/task_source.py and task_env/assembly/source.py::TaskSceneSource; current source receipt is not extended for this LIBERO candidate",
        "reference_owner": "task_env/assembly/references.py::resolve_task_references",
        "runtime_source_owner": "task_env/runtime/sessions/source.py::RuntimeSource and ExecutionSourceReceiptV1",
        "core_native_admission_ready": False,
    }


__all__ = ["build_assembly", "build_source_composition_plan"]
