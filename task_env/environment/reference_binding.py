"""Internal binding between selected task semantics and the environment."""

from dataclasses import dataclass, replace
from collections.abc import Mapping
from typing import Callable, NamedTuple


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


@dataclass(frozen=True)
class TaskBuildRequest:
    """Inputs to every task construction and reset reconstruction callback."""
    provider: str
    backend: str
    seed: int
    horizon: int
    sampled_reset: object
    binding: object


class SourceBoundTaskBuilder:
    """Construct a source and Controller, then derive each episode's reset plan.

    Source stages pass ``(CompiledReferenceTaskV1, task_context)``. Controller
    options consume that pair; ``compile_control`` receives the selection as a
    separate argument and returns the Env's construction mapping. Only this
    finished mapping is cached. Task context never enters the Runtime value.
    """

    def __init__(self, compile_source, reset_plan, *, backend, reuse_source=False,
                 allow_sampled_reset=True, compile_control=None,
                 controller_factory=None, controller_options=None, source_composer=None):
        self.compile_source, self.reset_plan = compile_source, reset_plan
        self.compile_control = compile_control
        if (controller_factory is None) != (controller_options is None):
            raise ValueError('Controller factory and options must be supplied together')
        self.controller_factory, self.controller_options = controller_factory, controller_options
        self.source_composer = source_composer
        self.backend, self.reuse_source = backend, reuse_source
        self.allow_sampled_reset = allow_sampled_reset
        self._cached = self._route = None

    def __call__(self, request):
        if request.backend != self.backend:
            raise ValueError('requested backend differs from resolved configuration')
        if request.sampled_reset is not None and not self.allow_sampled_reset:
            raise ValueError('task does not accept an externally sampled reset')
        route = (request.provider, request.backend)
        if self._cached is not None and route != self._route:
            raise ValueError('reused task source differs from the requested provider/backend')
        fresh = self._cached is None
        if fresh:
            compiled, context = self.compile_source(request)
        else:
            value = self._cached
            from ..runtime.sessions.source import source_resource_receipt
            source = value.get('source')
            receipt = source_resource_receipt(source)
            if receipt is not None:
                receipt.validate_snapshot()
            else:
                assert_fresh = getattr(getattr(source, 'scene_source', None), 'assert_fresh', None)
                if callable(assert_fresh):
                    assert_fresh()
        try:
            if fresh:
                assert_fresh = getattr(getattr(compiled.source, 'scene_source', None), 'assert_fresh', None)
                if callable(assert_fresh):
                    assert_fresh()
            if fresh and self.source_composer is not None:
                compiled, context = self.source_composer(compiled, context, request)
            if fresh:
                selection = None
                if self.controller_factory is not None:
                    options = self.controller_options(compiled, context, request)
                    selection = self.controller_factory(compiled.artifact, compiled.source, **options)
                value = (self.compile_control(compiled, context, selection, request)
                         if self.compile_control is not None
                         else {'artifact': compiled.artifact, 'source': compiled.source})
            plan = self.reset_plan(value, request) if self.reset_plan is not None else None
        except BaseException as error:
            if fresh:
                from ..runtime.sessions.source import source_resource_receipt
                receipt = source_resource_receipt(compiled.source)
                if receipt is not None:
                    try:
                        receipt.close()
                    except BaseException as cleanup_error:
                        error.add_note(f'task source cleanup also failed: {cleanup_error!r}')
            raise
        if self.reuse_source and fresh:
            self._cached, self._route = value, route
        return value if self.reset_plan is None else {**value, 'reset_plan': plan}


class _StandardResetReconstruction:
    """Rebuild one task through its binding and manage source replacement."""
    def __init__(self, binding, provider, backend, horizon):
        self.binding, self.provider, self.backend, self.horizon = binding, provider, backend, horizon
        self.sampled_reset = None

    def build_switch_candidate(self, seed):
        return self._build(seed, None)

    def initial(self, *, seed=31):
        return self._build(seed, None)

    def build_reset(self, current, seed, external_solution):
        sampled = None if external_solution is not None else self.sampled_reset
        return self._build(seed, sampled)

    def _build(self, seed, sampled):
        return self.binding.build_for_request(self.provider, self.backend, seed,
                                              self.horizon, sampled)

    def use_binding(self, binding):
        """Use the Env's currently admitted task binding without changing policy."""
        self.binding = binding

    def reconstruct(self, current, artifact, seed, external_solution, artifact_for_reset, *,
                    verify_source, set_phase=lambda _phase: None, prepared=None):
        value = prepared if prepared is not None else self.build_reset(current, seed, external_solution)
        from ..runtime.sessions.source import source_resource_receipt
        old_receipt = source_resource_receipt(current.get('source'))
        receipt = source_resource_receipt(value.get('source'))
        try:
            verify_source(value)
            selector = self.binding.reset_runtime_input
            runtime_input = selector(value) if selector else None
            artifact = artifact_for_reset(artifact, value, runtime_input)
            if external_solution is not None:
                self.binding.validate_external_solution(value, external_solution)
            solution = value.get('solution')
            set_phase('reset_seed')
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


def _compose_robot_source(binding, value):
    """Attach the declared Robot source as part of the task build."""
    compose = binding.compose_robot_source
    if compose is None:
        return value
    source = value['source']
    try:
        adapted = compose(source, artifact=value['artifact'], controller=value['controller'])
        from ..assembly.compiler import reference_task_identity_fields
        from ..controllers.canonical.contracts import digest
        result = dict(value)
        result['source'] = adapted
        resolved = dict(value['resolved_configuration'])
        resolved.update(reference_task_identity_fields(value['artifact'], adapted, value['controller']))
        composition = adapted.composition_runtime_input
        reference = adapted.source_reference_plan
        resolved['source_composition_plan_sha256'] = (composition.plan.identity_hash if composition
                                                     else reference.identity_hash)
        if adapted.source_composition_request is not None:
            resolved['source_composition_request_v2_sha256'] = adapted.source_composition_request.identity_hash
        if adapted.source_composition_intent is not None:
            resolved['source_composition_intent_v1_sha256'] = adapted.source_composition_intent.identity_hash
        result['resolved_configuration'] = resolved
        result['recipe_identity'] = digest(resolved)
        return result
    except BaseException as error:
        from ..runtime.sessions.source import source_resource_receipt
        receipt = source_resource_receipt(source)
        if receipt is not None:
            try:
                receipt.close()
            except BaseException as cleanup_error:
                error.add_note(f'Robot source cleanup also failed: {cleanup_error!r}')
        raise


def legacy_position_physical_observation_binding(env):
    """Compatibility projection for selected callers that still publish V1 state."""
    return (env.position_scene, env.position_joint_bindings,
            env.position_frame_bindings, env._position_requirements())


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


def prepare_selected_reset(binding, *, seed, seed_unset, options, value, requires_reset_plan=False):
    """Validate reset inputs before changing the live RuntimeSession."""
    if options:
        raise ValueError('selected reference reset options are not supported')
    plan = selected_episode_reset_plan(value)
    if requires_reset_plan and plan is None:
        raise ValueError('selected Controller capability requires a declared reset plan')
    if seed is seed_unset:
        seed = plan.reset_sample.task_seed if plan is not None else 19
    seed = binding.reset_seed(seed)
    return seed


def resolve_selected_reset_effect(binding, value, artifact, seed):
    """Resolve the rebuilt task sample and its provider reset operation."""
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


def selected_task_reset_identity(env):
    """Resolve task identity at binding time, including typed construction."""
    task = getattr(getattr(env, 'config', None), 'task', None)
    uid, success = getattr(task, 'task_uid', None), getattr(task, 'success_definition', None)
    if uid and success:
        if type(success) is not str:
            raise ValueError('selected reset cannot resolve its task success definition')
        return uid, success
    configuration = env.value.get('resolved_configuration', {})
    configuration = configuration if isinstance(configuration, Mapping) else {}
    task_recipe = configuration.get('task_recipe', {})
    recipe = task_recipe.get('recipe', {}) if isinstance(task_recipe, Mapping) else {}
    recipe = recipe if isinstance(recipe, Mapping) else {}
    source = env.value.get('task_source')
    uid = (getattr(task, 'task_uid', None) or getattr(source, 'task_id', None)
           or recipe.get('task_uid') or getattr(env.artifact, 'task_id', None) or env.uid)
    success = (getattr(task, 'success_definition', None) or recipe.get('success_definition')
               or getattr(getattr(env.artifact, 'semantics', None), 'success_definition', None))
    if type(success) is not str or not success:
        raise ValueError('selected reset cannot resolve its task success definition')
    return uid, success


def evaluate_task_definition(env, state, *, action=None, task_state=None):
    """Evaluate a declared TaskDefinition through the common semantic lifecycle."""
    if env.binding.task_definition_factory is None:
        return env.binding.evaluate(state, env.artifact.semantics)
    snapshot = env.binding.task_state_projection(state) if task_state is None else task_state
    lifecycle = env._task_lifecycle
    return (lifecycle.reset_task(state=snapshot) if state.control_step == 0
            else lifecycle.evaluate_task(state=snapshot, action=action, elapsed_steps=state.control_step))


def observe_task_definition(env, state):
    """Project public Runtime state into the existing TaskDefinition lifecycle."""
    snapshot = env.binding.task_state_projection(state)
    evaluation = evaluate_task_definition(env, state, action=env.controller.last_action, task_state=snapshot)
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
    validate_external_solution: Callable | None = None
    runtime_episode_identity: bool = False
    task_reset_sampler: Callable | None = None
    task_reset_metadata: Callable | None = None
    prepare_reset_switch: Callable | None = None
    task_definition_factory: Callable | None = None
    task_state_projection: Callable | None = None
    task_observation_schema: object | None = None
    external_action_contract: object | None = None
    observation_metadata: dict | None = None
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
    reset_runtime_input: Callable | None = None
    position_control_binding: Callable | None = None
    physical_observation_binding: Callable | None = None
    physical_sequence_v2_observation: bool = False
    position_physical_mixed: bool = False
    physical_reset_capability: object | None = None
    physical_action_observer: Callable | None = None
    task_com_wrench_factory: Callable | None = None
    physical_direct_effort_feedback: bool = False
    physical_terminate_on_success: bool = False
    physical_ignore_done: bool = False
    compose_robot_source: Callable | None = None
    robot: object | None = None

    def __post_init__(self):
        if self.compose_robot_source is not None and not callable(self.compose_robot_source):
            raise TypeError('Robot source composer must be callable')
        sampling = (self.task_reset_sampler, self.task_reset_metadata)
        if any(value is not None for value in sampling) and not all(map(callable, sampling)):
            raise ValueError('sampled reset requires construction, RNG sampler and metadata projection')
        semantics = (self.task_definition_factory, self.task_state_projection)
        if any(value is not None for value in semantics) and not all(map(callable, semantics)):
            raise ValueError('TaskDefinition requires construction and state projection')
        if self.task_com_wrench_factory is not None and not callable(self.task_com_wrench_factory):
            raise TypeError('Task COM wrench factory must be callable')
        if type(self.physical_direct_effort_feedback) is not bool:
            raise TypeError('direct effort feedback selection must be a boolean')
        if type(self.physical_terminate_on_success) is not bool:
            raise TypeError('physical termination policy must be a boolean')
        if type(self.physical_ignore_done) is not bool:
            raise TypeError('physical ignore_done policy must be a boolean')
        compiled_physical_action = self.action_space_factory is None and (
            self.action_schema is None or self.external_action_contract is not None)
        if (not callable(self.prepare_action) or (not compiled_physical_action and (
                not callable(self.action_space_factory)
                or not isinstance(self.action_schema, dict) or not self.action_schema))):
            raise TypeError('selected action schema, space and preparation must be explicitly declared')
        if not callable(self.observation_space_factory) or not callable(self.observation_projection):
            raise TypeError('selected observation space and projection must be explicitly declared')
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
        if self.validate_external_solution is not None and not callable(self.validate_external_solution):
            raise TypeError('external Solution validation must be callable')
        if (self.native_sample_factory is None) != (self.native_interval_receipt_factory is None):
            raise ValueError('native sample and interval receipt factories must be supplied together')
        if self.reset_runtime_input is not None and not callable(self.reset_runtime_input):
            raise ValueError('reset runtime input selector must be callable when supplied')
        if self.position_control_binding is not None and not callable(self.position_control_binding):
            raise ValueError('position control binding selector must be callable when supplied')
        if type(self.position_physical_mixed) is not bool:
            raise TypeError('Position/physical mixed capability must be bool')
        if type(self.physical_sequence_v2_observation) is not bool:
            raise TypeError('physical sequence V2 observation capability must be bool')
        if self.physical_observation_binding is not None and not callable(self.physical_observation_binding):
            raise ValueError('physical observation binding must be callable when supplied')
        if self.physical_reset_capability is not None:
            from ..controllers.canonical.reset_selection import PhysicalResetCapability
            if type(self.physical_reset_capability) is not PhysicalResetCapability:
                raise TypeError('physical reset requires a Controller capability')
        if self.physical_action_observer is not None and not callable(self.physical_action_observer):
            raise ValueError('physical action observer must be callable when supplied')
        if self.close_task_resources is not None and not callable(self.close_task_resources):
            raise ValueError('task resource cleanup hook must be callable when supplied')
        if self.control_request_required and self.native_sample_factory is None:
            raise ValueError('native controller requests require the selected native sample contract')
        if self.external_solution_actions and not self.external_actions and not self.control_request_required:
            raise ValueError('caller-driven guarded Solution actions require the native control request contract')
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
        if 'build' in binding_fields:
            raise ValueError('compiled binding owns its build callback')
        metadata = None if metadata is None else dict(metadata)

        def build(request):
            if request.sampled_reset is not None:
                raise ValueError('provider-free compiler does not accept sampled reset input')
            from ..assembly.compiler import reference_construction_value
            return reference_construction_value(
                compiler(), task_id=task_id, construction_schema=construction_schema,
                owners=(compiler,), binding=request.binding, metadata=metadata,
            )

        return cls(build=build, **binding_fields)

    def reset_reconstruction_strategy(self, provider, backend, horizon):
        """Select task-owned reconstruction once when a configuration is admitted."""
        return _StandardResetReconstruction(self, provider, backend, horizon)

    def build_for_request(self, provider, backend, seed, horizon, sampled=None):
        """Build from one explicit Task/Robot/Runtime request."""
        value = self.build(TaskBuildRequest(provider, backend, seed, horizon, sampled, self))
        execution = value.get('physical_execution')
        profile = getattr(execution, 'selection_profile_id', None)
        if profile is not None:
            declared = value.get('selected_controller_profile_id', profile)
            if declared != profile:
                raise ValueError('selected Controller profile differs from its execution')
            value = {**value, 'selected_controller_profile_id': profile}
        return _compose_robot_source(self, value)

    def bind_compiled_control(self, value):
        """Bind the physical action contract to the Controllers actually compiled.

        Explicit task action contracts keep their owners. Physical contracts can
        be resolved after source compile.
        """
        physical = value.get('physical_execution')
        declared = self.action_schema
        if self.external_action_contract is not None:
            from ..runtime.sessions.physical_control import PhysicalControlExecutionV1
            from gymnasium.spaces import Box, Dict
            import numpy as np

            if type(physical) is not PhysicalControlExecutionV1 or len(physical.controllers) != 1:
                raise ValueError('declared Robot action requires one compiled physical Controller')
            space = physical.action_space()
            contract = self.external_action_contract
            if not isinstance(space, Dict) or len(space.spaces) != 1:
                raise ValueError('compiled Controller action tree differs from its declared action')
            component = next(iter(space.spaces.values()))
            if (not isinstance(component, Box) or component.shape != (contract.dimension,)
                    or not np.array_equal(component.low, np.full(component.shape, contract.low, dtype=component.dtype))
                    or not np.array_equal(component.high, np.full(component.shape, contract.high, dtype=component.dtype))
                    or any(channel.unit != contract.unit for channel in physical.compiled.binding.channels)):
                raise ValueError('compiled Controller action bounds or units differ from its declared action')
            return replace(self, action_space_factory=physical.action_space)
        if declared is not None and declared.get('schema_version') != 'physical-control-actions-v1':
            return self
        if physical is None:
            if declared is None:
                raise ValueError('compiled physical action contract requires its execution')
            return self
        from ..runtime.sessions.physical_control import PhysicalControlExecutionV1
        if type(physical) is not PhysicalControlExecutionV1:
            raise TypeError('compiled physical action contract requires PhysicalControlExecutionV1')
        schema = {**(declared or {}), **physical.action_schema()}
        if schema == declared and getattr(self.action_space_factory, '__self__', None) is physical:
            return self
        return replace(self, action_schema=schema, action_space_factory=physical.action_space)


class _ExistingSubjectSource(NamedTuple):
    scene: object
    task_source: object
    execution_spec: object
    closure: str
    subject: object
    declarations: tuple


@dataclass(frozen=True)
class ExistingSubjectEffortTask:
    """Task declarations consumed by the shared existing-subject construction path."""
    robot: object
    compile_declaration: Callable
    reset_plan: Callable
    composition: object
    construction_id: str
    source_revision: str
    reset_sampler: Callable
    reset_metadata: Callable
    definition_factory: Callable
    state_projection: Callable
    observation_schema: object
    observation_space_factory: Callable

    def bind(self, config, *, source_delivery_manifest=None):
        """Build one Task binding; native resource ownership stays with Runtime."""
        import hashlib
        from ..assembly.compiler import CompiledReferenceTaskV1
        from ..runtime.sessions.declared_effort_source import declared_effort_scene, compile_declared_effort_source
        from ..runtime.sessions.physical_control import build_existing_subject_effort
        from ..runtime.sessions.source_composition_adapters import (
            prepare_robot_source_intent, validate_effort_robot_intent)

        def compile_source(request):
            provider, seed = request.provider, request.seed
            robot = self.robot
            scene, delivery = declared_effort_scene(robot, provider=provider,
                                          source_delivery_manifest=source_delivery_manifest)
            task_source, artifact = self.compile_declaration(scene, robot)
            source, execution_spec, closure, subject, declarations = compile_declared_effort_source(
                robot=robot, scene=scene, artifact=artifact, task_source=task_source,
                composition=self.composition, config=config, provider=provider,
                source_delivery=delivery, seed=seed)
            return (CompiledReferenceTaskV1(artifact, source),
                    _ExistingSubjectSource(scene, task_source, execution_spec, closure, subject, declarations))

        def compile_control(compiled, context, _selection, request):
            robot, source, artifact = self.robot, compiled.source, compiled.artifact
            scene = context.scene
            profile_id = config.control.profile_id
            intent, _recipe = prepare_robot_source_intent(source, robot=robot,
                controller_profile=profile_id, existing_robot_entity=robot.uid,
                task_body_names=(), task_site_transfers=())
            physical = build_existing_subject_effort(robot, scene=scene, artifact=artifact,
                source=source, profile_id=profile_id, subject=context.subject,
                declarations=context.declarations)
            validate_effort_robot_intent(intent, source, physical, controller_profile=profile_id)
            return {'artifact': artifact, 'task_source': context.task_source, 'source': source,
                'construction_id': self.construction_id,
                'source_revision': scene.assets[0].source_revision or self.source_revision,
                'execution_spec_v1': context.execution_spec,
                'source_sha256': {'original': hashlib.sha256(robot.source_xml.encode()).hexdigest(),
                                  'projected_closure': context.closure},
                'controller': physical.controllers[0], 'solution': None,
                'physical_execution': physical, 'selected_controller_profile_id': profile_id,
                'resolved_configuration': {'physics_dt': artifact.timebase.physics_dt,
                    'control_substeps': artifact.timebase.control_substeps,
                    'source_composition_intent_v1_sha256': intent.identity_hash}}

        def reset_seed(seed):
            if type(seed) is not int or seed < 0:
                raise ValueError('seed must be a nonnegative integer')
            return seed

        action = self.robot.action_contract
        return ReferenceTaskBinding(
            build=SourceBoundTaskBuilder(compile_source,
                lambda value, request: self.reset_plan(value['artifact'], value['source'],
                                                       request.seed, request.sampled_reset),
                backend=config.runtime.backend, compile_control=compile_control),
            task_reset_sampler=self.reset_sampler, task_reset_metadata=self.reset_metadata,
            task_definition_factory=self.definition_factory, task_state_projection=self.state_projection,
            task_observation_schema=self.observation_schema, external_action_contract=action,
            reset_sample=lambda _artifact, _seed: None, evaluate=lambda _state, _semantics: None,
            object_poses=(), external_actions=True, interval_mode='grouped', recorder_mode='execution',
            reset_seed=reset_seed, action_schema={'schema_id': action.schema_id,
                'schema_version': action.schema_version, 'mode': action.mode,
                'components': list(action.components), 'low': action.low, 'high': action.high,
                'unit': action.unit},
            action_space_factory=None,
            prepare_action=lambda value: value, observation_space_factory=self.observation_space_factory,
            observation_projection=observe_task_definition,
            physical_direct_effort_feedback=(config.control.profile_id == 'direct_joint_effort_v1'),
            physical_terminate_on_success=True, physical_ignore_done=config.episode.ignore_done)
