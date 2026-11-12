"""Advanced Phase-I source bridge. Semantic names map to source names, never IDs."""
from dataclasses import dataclass, field
from contextlib import contextmanager
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

from ...artifacts import FrameReference, SceneDefinition, TaskArtifactV1
from ...assembly.source import TaskSceneSource, UsdTaskSceneSourceV1
from ...assembly.assets import _source_closure_digest


def source_resource_receipt(source):
    """Return the snapshot owned by a RuntimeSource, independent of projection."""
    return (getattr(source, 'source_snapshot_receipt', None)
            or getattr(source, 'execution_source_receipt', None))


def close_source_and_task_resources(source, binding, *, error=None):
    """Release owned source and Task resources, preserving the first failure."""
    receipt = source_resource_receipt(source)
    for label, operation in (('source receipt cleanup', getattr(receipt, 'close', None)),
                             ('task resource cleanup', getattr(binding, 'close_task_resources', None))):
        if not callable(operation):
            continue
        try:
            operation()
        except BaseException as cleanup_error:
            if error is None:
                error = cleanup_error
            else:
                error.add_note(f'{label} also failed: {cleanup_error!r}')
    return error


@contextmanager
def close_execution_source_on_failure(source):
    """Keep a source lease on success; release it if its owner cannot be built."""
    try:
        yield source
    except BaseException as error:
        receipt = source_resource_receipt(source)
        if receipt is not None:
            try:
                receipt.close()
            except BaseException as cleanup_error:
                error.add_note(f'execution source cleanup also failed: {cleanup_error!r}')
        raise


def position_frame_bindings_from_artifact(artifact, source):
    """Resolve runtime body/Frame names through their exact Artifact references."""
    semantics = (*source.bodies, *source.frames)
    if len(semantics) != len(set(semantics)):
        raise ValueError('Position RuntimeSource body/Frame semantics must be unique')
    bindings = {}
    for semantic in semantics:
        reference = artifact.legacy_frame_bindings.get(semantic)
        if type(reference) is not FrameReference:
            raise ValueError('Position RuntimeSource semantic lacks an exact Artifact FrameReference')
        bindings[semantic] = reference
    return bindings


def position_joint_bindings_from_artifact(scene, artifact, source):
    """Bind scalar joints and resolve each reset Frame to its unique floating Joint."""
    bindings = {
        f'{articulation.entity_id}/{joint.joint_id}': joint
        for articulation in scene.articulations or ()
        for joint in articulation.joints
        if joint.kind in {'revolute', 'continuous', 'prismatic'}
    }
    for reset_frame_name in source.free_joints:
        frame_reference = artifact.legacy_frame_bindings.get(reset_frame_name)
        if frame_reference is None:
            raise ValueError('free-body reset key lacks an Artifact Frame binding')
        candidates = tuple(
            joint
            for articulation in scene.articulations or ()
            if articulation.entity_id == frame_reference.entity_id
            for joint in articulation.joints
            if joint.kind == 'floating' and joint.child_frame == frame_reference
        )
        if len(candidates) != 1:
            raise ValueError('reset Frame must resolve to exactly one Scene floating Joint')
        if reset_frame_name in bindings:
            raise ValueError('free-body reset Joint binding overlaps a scalar binding')
        bindings[reset_frame_name] = candidates[0]
    return bindings


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


def snapshot_legacy_mjcf_source(source):
    """Capture the files actually referenced by an existing Panda MJCF source.

    Canonical XML remains unchanged. The importer XML points at the existing
    receipt snapshot and its bytes are consumed directly by the adapter.
    """
    from dataclasses import replace
    if source.scene_definition is not None or source.execution_source_receipt is not None:
        return source
    xml = source.scene_source.xml
    root = ET.fromstring(xml)
    compiler = root.find('compiler')
    if compiler is None:
        raise ValueError('selected MJCF source has no compiler')
    allowed = []
    for component in (*source.agents, *source.objects):
        manifest = component.asset_manifest()
        if manifest.owner_uid != component.uid:
            raise ValueError('MJCF component asset manifest has a foreign owner')
        allowed.extend(path.resolve() for path in manifest.asset_roots)
    files = {'canonical-source.xml': xml.encode('utf-8')}
    total = 0
    for node in root.iter():
        raw = node.get('file')
        if raw is None:
            continue
        if node.tag not in {'mesh', 'skin', 'texture'}:
            raise ValueError(f'unsupported MJCF external reference: {node.tag}')
        rel = Path(raw)
        if rel.is_absolute() or '\\' in raw or any(part in {'', '.', '..'} for part in rel.parts):
            raise ValueError(f'unsafe MJCF asset reference: {raw!r}')
        attr = 'texturedir' if node.tag == 'texture' else 'meshdir'
        directory = Path(compiler.get(attr, compiler.get('meshdir', '')))
        if not directory.is_absolute():
            directory = source.scene_source.base_dir / directory
        directory = directory.resolve()
        if not any(directory.is_relative_to(root) for root in allowed):
            raise ValueError(f'MJCF {attr} is outside declared component asset roots')
        path = (directory / rel).resolve()
        if not path.is_relative_to(directory):
            raise ValueError('MJCF asset escaped its declared directory')
        if not path.is_file():
            raise ValueError(f'MJCF asset is missing: {raw!r}')
        data = path.read_bytes()
        total += len(data)
        if total > 128 * 1024 * 1024:
            raise ValueError('selected MJCF referenced assets exceed 128 MiB')
        key = 'assets/' + rel.as_posix()
        if key in files and files[key] != data:
            raise ValueError(f'MJCF asset alias differs: {key}')
        files[key] = data
    compiler.set('meshdir', 'assets')
    if compiler.get('texturedir') is not None:
        compiler.set('texturedir', 'assets')
    importer = ET.tostring(root, encoding='utf-8')
    receipt = ExecutionSourceReceiptV1.create(source_id=source.scene_source.source_id,
        canonical_xml=xml.encode('utf-8'), importer_xml=importer, closure_files=files)
    try:
        return replace(source, execution_source_receipt=receipt,
                       source_closure_digest=receipt.source_closure_digest)
    except BaseException:
        receipt.close()
        raise


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


def project_mjcf_scene_source(scene_source, scene_definition):
    """Project one MJCF Scene and calculate its bounded source closure."""
    if not isinstance(scene_source, TaskSceneSource):
        raise TypeError('MJCF Scene lowering requires the public TaskSceneSource value')
    if not isinstance(scene_definition, SceneDefinition):
        raise TypeError('MJCF Scene lowering requires the canonical SceneDefinition')
    projected = project_scene_definition_v3_to_mjcf(scene_source.xml, scene_definition)
    assets = source_asset_bytes(scene_source.base_dir, projected)
    closure = _source_closure_digest({'scene.xml': projected.encode('utf-8'), **assets})
    return projected, assets, closure


def verify_projected_scene_source(scene_source, scene_definition, expected_closure_digest: str):
    """Project a canonical Scene and verify its XML and asset closure."""
    if not re.fullmatch(r'[0-9a-f]{64}', str(expected_closure_digest)):
        raise ValueError('MJCF Scene lowering requires a source closure SHA-256')
    projected, assets, closure = project_mjcf_scene_source(scene_source, scene_definition)
    if closure != expected_closure_digest:
        raise ValueError('MuJoCo canonical source closure digest mismatch')
    return projected, assets


def bind_reference_scene_source(source, *, artifact, scene, bodies, frames):
    """Bind a declared Scene to its owned MJCF snapshot without native I/O."""
    from dataclasses import replace
    receipt = source.execution_source_receipt
    receipt.validate_snapshot()
    scene_source = TaskSceneSource(receipt.importer_xml.decode('utf-8'), receipt.snapshot_root,
                                   f'scene-definition-v3:{scene.identity_hash}')
    projected, _, closure = project_mjcf_scene_source(scene_source, scene)
    bound = replace(source, task_artifact_hash=artifact.identity_hash,
        scene_source=scene_source, scene_definition=scene, source_closure_digest=closure,
        execution_source_receipt=None, source_snapshot_receipt=receipt,
        bodies=bodies, frames=frames)
    return bound, projected, closure


def lower_mujoco_scene_source(scene_source, scene_definition, expected_closure_digest: str):
    """Verify the common Scene source and lower it for the MuJoCo importer."""
    source_xml, assets = verify_projected_scene_source(
        scene_source, scene_definition, expected_closure_digest)
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
    composition_runtime_input: object | None = None
    position_subject_binding: object | None = None
    source_reference_plan: object | None = None
    source_composition_request: object | None = None
    source_composition_intent: object | None = None
    source_snapshot_receipt: ExecutionSourceReceiptV1 | None = None

    @property
    def source_id(self) -> str:
        """Expose the canonical TaskSceneSource identity used by Core receipts."""
        return self.scene_source.source_id

    @property
    def position_subject_plan(self):
        """Expose the source-owned Position plan independently of native mapping."""
        return self.position_subject_binding

    def __post_init__(self):
        snapshot = self.source_snapshot_receipt
        if snapshot is not None:
            if (type(snapshot) is not ExecutionSourceReceiptV1 or self.scene_definition is None
                    or self.execution_source_receipt is not None
                    or Path(self.scene_source.base_dir).resolve() != snapshot.snapshot_root
                    or self.scene_source.xml.encode('utf-8') != snapshot.importer_xml):
                raise ValueError('canonical source snapshot differs from its owned input')
            snapshot.validate_snapshot()
        if self.source_composition_request is not None:
            from ...assembly.source_composition import (
                SourceCompositionIntentV1, SourceCompositionRequestV2,
            )
            request = self.source_composition_request
            if (type(request) is not SourceCompositionRequestV2
                    or request.task_source.source_id != self.scene_source.source_id
                    or request.task_source.closure_sha256 != self.source_closure_digest):
                raise ValueError('V2 composition request differs from RuntimeSource provenance')
            intent = self.source_composition_intent
            if (type(intent) is not SourceCompositionIntentV1
                    or intent.identity_hash != request.intent_identity_sha256
                    or intent.task_source_id != request.task_source.source_id
                    or intent.task_source_closure_sha256 != request.task_source.closure_sha256
                    or intent.task_entity_ids != request.task_entity_ids
                    or intent.existing_robot_entity_ids != request.existing_robot_entity_ids
                    or intent.robot_uid != request.robot_uid or intent.mode != request.mode):
                raise ValueError('V2 composition request lacks its matching pre-parse intent')
            intent_entities = {entity for item in intent.robot_sources for entity in item.entity_ids}
            request_entities = {entity for item in request.robot_sources for entity in item.entity_ids}
            if intent_entities != request_entities:
                raise ValueError('resolved Robot source ownership differs from composition intent')
            intent_edges = set(intent.component_edges)
            request_edges = {(item.parent_entity_id, item.parent_frame_id,
                              item.child_entity_id, item.child_frame_id, item.rule_id)
                             for item in request.attachments}
            if intent_edges != request_edges:
                raise ValueError('resolved attachment edges differ from composition intent')
            if set(intent.resource_writers) != set(request.resource_writers):
                raise ValueError('resolved resource writers differ from composition intent')
            if request.mode == 'reference':
                if self.source_reference_plan is None or self.source_reference_plan.robot_uid != request.robot_uid:
                    raise ValueError('V2 reference request lacks its compatible V1 reference projection')
            elif self.composition_runtime_input is None or self.composition_runtime_input.plan.robot_uid != request.robot_uid:
                raise ValueError('V2 add/replace request lacks its provider materialization input')
        if self.source_reference_plan is not None:
            from ...assembly.source_composition import SourceCompositionPlanV1
            reference = self.source_reference_plan
            if (type(reference) is not SourceCompositionPlanV1 or reference.mode != 'reference'
                    or reference.task_source.source_id != self.scene_source.source_id
                    or reference.task_source.closure_sha256 != self.source_closure_digest):
                raise ValueError('reference source composition differs from RuntimeSource')
            if self.composition_runtime_input is not None:
                raise ValueError('reference and replacement compositions are mutually exclusive')
            if self.position_subject_binding is None or self.position_subject_binding.identity_hash != reference.position_binding_identity_sha256:
                raise ValueError('reference source position mapping identity differs from its plan')
        if self.position_subject_binding is not None:
            from ...assembly.source_composition import PositionSubjectControlBindingV1
            binding = self.position_subject_binding
            if type(binding) is not PositionSubjectControlBindingV1:
                raise TypeError('position subject binding requires its exact typed value')
            if (binding.plan.artifact_identity_hash != self.task_artifact_hash
                    or binding.plan.source_closure_digest != self.source_closure_digest):
                raise ValueError('position subject binding differs from RuntimeSource identity')
            declared_joints = {semantic: native for semantic, _entity, _joint, native, _actuator
                               in binding.joint_native_ownership}
            if dict(self.joints) != declared_joints:
                raise ValueError('position semantic joint mapping differs from declared subject ownership')
            native_resources = {(entity, actuator): native for entity, actuator, native
                                in binding.resource_native_names}
            for semantic, entity, _joint, _native, actuator in binding.joint_native_ownership:
                if semantic in self.joint_targets and self.joint_targets[semantic] != native_resources[(entity, actuator)]:
                    raise ValueError('position joint target maps to the wrong subject actuator')
        if self.composition_runtime_input is not None:
            from ...assembly.source_composition import CompositionRuntimeInputV1
            value = self.composition_runtime_input
            if type(value) is not CompositionRuntimeInputV1:
                raise TypeError('composition input must be CompositionRuntimeInputV1')
            if self.execution_source_receipt is None:
                raise ValueError('composition input requires a verified task source receipt')
            binding = self.position_subject_binding
            if binding is not None and binding.identity_hash != value.plan.position_binding_identity_sha256:
                raise ValueError('composition source position mapping identity differs from its plan')
            if value.control_binding_plan is not None and (
                    binding is None or binding.plan.identity_hash != value.control_binding_plan.identity_hash
                    or binding.subject_identity_sha256 != value.subject_binding_identity_sha256):
                raise ValueError('composition input requires the same declared position subject binding')
            if (value.plan.task_source.source_id != self.scene_source.source_id
                    or value.plan.task_source.closure_sha256 != self.source_closure_digest):
                raise ValueError('composition plan differs from task RuntimeSource identity')
            if self.fixed_attachment_plan is not None or self.scene_definition is not None:
                raise ValueError('composition input cannot alias an existing fixed or canonical source')
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
        if self.mixed_actuator_plan is not None and self.position_subject_binding is not None:
            raise ValueError('position subject and mixed actuator writers cannot share a RuntimeSource')
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
class PositionSubjectPlanV1:
    """Source-bound Position subjects and their compiled Controller plan."""

    plan: object
    subject_identity_sha256: str
    subjects: tuple

    def __post_init__(self):
        from .control import ControlBindingPlanV1, position_subject_identity
        from .physical_control import ControlledSubjectV1
        if type(self.plan) is not ControlBindingPlanV1 or not self.plan._compiled:
            raise TypeError('Position subjects require a compiled Controller plan')
        if (type(self.subjects) is not tuple or not self.subjects
                or any(type(subject) is not ControlledSubjectV1 for subject in self.subjects)):
            raise TypeError('Position plan requires declared controlled subjects')
        if position_subject_identity(self.plan, self.subjects) != self.subject_identity_sha256:
            raise ValueError('Position subjects differ from their compiled identity')
        owners = {(subject.entity_id, writer) for subject in self.subjects
                  for writer in subject.controller_writers}
        plan_owners = {(entity, writer) for entity, _resource, writer in self.plan.resource_writers}
        if owners != plan_owners:
            raise ValueError('Position subjects differ from Controller resource owners')


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
    position_subject_plan: PositionSubjectPlanV1 | None = None

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
        if self.position_subject_plan is not None:
            binding = self.position_subject_plan
            if type(binding) is not PositionSubjectPlanV1:
                raise TypeError('USD Position subjects require a typed source plan')
            plan = binding.plan
            if (plan.scene_identity_hash != self.scene_definition.identity_hash
                    or plan.artifact_identity_hash != self.task_artifact.identity_hash
                    or plan.source_closure_digest != self.source_closure_digest
                    or any(subject.source_id != self.source_id
                           or subject.source_closure_sha256 != self.source_closure_digest
                           for subject in binding.subjects)):
                raise ValueError('USD Position subjects differ from their Scene, Artifact or source')
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


def build_usd_runtime_source(*, loaded, representation, task_source_identity_sha256,
                             scene, artifact, joints, bodies, frames, free_joints,
                             joint_targets):
    """Bind admitted USD bytes and declared native mappings to a Task source."""
    scene_source = UsdTaskSceneSourceV1('usd-task-scene-source-v1', loaded, representation,
                                        task_source_identity_sha256, scene.identity_hash)
    return UsdRuntimeSourceV1('usd-runtime-source-v1', artifact, scene, scene_source,
                              joints, bodies, frames, free_joints, joint_targets)


def validate_usd_task_reset_identities(task_source, artifact, source, reset_plan, *, error_message):
    """Check the shared source/scene/artifact/reset identity closure.

    Callers validate the contract types and each object's own fields first;
    provider and task-specific admission remain with their respective owners.
    """
    scene = source.scene_definition
    if (source.task_artifact.identity_hash != artifact.identity_hash
            or artifact.scene_identity_hash != scene.identity_hash
            or source.scene_source.task_source_identity_sha256 != task_source.identity_hash
            or source.scene_source.scene_identity_sha256 != scene.identity_hash
            or reset_plan.role_binding.task_source_identity_hash != task_source.identity_hash
            or reset_plan.role_binding.scene_identity_hash != scene.identity_hash
            or reset_plan.reset_sample.task_artifact_hash != artifact.identity_hash):
        raise ValueError(error_message)


@dataclass(frozen=True)
class UsdRuntimeInputV1:
    """Source-bound USD session inputs; admission policy remains in runtime."""
    schema_version: str
    task_source: object
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: object
    reset_plan: object
    controller_profile: str
    horizon: int
    delivery_manifest_sha256: str
    admission_policy: Mapping | None = None

    def validate(self):
        from ...artifacts import ExecutionSpecV1
        from ...artifacts.execution import EpisodeResetPlanV1
        from ...environment.task_source import TaskSourceV1
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1):
            raise TypeError("USD RuntimeInput requires exact TaskSource/Artifact/USD/Execution/reset contracts")
        self.artifact.validate()
        self.runtime_source.validate()
        self.execution.validate()
        self.reset_plan.validate()
        self.reset_plan.role_binding.validate()
        self.reset_plan.reset_sample.validate()
        if self.runtime_source.task_artifact is not self.artifact:
            raise ValueError("USD RuntimeSource must reference the exact TaskArtifact")
        if (self.runtime_source.scene_source.task_source_identity_sha256
                != self.task_source.identity_hash
                or self.runtime_source.scene_source.scene_identity_sha256
                != self.runtime_source.scene_definition.identity_hash):
            raise ValueError("USD RuntimeSource must bind the exact TaskSource and Scene")
        if (self.artifact.task_source_identity_hash != self.task_source.identity_hash
                or self.artifact.scene_identity_hash != self.runtime_source.scene_definition.identity_hash
                or self.reset_plan.role_binding.task_source_identity_hash != self.task_source.identity_hash
                or self.reset_plan.role_binding.scene_identity_hash != self.runtime_source.scene_definition.identity_hash
                or self.reset_plan.reset_sample.task_artifact_hash != self.artifact.identity_hash):
            raise ValueError("USD RuntimeInput TaskSource/Scene/Artifact/reset identities disagree")
