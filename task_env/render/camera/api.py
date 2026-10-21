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
from .source import DynamicCameraRenderSourceV1, project_render_state_v1

PROFILE = 'p1_4_native_camera_cpu_v0'
D03_PHYSICS_PROFILE = 'geophys-scene-v3-runtime-v1'
D03_DYNAMIC_PROFILE = 'd03_mujoco_native_dynamic_opengl_v1'


class CameraRenderSession(Protocol):
    def capture(self, state) -> CanonicalCameraObservation: ...
    def close(self) -> None: ...


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


def admit_dynamic_camera(camera, execution, *, source, manifest=None) -> None:
    """Fail-closed admission for the D03 scalar Scene-v3 render intersection."""

    if not isinstance(execution, ExecutionSpecV1):
        raise TypeError('dynamic camera admission requires execution-spec-v1')
    if not isinstance(source, DynamicCameraRenderSourceV1):
        raise TypeError('dynamic camera admission requires camera-dynamic-source-v1')
    camera.validate()
    source.validate()
    selected = execution.renderer_for_camera(camera.camera_id)
    if (
        execution.physics_provider != 'geophys'
        or execution.physics_backend != 'cpu'
        or execution.physics_profile != D03_PHYSICS_PROFILE
        or selected.provider != 'mujoco'
        or selected.backend != 'native-opengl'
        or selected.profile != D03_DYNAMIC_PROFILE
        or selected.device is not None
        or execution.determinism_mode != 'best_effort'
    ):
        raise CapabilityAdmissionError(
            'D03 dynamic camera admits only GeoPhys CPU physics with the MuJoCo native OpenGL render route'
        )
    if camera.task_artifact_hash != source.task_artifact_hash:
        raise CapabilityAdmissionError('camera/render source TaskArtifact linkage mismatch')
    if manifest is not None and manifest.identity_hash != dynamic_render_manifest().identity_hash:
        raise CapabilityAdmissionError('dynamic camera manifest does not match the admitted D03 route')
    actual = dynamic_render_manifest()
    claims = {claim.name: claim.status for claim in actual.capabilities}
    requested = tuple(name for name, enabled in (('rgb_camera', camera.rgb), ('depth_camera', camera.depth)) if enabled)
    missing = [name for name in requested if claims.get(name) != 'implemented' or name in actual.known_unsupported]
    if missing:
        raise CapabilityAdmissionError(f'missing D03 dynamic render capability: {missing}')


def create_dynamic_camera_session(
    camera,
    execution,
    *,
    source: DynamicCameraRenderSourceV1,
    initial_state,
    manifest=None,
):
    """Create one independent visual consumer after source/state admission."""

    admit_dynamic_camera(camera, execution, source=source, manifest=manifest)
    initial_projection = project_render_state_v1(source, initial_state)
    from .mujoco import MuJoCoDynamicCameraSession
    return MuJoCoDynamicCameraSession(camera, source, initial_projection)


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
        native_rgb, native_depth = self._render(metadata)
        return CanonicalCameraObservation(
            normalize_rgb(native_rgb,self._geometry) if self._geometry.rgb else None,
            optical_depth(native_depth,metadata,native_convention=self.native_depth_convention) if self._geometry.depth else None,
            metadata)

    def _before_capture(self, state):
        """Optional read-only source synchronization for dynamic camera consumers."""

        return None
