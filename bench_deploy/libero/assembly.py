"""Pinned source binding and source-to-Core assembly owners.

The R07c helper below verifies a deterministic composition declaration against
an already independently verified local source installation. It deliberately
does not claim to emit the native MJCF: LIBERO builds arena, robot, fixture,
object, site and placement pieces through upstream Python model owners.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET


_COMPOSITION_SCHEMA = "libero-source-composition-mjcf-v2"
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


_MJCF_REFERENCE_ATTRIBUTES = frozenset({
    "mesh", "material", "texture", "hfield", "joint", "joint1", "joint2",
    "body", "site", "geom", "geom1", "geom2", "tendon", "actuator",
    "class", "childclass", "target", "objname", "refname", "name1", "name2",
})


def _source_payload(manifest: dict, payloads: dict[str, bytes], repository: str, path: str) -> bytes:
    matches = [
        row for row in manifest.get("files", ())
        if isinstance(row, dict)
        and row.get("repository") == repository
        and row.get("source_path", row.get("path")) == path
    ]
    if len(matches) != 1:
        raise ValueError(f"MJCF source must resolve to one manifest row: {repository}/{path}")
    install_path = matches[0].get("install_path")
    if type(install_path) is not str or install_path not in payloads:
        raise ValueError(f"MJCF bytes are absent from verified installation: {repository}/{path}")
    return payloads[install_path]


def _parse_mjcf(data: bytes, identity: str) -> ET.Element:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"pinned MJCF source is malformed: {identity}") from exc
    if root.tag != "mujoco":
        raise ValueError(f"pinned source is not a <mujoco> document: {identity}")
    return root


def _prefix_fragment_names(root: ET.Element, prefix: str, *, preserve: frozenset[str] = frozenset()) -> None:
    """Namespace a fragment's local names and rewrite its intra-fragment refs."""
    names: dict[str, str] = {}
    for element in root.iter():
        name = element.get("name")
        if name and name not in preserve:
            replacement = f"{prefix}__{name}"
            if name in names and names[name] != replacement:
                raise ValueError(f"duplicate MJCF local name in {prefix}: {name}")
            names[name] = replacement
    for element in root.iter():
        name = element.get("name")
        if name in names:
            element.set("name", names[name])
        for attribute in _MJCF_REFERENCE_ATTRIBUTES:
            value = element.get(attribute)
            if value in names:
                element.set(attribute, names[value])


def _resolve_asset_files(
    root: ET.Element,
    source_path: str,
    repository: str,
    install_root: Path,
    payloads: dict[str, bytes],
) -> list[str]:
    """Rewrite relative MJCF file references to verified-install absolute paths."""
    install_rel = PurePosixPath("upstream") / repository / PurePosixPath(source_path)
    model_dir = install_rel.parent
    compiler = root.find("compiler")
    meshdir = PurePosixPath(compiler.get("meshdir", ".")) if compiler is not None else PurePosixPath(".")
    texturedir = PurePosixPath(compiler.get("texturedir", str(meshdir))) if compiler is not None else meshdir
    rewritten: list[str] = []
    for element in root.iter():
        raw = element.get("file")
        if not raw:
            continue
        file_path = PurePosixPath(raw)
        directory = texturedir if element.tag == "texture" else meshdir
        if file_path.is_absolute():
            raise ValueError(f"absolute MJCF asset paths are forbidden: {source_path}:{raw}")
        resolved = PurePosixPath(posixpath.normpath(str(model_dir / directory / file_path)))
        if ".." in resolved.parts:
            raise ValueError(f"MJCF asset path escapes verified install: {source_path}:{raw}")
        target = "/".join(resolved.parts)
        if target not in payloads:
            raise ValueError(f"MJCF asset is outside the verified source closure: {source_path}:{raw}")
        absolute = (install_root / target).resolve(strict=True)
        try:
            absolute.relative_to(install_root.resolve(strict=True))
        except ValueError as exc:
            raise ValueError(f"MJCF asset escaped verified install: {source_path}:{raw}") from exc
        rewritten.append(str(absolute))
        element.set("file", str(absolute))
    if compiler is not None:
        compiler.attrib.pop("meshdir", None)
        compiler.attrib.pop("texturedir", None)
    return rewritten


def _append_section(output: ET.Element, source: ET.Element, section_name: str) -> None:
    section = source.find(section_name)
    if section is None:
        return
    target = output.find(section_name)
    if target is None:
        target = ET.SubElement(output, section_name)
    for child in list(section):
        target.append(child)


def _compose_mjcf(
    task_input: dict,
    manifest: dict,
    payloads: dict[str, bytes],
    install_root: Path,
) -> tuple[str, dict[str, Any]]:
    """Emit a deterministic, source-bound static MJCF composition candidate.

    The source code's runtime placement sampler remains a separate, explicitly
    unresolved step; this function composes the exact XML fragments only.
    """
    task = manifest["task"]
    input_ref = task_input["native_reference"]["active_scene_xml"]
    source_rows: list[dict[str, str]] = []
    resources: set[str] = set()
    root = ET.Element("mujoco", {"model": "libero_r07c_pilot_candidate_v2"})
    ET.SubElement(root, "compiler", {"angle": "radian", "autolimits": "true"})
    ET.SubElement(root, "option", {"timestep": "0.002", "gravity": "0 0 -9.81", "integrator": "implicitfast"})

    def read(repository: str, path: str, role: str) -> ET.Element:
        data = _source_payload(manifest, payloads, repository, path)
        digest = _sha(data)
        source_rows.append({"repository": repository, "path": path, "role": role, "sha256": digest})
        fragment = _parse_mjcf(data, f"{repository}/{path}")
        resources.update(_resolve_asset_files(fragment, path, repository, install_root, payloads))
        return fragment

    arena = _parse_mjcf(
        _source_payload(manifest, payloads, input_ref["repository"], input_ref["path"]),
        f"{input_ref['repository']}/{input_ref['path']}",
    )
    arena_digest = _sha(
        _source_payload(manifest, payloads, input_ref["repository"], input_ref["path"])
    )
    source_rows.append({"repository": input_ref["repository"], "path": input_ref["path"],
                        "role": "active_scene", "sha256": arena_digest})
    # The pinned style source records these two upstream rewrite rules. Apply
    # them before file resolution so the composed root references the effective
    # files actually selected by LIBERO's fixed style policy.
    style_rules = manifest.get("source_resolution", {}).get("scene_style_rewrite_rules", ())
    for rule in style_rules:
        for element in arena.iter(rule.get("element", "")):
            if element.get("name") == rule.get("name") and element.get("file") == rule.get("declared_ref"):
                element.set("file", rule["effective_ref"])
    # Re-run resolution after style substitution.
    resources.update(_resolve_asset_files(
        arena, input_ref["path"], input_ref["repository"], install_root, payloads
    ))
    table = next((body for body in arena.iter("body") if body.get("name") == "table"), None)
    if table is None:
        raise ValueError("active LIBERO arena XML has no semantic table body")
    table.set("name", "main_table")
    for section_name in ("asset", "worldbody", "actuator", "sensor", "contact", "default", "tendon", "equality", "keyframe"):
        _append_section(root, arena, section_name)

    type_sources = task.get("type_to_source_and_xml", {})
    semantic_to_body: dict[str, str] = {"main_table": "main_table"}
    # The XML's exact source-declared body templates are instantiated once per
    # semantic object/fixture. Runtime BDDL placement sampling is not claimed.
    for collection, role in ((task.get("objects_instance_to_type", {}), "object"),
                             (task.get("fixtures_instance_to_type", {}), "fixture")):
        for instance, type_name in sorted(collection.items()):
            if type_name == "table":
                semantic_to_body[instance] = "main_table"
                continue
            source = type_sources[type_name]
            source_path = source.get("asset_source", source.get("xml_source"))
            repository = "robosuite" if source_path.startswith("robosuite/") else "libero"
            fragment = read(repository, source_path, f"{role}:{instance}")
            _prefix_fragment_names(fragment, instance)
            world = fragment.find("worldbody")
            bodies = [] if world is None else world.findall("body")
            if len(bodies) != 1:
                raise ValueError(f"source object must expose exactly one world root body: {source_path}")
            bodies[0].set("name", instance)
            semantic_to_body[instance] = instance
            for section_name in ("asset",):
                _append_section(root, fragment, section_name)
            target_world = root.find("worldbody")
            if target_world is None:
                target_world = ET.SubElement(root, "worldbody")
            target_world.append(bodies[0])

    # Compose the pinned robot, mount and gripper sources as a declared static
    # tree. The source code also applies placement transforms and samplers; the
    # tree hash here therefore attests only this XML composition.
    robot_paths = {
        (row.get("repository"), row.get("path"))
        for row in (*manifest.get("source_code_references", ()), *manifest.get("selected_xml_sources", ()))
        if isinstance(row, dict)
    }
    def robot_source(suffix: str) -> tuple[str, str]:
        matches = sorted((repo, path) for repo, path in robot_paths if isinstance(path, str) and path.endswith(suffix))
        if len(matches) != 1:
            raise ValueError(f"expected one pinned robot source ending {suffix!r}")
        return matches[0]

    robot_repo, robot_path = robot_source("robosuite/models/assets/robots/panda/robot.xml")
    mount_repo, mount_path = robot_source("robosuite/models/assets/mounts/rethink_mount.xml")
    gripper_repo, gripper_path = robot_source("robosuite/models/assets/grippers/panda_gripper.xml")
    robot = read(robot_repo, robot_path, "mounted_panda_robot")
    mount = read(mount_repo, mount_path, "rethink_mount")
    gripper = read(gripper_repo, gripper_path, "panda_gripper")
    _prefix_fragment_names(robot, "robot", preserve=frozenset({
        "joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7",
        "torq_j1", "torq_j2", "torq_j3", "torq_j4", "torq_j5", "torq_j6", "torq_j7",
    }))
    _prefix_fragment_names(mount, "mount")
    _prefix_fragment_names(gripper, "gripper", preserve=frozenset({
        "finger_joint1", "finger_joint2", "gripper_finger_joint1", "gripper_finger_joint2",
        "right_gripper", "eef", "grip_site",
    }))
    robot_body = robot.find("worldbody/body")
    mount_body = mount.find("worldbody/body")
    gripper_body = gripper.find("worldbody/body")
    if robot_body is None or mount_body is None or gripper_body is None:
        raise ValueError("robot, mount and gripper fragments must each have a world root body")
    robot_body.set("name", "panda_base")
    # Attach the gripper at the source-defined right_hand end body.
    hand = next((body for body in robot_body.iter("body") if body.get("name") == "robot__right_hand"), None)
    if hand is None:
        raise ValueError("pinned Panda XML has no right_hand gripper attachment body")
    hand.append(gripper_body)
    world = root.find("worldbody")
    assert world is not None
    world.append(mount_body)
    world.append(robot_body)
    for fragment in (robot, gripper):
        _append_section(root, fragment, "asset")
        _append_section(root, fragment, "actuator")
    _append_section(root, mount, "asset")

    # Stable output bytes: sorted attributes, fixed indentation and UTF-8 XML.
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode", short_empty_elements=True) + "\n"
    digest = _sha(xml.encode("utf-8"))
    receipt = {
        "schema_version": "libero-static-mjcf-composition-receipt-v1",
        "source_files": sorted(source_rows, key=lambda row: (row["repository"], row["path"], row["role"])),
        "semantic_body_map": semantic_to_body,
        "resource_references": sorted(resources),
        "output_sha256": digest,
        "output_bytes": len(xml.encode("utf-8")),
        "placement_status": "STATIC_XML_ONLY_UPSTREAM_BDDL_AND_SITE_SAMPLERS_NOT_EXECUTED",
        "pruned_init_status": "NOT_DECODED_OR_MAPPED",
    }
    receipt["receipt_sha256"] = _sha(_canonical(receipt))
    return xml, receipt


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
    compose_mjcf: bool = True,
) -> dict:
    """Verify source bytes and emit a deterministic static MJCF candidate."""
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
    if type(compose_mjcf) is not bool:
        raise TypeError("compose_mjcf must be bool")
    composed_xml, composition_receipt = (
        _compose_mjcf(task_input, manifest, payloads, Path(install_root).resolve(strict=True))
        if compose_mjcf else (None, None)
    )
    if composition_receipt is not None:
        semantic_body_map = composition_receipt["semantic_body_map"]
        for row in semantic_rows:
            row["compiled_body_name"] = semantic_body_map.get(row["instance_name"])
            row["status"] = "STATIC_COMPOSITION_NAME_BOUND_NATIVE_ID_UNVERIFIED"
    composition = {
        "schema_version": _COMPOSITION_SCHEMA,
        "status": (
            "STATIC_SOURCE_XML_COMPOSED_RUNTIME_PLACEMENT_NOT_EXECUTED"
            if compose_mjcf else "SOURCE_BYTES_VERIFIED_COMPOSITION_SKIPPED"
        ),
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
                "compiled_joint_actuator_slots": (
                    [item.get("name") for item in task_input.get("native_reference", {}).get("robot", {}).get("actuators", ())]
                    if composition_receipt is not None else None
                ),
                "status": "STATIC_MJCF_NAMES_BOUND_NATIVE_LAYOUT_UNVERIFIED" if composition_receipt is not None else "SOURCE_BYTES_BOUND_COMPILED_LAYOUT_UNVERIFIED",
            },
        ],
        "core_seam": {
            "candidate_owner": "BaseTaskEnv.compile_task_scene -> task-specific source composer -> TaskDefinitionBase.create_action_adapter",
            "factory_route": "explicit internal LIBERO pilot candidate; no make_env UID or provider admission is registered",
            "compiled_scene_xml_sha256": None if composition_receipt is None else composition_receipt["output_sha256"],
            "importable_by_task_env": composition_receipt is not None,
            "core_native_admission_ready": False,
        },
        "output": {
            "composed_mjcf_sha256": None if composition_receipt is None else composition_receipt["output_sha256"],
            "composed_mjcf_bytes": None if composition_receipt is None else composition_receipt["output_bytes"],
            "composition_receipt_sha256": None if composition_receipt is None else composition_receipt["receipt_sha256"],
            "compiled_scene_identity": None,
            "status": "STATIC_XML_COMPOSED_NOT_NATIVE_COMPILED" if compose_mjcf else "NOT_COMPOSED_TEST_PREFLIGHT_ONLY",
        },
        "composition_receipt": composition_receipt,
        "semantic_to_compiled_body_names": {} if composition_receipt is None else composition_receipt["semantic_body_map"],
        "mjcf_xml": composed_xml,
    }
    # The deterministic plan binds the output hash and receipt. The XML itself
    # is supplied separately to SceneSource and re-hashed at that boundary.
    plan_projection = dict(composition)
    plan_projection.pop("mjcf_xml")
    composition["composition_plan_sha256"] = _sha(_canonical(plan_projection))
    return composition


def build_assembly(task_input: dict, manifest: dict) -> dict:
    return {
        "native_problem": task_input["native_reference"]["problem_class"],
        "native_arena_xml": task_input["native_reference"]["active_scene_xml"],
        "source_manifest_id": manifest["manifest_id"],
        "asset_closure": manifest["asset_closure"],
        "source_consumption": "A deterministic static MJCF candidate is composed from the verified active arena, object, fixture, Panda, mount and gripper XML sources; upstream BDDL/site placement and pruned-init realization remain unexecuted.",
        "factory_owner": "bench_deploy.libero.core_candidate.build_libero_pilot_env explicitly constructs an internal BaseTaskEnv candidate; it is not registered with make_env",
        "task_source_owner": "bench_deploy.libero.core_candidate.LiberoPilotSceneComposer -> task_env.assembly.compile_task_scene -> GeoPhys SceneSource",
        "reference_owner": "task_env/assembly/references.py::resolve_task_references",
        "runtime_source_owner": "task_env/runtime/sessions/source.py::RuntimeSource and ExecutionSourceReceiptV1",
        "core_native_admission_ready": False,
    }


__all__ = ["build_assembly", "build_source_composition_plan"]
