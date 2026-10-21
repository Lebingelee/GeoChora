"""One-process-per-provider C03b Stop/Outcome S2 probe for candidate and Pendulum."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from task_env import make_env
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.diagnostics.tasks.c02b_position_s2_probe import _request, _typed_hand_and_joints
from task_env.environment.types import TaskEvaluation
from task_env.recorders import (
    RecorderConfig,
    TransitionRecorder,
    TransitionRecordWrapper,
    load_structured_control_records_h5,
    load_structured_training_episode_h5,
)


def _guarded_stop(env, reason):
    counters = {"compute": 0, "apply": 0, "step": 0}
    controller_type, session_type = type(env.controller), type(env.session)
    original_compute = controller_type.compute
    original_apply = session_type.apply_control
    original_step = session_type.step

    def compute(controller, *args, **kwargs):
        if controller is env.controller:
            counters["compute"] += 1
        return original_compute(controller, *args, **kwargs)

    def apply(session, *args, **kwargs):
        if session is env.session:
            counters["apply"] += 1
        return original_apply(session, *args, **kwargs)

    def step(session, *args, **kwargs):
        if session is env.session:
            counters["step"] += 1
        return original_step(session, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(controller_type, "compute", compute))
        stack.enter_context(patch.object(session_type, "apply_control", apply))
        stack.enter_context(patch.object(session_type, "step", step))
        before = (env.state.control_step, float(env.state.simulation_time))
        result = env.stop(reason)
        repeated = env.stop("repeat-after-stop")
        after = (env.state.control_step, float(env.state.simulation_time))
        if before != after or counters != {"compute": 0, "apply": 0, "step": 0}:
            raise AssertionError(f"Stop changed clock or executed control: {before}, {after}, {counters}")
        try:
            env.step(object())
        except RuntimeError:
            pass
        else:
            raise AssertionError("step after Stop was accepted")
        if counters != {"compute": 0, "apply": 0, "step": 0}:
            raise AssertionError(f"post-Stop refusal executed control: {counters}")
    if repeated is not result:
        raise AssertionError("repeated Stop did not return its cached EpisodeEnd")
    return result, before, counters


def _position_probe(provider: str, root: Path) -> dict[str, object]:
    candidate = build_position_candidate(root / "position-source", provider=provider, horizon=4)
    env = candidate.env
    try:
        env.reset()
        env.start_recording(root / "position-t0.h5")
        zero_end, zero_clock, zero_counts = _guarded_stop(env, "operator_pause")
        if zero_end.outcome.final_boundary != 0 or zero_end.outcome.end_reason != "external_stop":
            raise AssertionError("T=0 Stop outcome does not identify boundary zero")
        zero_saved = env.finish_recording("external_stop")
        zero_read = load_structured_control_records_h5(zero_saved["path"])
        zero_training = load_structured_training_episode_h5(zero_saved["path"])
        if zero_read["transition_count"] != 0 or zero_read["observation_count"] != 1:
            raise AssertionError("T=0 H5 did not preserve T/T+1")
        if zero_read["boundary_events"] != (zero_end.boundary_event,) or zero_read["outcome"] != zero_end.outcome:
            raise AssertionError("T=0 Event/Outcome did not roundtrip")
        if zero_training["actions"] != () or zero_training["bootstrap_allowed"] is not True:
            raise AssertionError("T=0 training consumer lost Stop bootstrap")
        try:
            env.finish_recording("external_stop")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Position recording finalizer ran twice")

        # Keep the established selected-success behavior: it is observable but
        # does not terminate this Position candidate's external control route.
        env.binding = replace(
            env.binding,
            evaluate=lambda _state, _semantics: TaskEvaluation(
                0.0, success=True, failure=False,
            ),
        )
        _obs, reset_info = env.reset()
        if reset_info.get("previous_episode_end_v1", {}).get("outcome", {}).get("final_boundary") != 0:
            raise AssertionError("reset omitted the prior T=0 EpisodeEnd receipt")
        env.start_recording(root / "position-t1.h5")
        hand_pose = _typed_hand_and_joints(env)[1]
        request = _request(env.position_plan, hand_pose, 1.0)
        result = env.step(request)
        if result[2:4] != (False, False) or result[4]["is_success"] is not True:
            raise AssertionError("selected success was incorrectly converted to a step terminal")
        if (env.recorder.transition_count, env.recorder.observation_count) != (1, 2):
            raise AssertionError("Position live recorder did not preserve one T/T+1 transition")
        one_end, one_clock, one_counts = _guarded_stop(env, "operator_pause")
        if one_end.outcome.final_boundary != 1 or one_end.outcome.task_success is not True:
            raise AssertionError("external Stop lost its final boundary or task success")
        one_saved = env.finish_recording("external_stop")
        one_read = load_structured_control_records_h5(one_saved["path"])
        one_training = load_structured_training_episode_h5(one_saved["path"])
        if one_read["transition_count"] != 1 or one_read["observation_count"] != 2:
            raise AssertionError("one-transition H5 did not preserve T/T+1")
        if one_read["boundary_events"][-1] != one_end.boundary_event or one_read["outcome"] != one_end.outcome:
            raise AssertionError("one-transition Event/Outcome did not roundtrip")
        if one_training["transition_terminated"] != (False,) or one_training["transition_truncated"] != (False,):
            raise AssertionError("external Stop rewrote the already-returned transition flags")
        if one_training["transition_bootstrap_allowed"] != (True,) or one_training["bootstrap_allowed"] is not True:
            raise AssertionError("training consumer did not expose external Stop bootstrap")

        return {
            "profile_id": env.controller.profile_id,
            "controller_identity": env.controller.identity,
            "source_closure_digest": env.value["source"].source_closure_digest,
            "T0": {"clock": zero_clock, "stop_execution_counts": zero_counts,
                   "observations": zero_read["observation_count"], "transitions": zero_read["transition_count"],
                   "event": zero_read["boundary_events"][0].to_mapping(),
                   "outcome": zero_read["outcome"].to_mapping()},
            "T1": {"clock": one_clock, "stop_execution_counts": one_counts,
                   "observations": one_read["observation_count"], "transitions": one_read["transition_count"],
                   "transition_flags": {"terminated": one_training["transition_terminated"],
                                        "truncated": one_training["transition_truncated"]},
                   "training_bootstrap": one_training["transition_bootstrap_allowed"],
                   "event": one_read["boundary_events"][-1].to_mapping(),
                   "outcome": one_read["outcome"].to_mapping()},
        }
    finally:
        env.close()


def _position_fault_stop_probe(provider: str, root: Path) -> dict[str, object]:
    candidate = build_position_candidate(root / "position-fault-source", provider=provider, horizon=2)
    env = candidate.env
    try:
        env.reset()
        env.start_recording(root / "position-fault.h5")
        request = _request(env.position_plan, _typed_hand_and_joints(env)[1], 1.0)
        original = TransitionRecorder.append_transition

        def reject_append(recorder, *args, **kwargs):
            if recorder is env.recorder:
                raise RuntimeError("injected c03b recorder append failure")
            return original(recorder, *args, **kwargs)

        with patch.object(TransitionRecorder, "append_transition", reject_append):
            try:
                env.step(request)
            except RuntimeError as error:
                if "injected c03b recorder append failure" not in str(error):
                    raise
            else:
                raise AssertionError("injected Position recorder failure was not raised")
        physical_fault_clock = (int(env.state.control_step), float(env.state.simulation_time))
        if physical_fault_clock[0] != 1 or env.recorder.transition_count != 0:
            raise AssertionError("fault fixture did not separate physical progress from recorded T")
        end, before, counts = _guarded_stop(env, "fault_after_step")
        if end.outcome.end_reason != "execution_fault" or end.outcome.final_boundary != 0:
            raise AssertionError("fault Stop did not finish at the last complete published T=0 boundary")
        if end.outcome.bootstrap_allowed or end.boundary_event.boundary_index != 0:
            raise AssertionError("fault Stop exposed bootstrap or a pseudo boundary")
        if end.boundary_event.payload["fault"]["transition_status"] != "rejected":
            raise AssertionError("fault Event lost its rejected transition evidence")
        saved = env.finish_recording("execution_fault")
        loaded = load_structured_control_records_h5(saved["path"])
        if loaded["transition_count"] != 0 or loaded["observation_count"] != 1:
            raise AssertionError("fault finalization inserted a pseudo transition")
        if loaded["outcome"] != end.outcome or loaded["boundary_events"] != (end.boundary_event,):
            raise AssertionError("fault Event/Outcome did not roundtrip")
        return {
            "observed_runtime_clock_after_failed_record": physical_fault_clock,
            "stop_clock": before,
            "stop_execution_counts": counts,
            "recorded_T": loaded["transition_count"],
            "recorded_T_plus_1": loaded["observation_count"],
            "outcome": loaded["outcome"].to_mapping(),
            "event": loaded["boundary_events"][0].to_mapping(),
        }
    finally:
        env.close()


def _pendulum_probe(provider: str) -> dict[str, object]:
    if provider != "geophys":
        return {
            "status": "NOT_ADMITTED",
            "reason": "generic TaskEnv ExecutionPlan currently declares the GeoPhys provider only",
        }
    env = make_env(
        "pendulum-v1",
        config={"runtime": {"backend": "cpu"}, "episode": {"horizon": 3}},
    )
    try:
        env.reset(seed=37)
        zero_before = (env._elapsed_steps, float(env._last_snapshot.simulation_time))
        zero_end = env.stop("operator_pause")
        zero_after = (env._elapsed_steps, float(env._last_snapshot.simulation_time))
        if zero_before != zero_after or zero_end.outcome.final_boundary != 0:
            raise AssertionError("Pendulum T=0 Stop changed its public boundary clock")
        try:
            env.step(np.asarray([0.0], dtype=np.float32))
        except RuntimeError:
            pass
        else:
            raise AssertionError("Pendulum accepted a step after T=0 Stop")
        repeated = env.stop("repeat")
        if repeated is not zero_end:
            raise AssertionError("Pendulum repeated Stop changed its EpisodeEnd")

        _observation, info = env.reset(seed=37)
        if info.get("previous_episode_end_v1", {}).get("outcome", {}).get("final_boundary") != 0:
            raise AssertionError("Pendulum reset omitted the prior Stop outcome")
        step = env.step(np.asarray([0.0], dtype=np.float32))
        before = (int(step[4]["elapsed_steps"]), float(step[4]["simulation_time_s"]))
        one_end = env.stop("operator_pause")
        after = (int(env._elapsed_steps), float(env._last_snapshot.simulation_time))
        if before != after or one_end.outcome.final_boundary != 1:
            raise AssertionError("Pendulum external Stop advanced or misidentified the boundary")
        if step[2:4] != (False, False):
            raise AssertionError("Pendulum returned an unexpected transition flag before Stop")
        try:
            env.step(np.asarray([0.0], dtype=np.float32))
        except RuntimeError:
            pass
        else:
            raise AssertionError("Pendulum accepted a step after external Stop")
        return {
            "T0": {"clock_before": zero_before, "clock_after": zero_after,
                   "outcome": zero_end.outcome.to_mapping()},
            "T1": {"clock_before": before, "clock_after": after,
                   "returned_transition_flags": {"terminated": step[2], "truncated": step[3]},
                   "outcome": one_end.outcome.to_mapping()},
        }
    finally:
        env.close()


def _pendulum_v2_wrapper_guard(provider: str) -> dict[str, object]:
    from task_env.environment.types import StageUnavailableError

    if provider != "geophys":
        return {
            "status": "NOT_ADMITTED",
            "reason": "generic TaskEnv ExecutionPlan currently declares the GeoPhys provider only",
        }
    base = make_env(
        "pendulum-v1",
        config={"runtime": {"backend": "cpu"}, "episode": {"horizon": 3}},
    )
    wrapper = TransitionRecordWrapper(base, RecorderConfig(schema_version="v2"))
    try:
        wrapper.reset(seed=41)
        wrapper.start_record()
        wrapper.step(wrapper.action_space.sample())
        before = (base._elapsed_steps, float(base._last_snapshot.simulation_time))
        try:
            wrapper.stop("operator_pause")
        except StageUnavailableError:
            pass
        else:
            raise AssertionError("v2 active recorder accepted Stop without an outcome contract")
        after = (base._elapsed_steps, float(base._last_snapshot.simulation_time))
        if before != after or wrapper.recorder.transition_count != 1:
            raise AssertionError("v2 Stop rejection mutated physics or recording")
        wrapper.end_record()  # Manual v2 finalization is an explicit non-episode record.
        return {"status": "explicitly_rejected_active_v2_stop", "clock": after,
                "transitions": wrapper.recorder.frozen.transition_count}
    finally:
        if wrapper.record_state.value == "recording":
            wrapper.end_record()
        wrapper.close()


def run(provider: str, workspace: Path) -> dict[str, object]:
    root = workspace.resolve() / provider
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "geochora.c03b-stop-s2-v1",
        "status": "PASS_BOUNDED_STOP_OUTCOME_S2",
        "provider": provider,
        "backend": "cpu",
        "position_candidate": _position_probe(provider, root),
        "position_fault_after_physical_step": _position_fault_stop_probe(provider, root),
        "pendulum": _pendulum_probe(provider),
        "pendulum_v2_wrapper": _pendulum_v2_wrapper_guard(provider),
        "limits": [
            "Position source is the versioned C02b candidate; this does not change frozen A05.",
            "Pendulum is tested through the scalar TaskEnv lifecycle, not H5 v3 structured controls.",
            "No C02c, dual-Entity, Assembly, R1 force-refresh, or complete Expert claim is made.",
        ],
    }
    output = root / "c03b-stop-s2-report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.provider, args.workspace)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
