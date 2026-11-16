"""Provider-free checks for the shared declared reset capability."""
from types import SimpleNamespace

import pytest

from task_env.artifacts.execution import EpisodeResetPlanV1
from task_env.environment.reference_binding import (
    execute_selected_reset_effect, prepare_selected_reset, resolve_selected_reset_effect,
)


def _plan(seed=31, artifact='a' * 64):
    plan = object.__new__(EpisodeResetPlanV1)
    object.__setattr__(plan, 'schema_version', 'episode-reset-plan-v1')
    object.__setattr__(plan, 'role_binding', SimpleNamespace(task_seed=seed))
    object.__setattr__(plan, 'reset_sample', SimpleNamespace(task_seed=seed, task_artifact_hash=artifact))
    object.__setattr__(plan, 'sampling_domain', 'training')
    return plan


def test_declared_plan_resolves_and_executes_without_controller_class():
    plan = _plan()
    binding = SimpleNamespace(reset_seed=lambda value: value, build_seeded=None,
                              reset_sample=lambda *_: pytest.fail('legacy sample chosen'))
    unset = object()
    seed, options, mixed_plan, mixed_sample = prepare_selected_reset(
        binding, seed=unset, seed_unset=unset, options=None, mixed=False,
        has_session=False, previous_sample=None, artifact=SimpleNamespace(identity_hash='a' * 64),
        value={'reset_plan': plan})
    assert (seed, options, mixed_plan, mixed_sample) == (31, None, None, None)
    sample, resolved = resolve_selected_reset_effect(binding, {'reset_plan': plan},
        SimpleNamespace(identity_hash='a' * 64), seed, mixed=False, mixed_plan=None, mixed_sample=None)
    calls = []
    session = SimpleNamespace(reset=lambda sample: calls.append(('sample', sample)),
                              reset_plan=lambda value: calls.append(('plan', value)))
    execute_selected_reset_effect(session, sample, resolved)
    assert calls == [('plan', plan)]
    with pytest.raises(ValueError, match='Artifact'):
        resolve_selected_reset_effect(binding, {'reset_plan': plan}, SimpleNamespace(identity_hash='b' * 64),
                                      seed, mixed=False, mixed_plan=None, mixed_sample=None)
    with pytest.raises(ValueError, match='seed'):
        resolve_selected_reset_effect(binding, {'reset_plan': plan}, SimpleNamespace(identity_hash='a' * 64),
                                      32, mixed=False, mixed_plan=None, mixed_sample=None)


def test_legacy_and_mixed_reset_keep_their_existing_provider_operations():
    sample, mixed_sample, plan = object(), object(), object()
    binding = SimpleNamespace(reset_sample=lambda *_: sample)
    artifact = SimpleNamespace(identity_hash='a' * 64)
    assert resolve_selected_reset_effect(binding, {}, artifact, 31,
        mixed=False, mixed_plan=None, mixed_sample=None) == (sample, None)
    assert resolve_selected_reset_effect(binding, {}, artifact, 31,
        mixed=True, mixed_plan=plan, mixed_sample=mixed_sample) == (mixed_sample, plan)
    calls = []
    session = SimpleNamespace(reset=lambda value: calls.append(('sample', value)),
                              reset_plan=lambda value: calls.append(('plan', value)))
    execute_selected_reset_effect(session, sample, None)
    execute_selected_reset_effect(session, mixed_sample, plan)
    assert calls == [('sample', sample), ('plan', plan)]
    with pytest.raises(TypeError, match='reset contract'):
        resolve_selected_reset_effect(binding, {'reset_plan': object()}, artifact, 31,
                                      mixed=False, mixed_plan=None, mixed_sample=None)
    with pytest.raises(ValueError, match='requires a declared reset plan'):
        prepare_selected_reset(SimpleNamespace(reset_seed=lambda seed: seed, build_seeded=None),
            seed=31, seed_unset=object(), options=None, mixed=False, has_session=False,
            previous_sample=None, artifact=artifact, value={}, requires_reset_plan=True)
