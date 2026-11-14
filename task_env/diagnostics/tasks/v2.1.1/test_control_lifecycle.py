"""Formal selected control must enter a declared submission capability."""

from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.control_lifecycle import prepare_selected_control_action


def test_undeclared_controller_cannot_bypass_the_submission_owner():
    calls = []
    env = SimpleNamespace(_stopped=False, session=object(), position_profiles=(),
        controller=object(), _physical_execution=lambda: None,
        _prepare_reference_step=lambda *args, **kwargs: calls.append('legacy'))
    with pytest.raises(TypeError, match='common control submission capability'):
        prepare_selected_control_action(env, [0.0])
    assert calls == []


def test_mixed_action_rejects_reset_scoped_selection_before_preparation():
    from task_env.controllers.canonical.position_sequence import PositionPhysicalActionV1
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    session = SimpleNamespace()
    profile = object.__new__(PhysicalControlExecutionV1)
    env = SimpleNamespace(_stopped=False, session=session,
        _physical_execution=lambda: profile, _physical_reset_selection=object())
    action = object.__new__(PositionPhysicalActionV1)
    with pytest.raises(ValueError, match='does not support reset-scoped'):
        prepare_selected_control_action(env, action)
    assert not hasattr(session, '_prepared_mixed_position')
    assert not hasattr(session, '_control_lifecycle_dispatch')


def test_position_sequence_is_not_reinterpreted_as_a_pose_action():
    from task_env.controllers.canonical.contracts import RequestedAction
    from task_env.controllers.canonical.position_sequence import PositionActionSequenceV1, PositionActionSliceV1

    def reject_projection(*args, **kwargs):
        pytest.fail('a typed Position sequence must not be projected as a pose action')

    profile = SimpleNamespace(identity='controller', prepare_action_request=reject_projection)
    boundary = SimpleNamespace(episode_id='episode', boundary_id='boundary', control_step=0)
    session = SimpleNamespace(episode_id='episode', state_boundary_identity=lambda: boundary)
    source = SimpleNamespace(source_id='source', source_closure_digest='closure')
    artifact = SimpleNamespace(identity_hash='artifact', timebase=SimpleNamespace(control_substeps=5))
    env = SimpleNamespace(_stopped=False, session=session, position_profiles=(profile,),
        position_plan=object(), _physical_execution=lambda: None, state=SimpleNamespace(control_step=0),
        horizon=8, binding=SimpleNamespace(external_actions=True), value={'source': source},
        artifact=artifact, _prepare_position_profile=lambda action, **kwargs: action)
    action = RequestedAction('absolute_joint', None, 'none', (0., 0., 0., -1., 0., 1., 0., 0.))
    sequence = PositionActionSequenceV1((PositionActionSliceV1(0, 5, action),))
    assert prepare_selected_control_action(env, sequence) is sequence
    assert session._control_lifecycle_dispatch.stage == 'prepared'


@pytest.mark.parametrize('provider,backend,module,method', [
    ('mujoco', 'cpu', 'mujoco_physical', 'preflight_physical_mujoco'),
    ('geophys', 'cpu', 'geophys_physical', 'preflight_physical_geophys'),
    ('isaacsim', 'cuda', 'isaac_physical', 'preflight_physical_isaac'),
])
def test_physical_execution_preflight_uses_its_native_adapter(monkeypatch, provider, backend, module, method):
    from importlib import import_module
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    adapter = import_module('task_env.runtime.sessions.' + module)
    execution = object.__new__(PhysicalControlExecutionV1)
    artifact, source = object(), object()
    calls = []
    monkeypatch.setattr(adapter, method, lambda *args: calls.append(args))
    execution.preflight(provider=provider, backend=backend, artifact=artifact, source=source)
    assert calls == [(execution, artifact, source)]


def test_unsupported_physical_preflight_rejects_before_native_import(monkeypatch):
    import importlib
    from task_env.environment.types import StageUnavailableError
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    monkeypatch.setattr(importlib, 'import_module',
                        lambda *_args: pytest.fail('unsupported adapter must not import a provider'))
    execution = object.__new__(PhysicalControlExecutionV1)
    with pytest.raises(StageUnavailableError, match='not implemented'):
        execution.preflight(provider='mujoco', backend='cuda', artifact=object(), source=object())


def test_overlapping_scene_writers_are_rejected_before_submission():
    from task_env.runtime.sessions.control_submission import _validate_resource_intervals

    with pytest.raises(ValueError, match='overlap'):
        _validate_resource_intervals((('arm', 'joint', 0, 3), ('hand', 'joint', 2, 5)),
            writer_resources=(('arm', ('joint',)), ('hand', ('joint',))), substeps=5)


def test_partial_control_write_preserves_error_and_skips_advance():
    from task_env.environment.lifecycle import EpisodeExecutionState

    events = []
    error = RuntimeError('partial write')
    def apply():
        events.append('write')
        raise error
    def on_failure(phase, received):
        assert received is error
        events.append(phase)
    state = EpisodeExecutionState()
    with pytest.raises(RuntimeError, match='partial write') as caught:
        state.execute_interval(apply_control=apply, advance=lambda _: events.append('advance'),
            read_state=lambda: None, evaluate=lambda _: None, observe=lambda _: None,
            publish=lambda *_: None, on_failure=on_failure)
    assert caught.value is error
    assert events == ['write', 'control_application']


def test_position_resource_projection_preserves_writer_scope_and_duplicates():
    from task_env.runtime.sessions.control_submission import _resource_owners_from_rows

    rows = (('hand', 'z', 'w2'), ('arm', 'b', 'w1'), ('arm', 'a', 'w1'),
            ('arm', 'a', 'w1'))
    assert _resource_owners_from_rows(rows, ('w2', 'missing', 'w1')) == (
        ('missing', ()), ('w1', ('arm/a', 'arm/a', 'arm/b')), ('w2', ('hand/z',)))


def test_selected_interval_reads_committed_env_state_and_observation_once():
    from task_env.environment.lifecycle import EpisodeExecutionState

    env = SimpleNamespace(state='before', obs='old')
    events = []
    def apply():
        events.append('apply')
        return 'command'
    def advance(command):
        events.append(('advance', command))
        env.state = 'after'
    def evaluate(state):
        events.append(('evaluate', state))
        env.obs = 'new'
        return 'evaluation'
    def publish(command, state, evaluation, observation):
        events.append(('publish', command, state, evaluation, observation))
        return observation
    state = EpisodeExecutionState()
    assert state.execute_selected_interval(env, apply_control=apply, advance=advance,
        evaluate=evaluate, publish=publish, on_failure=lambda *_: pytest.fail('unexpected fault')) == 'new'
    assert events == ['apply', ('advance', 'command'), ('evaluate', 'after'),
                      ('publish', 'command', 'after', 'evaluation', 'new')]


def test_selected_interval_preserves_evaluation_failure_phase():
    from task_env.environment.lifecycle import EpisodeExecutionState

    env = SimpleNamespace(state='boundary', obs='prior')
    phases = []
    def fail(_state):
        raise RuntimeError('evaluation failed')
    with pytest.raises(RuntimeError, match='evaluation failed'):
        EpisodeExecutionState().execute_selected_interval(env, apply_control=lambda: None,
            advance=lambda _: None, evaluate=fail, publish=lambda *_: pytest.fail('published'),
            on_failure=lambda phase, error: phases.append((phase, str(error))))
    assert phases == [('task_evaluation', 'evaluation failed')]
