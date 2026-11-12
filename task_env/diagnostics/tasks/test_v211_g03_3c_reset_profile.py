"""Selected reset profile stays explicit and restricted to its admitted task."""
import sys

import pytest

from task_env.environment.configuration import resolve_task_env_config
from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
from task_env.tasks.nut_assembly.specialization import NutAssemblyReferenceEnv


PROFILE = 'pickcube-state-only-switch-v1'


def selected(**execution):
    return {'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                          'physics_device': 'cpu', 'deployment': 'in_process',
                          'interpreter': sys.executable, **execution},
            'task': {'controller_profile': 'r3_continuous_v1'}}


def test_profile_round_trips_and_default_is_absent_from_request():
    default = resolve_task_env_config(PickCubeReferenceEnv, selected())
    assert default.reset_profile is None
    assert 'reset_profile' not in default.requested_execution_json
    resolved = resolve_task_env_config(PickCubeReferenceEnv, selected(reset_profile=PROFILE))
    assert resolved.reset_profile == PROFILE
    assert resolve_task_env_config(PickCubeReferenceEnv, resolved) == resolved


def test_invalid_or_incompatible_profiles_are_rejected():
    with pytest.raises(ValueError):
        resolve_task_env_config(PickCubeReferenceEnv, selected(reset_profile='unknown'))
    cfg = selected(reset_profile=PROFILE)
    cfg['controller'] = {'gravity_compensation': True}
    with pytest.raises(ValueError):
        resolve_task_env_config(PickCubeReferenceEnv, cfg)
    nut_cfg = selected(reset_profile=PROFILE)
    nut_cfg.pop('task')
    with pytest.raises(ValueError):
        resolve_task_env_config(NutAssemblyReferenceEnv, nut_cfg)


def test_candidate_rng_is_detached_and_explicit_seed_restarts():
    from copy import deepcopy
    from task_env.environment.reset_switch import prepare_switch_reset
    initial = resolve_task_env_config(PickCubeReferenceEnv, selected(reset_profile=PROFILE))
    first = prepare_switch_reset(PickCubeReferenceEnv, initial, 31, None, None)
    saved = deepcopy(first.rng_state)
    next1 = prepare_switch_reset(PickCubeReferenceEnv, initial, None, saved, None)
    next2 = prepare_switch_reset(PickCubeReferenceEnv, initial, None, saved, None)
    assert first.task_seed == 31
    assert next1 == next2 and next1.task_seed != first.task_seed
    assert first.rng_state == saved
    assert prepare_switch_reset(PickCubeReferenceEnv, initial, 31, next1.rng_state, None) == first


def test_target_config_is_not_inherited_from_previous_route():
    from task_env.environment.reset_switch import prepare_switch_reset
    initial = resolve_task_env_config(PickCubeReferenceEnv, selected(reset_profile=PROFILE))
    first = prepare_switch_reset(PickCubeReferenceEnv, initial, 31, None,
                                 {'physics_provider': 'geophys', 'deployment': 'in_process',
                                  'interpreter': sys.executable})
    assert first.config.execution_spec_v2.engine == 'geophys'
    assert first.config.execution_spec_v2.host == 'standalone'
    assert first.config.source_delivery_manifest is None
    with pytest.raises(ValueError):
        prepare_switch_reset(PickCubeReferenceEnv, first.config, None, first.rng_state,
                             {'physics_provider': 'isaacsim'})
    with pytest.raises(ValueError):
        prepare_switch_reset(PickCubeReferenceEnv, initial, None, first.rng_state,
                             {'physics_provider': 'geophys', 'reset_profile': 'different'})


def test_first_unseeded_reset_initializes_a_core_rng_without_fixed_seed():
    from task_env.environment.reset_switch import prepare_switch_reset
    initial = resolve_task_env_config(PickCubeReferenceEnv, selected(reset_profile=PROFILE))
    candidate = prepare_switch_reset(PickCubeReferenceEnv, initial, None, None, None)
    assert 0 <= candidate.task_seed < 2**31
    assert candidate.rng_state['bit_generator'] == 'PCG64'
    continuation = prepare_switch_reset(PickCubeReferenceEnv, initial, None, candidate.rng_state, None)
    assert continuation.rng_state != candidate.rng_state
