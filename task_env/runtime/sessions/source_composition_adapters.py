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

    def compose_pickcube_robot_source(self, *args, **kwargs):
        implementation = getattr(import_module(self.implementation_module),
                                 self.implementation_name)
        return implementation(*args, **kwargs)


_PICKCUBE_SOURCE_ADAPTERS = {
    ('mujoco', 'cpu'): SourceCompositionAdapterV1(
        'mujoco', 'cpu', 'pickcube-robot-source-composition-v1',
        'task_env.runtime.sessions.mujoco_composition',
        'compose_pickcube_robot_source',
    ),
}


def resolve_pickcube_robot_source_adapter(provider, backend):
    """Resolve a real registered adapter before Task source construction begins."""
    if type(provider) is not str or type(backend) is not str:
        raise TypeError('provider and backend selectors must be strings')
    adapter = _PICKCUBE_SOURCE_ADAPTERS.get((provider, backend))
    if adapter is None:
        raise SourceCompositionCapabilityUnavailable(
            f'no PickCube Robot source-composition adapter is registered for '
            f'{provider!r}/{backend!r}'
        )
    return adapter
