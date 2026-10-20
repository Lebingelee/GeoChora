"""B04b Source-to-TaskArtifact-v1 compiler and strict version dispatch."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from task_env.artifacts import (
    ActionIntent,
    ArticulationDefinition,
    AssetDefinition,
    EntityDefinition,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    InitializationContract,
    PoseWorld,
    RequiredCapabilitySet,
    RobotInstance,
    SceneDefinition,
    SemanticDefinition,
    TaskArtifact,
    TaskArtifactV1,
    Timebase,
    WorldDefinition,
    decode_task_artifact,
)
from task_env.environment import (
    TaskRoleDeclarationV1,
    TaskSourceV1,
    compile_task_artifact_v1,
)


def _scene() -> SceneDefinition:
    assets = (
        AssetDefinition("asset-definition-v1", "robot-asset", "v1", "test://robot"),
        AssetDefinition("asset-definition-v1", "block-asset", "v1", "test://block"),
    )
    entities = (
        EntityInstance("entity-instance-v1", "robot-a", "robot-asset", "v1"),
        EntityInstance("entity-instance-v1", "block-a", "block-asset", "v1"),
    )
    frame = FrameDefinition("frame-definition-v1", "robot-a", "base", "runtime", None, None)
    articulation = ArticulationDefinition(
        "articulation-definition-v1", "robot-a", "base", ("base",), (),
    )
    robot = RobotInstance("robot-instance-v1", "robot-a", (FrameReference("robot-a", "base"),))
    return SceneDefinition(
        "scene-definition-v3", "b04b-scene", assets, entities,
        (frame,), (articulation,), (robot,), (), (),
    )


def _legacy_artifact() -> TaskArtifact:
    return TaskArtifact(
        "task-artifact-v0", "b04b-probe-v0", "b04b-probe", "v0",
        WorldDefinition(
            "world-v0", "SI_right_handed_z_up_wxyz",
            (
                EntityDefinition("robot-a", "embodiment", "test://robot", ("robot-a/base",), (),
                                 "articulated", "retained", {}),
                EntityDefinition("block-a", "movable", "test://block", (), (),
                                 "box", "retained", {}),
            ),
            ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            ("canonical-state-v0",), (),
        ),
        InitializationContract(
            "initialization-v0", {"block-a": PoseWorld((0.0, 0.0, 0.1), (1.0, 0.0, 0.0, 0.0))},
            {}, (), "zero_named_joint_and_entity_velocities", "fixed-probe", 0,
        ),
        SemanticDefinition("semantics-v0", "b04b_probe", ("block-a",), (), {}, "lifted"),
        Timebase(0.002, 1, 0.002),
        RequiredCapabilitySet(("rigid_body", "articulated_robot", "joint_state_query")),
    )


def _source() -> TaskSourceV1:
    return TaskSourceV1(
        "b04b-probe", "v0", "b04b-scene",
        (
            TaskRoleDeclarationV1("manipulator", "robot", "ids", ("robot-a",), "exactly_one"),
            TaskRoleDeclarationV1("target", "rigid_body", "ids", ("block-a",), "exactly_one"),
        ),
        None,
    )


def test_source_compiles_to_v1_without_copying_scene_or_execution_provenance():
    source, scene, legacy = _source(), _scene(), _legacy_artifact()
    compiled = compile_task_artifact_v1(source, scene, legacy)

    assert compiled.schema_version == "task-artifact-v1"
    assert compiled.task_source_mapping == source.to_mapping()
    assert compiled.task_source_identity_hash == source.identity_hash
    assert compiled.scene_schema_version == scene.schema_version
    assert compiled.scene_id == scene.scene_id
    assert compiled.scene_identity_hash == scene.identity_hash
    assert compiled.legacy_frame_bindings == {"robot-a/base": FrameReference("robot-a", "base")}
    assert compiled.legacy_joint_bindings == {}
    assert compiled.source_artifact_identity_hash == legacy.identity_hash
    assert compiled.source_retained_v0_fields == (
        "/world/entities/0/kind", "/world/entities/0/asset_reference",
        "/world/entities/0/geometry", "/world/entities/0/collision_intent",
        "/world/entities/0/parameters_si", "/world/entities/1/kind",
        "/world/entities/1/asset_reference", "/world/entities/1/geometry",
        "/world/entities/1/collision_intent", "/world/entities/1/parameters_si",
    )
    assert compiled.action == legacy.world.action
    assert compiled.world_convention == legacy.world.convention
    assert compiled.initialization == legacy.initialization
    assert compiled.semantics == legacy.semantics
    assert compiled.timebase == legacy.timebase
    assert compiled.required_capabilities == legacy.required_capabilities
    assert "world" not in compiled.to_mapping()
    assert "execution" not in compiled.to_mapping()

    raw = compiled.to_mapping()
    assert decode_task_artifact(raw) == compiled
    assert TaskArtifactV1.from_mapping(raw).identity_hash == compiled.identity_hash
    assert hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest() == compiled.identity_hash


def test_v1_codec_rejects_identity_drift_unknown_fields_and_implicit_v0_upgrade():
    compiled = compile_task_artifact_v1(_source(), _scene(), _legacy_artifact())
    raw = compiled.to_mapping()

    with pytest.raises(ValueError, match="Source snapshot identity mismatch"):
        TaskArtifactV1.from_mapping({**raw, "task_source_identity_hash": "0" * 64})
    with pytest.raises(ValueError, match="unknown TaskArtifactV1 fields"):
        TaskArtifactV1.from_mapping({**raw, "world": _legacy_artifact().world.to_mapping()})
    with pytest.raises(ValueError, match="unknown ActionIntent fields"):
        TaskArtifactV1.from_mapping(
            {**raw, "action": {**raw["action"], "unrecognized": True}}
        )
    with pytest.raises(ValueError, match="unknown InitializationContract fields"):
        TaskArtifactV1.from_mapping(
            {
                **raw,
                "initialization": {
                    **raw["initialization"],
                    "unrecognized": True,
                },
            }
        )
    with pytest.raises(ValueError, match="unsupported TaskArtifact schema"):
        decode_task_artifact({**raw, "schema_version": "task-artifact-v9"})

    legacy = _legacy_artifact()
    assert decode_task_artifact(legacy.to_mapping()) == legacy
    with pytest.raises(ValueError, match="unknown TaskArtifact fields"):
        TaskArtifact.from_mapping({**raw, "schema_version": "task-artifact-v0"})

    fixture = Path(__file__).with_name("fixtures") / "phase_ii_b04a" / "pick_cube_task_artifact_v0.json"
    frozen = decode_task_artifact(json.loads(fixture.read_text(encoding="utf-8")))
    assert isinstance(frozen, TaskArtifact)
    assert frozen.identity_hash == "fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4"


def test_compiler_rejects_scene_source_and_legacy_topology_mismatch():
    source, scene, legacy = _source(), _scene(), _legacy_artifact()
    with pytest.raises(ValueError, match="Scene reference"):
        compile_task_artifact_v1(replace(source, scene_ref="other-scene"), scene, legacy)

    wrong_source = replace(source, task_id="other-task")
    with pytest.raises(ValueError, match="Task Source identity"):
        compile_task_artifact_v1(wrong_source, scene, legacy)

    wrong_legacy = replace(
        legacy,
        world=replace(
            legacy.world,
            entities=tuple(
                replace(entity, frames=("robot-a/missing",)) if entity.semantic_id == "robot-a" else entity
                for entity in legacy.world.entities
            ),
        ),
    )
    with pytest.raises(ValueError, match="no valid canonical Scene binding"):
        compile_task_artifact_v1(source, scene, wrong_legacy)


def test_compiler_rejects_rigid_body_role_for_scene_kind_legacy_entity():
    source, scene, legacy = _source(), _scene(), _legacy_artifact()
    wrong_kind = replace(
        legacy,
        world=replace(
            legacy.world,
            entities=tuple(
                replace(entity, kind="scene")
                if entity.semantic_id == "block-a"
                else entity
                for entity in legacy.world.entities
            ),
        ),
    )
    with pytest.raises(ValueError, match="rigid-body TaskArtifact Entity"):
        compile_task_artifact_v1(source, scene, wrong_kind)


def test_v1_codec_rejects_malformed_or_incomplete_source_retained_pointers():
    compiled = compile_task_artifact_v1(_source(), _scene(), _legacy_artifact())
    with pytest.raises(ValueError, match="source-retained v0 field pointer"):
        replace(
            compiled,
            source_retained_v0_fields=(
                "/world/entities/0/unrecognized",
                *compiled.source_retained_v0_fields[1:],
            ),
        )
    with pytest.raises(ValueError, match="complete legacy World Entity fields"):
        replace(
            compiled,
            source_retained_v0_fields=compiled.source_retained_v0_fields[:-1],
        )


def test_compiler_requires_explicit_binding_for_renamed_scene_frames():
    scene = _scene()
    mapping = scene.to_mapping()
    mapping["frames"][0]["frame_id"] = "root"
    mapping["articulations"][0]["root_frame_id"] = "root"
    mapping["articulations"][0]["link_frame_ids"] = ["root"]
    mapping["robots"][0]["articulation_roots"] = [FrameReference("robot-a", "root").to_mapping()]
    renamed_scene = SceneDefinition.from_mapping(mapping)

    with pytest.raises(ValueError, match="no valid canonical Scene binding"):
        compile_task_artifact_v1(_source(), renamed_scene, _legacy_artifact())

    compiled = compile_task_artifact_v1(
        _source(), renamed_scene, _legacy_artifact(),
        frame_bindings={"robot-a/base": FrameReference("robot-a", "root")},
    )
    assert compiled.legacy_frame_bindings["robot-a/base"] == FrameReference("robot-a", "root")
    assert TaskArtifactV1.from_mapping(compiled.to_mapping()).identity_hash == compiled.identity_hash
