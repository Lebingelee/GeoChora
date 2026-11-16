"""Publication boundaries shared by selected physical sequence and Env."""
from types import SimpleNamespace


def test_sequence_publishes_new_boundary_for_bound_position_observation(monkeypatch):
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import physical_sequence

    monkeypatch.setattr(physical_sequence, 'describe_physical_sequence_capability', lambda *_: None)
    env = object.__new__(SelectedReferenceEnv)
    env.binding = SimpleNamespace(physical_observation_binding=object(), physical_terminate_on_success=False)
    env.recorder = None
    env.session = SimpleNamespace(apply_physical_command_sequence=lambda _: None,
        physical_joint_build_receipt=lambda _: SimpleNamespace(provenance='native_build'))
    env.artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=1))
    env.value = {}
    env.horizon = 2
    env.state = SimpleNamespace(control_step=1)
    env.typed_state = object()
    env.obs, env.info = {'state': 1}, {'boundary': 1}
    env.evaluation = SimpleNamespace(reward=1.0, failure=False, success=False)
    env._published_position_state = object()
    lifecycle = SimpleNamespace(step_outcome=lambda **_: (False, False), finish_step=lambda **_: None)
    env._episode_execution_state = lambda: lifecycle
    profile = SimpleNamespace(controllers=(), compiled=SimpleNamespace(binding=object()))
    action = SimpleNamespace(slices=(), validate=lambda **_: None)
    hooks = physical_sequence.prepare_selected_physical_sequence(env, action, profile=profile,
        view=None, context=None, assessment=None, proposal=None, observer_solution=None,
        clock_tolerance=1e-9)
    result = hooks['publish'](None, None, None, None)
    assert env._published_position_state is env.state
    assert env._published_position_typed_state is env.typed_state
    assert env._published_position_evaluation is env.evaluation
    assert result == (env.obs, 1.0, False, False, env.info)


def test_failed_deferred_capture_follows_commit_without_second_reset():
    import pytest
    from task_env.environment.reference_env import SelectedReferenceEnv

    env = object.__new__(SelectedReferenceEnv)
    env._task_rgb_config = object()
    env.state = object()
    events = []
    lifecycle = SimpleNamespace(execute_reset=lambda **_: events.append('commit') or ({}, {}))
    env._episode_execution_state = lambda: lifecycle
    env._has_component_assembly = lambda: False
    def fail_capture(state, _result):
        assert state is env.state and env._defer_task_rgb_capture is False
        events.append('capture')
        raise RuntimeError('capture failed')
    def on_failure(phase, error):
        events.append((phase, str(error)))
    with pytest.raises(RuntimeError, match='capture failed'):
        env._execute_reset_operations(lambda: {'after_commit': fail_capture, 'on_failure': on_failure})
    assert events == ['commit', 'capture', ('task_rgb_capture_after_reset_commit', 'capture failed')]


def test_reset_task_facts_prefer_formal_config_and_keep_typed_fallback():
    from task_env.environment.reference_binding import selected_task_reset_identity

    class NoRecipeLookup(dict):
        def get(self, key, default=None):
            raise AssertionError('formal task must not infer identity from recipe')

    env = SimpleNamespace(config=SimpleNamespace(task=SimpleNamespace(
        task_uid='formal-task', success_definition='formal-success')),
        value=NoRecipeLookup(), artifact=object(), uid='environment')
    assert selected_task_reset_identity(env) == ('formal-task', 'formal-success')
    env.config = None
    env.value = {'task_source': SimpleNamespace(task_id='typed-task'),
                 'resolved_configuration': {'task_recipe': {'recipe': {'success_definition': 'typed-success'}}}}
    assert selected_task_reset_identity(env) == ('typed-task', 'typed-success')


def test_position_interval_record_failure_does_not_publish_new_boundary(monkeypatch):
    import pytest
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import control
    from task_env.recorders import position_metadata

    before = SimpleNamespace(control_step=0, simulation_time=0.)
    after = SimpleNamespace(control_step=1, simulation_time=.01)
    old, new = object(), object()
    env = object.__new__(SelectedReferenceEnv)
    env.__dict__.update(_uses_component_assembly=False, _execution_fault=None,
        _stopped=False, _closed=False, horizon=4, position_profile=True,
        dual_entity_position=False, session=SimpleNamespace(snapshot=lambda: after),
        _selected_controller=object(), position_profiles=(SimpleNamespace(requirements=object()),),
        position_plan=object(), typed_state=old, position_scene=object(),
        position_joint_bindings={}, position_frame_bindings={}, state=before,
        artifact=SimpleNamespace(timebase=SimpleNamespace(control_substeps=5, control_dt=.01)),
        recorder=SimpleNamespace(transition_count=0, observation_count=1),
        _published_position_typed_state=old, value={})
    env._position_requirements = lambda: object()
    env._publish_task_position_execution_info = lambda _info: None
    env.observation = lambda _state: ({'sample': 1}, {}, SimpleNamespace(failure=False, reward=1.))
    monkeypatch.setattr(control, 'execute_position_control_interval',
                        lambda *_args, **_kwargs: (object(), object(), object(), after, new))
    def reject_record(*_args, **_kwargs):
        raise RuntimeError('record failed after advance')
    monkeypatch.setattr(position_metadata, 'record_position_transition', reject_record)
    operations = env._prepare_position_profile(object())
    with pytest.raises(RuntimeError, match='record failed after advance'):
        env._episode_execution_state().execute_selected_interval(env, **operations)
    assert env._published_position_typed_state is old
    assert env.execution_fault.phase == 'record_position_transition'
    assert env.execution_fault.interval_completed is True
    assert env.execution_fault.transition_status == 'rejected'
