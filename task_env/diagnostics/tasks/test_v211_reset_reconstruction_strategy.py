"""Task-bound reset reconstruction and source lease contracts; no provider."""
from types import SimpleNamespace

import pytest

from task_env.environment.reference_binding import ReferenceTaskBinding


class Receipt:
    def __init__(self, name, events):
        self.name, self.events, self.closed = name, events, False

    def close(self):
        self.closed = True
        self.events.append(('close', self.name))


def setup_binding():
    events = []
    artifact = object()
    def value(name, *, solution=None):
        return {'artifact': artifact, 'source': SimpleNamespace(
            execution_source_receipt=Receipt(name, events)), 'solution': solution, 'name': name}
    def build(name, *args, **kwargs):
        events.append((name, *args))
        return value(name, **kwargs)
    binding = SimpleNamespace(
        build_sampled=None,
        build_for_provider=lambda provider: build('normal', provider),
        build_seeded=lambda provider, backend, seed, horizon: build('seeded', provider, backend, seed, horizon),
        build_external=lambda provider: build('external', provider),
        build_mixed_control_profile=lambda provider, backend: build('mixed', provider, backend),
        build_native_feedback_profile=lambda provider, backend, request, flag: build(
            'native', provider, backend, request, flag, solution='owned'),
        admit_native_feedback_profile=lambda *_args: 'admitted-native',
        validate_external_solution=lambda actual, solution: events.append(('validate', actual['name'], solution)),
        reset_seed=lambda seed: events.append(('seed', seed)) or seed,
        reset_runtime_input=None,
    )
    return binding, artifact, events, value


def strategy(binding, *, mixed=False, native_request=None):
    return ReferenceTaskBinding.reset_reconstruction_strategy(
        binding, 'mujoco', 'cpu', 50, mixed=mixed, native_request=native_request)


def apply(owner, current, artifact, *, seed=31, external=None, verify=lambda _value: None, prepared=None):
    return owner.reconstruct(current, artifact, seed, external,
        lambda old, value, runtime: old if value['artifact'] is old else (_ for _ in ()).throw(ValueError('artifact')),
        verify_source=verify, prepared=prepared)


def test_mixed_initial_value_is_used_once_then_task_owner_rebuilds():
    binding, artifact, events, _value = setup_binding()
    owner = strategy(binding, mixed=True)
    initial = owner.initial()
    first = apply(owner, initial, artifact)
    assert first.value is initial and [row[0] for row in events].count('mixed') == 1
    second = apply(owner, first.value, artifact, seed=32)
    assert second.value is not initial and second.seed == 32
    assert [row[0] for row in events].count('mixed') == 2
    assert initial['source'].execution_source_receipt.closed


def test_standard_seeded_and_external_solution_builders_are_distinct():
    binding, artifact, events, value = setup_binding()
    owner = strategy(binding)
    old = value('old')
    assert owner.initial()['name'] == 'seeded'
    seeded = apply(owner, old, artifact, seed=7)
    assert ('seeded', 'mujoco', 'cpu', 7, 50) in events
    external = apply(owner, seeded.value, artifact, seed=9, external='caller-solution')
    assert external.value['name'] == 'external'
    assert ('validate', 'external', 'caller-solution') in events


def test_native_profile_admission_and_both_solution_validations():
    binding, artifact, events, value = setup_binding()
    owner = strategy(binding, native_request='100hz')
    assert owner.profile == 'admitted-native' and owner.initial()['solution'] == 'owned'
    result = apply(owner, value('old'), artifact, external='caller')
    assert result.solution == 'owned'
    assert ('validate', 'native', 'caller') in events and ('validate', 'native', 'owned') in events
    assert ('native', 'mujoco', 'cpu', '100hz', False) in events


def test_source_or_artifact_failure_closes_new_lease_and_preserves_old_for_retry():
    binding, artifact, events, value = setup_binding()
    owner = strategy(binding)
    old, candidate = value('old'), value('candidate')
    def reject(_candidate):
        raise ValueError('source closure changed')
    with pytest.raises(ValueError, match='source closure changed'):
        apply(owner, old, artifact, prepared=candidate, verify=reject)
    assert candidate['source'].execution_source_receipt.closed
    assert not old['source'].execution_source_receipt.closed
    bad = value('bad'); bad['artifact'] = object()
    with pytest.raises(ValueError, match='artifact'):
        apply(owner, old, artifact, prepared=bad)
    assert bad['source'].execution_source_receipt.closed
    assert not old['source'].execution_source_receipt.closed
    valid = apply(owner, old, artifact, seed=5)
    assert valid.value['name'] == 'seeded' and old['source'].execution_source_receipt.closed


def test_switch_candidate_is_prepared_before_reconstruction_and_not_built_twice():
    binding, artifact, events, value = setup_binding()
    owner = strategy(binding)
    previous = value('old')
    candidate = owner.build_switch_candidate(23)
    assert not previous['source'].execution_source_receipt.closed
    result = apply(owner, previous, artifact, seed=23, prepared=candidate)
    assert result.value is candidate
    assert len([row for row in events if row[0] == 'seeded']) == 1
    assert previous['source'].execution_source_receipt.closed


def test_selected_strategy_uses_current_task_binding_without_reselecting_policy():
    binding, artifact, events, value = setup_binding()
    owner = strategy(binding)
    replacement = SimpleNamespace(**vars(binding))
    replacement.build_seeded = lambda *args: events.append(('replacement-seeded', *args)) or value('replacement')
    owner.use_binding(replacement)
    result = apply(owner, value('old'), artifact, seed=17)
    assert result.value['name'] == 'replacement'
    assert ('replacement-seeded', 'mujoco', 'cpu', 17, 50) in events


@pytest.mark.parametrize('failure_point', ('preflight', 'old_stop'))
def test_switch_preflight_failure_closes_candidate_lease_before_old_session(monkeypatch, failure_point):
    import hashlib
    from pathlib import Path
    from task_env.diagnostics.tasks.test_v211_g03_3c_reset_failures import make_selected
    from task_env.runtime.sessions import provenance
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1

    env = make_selected()
    old_receipt = env.value['source'].execution_source_receipt
    original_asset = (Path(__file__).resolve().parents[3] / 'asset/external/mujoco_menagerie'
                      / 'franka_emika_panda/panda.xml')
    original_hash = hashlib.sha256(original_asset.read_bytes()).hexdigest()
    assert old_receipt.snapshot_root.exists()
    previous = SimpleNamespace(close=lambda: pytest.fail('old session must remain open'))
    env.session = previous
    candidate_receipts, closed = [], []
    original_close = ExecutionSourceReceiptV1.close
    def observe_close(receipt):
        closed.append(receipt)
        return original_close(receipt)
    monkeypatch.setattr(ExecutionSourceReceiptV1, 'close', observe_close)
    original_preflight = provenance.preflight_selected_deployment
    def preflight(*args, **kwargs):
        candidate_receipts.append(kwargs['source'].execution_source_receipt)
        if failure_point == 'preflight':
            raise RuntimeError('candidate preflight failure')
        return original_preflight(*args, **kwargs)
    monkeypatch.setattr(provenance, 'preflight_selected_deployment', preflight)
    if failure_point == 'old_stop':
        env._selected_reset_stop_capability = True
        env._published_position_typed_state = object()
        monkeypatch.setattr(env, 'stop', lambda _reason: (_ for _ in ()).throw(RuntimeError('old stop failure')))
    try:
        with pytest.raises(RuntimeError, match='failure'):
            env.reset(seed=31)
        assert env.session is previous and len(candidate_receipts) == 1
        assert any(receipt is candidate_receipts[0] for receipt in closed)
        # Candidate snapshots are owned temporaries, not the original asset.
        assert candidate_receipts[0] is not old_receipt
        assert not candidate_receipts[0].snapshot_root.exists()
        assert old_receipt.snapshot_root.exists()
        assert hashlib.sha256(original_asset.read_bytes()).hexdigest() == original_hash
    finally:
        env.session = None
        env._published_position_typed_state = None
        env._published_position_state = None
        env.close()
