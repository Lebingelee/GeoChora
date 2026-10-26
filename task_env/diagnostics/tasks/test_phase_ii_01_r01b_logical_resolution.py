"""Provider-free S1 for bounded recursive Logical Assembly resolution."""

import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap

import pytest

from task_env.artifacts import (
    ActuatorReference,
    ActuatorResourceDefinition,
    ArticulationDefinition,
    AssetDefinition,
    ControlGroup,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    JointReference,
    LogicalAssemblyControlGroupReferenceV1,
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblyNestedMemberV1,
    LogicalAssemblyScenePinV1,
    LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
    PoseWorld,
    RobotInstance,
    SceneDefinition,
    resolve_logical_assembly,
)


ROOT = Path(__file__).resolve().parents[3]
IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
SHARED_ASSET = "robot/shared"


def _asset(asset_id=SHARED_ASSET, *, version="v1", source_revision=None):
    return AssetDefinition(
        "asset-definition-v1",
        asset_id,
        version,
        f"procedural://example/{asset_id}",
        source_revision=source_revision,
    )


def _entity(entity_id, asset_id=SHARED_ASSET, *, version="v1"):
    return EntityInstance("entity-instance-v1", entity_id, asset_id, version)


def _scene_v3(*, source_revision=None):
    entities = (_entity("arm"), _entity("hand"))
    frames = tuple(
        FrameDefinition("frame-definition-v1", entity.entity_id, frame_id, "runtime", None, None)
        for entity in entities
        for frame_id in ("base", "tool")
    )
    articulations = tuple(
        ArticulationDefinition(
            "articulation-definition-v1",
            entity.entity_id,
            "base",
            ("base", "tool"),
            (JointDefinition(
                "joint-definition-v1",
                "drive",
                FrameReference(entity.entity_id, "base"),
                FrameReference(entity.entity_id, "tool"),
                IDENTITY,
                IDENTITY,
                "revolute",
                (0.0, 0.0, 1.0),
                "radian",
                "radian_per_second",
                1,
                1,
            ),),
        )
        for entity in entities
    )
    actuators = (
        ActuatorResourceDefinition("actuator-resource-v1", "arm", "drive"),
        ActuatorResourceDefinition("actuator-resource-v1", "arm", "gripper"),
        ActuatorResourceDefinition("actuator-resource-v1", "hand", "drive"),
    )
    groups = (
        ControlGroup("control-group-v1", "arm", "arm-main", (ActuatorReference("arm", "drive"),)),
        ControlGroup("control-group-v1", "arm", "arm-hand", (ActuatorReference("arm", "gripper"),)),
        ControlGroup("control-group-v1", "hand", "hand-main", (ActuatorReference("hand", "drive"),)),
    )
    robots = tuple(
        RobotInstance("robot-instance-v1", entity.entity_id, (FrameReference(entity.entity_id, "base"),))
        for entity in entities
    )
    return SceneDefinition(
        "scene-definition-v3",
        "scene-main",
        (_asset(source_revision=source_revision),),
        entities,
        frames,
        articulations,
        robots,
        actuators,
        groups,
    )


def _scene_v2():
    entity = _entity("arm")
    frames = (
        FrameDefinition("frame-definition-v1", "arm", "base", "runtime", None, None),
        FrameDefinition("frame-definition-v1", "arm", "tool", "runtime", None, None),
    )
    joint = JointDefinition(
        "joint-definition-v1", "drive", FrameReference("arm", "base"),
        FrameReference("arm", "tool"), IDENTITY, IDENTITY, "revolute",
        (0.0, 0.0, 1.0), "radian", "radian_per_second", 1, 1,
    )
    articulation = ArticulationDefinition(
        "articulation-definition-v1", "arm", "base", ("base", "tool"), (joint,)
    )
    return SceneDefinition(
        "scene-definition-v2", "scene-main", (_asset(),), (entity,), frames, (articulation,)
    )


def _scene_v1(*, entity_ids=("arm",)):
    return SceneDefinition(
        "scene-definition-v1",
        "scene-main",
        (_asset(),),
        tuple(_entity(entity_id) for entity_id in entity_ids),
    )


def _pin(scene):
    return LogicalAssemblyScenePinV1(
        "logical-assembly-scene-pin-v1",
        scene.scene_id,
        scene.schema_version,
        scene.identity_hash,
    )


def _entity_member(entity_id, *, path=None, asset_id=SHARED_ASSET, asset_version="v1"):
    return LogicalAssemblyEntityMemberV1(
        "entity_member", path or (f"owner-{entity_id}",), entity_id, asset_id, asset_version
    )


def _sub(path, target, target_kind):
    return LogicalAssemblySubcomponentReferenceV1(
        "existing_entity_subcomponent_ref", tuple(path), target_kind, target
    )


def _nested(path, child, *, digest=None):
    return LogicalAssemblyNestedMemberV1(
        "nested_assembly",
        tuple(path),
        child.assembly_id,
        child.revision,
        child.logical_content_sha256 if digest is None else digest,
    )


def _assembly(scene, assembly_id, members=(), *, revision="r1", scene_pin=None):
    return LogicalAssemblyV1(
        "logical-assembly-v1", assembly_id, revision, scene_pin or _pin(scene), tuple(members)
    )


def _primary_closure(scene=None):
    scene = scene or _scene_v3()
    arm = _assembly(scene, "arm-leaf", (_entity_member("arm", path=("owner", "arm")),))
    hand = _assembly(scene, "hand-leaf", (_entity_member("hand", path=("owner", "hand")),))
    branch = _assembly(scene, "robot-branch", (
        _nested(("arm",), arm),
        _nested(("hand",), hand),
        _sub(("arm-base-view",), FrameReference("arm", "base"), "frame"),
        _sub(("arm-tool-view",), FrameReference("arm", "tool"), "frame"),
        _sub(("arm-drive-joint",), JointReference("arm", "drive"), "joint"),
        _sub(("arm-drive-actuator",), ActuatorReference("arm", "drive"), "actuator"),
        _sub(("arm-main-group",), LogicalAssemblyControlGroupReferenceV1("arm", "arm-main"), "control_group"),
        _sub(("arm-hand-group",), LogicalAssemblyControlGroupReferenceV1("arm", "arm-hand"), "control_group"),
        # This reference is read-only and points at the separately owned sibling hand leaf.
        _sub(("hand-group-view",), LogicalAssemblyControlGroupReferenceV1("hand", "hand-main"), "control_group"),
    ))
    root = _assembly(scene, "robot-root", (_nested(("robot",), branch),))
    return root, branch, arm, hand, {
        (branch.assembly_id, branch.revision): branch,
        (arm.assembly_id, arm.revision): arm,
        (hand.assembly_id, hand.revision): hand,
    }


def test_multilevel_resolution_preserves_typed_refs_sibling_views_and_distinct_entities(monkeypatch):
    scene = _scene_v3()
    root, _, arm, hand, catalog = _primary_closure(scene)

    def no_runtime_pose(*args, **kwargs):
        raise AssertionError("static resolution must not request a runtime Frame pose")

    monkeypatch.setattr(SceneDefinition, "resolve_frame_pose", no_runtime_pose)
    result = resolve_logical_assembly(root, scene, catalog)

    assert result.scene_identity_sha256 == scene.identity_hash
    assert result.root_logical_content_sha256 == root.logical_content_sha256
    assert [leaf.full_path for leaf in result.leaves] == sorted(leaf.full_path for leaf in result.leaves)
    owners = [leaf for leaf in result.leaves if leaf.member_kind == "entity_member"]
    assert {(leaf.member.entity_id, leaf.member.asset_id, leaf.member.asset_version) for leaf in owners} == {
        ("arm", SHARED_ASSET, "v1"), ("hand", SHARED_ASSET, "v1")
    }
    assert len({leaf.member.entity_id for leaf in owners}) == 2  # Same Asset, distinct Entity instances.
    references = [leaf for leaf in result.leaves if leaf.member_kind == "existing_entity_subcomponent_ref"]
    assert {leaf.member.target_kind for leaf in references} == {
        "frame", "joint", "actuator", "control_group"
    }
    assert {leaf.member.target.group_id for leaf in references if leaf.member.target_kind == "control_group"} == {
        "arm-main", "arm-hand", "hand-main"
    }
    assert any(
        leaf.member.target_kind == "control_group"
        and leaf.member.target.entity_id == "hand"
        and leaf.source_assembly_id == "robot-branch"
        for leaf in references
    )
    assert any(leaf.source_assembly_id == arm.assembly_id for leaf in owners)
    assert any(leaf.source_assembly_id == hand.assembly_id for leaf in owners)


def test_scene_v1_entity_only_and_scene_v2_frame_joint_paths_are_supported():
    scene_v1 = _scene_v1()
    root_v1 = _assembly(scene_v1, "v1-root", (_entity_member("arm"),))
    result_v1 = resolve_logical_assembly(root_v1, scene_v1, {})
    assert len(result_v1.leaves) == 1
    assert result_v1.leaves[0].member.entity_id == "arm"

    scene_v2 = _scene_v2()
    root_v2 = _assembly(scene_v2, "v2-root", (
        _entity_member("arm"),
        _sub(("runtime-frame",), FrameReference("arm", "tool"), "frame"),
        _sub(("joint",), JointReference("arm", "drive"), "joint"),
    ))
    result_v2 = resolve_logical_assembly(root_v2, scene_v2, {})
    assert {leaf.member_kind for leaf in result_v2.leaves} == {
        "entity_member", "existing_entity_subcomponent_ref"
    }


@pytest.mark.parametrize(
    "target_kind,target",
    [
        ("frame", FrameReference("arm", "tool")),
        ("joint", JointReference("arm", "drive")),
    ],
)
def test_scene_v1_rejects_structure_refs_without_synthesizing_v2(target_kind, target):
    scene = _scene_v1()
    root = _assembly(scene, "v1-structure-ref", (_sub(("view",), target, target_kind),))
    with pytest.raises(ValueError, match="require a Scene v2 or v3"):
        resolve_logical_assembly(root, scene, {})


@pytest.mark.parametrize(
    "pin_change",
    [
        {"scene_id": "scene-other"},
        {"scene_schema_version": "scene-definition-v2"},
        {"scene_identity_sha256": "f" * 64},
    ],
)
def test_wrong_root_scene_pin_is_rejected(pin_change):
    scene = _scene_v3()
    values = {
        "schema_version": "logical-assembly-scene-pin-v1",
        "scene_id": scene.scene_id,
        "scene_schema_version": scene.schema_version,
        "scene_identity_sha256": scene.identity_hash,
    }
    values.update(pin_change)
    root = _assembly(scene, "wrong-pin", (_entity_member("arm"),), scene_pin=LogicalAssemblyScenePinV1(**values))
    with pytest.raises(ValueError, match="scene pin mismatch"):
        resolve_logical_assembly(root, scene, {})


def test_asset_source_revision_change_invalidates_prior_scene_pin():
    original_scene = _scene_v3(source_revision="asset-rev-1")
    root = _assembly(original_scene, "pinned-root", (_entity_member("arm"),))
    changed_scene = _scene_v3(source_revision="asset-rev-2")
    assert original_scene.scene_id == changed_scene.scene_id
    assert original_scene.identity_hash != changed_scene.identity_hash
    with pytest.raises(ValueError, match="scene pin mismatch"):
        resolve_logical_assembly(root, changed_scene, {})


def test_reachable_child_scene_pin_is_checked_independently_of_root_pin():
    scene = _scene_v3()
    other_scene = _scene_v1()
    child = _assembly(other_scene, "child-wrong-scene", ())
    root = _assembly(scene, "root", (_nested(("child",), child),))
    with pytest.raises(ValueError, match="scene pin mismatch.*child-wrong-scene"):
        resolve_logical_assembly(root, scene, {(child.assembly_id, child.revision): child})


def test_entity_and_asset_identity_are_exact():
    scene = _scene_v3()
    cases = (
        _entity_member("missing"),
        _entity_member("arm", asset_id="robot/other"),
        _entity_member("arm", asset_version="v2"),
    )
    for member in cases:
        root = _assembly(scene, "entity-check", (member,))
        with pytest.raises(ValueError):
            resolve_logical_assembly(root, scene, {})


@pytest.mark.parametrize(
    "target_kind,target",
    [
        ("frame", FrameReference("ghost", "tool")),
        ("joint", JointReference("ghost", "drive")),
        ("actuator", ActuatorReference("ghost", "drive")),
        ("control_group", LogicalAssemblyControlGroupReferenceV1("ghost", "arm-main")),
    ],
)
def test_each_typed_reference_rejects_unknown_entity(target_kind, target):
    scene = _scene_v3()
    root = _assembly(scene, "unknown-entity", (_sub(("view",), target, target_kind),))
    with pytest.raises(ValueError, match="unknown Scene Entity"):
        resolve_logical_assembly(root, scene, {})


@pytest.mark.parametrize(
    "target_kind,target",
    [
        ("frame", FrameReference("arm", "missing")),
        ("joint", JointReference("arm", "missing")),
        ("actuator", ActuatorReference("arm", "missing")),
        ("control_group", LogicalAssemblyControlGroupReferenceV1("arm", "missing")),
    ],
)
def test_each_typed_reference_rejects_missing_entity_qualified_target(target_kind, target):
    scene = _scene_v3()
    root = _assembly(scene, "missing-target", (_sub(("view",), target, target_kind),))
    with pytest.raises((KeyError, ValueError)):
        resolve_logical_assembly(root, scene, {})


def test_entity_qualified_actuator_does_not_fall_back_to_same_name_on_other_entity():
    scene = _scene_v3()
    root = _assembly(scene, "wrong-entity-resource", (
        _sub(("view",), ActuatorReference("hand", "gripper"), "actuator"),
    ))
    with pytest.raises(KeyError, match="unknown entity-qualified actuator"):
        resolve_logical_assembly(root, scene, {})


def test_malformed_typed_target_kind_is_rejected_by_strict_redecode():
    scene = _scene_v3()
    malformed = _sub(("view",), FrameReference("arm", "tool"), "frame")
    object.__setattr__(malformed, "target_kind", "joint")
    root = _assembly(scene, "wrong-target-kind", (malformed,))
    with pytest.raises((TypeError, ValueError)):
        resolve_logical_assembly(root, scene, {})


def test_missing_child_wrong_catalog_key_wrong_revision_and_wrong_digest_are_rejected():
    scene = _scene_v3()
    child = _assembly(scene, "child", (_entity_member("arm"),))
    missing = _assembly(scene, "missing-root", (_nested(("child",), child),))
    with pytest.raises(ValueError, match="missing child Assembly"):
        resolve_logical_assembly(missing, scene, {})

    with pytest.raises(ValueError, match="catalog key"):
        resolve_logical_assembly(missing, scene, {("other", "r1"): child})

    wrong_revision = _assembly(scene, "wrong-revision-root", (
        LogicalAssemblyNestedMemberV1(
            "nested_assembly", ("child",), child.assembly_id, "r2", child.logical_content_sha256
        ),
    ))
    with pytest.raises(ValueError, match="missing child Assembly"):
        resolve_logical_assembly(wrong_revision, scene, {(child.assembly_id, child.revision): child})

    wrong_digest = _assembly(scene, "wrong-digest-root", (_nested(("child",), child, digest="f" * 64),))
    with pytest.raises(ValueError, match="digest mismatch"):
        resolve_logical_assembly(wrong_digest, scene, {(child.assembly_id, child.revision): child})


def test_wrong_child_type_conflicting_revision_and_root_substitution_are_rejected():
    scene = _scene_v3()
    child = _assembly(scene, "child", (_entity_member("arm"),))
    root = _assembly(scene, "root", (_nested(("child",), child),))
    with pytest.raises(TypeError, match="LogicalAssemblyV1"):
        resolve_logical_assembly(root, scene, {(child.assembly_id, child.revision): {"schema_version": "logical-assembly-v2"}})

    conflicting = _assembly(scene, "child", (_entity_member("hand"),))
    entries = [((child.assembly_id, child.revision), child), ((conflicting.assembly_id, conflicting.revision), conflicting)]
    with pytest.raises(ValueError, match="conflicting content"):
        resolve_logical_assembly(root, scene, entries)

    replacement = _assembly(scene, "root", (_entity_member("hand"),))
    with pytest.raises(ValueError, match="root Assembly key cannot be replaced"):
        resolve_logical_assembly(root, scene, {(root.assembly_id, root.revision): replacement,
                                               (child.assembly_id, child.revision): child})


def test_unknown_assembly_schema_is_rejected_on_detached_strict_redecode():
    scene = _scene_v3()
    root = _assembly(scene, "unknown-schema", (_entity_member("arm"),))
    object.__setattr__(root, "schema_version", "logical-assembly-v2")
    with pytest.raises(ValueError, match="unsupported logical Assembly schema"):
        resolve_logical_assembly(root, scene, {})


def test_equal_root_catalog_entry_is_not_a_second_owning_edge_and_unreachable_pins_are_not_checked():
    scene = _scene_v3()
    root = _assembly(scene, "root", (_entity_member("arm"),))
    unrelated_scene = _scene_v1()
    unrelated = _assembly(unrelated_scene, "unrelated", (_entity_member("arm"),))
    result = resolve_logical_assembly(
        root,
        scene,
        {(root.assembly_id, root.revision): root, (unrelated.assembly_id, unrelated.revision): unrelated},
    )
    assert len(result.leaves) == 1
    assert result.leaves[0].member.entity_id == "arm"


@pytest.mark.parametrize("cycle_kind", ["direct", "indirect"])
def test_containment_cycles_are_reported_before_hash_validation(cycle_kind):
    scene = _scene_v3()
    if cycle_kind == "direct":
        root = _assembly(scene, "root", (
            LogicalAssemblyNestedMemberV1("nested_assembly", ("again",), "root", "r1", "a" * 64),
        ))
        with pytest.raises(ValueError, match="containment cycle.*root@r1"):
            resolve_logical_assembly(root, scene, {})
    else:
        child = _assembly(scene, "child", (
            LogicalAssemblyNestedMemberV1("nested_assembly", ("back",), "root", "r1", "a" * 64),
        ))
        root = _assembly(scene, "root", (_nested(("child",), child),))
        with pytest.raises(ValueError, match="containment cycle.*root@r1"):
            resolve_logical_assembly(root, scene, {(child.assembly_id, child.revision): child})


def test_cross_level_duplicate_owners_and_typed_aliases_are_rejected():
    scene = _scene_v3()
    child_owner = _assembly(scene, "child-owner", (_entity_member("arm", path=("child-arm",)),))
    root_owner = _assembly(scene, "root-owner", (
        _entity_member("arm", path=("root-arm",)),
        _nested(("child",), child_owner),
    ))
    with pytest.raises(ValueError, match="multiple owning members"):
        resolve_logical_assembly(root_owner, scene, {(child_owner.assembly_id, child_owner.revision): child_owner})

    child_ref = _assembly(scene, "child-ref", (
        _sub(("nested-view",), FrameReference("arm", "tool"), "frame"),
    ))
    root_ref = _assembly(scene, "root-ref", (
        _sub(("direct-view",), FrameReference("arm", "tool"), "frame"),
        _nested(("child",), child_ref),
    ))
    with pytest.raises(ValueError, match="same typed target"):
        resolve_logical_assembly(root_ref, scene, {(child_ref.assembly_id, child_ref.revision): child_ref})


def test_expanded_path_collision_is_rejected_after_tuple_concatenation():
    scene = _scene_v3()
    child = _assembly(scene, "child", (_entity_member("hand", path=("b",)),))
    root = _assembly(scene, "root", (
        _nested(("a",), child),
        _entity_member("arm", path=("a", "b")),
    ))
    with pytest.raises(ValueError, match="path collision"):
        resolve_logical_assembly(root, scene, {(child.assembly_id, child.revision): child})


def _empty_chain(scene, depth):
    current = _assembly(scene, f"node-{depth - 1}")
    catalog = {}
    for index in range(depth - 2, -1, -1):
        catalog[(current.assembly_id, current.revision)] = current
        current = _assembly(scene, f"node-{index}", (_nested(("child",), current),))
    return current, catalog


def test_depth_32_succeeds_and_depth_33_fails():
    scene = _scene_v1()
    root32, catalog32 = _empty_chain(scene, 32)
    assert resolve_logical_assembly(root32, scene, catalog32).leaves == ()
    root33, catalog33 = _empty_chain(scene, 33)
    with pytest.raises(ValueError, match="depth exceeds 32"):
        resolve_logical_assembly(root33, scene, catalog33)


def test_leaf_1024_succeeds_and_leaf_1025_fails():
    def build(count):
        entity_ids = tuple(f"arm-{index:04d}" for index in range(count))
        scene = _scene_v1(entity_ids=entity_ids)
        members = tuple(
            _entity_member(entity_id, path=(f"member-{index:04d}",))
            for index, entity_id in enumerate(entity_ids)
        )
        return scene, _assembly(scene, f"leaf-root-{count}", members)

    scene1024, root1024 = build(1024)
    result = resolve_logical_assembly(root1024, scene1024, {})
    assert len(result.leaves) == 1024
    scene1025, root1025 = build(1025)
    with pytest.raises(ValueError, match="exceeds 1024 leaves"):
        resolve_logical_assembly(root1025, scene1025, {})


def test_subcomponent_references_also_count_toward_the_leaf_limit():
    def build(count):
        entity = _entity("arm")
        frames = tuple(
            FrameDefinition(
                "frame-definition-v1", "arm", f"frame-{index:04d}", "authored_fixed", None, IDENTITY
            )
            for index in range(count)
        )
        scene = SceneDefinition(
            "scene-definition-v2", "scene-main", (_asset(),), (entity,), frames, ()
        )
        members = tuple(
            _sub((f"view-{index:04d}",), FrameReference("arm", f"frame-{index:04d}"), "frame")
            for index in range(count)
        )
        return scene, _assembly(scene, f"reference-root-{count}", members)

    scene1024, root1024 = build(1024)
    assert len(resolve_logical_assembly(root1024, scene1024, {}).leaves) == 1024
    scene1025, root1025 = build(1025)
    with pytest.raises(ValueError, match="exceeds 1024 leaves"):
        resolve_logical_assembly(root1025, scene1025, {})


def test_shared_empty_child_is_memoized_and_unbounded_expansion_is_avoided():
    scene = _scene_v1()
    shared_empty = _assembly(scene, "shared-empty")
    left = _assembly(scene, "left", (_nested(("shared",), shared_empty),))
    right = _assembly(scene, "right", (_nested(("shared",), shared_empty),))
    root = _assembly(scene, "root", (
        _nested(("left",), left),
        _nested(("right",), right),
    ))
    catalog = {
        (left.assembly_id, left.revision): left,
        (right.assembly_id, right.revision): right,
        (shared_empty.assembly_id, shared_empty.revision): shared_empty,
    }
    assert resolve_logical_assembly(root, scene, catalog).leaves == ()


def test_declaration_and_catalog_order_do_not_change_result():
    scene = _scene_v3()
    root, branch, arm, hand, catalog = _primary_closure(scene)
    reversed_root = _assembly(scene, "robot-root", tuple(reversed(root.members)))
    assert root.identity_hash == reversed_root.identity_hash
    first = resolve_logical_assembly(root, scene, catalog)
    second = resolve_logical_assembly(reversed_root, scene, list(reversed(tuple(catalog.items()))))
    assert first == second


def test_result_and_input_snapshots_are_detached_and_failures_do_not_cache():
    scene = _scene_v3()
    root, _, _, _, catalog = _primary_closure(scene)
    bad_child = catalog[("arm-leaf", "r1")]
    bad_root = _assembly(scene, "bad-root", (_nested(("arm",), bad_child, digest="e" * 64),))
    with pytest.raises(ValueError, match="digest mismatch"):
        resolve_logical_assembly(bad_root, scene, catalog)

    result = resolve_logical_assembly(root, scene, catalog)
    before = tuple((leaf.full_path, leaf.source_logical_content_sha256) for leaf in result.leaves)
    snapshot = root.to_mapping()
    snapshot["members"].clear()
    with pytest.raises((AttributeError, TypeError)):
        result.leaves[0].full_path[0] = "mutated"
    with pytest.raises((AttributeError, TypeError)):
        result.leaves[0].member.member_kind = "mutated"
    assert tuple((leaf.full_path, leaf.source_logical_content_sha256) for leaf in result.leaves) == before
    assert resolve_logical_assembly(root, scene, catalog) == result


def test_public_documented_minimal_example_executes():
    document = (ROOT / "docs/module/task_env/public-api.md").read_text(encoding="utf-8")
    match = re.search(
        r"### Bounded Logical Assembly resolution \(R01b\)\s+```python\n(.*?)\n```",
        document,
        flags=re.DOTALL,
    )
    assert match is not None
    namespace = {}
    exec(compile(match.group(1), "public-api.md:R01b-example", "exec"), namespace, namespace)
    assert namespace["resolved"].leaves[0].full_path == ("robot", "arm")


def test_import_and_resolution_do_not_load_provider_or_native_modules_in_subprocess():
    script = textwrap.dedent(
        """
        import sys
        from task_env.artifacts import (
            AssetDefinition, EntityInstance, LogicalAssemblyEntityMemberV1,
            LogicalAssemblyScenePinV1, LogicalAssemblyV1, SceneDefinition,
            resolve_logical_assembly,
        )
        asset = AssetDefinition('asset-definition-v1', 'robot/test', 'v1', 'procedural://example/robot')
        entity = EntityInstance('entity-instance-v1', 'arm', 'robot/test', 'v1')
        scene = SceneDefinition('scene-definition-v1', 'scene-test', (asset,), (entity,))
        pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
            scene.schema_version, scene.identity_hash)
        root = LogicalAssemblyV1('logical-assembly-v1', 'root', 'r1', pin,
            (LogicalAssemblyEntityMemberV1('entity_member', ('arm',), 'arm', 'robot/test', 'v1'),))
        assert len(resolve_logical_assembly(root, scene, {}).leaves) == 1
        assert not {'mujoco', 'taichi', 'geophys'} & set(sys.modules)
        """
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "GeoPhys" / "src")))
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
