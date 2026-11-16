"""Read Core's admitted PickCube Isaac deliveries without restating them.

Core owns which exact USD delivery manifests the F06 PickCube Isaac route
accepts. On the v2.1.1 develop line these live in
``task_env.runtime.sessions.isaac_usd_admission`` (one pinned desktop delivery);
the earlier ``task_env.tasks.pick_cube.isaac`` module (which also admitted an
asset-object delivery) was retired. The Harness reads whichever owner exists and
never widens the set itself.
"""
from __future__ import annotations

from types import MappingProxyType


def admitted_isaac_deliveries():
    """Return ``{manifest_sha256: representation_id}`` exactly as Core admits them."""
    try:
        from task_env.tasks.pick_cube.isaac import ISAAC_ADMITTED_DELIVERIES_V1
    except ImportError:
        from task_env.runtime.sessions.isaac_usd_admission import (
            _F06_DELIVERY_MANIFEST_SHA256_V1, _F06_REPRESENTATION_V1)
        return MappingProxyType({_F06_DELIVERY_MANIFEST_SHA256_V1: _F06_REPRESENTATION_V1})
    return MappingProxyType(dict(ISAAC_ADMITTED_DELIVERIES_V1))


def pinned_isaac_delivery_sha256() -> str:
    try:
        from task_env.tasks.pick_cube.isaac import ISAAC_DELIVERY_MANIFEST_SHA256_V1
    except ImportError:
        from task_env.runtime.sessions.isaac_usd_admission import (
            _F06_DELIVERY_MANIFEST_SHA256_V1 as ISAAC_DELIVERY_MANIFEST_SHA256_V1)
    return ISAAC_DELIVERY_MANIFEST_SHA256_V1


def isaac_physics_profile() -> str:
    try:
        from task_env.tasks.pick_cube.isaac import ISAAC_PROFILE_V1
    except ImportError:
        from task_env.runtime.sessions.isaac_usd_admission import (
            F06_PICKCUBE_ISAAC_PROFILE as ISAAC_PROFILE_V1)
    return ISAAC_PROFILE_V1


__all__ = ['admitted_isaac_deliveries', 'pinned_isaac_delivery_sha256', 'isaac_physics_profile']
