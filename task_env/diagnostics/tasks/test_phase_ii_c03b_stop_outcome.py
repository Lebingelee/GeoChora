"""C03b S1: independent Stop, outcome policy, wrapper and H5 consumer guards."""

from __future__ import annotations

import numpy as np
import pytest
import gymnasium as gym
from gymnasium.spaces import Box

from task_env.diagnostics.tasks.test_phase_ii_c03a_fault_lifecycle import (
    FaultInjectingRuntime,
    _command,
)
from task_env.environment.lifecycle import SingleTaskLifecycleAdapter
from task_env.environment.task_definition import EpisodeTerminationPolicyV1
from task_env.environment.types import StageUnavailableError, TaskEvaluation
from task_env.recorders import (
    RecorderConfig,
    TransitionRecordWrapper,
    TransitionRecorder,
    load_structured_training_episode_h5,
)
from task_env.trajectory.canonical.episode import make_episode_end_v1


def _lifecycle(runtime, *, horizon=3, policy=None):
    return SingleTaskLifecycleAdapter(
        runtime=runtime,
        task_definition=None,
        control_substeps=2,
        horizon=horizon,
        ignore_done=False,
        sample_reset_state=lambda _seed, _rng: (None, {}),
        snapshot_request=lambda: None,
        reset_components=lambda _snapshot: None,
        convert_action=_command,
        observation_fallback=lambda state: {"time": state.simulation_time},
        termination_policy=policy,
    )


def test_stop_before_reset_and_after_close_reject_without_runtime_calls():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    with pytest.raises(RuntimeError, match=r"reset\(\) must complete"):
        lifecycle.stop()
    assert (runtime.apply_calls, runtime.step_calls) == (0, 0)
    lifecycle.close()
    assert runtime.close_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        lifecycle.stop()


def test_t0_stop_is_idempotent_nonphysical_and_blocks_later_step():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    before = (runtime.time, runtime.apply_calls, runtime.step_calls)

    first = lifecycle.stop()
    second = lifecycle.stop("ignored-after-stop")

    assert first is second
    assert first.outcome.end_reason == "external_stop"
    assert (first.outcome.final_boundary, first.outcome.terminated, first.outcome.truncated) == (0, False, True)
    assert first.outcome.bootstrap_allowed is True
    assert first.boundary_event.boundary_index == 0
    assert (runtime.time, runtime.apply_calls, runtime.step_calls) == before
    with pytest.raises(RuntimeError, match="episode end"):
        lifecycle.step(0.2)
    assert (runtime.time, runtime.apply_calls, runtime.step_calls) == before


def test_task_terminal_horizon_and_reset_stop_keep_flags_and_outcomes_separate():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime, horizon=1)
    lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    lifecycle.evaluate_task = lambda **_kwargs: TaskEvaluation(0.0, success=True, failure=True)
    result = lifecycle.step(0.2)
    # The legacy Gymnasium flags remain the result of the pre-existing resolver.
    assert (result.terminated, result.truncated) == (True, True)
    assert result.episode_end.outcome.end_reason == "task_terminal"
    assert (result.episode_end.outcome.terminated, result.episode_end.outcome.truncated) == (True, False)
    assert result.episode_end.outcome.bootstrap_allowed is False
    assert lifecycle.stop().outcome == result.episode_end.outcome
    assert lifecycle.stop() is result.episode_end
    calls = (runtime.time, runtime.apply_calls, runtime.step_calls)
    with pytest.raises(RuntimeError, match="episode end"):
        lifecycle.step(0.2)
    assert (runtime.time, runtime.apply_calls, runtime.step_calls) == calls

    reset = lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    assert reset.previous_episode_end is result.episode_end

    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime, horizon=1)
    lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    horizon_result = lifecycle.step(0.2)
    assert horizon_result.terminated is False and horizon_result.truncated is True
    assert horizon_result.episode_end.outcome.end_reason == "horizon_reached"
    assert horizon_result.episode_end.outcome.bootstrap_allowed is True

    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime, horizon=2)
    lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    lifecycle.evaluate_task = lambda **_kwargs: TaskEvaluation(0.0, success=False, failure=False)
    lifecycle.step(0.2)
    before_reset = (runtime.time, runtime.apply_calls, runtime.step_calls)
    reset = lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    assert reset.previous_episode_end.outcome.end_reason == "external_stop"
    assert reset.previous_episode_end.outcome.final_boundary == 1
    assert reset.previous_episode_end.boundary_event.payload["requested_reason"] == "reset"
    assert before_reset == (0.2, 1, 1)
    assert (runtime.time, runtime.apply_calls, runtime.step_calls) == (0.0, 1, 1)


def test_fault_stop_uses_last_complete_boundary_and_does_not_add_transition():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    runtime.fail_after_substeps = 1
    with pytest.raises(RuntimeError, match="partial interval"):
        lifecycle.step(0.2)
    before = (runtime.time, runtime.apply_calls, runtime.step_calls)
    episode_end = lifecycle.stop()
    assert episode_end.outcome.end_reason == "execution_fault"
    assert episode_end.outcome.final_boundary == 0
    assert episode_end.outcome.bootstrap_allowed is False
    assert episode_end.boundary_event.payload["fault"]["physical_progress"] == "unknown"
    assert episode_end.boundary_event.payload["fault"]["simulation_time_after_s"] == pytest.approx(0.1)
    assert episode_end.boundary_event.payload["simulation_time_s"] == 0.0
    assert (runtime.time, runtime.apply_calls, runtime.step_calls) == before


def test_termination_policy_defaults_and_external_stop_constraints():
    assert EpisodeTerminationPolicyV1().to_mapping()["bootstrap_on_horizon"] is True
    with pytest.raises(ValueError, match="cannot bootstrap"):
        EpisodeTerminationPolicyV1(external_stop_terminated=True)
    policy = EpisodeTerminationPolicyV1(
        terminate_on_success=False,
        external_stop_terminated=True,
        bootstrap_on_external_stop=False,
    )
    assert policy.terminate_on_success is False
    assert policy.external_stop_terminated is True


def test_close_finalizes_the_active_episode_once_before_runtime_teardown():
    runtime = FaultInjectingRuntime()
    lifecycle = _lifecycle(runtime)
    lifecycle.reset(seed=7, options=None, rng=np.random.default_rng(7))
    lifecycle.close()
    assert lifecycle.episode_end.outcome.end_reason == "external_stop"
    assert lifecycle.episode_end.boundary_event.payload["requested_reason"] == "environment_close"
    assert runtime.close_calls == 1
    lifecycle.close()
    assert runtime.close_calls == 1


def test_position_close_stops_and_finalizes_active_v3_recording_once(tmp_path, monkeypatch):
    pytest.importorskip("scene", reason="GeoPhys public Scene importer is required")
    from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
    from task_env.recorders import load_structured_control_records_h5

    candidate = build_position_candidate(tmp_path / "position-close-source", provider="geophys", horizon=2)
    env = candidate.env
    finalize_calls = []
    original_end_episode = TransitionRecorder.end_episode

    def counted_end_episode(recorder, *args, **kwargs):
        if recorder is env.recorder:
            finalize_calls.append((args, kwargs))
        return original_end_episode(recorder, *args, **kwargs)

    try:
        env.reset()
        env.start_recording(tmp_path / "position-close.h5")
        monkeypatch.setattr(TransitionRecorder, "end_episode", counted_end_episode)
        env.close()
        env.close()
        assert len(finalize_calls) == 1
        assert env.recorder.frozen is not None
        loaded = load_structured_control_records_h5(env.recording_path)
        assert loaded["transition_count"] == 0
        assert loaded["observation_count"] == 1
        assert loaded["outcome"].end_reason == "external_stop"
        assert loaded["boundary_events"][-1].event_type == "episode_ended"
        assert loaded["boundary_events"][-1].boundary_index == 0
    finally:
        env.close()


class _V3FixtureEnv(gym.Env):
    """Tiny declared structured-control source for the wrapper's public contract."""

    supports_structured_control_recording = True
    observation_space = Box(-10.0, 10.0, shape=(1,), dtype=np.float32)
    action_space = Box(-1.0, 1.0, shape=(8,), dtype=np.float32)

    def __init__(self):
        self.steps = 0
        self.stop_calls = 0
        self.reset_calls = 0
        self.values = (0.1, 0.2, 0.3, 1.0, 0.0, 0.0, 0.0, 0.5)

    def get_record_metadata(self):
        components = ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")
        return {
            "env_metadata": {
                "env_name": "fixture-v3", "task_name": "fixture", "task_version": "1",
                "scene_uid": "fixture", "agent_uids": ("panda-main",),
                "action_schema": {
                    "schema_id": "panda-action-v1", "schema_version": 1,
                    "controller_kind": "absolute_pose", "reference": "world",
                    "components": components,
                },
                "observation_schema": {"leaf_specs": [{"path": "obs", "semantic": "state"}]},
            },
            "universal_action_schema": {
                "version": "panda-universal-action-v1", "dimension": 8,
                "components": components,
            },
        }

    def reset(self, **_kwargs):
        self.reset_calls += 1
        self.steps = 0
        return np.zeros(1, dtype=np.float32), {"seed": 1}

    def step(self, _action):
        from task_env.diagnostics.tasks.test_phase_ii_c05a_structured_recording import _control

        self.steps += 1
        action = np.asarray(self.values, dtype=np.float32)
        info = {
            "external_action": action,
            "universal_action": action,
            "is_success": False,
            "structured_control_transition": _control(self.values),
        }
        return np.asarray([self.steps], dtype=np.float32), 0.0, False, False, info

    def stop(self, reason="external_stop"):
        self.stop_calls += 1
        return make_episode_end_v1(
            episode_id="fixture-episode", final_boundary=self.steps,
            end_reason="external_stop", terminated=False, truncated=True,
            bootstrap_allowed=True, source="fixture",
            payload={"requested_reason": reason, "control_step": self.steps,
                     "simulation_time_s": self.steps * 0.01},
        )

    def close(self):
        pass


def test_wrapper_v2_rejects_stop_and_reset_before_mutating_active_recording():
    env = _V3FixtureEnv()
    wrapper = TransitionRecordWrapper(env, RecorderConfig(schema_version="v2"))
    wrapper.reset()
    wrapper.start_record()
    reset_calls = env.reset_calls
    with pytest.raises(RuntimeError, match="active recording"):
        wrapper.reset()
    assert env.reset_calls == reset_calls
    with pytest.raises(StageUnavailableError, match="v2 recording"):
        wrapper.stop()
    assert env.stop_calls == 0
    assert wrapper.recorder.transition_count == 0


def test_wrapper_v3_stop_finalizes_event_outcome_and_training_bootstrap(tmp_path):
    from task_env.diagnostics.tasks.test_phase_ii_c05a_structured_recording import (
        COMPONENTS,
        ACTION_SCHEMA,
    )

    env = _V3FixtureEnv()
    wrapper = TransitionRecordWrapper(
        env, RecorderConfig(schema_version="v3", max_transitions=4),
    )
    try:
        wrapper.reset()
        wrapper.start_record()
        wrapper.step(np.asarray(env.values, dtype=np.float32))
        end = wrapper.stop("operator_pause")
        assert end.outcome.final_boundary == 1
        assert wrapper.recorder.frozen.terminated == (False,)
        assert wrapper.recorder.frozen.truncated == (False,)
        assert wrapper.stop("repeat") is end
        assert env.stop_calls == 1
        path = wrapper.save_h5(tmp_path, "c03b-wrapper-v3.h5")
        training = load_structured_training_episode_h5(path)
        assert training["actions"] == (env.values,)
        assert training["transition_terminated"] == (False,)
        assert training["transition_truncated"] == (False,)
        assert training["transition_bootstrap_allowed"] == (True,)
        assert training["end_reason"] == "external_stop"
        assert training["bootstrap_allowed"] is True
        assert len(training["actions"][0]) == len(COMPONENTS) == 8
        assert ACTION_SCHEMA == "panda-action-v1"
    finally:
        wrapper.close()


def test_v3_wrapper_rejects_undeclared_environment():
    env = _V3FixtureEnv()
    env.supports_structured_control_recording = False
    with pytest.raises(StageUnavailableError, match="explicitly publishes"):
        TransitionRecordWrapper(env, RecorderConfig(schema_version="v3"))


def test_recorder_finalization_is_exactly_once_and_validates_event_before_mutation():
    recorder = TransitionRecorder(RecorderConfig(schema_version="v3"))
    recorder.begin_episode(np.zeros(1), {"seed": 1}, {"universal_action_schema": {"dimension": 8}})
    end = make_episode_end_v1(
        episode_id="episode", final_boundary=0, end_reason="external_stop",
        terminated=False, truncated=True, bootstrap_allowed=True, source="test",
    )
    with pytest.raises(ValueError, match="reason"):
        recorder.end_episode("wrong", outcome=end.outcome, end_event=end.boundary_event)
    assert recorder.active and recorder.transition_count == 0 and recorder.observation_count == 1
    recorder.end_episode("external_stop", outcome=end.outcome, end_event=end.boundary_event)
    assert not recorder.active
    with pytest.raises(RuntimeError, match="no active recording"):
        recorder.end_episode("external_stop", outcome=end.outcome, end_event=end.boundary_event)
