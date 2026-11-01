from __future__ import annotations

import numpy as np

from task_env.objects.pick_cube import CUBE_HALF_SIZE
from task_env.tasks.pick_cube.solution import (
    _ABOVE_CLEARANCE,
    _APPROACH_CLEARANCE,
    PickCubePositionExecutionInfoV1,
    PickCubeReadinessConfig,
    PickCubeReadinessSolution,
    PickCubeSolutionConfig,
    PickCubeSolution,
)
from task_env.planners.completion import StageCompletionPolicy


def test_move_above_cube_clears_vertically_before_lateral_transit():
    start = np.asarray(
        [0.5465, -0.0938, 0.5661, 0.0, 0.7646, 0.6445, 0.0],
        dtype=np.float32,
    )
    cube = np.asarray([0.6351, -0.0865, 0.488], dtype=np.float32)
    observation = {
        "state": {"ee_pose": start},
        "privileged_state": {"cube_v1_body_pose": np.asarray([[*cube, 1, 0, 0, 0]])},
    }

    plan = PickCubeSolution()._plan_move_above(observation, {})
    positions = plan.actions[:, :3]
    target = cube + np.asarray(
        [0.0, 0.0, CUBE_HALF_SIZE + _ABOVE_CLEARANCE], dtype=np.float32,
    )
    clear_z = float(target[2]) + _APPROACH_CLEARANCE
    deltas = np.diff(np.vstack((start[:3], positions)), axis=0)
    lateral = np.flatnonzero(np.linalg.norm(deltas[:, :2], axis=1) > 1e-7)

    assert lateral.size > 0
    first_lateral, last_lateral = int(lateral[0]), int(lateral[-1])
    assert plan.measured_tcp_gates[0].name == "vertical_clearance"
    assert plan.measured_tcp_gates[0].after_actions == first_lateral
    assert plan.measured_tcp_gates[1].name == "over_cube_before_descent"
    assert plan.measured_tcp_gates[1].after_actions > first_lateral
    before_lateral = start[:3] if first_lateral == 0 else positions[first_lateral - 1]
    assert before_lateral[2] >= clear_z - 1e-5
    assert positions[first_lateral, 2] >= clear_z - 1e-5
    assert positions[last_lateral, 2] >= clear_z - 1e-5
    assert np.all(np.abs(deltas[last_lateral + 1 :, :2]) <= 1e-7)
    assert np.allclose(plan.target_pose[:3], target, atol=1e-6)
    assert np.allclose(positions[-1], target, atol=1e-5)
    assert np.isfinite(plan.actions).all()


def test_r3_readiness_holds_vertical_action_until_public_tcp_clearance_is_measured():
    start = np.asarray(
        [0.5465, -0.0938, 0.5661, 0.0, 0.7646, 0.6445, 0.0],
        dtype=np.float32,
    )
    cube = np.asarray([0.6351, -0.0865, 0.488], dtype=np.float32)
    observation = {
        "state": {"ee_pose": start.copy()},
        "privileged_state": {"cube_v1_body_pose": np.asarray([[*cube, 1, 0, 0, 0]])},
    }
    info = {
        "is_success": False,
        "task_failure": False,
        "task_metrics": {"cube_lift": 0.0},
    }
    policy = lambda kind, reason: StageCompletionPolicy(
        "stage-completion-v1", kind, 12, 0.15, 0.5, 0.105,
        "panda-v1/gripper", reason,
    )
    config = PickCubeReadinessConfig(
        base=PickCubeSolutionConfig(),
        control_dt=0.01,
        policies=(
            policy("pose_ready", "above_pose_readiness_timeout"),
            policy("pose_ready", "descend_pose_readiness_timeout"),
            policy("gripper_ready", "gripper_readiness_timeout"),
            policy("task_outcome", "lift_outcome_timeout"),
        ),
        profile_identity="test-profile",
        timeout_derivation="test-only",
        measured_tcp_clearance_gate=True,
    )
    solution = PickCubeReadinessSolution(config=config)
    metadata = {
        "action_schema": {
            "controller_kind": "absolute_pose",
            "reference": "world",
            "rotation_representation": "quaternion_wxyz",
            "dimension": 8,
        }
    }

    def execution_info(step):
        return PickCubePositionExecutionInfoV1(
            "pickcube-position-execution-info-v1", step, step * 0.01,
            0.08, 0.0, 0.08, False,
        )

    solution.reset(observation, info, metadata, execution_info=execution_info(0))
    plan = solution._segments[0].plan
    vertical_gate = plan.measured_tcp_gates[0]
    assert vertical_gate.after_actions > 0

    for step in range(1, vertical_gate.after_actions + 1):
        proposal = solution.act()
        assert proposal.diagnostics.get("measured_tcp_clearance_gate_hold") is False
        solution.observe(
            observation, 0.0, False, False, info,
            execution_info=execution_info(step),
        )

    hold = solution.act()
    assert hold.diagnostics["measured_tcp_clearance_gate_hold"] is True
    assert hold.diagnostics["measured_tcp_clearance_gate"] == "vertical_clearance"
    assert np.array_equal(hold.action, plan.actions[vertical_gate.after_actions - 1])

    measured_clear = observation["state"]["ee_pose"].copy()
    measured_clear[2] = cube[2] + CUBE_HALF_SIZE + vertical_gate.minimum_height_above_cube_top_m + 0.001
    cleared_observation = {
        "state": {"ee_pose": measured_clear},
        "privileged_state": observation["privileged_state"],
    }
    solution.observe(
        cleared_observation, 0.0, False, False, info,
        execution_info=execution_info(vertical_gate.after_actions + 1),
    )

    lateral = solution.act()
    assert lateral.diagnostics.get("measured_tcp_clearance_gate_hold") is False
    assert np.array_equal(lateral.action, plan.actions[vertical_gate.after_actions])
