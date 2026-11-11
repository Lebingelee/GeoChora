"""Construction capabilities supplied by admitted selected-control owners.

Each capability creates and binds the existing session route it owns. The
orchestrator only orders declared capabilities and composes initial state.
Provider admission and typed lowerers remain in their existing owners.
"""
from dataclasses import dataclass

from ...environment.types import StageUnavailableError
from .state_initialization import (
    LegacyFeedbackInitialState, PhysicalInitialState, PositionInitialState,
)


@dataclass(frozen=True)
class RuntimeBuildResult:
    initial_capabilities: tuple = ()
    skip_gravity: bool = False


def _worker(selection):
    return selection is not None and selection.deployment == 'isolated_worker'


@dataclass(frozen=True)
class PhysicalRuntimeBuilder:
    execution: object
    position_owner_present: bool = False
    selection_matches: tuple = ()

    @property
    def priority(self):
        return 20 if self.position_owner_present else 40

    @property
    def declaring_owner(self):
        return self.execution

    def create(self, env, selection, start_worker, materialize, _materialize_control):
        from .physical_control import PhysicalControlExecutionV1
        if (type(self.execution) is not PhysicalControlExecutionV1
                or env._physical_execution() is not self.execution):
            raise TypeError('physical construction requires its admitted execution and Task binding')
        if env.value.get('selected_controller_profile_id') is not None:
            if len(self.selection_matches) != 1:
                raise ValueError('physical construction requires one common Controller match result')
            match = self.selection_matches[0]
            from .control import _match_physical_execution
            if _match_physical_execution(env.value) != match:
                raise ValueError('physical Controller match changed after selection')
            expected_resources = tuple((channel.entity_id, channel.joint_id, writer)
                for controller in self.execution.controllers
                for channel in controller._channels for writer in (controller.writer_id,))
            if (match.control_kind != 'joint_effort'
                    or match.selection_profile_id != env.value['selected_controller_profile_id']
                    or match.artifact_identity_sha256 != env.artifact.identity_hash
                    or match.source_id != env.value['source'].source_id
                    or match.source_closure_sha256 != env.value['source'].source_closure_digest
                    or match.scene_identity_sha256 != self.execution.scene.identity_hash
                    or match.controller_identities != tuple(c.identity for c in self.execution.controllers)
                    or match.writer_ids != tuple(c.writer_id for c in self.execution.controllers)
                    or set(match.resource_keys) != set(expected_resources)):
                raise ValueError('physical construction Controller match differs from its selected execution')
            env._controller_selection_matches = self.selection_matches
        if _worker(selection):
            env.session = start_worker()
        else:
            options = {'_observer_render_request': getattr(env, '_observer_render_request', None),
                       '_session_admission_input': env.value.get('session_admission_input'),
                       '_task_render_requested': bool(getattr(env, 'render_mode', None) is not None
                                                      or getattr(env, '_task_rgb_config', None) is not None)}
            if getattr(env, '_legacy_observer_requested', False):
                options['_legacy_observer_requested'] = True
            if getattr(env, '_legacy_camera_observations', False):
                options['_legacy_camera_observations'] = True
            env.session = materialize(env.artifact, env.execution, source=env.value['source'], **options)
        return RuntimeBuildResult()


@dataclass(frozen=True)
class PositionRuntimeBuilder:
    capabilities: tuple
    selection_matches: tuple = ()
    selection_match_required: bool = False
    priority = 30

    @property
    def declaring_owner(self):
        return self.capabilities[0]

    def create(self, env, selection, start_worker, _materialize, materialize_control):
        from .control import prepare_position_control_materialization
        source = env.value['source']
        env.position_scene = source.scene_definition
        selector = env.binding.position_control_binding
        profiles = tuple(item.owner for item in self.capabilities)
        plan, joints, frames, position_binding = prepare_position_control_materialization(
            source=source, artifact=env.artifact, profiles=profiles,
            plan=env.value.get('controller_binding_plan'),
            select_binding=selector, value=env.value, capabilities=self.capabilities)
        if self.selection_match_required:
            if len(self.selection_matches) != 1:
                raise ValueError('Position materialization requires its common Controller match result')
            match = self.selection_matches[0]
            from .control import _match_position_profiles
            current_match = _match_position_profiles(
                env.value, tuple(item.owner for item in self.capabilities))
            if current_match != self.selection_matches:
                raise ValueError('Position Controller match changed after selection')
            if (match.control_kind != 'position'
                    or match.artifact_identity_sha256 != env.artifact.identity_hash
                    or match.source_id != source.source_id
                    or match.source_closure_sha256 != source.source_closure_digest
                    or match.scene_identity_sha256 != source.scene_definition.identity_hash
                    or match.writer_ids != tuple(item.writer_id for item in self.capabilities)
                    or match.controller_identities != tuple(item.owner.identity for item in self.capabilities)
                    or set(match.subject_ids) != {
                        subject.subject_id for subject in source.position_subject_plan.subjects}
                    or set(match.resource_keys) != set(plan.resource_writers)):
                raise ValueError('Position materialization differs from its Controller match result')
            env._controller_selection_matches = self.selection_matches
        env.position_plan, env.position_joint_bindings, env.position_frame_bindings = plan, joints, frames
        env._position_state_declaration = plan
        if _worker(selection):
            env.session = start_worker()
        else:
            env.session = materialize_control(env.artifact, env.execution, source=source,
                binding=position_binding, controller_binding_plan=plan, controller_profile=profiles,
                session_admission_input=env.value.get('session_admission_input'),
                observer_render_request=getattr(env, '_observer_render_request', None),
                task_render_requested=bool(
                    getattr(env, 'render_mode', None) is not None
                    or getattr(env, '_component_task_rgb', None) is not None
                ))
        env._materialized_position_control_binding = position_binding
        env._materialized_position_control_selector = selector
        initial = PositionInitialState(plan, env.position_scene, joints, frames,
                                       self.capabilities, plan)
        return RuntimeBuildResult((initial,))


@dataclass(frozen=True)
class ScalarRuntimeBuilder:
    binding: object
    priority = 10

    @property
    def declaring_owner(self):
        return self.binding

    def create(self, env, selection, start_worker, _materialize, materialize_control):
        from .control import ControlBinding
        env.position_profile = False
        if type(self.binding) is not ControlBinding:
            raise TypeError('selected scalar control requires its declared ControlBinding')
        if _worker(selection):
            env.session = start_worker()
            env.session._source, env.session._artifact = env.value['source'], env.artifact
            if (env.binding.interval_mode == 'native'
                    and getattr(env.value['source'], 'position_subject_binding', None) is None):
                from .legacy_native_feedback_binding import install_admitted_binding
                install_admitted_binding(env.session, source=env.value['source'],
                                         artifact=env.artifact, controller=env._selected_controller)
            return RuntimeBuildResult(skip_gravity=env._physical_execution() is None)
        env.session = materialize_control(env.artifact, env.execution, source=env.value['source'],
            binding=self.binding,
            selected_controller=(env._selected_controller if env.binding.interval_mode == 'native' else None))
        return RuntimeBuildResult()


def build_selected_runtime(env, selected, selection, start_worker, materialize, materialize_control):
    """Execute one admitted builder, then compose declared physical/state capabilities."""
    source = env.value['source']
    providers = (env._physical_execution(),
                 *selected.position_capabilities[:1], getattr(source, 'mixed_actuator_plan', None),
                 getattr(env.binding, 'scalar_control_binding', None))
    candidates = []
    for provider in providers:
        factory = getattr(provider, 'selected_runtime_builder', None)
        if callable(factory):
            candidate = factory(selected)
            if (getattr(candidate, 'declaring_owner', None) is not provider
                    or type(getattr(candidate, 'priority', None)) is not int
                    or not callable(getattr(candidate, 'create', None))):
                raise ValueError('runtime construction capability is foreign or invalid')
            candidates.append(candidate)
        elif provider is not None:
            raise TypeError('declared owner lacks its runtime construction capability')
    if not candidates:
        raise TypeError('selected binding exposes no runtime construction capability')
    priority = max(item.priority for item in candidates)
    builders = [item for item in candidates if item.priority == priority]
    if len(builders) != 1:
        raise ValueError('selected runtime has conflicting construction capabilities')
    result = builders[0].create(env, selection, start_worker, materialize, materialize_control)
    capabilities = list(result.initial_capabilities)
    execution = env._physical_execution()
    if execution is not None:
        declared = env.value.get('physical_execution')
        reset_selection = getattr(env, '_physical_reset_selection', None)
        if (declared is not None and execution is not declared
                and (reset_selection is None or declared is not reset_selection.declaration)):
            raise ValueError('physical execution changed after selected preflight')
        bind = getattr(env.session, 'bind_physical_control', None)
        if not callable(bind):
            raise StageUnavailableError('RuntimeSession does not expose a physical-control build port')
        bind(execution)
        capabilities.append(PhysicalInitialState(execution,
            getattr(env.binding, 'physical_observation_binding', None) is None,
            declared is execution))
    if not capabilities:
        capabilities.append(LegacyFeedbackInitialState(env._selected_controller))
    env._selected_state_capabilities = tuple(capabilities)
    env._selected_reset_stop_capability = any(getattr(item, 'supports_stop', False) for item in capabilities)
    return result
