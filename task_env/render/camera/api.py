"""Render-specific admission before native construction; physics admission unchanged."""
from typing import Protocol
from ...artifacts import (
    CapabilityAdmissionError, CapabilityClaim, ExecutionSpec, ExecutionSpecV1,
    ProviderCapabilityManifest,
)
from ...runtime.sessions.provenance import provider_build_identity
from ...observations.canonical_camera import resolve_camera, CanonicalCameraObservation
from ...observations.canonical_camera.geometry import optical_depth
from ...observations.canonical_camera.images import normalize_rgb
from .source import DynamicCameraRenderSourceV1, DynamicCameraRenderSourceV2, project_render_state_v1

PROFILE = 'p1_4_native_camera_cpu_v0'
V211_DYNAMIC_PROFILE = 'v211_mujoco_cpu_render_binding_v1'
from ..base.contracts import task_rgb_capability

V211_RGB_PROFILE = task_rgb_capability('mujoco', 'cpu', 'mujoco').profile
V211_GEOPHYS_MUJOCO_RGB_PROFILE = task_rgb_capability('geophys', 'cpu', 'mujoco').profile
V211_PHYSICS_PROFILE = task_rgb_capability('mujoco', 'cpu', 'mujoco').physics_profile
D03_PHYSICS_PROFILE = task_rgb_capability('geophys', 'cpu', 'mujoco').physics_profile
D03_DYNAMIC_PROFILE = 'd03_mujoco_native_dynamic_opengl_v1'
D04_DYNAMIC_PROFILE = 'd04_mujoco_native_dynamic_opengl_rgbd_v1'
D04_ENTITY_SEGMENTATION_PROFILE = 'd04_mujoco_native_dynamic_opengl_entity_instance_segmentation_v1'


class CameraRenderSession(Protocol):
    def capture(self, state) -> CanonicalCameraObservation: ...
    def close(self) -> None: ...


def prepare_task_rgb_render_source(renderer, source, *, artifact, joint_bindings, frame_bindings):
    """Prepare only the visual model required by the selected task renderer.

    GeoPhys and Isaac lease their cameras from the existing RuntimeSession.
    A MuJoCo renderer instead needs its own source-bound visual model.
    """
    if renderer in {'geophys', 'isaacsim'}:
        return None
    if renderer != 'mujoco':
        raise CapabilityAdmissionError(f'unsupported task RGB renderer: {renderer}')
    result = DynamicCameraRenderSourceV2.from_runtime_source(
        source, artifact=artifact, joint_bindings=joint_bindings,
        frame_bindings=frame_bindings,
    )
    result.validate_binding_provenance()
    return result


def prepare_task_rgb_state_binding(renderer, source, *, artifact):
    """Declare and bind the renderer's source and evaluation-boundary state needs."""
    from ...artifacts import StateFieldRequirement, StateRequirements
    from ...runtime.sessions.source import (
        position_frame_bindings_from_artifact, position_joint_bindings_from_artifact,
    )

    scene = getattr(source, 'scene_definition', None)
    if scene is None or getattr(source, 'source_closure_digest', None) is None:
        raise ValueError('selected task RGB requires a canonical Scene and source closure')
    if getattr(source, 'task_artifact_hash', None) != artifact.identity_hash:
        raise ValueError('selected task RGB source differs from its Task Artifact')
    joints = position_joint_bindings_from_artifact(scene, artifact, source)
    frames = position_frame_bindings_from_artifact(artifact, source)
    visual = prepare_task_rgb_render_source(
        renderer, source, artifact=artifact, joint_bindings=joints, frame_bindings=frames,
    )
    fields = [StateFieldRequirement(
        'state-field-requirement-v1', field, 'joint', definition.parent_frame.entity_id,
        definition.joint_id, 'required', 'evaluation_boundary', 'joint-definition',
        'joint_state_query',
    ) for definition in joints.values() for field in ('joint_position', 'joint_velocity')]
    fields.extend(StateFieldRequirement(
        'state-field-requirement-v1', 'frame_pose_world', 'frame', reference.entity_id,
        reference.frame_id, 'required', 'evaluation_boundary', 'meter+quaternion_wxyz',
        'frame_pose_query',
    ) for reference in frames.values())
    requirements = StateRequirements(
        'state-requirements-v1', 'renderer', 'selected-task-rgb-v1', tuple(fields),
    )
    requirements.validate()
    return source, artifact.identity_hash, scene, joints, frames, requirements, visual


def render_manifest(provider):
    if provider not in ('geophys','mujoco'):
        raise CapabilityAdmissionError(f'unsupported render provider: {provider}')
    return ProviderCapabilityManifest('provider-capability-v0', provider,
        provider_build_identity(provider)['manifest_version'], 'p1_4-camera-v0', 'cpu',
        'native_pairing', PROFILE, 'strict',
        tuple(CapabilityClaim(c,'implemented','task_env/render/camera') for c in ('rgb_camera','depth_camera')),
        (), 'implementation_only_no_qualification')


def admit_render(camera, execution, manifest):
    if not isinstance(execution, ExecutionSpec):
        raise TypeError('current camera admission requires the legacy ExecutionSpec contract')
    if execution.render_provider not in ('geophys','mujoco'):
        raise CapabilityAdmissionError('unsupported render provider; no fallback')
    if (execution.render_provider != manifest.provider_name or execution.backend != manifest.backend
        or execution.physics_provider != execution.render_provider
        or manifest.render_profile != PROFILE or execution.determinism_mode != manifest.determinism_mode):
        raise CapabilityAdmissionError('unsupported render provider/pairing/profile/backend')
    claims = {c.name:c.status for c in manifest.capabilities}
    requested = tuple(c for c,enabled in (('rgb_camera',camera.rgb),('depth_camera',camera.depth)) if enabled)
    missing = [c for c in requested if claims.get(c) not in ('implemented','tested','qualified') or c in manifest.known_unsupported]
    if missing:
        raise CapabilityAdmissionError(f'missing render capability: {missing}')


def create_camera_session(camera, execution, *, source, manifest=None):
    if not isinstance(execution, ExecutionSpec):
        raise TypeError('current camera session requires the legacy ExecutionSpec contract')
    actual = render_manifest(execution.render_provider)
    if manifest is not None:
        admit_render(camera, execution, manifest)
    admit_render(camera, execution, actual)
    if camera.task_artifact_hash != source.task_artifact_hash:
        raise ValueError('camera/render source TaskArtifact linkage mismatch')
    return _construct_admitted(camera, execution, source)


def dynamic_render_manifest():
    """Manifest for the first bounded GeoPhys CPU → MuJoCo native GL intersection."""

    return ProviderCapabilityManifest(
        'provider-capability-v0', 'mujoco',
        provider_build_identity('mujoco')['manifest_version'],
        'd03-dynamic-camera-v1', 'native-opengl',
        'geophys-cpu-to-mujoco-native-opengl', D03_DYNAMIC_PROFILE, 'best_effort',
        (CapabilityClaim('rgb_camera', 'implemented', 'task_env/render/camera/dynamic-v1'),),
        (), 'implementation_only_no_qualification',
    )


def dynamic_rgbd_render_manifest():
    """Manifest for the first bounded RGB/optical-Z D04 intersection."""

    return ProviderCapabilityManifest(
        'provider-capability-v0', 'mujoco',
        provider_build_identity('mujoco')['manifest_version'],
        'd04-dynamic-camera-rgbd-v1', 'native-opengl',
        'geophys-cpu-to-mujoco-native-opengl', D04_DYNAMIC_PROFILE, 'best_effort',
        (
            CapabilityClaim('rgb_camera', 'implemented', 'task_env/render/camera/dynamic-v1'),
            CapabilityClaim('depth_camera', 'implemented', 'task_env/render/camera/dynamic-v1'),
        ), (), 'implementation_only_no_qualification',
    )


def dynamic_entity_instance_segmentation_manifest():
    """Manifest for the bounded D04 RGB/Depth/Entity-mask intersection."""

    return ProviderCapabilityManifest(
        'provider-capability-v0', 'mujoco',
        provider_build_identity('mujoco')['manifest_version'],
        'd04-dynamic-camera-entity-segmentation-v1', 'native-opengl',
        'geophys-cpu-to-mujoco-native-opengl', D04_ENTITY_SEGMENTATION_PROFILE,
        'best_effort',
        (
            CapabilityClaim('rgb_camera', 'implemented', 'task_env/render/camera/dynamic-v1'),
            CapabilityClaim('depth_camera', 'implemented', 'task_env/render/camera/dynamic-v1'),
            CapabilityClaim('entity_instance_segmentation', 'implemented', 'task_env/render/camera/dynamic-v1'),
        ), (), 'implementation_only_no_qualification',
    )


def v211_dynamic_render_manifest():
    return ProviderCapabilityManifest(
        'provider-capability-v0', 'mujoco', provider_build_identity('mujoco')['manifest_version'],
        'v211-render-binding-v1', 'native-opengl', 'mujoco-cpu-to-mujoco-native-opengl',
        V211_DYNAMIC_PROFILE, 'best_effort',
        (CapabilityClaim('rgb_camera', 'unknown', 'v211-binding-only-no-capture-admission'),),
        (), 'implementation_only_no_qualification')


def v211_rgb_render_manifest():
    """Separate RGB admission; the earlier binding-only profile stays unchanged."""
    return ProviderCapabilityManifest(
        'provider-capability-v0', 'mujoco', provider_build_identity('mujoco')['manifest_version'],
        'v211-native-rgb-v1', 'native-opengl', 'mujoco-cpu-to-mujoco-native-opengl',
        V211_RGB_PROFILE, 'best_effort',
        (CapabilityClaim('rgb_camera', 'implemented', 'task_env/render/camera/dynamic-v2'),),
        (), 'implementation_only_no_qualification')


def v211_geophys_mujoco_rgb_render_manifest():
    """Declare the V2 named-state cross route separately from D03/D04."""
    return ProviderCapabilityManifest(
        'provider-capability-v0', 'mujoco', provider_build_identity('mujoco')['manifest_version'],
        'v211-cross-rgb-v1', 'native-opengl', 'geophys-cpu-to-mujoco-native-opengl',
        V211_GEOPHYS_MUJOCO_RGB_PROFILE, 'best_effort',
        (CapabilityClaim('rgb_camera', 'implemented', 'task_env/render/camera/dynamic-v2'),),
        (), 'implementation_only_no_qualification')


def _dynamic_manifest_for_profile(profile):
    if profile == V211_DYNAMIC_PROFILE:
        return v211_dynamic_render_manifest()
    if profile == V211_RGB_PROFILE:
        return v211_rgb_render_manifest()
    if profile == V211_GEOPHYS_MUJOCO_RGB_PROFILE:
        return v211_geophys_mujoco_rgb_render_manifest()
    if profile == D03_DYNAMIC_PROFILE:
        return dynamic_render_manifest()
    if profile == D04_DYNAMIC_PROFILE:
        return dynamic_rgbd_render_manifest()
    if profile == D04_ENTITY_SEGMENTATION_PROFILE:
        return dynamic_entity_instance_segmentation_manifest()
    raise CapabilityAdmissionError(f'unsupported dynamic camera profile: {profile!r}')


def admit_dynamic_camera(camera, execution, *, source, manifest=None) -> None:
    """Fail-closed admission for the bounded D03/D04 dynamic camera profiles."""

    if not isinstance(execution, ExecutionSpecV1):
        raise TypeError('dynamic camera admission requires execution-spec-v1')
    if not isinstance(source, DynamicCameraRenderSourceV1):
        raise TypeError('dynamic camera admission requires camera-dynamic-source-v1')
    camera.validate()
    source.validate()
    if isinstance(source, DynamicCameraRenderSourceV2):
        source.validate_binding_provenance()
    selected = execution.renderer_for_camera(camera.camera_id)
    actual = _dynamic_manifest_for_profile(selected.profile)
    legacy = (execution.physics_provider == 'geophys'
              and execution.physics_backend == 'cpu'
              and execution.physics_profile == D03_PHYSICS_PROFILE
              and selected.profile in {D03_DYNAMIC_PROFILE, D04_DYNAMIC_PROFILE, D04_ENTITY_SEGMENTATION_PROFILE}
              and type(source) is DynamicCameraRenderSourceV1)
    v211 = (execution.physics_provider == 'mujoco' and execution.physics_backend == 'cpu'
            and execution.physics_profile == V211_PHYSICS_PROFILE
            and selected.profile in {V211_DYNAMIC_PROFILE, V211_RGB_PROFILE}
            and type(source) is DynamicCameraRenderSourceV2)
    cross_v211 = (execution.physics_provider == 'geophys' and execution.physics_backend == 'cpu'
                  and execution.physics_profile == D03_PHYSICS_PROFILE
                  and selected.profile == V211_GEOPHYS_MUJOCO_RGB_PROFILE
                  and type(source) is DynamicCameraRenderSourceV2)
    if (not (legacy or v211 or cross_v211) or selected.provider != 'mujoco'
            or selected.backend != 'native-opengl' or selected.device is not None
            or execution.determinism_mode != 'best_effort'):
        raise CapabilityAdmissionError('dynamic camera admits only GeoPhys CPU D03/D04 or the bounded MuJoCo CPU v2 intersection')
    if camera.task_artifact_hash != source.task_artifact_hash:
        raise CapabilityAdmissionError('camera/render source TaskArtifact linkage mismatch')
    if selected.profile == D04_ENTITY_SEGMENTATION_PROFILE and not (camera.rgb and camera.depth):
        raise CapabilityAdmissionError(
            'D04 Entity segmentation profile requires RGB and Depth on the same CameraGeometry capture'
        )
    if manifest is not None and manifest.identity_hash != actual.identity_hash:
        raise CapabilityAdmissionError('dynamic camera manifest does not match the admitted profile route')
    claims = {claim.name: claim.status for claim in actual.capabilities}
    requested = tuple(name for name, enabled in (('rgb_camera', camera.rgb), ('depth_camera', camera.depth)) if enabled)
    if v211 and selected.profile == V211_DYNAMIC_PROFILE:
        # Geometry config supplies a render context only; no RGB request is admitted.
        if not camera.rgb or camera.depth:
            raise CapabilityAdmissionError('v211 visual binding requires RGB camera geometry without capture admission')
        requested = ()
    if selected.profile in {V211_RGB_PROFILE, V211_GEOPHYS_MUJOCO_RGB_PROFILE} and (not camera.rgb or camera.depth):
        raise CapabilityAdmissionError('v211 native RGB profile requires RGB without depth')
    if selected.profile == D04_ENTITY_SEGMENTATION_PROFILE:
        requested += ('entity_instance_segmentation',)
    missing = [name for name in requested if claims.get(name) != 'implemented' or name in actual.known_unsupported]
    if missing:
        if selected.profile == D03_DYNAMIC_PROFILE:
            raise CapabilityAdmissionError(f'missing D03 dynamic render capability: {missing}')
        raise CapabilityAdmissionError(f'missing D04 dynamic render capability: {missing}')

    if camera.parent_frame != 'world':
        matches = [
            item for item in source.frame_bindings
            if item.frame_id == camera.parent_frame
        ]
        if len(matches) != 1:
            raise CapabilityAdmissionError(
                'dynamic camera parent Frame must resolve to exactly one Entity-qualified source Frame'
            )


def create_dynamic_camera_session(
    camera,
    execution,
    *,
    source: DynamicCameraRenderSourceV1,
    initial_state,
    manifest=None,
    task_camera=None,
):
    """Create one independent visual consumer after source/state admission."""

    admit_dynamic_camera(camera, execution, source=source, manifest=manifest)
    initial_projection = project_render_state_v1(source, initial_state)
    selected = execution.renderer_for_camera(camera.camera_id)
    actual_manifest = _dynamic_manifest_for_profile(selected.profile)
    from .mujoco import MuJoCoDynamicCameraSession
    return MuJoCoDynamicCameraSession(
        camera, source, initial_projection, execution=execution, manifest=actual_manifest,
        entity_segmentation=(selected.profile == D04_ENTITY_SEGMENTATION_PROFILE),
        task_camera=task_camera,
    )


def _construct_admitted(camera, execution, source):
    if execution.render_provider == 'geophys':
        from .geophys import GeoPhysCameraSession
        return GeoPhysCameraSession(camera, source)
    from .mujoco import MuJoCoCameraSession
    return MuJoCoCameraSession(camera, source)


class CameraSessionValues:
    def _initialize(self, camera):
        self._geometry = camera
        self._closed = False

    def capture(self, state):
        if self._closed:
            raise RuntimeError('camera session is closed')
        self._before_capture(state)
        metadata = resolve_camera(self._geometry, state)
        rendered = self._render(metadata)
        if not isinstance(rendered, tuple) or len(rendered) not in (2, 3):
            raise RuntimeError('camera renderer returned an invalid modality bundle')
        native_rgb, native_depth = rendered[:2]
        native_segmentation = rendered[2] if len(rendered) == 3 else None
        capture_identity = self._capture_identity(state)
        segmentation = self._canonical_segmentation(native_segmentation, state, capture_identity)
        return CanonicalCameraObservation(
            normalize_rgb(native_rgb,self._geometry) if self._geometry.rgb else None,
            optical_depth(native_depth,metadata,native_convention=self.native_depth_convention) if self._geometry.depth else None,
            metadata, capture_identity, segmentation)

    def _before_capture(self, state):
        """Optional read-only source synchronization for dynamic camera consumers."""

        return None

    def _capture_identity(self, state):
        """Legacy renderers keep their existing metadata-only observation contract."""

        return None

    def _canonical_segmentation(self, native, state, capture_identity):
        if native is not None:
            raise RuntimeError('renderer returned Entity segmentation outside an admitted segmentation profile')
        return None
