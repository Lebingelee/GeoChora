"""Task-owned pre-lift authorization; measured lift remains the success oracle."""
from dataclasses import replace

import numpy as np
import pytest

from task_env.tasks.pick_cube.solution import (
    PickCubePositionExecutionInfoV1, PickCubeReadinessSolution,
)
from task_env.tasks.pick_cube.specialization import build_reference


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
    solution.reset(observation, info, metadata, execution_info=execution)
    # Enter the real close-stage act/observe loop with its actual plan builder.
    solution._segment_index = 2
    solution._action_index = 0
    solution._refresh_current_segment(observation, info)
    return solution, observation, info, execution


def advance_close(solution, observation, info, execution, count=40):
    for step in range(1, count + 1):
        if solution.stage != "close_gripper" or solution.failed:
            break
        action = solution.act()
        assert action.stage == "close_gripper"
        solution.observe(observation, 0., False, False, info,
            execution_info=replace(execution, control_step=step, simulation_time=step * .01))


def test_position_can_authorize_a_stable_opposed_pad_capture_without_relabeling_close_ready():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution)
    assert execution.close_ready is False
    assert solution.stage == "lift"
    assert not solution.done
    assert solution.completion_events[-1]["authorization"] == "stable_opposed_pad_capture_geometry"


@pytest.mark.parametrize("mutation", ["open_target", "moving_fingers", "off_center", "above_cube", "readback_mismatch"])
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
    advance_close(solution, observation, info, execution)
    assert solution.stage == "close_gripper"
    assert not solution.done


def test_capture_requires_continuous_dwell_after_the_close_plan():
    solution, observation, info, execution = fixture_values()
    advance_close(solution, observation, info, execution, count=20)
    assert solution.stage == "close_gripper"
    assert not solution.done
