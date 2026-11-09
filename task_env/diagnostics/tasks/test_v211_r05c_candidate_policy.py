"""Pure checks for the explicitly opted-in R05c diagnostic identity."""
import pytest

from task_env.runtime.sessions.r05c_v211_candidate import (
    CONTROLLER_IDENTITY, PROFILE_ID, PROVIDER_REVISION, admit_request,
)


def test_candidate_is_exactly_geophys_cpu_100_only():
    assert admit_request('geophys', 'cpu', 100) == PROFILE_ID
    for arguments in (('geophys', 'cpu', 500), ('geophys', 'cuda', 100),
                      ('mujoco', 'cpu', 100), ('geophys', 'cpu', 100.0),
                      ('geophys', 'cpu', True)):
        with pytest.raises(ValueError, match='GeoPhys CPU and 100 Hz'):
            admit_request(*arguments)
    assert CONTROLLER_IDENTITY == 'ea357a92bf10d7989d8e43ac566b15af9f5096ba5bed836570f83ce9f62b5468'
    assert PROVIDER_REVISION == 'c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7'


def test_candidate_constructor_uses_distinct_binding_and_metadata(monkeypatch):
    from task_env.diagnostics.tasks.r05c_v211_candidate import make_cpu100_candidate
    from task_env.tasks.nut_assembly import specialization

    old_recipe = {'native_feedback_profile': 'nutassembly-native-feedback-v1', 'unchanged': 7}
    def original_build(*_args):
        return {'resolved_configuration': old_recipe, 'recipe': old_recipe, 'recipe_identity': 'old'}

    from dataclasses import dataclass
    @dataclass(frozen=True)
    class Binding:
        admit_native_feedback_profile: object
        build_native_feedback_profile: object

    original_binding = Binding(lambda *_: 'historical', original_build)

    class FakeEnv:
        binding = original_binding
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(specialization, 'NutAssemblyReferenceEnv', FakeEnv)
    env = make_cpu100_candidate(horizon=8)
    binding = env.kwargs['_binding']
    assert binding is not original_binding
    assert env.kwargs['_native_feedback_request'] == 100
    assert binding.admit_native_feedback_profile('geophys', 'cpu', 100) == PROFILE_ID
    value = binding.build_native_feedback_profile('geophys', 'cpu', 100, False)
    assert value['recipe']['native_feedback_profile'] == PROFILE_ID
    assert value['recipe']['diagnostic_candidate_qualification'] == 'NOT_REQUALIFIED'
    assert value['resolved_configuration'] is value['recipe']
    assert value['recipe_identity'] != 'old'
    assert old_recipe == {'native_feedback_profile': 'nutassembly-native-feedback-v1', 'unchanged': 7}


def test_historical_and_candidate_identity_are_distinct():
    from task_env.runtime.sessions.api import (
        _GEOPHYS_R05B_NATIVE_FEEDBACK_PROFILE, _GEOPHYS_R05B_NATIVE_FEEDBACK_REVISION,
        _r05b_native_feedback_manifest,
    )
    assert PROFILE_ID != _GEOPHYS_R05B_NATIVE_FEEDBACK_PROFILE
    assert PROVIDER_REVISION != _GEOPHYS_R05B_NATIVE_FEEDBACK_REVISION
    for unknown in ('unknown-profile', []):
        with pytest.raises(ValueError, match='unknown normal native-feedback'):
            _r05b_native_feedback_manifest(None, None, None, unknown)
