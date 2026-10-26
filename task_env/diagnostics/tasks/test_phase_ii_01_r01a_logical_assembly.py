"""Provider-free S1 for the versioned static Logical Assembly value contract."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import (
    ActuatorReference,
    FrameReference,
    JointReference,
    LogicalAssemblyControlGroupReferenceV1,
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblyNestedMemberV1,
    LogicalAssemblyScenePinV1,
    LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
    decode_logical_assembly,
)


SCENE_HASH = "a" * 64
CHILD_HASH = "b" * 64
PIN = LogicalAssemblyScenePinV1(
    "logical-assembly-scene-pin-v1",
    "scene-main",
    "scene-definition-v3",
    SCENE_HASH,
)


def _entity_member(*, path=("arm",), entity_id="arm", asset_version="v1"):
    return LogicalAssemblyEntityMemberV1(
        "entity_member", path, entity_id, "robot/panda", asset_version
    )


def _subref(path=("arm", "base"), target=None, target_kind="frame"):
    return LogicalAssemblySubcomponentReferenceV1(
        "existing_entity_subcomponent_ref",
        path,
        target_kind,
        target or FrameReference("arm", "base"),
    )


def _nested(*, path=("tool",), revision="r1", content_hash=CHILD_HASH):
    return LogicalAssemblyNestedMemberV1(
        "nested_assembly", path, "toolkit", revision, content_hash
    )


def _assembly(*, assembly_id="robot-assembly", revision="r1", scene_pin=PIN,
              members=None):
    return LogicalAssemblyV1(
        "logical-assembly-v1",
        assembly_id,
        revision,
        scene_pin,
        tuple(members if members is not None else (
            _entity_member(), _subref(), _nested(),
        )),
    )


def test_two_member_kinds_all_typed_targets_and_nested_pin_roundtrip():
    typed = (
        _subref(("frame",), FrameReference("arm", "hand"), "frame"),
        _subref(("joint",), JointReference("arm", "finger"), "joint"),
        _subref(("actuator",), ActuatorReference("arm", "gripper"), "actuator"),
        _subref(
            ("group",),
            LogicalAssemblyControlGroupReferenceV1("arm", "hand"),
            "control_group",
        ),
    )
    assembly = _assembly(members=(_entity_member(), *typed, _nested()))
    decoded = decode_logical_assembly(assembly.to_mapping())

    assert decoded == assembly
    assert {member.member_kind for member in decoded.members} == {
        "entity_member", "existing_entity_subcomponent_ref", "nested_assembly"
    }
    assert {
        member.target_kind for member in decoded.members
        if isinstance(member, LogicalAssemblySubcomponentReferenceV1)
    } == {"frame", "joint", "actuator", "control_group"}
    nested = next(member for member in decoded.members if isinstance(member, LogicalAssemblyNestedMemberV1))
    assert (nested.assembly_id, nested.revision, nested.logical_content_sha256) == (
        "toolkit", "r1", CHILD_HASH
    )


def test_identity_hash_is_fixed_canonical_and_excludes_its_own_digest():
    expected_payload = {
        "schema_version": "logical-assembly-v1",
        "assembly_id": "robot-assembly",
        "revision": "r1",
        "scene_pin": {
            "schema_version": "logical-assembly-scene-pin-v1",
            "scene_id": "scene-main",
            "scene_schema_version": "scene-definition-v3",
            "scene_identity_sha256": SCENE_HASH,
        },
        "members": [
            {
                "member_kind": "entity_member",
                "component_path": ["arm"],
                "entity_id": "arm",
                "asset_id": "robot/panda",
                "asset_version": "v1",
            },
            {
                "member_kind": "existing_entity_subcomponent_ref",
                "component_path": ["arm", "base"],
                "target_kind": "frame",
                "target": {"entity_id": "arm", "frame_id": "base"},
            },
            {
                "member_kind": "nested_assembly",
                "component_path": ["tool"],
                "assembly_id": "toolkit",
                "revision": "r1",
                "logical_content_sha256": CHILD_HASH,
            },
        ],
    }
    expected_digest = "c778b8e4afced57dac096fe6f711829effa83b2d6e42d26ad2612588bcda6f43"
    canonical = json.dumps(expected_payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assembly = _assembly()

    assert assembly.to_mapping() == expected_payload
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected_digest
    assert assembly.identity_hash == expected_digest
    assert assembly.logical_content_sha256 == expected_digest
    assert "identity_hash" not in assembly.to_mapping()
    assert "logical_content_sha256" not in assembly.to_mapping()


def test_member_order_does_not_change_canonical_mapping_or_identity():
    ordered = (_entity_member(), _subref(), _nested())
    reversed_assembly = _assembly(members=tuple(reversed(ordered)))
    normal_assembly = _assembly(members=ordered)
    assert reversed_assembly.to_mapping() == normal_assembly.to_mapping()
    assert reversed_assembly.identity_hash == normal_assembly.identity_hash


@pytest.mark.parametrize(
    "changed",
    [
        {"assembly_id": "renamed-assembly"},
        {"revision": "r2"},
        {"scene_pin": LogicalAssemblyScenePinV1(
            "logical-assembly-scene-pin-v1", "scene-other", "scene-definition-v3", SCENE_HASH
        )},
        {"scene_pin": LogicalAssemblyScenePinV1(
            "logical-assembly-scene-pin-v1", "scene-main", "scene-definition-v3", "c" * 64
        )},
        {"scene_pin": LogicalAssemblyScenePinV1(
            "logical-assembly-scene-pin-v1", "scene-main", "scene-definition-v2", SCENE_HASH
        )},
        {"members": (_entity_member(asset_version="v2"), _subref(), _nested())},
        {"members": (_entity_member(), _subref(target=FrameReference("arm", "tool")), _nested())},
        {"members": (_entity_member(), _subref(), _nested(content_hash="c" * 64))},
    ],
)
def test_identity_changes_with_declared_identity_and_typed_reference(changed):
    original = _assembly()
    values = {
        "assembly_id": "robot-assembly",
        "revision": "r1",
        "scene_pin": PIN,
        "members": (_entity_member(), _subref(), _nested()),
    }
    values.update(changed)
    assert _assembly(**values).identity_hash != original.identity_hash


def test_mapping_input_and_output_are_detached_from_identity():
    raw = _assembly().to_mapping()
    decoded = decode_logical_assembly(raw)
    digest = decoded.identity_hash
    raw["members"][0]["component_path"].append("mutated")
    raw["members"].append({"member_kind": "unknown"})
    assert decoded.identity_hash == digest

    exported = decoded.to_mapping()
    exported["scene_pin"]["scene_id"] = "mutated"
    exported["members"][0]["component_path"][0] = "mutated"
    assert decoded.identity_hash == digest
    with pytest.raises((AttributeError, TypeError)):
        decoded.members[0].component_path[0] = "mutated"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.update(unexpected=True),
        lambda m: m.pop("scene_pin"),
        lambda m: m.update(schema_version="logical-assembly-v2"),
        lambda m: m["members"][0].update(asset_version=True),
        lambda m: m["members"][0].update(target_kind="frame"),
        lambda m: m["members"][1].update(target_kind="future_target"),
        lambda m: m["members"][1]["target"].update(joint_id="cross_kind"),
        lambda m: m["members"][2].update(logical_content_sha256="A" * 64),
        lambda m: m["members"].append({"member_kind": "future_member"}),
    ],
)
def test_strict_dispatch_rejects_unknown_missing_cross_kind_and_bad_values(mutate):
    values = _assembly().to_mapping()
    mutate(values)
    with pytest.raises((TypeError, ValueError)):
        decode_logical_assembly(values)


@pytest.mark.parametrize("path", [(), ("",), ("." ,), ("..",), ("arm/hand",), ("arm\\hand",), ("%2f",)])
def test_component_paths_reject_empty_or_ambiguous_segments(path):
    with pytest.raises(ValueError, match="component_path|segment|nonempty string"):
        _entity_member(path=path)


def test_duplicate_paths_and_duplicate_same_level_targets_are_rejected():
    with pytest.raises(ValueError, match="component_path"):
        _assembly(members=(_entity_member(), _subref(path=("arm",))))
    with pytest.raises(ValueError, match="duplicate logical member target"):
        _assembly(members=(
            _entity_member(path=("arm",)),
            _entity_member(path=("arm-alias",)),
        ))
    with pytest.raises(ValueError, match="duplicate logical member target"):
        _assembly(members=(
            _nested(path=("left",), content_hash="b" * 64),
            _nested(path=("right",), content_hash="c" * 64),
        ))


def test_static_artifact_import_and_codec_do_not_load_provider_runtime():
    code = r'''
import sys
from task_env.artifacts import LogicalAssemblyV1, decode_logical_assembly
values = {
    "schema_version": "logical-assembly-v1",
    "assembly_id": "assembly",
    "revision": "r1",
    "scene_pin": {
        "schema_version": "logical-assembly-scene-pin-v1",
        "scene_id": "scene",
        "scene_schema_version": "scene-definition-v3",
        "scene_identity_sha256": "a" * 64,
    },
    "members": [],
}
assert isinstance(decode_logical_assembly(values), LogicalAssemblyV1)
for name in sys.modules:
    assert name.split(".", 1)[0] not in {"mujoco", "geophys", "taichi", "solvers"}, name
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[3],
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3]), PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_public_api_documented_minimal_example():
    from task_env.artifacts import AssetDefinition, EntityInstance, SceneDefinition

    asset = AssetDefinition(
        "asset-definition-v1", "robot/panda", "v1", "procedural://example/panda"
    )
    entity = EntityInstance("entity-instance-v1", "arm", "robot/panda", "v1")
    scene = SceneDefinition("scene-definition-v1", "example-scene", (asset,), (entity,))
    assembly = LogicalAssemblyV1(
        "logical-assembly-v1",
        "robot-assembly",
        "r1",
        LogicalAssemblyScenePinV1(
            "logical-assembly-scene-pin-v1",
            scene.scene_id,
            scene.schema_version,
            scene.identity_hash,
        ),
        (_entity_member(),),
    )
    assert decode_logical_assembly(assembly.to_mapping()) == assembly
