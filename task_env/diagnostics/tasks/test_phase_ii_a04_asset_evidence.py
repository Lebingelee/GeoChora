"""A04 evidence for existing asset manifests, source identity and public imports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from task_env.assembly.assets import (
    _asset_definition_from_manifest,
    _source_closure_digest,
    _source_closure_manifest,
)
from task_env.artifacts import (
    ActuatorReference,
    ActuatorResourceDefinition,
    ArticulationDefinition,
    ControlGroup,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    PoseWorld,
    RobotInstance,
    SceneDefinition,
)
from task_env.environment import AssetManifest, TaskCompositionSpec
from task_env.objects.nut_assembly import SquarePegObject
from task_env.registry import ComponentRegistry, make_agent, make_object, make_scene
from task_env.robots.panda import PANDA_ASSET_ROOT, PandaAgent
from task_env.utils.rotation import matrix_to_quat_wxyz


MENAGERIE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
PANDA_ENTITY_ID = "panda-main"


def _asset_root() -> Path:
    return PANDA_ASSET_ROOT.resolve()


def _copy_snapshot(files: dict[str, bytes], root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for logical_path, content in files.items():
        target = root / Path(*logical_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return root


def _protect_snapshot(root: Path) -> None:
    for path in root.rglob("*"):
        path.chmod(0o444 if path.is_file() else 0o555)
    root.chmod(0o555)


def _unprotect_snapshot(root: Path) -> None:
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o644)


def _logical_files(imported, root: Path) -> dict[str, bytes]:
    files = {}
    for path in imported.dependency_paths:
        resolved = Path(path).resolve()
        try:
            logical = resolved.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise AssertionError(f"import dependency escaped declared asset root: {resolved}") from exc
        files[logical] = resolved.read_bytes()
    return files


def _stable_source_locator(source_ref, root: Path) -> dict[str, str]:
    """Replace importer-local absolute source paths with closure-relative paths."""

    source_path = Path(source_ref.uri).resolve()
    try:
        logical_path = source_path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise AssertionError(f"source locator escaped declared asset root: {source_path}") from exc
    return {
        "path": logical_path,
        "element_path": source_ref.element_path,
        "format": source_ref.format,
    }


def _source_xml_inventory(xml_bytes: bytes, logical_path: str):
    """Enumerate XML structure for stable provenance without interpreting MJCF."""

    root = ET.fromstring(xml_bytes)
    inventory = []
    by_tag_and_name = {}

    def visit(element, parent_path: str | None, ordinal: int) -> None:
        tag = str(element.tag)
        name = str(element.get("name", ""))
        if parent_path is None:
            element_path = "/mjcf"
        else:
            token = f"{tag}[{name}]#{ordinal}" if name else f"{tag}[{ordinal}]"
            element_path = f"{parent_path}/{token}"
        locator = {
            "path": logical_path,
            "element_path": element_path,
            "format": "mjcf",
        }
        inventory.append(
            {
                "source_locator": locator,
                "element_tag": tag,
                "element_name": name or None,
                "imported_locator": None,
                "canonical_reference": None,
                "mapping_ids": [],
                "core_disposition": "SOURCE_RETAINED",
            }
        )
        if name:
            by_tag_and_name.setdefault((tag, name), []).append(locator)

        tag_ordinals = {}
        for child in list(element):
            child_tag = str(child.tag)
            tag_ordinals[child_tag] = tag_ordinals.get(child_tag, 0) + 1
            visit(child, element_path, tag_ordinals[child_tag])

    visit(root, None, 1)
    return inventory, by_tag_and_name


def _raw_xml_locator(by_tag_and_name, tag: str, name: str) -> dict[str, str]:
    matches = by_tag_and_name.get((tag, name), ())
    if len(matches) != 1:
        raise AssertionError(f"expected one raw XML locator for {tag}[{name}], got {len(matches)}")
    return dict(matches[0])


def _raw_xml_locator_by_name(by_tag_and_name, name: str) -> dict[str, str]:
    matches = [
        locator
        for (tag, candidate_name), locators in by_tag_and_name.items()
        if candidate_name == name
        for locator in locators
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one raw XML locator for name {name!r}, got {len(matches)}")
    return dict(matches[0])


def _core_disposition(semantic: str, source_path: str, closure_paths: set[str]) -> str:
    """Classify Core representation independently of provider capability status."""

    if semantic in {"frame.body", "joint.kinematic", "actuator.control"}:
        return "CANONICAL_REPRESENTED"
    if source_path and source_path in closure_paths:
        return "SOURCE_RETAINED"
    return "UNSUPPORTED"


def _pose_from_transform(values) -> PoseWorld:
    matrix = np.asarray(values, dtype=np.float64).reshape(4, 4)
    quaternion = matrix_to_quat_wxyz(matrix[:3, :3])
    return PoseWorld(
        tuple(float(value) for value in matrix[:3, 3]),
        tuple(float(value) for value in quaternion),
    )


def _panda_scene_from_import(imported, manifest) -> SceneDefinition:
    entity_id = PANDA_ENTITY_ID
    asset = _asset_definition_from_manifest(manifest)
    bodies = {body.body_id: body for body in imported.ir.bodies}
    bodies_by_frame = {body.frame_id: body for body in imported.ir.bodies}
    frames_by_id = {frame.node_id: frame for frame in imported.ir.frames}
    frame_definitions = tuple(
        FrameDefinition(
            schema_version="frame-definition-v1",
            entity_id=entity_id,
            frame_id=body.name,
            frame_kind="runtime",
            parent=None,
            pose_parent=None,
        )
        for body in imported.ir.bodies
    )

    coordinate_layout = {
        "hinge": ("revolute", "radian", "radian_per_second", 1, 1),
        "slide": ("prismatic", "meter", "meter_per_second", 1, 1),
        "fixed": ("fixed", "none", "none", 0, 0),
    }
    joints = []
    source_joint_names = set()
    joint_child_frames = set()
    for imported_joint in imported.ir.joints:
        source_name = imported_joint.dynamics.get("source_name")
        if not source_name:
            raise AssertionError(f"joint lacks source name: {imported_joint.joint_id}")
        if imported_joint.body_a is None or imported_joint.body_a not in bodies:
            raise AssertionError(f"Panda joint has no canonical parent body: {source_name}")
        if imported_joint.body_b not in bodies:
            raise AssertionError(f"Panda joint has no canonical child body: {source_name}")
        parent = bodies[imported_joint.body_a]
        child = bodies[imported_joint.body_b]
        kind, position, velocity, position_size, velocity_size = coordinate_layout[
            imported_joint.type
        ]
        joints.append(
            JointDefinition(
                schema_version="joint-definition-v1",
                joint_id=source_name,
                parent_frame=FrameReference(entity_id, parent.name),
                child_frame=FrameReference(entity_id, child.name),
                pose_parent_from_joint=_pose_from_transform(imported_joint.frame_a),
                pose_child_from_joint=_pose_from_transform(imported_joint.frame_b),
                kind=kind,
                axis=(
                    tuple(float(value) for value in imported_joint.axis)
                    if kind in {"revolute", "prismatic"}
                    else None
                ),
                position_representation=position,
                velocity_representation=velocity,
                position_size=position_size,
                velocity_size=velocity_size,
            )
        )
        source_joint_names.add(source_name)
        joint_child_frames.add(child.frame_id)

    # GeoPhys correctly preserves the fixed hand body as a frame, not a
    # synthetic source joint. The canonical articulation needs that fixed edge
    # so its two finger joints remain connected to the Panda root.
    root_body = next(body for body in imported.ir.bodies if body.name == "link0")
    for body in imported.ir.bodies:
        if body is root_body or body.frame_id in joint_child_frames:
            continue
        source_frame = frames_by_id[body.frame_id]
        parent_body = bodies_by_frame.get(source_frame.parent_id)
        if parent_body is None:
            raise AssertionError(f"unmapped fixed Panda frame: {body.name}")
        fixed_id = f"{body.name}_fixed_mount"
        joints.append(
            JointDefinition(
                schema_version="joint-definition-v1",
                joint_id=fixed_id,
                parent_frame=FrameReference(entity_id, parent_body.name),
                child_frame=FrameReference(entity_id, body.name),
                pose_parent_from_joint=_pose_from_transform(source_frame.local_transform),
                pose_child_from_joint=PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
                kind="fixed",
                axis=None,
                position_representation="none",
                velocity_representation="none",
                position_size=0,
                velocity_size=0,
            )
        )
    articulation = ArticulationDefinition(
        schema_version="articulation-definition-v1",
        entity_id=entity_id,
        root_frame_id="link0",
        link_frame_ids=tuple(body.name for body in imported.ir.bodies),
        joints=tuple(joints),
    )
    actuator_names = tuple(
        sorted(str(actuator.parameters.get("source_name")) for actuator in imported.ir.actuators)
    )
    actuator_resources = tuple(
        ActuatorResourceDefinition(
            schema_version="actuator-resource-v1",
            entity_id=entity_id,
            actuator_id=name,
        )
        for name in actuator_names
    )
    actuator_references = tuple(ActuatorReference(entity_id, name) for name in actuator_names)
    scene = SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id="a04-panda-import",
        assets=(asset,),
        entities=(
            EntityInstance(
                schema_version="entity-instance-v1",
                entity_id=entity_id,
                asset_id=asset.asset_id,
                asset_version=asset.asset_version,
            ),
        ),
        frames=frame_definitions,
        articulations=(articulation,),
        robots=(
            RobotInstance(
                schema_version="robot-instance-v1",
                entity_id=entity_id,
                articulation_roots=(FrameReference(entity_id, "link0"),),
            ),
        ),
        actuator_resources=actuator_resources,
        control_groups=(
            ControlGroup(
                schema_version="control-group-v1",
                entity_id=entity_id,
                group_id="arm",
                actuator_refs=tuple(
                    ActuatorReference(entity_id, f"actuator{index}")
                    for index in range(1, 8)
                ),
            ),
            ControlGroup(
                schema_version="control-group-v1",
                entity_id=entity_id,
                group_id="gripper",
                actuator_refs=(ActuatorReference(entity_id, "actuator8"),),
            ),
        ),
    )
    scene.validate()
    scene_joint_ids = {joint.joint_id for joint in scene.articulations[0].joints}
    assert source_joint_names <= scene_joint_ids
    for reference in actuator_references:
        assert scene.resolve_actuator(reference) == ActuatorResourceDefinition(
            "actuator-resource-v1", entity_id, reference.actuator_id
        )
    return scene


def test_asset_manifest_additions_preserve_legacy_construction_and_normalize_generator_values():
    legacy = AssetManifest("legacy-object-v1", "task_object_mjcf", asset_version="v1")
    assert legacy.source_reference is None
    assert legacy.source_revision is None
    assert legacy.generator_parameters == ()
    defaulted = AssetManifest("legacy-default-v1", "inline_mjcf_scene")
    assert defaulted.asset_version == "stage0"
    assert defaulted.source_reference is None
    positional_legacy = AssetManifest(
        "legacy-positional-v1",
        "task_object_mjcf",
        (Path("/asset/object.xml"),),
        (Path("/asset"),),
        "v0",
    )
    assert positional_legacy.mjcf_sources == (Path("/asset/object.xml"),)
    assert positional_legacy.asset_roots == (Path("/asset"),)
    assert positional_legacy.asset_version == "v0"

    procedural = AssetManifest(
        "procedural-object-v1",
        "procedural_task_object",
        asset_version="shape-v1",
        source_reference="geochora-procedural://fixture/shape",
        source_revision="shape-v1",
        generator_id="fixture.shape",
        generator_version="1",
        generator_parameters={"width_m": 0.2, "shape": "box"},
    )
    assert procedural.generator_parameters == (("shape", "box"), ("width_m", 0.2))

    with pytest.raises(ValueError, match="requires source_reference"):
        AssetManifest("bad-revision-v1", "task_object_mjcf", source_revision="rev1")
    with pytest.raises(ValueError, match="declared together"):
        AssetManifest("bad-v1", "procedural_task_object", generator_id="fixture.shape")
    with pytest.raises(ValueError, match="finite"):
        AssetManifest(
            "bad-v1",
            "procedural_task_object",
            source_reference="geochora-procedural://fixture/bad",
            generator_id="fixture.shape",
            generator_version="1",
            generator_parameters={"width_m": float("nan")},
        )


def test_manifest_to_asset_definition_keeps_declaration_identity_separate_from_source_bytes():
    manifest = PandaAgent().asset_manifest()
    declaration = _asset_definition_from_manifest(manifest)
    assert declaration.asset_id == "panda-v1"
    assert declaration.source_reference == "mujoco-menagerie://franka_emika_panda/panda.xml"
    assert declaration.source_revision == MENAGERIE_REVISION
    assert declaration.source_content_sha256 is None

    equivalent = AssetManifest(
        owner_uid=manifest.owner_uid,
        asset_kind=manifest.asset_kind,
        mjcf_sources=(Path("/a/different/checkout/panda.xml"),),
        asset_roots=(Path("/a/different/checkout"),),
        asset_version=manifest.asset_version,
        source_reference=manifest.source_reference,
        source_revision=manifest.source_revision,
    )
    assert _asset_definition_from_manifest(equivalent).identity_hash == declaration.identity_hash
    revised = AssetManifest(
        owner_uid=manifest.owner_uid,
        asset_kind=manifest.asset_kind,
        asset_version=manifest.asset_version,
        source_reference=manifest.source_reference,
        source_revision="different-menagerie-revision",
    )
    assert _asset_definition_from_manifest(revised).identity_hash != declaration.identity_hash
    with pytest.raises(ValueError, match="stable source_reference"):
        _asset_definition_from_manifest(AssetManifest("missing-source", "task_object_mjcf"))


def test_source_closure_digest_is_checkout_independent_and_content_sensitive():
    first_root = {"panda.xml": b"<mujoco/>\n", "assets/link.obj": b"v 0 0 0\n"}
    second_root = {"panda.xml": b"<mujoco/>\n", "assets/link.obj": b"v 0 0 0\n"}
    assert _source_closure_digest(first_root) == _source_closure_digest(second_root)
    changed_dependency = {**second_root, "assets/link.obj": b"v 0 0 0\n# changed\n"}
    assert _source_closure_digest(changed_dependency) != _source_closure_digest(first_root)
    with pytest.raises(ValueError, match="root-relative"):
        _source_closure_digest({"/checkout/panda.xml": b"<mujoco/>"})
    with pytest.raises(ValueError, match="not canonical"):
        _source_closure_digest({"assets/../outside.obj": b"x"})
    with pytest.raises(TypeError, match="must be bytes"):
        _source_closure_digest({"panda.xml": "<mujoco/>"})


def test_panda_mjcf_public_import_uses_hashed_snapshot_and_maps_to_scene_v3(tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public scene importer is required")
    manifest = PandaAgent().asset_manifest()
    asset_root = _asset_root()
    source_path = manifest.mjcf_sources[0].resolve()
    assert source_path.is_file()
    gitlink_revision = subprocess.check_output(
        ["git", "-C", str(asset_root.parents[0]), "rev-parse", "HEAD"], text=True
    ).strip()
    assert gitlink_revision == manifest.source_revision == MENAGERIE_REVISION

    # First import discovers the public dependency closure. The evidence import
    # below consumes a copied, immutable-in-test snapshot and hashes those bytes.
    discovered = scene_module.import_scene_source(
        scene_module.SceneSource.mjcf_path(source_path), cache=False
    )
    original_files = _logical_files(discovered, asset_root)
    assert "panda.xml" in original_files
    assert len(original_files) == 68
    assert all(
        path == "panda.xml" or path.lower().endswith((".obj", ".stl"))
        for path in original_files
    )
    assert any(path.startswith("assets/") and path.endswith(".obj") for path in original_files)
    assert any(path.startswith("assets/") and path.endswith(".stl") for path in original_files)

    snapshot_root = _copy_snapshot(original_files, tmp_path / "checkout-a")
    staged_files = {
        path: (snapshot_root / Path(*path.split("/"))).read_bytes()
        for path in original_files
    }
    closure_manifest = _source_closure_manifest(staged_files)
    digest_before = _source_closure_digest(staged_files)
    assert [path for path in original_files if path.lower().endswith(".xml")] == ["panda.xml"]
    source_xml_inventory, raw_xml_locators = _source_xml_inventory(
        staged_files["panda.xml"], "panda.xml"
    )
    assert len({
        (row["source_locator"]["path"], row["source_locator"]["element_path"])
        for row in source_xml_inventory
    }) == len(source_xml_inventory)
    assert not any(
        row["element_tag"] in {"include", "texture"} for row in source_xml_inventory
    )
    _protect_snapshot(snapshot_root)
    try:
        imported = scene_module.import_scene_source(
            scene_module.SceneSource.mjcf_path(snapshot_root / "panda.xml"), cache=False
        )
        consumed_files = _logical_files(imported, snapshot_root)
    finally:
        _unprotect_snapshot(snapshot_root)
    assert set(consumed_files) == set(original_files)
    assert _source_closure_digest(consumed_files) == digest_before
    assert [entry["path"] for entry in closure_manifest] == sorted(original_files)
    assert sum(int(entry["size_bytes"]) for entry in closure_manifest) == sum(
        len(content) for content in staged_files.values()
    )
    assert len(imported.dependency_paths) == 68

    scene = _panda_scene_from_import(imported, manifest)
    body_by_name = {body.name: body for body in imported.ir.bodies}
    frame_by_id = {frame.node_id: frame for frame in imported.ir.frames}
    source_frames = {
        body.name: frame_by_id[body.frame_id]
        for body in imported.ir.bodies
    }
    joint_names = {
        str(joint.dynamics.get("source_name")): joint
        for joint in imported.ir.joints
    }
    actuator_names = {
        str(actuator.parameters.get("source_name")): actuator
        for actuator in imported.ir.actuators
    }
    mapping_rows = []
    for name, body in body_by_name.items():
        frame = source_frames[name]
        mapping_rows.append(
            {
                "source_locator": _stable_source_locator(body.source_ref, snapshot_root),
                "raw_source_locator": _raw_xml_locator(raw_xml_locators, "body", name),
                "imported_locator": {"body_id": body.body_id, "frame_id": frame.node_id},
                "canonical_reference": FrameReference(PANDA_ENTITY_ID, name).to_mapping(),
                "core_disposition": "CANONICAL_REPRESENTED",
            }
        )
    canonical_joint_ids = {joint.joint_id for joint in scene.articulations[0].joints}
    for name, joint in joint_names.items():
        assert name in canonical_joint_ids
        mapping_rows.append(
            {
                "source_locator": _stable_source_locator(joint.source_ref, snapshot_root),
                "raw_source_locator": _raw_xml_locator(raw_xml_locators, "joint", name),
                "imported_locator": {"joint_id": joint.joint_id},
                "canonical_reference": {"entity_id": PANDA_ENTITY_ID, "joint_id": name},
                "core_disposition": "CANONICAL_REPRESENTED",
            }
        )
    for name, actuator in actuator_names.items():
        reference = ActuatorReference(PANDA_ENTITY_ID, name)
        scene.resolve_actuator(reference)
        mapping_rows.append(
            {
                "source_locator": _stable_source_locator(actuator.source_ref, snapshot_root),
                "raw_source_locator": _raw_xml_locator_by_name(raw_xml_locators, name),
                "imported_locator": {"actuator_id": actuator.actuator_id},
                "canonical_reference": reference.to_mapping(),
                "core_disposition": "CANONICAL_REPRESENTED",
            }
        )
    for name, frame in source_frames.items():
        mapping_rows.append(
            {
                "source_locator": _stable_source_locator(frame.source_ref, snapshot_root),
                "raw_source_locator": _raw_xml_locator(raw_xml_locators, "body", name),
                "imported_locator": {"frame_id": frame.node_id},
                "canonical_reference": FrameReference(PANDA_ENTITY_ID, name).to_mapping(),
                "core_disposition": "CANONICAL_REPRESENTED",
            }
        )
        if name == "hand":
            mapping_rows.append(
                {
                    "source_locator": _stable_source_locator(frame.source_ref, snapshot_root),
                    "raw_source_locator": _raw_xml_locator(raw_xml_locators, "body", name),
                    "imported_locator": {"frame_id": frame.node_id},
                    "canonical_reference": {
                        "entity_id": PANDA_ENTITY_ID,
                        "joint_id": "hand_fixed_mount",
                    },
                    "mapping_relation": "source fixed frame to derived canonical fixed joint",
                    "core_disposition": "CANONICAL_REPRESENTED",
                }
            )
    canonical_frame_ids = {
        frame.frame_id for frame in scene.frames if frame.entity_id == PANDA_ENTITY_ID
    }
    assert {body.name for body in imported.ir.bodies} == canonical_frame_ids
    assert {name for name in joint_names} <= canonical_joint_ids
    assert set(actuator_names) == {resource.actuator_id for resource in scene.actuator_resources}
    source_xml_locator_set = {
        (row["source_locator"]["path"], row["source_locator"]["element_path"])
        for row in source_xml_inventory
    }
    for mapping_index, mapping_row in enumerate(mapping_rows):
        mapping_row["mapping_id"] = f"mapping-{mapping_index:03d}"
        raw_locator = mapping_row["raw_source_locator"]
        source_key = (raw_locator["path"], raw_locator["element_path"])
        assert source_key in source_xml_locator_set
        source_element = next(
            row for row in source_xml_inventory
            if (row["source_locator"]["path"], row["source_locator"]["element_path"])
            == source_key
        )
        source_element["mapping_ids"].append(mapping_row["mapping_id"])
    for source_element in source_xml_inventory:
        if source_element["mapping_ids"]:
            source_element["core_disposition"] = "CANONICAL_REPRESENTED"
    assert all(
        row["core_disposition"] in {"CANONICAL_REPRESENTED", "SOURCE_RETAINED"}
        for row in source_xml_inventory
    )

    # Provider capability statuses are evidence about GeoPhys only. The Core
    # disposition is classified independently and every provider entry appears.
    closure_paths = {str(entry["path"]) for entry in closure_manifest}
    dispositions = []
    for entry in imported.capability_report.entries:
        locator = _stable_source_locator(entry.source_ref, snapshot_root)
        core_disposition = _core_disposition(entry.semantic, locator["path"], closure_paths)
        dispositions.append(
            {
                "source_locator": locator,
                "semantic": entry.semantic,
                "provider_status": entry.status.value,
                "core_disposition": core_disposition,
            }
        )
    assert len(dispositions) == imported.capability_report.source_element_count
    assert all(row["source_locator"]["path"] and row["source_locator"]["element_path"] for row in dispositions)
    assert all(
        row["core_disposition"]
        in {"CANONICAL_REPRESENTED", "SOURCE_RETAINED", "APPROXIMATE", "UNSUPPORTED"}
        for row in dispositions
    )
    assert any(
        row["semantic"] == "extension.light" and row["core_disposition"] == "SOURCE_RETAINED"
        for row in dispositions
    )
    assert all(row["core_disposition"] for row in dispositions)

    provider_revision = subprocess.check_output(
        ["git", "-C", str(Path(scene_module.__file__).resolve().parents[2]), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    receipt = {
        "schema_version": "geochora.a04-asset-import-receipt-v1",
        "canonical_scene": scene.to_mapping(),
        "asset_definition": scene.assets[0].to_mapping(),
        "asset_declaration_identity": scene.assets[0].identity_hash,
        "canonical_scene_identity": scene.identity_hash,
        "source_reference": manifest.source_reference,
        "source_revision": manifest.source_revision,
        "source_closure_manifest": list(closure_manifest),
        "source_closure_digest": digest_before,
        "source_file_dispositions": [
            {"path": entry["path"], "core_disposition": "SOURCE_RETAINED"}
            for entry in closure_manifest
        ],
        "source_xml_inventory": source_xml_inventory,
        "source_xml_element_count": len(source_xml_inventory),
        "semantic_inventory_scope": (
            "GeoPhys public CapabilityReport.entries are provider semantic diagnostics; "
            "raw root XML nodes are independently enumerated structurally"
        ),
        "provider_import_identity": {
            "provider": "GeoPhys",
            "provider_revision": provider_revision,
            "importer": "scene.import_scene_source",
            "source_graph_hash": imported.source_graph_hash,
            "ir_semantic_hash": imported.ir_semantic_hash,
        },
        "mapping": mapping_rows,
        "semantic_dispositions": dispositions,
    }
    encoded_receipt = json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False)
    (tmp_path / "a04_panda_import_receipt.json").write_text(encoded_receipt + "\n", encoding="utf-8")
    assert len({
        receipt["asset_declaration_identity"],
        receipt["source_closure_digest"],
        receipt["provider_import_identity"]["source_graph_hash"],
    }) == 3

    # A changed root byte changes the content closure even when normalized IR
    # and the provider's semantic graph identity do not.
    root_xml = snapshot_root / "panda.xml"
    original_root_bytes = staged_files["panda.xml"]
    try:
        root_xml.write_bytes(original_root_bytes + b"\n")
        changed_import = scene_module.import_scene_source(
            scene_module.SceneSource.mjcf_path(root_xml), cache=False
        )
        changed_root_digest = _source_closure_digest(_logical_files(changed_import, snapshot_root))
    finally:
        root_xml.write_bytes(original_root_bytes)
    assert changed_root_digest != digest_before
    restored_snapshot = {
        path: (snapshot_root / Path(*path.split("/"))).read_bytes()
        for path in original_files
    }
    assert _source_closure_digest(restored_snapshot) == digest_before
    assert changed_import.source_graph_hash == imported.source_graph_hash
    assert changed_import.ir_semantic_hash == imported.ir_semantic_hash

    # A stable logical closure is independent of checkout root, while the
    # provider import identity remains importer-scoped and path-sensitive.
    same_root = _copy_snapshot(original_files, tmp_path / "checkout-c")
    same_import = scene_module.import_scene_source(
        scene_module.SceneSource.mjcf_path(same_root / "panda.xml"), cache=False
    )
    assert _source_closure_digest(_logical_files(same_import, same_root)) == digest_before
    assert same_import.source_graph_hash != imported.source_graph_hash
    assert same_import.ir_semantic_hash != imported.ir_semantic_hash

    dependency_root = _copy_snapshot(original_files, tmp_path / "checkout-dependency-change")
    mesh_path = next(path for path in original_files if path.endswith(".obj"))
    staged_mesh = dependency_root / Path(*mesh_path.split("/"))
    staged_mesh.write_bytes(staged_mesh.read_bytes() + b"\n# closure digest check\n")
    dependency_changed_import = scene_module.import_scene_source(
        scene_module.SceneSource.mjcf_path(dependency_root / "panda.xml"), cache=False
    )
    assert _source_closure_digest(_logical_files(dependency_changed_import, dependency_root)) != digest_before


def test_procedural_peg_manifest_maps_generator_content_through_public_importer(tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public scene importer is required")
    from task_env.objects.nut_assembly import (
        PEG_HALF_HEIGHT,
        SQUARE_PEG_HALF_WIDTH,
    )
    from task_env.tasks.nut_assembly.task import build_artifact, build_runtime_source

    manifest = SquarePegObject().asset_manifest()
    definition = _asset_definition_from_manifest(manifest)
    runtime_source, _ = build_runtime_source(build_artifact(), provider="geophys")
    generated_xml = runtime_source.scene_source.xml
    generated_root = ET.fromstring(generated_xml)
    generated_peg = generated_root.find(".//body[@name='peg1']")
    assert generated_peg is not None
    generated_peg_bytes = ET.tostring(generated_peg, encoding="utf-8")
    generated_content_sha256 = hashlib.sha256(generated_peg_bytes).hexdigest()
    assert manifest.generator_id == "task_env.assembly.nut_assembly.build_nut_assembly_model_xml"
    assert manifest.generator_version == manifest.asset_version == "nut-assembly-peg-v1"
    assert dict(manifest.generator_parameters) == {
        "shape": "square",
        "half_height_m": PEG_HALF_HEIGHT,
        "half_width_m": SQUARE_PEG_HALF_WIDTH,
    }

    # Import the exact generated body bytes in a minimal in-memory MJCF source;
    # the wrapper contains no external dependencies and introduces no parser.
    isolated_root = ET.Element("mujoco", {"model": "a04-square-peg"})
    worldbody = ET.SubElement(isolated_root, "worldbody")
    worldbody.append(ET.fromstring(generated_peg_bytes))
    imported_xml = ET.tostring(isolated_root, encoding="unicode")
    native_source = scene_module.SceneSource.mjcf_string(imported_xml, label="a04-square-peg")
    imported = scene_module.import_scene_source(native_source, cache=False)
    assert not imported.dependency_paths
    procedural_source_bytes = imported_xml.encode("utf-8")
    procedural_closure = {"square-peg.xml": procedural_source_bytes}
    digest = _source_closure_digest(procedural_closure)
    procedural_closure_manifest = _source_closure_manifest(procedural_closure)
    (tmp_path / "square-peg.xml").write_bytes(procedural_source_bytes)
    (tmp_path / "generated_peg_subtree.xml").write_bytes(generated_peg_bytes)
    source_xml_inventory, raw_xml_locators = _source_xml_inventory(
        procedural_source_bytes, "square-peg.xml"
    )
    assert len({
        (row["source_locator"]["path"], row["source_locator"]["element_path"])
        for row in source_xml_inventory
    }) == len(source_xml_inventory)

    body = next(body for body in imported.ir.bodies if body.name == "peg1")
    frame = next(frame for frame in imported.ir.frames if frame.node_id == body.frame_id)
    entity_id = "square-peg-instance"
    frame_ref = FrameReference(entity_id, "peg1")
    canonical_scene = SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id="a04-square-peg",
        assets=(definition,),
        entities=(
            EntityInstance(
                schema_version="entity-instance-v1",
                entity_id=entity_id,
                asset_id=definition.asset_id,
                asset_version=definition.asset_version,
            ),
        ),
        frames=(
            FrameDefinition(
                schema_version="frame-definition-v1",
                entity_id=entity_id,
                frame_id=body.name,
                frame_kind="runtime",
                parent=None,
                pose_parent=None,
            ),
        ),
        articulations=(),
        robots=(),
        actuator_resources=(),
        control_groups=(),
    )
    canonical_scene.validate()
    canonical_raw_locator = _raw_xml_locator(raw_xml_locators, "body", body.name)
    canonical_source_element = next(
        row for row in source_xml_inventory if row["source_locator"] == canonical_raw_locator
    )
    canonical_source_element["mapping_ids"].append("mapping-000")
    for source_element in source_xml_inventory:
        if source_element["mapping_ids"]:
            source_element["core_disposition"] = "CANONICAL_REPRESENTED"
    assert any(
        source_element["source_locator"] == canonical_raw_locator
        and source_element["core_disposition"] == "CANONICAL_REPRESENTED"
        for source_element in source_xml_inventory
    )
    assert all(
        row["core_disposition"] in {"CANONICAL_REPRESENTED", "SOURCE_RETAINED"}
        for row in source_xml_inventory
    )
    assert any(
        source_element["source_locator"] == canonical_raw_locator
        for source_element in source_xml_inventory
    )
    procedural_closure_paths = {"square-peg.xml"}
    semantic_dispositions = [
        {
            "source_locator": {
                "path": "square-peg.xml",
                "element_path": entry.source_ref.element_path,
                "format": entry.source_ref.format,
            },
            "semantic": entry.semantic,
            "provider_status": entry.status.value,
            "core_disposition": _core_disposition(
                entry.semantic, "square-peg.xml", procedural_closure_paths
            ),
        }
        for entry in imported.capability_report.entries
    ]
    assert len(semantic_dispositions) == imported.capability_report.source_element_count
    assert all(
        row["core_disposition"]
        in {"CANONICAL_REPRESENTED", "SOURCE_RETAINED", "APPROXIMATE", "UNSUPPORTED"}
        for row in semantic_dispositions
    )
    receipt = {
        "schema_version": "geochora.a04-asset-import-receipt-v1",
        "canonical_scene": canonical_scene.to_mapping(),
        "asset_definition": definition.to_mapping(),
        "asset_declaration_identity": definition.identity_hash,
        "canonical_scene_identity": canonical_scene.identity_hash,
        "source_reference": manifest.source_reference,
        "source_revision": manifest.source_revision,
        "source_closure_manifest": list(procedural_closure_manifest),
        "source_closure_digest": digest,
        "source_file_dispositions": [
            {"path": entry["path"], "core_disposition": "SOURCE_RETAINED"}
            for entry in procedural_closure_manifest
        ],
        "source_xml_inventory": source_xml_inventory,
        "source_xml_element_count": len(source_xml_inventory),
        "semantic_inventory_scope": (
            "GeoPhys public CapabilityReport.entries are provider semantic diagnostics; "
            "raw source XML nodes are independently enumerated structurally"
        ),
        "generator": {
            "id": manifest.generator_id,
            "version": manifest.generator_version,
            "parameters": dict(manifest.generator_parameters),
            "generated_content_sha256": generated_content_sha256,
            "generated_content_serialization": "ElementTree.tostring(peg body, encoding=utf-8)",
        },
        "provider_import_identity": {
            "provider": "GeoPhys",
            "provider_revision": subprocess.check_output(
                ["git", "-C", str(Path(scene_module.__file__).resolve().parents[2]), "rev-parse", "HEAD"],
                text=True,
            ).strip(),
            "importer": "scene.import_scene_source",
            "source_graph_hash": imported.source_graph_hash,
            "ir_semantic_hash": imported.ir_semantic_hash,
        },
        "mapping": [
            {
                "source_locator": {
                    "path": "square-peg.xml",
                    "element_path": body.source_ref.element_path,
                    "format": body.source_ref.format,
                },
                "raw_source_locator": canonical_raw_locator,
                "imported_locator": {"body_id": body.body_id, "frame_id": frame.node_id},
                "canonical_reference": frame_ref.to_mapping(),
                "core_disposition": "CANONICAL_REPRESENTED",
                "mapping_id": "mapping-000",
            },
        ],
        "semantic_dispositions": semantic_dispositions,
        "unsupported_or_absent": {"joints": [], "actuators": []},
    }
    assert definition.asset_id == "square-peg-v1"
    assert body.name in SquarePegObject().reference_spec().body_names
    encoded_receipt = json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False)
    (tmp_path / "a04_procedural_peg_receipt.json").write_text(encoded_receipt + "\n", encoding="utf-8")
    assert len({
        receipt["asset_declaration_identity"],
        receipt["source_closure_digest"],
        receipt["provider_import_identity"]["source_graph_hash"],
    }) == 3

    # Verify the same existing generator is still called by the old selected
    # construction path; this does not create a TaskEnv or execute a step.
    legacy_source, _ = build_runtime_source(build_artifact(), provider="mujoco")
    assert legacy_source.composition.object_uids == ("square-nut-v1", "square-peg-v1", "round-peg-v1")
    assert legacy_source.objects[1].asset_manifest() == manifest
    assert legacy_source.objects[1].reference_spec() == SquarePegObject().reference_spec()


def test_legacy_factory_uids_defaults_and_unknown_duplicate_rejections_remain(tmp_path):
    from task_env.environment.protocols import AgentComponent
    from task_env.tasks.nut_assembly.task import build_artifact, build_runtime_source

    artifact = build_artifact()
    selected_source, _ = build_runtime_source(artifact, provider="mujoco")
    agent = make_agent(selected_source.composition.agent_uids[0])
    peg = make_object("square-peg-v1")
    scene = make_scene(selected_source.composition.scene_uid)
    assert agent.uid == "panda-v1"
    assert peg.uid == "square-peg-v1"
    assert selected_source.composition.scene_uid == scene.uid == "tabletop-v1"
    assert agent.asset_manifest() == PandaAgent().asset_manifest()
    assert agent.reference_spec() == PandaAgent().reference_spec()
    assert agent.initial_state_spec() == PandaAgent().initial_state_spec()
    assert agent.reference_spec().joint_names == (
        "joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7",
        "finger_joint1", "finger_joint2",
    )
    assert agent.reference_spec().actuator_names == tuple(f"actuator{i}" for i in range(1, 9))
    assert agent.reference_spec().site_names == ("nutassembly_ee_site",)
    assert peg.asset_manifest() == SquarePegObject().asset_manifest()
    assert peg.reference_spec().body_names == ("peg1",)
    assert scene.asset_manifest().owner_uid == "tabletop-v1"
    assert scene.reference_spec().body_names == ("grasp_table",)

    for factory, uid in ((make_agent, "unknown-a04-agent"), (make_object, "unknown-a04-object"), (make_scene, "unknown-a04-scene")):
        with pytest.raises(KeyError, match="unknown"):
            factory(uid)

    registry = ComponentRegistry("agent", AgentComponent)
    registry.register("panda-v1", PandaAgent)
    with pytest.raises(KeyError, match="duplicate agent uid"):
        registry.register("panda-v1", PandaAgent)
    with pytest.raises(ValueError, match="duplicate"):
        TaskCompositionSpec("task-v1", "scene-v1", agent_uids=("panda-v1", "panda-v1"))

    legacy_receipt = {
        "schema_version": "geochora.a04-legacy-factory-receipt-v1",
        "component_uids": {
            "agent": agent.uid,
            "object": peg.uid,
            "scene": scene.uid,
            "selected_scene": selected_source.composition.scene_uid,
        },
        "panda_joint_names": list(agent.reference_spec().joint_names),
        "panda_body_names": list(agent.reference_spec().body_names),
        "panda_site_names": list(agent.reference_spec().site_names),
        "panda_actuator_names": list(agent.reference_spec().actuator_names),
        "task_artifact": artifact.to_mapping(),
        "task_artifact_identity": artifact.identity_hash,
        "panda_asset_version": agent.asset_manifest().asset_version,
        "peg_asset_version": peg.asset_manifest().asset_version,
        "scene_asset_version": scene.asset_manifest().asset_version,
        "peg_body_names": list(peg.reference_spec().body_names),
        "unknown_factories_fail_closed": True,
        "duplicate_registry_uid_fails_closed": True,
        "duplicate_composition_uid_fails_closed": True,
        "selected_route_provider": "mujoco",
        "selected_route_runtime_constructed": False,
    }
    (tmp_path / "a04_legacy_factory_receipt.json").write_text(
        json.dumps(legacy_receipt, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
