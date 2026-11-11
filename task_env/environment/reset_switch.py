"""Pure preparation for the selected PickCube state-only reset profile.

Candidate random state is detached: a caller must commit it only once the
replacement becomes destructive. Provider initialization never mutates it.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import json

import numpy as np

PROFILE = 'pickcube-state-only-switch-v1'
_ROUTES = frozenset({('mujoco', 'geophys'), ('geophys', 'mujoco'),
                     ('mujoco', 'isaacsim'), ('isaacsim', 'mujoco')})


@dataclass(frozen=True)
class SwitchResetCandidate:
    config: object
    task_seed: int
    provider_seed: int
    rng_state: dict
    seed_algorithm: str = 'pickcube-reset-seed-v1'


def reset_switch_receipt(candidate, *, provider, provider_seed, configuration_generation,
                         topology_generation):
    """Describe this selected reset strategy after its new boundary commits."""
    return {
        'schema_version': 'pickcube-reset-switch-receipt-v1',
        'task_seed': candidate.task_seed,
        'provider_seed': provider_seed,
        'task_seed_algorithm': candidate.seed_algorithm,
        'provider_seed_algorithm': 'pickcube-provider-seed-task-identity-v1',
        'provider': provider,
        'configuration_generation': configuration_generation,
        'topology_generation': topology_generation,
    }


def reset_switch_execution_receipt(*, configuration_generation, topology_generation,
                                   task_seed, provider_seed):
    """Describe the current switch generation in an execution receipt."""
    return {
        'configuration_generation': configuration_generation,
        'topology_generation': topology_generation,
        'task_seed': task_seed,
        'provider_seed': provider_seed,
        'task_seed_algorithm': 'pickcube-reset-seed-v1',
        'provider_seed_algorithm': 'pickcube-provider-seed-task-identity-v1',
    }


def prepare_switch_reset(environment_type, current, seed, rng_state, execution):
    """Resolve a target from its own defaults and a detached RNG candidate."""
    from .configuration import resolve_task_env_config

    if current.reset_profile != PROFILE:
        raise ValueError('reset switching requires the explicit reset profile')
    if execution is not None and not isinstance(execution, Mapping):
        raise TypeError('reset execution must be a mapping')
    target = (json.loads(current.requested_execution_json)
              if execution is None else dict(execution))
    if 'reset_profile' in target and target['reset_profile'] != PROFILE:
        raise ValueError('reset_profile cannot be changed at reset')
    target['reset_profile'] = PROFILE
    provider = target.get('physics_provider', current.physics_provider if execution is None else None)
    if provider is None:
        raise ValueError('target execution must specify physics_provider')
    if provider != current.physics_provider and (current.physics_provider, provider) not in _ROUTES:
        raise ValueError('requested reset provider edge is not supported')
    if execution is not None:
        # Provider/backend/device are a fresh route selection, never inherited
        # from the current execution; the normal resolver supplies defaults.
        target.setdefault('physics_backend', 'cuda' if provider == 'isaacsim' else 'cpu')
        target.setdefault('physics_device', 'cuda:0' if provider == 'isaacsim' else 'cpu')
    config = resolve_task_env_config(environment_type, {
        'execution': target,
        'episode': {'horizon': current.environment.episode.horizon},
        'controller': {'profile_id': current.controller_profile},
        'task': dict(current.task_parameters),
    })
    if seed is not None:
        if type(seed) is not int or seed < 0:
            raise ValueError('reset seed must be a nonnegative integer or None')
        rng = np.random.default_rng(seed)
        task_seed = seed
    else:
        rng = np.random.default_rng()
        if rng_state is not None:
            rng.bit_generator.state = deepcopy(rng_state)
        task_seed = int(rng.integers(0, 2**31, dtype=np.int64))
    # Both existing runtime execution contracts admit the task seed as their
    # provider seed.  This pure mapping consumes no additional Core RNG value.
    provider_seed = task_seed
    return SwitchResetCandidate(config, task_seed, provider_seed, deepcopy(rng.bit_generator.state))
