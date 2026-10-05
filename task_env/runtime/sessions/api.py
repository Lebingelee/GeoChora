"""Admission precedes every native materialization. No task-ID dispatch."""
from importlib.metadata import version
from typing import Protocol

from ...artifacts import (
    CanonicalStateView, CapabilityClaim, ExecutionSpec, ProviderCapabilityManifest,
    TaskArtifact, admit_capabilities,
)
from ...artifacts.execution import RealizedInitialState, ResetSample
from .source import RuntimeSource

CAPABILITIES = ('rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation',
                'joint_state_query', 'body_pose_query', 'frame_pose_query')
PROFILE = 'p1_2_scalar_cpu_v0'


class RuntimeSession(Protocol):
    def reset(self, sample: ResetSample) -> RealizedInitialState: ...
    def snapshot(self) -> CanonicalStateView: ...
    def step(self) -> CanonicalStateView: ...
    def close(self) -> None: ...


def provider_manifest(provider: str) -> ProviderCapabilityManifest:
    if provider not in ('geophys', 'mujoco'):
        raise ValueError('provider not implemented in P1.2')
    return ProviderCapabilityManifest(
        schema_version='provider-capability-v0', provider_name=provider,
        provider_version=(version('mujoco') if provider == 'mujoco' else 'c665ce5028a12bb4d2afe49f05e015fa9b684a39'),
        adapter_version='p1_2-v0', backend='cpu', physics_profile=PROFILE, render_profile='none',
        determinism_mode='strict',
        capabilities=tuple(CapabilityClaim(c, 'implemented', 'task_env/runtime/sessions') for c in CAPABILITIES),
        known_unsupported=('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
        evidence_reference='implementation_only_no_qualification',
    )


def materialize(artifact: TaskArtifact, execution: ExecutionSpec, *, source: RuntimeSource,
                manifest: ProviderCapabilityManifest | None = None) -> RuntimeSession:
    actual = provider_manifest(execution.physics_provider)
    # A caller may restrict a manifest for negative admission, never expand support.
    if manifest is not None:
        admit_capabilities(artifact.required_capabilities, manifest, execution)
    admit_capabilities(artifact.required_capabilities, actual, execution)
    if execution.render_provider != 'none':
        raise ValueError('P1.2 rendering is unsupported')
    if (source.config.runtime.physics_dt != artifact.timebase.physics_dt
        or source.config.runtime.control_substeps != artifact.timebase.control_substeps
        or source.config.runtime.backend != execution.backend
        or source.config.render.camera_obs):
        raise ValueError('source execution/timebase mismatch')
    if source.task_artifact_hash != artifact.identity_hash:
        raise ValueError('source/Artifact mismatch')
    if set(source.joints) != set(artifact.initialization.joint_position):
        raise ValueError('source joint bindings do not cover initialization')
    if not set(artifact.semantics.required_poses) <= set(source.bodies) | set(source.frames):
        raise ValueError('source pose bindings do not cover semantics')
    return _materialize_admitted(artifact, execution, source)


def _materialize_admitted(artifact, execution, source):
    if execution.physics_provider == 'geophys':
        from .geophys import _GeoPhysSession
        return _GeoPhysSession(artifact, source)
    from .mujoco import _MuJoCoSession
    return _MuJoCoSession(artifact, source)
