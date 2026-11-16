"""Task-owned pre-lift authorization; measured lift remains the success oracle."""
from dataclasses import replace

import numpy as np
import pytest

from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
from task_env.tasks.pick_cube.solution import (
    PickCubePositionExecutionInfoV1, PickCubeReadinessSolution,
)
from task_env.tasks.pick_cube.specialization import build_reference


def stamp_boundary(observation, info, step, *, episode="synthetic-capture-episode", revision=None):
    """Synthetic public publication identity; this fixture does not run physics."""
    boundary = StateBoundaryIdentity("state-boundary-identity-v1", episode,
        "reset-" + "a" * 64, "b" * 64, "synthetic-scene", "synthetic-provider", step,
        step if revision is None else revision)
    clock = StateSampleClock("state-sample-clock-v1", "evaluation_boundary", step, step * .01)
    observation["state"]["boundary_identity_sha256"] = np.frombuffer(
        bytes.fromhex(boundary.boundary_id.removeprefix("state-boundary-")), dtype=np.uint8,
    ).copy()
    info.update(state_boundary_identity=boundary.to_mapping(), state_boundary_id=boundary.boundary_id,
        state_sample_clock=clock.to_mapping(), control_step=step, simulation_time_s=step * .01)


def fixture_values():
    # Public seed-2 boundary 700 from the original failed diagnostic H5.
    observation = {
        "state": {
            "ee_pose": np.array([.53884965, -.01008420, .53649460,
                .01155085, .76459510, .64427423, .01310068], dtype=np.float32),
            "joint_position": np.array([0., 0., 0., 0., 0., 0., 0., .02677582, .02677970]),
        },
        "privileged_state": {"cube_v1_body_pose": np.array([[
            .54041481, -.00858662, .48761842, .99982214,
            .00063406, .00484885, -.01821133,
        ]], dtype=np.float32)},
    }
    observation["state"]["hand_pose"] = observation["state"]["ee_pose"].copy()
    execution = PickCubePositionExecutionInfoV1(
        "pickcube-position-execution-info-v1", 0, 0., .05355552, .0001, 0., False,
    )
    value = build_reference(include_solution=False, controller_profile="r3_continuous_v1")
    solution = PickCubeReadinessSolution(config=value["readiness"])
    info = {"is_success": False, "task_failure": False, "task_metrics": {"cube_lift": .00061842}}
    metadata = {"action_schema": {"controller_kind": "absolute_pose", "reference": "world",
        "rotation_representation": "quaternion_wxyz", "dimension": 8}}
    stamp_boundary(observation, info, 0)
    solution.reset(observation, info, metadata, execution_info=execution)
    # Enter the real close-stage act/observe loop with its actual plan builder.
    solution._segment_index = 2
    solution._action_index = 0
    solution._refresh_current_segment(observation, info)
    return solution, observation, info, execution


def advance_close(solution, observation, info, execution, count=40, *, start=1, fresh=True):
    for step in range(start, start + count):
        if solution.stage != "close_gripper" or solution.failed:
            break
        action = solution.act()
        assert action.stage == "close_gripper"
        if fresh:
            stamp_boundary(observation, info, step)
        solution.observe(observation, 0., False, False, info,
            execution_info=replace(execution, control_step=step, simulation_time=step * .01))


def test_position_can_authorize_a_stable_opposed_pad_capture_without_relabeling_close_ready():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution)
    assert execution.close_ready is False
    assert solution.stage == "lift"
    assert not solution.done
    assert solution.completion_events[-1]["authorization"] == "stable_opposed_pad_capture_geometry"


@pytest.mark.parametrize("mutation", ["open_target", "moving_fingers", "off_center", "above_cube", "readback_mismatch", "visible_pad_gap"])
def test_position_capture_authorization_rejects_missing_geometry_or_measurement(mutation):
    solution, observation, info, execution = fixture_values()
    if mutation == "open_target":
        execution = replace(execution, target_opening_m=.08)
    elif mutation == "moving_fingers":
        execution = replace(execution, measured_opening_velocity_m_s=.006)
    elif mutation == "off_center":
        observation["privileged_state"]["cube_v1_body_pose"][0, 0] += .02
    elif mutation == "above_cube":
        observation["state"]["ee_pose"][2] += .10
    elif mutation == "readback_mismatch":
        observation["state"]["joint_position"][7:] = .04
    elif mutation == "visible_pad_gap":
        opening = execution.measured_opening_m + .002
        execution = replace(execution, measured_opening_m=opening)
        observation["state"]["joint_position"][7:] += .001
    advance_close(solution, observation, info, execution)
    assert solution.stage == "close_gripper"
    assert not solution.done


def test_capture_requires_continuous_dwell_after_the_close_plan():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution, count=20)
    assert solution.stage == "close_gripper"
    assert not solution.done


def test_capture_rejects_an_object_sliding_inside_the_pad_geometry():
    solution, observation, info, execution = fixture_values()
    for step in range(1, 41):
        assert solution.stage == "close_gripper"
        solution.act()
        # Both poses remain near pads, but the cube translates along their face.
        observation["privileged_state"]["cube_v1_body_pose"][0, 2] += .0002 * (1 if step % 2 else -1)
        stamp_boundary(observation, info, step)
        solution.observe(observation, 0., False, False, info,
            execution_info=replace(execution, control_step=step, simulation_time=step * .01))
    assert solution.stage == "close_gripper"


def test_capture_dwell_counts_elapsed_intervals_and_records_its_evidence():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution, count=29)
    assert solution.stage == "close_gripper"
    advance_close(solution, observation, info, execution, count=1, start=30)
    assert solution.stage == "lift"
    event = solution.completion_events[-1]
    assert event["capture_first_sample_step"] == 20
    assert event["capture_stable_intervals"] == 10
    assert event["capture_dwell_s"] >= .1 - 1e-12


def test_capture_rejects_a_stale_publication_with_fresh_execution_clocks():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution, fresh=False)
    assert solution.stage == "close_gripper"


def test_interrupted_capture_dwell_restarts():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution, count=25)
    advance_close(solution, observation, info, execution, count=1, start=26,
        fresh=False)
    advance_close(solution, observation, info, execution, count=10, start=27)
    assert solution.stage == "close_gripper"
    advance_close(solution, observation, info, execution, count=1, start=37)
    assert solution.stage == "lift"


def test_measured_closure_uses_its_own_authorization_after_a_geometry_candidate():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution, count=25)
    closed = replace(execution, measured_opening_m=.04, close_ready=True)
    advance_close(solution, observation, info, closed, count=1, start=26)
    assert solution.stage == "lift"
    assert solution.completion_events[-1]["authorization"] == "measured_closed_gripper"


@pytest.mark.parametrize("mutation", ["missing", "digest", "clock", "episode", "revision"])
def test_capture_rejects_unbound_or_conflicting_public_state(mutation):
    solution, observation, info, execution = fixture_values()
    for step in range(1, 41):
        solution.act()
        stamp_boundary(observation, info, step,
            episode="other-episode" if mutation == "episode" else "synthetic-capture-episode",
            revision=0 if mutation == "revision" else None)
        if mutation == "missing":
            info.pop("state_boundary_identity")
        elif mutation == "digest":
            observation["state"]["boundary_identity_sha256"][0] ^= 1
        elif mutation == "clock":
            info["state_sample_clock"]["simulation_time_s"] += .01
        solution.observe(observation, 0., False, False, info,
            execution_info=replace(execution, control_step=step, simulation_time=step * .01))
        assert solution.stage == "close_gripper"


def test_reset_discards_capture_dwell_and_binds_the_new_episode():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution, count=25)
    metadata = solution._metadata
    stamp_boundary(observation, info, 0, episode="second-capture-episode")
    solution.reset(observation, info, metadata, execution_info=execution)
    solution._segment_index = 2
    solution._action_index = 0
    solution._refresh_current_segment(observation, info)
    for step in range(1, 31):
        solution.act()
        stamp_boundary(observation, info, step, episode="second-capture-episode")
        solution.observe(observation, 0., False, False, info,
            execution_info=replace(execution, control_step=step, simulation_time=step * .01))
        assert solution.stage == ("lift" if step == 30 else "close_gripper")
    assert solution.completion_events[-1]["capture_first_sample_step"] == 20
