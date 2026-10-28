"""Versioned provider-neutral intent for one static fixed Entity attachment.

The value binds an existing LogicalAssembly and Scene to two source owners.
It describes a fixed tree edge; it does not create a native model or imply
support for arbitrary assemblies.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import hashlib
import json
import re
from types import MappingProxyType

from .contracts import Contract, FrameReference, PoseWorld, _SHA256, _name
from .logical_assembly import LogicalAssemblyScenePinV1, LogicalAssemblyV1
from .logical_assembly_resolution import ResolvedLogicalAssemblyV1


_FIXED_ATTACHMENT_SCHEMA = "fixed-attachment-plan-v1"


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class FixedAttachmentPlanV1(Contract):
    """One exact static parent/child mount with explicit source and native maps."""

    schema_version: str
    assembly_id: str
    assembly_revision: str
    logical_content_sha256: str
    scene_pin: LogicalAssemblyScenePinV1
    parent_entity_id: str
    child_entity_id: str
    parent_asset_id: str
    parent_asset_version: str
    child_asset_id: str
    child_asset_version: str
    parent_source_sha256: str
    child_source_sha256: str
    license_source_sha256: str
    source_closure_sha256: str
    parent_root: FrameReference
    child_root: FrameReference
    parent_mount: FrameReference
    child_mount: FrameReference
    parent_mount_site_name: str
    child_mount_body_name: str
    parent_site_from_child_root: PoseWorld
    attach_frame_from_child_worldbody: PoseWorld
    namespace_prefix: str
    root_policy: str
    collision_policy: str
    reset_hand_opening_m: float
    extra_cross_entity_overrides: tuple[str, ...]
    native_body_names: Mapping[str, str]
    native_site_names: Mapping[str, str]
    native_joint_names: Mapping[str, str]
    native_actuator_names: Mapping[str, str]
    native_tendon_names: Mapping[str, str]

    def validate(self):
        if self.schema_version != _FIXED_ATTACHMENT_SCHEMA:
            raise ValueError(f"unsupported fixed Attachment schema: {self.schema_version!r}")
        for value in (self.assembly_id, self.parent_entity_id, self.child_entity_id,
                      self.parent_asset_id, self.parent_asset_version,
                      self.child_asset_id, self.child_asset_version,
                      self.parent_mount_site_name, self.child_mount_body_name,
                      self.namespace_prefix):
            _name(value)
        if self.parent_entity_id == self.child_entity_id:
            raise ValueError("fixed Attachment requires two distinct canonical Entities")
        if (self.parent_root.entity_id != self.parent_entity_id
                or self.child_root.entity_id != self.child_entity_id
                or self.parent_mount.entity_id != self.parent_entity_id
                or self.child_mount.entity_id != self.child_entity_id):
            raise ValueError("fixed Attachment Frame references must match their Entity owners")
        if type(self.assembly_revision) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._~-]*", self.assembly_revision,
        ):
            raise ValueError("fixed Attachment Assembly revision must be a stable token")
        for value in (self.logical_content_sha256, self.parent_source_sha256,
                      self.child_source_sha256, self.license_source_sha256,
                      self.source_closure_sha256):
            if type(value) is not str or not _SHA256.fullmatch(value):
                raise ValueError("fixed Attachment identities must be lowercase SHA-256")
        if type(self.scene_pin) is not LogicalAssemblyScenePinV1:
            raise TypeError("fixed Attachment requires a typed LogicalAssembly Scene pin")
        if type(self.parent_site_from_child_root) is not PoseWorld or type(
            self.attach_frame_from_child_worldbody
        ) is not PoseWorld:
            raise TypeError("fixed Attachment transforms require PoseWorld values")
        if self.root_policy != "fixed_child_root_under_parent_mount_no_free_joint":
            raise ValueError("unsupported fixed Attachment root policy")
        if self.collision_policy != "source_preserved":
            raise ValueError("this fixed Attachment slice only admits source-preserved collisions")
        if not 0.0 <= self.reset_hand_opening_m <= 0.08:
            raise ValueError("fixed Attachment reset opening must be within the measured Hand command range")
        if type(self.extra_cross_entity_overrides) not in (tuple, list):
            raise TypeError("extra collision overrides must be an immutable string sequence")
        object.__setattr__(self, "extra_cross_entity_overrides", tuple(self.extra_cross_entity_overrides))
        if self.extra_cross_entity_overrides:
            raise ValueError("undeclared cross-Entity collision overrides are not admitted")
        maps = (
            "native_body_names", "native_site_names", "native_joint_names",
            "native_actuator_names", "native_tendon_names",
        )
        for field in maps:
            raw = getattr(self, field)
            if not isinstance(raw, Mapping):
                raise TypeError(f"{field} must be a canonical-name/native-name mapping")
            values = dict(raw)
            if any(type(key) is not str or not key or type(value) is not str or not value
                   for key, value in values.items()):
                raise ValueError(f"{field} contains an empty or non-string name")
            if len(set(values.values())) != len(values):
                raise ValueError(f"{field} native names must be injective")
            object.__setattr__(self, field, MappingProxyType(values))
        if not self.native_body_names or not self.native_joint_names or not self.native_actuator_names:
            raise ValueError("fixed Attachment requires explicit body, joint and actuator mappings")
        if self.native_body_names.get(_frame_key(self.parent_root)) is None:
            raise ValueError("parent articulation root has no native body mapping")
        if self.native_body_names.get(_frame_key(self.child_root)) is None:
            raise ValueError("child articulation root has no native body mapping")
        if self.native_site_names.get(_frame_key(self.parent_mount)) != self.parent_mount_site_name:
            raise ValueError("parent mount Site mapping differs from its declared native name")
        if self.native_body_names.get(_frame_key(self.child_mount)) != self.child_mount_body_name:
            raise ValueError("child mount Body mapping differs from its declared native name")

    @property
    def identity_hash(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_mapping()).encode("utf-8")).hexdigest()

    def validate_against(
        self,
        assembly: LogicalAssemblyV1,
        resolved: ResolvedLogicalAssemblyV1,
        projection: LogicalAssemblySourceProjectionV1,
    ) -> None:
        """Rebind the plan to the real resolved Assembly and source projection."""
        if type(assembly) is not LogicalAssemblyV1 or type(resolved) is not ResolvedLogicalAssemblyV1:
            raise TypeError("fixed Attachment admission requires a real resolved LogicalAssembly")
        from ..assembly.logical_source import LogicalAssemblySourceProjectionV1
        if type(projection) is not LogicalAssemblySourceProjectionV1:
            raise TypeError("fixed Attachment admission requires the production source projection")
        if (self.assembly_id, self.assembly_revision, self.logical_content_sha256) != (
            assembly.assembly_id, assembly.revision, assembly.logical_content_sha256,
        ):
            raise ValueError("fixed Attachment Assembly identity differs from the resolved Assembly")
        if self.scene_pin != assembly.scene_pin or (
            resolved.scene_id, resolved.scene_schema_version, resolved.scene_identity_sha256
        ) != (
            self.scene_pin.scene_id, self.scene_pin.scene_schema_version,
            self.scene_pin.scene_identity_sha256,
        ):
            raise ValueError("fixed Attachment Scene pin differs from the resolved Scene")
        entity_members = {
            leaf.member.entity_id: leaf.member
            for leaf in resolved.leaves
            if getattr(leaf.member, "member_kind", None) == "entity_member"
        }
        expected = {self.parent_entity_id, self.child_entity_id}
        if set(entity_members) != expected or len(resolved.leaves) != 2:
            raise ValueError("fixed Attachment must resolve exactly its parent and child Entity owners")
        source_entities = {entry.entity.entity_id: entry for entry in projection.entities}
        if set(source_entities) != expected:
            raise ValueError("fixed Attachment source projection must retain both exact Scene Entities")
        for entity_id, asset_id, asset_version in (
            (self.parent_entity_id, self.parent_asset_id, self.parent_asset_version),
            (self.child_entity_id, self.child_asset_id, self.child_asset_version),
        ):
            entry = source_entities[entity_id]
            if (entry.entity.asset_id, entry.entity.asset_version) != (asset_id, asset_version):
                raise ValueError(f"fixed Attachment Asset identity differs for Entity {entity_id!r}")


def _frame_key(reference: FrameReference) -> str:
    return f"{reference.entity_id}/{reference.frame_id}"


__all__ = ["FixedAttachmentPlanV1"]
