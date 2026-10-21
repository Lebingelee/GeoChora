"""Advanced Phase-I source bridge. Semantic names map to source names, never IDs."""
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import posixpath
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


def source_asset_bytes(base_dir, source_xml: str) -> dict[str, bytes]:
    """Read bounded external bytes referenced by one MJCF source document."""

    if base_dir is None:
        raise ValueError('canonical MuJoCo materialization requires a bounded source base_dir')
    root = Path(base_dir).resolve()
    if not root.is_dir():
        raise ValueError('canonical MuJoCo source base_dir must be an existing directory')
    document = ET.fromstring(source_xml)
    compiler = document.find('compiler')
    meshdir = '' if compiler is None else compiler.get('meshdir', '')
    texturedir = '' if compiler is None else compiler.get('texturedir', '')
    assets: dict[str, bytes] = {}
    for node in document.iter():
        raw_path = node.get('file')
        if raw_path is None:
            continue
        if node.tag == 'include':
            raise ValueError('Scene-v3 MuJoCo materialization does not admit nested MJCF includes')
        directory = meshdir if node.tag in {'mesh', 'skin'} else texturedir if node.tag == 'texture' else ''
        logical_path = posixpath.normpath(posixpath.join(directory, raw_path.replace('\\', '/')))
        if logical_path in {'.', '..'} or logical_path.startswith('../') or logical_path.startswith('/'):
            raise ValueError(f'MuJoCo source asset path escapes its bounded base_dir: {raw_path!r}')
        path = root.joinpath(*logical_path.split('/'))
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f'MuJoCo source asset escaped its bounded base_dir: {path}') from exc
        if not resolved.is_file():
            raise ValueError(f'MuJoCo source asset is missing: {logical_path!r}')
        assets[logical_path] = resolved.read_bytes()
    return assets


def lower_mujoco_scene_source(scene_source, scene_definition, expected_closure_digest: str):
    """Apply the shared Scene-v3 MJCF lowering and verify its source closure.

    Runtime physics materialization and the D03 visual consumer use this same
    source path. Returned XML contains the current MuJoCo compatibility lowering;
    a renderer may append its camera/light settings after this boundary.
    """

    if not isinstance(scene_source, TaskSceneSource):
        raise TypeError('MuJoCo Scene lowering requires the public TaskSceneSource value')
    if not isinstance(scene_definition, SceneDefinition):
        raise TypeError('MuJoCo Scene lowering requires the canonical SceneDefinition')
    if not re.fullmatch(r'[0-9a-f]{64}', str(expected_closure_digest)):
        raise ValueError('MuJoCo Scene lowering requires a source closure SHA-256')
    source_xml = project_scene_definition_v3_to_mjcf(scene_source.xml, scene_definition)
    assets = source_asset_bytes(scene_source.base_dir, source_xml)
    from ...assembly.assets import _source_closure_digest
    measured_closure = _source_closure_digest({
        'scene.xml': source_xml.encode('utf-8'),
        **assets,
    })
    if measured_closure != expected_closure_digest:
        raise ValueError('MuJoCo canonical source closure digest mismatch')
    root = ET.fromstring(source_xml)
    # GeoPhys accepts extended freejoint attributes; MuJoCo expects type=free.
    for element in root.iter('freejoint'):
        element.tag = 'joint'
        element.set('type', 'free')
    # ResetPlan owns initialization; stale source keyframes are not materialized.
    for element in root.findall('keyframe'):
        root.remove(element)
    return ET.tostring(root, encoding='unicode'), assets


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
