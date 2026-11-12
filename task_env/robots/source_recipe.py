"""Provider-neutral Robot source recipes.

Recipes identify pinned inputs and canonical ownership relationships. They do
not open assets, parse source text, import a physics provider, or allocate a
native object.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


def _token(value: str, label: str) -> None:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f'{label} must be a nonempty trimmed string')


@dataclass(frozen=True)
class PositionSubjectLayoutV1:
    """Robot-owned subject topology and control groups, independent of source parsing."""
    components: tuple[tuple[str, str, tuple[str, ...], str | None], ...]
    site_entity: str
    site_name: str
    groups: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if type(self.components) is not tuple or not self.components:
            raise ValueError('position layout requires subject components')
        entities = []
        for entity, root, joints, parent in self.components:
            _token(entity, 'subject entity')
            _token(root, 'subject root')
            if type(joints) is not tuple or not joints or len(set(joints)) != len(joints):
                raise ValueError('position subject requires distinct joints')
            for joint in joints:
                _token(joint, 'subject joint')
            if parent is not None and parent not in entities:
                raise ValueError('position subject parent must precede its child')
            entities.append(entity)
        if len(set(entities)) != len(entities) or self.site_entity not in entities:
            raise ValueError('position layout requires unique subjects and an owned site')
        _token(self.site_name, 'position site')
        if type(self.groups) is not tuple or len(self.groups) != 2:
            raise ValueError('position layout requires arm and gripper control groups')
        for entity, group in self.groups:
            if entity not in entities:
                raise ValueError('position control group belongs to a foreign subject')
            _token(group, 'position control group')


@dataclass(frozen=True)
class RobotSourceReferenceV1:
    source_id: str
    source_reference: str
    source_revision: str
    entity_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for label in ('source_id', 'source_reference', 'source_revision'):
            _token(getattr(self, label), label)
        if type(self.entity_ids) is not tuple or not self.entity_ids:
            raise ValueError('Robot source entities must be a nonempty tuple')
        for entity in self.entity_ids:
            _token(entity, 'Robot source entity')
        if len(set(self.entity_ids)) != len(self.entity_ids):
            raise ValueError('Robot source entities must be unique')


@dataclass(frozen=True)
class RobotSourceRecipeV1:
    robot_uid: str
    mode: str
    sources: tuple[RobotSourceReferenceV1, ...]
    component_edges: tuple[tuple[str, str, str, str, str], ...]
    controlled_joints: tuple[str, ...]
    control_profiles: tuple[str, ...]
    resource_writers: tuple[tuple[str, str, str], ...] = ()

    def __post_init__(self) -> None:
        _token(self.robot_uid, 'Robot uid')
        if self.mode not in {'reference-task-source', 'replace-task-subtree', 'add-source'}:
            raise ValueError('unsupported Robot source recipe mode')
        if type(self.sources) is not tuple or any(type(x) is not RobotSourceReferenceV1 for x in self.sources):
            raise TypeError('Robot recipe sources must be typed source references')
        if type(self.component_edges) is not tuple:
            raise TypeError('Robot component edges must be an immutable tuple')
        if type(self.controlled_joints) is not tuple or not self.controlled_joints:
            raise ValueError('Robot recipe must declare its controlled joints')
        if len(set(self.controlled_joints)) != len(self.controlled_joints):
            raise ValueError('Robot controlled joints must be unique')
        if type(self.control_profiles) is not tuple or not self.control_profiles:
            raise ValueError('Robot recipe must declare supported Controller profiles')
        if len(set(self.control_profiles)) != len(self.control_profiles):
            raise ValueError('Robot Controller profiles must be unique')
        entities = {entity for source in self.sources for entity in source.entity_ids}
        if type(self.resource_writers) is not tuple:
            raise TypeError('Robot resource writers must be an immutable tuple')
        resources = []
        for row in self.resource_writers:
            if type(row) is not tuple or len(row) != 3:
                raise ValueError('Robot resource writer rows require entity, resource, and writer')
            entity, resource, writer = row
            for value in row:
                _token(value, 'Robot resource writer')
            if entity not in entities:
                raise ValueError('Robot resource writer owner is not declared by its sources')
            resources.append((entity, resource))
        if len(set(resources)) != len(resources):
            raise ValueError('Robot source recipe may assign only one writer to a resource')
        for edge in self.component_edges:
            if type(edge) is not tuple or len(edge) != 5:
                raise ValueError('Robot component edges require parent/frame/child/frame/rule')
            parent, parent_frame, child, child_frame, rule = edge
            for value in edge:
                _token(value, 'Robot component edge')
            if parent not in entities or child not in entities or parent == child:
                raise ValueError('Robot component edge must connect declared source entities')

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
