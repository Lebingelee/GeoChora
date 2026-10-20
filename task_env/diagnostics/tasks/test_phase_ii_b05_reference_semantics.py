"""B05 bounded bridge of the frozen NutAssembly task semantics into A Scene."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import xml.etree.ElementTree as ET

from task_env.artifacts import (
    AssetDefinition,
    CanonicalStateView,
    EntityInstance,
    FrameReference,
    FrameDefinition,
    JointReference,
    PoseWorld,
    SceneDefinition,
)
from task_env.environment import adapt_legacy_recipe_task_source, compile_task_artifact_v1
from task_env.environment.configuration import load_yaml_mapping
from task_env.tasks.pick_cube.task import (
    build_artifact as build_pickcube_artifact,
    build_runtime_source as build_pickcube_runtime_source,
    evaluate as evaluate_pickcube,
)
from task_env.tasks.nut_assembly.task import build_artifact, evaluate


def test_nutassembly_a05_projection_compiles_with_explicit_reference_map_and_keeps_semantics(tmp_path):
    # Reuse A05's source-backed receipts and its read-only legacy projection;
    # this proves the real Panda/peg Scene path, not a hand-built Scene fixture.
    from task_env.diagnostics.tasks.test_phase_ii_a05_static_projection import (
        _project_existing_nutassembly_task,
        _run_a04_evidence,
    )

    panda_receipt, peg_receipt, legacy_receipt = _run_a04_evidence(tmp_path)
    legacy = build_artifact()
    projection = _project_existing_nutassembly_task(
        legacy, panda_receipt, peg_receipt, legacy_receipt,
    )
    scene = SceneDefinition.from_mapping(projection["target_scene"])

    task_root = Path(__file__).resolve().parents[2] / "tasks" / "nut_assembly"
    source = adapt_legacy_recipe_task_source(
        load_yaml_mapping(task_root / "config.yaml")
    )
    # A05's approved compatibility projection has its own Scene identity. Bind
    # that identity explicitly into this new authoring Source snapshot.
    source = replace(source, scene_ref=scene.scene_id)
    frame_bindings = {
        row["legacy_reference"]: FrameReference.from_mapping(row["canonical_identity"])
        for row in projection["field_map"] if row["kind"] == "Frame"
    }
    joint_bindings = {
        row["legacy_reference"]: JointReference.from_mapping(row["canonical_identity"])
        for row in projection["field_map"] if row["kind"] == "Joint"
    }

    candidate = compile_task_artifact_v1(
        source,
        scene,
        legacy,
        frame_bindings=frame_bindings,
        joint_bindings=joint_bindings,
    )
    assert candidate.schema_version == "task-artifact-v1"
    assert candidate.scene_identity_hash == scene.identity_hash
    assert candidate.source_artifact_identity_hash == legacy.identity_hash
    assert candidate.identity_hash != legacy.identity_hash
    assert candidate.legacy_frame_bindings == frame_bindings
    assert candidate.legacy_joint_bindings == joint_bindings
    assert candidate.semantics == legacy.semantics

    # Frozen canonical terminal-state input for semantic comparison; this is
    # not a claim that the v1 candidate has run through a provider rollout.
    state = CanonicalStateView(
        "canonical-state-v0",
        "SI_right_handed_z_up_wxyz",
        0,
        0.0,
        {
            "panda-v1/finger_joint1": 0.04,
            "panda-v1/finger_joint2": 0.04,
        },
        {
            "panda-v1/finger_joint1": 0.0,
            "panda-v1/finger_joint2": 0.0,
        },
        {
            "square-nut-v1": PoseWorld((0.58, 0.045, 0.473), (0.0, 0.0, 0.0, 1.0)),
            "square-peg-v1": PoseWorld((0.58, 0.045, 0.5), (1.0, 0.0, 0.0, 0.0)),
            "panda-v1/ee": PoseWorld((0.58, 0.045, 0.65), (1.0, 0.0, 0.0, 0.0)),
        },
    )
    old_result = evaluate(state, legacy.semantics)
    new_result = evaluate(state, candidate.semantics)
    assert new_result == old_result
    assert new_result.success is True
    assert new_result.metrics["task_success"] is True
    assert new_result.reward_terms == old_result.reward_terms
    assert new_result.reward == 1.254820316853445
    assert new_result.metrics["aligned_with_peg"] is True
    assert new_result.metrics["inserted_on_peg"] is True
    assert new_result.metrics["released_nut"] is True
    assert new_result.metrics["eef_to_handle_dist"] == 0.1850540461594937
    assert dict(new_result.reward_terms) == {
        "reach": 0.004820316853445051,
        "grasp": 0.0,
        "lift": 0.0,
        "hover": 0.0,
        "insert": 0.15,
        "release": 0.1,
        "success": 1.0,
    }


def test_pickcube_a04_panda_scene_candidate_keeps_pinned_legacy_metrics(tmp_path):
    """Compile PickCube semantics against real imported Panda structure.

    Cube/table geometry remains explicitly source-retained from the selected
    v0 Artifact here; this is a semantic compatibility probe, not materialization.
    """
    from task_env.diagnostics.tasks.test_phase_ii_a05_static_projection import (
        _rekey_scene_entity,
        _run_a04_evidence,
        _task_asset_from_artifact,
    )

    panda_receipt, _peg_receipt, _legacy_receipt = _run_a04_evidence(tmp_path)
    legacy = build_pickcube_artifact()
    panda = _rekey_scene_entity(
        SceneDefinition.from_mapping(panda_receipt["canonical_scene"]),
        {"panda-main": "panda-v1"},
    )

    runtime_source = build_pickcube_runtime_source(legacy, backend="cpu")
    root = ET.fromstring(runtime_source.scene_source.xml)
    hand = root.find(".//body[@name='hand']")
    site_name = runtime_source.frames["panda-v1/ee"]
    site = None if hand is None else hand.find(f"site[@name='{site_name}']")
    assert site is not None
    ee_frame = FrameDefinition(
        "frame-definition-v1", "panda-v1", "ee", "authored_fixed",
        FrameReference("panda-v1", "hand"),
        PoseWorld(
            tuple(float(value) for value in site.get("pos", "0 0 0").split()),
            tuple(float(value) for value in site.get("quat", "1 0 0 0").split()),
        ),
    )
    scene_config = load_yaml_mapping(
        Path(__file__).resolve().parents[2] / "tasks" / "pick_cube" / "config.yaml"
    )["recipe"]["scene"]
    table_top = FrameDefinition(
        "frame-definition-v1", "tabletop-v1", "top", "authored_fixed", None,
        PoseWorld((0.0, 0.0, float(scene_config["table_top_z"])), (1.0, 0.0, 0.0, 0.0)),
    )

    extra_assets = []
    extra_entities = []
    for entity in legacy.world.entities:
        if entity.semantic_id == "panda-v1":
            continue
        asset = _task_asset_from_artifact(legacy, entity)
        extra_assets.append(asset)
        extra_entities.append(
            EntityInstance("entity-instance-v1", entity.semantic_id, asset.asset_id, asset.asset_version)
        )
    scene = SceneDefinition(
        "scene-definition-v3", "pickcube-world-v0-compat-v1",
        (*panda.assets, *extra_assets), (*panda.entities, *extra_entities),
        (*panda.frames, ee_frame, table_top), panda.articulations, panda.robots,
        panda.actuator_resources, panda.control_groups,
    )

    task_root = Path(__file__).resolve().parents[2] / "tasks" / "pick_cube"
    source = adapt_legacy_recipe_task_source(load_yaml_mapping(task_root / "config.yaml"))
    source = replace(source, scene_ref=scene.scene_id)
    frame_bindings = {
        "panda-v1/base": FrameReference("panda-v1", "link0"),
        "panda-v1/ee": FrameReference("panda-v1", "ee"),
    }
    joint_bindings = {
        name: JointReference("panda-v1", name.split("/", 1)[1])
        for entity in legacy.world.entities
        for name in entity.joints
    }
    candidate = compile_task_artifact_v1(
        source, scene, legacy,
        frame_bindings=frame_bindings,
        joint_bindings=joint_bindings,
    )

    state = CanonicalStateView(
        "canonical-state-v0", "SI_right_handed_z_up_wxyz", 0, 0.0,
        {
            "panda-v1/finger_joint1": 0.07999873306277117 / 2,
            "panda-v1/finger_joint2": 0.07999873306277117 / 2,
        },
        {"panda-v1/finger_joint1": 0.0, "panda-v1/finger_joint2": 0.0},
        {
            "cube-v1": PoseWorld(
                (0.6351343459705087, -0.08646434752767339, 0.48762747518153127),
                (1.0, 0.0, 0.0, 0.0),
            ),
            "panda-v1/ee": PoseWorld(
                (0.5914863404002174, -0.08949059580312209, 0.5771712604381248),
                (-0.01493029538157625, 0.7644666296611904, 0.6443596055257806, -0.012982957326429108),
            ),
        },
    )
    old_result = evaluate_pickcube(state, legacy.semantics)
    new_result = evaluate_pickcube(state, candidate.semantics)
    assert candidate.scene_identity_hash == scene.identity_hash
    assert candidate.source_artifact_identity_hash == legacy.identity_hash
    assert candidate.identity_hash != legacy.identity_hash
    assert new_result == old_result
    assert new_result.success is False
    assert new_result.metrics["eef_to_cube_dist"] == 0.09966140700877033
    assert new_result.metrics["cube_lift"] == 0.000627475181531223
    assert new_result.reward == 0.026493052593642232
