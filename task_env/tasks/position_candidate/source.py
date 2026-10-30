"""Fixed A05 Scene/source construction shared by the Position task and diagnostics.

Extracted without changing frozen identities or source bytes. Native scene import
is supplied by the construction caller; importing this module builds no runtime.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


from task_env.assembly.assets import (
    _asset_definition_from_manifest,
    _source_closure_digest,
)
from task_env.assembly.source import TaskSceneSource
from task_env.artifacts import (
    ActionIntent,
    EntityDefinition,
    InitializationContract,
    RequiredCapabilitySet,
    SceneDefinition,
    SemanticDefinition,
    TaskArtifact,
    Timebase,
    WorldDefinition,
    PoseWorld,
)
from task_env.artifacts.execution import ResetSample
from task_env.environment import (
    ReferenceSpec,
    TaskCompositionSpec,
    TaskInitializationV1,
    TaskRoleDeclarationV1,
    TaskSourceV1,
)
from task_env.environment.configuration import resolve_env_config
from task_env.objects.nut_assembly import SquarePegObject
from task_env.robots.panda import PandaAgent
from task_env.runtime.sessions.geophys_source import (
    project_scene_definition_v3_to_mjcf,
    source_closure_digest_for_import,
)
from task_env.runtime.sessions.source import RuntimeSource

FIXTURE_ROOT = Path(__file__).with_name("assets")
MENAGERIE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
EXPECTED_SCENE_IDENTITY = "047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e"
EXPECTED_PANDA_CLOSURE = "a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a"
EXPECTED_PEG_CLOSURE = "6fadf3986265a56bbedc99e1546a566641928e612d8839ea94cafaa6f15b19ff"
F05_DG01_SCENE_ID = "f05-dg01-menagerie-panda-cube-support"
F05_DG01_TASK_ID = "phase-ii-f05-dg01-panda-cube"
F05_DG01_TASK_VERSION = "candidate-v1"
F05_DG01_RECIPE = FIXTURE_ROOT / "f05_dg01_task_scene_recipe.json"
F05_DG01_RECIPE_SHA256 = "6a705816e619681e948a1b243e0588dd1db2f667ecfb085bd2e55b1c3fd8b89d"
F05_DG01_R009_RECIPE_SHA256 = "3af9f3da9c8b186d8568eb8dc0e82ccba65e020c4d853cca50da8bbc8cd6dede"


class _MicroprobeScene:
    """Compatibility view consumed by the existing assembly reference resolver."""

    uid = "phase-ii-d01a-microprobe"

    def reference_spec(self):
        return ReferenceSpec(geom_names=("square_peg_collision", "square_peg_visual"))


def _a05_scene() -> SceneDefinition:
    mapping = json.loads((FIXTURE_ROOT / "a05_scene_definition_v3.json").read_text())
    scene = SceneDefinition.from_mapping(mapping)
    if scene.schema_version != "scene-definition-v3" or scene.identity_hash != EXPECTED_SCENE_IDENTITY:
        raise ValueError("Position candidate Scene identity mismatch")
    return scene


def _artifact_and_sample(scene: SceneDefinition) -> tuple[TaskArtifact, ResetSample]:
    entity_by_id = {entity.entity_id: entity for entity in scene.entities}
    asset_by_identity = {(asset.asset_id, asset.asset_version): asset for asset in scene.assets}
    robot_entities = {robot.entity_id for robot in scene.robots or ()}
    frames_by_entity: dict[str, list[str]] = {entity_id: [] for entity_id in entity_by_id}
    for frame in scene.frames or ():
        frames_by_entity[frame.entity_id].append(f"{frame.entity_id}/{frame.frame_id}")
    joints_by_entity: dict[str, list[str]] = {entity_id: [] for entity_id in entity_by_id}
    state_joints = {}
    for articulation in scene.articulations or ():
        for joint in articulation.joints:
            semantic_name = f"{articulation.entity_id}/{joint.joint_id}"
            joints_by_entity[articulation.entity_id].append(semantic_name)
            if joint.kind in {"revolute", "continuous", "prismatic"}:
                state_joints[semantic_name] = 0.0
    arm_joint = "panda-main/joint1"
    state_joints[arm_joint] = 0.35

    world_entities = []
    for entity_id, instance in sorted(entity_by_id.items()):
        asset = asset_by_identity[(instance.asset_id, instance.asset_version)]
        world_entities.append(EntityDefinition(
            semantic_id=entity_id,
            kind="embodiment" if entity_id in robot_entities else "static",
            asset_reference=f"{asset.source_reference}@{asset.asset_version}",
            frames=tuple(sorted(frames_by_entity[entity_id])),
            joints=tuple(sorted(joints_by_entity[entity_id])),
            geometry="source_asset",
            collision_intent="source_retained",
            parameters_si={},
        ))
    frame_names = tuple(sorted(name for names in frames_by_entity.values() for name in names))
    joint_names = tuple(sorted(state_joints))
    artifact = TaskArtifact(
        schema_version="task-artifact-v0",
        artifact_id="phase-ii-d01a-a05-scene-microprobe-v0",
        task_id="phase-ii-d01a-microprobe",
        artifact_version="candidate-v0",
        world=WorldDefinition(
            schema_version="world-v0",
            convention="SI_right_handed_z_up_wxyz",
            entities=tuple(world_entities),
            action=ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            observation_requirements=("canonical-state-v0",),
            randomization_dimensions=(),
        ),
        initialization=InitializationContract(
            schema_version="initialization-v0",
            poses_world={},
            joint_position=state_joints,
            randomization=(),
            inherited_state_policy="zero_named_joint_and_entity_velocities",
            reset_validity="fixed-d01a-microprobe-sample",
            settle_steps=0,
        ),
        semantics=SemanticDefinition(
            schema_version="semantics-v0",
            evaluator="d01a_materialization_probe",
            required_poses=frame_names,
            required_joints=joint_names,
            parameters_si={},
            success_definition="d01a-materialization-only",
        ),
        timebase=Timebase(0.002, 1, 0.002),
        required_capabilities=RequiredCapabilitySet((
            "rigid_body", "articulated_robot", "joint_position_actuation",
            "joint_state_query", "body_pose_query", "frame_pose_query",
        )),
    )
    sample = ResetSample.create(
        schema_version="reset-sample-v0",
        task_artifact_hash=artifact.identity_hash,
        sampler_id="d01a-fixed-reset-sample",
        sampler_version="v1",
        task_seed=31,
        joint_position=state_joints,
        poses_world={},
        velocity_policy="zero_named_joint_and_entity_velocities",
        control_policy="arm_targets_at_initial_joints_gripper_open",
        settle_steps=0,
    )
    return artifact, sample


def _f05_dg01_task_scene_recipe() -> dict:
    raw = F05_DG01_RECIPE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != F05_DG01_RECIPE_SHA256:
        raise ValueError("F05 DG01 task-scene recipe byte identity mismatch")
    recipe = json.loads(raw)
    if (recipe.get("schema_version") != "f05-dg01-task-scene-recipe-v1"
            or recipe.get("recipe_id") != F05_DG01_SCENE_ID
            or recipe.get("source", {}).get("r009_recipe_sha256") != F05_DG01_R009_RECIPE_SHA256):
        raise ValueError("F05 DG01 task-scene recipe identity mismatch")
    return recipe


def _f05_dg01_scene() -> SceneDefinition:
    """Compose the distinct cube/support Scene while retaining the exact Panda declaration."""
    recipe_bytes = F05_DG01_RECIPE.read_bytes()
    recipe = _f05_dg01_task_scene_recipe()
    recipe_digest = hashlib.sha256(recipe_bytes).hexdigest()
    mapping = _a05_scene().to_mapping()
    mapping["scene_id"] = F05_DG01_SCENE_ID
    mapping["assets"] = [
        asset for asset in mapping["assets"] if asset["asset_id"] != "square-peg-v1"
    ] + [
        {
            "schema_version": "asset-definition-v1",
            "asset_id": "f05-dg01-free-cube-v1",
            "asset_version": "r009-task-scene-recipe-v1",
            "license_id": None,
            "source_content_sha256": recipe_digest,
            "source_reference": "geochora-task-scene://f05-dg01/free-cube",
            "source_revision": F05_DG01_R009_RECIPE_SHA256,
        },
        {
            "schema_version": "asset-definition-v1",
            "asset_id": "f05-dg01-support-v1",
            "asset_version": "r009-task-scene-recipe-v1",
            "license_id": None,
            "source_content_sha256": recipe_digest,
            "source_reference": "geochora-task-scene://f05-dg01/support",
            "source_revision": F05_DG01_R009_RECIPE_SHA256,
        },
    ]
    mapping["entities"] = [
        entity for entity in mapping["entities"]
        if entity["entity_id"] != "square-peg-instance"
    ] + [
        {
            "schema_version": "entity-instance-v1",
            "entity_id": "free-cube",
            "asset_id": "f05-dg01-free-cube-v1",
            "asset_version": "r009-task-scene-recipe-v1",
        },
        {
            "schema_version": "entity-instance-v1",
            "entity_id": "support",
            "asset_id": "f05-dg01-support-v1",
            "asset_version": "r009-task-scene-recipe-v1",
        },
    ]
    mapping["frames"] = [
        frame for frame in mapping["frames"]
        if frame["entity_id"] != "square-peg-instance"
    ] + [
        {
            "schema_version": "frame-definition-v1",
            "entity_id": "free-cube",
            "frame_id": "world",
            "frame_kind": "runtime",
            "parent": None,
            "pose_parent": None,
        },
        {
            "schema_version": "frame-definition-v1",
            "entity_id": "free-cube",
            "frame_id": "free_cube",
            "frame_kind": "runtime",
            "parent": None,
            "pose_parent": None,
        },
        {
            "schema_version": "frame-definition-v1",
            "entity_id": "support",
            "frame_id": "support",
            "frame_kind": "runtime",
            "parent": None,
            "pose_parent": None,
        },
    ]
    identity_pose = {
        "position": [0.0, 0.0, 0.0],
        "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
    }
    mapping["articulations"] = [*mapping["articulations"], {
        "schema_version": "articulation-definition-v1",
        "entity_id": "free-cube",
        "root_frame_id": "world",
        "link_frame_ids": ["world", "free_cube"],
        "joints": [{
            "schema_version": "joint-definition-v1",
            "joint_id": "cube_freejoint",
            "parent_frame": {"entity_id": "free-cube", "frame_id": "world"},
            "child_frame": {"entity_id": "free-cube", "frame_id": "free_cube"},
            "pose_parent_from_joint": identity_pose,
            "pose_child_from_joint": identity_pose,
            "kind": "floating",
            "axis": None,
            "position_representation": "xyz_meter_quaternion_wxyz",
            "velocity_representation": "linear_xyz_meter_per_second_angular_xyz_radian_per_second",
            "position_size": 7,
            "velocity_size": 6,
        }],
    }]
    scene = SceneDefinition.from_mapping(mapping)
    if (scene.schema_version != "scene-definition-v3"
            or len(scene.robots or ()) != 1
            or scene.resolve_robot("panda-main") != _a05_scene().resolve_robot("panda-main")):
        raise ValueError("F05 DG01 Scene changed the original Panda robot declaration")
    cube = recipe["free_cube"]
    support = recipe["support"]
    if (
        (cube["entity_id"], cube["frame_id"], cube["joint_id"], cube["mass_kg"], cube["edge_m"])
        != ("free-cube", "free_cube", "cube_freejoint", 0.1, 0.06)
    ):
        raise ValueError("F05 DG01 cube recipe values mismatch")
    if (
        (support["entity_id"], support["frame_id"], support["center_m"], support["full_size_m"])
        != ("support", "support", [1.0, 0.5, 0.45], [0.35, 0.35, 0.05])
    ):
        raise ValueError("F05 DG01 support recipe values mismatch")
    return scene


def _f05_dg01_artifact_and_sample(scene: SceneDefinition) -> tuple[TaskArtifact, ResetSample]:
    recipe = _f05_dg01_task_scene_recipe()
    entity_by_id = {entity.entity_id: entity for entity in scene.entities}
    asset_by_identity = {(asset.asset_id, asset.asset_version): asset for asset in scene.assets}
    robot_entities = {robot.entity_id for robot in scene.robots or ()}
    frames_by_entity: dict[str, list[str]] = {entity_id: [] for entity_id in entity_by_id}
    for frame in scene.frames or ():
        frames_by_entity[frame.entity_id].append(f"{frame.entity_id}/{frame.frame_id}")
    joints_by_entity: dict[str, list[str]] = {entity_id: [] for entity_id in entity_by_id}
    state_joints = {}
    for articulation in scene.articulations or ():
        for joint in articulation.joints:
            semantic_name = f"{articulation.entity_id}/{joint.joint_id}"
            joints_by_entity[articulation.entity_id].append(semantic_name)
            if joint.kind in {"revolute", "continuous", "prismatic"}:
                state_joints[semantic_name] = 0.0
    home = recipe["reset_home_joint_position_rad"]
    state_joints = {f"panda-main/{name}": value for name, value in home.items()}
    asset_by_identity = {(asset.asset_id, asset.asset_version): asset for asset in scene.assets}
    world_entities = []
    for entity_id, instance in sorted(entity_by_id.items()):
        asset = asset_by_identity[(instance.asset_id, instance.asset_version)]
        if entity_id in robot_entities:
            kind = "embodiment"
        elif entity_id == "free-cube":
            kind = "movable"
        else:
            kind = "static"
        parameters = {}
        if entity_id == "free-cube":
            parameters = {"edge_m": 0.06, "mass_kg": 0.1}
        elif entity_id == "support":
            parameters = {"top_z_m": 0.475}
        world_entities.append(EntityDefinition(
            semantic_id=entity_id,
            kind=kind,
            asset_reference=f"{asset.source_reference}@{asset.asset_version}",
            frames=tuple(sorted(frames_by_entity[entity_id])),
            joints=tuple(sorted(joints_by_entity[entity_id])),
            geometry="source_asset" if entity_id == "panda-main" else "recipe_box",
            collision_intent="source_retained",
            parameters_si=parameters,
        ))
    scalar_joints = tuple(sorted(state_joints))
    pose = recipe["free_cube"]["reset_pose_world"]
    poses_world = {
        "free-cube/free_cube": PoseWorld(
            tuple(pose["position_m"]), tuple(pose["quaternion_wxyz"]),
        ),
    }
    artifact = TaskArtifact(
        schema_version="task-artifact-v0",
        artifact_id="f05-dg01-panda-cube-v1",
        task_id=F05_DG01_TASK_ID,
        artifact_version=F05_DG01_TASK_VERSION,
        world=WorldDefinition(
            schema_version="world-v0",
            convention="SI_right_handed_z_up_wxyz",
            entities=tuple(world_entities),
            action=ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            observation_requirements=("canonical-state-v0",),
            randomization_dimensions=(),
        ),
        initialization=InitializationContract(
            schema_version="initialization-v0",
            poses_world=poses_world,
            joint_position=state_joints,
            randomization=(),
            inherited_state_policy="zero_named_joint_and_entity_velocities",
            reset_validity="f05-dg01-original-home-and-r009-cube-pose-v1",
            settle_steps=0,
        ),
        semantics=SemanticDefinition(
            schema_version="semantics-v0",
            evaluator="f05_dg01_cube_lift_height_v1",
            required_poses=("free-cube/free_cube", "support/support"),
            required_joints=scalar_joints,
            parameters_si={
                "cube_rest_center_z_m": 0.505,
                "lift_height_m": 0.08,
                "lift_threshold_z_m": 0.585,
            },
            success_definition="free-cube-origin-z-at-or-above-0.585m-v1",
        ),
        timebase=Timebase(0.002, 5, 0.01),
        required_capabilities=RequiredCapabilitySet((
            "rigid_body", "free_body", "articulated_robot", "joint_position_actuation",
            "joint_state_query", "body_pose_query", "frame_pose_query",
        )),
    )
    sample = ResetSample.create(
        schema_version="reset-sample-v0",
        task_artifact_hash=artifact.identity_hash,
        sampler_id="f05-dg01-original-home-reset",
        sampler_version="frozen-authored-v0",
        task_seed=31,
        joint_position=state_joints,
        poses_world=poses_world,
        velocity_policy="zero_named_joint_and_entity_velocities",
        control_policy="arm_targets_at_initial_joints_gripper_open",
        settle_steps=0,
    )
    return artifact, sample


def _copy_panda_snapshot(
    scene_module, root: Path, scene_definition: SceneDefinition,
) -> tuple[Path, dict[str, bytes], str]:
    manifest = PandaAgent().asset_manifest()
    panda_asset = _asset_definition_from_manifest(manifest)
    scene_assets = {
        (asset.asset_id, asset.asset_version): asset
        for asset in scene_definition.assets
    }
    if scene_assets.get((panda_asset.asset_id, panda_asset.asset_version)) != panda_asset:
        raise ValueError("A05 Scene does not bind the current Panda asset declaration")
    source_path = manifest.mjcf_sources[0].resolve()
    asset_root = source_path.parent
    provider_menagerie_root = asset_root.parent
    revision = subprocess.check_output(
        ["git", "-C", str(provider_menagerie_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if not (revision == manifest.source_revision == MENAGERIE_REVISION):
        raise ValueError("Position candidate asset/source identity mismatch")

    discovered = scene_module.import_scene_source(
        scene_module.SceneSource.mjcf_path(source_path), cache=False,
    )
    files: dict[str, bytes] = {}
    for raw_path in discovered.dependency_paths:
        path = Path(raw_path).resolve()
        logical = path.relative_to(asset_root).as_posix()
        files[logical] = path.read_bytes()
    if not ("panda.xml" in files and len(files) == 68):
        raise ValueError("Position candidate asset/source identity mismatch")
    digest = _source_closure_digest(files)
    panda_receipt = json.loads((FIXTURE_ROOT / "panda_source_receipt.json").read_text())
    if not (digest == panda_receipt["source_closure_digest"] == EXPECTED_PANDA_CLOSURE):
        raise ValueError("Position candidate asset/source identity mismatch")

    root.mkdir(parents=True, exist_ok=True)
    for logical, content in files.items():
        destination = root / Path(*logical.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return root, files, digest


def _compose_scene_source(
    scene_definition: SceneDefinition,
    source_root: Path,
    *,
    physics_dt: float,
) -> str:
    panda_root = ET.parse(source_root / "panda.xml").getroot()
    option = panda_root.find("option")
    if option is None:
        option = ET.SubElement(panda_root, "option")
    option.set("timestep", format(float(physics_dt), ".17g"))
    worldbody = panda_root.find("worldbody")
    if worldbody is None:
        raise ValueError("Panda source has no worldbody")
    peg_manifest = SquarePegObject().asset_manifest()
    peg_asset = _asset_definition_from_manifest(peg_manifest)
    scene_assets = {(asset.asset_id, asset.asset_version): asset for asset in scene_definition.assets}
    if scene_assets.get((peg_asset.asset_id, peg_asset.asset_version)) != peg_asset:
        raise ValueError("A05 Scene does not bind the current square peg asset declaration")
    peg_receipt = json.loads((FIXTURE_ROOT / "square_peg_receipt.json").read_text())
    if not (peg_receipt["asset_declaration_identity"] == peg_asset.identity_hash):
        raise ValueError("Position candidate asset/source identity mismatch")
    if not (peg_receipt["source_closure_digest"] == EXPECTED_PEG_CLOSURE):
        raise ValueError("Position candidate asset/source identity mismatch")
    peg_xml_bytes = (FIXTURE_ROOT / "square_peg.xml").read_bytes()
    if not (_source_closure_digest({"square-peg.xml": peg_xml_bytes}) == EXPECTED_PEG_CLOSURE):
        raise ValueError("Position candidate asset/source identity mismatch")
    peg_root = ET.fromstring(peg_xml_bytes)
    peg_body = peg_root.find(".//body[@name='peg1']")
    if peg_body is None:
        raise ValueError("procedural square peg source has no peg1 body")
    worldbody.append(ET.fromstring(ET.tostring(peg_body, encoding="utf-8")))
    return ET.tostring(panda_root, encoding="unicode")


def _compose_f05_dg01_scene_source(
    scene_definition: SceneDefinition,
    source_root: Path,
    *,
    physics_dt: float,
) -> str:
    """Add only the frozen F05 cube/support task scene to the untouched Panda model."""
    recipe = _f05_dg01_task_scene_recipe()
    panda_root = ET.parse(source_root / "panda.xml").getroot()
    option = panda_root.find("option")
    if option is None:
        option = ET.SubElement(panda_root, "option")
    option.set("timestep", format(float(physics_dt), ".17g"))
    gravity = recipe["world"]["gravity_m_s2"]
    option.set("gravity", " ".join(format(float(value), ".17g") for value in gravity))
    worldbody = panda_root.find("worldbody")
    if worldbody is None:
        raise ValueError("Menagerie Panda source has no worldbody")

    support = recipe["support"]
    support_body = ET.Element(
        "body", {
            "name": support["frame_id"],
            "pos": " ".join(format(float(value), ".17g") for value in support["center_m"]),
        },
    )
    half_size = tuple(float(value) / 2.0 for value in support["full_size_m"])
    ET.SubElement(support_body, "geom", {
        "name": "support_geom",
        "type": "box",
        "size": " ".join(format(value, ".17g") for value in half_size),
        "contype": "1",
        "conaffinity": "1",
    })
    worldbody.append(support_body)

    cube = recipe["free_cube"]
    reset_pose = cube["reset_pose_world"]
    cube_body = ET.Element(
        "body", {
            "name": cube["frame_id"],
            "pos": " ".join(format(float(value), ".17g") for value in reset_pose["position_m"]),
            "quat": " ".join(format(float(value), ".17g") for value in reset_pose["quaternion_wxyz"]),
        },
    )
    ET.SubElement(cube_body, "freejoint", {"name": cube["joint_id"]})
    ET.SubElement(cube_body, "geom", {
        "name": "free_cube_geom",
        "type": "box",
        "size": " ".join(format(float(value), ".17g") for value in cube["half_extent_m"]),
        "mass": format(float(cube["mass_kg"]), ".17g"),
        "contype": "1",
        "conaffinity": "1",
    })
    worldbody.append(cube_body)

    # Ensure the composition retained the entire original source mechanism.
    if (len(list(panda_root.iter("actuator"))) != 1
            or len(panda_root.findall("./actuator/*")) != 8
            or len(panda_root.findall("./equality/*")) != 1
            or len(panda_root.findall("./tendon/*")) != 1
            or len(panda_root.findall("./tendon/fixed/*")) != 2):
        raise ValueError("F05 DG01 composition changed the source actuator/equality/tendon structure")
    if (scene_definition.scene_id != F05_DG01_SCENE_ID
            or len(scene_definition.robots or ()) != 1):
        raise ValueError("F05 DG01 composition requires its exact source/task Scene")
    return ET.tostring(panda_root, encoding="unicode")


def _f05_dg01_runtime_source(scene_module, scene_definition, source_root, source_xml, artifact):
    source_id = f"scene-definition-v3:{scene_definition.identity_hash}"
    task_scene_source = TaskSceneSource(source_xml, source_root, source_id)
    projected_xml = project_scene_definition_v3_to_mjcf(source_xml, scene_definition)
    native_source = scene_module.SceneSource.mjcf_string(
        projected_xml, base_dir=source_root, label=source_id,
    )
    imported = scene_module.import_scene_source(native_source, cache=False)
    source_digest = source_closure_digest_for_import(imported, task_scene_source, projected_xml)

    joints = {}
    free_joints = {}
    for articulation in scene_definition.articulations or ():
        for joint in articulation.joints:
            if joint.kind in {"revolute", "continuous", "prismatic"}:
                joints[f"{articulation.entity_id}/{joint.joint_id}"] = joint.joint_id
            elif joint.kind == "floating":
                free_joints[f"{joint.child_frame.entity_id}/{joint.child_frame.frame_id}"] = joint.joint_id
    bodies = {
        f"{frame.entity_id}/{frame.frame_id}": frame.frame_id
        for frame in scene_definition.frames or ()
        if frame.frame_kind == "runtime"
    }
    config = resolve_env_config(
        task_uid=F05_DG01_TASK_ID,
        scene_uid=F05_DG01_SCENE_ID,
        runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 5, "prewarm": False},
        render={"camera_obs": False},
    )
    runtime_source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=task_scene_source,
        joints=joints,
        bodies=bodies,
        frames={},
        free_joints=free_joints,
        joint_targets={f"panda-main/joint{i}": f"actuator{i}" for i in range(1, 8)},
        open_actuators=("actuator8",),
        composition=TaskCompositionSpec(F05_DG01_TASK_ID, F05_DG01_SCENE_ID),
        config=config,
        scene=_F05DG01TaskScene(),
        agents=(),
        objects=(),
        scene_definition=scene_definition,
        source_closure_digest=source_digest,
    )
    return runtime_source, imported, source_digest


class _F05DG01TaskScene:
    """Compatibility view for the existing reference resolver, scoped to DG01."""

    uid = F05_DG01_SCENE_ID

    def reference_spec(self):
        return ReferenceSpec(geom_names=("free_cube_geom", "support_geom"))


def _runtime_source(scene_module, scene_definition, source_root, source_xml, artifact, *, digest_override=None):
    source_id = f"scene-definition-v3:{scene_definition.identity_hash}"
    task_scene_source = TaskSceneSource(source_xml, source_root, source_id)
    projected_xml = project_scene_definition_v3_to_mjcf(source_xml, scene_definition)
    native_source = scene_module.SceneSource.mjcf_string(
        projected_xml, base_dir=source_root, label=source_id,
    )
    imported = scene_module.import_scene_source(native_source, cache=False)
    source_digest = source_closure_digest_for_import(imported, task_scene_source, projected_xml)
    if digest_override is not None:
        source_digest = digest_override

    joints = {}
    for articulation in scene_definition.articulations or ():
        for joint in articulation.joints:
            if joint.kind != "fixed":
                joints[f"{articulation.entity_id}/{joint.joint_id}"] = joint.joint_id
    bodies = {
        f"{frame.entity_id}/{frame.frame_id}": frame.frame_id
        for frame in scene_definition.frames or ()
        if frame.frame_kind == "runtime"
    }
    config = resolve_env_config(
        task_uid="phase-ii-d01a-microprobe",
        scene_uid="phase-ii-d01a-microprobe",
        runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 1, "prewarm": False},
        render={"camera_obs": False},
    )
    runtime_source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=task_scene_source,
        joints=joints,
        bodies=bodies,
        frames={},
        free_joints={},
        joint_targets={},
        open_actuators=(),
        composition=TaskCompositionSpec(
            "phase-ii-d01a-microprobe", "phase-ii-d01a-microprobe",
        ),
        config=config,
        scene=_MicroprobeScene(),
        agents=(),
        objects=(),
        scene_definition=scene_definition,
        source_closure_digest=source_digest,
    )
    return runtime_source, imported, source_digest


def _source_input(scene_module, tmp_path, scene_definition, artifact, *, source_mutator=None, digest_override=None):
    root, panda_files, panda_digest = _copy_panda_snapshot(
        scene_module, tmp_path / "panda-snapshot", scene_definition,
    )
    source_xml = _compose_scene_source(
        scene_definition, root, physics_dt=artifact.timebase.physics_dt,
    )
    if source_mutator is not None:
        source_xml = source_mutator(source_xml)
    source, imported, closure_digest = _runtime_source(
        scene_module, scene_definition, root, source_xml, artifact,
        digest_override=digest_override,
    )
    return source, imported, closure_digest, panda_digest, len(panda_files)


def _task_source(scene) -> TaskSourceV1:
    return TaskSourceV1(
        "phase-ii-d01a-microprobe",
        "candidate-v0",
        scene.scene_id,
        (
            TaskRoleDeclarationV1(
                "manipulator", "robot", "ids", ("panda-main",), "exactly_one",
            ),
            TaskRoleDeclarationV1(
                "target_peg", "rigid_body", "ids", ("square-peg-instance",), "exactly_one",
            ),
        ),
        TaskInitializationV1(
            "phase-ii-d01b-fixed-reset",
            "frozen-authored-v0",
            "training",
            "zero_named_joint_and_entity_velocities",
            "arm_targets_at_initial_joints_gripper_open",
        ),
    )


def _f05_dg01_task_source(scene) -> TaskSourceV1:
    return TaskSourceV1(
        F05_DG01_TASK_ID,
        F05_DG01_TASK_VERSION,
        scene.scene_id,
        (
            TaskRoleDeclarationV1(
                "manipulator", "robot", "ids", ("panda-main",), "exactly_one",
            ),
            TaskRoleDeclarationV1(
                "target_cube", "rigid_body", "ids", ("free-cube",), "exactly_one",
            ),
            TaskRoleDeclarationV1(
                "support", "rigid_body", "ids", ("support",), "exactly_one",
            ),
        ),
        TaskInitializationV1(
            "f05-dg01-original-home-reset",
            "frozen-authored-v0",
            "training",
            "zero_named_joint_and_entity_velocities",
            "arm_targets_at_initial_joints_gripper_open",
        ),
    )
