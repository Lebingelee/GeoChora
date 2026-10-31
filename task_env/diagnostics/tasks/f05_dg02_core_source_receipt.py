"""Build the DG02 Core candidate and public-model receipt without solver init."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provider_module_sources(provider_src: Path) -> tuple[tuple[str, str, str], ...]:
    rows = {}
    for module_name, module in tuple(sys.modules.items()):
        raw_origin = getattr(module, "__file__", None)
        if not raw_origin:
            continue
        path = Path(raw_origin).resolve()
        try:
            path.relative_to(provider_src)
        except ValueError:
            continue
        if path.is_file():
            rows[module_name] = (module_name, str(path), _sha(path))
    return tuple(sorted(rows.values(), key=lambda row: row[0]))


def build_candidate_receipt(plan: dict, *, include_candidate: bool = False):
    core = Path(plan["input_identity"]["core_worktree"]).resolve(strict=True)
    provider = Path(plan["input_identity"]["provider_worktree"]).resolve(strict=True)
    provider_src = provider / "src"
    delivery_path = Path(plan["source"]["delivery_manifest"]["path"]).resolve(strict=True)
    stage_path = Path(plan["source"]["usd_stage"]["path"]).resolve(strict=True)
    target_build = "geophys-" + str(plan["input_identity"]["provider_gitlink"])

    os.chdir(core)
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    if str(provider_src) not in sys.path:
        sys.path.insert(0, str(provider_src))

    from task_env.assembly.source import UsdTaskSceneSourceV1
    from task_env.assembly.usd_delivery import (
        load_usd_asset_delivery,
        resolve_provider_representation,
    )
    from task_env.artifacts import TaskArtifact, ExecutionSpecV1, RendererSelectionV1
    from task_env.diagnostics.tasks.f05_source_control_support import lower_public_model
    from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
    from task_env.environment.config import ActionConfig
    from task_env.runtime.sessions.geophys_source import (
        compile_geophys_usd_source_actuation_receipt_v2,
    )
    from task_env.runtime.sessions.leaf_control import GeoPhysHostModelProducerIdentityV1
    from task_env.runtime.sessions.source import UsdRuntimeSourceV1
    from task_env.tasks.position_candidate.builder import (
        F05Dg02GeoPhysUsdCandidateInputV1,
        F05_DG02_GEOPHYS_PROFILE,
        _f05_dg02_usd_source_bindings,
        build_versioned_position_candidate,
    )
    from task_env.tasks.position_candidate.source import (
        F05_DG01_SCENE_ID,
        F05_DG01_TASK_ID,
        _f05_dg01_artifact_and_sample,
        _f05_dg01_scene,
        _f05_dg01_task_source,
    )

    if _sha(stage_path) != plan["source"]["usd_stage"]["sha256"]:
        raise ValueError("DG02 USD stage hash differs from its frozen run plan")
    if _sha(delivery_path) != plan["source"]["delivery_manifest"]["sha256"]:
        raise ValueError("DG02 delivery manifest hash differs from its frozen run plan")
    geometry_audit_row = plan["source"]["usd_geometry_audit_v2"]
    geometry_audit_path = Path(geometry_audit_row["path"]).resolve(strict=True)
    if _sha(geometry_audit_path) != geometry_audit_row["sha256"]:
        raise ValueError("DG02 source geometry audit differs from its frozen run plan")
    geometry_audit = json.loads(geometry_audit_path.read_text(encoding="utf-8"))
    if (not geometry_audit.get("passed")
            or geometry_audit.get("usd_stage_sha256") != _sha(stage_path)):
        raise ValueError("DG02 source geometry audit is not a passing receipt for this USD stage")
    loaded = load_usd_asset_delivery(delivery_path)
    delivery = loaded.delivery
    if not loaded.locally_validated or loaded.source_verified:
        raise ValueError("DG02 candidate requires the exact locally validated, non-upstream USD delivery")

    scene = _f05_dg01_scene()
    legacy_artifact, _legacy_sample = _f05_dg01_artifact_and_sample(scene)
    task_source = _f05_dg01_task_source(scene)
    panda_asset = delivery.asset_definition
    old_panda_assets = [asset for asset in scene.assets if asset.asset_id == "panda-v1"]
    if len(old_panda_assets) != 1:
        raise ValueError("DG02 could not locate the exact DG01 Panda Asset in the pure-data Scene")
    old_panda_asset = old_panda_assets[0]
    scene = replace(
        scene,
        assets=tuple(panda_asset if asset == old_panda_asset else asset for asset in scene.assets),
        entities=tuple(
            replace(entity, asset_id=panda_asset.asset_id, asset_version=panda_asset.asset_version)
            if entity.entity_id == "panda-main" else entity
            for entity in scene.entities
        ),
    )
    scene.validate()
    legacy_mapping = legacy_artifact.to_mapping()
    for entity in legacy_mapping["world"]["entities"]:
        if entity["semantic_id"] == "panda-main":
            entity["asset_reference"] = f"{panda_asset.source_reference}@{panda_asset.asset_version}"
    legacy_artifact = TaskArtifact.from_mapping(legacy_mapping)
    artifact = compile_task_artifact_v1(task_source, scene, legacy_artifact)
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact,
        task_seed=int(plan["source"]["task_seed"]),
    )

    expected_bodies, expected_joints = _f05_dg02_usd_source_bindings()
    if set(expected_bodies) != {
            f"{frame.entity_id}/{frame.frame_id}"
            for frame in scene.frames or () if frame.frame_kind == "runtime"}:
        raise ValueError("DG02 source binding table does not cover the DG01 canonical runtime Frames")
    target_build_identity = target_build
    representation = resolve_provider_representation(
        loaded,
        provider="geophys",
        provider_build_identity=target_build_identity,
        options={
            "f05_goal": "DG02",
            "lowering": "public-host-model-source-actuation-v2",
            "producer_capture": "pending",
        },
    )
    task_scene_source = UsdTaskSceneSourceV1(
        "usd-task-scene-source-v1", loaded, representation,
        task_source.identity_hash, scene.identity_hash,
    )
    source = UsdRuntimeSourceV1(
        "usd-runtime-source-v1", artifact, scene, task_scene_source,
        expected_joints, expected_bodies, {},
        {"free-cube/free_cube": "/F04Scene/free_cube/rootJoint"},
        expected_joints,
    )
    execution = ExecutionSpecV1(
        "execution-spec-v1", "geophys", "cpu", F05_DG02_GEOPHYS_PROFILE,
        0, "best_effort", RendererSelectionV1(
            "renderer-selection-v1", "none", "cpu", "none", None,
        ), "cpu", (),
    )
    imported, model, bridge_id, mapping_report = lower_public_model(source)

    provider_url = subprocess.check_output(
        ["git", "-C", str(provider), "remote", "get-url", "origin"],
        text=True,
    ).strip()
    provider_head = subprocess.check_output(
        ["git", "-C", str(provider), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    provider_clean = not subprocess.check_output(
        ["git", "-C", str(provider), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
    ).strip()
    producer = GeoPhysHostModelProducerIdentityV1(
        "geophys-host-model-producer-identity-v1", target_build_identity, str(provider),
        provider_url, provider_head, provider_clean,
        _provider_module_sources(provider_src),
    )
    producer.validate_current_tree()
    representation = resolve_provider_representation(
        loaded,
        provider="geophys",
        provider_build_identity=target_build_identity,
        options={
            "f05_goal": "DG02",
            "lowering": "public-host-model-source-actuation-v2",
            "host_model_producer_identity_sha256": producer.identity_sha256,
            "actual_execution_build_identity": producer.actual_provider_build_identity,
        },
    )
    task_scene_source = replace(task_scene_source, representation=representation)
    source = UsdRuntimeSourceV1(
        "usd-runtime-source-v1", artifact, scene, task_scene_source,
        expected_joints, expected_bodies, {},
        {"free-cube/free_cube": "/F04Scene/free_cube/rootJoint"},
        expected_joints,
    )
    receipt = compile_geophys_usd_source_actuation_receipt_v2(
        source, imported, model, execution,
        provider_build_identity=producer.actual_provider_build_identity,
        provenance_kind="native_runtime",
        host_model_producer_identity=producer,
    )
    source_xml = (delivery_path.parent / delivery.source_entry_file).read_text()
    if _sha(delivery_path.parent / delivery.source_entry_file) != delivery.source_entry_sha256:
        raise ValueError("DG02 kinematics XML is not the exact frozen Menagerie source entry")
    action_config = ActionConfig(
        joint_position_correction_gain=1.0,
        gripper_default_force_N=100.0,
    )
    candidate_input = F05Dg02GeoPhysUsdCandidateInputV1(
        "f05-dg02-geophys-usd-candidate-input-v1",
        task_source, artifact, source, execution, reset_plan,
        source_xml, hashlib.sha256(source_xml.encode()).hexdigest(),
        producer, receipt, action_config,
    )
    candidate_input.validate()
    candidate = build_versioned_position_candidate(
        candidate_input, horizon=int(plan["source"]["candidate_horizon"]),
    )
    counts = model.joint_data
    result = {
        "schema_version": "f05-dg02-core-source-actuation-model-receipt-v1",
        "run_id": plan["run_id"],
        "provider_format": imported.format,
        "delivery_manifest_sha256": _sha(delivery_path),
        "usd_stage_sha256": _sha(stage_path),
        "usd_geometry_audit_v2": {
            "path": str(geometry_audit_path),
            "sha256": geometry_audit_row["sha256"],
            "passed": geometry_audit["passed"],
            "max_vertex_error_m": geometry_audit["panda"]["max_vertex_error_m"],
            "max_triangle_coordinate_error_m": geometry_audit["panda"]["max_triangle_coordinate_error_m"],
            "max_full_inertia_tensor_error_kg_m2": geometry_audit["panda"]["max_full_inertia_tensor_error_kg_m2"],
        },
        "provider_source_closure_sha256": delivery.source_closure_sha256,
        "provider_delivery_closure_sha256": loaded.closure_sha256,
        "provider_representation_identity_sha256": representation.identity_hash,
        "provider_requested_build_identity": producer.requested_target_build_identity,
        "provider_actual_build_identity": producer.actual_provider_build_identity,
        "provider_module_source_count": len(producer.module_sources),
        "source_task_id": task_source.task_id,
        "source_task_identity_sha256": task_source.identity_hash,
        "dg02_task_artifact_identity_sha256": artifact.identity_hash,
        "dg02_scene_identity_sha256": scene.identity_hash,
        "execution_identity_sha256": execution.identity_hash,
        "controller_binding_plan_identity_sha256": candidate.controller_binding_plan.identity_hash,
        "controller_identity_sha256": candidate.env.controller.identity,
        "controller_method": {
            "nullspace_reference_gain": candidate.env.controller.nullspace_reference_gain,
            "reference_source": "reset_typed_arm_joint_position",
            "projector": "svd_right_nullspace_v1",
            "pose_target_method": candidate.env.controller.pose_target_method,
            "arm_target_limit_source": candidate.env.controller.arm_target_limit_source,
        },
        "action_config": {
            "joint_position_correction_gain": candidate_input.action_config.joint_position_correction_gain,
            "gripper_default_force_N": candidate_input.action_config.gripper_default_force_N,
            "gripper_opening_range_m": candidate_input.action_config.gripper_opening_range_m,
            "gripper_close_ctrl": candidate_input.action_config.gripper_close_ctrl,
            "gripper_open_ctrl": candidate_input.action_config.gripper_open_ctrl,
        },
        "source_actuation_receipt": asdict(receipt),
        "source_actuation_receipt_identity_sha256": receipt.identity_sha256,
        "import_bridge_id": bridge_id,
        "mapping_report": mapping_report,
        "public_model_counts": {
            "n_qpos": int(counts["n_qpos"]),
            "n_dof": int(counts["n_dof"]),
            "n_actuators": int(counts["n_actuators"]),
            "n_tendons": int(counts["n_tendons"]),
            "n_equalities": int(counts.get("n_equalities", 1)),
            "n_geoms": int(counts["n_geoms"]),
        },
        "checks": {
            "task_source_is_dg01_semantics": task_source.task_id == F05_DG01_TASK_ID,
            "candidate_input_validate": True,
            "v2_receipt_bound_to_public_model": True,
            "position_candidate_action_config": True,
            "selected_reference_env_candidate_built": candidate.env is not None,
            "solver_initialized": False,
            "solver_constructed": False,
            "physics_steps": 0,
        },
    }
    if include_candidate:
        return result, candidate
    return result


def main() -> None:
    core_root = Path(__file__).resolve().parents[3]
    if str(core_root) not in sys.path:
        sys.path.insert(0, str(core_root))
    from task_env.diagnostics.tasks.f05_dg02_n0_model_compile import _verify_plan

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    plan, plan_hash = _verify_plan(args.plan.resolve(strict=True), args.plan_sha256.resolve(strict=True))
    if args.stage.resolve(strict=True) != Path(plan["source"]["usd_stage"]["path"]).resolve(strict=True):
        raise ValueError("host supervisor stage differs from the frozen USD source in the plan")
    receipt = build_candidate_receipt(plan)
    receipt["plan_path"] = str(args.plan.resolve())
    receipt["plan_sha256"] = plan_hash
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
