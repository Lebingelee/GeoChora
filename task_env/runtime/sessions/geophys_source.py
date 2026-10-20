"""The only conversion of a neutral MJCF description to GeoPhys SceneSource."""
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from ...assembly.assets import _source_closure_digest
from ...assembly.source import TaskSceneSource


def native_scene_source(source: TaskSceneSource):
    from scene import SceneSource
    return SceneSource.mjcf_string(source.xml, base_dir=source.base_dir, label=source.source_id)


def project_scene_definition_v3_to_mjcf(source_xml: str, scene_definition) -> str:
    """Apply the supported v3 scalar-joint axes to the MJCF import source.

    This is a deliberately narrow compatibility projection. The Provider's
    public importer remains responsible for parsing and lowering MJCF; fields
    outside this projection stay source-owned and must be reported separately.
    """

    scene_definition.validate()
    if scene_definition.schema_version != 'scene-definition-v3':
        raise ValueError('GeoPhys compatibility projection requires scene-definition-v3')
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
                raise ValueError(f'unsupported D01a joint representation: {joint.joint_id!r}')
            matches = source_joints.get(joint.joint_id, ())
            if len(matches) != 1:
                raise ValueError(
                    f'canonical joint {joint.joint_id!r} must resolve to exactly one MJCF joint; '
                    f'found {len(matches)}'
                )
            matches[0].set('axis', ' '.join(format(float(value), '.17g') for value in joint.axis))
    return ET.tostring(root, encoding='unicode')


def source_closure_digest_for_import(imported_scene, source: TaskSceneSource, source_xml: str) -> str:
    """Digest exactly the root XML and external bytes consumed by one import."""

    if source.base_dir is None:
        if imported_scene.dependency_paths:
            raise ValueError('imported source dependencies require a bounded base_dir')
        files = {'scene.xml': source_xml.encode('utf-8')}
    else:
        base = Path(source.base_dir).resolve()
        files = {'scene.xml': source_xml.encode('utf-8')}
        for raw_path in imported_scene.dependency_paths:
            path = Path(raw_path).resolve()
            try:
                logical_path = path.relative_to(base).as_posix()
            except ValueError as exc:
                raise ValueError(f'import dependency escaped the declared source closure: {path}') from exc
            if logical_path == 'scene.xml':
                raise ValueError('scene.xml cannot also be an external importer dependency')
            files[logical_path] = path.read_bytes()
    return _source_closure_digest(files)


def _pose_matrix(pose) -> np.ndarray:
    w, x, y, z = (float(value) for value in pose.quaternion_wxyz)
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    )
    matrix[:3, 3] = tuple(float(value) for value in pose.position)
    return matrix


def validate_canonical_scene_import(scene_definition, imported_scene) -> dict[str, object]:
    """Fail closed unless the public ImportedScene matches the v3 projection."""

    scene_definition.validate()
    if scene_definition.schema_version != 'scene-definition-v3':
        raise ValueError('GeoPhys import mapping requires scene-definition-v3')
    bodies = {body.name: body for body in imported_scene.ir.bodies}
    if len(bodies) != len(imported_scene.ir.bodies):
        raise ValueError('GeoPhys import contains ambiguous body names')
    expected_frames = [frame for frame in scene_definition.frames or () if frame.frame_kind == 'runtime']
    expected_names = [frame.frame_id for frame in expected_frames]
    if len(set(expected_names)) != len(expected_names):
        raise ValueError('D01a projection requires globally unique native frame names')
    if set(expected_names) != set(bodies):
        missing = sorted(set(expected_names) - set(bodies))
        extra = sorted(set(bodies) - set(expected_names))
        raise ValueError(f'canonical Frame mapping mismatch: missing={missing}, extra={extra}')

    body_names_by_id = {body.body_id: body.name for body in imported_scene.ir.bodies}
    frames_by_id = {frame.node_id: frame for frame in imported_scene.ir.frames}
    joints_by_name = {
        str(joint.dynamics.get('source_name')): joint
        for joint in imported_scene.ir.joints
        if joint.dynamics.get('source_name')
    }
    canonical_dynamic: dict[str, object] = {}
    canonical_fixed = []
    for articulation in scene_definition.articulations or ():
        for joint in articulation.joints:
            if joint.kind == 'fixed':
                canonical_fixed.append((articulation.entity_id, joint))
            else:
                if joint.joint_id in canonical_dynamic:
                    raise ValueError(f'ambiguous canonical joint ID: {joint.joint_id!r}')
                canonical_dynamic[joint.joint_id] = joint
    if set(canonical_dynamic) != set(joints_by_name):
        missing = sorted(set(canonical_dynamic) - set(joints_by_name))
        extra = sorted(set(joints_by_name) - set(canonical_dynamic))
        raise ValueError(f'canonical Joint mapping mismatch: missing={missing}, extra={extra}')

    joint_rows = []
    for name, definition in sorted(canonical_dynamic.items()):
        imported = joints_by_name[name]
        parent_name = body_names_by_id.get(imported.body_a)
        child_name = body_names_by_id.get(imported.body_b)
        if (parent_name, child_name) != (
            definition.parent_frame.frame_id,
            definition.child_frame.frame_id,
        ):
            raise ValueError(f'canonical Joint endpoints do not match imported joint {name!r}')
        if not np.allclose(np.asarray(imported.axis), np.asarray(definition.axis), rtol=0.0, atol=1e-9):
            raise ValueError(f'canonical Joint axis was not consumed for {name!r}')
        if not np.allclose(
            np.asarray(imported.frame_a, dtype=np.float64).reshape(4, 4),
            _pose_matrix(definition.pose_parent_from_joint), rtol=0.0, atol=1e-8,
        ) or not np.allclose(
            np.asarray(imported.frame_b, dtype=np.float64).reshape(4, 4),
            _pose_matrix(definition.pose_child_from_joint), rtol=0.0, atol=1e-8,
        ):
            raise ValueError(f'canonical Joint frame transforms do not match import for {name!r}')
        joint_rows.append({
            'entity_id': definition.parent_frame.entity_id,
            'joint_id': name,
            'parent_frame_id': parent_name,
            'child_frame_id': child_name,
            'axis': tuple(float(value) for value in definition.axis),
            'core_disposition': 'CANONICAL_REPRESENTED',
            'provider_consumption': 'ImportedScene.ir.joints',
        })

    fixed_rows = []
    for entity_id, definition in canonical_fixed:
        parent_body = bodies.get(definition.parent_frame.frame_id)
        child_body = bodies.get(definition.child_frame.frame_id)
        if parent_body is None or child_body is None:
            raise ValueError(f'canonical fixed Joint {definition.joint_id!r} has a missing Frame')
        child_frame = frames_by_id.get(child_body.frame_id)
        if child_frame is None or child_frame.parent_id != parent_body.frame_id:
            raise ValueError(f'canonical fixed Joint {definition.joint_id!r} does not match imported frame tree')
        if not np.allclose(
            np.asarray(child_frame.local_transform, dtype=np.float64).reshape(4, 4),
            _pose_matrix(definition.pose_parent_from_joint), rtol=0.0, atol=1e-8,
        ):
            raise ValueError(f'canonical fixed Joint transform does not match import for {definition.joint_id!r}')
        fixed_rows.append({
            'entity_id': entity_id,
            'joint_id': definition.joint_id,
            'parent_frame_id': definition.parent_frame.frame_id,
            'child_frame_id': definition.child_frame.frame_id,
            'core_disposition': 'CANONICAL_REPRESENTED',
            'provider_consumption': 'ImportedScene.ir.frames',
        })

    expected_actuators = {resource.actuator_id for resource in scene_definition.actuator_resources or ()}
    imported_actuators = {
        str(actuator.parameters.get('source_name'))
        for actuator in imported_scene.ir.actuators
        if actuator.parameters.get('source_name')
    }
    if expected_actuators != imported_actuators:
        missing = sorted(expected_actuators - imported_actuators)
        extra = sorted(imported_actuators - expected_actuators)
        raise ValueError(f'canonical Actuator mapping mismatch: missing={missing}, extra={extra}')
    return {
        'schema_version': 'geochora.scene-v3-import-mapping-v1',
        'scene_identity': scene_definition.identity_hash,
        'frames': [
            {'entity_id': frame.entity_id, 'frame_id': frame.frame_id,
             'core_disposition': 'CANONICAL_REPRESENTED',
             'provider_consumption': 'ImportedScene.ir.bodies'}
            for frame in expected_frames
        ],
        'joints': joint_rows + fixed_rows,
        'actuator_resources': [
            {'actuator_id': actuator_id, 'core_disposition': 'CANONICAL_REPRESENTED',
             'provider_consumption': 'ImportedScene.ir.actuators'}
            for actuator_id in sorted(expected_actuators)
        ],
        'source_geometry_disposition': 'SOURCE_RETAINED',
        'source_inertial_disposition': 'SOURCE_RETAINED',
        'source_contact_disposition': 'SOURCE_RETAINED',
        'source_constraint_disposition': 'SOURCE_RETAINED',
        'source_transmission_disposition': 'SOURCE_RETAINED',
    }


class GeoPhysSourceComposer:
    adapter_name = 'task_env_neutral_mjcf_bridge_v0'

    def __init__(self, source, *, scene_definition=None, source_closure_digest=None):
        self._source = source
        self._scene_definition = scene_definition
        self._source_closure_digest = source_closure_digest
        self._projected_xml = None
        if (scene_definition is None) != (source_closure_digest is None):
            raise ValueError('canonical Scene and source closure digest must be provided together')
        if scene_definition is not None and source.source_id != f'scene-definition-v3:{scene_definition.identity_hash}':
            raise ValueError('source ID does not bind the canonical Scene identity')

    def build_scene_source(self, composition, agents):
        if self._scene_definition is None:
            return native_scene_source(self._source), self.adapter_name
        self._projected_xml = project_scene_definition_v3_to_mjcf(
            self._source.xml, self._scene_definition,
        )
        from scene import SceneSource
        return (
            SceneSource.mjcf_string(
                self._projected_xml,
                base_dir=self._source.base_dir,
                label=self._source.source_id,
            ),
            'task_env_scene_definition_v3_geophys_bridge_v1',
        )

    def build_scene_model(self, imported_scene, composition):
        if self._scene_definition is not None:
            if self._projected_xml is None:
                raise RuntimeError('canonical Scene source must be built before model lowering')
            actual_digest = source_closure_digest_for_import(
                imported_scene, self._source, self._projected_xml,
            )
            if actual_digest != self._source_closure_digest:
                raise ValueError('canonical Scene source closure digest mismatch')
            validate_canonical_scene_import(self._scene_definition, imported_scene)
        # The public lowering resolves canonical mesh IDs through its imported
        # resource table; disabling that table leaves IDs as unreadable paths.
        scene_model = imported_scene.build_rigid_scene_model(use_imported_meshes=True)
        if self._scene_definition is not None:
            raw_geom_count = sum(
                1 for geom in ET.fromstring(self._projected_xml).iter('geom')
                if geom.get('name')
            )
            if int(scene_model.joint_data.get('n_geoms', -1)) <= 0 or len(imported_scene.ir.shapes) < raw_geom_count:
                raise ValueError('canonical Scene source geometry was not fully imported')
        return scene_model
