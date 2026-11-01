"""Advanced Phase-I source bridge. Semantic names map to source names, never IDs."""
from dataclasses import dataclass, field
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import hashlib
import math
import os
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET

from ...artifacts import SceneDefinition, TaskArtifactV1
from ...assembly.source import TaskSceneSource, UsdTaskSceneSourceV1
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
    source_floating_joints: dict[str, list[ET.Element]] = {}
    for node in root.iter('freejoint'):
        name = node.get('name')
        if name:
            source_floating_joints.setdefault(name, []).append(node)
    for node in root.iter('joint'):
        name = node.get('name')
        if name and node.get('type') == 'free':
            source_floating_joints.setdefault(name, []).append(node)

    for articulation in scene_definition.articulations or ():
        for joint in articulation.joints:
            if joint.kind == 'fixed':
                continue
            if joint.kind == 'floating':
                if (joint.position_representation != 'xyz_meter_quaternion_wxyz'
                        or joint.velocity_representation != (
                            'linear_xyz_meter_per_second_angular_xyz_radian_per_second'
                        )
                        or joint.position_size != 7 or joint.velocity_size != 6):
                    raise ValueError(
                        f'unsupported canonical MJCF floating Joint representation: {joint.joint_id!r}'
                    )
                matches = source_floating_joints.get(joint.joint_id, ())
                if len(matches) != 1:
                    raise ValueError(
                        f'canonical floating Joint {joint.joint_id!r} must resolve to exactly one '
                        f'MJCF free Joint; found {len(matches)}'
                    )
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
    mixed_actuator_plan: object | None = None
    task_local_joint_limit_tolerance_overrides: Mapping[str, float] = field(default_factory=dict)

    @property
    def source_id(self) -> str:
        """Expose the canonical TaskSceneSource identity used by Core receipts."""
        return self.scene_source.source_id

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
        tolerances = dict(self.task_local_joint_limit_tolerance_overrides)
        if any(type(name) is not str or not name.strip() for name in tolerances):
            raise TypeError('task-local joint limit tolerances require semantic joint names')
        if set(tolerances) - set(self.joints):
            raise ValueError('task-local joint limit tolerances must bind source joint semantics')
        if any(isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0.0
               for value in tolerances.values()):
            raise ValueError('task-local joint limit tolerances must be finite and positive')
        object.__setattr__(self, 'task_local_joint_limit_tolerance_overrides', MappingProxyType(
            {name: float(value) for name, value in tolerances.items()}
        ))
        groups = {str(entity): tuple(names) for entity, names in dict(self.contact_geom_groups).items()}
        if any(not entity.strip() or not names or any(type(name) is not str or not name.strip() for name in names)
               or len(set(names)) != len(names) for entity, names in groups.items()):
            raise ValueError('contact geom groups require unique named source geoms')
        object.__setattr__(self, 'contact_geom_groups', MappingProxyType(groups))
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
        if self.mixed_actuator_plan is not None:
            from ...controllers.canonical.contracts import MixedActuatorPlanV1
            plan = self.mixed_actuator_plan
            if type(plan) is not MixedActuatorPlanV1:
                raise TypeError('mixed actuator source binding requires MixedActuatorPlanV1')
            plan.validate()
            if (plan.task_artifact_hash != self.task_artifact_hash
                    or plan.source_id != self.scene_source.source_id
                    or plan.source_closure_digest != self.source_closure_digest):
                raise ValueError('mixed actuator plan does not bind this Artifact/source/closure')
            declared = {item.semantic_id: item for item in plan.channels}
            expected = {
                **{name: ('joint_torque', actuator, 'N*m')
                   for name, actuator in self.torque_actuators.items()},
                **{name: ('joint_position', actuator, self.actuator_units[actuator])
                   for name, actuator in self.position_actuators.items()},
            }
            if set(declared) != set(expected):
                raise ValueError('mixed actuator plan does not cover the source control channels exactly')
            for semantic, channel in declared.items():
                drive, actuator, unit = expected[semantic]
                if (channel.drive_mode, channel.actuator_name, channel.unit) != (drive, actuator, unit):
                    raise ValueError(f'mixed actuator plan differs from the source channel: {semantic}')
                if semantic not in self.joints or channel.joint_name != self.joints[semantic]:
                    raise ValueError(f'mixed actuator plan joint differs from source binding: {semantic}')
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
    def task_artifact_hash(self) -> str:
        """Compatibility spelling for existing Core source-bound Controllers."""
        return self.task_artifact.identity_hash

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
        task_joint_names = set(self.task_artifact.legacy_joint_bindings)
        missing_task_scalar_bindings = scalar_names - task_joint_names
        if missing_task_scalar_bindings:
            raise ValueError(
                'USD RuntimeSource scalar Joint map is missing TaskArtifact v1 bindings: '
                f'{sorted(missing_task_scalar_bindings)}'
            )
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
