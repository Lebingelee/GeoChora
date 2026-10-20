"""D01b: bounded v1 Artifact/Role/Reset materialization on GeoPhys and MuJoCo."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from task_env.artifacts import ExecutionSpec, TaskArtifact
from task_env.diagnostics.tasks.test_phase_ii_d01a_scene_materialization import (
    _a05_scene,
    _artifact_and_sample,
    _axis_variant,
    _pose_difference,
    _source_input,
)
from task_env.environment import (
    TaskInitializationV1,
    TaskRoleDeclarationV1,
    TaskSourceV1,
    compile_task_artifact_v1,
    sample_episode_reset_plan,
)
from task_env.runtime.sessions.api import materialize, provider_manifest
from task_env.runtime.sessions.geophys_source import validate_canonical_scene_import


EXPECTED_GEOPHYS_REVISION = "4436787e9cb85ce519506a2a9af86d1eeec9de2d"
RESET_SEED = 31


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


def _execution(provider: str) -> ExecutionSpec:
    return ExecutionSpec(provider, "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict")


def _materialize_plan(provider, artifact, source, plan):
    session = materialize(artifact, _execution(provider), source=source)
    try:
        realized = session.reset_plan(plan)
        evidence = session.reset_plan_evidence
        # The public reset-plan method returns only after measured state passes
        # the gate; snapshot/step are checked while the exact same plan is live.
        assert evidence is not None
        assert evidence["reset_sample_id"] == plan.reset_sample.sample_id
        assert evidence["scene_identity_hash"] == plan.role_binding.scene_identity_hash
        assert evidence["role_bindings"] == dict(plan.role_binding.bindings)
        assert evidence["joint_max_abs_error"] <= evidence["tolerances"]["joint_atol"]
        assert evidence["pose_position_max_abs_error"] <= evidence["tolerances"]["pose_position_atol"]
        assert evidence["pose_orientation_max_error"] <= evidence["tolerances"]["pose_orientation_atol"]
        assert realized.reset_sample_id == plan.reset_sample.sample_id
        assert realized.actual_settle_steps == 0
        state_before_step = session.snapshot()
        assert state_before_step.control_step == 0
        assert max(
            abs(float(state_before_step.joint_position[name]) - float(value))
            for name, value in plan.reset_sample.joint_position.items()
        ) <= evidence["tolerances"]["joint_atol"]
        state_after_step = session.step()
        assert state_after_step.control_step == 1
        return realized, state_before_step, state_after_step, evidence
    finally:
        session.close()


def _plain_pose(value):
    return {
        "position": [float(item) for item in value.position],
        "quaternion_wxyz": [float(item) for item in value.quaternion_wxyz],
    }


def test_vnext_a05_scene_role_reset_materializes_on_geophys_and_mujoco(tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public Scene importer is required")
    mujoco = pytest.importorskip("mujoco", reason="MuJoCo CPU materialization is required")
    assert mujoco.__version__ == "3.8.1"

    source_decl = _task_source(_a05_scene())
    variants = {"base": _a05_scene(), "axis_x": _axis_variant(_a05_scene())}
    rows = {}
    scene_rows = {}

    for variant_name, scene_definition in variants.items():
        legacy_artifact, _ = _artifact_and_sample(scene_definition)
        artifact = compile_task_artifact_v1(source_decl, scene_definition, legacy_artifact)
        artifact.validate_scene(scene_definition)
        plan = sample_episode_reset_plan(
            source_decl, scene_definition, artifact, task_seed=RESET_SEED,
        )
        assert plan.reset_sample.task_artifact_hash == artifact.identity_hash
        assert plan.reset_sample.settle_steps == 0
        assert not plan.reset_sample.poses_world
        assert plan.role_binding.scene_identity_hash == scene_definition.identity_hash

        artifact_declarations = [
            {
                "identity_hash": asset.identity_hash,
                "source_reference": asset.source_reference,
                "source_revision": asset.source_revision,
            }
            for asset in scene_definition.assets
        ]

        runtime_source, imported_scene, source_closure_digest, panda_digest, panda_file_count = _source_input(
            scene_module,
            tmp_path / variant_name,
            scene_definition,
            legacy_artifact,
        )
        canonical_mapping = validate_canonical_scene_import(scene_definition, imported_scene)
        source_rows = {}
        for provider in ("geophys", "mujoco"):
            provider_source = replace(
                runtime_source,
                task_artifact_hash=artifact.identity_hash,
            )
            realized, before_step, after_step, gate = _materialize_plan(
                provider, artifact, provider_source, plan,
            )
            assert realized.provider_name == provider
            source_rows[provider] = {
                "sample_id": plan.reset_sample.sample_id,
                "source_closure_digest": source_closure_digest,
                "joint_max_abs_error": gate["joint_max_abs_error"],
                "pose_position_max_abs_error": gate["pose_position_max_abs_error"],
                "pose_orientation_max_error": gate["pose_orientation_max_error"],
                "gate_before_rollout": True,
                "settle_steps": realized.actual_settle_steps,
                "control_step_after_one_step": after_step.control_step,
                "link1_pose_before_step": _plain_pose(before_step.pose_world["panda-main/link1"]),
                "provider_version": provider_manifest(provider).provider_version,
            }
            if provider == "geophys":
                source_rows[provider]["provider_import_identity"] = {
                    "importer": "scene.import_scene_source",
                    "source_graph_hash": imported_scene.source_graph_hash,
                    "ir_semantic_hash": imported_scene.ir_semantic_hash,
                    "provider_cache_key": None,
                    "provider_cache_key_limitation": "public importer does not expose its cache key",
                }
            else:
                source_rows[provider]["provider_import_identity"] = {
                    "engine": "MuJoCo MjModel.from_xml_string",
                    "provider_version": mujoco.__version__,
                    "source_closure_digest": source_closure_digest,
                    "provider_cache_key": None,
                    "provider_cache_key_limitation": "MuJoCo model import/cache identity is not exposed",
                }
            rows[(variant_name, provider)] = before_step.pose_world["panda-main/link1"]

        assert source_rows["geophys"]["sample_id"] == source_rows["mujoco"]["sample_id"]
        scene_rows[variant_name] = {
            "schema_version": scene_definition.schema_version,
            "scene_id": scene_definition.scene_id,
            "scene_identity_hash": scene_definition.identity_hash,
            "task_artifact_identity_hash": artifact.identity_hash,
            "task_source_identity_hash": artifact.task_source_identity_hash,
            "role_bindings": dict(plan.role_binding.bindings),
            "reset_sample_id_shared_by_both_providers": plan.reset_sample.sample_id,
            "reset_sample_free_body_pose_target_count": len(plan.reset_sample.poses_world),
            "source_closure_digest": source_closure_digest,
            "panda_asset_source_closure_digest": panda_digest,
            "panda_source_file_count": panda_file_count,
            "asset_declarations": artifact_declarations,
            "geo_phys_import_mapping": canonical_mapping,
            "providers": source_rows,
        }

    deltas = {
        provider: _pose_difference(rows[("base", provider)], rows[("axis_x", provider)])
        for provider in ("geophys", "mujoco")
    }
    provider_pose_deltas = {
        variant_name: _pose_difference(
            rows[(variant_name, "geophys")], rows[(variant_name, "mujoco")],
        )
        for variant_name in variants
    }
    assert all(delta > 1.0e-2 for delta in deltas.values())
    assert all(delta <= 1.0e-6 for delta in provider_pose_deltas.values())
    assert scene_rows["base"]["task_artifact_identity_hash"] != scene_rows["axis_x"]["task_artifact_identity_hash"]
    assert scene_rows["base"]["providers"]["geophys"]["sample_id"] == scene_rows["base"]["providers"]["mujoco"]["sample_id"]
    assert scene_rows["axis_x"]["providers"]["geophys"]["sample_id"] == scene_rows["axis_x"]["providers"]["mujoco"]["sample_id"]

    provider_root = Path(scene_module.__file__).resolve().parents[2]
    geophys_revision = subprocess.check_output(
        ["git", "-C", str(provider_root), "rev-parse", "HEAD"], text=True,
    ).strip()
    assert geophys_revision == EXPECTED_GEOPHYS_REVISION
    receipt = {
        "schema_version": "geochora.d01b-vnext-materialization-receipt-v1",
        "result": "PASS_BOUNDED_GEOPHYS_MUJOCO_CPU",
        "provider_scope": {
            "GeoPhys": geophys_revision,
            "MuJoCo": mujoco.__version__,
            "backend": "cpu",
            "physics_profile": "p1_2_scalar_cpu_v0",
            "render_profile": "none",
            "determinism_mode": "strict",
        },
        "task_source": {
            "identity_hash": source_decl.identity_hash,
            "role_binding_is_fixed_topology": True,
            "role_bindings": {"manipulator": "panda-main", "target_peg": "square-peg-instance"},
        },
        "scene_runs": scene_rows,
        "cross_provider_link1_pose_delta": provider_pose_deltas,
        "canonical_axis_change_measured_link1_pose_delta": deltas,
        "scope_limits": [
            "one A05 Scene-v3 Panda RobotInstance and one procedural static square peg",
            "scalar revolute/prismatic joints, fixed topology, reset realization, one CPU physics step",
            "same v1 ResetSample is shared across GeoPhys and MuJoCo for each exact v1 Artifact/Scene",
            "a Scene axis change changes TaskArtifact v1 identity, so its correctly bound ResetSample is a separate sample",
            "no controller/action, gripper-control, contact-response, task-success, multi-Robot, rendering, or qualification claim",
            "MuJoCo import/cache identity is not exposed; provider package version and source closure are recorded",
        ],
    }
    output = Path("workspace/maintenance/phase_ii_d01b_20261020")
    output.mkdir(parents=True, exist_ok=True)
    (output / "d01b_vnext_materialization_receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("provider", ("geophys", "mujoco"))
def test_vnext_materialization_rejects_missing_scene_source_bindings(provider, tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public Scene importer is required")
    pytest.importorskip("mujoco", reason="D01b provider intersection requires MuJoCo")
    scene_definition = _a05_scene()
    legacy_artifact, _ = _artifact_and_sample(scene_definition)
    task_source = _task_source(scene_definition)
    artifact = compile_task_artifact_v1(task_source, scene_definition, legacy_artifact)
    runtime_source, _, _, _, _ = _source_input(
        scene_module, tmp_path / provider, scene_definition, legacy_artifact,
    )
    runtime_source = replace(runtime_source, task_artifact_hash=artifact.identity_hash)

    variant = _axis_variant(scene_definition)
    wrong_scene_source = replace(
        runtime_source,
        scene_definition=variant,
        scene_source=replace(
            runtime_source.scene_source,
            source_id=f"{variant.schema_version}:{variant.identity_hash}",
        ),
    )
    with pytest.raises(ValueError, match="exact canonical Scene"):
        materialize(artifact, _execution(provider), source=wrong_scene_source)

    missing_frame = replace(
        runtime_source,
        bodies={name: native for name, native in runtime_source.bodies.items()
                if name != "panda-main/link1"},
    )
    with pytest.raises(ValueError, match="canonical Scene Frame"):
        materialize(artifact, _execution(provider), source=missing_frame)

    missing_joint = replace(
        runtime_source,
        joints={name: native for name, native in runtime_source.joints.items()
                if name != "panda-main/joint1"},
    )
    with pytest.raises(ValueError, match="required TaskArtifact v1 Joint"):
        materialize(artifact, _execution(provider), source=missing_joint)

    stale_closure = replace(runtime_source, source_closure_digest="0" * 64)
    with pytest.raises(ValueError, match="closure digest mismatch"):
        materialize(artifact, _execution(provider), source=stale_closure)

    unbounded_source = replace(
        runtime_source,
        scene_source=replace(runtime_source.scene_source, base_dir=None),
    )
    with pytest.raises(ValueError, match="bounded source base_dir"):
        materialize(artifact, _execution(provider), source=unbounded_source)


@pytest.mark.parametrize("provider", ("geophys", "mujoco"))
def test_vnext_materialization_rejects_missing_required_asset_source(provider, tmp_path):
    scene_module = pytest.importorskip("scene", reason="GeoPhys public Scene importer is required")
    pytest.importorskip("mujoco", reason="D01b provider intersection requires MuJoCo")
    scene_definition = _a05_scene()
    legacy_artifact, _ = _artifact_and_sample(scene_definition)
    task_source = _task_source(scene_definition)
    artifact = compile_task_artifact_v1(task_source, scene_definition, legacy_artifact)
    runtime_source, _, _, _, _ = _source_input(
        scene_module, tmp_path / provider, scene_definition, legacy_artifact,
    )
    runtime_source = replace(runtime_source, task_artifact_hash=artifact.identity_hash)
    required_asset = Path(runtime_source.scene_source.base_dir) / "assets" / "link1.stl"
    assert required_asset.is_file()
    required_asset.unlink()

    with pytest.raises((ValueError, FileNotFoundError, RuntimeError)):
        materialize(artifact, _execution(provider), source=runtime_source)


def test_vnext_reset_plan_rejects_hidden_settle_steps():
    scene_definition = _a05_scene()
    legacy_artifact, _ = _artifact_and_sample(scene_definition)
    legacy_artifact = replace(
        legacy_artifact,
        initialization=replace(legacy_artifact.initialization, settle_steps=1),
    )
    task_source = _task_source(scene_definition)
    artifact = compile_task_artifact_v1(task_source, scene_definition, legacy_artifact)
    with pytest.raises(ValueError, match="nonzero settle_steps"):
        sample_episode_reset_plan(task_source, scene_definition, artifact, task_seed=RESET_SEED)
