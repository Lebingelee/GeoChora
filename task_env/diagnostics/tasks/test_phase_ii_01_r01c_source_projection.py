"""Provider-free S1 for logical Assembly to existing Scene source projection."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import (
    AssetDefinition,
    EntityInstance,
    FrameReference,
    JointReference,
    ActuatorReference,
    LogicalAssemblyControlGroupReferenceV1,
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblyScenePinV1,
    LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
    SceneDefinition,
)
from task_env.assembly import project_logical_assembly_source


ROOT = Path(__file__).resolve().parents[3]
MENAGERIE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
ARM_XML_SHA256 = "e7090a5e2384b18a223ef532d98bf914f7f9a6b74dc8bc9f74c8291201074071"
HAND_XML_SHA256 = "d2a6539d0fd7c55c75c14f11c78f04505ee33f31d93e6112e3ad7120e5ee786a"


def _scene_pin(scene: SceneDefinition) -> LogicalAssemblyScenePinV1:
    return LogicalAssemblyScenePinV1(
        "logical-assembly-scene-pin-v1", scene.scene_id, scene.schema_version, scene.identity_hash
    )


def _entity_member(entity_id: str, asset_id: str, asset_version: str, *path: str):
    return LogicalAssemblyEntityMemberV1(
        "entity_member", tuple(path), entity_id, asset_id, asset_version
    )


def _reference(path, target_kind, target):
    return LogicalAssemblySubcomponentReferenceV1(
        "existing_entity_subcomponent_ref", tuple(path), target_kind, target
    )


def _assembly(scene, members, *, assembly_id="projection-root"):
    return LogicalAssemblyV1(
        "logical-assembly-v1", assembly_id, "r1", _scene_pin(scene), tuple(members)
    )


def _a05_scene():
    path = ROOT / "task_env/tasks/position_candidate/assets/a05_scene_definition_v3.json"
    return SceneDefinition.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def _independent_scene(*, shared_asset=False):
    arm_asset = AssetDefinition(
        "asset-definition-v1", "panda-arm-source", "menagerie-nohand-v1",
        "mujoco-menagerie://franka_emika_panda/panda_nohand.xml",
        source_revision=MENAGERIE_REVISION, source_content_sha256=ARM_XML_SHA256,
        license_id="Apache-2.0",
    )
    hand_asset = arm_asset if shared_asset else AssetDefinition(
        "asset-definition-v1", "panda-hand-source", "menagerie-hand-v1",
        "mujoco-menagerie://franka_emika_panda/hand.xml",
        source_revision=MENAGERIE_REVISION, source_content_sha256=HAND_XML_SHA256,
        license_id="Apache-2.0",
    )
    hand_asset_id = arm_asset.asset_id if shared_asset else hand_asset.asset_id
    hand_version = arm_asset.asset_version if shared_asset else hand_asset.asset_version
    assets = (arm_asset,) if shared_asset else (arm_asset, hand_asset)
    return SceneDefinition(
        "scene-definition-v1", "independent-arm-hand-source-scene", assets,
        (
            EntityInstance("entity-instance-v1", "panda-arm", arm_asset.asset_id, arm_asset.asset_version),
            EntityInstance("entity-instance-v1", "panda-hand", hand_asset_id, hand_version),
        ),
    )


def _independent_root(scene):
    return _assembly(scene, (
        _entity_member("panda-arm", scene.entities[0].asset_id, scene.entities[0].asset_version, "arm"),
        _entity_member("panda-hand", scene.entities[1].asset_id, scene.entities[1].asset_version, "hand"),
    ))


def test_a05_full_panda_projects_arm_and_gripper_views_with_historical_receipt():
    scene = _a05_scene()
    root = _assembly(scene, (
        _entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "panda"),
        _reference(("arm-view",), "control_group", LogicalAssemblyControlGroupReferenceV1("panda-main", "arm")),
        _reference(("gripper-view",), "control_group", LogicalAssemblyControlGroupReferenceV1("panda-main", "gripper")),
    ), assembly_id="a05-panda-logical-view")
    receipt = json.loads((
        ROOT / "task_env/tasks/position_candidate/assets/panda_source_receipt.json"
    ).read_text(encoding="utf-8"))

    result = project_logical_assembly_source(
        root, scene, {}, source_receipts={("panda-v1", "mujoco-menagerie-panda"): receipt}
    )
    snapshot = result.to_mapping()
    assert len(result.entities) == 1
    assert {leaf.target_kind for leaf in result.leaves} == {"entity", "control_group"}
    groups = {leaf.target_definition.group_id: leaf for leaf in result.leaves if leaf.target_kind == "control_group"}
    assert tuple(ref.actuator_id for ref in groups["arm"].target_definition.actuator_refs) == tuple(
        item.actuator_id for item in groups["arm"].group_actuator_definitions
    )
    assert tuple(item.actuator_id for item in groups["gripper"].group_actuator_definitions) == ("actuator8",)
    assert result.entities[0].asset.source_content_sha256 is None
    assert result.entities[0].evidence_status == "MATCHED_DECLARATION_NOT_REVALIDATED"
    assert snapshot["entities"][0]["source_receipt"]["evidence_status"] == "MATCHED_DECLARATION_NOT_REVALIDATED"
    assert "source_closure_digest" not in snapshot["entities"][0]["asset_definition"]


def test_independent_arm_and_hand_entities_retain_distinct_source_declarations():
    scene = _independent_scene()
    result = project_logical_assembly_source(_independent_root(scene), scene, {})
    entities = {item.entity.entity_id: item for item in result.entities}
    assert set(entities) == {"panda-arm", "panda-hand"}
    assert entities["panda-arm"].asset.source_reference.endswith("panda_nohand.xml")
    assert entities["panda-arm"].asset.source_content_sha256 == ARM_XML_SHA256
    assert entities["panda-hand"].asset.source_reference.endswith("hand.xml")
    assert entities["panda-hand"].asset.source_content_sha256 == HAND_XML_SHA256
    assert all(item.asset.source_revision == MENAGERIE_REVISION for item in entities.values())
    assert all(item.evidence_status == "DECLARED_ONLY_NOT_BYTE_VERIFIED" for item in entities.values())
    assert [leaf.entity_id for leaf in result.leaves] == ["panda-arm", "panda-hand"]
    assert all("robots" not in leaf.to_mapping() for leaf in result.leaves)


def test_four_typed_targets_resolve_to_exact_a05_scene_definitions():
    scene = _a05_scene()
    root = _assembly(scene, (
        _entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "owner"),
        _reference(("frame-view",), "frame", FrameReference("panda-main", "link7")),
        _reference(("joint-view",), "joint", JointReference("panda-main", "joint7")),
        _reference(("actuator-view",), "actuator", ActuatorReference("panda-main", "actuator1")),
        _reference(("group-view",), "control_group", LogicalAssemblyControlGroupReferenceV1("panda-main", "arm")),
    ))
    result = project_logical_assembly_source(root, scene, {})
    by_kind = {leaf.target_kind: leaf for leaf in result.leaves}
    assert type(by_kind["frame"].target_definition).__name__ == "FrameDefinition"
    assert type(by_kind["joint"].target_definition).__name__ == "JointDefinition"
    assert type(by_kind["actuator"].target_definition).__name__ == "ActuatorResourceDefinition"
    assert type(by_kind["control_group"].target_definition).__name__ == "ControlGroup"
    assert by_kind["control_group"].group_actuator_definitions
    assert len(result.entities) == 1


def test_same_asset_does_not_merge_distinct_scene_entities_and_reference_only_stays_read_only():
    scene = _independent_scene(shared_asset=True)
    owner_root = _independent_root(scene)
    owners = project_logical_assembly_source(owner_root, scene, {})
    assert [item.entity.entity_id for item in owners.entities] == ["panda-arm", "panda-hand"]
    assert owners.entities[0].asset.identity_hash == owners.entities[1].asset.identity_hash

    reference_only = _assembly(scene, (
        _reference(("hand-frame-view",), "frame", FrameReference("panda-hand", "hand")),
    ), assembly_id="reference-only-root")
    # The Scene-v1 version correctly rejects typed Frame refs before projection.
    with pytest.raises(ValueError, match="Scene v2 or v3"):
        project_logical_assembly_source(reference_only, scene, {})


def test_a05_reference_only_leaf_does_not_create_an_owner_or_writer():
    scene = _a05_scene()
    root = _assembly(scene, (
        _reference(("gripper-view",), "control_group", LogicalAssemblyControlGroupReferenceV1("panda-main", "gripper")),
    ), assembly_id="reference-only-a05")
    result = project_logical_assembly_source(root, scene, {})
    mapping = result.to_mapping()
    assert [entity.entity.entity_id for entity in result.entities] == ["panda-main"]
    assert mapping["leaves"][0]["member"]["member_kind"] == "existing_entity_subcomponent_ref"
    assert "owner" not in mapping["leaves"][0]
    assert "writer" not in mapping["leaves"][0]
    assert "robots" not in mapping["leaves"][0]


def test_wrong_scene_pin_child_hash_asset_and_source_receipt_alias_are_rejected():
    scene = _a05_scene()
    root = _assembly(scene, (_entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "panda"),))
    changed_scene_mapping = scene.to_mapping()
    changed_scene_mapping["scene_id"] = "different-scene"
    changed_scene = SceneDefinition.from_mapping(changed_scene_mapping)
    with pytest.raises(ValueError, match="scene pin mismatch"):
        project_logical_assembly_source(root, changed_scene, {})

    # A nested child with a wrong pinned digest is rejected by the existing resolver.
    from task_env.artifacts import LogicalAssemblyNestedMemberV1
    child = _assembly(scene, (_entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "owner"),), assembly_id="child")
    nested = LogicalAssemblyNestedMemberV1(
        "nested_assembly", ("nested",), child.assembly_id, child.revision, "0" * 64
    )
    bad_hash_root = _assembly(scene, (nested,), assembly_id="bad-child-hash")
    with pytest.raises(ValueError, match="hash"):
        project_logical_assembly_source(bad_hash_root, scene, {(child.assembly_id, child.revision): child})
    missing_child_member = LogicalAssemblyNestedMemberV1(
        "nested_assembly", ("nested",), child.assembly_id, child.revision, child.logical_content_sha256
    )
    missing_child_root = _assembly(scene, (missing_child_member,), assembly_id="missing-child")
    with pytest.raises(ValueError, match="missing child Assembly"):
        project_logical_assembly_source(missing_child_root, scene, {})

    wrong_asset_root = _assembly(scene, (
        _entity_member("panda-main", "wrong-asset", "mujoco-menagerie-panda", "panda"),
    ), assembly_id="wrong-asset-root")
    with pytest.raises(ValueError, match="asset identity"):
        project_logical_assembly_source(wrong_asset_root, scene, {})

    receipt = json.loads((ROOT / "task_env/tasks/position_candidate/assets/panda_source_receipt.json").read_text())
    receipt["asset_declaration_identity"] = "f" * 64
    with pytest.raises(ValueError, match="Asset declaration identity"):
        project_logical_assembly_source(
            root, scene, {}, source_receipts={("panda-v1", "mujoco-menagerie-panda"): receipt}
        )
    with pytest.raises(ValueError, match="does not correspond"):
        project_logical_assembly_source(
            root, scene, {}, source_receipts={("unrelated", "v1"): receipt}
        )


def test_projector_re_resolves_current_inputs_and_does_not_accept_forged_resolved_receipt():
    scene = _a05_scene()
    root = _assembly(scene, (_entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "panda"),))
    result = project_logical_assembly_source(root, scene, {})
    with pytest.raises(TypeError, match="root must be a LogicalAssemblyV1"):
        project_logical_assembly_source(result, scene, {})


def test_order_identity_and_snapshots_are_stable_and_detached_after_failure():
    scene = _a05_scene()
    owner = _entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "panda")
    arm = _reference(("arm-view",), "control_group", LogicalAssemblyControlGroupReferenceV1("panda-main", "arm"))
    gripper = _reference(("gripper-view",), "control_group", LogicalAssemblyControlGroupReferenceV1("panda-main", "gripper"))
    first = _assembly(scene, (owner, arm, gripper), assembly_id="ordered-root")
    second = _assembly(scene, (gripper, owner, arm), assembly_id="ordered-root")
    projected_first = project_logical_assembly_source(first, scene, {})
    projected_second = project_logical_assembly_source(second, scene, {})
    assert projected_first.to_mapping() == projected_second.to_mapping()
    assert projected_first.identity_sha256 == projected_second.identity_sha256
    original = projected_first.to_mapping()
    edited = projected_first.to_mapping()
    edited["leaves"].clear()
    assert projected_first.to_mapping() == original
    with pytest.raises((AttributeError, TypeError)):
        projected_first.entities = ()
    with pytest.raises(ValueError):
        changed = scene.to_mapping()
        changed["scene_id"] = "broken"
        project_logical_assembly_source(first, SceneDefinition.from_mapping(changed), {})
    assert project_logical_assembly_source(first, scene, {}).to_mapping() == original


def test_static_entrypoint_never_calls_legacy_compile_path(monkeypatch):
    import task_env.assembly as assembly_api
    from task_env.assembly import compiler

    assert "project_logical_assembly_source" in assembly_api.__all__

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy Provider compile path must not run for static projection")

    monkeypatch.setattr(compiler, "compile_task_scene", forbidden)
    scene = _a05_scene()
    root = _assembly(scene, (_entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "panda"),))
    assert project_logical_assembly_source(root, scene, {}).scene_id == scene.scene_id


def test_static_projection_imports_no_provider_or_native_modules_in_subprocess():
    code = """
import json, sys
from task_env.assembly.compiler import project_logical_assembly_source
forbidden = sorted(name for name in sys.modules if name == 'mujoco' or name.startswith('mujoco.') or name in {'scene', 'geophys'} or name.startswith('geophys.'))
print(json.dumps(forbidden))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT}:" + str(ROOT / "GeoPhys/src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, check=True,
        capture_output=True, text=True, timeout=20,
    )
    assert json.loads(completed.stdout) == []


def test_projection_rejects_alias_typed_reference_and_dangling_member():
    scene = _a05_scene()
    with pytest.raises(ValueError, match="duplicate logical member target"):
        _assembly(scene, (
            _entity_member("panda-main", "panda-v1", "mujoco-menagerie-panda", "owner"),
            _reference(("one",), "frame", FrameReference("panda-main", "hand")),
            _reference(("two",), "frame", FrameReference("panda-main", "hand")),
        ), assembly_id="duplicate-target")

    dangling = _assembly(scene, (
        _entity_member("ghost", "ghost-asset", "v1", "ghost"),
    ), assembly_id="dangling-entity")
    with pytest.raises(ValueError, match="unknown Scene Entity"):
        project_logical_assembly_source(dangling, scene, {})


def test_documentation_minimal_example_executes():
    document = (ROOT / "docs/module/task_env/public-api.md").read_text(encoding="utf-8")
    marker = "<!-- R01C_EXECUTABLE_EXAMPLE_BEGIN -->"
    assert marker in document
    example = document.split(marker, 1)[1].split("<!-- R01C_EXECUTABLE_EXAMPLE_END -->", 1)[0]
    code = example.split("```python", 1)[1].split("```", 1)[0]
    exec(compile(code, "public-api.md:R01c-example", "exec"), {"__name__": "__main__"})
