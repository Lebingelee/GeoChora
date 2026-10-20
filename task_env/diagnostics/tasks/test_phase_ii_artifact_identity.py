"""Provider-free S1 checks for the Phase II asset and scene identity contracts."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import AssetDefinition, EntityInstance, SceneDefinition


MENAGERIE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
PANDA_SOURCE = f"mujoco-menagerie://{MENAGERIE_REVISION}/franka_emika_panda/panda.xml"


def asset(
    *,
    asset_id="franka/panda",
    asset_version="menagerie-pinned",
    source_reference=PANDA_SOURCE,
    source_revision=MENAGERIE_REVISION,
    source_content_sha256=None,
):
    return AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id=asset_id,
        asset_version=asset_version,
        source_reference=source_reference,
        source_revision=source_revision,
        source_content_sha256=source_content_sha256,
        license_id="Apache-2.0",
    )


def entity(entity_id, *, asset_id="franka/panda", asset_version="menagerie-pinned"):
    return EntityInstance(
        schema_version="entity-instance-v1",
        entity_id=entity_id,
        asset_id=asset_id,
        asset_version=asset_version,
    )


def scene(entities=None):
    definition = asset()
    return SceneDefinition(
        schema_version="scene-definition-v1",
        scene_id="dual-arm-tabletop",
        assets=(definition,),
        entities=tuple(entities or (entity("robot-right"), entity("robot-left"))),
    )


def test_asset_and_scene_identity_roundtrip_reuse_and_canonical_order():
    first = scene()
    reversed_order = scene((entity("robot-left"), entity("robot-right")))

    assert first.identity_hash == reversed_order.identity_hash
    assert first.assets[0].identity_hash == asset().identity_hash
    assert [instance.entity_id for instance in first.entities] == ["robot-left", "robot-right"]
    assert SceneDefinition.from_mapping(first.to_mapping()) == first
    assert AssetDefinition.from_mapping(first.assets[0].to_mapping()) == first.assets[0]
    assert EntityInstance.from_mapping(first.entities[0].to_mapping()) == first.entities[0]
    assert SceneDefinition.from_mapping(first.to_mapping()).identity_hash == first.identity_hash


def test_scene_and_asset_identity_change_when_their_declared_identity_changes():
    original = scene()
    changed_source = AssetDefinition.from_mapping(
        asset(source_reference="mujoco-menagerie://another-pinned-revision/panda.xml").to_mapping()
    )
    changed_source_digest = asset(source_content_sha256="0" * 64)
    changed_instance = scene((entity("robot-left"), entity("robot-center")))
    changed_scene_name = SceneDefinition(
        schema_version="scene-definition-v1",
        scene_id="dual-arm-tabletop-renamed",
        assets=original.assets,
        entities=original.entities,
    )

    assert changed_source.identity_hash != original.assets[0].identity_hash
    assert changed_source_digest.identity_hash != original.assets[0].identity_hash
    assert changed_instance.identity_hash != original.identity_hash
    assert changed_scene_name.identity_hash != original.identity_hash


def test_mapping_inputs_are_copied_into_immutable_contract_values():
    raw = {
        "schema_version": "scene-definition-v1",
        "scene_id": "dual-arm-tabletop",
        "assets": [asset().to_mapping()],
        "entities": [entity("robot-right").to_mapping(), entity("robot-left").to_mapping()],
    }
    decoded = SceneDefinition.from_mapping(raw)
    original_hash = decoded.identity_hash
    raw["assets"][0]["asset_version"] = "mutated"
    raw["entities"].append(entity("robot-third").to_mapping())

    assert len(decoded.entities) == 2
    assert decoded.identity_hash == original_hash


def test_scene_rejects_duplicate_ids_unresolved_assets_and_unused_definitions():
    with pytest.raises(ValueError, match="scene entity IDs"):
        scene((entity("robot-left"), entity("robot-left")))
    with pytest.raises(ValueError, match="undeclared asset"):
        scene((entity("robot-left", asset_version="missing-version"),))
    with pytest.raises(ValueError, match="unique"):
        SceneDefinition(
            schema_version="scene-definition-v1",
            scene_id="duplicate-assets",
            assets=(asset(), asset()),
            entities=(entity("robot-left"),),
        )
    with pytest.raises(ValueError, match="unused asset"):
        SceneDefinition(
            schema_version="scene-definition-v1",
            scene_id="unused-asset",
            assets=(asset(), asset(asset_id="unused/asset", source_reference="procedural://geochora/unused")),
            entities=(entity("robot-left"),),
        )


def test_scene_definition_rejects_unknown_schema_versions_and_fields():
    values = scene().to_mapping()
    values["schema_version"] = "scene-definition-v9"
    with pytest.raises(ValueError, match="scene definition schema"):
        SceneDefinition.from_mapping(values)

    values = scene().to_mapping()
    values["unexpected"] = True
    with pytest.raises(ValueError, match="unknown SceneDefinition fields"):
        SceneDefinition.from_mapping(values)


@pytest.mark.parametrize(
    "values, message",
    [
        ({"schema_version": "asset-definition-v9", "asset_id": "a", "asset_version": "v1",
          "source_reference": "procedural://test/a"}, "asset definition schema"),
        ({"schema_version": "asset-definition-v1", "asset_id": "a", "asset_version": "v1",
          "source_reference": "/tmp/checkout/asset.xml"}, "stable URI"),
        ({"schema_version": "asset-definition-v1", "asset_id": "a", "asset_version": "v1",
          "source_reference": "file:///tmp/asset.xml"}, "file URI"),
        ({"schema_version": "asset-definition-v1", "asset_id": "a", "asset_version": "v1",
          "source_reference": "package://assets/../private.xml"}, "parent paths"),
        ({"schema_version": "asset-definition-v1", "asset_id": "a", "asset_version": "v1",
          "source_reference": "procedural://test/a", "source_content_sha256": "A" * 64}, "lowercase SHA-256"),
        ({"schema_version": "asset-definition-v1", "asset_id": "a", "asset_version": "v1",
          "source_reference": "procedural://test/a", "unexpected": True}, "unknown AssetDefinition fields"),
    ],
)
def test_asset_definition_rejects_unknown_versions_fields_and_unstable_provenance(values, message):
    with pytest.raises(ValueError, match=message):
        AssetDefinition.from_mapping(values)


def test_entity_instance_rejects_unknown_schema_versions():
    with pytest.raises(ValueError, match="entity instance schema"):
        EntityInstance.from_mapping(
            {"schema_version": "entity-instance-v9", "entity_id": "e", "asset_id": "a",
             "asset_version": "v1"}
        )


def test_v0_task_artifact_identity_hashes_remain_unchanged():
    from task_env.tasks.nut_assembly.task import build_artifact as build_nut_assembly
    from task_env.tasks.pick_cube.task import build_artifact as build_pick_cube

    pick_cube = build_pick_cube()
    nut_assembly = build_nut_assembly()
    assert pick_cube.world.schema_version == "world-v0"
    assert pick_cube.identity_hash == "fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4"
    assert nut_assembly.world.schema_version == "world-v0"
    assert nut_assembly.identity_hash == "99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe"


def test_existing_agent_and_object_factory_exports_remain_importable():
    from task_env import make_agent, make_object

    assert callable(make_agent)
    assert callable(make_object)


def test_artifact_contract_import_does_not_load_provider_or_native_runtime(tmp_path):
    code = r'''
import sys
from task_env.artifacts import AssetDefinition, EntityInstance, SceneDefinition
asset = AssetDefinition("asset-definition-v1", "cube", "v1", "procedural://geochora/cube")
entity = EntityInstance("entity-instance-v1", "cube-01", "cube", "v1")
scene = SceneDefinition("scene-definition-v1", "single-cube", (asset,), (entity,))
assert scene.identity_hash
for name in sys.modules:
    assert name.split(".", 1)[0] not in {"mujoco", "geophys", "solvers", "scene", "visualization"}, name
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3]), PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
