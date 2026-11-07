"""Bounded provider-neutral static triangle source; dynamic cameras are separate."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import numpy as np
import re
from ...artifacts.contracts import (
    Contract,
    ExecutionSpecV1,
    ProviderCapabilityManifest,
    RendererSelectionV1,
    _choice,
    _name,
)
from ...artifacts.state import CanonicalStateViewV1, StateBoundaryIdentity, StateSampleClock
from ...artifacts.contracts import SceneDefinition
from ...assembly.source import TaskSceneSource
from ...observations.canonical_camera.contracts import CameraGeometry


@dataclass(frozen=True)
class TriangleMesh(Contract):
    semantic_id: str
    vertices_world: tuple[tuple[float,float,float], ...]
    faces: tuple[tuple[int,int,int], ...]
    color_rgb: tuple[float,float,float]

    def validate(self):
        _name(self.semantic_id)
        if len(self.vertices_world) < 4 or not self.faces:
            raise ValueError('nonempty volume mesh required by native pairings')
        if any(i < 0 or i >= len(self.vertices_world) for face in self.faces for i in face):
            raise ValueError('mesh face outside vertices')
        if any(not 0 <= v <= 1 for v in self.color_rgb):
            raise ValueError('invalid RGB material')
        points = np.array(self.vertices_world)
        if any(np.linalg.norm(np.cross(points[b]-points[a],points[c]-points[a])) <= 1e-12 for a,b,c in self.faces):
            raise ValueError('degenerate triangle')


@dataclass(frozen=True)
class CameraRenderSource(Contract):
    schema_version: str
    task_artifact_hash: str
    meshes: tuple[TriangleMesh, ...]

    def validate(self):
        if self.schema_version != 'camera-static-triangles-v0' or len(self.task_artifact_hash) != 64:
            raise ValueError('unsupported render source/schema')
        if not self.meshes or len({m.semantic_id for m in self.meshes}) != len(self.meshes):
            raise ValueError('mesh names must be unique and nonempty')

    @property
    def identity_hash(self):
        return hashlib.sha256(json.dumps(self.to_mapping(),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

    def capture_identity(
        self,
        camera: CameraGeometry,
        execution: ExecutionSpecV1,
        manifest: ProviderCapabilityManifest,
        state: CanonicalStateViewV1,
    ) -> CameraCaptureIdentityV1:
        """Bind a planned capture slot to exact static inputs without claiming capture."""

        if not isinstance(camera, CameraGeometry):
            raise TypeError('capture identity requires CameraGeometry')
        if not isinstance(execution, ExecutionSpecV1):
            raise TypeError('capture identity requires execution-spec-v1')
        if not isinstance(manifest, ProviderCapabilityManifest):
            raise TypeError('capture identity requires an existing provider manifest')
        if not isinstance(state, CanonicalStateViewV1):
            raise TypeError('capture identity requires canonical-state-v1')
        if camera.task_artifact_hash != self.task_artifact_hash:
            raise ValueError('camera/render source TaskArtifact linkage mismatch')

        selection = execution.renderer_for_camera(camera.camera_id)
        if (
            manifest.provider_name != selection.provider
            or manifest.backend != selection.backend
            or manifest.render_profile != selection.profile
            or manifest.determinism_mode != execution.determinism_mode
        ):
            raise ValueError('manifest identity does not describe the selected renderer contract')
        if state.sample_clock.clock_domain != 'evaluation_boundary':
            raise ValueError('camera capture identity requires an evaluation boundary state clock')
        if state.sample_clock.sample_index != state.boundary.control_step:
            raise ValueError('camera capture state clock does not match its boundary')

        modalities = tuple(
            modality
            for modality, enabled in (('rgb', camera.rgb), ('depth', camera.depth))
            if enabled
        )
        return CameraCaptureIdentityV1(
            schema_version='camera-capture-identity-v1',
            task_artifact_hash=camera.task_artifact_hash,
            camera_id=camera.camera_id,
            camera_geometry_identity_hash=camera.identity_hash,
            render_source_identity_hash=self.identity_hash,
            execution_spec_identity_hash=execution.identity_hash,
            renderer_selection=selection,
            provider_manifest_identity_hash=manifest.identity_hash,
            state_boundary=state.boundary,
            sample_clock=state.sample_clock,
            modalities=modalities,
            capture_phase=camera.capture_phase,
        )


@dataclass(frozen=True)
class DynamicRenderJointBindingV1:
    """Canonical scalar Joint to source MJCF joint name."""

    entity_id: str
    joint_id: str
    native_joint_name: str

    def to_mapping(self) -> dict[str, str]:
        return {
            'entity_id': self.entity_id,
            'joint_id': self.joint_id,
            'native_joint_name': self.native_joint_name,
        }


@dataclass(frozen=True)
class DynamicRenderFrameBindingV1:
    """Canonical Frame to source MJCF body name."""

    entity_id: str
    frame_id: str
    native_body_name: str

    def to_mapping(self) -> dict[str, str]:
        return {
            'entity_id': self.entity_id,
            'frame_id': self.frame_id,
            'native_body_name': self.native_body_name,
        }


@dataclass(frozen=True)
class RenderVisualInstanceBindingV1:
    """One rendered geometry instance bound to a Canonical Entity/Frame."""

    entity_id: str
    frame_id: str
    native_body_name: str
    render_geometry_names: tuple[str, ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            'entity_id': self.entity_id,
            'frame_id': self.frame_id,
            'native_body_name': self.native_body_name,
            'render_geometry_names': self.render_geometry_names,
        }


@dataclass(frozen=True)
class DynamicCameraRenderSourceV1:
    """Source identity and explicit bindings for a bounded dynamic MJCF view.

    The backing TaskSceneSource/SceneDefinition are existing immutable source
    values. They are deliberately kept out of the serialized identity; their
    exact canonical identity and consumed asset closure are represented by the
    hashes below.
    """

    schema_version: str
    task_artifact_hash: str
    scene_identity_hash: str
    source_identity: str
    source_closure_digest: str
    scene_source: TaskSceneSource
    scene_definition: SceneDefinition
    joint_bindings: tuple[DynamicRenderJointBindingV1, ...]
    frame_bindings: tuple[DynamicRenderFrameBindingV1, ...]

    @classmethod
    def from_runtime_source(cls, source) -> 'DynamicCameraRenderSourceV1':
        from ...runtime.sessions.source import RuntimeSource

        if not isinstance(source, RuntimeSource):
            raise TypeError('dynamic render source requires the existing RuntimeSource owner value')
        if source.free_joints:
            raise ValueError('D03 first intersection currently admits scalar joints only')
        if source.scene_definition is None or source.source_closure_digest is None:
            raise ValueError('dynamic render source requires a canonical Scene-v3 source closure')

        def split_semantic_id(value: str, kind: str) -> tuple[str, str]:
            if type(value) is not str or value.count('/') != 1:
                raise ValueError(f'{kind} binding key must be Entity-qualified as entity/id')
            entity_id, semantic_id = value.split('/', 1)
            _name(entity_id)
            _name(semantic_id)
            return entity_id, semantic_id

        joints = tuple(
            DynamicRenderJointBindingV1(*split_semantic_id(key, 'Joint'), native)
            for key, native in sorted(source.joints.items())
        )
        frames = tuple(
            DynamicRenderFrameBindingV1(*split_semantic_id(key, 'Frame'), native)
            for key, native in sorted(source.bodies.items())
        )
        result = cls(
            'camera-dynamic-source-v1', source.task_artifact_hash,
            source.scene_definition.identity_hash, source.scene_source.source_id,
            source.source_closure_digest, source.scene_source, source.scene_definition,
            joints, frames,
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != 'camera-dynamic-source-v1':
            raise ValueError('unsupported dynamic render source schema')
        for digest in (self.task_artifact_hash, self.scene_identity_hash, self.source_closure_digest):
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('dynamic render source requires lowercase SHA-256 identities')
        if not isinstance(self.scene_source, TaskSceneSource) or not isinstance(self.scene_definition, SceneDefinition):
            raise TypeError('dynamic render source requires the existing canonical source values')
        self.scene_definition.validate()
        if self.scene_definition.schema_version != 'scene-definition-v3':
            raise ValueError('D03 dynamic render source requires Scene-v3')
        if self.scene_definition.identity_hash != self.scene_identity_hash:
            raise ValueError('dynamic render source Scene identity mismatch')
        if self.source_identity != f'scene-definition-v3:{self.scene_identity_hash}' or self.scene_source.source_id != self.source_identity:
            raise ValueError('dynamic render source ID does not bind its Scene identity')
        if not self.joint_bindings or not self.frame_bindings:
            raise ValueError('dynamic render source requires explicit Joint and Frame bindings')
        joint_keys = tuple((item.entity_id, item.joint_id) for item in self.joint_bindings)
        frame_keys = tuple((item.entity_id, item.frame_id) for item in self.frame_bindings)
        if len(joint_keys) != len(set(joint_keys)) or len({item.native_joint_name for item in self.joint_bindings}) != len(self.joint_bindings):
            raise ValueError('dynamic render Joint bindings must be one-to-one')
        if len(frame_keys) != len(set(frame_keys)) or len({item.native_body_name for item in self.frame_bindings}) != len(self.frame_bindings):
            raise ValueError('dynamic render Frame bindings must be one-to-one')
        for item in self.joint_bindings:
            _name(item.entity_id); _name(item.joint_id); _name(item.native_joint_name)
        for item in self.frame_bindings:
            _name(item.entity_id); _name(item.frame_id); _name(item.native_body_name)

    @property
    def identity_hash(self) -> str:
        self.validate()
        payload = {
            'schema_version': self.schema_version,
            'task_artifact_hash': self.task_artifact_hash,
            'scene_identity_hash': self.scene_identity_hash,
            'source_identity': self.source_identity,
            'source_closure_digest': self.source_closure_digest,
            'joint_bindings': tuple(item.to_mapping() for item in self.joint_bindings),
            'frame_bindings': tuple(item.to_mapping() for item in self.frame_bindings),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    @property
    def geometry_version(self) -> str:
        payload = {
            'schema_version': 'mujoco-dynamic-geometry-v1',
            'source_identity_hash': self.identity_hash,
            'lowering': 'canonical-scene-v3-mujoco-source-v1',
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    def capture_identity(
        self,
        camera: CameraGeometry,
        execution: ExecutionSpecV1,
        manifest: ProviderCapabilityManifest,
        state: CanonicalStateViewV1,
        *,
        additional_modalities: tuple[str, ...] = (),
    ) -> 'CameraCaptureIdentityV1':
        """Bind one successful dynamic capture to its exact public publication."""

        self.validate()
        if not isinstance(camera, CameraGeometry):
            raise TypeError('capture identity requires CameraGeometry')
        if not isinstance(execution, ExecutionSpecV1):
            raise TypeError('capture identity requires execution-spec-v1')
        if not isinstance(manifest, ProviderCapabilityManifest):
            raise TypeError('capture identity requires an existing provider manifest')
        if not isinstance(state, CanonicalStateViewV1):
            raise TypeError('capture identity requires canonical-state-v1')
        if camera.task_artifact_hash != self.task_artifact_hash:
            raise ValueError('camera/render source TaskArtifact linkage mismatch')
        selection = execution.renderer_for_camera(camera.camera_id)
        if (
            manifest.provider_name != selection.provider
            or manifest.backend != selection.backend
            or manifest.render_profile != selection.profile
            or manifest.determinism_mode != execution.determinism_mode
        ):
            raise ValueError('manifest identity does not describe the selected renderer contract')
        if state.boundary.scene_identity_hash != self.scene_identity_hash:
            raise ValueError('capture identity state Scene differs from the dynamic render source')
        if state.sample_clock.clock_domain != 'evaluation_boundary':
            raise ValueError('camera capture identity requires an evaluation boundary state clock')
        if state.sample_clock.sample_index != state.boundary.control_step:
            raise ValueError('camera capture state clock does not match its boundary')
        modalities = tuple(
            modality
            for modality, enabled in (('rgb', camera.rgb), ('depth', camera.depth))
            if enabled
        ) + tuple(additional_modalities)
        if len(modalities) != len(set(modalities)):
            raise ValueError('capture identity modalities must be unique')
        return CameraCaptureIdentityV1(
            schema_version='camera-capture-identity-v1',
            task_artifact_hash=camera.task_artifact_hash,
            camera_id=camera.camera_id,
            camera_geometry_identity_hash=camera.identity_hash,
            render_source_identity_hash=self.identity_hash,
            execution_spec_identity_hash=execution.identity_hash,
            renderer_selection=selection,
            provider_manifest_identity_hash=manifest.identity_hash,
            state_boundary=state.boundary,
            sample_clock=state.sample_clock,
            modalities=modalities,
            capture_phase=camera.capture_phase,
        )


@dataclass(frozen=True)
class DynamicCameraRenderSourceV2(DynamicCameraRenderSourceV1):
    """Scene-bound free-body extension; v1 serialization and behavior are unchanged.

    Free poses are body-origin world transforms in metres and wxyz. Sites are
    admitted as published frames but do not own geometry or a free transform.
    """
    free_bindings: tuple[tuple[str, str, str, str, str], ...]
    published_frame_keys: tuple[tuple[str, str], ...]
    runtime_source: object = None
    artifact: object = None

    @classmethod
    def from_runtime_source(cls, source, *, artifact, joint_bindings, frame_bindings):
        from ...runtime.sessions.source import RuntimeSource
        if not isinstance(source, RuntimeSource):
            raise TypeError('dynamic render source requires RuntimeSource')
        if source.scene_definition is None or source.source_closure_digest is None:
            raise ValueError('dynamic render source requires a canonical source closure')
        from ...runtime.sessions.source import (position_frame_bindings_from_artifact,
                                                 position_joint_bindings_from_artifact)
        if artifact.identity_hash != source.task_artifact_hash:
            raise ValueError('render source TaskArtifact identity mismatch')
        if (dict(frame_bindings) != position_frame_bindings_from_artifact(artifact, source)
                or dict(joint_bindings) != position_joint_bindings_from_artifact(source.scene_definition, artifact, source)):
            raise ValueError('render mappings differ from Artifact/source bindings')
        if set(joint_bindings) != set(source.joints) | set(source.free_joints):
            raise ValueError('render Joint definitions must exactly cover source')
        if set(frame_bindings) != set(source.bodies) | set(source.frames):
            raise ValueError('render Frame definitions must exactly cover source')
        scene_joints = {(j.parent_frame.entity_id, j.joint_id): j
                        for a in source.scene_definition.articulations or () for j in a.joints}
        scene_frames = {(f.entity_id, f.frame_id) for f in source.scene_definition.frames or ()}
        if (len({(v.parent_frame.entity_id, v.joint_id) for v in joint_bindings.values()}) != len(joint_bindings)
                or len({(v.entity_id, v.frame_id) for v in frame_bindings.values()}) != len(frame_bindings)):
            raise ValueError('source Joint/Frame mappings must be one-to-one')
        for definition in joint_bindings.values():
            if scene_joints.get((definition.parent_frame.entity_id, definition.joint_id)) != definition:
                raise ValueError('Joint binding differs from its Scene definition')
        if not {(v.entity_id, v.frame_id) for v in frame_bindings.values()} <= scene_frames:
            raise ValueError('Frame binding differs from its Scene definition')
        joints = tuple(DynamicRenderJointBindingV1(
            joint_bindings[k].parent_frame.entity_id, joint_bindings[k].joint_id, native)
            for k, native in sorted(source.joints.items()))
        frames = tuple(DynamicRenderFrameBindingV1(
            frame_bindings[k].entity_id, frame_bindings[k].frame_id, native)
            for k, native in sorted(source.bodies.items()))
        free = tuple((joint_bindings[k].parent_frame.entity_id, joint_bindings[k].joint_id,
                      native, joint_bindings[k].child_frame.entity_id,
                      joint_bindings[k].child_frame.frame_id)
                     for k, native in sorted(source.free_joints.items()))
        result = cls('camera-dynamic-source-v2', source.task_artifact_hash,
                     source.scene_definition.identity_hash, source.scene_source.source_id,
                     source.source_closure_digest, source.scene_source, source.scene_definition,
                     joints, frames, free,
                     tuple(sorted((v.entity_id, v.frame_id) for v in frame_bindings.values())),
                     source, artifact)
        result.validate()
        return result

    def validate(self):
        if self.schema_version != 'camera-dynamic-source-v2':
            raise ValueError('unsupported dynamic render source schema')
        DynamicCameraRenderSourceV1.validate(replace(self, schema_version='camera-dynamic-source-v1'))
        keys = [(v[0], v[1]) for v in self.free_bindings]
        body_keys = {(v.entity_id, v.frame_id) for v in self.frame_bindings}
        if (len(keys) != len(set(keys)) or len({v[2] for v in self.free_bindings}) != len(keys)
                or set(keys) & {(v.entity_id, v.joint_id) for v in self.joint_bindings}
                or len(self.published_frame_keys) != len(set(self.published_frame_keys))
                or not body_keys <= set(self.published_frame_keys)):
            raise ValueError('dynamic free Joint/Frame bindings must be unique and complete')
        definitions = {(j.parent_frame.entity_id, j.joint_id): j
                       for a in self.scene_definition.articulations or () for j in a.joints}
        for entity, joint, native, frame_entity, frame_id in self.free_bindings:
            for value in (entity, joint, native, frame_entity, frame_id): _name(value)
            definition = definitions.get((entity, joint))
            if (definition is None or definition.kind != 'floating'
                    or (definition.child_frame.entity_id, definition.child_frame.frame_id) != (frame_entity, frame_id)
                    or (frame_entity, frame_id) not in body_keys):
                raise ValueError('free Joint must resolve to its declared body Frame')
        scene_frames = {(f.entity_id, f.frame_id) for f in self.scene_definition.frames or ()}
        if not set(self.published_frame_keys) <= scene_frames:
            raise ValueError('published Frame binding is not in the Scene')

    def validate_binding_provenance(self):
        """Require exact Artifact-derived names before any native renderer build."""
        from ...artifacts import TaskArtifactV1
        from ...runtime.sessions.source import (RuntimeSource, position_frame_bindings_from_artifact,
                                                 position_joint_bindings_from_artifact)
        source, artifact = self.runtime_source, self.artifact
        if not isinstance(source, RuntimeSource) or not isinstance(artifact, TaskArtifactV1):
            raise TypeError('v2 native binding requires its RuntimeSource and TaskArtifactV1')
        if (artifact.identity_hash != self.task_artifact_hash
                or source.task_artifact_hash != self.task_artifact_hash
                or source.scene_definition != self.scene_definition
                or source.scene_source != self.scene_source
                or source.source_closure_digest != self.source_closure_digest):
            raise ValueError('v2 source provenance differs from its materialized inputs')
        frames = position_frame_bindings_from_artifact(artifact, source)
        joints = position_joint_bindings_from_artifact(self.scene_definition, artifact, source)
        expected_joints = tuple(DynamicRenderJointBindingV1(joints[k].parent_frame.entity_id,
                                joints[k].joint_id, native) for k,native in sorted(source.joints.items()))
        expected_frames = tuple(DynamicRenderFrameBindingV1(frames[k].entity_id, frames[k].frame_id, native)
                                for k,native in sorted(source.bodies.items()))
        expected_free = tuple((joints[k].parent_frame.entity_id, joints[k].joint_id, native,
                               joints[k].child_frame.entity_id, joints[k].child_frame.frame_id)
                              for k,native in sorted(source.free_joints.items()))
        expected_published = tuple(sorted((v.entity_id,v.frame_id) for v in frames.values()))
        if (self.joint_bindings != expected_joints or self.frame_bindings != expected_frames
                or self.free_bindings != expected_free or self.published_frame_keys != expected_published):
            raise ValueError('v2 mapping differs from Artifact/source provenance')

    @property
    def identity_hash(self):
        self.validate()
        payload = {'schema_version': self.schema_version,
                   'task_artifact_hash': self.task_artifact_hash, 'scene_identity_hash': self.scene_identity_hash,
                   'source_identity': self.source_identity, 'source_closure_digest': self.source_closure_digest,
                   'joint_bindings': tuple(v.to_mapping() for v in self.joint_bindings),
                   'frame_bindings': tuple(v.to_mapping() for v in self.frame_bindings),
                   'free_bindings': self.free_bindings,
                   'published_frame_keys': self.published_frame_keys}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RenderStateProjectionV1:
    """One read-only canonical state projection consumed by a renderer."""

    source_identity_hash: str
    geometry_version: str
    publication_version: str
    transform_version: str
    state_boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    joint_positions: tuple[tuple[str, str, str, float], ...]
    frame_poses: tuple[tuple[str, str, str, tuple[float, ...], tuple[float, ...]], ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            'source_identity_hash': self.source_identity_hash,
            'geometry_version': self.geometry_version,
            'publication_version': self.publication_version,
            'transform_version': self.transform_version,
            'state_boundary': self.state_boundary.to_mapping(),
            'sample_clock': self.sample_clock.to_mapping(),
            'joint_positions': self.joint_positions,
            'frame_poses': self.frame_poses,
        }


@dataclass(frozen=True)
class RenderStateProjectionV2(RenderStateProjectionV1):
    """V2 includes free-body world poses in frame_poses."""
    def to_mapping(self):
        return {'schema_version': 'render-state-projection-v2', **super().to_mapping()}


@dataclass(frozen=True)
class RenderStateSyncReceiptV1:
    """Versions and public-state boundary consumed by one renderer instance."""

    schema_version: str
    consumer_id: str
    source_identity_hash: str
    geometry_version: str
    publication_version: str
    transform_version: str
    state_boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    publication_updated: bool
    transforms_updated: bool
    static_geometry_build_count: int
    max_frame_position_error_m: float
    max_frame_quaternion_sign_invariant_l2_error: float
    visual_instance_bindings: tuple[RenderVisualInstanceBindingV1, ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            'schema_version': self.schema_version,
            'consumer_id': self.consumer_id,
            'source_identity_hash': self.source_identity_hash,
            'geometry_version': self.geometry_version,
            'publication_version': self.publication_version,
            'transform_version': self.transform_version,
            'state_boundary': self.state_boundary.to_mapping(),
            'sample_clock': self.sample_clock.to_mapping(),
            'publication_updated': self.publication_updated,
            'transforms_updated': self.transforms_updated,
            'static_geometry_build_count': self.static_geometry_build_count,
            'max_frame_position_error_m': self.max_frame_position_error_m,
            'max_frame_quaternion_sign_invariant_l2_error': self.max_frame_quaternion_sign_invariant_l2_error,
            'visual_instance_bindings': tuple(item.to_mapping() for item in self.visual_instance_bindings),
        }


@dataclass(frozen=True)
class RenderStateSyncReceiptV2(RenderStateSyncReceiptV1):
    """Owned renderer-only model with copied CPU state and synchronous update."""
    def to_mapping(self):
        return {**super().to_mapping(), 'resource_owner': 'renderer-only',
                'state_transfer': 'cpu-copy-synchronous-kinematics',
                'topology_generation': self.geometry_version,
                'limitations': ('rigid-only', 'no-physics-step', 'no-shared-state')}


def project_render_state_v1(source: DynamicCameraRenderSourceV1, state: CanonicalStateViewV1) -> RenderStateProjectionV1:
    """Bind Entity-qualified scalar state values to one dynamic render source."""

    source.validate()
    if not isinstance(state, CanonicalStateViewV1):
        raise TypeError('dynamic camera synchronization requires canonical-state-v1')
    if state.boundary.scene_identity_hash != source.scene_identity_hash:
        raise ValueError('dynamic camera state Scene identity differs from the source')
    if state.sample_clock.clock_domain != 'evaluation_boundary' or state.sample_clock.sample_index != state.boundary.control_step:
        raise ValueError('dynamic camera requires one evaluation-boundary state publication')

    state.validate()
    if isinstance(source, DynamicCameraRenderSourceV2):
        state.validate_against_scene(source.scene_definition)
    expected_joints = {(item.entity_id, item.joint_id): item for item in source.joint_bindings}
    free_keys = {(v[0], v[1]) for v in source.free_bindings} if isinstance(source, DynamicCameraRenderSourceV2) else set()
    observed_joints = {(item.entity_id, item.joint_id): item for item in state.joints}
    if set(observed_joints) != set(expected_joints) | free_keys:
        raise ValueError('dynamic camera state Joint identities do not exactly match the render source')
    joint_positions = []
    for key in sorted(expected_joints):
        binding = expected_joints[key]
        value = observed_joints[key]
        if value.kind not in {'revolute', 'continuous', 'prismatic'} or len(value.position) != 1:
            raise ValueError(f'D03 scalar render projection does not support Joint {key!r}')
        number = float(value.position[0])
        if not np.isfinite(number):
            raise ValueError(f'dynamic camera state contains a non-finite Joint position for {key!r}')
        joint_positions.append((binding.entity_id, binding.joint_id, binding.native_joint_name, number))

    expected_frames = {(item.entity_id, item.frame_id): item for item in source.frame_bindings}
    observed_frames = {(item.frame.entity_id, item.frame.frame_id): item for item in state.frames}
    if set(observed_frames) != (set(source.published_frame_keys) if isinstance(source, DynamicCameraRenderSourceV2) else set(expected_frames)):
        raise ValueError('dynamic camera state Frame identities do not exactly match the render source')
    frame_poses = []
    for key in sorted(expected_frames):
        binding = expected_frames[key]
        pose = observed_frames[key].pose_world
        position = tuple(float(value) for value in pose.position)
        quaternion = tuple(float(value) for value in pose.quaternion_wxyz)
        if not np.isfinite((*position, *quaternion)).all():
            raise ValueError(f'dynamic camera state contains a non-finite Frame pose for {key!r}')
        frame_poses.append((binding.entity_id, binding.frame_id, binding.native_body_name, position, quaternion))

    if isinstance(source, DynamicCameraRenderSourceV2):
        for entity, joint, _native, frame_entity, frame_id in source.free_bindings:
            value = observed_joints[(entity, joint)]
            pose = observed_frames[(frame_entity, frame_id)].pose_world
            if value.kind != 'floating' or len(value.position) != 7:
                raise ValueError('free Joint state must have floating 7-position')
            q = np.asarray(value.position[3:], dtype=np.float64)
            frame_q = np.asarray(pose.quaternion_wxyz, dtype=np.float64)
            if (not np.isfinite(value.position).all() or abs(float(np.linalg.norm(frame_q)) - 1.) > 1e-6
                    or np.linalg.norm(np.asarray(value.position[:3]) - pose.position) > 1e-8
                    or min(np.linalg.norm(q-frame_q), np.linalg.norm(q+frame_q)) > 1e-8):
                raise ValueError('free Joint and body-origin world Frame pose disagree')
    payload = {'joint_positions': tuple(joint_positions), 'frame_poses': tuple(frame_poses)}
    transform_version = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    projection_type = RenderStateProjectionV2 if isinstance(source, DynamicCameraRenderSourceV2) else RenderStateProjectionV1
    return projection_type(
        source.identity_hash, source.geometry_version, state.boundary.boundary_id,
        transform_version, state.boundary, state.sample_clock,
        tuple(joint_positions), tuple(frame_poses),
    )


@dataclass(frozen=True)
class CameraCaptureIdentityV1(Contract):
    """Static capture-request identity; only a later runtime receipt proves fulfillment."""

    schema_version: str
    task_artifact_hash: str
    camera_id: str
    camera_geometry_identity_hash: str
    render_source_identity_hash: str
    execution_spec_identity_hash: str
    renderer_selection: RendererSelectionV1
    provider_manifest_identity_hash: str
    state_boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    modalities: tuple[str, ...]
    capture_phase: str

    def validate(self):
        _choice(self.schema_version, {'camera-capture-identity-v1'}, 'camera capture identity schema')
        for digest in (
            self.task_artifact_hash,
            self.camera_geometry_identity_hash,
            self.render_source_identity_hash,
            self.execution_spec_identity_hash,
            self.provider_manifest_identity_hash,
        ):
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('camera capture identity requires lowercase SHA-256 references')
        _name(self.camera_id)
        _choice(self.capture_phase, {'reset_initial', 'post_control_step'}, 'capture phase')
        if self.capture_phase == 'reset_initial' and self.state_boundary.control_step != 0:
            raise ValueError('reset-initial capture requires control step zero')
        if self.sample_clock.clock_domain != 'evaluation_boundary':
            raise ValueError('camera capture identity requires an evaluation boundary clock')
        if self.sample_clock.sample_index != self.state_boundary.control_step:
            raise ValueError('camera capture clock and state boundary index disagree')
        if not self.modalities or len(self.modalities) != len(set(self.modalities)):
            raise ValueError('camera capture modalities must be nonempty and unique')
        for modality in self.modalities:
            _choice(modality, {'rgb', 'depth', 'entity_instance_segmentation'}, 'camera output modality')
        object.__setattr__(self, 'modalities', tuple(sorted(self.modalities)))

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode()).hexdigest()
