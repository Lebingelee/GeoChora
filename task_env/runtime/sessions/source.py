"""Advanced Phase-I source bridge. Semantic names map to source names, never IDs."""
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET

from ...artifacts import SceneDefinition, TaskArtifactV1
from ...assembly.source import TaskSceneSource, UsdTaskSceneSourceV1


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
    fixed_attachment_plan: object | None = None
    fixed_attachment_assembly: object | None = None
    fixed_attachment_sources: Mapping[str, TaskSceneSource] | None = None

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
        attached_values = (
            self.fixed_attachment_plan, self.fixed_attachment_assembly,
            self.fixed_attachment_sources,
        )
        if any(value is not None for value in attached_values):
            if any(value is None for value in attached_values):
                raise ValueError('fixed Attachment RuntimeSource requires its full immutable plan, Assembly and sources')
            from ...artifacts import FixedAttachmentPlanV1, LogicalAssemblyV1
            if type(self.fixed_attachment_plan) is not FixedAttachmentPlanV1:
                raise TypeError('fixed_attachment_plan must be FixedAttachmentPlanV1')
            if type(self.fixed_attachment_assembly) is not LogicalAssemblyV1:
                raise TypeError('fixed_attachment_assembly must be LogicalAssemblyV1')
            if not isinstance(self.fixed_attachment_sources, Mapping):
                raise TypeError('fixed_attachment_sources must map Entity IDs to TaskSceneSource values')
            sources = dict(self.fixed_attachment_sources)
            if set(sources) != {
                self.fixed_attachment_plan.parent_entity_id,
                self.fixed_attachment_plan.child_entity_id,
            } or any(not isinstance(value, TaskSceneSource) for value in sources.values()):
                raise ValueError('fixed Attachment RuntimeSource must contain exactly its two Entity sources')
            if sources[self.fixed_attachment_plan.parent_entity_id].xml != self.scene_source.xml:
                raise ValueError('fixed Attachment primary SceneSource must be its parent Entity source')
            object.__setattr__(self, 'fixed_attachment_sources', MappingProxyType(sources))


@dataclass(frozen=True)
class UsdRuntimeSourceV1:
    """Provider-neutral, versioned construction input for a verified USD delivery.

    This declaration deliberately has no native runtime admission. It binds
    the already loaded delivery and canonical task/scene identities until a
    provider adapter consumes the same immutable bytes.
    """

    schema_version: str
    task_artifact: TaskArtifactV1
    scene_definition: SceneDefinition
    scene_source: UsdTaskSceneSourceV1
    joints: Mapping[str, str]
    bodies: Mapping[str, str]
    frames: Mapping[str, str]
    free_joints: Mapping[str, str]
    joint_targets: Mapping[str, str]

    def __post_init__(self):
        if self.schema_version != 'usd-runtime-source-v1':
            raise ValueError('unsupported USD RuntimeSource schema')
        if type(self.task_artifact) is not TaskArtifactV1:
            raise TypeError('USD RuntimeSource requires TaskArtifactV1')
        if type(self.scene_definition) is not SceneDefinition:
            raise TypeError('USD RuntimeSource requires SceneDefinition')
        if type(self.scene_source) is not UsdTaskSceneSourceV1:
            raise TypeError('USD RuntimeSource requires the versioned USD TaskSceneSource')
        for field in ('joints', 'bodies', 'frames', 'free_joints', 'joint_targets'):
            values = dict(getattr(self, field))
            if any(type(key) is not str or not key.strip()
                   or type(value) is not str or not value.strip()
                   for key, value in values.items()):
                raise TypeError('USD RuntimeSource bindings require nonempty canonical/native strings')
            object.__setattr__(self, field, MappingProxyType(values))
        self.validate()

    @property
    def source_closure_digest(self) -> str:
        return self.scene_source.source_closure_sha256

    @property
    def source_id(self) -> str:
        return self.scene_source.source_id

    @property
    def runtime_admitted(self) -> bool:
        # F02 representation selection is not runtime admission.
        return False

    def validate(self) -> None:
        self.task_artifact.validate()
        self.scene_definition.validate()
        self.scene_source.validate()
        self.task_artifact.validate_scene(self.scene_definition)
        if self.scene_source.scene_identity_sha256 != self.scene_definition.identity_hash:
            raise ValueError('USD RuntimeSource does not bind the exact SceneDefinition')
        if self.scene_source.task_source_identity_sha256 != self.task_artifact.task_source_identity_hash:
            raise ValueError('USD RuntimeSource does not bind the exact TaskSource identity')
        delivery_asset = self.scene_source.loaded_delivery.delivery.asset_definition
        scene_assets = {
            (asset.asset_id, asset.asset_version): asset
            for asset in self.scene_definition.assets
        }
        if scene_assets.get((delivery_asset.asset_id, delivery_asset.asset_version)) != delivery_asset:
            raise ValueError('USD delivery AssetDefinition is not the exact declared Scene asset')

        scalar_names = set()
        floating_entity_ids = set()
        for articulation in self.scene_definition.articulations or ():
            for joint in articulation.joints:
                name = f'{articulation.entity_id}/{joint.joint_id}'
                if joint.kind in {'revolute', 'continuous', 'prismatic'}:
                    scalar_names.add(name)
                elif joint.kind == 'floating':
                    if articulation.entity_id in floating_entity_ids:
                        raise ValueError('USD RuntimeSource admits at most one floating root Joint per Entity')
                    floating_entity_ids.add(articulation.entity_id)
                elif joint.kind != 'fixed':
                    raise ValueError(f'USD RuntimeSource has unsupported joint kind: {joint.kind!r}')
        if set(self.joints) != set(self.task_artifact.legacy_joint_bindings):
            raise ValueError('USD RuntimeSource scalar Joint keys must match TaskArtifact v1 bindings')
        if set(self.joints) != scalar_names:
            raise ValueError('USD RuntimeSource scalar Joint map must exactly cover the Scene scalar Joints')
        reset_pose_names = set(self.task_artifact.initialization.poses_world)
        if set(self.free_joints) != reset_pose_names:
            raise ValueError('USD RuntimeSource free Joint map must exactly cover TaskArtifact reset pose names')
        for semantic_name in self.free_joints:
            reference = self.task_artifact.legacy_frame_bindings.get(semantic_name)
            if reference is None or reference.entity_id not in floating_entity_ids:
                raise ValueError('USD RuntimeSource reset pose must bind an Entity with a floating root Joint')

        runtime_frames = set(self.task_artifact.legacy_frame_bindings)
        if set(self.bodies) & set(self.frames):
            raise ValueError('USD RuntimeSource body and Frame mappings overlap')
        if set(self.bodies) | set(self.frames) != runtime_frames:
            raise ValueError('USD RuntimeSource body/Frame maps must exactly cover runtime Scene Frames')
        if set(self.joint_targets) != scalar_names:
            raise ValueError('USD RuntimeSource joint target map must exactly cover scalar Scene Joints')
        native_targets = tuple(self.joint_targets.values())
        if len(native_targets) != len(set(native_targets)):
            raise ValueError('USD RuntimeSource must give each scalar Joint an exclusive native target')

    def assert_fresh(self) -> None:
        self.validate()
        self.scene_source.assert_fresh()
