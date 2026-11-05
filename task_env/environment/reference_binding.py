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


def prepare_selected_reset(binding, *, seed, seed_unset, options, mixed, position,
                           has_session, previous_sample, artifact, value):
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
    if seed is seed_unset:
        if mixed and mixed_plan is not None:
            seed = mixed_plan.reset_sample.task_seed
        elif mixed and has_session:
            seed = previous_sample.task_seed
        elif position:
            seed = value['reset_plan'].reset_sample.task_seed
        else:
            seed = 19
    if position:
        seed = binding.reset_seed(seed)
        reset_plan = value.get('reset_plan')
        if reset_plan is None:
            raise ValueError('PositionServoV1 selected route requires an EpisodeResetPlan')
        if binding.build_seeded is None and seed != reset_plan.reset_sample.task_seed:
            raise ValueError('PositionServoV1 reset seed must match its fixed EpisodeResetPlan')
    if not mixed and not position:
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
    classify_position_input: Callable | None = None
    diagnostic_profile: str | None = None
    build_receives_binding: bool = False

    def __post_init__(self):
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

    def build_for_provider(self, provider):
        """Build with this binding when the construction owner opts into it."""
        if self.build_receives_binding:
            return self.build(provider, self)
        return self.build(provider)
