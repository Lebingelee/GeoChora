"""Admission precedes every native materialization. No task-ID dispatch."""
from collections.abc import Mapping
from typing import Protocol

from .provenance import provider_build_identity

from ...artifacts import (
    CanonicalStatePublicationV1, CanonicalStatePublicationV2,
    CanonicalStateView, CapabilityClaim, ExecutionSpec,
    FrameReference, JointDefinition, ProviderCapabilityManifest, SceneDefinition,
    StateRequirements, TaskArtifact, TaskArtifactV1, admit_capabilities,
)
from ...artifacts.execution import EpisodeResetPlanV1, RealizedInitialState, ResetSample
from ...controllers.canonical.feedback import (
    CanonicalControlFeedback, NativeControlFeedbackSampleV1,
)
from .source import RuntimeSource

CAPABILITIES = ('rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation',
                'joint_state_query', 'body_pose_query', 'frame_pose_query')
PROFILE = 'p1_2_scalar_cpu_v0'
_DUAL_POSITION_MATERIALIZATION_AUTHORITY = object()
_GEOPHYS_C05C_CADENCE_DIAGNOSTIC_REVISION = 'a53a8cfed7c9d6464274b5c96fca601271dc4ee4'
_GEOPHYS_C05C_CADENCE_DIAGNOSTIC_PROFILE = 'nutassembly-gripper-cadence-v1'


class RuntimeSession(Protocol):
    @property
    def provider_materialization_id(self) -> str: ...
    @property
    def episode_id(self) -> str: ...
    def reset(self, sample: ResetSample) -> RealizedInitialState: ...
    def reset_plan(self, plan: EpisodeResetPlanV1) -> RealizedInitialState: ...
    def snapshot(self) -> CanonicalStateView: ...
    def snapshot_v1(
        self,
        *,
        scene: SceneDefinition,
        joint_bindings: Mapping[str, JointDefinition],
        frame_bindings: Mapping[str, FrameReference],
        requirements: StateRequirements,
    ) -> CanonicalStatePublicationV1: ...
    def snapshot_v2(
        self,
        *,
        scene: SceneDefinition,
        joint_bindings: Mapping[str, JointDefinition],
        frame_bindings: Mapping[str, FrameReference],
        requirements: StateRequirements,
    ) -> CanonicalStatePublicationV2: ...
    def native_control_feedback_sample(
        self, state: CanonicalStateView, feedback: CanonicalControlFeedback,
    ) -> NativeControlFeedbackSampleV1: ...
    def step(self) -> CanonicalStateView: ...
    def close(self) -> None: ...


def provider_manifest(provider: str) -> ProviderCapabilityManifest:
    if provider not in ('geophys', 'mujoco', 'sapien', 'genesis'):
        raise ValueError(f'unknown physics provider: {provider}')
    return ProviderCapabilityManifest(
        schema_version='provider-capability-v0', provider_name=provider,
        provider_version=provider_build_identity(provider)['manifest_version'],
        adapter_version='p1_8-'+provider+'-v0' if provider in ('genesis','sapien') else 'p1_2-v0',
        backend='cpu', physics_profile=PROFILE, render_profile='none',
        determinism_mode='strict',
        capabilities=tuple(CapabilityClaim(c, 'implemented', 'task_env/runtime/sessions') for c in CAPABILITIES),
        known_unsupported=('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
        evidence_reference='implementation_only_no_qualification',
    )


def _diagnostic_manifest(artifact, execution, source, profile_id):
    """Return a process-local admission view for one non-capability diagnostic.

    This does not change ``provider_manifest`` or any production registry. It
    is deliberately tied to the frozen NutAssembly v0 source and the exact
    GeoPhys CUDA cadence experiment requested for C05c.
    """
    from dataclasses import replace

    if profile_id != _GEOPHYS_C05C_CADENCE_DIAGNOSTIC_PROFILE:
        raise ValueError('unknown RuntimeSession diagnostic admission profile')
    if not isinstance(artifact, TaskArtifact):
        raise ValueError('NutAssembly cadence diagnostic requires the frozen TaskArtifact v0')
    if (artifact.artifact_id != 'nut-assembly-square-v1/p1_8_e/nominal-v1'
            or artifact.task_id != 'nut-assembly-square-v1'
            or artifact.timebase.physics_dt != 0.002
            or artifact.timebase.control_dt != 0.01
            or artifact.timebase.control_substeps != 5
            or set(artifact.required_capabilities.names) != set(CAPABILITIES)):
        raise ValueError('diagnostic admission is limited to the frozen NutAssembly 100 Hz / 2 ms Artifact')
    if (execution.physics_provider != 'geophys' or execution.backend != 'cuda'
            or execution.physics_profile != PROFILE or execution.render_provider != 'none'
            or execution.determinism_mode != 'strict'):
        raise ValueError('diagnostic admission is limited to GeoPhys CUDA with the existing scalar profile')
    if (source.task_artifact_hash != artifact.identity_hash
            or source.scene_source.source_id !=
            'nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1'
            or source.config.runtime.backend != 'cuda'
            or source.config.runtime.physics_dt != 0.002
            or source.config.runtime.control_substeps != 5
            or source.config.render.camera_obs
            or len(source.joint_targets) != 7
            or tuple(source.open_actuators) != ('actuator8',)):
        raise ValueError('diagnostic admission source does not match the exact NutAssembly R3 execution source')
    build = provider_build_identity('geophys')
    if build['repository_revision'] != _GEOPHYS_C05C_CADENCE_DIAGNOSTIC_REVISION:
        raise ValueError('diagnostic admission requires the fixed GeoPhys a53a8cf repair baseline')
    cpu_manifest = provider_manifest('geophys')
    return replace(
        cpu_manifest,
        adapter_version='task-env-c05c-geophys-cuda-cadence-diagnostic-v1',
        backend='cuda',
        evidence_reference='diagnostic-only-no-capability-or-qualification',
    )


def materialize(artifact: TaskArtifact | TaskArtifactV1, execution: ExecutionSpec, *, source: RuntimeSource,
                manifest: ProviderCapabilityManifest | None = None,
                _materialization_authority=None, _diagnostic_profile=None) -> RuntimeSession:
    if not isinstance(artifact, (TaskArtifact, TaskArtifactV1)):
        raise TypeError('materialize requires TaskArtifact v0 or v1')
    if isinstance(artifact, TaskArtifactV1):
        artifact.validate()
    actual = (provider_manifest(execution.physics_provider) if _diagnostic_profile is None
              else _diagnostic_manifest(artifact, execution, source, _diagnostic_profile))
    # A caller may restrict a manifest for negative admission, never expand support.
    if manifest is not None:
        if _diagnostic_profile is not None:
            raise ValueError('diagnostic admission cannot be combined with a caller-supplied manifest')
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
    if isinstance(artifact, TaskArtifactV1):
        _validate_v1_materialization_source(
            artifact, execution, source,
            _allow_independent_robot_instances=(
                _materialization_authority is _DUAL_POSITION_MATERIALIZATION_AUTHORITY
            ),
        )
    elif source.scene_definition is not None and execution.physics_provider != 'geophys':
        raise ValueError('scene-definition-v3 v0 compatibility materialization is currently GeoPhys-only')
    if set(source.joints) != set(artifact.initialization.joint_position):
        raise ValueError('source joint bindings do not cover initialization')
    if not set(artifact.semantics.required_poses) <= set(source.bodies) | set(source.frames):
        raise ValueError('source pose bindings do not cover semantics')
    return _materialize_admitted(artifact, execution, source)


def _validate_v1_materialization_source(
    artifact: TaskArtifactV1,
    execution: ExecutionSpec,
    source: RuntimeSource,
    *,
    _allow_independent_robot_instances: bool = False,
) -> None:
    """Admit only the current single-Robot, scalar-joint Scene-v3 runtime slice."""
    if execution.physics_provider not in {'geophys', 'mujoco'}:
        raise ValueError('TaskArtifact v1 D01b materialization supports GeoPhys and MuJoCo only')
    scene = source.scene_definition
    if scene is None:
        raise ValueError('TaskArtifact v1 materialization requires its canonical SceneDefinition')
    if source.scene_source.base_dir is None:
        raise ValueError('TaskArtifact v1 materialization requires a bounded source base_dir')
    if scene.schema_version != 'scene-definition-v3':
        raise ValueError('TaskArtifact v1 materialization currently requires scene-definition-v3')
    artifact.validate_scene(scene)
    expected_source_id = f'{scene.schema_version}:{scene.identity_hash}'
    if source.scene_source.source_id != expected_source_id:
        raise ValueError('RuntimeSource ID must bind the exact TaskArtifact v1 Scene')
    robot_count = len(scene.robots or ())
    if robot_count != 1:
        independent_roots = tuple(
            root
            for robot in (scene.robots or ())
            for root in robot.articulation_roots
        )
        if (not _allow_independent_robot_instances or robot_count != 2
                or len(independent_roots) != 2
                or len({root.entity_id for root in independent_roots}) != 2):
            raise ValueError('D01b v1 materialization currently requires exactly one RobotInstance')
        roots_by_entity = {
            robot.entity_id: robot.articulation_roots for robot in (scene.robots or ())
        }
        if any(len(roots) != 1 for roots in roots_by_entity.values()):
            raise ValueError('bounded dual Position materialization requires two independent single-root Entities')
    if artifact.initialization.poses_world:
        raise ValueError('D01b v1 materialization does not yet admit free-body pose reset fields')
    if not set(artifact.semantics.required_joints) <= set(source.joints):
        raise ValueError('RuntimeSource does not bind every required TaskArtifact v1 Joint')

    for legacy_name in set(artifact.initialization.joint_position) | set(artifact.semantics.required_joints):
        reference = artifact.legacy_joint_bindings[legacy_name]
        if source.joints.get(legacy_name) != reference.joint_id:
            raise ValueError(
                f'RuntimeSource Joint {legacy_name!r} does not target its canonical Scene Joint'
            )

    required_frames = set(artifact.semantics.required_poses) | set(artifact.initialization.poses_world)
    for legacy_name in required_frames:
        reference = artifact.legacy_frame_bindings[legacy_name]
        native_targets = [
            mapping[legacy_name]
            for mapping in (source.bodies, source.frames)
            if legacy_name in mapping
        ]
        if native_targets != [reference.frame_id]:
            raise ValueError(
                f'RuntimeSource Frame {legacy_name!r} does not uniquely target its canonical Scene Frame'
            )


def _materialize_admitted(artifact, execution, source):
    if execution.physics_provider == 'geophys':
        from .geophys import _GeoPhysSession
        return _GeoPhysSession(artifact, source)
    if execution.physics_provider == 'mujoco':
        from .mujoco import _MuJoCoSession
        return _MuJoCoSession(artifact, source)
    if execution.physics_provider == 'sapien':
        from .sapien import _SapienSession
        return _SapienSession(artifact, source)
    if execution.physics_provider == 'genesis':
        from .genesis import _GenesisSession
        return _GenesisSession(artifact, source)
    raise ValueError(f'unknown physics provider: {execution.physics_provider}')
