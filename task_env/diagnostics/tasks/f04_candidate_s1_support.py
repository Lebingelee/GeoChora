"""F04 candidate construction and public action helpers for provider-free S1."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from task_env.artifacts import (
    ArticulationDefinition, AssetDefinition, ExecutionSpecV1, FrameDefinition,
    FrameReference, JointDefinition, PoseWorld, RendererSelectionV1, Timebase,
)
from task_env.assembly.source import UsdTaskSceneSourceV1
from task_env.assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation
from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
from task_env.runtime.sessions.api import _validate_f04_isaac_position_source
from task_env.runtime.sessions.source import UsdRuntimeSourceV1
from task_env.tasks.position_candidate.builder import (
    F04PositionCandidateInputV1, build_versioned_position_candidate,
)
from task_env.tasks.position_candidate.source import _a05_scene, _artifact_and_sample, _task_source


REPO = Path(__file__).resolve().parents[3]
BASE = REPO / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
ASSETS = BASE / "f04_003/assets"
MENAGERIE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"


def _execution():
    return ExecutionSpecV1(
        "execution-spec-v1", "isaacsim", "cuda", "isaac-gpu-physx-f04-position-v1",
        31, "best_effort", RendererSelectionV1(
            "renderer-selection-v1", "none", "cpu", "none", None,
        ), "cuda:0", (),
    )


def _kinematics_source(family, delivery_root):
    if family == "official-panda":
        calibration_root = BASE / "f04_003/evidence/kinematics"
        xml_path = calibration_root / "official-panda-derived.xml"
        receipt_path = calibration_root / "official-panda-derived.json"
        source_usd = delivery_root / "derived/panda.usda"
        xml_bytes = xml_path.read_bytes()
        receipt = json.loads(receipt_path.read_text())
        source_sha = hashlib.sha256(source_usd.read_bytes()).hexdigest()
        xml_sha = hashlib.sha256(xml_bytes).hexdigest()
        if (receipt.get("schema_version") != "f04-official-usd-kinematics-derivation-v1"
                or receipt.get("source_usd_sha256") != source_sha
                or receipt.get("source_usd") != str(source_usd.resolve())
                or receipt.get("output_xml_sha256") != xml_sha
                or receipt.get("provenance") != "local source-derived kinematics calibration; not upstream validation"):
            raise ValueError("official Panda FK calibration is not bound to the selected official USD bytes")
        return xml_bytes.decode("utf-8"), xml_sha
    if family != "menagerie-panda":
        raise ValueError(f"unknown F04 source family: {family}")
    source_xml = REPO / "asset/external/mujoco_menagerie/franka_emika_panda/panda.xml"
    xml_bytes = source_xml.read_bytes()
    return xml_bytes.decode("utf-8"), hashlib.sha256(xml_bytes).hexdigest()


def build_candidate(family):
    """Build the frozen F04 data contract through current Core public owners."""
    family_dirs = {
        "official-panda": "local_official_panda_r009",
        "menagerie-panda": "local_menagerie_panda_r009",
    }
    if family not in family_dirs:
        raise ValueError(f"unknown F04 source family: {family}")
    delivery_path = ASSETS / family_dirs[family] / "usd_delivery.json"
    loaded = load_usd_asset_delivery(delivery_path)
    kinematics_xml, kinematics_sha256 = _kinematics_source(family, delivery_path.parent)
    representation = resolve_provider_representation(
        loaded, provider="isaacsim", provider_build_identity="isaacsim-6.2.0.0",
    )
    base = _a05_scene()
    panda = loaded.delivery.asset_definition
    cube = AssetDefinition(
        "asset-definition-v1", "f04-free-cube", "r009",
        "geochora-procedural://f04-003/free-cube", "f04-003-physx-task-scene-recipe",
        loaded.delivery.recipe_sha256, "local-task-fixture",
    )
    assets = []
    for asset in base.assets:
        if asset.asset_id == "panda-v1":
            assets.append(panda)
        elif asset.asset_id == "square-peg-v1":
            assets.append(cube)
        else:
            raise ValueError(f"unexpected base scene asset: {asset.asset_id}")
    entities = tuple(
        replace(item, asset_id=panda.asset_id, asset_version=panda.asset_version)
        if item.entity_id == "panda-main" else
        replace(item, asset_id=cube.asset_id, asset_version=cube.asset_version)
        if item.entity_id == "square-peg-instance" else item
        for item in base.entities
    )
    frames = (*base.frames,
              FrameDefinition("frame-definition-v1", "square-peg-instance", "anchor", "runtime", None, None))
    floating = JointDefinition(
        "joint-definition-v1", "floating_root",
        FrameReference("square-peg-instance", "anchor"),
        FrameReference("square-peg-instance", "peg1"),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        "floating", None, "xyz_meter_quaternion_wxyz",
        "linear_xyz_meter_per_second_angular_xyz_radian_per_second", 7, 6,
    )
    scene = replace(
        base, scene_id=f"f04-attempt003-{family}-panda-free-cube-v1",
        assets=tuple(assets), entities=entities, frames=tuple(frames),
        articulations=(*base.articulations, ArticulationDefinition(
            "articulation-definition-v1", "square-peg-instance", "anchor",
            ("anchor", "peg1"), (floating,),
        )),
    )
    legacy, _sample = _artifact_and_sample(scene)
    scalar_names = tuple(sorted(
        f"{articulation.entity_id}/{joint.joint_id}"
        for articulation in scene.articulations for joint in articulation.joints
        if joint.kind in {"revolute", "continuous", "prismatic"}
    ))
    scalar_name_set = set(scalar_names)
    world_entities = tuple(
        replace(
            entity,
            kind="movable" if entity.semantic_id == "square-peg-instance" else entity.kind,
            joints=tuple(name for name in entity.joints if name in scalar_name_set),
        )
        for entity in legacy.world.entities
    )
    recipe_path = delivery_path.parent / loaded.delivery.recipe_path
    recipe_bytes = recipe_path.read_bytes()
    if hashlib.sha256(recipe_bytes).hexdigest() != loaded.delivery.recipe_sha256:
        raise ValueError("F04 task-scene recipe bytes do not match the loaded delivery identity")
    task_scene = json.loads(recipe_bytes).get("task_scene", {})
    body, support = task_scene.get("free_body"), task_scene.get("support")
    if not isinstance(body, dict) or not isinstance(support, dict):
        raise ValueError("F04 local recipe must bind both the free body and its support")
    center = tuple(float(value) for value in body.get("center_m", ()))
    support_center = tuple(float(value) for value in support.get("center_m", ()))
    support_scale = tuple(float(value) for value in support.get("scale_m", ()))
    edge = float(body.get("edge_m", 0.0))
    if (len(center) != 3 or len(support_center) != 3 or len(support_scale) != 3
            or edge <= 0.0 or not body.get("rigid_body") or not body.get("collision")
            or not support.get("collision")
            or abs(center[0] - support_center[0]) > support_scale[0] / 2.0 - edge / 2.0
            or abs(center[1] - support_center[1]) > support_scale[1] / 2.0 - edge / 2.0
            or center[2] <= support_center[2] + support_scale[2] / 2.0 + edge / 2.0):
        raise ValueError("F04 reset drop path is not vertically aligned over the frozen support recipe")
    reset_joints = {
        "panda-main/joint1": 0.012, "panda-main/joint2": -0.568,
        "panda-main/joint3": 0.0, "panda-main/joint4": -2.811,
        "panda-main/joint5": 0.0, "panda-main/joint6": 3.037,
        "panda-main/joint7": 0.741,
        "panda-main/finger_joint1": 0.03999999910593033,
        "panda-main/finger_joint2": 0.03999999910593033,
    }
    legacy = replace(
        legacy, artifact_id=f"f04-attempt003-{family}-position-v1",
        task_id=f"f04-attempt003-{family}-position", artifact_version="candidate-v1",
        world=replace(legacy.world, entities=world_entities),
        initialization=replace(
            legacy.initialization,
            poses_world={"square-peg-instance/peg1": PoseWorld(center, (1.0, 0.0, 0.0, 0.0))},
            joint_position=reset_joints,
        ),
        semantics=replace(legacy.semantics, required_joints=scalar_names),
        timebase=Timebase(0.002, 5, 0.01),
    )
    task_source = replace(_task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version)
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=31)
    task_scene_source = UsdTaskSceneSourceV1(
        "usd-task-scene-source-v1", loaded, representation,
        task_source.identity_hash, scene.identity_hash,
    )
    if family == "official-panda":
        body_paths = {
            **{f"panda-main/link{i}": f"/panda/panda_link{i}" for i in range(8)},
            "panda-main/hand": "/panda/panda_hand",
            "panda-main/left_finger": "/panda/panda_leftfinger",
            "panda-main/right_finger": "/panda/panda_rightfinger",
        }
        family_dofs = {
            **{f"panda-main/joint{i}": f"panda_joint{i}" for i in range(1, 8)},
            "panda-main/finger_joint1": "panda_finger_joint1",
            "panda-main/finger_joint2": "panda_finger_joint2",
        }
    else:
        path = "/panda/Geometry"
        body_paths = {}
        for index in range(8):
            path = f"{path}/link{index}"
            body_paths[f"panda-main/link{index}"] = path
        hand = f"{path}/hand"
        body_paths.update({
            "panda-main/hand": hand,
            "panda-main/left_finger": f"{hand}/left_finger",
            "panda-main/right_finger": f"{hand}/right_finger",
        })
        family_dofs = {
            **{f"panda-main/joint{i}": f"joint{i}" for i in range(1, 8)},
            "panda-main/finger_joint1": "finger_joint1",
            "panda-main/finger_joint2": "finger_joint2",
        }
    body_paths.update({
        "square-peg-instance/peg1": "/F04Scene/free_cube",
        "square-peg-instance/anchor": "/F04Scene/free_cube",
    })
    runtime_source = UsdRuntimeSourceV1(
        "usd-runtime-source-v1", artifact, scene, task_scene_source,
        family_dofs, body_paths, {},
        {"square-peg-instance/peg1": "/F04Scene/free_cube/rootJoint"},
        family_dofs,
    )
    candidate = F04PositionCandidateInputV1(
        "f04-position-candidate-input-v1", task_source, artifact, runtime_source,
        _execution(), reset_plan, kinematics_xml, kinematics_sha256,
    )
    candidate.validate()
    _validate_f04_isaac_position_source(artifact, candidate.execution, runtime_source)
    build_versioned_position_candidate(candidate, horizon=200)
    return candidate


def _native_order(source):
    values = tuple(source.joint_targets.values())
    if len(values) != 9 or len(set(values)) != 9:
        raise ValueError("S1 metadata order requires exactly nine source-bound native DOFs")
    order = (7, 3, 8, 0, 6, 2, 5, 1, 4)
    return tuple(values[index] for index in order)


def _limits(source):
    canonical = {
        "panda-main/joint1": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/joint2": (-1.7627999782562256, 1.7627999782562256),
        "panda-main/joint3": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/joint4": (-3.0717999935150146, -0.0697999969124794),
        "panda-main/joint5": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/joint6": (-0.017500000074505806, 3.752500057220459),
        "panda-main/joint7": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/finger_joint1": (0.0, 0.03999999910593033),
        "panda-main/finger_joint2": (0.0, 0.03999999910593033),
    }
    return {native: canonical[semantic] for semantic, native in source.joint_targets.items()}


def _home():
    return {
        "panda-main/joint1": 0.012,
        "panda-main/joint2": -0.568,
        "panda-main/joint3": 0.0,
        "panda-main/joint4": -2.811,
        "panda-main/joint5": 0.0,
        "panda-main/joint6": 3.037,
        "panda-main/joint7": 0.741,
        "panda-main/finger_joint1": 0.03999999910593033,
        "panda-main/finger_joint2": 0.03999999910593033,
    }


def _action_for(env, interval):
    from task_env.controllers.canonical.contracts import (
        ControlGroupActionV1, StructuredActionRequestV1,
    )

    current = {item.joint_id: float(item.position[0])
               for item in env.typed_state.view.joints if item.entity_id == "panda-main"}
    goal = [current[f"joint{i}"] for i in range(1, 8)]
    direction = 1.0 if interval in (0, 3) else -1.0
    goal[0] += direction * 0.045
    goal[1] -= direction * 0.025
    goal[3] += direction * 0.02
    pose = env.controller.model.pose(goal)
    schema = env.controller.controller_binding().action_schema
    return StructuredActionRequestV1(
        "structured-action-request-v1", env.position_plan.scene_identity_hash,
        env.position_plan.identity_hash,
        (
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "arm", schema.schema_id,
                (*pose.position, *pose.quaternion_wxyz),
            ),
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "gripper", schema.schema_id,
                (1.0 if interval in (0, 3) else 0.25,),
            ),
        ),
    )
