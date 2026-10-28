"""Static source admission and exact source closure for fixed Attachments."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import xml.etree.ElementTree as ET

from ..artifacts import (
    FixedAttachmentPlanV1, LogicalAssemblyV1, SceneDefinition, resolve_logical_assembly,
)
from ..assembly.assets import _source_closure_digest, _source_closure_manifest
from ..assembly.logical_source import project_logical_assembly_source
from ..assembly.source import TaskSceneSource


@dataclass(frozen=True)
class LoweredFixedAttachmentSourceV1:
    """Two separately verified source snapshots ready for MjSpec attachment."""

    parent_xml: str
    child_xml: str
    parent_assets: dict[str, bytes]
    child_assets: dict[str, bytes]
    source_closure_sha256: str
    closure_bytes: int
    closure_manifest: tuple[dict[str, object], ...]


def _native_names(root: ET.Element, tags: set[str]) -> set[str]:
    return {node.get("name") for tag in tags for node in root.iter(tag) if node.get("name")}


def _validate_source_declarations(root: ET.Element, entity_id: str, scene: SceneDefinition,
                                  source_sha256: str) -> None:
    """Check canonical kinematics against the pinned Panda source, without native IO.

    Hashing two internally consistent declarations does not establish that they
    describe the same source. This bounded reader covers the scalar, zero-anchor
    joints in the admitted Panda pair; it is not a general MJCF compiler.
    """
    entity = next(item for item in scene.entities if item.entity_id == entity_id)
    asset = next(item for item in scene.assets
                 if (item.asset_id, item.asset_version) == (entity.asset_id, entity.asset_version))
    if asset.source_content_sha256 != source_sha256:
        raise ValueError(f"fixed Attachment Asset content hash differs from source for {entity_id!r}")
    defaults = {}

    def collect_defaults(node, inherited):
        values = dict(inherited)
        joint = node.find("joint")
        if joint is not None:
            values.update(joint.attrib)
        if node.get("class"):
            defaults[node.get("class")] = values
        for child in node.findall("default"):
            collect_defaults(child, values)

    for node in root.findall("default"):
        collect_defaults(node, {})
    articulation = next(item for item in scene.articulations if item.entity_id == entity_id)
    expected = []

    def vector(text, fallback):
        return tuple(float(value) for value in text.split()) if text is not None else fallback

    def near(left, right):
        return len(left) == len(right) and all(abs(a - b) <= 1e-12 for a, b in zip(left, right))

    def walk(body, parent_name, inherited_class):
        childclass = body.get("childclass", inherited_class)
        position = vector(body.get("pos"), (0.0, 0.0, 0.0))
        quaternion = vector(body.get("quat"), (1.0, 0.0, 0.0, 0.0))
        norm = math.sqrt(sum(value * value for value in quaternion))
        quaternion = tuple(value / norm for value in quaternion)
        for node in body.findall("joint"):
            values = {**defaults.get(node.get("class", childclass), {}), **node.attrib}
            name = node.get("name")
            expected.append(name)
            declared = next((joint for joint in articulation.joints if joint.joint_id == name), None)
            axis = vector(values.get("axis"), (0.0, 0.0, 1.0))
            axis_norm = math.sqrt(sum(value * value for value in axis))
            axis = tuple(value / axis_norm for value in axis)
            kind = {"hinge": "revolute", "slide": "prismatic"}.get(values.get("type", "hinge"))
            if not near(vector(values.get("pos"), (0.0, 0.0, 0.0)), (0.0, 0.0, 0.0)):
                raise ValueError("fixed Attachment source requires the pinned zero-anchor joint recipe")
            if (declared is None or kind is None or declared.kind != kind
                    or declared.parent_frame.entity_id != entity_id
                    or declared.child_frame.entity_id != entity_id
                    or declared.parent_frame.frame_id != parent_name
                    or declared.child_frame.frame_id != body.get("name")
                    or declared.axis is None or not near(declared.axis, axis)):
                raise ValueError(f"fixed Attachment canonical Joint topology/type/axis differs from source: {entity_id}/{name}")
            parent_pose, child_pose = declared.pose_parent_from_joint, declared.pose_child_from_joint
            if (not near(parent_pose.position, position)
                    or not (near(parent_pose.quaternion_wxyz, quaternion)
                            or near(parent_pose.quaternion_wxyz, tuple(-v for v in quaternion)))
                    or not near(child_pose.position, (0.0, 0.0, 0.0))
                    or not (near(child_pose.quaternion_wxyz, (1.0, 0.0, 0.0, 0.0))
                            or near(child_pose.quaternion_wxyz, (-1.0, 0.0, 0.0, 0.0)))):
                raise ValueError(f"fixed Attachment canonical Joint pose differs from source: {entity_id}/{name}")
        for child in body.findall("body"):
            walk(child, body.get("name"), childclass)

    for body in root.findall("./worldbody/body"):
        walk(body, None, None)
    if tuple(expected) != tuple(joint.joint_id for joint in articulation.joints):
        raise ValueError("fixed Attachment canonical Joint order/coverage differs from source")


def validate_fixed_attachment_scene(
    plan: FixedAttachmentPlanV1,
    assembly: LogicalAssemblyV1,
    scene: SceneDefinition,
) -> dict[str, object]:
    """Resolve the real R01c closure and reject unmapped or extra owners."""
    if type(plan) is not FixedAttachmentPlanV1:
        raise TypeError("fixed Attachment validation requires FixedAttachmentPlanV1")
    if type(assembly) is not LogicalAssemblyV1 or type(scene) is not SceneDefinition:
        raise TypeError("fixed Attachment validation requires canonical Assembly and Scene values")
    resolved_projection = project_logical_assembly_source(assembly, scene, ())
    resolved = resolve_logical_assembly(assembly, scene, ())
    plan.validate_against(assembly, resolved, resolved_projection)
    if scene.schema_version != "scene-definition-v3":
        raise ValueError("fixed Attachment runtime plan requires Scene-definition-v3")
    if len(scene.entities) != 2 or len(scene.robots or ()) != 2 or len(scene.articulations or ()) != 2:
        raise ValueError("fixed Attachment slice requires two robot Entities and two articulations")
    robots = {robot.entity_id: robot for robot in scene.robots or ()}
    articulations = {item.entity_id: item for item in scene.articulations or ()}
    if set(robots) != {plan.parent_entity_id, plan.child_entity_id}:
        raise ValueError("fixed Attachment robot Entity set differs from its plan")
    if any(len(robot.articulation_roots) != 1 for robot in robots.values()):
        raise ValueError("fixed Attachment slice requires one declared root per Entity")
    for entity_id, expected_root in (
        (plan.parent_entity_id, plan.parent_root),
        (plan.child_entity_id, plan.child_root),
    ):
        articulation = articulations.get(entity_id)
        if articulation is None or articulation.root_frame_id != expected_root.frame_id:
            raise ValueError(f"fixed Attachment articulation root differs for {entity_id!r}")
        if robots[entity_id].articulation_roots != (expected_root,):
            raise ValueError(f"fixed Attachment RobotInstance root differs for {entity_id!r}")
    frames = {(frame.entity_id, frame.frame_id): frame for frame in scene.frames or ()}
    for reference in (plan.parent_root, plan.child_root, plan.parent_mount, plan.child_mount):
        if (reference.entity_id, reference.frame_id) not in frames:
            raise ValueError(f"fixed Attachment references missing Scene Frame: {reference}")
        if frames[(reference.entity_id, reference.frame_id)].frame_kind != "runtime":
            raise ValueError("fixed Attachment mount and root references must be runtime Frames")
    parent_mount_key = f"{plan.parent_mount.entity_id}/{plan.parent_mount.frame_id}"
    if parent_mount_key not in plan.native_site_names:
        raise ValueError("fixed Attachment parent mount Site has no native mapping")
    if set(plan.native_body_names) != {
        f"{frame.entity_id}/{frame.frame_id}"
        for frame in scene.frames or ()
        if frame.frame_kind == "runtime" and (frame.entity_id, frame.frame_id) != (
            plan.parent_mount.entity_id, plan.parent_mount.frame_id,
        )
    }:
        raise ValueError("fixed Attachment body mappings must cover each runtime body frame exactly")
    expected_sites = {
        f"{frame.entity_id}/{frame.frame_id}"
        for frame in scene.frames or ()
        if frame.frame_kind == "runtime" and (frame.entity_id, frame.frame_id) == (
            plan.parent_mount.entity_id, plan.parent_mount.frame_id,
        )
    }
    if set(plan.native_site_names) != expected_sites:
        raise ValueError("fixed Attachment Site mappings must cover the declared mount Site exactly")
    expected_joints = {
        f"{articulation.entity_id}/{joint.joint_id}"
        for articulation in scene.articulations or () for joint in articulation.joints
        if joint.kind != "fixed"
    }
    if set(plan.native_joint_names) != expected_joints:
        raise ValueError("fixed Attachment native Joint mappings must cover all scalar joints exactly")
    expected_actuators = {
        f"{item.entity_id}/{item.actuator_id}" for item in scene.actuator_resources or ()
    }
    if set(plan.native_actuator_names) != expected_actuators:
        raise ValueError("fixed Attachment native Actuator mappings must cover all resources exactly")
    if plan.native_tendon_names != {
        f"{plan.child_entity_id}/split": f"{plan.namespace_prefix}split",
    }:
        raise ValueError("fixed Attachment slice requires the exact Hand split tendon mapping")
    return {
        "resolved_logical_assembly": resolved,
        "source_projection": resolved_projection,
        "scene_identity_sha256": scene.identity_hash,
        "assembly_identity_sha256": assembly.identity_hash,
        "entity_ids": sorted(robots),
        "native_frame_count": len(plan.native_body_names) + len(plan.native_site_names),
        "native_joint_count": len(plan.native_joint_names),
        "native_actuator_count": len(plan.native_actuator_names),
        "native_tendon_count": len(plan.native_tendon_names),
    }


def lower_fixed_attachment_sources(
    *,
    parent_source: TaskSceneSource,
    source_by_entity: dict[str, TaskSceneSource],
    scene: SceneDefinition,
    plan: FixedAttachmentPlanV1,
    assembly: LogicalAssemblyV1,
) -> LoweredFixedAttachmentSourceV1:
    """Verify two exact MJCF source closures without parsing either natively."""
    validate_fixed_attachment_scene(plan, assembly, scene)
    expected_ids = {plan.parent_entity_id, plan.child_entity_id}
    if set(source_by_entity) != expected_ids:
        raise ValueError("fixed Attachment must provide exactly its two canonical Entity sources")
    if source_by_entity[plan.parent_entity_id] != parent_source:
        raise ValueError("fixed Attachment parent source differs from RuntimeSource.scene_source")
    parent = source_by_entity[plan.parent_entity_id]
    child = source_by_entity[plan.child_entity_id]
    if parent.source_id != f"scene-definition-v3:{scene.identity_hash}":
        raise ValueError("fixed Attachment parent source ID does not bind the exact Scene identity")
    if child.source_id != f"fixed-attachment-source-v1:{plan.child_entity_id}:{plan.child_source_sha256}":
        raise ValueError("fixed Attachment child source ID differs from the exact Entity source digest")
    from ..runtime.sessions.source import source_asset_bytes
    parent_bytes = parent.xml.encode("utf-8")
    child_bytes = child.xml.encode("utf-8")
    if (hashlib.sha256(parent_bytes).hexdigest() != plan.parent_source_sha256
            or hashlib.sha256(child_bytes).hexdigest() != plan.child_source_sha256):
        raise ValueError("fixed Attachment source XML SHA-256 differs from its immutable plan")
    parent_assets = source_asset_bytes(parent.base_dir, parent.xml)
    child_assets = source_asset_bytes(child.base_dir, child.xml)
    closure: dict[str, bytes] = {"parent/scene.xml": parent_bytes, "child/scene.xml": child_bytes}
    closure.update({f"parent/{name}": content for name, content in parent_assets.items()})
    closure.update({f"child/{name}": content for name, content in child_assets.items()})
    license_path = parent.base_dir.resolve() / "LICENSE"
    try:
        license_path.resolve().relative_to(parent.base_dir.resolve())
    except ValueError as exc:
        raise ValueError("fixed Attachment license path escapes the parent source root") from exc
    license_bytes = license_path.read_bytes()
    if hashlib.sha256(license_bytes).hexdigest() != plan.license_source_sha256:
        raise ValueError("fixed Attachment Menagerie license bytes differ from the immutable plan")
    closure["license/LICENSE"] = license_bytes
    closure_bytes = sum(map(len, closure.values()))
    if closure_bytes > 128 * 1024 * 1024:
        raise ValueError("fixed Attachment source closure exceeds the 128 MiB admission limit")
    measured = _source_closure_digest(closure)
    if measured != plan.source_closure_sha256:
        raise ValueError("fixed Attachment derived source closure digest mismatch")

    parent_root, child_root = ET.fromstring(parent.xml), ET.fromstring(child.xml)
    _validate_source_declarations(parent_root, plan.parent_entity_id, scene, plan.parent_source_sha256)
    _validate_source_declarations(child_root, plan.child_entity_id, scene, plan.child_source_sha256)
    for root, label, native_maps in (
        (parent_root, "parent", (
            ("body", plan.native_body_names, {k: v for k, v in plan.native_body_names.items()
                                               if k.startswith(plan.parent_entity_id + "/")}),
            ("site", plan.native_site_names, {k: v for k, v in plan.native_site_names.items()
                                               if k.startswith(plan.parent_entity_id + "/")}),
            ("joint", plan.native_joint_names, {k: v for k, v in plan.native_joint_names.items()
                                                 if k.startswith(plan.parent_entity_id + "/")}),
            ("actuator", plan.native_actuator_names, {k: v for k, v in plan.native_actuator_names.items()
                                                       if k.startswith(plan.parent_entity_id + "/")}),
        )),
        (child_root, "child", (
            ("body", plan.native_body_names, {k: v for k, v in plan.native_body_names.items()
                                               if k.startswith(plan.child_entity_id + "/")}),
            ("site", plan.native_site_names, {k: v for k, v in plan.native_site_names.items()
                                               if k.startswith(plan.child_entity_id + "/")}),
            ("joint", plan.native_joint_names, {k: v for k, v in plan.native_joint_names.items()
                                                 if k.startswith(plan.child_entity_id + "/")}),
            ("actuator", plan.native_actuator_names, {k: v for k, v in plan.native_actuator_names.items()
                                                       if k.startswith(plan.child_entity_id + "/")}),
        )),
    ):
        actual = _native_names(root, {"body", "site", "joint", "actuator", "fixed", "general"})
        for tag, _all, mappings in native_maps:
            for key, native_name in mappings.items():
                canonical_local = key.split("/", 1)[1]
                expected_native_name = (
                    plan.namespace_prefix + canonical_local
                    if label == "child" else canonical_local
                )
                if native_name != expected_native_name or canonical_local not in actual:
                    raise ValueError(f"fixed Attachment {label} {tag} mapping is absent or out of order: {key!r}")
    if not any(node.get("name") == plan.parent_mount_site_name for node in parent_root.iter("site")):
        raise ValueError("fixed Attachment parent mount Site is absent from the parent source")
    expected_child_mount_source_name = plan.child_mount_body_name.removeprefix(plan.namespace_prefix)
    if not any(node.get("name") == expected_child_mount_source_name for node in child_root.iter("body")):
        raise ValueError("fixed Attachment child mount Body is absent from the child source")
    if any(node.tag == "freejoint" or node.get("type") == "free" for node in child_root.iter("joint")):
        raise ValueError("fixed Attachment child source must not retain a free root")
    hand_tendon = child_root.find("./tendon/fixed[@name='split']")
    if hand_tendon is None:
        raise ValueError("fixed Attachment Hand source is missing its split tendon")
    if plan.native_tendon_names[f"{plan.child_entity_id}/split"] != f"{plan.namespace_prefix}split":
        raise ValueError("fixed Attachment Hand tendon native mapping differs from its namespace")
    wraps = [(item.get("joint"), item.get("coef")) for item in hand_tendon.findall("joint")]
    if wraps != [("finger_joint1", "0.5"), ("finger_joint2", "0.5")]:
        raise ValueError("fixed Attachment Hand split tendon order/coefficients differ from source")
    equalities = child_root.findall("./equality/joint")
    if len(equalities) != 1 or (
        equalities[0].get("joint1"), equalities[0].get("joint2")
    ) != ("finger_joint1", "finger_joint2"):
        raise ValueError("fixed Attachment Hand source must preserve its one finger equality")
    child_actuators = [node for node in child_root.findall("./actuator/*") if node.get("name")]
    if (len(child_actuators) != 1 or child_actuators[0].get("name") != "actuator8"
            or child_actuators[0].get("tendon") != "split"):
        raise ValueError("fixed Attachment Hand actuator must remain attached to its split tendon")
    return LoweredFixedAttachmentSourceV1(
        parent.xml, child.xml, parent_assets, child_assets, measured, closure_bytes,
        _source_closure_manifest(closure),
    )


__all__ = [
    "LoweredFixedAttachmentSourceV1",
    "lower_fixed_attachment_sources",
    "validate_fixed_attachment_scene",
]
