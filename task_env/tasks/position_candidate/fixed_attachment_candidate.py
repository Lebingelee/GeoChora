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


# Source parsing and attachment identity are owned by the shared source adapter.
from ...assembly.panda_fixed_source import (
    _sha, _numbers, _body_records, _joint_definitions, _entity_scene,
    _scene_and_bindings, _plan_and_source, declare_panda_fixed_source,
)


def build_fixed_attachment_candidate(*, order_variant: bool = False) -> FixedAttachmentCandidate:
    """Build the exact source-only candidate through Core Artifact/Assembly owners."""
    if type(order_variant) is not bool:
        raise TypeError("fixed Attachment source recipe selector must be a bool")
    declaration = declare_panda_fixed_source(order_variant=order_variant)
    scene, assembly, projection = declaration.scene, declaration.assembly, declaration.projection
    plan, parent_source, sources, assets = (declaration.attachment_plan, declaration.parent_source,
                                            declaration.source_by_entity, declaration.assets_by_entity)
    arm_xml, hand_xml = sources[ARM_ENTITY].xml, sources[HAND_ENTITY].xml
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
