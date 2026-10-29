"""Pinned source binding and source-to-Core assembly owners.

The R07c helper below verifies a deterministic composition declaration against
an already independently verified local source installation. It deliberately
does not claim to emit the native MJCF: LIBERO builds arena, robot, fixture,
object, site and placement pieces through upstream Python model owners.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import posixpath
from pathlib import Path, PurePosixPath
import re
from typing import Any
import xml.etree.ElementTree as ET


_COMPOSITION_SCHEMA = "libero-source-composition-mjcf-v4"
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
            replacement = f"{prefix}{name}"
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
    """Normalize MJCF references to verified-install-relative closure paths."""
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
        rewritten.append(target)
        element.set("file", target)
    if compiler is not None:
        compiler.attrib.pop("meshdir", None)
        compiler.attrib.pop("texturedir", None)
    return rewritten


def _merge_fragment_assets(
    output: ET.Element,
    fragment: ET.Element,
    *,
    semantic_id: str,
    source_repository: str,
    source_path: str,
) -> list[dict[str, Any]]:
    """Replay pinned robosuite ``MujocoXML.merge_assets`` first-name wins.

    The upstream merge checks existing ``(tag, name)`` pairs and retains the
    first declaration. This matters for pinned LIBERO source such as
    ``flat_stove.xml``, which repeats ``tex-stove_knob`` for different files;
    both materials continue to reference the first retained declaration under
    the upstream merge rule.
    """
    source_asset = fragment.find("asset")
    if source_asset is None:
        return []
    output_asset = output.find("asset")
    if output_asset is None:
        output_asset = ET.SubElement(output, "asset")
    existing = {
        (node.tag, node.get("name")): node
        for node in output_asset
        if node.get("name") is not None
    }
    rows: list[dict[str, Any]] = []
    for ordinal, node in enumerate(list(source_asset), start=1):
        name = node.get("name")
        key = (node.tag, name)
        kept = existing.get(key) if name is not None else None
        if kept is None:
            output_asset.append(node)
            if name is not None:
                existing[key] = node
            continue
        incoming_attributes = dict(node.attrib)
        kept_attributes = dict(kept.attrib)
        rows.append({
            "semantic_id": semantic_id,
            "source_repository": source_repository,
            "source_path": source_path,
            "asset_type": node.tag,
            "source_name": name,
            "source_definition_ordinal": ordinal,
            "resolution": (
                "upstream_first_definition_identical_duplicate"
                if incoming_attributes == kept_attributes
                else "upstream_first_name_match_wins_conflicting_definition"
            ),
            "kept_attributes": kept_attributes,
            "discarded_attributes": incoming_attributes,
        })
    return rows


def _validate_composed_asset_names(root: ET.Element) -> None:
    """Reject duplicate composed asset declarations and dangling references."""
    asset = root.find("asset")
    if asset is None:
        return
    names: dict[str, set[str]] = {}
    for child in asset:
        name = child.get("name")
        if not name:
            continue
        bucket = names.setdefault(child.tag, set())
        if name in bucket:
            raise ValueError(f"composed MJCF still contains duplicate {child.tag} name {name!r}")
        bucket.add(name)
    for node in root.iter():
        for attribute, asset_type in (
            ("mesh", "mesh"), ("material", "material"), ("texture", "texture"),
            ("hfield", "hfield"),
        ):
            name = node.get(attribute)
            if name and name not in names.get(asset_type, set()):
                raise ValueError(
                    f"composed MJCF {node.tag} references missing {asset_type} {name!r}"
                )


def _append_section(output: ET.Element, source: ET.Element, section_name: str) -> None:
    section = source.find(section_name)
    if section is None:
        return
    target = output.find(section_name)
    if target is None:
        target = ET.SubElement(output, section_name)
    for child in list(section):
        target.append(child)


def _inline_source_defaults(fragment: ET.Element) -> None:
    """Apply the pinned robosuite MujocoXML default-class expansion rule."""
    defaults = fragment.find("default")
    if defaults is None:
        return
    classes = {
        item.get("class"): {child.tag: child for child in item}
        for item in defaults
        if item.get("class") is not None
    }

    def expand(element: ET.Element) -> None:
        class_name = element.attrib.pop("class", None)
        if class_name is not None:
            template = classes.get(class_name)
            if template is None:
                raise ValueError(f"MJCF default class is unresolved: {class_name}")
            defaults_for_tag = template.get(element.tag)
            if defaults_for_tag is not None:
                for key, value in defaults_for_tag.attrib.items():
                    if element.get(key) is None:
                        element.set(key, value)
        for child in list(element):
            expand(child)

    expand(fragment)
    fragment.remove(defaults)


def _extract_libero_object(
    fragment: ET.Element,
    *,
    instance: str,
    movable: bool,
) -> ET.Element:
    """Mirror the pinned MujocoXMLObject subtree, geometry and joint policy."""
    world = fragment.find("worldbody")
    if world is None:
        raise ValueError("pinned LIBERO object source has no worldbody")
    candidates = [body for body in world.iter("body") if body.get("name") == "object"]
    if len(candidates) != 1:
        raise ValueError("pinned LIBERO object source must contain exactly one body named 'object'")
    body = copy.deepcopy(candidates[0])
    body.set("name", "main")
    parents = {child: parent for parent in body.iter() for child in parent}
    for geom in tuple(body.iter("geom")):
        if geom.get("group") not in {"0", "1"}:
            parent = parents.get(geom)
            if parent is None:
                raise ValueError("pinned object geom has no parent")
            parent.remove(geom)
    if movable:
        ET.SubElement(body, "joint", {
            "name": "joint0", "type": "free", "damping": "0.0005",
        })
    site = ET.SubElement(body, "site", {
        "name": "default_site", "pos": "0 0 0", "size": "0.002 0.002 0.002",
        "rgba": "1 0 0 0", "type": "sphere", "group": "0",
    })
    del site
    _prefix_fragment_names(body, f"{instance}_")
    return body


def _set_table_arena_source_parameters(arena: ET.Element) -> dict[str, Any]:
    """Apply the fixed LIBERO TableArena constructor values to active scene XML."""
    table = next((body for body in arena.iter("body") if body.get("name") == "table"), None)
    if table is None:
        raise ValueError("active LIBERO arena XML has no semantic table body")
    size = (1.0, 1.2, 0.05)
    offset = (0.0, 0.0, 0.90)
    friction = (0.6, 0.005, 0.0001)
    half = tuple(value / 2.0 for value in size)
    center = (offset[0], offset[1], offset[2] - half[2])
    table.set("name", "main_table")
    table.set("pos", " ".join(f"{value:g}" for value in center))
    collision = table.find("./geom[@name='table_collision']")
    visual = table.find("./geom[@name='table_visual']")
    top = table.find("./site[@name='table_top']")
    if collision is None or visual is None or top is None:
        raise ValueError("pinned TableArena XML is missing the table collision/visual/top source elements")
    size_text = " ".join(f"{value:g}" for value in half)
    collision.set("size", size_text)
    collision.set("friction", " ".join(f"{value:g}" for value in friction))
    visual.set("size", size_text)
    top.set("pos", f"0 0 {half[2]:g}")
    leg_geom_names = ("table_leg1_visual", "table_leg2_visual", "table_leg3_visual", "table_leg4_visual")
    dxs, dys = (0.1, -0.1, -0.1, 0.1), (0.1, 0.1, -0.1, -0.1)
    leg_center_z = (offset[2] - half[2]) / 2.0
    for name, dx, dy in zip(leg_geom_names, dxs, dys):
        leg = table.find(f"./geom[@name='{name}']")
        if leg is None:
            raise ValueError(f"pinned TableArena is missing {name}")
        x = math.copysign(half[0], dx) - dx if half[0] > abs(dx * 2.0) else 0.0
        y = math.copysign(half[1], dy) - dy if half[1] > abs(dy * 2.0) else 0.0
        leg.set("pos", f"{x:g} {y:g} {-leg_center_z:g}")
        leg.set("size", f"0.025 {leg_center_z:g}")
    return {
        "table_body": "main_table",
        "full_size_m": list(size),
        "table_offset_m": list(offset),
        "table_center_m": list(center),
        "friction": list(friction),
        "has_legs": True,
    }


def _ordered_bddl_instances(data: bytes, section_name: str) -> list[tuple[str, str]]:
    """Read one flat pinned BDDL instance section in its lexical category order."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("pinned BDDL source is not UTF-8") from exc
    match = re.search(rf"\(:{re.escape(section_name)}\b(.*?)\)", text, re.DOTALL)
    if match is None:
        raise ValueError(f"pinned BDDL source has no :{section_name} section")
    section = "\n".join(line.split(";", 1)[0] for line in match.group(1).splitlines())
    tokens = section.split()
    instances: list[str] = []
    rows: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "-":
            if not instances or i + 1 >= len(tokens):
                raise ValueError(f"malformed pinned BDDL :{section_name} declaration")
            category = tokens[i + 1]
            rows.extend((instance, category) for instance in instances)
            instances.clear()
            i += 2
        else:
            instances.append(token)
            i += 1
    if instances:
        raise ValueError(f"pinned BDDL :{section_name} has untyped trailing instances")
    return rows


def _compose_mjcf(
    task_input: dict,
    manifest: dict,
    payloads: dict[str, bytes],
    install_root: Path,
) -> tuple[str, dict[str, Any]]:
    """Compose the source-derived LIBERO tree without claiming reset equivalence."""
    task = manifest["task"]
    input_ref = task_input["native_reference"]["active_scene_xml"]
    source_rows: list[dict[str, str]] = []
    resources: set[str] = set()
    root = ET.Element("mujoco", {"model": "libero_r07c_pilot_candidate_v3"})
    ET.SubElement(root, "compiler", {"angle": "radian", "autolimits": "true"})
    ET.SubElement(root, "option", {"timestep": "0.002", "gravity": "0 0 -9.81"})

    def read(repository: str, path: str, role: str) -> ET.Element:
        data = _source_payload(manifest, payloads, repository, path)
        digest = _sha(data)
        source_rows.append({"repository": repository, "path": path, "role": role, "sha256": digest})
        fragment = _parse_mjcf(data, f"{repository}/{path}")
        resources.update(_resolve_asset_files(fragment, path, repository, install_root, payloads))
        return fragment

    arena_bytes = _source_payload(manifest, payloads, input_ref["repository"], input_ref["path"])
    arena = _parse_mjcf(arena_bytes, f"{input_ref['repository']}/{input_ref['path']}")
    arena_digest = _sha(arena_bytes)
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
    _inline_source_defaults(arena)
    resources.update(_resolve_asset_files(
        arena, input_ref["path"], input_ref["repository"], install_root, payloads
    ))
    table_transform = _set_table_arena_source_parameters(arena)
    for section_name in ("asset", "worldbody", "actuator", "sensor", "contact", "tendon", "equality", "keyframe"):
        _append_section(root, arena, section_name)

    # LIBERO's ManipulationTask merges arena, then one robot, then movable
    # objects followed by fixtures. Match that source order because the init
    # flattened state stores native qpos/qvel in compiled joint order.
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
    for fragment in (robot, mount, gripper):
        _inline_source_defaults(fragment)
    _prefix_fragment_names(robot, "robot0_")
    _prefix_fragment_names(mount, "mount0_")
    _prefix_fragment_names(gripper, "gripper0_")
    robot_world, mount_world, gripper_world = (item.find("worldbody") for item in (robot, mount, gripper))
    if robot_world is None or mount_world is None or gripper_world is None:
        raise ValueError("pinned robot, mount and gripper sources require worldbody sections")
    robot_roots, mount_roots, gripper_roots = (list(item.findall("body")) for item in (robot_world, mount_world, gripper_world))
    if len(robot_roots) != 1 or len(mount_roots) != 1 or len(gripper_roots) != 1:
        raise ValueError("pinned robot, mount and gripper must each have one world root body")
    robot_body, mount_body, gripper_body = robot_roots[0], mount_roots[0], gripper_roots[0]
    if robot_body.get("name") != "robot0_base" or mount_body.get("name") != "mount0_base":
        raise ValueError("robot or mount root body name differs from pinned source")
    hand = next((body for body in robot_body.iter("body") if body.get("name") == "robot0_right_hand"), None)
    if hand is None:
        raise ValueError("pinned Panda XML has no right_hand gripper attachment body")
    hand.append(gripper_body)

    # MountedPanda.set_base_xpos(table offset) and RobotModel.add_mount derive
    # these transforms from the source model offsets. The current RethinkMount
    # XML root body has source base z=-0.922 and its source top offset is -0.01.
    robot_base_pos = tuple(float(v) for v in robot_body.get("pos", "0 0 0").split())
    mount_source_base_pos = tuple(float(v) for v in mount_body.get("pos", "0 0 0").split())
    if len(robot_base_pos) != 3 or len(mount_source_base_pos) != 3:
        raise ValueError("robot and mount source base offsets must each contain three coordinates")
    mount_top_offset = (0.0, 0.0, -0.01)
    requested_base = (-0.16 - 1.0 / 2.0, 0.0, 0.0)
    mount_relative = tuple(a - b for a, b in zip(robot_base_pos, mount_top_offset))
    mount_bottom = tuple(a - b for a, b in zip(mount_source_base_pos, mount_top_offset))
    robot_bottom = tuple(a + b for a, b in zip(mount_bottom, robot_base_pos))
    robot_world_pos = tuple(a - b for a, b in zip(requested_base, robot_bottom))
    mount_body.set("pos", " ".join(f"{value:g}" for value in mount_relative))
    robot_body.set("pos", " ".join(f"{value:g}" for value in robot_world_pos))
    robot_body.append(mount_body)
    for joint in robot.iter("joint"):
        name = joint.get("name", "")
        suffix = name.removeprefix("robot0_")
        if suffix in {f"joint{i}" for i in range(1, 6)}:
            joint.set("damping", "0.1")
        elif suffix in {"joint6", "joint7"}:
            joint.set("damping", "0.01")
    world = root.find("worldbody")
    if world is None:
        world = ET.SubElement(root, "worldbody")
    world.append(robot_body)
    for fragment in (robot, gripper, mount):
        for section_name in ("asset", "actuator", "sensor", "contact", "tendon", "equality", "keyframe"):
            _append_section(root, fragment, section_name)

    bddl_ref = task_input.get("bddl", {})
    bddl_path = bddl_ref.get("path")
    if type(bddl_path) is not str:
        raise ValueError("task input must bind the exact BDDL declaration source")
    bddl_bytes = _source_payload(manifest, payloads, "libero", bddl_path)
    if _sha(bddl_bytes) != bddl_ref.get("sha256"):
        raise ValueError("pinned BDDL declaration bytes differ from task input")
    source_rows.append({"repository": "libero", "path": bddl_path,
                        "role": "ordered_task_instances", "sha256": _sha(bddl_bytes)})
    declared_objects = _ordered_bddl_instances(bddl_bytes, "objects")
    declared_fixtures = _ordered_bddl_instances(bddl_bytes, "fixtures")
    object_map = task.get("objects_instance_to_type", {})
    fixture_map = task.get("fixtures_instance_to_type", {})
    if dict(declared_objects) != object_map or dict(declared_fixtures) != fixture_map:
        raise ValueError("pinned BDDL instance declarations differ from the frozen task maps")

    type_sources = task.get("type_to_source_and_xml", {})
    semantic_to_body: dict[str, str] = {"main_table": "main_table"}
    ordered_objects: list[dict[str, str]] = []
    ordered_fixtures: list[dict[str, str]] = []
    asset_merge_rows: list[dict[str, Any]] = []
    for declarations, role, movable in (
        (declared_objects, "object", True),
        (declared_fixtures, "fixture", False),
    ):
        for instance, type_name in declarations:
            if type_name == "table":
                semantic_to_body[instance] = "main_table"
                continue
            source = type_sources[type_name]
            source_path = source.get("asset_source", source.get("xml_source"))
            repository = "robosuite" if source_path.startswith("robosuite/") else "libero"
            fragment = read(repository, source_path, f"{role}:{instance}")
            _inline_source_defaults(fragment)
            asset_merge_rows.extend(_merge_fragment_assets(
                root, fragment, semantic_id=instance,
                source_repository=repository, source_path=source_path,
            ))
            body = _extract_libero_object(fragment, instance=instance, movable=movable)
            semantic_to_body[instance] = body.get("name", "")
            geom_names = []
            for geom_index, geom in enumerate(body.iter("geom")):
                name = geom.get("name")
                if not name:
                    # The upstream task gives several object geoms no names.
                    # Stable names are metadata only; retaining the original
                    # unnamed geoms would make exact public contact groups
                    # impossible to bind through MuJoCo's name API.
                    name = f"libero_contact_{instance}_{geom_index:03d}"
                    geom.set("name", name)
                if name in geom_names:
                    raise ValueError(f"duplicate source geom name in {instance!r}: {name!r}")
                geom_names.append(name)
            row = {
                "semantic_id": instance,
                "source_path": source_path,
                "body_name": body.get("name", ""),
                "geom_names": geom_names,
                "joint_policy": "free_joint_joint0_damping_0.0005" if movable else "no_root_joint_fixture_internal_joints_preserved",
                "geom_groups": ["0", "1"],
            }
            (ordered_objects if movable else ordered_fixtures).append(row)
            world = root.find("worldbody")
            if world is None:
                world = ET.SubElement(root, "worldbody")
            world.append(body)

    _validate_composed_asset_names(root)
    # Stable output bytes: sorted attributes, fixed indentation and UTF-8 XML.
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode", short_empty_elements=True) + "\n"
    digest = _sha(xml.encode("utf-8"))
    receipt = {
        "schema_version": "libero-source-composition-mjcf-v4",
        "source_files": sorted(source_rows, key=lambda row: (row["repository"], row["path"], row["role"])),
        "semantic_body_map": semantic_to_body,
        "joint_instance_order": ["robot0", *[row["semantic_id"] for row in ordered_objects],
                                  *[row["semantic_id"] for row in ordered_fixtures]],
        "movable_object_instances": ordered_objects,
        "fixture_instances": ordered_fixtures,
        "contact_geom_name_transform": {
            "schema_version": "libero-contact-source-name-transform-v1",
            "scope": "unnamed geoms inside task object and fixture source bodies",
            "rule": "libero_contact_{semantic_id}_{zero_based_body_geom_index:03d}",
            "physics_attributes_changed": False,
            "groups": {
                row["semantic_id"]: row["geom_names"]
                for row in (*ordered_objects, *ordered_fixtures)
            },
        },
        "asset_merge_receipt": {
            "schema_version": "libero-source-asset-merge-v1",
            "rule": "match pinned robosuite MujocoXML.merge_assets by (asset tag, name), retaining the first definition and preserving all source references",
            "physics_attributes_changed": False,
            "duplicate_definitions": asset_merge_rows,
        },
        "table_arena_transform": table_transform,
        "mounted_panda_transform": {
            "schema_version": "libero-mounted-panda-transform-v1",
            "robot_root_body": "robot0_base",
            "mount_root_body": "mount0_base",
            "mount_parent_body": "robot0_base",
            "gripper_parent_body": "robot0_right_hand",
            "requested_base_bottom_m": list(requested_base),
            "robot_root_pos_m": list(robot_world_pos),
            "mount_child_pos_m": list(mount_relative),
            "mount_top_offset_m": list(mount_top_offset),
            "mount_source_root_pos_m": list(mount_source_base_pos),
            "formulas": ["mount_relative=robot_base_offset-mount_top_offset",
                         "robot_bottom_offset=mount_source_root_pos-mount_top_offset+robot_base_offset",
                         "robot_root_pos=requested_base_bottom-robot_bottom_offset"],
        },
        "resource_references": sorted(resources),
        "output_sha256": digest,
        "output_bytes": len(xml.encode("utf-8")),
        "physics_options": {"timestep_s": 0.002, "gravity_m_s2": [0.0, 0.0, -9.81],
                            "integrator": "MuJoCo default; no implicitfast override"},
        "placement_status": "DYNAMIC_FREE_ROOTS_COMPOSED; ORIGINAL_FIXTURE_BODY_POSES_NOT_IN_PRUNED_INIT",
        "pruned_init_status": "SAFE_DECODER_AND_SOURCE_NAME_LAYOUT_SEPARATE; COMPILED_MODEL_CONFIRMATION_REQUIRED",
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
            "SOURCE_DERIVED_MJCF_COMPOSED_ORIGINAL_FIXTURE_POSES_UNRESOLVED"
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
                "operation": "apply TableArena geometry, source style, named object subtrees, movable root joints, and MountedPanda model transforms in ManipulationTask order",
                "active_scene_xml": active_scene,
                "style_properties": source_resolution.get("scene_style_properties"),
                "style_rewrite_rules": source_resolution.get("scene_style_rewrite_rules"),
                "status": "SOURCE_RULES_REPLAYED; ORIGINAL_PER_ROW_FIXTURE_BODY_POSES_STILL_MISSING",
            },
            {
                "owner": "LIBERO BDDLBaseDomain._load_fixtures_in_arena / _load_objects_in_arena",
                "operation": "instantiate frozen instance-to-type maps in insertion order; movable classes receive default free joint and fixtures keep internal joints with fixed root",
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
                "status": "SOURCE_MJCF_NAMES_BOUND_COMPILED_LAYOUT_UNVERIFIED" if composition_receipt is not None else "SOURCE_BYTES_BOUND_COMPILED_LAYOUT_UNVERIFIED",
            },
        ],
        "core_seam": {
            "candidate_owner": "bench_deploy.libero.selected_candidate.build_libero_selected_candidate -> SelectedReferenceEnv.from_libero_diagnostic_candidate -> RuntimeSession.materialize",
            "factory_route": "versioned internal diagnostic candidate through the existing SelectedReferenceEnv and RuntimeSession owners; no make_env UID or general provider capability is registered",
            "compiled_scene_xml_sha256": None if composition_receipt is None else composition_receipt["output_sha256"],
            "source_candidate_ready": composition_receipt is not None,
            "runtime_admission": "checked by the selected diagnostic candidate before reset",
            "formal_qualification": "NOT_GRANTED",
        },
        "output": {
            "composed_mjcf_sha256": None if composition_receipt is None else composition_receipt["output_sha256"],
            "composed_mjcf_bytes": None if composition_receipt is None else composition_receipt["output_bytes"],
            "composition_receipt_sha256": None if composition_receipt is None else composition_receipt["receipt_sha256"],
            "compiled_scene_identity": None,
            "status": "SOURCE_MJCF_COMPOSED_NOT_NATIVE_COMPILED" if compose_mjcf else "NOT_COMPOSED_TEST_PREFLIGHT_ONLY",
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
        "source_consumption": "A deterministic source-derived MJCF applies the LIBERO object subtree/free-joint policy, fixture internal joints, table parameters, and MountedPanda transforms; the selected diagnostic route binds its versioned fixture realization and row restore through the existing RuntimeSession reset owner.",
        "factory_owner": "bench_deploy.libero.selected_candidate.build_libero_selected_candidate constructs the versioned SelectedReferenceEnv diagnostic candidate through the existing RuntimeSession admission route; it is not registered with make_env",
        "task_source_owner": "bench_deploy.libero.assembly source composer -> versioned SelectedReferenceEnv candidate -> task_env/runtime/sessions/source.py RuntimeSource and ExecutionSourceReceiptV1",
        "reference_owner": "task_env/assembly/references.py::resolve_task_references",
        "runtime_source_owner": "task_env/runtime/sessions/source.py::RuntimeSource and ExecutionSourceReceiptV1",
        "runtime_admission": "checked by the selected diagnostic candidate before reset",
        "formal_qualification": "NOT_GRANTED",
    }


__all__ = ["build_assembly", "build_source_composition_plan"]
