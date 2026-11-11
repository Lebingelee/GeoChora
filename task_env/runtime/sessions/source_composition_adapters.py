"""Capability dispatch for provider-owned Robot source composition."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module


class SourceCompositionCapabilityUnavailable(ValueError):
    """The selected provider/backend has no registered source composer."""


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


def declared_robot_source_composer(config, *, robot_uid, existing_robot_entity, task_body_names, task_site_transfers):
    """Resolve the selected Robot recipe and provider composer once per build."""
    from ...registry import AGENT_REGISTRY
    from ...assembly.source_composition import build_source_composition_intent_v1

    robot = AGENT_REGISTRY.create(robot_uid)
    profile = config.controller_profile
    profile_recipe = getattr(robot, 'source_recipe_for_profile', None)
    recipe = profile_recipe(profile) if profile is not None and callable(profile_recipe) else robot.source_recipe()
    if profile is not None and profile not in recipe.control_profiles:
        raise ValueError('selected Robot does not declare this Controller profile')
    adapter = resolve_robot_source_adapter(config.physics_provider, config.environment.runtime.backend)
    task_entities = tuple(entity for entity, _ in task_body_names)

    def compose(source, *, artifact, controller):
        intent = build_source_composition_intent_v1(
            task_source=source, task_entity_ids=task_entities,
            existing_robot_entity_ids=(existing_robot_entity,), robot_recipe=recipe,
            task_site_transfers=task_site_transfers)
        return adapter.compose_robot_source(source, robot=robot, composition_intent=intent,
            artifact=artifact, controller=controller, robot_recipe=recipe,
            controller_profile=profile, task_entities=task_entities,
            existing_robot_entity=existing_robot_entity, task_body_names=task_body_names,
            task_site_transfers=task_site_transfers)

    return compose
