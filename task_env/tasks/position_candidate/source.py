"""Fixed A05 Scene/source construction shared by the Position task and diagnostics.

Extracted without changing frozen identities or source bytes. Native scene import
is supplied by the construction caller; importing this module builds no runtime.
"""

from __future__ import annotations

import json
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
            if joint.kind != "fixed":
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
