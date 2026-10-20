"""A05 integration of A04 evidence into the existing Scene contract.

This is S1 static Evidence only. The maintainer approved the unchanged
scene-definition-v3 mapping as D01a's microprobe input contract; this test
records that projection without claiming Provider materialization or a new
production API.
"""

from __future__ import annotations

import copy
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from task_env.artifacts import (
    ActuatorReference,
    AssetDefinition,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    PoseWorld,
    SceneDefinition,
)


def _run_a04_evidence(root: Path) -> tuple[dict, dict, dict]:
    """Regenerate the actual A04 receipts; A05 consumes those receipts."""

    from task_env.diagnostics.tasks.test_phase_ii_a04_asset_evidence import (
        test_legacy_factory_uids_defaults_and_unknown_duplicate_rejections_remain,
        test_panda_mjcf_public_import_uses_hashed_snapshot_and_maps_to_scene_v3,
        test_procedural_peg_manifest_maps_generator_content_through_public_importer,
    )

    panda_root = root / "a04-panda"
    peg_root = root / "a04-peg"
    legacy_root = root / "a04-legacy"
    for directory in (panda_root, peg_root, legacy_root):
        directory.mkdir(parents=True, exist_ok=True)

    # Reuse the A04 acceptance paths so this integration cannot silently drift
    # to a hand-authored substitute for either the real MJCF or the generator.
    test_panda_mjcf_public_import_uses_hashed_snapshot_and_maps_to_scene_v3(panda_root)
    test_procedural_peg_manifest_maps_generator_content_through_public_importer(peg_root)
    test_legacy_factory_uids_defaults_and_unknown_duplicate_rejections_remain(legacy_root)

    def load(directory: Path, filename: str) -> dict:
        return json.loads((directory / filename).read_text(encoding="utf-8"))

    return (
        load(panda_root, "a04_panda_import_receipt.json"),
        load(peg_root, "a04_procedural_peg_receipt.json"),
        load(legacy_root, "a04_legacy_factory_receipt.json"),
    )


def _combine_scenes(panda: SceneDefinition, peg: SceneDefinition) -> SceneDefinition:
    assert panda.schema_version == peg.schema_version == "scene-definition-v3"
    return SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id="phase-ii-a05-panda-and-procedural-peg",
        assets=(*panda.assets, *peg.assets),
        entities=(*panda.entities, *peg.entities),
        frames=(*panda.frames, *peg.frames),
        articulations=(*panda.articulations, *peg.articulations),
        robots=(*panda.robots, *peg.robots),
        actuator_resources=(*panda.actuator_resources, *peg.actuator_resources),
        control_groups=(*panda.control_groups, *peg.control_groups),
    )


def _rekey_scene_entity(scene: SceneDefinition, entity_ids: dict[str, str]) -> SceneDefinition:
    """Apply an explicit legacy Entity ID projection to one imported Scene."""

    def rekey_frame(reference):
        if reference is None:
            return None
        return replace(
            reference,
            entity_id=entity_ids.get(reference.entity_id, reference.entity_id),
        )

    entities = tuple(
        replace(entity, entity_id=entity_ids.get(entity.entity_id, entity.entity_id))
        for entity in scene.entities
    )
    frames = tuple(
        replace(
            frame,
            entity_id=entity_ids.get(frame.entity_id, frame.entity_id),
            parent=rekey_frame(frame.parent),
        )
        for frame in scene.frames
    )
    articulations = tuple(
        replace(
            articulation,
            entity_id=entity_ids.get(articulation.entity_id, articulation.entity_id),
            joints=tuple(
                replace(
                    joint,
                    parent_frame=rekey_frame(joint.parent_frame),
                    child_frame=rekey_frame(joint.child_frame),
                )
                for joint in articulation.joints
            ),
        )
        for articulation in scene.articulations
    )
    robots = tuple(
        replace(
            robot,
            entity_id=entity_ids.get(robot.entity_id, robot.entity_id),
            articulation_roots=tuple(rekey_frame(root) for root in robot.articulation_roots),
        )
        for robot in scene.robots
    )
    actuator_resources = tuple(
        replace(
            resource,
            entity_id=entity_ids.get(resource.entity_id, resource.entity_id),
        )
        for resource in scene.actuator_resources
    )
    control_groups = tuple(
        replace(
            group,
            entity_id=entity_ids.get(group.entity_id, group.entity_id),
            actuator_refs=tuple(
                ActuatorReference(
                    entity_ids.get(reference.entity_id, reference.entity_id),
                    reference.actuator_id,
                )
                for reference in group.actuator_refs
            ),
        )
        for group in scene.control_groups
    )
    return SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id=scene.scene_id,
        assets=scene.assets,
        entities=entities,
        frames=frames,
        articulations=articulations,
        robots=robots,
        actuator_resources=actuator_resources,
        control_groups=control_groups,
    )


def _task_asset_from_artifact(artifact, entity) -> AssetDefinition:
    """Give legacy TaskArtifact-local geometry a stable, explicitly scoped identity."""

    return AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id=entity.semantic_id,
        asset_version=artifact.artifact_version,
        source_reference=(
            f"geochora-task-artifact://{artifact.artifact_id}/world-v0/"
            f"{entity.asset_reference}"
        ),
        source_revision=artifact.identity_hash,
    )


def _project_existing_nutassembly_task(
    artifact,
    panda_receipt: dict,
    peg_receipt: dict,
    legacy: dict,
) -> dict:
    """Project one frozen selected TaskArtifact into the existing Scene v3 owner.

    This is a read-only compatibility Evidence path. It does not change the
    selected TaskArtifact, compiler, RuntimeSource, or provider construction.
    """

    if artifact.identity_hash != "99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe":
        raise AssertionError("selected frozen NutAssembly world-v0 Artifact identity changed")
    if legacy["task_artifact_identity"] != artifact.identity_hash:
        raise AssertionError("legacy construction receipt refers to a different TaskArtifact")
    if legacy["task_artifact"] != artifact.to_mapping():
        raise AssertionError("legacy construction receipt did not preserve exact TaskArtifact bytes")

    panda = _rekey_scene_entity(
        SceneDefinition.from_mapping(panda_receipt["canonical_scene"]),
        {"panda-main": "panda-v1"},
    )
    peg = _rekey_scene_entity(
        SceneDefinition.from_mapping(peg_receipt["canonical_scene"]),
        {"square-peg-instance": "square-peg-v1"},
    )

    from task_env.objects.nut_assembly import RoundPegObject, SquareNutObject
    from task_env.assembly.assets import _asset_definition_from_manifest
    from task_env.tasks.nut_assembly.task import build_runtime_source

    manifests = {
        "square-nut-v1": SquareNutObject().asset_manifest(),
        "round-peg-v1": RoundPegObject().asset_manifest(),
    }
    imported_asset_defs = {
        "panda-v1": AssetDefinition.from_mapping(panda_receipt["asset_definition"]),
        "square-peg-v1": AssetDefinition.from_mapping(peg_receipt["asset_definition"]),
    }
    asset_provenance = {}
    asset_by_entity = {}
    artifact_entities = {entity.semantic_id: entity for entity in artifact.world.entities}
    for entity_id, entity in artifact_entities.items():
        if entity_id in imported_asset_defs:
            definition = imported_asset_defs[entity_id]
            evidence_status = "A04_IMPORT_RECEIPT"
        elif entity_id in manifests:
            manifest = manifests[entity_id]
            base_definition = _asset_definition_from_manifest(manifest)
            # The legacy task pins a TaskArtifact-specific embodiment profile;
            # retain that profile in the v0 Artifact while carrying the stable
            # source declaration in this read-only scene projection.
            definition = replace(
                base_definition,
                asset_version=artifact.artifact_version,
                source_revision=manifest.source_revision,
            )
            evidence_status = "MANIFEST_DECLARED; NOT IN THE A04 MICROPROBE RECEIPT"
        elif entity_id == "tabletop-v1":
            definition = _task_asset_from_artifact(artifact, entity)
            evidence_status = "TASK_ARTIFACT_SOURCE; NO SEPARATE IMPORT RECEIPT"
        else:
            raise AssertionError(f"no compatibility AssetDefinition for {entity_id!r}")
        asset_by_entity[entity_id] = definition
        asset_provenance[entity_id] = {
            "asset_declaration": definition.to_mapping(),
            "asset_declaration_identity": definition.identity_hash,
            "evidence_status": evidence_status,
        }

    # The TaskArtifact names a semantic end-effector frame. Its existing
    # selected RuntimeSource adds this named site beneath Panda's hand; record
    # the exact generated transform as a static local-frame projection.
    runtime_source, _ = build_runtime_source(artifact, provider="mujoco")
    source_xml = runtime_source.scene_source.xml
    source_root = ET.fromstring(source_xml)
    hand = source_root.find(".//body[@name='hand']")
    site_name = legacy["panda_site_names"][0]
    site = None if hand is None else hand.find(f"site[@name='{site_name}']")
    if site is None:
        raise AssertionError(f"selected RuntimeSource lost Panda end-effector site {site_name!r}")
    position = tuple(float(value) for value in site.get("pos", "0 0 0").split())
    quaternion = tuple(float(value) for value in site.get("quat", "1 0 0 0").split())
    if len(position) != 3 or len(quaternion) != 4:
        raise AssertionError("selected RuntimeSource end-effector transform has invalid width")
    ee_frame = FrameDefinition(
        schema_version="frame-definition-v1",
        entity_id="panda-v1",
        frame_id="ee",
        frame_kind="authored_fixed",
        parent=FrameReference("panda-v1", "hand"),
        pose_parent=PoseWorld(position, quaternion),
    )
    panda_frames = (*panda.frames, ee_frame)

    extra_entities = []
    extra_assets = []
    for entity_id, entity in artifact_entities.items():
        definition = asset_by_entity[entity_id]
        extra_assets.append(definition)
        extra_entities.append(
            EntityInstance(
                schema_version="entity-instance-v1",
                entity_id=entity_id,
                asset_id=definition.asset_id,
                asset_version=definition.asset_version,
            )
        )

    # Remove the two entities/assets already carried by the imported A04
    # structures; their identities are pinned to the A04 AssetDeclarations.
    imported_entity_ids = {"panda-v1", "square-peg-v1"}
    imported_asset_ids = {"panda-v1", "square-peg-v1"}
    projected_scene = SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id="nut-assembly-world-v0-compat-v1",
        assets=(
            *panda.assets,
            *peg.assets,
            *(asset for asset in extra_assets if asset.asset_id not in imported_asset_ids),
        ),
        entities=(
            *panda.entities,
            *peg.entities,
            *(entity for entity in extra_entities if entity.entity_id not in imported_entity_ids),
        ),
        frames=panda_frames + peg.frames,
        articulations=panda.articulations + peg.articulations,
        robots=panda.robots + peg.robots,
        actuator_resources=panda.actuator_resources + peg.actuator_resources,
        control_groups=panda.control_groups + peg.control_groups,
    )
    encoded_scene = projected_scene.to_mapping()
    assert SceneDefinition.from_mapping(encoded_scene).to_mapping() == encoded_scene

    frame_mapping = {
        "panda-v1/base": FrameReference("panda-v1", "link0"),
        "panda-v1/ee": FrameReference("panda-v1", "ee"),
    }
    joint_mapping = {
        name: {"entity_id": "panda-v1", "joint_id": name.split("/", 1)[1]}
        for name in artifact_entities["panda-v1"].joints
    }
    canonical_joint_ids = {
        joint.joint_id
        for articulation in projected_scene.articulations
        if articulation.entity_id == "panda-v1"
        for joint in articulation.joints
    }
    assert {value["joint_id"] for value in joint_mapping.values()} <= canonical_joint_ids
    assert all(
        frame.entity_id == "panda-v1" and frame.frame_id in {
            item.frame_id for item in projected_scene.frames if item.entity_id == "panda-v1"
        }
        for frame in frame_mapping.values()
    )

    entity_fields = []
    source_retained = []
    for index, entity in enumerate(artifact.world.entities):
        entity_id = entity.semantic_id
        entity_fields.append(
            {
                "kind": "Entity",
                "source_pointers": [
                    f"/world/entities/{index}/semantic_id",
                    f"/world/entities/{index}/asset_reference",
                ],
                "legacy_reference": entity_id,
                "canonical_identity": {
                    "entity_id": entity_id,
                    "asset_id": asset_by_entity[entity_id].asset_id,
                    "asset_version": asset_by_entity[entity_id].asset_version,
                },
                "canonical_path": f"entities[{index}]",
                "asset_declaration_identity": asset_by_entity[entity_id].identity_hash,
                "legacy_asset_reference": entity.asset_reference,
            }
        )
        for field in ("kind", "geometry", "collision_intent", "parameters_si"):
            source_retained.append(
                {
                    "source_pointer": f"/world/entities/{index}/{field}",
                    "source_task_artifact_identity": artifact.identity_hash,
                    "disposition": "SOURCE_RETAINED",
                    "reason": "SceneDefinition v3 carries Entity/Asset identity, not TaskArtifact geometry or contact intent",
                }
            )
        for frame_index, reference in enumerate(entity.frames):
            if reference not in frame_mapping:
                raise AssertionError(f"legacy frame has no explicit canonical mapping: {reference}")
            mapped = frame_mapping[reference]
            entity_fields.append(
                {
                "kind": "Frame",
                "source_pointer": f"/world/entities/{index}/frames/{frame_index}",
                "legacy_reference": reference,
                    "canonical_identity": mapped.to_mapping(),
                    "canonical_path": f"frames[{projected_scene.frames.index(next(frame for frame in projected_scene.frames if frame.entity_id == mapped.entity_id and frame.frame_id == mapped.frame_id))}]",
                    "task_source_locator": (
                        {
                            "source_route": "NutAssembly.build_runtime_source(provider='mujoco')",
                            "generated_xml_sha256": hashlib.sha256(source_xml.encode("utf-8")).hexdigest(),
                            "element_path": f"/mujoco/worldbody/body[@name='hand']/site[@name='{site_name}']",
                        }
                        if reference.endswith("/ee") else None
                    ),
                }
            )
        for joint_index, reference in enumerate(entity.joints):
            if reference not in joint_mapping:
                raise AssertionError(f"legacy joint has no explicit canonical mapping: {reference}")
            entity_fields.append(
                {
                "kind": "Joint",
                "source_pointer": f"/world/entities/{index}/joints/{joint_index}",
                "legacy_reference": reference,
                    "canonical_identity": joint_mapping[reference],
                    "canonical_path": "articulations[panda-v1].joints",
                }
            )
    for actuator_index, actuator_id in enumerate(legacy["panda_actuator_names"]):
        reference = ActuatorReference("panda-v1", actuator_id)
        entity_fields.append(
            {
                "kind": "Actuator",
                "source_pointer": f"legacy_factory_receipt.panda_actuator_names[{actuator_index}]",
                "legacy_reference": {"factory_uid": "panda-v1", "name": actuator_id},
                "canonical_identity": reference.to_mapping(),
                "canonical_path": "actuator_resources[panda-v1]",
            }
        )

    task_mapping = artifact.to_mapping()
    task_identity_fields = [
        {
            "source_pointer": f"/{field}",
            "projection_path": path,
            "value": task_mapping[field],
        }
        for field, path in (
            ("schema_version", "source_task_artifact.schema_version"),
            ("artifact_id", "source_task_artifact.artifact_id"),
            ("task_id", "source_task_id / source_task_artifact.task_id"),
            ("artifact_version", "source_task_artifact_version / source_task_artifact.artifact_version"),
        )
    ]
    retained_top_level = (
        "initialization",
        "semantics",
        "timebase",
        "required_capabilities",
    )
    source_retained.extend(
        {
            "source_pointer": f"/{field}",
            "source_task_artifact_identity": artifact.identity_hash,
            "disposition": "SOURCE_RETAINED",
            "reason": "TaskArtifact lifecycle/evaluation contract is not SceneDefinition structure",
        }
        for field in retained_top_level
    )
    source_retained.extend(
        {
            "source_pointer": f"/world/{field}",
            "source_task_artifact_identity": artifact.identity_hash,
            "disposition": "SOURCE_RETAINED",
            "reason": "TaskArtifact world semantics are preserved by the embedded frozen source mapping",
        }
        for field in (
            "schema_version",
            "convention",
            "action",
            "observation_requirements",
            "randomization_dimensions",
        )
    )
    assert set(task_mapping) == {
        "schema_version", "artifact_id", "task_id", "artifact_version", "world",
        "initialization", "semantics", "timebase", "required_capabilities",
    }
    assert all(row["disposition"] == "SOURCE_RETAINED" for row in source_retained)

    # Prove every frozen TaskArtifact field has an explicit destination or is
    # carried in the SOURCE_RETAINED section. Entity array paths are index
    # qualified so semantic IDs remain data rather than path syntax.
    accounted = {row["source_pointer"] for row in source_retained}
    accounted.update(row["source_pointer"] for row in task_identity_fields)
    for index, entity in enumerate(artifact.world.entities):
        accounted.update(
            {
                f"/world/entities/{index}/semantic_id",
                f"/world/entities/{index}/asset_reference",
                f"/world/entities/{index}/frames",
                f"/world/entities/{index}/joints",
            }
        )
        accounted.update(
            f"/world/entities/{index}/{field}"
            for field in ("kind", "geometry", "collision_intent", "parameters_si")
        )
    expected = {
        f"/{key}" for key in task_mapping if key != "world"
    }
    expected.update(f"/world/{key}" for key in task_mapping["world"] if key != "entities")
    expected.update(
        f"/world/entities/{index}/{key}"
        for index, entity in enumerate(artifact.world.entities)
        for key in entity.to_mapping()
    )
    assert expected <= accounted

    return {
        "schema_version": "geochora.a05-legacy-task-projection-v1",
        "source_task_id": artifact.task_id,
        "source_task_artifact_id": artifact.artifact_id,
        "source_task_artifact_version": artifact.artifact_version,
        "source_task_artifact_identity": artifact.identity_hash,
        "source_task_artifact": task_mapping,
        "source_task_identity_fields": task_identity_fields,
        "target_schema": "scene-definition-v3",
        "target_scene": encoded_scene,
        "target_scene_identity": projected_scene.identity_hash,
        "asset_provenance": asset_provenance,
        "field_map": entity_fields,
        "source_retained_fields": source_retained,
        "defaults_applied": [],
        "approximations": [],
        "unsupported_canonical_fields": [],
        "source_task_scene_xml_sha256": hashlib.sha256(source_xml.encode("utf-8")).hexdigest(),
        "end_effector_site": {
            "legacy_reference": "panda-v1/ee",
            "provider_neutral_frame": FrameReference("panda-v1", "ee").to_mapping(),
            "parent": FrameReference("panda-v1", "hand").to_mapping(),
            "pose_parent": ee_frame.pose_parent.to_mapping(),
            "source_element": f"/mujoco/worldbody/body[@name='hand']/site[@name='{site_name}']",
            "scope": "static link-local frame identity only; no world pose or runtime state claim",
        },
        "d01a_microprobe_input": False,
        "d01a_exclusion_reason": (
            "The selected task projection also references assets without A04 source-closure/import receipts; "
            "the separately approved A04-backed two-asset scene is the D01a microprobe payload."
        ),
        "scope": "read-only compatibility evidence; no TaskArtifact rewrite, Runtime, or Physics",
    }


def _matching_mapping(receipt: dict, identity: dict) -> list[str]:
    return [
        row["mapping_id"]
        for row in receipt["mapping"]
        if row.get("canonical_reference") == identity
        and row["core_disposition"] == "CANONICAL_REPRESENTED"
    ]


def _field_map(scene: SceneDefinition, receipts: dict[str, dict], legacy: dict) -> list[dict]:
    rows = []

    def add(kind, identity, canonical_path, asset_id, legacy_reference=None):
        receipt = receipts[asset_id]
        mapping_ids = _matching_mapping(receipt, identity)
        if kind in {"Frame", "Joint", "Actuator"}:
            assert mapping_ids, f"A04 has no source mapping for {kind}: {identity}"
        rows.append(
            {
                "kind": kind,
                "canonical_identity": identity,
                "canonical_path": canonical_path,
                "target_path": canonical_path,
                "default_rule": "none; copy the canonical value unchanged",
                "legacy_reference": legacy_reference,
                "source_receipt": receipt["schema_version"],
                "source_scene_identity": receipt["canonical_scene_identity"],
                "source_mapping_ids": mapping_ids,
            }
        )

    for index, asset in enumerate(scene.assets):
        aid = asset.asset_id
        add(
            "Asset",
            {
                "asset_id": aid,
                "asset_version": asset.asset_version,
                "asset_declaration_identity": asset.identity_hash,
            },
            f"assets[{index}]",
            aid,
            {"factory_uid": aid} if aid in legacy["component_uids"].values() else None,
        )

    for index, entity in enumerate(scene.entities):
        add(
            "Entity",
            {
                "entity_id": entity.entity_id,
                "asset_id": entity.asset_id,
                "asset_version": entity.asset_version,
            },
            f"entities[{index}]",
            entity.asset_id,
            {"factory_uid": legacy["component_uids"].get(
                "agent" if entity.asset_id == "panda-v1" else "object"
            )},
        )

    for index, frame in enumerate(scene.frames):
        identity = FrameReference(frame.entity_id, frame.frame_id).to_mapping()
        if frame.entity_id == "panda-main":
            legacy_ref = (
                {
                    "factory_uid": "panda-v1",
                    "reference": "body_names",
                    "name": frame.frame_id,
                }
                if frame.frame_id in legacy["panda_body_names"] else None
            )
        else:
            legacy_ref = {
                "factory_uid": "square-peg-v1",
                "reference": "body_names",
                "name": frame.frame_id,
            }
        asset_id = "panda-v1" if frame.entity_id == "panda-main" else "square-peg-v1"
        add("Frame", identity, f"frames[{index}]", asset_id, legacy_ref)

    for articulation_index, articulation in enumerate(scene.articulations):
        for joint_index, joint in enumerate(articulation.joints):
            identity = {"entity_id": articulation.entity_id, "joint_id": joint.joint_id}
            legacy_ref = None
            if (
                articulation.entity_id == "panda-main"
                and joint.joint_id in legacy["panda_joint_names"]
            ):
                legacy_ref = {
                    "factory_uid": "panda-v1",
                    "reference": "joint_names",
                    "name": joint.joint_id,
                }
            add(
                "Joint",
                identity,
                f"articulations[{articulation_index}].joints[{joint_index}]",
                "panda-v1",
                legacy_ref,
            )

    for index, actuator in enumerate(scene.actuator_resources):
        legacy_ref = (
            {
                "factory_uid": "panda-v1",
                "reference": "actuator_names",
                "name": actuator.actuator_id,
            }
            if actuator.actuator_id in legacy["panda_actuator_names"] else None
        )
        add(
            "Actuator",
            {"entity_id": actuator.entity_id, "actuator_id": actuator.actuator_id},
            f"actuator_resources[{index}]",
            "panda-v1",
            legacy_ref,
        )
    return rows


def _source_retained_summary(receipts: dict[str, dict]) -> list[dict]:
    retained = []
    for asset_id, receipt in receipts.items():
        for row in receipt["semantic_dispositions"]:
            if row["core_disposition"] != "CANONICAL_REPRESENTED":
                retained.append(
                    {
                        "asset_id": asset_id,
                        "source_locator": row["source_locator"],
                        "semantic": row["semantic"],
                        "provider_status": row["provider_status"],
                        "core_disposition": row["core_disposition"],
                        "projection_disposition": (
                            "SOURCE_RETAINED_PROVENANCE_ONLY; not canonical runtime semantics"
                            if row["core_disposition"] == "SOURCE_RETAINED"
                            else "UNSUPPORTED_OR_APPROXIMATE; excluded and requires an explicit later gate"
                        ),
                    }
                )
    return retained


def test_a05_integrates_a04_assets_and_emits_approved_d01a_identity_projection(tmp_path):
    panda_receipt, peg_receipt, legacy = _run_a04_evidence(tmp_path)
    source_receipts = {
        "panda-v1": panda_receipt,
        "square-peg-v1": peg_receipt,
    }
    panda = SceneDefinition.from_mapping(panda_receipt["canonical_scene"])
    peg = SceneDefinition.from_mapping(peg_receipt["canonical_scene"])
    assert panda.identity_hash == panda_receipt["canonical_scene_identity"]
    assert peg.identity_hash == peg_receipt["canonical_scene_identity"]

    scene = _combine_scenes(panda, peg)
    encoded_scene = scene.to_mapping()
    assert SceneDefinition.from_mapping(encoded_scene).identity_hash == scene.identity_hash
    assert SceneDefinition.from_mapping(encoded_scene).to_mapping() == encoded_scene

    # Preserve selected legacy identities and names alongside the new
    # canonical identities; this is evidence only, not a second writable model.
    assert legacy["component_uids"]["agent"] == "panda-v1"
    assert legacy["component_uids"]["object"] == "square-peg-v1"
    assert legacy["component_uids"]["selected_scene"] == "tabletop-v1"
    panda_joints = {
        joint.joint_id
        for articulation in scene.articulations
        if articulation.entity_id == "panda-main"
        for joint in articulation.joints
    }
    assert set(legacy["panda_joint_names"]) <= panda_joints
    assert set(legacy["panda_actuator_names"]) == {
        actuator.actuator_id for actuator in scene.actuator_resources
        if actuator.entity_id == "panda-main"
    }
    assert set(legacy["panda_body_names"]) <= {
        frame.frame_id for frame in scene.frames if frame.entity_id == "panda-main"
    }
    assert legacy["peg_body_names"] == ["peg1"]

    from task_env.tasks.nut_assembly.task import build_artifact

    nutassembly_artifact = build_artifact()
    legacy_task_projection = _project_existing_nutassembly_task(
        nutassembly_artifact,
        panda_receipt,
        peg_receipt,
        legacy,
    )

    receipt_by_asset = {
        asset_id: {
            "a04_receipt": receipt,
            "asset_declaration_identity": receipt["asset_declaration_identity"],
            "source_closure_digest": receipt["source_closure_digest"],
            "provider_import_identity": receipt["provider_import_identity"],
            "canonical_scene_identity": receipt["canonical_scene_identity"],
        }
        for asset_id, receipt in source_receipts.items()
    }
    for receipt in source_receipts.values():
        provider_identity = receipt["provider_import_identity"]
        assert len({
            receipt["asset_declaration_identity"],
            receipt["source_closure_digest"],
            provider_identity["source_graph_hash"],
            provider_identity["ir_semantic_hash"],
        }) == 4
    field_map = _field_map(scene, source_receipts, legacy)
    retained = _source_retained_summary(source_receipts)
    evidence = {
        "schema_version": "geochora.a05-static-projection-evidence-v1",
        "gate": "PASS_A05_STATIC_CONTRACT",
        "maintainer_decision": {
            "decision": "APPROVED",
            "approved_contract": "scene-definition-v3 mapping copied unchanged",
            "approved_destination": "D01a microprobe input",
            "approval_date": "2026-10-20",
            "evidence": "maintainer response in the current review thread",
        },
        "scope": "S1 static integration and compatibility only; no Provider Runtime or Physics",
        "legacy_task_compatibility_projection": legacy_task_projection,
        "canonical_scene": encoded_scene,
        "scene_definition_identity": scene.identity_hash,
        "a04_sources": receipt_by_asset,
        "legacy_factory_receipt": legacy,
        "projection": {
            "kind": "approved read-only identity projection",
            "source_contract": "scene-definition-v3",
            "destination": "D01a microprobe input",
            "destination_contract": "scene-definition-v3 mapping copied unchanged",
            "payload": encoded_scene,
            "field_map": field_map,
            "defaults_applied": [],
            "approximations": [],
            "unsupported_canonical_fields": [],
            "unsupported_list": [],
            "unprojected_source_semantics": retained,
            "rejection_rules": [
                "Reject unknown or missing scene-definition-v3 fields through the existing strict codec.",
                "Reject unsupported or approximate canonical fields; do not synthesize defaults.",
                "SOURCE_RETAINED source semantics remain provenance only and are not materialized by this projection.",
            ],
        },
    }
    assert field_map
    assert Counter(row["kind"] for row in field_map) == {
        "Asset": len(scene.assets),
        "Entity": len(scene.entities),
        "Frame": len(scene.frames),
        "Joint": sum(len(articulation.joints) for articulation in scene.articulations),
        "Actuator": len(scene.actuator_resources),
    }
    assert all(row["canonical_path"] == row["target_path"] for row in field_map)
    assert evidence["maintainer_decision"]["decision"] == "APPROVED"
    assert evidence["projection"]["payload"] == encoded_scene
    assert legacy_task_projection["source_task_artifact_identity"] == nutassembly_artifact.identity_hash
    assert legacy_task_projection["target_schema"] == "scene-definition-v3"
    assert legacy_task_projection["d01a_microprobe_input"] is False
    assert not evidence["projection"]["defaults_applied"]
    assert not evidence["projection"]["approximations"]
    assert not evidence["projection"]["unsupported_canonical_fields"]
    assert all(row["core_disposition"] == "SOURCE_RETAINED" for row in retained)

    # Negative projection checks: a field cannot disappear or be smuggled into
    # this candidate under an unapproved extension.
    missing_field = copy.deepcopy(encoded_scene)
    del missing_field["actuator_resources"]
    with pytest.raises(ValueError, match="missing SceneDefinition fields"):
        SceneDefinition.from_mapping(missing_field)
    unknown_field = copy.deepcopy(encoded_scene)
    unknown_field["provider_private_state"] = {}
    with pytest.raises(ValueError, match="unknown SceneDefinition fields"):
        SceneDefinition.from_mapping(unknown_field)

    output_path = tmp_path / "a05_static_projection_receipt.json"
    output_path.write_text(
        json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    reread = json.loads(output_path.read_text(encoding="utf-8"))
    assert reread["scene_definition_identity"] == scene.identity_hash
    assert len(reread["a04_sources"]) == 2
    assert reread["maintainer_decision"]["approved_contract"] == (
        "scene-definition-v3 mapping copied unchanged"
    )
    assert reread["legacy_task_compatibility_projection"]["source_task_artifact_identity"] == (
        nutassembly_artifact.identity_hash
    )
    assert {item["asset_id"] for item in reread["projection"]["unprojected_source_semantics"]} == {
        "panda-v1", "square-peg-v1"
    }
