"""Provider route table shared by the Harness CLIs; no per-call CPU assumption.

The Harness selects a provider by name. Each name has exactly one admitted
backend/device pair, which is asserted against Core's own selected-config
table before any run. A route also records whether its episodes may only be
executed by a supervised native worker (Isaac Sim needs its own interpreter and
a headless ``SimulationApp``) instead of the Core Python process.
"""
from __future__ import annotations

ROUTES = {
    'mujoco': {'backend': 'cpu', 'device': 'cpu', 'native_worker': False},
    'geophys': {'backend': 'cpu', 'device': 'cpu', 'native_worker': False},
    'isaacsim': {'backend': 'cuda', 'device': 'cuda:0', 'native_worker': True},
}


class UnknownProvider(ValueError):
    """The Harness has no route for this provider name."""


def route_for(provider: str) -> dict:
    if provider not in ROUTES:
        raise UnknownProvider(f'harness has no admitted route for provider: {provider!r}')
    return dict(ROUTES[provider])


def backend_for(provider: str) -> str:
    return route_for(provider)['backend']


def device_for(provider: str) -> str:
    return route_for(provider)['device']


def requires_native_worker(provider: str) -> bool:
    return bool(route_for(provider)['native_worker'])


__all__ = [
    'ROUTES', 'UnknownProvider', 'backend_for', 'device_for', 'requires_native_worker',
    'route_for',
]
