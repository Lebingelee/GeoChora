"""Admission precedes every native materialization. No task-ID dispatch."""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Protocol

from .provenance import provider_build_identity

from ...artifacts import (
    CanonicalStatePublicationV1, CanonicalStatePublicationV2,
    CanonicalStateView, CapabilityClaim, ExecutionSpec,
    ExecutionSpecV1,
    FrameReference, JointDefinition, ProviderCapabilityManifest, SceneDefinition,
    StateRequirements, TaskArtifact, TaskArtifactV1, admit_capabilities,
)
from ...artifacts.contracts import UsdAssetDeliveryLocalV1
from ...assembly.usd_delivery import variant_selection_hash
from ...artifacts.execution import (
    EpisodeResetPlanV1, RealizedInitialState, ResetSample, legacy_execution_projection,
)
from ...controllers.canonical.feedback import (
    CanonicalControlFeedback, NativeControlFeedbackSampleV1,
)
from .source import RuntimeSource, UsdRuntimeSourceV1

CAPABILITIES = ('rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation',
                'joint_state_query', 'body_pose_query', 'frame_pose_query')
PROFILE = 'p1_2_scalar_cpu_v0'
F04_ISAAC_POSITION_PROFILE = 'isaac-gpu-physx-f04-position-v1'
F05_GEOPHYS_NATIVE_POSITION_PROFILE = 'geophys-usd-position-f05-native-v1'
F05_DG02_GEOPHYS_USD_PROFILE = 'geophys-usd-position-f05-dg02-core-v1'
F05_DG04_ISAAC_NATIVE_PROFILE = 'isaac-gpu-physx-f05-dg04-native-mimic-v1'
F06_PICKCUBE_ISAAC_PROFILE = 'isaac-gpu-physx-pickcube-f06-v1'
_F04_OFFICIAL_PANDA_SOURCE_REFERENCE = (
    'https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.2/Isaac/'
    'Robots_Multiphysics/FrankaRobotics/FrankaPanda/franka/franka.usda'
)
_F04_MENAGERIE_PANDA_SOURCE_REFERENCE = (
    'mujoco-menagerie://franka_emika_panda/panda.xml'
)
_F04_MENAGERIE_PANDA_REVISION = 'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7'
_F04_OFFICIAL_PANDA_LOCAL_REVISION = 's3-prefix-last-modified-2026-10-07T01:07:07Z-through-2026-10-07T01:07:09Z'
_F04_OFFICIAL_PANDA_SOURCE_CLOSURE_SHA256 = '7ba946a0b02623525dc6b92db9f1000f85fb2e9ea140a0ec6fabb6f818f6c072'
_F04_MENAGERIE_PANDA_SOURCE_CLOSURE_SHA256 = 'a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a'
_F04_LOCAL_CHECKER_SHA256 = '047fc1e436d846296ae3d051c56e9f17d7d0ed378653989b3bc28dc00e77ec23'
_F04_OFFICIAL_LOCAL_RECIPE_SHA256 = '158fb4ca7de5c49b0a430f46b08ff5953c5562baec507a04d91e9d55640c1558'
_F04_MENAGERIE_LOCAL_RECIPE_SHA256 = '3af9f3da9c8b186d8568eb8dc0e82ccba65e020c4d853cca50da8bbc8cd6dede'
_DUAL_POSITION_MATERIALIZATION_AUTHORITY = object()
_GEOPHYS_C05C_CADENCE_DIAGNOSTIC_REVISION = 'a53a8cfed7c9d6464274b5c96fca601271dc4ee4'
_GEOPHYS_C05C_CADENCE_DIAGNOSTIC_PROFILE = 'nutassembly-gripper-cadence-v1'
_F05_DG04_S1_NATIVE_IO_CONTEXT: ContextVar[object | None] = ContextVar(
    'task_env_f05_dg04_s1_native_io_context', default=None,
)


class _F05Dg04S1NativeIOContext:
    """Private S1 scope replacing only the exact DG04 native I/O port."""

    def __init__(self, input_v1, factory):
        from ...tasks.position_candidate.builder import F05Dg04IsaacNativeCandidateInputV1

        if type(input_v1) is not F05Dg04IsaacNativeCandidateInputV1:
            raise TypeError('DG04 S1 requires its exact versioned source-bound candidate input')
        input_v1.validate()
        if not callable(factory):
            raise TypeError('DG04 S1 factory must be callable')
        source = input_v1.runtime_source
        representation = source.scene_source.representation
        if (source.scene_source.source_verified or not source.scene_source.locally_validated
                or representation.runtime_admitted or representation.source_verified
                or representation.provider != 'isaacsim'
                or representation.provider_build_identity != 'isaacsim-6.2.0.0'):
            raise ValueError('DG04 S1 cannot promote local validation to runtime admission')
        self.input_v1, self.factory = input_v1, factory

    def validate_call(self, artifact, execution, source):
        declared = self.input_v1
        if (artifact is not declared.artifact or source is not declared.runtime_source
                or type(execution) is not ExecutionSpecV1
                or execution.identity_hash != declared.execution.identity_hash):
            raise ValueError('DG04 S1 factory differs from its exact candidate identities')
        declared.validate()


@contextmanager
def _f05_dg04_s1_native_io_context(input_v1, factory):
    scope = _F05Dg04S1NativeIOContext(input_v1, factory)
    token = _F05_DG04_S1_NATIVE_IO_CONTEXT.set(scope)
    try:
        yield scope
    finally:
        _F05_DG04_S1_NATIVE_IO_CONTEXT.reset(token)


def _current_f05_dg04_s1_native_io_context():
    return _F05_DG04_S1_NATIVE_IO_CONTEXT.get()


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


def _validate_f04_source_family(delivery) -> None:
    """Bind the two F04 source families to their exact stable source identities."""
    definition = delivery.asset_definition
    if definition.source_reference not in {
            _F04_OFFICIAL_PANDA_SOURCE_REFERENCE,
            _F04_MENAGERIE_PANDA_SOURCE_REFERENCE,
    }:
        raise ValueError('F04 production materialization is limited to the two frozen Panda source families')
    if (definition.source_reference == _F04_MENAGERIE_PANDA_SOURCE_REFERENCE
            and (definition.source_revision != _F04_MENAGERIE_PANDA_REVISION
                 or delivery.source_revision != _F04_MENAGERIE_PANDA_REVISION)):
        raise ValueError('F04 Menagerie Panda source must bind the current frozen provider Gitlink')
    if type(delivery) is UsdAssetDeliveryLocalV1:
        if delivery.provenance_kind != 'local-validated':
            raise ValueError('F04 local Panda route requires explicit local-validated provenance')
        selected_source_variants = dict(delivery.source_variant_selections)
        if definition.source_reference == _F04_OFFICIAL_PANDA_SOURCE_REFERENCE:
            expected_variants = {
                '/panda#Gripper': 'alternatefinger',
                '/panda#Mesh': 'performance',
                '/panda#Physics': 'physx',
            }
            if selected_source_variants != expected_variants:
                raise ValueError('F04 local official Panda report must bind the exact F01 source variants')
            if delivery.source_entry_sha256 != 'cbdbfc4481e0420aa30c2e57c39cce91006cb29b93bc2e06becaf4304c20ea30':
                raise ValueError('F04 local official Panda report binds an unexpected source entry byte')
            if (delivery.source_revision != _F04_OFFICIAL_PANDA_LOCAL_REVISION
                    or delivery.source_closure_sha256 != _F04_OFFICIAL_PANDA_SOURCE_CLOSURE_SHA256):
                raise ValueError('F04 local official Panda report differs from the frozen S3 prefix inventory')
        else:
            if selected_source_variants:
                raise ValueError('F04 local Menagerie report does not admit unreviewed source variants')
            if (delivery.source_entry_sha256 != '96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273'
                    or delivery.source_revision != _F04_MENAGERIE_PANDA_REVISION
                    or delivery.source_closure_sha256 != _F04_MENAGERIE_PANDA_SOURCE_CLOSURE_SHA256):
                raise ValueError('F04 local Menagerie report differs from the frozen Panda XML/gitlink')
        if delivery.source_variant_selection_sha256 != variant_selection_hash(selected_source_variants):
            raise ValueError('F04 local report source variant identity is inconsistent')
        if delivery.recipe_path != 'metadata/physx_task_scene_recipe.json':
            raise ValueError('F04 local delivery must use the frozen task-scene/PhysX recipe path')
        expected_recipe_sha = (
            _F04_OFFICIAL_LOCAL_RECIPE_SHA256
            if definition.source_reference == _F04_OFFICIAL_PANDA_SOURCE_REFERENCE
            else _F04_MENAGERIE_LOCAL_RECIPE_SHA256
        )
        if (delivery.recipe_sha256 != expected_recipe_sha
                or delivery.checker_sha256 != _F04_LOCAL_CHECKER_SHA256):
            raise ValueError('F04 local delivery differs from the exact reviewed source recipe/checker bytes')
        if delivery.entry_prim != '/panda' or delivery.variant_selections:
            raise ValueError('F04 local derived stage must be a flattened selected scene rooted at /panda')
    elif definition.source_reference == _F04_OFFICIAL_PANDA_SOURCE_REFERENCE:
        expected_variants = {
            '/panda#Gripper': 'alternatefinger',
            '/panda#Mesh': 'performance',
            '/panda#Physics': 'physx',
        }
        if dict(delivery.variant_selections) != expected_variants:
            raise ValueError('F04 official Panda source must bind the exact F01 gripper/mesh/physics variants')


def _validate_f04_isaac_position_source(artifact, execution, source) -> None:
    """Admit only the exact F04 Panda/source/runtime intersection."""
    if type(artifact) is not TaskArtifactV1 or type(execution) is not ExecutionSpecV1:
        raise TypeError('F04 Isaac materialization requires TaskArtifactV1 and ExecutionSpecV1')
    execution.validate()
    source.validate()
    delivery = source.scene_source.loaded_delivery
    definition = delivery.delivery.asset_definition
    if not (delivery.source_verified or source.scene_source.locally_validated):
        raise ValueError('synthetic or unverified USD source is not admitted for production materialization')
    if source.scene_source.locally_validated:
        if (not delivery.locally_validated or delivery.report.provenance_kind != 'local-validated'
                or delivery.report.recipe_id != 'f04-physx-task-scene-overlay-v2'
                or delivery.report.checker_id != 'geochora-f04-local-usd-checker-v2'
                or delivery.report.checker_sha256 != _F04_LOCAL_CHECKER_SHA256
                or delivery.report.recipe_sha256 != delivery.delivery.recipe_sha256
                or not delivery.report.passed):
            raise ValueError('F04 local source lacks the loader-verified local validation report')
    _validate_f04_source_family(delivery.delivery)
    if source.scene_source.representation.provider != 'isaacsim':
        raise ValueError('F04 adapter requires the exact Isaac Sim representation')
    if (source.scene_source.representation.provider_build_identity,
            source.scene_source.representation.representation_format,
            source.scene_source.representation.runtime_admitted) != (
            'isaacsim-6.2.0.0', 'usd', False):
        raise ValueError('F04 source representation must be USD prepared for Isaac Sim 6.2.0.0')
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.determinism_mode, execution.physics_profile) != (
            'isaacsim', 'cuda', 'cuda:0', 'best_effort', F04_ISAAC_POSITION_PROFILE):
        raise ValueError('unsupported Isaac provider/build/backend/device/profile intersection')
    if (execution.render_default.provider, execution.render_default.backend,
            execution.render_default.profile, execution.render_default.device,
            execution.camera_overrides) != ('none', 'cpu', 'none', None, ()):
        raise ValueError('F04 Isaac Position profile is state-only and does not admit task cameras')
    if (artifact.timebase.physics_dt, artifact.timebase.control_substeps,
            artifact.timebase.control_dt) != (0.002, 5, 0.01):
        raise ValueError('F04 Isaac Position profile requires 100 Hz / five 2 ms physics steps')
    if (source.task_artifact.identity_hash != artifact.identity_hash
            or source.scene_definition.identity_hash != artifact.scene_identity_hash):
        raise ValueError('F04 USD source does not bind the exact TaskArtifact and Scene')
    if not (set(artifact.required_capabilities.names) <= set(CAPABILITIES)):
        raise ValueError('F04 Isaac profile does not implement every TaskArtifact capability')


def _validate_f05_geophys_native_position_input(input_v1, artifact, execution, source) -> None:
    """Admit only the frozen local Menagerie/GeoPhys CPU Position cell."""
    from ...tasks.position_candidate.builder import F05NativePositionCandidateInputV1

    if type(input_v1) is not F05NativePositionCandidateInputV1:
        raise TypeError('F05 GeoPhys native materialization requires the exact versioned native input')
    input_v1.validate()
    if (artifact is not input_v1.artifact or source is not input_v1.runtime_source
            or execution.identity_hash != input_v1.execution.identity_hash):
        raise ValueError('F05 GeoPhys native materialization differs from its exact candidate identities')
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.physics_profile, execution.determinism_mode) != (
            'geophys', 'cpu', 'cpu', F05_GEOPHYS_NATIVE_POSITION_PROFILE, 'best_effort'):
        raise ValueError('unsupported GeoPhys USD native provider/backend/device/profile intersection')
    if (source.scene_source.representation.provider,
            source.scene_source.representation.representation_format,
            source.scene_source.representation.runtime_admitted,
            source.scene_source.locally_validated,
            source.scene_source.source_verified) != ('geophys', 'usd', False, True, False):
        raise ValueError('F05 native production admission requires the exact locally validated USD source')
    _validate_f04_source_family(source.scene_source.loaded_delivery.delivery)
    if source.scene_source.loaded_delivery.delivery.asset_definition.source_reference != _F04_MENAGERIE_PANDA_SOURCE_REFERENCE:
        raise ValueError('F05 native admission is limited to the frozen Menagerie Panda source')
    if source.scene_source.representation.provider_build_identity != input_v1.host_model_producer_identity.requested_target_build_identity:
        raise ValueError('F05 requested target build differs from the source Representation')
    if execution.render_default.provider != 'none' or execution.camera_overrides:
        raise ValueError('F05 native Position cell is state-only and cannot create a renderer')


def _validate_f05_dg02_geophys_usd_input(input_v1, artifact, execution, source) -> None:
    """Admit only the exact DG02 source-preserving USD/Core input contract."""
    from ...tasks.position_candidate.builder import F05Dg02GeoPhysUsdCandidateInputV1

    if type(input_v1) is not F05Dg02GeoPhysUsdCandidateInputV1:
        raise TypeError('DG02 GeoPhys/USD materialization requires the exact candidate input')
    input_v1.validate()
    if (artifact is not input_v1.artifact or source is not input_v1.runtime_source
            or type(execution) is not ExecutionSpecV1
            or execution.identity_hash != input_v1.execution.identity_hash):
        raise ValueError('DG02 materialization differs from its exact Task/Scene/Execution identities')
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.physics_profile, execution.determinism_mode) != (
            'geophys', 'cpu', 'cpu', F05_DG02_GEOPHYS_USD_PROFILE, 'best_effort'):
        raise ValueError('unsupported DG02 GeoPhys CPU/USD source intersection')
    if (source.scene_source.representation.provider,
            source.scene_source.representation.representation_format,
            source.scene_source.representation.runtime_admitted,
            source.scene_source.locally_validated,
            source.scene_source.source_verified) != ('geophys', 'usd', False, True, False):
        raise ValueError('DG02 production admission requires its exact locally validated source-preserving USD')
    if (source.scene_source.loaded_delivery.delivery.recipe_sha256
            != input_v1.runtime_source.scene_source.loaded_delivery.delivery.recipe_sha256):
        raise ValueError('DG02 delivery recipe identity changed after candidate validation')


def _validate_f05_dg04_isaac_native_input(input_v1, artifact, execution, source) -> None:
    """Admit only the exact source-bound DG04 native PhysX mimic profile."""
    from ...tasks.position_candidate.builder import F05Dg04IsaacNativeCandidateInputV1

    if type(input_v1) is not F05Dg04IsaacNativeCandidateInputV1:
        raise TypeError('DG04 Isaac native materialization requires its exact candidate input')
    input_v1.validate()
    if (artifact is not input_v1.artifact or source is not input_v1.runtime_source
            or type(execution) is not ExecutionSpecV1
            or execution.identity_hash != input_v1.execution.identity_hash):
        raise ValueError('DG04 materialization differs from its exact Task/Scene/Execution identities')
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.physics_profile, execution.determinism_mode) != (
            'isaacsim', 'cuda', 'cuda:0', F05_DG04_ISAAC_NATIVE_PROFILE, 'best_effort'):
        raise ValueError('unsupported DG04 Isaac CUDA/native-mimic execution intersection')
    representation = source.scene_source.representation
    if (representation.provider, representation.provider_build_identity,
            representation.representation_format, representation.runtime_admitted,
            representation.source_verified, source.scene_source.locally_validated,
            source.scene_source.source_verified) != (
            'isaacsim', 'isaacsim-6.2.0.0', 'usd', False, False, True, False):
        raise ValueError('DG04 production admission requires its exact locally validated non-upstream USD')
    if (source.scene_source.loaded_delivery.manifest_bytes_sha256
            != input_v1.runtime_source.scene_source.loaded_delivery.manifest_bytes_sha256
            or source.scene_source.loaded_delivery.delivery_sha256
            != input_v1.runtime_source.scene_source.loaded_delivery.delivery_sha256
            or dict(source.joints) != dict(source.joint_targets)):
        raise ValueError('DG04 delivery or exact nine-joint source identity changed after candidate validation')
    if execution.render_default.provider != 'none' or execution.camera_overrides:
        raise ValueError('DG04 Core cell is state-only and does not admit a renderer')


def _validate_f06_pickcube_isaac_input(input_v1, artifact, execution, source) -> None:
    """Admit the exact locally validated PickCube desktop USD F06 input."""
    from ...tasks.pick_cube.isaac import (
        ISAAC_PROFILE_V1, PickCubeIsaacRuntimeInputV1,
    )

    if type(input_v1) is not PickCubeIsaacRuntimeInputV1:
        raise TypeError('F06 Isaac materialization requires its exact PickCube RuntimeInputV1')
    input_v1.validate()
    if (artifact is not input_v1.artifact or source is not input_v1.runtime_source
            or type(execution) is not ExecutionSpecV1
            or execution.identity_hash != input_v1.execution.identity_hash):
        raise ValueError('F06 materialization differs from its exact Task/Scene/Execution identities')
    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.physics_profile, execution.determinism_mode) != (
            'isaacsim', 'cuda', 'cuda:0', ISAAC_PROFILE_V1, 'best_effort'):
        raise ValueError('unsupported F06 PickCube Isaac CUDA/PhysX execution intersection')
    representation = source.scene_source.representation
    if (representation.provider, representation.provider_build_identity,
            representation.representation_format, representation.runtime_admitted,
            representation.source_verified, source.scene_source.locally_validated,
            source.scene_source.source_verified) != (
            'isaacsim', 'isaacsim-6.2.0.0', 'usd', False, False, True, False):
        raise ValueError('F06 admission requires its exact locally validated non-upstream USD')
    if (source.scene_source.loaded_delivery.manifest_bytes_sha256
            != input_v1.delivery_manifest_sha256
            or dict(source.joints) != dict(source.joint_targets)):
        raise ValueError('F06 delivery or exact PickCube source Joint identity changed')
    if execution.render_default.provider != 'none' or execution.camera_overrides:
        raise ValueError('F06 Core cell is state-only and does not admit a renderer')


def _f05_dg04_isaac_capability_manifest(artifact, *, synthetic_s1=False):
    from ...artifacts import CapabilityClaim, ProviderCapabilityManifest

    names = sorted(set(artifact.required_capabilities.names) | {
        'articulated_robot', 'joint_position_actuation', 'joint_state_query',
        'body_pose_query', 'frame_pose_query',
    })
    status = 'tested' if synthetic_s1 else 'implemented'
    evidence = (
        'DG04-synthetic-S1-only-no-runtime-admission' if synthetic_s1
        else 'F05-DG04-versioned-native-PhysX-mimic-Core-cell'
    )
    return ProviderCapabilityManifest(
        'provider-capability-v0', 'isaacsim', '6.2.0.0',
        'f05-dg04-native-mimic-core-v1', 'cuda', F05_DG04_ISAAC_NATIVE_PROFILE,
        'none', 'best_effort',
        tuple(CapabilityClaim(name, status, evidence) for name in names),
        ('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
        'bounded F05 DG04 source-bound native mimic cell; no provider-wide qualification',
    )


def _f06_pickcube_isaac_capability_manifest(artifact):
    from ...artifacts import CapabilityClaim, ProviderCapabilityManifest
    from ...tasks.pick_cube.isaac import ISAAC_PROFILE_V1

    names = sorted(set(artifact.required_capabilities.names) | {
        'articulated_robot', 'joint_position_actuation', 'joint_state_query',
        'body_pose_query', 'frame_pose_query', 'free_body',
    })
    return ProviderCapabilityManifest(
        'provider-capability-v0', 'isaacsim', '6.2.0.0',
        'f06-pickcube-desktop-native-mimic-v1', 'cuda', ISAAC_PROFILE_V1,
        'none', 'best_effort',
        tuple(CapabilityClaim(name, 'implemented', 'F06-exact-PickCube-desktop-source-bound-cell')
              for name in names),
        ('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
        'bounded F06 PickCube Isaac desktop cell; no provider-wide qualification',
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


def _session_admission_input_route(input_v1) -> str | None:
    """Classify one exact task-owned input for a versioned Session route."""
    if input_v1 is None:
        return None
    from ...tasks.position_candidate.builder import (
        F05Dg02GeoPhysUsdCandidateInputV1,
        F05Dg04IsaacNativeCandidateInputV1,
        F05NativePositionCandidateInputV1,
    )
    routes = (
        (F05NativePositionCandidateInputV1, 'f05_native'),
        (F05Dg02GeoPhysUsdCandidateInputV1, 'f05_dg02'),
        (F05Dg04IsaacNativeCandidateInputV1, 'f05_dg04'),
    )
    for input_type, route in routes:
        if type(input_v1) is input_type:
            return route
    from ...tasks.pick_cube.isaac import PickCubeIsaacRuntimeInputV1

    if type(input_v1) is PickCubeIsaacRuntimeInputV1:
        return 'f06_pickcube'
    raise TypeError('Session admission requires one exact supported task runtime input')


def materialize(artifact: TaskArtifact | TaskArtifactV1, execution: ExecutionSpec | ExecutionSpecV1, *, source: RuntimeSource | UsdRuntimeSourceV1,
                manifest: ProviderCapabilityManifest | None = None,
                _materialization_authority=None, _diagnostic_profile=None,
                _session_admission_input=None) -> RuntimeSession:
    if not isinstance(artifact, (TaskArtifact, TaskArtifactV1)):
        raise TypeError('materialize requires TaskArtifact v0 or v1')
    if isinstance(artifact, TaskArtifactV1):
        artifact.validate()
    declared_execution = execution
    admission_route = _session_admission_input_route(_session_admission_input)
    _f05_native_input = _session_admission_input if admission_route == 'f05_native' else None
    _f05_dg02_geophys_input = _session_admission_input if admission_route == 'f05_dg02' else None
    _f05_dg04_isaac_native_input = _session_admission_input if admission_route == 'f05_dg04' else None
    _f06_pickcube_isaac_input = _session_admission_input if admission_route == 'f06_pickcube' else None
    if (_f06_pickcube_isaac_input is not None
            or (type(execution) is ExecutionSpecV1
                and execution.physics_profile == F06_PICKCUBE_ISAAC_PROFILE)):
        if _f06_pickcube_isaac_input is None:
            raise ValueError('F06 PickCube Isaac profile requires its exact versioned input')
        _validate_f06_pickcube_isaac_input(
            _f06_pickcube_isaac_input, artifact, declared_execution, source,
        )
        expected_manifest = _f06_pickcube_isaac_capability_manifest(artifact)
        if (manifest is None or manifest.identity_hash != expected_manifest.identity_hash
                or _materialization_authority is not None or _diagnostic_profile is not None):
            raise ValueError('F06 exact admission requires the Core-generated source-bound manifest only')
        projected_execution = ExecutionSpec(
            'isaacsim', F06_PICKCUBE_ISAAC_PROFILE, 'none', 'cuda',
            declared_execution.provider_seed, 'best_effort',
        )
        admit_capabilities(artifact.required_capabilities, manifest, projected_execution)
        from .isaac_native_io import create_isaac_native_runtime_io

        native_io = create_isaac_native_runtime_io(
            artifact, declared_execution, source,
            f06_pickcube_input=_f06_pickcube_isaac_input,
        )
        from .native_io import UsdCoreRuntimeSession
        try:
            session = UsdCoreRuntimeSession(
                artifact, declared_execution, source, native_io,
                getattr(native_io, 'drive_receipt', None),
            )
        except BaseException as materialization_error:
            try:
                native_io.close()
            except BaseException as cleanup_error:
                materialization_error.add_note(
                    'F06 Isaac native-I/O cleanup after Core admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            try:
                native_io.close_runtime_owner()
            except BaseException as cleanup_error:
                materialization_error.add_note(
                    'F06 Isaac App owner cleanup after Core admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            raise
        session._declared_execution_spec_v1 = declared_execution
        session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
        return session
    if (_f05_dg04_isaac_native_input is not None
            or (type(execution) is ExecutionSpecV1
                and execution.physics_profile == F05_DG04_ISAAC_NATIVE_PROFILE)):
        if _f05_dg04_isaac_native_input is None:
            raise ValueError('DG04 native PhysX profile requires its exact versioned candidate input')
        _validate_f05_dg04_isaac_native_input(
            _f05_dg04_isaac_native_input, artifact, declared_execution, source,
        )
        scope = _current_f05_dg04_s1_native_io_context()
        expected_manifest = _f05_dg04_isaac_capability_manifest(
            artifact, synthetic_s1=scope is not None,
        )
        if (manifest is None or manifest.identity_hash != expected_manifest.identity_hash
                or _materialization_authority is not None or _diagnostic_profile is not None):
            raise ValueError('DG04 exact admission requires the Core-generated source-bound manifest only')
        projected_execution = ExecutionSpec(
            'isaacsim', F05_DG04_ISAAC_NATIVE_PROFILE, 'none', 'cuda',
            declared_execution.provider_seed, 'best_effort',
        )
        admit_capabilities(artifact.required_capabilities, manifest, projected_execution)
        if scope is not None:
            scope.validate_call(artifact, declared_execution, source)
            native_io = scope.factory(
                artifact=artifact, execution=declared_execution, source=source,
                input_v1=_f05_dg04_isaac_native_input,
            )
            required_methods = (
                'metadata', 'write_reset', 'read_state', 'write_position_targets',
                'advance', 'close',
            )
            if any(not callable(getattr(native_io, name, None)) for name in required_methods):
                raise TypeError('DG04 S1 fixture must implement only the exact typed NativeRuntimeIO port')
        else:
            from .isaac_native_io import create_isaac_native_runtime_io

            native_io = create_isaac_native_runtime_io(
                artifact, declared_execution, source,
                dg04_native_input=_f05_dg04_isaac_native_input,
            )
        from .leaf_control import IsaacNativeMimicPositionDriveReceiptV1
        from .native_io import UsdCoreRuntimeSession

        try:
            receipt = getattr(native_io, 'drive_receipt', None)
            expected_provenance = 'synthetic_fixture' if scope is not None else 'native_runtime'
            if (type(receipt) is not IsaacNativeMimicPositionDriveReceiptV1
                    or receipt.provenance_kind != expected_provenance
                    or receipt.execution_identity_sha256 != declared_execution.identity_hash
                    or receipt.source_closure_sha256 != source.source_closure_digest
                    or receipt.scene_identity_sha256 != source.scene_definition.identity_hash
                    or len(receipt.native_dof_names) != 9
                    or set(receipt.native_dof_names) != set(source.joint_targets.values())):
                raise ValueError('DG04 model-bound native mimic receipt differs from exact source/execution mapping')
            session = UsdCoreRuntimeSession(
                artifact, declared_execution, source, native_io, receipt,
            )
        except BaseException as materialization_error:
            try:
                native_io.close()
            except BaseException as cleanup_error:
                materialization_error.add_note(
                    'DG04 native-I/O cleanup after Core admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            if scope is None:
                try:
                    native_io.close_runtime_owner()
                except BaseException as cleanup_error:
                    materialization_error.add_note(
                        'DG04 Isaac App owner cleanup after Core admission failure also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
            raise
        session._declared_execution_spec_v1 = declared_execution
        session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
        return session
    if (_f05_dg02_geophys_input is not None
            or (type(execution) is ExecutionSpecV1
                and execution.physics_profile == F05_DG02_GEOPHYS_USD_PROFILE)):
        if _f05_dg02_geophys_input is None:
            raise ValueError('DG02 GeoPhys/USD profile requires its exact versioned candidate input')
        _validate_f05_dg02_geophys_usd_input(
            _f05_dg02_geophys_input, artifact, declared_execution, source,
        )
        if manifest is None or _materialization_authority is not None or _diagnostic_profile is not None:
            raise ValueError('DG02 exact admission requires its Core-generated capability manifest only')
        projected_execution = ExecutionSpec(
            'geophys', F05_DG02_GEOPHYS_USD_PROFILE, 'none', 'cpu',
            declared_execution.provider_seed, 'best_effort',
        )
        admit_capabilities(artifact.required_capabilities, manifest, projected_execution)
        from .geophys_native_io import create_f05_geophys_native_io
        from .native_io import UsdCoreRuntimeSession

        native_io = create_f05_geophys_native_io(
            artifact=artifact, execution=declared_execution,
            source=source, input_v1=_f05_dg02_geophys_input,
        )
        try:
            receipt = native_io.drive_receipt
            if receipt.identity_sha256 != _f05_dg02_geophys_input.native_drive_receipt.identity_sha256:
                raise ValueError('DG02 runtime model receipt differs from the frozen public-model receipt')
            session = UsdCoreRuntimeSession(
                artifact, declared_execution, source, native_io, receipt,
            )
        except BaseException as materialization_error:
            try:
                native_io.close()
            except BaseException as cleanup_error:
                materialization_error.add_note(
                    'DG02 native-I/O cleanup after Core admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            raise
        session._declared_execution_spec_v1 = declared_execution
        session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
        return session
    if (type(execution) is ExecutionSpecV1
            and execution.physics_profile == F05_DG02_GEOPHYS_USD_PROFILE
            and _f05_dg02_geophys_input is None):
        raise ValueError('DG02 GeoPhys/USD profile cannot use generic v1 admission')
    if type(source) is UsdRuntimeSourceV1:
        if type(declared_execution) is not ExecutionSpecV1:
            raise TypeError('USD RuntimeSource requires an explicit ExecutionSpecV1')
        declared_execution.validate()
        source.validate()
        if declared_execution.physics_provider != source.scene_source.representation.provider:
            raise ValueError('USD source representation provider differs from ExecutionSpecV1')
        if (source.task_artifact.identity_hash != artifact.identity_hash
                or source.scene_definition.identity_hash != artifact.scene_identity_hash):
            raise ValueError('USD RuntimeSource differs from the materialize TaskArtifact')
        if _f05_native_input is not None:
            _validate_f05_geophys_native_position_input(
                _f05_native_input, artifact, declared_execution, source,
            )
            if manifest is not None or _materialization_authority is not None or _diagnostic_profile is not None:
                raise ValueError('F05 native exact-cell admission cannot combine with caller manifests or diagnostics')
            from .geophys_native_io import create_f05_geophys_native_io
            from .native_io import UsdCoreRuntimeSession

            native_io = create_f05_geophys_native_io(
                artifact=artifact, execution=declared_execution,
                source=source, input_v1=_f05_native_input,
            )
            try:
                session = UsdCoreRuntimeSession(
                    artifact, declared_execution, source, native_io,
                    native_io.drive_receipt,
                )
            except BaseException as materialization_error:
                try:
                    native_io.close()
                except BaseException as cleanup_error:
                    materialization_error.add_note(
                        'F05 GeoPhys native-I/O cleanup after Core admission failure also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
                raise
            session._declared_execution_spec_v1 = declared_execution
            session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
            return session
        if declared_execution.physics_profile == F05_GEOPHYS_NATIVE_POSITION_PROFILE:
            raise ValueError('F05 GeoPhys native profile requires its exact versioned source admission input')
        if not (source.scene_source.source_verified or source.scene_source.locally_validated):
            raise ValueError('synthetic or unverified USD source is not admitted for production materialization')
        if not declared_execution.physics_provider == 'isaacsim':
            raise ValueError('no USD Core RuntimeSession adapter is admitted for the selected provider')
        if manifest is not None or _materialization_authority is not None or _diagnostic_profile is not None:
            raise ValueError('F04 Isaac materialization does not accept caller-supplied admission authorities')
        _validate_f04_isaac_position_source(artifact, declared_execution, source)
        from .isaac_native_io import create_isaac_native_runtime_io
        from .native_io import UsdCoreRuntimeSession

        native_io = None
        try:
            native_io = create_isaac_native_runtime_io(artifact, declared_execution, source)
            session = UsdCoreRuntimeSession(
                artifact, declared_execution, source, native_io, drive_receipt=None,
            )
        except BaseException as materialization_error:
            if native_io is not None:
                try:
                    native_io.close()
                except BaseException as cleanup_error:
                    materialization_error.add_note(
                        'Isaac native-I/O cleanup after Core admission failure also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
                try:
                    native_io.close_runtime_owner()
                except BaseException as cleanup_error:
                    materialization_error.add_note(
                        'Isaac App owner cleanup after Core admission failure also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
            raise
        session._declared_execution_spec_v1 = declared_execution
        session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
        return session
    execution = legacy_execution_projection(execution)
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
        if source.fixed_attachment_plan is not None:
            if _materialization_authority is not None:
                raise ValueError('fixed Attachment uses its own exact plan admission, not the dual Position authority')
            _validate_fixed_attachment_materialization_source(artifact, execution, source)
        else:
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
    session = _materialize_admitted(artifact, execution, source)
    if type(declared_execution) is ExecutionSpecV1:
        # Keep the exact V1 declaration alongside the legacy-compatible adapter
        # view. It remains provenance; it is never reconstructed from defaults.
        session._declared_execution_spec_v1 = declared_execution
        session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
    return session


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


def _validate_fixed_attachment_materialization_source(artifact, execution, source) -> None:
    """Preflight the one fixed Panda Arm+Hand plan before native import/compile."""
    from ...artifacts import FixedAttachmentPlanV1, LogicalAssemblyV1
    from ...assembly.fixed_attachment import (
        lower_fixed_attachment_sources, validate_fixed_attachment_scene,
    )

    plan = source.fixed_attachment_plan
    if type(plan) is not FixedAttachmentPlanV1 or type(source.fixed_attachment_assembly) is not LogicalAssemblyV1:
        raise TypeError('fixed Attachment materialization requires the typed R03b plan and Assembly')
    if execution.physics_provider != 'mujoco' or execution.backend != 'cpu' or execution.render_provider != 'none':
        raise ValueError('fixed Attachment materialization is bounded to MuJoCo CPU without rendering')
    if (artifact.timebase.physics_dt, artifact.timebase.control_substeps, artifact.timebase.control_dt) != (
        0.002, 5, 0.01,
    ):
        raise ValueError('fixed Attachment materialization requires the R03b 2 ms / 100 Hz timebase')
    if source.free_joints:
        raise ValueError('fixed Attachment must not admit a free root joint')
    scene = source.scene_definition
    if scene is None:
        raise ValueError('fixed Attachment materialization requires a pinned canonical Scene-v3')
    artifact.validate_scene(scene)
    validate_fixed_attachment_scene(plan, source.fixed_attachment_assembly, scene)
    if (
        plan.parent_entity_id, plan.child_entity_id,
        plan.parent_asset_id, plan.parent_asset_version,
        plan.child_asset_id, plan.child_asset_version,
        plan.parent_source_sha256, plan.child_source_sha256,
        plan.license_source_sha256, plan.parent_mount_site_name,
        plan.child_mount_body_name, plan.namespace_prefix,
        plan.parent_mount.frame_id, plan.child_mount.frame_id,
        plan.parent_root.frame_id, plan.child_root.frame_id,
        plan.reset_hand_opening_m,
    ) != (
        'panda-arm', 'panda-hand', 'panda-arm-nohand', 'menagerie-b846dd12',
        'panda-hand', 'menagerie-b846dd12',
        'e7090a5e2384b18a223ef532d98bf914f7f9a6b74dc8bc9f74c8291201074071',
        'd2a6539d0fd7c55c75c14f11c78f04505ee33f31d93e6112e3ad7120e5ee786a',
        'a6cba85bc92e0cff7a450b1d873c0eaa2e9fc96bf472df0247a26bec77bf3ff9',
        'attachment_site', 'probe_hand_hand', 'probe_hand_',
        'attachment_site', 'hand', 'link0', 'hand', 0.076,
    ):
        raise ValueError('fixed Attachment source pair differs from the accepted R03a source recipe')
    if (
        plan.parent_site_from_child_root.position,
        plan.parent_site_from_child_root.quaternion_wxyz,
        plan.attach_frame_from_child_worldbody.position,
        plan.attach_frame_from_child_worldbody.quaternion_wxyz,
    ) != (
        (0.0, 0.0, 0.0), (0.9238795391929064, 0.0, 0.0, 0.38268341623423263),
        (0.0, 0.0, 0.0), (0.38268341623423263, 0.0, 0.0, -0.9238795391929064),
    ):
        raise ValueError('fixed Attachment mount direction or child-frame compensation differs from the source oracle')
    if plan.collision_policy != 'source_preserved' or plan.extra_cross_entity_overrides:
        raise ValueError('fixed Attachment collision admission must preserve source filters and exclusions')
    assets = {(asset.asset_id, asset.asset_version): asset for asset in scene.assets}
    for asset_id, asset_version, source_reference in (
        (plan.parent_asset_id, plan.parent_asset_version, 'menagerie:franka_emika_panda/panda_nohand.xml'),
        (plan.child_asset_id, plan.child_asset_version, 'menagerie:franka_emika_panda/hand.xml'),
    ):
        asset = assets[(asset_id, asset_version)]
        if (asset.source_reference, asset.source_revision, asset.license_id) != (
            source_reference, 'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7', 'Apache-2.0',
        ):
            raise ValueError('fixed Attachment Asset provenance differs from the pinned source recipe')
    if source.task_artifact_hash != artifact.identity_hash:
        raise ValueError('fixed Attachment RuntimeSource does not bind the exact TaskArtifact')
    if source.scene_source.source_id != f'scene-definition-v3:{scene.identity_hash}':
        raise ValueError('fixed Attachment RuntimeSource ID differs from the pinned Scene')
    if set(source.joints) != set(artifact.initialization.joint_position):
        raise ValueError('fixed Attachment Joint bindings do not cover the exact reset declaration')
    if any(source.joints.get(key) != value for key, value in plan.native_joint_names.items()):
        raise ValueError('fixed Attachment Joint binding differs from its Entity/native map')
    if source.bodies != plan.native_body_names or source.frames != plan.native_site_names:
        raise ValueError('fixed Attachment body/Site bindings differ from their explicit maps')
    expected_arm_targets = {
        f'{plan.parent_entity_id}/joint{index}': plan.native_actuator_names[
            f'{plan.parent_entity_id}/actuator{index}'
        ] for index in range(1, 8)
    }
    if dict(source.joint_targets) != expected_arm_targets:
        raise ValueError('fixed Attachment Arm target mapping differs from its seven named actuator owners')
    expected_hand_open = (plan.native_actuator_names[f'{plan.child_entity_id}/actuator8'],)
    if source.open_actuators != expected_hand_open:
        raise ValueError('fixed Attachment open-actuator mapping differs from source Hand actuator8')
    # The source and path closure are re-read here, still before importing MuJoCo.
    lowered = lower_fixed_attachment_sources(
        parent_source=source.scene_source,
        source_by_entity=source.fixed_attachment_sources,
        scene=scene,
        plan=plan,
        assembly=source.fixed_attachment_assembly,
    )
    if lowered.source_closure_sha256 != source.source_closure_digest:
        raise ValueError('fixed Attachment RuntimeSource closure differs from its measured source closure')

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
