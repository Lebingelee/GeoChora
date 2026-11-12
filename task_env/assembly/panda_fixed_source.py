"""Pinned Panda arm/hand source declarations and fixed attachment recipe."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from ..artifacts import (
    ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition, AssetDefinition,
    ControlGroup, EntityInstance, FixedAttachmentPlanV1, FrameDefinition, FrameReference,
    JointDefinition, LogicalAssemblyEntityMemberV1, LogicalAssemblyScenePinV1,
    LogicalAssemblyV1, PoseWorld, RobotInstance, SceneDefinition,
)
from .assets import _source_closure_digest
from .fixed_attachment import validate_fixed_attachment_scene
from .logical_source import project_logical_assembly_source
from .source import TaskSceneSource


ARM_ENTITY = "panda-arm"
HAND_ENTITY = "panda-hand"
ASSEMBLY_ID = "panda-arm-hand-fixed"
ASSEMBLY_REVISION = "r03b-001"
SCENE_ID = "phase-ii-r03b-fixed-attachment"
MENAGERIE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
ARM_SHA256 = "e7090a5e2384b18a223ef532d98bf914f7f9a6b74dc8bc9f74c8291201074071"
HAND_SHA256 = "d2a6539d0fd7c55c75c14f11c78f04505ee33f31d93e6112e3ad7120e5ee786a"
LICENSE_SHA256 = "a6cba85bc92e0cff7a450b1d873c0eaa2e9fc96bf472df0247a26bec77bf3ff9"
PREFIX = "probe_hand_"
_IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _numbers(raw: str | None, width: int, default: tuple[float, ...]) -> tuple[float, ...]:
    if raw is None:
        return default
    values = tuple(float(item) for item in raw.split())
    if len(values) != width:
        raise ValueError(f"MJCF source vector must have {width} values")
    return values


def _body_records(xml: str):
    root = ET.fromstring(xml)
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise ValueError("fixed Attachment source has no worldbody")
    records = []

    def walk(body, parent_name=None):
        name = body.get("name")
        if not name:
            raise ValueError("fixed Attachment source requires a name for every represented body")
        records.append((name, parent_name, body))
        for child in body.findall("body"):
            walk(child, name)

    for body in worldbody.findall("body"):
        walk(body)
    return root, records


def _joint_definitions(entity_id: str, root: ET.Element, records) -> tuple[JointDefinition, ...]:
    definitions = []
    defaults = {
        "arm": {"axis": (0.0, 0.0, 1.0), "range": (-2.8973, 2.8973), "kind": "revolute"},
        "finger": {"axis": (0.0, 1.0, 0.0), "range": (0.0, 0.04), "kind": "prismatic"},
    }
    for _name, parent_name, body in records:
        for node in body.findall("joint"):
            joint_id = node.get("name")
            if not joint_id:
                raise ValueError("source joint lacks a stable canonical name")
            preset = defaults["finger"] if node.get("class") == "finger" else defaults["arm"]
            axis = _numbers(node.get("axis"), 3, preset["axis"])
            norm = sum(value * value for value in axis) ** 0.5
            axis = tuple(value / norm for value in axis)
            body_quaternion = _numbers(body.get("quat"), 4, (1.0, 0.0, 0.0, 0.0))
            quaternion_norm = sum(value * value for value in body_quaternion) ** 0.5
            body_quaternion = tuple(value / quaternion_norm for value in body_quaternion)
            child_pose = PoseWorld(
                _numbers(body.get("pos"), 3, (0.0, 0.0, 0.0)),
                body_quaternion,
            )
            parent_frame = FrameReference(entity_id, parent_name)
            child_frame = FrameReference(entity_id, body.get("name"))
            definitions.append(JointDefinition(
                "joint-definition-v1", joint_id, parent_frame, child_frame,
                child_pose, _IDENTITY, preset["kind"], axis,
                "radian" if preset["kind"] == "revolute" else "meter",
                "radian_per_second" if preset["kind"] == "revolute" else "meter_per_second",
                1, 1,
            ))
    return tuple(definitions)


def _entity_scene(xml: str, entity_id: str, asset_id: str, asset_version: str,
                  asset_source: str, is_hand: bool):
    root, records = _body_records(xml)
    frames = [FrameDefinition(
        "frame-definition-v1", entity_id, name, "runtime", None, None,
    ) for name, _parent, _body in records]
    if not is_hand:
        if not any(node.get("name") == "attachment_site" for node in root.iter("site")):
            raise ValueError("Arm source is missing its measured attachment_site")
        frames.append(FrameDefinition(
            "frame-definition-v1", entity_id, "attachment_site", "runtime", None, None,
        ))
    joints = _joint_definitions(entity_id, root, records)
    joint_names = tuple(item.joint_id for item in joints)
    asset = AssetDefinition(
        "asset-definition-v1", asset_id, asset_version, asset_source,
        MENAGERIE_REVISION, hashlib.sha256(xml.encode("utf-8")).hexdigest(), "Apache-2.0",
    )
    entity = EntityInstance("entity-instance-v1", entity_id, asset_id, asset_version)
    root_frame = "hand" if is_hand else "link0"
    articulation = ArticulationDefinition(
        "articulation-definition-v1", entity_id, root_frame,
        tuple(name for name, _parent, _body in records if name != "attachment"),
        joints,
    )
    actuators = tuple(
        node.get("name") for node in root.findall("actuator/*") if node.get("name")
    )
    return asset, entity, tuple(frames), articulation, actuators, records


def _scene_and_bindings(arm_path, hand_path, license_path):
    if (_sha(arm_path), _sha(hand_path), _sha(license_path)) != (ARM_SHA256, HAND_SHA256, LICENSE_SHA256):
        raise ValueError("fixed source bytes or Menagerie license differ from the frozen recipe")
    arm_xml, hand_xml = arm_path.read_text(), hand_path.read_text()
    asset_version = "menagerie-b846dd12"
    arm_asset, arm_entity, arm_frames, arm_articulation, arm_actuators, arm_records = _entity_scene(
        arm_xml, ARM_ENTITY, "panda-arm-nohand", asset_version,
        "menagerie:franka_emika_panda/panda_nohand.xml", False,
    )
    hand_asset, hand_entity, hand_frames, hand_articulation, hand_actuators, hand_records = _entity_scene(
        hand_xml, HAND_ENTITY, "panda-hand", asset_version,
        "menagerie:franka_emika_panda/hand.xml", True,
    )
    semantic_arm_actuators = tuple(f"actuator{i}" for i in range(1, 8))
    if arm_actuators != semantic_arm_actuators or hand_actuators != ("actuator8",):
        raise ValueError("fixed source actuator inventory/order differs from its pinned recipe")
    parent_root, child_root = FrameReference(ARM_ENTITY, "link0"), FrameReference(HAND_ENTITY, "hand")
    scene = SceneDefinition(
        "scene-definition-v3", SCENE_ID,
        (arm_asset, hand_asset), (arm_entity, hand_entity),
        arm_frames + hand_frames, (arm_articulation, hand_articulation),
        (
            RobotInstance("robot-instance-v1", ARM_ENTITY, (parent_root,)),
            RobotInstance("robot-instance-v1", HAND_ENTITY, (child_root,)),
        ),
        tuple(
            ActuatorResourceDefinition("actuator-resource-v1", entity_id, name)
            for entity_id, names in ((ARM_ENTITY, arm_actuators), (HAND_ENTITY, hand_actuators))
            for name in names
        ),
        (
            ControlGroup("control-group-v1", ARM_ENTITY, "arm-position",
                         tuple(ActuatorReference(ARM_ENTITY, name) for name in semantic_arm_actuators)),
            ControlGroup("control-group-v1", HAND_ENTITY, "hand-position",
                         (ActuatorReference(HAND_ENTITY, "actuator8"),)),
        ),
    )
    asset_by_entity = {ARM_ENTITY: arm_asset, HAND_ENTITY: hand_asset}
    assembly = LogicalAssemblyV1(
        "logical-assembly-v1", ASSEMBLY_ID,
        ASSEMBLY_REVISION,
        LogicalAssemblyScenePinV1(
            "logical-assembly-scene-pin-v1", scene.scene_id, scene.schema_version, scene.identity_hash,
        ),
        (
            LogicalAssemblyEntityMemberV1(
                "entity_member", ("arm",), ARM_ENTITY,
                arm_asset.asset_id, arm_asset.asset_version,
            ),
            LogicalAssemblyEntityMemberV1(
                "entity_member", ("hand",), HAND_ENTITY,
                hand_asset.asset_id, hand_asset.asset_version,
            ),
        ),
    )
    projection = project_logical_assembly_source(assembly, scene, ())
    return scene, assembly, projection, arm_xml, hand_xml, arm_records, hand_records, asset_by_entity


def _plan_and_source(scene, assembly, arm_xml, hand_xml, arm_records, hand_records, base_dir, license_path):
    parent_root, child_root = FrameReference(ARM_ENTITY, "link0"), FrameReference(HAND_ENTITY, "hand")
    parent_mount, child_mount = FrameReference(ARM_ENTITY, "attachment_site"), child_root
    body_names = {}
    for name, _parent, _body in arm_records:
        body_names[f"{ARM_ENTITY}/{name}"] = name
    for name, _parent, _body in hand_records:
        body_names[f"{HAND_ENTITY}/{name}"] = PREFIX + name
    site_names = {f"{ARM_ENTITY}/attachment_site": "attachment_site"}
    joint_names = {
        f"{ARM_ENTITY}/joint{index}": f"joint{index}" for index in range(1, 8)
    }
    joint_names.update({
        f"{HAND_ENTITY}/finger_joint{index}": f"{PREFIX}finger_joint{index}"
        for index in (1, 2)
    })
    actuator_names = {
        f"{ARM_ENTITY}/actuator{index}": f"actuator{index}" for index in range(1, 8)
    }
    actuator_names[f"{HAND_ENTITY}/actuator8"] = f"{PREFIX}actuator8"
    tendon_names = {f"{HAND_ENTITY}/split": f"{PREFIX}split"}
    files = {
        "parent/scene.xml": arm_xml.encode("utf-8"),
        "child/scene.xml": hand_xml.encode("utf-8"),
    }
    from ..runtime.sessions.source import source_asset_bytes
    arm_assets = source_asset_bytes(base_dir, arm_xml)
    hand_assets = source_asset_bytes(base_dir, hand_xml)
    files.update({f"parent/{path}": content for path, content in arm_assets.items()})
    files.update({f"child/{path}": content for path, content in hand_assets.items()})
    files["license/LICENSE"] = license_path.read_bytes()
    closure_sha = _source_closure_digest(files)
    asset_by_id = {asset.asset_id: asset for asset in scene.assets}
    parent_asset = asset_by_id["panda-arm-nohand"]
    child_asset = asset_by_id["panda-hand"]
    plan = FixedAttachmentPlanV1(
        "fixed-attachment-plan-v1", ASSEMBLY_ID, assembly.revision,
        assembly.logical_content_sha256, assembly.scene_pin,
        ARM_ENTITY, HAND_ENTITY, parent_asset.asset_id, parent_asset.asset_version,
        child_asset.asset_id, child_asset.asset_version,
        parent_asset.source_content_sha256, child_asset.source_content_sha256,
        LICENSE_SHA256, closure_sha,
        parent_root, child_root, parent_mount, child_mount,
        "attachment_site", PREFIX + "hand",
        PoseWorld((0.0, 0.0, 0.0), (0.9238795391929064, 0.0, 0.0, 0.38268341623423263)),
        PoseWorld((0.0, 0.0, 0.0), (0.38268341623423263, 0.0, 0.0, -0.9238795391929064)),
        PREFIX, "fixed_child_root_under_parent_mount_no_free_joint", "source_preserved", 0.076, (),
        body_names, site_names, joint_names, actuator_names, tendon_names,
    )
    source_id = f"scene-definition-v3:{scene.identity_hash}"
    parent_source = TaskSceneSource(arm_xml, base_dir, source_id)
    child_source = TaskSceneSource(
        hand_xml, base_dir,
        f"fixed-attachment-source-v1:{HAND_ENTITY}:{plan.child_source_sha256}",
    )
    return plan, parent_source, {ARM_ENTITY: parent_source, HAND_ENTITY: child_source}, arm_assets, hand_assets


@dataclass(frozen=True)
class PandaFixedSourceDeclarationV1:
    """Pinned two-source Panda assembly, before task and native construction."""
    scene: SceneDefinition
    assembly: LogicalAssemblyV1
    projection: object
    attachment_plan: FixedAttachmentPlanV1
    source_by_entity: object
    parent_source: TaskSceneSource
    assets_by_entity: object


def declare_panda_fixed_source(manifest) -> PandaFixedSourceDeclarationV1:
    """Resolve the selected Robot's declared MJCF sources into one fixed assembly."""
    from ..environment.types import AssetManifest
    if (type(manifest) is not AssetManifest or manifest.asset_kind != 'agent_mjcf'
            or len(manifest.mjcf_sources) != 2 or len(manifest.asset_roots) != 1
            or manifest.source_revision != MENAGERIE_REVISION):
        raise ValueError('fixed Robot source requires its declared two-source MJCF manifest')
    base_dir = manifest.asset_roots[0].resolve()
    arm_path, hand_path = (path.resolve() for path in manifest.mjcf_sources)
    if any(not path.is_relative_to(base_dir) for path in (arm_path, hand_path)):
        raise ValueError('Robot source paths must belong to the declared asset root')
    license_path = base_dir / 'LICENSE'
    scene, assembly, projection, arm_xml, hand_xml, arm_records, hand_records, assets = _scene_and_bindings(
        arm_path, hand_path, license_path)
    plan, parent_source, sources, _arm_assets, _hand_assets = _plan_and_source(
        scene, assembly, arm_xml, hand_xml, arm_records, hand_records, base_dir, license_path)
    validate_fixed_attachment_scene(plan, assembly, scene)
    return PandaFixedSourceDeclarationV1(scene, assembly, projection, plan, sources, parent_source, assets)
