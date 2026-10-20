"""Bounded provider-neutral static triangle source; dynamic cameras are separate."""
from __future__ import annotations

from dataclasses import dataclass
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
        _choice(self.capture_phase, {'post_control_step'}, 'capture phase')
        if self.sample_clock.clock_domain != 'evaluation_boundary':
            raise ValueError('camera capture identity requires an evaluation boundary clock')
        if self.sample_clock.sample_index != self.state_boundary.control_step:
            raise ValueError('camera capture clock and state boundary index disagree')
        if not self.modalities or len(self.modalities) != len(set(self.modalities)):
            raise ValueError('camera capture modalities must be nonempty and unique')
        for modality in self.modalities:
            _choice(modality, {'rgb', 'depth'}, 'camera output modality')
        object.__setattr__(self, 'modalities', tuple(sorted(self.modalities)))

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode()).hexdigest()
