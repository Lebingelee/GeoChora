"""Admission precedes every native materialization. No task-ID dispatch."""
from collections.abc import Callable, Mapping
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
from ...artifacts.execution import (
    EpisodeResetPlanV1, RealizedInitialState, ResetPlanV1, ResetSample,
    legacy_execution_projection,
)
from ...controllers.canonical.feedback import (
    CanonicalControlFeedback, NativeControlFeedbackSampleV1,
)
from ...controllers.canonical.contracts import MixedActuatorCommandV1
from .source import RuntimeSource, UsdRuntimeSourceV1, UsdRuntimeInputV1
from .isaac_g05 import G05_ISAAC_EFFORT_PROFILE, _validate_g05_isaac_effort_source
from .mujoco_attachment_admission import _validate_fixed_attachment_materialization_source
from .isaac_usd_admission import (
    F06_PICKCUBE_ISAAC_PROFILE, _F06_DELIVERY_MANIFEST_SHA256_V1,
    _F06_REPRESENTATION_V1, _F06_TASK_POLICY_SHA256_V1,
    _validate_f06_isaac_delivery, load_f06_isaac_delivery,
    f06_isaac_robot_geometry_root, _validate_usd_task_policy,
    _validate_exact_admission_binding, _validate_f06_pickcube_isaac_input,
    f06_capability_manifest, isaac_cuda_execution_spec,
    build_usd_task_runtime_input, compile_usd_task_runtime_input,
)

CAPABILITIES = ('rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation',
                'joint_state_query', 'body_pose_query', 'frame_pose_query')
PROFILE = 'p1_2_scalar_cpu_v0'


def close_session_and_runtime_owner(
    session, *, first_error=None, session_error_label, owner_error_label,
    capture_close_receipt=False,
):
    """Close a materialized session and its owner, retaining the first fault.

    The receipt is observed after session close and before owner close, as the
    mixed-control session owns that evidence. The caller retains route-specific
    finalization, source/task cleanup and publication of the receipt.
    """
    if session is None:
        return first_error, None

    def retain(error, label):
        nonlocal first_error
        if first_error is None:
            first_error = error
        else:
            first_error.add_note(f'{label} also failed: {type(error).__name__}: {error}')

    try:
        session.close()
    except BaseException as error:
        retain(error, session_error_label)
    receipt = None
    if capture_close_receipt:
        try:
            receipt = getattr(session, 'close_receipt', None)
        except BaseException as error:
            retain(error, 'session close receipt read')
    try:
        close_owner = getattr(session, 'close_runtime_owner', None)
        if callable(close_owner):
            close_owner()
    except BaseException as error:
        retain(error, owner_error_label)
    return first_error, receipt


def validate_selected_position_route(execution):
    """Check the bounded construction envelope, before source-specific admission.

    Passing this check does not admit a source, delivery, provider build, or
    native session; those retain their independent materialization checks.
    """
    route = (execution.physics_provider, execution.physics_backend,
             execution.physics_device, execution.determinism_mode,
             execution.physics_profile)
    if route not in {
        ('isaacsim', 'cuda', 'cuda:0', 'best_effort', F06_PICKCUBE_ISAAC_PROFILE),
        ('isaacsim', 'cuda', 'cuda:0', 'best_effort', G05_ISAAC_EFFORT_PROFILE),
    }:
        raise ValueError('versioned Position construction has an unsupported provider execution route')


_DUAL_POSITION_MATERIALIZATION_AUTHORITY = object()


class RuntimeSession(Protocol):
    @property
    def provider_materialization_id(self) -> str: ...
    @property
    def episode_id(self) -> str: ...
    @property
    def state_revision(self) -> int: ...
    def reset(self, sample: ResetSample) -> RealizedInitialState: ...
    def reset_plan(self, plan: EpisodeResetPlanV1 | ResetPlanV1) -> RealizedInitialState: ...
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


class CompiledModelOptionsReadbackV1(Protocol):
    """Optional provider-bound readback of effective compiled model settings.

    This diagnostic interface is separate from ``RuntimeSession`` so a
    provider does not claim model-option readback unless its adapter can bind
    the values to the exact compiled model and source receipt.
    """

    @property
    def compiled_model_options_receipt_v1(self) -> Mapping[str, object]: ...


class CompiledModelPhysicsFingerprintReadbackV1(Protocol):
    """Optional source-bound hashes of compiled physical-model arrays.

    This diagnostic is separate from ``RuntimeSession`` and returns only
    versioned inventory plus hashes, not provider-owned model objects.
    """

    @property
    def compiled_model_physics_fingerprint_v1(self) -> Mapping[str, object]: ...


class MixedActuatorSubstepSession(Protocol):
    """Optional profile capability for state-bound commands at every physics step."""

    def step_mixed_actuator_interval(
        self,
        command_factory: Callable[[CanonicalStateView, int, int, int], MixedActuatorCommandV1],
    ) -> tuple[CanonicalStateView, Mapping[str, object]]: ...


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


def _f06_pickcube_isaac_capability_manifest(artifact):
    return f06_capability_manifest(artifact, CAPABILITIES)


def _session_admission_input_route(input_v1) -> str | None:
    """Classify one exact task-owned input for a versioned Session route."""
    if input_v1 is None:
        return None
    if (type(input_v1) is UsdRuntimeInputV1
            and getattr(input_v1, 'schema_version', None) == 'pick-cube-isaac-runtime-input-v1'):
        return 'f06_pickcube'
    raise TypeError('Session admission requires one exact supported task runtime input')


def _require_session_admission_input_route(input_v1, expected, message):
    """Require the centralized exact input type, retaining each caller's error."""
    try:
        actual = _session_admission_input_route(input_v1)
    except TypeError as error:
        raise TypeError(message) from error
    if actual != expected:
        raise TypeError(message)


def _close_failed_native_materialization(
        error, native_io, *, io_label, runtime_owner_label=None):
    if native_io is None:
        return
    cleanup_steps = [('close', io_label)]
    if runtime_owner_label is not None:
        cleanup_steps.append(('close_runtime_owner', runtime_owner_label))
    for method_name, label in cleanup_steps:
        try:
            getattr(native_io, method_name)()
        except BaseException as cleanup_error:
            error.add_note(
                f'{label} cleanup after Core admission failure also failed: '
                f'{type(cleanup_error).__name__}: {cleanup_error}'
            )


def _mixed_actuator_manifest(artifact, execution, source):
    """Admit the bounded, typed source-bound mixed actuator route."""
    from dataclasses import replace
    import hashlib
    from pathlib import Path
    from ...controllers.canonical.contracts import MixedActuatorPlanV1

    plan = getattr(source, 'mixed_actuator_plan', None)
    if type(plan) is not MixedActuatorPlanV1:
        raise ValueError('mixed actuator admission requires its typed source-bound plan')
    plan.validate()
    if not isinstance(artifact, TaskArtifact):
        raise ValueError('mixed actuator admission requires TaskArtifact v0')
    if (execution.physics_provider, execution.backend, execution.render_provider,
            execution.physics_profile, execution.determinism_mode) not in {
            ('mujoco', 'cpu', 'none', PROFILE, 'strict'),
            ('geophys', 'cpu', 'none', PROFILE, 'strict'),
    }:
        raise ValueError('mixed actuator admission requires strict scalar CPU state-only execution')
    if (plan.task_artifact_hash != artifact.identity_hash
            or plan.source_id != source.scene_source.source_id
            or plan.source_closure_digest != source.source_closure_digest):
        raise ValueError('mixed actuator plan differs from its Artifact or RuntimeSource identity')
    if (source.config.runtime.physics_dt != artifact.timebase.physics_dt
            or source.config.runtime.control_substeps != artifact.timebase.control_substeps
            or source.config.runtime.backend != 'cpu'
            or source.config.runtime.integrator not in ('implicitfast', 'euler')
            or source.config.render.camera_obs):
        raise ValueError(
            'mixed actuator source requires the supported strict scalar CPU envelope '
            'with an implicitfast or euler integrator'
        )
    receipt = getattr(source, 'execution_source_receipt', None)
    if (receipt is None or source.scene_definition is not None
            or source.scene_source.source_id != receipt.source_id
            or source.scene_source.base_dir is None
            or source.source_closure_digest != receipt.source_closure_digest
            or source.scene_source.xml.encode('utf-8') != receipt.closure_files.get('canonical-source.xml')
            or Path(source.scene_source.base_dir).resolve() != receipt.snapshot_root):
        raise ValueError('mixed actuator admission requires its immutable canonical/importer source receipt')
    receipt.validate_snapshot()
    if (hashlib.sha256(receipt.importer_xml).hexdigest() != receipt.importer_xml_sha256
            or receipt.closure_files.get('scene.xml') != receipt.importer_xml):
        raise ValueError('mixed actuator source receipt does not bind its importer XML bytes')
    if source.task_artifact_hash != artifact.identity_hash:
        raise ValueError('mixed actuator RuntimeSource differs from the exact Artifact')
    if not source.torque_actuators or not source.position_actuators:
        raise ValueError('supported mixed actuator profile requires torque and position channels')
    if not set(source.contact_geom_groups) <= set(source.bodies) | set(source.fixture_bodies):
        raise ValueError('contact geom groups must bind named source bodies or fixtures')
    evidence = (
        f'mixed-actuator-plan={plan.identity_hash}/artifact={artifact.identity_hash}/'
        f'source={receipt.canonical_xml_sha256}/closure={receipt.source_closure_digest}'
    )
    provider = execution.physics_provider
    base = provider_manifest(provider)
    claims = tuple(base.capabilities)
    unsupported = base.known_unsupported
    if provider in {'mujoco', 'geophys'}:
        if not any(channel.drive_mode == 'joint_torque' for channel in plan.channels):
            raise ValueError('mixed actuator admission requires a named torque channel')
        claims += (CapabilityClaim(
            'joint_torque_actuation', 'tested',
            f'{evidence}/provider_adapter=task_env.runtime.sessions.{provider}',
        ),)
        unsupported = tuple(item for item in unsupported if item != 'joint_torque_actuation')
    if source.contact_geom_groups:
        if provider == 'geophys':
            raise ValueError('GeoPhys mixed actuator admission does not claim geom-pair contact queries')
        claims += (CapabilityClaim('contact_detection', 'tested', evidence),)
        unsupported = tuple(item for item in unsupported if item != 'contact_detection')
    return replace(
        base, adapter_version=(
            'task-env-mixed-actuator-source-v1' if provider == 'mujoco'
            else 'task-env-geophys-mixed-actuator-source-v1'
        ),
        capabilities=claims, known_unsupported=unsupported, evidence_reference=evidence,
    )


def materialize(artifact: TaskArtifact | TaskArtifactV1, execution: ExecutionSpec | ExecutionSpecV1, *,
                source: RuntimeSource | UsdRuntimeSourceV1,
                manifest: ProviderCapabilityManifest | None = None,
                _materialization_authority=None,
                _session_admission_input=None,
                _observer_render_request=None, _task_render_requested=False,
                _legacy_observer_requested=False,
                _legacy_camera_observations=False,
                _geophys_contact_mode='provider_default') -> RuntimeSession:
    if _geophys_contact_mode not in ('provider_default', 'discrete', 'continuous'):
        raise ValueError('unsupported GeoPhys contact mode')
    if _geophys_contact_mode != 'provider_default' and execution.physics_provider != 'geophys':
        raise ValueError('explicit GeoPhys contact mode requires the GeoPhys provider')
    if type(_legacy_observer_requested) is not bool:
        raise TypeError('legacy observer request must be boolean')
    if type(_task_render_requested) is not bool:
        raise TypeError('task render request must be boolean')
    if _legacy_observer_requested and execution.physics_provider != 'geophys':
        raise ValueError('legacy observer is only available with GeoPhys physics')
    if type(_legacy_camera_observations) is not bool:
        raise TypeError('legacy camera observation request must be boolean')
    if _legacy_camera_observations and execution.physics_provider != 'geophys':
        raise ValueError('legacy camera observations require GeoPhys physics')
    if not isinstance(artifact, (TaskArtifact, TaskArtifactV1)):
        raise TypeError('materialize requires TaskArtifact v0 or v1')
    if isinstance(artifact, TaskArtifactV1):
        artifact.validate()
    declared_execution = execution
    if _observer_render_request is not None:
        from ...render.base.contracts import ObserverRenderRequestV1
        if type(_observer_render_request) is not ObserverRenderRequestV1:
            raise TypeError('observer render requirement must use ObserverRenderRequestV1')
        _observer_render_request.validate(artifact=artifact, physics_provider=execution.physics_provider,
                                          physics_backend=(execution.physics_backend if type(execution) is ExecutionSpecV1
                                                           else execution.backend))
    admission_route = _session_admission_input_route(_session_admission_input)
    if (_observer_render_request is not None and _observer_render_request.provider == 'isaacsim'
            and admission_route != 'f06_pickcube'
            and getattr(declared_execution, 'physics_profile', None) != G05_ISAAC_EFFORT_PROFILE):
        raise ValueError('Isaac observer request requires an admitted F06 or G05 input')
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
        if manifest is None and _materialization_authority is None:
            manifest = expected_manifest
        if (manifest is None or manifest.identity_hash != expected_manifest.identity_hash
                or _materialization_authority is not None):
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
            observer_render_request=_observer_render_request,
            task_render_requested=_task_render_requested,
        )
        from .native_io import UsdCoreRuntimeSession
        try:
            session = UsdCoreRuntimeSession(
                artifact, declared_execution, source, native_io,
                getattr(native_io, 'drive_receipt', None),
            )
        except BaseException as materialization_error:
            _close_failed_native_materialization(
                materialization_error, native_io,
                io_label='F06 Isaac native-I/O',
                runtime_owner_label='F06 Isaac App owner',
            )
            raise
        session._declared_execution_spec_v1 = declared_execution
        session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
        return session
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
        if not (source.scene_source.source_verified or source.scene_source.locally_validated):
            raise ValueError('synthetic or unverified USD source is not admitted for production materialization')
        if not declared_execution.physics_provider == 'isaacsim':
            raise ValueError('no USD Core RuntimeSession adapter is admitted for the selected provider')
        if manifest is not None or _materialization_authority is not None:
            raise ValueError('Isaac materialization does not accept caller-supplied admission authorities')
        from .isaac_native_io import create_isaac_native_runtime_io
        from .native_io import UsdCoreRuntimeSession
        if declared_execution.physics_profile == G05_ISAAC_EFFORT_PROFILE:
            _validate_g05_isaac_effort_source(artifact, declared_execution, source)
            native_io = None
            try:
                native_io = create_isaac_native_runtime_io(
                    artifact, declared_execution, source,
                    g05_effort=True, observer_render_request=_observer_render_request,
                    task_render_requested=_task_render_requested,
                )
                session = UsdCoreRuntimeSession(
                    artifact, declared_execution, source, native_io, drive_receipt=None,
                )
            except BaseException as materialization_error:
                _close_failed_native_materialization(
                    materialization_error, native_io, io_label='G05 Isaac effort native-I/O',
                    runtime_owner_label='G05 Isaac App owner',
                )
                raise
            session._declared_execution_spec_v1 = declared_execution
            session._declared_execution_spec_v1_identity_sha256 = declared_execution.identity_hash
            return session
        raise ValueError('unsupported Isaac USD execution profile')
    execution = legacy_execution_projection(execution)
    if source.mixed_actuator_plan is not None:
        actual = _mixed_actuator_manifest(artifact, execution, source)
    else:
        actual = provider_manifest(execution.physics_provider)
    # A caller may restrict a manifest for negative admission, never expand support.
    if manifest is not None:
        if source.mixed_actuator_plan is not None:
            raise ValueError('bounded process-local admission does not accept caller-supplied manifests')
        admit_capabilities(artifact.required_capabilities, manifest, execution)
    admit_capabilities(artifact.required_capabilities, actual, execution)
    if source.mixed_actuator_plan is not None and source.contact_geom_groups:
        from ...artifacts import RequiredCapabilitySet
        admit_capabilities(RequiredCapabilitySet(('contact_detection',)), actual, execution)
    if execution.render_provider != 'none':
        raise ValueError('P1.2 rendering is unsupported')
    if (source.config.runtime.physics_dt != artifact.timebase.physics_dt
            or source.config.runtime.control_substeps != artifact.timebase.control_substeps
            or source.config.runtime.backend != execution.backend
            or (source.config.render.camera_obs and not _legacy_camera_observations)):
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
    materialization_options = {'mixed_actuator_plan': source.mixed_actuator_plan,
                               'observer_render_request': _observer_render_request}
    if _geophys_contact_mode != 'provider_default':
        materialization_options['geophys_contact_mode'] = _geophys_contact_mode
    if _legacy_observer_requested:
        materialization_options['legacy_observer_requested'] = True
    if _legacy_camera_observations:
        materialization_options['legacy_camera_observations'] = True
    session = _materialize_admitted(artifact, execution, source, **materialization_options)
    if _observer_render_request is not None and _observer_render_request.provider == 'geophys':
        import hashlib
        import json
        session._observer_execution_identity = hashlib.sha256(
            json.dumps(declared_execution.to_mapping(), sort_keys=True,
                       separators=(',', ':'), allow_nan=False).encode()).hexdigest()
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
    if set(artifact.initialization.poses_world) != set(source.free_joints):
        raise ValueError('free-body reset poses must exactly match source free-joint bindings')
    for semantic, native in source.free_joints.items():
        frame = artifact.legacy_frame_bindings.get(semantic)
        matches = [joint for articulation in scene.articulations or () for joint in articulation.joints
                   if joint.kind == 'floating' and joint.joint_id == native
                   and joint.child_frame == frame]
        if len(matches) != 1:
            raise ValueError('free-body reset pose must bind one canonical floating Joint')
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


def _materialize_admitted(artifact, execution, source, *, mixed_actuator_plan=None,
                          observer_render_request=None, legacy_observer_requested=False,
                          legacy_camera_observations=False, geophys_contact_mode='provider_default'):
    if execution.physics_provider == 'geophys':
        from .geophys import _GeoPhysSession
        options = {'observer_render_request': observer_render_request}
        if geophys_contact_mode != 'provider_default':
            options['contact_mode'] = geophys_contact_mode
        if legacy_observer_requested:
            options['legacy_observer_requested'] = True
        if legacy_camera_observations:
            options['legacy_camera_observations'] = True
        return _GeoPhysSession(artifact, source, **options)
    if execution.physics_provider == 'mujoco':
        from .mujoco import _MuJoCoSession
        return _MuJoCoSession(artifact, source, mixed_actuator_plan=mixed_actuator_plan)
    if execution.physics_provider == 'sapien':
        from .sapien import _SapienSession
        return _SapienSession(artifact, source)
    if execution.physics_provider == 'genesis':
        from .genesis import _GenesisSession
        return _GenesisSession(artifact, source)
    raise ValueError(f'unknown physics provider: {execution.physics_provider}')


def project_feedback_assessment(projected_feedback, artifact, source, actual_capabilities, helper):
    """Classify each existing typed feedback requirement against source bindings."""
    result = []
    for writer_id, requirement in projected_feedback:
        name, kind = requirement.required_capability, requirement.subject_kind
        semantic = requirement.entity_id + '/' + requirement.subject_id
        if kind == 'frame':
            bindings = getattr(artifact, 'legacy_frame_bindings', {})
            matches = [key for key, reference in bindings.items()
                       if reference.entity_id == requirement.entity_id
                       and reference.frame_id == requirement.subject_id
                       and key in (set(getattr(source, 'frames', {})) |
                                   set(getattr(source, 'bodies', {})))]
            if len(matches) == 1:
                semantic = matches[0]
        source_values = (getattr(source, 'joints', {}) if kind == 'joint'
                         else {**getattr(source, 'bodies', {}), **getattr(source, 'frames', {})}
                         if kind == 'frame' else {})
        supported = name in actual_capabilities and kind in {'joint', 'frame'}
        bound = semantic in source_values
        subject = ('state:' + kind + ':' + semantic + ':' + requirement.field_name + ':'
                   + requirement.sample_domain + ':' + writer_id)
        result.append((name, subject, requirement.requiredness, supported,
                       'unknown' if bound else 'unsatisfied',
                       (f'{helper} must resolve the declared Controller feedback object' if supported and bound
                        else 'selected Core adapter does not implement this declared feedback field' if not supported
                        else 'declared feedback object has no source binding'),
                       helper if supported and bound else None))
    return tuple(result)


def assess_selected_request(*, selection, artifact, source, value, binding,
                            dependency_status, request_identity, caller_manifest=None):
    """Assess actual selected declarations before any native materialization.

    Provider API and historical evidence are intentionally not inferred from
    a generic Core manifest. Exact build checks are identified separately.
    """
    from ...artifacts import CapabilityAssessmentV1, CapabilityAssessmentRowV1
    from .control import (ControlBinding, ControlBindingPlanV1, bind_selected_controller,
                          prepare_position_control_materialization, project_controller_feedback,
                          declared_source_capabilities)
    from ...artifacts.contracts import SUPPORTED_STATUSES

    if dependency_status not in {'available', 'unavailable', 'unknown'}:
        raise ValueError('invalid dependency assessment status')
    if caller_manifest is not None and not isinstance(caller_manifest, ProviderCapabilityManifest):
        raise TypeError('caller restriction must be a ProviderCapabilityManifest')
    actual_capabilities = set(CAPABILITIES)
    restricted = None if caller_manifest is None else {
        item.name for item in caller_manifest.capabilities if item.status in SUPPORTED_STATUSES
    }
    if caller_manifest is not None and (caller_manifest.provider_name != selection.physics_provider
                                        or caller_manifest.backend != selection.physics_backend):
        restricted = set()
    phase = 'static_preflight'
    rows = []

    helper = {
        'mujoco': 'task_env.runtime.sessions.mujoco:check_mujoco_named_layout',
        'geophys': 'task_env.runtime.sessions.geophys:check_geophys_named_layout',
        'isaacsim': 'task_env.runtime.sessions.isaac_native_io:check_isaac_named_layout',
    }.get(selection.physics_provider)

    def row(capability, subject, required='required', *, implemented=True,
            valid='satisfied', reason='Core declaration was checked',
            oracle=None, restrict=False):
        rows.append(CapabilityAssessmentRowV1(
            'capability-assessment-row-v1', capability, subject, required,
            'supported' if implemented and valid != 'unknown' else 'unknown',
            'implemented' if implemented else 'not_implemented',
            dependency_status, 'none', phase, reason, None,
            oracle if implemented else None, 'denied' if restrict else 'none', valid,
        ))

    source_problem = None
    try:
        artifact.validate()
        if (value.get('source') is not source or value.get('artifact') is None
                or value['artifact'].identity_hash != artifact.identity_hash):
            raise ValueError('selected value/source/Artifact identity mismatch')
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError('source/Artifact identity mismatch')
        if selection.physics_provider in {'geophys', 'mujoco'}:
            if not isinstance(source, RuntimeSource):
                raise TypeError('MJCF route requires RuntimeSource')
            if (source.config.runtime.backend != selection.physics_backend
                    or source.config.runtime.physics_dt != artifact.timebase.physics_dt
                    or source.config.runtime.control_substeps != artifact.timebase.control_substeps
                    or source.config.render.camera_obs):
                raise ValueError('source execution/timebase mismatch')
            if not set(artifact.initialization.joint_position) <= set(source.joints):
                raise ValueError('source joint bindings do not cover initialization')
            if not set(artifact.semantics.required_poses) <= set(source.bodies) | set(source.frames):
                raise ValueError('source pose bindings do not cover semantics')
            if isinstance(artifact, TaskArtifactV1):
                execution = ExecutionSpec(selection.physics_provider, PROFILE, 'none',
                                          selection.physics_backend, 0, 'strict')
                if source.fixed_attachment_plan is not None:
                    _validate_fixed_attachment_materialization_source(artifact, execution, source)
                else:
                    _validate_v1_materialization_source(
                        artifact, execution, source,
                        _allow_independent_robot_instances=(
                            isinstance(value.get('controller'), (tuple, list))
                            and len(value['controller']) > 1),
                    )
            elif source.scene_definition is not None and selection.physics_provider != 'geophys':
                raise ValueError('Scene-v3 legacy projection is currently GeoPhys-only')
            # Check names against this request's actual MJCF, not only the
            # number of joints or actuators in its declared binding.
            import xml.etree.ElementTree as ET
            root = ET.fromstring(source.scene_source.xml)
            joints = {node.get('name') for tag in ('joint', 'freejoint') for node in root.iter(tag)}
            bodies = {node.get('name') for node in root.iter('body')}
            sites = {node.get('name') for node in root.iter('site')}
            actuators = root.find('actuator')
            actuators = set() if actuators is None else {node.get('name') for node in actuators}
            if source.composition_runtime_input is not None:
                if selection.physics_provider != 'mujoco':
                    raise ValueError('source composition has no admitted adapter for this provider')
                from .mujoco_composition import validate_composed_source_names
                validate_composed_source_names(source)
            for label, requested, available in (() if (source.fixed_attachment_plan is not None
                    or source.composition_runtime_input is not None) else (
                ('joint', (*source.joints.values(), *source.free_joints.values()), joints),
                ('body', source.bodies.values(), bodies),
                ('frame', source.frames.values(), sites),
                ('actuator', (*source.joint_targets.values(), *source.open_actuators,
                              *source.torque_actuators.values(), *source.position_actuators.values()), actuators),
            )):
                missing = set(requested) - available
                if missing:
                    raise ValueError(f'selected source missing named {label}: {sorted(missing)}')
            receipt = source.execution_source_receipt
            if source.scene_definition is None:
                if receipt is None or source.source_closure_digest is None:
                    raise ValueError('asset closure has no source-bound receipt; native import cannot prove the requested closure')
                receipt.validate_snapshot()
            elif source.source_closure_digest is None:
                raise ValueError('versioned Scene source has no declared closure digest')
        elif selection.physics_provider == 'isaacsim':
            runtime_input = value.get('session_admission_input')
            declared_execution = value.get('execution_spec_v1')
            if type(runtime_input) is UsdRuntimeInputV1:
                _validate_f06_pickcube_isaac_input(runtime_input, artifact, runtime_input.execution, source)
            elif (type(declared_execution) is ExecutionSpecV1
                  and declared_execution.physics_profile == G05_ISAAC_EFFORT_PROFILE
                  and type(source) is UsdRuntimeSourceV1):
                if (declared_execution.physics_provider, declared_execution.physics_backend,
                        declared_execution.physics_device) != (
                        selection.physics_provider, selection.physics_backend, selection.physics_device):
                    raise ValueError('USD execution differs from the requested provider selection')
                _validate_g05_isaac_effort_source(artifact, declared_execution, source)
            else:
                raise TypeError('Isaac source requires an admitted runtime input or G05 effort declaration')
        else:
            raise ValueError('no selected adapter for provider')
    except (TypeError, ValueError, OSError, AttributeError) as error:
        source_problem = f'{type(error).__name__}: {error}'
    row('source_closure', 'task:' + artifact.task_id,
        valid='unsatisfied' if source_problem else 'satisfied',
        reason=source_problem or 'source declarations passed; native importer must verify the closure')

    selected = None
    control_problem = None
    plan = value.get('controller_binding_plan')
    declared_bindings = ()
    projected_feedback = ()
    try:
        if plan is not None:
            if (type(plan) is not ControlBindingPlanV1 or not plan._compiled
                    or source.scene_definition is None
                    or plan.scene_identity_hash != source.scene_definition.identity_hash):
                raise ValueError('Controller binding plan is not compiled for the selected Scene')
            declared_bindings = plan.controller_bindings
            projected_feedback = project_controller_feedback(plan)
        selected = bind_selected_controller(value, binding=binding,
                                            provider=selection.physics_provider,
                                            backend=selection.physics_backend)
        if selection.deployment == 'isolated_worker' and len(selected.position_profiles) > 1:
            raise ValueError('selected worker profile is outside the scalar adapter envelope')
        if value.get('physical_execution') is not None:
            from .physical_control import PhysicalControlExecutionV1
            physical = value['physical_execution']
            position_owner = (selected.position and len(selected.position_capabilities) == 1
                              and callable(binding.physical_observation_binding)
                              and (selection.physics_provider, selection.physics_backend)
                                  in {('mujoco', 'cpu'), ('geophys', 'cpu'), ('isaacsim', 'cuda')})
            if (type(physical) is not PhysicalControlExecutionV1
                    or (not position_owner
                        and not any(selected.controller is item for item in physical.controllers))):
                raise ValueError('physical Controller is not bound to the selected execution')
            if selection.deployment == 'isolated_worker':
                if (physical.requires_source_dynamics
                        and (selection.physics_provider, selection.physics_backend) != ('mujoco', 'cpu')):
                    raise ValueError('physical worker source dynamics requires MuJoCo CPU')
                if physical.compiled.binding.bodies:
                    raise ValueError('physical worker currently admits joint effort only')
            physical.validate_source(
                scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
                source_id=source.source_id, source_closure_sha256=source.source_closure_digest,
                source=source,
            )
            if getattr(source, 'torque_actuators', None) and selection.physics_provider in {'mujoco', 'geophys'}:
                # Typed effort execution and its source bindings were checked;
                # the adapter still verifies native actuator names at build.
                actual_capabilities.add('joint_torque_actuation')
            if position_owner:
                if any(selected.controller is item or selected.controller.identity == item.identity
                       for item in physical.controllers):
                    raise ValueError('Position and physical port Controllers must have distinct identities')
                plan, _, _, _ = prepare_position_control_materialization(
                    source=source, artifact=artifact, profiles=selected.position_profiles,
                    plan=value.get('controller_binding_plan'),
                    select_binding=binding.position_control_binding, value=value,
                    capabilities=selected.position_capabilities,
                )
                declared_bindings = plan.controller_bindings
                projected_feedback = project_controller_feedback(plan)
        elif selected.position:
            if not declared_bindings:
                declared_bindings = tuple(profile.controller_binding() for profile in selected.position_profiles)
            plan, _, _, _ = prepare_position_control_materialization(
                source=source, artifact=artifact, profiles=selected.position_profiles,
                plan=value.get('controller_binding_plan'),
                select_binding=binding.position_control_binding, value=value,
            )
            projected_feedback = project_controller_feedback(plan)
        else:
            if type(binding.scalar_control_binding) is not ControlBinding:
                raise TypeError('selected scalar Controller binding is missing')
            if len(source.joint_targets) != 7 or len(source.open_actuators) != 1:
                raise ValueError('source lacks the scalar position control bindings')
            import hashlib
            controller_artifact = getattr(selected.controller, 'source_artifact_hash', None)
            controller_source = getattr(selected.controller, 'source_xml_sha256', None)
            if (controller_artifact != artifact.identity_hash
                    or controller_source != hashlib.sha256(source.scene_source.xml.encode()).hexdigest()):
                raise ValueError('Controller model does not match the selected Artifact and source')
    except (TypeError, ValueError, OSError, AttributeError) as error:
        control_problem = f'{type(error).__name__}: {error}'
    row('controller_binding', 'controller:' + artifact.task_id,
        valid='unsatisfied' if control_problem else 'satisfied',
        reason=control_problem or 'Controller/source declarations passed; build must verify native mapping',
        oracle=None)

    # Legacy scalar Controller requirements are inferred from its actual source
    # bindings; versioned controllers contribute their declared feedback below.
    declared = set(artifact.required_capabilities.names)
    for name in sorted(declared):
        available = name in actual_capabilities
        row(name, 'task:' + artifact.task_id, implemented=available,
            reason=('selected adapter exposes this declared capability; native evidence remains separate'
                    if available else 'required capability has no selected Core adapter'),
            restrict=restricted is not None and name not in restricted)

    for name in declared_source_capabilities(source).names:
        row(name, 'source:' + artifact.task_id,
            implemented=name in actual_capabilities,
            reason='required by the selected source bindings',
            restrict=restricted is not None and name not in restricted)

    source_objects = (
        ('joints', 'joint', 'joint_state_query'),
        ('free_joints', 'free', 'free_body'),
        ('bodies', 'body', 'body_pose_query'),
        ('frames', 'frame', 'frame_pose_query'),
        ('joint_targets', 'actuator', 'joint_position_actuation'),
        ('torque_actuators', 'actuator', 'joint_torque_actuation'),
        ('position_actuators', 'actuator', 'joint_position_actuation'),
    )
    check_conditions = {
        'joint': 'resolve the named scalar joint and its valid position/velocity state',
        'free': 'resolve the named floating body and its valid pose/velocity state',
        'body': 'resolve the named body and its public pose mapping',
        'frame': 'resolve the named site or public frame view',
        'actuator': 'resolve the named actuator and its declared joint mapping',
    }
    for field, kind, capability in source_objects:
        for semantic, native in getattr(source, field, {}).items():
            row(capability, kind + ':' + semantic, valid='unknown', oracle=helper,
                reason=(f'{helper} must {check_conditions[kind]} for '
                        f'{semantic!r} -> {native!r}; missing or incompatible mapping fails build'),
                restrict=restricted is not None and capability not in restricted)
    for native in getattr(source, 'open_actuators', ()):
        row('joint_position_actuation', 'actuator:open:' + native, valid='unknown', oracle=helper,
            reason=f'{helper} must resolve the declared opening actuator in the actual model',
            restrict=restricted is not None and 'joint_position_actuation' not in restricted)

    if plan is not None and declared_bindings:
        for controller_binding in plan.controller_bindings:
            for group in controller_binding.groups:
                row('control_group_binding', 'group:' + group.entity_id + '/' + group.group_id,
                    reason='compiled Scene ControlGroup is assigned to writer ' + controller_binding.writer_id)
        for entity_id, actuator_id, writer_id in plan.resource_writers:
            row('control_resource_binding', 'resource:' + entity_id + '/' + actuator_id,
                reason='compiled Scene actuator resource is assigned to writer ' + writer_id)
    for name, subject, required, supported, valid, reason, oracle in project_feedback_assessment(
            projected_feedback, artifact, source, actual_capabilities, helper):
        row(name, subject, required=required, implemented=supported, valid=valid,
            reason=reason, oracle=oracle, restrict=restricted is not None and name not in restricted)
    row('scalar_layout', 'batch:scalar',
        valid='satisfied' if selection.batch_layout == 'scalar' else 'unsatisfied',
        reason='selected adapter is scalar; native batch and partial reset are not admitted')
    render = selection.render_default
    state_only = (render.provider, render.backend, render.profile, render.device) == ('none', 'cpu', 'none', None)
    row('state_only_renderer', 'renderer:default',
        valid='satisfied' if state_only else 'unsatisfied',
        reason='selected adapter admits state-only rendering' if state_only else 'required renderer is not implemented')
    return CapabilityAssessmentV1('capability-assessment-v1', request_identity, phase, tuple(rows))
