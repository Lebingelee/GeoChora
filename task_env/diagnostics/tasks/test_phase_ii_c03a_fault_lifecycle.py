"""C03a fault receipts for the existing scalar lifecycle owner."""

import numpy as np
import pytest

from task_env.environment.lifecycle import SingleTaskLifecycleAdapter
from task_env.environment.types import (
    AppliedControl,
    ControlCommand,
    ExecutionFaultV1,
    RuntimeSnapshot,
)


class FaultInjectingRuntime:
    def __init__(self):
        self.time = 0.0
        self.apply_calls = 0
        self.step_calls = 0
        self.close_calls = 0
        self.fail_apply = False
        self.fail_before_step = False
        self.fail_after_substeps = None
        self.readback_failures = 0

    def apply_reset_state(self, _state):
        self.time = 0.0

    def read_snapshot(self, _request):
        if self.readback_failures:
            self.readback_failures -= 1
            raise RuntimeError("injected snapshot readback failure")
        return RuntimeSnapshot(
            qpos=np.asarray([0.0]),
            qvel=np.asarray([0.0]),
            simulation_time=self.time,
        )

    def apply_control(self, command):
        self.apply_calls += 1
        if self.fail_apply:
            raise RuntimeError("injected control application failure")
        return AppliedControl(command.actuator_ctrl, command.actuator_ctrl, False)

    def step(self, *, substeps):
        self.step_calls += 1
        if self.fail_before_step:
            raise RuntimeError("injected physics failure before first substep")
        for index in range(substeps):
            self.time += 0.1
            if self.fail_after_substeps == index + 1:
                raise RuntimeError("injected physics failure after a partial interval")

    def close(self):
        self.close_calls += 1


def _command(action, _snapshot):
    value = float(action)
    vector = np.asarray([value], dtype=np.float32)
    return ControlCommand(vector, vector, vector, vector, vector, "test")


def _lifecycle(runtime, *, horizon=3):
    return SingleTaskLifecycleAdapter(
        runtime=runtime,
        task_definition=None,
        control_substeps=2,
        horizon=horizon,
        ignore_done=False,
        expected_control_dt_s=0.2,
        sample_reset_state=lambda _seed, _rng: (None, {}),
        snapshot_request=lambda: None,
        reset_components=lambda _snapshot: None,
        convert_action=_command,
        observation_fallback=lambda state: {"time": state.simulation_time},
    )


def _reset(lifecycle):
    return lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))


def test_reset_before_step_normal_step_horizon_and_terminal_guard():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime, horizon=1)
    with pytest.raises(RuntimeError, match="reset"):
        lifecycle.step(0.5)
    assert lifecycle.execution_fault is None

    reset = _reset(lifecycle)
    assert reset.snapshot.simulation_time == 0.0
    result = lifecycle.step(0.5)
    assert (result.terminated, result.truncated) == (False, True)
    assert result.elapsed_steps == 1
    assert result.snapshot.simulation_time == pytest.approx(0.2)
    calls = runtime.step_calls
    with pytest.raises(RuntimeError, match="episode end"):
        lifecycle.step(0.5)
    assert runtime.step_calls == calls


def test_control_failure_is_not_advanced_latches_and_requires_reset():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)
    runtime.fail_apply = True

    with pytest.raises(RuntimeError, match="control application"):
        lifecycle.step(0.5)
    receipt = lifecycle.execution_fault
    assert receipt is not None
    assert receipt.phase == "control_application"
    assert receipt.physical_progress == "not_advanced"
    assert receipt.simulation_time_before_s == 0.0
    assert receipt.simulation_time_after_s is None

    apply_calls, step_calls = runtime.apply_calls, runtime.step_calls
    with pytest.raises(RuntimeError, match="faulted; reset"):
        lifecycle.step(0.5)
    assert (runtime.apply_calls, runtime.step_calls) == (apply_calls, step_calls)

    runtime.fail_apply = False
    _reset(lifecycle)
    assert lifecycle.execution_fault is None
    assert lifecycle.step(0.5).elapsed_steps == 1


def test_partial_physics_advance_is_reported_and_blocks_continuation():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)
    runtime.fail_after_substeps = 1

    with pytest.raises(RuntimeError, match="partial interval"):
        lifecycle.step(0.5)
    receipt = lifecycle.execution_fault
    assert receipt is not None
    assert receipt.phase == "physics_step"
    assert receipt.physical_progress == "partially_advanced"
    assert receipt.simulation_time_before_s == 0.0
    assert receipt.simulation_time_after_s == pytest.approx(0.1)

    calls = runtime.step_calls
    with pytest.raises(RuntimeError, match="faulted; reset"):
        lifecycle.step(0.5)
    assert runtime.step_calls == calls


def test_unreadable_boundary_after_failed_step_is_reported_as_unknown():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)
    runtime.fail_after_substeps = 1
    runtime.readback_failures = 1

    with pytest.raises(RuntimeError, match="partial interval"):
        lifecycle.step(0.5)
    receipt = lifecycle.execution_fault
    assert receipt is not None
    assert receipt.physical_progress == "unknown"
    assert receipt.readback_error.startswith("RuntimeError:")


def test_observer_count_without_public_clock_does_not_claim_physical_progress():
    receipt = ExecutionFaultV1.from_exception(
        "physics_step",
        RuntimeError("observer returned but boundary clock is unavailable"),
        expected_control_dt_s=0.2,
        interval_attempted=True,
        observer_confirmed_substeps=2,
        recorder_confirmed_substeps=2,
        native_substeps_expected=2,
        transition_status="incomplete",
    )
    assert receipt.physical_progress == "unknown"
    assert receipt.observer_confirmed_substeps == 2
    assert receipt.recorder_confirmed_substeps == 2
    assert receipt.transition_status == "incomplete"


def test_public_clock_conflicting_with_completed_interval_is_unknown():
    receipt = ExecutionFaultV1.from_exception(
        "snapshot_readback",
        RuntimeError("returned interval disagrees with public clock"),
        control_step_before=0,
        control_step_after=1,
        simulation_time_before_s=0.0,
        simulation_time_after_s=0.1,
        expected_control_dt_s=0.2,
        interval_attempted=True,
        interval_completed=True,
    )
    assert receipt.physical_progress == "unknown"
    assert receipt.interval_completed


def test_recorder_count_conflicting_with_observer_count_is_unknown():
    receipt = ExecutionFaultV1.from_exception(
        "physics_step",
        RuntimeError("Recorder evidence exceeds observer evidence"),
        control_step_before=0,
        control_step_after=0,
        simulation_time_before_s=0.0,
        simulation_time_after_s=0.2,
        expected_control_dt_s=0.2,
        interval_attempted=True,
        observer_confirmed_substeps=1,
        recorder_confirmed_substeps=2,
        native_substeps_expected=2,
    )
    assert receipt.physical_progress == "unknown"
    assert receipt.observer_confirmed_substeps == 1
    assert receipt.recorder_confirmed_substeps == 2


def test_public_clock_shorter_than_confirmed_substep_evidence_is_unknown():
    receipt = ExecutionFaultV1.from_exception(
        "physics_step",
        RuntimeError("public clock advances less than observer evidence requires"),
        control_step_before=0,
        control_step_after=0,
        simulation_time_before_s=0.0,
        simulation_time_after_s=0.05,
        expected_control_dt_s=0.2,
        interval_attempted=True,
        observer_confirmed_substeps=2,
        recorder_confirmed_substeps=2,
        native_substeps_expected=4,
    )
    assert receipt.physical_progress == "unknown"
    assert receipt.observer_confirmed_substeps == 2
    assert receipt.recorder_confirmed_substeps == 2


def test_public_clock_and_substep_evidence_remain_separate():
    receipt = ExecutionFaultV1.from_exception(
        "physics_step",
        RuntimeError("final physical step advanced before throwing"),
        control_step_before=0,
        control_step_after=0,
        simulation_time_before_s=1.0,
        simulation_time_after_s=1.2,
        expected_control_dt_s=0.2,
        interval_attempted=True,
        observer_confirmed_substeps=1,
        recorder_confirmed_substeps=1,
        native_substeps_expected=2,
        transition_status="incomplete",
    )
    assert receipt.physical_progress == "advanced"
    assert receipt.observer_confirmed_substeps == 1
    assert receipt.recorder_confirmed_substeps == 1
    assert receipt.interval_completed is False
    assert receipt.transition_status == "incomplete"
    mapping = receipt.to_mapping()
    assert mapping["physical_progress"] == "advanced"
    assert mapping["observer_confirmed_substeps"] == 1
    assert mapping["recorder_confirmed_substeps"] == 1
    assert mapping["transition_status"] == "incomplete"


def test_physics_failure_before_advance_is_distinguished_from_partial_advance():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)
    runtime.fail_before_step = True

    with pytest.raises(RuntimeError, match="before first substep"):
        lifecycle.step(0.5)
    receipt = lifecycle.execution_fault
    assert receipt is not None
    assert receipt.phase == "physics_step"
    assert receipt.physical_progress == "not_advanced"
    assert receipt.simulation_time_before_s == receipt.simulation_time_after_s == 0.0


def test_post_physics_failures_keep_truthful_advanced_receipt():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)
    lifecycle.evaluate_task = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("injected evaluation failure")
    )

    with pytest.raises(RuntimeError, match="evaluation failure"):
        lifecycle.step(0.5)
    receipt = lifecycle.execution_fault
    assert receipt is not None
    assert receipt.phase == "task_evaluation"
    assert receipt.physical_progress == "advanced"
    assert receipt.simulation_time_after_s == pytest.approx(0.2)


def test_readback_failure_after_step_recovers_public_snapshot_for_receipt():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)
    runtime.readback_failures = 1

    with pytest.raises(RuntimeError, match="snapshot readback failure"):
        lifecycle.step(0.5)
    receipt = lifecycle.execution_fault
    assert receipt is not None
    assert receipt.phase == "snapshot_readback"
    assert receipt.physical_progress == "advanced"
    assert receipt.simulation_time_after_s == pytest.approx(0.2)
    assert receipt.readback_error is None


def test_action_conversion_error_is_retryable_before_any_state_mutation():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)

    with pytest.raises((TypeError, ValueError)):
        lifecycle.step(object())
    assert lifecycle.execution_fault is None
    assert runtime.apply_calls == runtime.step_calls == 0
    assert lifecycle.step(0.5).elapsed_steps == 1


def test_construction_failure_exposes_a_not_advanced_fault_receipt(monkeypatch):
    from task_env import make_env

    def fail_bootstrap(**_kwargs):
        raise RuntimeError("injected runtime construction failure")

    monkeypatch.setattr("task_env.runtime.bootstrap_task_runtime", fail_bootstrap)
    with pytest.raises(RuntimeError, match="runtime construction") as caught:
        make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
    receipt = caught.value.execution_fault
    assert receipt.phase == "runtime_construction"
    assert receipt.physical_progress == "not_advanced"


def test_real_pendulum_scalar_env_preserves_five_tuple_clock_and_terminal_guard():
    from task_env import make_env

    env = make_env(
        "pendulum-v1",
        config={"runtime": {"backend": "cpu"}, "episode": {"horizon": 2}},
    )
    try:
        observation, info = env.reset(seed=37)
        assert env.observation_space.contains(observation)
        assert info["elapsed_steps"] == 0
        control_dt = env.config.runtime.physics_dt * env.config.runtime.control_substeps

        action = np.asarray([0.0], dtype=np.float32)
        first = env.step(action)
        assert isinstance(first, tuple) and len(first) == 5
        assert first[2:4] == (False, False)
        assert first[4]["elapsed_steps"] == 1
        assert env._last_snapshot.simulation_time == pytest.approx(control_dt)

        second = env.step(action)
        assert second[2:4] == (False, True)
        assert second[4]["elapsed_steps"] == 2
        assert env._last_snapshot.simulation_time == pytest.approx(2 * control_dt)
        calls = env.execution_fault
        assert calls is None
        with pytest.raises(RuntimeError, match="episode end"):
            env.step(action)
        assert env._last_snapshot.simulation_time == pytest.approx(2 * control_dt)

        env.reset(seed=37)
        env._format_step_result = lambda *_args: (_ for _ in ()).throw(
            RuntimeError("injected Gymnasium result packing failure")
        )
        with pytest.raises(RuntimeError, match="result packing failure"):
            env.step(action)
        assert env.execution_fault.phase == "gymnasium_result"
        assert env.execution_fault.physical_progress == "advanced"
        advanced_time = env._last_snapshot.simulation_time
        with pytest.raises(RuntimeError, match="faulted; reset"):
            env.step(action)
        assert env._last_snapshot.simulation_time == advanced_time
        stop_end = env.stop("after_result_packaging_fault")
        assert stop_end.outcome.end_reason == "execution_fault"
        assert stop_end.outcome.final_boundary == 0
        assert stop_end.outcome.bootstrap_allowed is False
        assert stop_end.boundary_event.payload["fault"]["physical_progress"] == "advanced"
        assert env._last_snapshot.simulation_time == advanced_time
    finally:
        env.close()


def test_classic_env_and_lifecycle_share_episode_close_state():
    from task_env.environment.env import BaseTaskEnv
    from task_env.environment.lifecycle import EpisodeExecutionState

    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    env = object.__new__(BaseTaskEnv)
    env._episode_state = lifecycle._episode_state
    env._task_lifecycle = lifecycle
    env._runtime = runtime
    env._runtime_assembly = None
    env._ui_render_provider = None
    env._sensor_provider = None
    env._last_episode_end = None
    assert isinstance(env._episode_state, EpisodeExecutionState)
    assert env._episode_state is lifecycle._episode_state
    _reset(lifecycle)
    lifecycle.step(0.5)
    env.close()
    env.close()
    assert env._closed and lifecycle._closed
    assert runtime.close_calls == 1
    assert env._last_episode_end is not None
    with pytest.raises(RuntimeError, match='closed'):
        lifecycle.step(0.5)


@pytest.mark.parametrize(('uid', 'size', 'actuators', 'obs_size'), [
    ('empty-v1', 0, 0, None),
    ('pendulum-v1', 1, 1, 3),
    ('two-wheel-balance-v1', 3, 2, 7),
])
def test_classic_public_env_lifecycle_uses_shared_episode_state_without_engine(
        monkeypatch, uid, size, actuators, obs_size):
    """Real public Env/reset/step/close with a provider-free runtime boundary."""
    from types import SimpleNamespace
    from task_env import make_env
    from task_env.environment.lifecycle import EpisodeExecutionState
    from task_env.environment.types import EpisodePhysicsState
    import task_env.runtime as runtime_module

    names = SimpleNamespace(
        joints={'pendulum_hinge': 0, 'chassis_pitch': 0,
                'left_wheel_hinge': 1, 'right_wheel_hinge': 2},
        actuators={'pendulum_torque': 0, 'left_wheel_torque': 0, 'right_wheel_torque': 1},
    )
    refs = SimpleNamespace(names=names, agents={}, objects={})
    compiled = SimpleNamespace(
        references=refs,
        scene_model=SimpleNamespace(joint_data={'jnt_qposadr': np.arange(size),
                                                 'jnt_dofadr': np.arange(size),
                                                 'n_actuators': actuators}),
    )

    class Runtime:
        def __init__(self, dt):
            self.dt = dt
            self.time = 0.0
            self.close_calls = 0
            self.fail_apply = False
            self.initial_state = EpisodePhysicsState(
                np.zeros(size), np.zeros(size), np.zeros(size),
                np.zeros(actuators), np.zeros(0),
            )
            self.apply_reset_state(self.initial_state)

        def apply_reset_state(self, state):
            self.state = state
            self.time = 0.0

        def read_snapshot(self, _request):
            return RuntimeSnapshot(qpos=self.state.qpos, qvel=self.state.qvel,
                                   qacc=self.state.qacc, ctrl=self.state.ctrl,
                                   simulation_time=self.time)

        def apply_control(self, command):
            if self.fail_apply:
                raise RuntimeError('injected boundary control failure')
            return AppliedControl(command.actuator_ctrl, command.actuator_ctrl, False)

        def step(self, *, substeps):
            self.time += self.dt * substeps

        def close(self):
            self.close_calls += 1

    holder = {}
    def bootstrap(**kwargs):
        runtime = Runtime(kwargs['config'].runtime.physics_dt)
        holder['runtime'] = runtime
        return SimpleNamespace(boundary=runtime, compiled_scene=compiled, render_source=None)
    monkeypatch.setattr(runtime_module, 'bootstrap_task_runtime', bootstrap)
    env = make_env(uid, config={'episode': {'horizon': 2}})
    runtime = holder['runtime']
    state = env._episode_state
    assert isinstance(state, EpisodeExecutionState)
    assert state is env._task_lifecycle._episode_state
    action = np.zeros(actuators, dtype=np.float32)
    try:
        first, info = env.reset(seed=37)
        assert state.episode_id == info['episode_id']
        assert env.observation_space.contains(first)
        if obs_size is not None:
            assert first['state']['proprioception'].shape == (obs_size,)
            assert first['state']['proprioception'].dtype == np.float32
        _, _, terminated, truncated, _ = env.step(action)
        assert not terminated and not truncated
        _, _, terminated, truncated, _ = env.step(action)
        assert not terminated and truncated and state.stopped
        with pytest.raises(RuntimeError, match='episode end'):
            env.step(action)
        again, _ = env.reset(seed=37)
        if obs_size is not None:
            np.testing.assert_array_equal(first['state']['proprioception'], again['state']['proprioception'])
        runtime.fail_apply = True
        with pytest.raises(RuntimeError, match='injected boundary'):
            env.step(action)
        assert state.fault is not None
        with pytest.raises(RuntimeError, match='faulted'):
            env.step(action)
        runtime.fail_apply = False
        env.reset(seed=37)
        assert state.fault is None and not state.stopped
        env.step(action)
        def fail_publication(*_args):
            raise RuntimeError('injected public result failure')
        monkeypatch.setattr(env, '_format_step_result', fail_publication)
        with pytest.raises(RuntimeError, match='injected public result'):
            env.step(action)
        assert state.fault.phase == 'gymnasium_result'
        end = env.stop('unpublished_terminal_step')
        assert env.stop('repeated_stop') is end
        assert state.episode_end is end
        assert end.outcome.end_reason == 'execution_fault'
        assert end.outcome.final_boundary == 1
        assert end.outcome.bootstrap_allowed is False
    finally:
        env.close()
        env.close()
    assert state.closed and runtime.close_calls == 1


@pytest.mark.parametrize('uid', ('empty-v1', 'pendulum-v1', 'two-wheel-balance-v1'))
def test_classic_public_pure_construction_does_not_bootstrap(monkeypatch, uid):
    from task_env import make_env
    from task_env.environment.types import StageUnavailableError
    import task_env.runtime as runtime_module

    def forbidden_bootstrap(**_kwargs):
        raise AssertionError('pure construction started a runtime')
    monkeypatch.setattr(runtime_module, 'bootstrap_task_runtime', forbidden_bootstrap)
    env = make_env(uid, config={'episode': {'horizon': 7}}, build_runtime=False)
    try:
        assert env._runtime is None and env._task_lifecycle is None
        assert env.config.episode.horizon == 7
        with pytest.raises(StageUnavailableError, match='runtime|lifecycle'):
            env.reset(seed=5)
    finally:
        env.close()
        env.close()
    assert env._episode_state.closed


def test_failed_reset_keeps_shared_state_inactive_until_success():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    original_sampler = lifecycle._sample_reset_state
    def fail_sampling(_seed, _rng):
        raise RuntimeError('reset sample failure')
    lifecycle._sample_reset_state = fail_sampling
    with pytest.raises(RuntimeError, match='reset sample failure'):
        _reset(lifecycle)
    assert lifecycle._episode_state.stopped
    assert lifecycle._episode_state.fault.phase == 'reset_sampling'
    with pytest.raises(RuntimeError, match='faulted'):
        lifecycle.step(0.0)
    lifecycle._sample_reset_state = original_sampler
    _reset(lifecycle)
    assert not lifecycle._episode_state.stopped
    assert lifecycle._episode_state.fault is None
    lifecycle.close()
    assert runtime.close_calls == 1


def test_env_closes_auxiliaries_even_if_shared_runtime_lifecycle_was_closed_first():
    from types import SimpleNamespace
    from task_env.environment.env import BaseTaskEnv

    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    _reset(lifecycle)
    env = object.__new__(BaseTaskEnv)
    env._episode_state = lifecycle._episode_state
    env._task_lifecycle = lifecycle
    env._runtime = runtime
    env._runtime_assembly = None
    calls = []
    env._ui_render_provider = SimpleNamespace(close=lambda: calls.append('ui'))
    env._sensor_provider = SimpleNamespace(close=lambda: calls.append('sensor'))
    lifecycle.close()
    assert env._closed and runtime.close_calls == 1
    env.close()
    env.close()
    assert calls == ['ui', 'sensor']
    assert runtime.close_calls == 1


@pytest.mark.parametrize('uid', ('empty-v1', 'pendulum-v1', 'two-wheel-balance-v1'))
def test_classic_scalar_render_routes_and_closes_auxiliary_provider_without_engine(uid):
    from task_env import make_env

    class RenderProbe:
        def __init__(self):
            self.renders = []
            self.closes = 0
        def render(self, *, mode, snapshot):
            self.renders.append((mode.value, snapshot))
            return np.zeros((2, 2, 3), dtype=np.uint8)
        def close(self):
            self.closes += 1

    env = make_env(uid, render_mode='rgb_array', build_runtime=False)
    provider = RenderProbe()
    env._ui_render_provider = provider
    try:
        frame = env.render()
        assert frame.shape == (2, 2, 3) and frame.dtype == np.uint8
        assert provider.renders == [('rgb_array', None)]
        with pytest.raises(ValueError, match='fixed at construction'):
            env.render(mode='human')
    finally:
        env.close()
        env.close()
    assert provider.closes == 1
