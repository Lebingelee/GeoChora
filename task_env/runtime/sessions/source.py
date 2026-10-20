"""Advanced Phase-I source bridge. Semantic names map to source names, never IDs."""
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
import re
import xml.etree.ElementTree as ET

from ...artifacts import SceneDefinition
from ...assembly.source import TaskSceneSource


def project_scene_definition_v3_to_mjcf(source_xml: str, scene_definition: SceneDefinition) -> str:
    """Apply the bounded v3 scalar-joint projection to an MJCF source.

    The existing provider importers remain responsible for parsing and
    materializing the projected MJCF. Fields outside this projection remain
    source-owned and require explicit disposition evidence.
    """

    scene_definition.validate()
    if scene_definition.schema_version != 'scene-definition-v3':
        raise ValueError('canonical MJCF projection requires scene-definition-v3')
    root = ET.fromstring(source_xml)
    source_joints: dict[str, list[ET.Element]] = {}
    for node in root.iter('joint'):
        name = node.get('name')
        if name:
            source_joints.setdefault(name, []).append(node)

    for articulation in scene_definition.articulations or ():
        for joint in articulation.joints:
            if joint.kind == 'fixed':
                continue
            if joint.kind not in {'revolute', 'continuous', 'prismatic'} or joint.axis is None:
                raise ValueError(f'unsupported canonical MJCF joint representation: {joint.joint_id!r}')
            matches = source_joints.get(joint.joint_id, ())
            if len(matches) != 1:
                raise ValueError(
                    f'canonical joint {joint.joint_id!r} must resolve to exactly one MJCF joint; '
                    f'found {len(matches)}'
                )
            matches[0].set('axis', ' '.join(format(float(value), '.17g') for value in joint.axis))
    return ET.tostring(root, encoding='unicode')


@dataclass(frozen=True)
class RuntimeSource:
    task_artifact_hash: str
    scene_source: TaskSceneSource
    joints: Mapping[str, str]
    bodies: Mapping[str, str]
    frames: Mapping[str, str]
    free_joints: Mapping[str, str]
    joint_targets: Mapping[str, str]
    open_actuators: tuple[str, ...]
    composition: object
    config: object
    scene: object
    agents: tuple
    objects: tuple
    scene_definition: SceneDefinition | None = None
    source_closure_digest: str | None = None

    def __post_init__(self):
        for field in ('joints', 'bodies', 'frames', 'free_joints', 'joint_targets'):
            values = dict(getattr(self, field))
            if any(type(k) is not str or type(v) is not str for k, v in values.items()):
                raise TypeError('source bindings require names, not indices')
            object.__setattr__(self, field, MappingProxyType(values))
        if self.scene_definition is None:
            if self.source_closure_digest is not None:
                raise ValueError('source closure digest requires a canonical Scene input')
            return
        if not isinstance(self.scene_definition, SceneDefinition):
            raise TypeError('canonical Scene input must be a SceneDefinition')
        self.scene_definition.validate()
        if self.scene_definition.schema_version != 'scene-definition-v3':
            raise ValueError('runtime Scene projection requires scene-definition-v3')
        if self.source_closure_digest is None or not re.fullmatch(r'[0-9a-f]{64}', self.source_closure_digest):
            raise ValueError('canonical Scene projection requires a source closure digest')
        expected_source_id = f'scene-definition-v3:{self.scene_definition.identity_hash}'
        if self.scene_source.source_id != expected_source_id:
            raise ValueError('runtime source ID must bind the exact canonical Scene identity')
