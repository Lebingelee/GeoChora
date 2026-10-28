"""Provider-neutral, versioned logical Assembly value contracts.

These values pin a Scene identity and describe logical membership only. They do
not resolve the Scene, lower an Assembly to source, or create native topology.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re

from .contracts import (
    ActuatorReference,
    Contract,
    FrameReference,
    JointReference,
    _SHA256,
    _name,
)


_LOGICAL_ASSEMBLY_SCHEMA = "logical-assembly-v1"
_SCENE_PIN_SCHEMA = "logical-assembly-scene-pin-v1"
_SCENE_SCHEMAS = frozenset({
    "scene-definition-v1",
    "scene-definition-v2",
    "scene-definition-v3",
})
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")


def _exact_fields(values: Mapping, required: set[str], owner: str) -> None:
    if not isinstance(values, Mapping):
        raise TypeError(f"{owner} requires mapping")
    actual = set(values)
    missing = required - actual
    unknown = actual - required
    if missing:
        raise ValueError(f"missing {owner} fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"unknown {owner} fields: {sorted(unknown, key=str)}")


def _revision(value: str, label: str = "revision") -> None:
    if type(value) is not str or not _REVISION.fullmatch(value):
        raise ValueError(f"{label} must be a stable nonempty revision token")


def _component_path(value) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not value:
        raise ValueError("component_path must be a nonempty segment sequence")
    result = tuple(value)
    for segment in result:
        if (
            type(segment) is not str
            or segment in {".", ".."}
            or not _PATH_SEGMENT.fullmatch(segment)
        ):
            raise ValueError(f"invalid or ambiguous component path segment: {segment!r}")
    return result


def _canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class LogicalAssemblyScenePinV1(Contract):
    """Exact, provider-neutral pin to an existing versioned Scene identity."""

    schema_version: str
    scene_id: str
    scene_schema_version: str
    scene_identity_sha256: str

    def validate(self):
        if self.schema_version != _SCENE_PIN_SCHEMA:
            raise ValueError(f"unsupported Scene pin schema: {self.schema_version!r}")
        _name(self.scene_id)
        if self.scene_schema_version not in _SCENE_SCHEMAS:
            raise ValueError(
                f"unsupported pinned Scene schema: {self.scene_schema_version!r}"
            )
        if type(self.scene_identity_sha256) is not str or not _SHA256.fullmatch(
            self.scene_identity_sha256
        ):
            raise ValueError("scene_identity_sha256 must be lowercase SHA-256 hex")


@dataclass(frozen=True)
class LogicalAssemblyEntityMemberV1(Contract):
    """Logical ownership reference to one already-declared Scene Entity."""

    member_kind: str
    component_path: tuple[str, ...]
    entity_id: str
    asset_id: str
    asset_version: str

    def validate(self):
        if self.member_kind != "entity_member":
            raise ValueError("Entity member discriminator must be 'entity_member'")
        object.__setattr__(self, "component_path", _component_path(self.component_path))
        _name(self.entity_id)
        _name(self.asset_id)
        _name(self.asset_version)


@dataclass(frozen=True)
class LogicalAssemblyControlGroupReferenceV1(Contract):
    """Typed reference to a ControlGroup definition, not a ControlGroup owner."""

    entity_id: str
    group_id: str

    def validate(self):
        _name(self.entity_id)
        _name(self.group_id)


_TARGET_TYPES = {
    "frame": FrameReference,
    "joint": JointReference,
    "actuator": ActuatorReference,
    "control_group": LogicalAssemblyControlGroupReferenceV1,
}


@dataclass(frozen=True)
class LogicalAssemblySubcomponentReferenceV1:
    """Reference-only typed view of one existing Entity subcomponent."""

    member_kind: str
    component_path: tuple[str, ...]
    target_kind: str
    target: object

    def __post_init__(self):
        if self.member_kind != "existing_entity_subcomponent_ref":
            raise ValueError(
                "subcomponent discriminator must be "
                "'existing_entity_subcomponent_ref'"
            )
        object.__setattr__(self, "component_path", _component_path(self.component_path))
        target_type = _TARGET_TYPES.get(self.target_kind)
        if target_type is None:
            raise ValueError(f"unknown typed subcomponent target: {self.target_kind!r}")
        if not isinstance(self.target, target_type):
            raise TypeError(
                f"target_kind {self.target_kind!r} requires {target_type.__name__}"
            )

    @classmethod
    def from_mapping(cls, values):
        required = {"member_kind", "component_path", "target_kind", "target"}
        _exact_fields(values, required, cls.__name__)
        target_kind = values["target_kind"]
        target_type = _TARGET_TYPES.get(target_kind)
        if target_type is None:
            raise ValueError(f"unknown typed subcomponent target: {target_kind!r}")
        target = values["target"]
        if isinstance(target, target_type):
            decoded = target
        else:
            decoded = target_type.from_mapping(target)
        return cls(
            member_kind=values["member_kind"],
            component_path=values["component_path"],
            target_kind=target_kind,
            target=decoded,
        )

    def to_mapping(self):
        return {
            "member_kind": self.member_kind,
            "component_path": list(self.component_path),
            "target_kind": self.target_kind,
            "target": self.target.to_mapping(),
        }


@dataclass(frozen=True)
class LogicalAssemblyNestedMemberV1(Contract):
    """Fixed child reference codec value; it does not resolve the child graph."""

    member_kind: str
    component_path: tuple[str, ...]
    assembly_id: str
    revision: str
    logical_content_sha256: str

    def validate(self):
        if self.member_kind != "nested_assembly":
            raise ValueError("nested member discriminator must be 'nested_assembly'")
        object.__setattr__(self, "component_path", _component_path(self.component_path))
        _name(self.assembly_id)
        _revision(self.revision, "nested Assembly revision")
        if type(self.logical_content_sha256) is not str or not _SHA256.fullmatch(
            self.logical_content_sha256
        ):
            raise ValueError("logical_content_sha256 must be lowercase SHA-256 hex")


LogicalAssemblyMemberV1 = (
    LogicalAssemblyEntityMemberV1
    | LogicalAssemblySubcomponentReferenceV1
    | LogicalAssemblyNestedMemberV1
)


def _decode_member(values) -> LogicalAssemblyMemberV1:
    if not isinstance(values, Mapping):
        raise TypeError("logical Assembly member requires mapping")
    kind = values.get("member_kind")
    if kind == "entity_member":
        return LogicalAssemblyEntityMemberV1.from_mapping(values)
    if kind == "existing_entity_subcomponent_ref":
        return LogicalAssemblySubcomponentReferenceV1.from_mapping(values)
    if kind == "nested_assembly":
        return LogicalAssemblyNestedMemberV1.from_mapping(values)
    raise ValueError(f"unknown logical Assembly member kind: {kind!r}")


def _member_target_key(member: LogicalAssemblyMemberV1) -> str:
    if isinstance(member, LogicalAssemblyEntityMemberV1):
        target = {"entity_id": member.entity_id}
    elif isinstance(member, LogicalAssemblySubcomponentReferenceV1):
        target = {
            "target_kind": member.target_kind,
            "target": member.target.to_mapping(),
        }
    else:
        target = {
            "assembly_id": member.assembly_id,
            "revision": member.revision,
            "logical_content_sha256": member.logical_content_sha256,
        }
    return _canonical_json({"member_kind": member.member_kind, "target": target})


def _member_ambiguity_key(member: LogicalAssemblyMemberV1) -> str:
    if isinstance(member, LogicalAssemblyNestedMemberV1):
        # One stable child revision cannot name two different content digests.
        target = {"assembly_id": member.assembly_id, "revision": member.revision}
        return _canonical_json({"member_kind": member.member_kind, "target": target})
    return _member_target_key(member)


def _member_sort_key(member: LogicalAssemblyMemberV1):
    return (
        member.component_path,
        member.member_kind,
        _member_target_key(member),
    )


@dataclass(frozen=True)
class LogicalAssemblyV1:
    """Immutable logical Assembly identity with non-self-referential hashing."""

    schema_version: str
    assembly_id: str
    revision: str
    scene_pin: LogicalAssemblyScenePinV1
    members: tuple[LogicalAssemblyMemberV1, ...]

    def __post_init__(self):
        if self.schema_version != _LOGICAL_ASSEMBLY_SCHEMA:
            raise ValueError(f"unsupported logical Assembly schema: {self.schema_version!r}")
        _name(self.assembly_id)
        _revision(self.revision, "Assembly revision")
        if not isinstance(self.scene_pin, LogicalAssemblyScenePinV1):
            raise TypeError("scene_pin must be LogicalAssemblyScenePinV1")
        if not isinstance(self.members, (tuple, list)):
            raise TypeError("members must be a sequence of typed logical members")
        members = tuple(self.members)
        if any(not isinstance(member, (
            LogicalAssemblyEntityMemberV1,
            LogicalAssemblySubcomponentReferenceV1,
            LogicalAssemblyNestedMemberV1,
        )) for member in members):
            raise TypeError("members must contain supported typed logical members")
        paths = [member.component_path for member in members]
        if len(set(paths)) != len(paths):
            raise ValueError("component_path values must be unique within one Assembly")
        targets = [_member_ambiguity_key(member) for member in members]
        if len(set(targets)) != len(targets):
            raise ValueError(
                "duplicate logical member target or conflicting child revision "
                "is ambiguous within one Assembly"
            )
        object.__setattr__(self, "members", tuple(sorted(members, key=_member_sort_key)))

    @classmethod
    def from_mapping(cls, values):
        required = {"schema_version", "assembly_id", "revision", "scene_pin", "members"}
        _exact_fields(values, required, cls.__name__)
        if not isinstance(values["scene_pin"], LogicalAssemblyScenePinV1):
            scene_pin = LogicalAssemblyScenePinV1.from_mapping(values["scene_pin"])
        else:
            scene_pin = values["scene_pin"]
        raw_members = values["members"]
        if not isinstance(raw_members, (tuple, list)):
            raise TypeError("members must be a sequence")
        return cls(
            schema_version=values["schema_version"],
            assembly_id=values["assembly_id"],
            revision=values["revision"],
            scene_pin=scene_pin,
            members=tuple(_decode_member(member) for member in raw_members),
        )

    def to_mapping(self):
        return {
            "schema_version": self.schema_version,
            "assembly_id": self.assembly_id,
            "revision": self.revision,
            "scene_pin": self.scene_pin.to_mapping(),
            "members": [member.to_mapping() for member in self.members],
        }

    @property
    def identity_hash(self) -> str:
        """SHA-256 of the canonical mapping; the result is not in that mapping."""
        return hashlib.sha256(_canonical_json(self.to_mapping()).encode("utf-8")).hexdigest()

    @property
    def logical_content_sha256(self) -> str:
        return self.identity_hash


def decode_logical_assembly(values) -> LogicalAssemblyV1:
    """Strict explicit dispatcher for the current logical Assembly schema."""
    if not isinstance(values, Mapping):
        raise TypeError("logical Assembly codec requires mapping")
    schema_version = values.get("schema_version")
    if schema_version != _LOGICAL_ASSEMBLY_SCHEMA:
        raise ValueError(f"unsupported logical Assembly schema: {schema_version!r}")
    return LogicalAssemblyV1.from_mapping(values)


__all__ = [
    "LogicalAssemblyControlGroupReferenceV1",
    "LogicalAssemblyEntityMemberV1",
    "LogicalAssemblyNestedMemberV1",
    "LogicalAssemblyScenePinV1",
    "LogicalAssemblySubcomponentReferenceV1",
    "LogicalAssemblyV1",
    "decode_logical_assembly",
]
