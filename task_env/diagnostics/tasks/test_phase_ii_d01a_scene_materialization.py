"""D01a: bounded SceneDefinition-v3 to GeoPhys materialization probe."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from task_env.assembly.assets import (
    _asset_definition_from_manifest,
    _source_closure_digest,
)
from task_env.assembly.source import TaskSceneSource
from task_env.artifacts import (
    ActionIntent,
    EntityDefinition,
    ExecutionSpec,
    InitializationContract,
    RequiredCapabilitySet,
    SceneDefinition,
    SemanticDefinition,
    TaskArtifact,
    Timebase,
    WorldDefinition,
)
from task_env.artifacts.execution import ResetSample
from task_env.diagnostics.tasks.test_phase_ii_a04_asset_evidence import (
    MENAGERIE_REVISION,
)
from task_env.environment import ReferenceSpec, TaskCompositionSpec
from task_env.environment.configuration import resolve_env_config
from task_env.objects.nut_assembly import SquarePegObject
from task_env.robots.panda import PandaAgent
from task_env.runtime.sessions.api import materialize
from task_env.runtime.sessions.common import validate_reset_realization
from task_env.runtime.sessions.geophys_source import (
    project_scene_definition_v3_to_mjcf,
    source_closure_digest_for_import,
    validate_canonical_scene_import,
)
from task_env.runtime.sessions.source import RuntimeSource


FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "phase_ii_d01a"
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
    assert scene.schema_version == "scene-definition-v3"
    assert scene.identity_hash == EXPECTED_SCENE_IDENTITY
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
    assert revision == manifest.source_revision == MENAGERIE_REVISION

    discovered = scene_module.import_scene_source(
        scene_module.SceneSource.mjcf_path(source_path), cache=False,
    )
    files: dict[str, bytes] = {}
    for raw_path in discovered.dependency_paths:
        path = Path(raw_path).resolve()
        logical = path.relative_to(asset_root).as_posix()
        files[logical] = path.read_bytes()
    assert "panda.xml" in files and len(files) == 68
    digest = _source_closure_digest(files)
    panda_receipt = json.loads((FIXTURE_ROOT / "panda_source_receipt.json").read_text())
    assert digest == panda_receipt["source_closure_digest"] == EXPECTED_PANDA_CLOSURE

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
    assert peg_receipt["asset_declaration_identity"] == peg_asset.identity_hash
    assert peg_receipt["source_closure_digest"] == EXPECTED_PEG_CLOSURE
    peg_xml_bytes = (FIXTURE_ROOT / "square_peg.xml").read_bytes()
    assert _source_closure_digest({"square-peg.xml": peg_xml_bytes}) == EXPECTED_PEG_CLOSURE
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


def _execution() -> ExecutionSpec:
    return ExecutionSpec("geophys", "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict")


def _axis_variant(scene: SceneDefinition) -> SceneDefinition:
    mapping = scene.to_mapping()
    joint = next(
        joint for articulation in mapping["articulations"]
        for joint in articulation["joints"] if joint["joint_id"] == "joint1"
    )
    joint["axis"] = [1.0, 0.0, 0.0]
    variant = SceneDefinition.from_mapping(mapping)
    assert variant.identity_hash != scene.identity_hash
    return variant


def _pose_difference(left, right) -> float:
    position = np.asarray(left.position, dtype=np.float64) - np.asarray(right.position, dtype=np.float64)
    left_q = np.asarray(left.quaternion_wxyz, dtype=np.float64)
    right_q = np.asarray(right.quaternion_wxyz, dtype=np.float64)
    quaternion = min(np.linalg.norm(left_q - right_q), np.linalg.norm(left_q + right_q))
    return float(max(np.linalg.norm(position), quaternion))


def _write_receipt(tmp_path, receipt):
    output = Path("workspace/maintenance/phase_ii_d01a_main_20261020")
    output.mkdir(parents=True, exist_ok=True)
    (output / "d01a_microprobe_receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def test_a05_scene_v3_drives_geophys_main_realization_before_rollout(tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public scene importer is required")
    scene_definition = _a05_scene()
    artifact, sample = _artifact_and_sample(scene_definition)
    source, imported, closure_digest, panda_digest, panda_file_count = _source_input(
        scene_module, tmp_path / "original", scene_definition, artifact,
    )
    assert panda_digest == EXPECTED_PANDA_CLOSURE
    mapping = validate_canonical_scene_import(scene_definition, imported)
    public_model = imported.build_rigid_scene_model(use_imported_meshes=True)
    solver_desc = imported.build_solver_scene_desc()
    assert int(public_model.joint_data["n_geoms"]) > 0
    assert int(public_model.joint_data["n_actuators"]) == 8
    assert len(imported.ir.shapes) >= 80
    assert len(imported.ir.transmissions) == 8

    session = materialize(artifact, _execution(), source=source)
    try:
        realized = session.reset(sample)
        base_gate = validate_reset_realization(sample, realized, joint_atol=1.0e-6)
        base_state = session.snapshot()
        assert base_state.control_step == 0
        session.step()
        post_gate_state = session.snapshot()
        assert post_gate_state.control_step == 1
    finally:
        session.close()

    # The Scene axis is the changed input; the exact same v0 Artifact and
    # ResetSample isolate its effect on the actual provider realization.
    variant_scene = _axis_variant(scene_definition)
    variant_source, variant_imported, variant_digest, _, _ = _source_input(
        scene_module, tmp_path / "axis-variant", variant_scene, artifact,
    )
    assert variant_digest != closure_digest
    validate_canonical_scene_import(variant_scene, variant_imported)
    variant_session = materialize(artifact, _execution(), source=variant_source)
    try:
        variant_realized = variant_session.reset(sample)
        variant_gate = validate_reset_realization(sample, variant_realized, joint_atol=1.0e-6)
        variant_state = variant_session.snapshot()
    finally:
        variant_session.close()
    assert _pose_difference(
        base_state.pose_world["panda-main/link1"],
        variant_state.pose_world["panda-main/link1"],
    ) > 1.0e-2

    provider_root = Path(scene_module.__file__).resolve().parents[2]
    provider_revision = subprocess.check_output(
        ["git", "-C", str(provider_root), "rev-parse", "HEAD"], text=True,
    ).strip()
    assert provider_revision == "4436787e9cb85ce519506a2a9af86d1eeec9de2d"
    capability_statuses = Counter(entry.status.value for entry in imported.capability_report.entries)
    canonical_semantics = {"frame.body", "joint.kinematic", "actuator.control"}
    semantic_rows = []
    for entry in imported.capability_report.entries:
        if entry.semantic in canonical_semantics:
            disposition = "CANONICAL_REPRESENTED"
        elif entry.status.value == "rejected":
            disposition = "UNSUPPORTED"
        elif entry.status.value == "approximated":
            disposition = "APPROXIMATE"
        else:
            disposition = "SOURCE_RETAINED"
        semantic_rows.append({
            "semantic": entry.semantic,
            "provider_status": entry.status.value,
            "core_disposition": disposition,
            "source_element_path": entry.source_ref.element_path,
            "provider_action": entry.action,
        })
    disposition_counts = Counter(row["core_disposition"] for row in semantic_rows)
    report = {
        "schema_version": "geochora.d01a-materialization-receipt-v1",
        "result": "PASS_BOUNDED_GEOPHYS_CPU_MICROPROBE",
        "scene_input": {
            "schema_version": scene_definition.schema_version,
            "scene_identity": scene_definition.identity_hash,
            "exact_a05_mapping": scene_definition.identity_hash == EXPECTED_SCENE_IDENTITY,
        },
        "task_artifact": {
            "schema_version": artifact.schema_version,
            "candidate_identity": artifact.identity_hash,
            "frozen": False,
        },
        "reset_sample": {
            "sample_id": sample.sample_id,
            "same_sample_used_for_scene_axis_variant": True,
        },
        "asset_declarations": [
            {"identity": asset.identity_hash, "source_reference": asset.source_reference,
             "source_revision": asset.source_revision}
            for asset in scene_definition.assets
        ],
        "source_closure": {
            "panda_source_closure_digest": panda_digest,
            "panda_source_files": panda_file_count,
            "square_peg_source_closure_digest": EXPECTED_PEG_CLOSURE,
            "materialized_scene_source_closure_digest": closure_digest,
            "axis_variant_scene_identity": variant_scene.identity_hash,
            "axis_variant_materialized_source_closure_digest": variant_digest,
        },
        "provider_import_identity": {
            "provider": "GeoPhys",
            "provider_revision": provider_revision,
            "importer": "scene.import_scene_source",
            "source_graph_hash": imported.source_graph_hash,
            "ir_semantic_hash": imported.ir_semantic_hash,
            "provider_cache_key": None,
            "provider_cache_key_limitation": "public importer does not expose its cache key",
        },
        "mapping": mapping,
        "source_semantic_dispositions": {
            "provider_status_counts": dict(capability_statuses),
            "core_disposition_counts": dict(disposition_counts),
            "entries": semantic_rows,
        },
        "consumption": {
            "public_imported_bodies": len(imported.ir.bodies),
            "public_imported_shapes": len(imported.ir.shapes),
            "public_imported_joints": len(imported.ir.joints),
            "public_imported_actuators": len(imported.ir.actuators),
            "public_imported_transmissions": len(imported.ir.transmissions),
            "public_imported_constraints": len(imported.ir.constraints),
            "solver_scene_description": {
                "bodies": len(solver_desc.bodies),
                "shapes": len(solver_desc.shapes),
                "joints": len(solver_desc.joints),
                "actuators": len(solver_desc.actuators),
                "transmissions": len(solver_desc.transmissions),
                "constraints": len(solver_desc.constraints),
            },
            "rigid_scene_model": {
                "collision_geometries": int(public_model.joint_data["n_geoms"]),
                "actuators": int(public_model.joint_data["n_actuators"]),
                "qpos": int(public_model.joint_data["n_qpos"]),
                "dof": int(public_model.joint_data["n_dof"]),
            },
            "contact_execution": "no contact rollout was performed",
            "source_retained_meaning": "retained bytes are not asserted as executed semantics",
        },
        "realization_gate": {
            "after_reset_before_first_step": base_gate,
            "axis_variant_after_reset_before_rollout": variant_gate,
            "first_step_control_boundary": post_gate_state.control_step,
            "measured_link1_pose_delta": _pose_difference(
                base_state.pose_world["panda-main/link1"],
                variant_state.pose_world["panda-main/link1"],
            ),
        },
        "limits": [
            "GeoPhys main CPU only; no MuJoCo or second Provider assertion",
            "no controller/action execution or task success claim",
            "contact response is not exercised by this one-step no-contact probe",
            "D01b, general Scene import, Task Harness and qualification remain out of scope",
        ],
    }
    _write_receipt(tmp_path, report)


def test_scene_v3_projection_rejects_missing_frame_and_joint(tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public scene importer is required")
    scene_definition = _a05_scene()
    artifact, _ = _artifact_and_sample(scene_definition)
    root, _, _ = _copy_panda_snapshot(
        scene_module, tmp_path / "snapshot", scene_definition,
    )
    source_xml = _compose_scene_source(
        scene_definition, root, physics_dt=artifact.timebase.physics_dt,
    )
    frame_missing = source_xml.replace('name="link1"', 'name="link1_missing"', 1)
    frame_source, _, _, _, _ = _source_input(
        scene_module, tmp_path / "frame", scene_definition, artifact,
        source_mutator=lambda _: frame_missing,
    )
    with pytest.raises(ValueError, match="Frame mapping mismatch"):
        materialize(artifact, _execution(), source=frame_source)

    joint_missing = source_xml.replace('<joint name="joint1"', '<joint name="joint1_missing"', 1)
    joint_source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=TaskSceneSource(
            joint_missing, root, f"scene-definition-v3:{scene_definition.identity_hash}"
        ),
        joints={f"panda-main/{joint.joint_id}": joint.joint_id
                for joint in scene_definition.articulations[0].joints if joint.kind != "fixed"},
        bodies={f"{frame.entity_id}/{frame.frame_id}": frame.frame_id
                for frame in scene_definition.frames if frame.frame_kind == "runtime"},
        frames={}, free_joints={}, joint_targets={}, open_actuators=(),
        composition=TaskCompositionSpec("phase-ii-d01a-microprobe", "phase-ii-d01a-microprobe"),
        config=resolve_env_config(
            task_uid="phase-ii-d01a-microprobe", scene_uid="phase-ii-d01a-microprobe",
            runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 1, "prewarm": False},
            render={"camera_obs": False},
        ),
        scene=_MicroprobeScene(), agents=(), objects=(),
        scene_definition=scene_definition, source_closure_digest="0" * 64,
    )
    with pytest.raises(ValueError, match="exactly one MJCF joint"):
        materialize(artifact, _execution(), source=joint_source)


def test_d01a_rejects_missing_geometry_and_source_closure_mismatch(tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public scene importer is required")
    scene_definition = _a05_scene()
    artifact, _ = _artifact_and_sample(scene_definition)
    source, _, _, _, _ = _source_input(scene_module, tmp_path / "digest", scene_definition, artifact)
    mismatched = replace(source, source_closure_digest="0" * 64)
    with pytest.raises(ValueError, match="source closure digest mismatch"):
        materialize(artifact, _execution(), source=mismatched)

    def remove_collision_geom(xml):
        root = ET.fromstring(xml)
        geom = root.find(".//geom[@name='square_peg_collision']")
        if geom is None:
            raise AssertionError("collision geom fixture is missing")
        parent = next(node for node in root.iter() if geom in list(node))
        parent.remove(geom)
        return ET.tostring(root, encoding="unicode")

    geometry_source, _, _, _, _ = _source_input(
        scene_module, tmp_path / "geometry", scene_definition, artifact,
        source_mutator=remove_collision_geom,
    )
    with pytest.raises(KeyError, match="square_peg_collision"):
        materialize(artifact, _execution(), source=geometry_source)


def test_d01a_reset_tolerance_rejects_over_tolerance_and_build_failure(tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public scene importer is required")
    scene_definition = _a05_scene()
    artifact, sample = _artifact_and_sample(scene_definition)
    source, _, _, _, _ = _source_input(scene_module, tmp_path / "build", scene_definition, artifact)
    session = materialize(artifact, _execution(), source=source)
    try:
        realized = session.reset(sample)
        validate_reset_realization(sample, realized, joint_atol=1.0e-6)
        wrong_values = dict(realized.measured_state.joint_position)
        wrong_values["panda-main/joint1"] += 2.0e-5
        wrong_state = replace(realized.measured_state, joint_position=wrong_values)
        over_tolerance = replace(realized, measured_state=wrong_state)
        with pytest.raises(ValueError, match="joint realization exceeds tolerance"):
            validate_reset_realization(sample, over_tolerance, joint_atol=1.0e-6)
    finally:
        session.close()

    malformed_source = replace(
        source,
        scene_source=TaskSceneSource(
            "<mujoco><option timestep='0.002'></mujoco>",
            source.scene_source.base_dir,
            source.scene_source.source_id,
        ),
    )
    with pytest.raises(ET.ParseError):
        materialize(artifact, _execution(), source=malformed_source)
