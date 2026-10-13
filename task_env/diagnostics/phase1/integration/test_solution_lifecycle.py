"""Fast provider-free tests for Canonical Solution lifecycle v1 / NutAssembly v2."""

import copy

import numpy as np
from task_env.tasks.canonical_solution_lifecycle import (
    CanonicalSolutionLifecycle,
    SolutionCompletionPolicy,
)


class _Raises:
    def __init__(self, expected, match):
        self.expected, self.match = expected, match

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if kind is None:
            raise AssertionError(f"expected {self.expected.__name__}")
        if not issubclass(kind, self.expected):
            return False
        if self.match not in str(error):
            raise AssertionError(f"{self.match!r} not in {str(error)!r}")
        return True


def _raises(expected, match):
    return _Raises(expected, match)
from task_env.tasks.nut_assembly.canonical_solution import (
    CanonicalNutAssemblyConfig,
    NutAssemblyCanonicalSolutionV1,
)
from task_env.tasks.nut_assembly.canonical_solution_v2 import NutAssemblyCanonicalSolutionV2


def _clock(step=0, time_s=0.0):
    return {"control_step": step, "simulation_time_s": time_s}


def _info(*, success=False, opening=0.02, failure=False, **clock):
    return {
        **clock,
        "is_success": success,
        "task_failure": failure,
        "task_metrics": {
            "task_success": success,
            "task_failure": failure,
            "gripper_opening": opening,
            "grasped_nut": False,
            "lifted_nut": False,
            "hovered_over_peg": False,
            "inserted_on_peg": success,
        },
    }


def _observation(ee=(0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)):
    return {
        "state": {"ee_pose": np.asarray(ee, dtype=np.float32)},
        "privileged_state": {
            "square_nut_v1_body_pose": np.asarray([[0.1, 0.0, 0.1, 1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
            "square_peg_v1_body_pose": np.asarray([[0.2, 0.0, 0.1, 1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
        },
    }


def _solution(config=None):
    config = config or CanonicalNutAssemblyConfig()
    initial_pose = (
        0.154, 0.0, 0.22, *config.grasp_quaternion_wxyz
    )
    solution = NutAssemblyCanonicalSolutionV2(
        config=config, control_dt=0.1
    )
    solution.reset(
        _observation(initial_pose), _info(**_clock()),
        {"action_schema": {
            "controller_kind": "absolute_pose", "reference": "world",
            "rotation_representation": "quaternion_wxyz",
        }},
    )
    return solution


def _set_stage(solution, stage, *, goal=None, actions=None, index=0):
    solution._stage_index = solution.STAGES.index(stage)
    pose = np.asarray(goal if goal is not None else _observation()["state"]["ee_pose"], dtype=float)
    solution._goal = pose.copy()
    solution._actions = np.asarray(
        actions if actions is not None else [[*pose, 1.0]], dtype=np.float32
    )
    solution._index = index
    solution._hold_ticks = 0
    solution._stable_ticks = 0


def test_on_task_success_completes_immediately():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_TASK_SUCCESS)
    assert lifecycle.observe_task_outcome(task_success=True, control_step=4, simulation_time_s=0.4)
    assert lifecycle.expert_complete and not lifecycle.expert_failed
    assert lifecycle.completion_reason == "canonical_task_success_observed"


def test_nutassembly_v1_keeps_legacy_immediate_success_semantics():
    config = CanonicalNutAssemblyConfig()
    metadata = {"action_schema": {
        "controller_kind": "absolute_pose", "reference": "world",
        "rotation_representation": "quaternion_wxyz",
    }}
    initial = _observation((0.154, 0.0, 0.22, *config.grasp_quaternion_wxyz))
    reset_success = NutAssemblyCanonicalSolutionV1(config=config, control_dt=0.1)
    reset_success.reset(initial, _info(success=True, opening=0.08, **_clock()), metadata)
    assert reset_success.done and not reset_success.failed
    assert reset_success.stage == "approach_nut"

    observed_success = NutAssemblyCanonicalSolutionV1(config=config, control_dt=0.1)
    observed_success.reset(initial, _info(opening=0.02, **_clock()), metadata)
    observed_success.observe(
        _observation(), 0.0, False, False,
        _info(success=True, opening=0.02, **_clock(1, 0.1)),
    )
    assert observed_success.done and not observed_success.failed
    assert not hasattr(observed_success, "lifecycle")


def test_terminal_stage_policy_records_success_without_completing():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    assert not lifecycle.observe_task_outcome(task_success=True, control_step=3, simulation_time_s=0.3)
    assert lifecycle.task_success_seen and not lifecycle.expert_complete and not lifecycle.expert_failed


def test_success_during_open_gripper_continues_to_terminal_stage():
    solution = _solution()
    pose = _observation()["state"]["ee_pose"]
    _set_stage(solution, "open_gripper", goal=pose, actions=[[*pose, 0.0], [*pose, 1.0]])
    first = solution.act()
    assert first.stage == "open_gripper"
    solution.observe(_observation(), 0.0, False, False,
                     _info(success=True, opening=0.03, **_clock(1, 0.1)))
    assert not solution.done and solution.stage == "open_gripper"
    second = solution.act()
    assert second.stage == "open_gripper"
    solution.observe(_observation(), 0.0, False, False,
                     _info(success=True, opening=0.08, **_clock(2, 0.2)))
    assert not solution.done and solution.stage == "release_retreat"
    assert solution.lifecycle.first_task_success_step == 1

    retreat_goal = np.array([0.0, 0.0, 0.1, 1.0, 0.0, 0.0, 0.0])
    _set_stage(solution, "release_retreat", goal=retreat_goal, actions=[[*retreat_goal, 1.0]])
    solution.act()
    solution.observe(_observation(retreat_goal), 0.0, False, False,
                     _info(success=True, opening=0.08, **_clock(3, 0.3)))
    assert solution.done and not solution.failed
    assert solution.lifecycle.completion_reason == "expert_sequence_completed"
    assert solution.lifecycle.completion_step == 3
    with _raises(RuntimeError, "cannot act after completion"):
        solution.act()


def test_terminal_stage_without_task_success_fails_closed():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    assert not lifecycle.complete_expert(
        terminal_stage_completed=True, final_task_success=True,
        control_step=5, simulation_time_s=0.5,
    )
    assert lifecycle.expert_failed and not lifecycle.expert_complete
    assert lifecycle.failure_reason == "task_success_never_observed"


def test_later_loss_of_task_success_invalidates_terminal_completion():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    lifecycle.observe_task_outcome(task_success=True, control_step=2, simulation_time_s=0.2)
    lifecycle.observe_task_outcome(task_success=False, control_step=3, simulation_time_s=0.3)
    assert not lifecycle.complete_expert(
        terminal_stage_completed=True, final_task_success=False,
        control_step=4, simulation_time_s=0.4,
    )
    assert lifecycle.expert_failed and lifecycle.failure_reason == "final_task_success_not_valid"
    assert [event["event"] for event in lifecycle.events] == [
        "task_success_first_observed", "task_success_lost", "expert_sequence_failed"
    ]


def test_terminal_stage_and_valid_final_success_complete():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    lifecycle.observe_task_outcome(task_success=True, control_step=2, simulation_time_s=0.2)
    assert lifecycle.complete_expert(
        terminal_stage_completed=True, final_task_success=True,
        control_step=8, simulation_time_s=0.8,
    )
    assert lifecycle.expert_complete and not lifecycle.expert_failed
    assert lifecycle.completion_reason == "expert_sequence_completed"


def test_terminal_stage_timeout_after_success_is_expert_failure():
    config = CanonicalNutAssemblyConfig(max_pose_hold_s=0.2, action_budget_s=2.0)
    solution = _solution(config)
    solution.lifecycle.observe_task_outcome(task_success=True, control_step=0, simulation_time_s=0.0)
    _set_stage(solution, "release_retreat", goal=[1, 0, 0, 1, 0, 0, 0],
                actions=[[1, 0, 0, 1, 0, 0, 0, 1]], index=1)
    for step in (1, 2):
        solution.act()
        solution.observe(_observation(), 0.0, False, False,
                         _info(success=False, **_clock(step, step * 0.1)))
    assert solution.failed and not solution.done
    assert solution.failure_reason == "release_retreat_readiness_timeout"
    assert solution.lifecycle.task_success_seen


def test_action_budget_exceeded_after_success_fails():
    solution = _solution(CanonicalNutAssemblyConfig(action_budget_s=0.2))
    solution.lifecycle.observe_task_outcome(task_success=True, control_step=0, simulation_time_s=0.0)
    _set_stage(solution, "release_retreat", goal=[1, 0, 0, 1, 0, 0, 0],
                actions=[[1, 0, 0, 1, 0, 0, 0, 1]])
    for step in (1, 2, 3):
        solution.act()
        solution.observe(_observation(), 0.0, False, False,
                         _info(success=False, **_clock(step, step * 0.1)))
    assert solution.failed and solution.failure_reason == "canonical_solution_action_budget"
    assert solution.lifecycle.task_success_seen


def _assert_environment_terminal_stops_incomplete_expert(terminated, truncated, success, expected_reason):
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    if success:
        lifecycle.observe_task_outcome(task_success=True, control_step=1, simulation_time_s=0.1)
    assert lifecycle.observe_task_outcome(
        task_success=success, terminated=terminated, truncated=truncated,
        control_step=2, simulation_time_s=0.2,
    )
    assert lifecycle.expert_failed and not lifecycle.expert_complete
    assert lifecycle.failure_reason == expected_reason
    assert lifecycle.environment_terminated is terminated
    assert lifecycle.environment_truncated is truncated


def test_environment_termination_after_task_success_stops_incomplete_expert():
    _assert_environment_terminal_stops_incomplete_expert(
        True, False, True, "TASK_SUCCESS_EXPERT_INCOMPLETE"
    )


def test_environment_truncation_stops_incomplete_expert():
    _assert_environment_terminal_stops_incomplete_expert(
        False, True, False, "environment_truncated_before_expert_completion"
    )


def test_task_failure_after_success_is_not_overridden():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    lifecycle.observe_task_outcome(task_success=True, control_step=1, simulation_time_s=0.1)
    lifecycle.observe_task_outcome(
        task_success=False, task_failure=True, control_step=2, simulation_time_s=0.2,
    )
    assert lifecycle.expert_failed and lifecycle.task_success_seen
    assert lifecycle.failure_reason == "task_failure"


def test_reset_clears_full_lifecycle_history_and_preserves_policy():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    lifecycle.observe_task_outcome(task_success=True, control_step=4, simulation_time_s=0.4)
    lifecycle.fail("environment_terminated_before_expert_completion",
                   control_step=5, simulation_time_s=0.5)
    lifecycle.reset()
    assert lifecycle.completion_policy is SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE
    assert not lifecycle.terminal and not lifecycle.task_success_seen and lifecycle.events == []
    assert lifecycle.failure_reason is None and lifecycle.first_task_success_step is None


def test_snapshot_restore_continues_deterministically():
    original = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    original.observe_task_outcome(task_success=True, control_step=2, simulation_time_s=0.2)
    snapshot = original.to_mapping()
    restored = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    restored.restore_state(copy.deepcopy(snapshot))
    restored.complete_expert(terminal_stage_completed=True, final_task_success=True,
                             control_step=8, simulation_time_s=0.8)
    original.complete_expert(terminal_stage_completed=True, final_task_success=True,
                             control_step=8, simulation_time_s=0.8)
    assert restored.to_mapping() == original.to_mapping()


def test_snapshot_restore_fails_closed_for_missing_or_incompatible_state():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    invalid = lifecycle.to_mapping()
    invalid.pop("completion_reason")
    with _raises(ValueError, "incomplete solution lifecycle snapshot"):
        lifecycle.restore_state(invalid)
    incompatible = lifecycle.to_mapping()
    incompatible["completion_policy"] = SolutionCompletionPolicy.ON_TASK_SUCCESS.value
    with _raises(ValueError, "policy mismatch"):
        lifecycle.restore_state(incompatible)


def test_terminated_and_truncated_cannot_be_combined():
    lifecycle = CanonicalSolutionLifecycle(SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
    with _raises(ValueError, "both terminated and truncated"):
        lifecycle.observe_task_outcome(
            task_success=False, terminated=True, truncated=True,
            control_step=1, simulation_time_s=0.1,
        )


if __name__ == "__main__":
    tests = sorted((name, value) for name, value in globals().items()
                   if name.startswith("test_") and callable(value))
    for name, test in tests:
        test()
        print(f"PASS {name}")
    print(f"{len(tests)} provider-free lifecycle tests passed")
