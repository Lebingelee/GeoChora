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
