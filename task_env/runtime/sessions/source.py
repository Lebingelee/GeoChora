"""Advanced Phase-I source bridge. Semantic names map to source names, never IDs."""
from dataclasses import dataclass, field
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import hashlib
import os
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET

from ...artifacts import SceneDefinition
from ...assembly.source import TaskSceneSource
from ...assembly.assets import _source_closure_digest


@dataclass(frozen=True)
class ExecutionSourceReceiptV1:
    """Versioned receipt binding canonical source bytes to one importer snapshot."""

    source_id: str
    canonical_xml_sha256: str
    importer_xml_sha256: str
    source_closure_digest: str
    snapshot_root: Path
    importer_xml: bytes = field(repr=False, compare=False)
    closure_files: Mapping[str, bytes] = field(repr=False, compare=False)
    _temporary_owner: object = field(repr=False, compare=False)

    def __post_init__(self):
        if type(self.source_id) is not str or not self.source_id:
            raise ValueError('execution source receipt requires a source label')
        for name in ('canonical_xml_sha256', 'importer_xml_sha256', 'source_closure_digest'):
            if type(getattr(self, name)) is not str or not re.fullmatch(r'[0-9a-f]{64}', getattr(self, name)):
                raise ValueError(f'execution source receipt {name} must be SHA-256')
        files = dict(self.closure_files)
        if files.get('scene.xml') != self.importer_xml:
            raise ValueError('execution source closure must contain the exact importer XML bytes')
        canonical = files.get('canonical-source.xml')
        if not isinstance(canonical, bytes) or hashlib.sha256(canonical).hexdigest() != self.canonical_xml_sha256:
            raise ValueError('execution source closure does not contain the canonical XML bytes')
        if hashlib.sha256(self.importer_xml).hexdigest() != self.importer_xml_sha256:
            raise ValueError('execution source importer XML digest mismatch')
        if _source_closure_digest(files) != self.source_closure_digest:
            raise ValueError('execution source closure digest mismatch')
        object.__setattr__(self, 'snapshot_root', Path(self.snapshot_root).resolve())
        object.__setattr__(self, 'closure_files', MappingProxyType(files))
        self.validate_snapshot()

    @classmethod
    def create(cls, *, source_id, canonical_xml, importer_xml, closure_files,
               expected_canonical_xml_sha256=None):
        if not isinstance(canonical_xml, bytes) or not isinstance(importer_xml, bytes):
            raise TypeError('execution source XML inputs must be immutable bytes')
        canonical_sha = hashlib.sha256(canonical_xml).hexdigest()
        if expected_canonical_xml_sha256 is not None and canonical_sha != expected_canonical_xml_sha256:
            raise ValueError('canonical source XML bytes differ from the admitted NutAssembly source')
        files = dict(closure_files)
        files['scene.xml'] = importer_xml
        closure_sha = _source_closure_digest(files)
        owner = tempfile.TemporaryDirectory(prefix='geochora-execution-source-')
        root = Path(owner.name).resolve()
        try:
            for logical, payload in files.items():
                if not isinstance(logical, str) or not logical or logical.startswith('/') or '\\' in logical:
                    raise ValueError('execution source snapshot paths must be relative POSIX paths')
                parts = logical.split('/')
                if any(part in {'', '.', '..'} for part in parts):
                    raise ValueError(f'unsafe execution source snapshot path: {logical!r}')
                target = root.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                target.chmod(0o444)
            for directory, _, _ in os.walk(root, topdown=False):
                Path(directory).chmod(0o555)
            return cls(
                source_id, canonical_sha, hashlib.sha256(importer_xml).hexdigest(),
                closure_sha, root, importer_xml, files, owner,
            )
        except BaseException:
            owner.cleanup()
            raise

    def validate_snapshot(self):
        root = self.snapshot_root
        if not root.is_dir():
            raise ValueError('execution source snapshot is missing')
        expected = set(self.closure_files)
        actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
        if actual != expected:
            raise ValueError(f'execution source snapshot file set mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}')
        for logical in expected:
            path = (root / logical).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ValueError('execution source snapshot path escaped its root') from exc
            if path.read_bytes() != self.closure_files[logical]:
                raise ValueError(f'execution source snapshot bytes changed: {logical}')
        if hashlib.sha256(self.importer_xml).hexdigest() != self.importer_xml_sha256:
            raise ValueError('execution source importer XML bytes changed')

    def validate_imported_scene(self, imported_scene):
        self.validate_snapshot()
        dependencies = tuple(Path(path).resolve() for path in imported_scene.dependency_paths)
        expected = {
            (self.snapshot_root / name).resolve()
            for name in self.closure_files
            if name not in {'scene.xml', 'canonical-source.xml'}
        }
        if set(dependencies) != expected or len(dependencies) != len(expected):
            raise ValueError('GeoPhys importer dependencies differ from the execution source receipt')
        for path in dependencies:
            try:
                logical = path.relative_to(self.snapshot_root).as_posix()
            except ValueError as exc:
                raise ValueError('GeoPhys importer read outside the execution source snapshot') from exc
            if path.read_bytes() != self.closure_files[logical]:
                raise ValueError(f'GeoPhys importer dependency bytes differ from the receipt: {logical}')

    def to_mapping(self):
        from ...assembly.assets import _source_closure_manifest
        return {
            'schema_version': 'runtime-execution-source-receipt-v1',
            'source_id': self.source_id,
            'canonical_xml_sha256': self.canonical_xml_sha256,
            'importer_xml_sha256': self.importer_xml_sha256,
            'source_closure_digest': self.source_closure_digest,
            'files': list(_source_closure_manifest(self.closure_files)),
        }

    def close(self):
        owner = self._temporary_owner
        if owner is not None:
            owner.cleanup()


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
    execution_source_receipt: ExecutionSourceReceiptV1 | None = None
    torque_actuators: Mapping[str, str] = field(default_factory=dict)
    position_actuators: Mapping[str, str] = field(default_factory=dict)
    actuator_units: Mapping[str, str] = field(default_factory=dict)
    fixture_bodies: tuple[str, ...] = ()
    contact_geom_groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    mixed_controller_profile_id: str | None = None
    mixed_controller_identity: str | None = None

    def __post_init__(self):
        for field in (
            'joints', 'bodies', 'frames', 'free_joints', 'joint_targets',
            'torque_actuators', 'position_actuators', 'actuator_units',
        ):
            values = dict(getattr(self, field))
            if any(type(k) is not str or type(v) is not str for k, v in values.items()):
                raise TypeError('source bindings require names, not indices')
            object.__setattr__(self, field, MappingProxyType(values))
        fixtures = tuple(self.fixture_bodies)
        if any(type(name) is not str or not name.strip() for name in fixtures):
            raise TypeError('fixture body bindings require nonempty names')
        if len(set(fixtures)) != len(fixtures):
            raise ValueError('fixture body bindings must be unique')
        object.__setattr__(self, 'fixture_bodies', fixtures)
        groups = {str(entity): tuple(names) for entity, names in dict(self.contact_geom_groups).items()}
        if any(not entity.strip() or not names or any(type(name) is not str or not name.strip() for name in names)
               or len(set(names)) != len(names) for entity, names in groups.items()):
            raise ValueError('contact geom groups require unique named source geoms')
        object.__setattr__(self, 'contact_geom_groups', MappingProxyType(groups))
        if (self.mixed_controller_profile_id is None) != (self.mixed_controller_identity is None):
            raise ValueError('mixed Controller profile and identity must be bound together')
        if self.mixed_controller_profile_id is not None:
            if (type(self.mixed_controller_profile_id) is not str
                    or not self.mixed_controller_profile_id.strip()
                    or type(self.mixed_controller_identity) is not str
                    or not re.fullmatch(r'[0-9a-f]{64}', self.mixed_controller_identity)):
                raise ValueError('mixed Controller source binding requires a profile and SHA-256 identity')
        if self.torque_actuators and self.position_actuators:
            all_actuators = (*self.torque_actuators.values(), *self.position_actuators.values())
            if len(set(all_actuators)) != len(all_actuators):
                raise ValueError('direct-control actuator bindings must have a single named writer')
            if set(self.actuator_units) != set(all_actuators):
                raise ValueError('direct-control actuator units must exactly cover named actuator bindings')
            if any(unit not in {'N*m', 'm'} for unit in self.actuator_units.values()):
                raise ValueError('direct-control units are limited to source-bound N*m and m')
            if (any(self.actuator_units[name] != 'N*m' for name in self.torque_actuators.values())
                    or any(self.actuator_units[name] != 'm' for name in self.position_actuators.values())):
                raise ValueError('direct-control unit differs from actuator role')
        if self.scene_definition is None:
            if self.execution_source_receipt is not None:
                receipt = self.execution_source_receipt
                if type(receipt) is not ExecutionSourceReceiptV1:
                    raise TypeError('execution source receipt must be ExecutionSourceReceiptV1')
                if (receipt.source_id != self.scene_source.source_id
                        or receipt.canonical_xml_sha256 != hashlib.sha256(self.scene_source.xml.encode('utf-8')).hexdigest()):
                    raise ValueError('execution source receipt differs from its RuntimeSource XML/label')
                if (self.source_closure_digest is not None
                        and self.source_closure_digest != receipt.source_closure_digest):
                    raise ValueError('RuntimeSource closure digest differs from its source receipt')
            elif self.source_closure_digest is not None:
                raise ValueError('legacy source closure digest requires an immutable execution source receipt')
            return
        if self.execution_source_receipt is not None:
            raise ValueError('versioned execution source receipt is only admitted for the frozen v0 NutAssembly route')
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
