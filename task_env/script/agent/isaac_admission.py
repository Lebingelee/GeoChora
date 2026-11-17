"""Read exact Isaac PickCube admission identities from the Core owner."""
from types import MappingProxyType
from task_env.runtime.sessions.isaac_usd_admission import (
    F06_PICKCUBE_ISAAC_PROFILE, f06_admitted_delivery_identities, f06_delivery_identity,
)


def admitted_isaac_deliveries():
    return MappingProxyType(f06_admitted_delivery_identities())


def pinned_isaac_delivery_sha256():
    return f06_delivery_identity()[0]


def isaac_physics_profile():
    return F06_PICKCUBE_ISAAC_PROFILE


__all__ = ['admitted_isaac_deliveries', 'pinned_isaac_delivery_sha256', 'isaac_physics_profile']
