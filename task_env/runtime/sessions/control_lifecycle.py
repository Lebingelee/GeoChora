"""Shared selected-control lifecycle dispatch for source-bound Controllers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlLifecycleDispatchV1:
    schema_version: str
    command_kind: str
    source_id: str
    source_closure_sha256: str
    artifact_sha256: str
    episode_id: str
    state_boundary_id: str
    control_step: int
    controller_generation: int
    controller_identities: tuple[str, ...]
    stage: str


def has_position_control_capability(env) -> bool:
    """Identify a compiled typed position capability without Env flags/Robot IDs."""
    return bool(getattr(env, 'position_profiles', ())) and getattr(env, 'position_plan', None) is not None


def has_declared_position_control_capability(env) -> bool:
    """Identify a Controller's declared canonical-position submission capability."""
    controller = getattr(env, 'controller', None)
    capabilities = getattr(controller, 'control_submission_capabilities', ())
    if not ('canonical-position-target-v1' in capabilities
            and callable(getattr(controller, 'compute', None))
            and type(getattr(controller, 'identity', None)) is str
            and bool(getattr(controller, 'identity', '').strip())):
        return False
    try:
        source = env.value['source']
    except (TypeError, KeyError, AttributeError):
        return False
    composition = getattr(source, 'source_composition_request', None)
    return bool(getattr(composition, 'resource_writers', ())) or (
        type(getattr(controller, 'control_submission_writer_id', None)) is str
        and bool(controller.control_submission_writer_id.strip())
    )


# Kept as a source-compatible alias for callers of the pre-v2 capability helper.
has_canonical_position_control_capability = has_declared_position_control_capability


def _dispatch_record(env, command_kind, controller_identities, generation):
    session = env.session
    boundary = session.state_boundary_identity()
    source = env.value.get('source')
    artifact = env.artifact
    receipt = ControlLifecycleDispatchV1(
        'control-lifecycle-dispatch-v1', command_kind,
        source.source_id, source.source_closure_digest, artifact.identity_hash,
        getattr(session, 'episode_id', boundary.episode_id), boundary.boundary_id, boundary.control_step,
        generation, tuple(controller_identities), 'preparing')
    session._control_lifecycle_dispatch = receipt
    return receipt


def prepare_selected_control_action(env, action, *, proposal=None, observer_solution=None,
                                    caller_driven=False):
    """Run one selected action through its declared capability's common lifecycle.

    Capability dispatch is based on bound execution objects. Position and
    effort keep separate typed controllers and lowering implementations, while
    both install one source/episode/boundary/generation dispatch record before
    Controller computation and converge on ``submit_control_command``.
    """
    if env._stopped or env.session is None:
        raise RuntimeError('reset required or episode already stopped')

    context = {}
    if proposal is not None:
        context['proposal'] = proposal
    if observer_solution is not None:
        context['observer_solution'] = observer_solution
    if caller_driven:
        context['caller_driven'] = True

    physical_factory = getattr(env.binding, 'physical_control_profile', None)
    if callable(physical_factory):
        profile = physical_factory(env)
        if profile is not None:
            from .physical_control import PhysicalControlExecutionV1
            if type(profile) is not PhysicalControlExecutionV1:
                raise TypeError('selected physical route requires PhysicalControlExecutionV1')
            _dispatch_record(env, 'physical-effort-batch',
                             tuple(item.identity for item in profile.controllers), profile.generation)
            selection = getattr(env, '_physical_reset_selection', None)
            if selection is not None:
                action = selection.validate_action(action)
            env._physical_controller_preparation_started = False
            try:
                result = env._prepare_physical_control(action, **context)
            except BaseException as error:
                if selection is not None or env._physical_controller_preparation_started:
                    env._latch_fault('physical_control_preparation', error, before_state=env.state)
                raise
            finally:
                env._physical_controller_preparation_started = False
            current = env.session._control_lifecycle_dispatch
            if current.stage == 'preparing':
                from dataclasses import replace
                env.session._control_lifecycle_dispatch = replace(current, stage='prepared')
            return result

    if getattr(env, 'mixed_control_profile', False):
        _dispatch_record(env, 'mixed-actuator-command', (env.controller.identity,),
                         int(getattr(env.controller, 'generation', 0)))
        return env._prepare_mixed_control(action, **context)

    if getattr(env, 'leaf_position_profile', False):
        plan = env.leaf_plan
        if plan is None or not getattr(plan, '_compiled', False):
            raise ValueError('leaf Position route requires a compiled control plan')
        if env.state.control_step >= env.horizon:
            env._stopped = True
            raise RuntimeError('selected position-control horizon is exhausted')
        if getattr(env, 'fixed_attachment_leaf_position_profile', False):
            from ...controllers.canonical.leaf_actions import AttachedLeafActionSetV1 as ActionType
        else:
            from ...controllers.canonical.leaf_actions import LeafPositionActionSetV1 as ActionType
        if type(action) is not ActionType:
            raise TypeError('leaf Position route requires its typed Arm and Hand action-set')
        action.structured_request(env.position_scene, plan)
        identities = tuple(sorted(entry.binding.identity_hash for entry in plan.leaves))
        _dispatch_record(env, 'position-target', identities, 0)
        result = env._prepare_leaf_position(action)
        current = env.session._control_lifecycle_dispatch
        if current.stage == 'preparing':
            from dataclasses import replace
            env.session._control_lifecycle_dispatch = replace(current, stage='prepared')
        return result

    if has_position_control_capability(env):
        profiles = env.position_profiles
        identities = tuple(profile.identity for profile in profiles)
        generation = int(getattr(profiles[0], 'generation', 0))
        if env.state.control_step >= env.horizon:
            env._stopped = True
            raise RuntimeError('selected position-control horizon is exhausted')
        from ...controllers.canonical.contracts import StructuredActionRequestV1
        if (not isinstance(action, StructuredActionRequestV1)
                and env.value.get('f06_pickcube_isaac_input') is not None
                and len(profiles) == 1):
            from .control import single_position_action_request
            action = single_position_action_request(
                action, scene=env.position_scene, plan=env.position_plan,
                profile=profiles[0])
        if not isinstance(action, StructuredActionRequestV1):
            raise TypeError('PositionServoV1 requires a StructuredActionRequestV1')
        from .control import prepare_structured_action
        prepare_structured_action(env.position_plan, action)
        _dispatch_record(env, 'position-target', identities, generation)
        result = env._prepare_position_profile(action, **context)
        current = getattr(env.session, '_control_lifecycle_dispatch', None)
        if current is not None and current.stage == 'preparing':
            from dataclasses import replace
            env.session._control_lifecycle_dispatch = replace(current, stage='prepared')
        return result

    if has_declared_position_control_capability(env):
        session_generation = getattr(env.session, 'physical_control_generation', None)
        generation = (session_generation if type(session_generation) is int
                      else int(getattr(env.controller, 'generation', 0)))
        _dispatch_record(env, 'position-target', (env.controller.identity,), generation)
        result = env._prepare_reference_step(action, **context)
        current = getattr(env.session, '_control_lifecycle_dispatch', None)
        if current is not None and current.stage == 'preparing':
            from dataclasses import replace
            env.session._control_lifecycle_dispatch = replace(current, stage='prepared')
        return result

    from ...controllers.canonical.contracts import StructuredActionRequestV1
    if isinstance(action, StructuredActionRequestV1):
        raise TypeError('structured ControllerGroup actions require a compiled position capability')
    if proposal is None or caller_driven:
        env._episode_mode = 'external'
    return env._prepare_reference_step(action, **context)
