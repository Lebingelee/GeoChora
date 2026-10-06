"""Render-specific admission before native construction; physics admission unchanged."""
from typing import Protocol
from ...artifacts import CapabilityAdmissionError, CapabilityClaim, ProviderCapabilityManifest
from ...runtime.sessions.provenance import provider_build_identity
from ...observations.canonical_camera import resolve_camera, CanonicalCameraObservation
from ...observations.canonical_camera.geometry import optical_depth
from ...observations.canonical_camera.images import normalize_rgb

PROFILE = 'p1_4_native_camera_cpu_v0'


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
    actual = render_manifest(execution.render_provider)
    if manifest is not None:
        admit_render(camera, execution, manifest)
    admit_render(camera, execution, actual)
    if camera.task_artifact_hash != source.task_artifact_hash:
        raise ValueError('camera/render source TaskArtifact linkage mismatch')
    return _construct_admitted(camera, execution, source)


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
        metadata = resolve_camera(self._geometry, state)
        native_rgb, native_depth = self._render(metadata)
        return CanonicalCameraObservation(
            normalize_rgb(native_rgb,self._geometry) if self._geometry.rgb else None,
            optical_depth(native_depth,metadata,native_convention=self.native_depth_convention) if self._geometry.depth else None,
            metadata)
