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
from task_env.environment import (
    ReferenceSpec,
    TaskCompositionSpec,
    TaskInitializationV1,
    TaskRoleDeclarationV1,
    TaskSourceV1,
    sample_episode_reset_plan,
)
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


from task_env.tasks.position_candidate.source import (
    _MicroprobeScene,
    _a05_scene,
    _artifact_and_sample,
    _compose_scene_source,
    _copy_panda_snapshot,
    _runtime_source,
    _source_input,
)


FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "phase_ii_d01a"
EXPECTED_SCENE_IDENTITY = "047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e"
EXPECTED_PANDA_CLOSURE = "a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a"
EXPECTED_PEG_CLOSURE = "6fadf3986265a56bbedc99e1546a566641928e612d8839ea94cafaa6f15b19ff"


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


def test_b02_plan_consumes_the_exact_a05_v3_scene_identity(tmp_path):
    """Join B02's rollout gate to D01a's real A05 Scene-v3 materialization."""
    scene_module = pytest.importorskip("scene", reason="GeoPhys public scene importer is required")
    scene_definition = _a05_scene()
    artifact, _ = _artifact_and_sample(scene_definition)
    source, imported, closure_digest, _, _ = _source_input(
        scene_module, tmp_path / "b02-a05-v3", scene_definition, artifact,
    )
    task_source = TaskSourceV1(
        artifact.task_id,
        artifact.artifact_version,
        scene_definition.scene_id,
        (
            TaskRoleDeclarationV1("manipulator", "robot", "ids", ("panda-main",), "exactly_one"),
            TaskRoleDeclarationV1(
                "target_peg", "rigid_body", "ids", ("square-peg-instance",), "exactly_one",
            ),
        ),
        TaskInitializationV1(
            "phase-ii-b02-a05-fixed", "frozen-authored-v0", "training",
            "zero_named_joint_and_entity_velocities", "arm_targets_at_initial_joints_gripper_open",
        ),
    )
    plan = sample_episode_reset_plan(task_source, scene_definition, artifact, task_seed=31)
    assert plan.role_binding.scene_identity_hash == scene_definition.identity_hash
    assert plan.role_binding.bindings == {
        "manipulator": "panda-main", "target_peg": "square-peg-instance",
    }
    assert source.scene_definition.identity_hash == plan.role_binding.scene_identity_hash
    assert source.source_closure_digest == closure_digest
    assert imported is not None

    session = materialize(artifact, _execution(), source=source)
    try:
        realized = session.reset_plan(plan)
        evidence = session.reset_plan_evidence
        assert realized.reset_sample_id == plan.reset_sample.sample_id
        assert evidence["scene_identity_hash"] == scene_definition.identity_hash
        assert evidence["role_bindings"] == dict(plan.role_binding.bindings)
        assert session.step().control_step == 1
    finally:
        session.close()
