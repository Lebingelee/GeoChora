"""Provider-free projection from a resolved logical Assembly to Scene sources.

This module records only existing Scene declarations. It does not read asset
bytes, lower source, create physical entities, or assign native names/indices.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re

from ..artifacts import (
    ActuatorReference,
    ActuatorResourceDefinition,
    AssetDefinition,
    ControlGroup,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    JointReference,
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
    SceneDefinition,
    decode_logical_assembly,
    resolve_logical_assembly,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STABLE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")
_NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]*\Z")
_PROJECTION_SCHEMA = "logical-assembly-source-projection-v1"
_RECEIPT_SCHEMA = "geochora.d01a-asset-source-fixture-v1"
_RECEIPT_FIELDS = frozenset({
    "asset_declaration_identity",
    "scene_identity",
    "schema_version",
    "source_closure_digest",
    "source_closure_root",
    "source_reference",
    "source_revision",
})


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceReceiptLinkV1:
    """A matched historical receipt declaration, without fresh byte proof."""

    source_closure_digest: str
    source_closure_root: str

    def __post_init__(self):
        if type(self.source_closure_digest) is not str or not _SHA256.fullmatch(self.source_closure_digest):
            raise ValueError("source receipt closure digest must be lowercase SHA-256")
        if (
            type(self.source_closure_root) is not str
            or not self.source_closure_root
            or self.source_closure_root.startswith("/")
            or "\\" in self.source_closure_root
            or any(part in {"", ".", ".."} for part in self.source_closure_root.split("/"))
        ):
            raise ValueError("source receipt closure root must be a canonical relative path")

    def to_mapping(self) -> dict[str, str]:
        return {
            "source_closure_digest": self.source_closure_digest,
            "source_closure_root": self.source_closure_root,
            "evidence_status": "MATCHED_DECLARATION_NOT_REVALIDATED",
        }


@dataclass(frozen=True)
class ProjectedEntitySourceV1:
    """One unique existing Scene Entity and its exact Asset declaration."""

    entity: EntityInstance
    asset: AssetDefinition
    asset_declaration_identity_sha256: str
    evidence_status: str
    source_receipt: SourceReceiptLinkV1 | None = None

    def __post_init__(self):
        if type(self.entity) is not EntityInstance or type(self.asset) is not AssetDefinition:
            raise TypeError("projected Entity source requires exact Scene Entity and Asset declarations")
        if (self.entity.asset_id, self.entity.asset_version) != (self.asset.asset_id, self.asset.asset_version):
            raise ValueError("projected Entity and Asset declaration identities disagree")
        if self.asset_declaration_identity_sha256 != self.asset.identity_hash:
            raise ValueError("projected Asset declaration identity digest is incorrect")
        if self.evidence_status not in {
            "DECLARED_ONLY_NOT_BYTE_VERIFIED",
            "MATCHED_DECLARATION_NOT_REVALIDATED",
        }:
            raise ValueError("unsupported source declaration evidence status")
        if self.source_receipt is not None and type(self.source_receipt) is not SourceReceiptLinkV1:
            raise TypeError("source_receipt must be a SourceReceiptLinkV1 value")
        expected_status = (
            "MATCHED_DECLARATION_NOT_REVALIDATED"
            if self.source_receipt is not None
            else "DECLARED_ONLY_NOT_BYTE_VERIFIED"
        )
        if self.evidence_status != expected_status:
            raise ValueError("source receipt and evidence status disagree")

    def to_mapping(self) -> dict[str, object]:
        return {
            "entity_definition": self.entity.to_mapping(),
            "asset_definition": self.asset.to_mapping(),
            "asset_declaration_identity_sha256": self.asset_declaration_identity_sha256,
            "evidence_status": self.evidence_status,
            "source_receipt": None if self.source_receipt is None else self.source_receipt.to_mapping(),
        }


@dataclass(frozen=True)
class ProjectedLeafSourceV1:
    """A logical leaf joined to its existing Scene typed declaration."""

    full_path: tuple[str, ...]
    member_kind: str
    source_assembly_id: str
    source_revision: str
    source_logical_content_sha256: str
    local_component_path: tuple[str, ...]
    entity_id: str
    asset_id: str
    asset_version: str
    target_kind: str
    member: LogicalAssemblyEntityMemberV1 | LogicalAssemblySubcomponentReferenceV1
    target_definition: EntityInstance | FrameDefinition | JointDefinition | ActuatorResourceDefinition | ControlGroup
    group_actuator_definitions: tuple[ActuatorResourceDefinition, ...] = ()

    def __post_init__(self):
        if type(self.full_path) is not tuple or not self.full_path or any(
            type(segment) is not str or not _STABLE_TOKEN.fullmatch(segment) for segment in self.full_path
        ):
            raise ValueError("projected full_path must be an immutable segment tuple")
        if type(self.local_component_path) is not tuple or not self.local_component_path or any(
            type(segment) is not str or not _STABLE_TOKEN.fullmatch(segment)
            for segment in self.local_component_path
        ):
            raise ValueError("projected local_component_path must be an immutable segment tuple")
        if (
            not all(_NAME_TOKEN.fullmatch(value) for value in (
                self.source_assembly_id, self.entity_id, self.asset_id, self.asset_version,
            ))
            or not _STABLE_TOKEN.fullmatch(self.source_revision)
        ):
            raise ValueError("projected leaf identity fields must be stable tokens")
        if type(self.source_logical_content_sha256) is not str or not _SHA256.fullmatch(
            self.source_logical_content_sha256
        ):
            raise ValueError("projected source Assembly identity must be lowercase SHA-256")
        if type(self.member) not in (LogicalAssemblyEntityMemberV1, LogicalAssemblySubcomponentReferenceV1):
            raise TypeError("projected member must preserve one resolved typed leaf")
        if type(self.group_actuator_definitions) is not tuple or any(
            type(item) is not ActuatorResourceDefinition for item in self.group_actuator_definitions
        ):
            raise TypeError("group actuator definitions must be an immutable tuple")
        if isinstance(self.member, LogicalAssemblyEntityMemberV1):
            if self.member_kind != "entity_member" or self.target_kind != "entity":
                raise ValueError("Entity member projection discriminators disagree")
            if type(self.target_definition) is not EntityInstance or self.target_definition.entity_id != self.entity_id:
                raise ValueError("Entity leaf must retain its exact Scene Entity definition")
            if (self.member.asset_id, self.member.asset_version) != (self.asset_id, self.asset_version):
                raise ValueError("Entity member and projected source Asset identities disagree")
            if self.group_actuator_definitions:
                raise ValueError("Entity member cannot carry ControlGroup actuator definitions")
        else:
            if self.member_kind != "existing_entity_subcomponent_ref" or self.member.target_kind != self.target_kind:
                raise ValueError("typed reference projection discriminators disagree")
            if self.member.target.entity_id != self.entity_id:
                raise ValueError("typed reference and projected Entity identities disagree")
            expected_types = {
                "frame": FrameDefinition,
                "joint": JointDefinition,
                "actuator": ActuatorResourceDefinition,
                "control_group": ControlGroup,
            }
            expected_type = expected_types.get(self.target_kind)
            if expected_type is None or type(self.target_definition) is not expected_type:
                raise TypeError("typed reference must retain its exact matching Scene definition")
            if self.target_kind == "frame":
                if (
                    self.target_definition.entity_id,
                    self.target_definition.frame_id,
                ) != (self.member.target.entity_id, self.member.target.frame_id):
                    raise ValueError("Frame definition does not match the typed reference")
            elif self.target_kind == "joint":
                if (
                    self.target_definition.joint_id != self.member.target.joint_id
                    or self.target_definition.parent_frame.entity_id != self.entity_id
                    or self.target_definition.child_frame.entity_id != self.entity_id
                ):
                    raise ValueError("Joint definition does not match the typed reference")
            elif self.target_kind == "actuator":
                if (
                    self.target_definition.entity_id,
                    self.target_definition.actuator_id,
                ) != (self.member.target.entity_id, self.member.target.actuator_id):
                    raise ValueError("Actuator definition does not match the typed reference")
            elif self.target_kind == "control_group":
                group = self.target_definition
                if (group.entity_id, group.group_id) != (
                    self.member.target.entity_id, self.member.target.group_id,
                ):
                    raise ValueError("ControlGroup definition does not match the typed reference")
                expected_refs = tuple((ref.entity_id, ref.actuator_id) for ref in group.actuator_refs)
                actual_refs = tuple((item.entity_id, item.actuator_id) for item in self.group_actuator_definitions)
                if actual_refs != expected_refs:
                    raise ValueError("ControlGroup actuator definitions must follow its declared references")
            elif self.group_actuator_definitions:
                raise ValueError("only a ControlGroup leaf can carry expanded actuator definitions")

    def to_mapping(self) -> dict[str, object]:
        return {
            "full_path": list(self.full_path),
            "member_kind": self.member_kind,
            "source_assembly_id": self.source_assembly_id,
            "source_revision": self.source_revision,
            "source_logical_content_sha256": self.source_logical_content_sha256,
            "local_component_path": list(self.local_component_path),
            "entity_id": self.entity_id,
            "asset_id": self.asset_id,
            "asset_version": self.asset_version,
            "target_kind": self.target_kind,
            "member": self.member.to_mapping(),
            "target_definition": self.target_definition.to_mapping(),
            "group_actuator_definitions": [value.to_mapping() for value in self.group_actuator_definitions],
        }


@dataclass(frozen=True)
class LogicalAssemblySourceProjectionV1:
    """Detached immutable view of logical leaves and referenced Scene sources."""

    root_assembly_id: str
    root_revision: str
    root_logical_content_sha256: str
    scene_id: str
    scene_schema_version: str
    scene_identity_sha256: str
    entities: tuple[ProjectedEntitySourceV1, ...]
    leaves: tuple[ProjectedLeafSourceV1, ...]

    def __post_init__(self):
        if (
            not _NAME_TOKEN.fullmatch(self.root_assembly_id)
            or not _STABLE_TOKEN.fullmatch(self.root_revision)
            or not _NAME_TOKEN.fullmatch(self.scene_id)
        ):
            raise ValueError("projection root and Scene identity fields must be stable tokens")
        for label, value in (
            ("root logical", self.root_logical_content_sha256),
            ("Scene", self.scene_identity_sha256),
        ):
            if type(value) is not str or not _SHA256.fullmatch(value):
                raise ValueError(f"{label} identity must be lowercase SHA-256")
        if self.scene_schema_version not in {
            "scene-definition-v1", "scene-definition-v2", "scene-definition-v3",
        }:
            raise ValueError("unsupported projection Scene schema")
        if type(self.entities) is not tuple or any(type(item) is not ProjectedEntitySourceV1 for item in self.entities):
            raise TypeError("projection entities must be an immutable tuple of Entity source values")
        if type(self.leaves) is not tuple or any(type(item) is not ProjectedLeafSourceV1 for item in self.leaves):
            raise TypeError("projection leaves must be an immutable tuple of typed leaf source values")
        entity_ids = tuple(item.entity.entity_id for item in self.entities)
        if entity_ids != tuple(sorted(set(entity_ids))):
            raise ValueError("projected Scene Entity sources must be unique and sorted")
        paths = tuple(item.full_path for item in self.leaves)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("projected leaf paths must be unique and canonically sorted")
        if {item.entity_id for item in self.leaves} != set(entity_ids):
            raise ValueError("projected Entity source table must match the referenced Scene Entity set")

    @property
    def schema_version(self) -> str:
        return _PROJECTION_SCHEMA

    def to_mapping(self) -> dict[str, object]:
        """Return a fresh JSON-compatible snapshot; its digest is not embedded."""
        return {
            "schema_version": self.schema_version,
            "root": {
                "assembly_id": self.root_assembly_id,
                "revision": self.root_revision,
                "logical_content_sha256": self.root_logical_content_sha256,
            },
            "scene": {
                "scene_id": self.scene_id,
                "schema_version": self.scene_schema_version,
                "identity_sha256": self.scene_identity_sha256,
            },
            "entities": [value.to_mapping() for value in self.entities],
            "leaves": [value.to_mapping() for value in self.leaves],
        }

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_mapping())


def _receipt_for(
    receipt: Mapping[str, object], *, scene: SceneDefinition, asset: AssetDefinition
) -> SourceReceiptLinkV1:
    if not isinstance(receipt, Mapping):
        raise TypeError("source receipt values must be mappings")
    if set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("source receipt must use the exact supported fixture fields")
    if receipt["schema_version"] != _RECEIPT_SCHEMA:
        raise ValueError("unsupported source receipt schema")
    if receipt["scene_identity"] != scene.identity_hash:
        raise ValueError("source receipt Scene identity does not match the projected Scene")
    if receipt["asset_declaration_identity"] != asset.identity_hash:
        raise ValueError("source receipt Asset declaration identity does not match the Scene Asset")
    if receipt["source_reference"] != asset.source_reference:
        raise ValueError("source receipt source reference does not match the Scene Asset")
    if receipt["source_revision"] != asset.source_revision:
        raise ValueError("source receipt source revision does not match the Scene Asset")
    if type(receipt["source_closure_digest"]) is not str or not _SHA256.fullmatch(
        receipt["source_closure_digest"]
    ):
        raise ValueError("source receipt closure digest must be lowercase SHA-256")
    root = receipt["source_closure_root"]
    if type(root) is not str or not root or root.startswith("/") or ".." in root.split("/"):
        raise ValueError("source receipt closure root must be a stable relative path")
    return SourceReceiptLinkV1(receipt["source_closure_digest"], root)


def project_logical_assembly_source(
    root: LogicalAssemblyV1,
    scene: SceneDefinition,
    child_assemblies: Mapping[tuple[str, str], LogicalAssemblyV1]
    | Sequence[tuple[tuple[str, str], LogicalAssemblyV1]],
    *,
    source_receipts: Mapping[tuple[str, str], Mapping[str, object]] | None = None,
) -> LogicalAssemblySourceProjectionV1:
    """Resolve current inputs and project only their existing source declarations.

    ``source_receipts`` is optional and keyed by ``(asset_id, asset_version)``.
    Matching it records historical declaration provenance only; no source bytes
    are opened or revalidated by this function.
    """
    if type(root) is not LogicalAssemblyV1:
        raise TypeError("root must be a LogicalAssemblyV1 value")
    if type(scene) is not SceneDefinition:
        raise TypeError("scene must be a SceneDefinition value")
    root_snapshot = decode_logical_assembly(root.to_mapping())
    scene_snapshot = SceneDefinition.from_mapping(scene.to_mapping())
    resolved = resolve_logical_assembly(root_snapshot, scene_snapshot, child_assemblies)

    if source_receipts is not None and not isinstance(source_receipts, Mapping):
        raise TypeError("source_receipts must be a mapping keyed by (asset_id, asset_version)")
    if source_receipts is not None and any(
        type(key) is not tuple or len(key) != 2
        or any(type(part) is not str or not part for part in key)
        for key in source_receipts
    ):
        raise TypeError("source receipt keys must be exact (asset_id, asset_version) tuples")

    entities_by_id = {item.entity_id: item for item in scene_snapshot.entities}
    assets_by_key = {(item.asset_id, item.asset_version): item for item in scene_snapshot.assets}
    frames_by_key = {(item.entity_id, item.frame_id): item for item in scene_snapshot.frames or ()}
    joints_by_key = {
        (articulation.entity_id, joint.joint_id): joint
        for articulation in scene_snapshot.articulations or ()
        for joint in articulation.joints
    }
    actuators_by_key = {
        (item.entity_id, item.actuator_id): item
        for item in scene_snapshot.actuator_resources or ()
    }
    groups_by_key = {
        (item.entity_id, item.group_id): item
        for item in scene_snapshot.control_groups or ()
    }

    referenced_entity_ids = set()
    for leaf in resolved.leaves:
        if isinstance(leaf.member, LogicalAssemblyEntityMemberV1):
            referenced_entity_ids.add(leaf.member.entity_id)
        else:
            referenced_entity_ids.add(leaf.member.target.entity_id)

    projected_entities = []
    receipt_keys_used = set()
    for entity_id in sorted(referenced_entity_ids):
        entity = entities_by_id[entity_id]
        asset_key = (entity.asset_id, entity.asset_version)
        asset = assets_by_key[asset_key]
        receipt = None
        if source_receipts is not None and asset_key in source_receipts:
            receipt = _receipt_for(source_receipts[asset_key], scene=scene_snapshot, asset=asset)
            receipt_keys_used.add(asset_key)
        projected_entities.append(ProjectedEntitySourceV1(
            entity=EntityInstance.from_mapping(entity.to_mapping()),
            asset=AssetDefinition.from_mapping(asset.to_mapping()),
            asset_declaration_identity_sha256=asset.identity_hash,
            evidence_status=(
                "MATCHED_DECLARATION_NOT_REVALIDATED" if receipt is not None
                else "DECLARED_ONLY_NOT_BYTE_VERIFIED"
            ),
            source_receipt=receipt,
        ))
    if source_receipts is not None:
        extra = set(source_receipts) - receipt_keys_used
        if extra:
            raise ValueError(
                "source receipt does not correspond to a projected Scene Asset: "
                f"{sorted(extra, key=repr)!r}"
            )

    projected_leaves = []
    for leaf in resolved.leaves:
        member = leaf.member
        if isinstance(member, LogicalAssemblyEntityMemberV1):
            entity_id = member.entity_id
            target_kind = "entity"
            target_definition = entities_by_id[entity_id]
            group_actuator_definitions = ()
        elif isinstance(member, LogicalAssemblySubcomponentReferenceV1):
            target = member.target
            entity_id = target.entity_id
            target_kind = member.target_kind
            group_actuator_definitions = ()
            if member.target_kind == "frame":
                target_definition = frames_by_key[(target.entity_id, target.frame_id)]
            elif member.target_kind == "joint":
                target_definition = joints_by_key[(target.entity_id, target.joint_id)]
            elif member.target_kind == "actuator":
                target_definition = actuators_by_key[(target.entity_id, target.actuator_id)]
            elif member.target_kind == "control_group":
                target_definition = groups_by_key[(target.entity_id, target.group_id)]
                group_actuator_definitions = tuple(
                    actuators_by_key[(ref.entity_id, ref.actuator_id)]
                    for ref in target_definition.actuator_refs
                )
            else:  # Resolver already rejects unknown kinds; keep this boundary defensive.
                raise ValueError(f"unsupported logical source target kind: {member.target_kind!r}")
        else:
            raise TypeError("resolved leaf has an unsupported member type")
        entity = entities_by_id[entity_id]
        projected_leaves.append(ProjectedLeafSourceV1(
            full_path=tuple(leaf.full_path),
            member_kind=leaf.member_kind,
            source_assembly_id=leaf.source_assembly_id,
            source_revision=leaf.source_revision,
            source_logical_content_sha256=leaf.source_logical_content_sha256,
            local_component_path=tuple(leaf.local_component_path),
            entity_id=entity_id,
            asset_id=entity.asset_id,
            asset_version=entity.asset_version,
            target_kind=target_kind,
            member=member,
            target_definition=target_definition,
            group_actuator_definitions=tuple(group_actuator_definitions),
        ))

    return LogicalAssemblySourceProjectionV1(
        root_assembly_id=resolved.root_assembly_id,
        root_revision=resolved.root_revision,
        root_logical_content_sha256=resolved.root_logical_content_sha256,
        scene_id=resolved.scene_id,
        scene_schema_version=resolved.scene_schema_version,
        scene_identity_sha256=resolved.scene_identity_sha256,
        entities=tuple(projected_entities),
        leaves=tuple(projected_leaves),
    )


__all__ = [
    "LogicalAssemblySourceProjectionV1",
    "ProjectedEntitySourceV1",
    "ProjectedLeafSourceV1",
    "SourceReceiptLinkV1",
    "project_logical_assembly_source",
]
