"""Bounded, provider-free resolution of versioned Logical Assembly references.

This module validates an Assembly's exact Scene and child closure and returns
immutable logical leaves. It does not construct task source, physics entities,
native names or indices, or any runtime resource.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re

from .contracts import (
    ActuatorReference,
    FrameReference,
    JointReference,
    SceneDefinition,
    _name,
)
from .logical_assembly import (
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblyNestedMemberV1,
    LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
    _component_path,
    _revision,
    decode_logical_assembly,
)


_ASSEMBLY_IDENTITY = re.compile(r"[0-9a-f]{64}\Z")
_SCENE_SCHEMAS = frozenset({
    "scene-definition-v1",
    "scene-definition-v2",
    "scene-definition-v3",
})
_MAX_DEPTH = 32
_MAX_LEAVES = 1024

AssemblyKey = tuple[str, str]
_LeafMember = LogicalAssemblyEntityMemberV1 | LogicalAssemblySubcomponentReferenceV1


@dataclass(frozen=True)
class ResolvedLogicalAssemblyLeafV1:
    """One static leaf with its original member and assembly provenance."""

    full_path: tuple[str, ...]
    source_assembly_id: str
    source_revision: str
    source_logical_content_sha256: str
    local_component_path: tuple[str, ...]
    member: _LeafMember

    def __post_init__(self):
        object.__setattr__(self, "full_path", _component_path(self.full_path))
        object.__setattr__(self, "local_component_path", _component_path(self.local_component_path))
        _name(self.source_assembly_id)
        _revision(self.source_revision, "source Assembly revision")
        if type(self.source_revision) is not str or not self.source_revision:
            raise ValueError("source_revision must be nonempty")
        if type(self.source_logical_content_sha256) is not str or not _ASSEMBLY_IDENTITY.fullmatch(
            self.source_logical_content_sha256
        ):
            raise ValueError("source logical content identity must be lowercase SHA-256")
        if type(self.member) not in (
            LogicalAssemblyEntityMemberV1,
            LogicalAssemblySubcomponentReferenceV1,
        ):
            raise TypeError("resolved leaf must preserve one typed Entity or subcomponent member")

    @property
    def member_kind(self) -> str:
        return self.member.member_kind


@dataclass(frozen=True)
class ResolvedLogicalAssemblyV1:
    """Immutable logical result; its digest is not written into an old payload."""

    root_assembly_id: str
    root_revision: str
    root_logical_content_sha256: str
    scene_id: str
    scene_schema_version: str
    scene_identity_sha256: str
    leaves: tuple[ResolvedLogicalAssemblyLeafV1, ...]

    def __post_init__(self):
        _name(self.root_assembly_id)
        _revision(self.root_revision, "root Assembly revision")
        if type(self.root_logical_content_sha256) is not str or not _ASSEMBLY_IDENTITY.fullmatch(
            self.root_logical_content_sha256
        ):
            raise ValueError("root logical content identity must be lowercase SHA-256")
        _name(self.scene_id)
        if self.scene_schema_version not in _SCENE_SCHEMAS:
            raise ValueError("unsupported resolved Scene schema")
        if type(self.scene_identity_sha256) is not str or not _ASSEMBLY_IDENTITY.fullmatch(
            self.scene_identity_sha256
        ):
            raise ValueError("Scene identity must be lowercase SHA-256")
        if type(self.leaves) is not tuple or any(
            type(leaf) is not ResolvedLogicalAssemblyLeafV1 for leaf in self.leaves
        ):
            raise TypeError("leaves must be an immutable tuple of resolved leaves")


@dataclass(frozen=True)
class _RelativeLeaf:
    path: tuple[str, ...]
    source_key: AssemblyKey
    source_hash: str
    member: _LeafMember


def _assembly_key(value, *, label: str) -> AssemblyKey:
    if (
        type(value) is not tuple
        or len(value) != 2
        or any(type(part) is not str or not part.strip() for part in value)
    ):
        raise TypeError(f"{label} must be an (assembly_id, revision) tuple")
    return value


def _clone_assembly(value, *, label: str) -> LogicalAssemblyV1:
    if type(value) is not LogicalAssemblyV1:
        raise TypeError(f"{label} must be a LogicalAssemblyV1 value")
    # Re-decode a detached strict snapshot so even a forged/mutated instance is
    # checked without changing caller-owned objects.
    return decode_logical_assembly(value.to_mapping())


def _child_entries(child_assemblies):
    if isinstance(child_assemblies, Mapping):
        return tuple(child_assemblies.items())
    if isinstance(child_assemblies, Sequence) and not isinstance(
        child_assemblies, (str, bytes, bytearray)
    ):
        return tuple(child_assemblies)
    raise TypeError("child_assemblies must be a mapping or finite sequence of key/value pairs")


def _path_text(path: tuple[AssemblyKey, ...]) -> str:
    return " -> ".join(f"{assembly_id}@{revision}" for assembly_id, revision in path)


def _member_target_key(member: _LeafMember):
    if isinstance(member, LogicalAssemblyEntityMemberV1):
        return ("entity", member.entity_id)
    target = member.target
    if member.target_kind == "frame":
        return ("frame", target.entity_id, target.frame_id)
    if member.target_kind == "joint":
        return ("joint", target.entity_id, target.joint_id)
    if member.target_kind == "actuator":
        return ("actuator", target.entity_id, target.actuator_id)
    if member.target_kind == "control_group":
        return ("control_group", target.entity_id, target.group_id)
    raise ValueError(f"unsupported typed target kind: {member.target_kind!r}")


def _validate_leaf(member, scene, entities, assets, frames, joints):
    if isinstance(member, LogicalAssemblyEntityMemberV1):
        actual = entities.get(member.entity_id)
        if actual is None:
            raise ValueError(f"unknown Scene Entity: {member.entity_id!r}")
        if (member.asset_id, member.asset_version) != (actual.asset_id, actual.asset_version):
            raise ValueError(
                f"Entity member asset identity does not match Scene Entity {member.entity_id!r}"
            )
        if (member.asset_id, member.asset_version) not in assets:
            raise ValueError(f"Entity member references an undeclared Scene Asset: {member.entity_id!r}")
        return

    target = member.target
    entity_id = target.entity_id
    if entity_id not in entities:
        raise ValueError(f"typed target references unknown Scene Entity: {entity_id!r}")
    if member.target_kind == "frame":
        if scene.schema_version == "scene-definition-v1":
            raise ValueError("Frame references require a Scene v2 or v3 definition")
        if FrameReference(target.entity_id, target.frame_id) not in frames:
            raise ValueError(f"unknown entity-qualified Frame reference: {target}")
    elif member.target_kind == "joint":
        if scene.schema_version == "scene-definition-v1":
            raise ValueError("Joint references require a Scene v2 or v3 definition")
        if (target.entity_id, target.joint_id) not in joints:
            raise ValueError(f"unknown entity-qualified Joint reference: {target}")
    elif member.target_kind == "actuator":
        scene.resolve_actuator(target)
    elif member.target_kind == "control_group":
        scene.resolve_control_group(target.entity_id, target.group_id)
    else:
        raise ValueError(f"unsupported typed target kind: {member.target_kind!r}")


def resolve_logical_assembly(
    root: LogicalAssemblyV1,
    scene: SceneDefinition,
    child_assemblies: Mapping[AssemblyKey, LogicalAssemblyV1]
    | Sequence[tuple[AssemblyKey, LogicalAssemblyV1]],
) -> ResolvedLogicalAssemblyV1:
    """Resolve a bounded logical closure against one exact existing Scene.

    ``child_assemblies`` is an explicit catalog keyed by ``(assembly_id,
    revision)``. A finite pair sequence is also accepted so duplicate catalog
    keys can be detected instead of being overwritten by a mapping constructor.
    Only reachable Assembly nodes are checked against the Scene pin; malformed
    or conflicting catalog entries are rejected before traversal.
    """
    root_value = _clone_assembly(root, label="root")
    if type(scene) is not SceneDefinition:
        raise TypeError("scene must be a SceneDefinition")
    # Scene validation occurs on a detached strict copy; static Frame lookup
    # below never asks for a runtime Frame pose.
    scene_value = SceneDefinition.from_mapping(scene.to_mapping())
    root_key = (root_value.assembly_id, root_value.revision)

    catalog: dict[AssemblyKey, LogicalAssemblyV1] = {}
    for index, entry in enumerate(_child_entries(child_assemblies)):
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise TypeError(f"child catalog entry {index} must be a key/value pair")
        key = _assembly_key(entry[0], label=f"child catalog key {index}")
        assembly = _clone_assembly(entry[1], label=f"child catalog value {index}")
        actual_key = (assembly.assembly_id, assembly.revision)
        if key != actual_key:
            raise ValueError(
                f"child catalog key {key!r} does not match Assembly identity {actual_key!r}"
            )
        previous = catalog.get(key)
        if previous is not None and previous.to_mapping() != assembly.to_mapping():
            raise ValueError(f"conflicting content for child Assembly key {key!r}")
        if key == root_key:
            if assembly.to_mapping() != root_value.to_mapping():
                raise ValueError("root Assembly key cannot be replaced by catalog content")
            # The root remains the root node; it is never added as a second
            # owning edge or resolved through a catalog substitute.
            continue
        catalog[key] = assembly

    assemblies = {root_key: root_value, **catalog}

    # First detect the key graph and its maximum path depth without comparing
    # any child content hashes. This makes cycles explicit even when a cyclic
    # digest graph cannot be made self-consistent.
    colors: dict[AssemblyKey, int] = {}
    heights: dict[AssemblyKey, int] = {}

    def check_graph(key: AssemblyKey, depth: int, path: tuple[AssemblyKey, ...]) -> int:
        state = colors.get(key, 0)
        if state == 1:
            raise ValueError(f"nested Assembly containment cycle at {_path_text(path + (key,))}")
        if state == 2:
            height = heights[key]
            if depth + height - 1 > _MAX_DEPTH:
                raise ValueError(
                    f"nested Assembly depth exceeds {_MAX_DEPTH} at {_path_text(path + (key,))}"
                )
            return height

        assembly = assemblies.get(key)
        if assembly is None:
            raise ValueError(f"missing child Assembly {key!r} at {_path_text(path)}")
        colors[key] = 1
        height = 1
        current_path = path + (key,)
        for member in assembly.members:
            if not isinstance(member, LogicalAssemblyNestedMemberV1):
                continue
            child_key = (member.assembly_id, member.revision)
            child_height = check_graph(child_key, depth + 1, current_path)
            height = max(height, child_height + 1)
        if depth + height - 1 > _MAX_DEPTH:
            raise ValueError(
                f"nested Assembly depth exceeds {_MAX_DEPTH} at {_path_text(current_path)}"
            )
        colors[key] = 2
        heights[key] = height
        return height

    check_graph(root_key, 1, ())
    reachable = tuple(sorted(colors))

    scene_identity = scene_value.identity_hash
    for key in reachable:
        assembly = assemblies[key]
        pin = assembly.scene_pin
        if (
            pin.scene_id != scene_value.scene_id
            or pin.scene_schema_version != scene_value.schema_version
            or pin.scene_identity_sha256 != scene_identity
        ):
            raise ValueError(
                f"Assembly scene pin mismatch for {key!r}: expected exact "
                f"Scene {scene_value.scene_id!r}/{scene_value.schema_version}/{scene_identity}"
            )

    for key in reachable:
        assembly = assemblies[key]
        for member in assembly.members:
            if not isinstance(member, LogicalAssemblyNestedMemberV1):
                continue
            child_key = (member.assembly_id, member.revision)
            child = assemblies[child_key]
            if member.logical_content_sha256 != child.logical_content_sha256:
                raise ValueError(
                    f"nested child digest mismatch at {_path_text((key, child_key))} "
                    f"for {member.component_path!r}"
                )

    entities = {entity.entity_id: entity for entity in scene_value.entities}
    assets = {(asset.asset_id, asset.asset_version) for asset in scene_value.assets}
    frames = {
        FrameReference(frame.entity_id, frame.frame_id)
        for frame in scene_value.frames or ()
    }
    joints = {
        (articulation.entity_id, joint.joint_id)
        for articulation in scene_value.articulations or ()
        for joint in articulation.joints
    }

    flattened: dict[AssemblyKey, tuple[_RelativeLeaf, ...]] = {}

    def expand(key: AssemblyKey) -> tuple[_RelativeLeaf, ...]:
        cached = flattened.get(key)
        if cached is not None:
            return cached
        assembly = assemblies[key]
        leaves: list[_RelativeLeaf] = []
        for member in assembly.members:
            if isinstance(member, LogicalAssemblyNestedMemberV1):
                child_key = (member.assembly_id, member.revision)
                for child_leaf in expand(child_key):
                    if len(leaves) >= _MAX_LEAVES:
                        raise ValueError(f"expanded Assembly exceeds {_MAX_LEAVES} leaves")
                    leaves.append(_RelativeLeaf(
                        member.component_path + child_leaf.path,
                        child_leaf.source_key,
                        child_leaf.source_hash,
                        child_leaf.member,
                    ))
                continue

            _validate_leaf(member, scene_value, entities, assets, frames, joints)
            if len(leaves) >= _MAX_LEAVES:
                raise ValueError(f"expanded Assembly exceeds {_MAX_LEAVES} leaves")
            leaves.append(_RelativeLeaf(
                member.component_path,
                key,
                assembly.logical_content_sha256,
                member,
            ))
        result = tuple(leaves)
        flattened[key] = result
        return result

    relative_leaves = expand(root_key)
    full_paths: set[tuple[str, ...]] = set()
    target_paths: dict[tuple, tuple[str, ...]] = {}
    owning_entities: dict[str, tuple[str, ...]] = {}
    resolved = []
    for leaf in relative_leaves:
        if leaf.path in full_paths:
            raise ValueError(f"expanded component path collision: {leaf.path!r}")
        full_paths.add(leaf.path)
        if isinstance(leaf.member, LogicalAssemblyEntityMemberV1):
            previous_owner = owning_entities.get(leaf.member.entity_id)
            if previous_owner is not None:
                raise ValueError(
                    f"Scene Entity {leaf.member.entity_id!r} has multiple owning members: "
                    f"{previous_owner!r} and {leaf.path!r}"
                )
            owning_entities[leaf.member.entity_id] = leaf.path
        target_key = _member_target_key(leaf.member)
        previous_path = target_paths.get(target_key)
        if previous_path is not None:
            raise ValueError(
                f"same typed target appears through multiple paths: "
                f"{previous_path!r} and {leaf.path!r} ({target_key!r})"
            )
        target_paths[target_key] = leaf.path
        resolved.append(ResolvedLogicalAssemblyLeafV1(
            full_path=leaf.path,
            source_assembly_id=leaf.source_key[0],
            source_revision=leaf.source_key[1],
            source_logical_content_sha256=leaf.source_hash,
            local_component_path=leaf.member.component_path,
            member=leaf.member,
        ))

    resolved.sort(key=lambda leaf: (
        leaf.full_path,
        leaf.member_kind,
        _member_target_key(leaf.member),
    ))
    return ResolvedLogicalAssemblyV1(
        root_assembly_id=root_value.assembly_id,
        root_revision=root_value.revision,
        root_logical_content_sha256=root_value.logical_content_sha256,
        scene_id=scene_value.scene_id,
        scene_schema_version=scene_value.schema_version,
        scene_identity_sha256=scene_identity,
        leaves=tuple(resolved),
    )


__all__ = [
    "ResolvedLogicalAssemblyLeafV1",
    "ResolvedLogicalAssemblyV1",
    "resolve_logical_assembly",
]
