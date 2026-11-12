"""Capability dispatch for provider-owned Robot source composition."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module


class SourceCompositionCapabilityUnavailable(ValueError):
    """The selected provider/backend has no registered source composer."""


def validate_effort_source_route(*, provider, backend, deployment, source_delivery_manifest,
                                 drive, kind, reset_selection):
    """Admit the source and reset capabilities before native materialization."""
    from ...controllers.canonical.r3_effort import PANDA_SWITCHABLE_EFFORT_KINDS

    if deployment != 'in_process':
        raise ValueError('physical profile currently requires explicit in_process execution')
    if (provider, backend) not in {('mujoco', 'cpu'), ('geophys', 'cpu'), ('isaacsim', 'cuda')}:
        raise ValueError('physical control requires an admitted CPU or Isaac CUDA route')
    if provider == 'isaacsim':
        if source_delivery_manifest is None:
            raise ValueError('Isaac physical control requires its USD delivery')
    elif source_delivery_manifest is not None:
        raise ValueError('MJCF physical profile does not consume a USD source delivery')
    if reset_selection and ((provider, backend) != ('mujoco', 'cpu') or drive != 'disabled'
                            or kind not in PANDA_SWITCHABLE_EFFORT_KINDS):
        raise ValueError('physical reset selection requires an isolated MuJoCo reference Controller')


def build_panda_effort_execution(robot, scene, artifact, source, *, native_drive,
                                 gripper_force_limit_N=None):
    """Bind a Robot's effort channels using the source format's native facts."""
    from .source import RuntimeSource, UsdRuntimeSourceV1

    if isinstance(source, RuntimeSource):
        from .mujoco_composition import checked_panda_effort_source_limits
        limits = checked_panda_effort_source_limits(source, scene)
        return robot.build_direct_effort_execution(
            scene, artifact, source, entity_id=robot.uid, native_drive=native_drive,
            native_ranges=tuple(limits), gripper_force_limit_N=gripper_force_limit_N)
    if isinstance(source, UsdRuntimeSourceV1):
        if gripper_force_limit_N is not None:
            raise ValueError('USD effort source does not admit a gripper force override')
        from .isaac_physical import build_isaac_panda_effort_execution
        return build_isaac_panda_effort_execution(robot, scene, artifact, source,
                                                  native_drive=native_drive)
    raise TypeError('Robot effort construction requires an admitted RuntimeSource')


def build_panda_source_effort_profile(robot, scene, artifact, source, *, native_drive,
                                      kind, config, source_xml, end_frame_id,
                                      task_settings, dynamic_parameters=None,
                                      gripper_force_limit_N=None):
    """Bind an admitted Robot source and compose its declared effort Controller."""
    from ...controllers.canonical.r3_effort import build_panda_effort_profile

    physical = build_panda_effort_execution(robot, scene, artifact, source,
        native_drive=native_drive, gripper_force_limit_N=gripper_force_limit_N)
    return build_panda_effort_profile(physical, kind=kind,
        cadence_s=artifact.timebase.control_dt, end_frame_id=end_frame_id,
        source_xml=source_xml, config=config, artifact_hash=artifact.identity_hash,
        dynamic_parameters=dynamic_parameters, **task_settings)


@dataclass(frozen=True)
class SourceCompositionAdapterV1:
    provider: str
    backend: str
    capability_id: str
    implementation_module: str
    implementation_name: str

    def compose_robot_source(self, *args, **kwargs):
        implementation = getattr(import_module(self.implementation_module),
                                 self.implementation_name)
        return implementation(*args, **kwargs)


_ROBOT_SOURCE_ADAPTERS = {
    ('geophys', 'cpu'): SourceCompositionAdapterV1(
        'geophys', 'cpu', 'reference-robot-source-composition-v1',
        'task_env.runtime.sessions.source_composition_adapters',
        'compose_reference_robot_source',
    ),
    ('mujoco', 'cpu'): SourceCompositionAdapterV1(
        'mujoco', 'cpu', 'robot-source-composition-v1',
        'task_env.runtime.sessions.mujoco_composition',
        'compose_robot_source',
    ),
}


def resolve_robot_source_adapter(provider, backend):
    """Resolve a real registered adapter before Task source construction begins."""
    if type(provider) is not str or type(backend) is not str:
        raise TypeError('provider and backend selectors must be strings')
    adapter = _ROBOT_SOURCE_ADAPTERS.get((provider, backend))
    if adapter is None:
        raise SourceCompositionCapabilityUnavailable(
            f'no Robot source-composition adapter is registered for '
            f'{provider!r}/{backend!r}'
        )
    return adapter


def declared_robot_source_composer(config, *, robot_uid, existing_robot_entity, task_body_names, task_site_transfers, robot=None):
    """Resolve the provider composer and bind the selected Robot per source."""
    from ...registry import AGENT_REGISTRY
    from ...assembly.source_composition import build_source_composition_intent_v1

    profile = config.controller_profile
    adapter = resolve_robot_source_adapter(config.physics_provider, config.environment.runtime.backend)
    task_entities = tuple(entity for entity, _ in task_body_names)

    def compose(source, *, artifact, controller):
        existing = tuple(robot for robot in getattr(source, 'agents', ()) if robot.uid == robot_uid)
        if len(existing) > 1:
            raise ValueError('Task source contains multiple Robots with the selected identity')
        selected = robot if robot is not None else (existing[0] if existing else AGENT_REGISTRY.create(robot_uid))
        if selected.uid != robot_uid or (existing and existing[0] is not selected):
            raise ValueError('Task source differs from the selected Robot declaration')
        profile_recipe = getattr(selected, 'source_recipe_for_profile', None)
        recipe = profile_recipe(profile) if profile is not None and callable(profile_recipe) else selected.source_recipe()
        if profile is not None and profile not in recipe.control_profiles:
            raise ValueError('selected Robot does not declare this Controller profile')
        intent = build_source_composition_intent_v1(
            task_source=source, task_entity_ids=task_entities,
            existing_robot_entity_ids=(existing_robot_entity,), robot_recipe=recipe,
            task_site_transfers=task_site_transfers)
        return adapter.compose_robot_source(source, robot=selected, composition_intent=intent,
            artifact=artifact, controller=controller, robot_recipe=recipe,
            controller_profile=profile, task_entities=task_entities,
            existing_robot_entity=existing_robot_entity, task_body_names=task_body_names,
            task_site_transfers=task_site_transfers)

    return compose



def validate_robot_source_request(source, *, robot, composition_intent, task_entities,
                                  existing_robot_entity, task_body_names, task_site_transfers,
                                  robot_recipe, controller_profile):
    """Check the selected source, intent, and Robot recipe before composition."""
    from ...assembly.source_composition import SourceCompositionIntentV1
    from ...robots.source_recipe import RobotSourceRecipeV1
    from .source import RuntimeSource

    recipe_method = getattr(robot, 'source_recipe', None)
    profile_recipe = getattr(robot, 'source_recipe_for_profile', None)
    recipe = (profile_recipe(controller_profile) if controller_profile is not None and callable(profile_recipe)
              else recipe_method() if callable(recipe_method) else None)
    if type(recipe) is not RobotSourceRecipeV1 or (robot_recipe is not None and robot_recipe != recipe):
        raise ValueError('Robot composition requires the selected provider-neutral recipe')
    if type(composition_intent) is not SourceCompositionIntentV1:
        raise TypeError('Robot source requires a frozen composition intent')
    if type(source) is not RuntimeSource:
        raise TypeError('Robot composition requires a typed RuntimeSource')
    if (type(task_entities) is not tuple or type(task_body_names) is not tuple
            or type(task_site_transfers) is not tuple or set(dict(task_body_names)) != set(task_entities)):
        raise ValueError('Task source roots must cover immutable Task entities')
    expected_mode = {'reference-task-source': 'reference',
                     'replace-task-subtree': 'replace', 'add-source': 'add'}[recipe.mode]
    if (composition_intent.task_source_id != source.source_id
            or composition_intent.task_source_closure_sha256 != source.source_closure_digest
            or composition_intent.task_entity_ids != task_entities
            or composition_intent.existing_robot_entity_ids != (existing_robot_entity,)
            or composition_intent.robot_uid != robot.uid
            or composition_intent.robot_recipe_sha256 != recipe.identity_hash
            or composition_intent.mode != expected_mode
            or composition_intent.task_site_transfers != task_site_transfers):
        raise ValueError('composition intent differs from Task/Robot declarations')
    if source.execution_source_receipt is not None:
        source.execution_source_receipt.validate_snapshot()
    elif source.scene_definition is not None and recipe.mode == 'reference-task-source':
        from .source import verify_projected_scene_source
        verify_projected_scene_source(source.scene_source, source.scene_definition,
                                      source.source_closure_digest)
    else:
        raise TypeError('Robot composition requires a verified source snapshot')
    return recipe


def compose_reference_robot_source(source, *, robot, composition_intent, artifact, controller, task_entities,
                                   existing_robot_entity, task_body_names, task_site_transfers,
                                   robot_recipe=None, controller_profile=None):
    """Bind an existing Robot source with the shared source and Controller contract."""
    recipe = validate_robot_source_request(source, robot=robot, composition_intent=composition_intent,
        task_entities=task_entities, existing_robot_entity=existing_robot_entity,
        task_body_names=task_body_names, task_site_transfers=task_site_transfers,
        robot_recipe=robot_recipe, controller_profile=controller_profile)
    if recipe.mode != 'reference-task-source':
        raise ValueError('reference source requires the selected Robot reference recipe')
    return _compose_checked_reference_source(source, robot=robot, recipe=recipe,
        composition_intent=composition_intent, artifact=artifact, controller=controller,
        task_entities=task_entities, existing_robot_entity=existing_robot_entity)


def _compose_checked_reference_source(source, *, robot, recipe, composition_intent, artifact,
                                      controller, task_entities, existing_robot_entity):
    from dataclasses import replace
    from ...assembly.source_composition import (CompositionSourceV1, CompositionSourceV2,
        SourceCompositionPlanV1, SourceCompositionRequestV2)
    position = robot.compile_reference_position_source(
        source, artifact=artifact, controller=controller,
        entity_id=existing_robot_entity, recipe=recipe)
    plan, subject_identity = position.plan, position.subject_identity_sha256
    legacy_task = CompositionSourceV1(source.source_id, source.source_closure_digest,
                                      (*task_entities, existing_robot_entity))
    legacy_robot = CompositionSourceV1(source.source_id, source.source_closure_digest,
                                       (existing_robot_entity,))
    legacy = SourceCompositionPlanV1(legacy_task, task_entities, (existing_robot_entity,),
        robot.uid, (legacy_robot,), 'reference', plan.assembly_identity_hash, None, (),
        plan.identity_hash, subject_identity, position_binding_identity_sha256=position.identity_hash)
    request = SourceCompositionRequestV2('source-composition-request-v2',
        CompositionSourceV2(source.source_id, source.source_closure_digest,
                             (*task_entities, existing_robot_entity)),
        task_entities, (existing_robot_entity,), robot.uid,
        (CompositionSourceV2(source.source_id, source.source_closure_digest,
                             (existing_robot_entity,)),), 'reference',
        plan.assembly_identity_hash,
        resource_writers=tuple(plan.resource_writers),
        intent_identity_sha256=composition_intent.identity_hash)
    if set(recipe.resource_writers) != set(request.resource_writers):
        raise ValueError('resolved Robot resource writers differ from its pre-parse recipe')
    return replace(source, position_subject_binding=position,
                   source_reference_plan=legacy, source_composition_request=request,
                   source_composition_intent=composition_intent)
