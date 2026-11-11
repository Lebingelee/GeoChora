"""Internal binding between selected task semantics and the environment."""

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Callable


def _identity_seed(seed):
    return seed


def _no_reset_kwargs(env):
    return {}


def _no_observe_kwargs(env, guard_samples):
    return {}


@dataclass(frozen=True)
class ResetReconstructionResult:
    value: object
    artifact: object
    seed: int
    solution: object


class _ResetReconstruction:
    """Task binding's reconstruction policy for one selected configuration."""
    def __init__(self, binding, provider, backend, horizon):
        self.binding, self.provider, self.backend, self.horizon = binding, provider, backend, horizon
        self.sampled_reset = None

    def build_switch_candidate(self, seed):
        if self.binding.build_seeded is None:
            raise ValueError('configuration switch requires a seeded task builder')
        return self.binding.build_seeded(self.provider, self.backend, seed, self.horizon)

    def use_binding(self, binding):
        """Use the Env's currently admitted task binding without changing policy."""
        self.binding = binding

    def _validate_solutions(self, value, external_solution, *, validate_owned=False):
        if external_solution is not None:
            self.binding.validate_external_solution(value, external_solution)
        solution = value.get('solution')
        if validate_owned and solution is not None:
            self.binding.validate_external_solution(value, solution)
        return solution

    def _finish(self, value, artifact, seed, external_solution, artifact_for_reset, set_phase):
        raise NotImplementedError

    def reconstruct(self, current, artifact, seed, external_solution, artifact_for_reset, *,
                    verify_source, set_phase=lambda _phase: None, prepared=None):
        value = prepared if prepared is not None else self.build_reset(current, seed, external_solution)
        old_receipt = getattr(current.get('source'), 'execution_source_receipt', None)
        receipt = getattr(value.get('source'), 'execution_source_receipt', None)
        try:
            verify_source(value)
            artifact, seed, solution = self._finish(
                value, artifact, seed, external_solution, artifact_for_reset, set_phase)
            # Keep the prior source lease until the replacement is validated;
            # a failed replacement must not strand the reset recovery route.
            if old_receipt is not None and old_receipt is not receipt:
                old_receipt.close()
        except BaseException as error:
            # A newly built source can own a temporary snapshot even when
            # validation fails before the Env installs it.
            if receipt is not None and receipt is not old_receipt:
                try:
                    receipt.close()
                except BaseException as cleanup_error:
                    error.add_note(f'rebuilt source cleanup also failed: {cleanup_error!r}')
            raise
        return ResetReconstructionResult(value, artifact, seed, solution)


class _StandardResetReconstruction(_ResetReconstruction):
    def initial(self):
        if self.binding.build_seeded is not None:
            return self.binding.build_seeded(self.provider, self.backend, 31, self.horizon)
        return self.binding.build_for_provider(self.provider)

    def build_reset(self, current, seed, external_solution):
        if external_solution is not None:
            return self.binding.build_external(self.provider)
        if self.binding.build_sampled is not None:
            return self.binding.build_sampled(
                self.provider, self.backend, seed, self.horizon, self.sampled_reset)
        if self.binding.build_seeded is not None:
            return self.binding.build_seeded(self.provider, self.backend, seed, self.horizon)
        return self.binding.build_for_provider(self.provider)

    def _finish(self, value, artifact, seed, external_solution, artifact_for_reset, set_phase):
        selector = getattr(self.binding, 'reset_runtime_input', None)
        runtime_input = selector(value) if selector else None
        artifact = artifact_for_reset(artifact, value, runtime_input)
        solution = self._validate_solutions(value, external_solution)
        set_phase('reset_seed')
        return artifact, seed, solution


class _MixedResetReconstruction(_ResetReconstruction):
    def __init__(self, *args):
        super().__init__(*args)
        self._initial_pending = True

    def initial(self):
        return self.binding.build_mixed_control_profile(self.provider, self.backend)

    def build_reset(self, current, seed, external_solution):
        if self._initial_pending:
            self._initial_pending = False
            return current
        return self.binding.build_mixed_control_profile(self.provider, self.backend)

    def _finish(self, value, artifact, seed, external_solution, artifact_for_reset, set_phase):
        if value['artifact'] != artifact:
            raise ValueError('selected Artifact changed between construction and reset')
        solution = self._validate_solutions(value, external_solution)
        set_phase('reset_seed')
        return artifact, self.binding.reset_seed(seed), solution


class _NativeFeedbackResetReconstruction(_ResetReconstruction):
    def __init__(self, binding, provider, backend, horizon, request):
        super().__init__(binding, provider, backend, horizon)
        if binding.admit_native_feedback_profile is None:
            raise ValueError('normal native-feedback profile requires an opted-in task binding')
        self.profile = binding.admit_native_feedback_profile(provider, backend, request)
        if type(self.profile) is not str or not self.profile:
            raise ValueError('native-feedback admission must return a nonempty profile identifier')
        self.request = request

    def initial(self):
        return self.binding.build_native_feedback_profile(self.provider, self.backend, self.request, False)

    def build_reset(self, current, seed, external_solution):
        return self.initial()

    def _finish(self, value, artifact, seed, external_solution, artifact_for_reset, set_phase):
        if value['artifact'] != artifact:
            raise ValueError('selected Artifact changed between construction and reset')
        if external_solution is not None:
            self.binding.validate_external_solution(value, external_solution)
        set_phase('reset_seed')
        solution = value.get('solution')
        if solution is not None:
            self.binding.validate_external_solution(value, solution)
        return artifact, seed, solution


def legacy_position_physical_observation_binding(env):
    """Compatibility projection for selected callers that still publish V1 state."""
    return (env.position_scene, env.position_joint_bindings,
            env.position_frame_bindings, env._position_requirements())


def position_input_kind(binding, value):
    """Ask the task binding to classify a versioned Position input, if present."""
    if value is None:
        return None
    classify = getattr(binding, 'classify_position_input', None)
    if not callable(classify):
        raise TypeError('versioned Position value requires its task-owned input classifier')
    kind = classify(value)
    if kind not in {'f04', 'f05_native', 'dg02_geophys', 'dg04_isaac_native'}:
        raise ValueError('versioned Position input classifier returned an unsupported kind')
    return kind


def resolve_reset_execution(binding, value, declared, *, seed, provider, backend):
    """Keep rebuilt task execution bound to its declared route and reset seed."""
    from ..artifacts import ExecutionSpec, ExecutionSpecV1
    from ..runtime.sessions.api import PROFILE

    versioned = value.get('execution_spec_v1')
    if versioned is None:
        if declared is not None:
            raise ValueError('SelectedReferenceEnv rebuild dropped its declared ExecutionSpecV1')
        return ExecutionSpec(provider, PROFILE, 'none', backend, 0, 'strict')
    if type(versioned) is not ExecutionSpecV1 or declared is None:
        raise ValueError('SelectedReferenceEnv rebuild changed its declared ExecutionSpecV1')
    select_runtime_input = getattr(binding, 'reset_runtime_input', None)
    runtime_input = select_runtime_input(value) if select_runtime_input else None
    if runtime_input is not None:
        if ((versioned.physics_provider, versioned.physics_backend,
             versioned.physics_device, versioned.physics_profile,
             versioned.determinism_mode, versioned.render_default,
             versioned.camera_overrides, versioned.provider_seed)
                != (declared.physics_provider, declared.physics_backend,
                    declared.physics_device, declared.physics_profile,
                    declared.determinism_mode, declared.render_default,
                    declared.camera_overrides, seed)
                or runtime_input.reset_plan.reset_sample.task_seed != seed):
            raise ValueError('seeded rebuild changed its exact route or requested seed')
    elif versioned.identity_hash != declared.identity_hash:
        raise ValueError('SelectedReferenceEnv rebuild changed its declared ExecutionSpecV1')
    return versioned


def selected_episode_reset_plan(value):
    """Resolve a declared reset capability independently of Controller type."""
    from ..artifacts.execution import EpisodeResetPlanV1, ResetPlanV1

    plan = value.get('reset_plan')
    if plan is None:
        return None
    if type(plan) not in (EpisodeResetPlanV1, ResetPlanV1):
        raise TypeError('selected reset plan must be an admitted reset contract')
    plan.validate()
    return plan


def prepare_selected_reset(binding, *, seed, seed_unset, options, mixed,
                           has_session, previous_sample, artifact, value, requires_reset_plan=False):
    """Validate reset inputs and resolve a task-bound sample before runtime changes."""
    mixed_plan = None
    if mixed:
        if options is None:
            options = {}
        if not isinstance(options, Mapping) or any(type(key) is not str for key in options):
            raise TypeError('mixed-control reset options must be a string-keyed mapping')
        if 'reset_plan_v1' in options:
            from ..artifacts import ResetPlanV1
            mixed_plan = options['reset_plan_v1']
            if type(mixed_plan) is not ResetPlanV1:
                raise TypeError('mixed-control reset_plan_v1 must be the public ResetPlanV1 contract')
            mixed_plan.validate()
            sample = mixed_plan.reset_sample
            if (sample.task_artifact_hash != artifact.identity_hash
                    or sample.source_id != value['source'].scene_source.source_id
                    or sample.source_closure_digest != value['source'].source_closure_digest):
                raise ValueError('ResetPlanV1 Artifact/source identity differs from this selected candidate')
            if seed is seed_unset:
                seed = sample.task_seed
            elif type(seed) is not int or seed != sample.task_seed:
                raise ValueError('ResetPlanV1 seed differs from reset seed')
    elif options:
        raise ValueError('selected reference reset options are not supported')
    declared_plan = None if mixed else selected_episode_reset_plan(value)
    if requires_reset_plan and declared_plan is None:
        raise ValueError('selected Controller capability requires a declared reset plan')
    if seed is seed_unset:
        if mixed and mixed_plan is not None:
            seed = mixed_plan.reset_sample.task_seed
        elif mixed and has_session:
            seed = previous_sample.task_seed
        elif declared_plan is not None:
            seed = declared_plan.reset_sample.task_seed
        else:
            seed = 19
    if declared_plan is not None:
        seed = binding.reset_seed(seed)
        if binding.build_seeded is None and seed != declared_plan.reset_sample.task_seed:
            raise ValueError('selected reset seed must match its fixed EpisodeResetPlan')
    if not mixed and declared_plan is None:
        # Task seed validation is pure preflight and must not close a live session.
        seed = binding.reset_seed(seed)
    mixed_sample = None
    if mixed:
        seed = binding.reset_seed(seed)
        mixed_sample = binding.reset_sample_with_options(artifact, seed, options, value['source'])
        from ..artifacts import ResetSampleV1
        if type(mixed_sample) is not ResetSampleV1:
            raise TypeError('mixed-control reset binding must return ResetSampleV1')
        if (mixed_sample.task_artifact_hash != artifact.identity_hash
                or mixed_sample.source_id != value['source'].scene_source.source_id
                or mixed_sample.source_closure_digest != value['source'].source_closure_digest
                or mixed_sample.task_seed != seed):
            raise ValueError('mixed-control reset sample differs from its selected source or seed')
    return seed, options, mixed_plan, mixed_sample


def resolve_selected_reset_effect(binding, value, artifact, seed, *, mixed, mixed_plan, mixed_sample):
    """Resolve the rebuilt task's sample and the one provider reset operation."""
    if mixed:
        return mixed_sample, mixed_plan
    plan = selected_episode_reset_plan(value)
    if plan is not None:
        if plan.reset_sample.task_seed != seed:
            raise ValueError('rebuilt reset plan seed differs from the prepared reset')
        if plan.reset_sample.task_artifact_hash != artifact.identity_hash:
            raise ValueError('rebuilt reset plan Artifact differs from the selected Artifact')
        return plan.reset_sample, plan
    return binding.reset_sample(artifact, seed), None


def execute_selected_reset_effect(session, sample, plan):
    """Execute exactly the selected source-bound reset through its session owner."""
    return session.reset(sample) if plan is None else session.reset_plan(plan)


def validate_initial_state_publication(session, publication, state):
    """Check the common initial boundary for every retained typed projection."""
    import math
    from ..artifacts.state import CanonicalStatePublicationV1, CanonicalStatePublicationV2

    if type(publication) not in (CanonicalStatePublicationV1, CanonicalStatePublicationV2):
        raise TypeError('initial state requires a typed publication')
    publication.validate()
    boundary = publication.view.boundary
    clock = publication.view.sample_clock
    if (not publication.lifetime.may_be_retained
            or boundary != session.state_boundary_identity()
            or boundary.control_step != 0
            or getattr(state, 'control_step', None) != boundary.control_step
            or not math.isclose(float(state.simulation_time), float(clock.simulation_time_s),
                                rel_tol=0, abs_tol=1e-9)):
        raise ValueError('typed initial state differs from the realized session boundary or clock')
    return publication


def observe_task_definition(env, state):
    """Project public Runtime state into the existing TaskDefinition lifecycle."""
    snapshot = env.binding.task_state_projection(state)
    lifecycle = env._task_lifecycle
    evaluation = (lifecycle.reset_task(state=snapshot) if state.control_step == 0
                  else lifecycle.evaluate_task(state=snapshot, action=env.controller.last_action,
                                               elapsed_steps=state.control_step))
    observation = env._task_definition.build_observation(snapshot)
    return observation, {
        'is_success': evaluation.success, 'task_failure': evaluation.failure,
        'task_metrics': dict(evaluation.metrics), 'reward_terms': dict(evaluation.reward_terms),
        'task_reward': evaluation.reward, 'elapsed_steps': state.control_step,
        'simulation_time_s': state.simulation_time,
        'external_action': env.controller.last_action.copy(),
        'universal_action': env.controller.last_action.copy(),
        'success_definition': env.config.task.success_definition,
        'observation_schema': env.binding.task_observation_schema,
    }, evaluation


@dataclass(frozen=True)
class ReferenceTaskBinding:
    """Internal task-to-reference adapter; not a new public task protocol."""

    build: Callable
    reset_sample: Callable
    evaluate: Callable
    object_poses: tuple[tuple[str, str], ...]
    external_actions: bool
    interval_mode: str
    recorder_mode: str
    external_action_error: str = 'selected reference route does not admit external actions'
    reset_seed: Callable = _identity_seed
    reset_expert_kwargs: Callable = _no_reset_kwargs
    observe_expert_kwargs: Callable = _no_observe_kwargs
    schedule_factory: Callable | None = None
    capture_guard_samples: bool = False
    record_native_substeps: bool = False
    abort_solution_on_runtime_error: bool = False
    native_sample_factory: Callable | None = None
    native_interval_receipt_factory: Callable | None = None
    control_request_required: bool = False
    external_solution_actions: bool = False
    expert_uses_public_observation: bool = False
    build_external: Callable | None = None
    validate_external_solution: Callable | None = None
    runtime_episode_identity: bool = False
    build_seeded: Callable | None = None
    build_sampled: Callable | None = None
    task_reset_sampler: Callable | None = None
    task_reset_metadata: Callable | None = None
    task_definition_factory: Callable | None = None
    task_state_projection: Callable | None = None
    task_observation_schema: object | None = None
    external_action_contract: object | None = None
    observation_metadata: dict | None = None
    build_native_feedback_profile: Callable | None = None
    admit_native_feedback_profile: Callable | None = None
    build_mixed_control_profile: Callable | None = None
    reset_sample_with_options: Callable | None = None
    prepare_mixed_control: Callable | None = None
    prepare_mixed_control_substep: Callable | None = None
    observe_mixed_control: Callable | None = None
    mixed_record_metadata: Callable | None = None
    pre_reset_session_validator: Callable | None = None
    post_reset_session_validator: Callable | None = None
    close_task_resources: Callable | None = None
    action_schema: dict | None = None
    scalar_control_binding: object | None = None
    action_space_factory: Callable | None = None
    prepare_action: Callable | None = None
    observation_space_factory: Callable | None = None
    observation_projection: Callable | None = None
    position_execution_info: Callable | None = None
    position_execution_info_key: str | None = None
    legacy_position_expert_admission: Callable | None = None
    reset_runtime_input: Callable | None = None
    position_control_binding: Callable | None = None
    physical_control_profile: Callable | None = None
    physical_observation_binding: Callable | None = None
    physical_sequence_v2_observation: bool = False
    position_physical_mixed: bool = False
    physical_reset_action_schema: Callable | None = None
    physical_reset_selection_factory: Callable | None = None
    physical_action_observer: Callable | None = None
    task_com_wrench_factory: Callable | None = None
    physical_direct_effort_feedback: bool = False
    physical_terminate_on_success: bool = False
    physical_ignore_done: bool = False
    classify_position_input: Callable | None = None
    diagnostic_profile: str | None = None
    build_receives_binding: bool = False

    def __post_init__(self):
        sampling = (self.build_sampled, self.task_reset_sampler, self.task_reset_metadata)
        if any(value is not None for value in sampling) and not all(map(callable, sampling)):
            raise ValueError('sampled reset requires construction, RNG sampler and metadata projection')
        semantics = (self.task_definition_factory, self.task_state_projection)
        if any(value is not None for value in semantics) and (
                not all(map(callable, semantics)) or self.task_observation_schema is None):
            raise ValueError('TaskDefinition requires construction, state projection and observation schema')
        if self.task_com_wrench_factory is not None and not callable(self.task_com_wrench_factory):
            raise TypeError('Task COM wrench factory must be callable')
        if type(self.physical_direct_effort_feedback) is not bool:
            raise TypeError('direct effort feedback selection must be a boolean')
        if type(self.physical_terminate_on_success) is not bool:
            raise TypeError('physical termination policy must be a boolean')
        if type(self.physical_ignore_done) is not bool:
            raise TypeError('physical ignore_done policy must be a boolean')
        if type(self.build_receives_binding) is not bool:
            raise TypeError('build_receives_binding must be a boolean')
        if self.build_mixed_control_profile is None and (
                not callable(self.action_space_factory) or not callable(self.prepare_action)
                or not isinstance(self.action_schema, dict) or not self.action_schema):
            raise TypeError('selected action schema, space and preparation must be explicitly declared')
        if self.build_mixed_control_profile is not None and (
                self.action_space_factory is not None or self.prepare_action is not None
                or self.action_schema is not None):
            raise ValueError('mixed-control action contract is supplied by its task construction')
        if self.build_mixed_control_profile is None and (
                not callable(self.observation_space_factory) or not callable(self.observation_projection)):
            raise TypeError('selected observation space and projection must be explicitly declared')
        if self.build_mixed_control_profile is not None and (
                self.observation_space_factory is not None or self.observation_projection is not None):
            raise ValueError('mixed-control observation contract is supplied by its task construction')
        if self.action_schema is not None and not isinstance(self.action_schema, dict):
            raise TypeError('selected task action schema must be a dictionary')
        if self.interval_mode not in {"grouped", "native"}:
            raise ValueError("unknown selected control-interval requirement")
        if self.recorder_mode not in {"canonical", "execution"}:
            raise ValueError("unknown selected recording requirement")
        if ((self.position_execution_info is None) != (self.position_execution_info_key is None)
                or (self.position_execution_info is not None
                    and (not callable(self.position_execution_info)
                         or not isinstance(self.position_execution_info_key, str)
                         or not self.position_execution_info_key))):
            raise ValueError('position execution info requires a callable and nonempty result key')
        if (self.build_external is None) != (self.validate_external_solution is None):
            raise ValueError('external Solution construction and validation must be supplied together')
        if ((self.build_native_feedback_profile is None) != (self.admit_native_feedback_profile is None)
                or (self.build_native_feedback_profile is not None
                    and (not callable(self.build_native_feedback_profile)
                         or not callable(self.admit_native_feedback_profile)))):
            raise ValueError('native feedback construction and admission must be supplied together')
        if (self.native_sample_factory is None) != (self.native_interval_receipt_factory is None):
            raise ValueError('native sample and interval receipt factories must be supplied together')
        if self.reset_runtime_input is not None and not callable(self.reset_runtime_input):
            raise ValueError('reset runtime input selector must be callable when supplied')
        if self.position_control_binding is not None and not callable(self.position_control_binding):
            raise ValueError('position control binding selector must be callable when supplied')
        if self.physical_control_profile is not None and not callable(self.physical_control_profile):
            raise ValueError('physical control profile selector must be callable when supplied')
        if type(self.position_physical_mixed) is not bool:
            raise TypeError('Position/physical mixed capability must be bool')
        if type(self.physical_sequence_v2_observation) is not bool:
            raise TypeError('physical sequence V2 observation capability must be bool')
        if self.physical_observation_binding is not None and not callable(self.physical_observation_binding):
            raise ValueError('physical observation binding must be callable when supplied')
        if self.physical_reset_action_schema is not None and not callable(self.physical_reset_action_schema):
            raise ValueError('physical reset action schema must be callable when supplied')
        if self.physical_reset_selection_factory is not None and not callable(self.physical_reset_selection_factory):
            raise ValueError('physical reset selection must be constructed by its declared owner')
        if self.physical_action_observer is not None and not callable(self.physical_action_observer):
            raise ValueError('physical action observer must be callable when supplied')
        if (self.legacy_position_expert_admission is not None
                and not callable(self.legacy_position_expert_admission)):
            raise ValueError('legacy Position expert admission must be callable when supplied')
        if self.classify_position_input is not None and not callable(self.classify_position_input):
            raise ValueError('position input classifier must be callable when supplied')
        if self.diagnostic_profile is not None and (
                type(self.diagnostic_profile) is not str or not self.diagnostic_profile):
            raise ValueError('diagnostic profile must be a nonempty explicit identifier')
        if self.close_task_resources is not None and not callable(self.close_task_resources):
            raise ValueError('task resource cleanup hook must be callable when supplied')
        if self.control_request_required and self.native_sample_factory is None:
            raise ValueError('native controller requests require the selected native sample contract')
        if self.external_solution_actions and not self.external_actions and not self.control_request_required:
            raise ValueError('caller-driven guarded Solution actions require the native control request contract')
        mixed_hooks = (
            self.build_mixed_control_profile, self.reset_sample_with_options,
            self.prepare_mixed_control, self.observe_mixed_control,
            self.mixed_record_metadata, self.pre_reset_session_validator,
        )
        if any(value is not None for value in mixed_hooks) and any(
            not callable(value) for value in mixed_hooks
        ):
            raise ValueError('mixed-control binding requires its complete task-owned hook set')
        if (self.prepare_mixed_control_substep is not None
                and not callable(self.prepare_mixed_control_substep)):
            raise ValueError('mixed-control substep preparation hook must be callable when supplied')
        if (self.post_reset_session_validator is not None
                and not callable(self.post_reset_session_validator)):
            raise ValueError('post-reset session validator must be callable when supplied')

    @classmethod
    def from_provider_free_compiler(cls, compiler, *, task_id, construction_schema,
                                    metadata=None, **binding_fields):
        """Bind a provider-free task compiler to the existing selected environment.

        The task still supplies its action, observation, reset, evaluation and
        control bindings explicitly. The compiler's own source is recorded.
        """
        if not callable(compiler):
            raise TypeError('selected task compiler must be callable')
        if 'build' in binding_fields or 'build_receives_binding' in binding_fields:
            raise ValueError('compiled binding owns its build callback')
        metadata = None if metadata is None else dict(metadata)

        def build(_provider, binding):
            from ..assembly.compiler import reference_construction_value
            return reference_construction_value(
                compiler(), task_id=task_id, construction_schema=construction_schema,
                owners=(compiler,), binding=binding, metadata=metadata,
            )

        return cls(build=build, build_receives_binding=True, **binding_fields)

    def reset_reconstruction_strategy(self, provider, backend, horizon, *, mixed=False, native_request=None):
        """Select task-owned reconstruction once when a configuration is admitted."""
        if mixed and native_request is not None:
            raise ValueError('mixed and native-feedback reconstruction are mutually exclusive')
        if mixed:
            if not callable(self.build_mixed_control_profile):
                raise ValueError('mixed-control candidate requires its task reconstruction binding')
            return _MixedResetReconstruction(self, provider, backend, horizon)
        if native_request is not None:
            return _NativeFeedbackResetReconstruction(self, provider, backend, horizon, native_request)
        return _StandardResetReconstruction(self, provider, backend, horizon)

    def build_for_provider(self, provider):
        """Build with this binding when the construction owner opts into it."""
        if self.build_receives_binding:
            return self.build(provider, self)
        return self.build(provider)
