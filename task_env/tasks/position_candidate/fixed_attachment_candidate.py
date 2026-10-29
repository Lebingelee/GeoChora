"""Task-owned R03b two-source Panda Arm + fixed Hand candidate."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from ...artifacts import (
    ActionIntent, ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityDefinition, EntityInstance, FixedAttachmentPlanV1,
    FrameDefinition, FrameReference, InitializationContract, JointDefinition, JointReference,
    LogicalAssemblyEntityMemberV1, LogicalAssemblyScenePinV1, LogicalAssemblyV1, PoseWorld,
    RequiredCapabilitySet, RobotInstance, SceneDefinition, SemanticDefinition, TaskArtifact,
    Timebase, WorldDefinition,
)
from ...artifacts.execution import EpisodeResetPlanV1, ResetSample, RoleBindingV1
from ...assembly.assets import _source_closure_digest
from ...assembly.fixed_attachment import (
    R06B_ORDER_ASSET_VERSION, R06B_ORDER_RECIPE_ID, R06B_ORDER_SOURCE_REFERENCES,
    derive_r06b_order_sources, lower_fixed_attachment_sources, validate_fixed_attachment_scene,
)
from ...assembly.logical_source import project_logical_assembly_source
from ...assembly.source import TaskSceneSource
from ...environment import (
    TaskCompositionSpec, TaskInitializationV1, TaskRoleDeclarationV1, TaskSourceV1,
    compile_task_artifact_v1,
)
from ...environment.configuration import resolve_env_config
from ...runtime.sessions.source import RuntimeSource


ARM_ENTITY = "panda-arm"
HAND_ENTITY = "panda-hand"
ASSEMBLY_ID = "panda-arm-hand-fixed"
ASSEMBLY_REVISION = "r03b-001"
SCENE_ID = "phase-ii-r03b-fixed-attachment"
TASK_ID = "phase-ii-r03b-fixed-arm-hand"
R06B_TASK_ID = "phase-ii-r06b-order-v1-fixed-arm-hand"
TASK_VERSION = "candidate-v1"
MENAGERIE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
MENAGERIE_ROOT = Path(__file__).resolve().parents[3] / "asset/external/mujoco_menagerie/franka_emika_panda"
ARM_XML = MENAGERIE_ROOT / "panda_nohand.xml"
HAND_XML = MENAGERIE_ROOT / "hand.xml"
LICENSE = MENAGERIE_ROOT / "LICENSE"
ARM_SHA256 = "e7090a5e2384b18a223ef532d98bf914f7f9a6b74dc8bc9f74c8291201074071"
HAND_SHA256 = "d2a6539d0fd7c55c75c14f11c78f04505ee33f31d93e6112e3ad7120e5ee786a"
LICENSE_SHA256 = "a6cba85bc92e0cff7a450b1d873c0eaa2e9fc96bf472df0247a26bec77bf3ff9"
PREFIX = "probe_hand_"
_IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
_ARM_HOME = (0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853)


@dataclass(frozen=True)
class FixedAttachmentCandidate:
    scene: SceneDefinition
    assembly: LogicalAssemblyV1
    projection: object
    attachment_plan: FixedAttachmentPlanV1
    artifact: object
    task_source: TaskSourceV1
    runtime_source: RuntimeSource
    reset_plan: EpisodeResetPlanV1
    source_inventory: dict[str, object]
    source_artifact: object


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


def _scene_and_bindings(*, order_variant: bool = False):
    if (_sha(ARM_XML), _sha(HAND_XML), _sha(LICENSE)) != (ARM_SHA256, HAND_SHA256, LICENSE_SHA256):
        raise ValueError("R03b fixed source bytes or Menagerie license differ from the frozen recipe")
    arm_xml, hand_xml = ARM_XML.read_text(), HAND_XML.read_text()
    if order_variant:
        arm_xml, hand_xml = derive_r06b_order_sources(arm_xml, hand_xml)
    asset_version = R06B_ORDER_ASSET_VERSION if order_variant else "menagerie-b846dd12"
    scene_id = "phase-ii-r06b-order-v1-fixed-attachment" if order_variant else SCENE_ID
    arm_asset, arm_entity, arm_frames, arm_articulation, arm_actuators, arm_records = _entity_scene(
        arm_xml, ARM_ENTITY, "panda-arm-nohand", asset_version,
        (R06B_ORDER_SOURCE_REFERENCES[ARM_ENTITY] if order_variant
         else "menagerie:franka_emika_panda/panda_nohand.xml"), False,
    )
    hand_asset, hand_entity, hand_frames, hand_articulation, hand_actuators, hand_records = _entity_scene(
        hand_xml, HAND_ENTITY, "panda-hand", asset_version,
        (R06B_ORDER_SOURCE_REFERENCES[HAND_ENTITY] if order_variant
         else "menagerie:franka_emika_panda/hand.xml"), True,
    )
    semantic_arm_actuators = tuple(f"actuator{i}" for i in range(1, 8))
    expected_arm_source_order = tuple(reversed(semantic_arm_actuators)) if order_variant else semantic_arm_actuators
    if arm_actuators != expected_arm_source_order or hand_actuators != ("actuator8",):
        raise ValueError("fixed source actuator inventory/order differs from its pinned recipe")
    parent_root, child_root = FrameReference(ARM_ENTITY, "link0"), FrameReference(HAND_ENTITY, "hand")
    scene = SceneDefinition(
        "scene-definition-v3", scene_id,
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
        (R06B_ORDER_RECIPE_ID if order_variant else ASSEMBLY_REVISION),
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


def _plan_and_source(scene, assembly, arm_xml, hand_xml, arm_records, hand_records):
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
    from ...runtime.sessions.source import source_asset_bytes
    arm_assets = source_asset_bytes(MENAGERIE_ROOT, arm_xml)
    hand_assets = source_asset_bytes(MENAGERIE_ROOT, hand_xml)
    files.update({f"parent/{path}": content for path, content in arm_assets.items()})
    files.update({f"child/{path}": content for path, content in hand_assets.items()})
    files["license/LICENSE"] = LICENSE.read_bytes()
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
    parent_source = TaskSceneSource(arm_xml, MENAGERIE_ROOT, source_id)
    child_source = TaskSceneSource(
        hand_xml, MENAGERIE_ROOT,
        f"fixed-attachment-source-v1:{HAND_ENTITY}:{plan.child_source_sha256}",
    )
    return plan, parent_source, {ARM_ENTITY: parent_source, HAND_ENTITY: child_source}, arm_assets, hand_assets


def build_fixed_attachment_candidate(*, order_variant: bool = False) -> FixedAttachmentCandidate:
    """Build the exact source-only candidate through Core Artifact/Assembly owners."""
    if type(order_variant) is not bool:
        raise TypeError("fixed Attachment source recipe selector must be a bool")
    scene, assembly, projection, arm_xml, hand_xml, arm_records, hand_records, assets = _scene_and_bindings(
        order_variant=order_variant,
    )
    plan, parent_source, sources, _arm_assets, _hand_assets = _plan_and_source(
        scene, assembly, arm_xml, hand_xml, arm_records, hand_records,
    )
    scene_elems = {entity.entity_id: entity for entity in scene.entities}
    assets_by_identity = {
        (asset.asset_id, asset.asset_version): asset for asset in assets.values()
    }
    frames_by_entity = {ARM_ENTITY: [], HAND_ENTITY: []}
    for frame in scene.frames or ():
        frames_by_entity[frame.entity_id].append(f"{frame.entity_id}/{frame.frame_id}")
    joints_by_entity = {ARM_ENTITY: [], HAND_ENTITY: []}
    for articulation in scene.articulations or ():
        for joint in articulation.joints:
            joints_by_entity[articulation.entity_id].append(
                f"{articulation.entity_id}/{joint.joint_id}"
            )
    state_joints = {
        f"{ARM_ENTITY}/joint{index}": _ARM_HOME[index - 1] for index in range(1, 8)
    }
    state_joints.update({f"{HAND_ENTITY}/finger_joint{index}": 0.038 for index in (1, 2)})
    task_id = R06B_TASK_ID if order_variant else TASK_ID
    reset_id = "r06b-order-v1-fixed-reset" if order_variant else "r03b-fixed-reset"
    world_entities = tuple(
        EntityDefinition(
            entity_id, "embodiment",
            f"{assets_by_identity[(entity.asset_id, entity.asset_version)].source_reference}@{entity.asset_version}",
            tuple(sorted(frames_by_entity[entity_id])), tuple(sorted(joints_by_entity[entity_id])),
            "source_asset", "source_preserved", {},
        )
        for entity_id, entity in sorted(scene_elems.items())
    )
    required_poses = tuple(sorted(name for names in frames_by_entity.values() for name in names))
    legacy = TaskArtifact(
        "task-artifact-v0", f"{task_id}-v0", task_id, TASK_VERSION,
        WorldDefinition(
            "world-v0", "SI_right_handed_z_up_wxyz", world_entities,
            ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            ("canonical-state-v0",), (),
        ),
        InitializationContract(
            "initialization-v0", {}, state_joints, (),
            "zero_named_joint_and_entity_velocities", reset_id, 0,
        ),
        SemanticDefinition(
            "semantics-v0", ("r06b_order_fixed_attachment_oracle" if order_variant
                              else "r03b_fixed_attachment_oracle"), required_poses,
            tuple(sorted(state_joints)), {}, "fixed_attachment_motion_only",
        ),
        Timebase(0.002, 5, 0.01),
        RequiredCapabilitySet((
            "articulated_robot", "body_pose_query", "frame_pose_query",
            "joint_position_actuation", "joint_state_query",
        )),
    )
    task_source = TaskSourceV1(
        task_id, TASK_VERSION, scene.scene_id,
        (
            TaskRoleDeclarationV1("arm", "robot", "ids", (ARM_ENTITY,), "exactly_one"),
            TaskRoleDeclarationV1("hand", "robot", "ids", (HAND_ENTITY,), "exactly_one"),
        ),
        TaskInitializationV1(
            reset_id, "frozen-authored-v0", "training",
            "zero_named_joint_and_entity_velocities", "arm_targets_at_initial_joints_gripper_open",
        ),
    )
    frame_bindings = {
        name: FrameReference(*name.split("/", 1)) for name in required_poses
    }
    joint_bindings = {
        name: JointReference(*name.split("/", 1)) for name in state_joints
    }
    artifact = compile_task_artifact_v1(
        task_source, scene, legacy, frame_bindings=frame_bindings,
        joint_bindings=joint_bindings,
    )
    runtime_config = resolve_env_config(
        task_uid=task_id, scene_uid=scene.scene_id,
        runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 5, "prewarm": False},
        render={"camera_obs": False},
    )
    runtime_source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=parent_source,
        joints=plan.native_joint_names,
        bodies=plan.native_body_names,
        frames=plan.native_site_names,
        free_joints={},
        joint_targets={
            f"{ARM_ENTITY}/joint{index}": plan.native_actuator_names[f"{ARM_ENTITY}/actuator{index}"]
            for index in range(1, 8)
        },
        open_actuators=(plan.native_actuator_names[f"{HAND_ENTITY}/actuator8"],),
        composition=TaskCompositionSpec(task_id, scene.scene_id),
        config=runtime_config, scene=scene, agents=(), objects=(),
        scene_definition=scene, source_closure_digest=plan.source_closure_sha256,
        fixed_attachment_plan=plan, fixed_attachment_assembly=assembly,
        fixed_attachment_sources=sources,
    )
    # The candidate itself uses the real R01c parser/projector, then checks the
    # exact two-source closure before a native session can be materialized.
    validate_fixed_attachment_scene(plan, assembly, scene)
    lowered = lower_fixed_attachment_sources(
        parent_source=parent_source, source_by_entity=sources, scene=scene,
        plan=plan, assembly=assembly,
    )
    role_binding = RoleBindingV1(
        "role-binding-v1", task_source.identity_hash, scene.identity_hash, 31,
        ("r06b-order-v1-fixed-role-selection" if order_variant else "r03b-fixed-role-selection"),
        "v1", {"arm": ARM_ENTITY, "hand": HAND_ENTITY},
    )
    sample = ResetSample.create(
        schema_version="reset-sample-v0", task_artifact_hash=artifact.identity_hash,
        sampler_id=reset_id, sampler_version="v1", task_seed=31,
        joint_position=state_joints, poses_world={},
        velocity_policy="zero_named_joint_and_entity_velocities",
        control_policy="arm_targets_at_initial_joints_gripper_open", settle_steps=0,
    )
    reset_plan = EpisodeResetPlanV1("episode-reset-plan-v1", role_binding, sample, "training")
    inventory = {
        "recipe_id": (R06B_ORDER_RECIPE_ID if order_variant else "menagerie-pinned-exact"),
        "arm": {"path": str(ARM_XML), "sha256": plan.parent_source_sha256,
                "bytes": len(arm_xml.encode("utf-8")),
                "base_sha256": ARM_SHA256},
        "hand": {"path": str(HAND_XML), "sha256": plan.child_source_sha256,
                 "bytes": len(hand_xml.encode("utf-8")),
                 "base_sha256": HAND_SHA256},
        "license": {"path": str(LICENSE), "sha256": LICENSE_SHA256, "bytes": LICENSE.stat().st_size},
        "derived_source_closure_sha256": lowered.source_closure_sha256,
        "derived_source_closure_bytes": lowered.closure_bytes,
        "derived_source_closure_file_count": len(lowered.closure_manifest),
        "derived_source_closure_files": list(lowered.closure_manifest),
        "projected_entity_ids": [entry.entity.entity_id for entry in projection.entities],
        "logical_assembly_identity_sha256": projection.root_logical_content_sha256,
        "source_projection_identity_sha256": projection.identity_sha256,
    }
    return FixedAttachmentCandidate(
        scene, assembly, projection, plan, artifact, task_source,
        runtime_source, reset_plan, inventory, legacy,
    )


__all__ = ["FixedAttachmentCandidate", "build_fixed_attachment_candidate"]
