"""Narrow regression coverage for the v2.1.1 PickCube R3 repair."""

from dataclasses import asdict

import numpy as np
import pytest

from task_env.tasks.pick_cube.specialization import (
    build_reference as build_pickcube_reference,
    make_reference_binding,
)
from task_env.tasks.nut_assembly.specialization import (
    build_reference as build_nutassembly_reference,
)
from task_env.utils.rotation import normalize_quat_wxyz, quat_angle_wxyz


PROFILE_A = "r3_continuous_v1"
PROFILE_B = "r3_continuous_v1_pose_path_x20"


def _reference_observation():
    return {
        "state": {
            "ee_pose": np.asarray(
                [0.5465, -0.0938, 0.5661, 0.0, 0.7646, 0.6445, 0.0],
                dtype=np.float32,
            ),
        },
        "privileged_state": {
            "cube_v1_body_pose": np.asarray(
                [[0.6351, -0.0865, 0.488, 1.0, 0.0, 0.0, 0.0]],
                dtype=np.float32,
            ),
        },
    }


def _compress_repeated_points(points):
    points = np.asarray(points)
    keep = np.r_[True, np.any(np.abs(np.diff(points, axis=0)) > 1e-7, axis=1)]
    return points[keep]


def test_r3_pickcube_resolution_matches_nut_controller_and_planner():
    nut = build_nutassembly_reference(provider="mujoco", include_solution=True)
    pick_a = build_pickcube_reference(controller_profile=PROFILE_A)
    pick_b = build_pickcube_reference(controller_profile=PROFILE_B)

    nut_controller = nut["controller"]
    for pick in (pick_a, pick_b):
        controller = pick["controller"]
        assert asdict(controller.config) == asdict(nut_controller.config)
        assert asdict(controller.gripper_config) == asdict(nut_controller.gripper_config)
        assert controller.rate_profile_mapping() == nut_controller.rate_profile_mapping()
        assert asdict(pick["source"].config.action) == asdict(nut["source"].config.action)
        assert asdict(pick["source"].config.robot.gripper) == asdict(
            nut["source"].config.robot.gripper
        )
        assert asdict(pick["readiness"].base.planner) == asdict(
            nut["solution"]._planner.config
        )
        assert pick["readiness"].base.planner.settle_steps == 27
        assert pick["readiness"].base.planner.max_steps == 600
        assert pick["readiness"].base.close_transition_steps == 34
        assert pick["readiness"].base.close_settle_steps == 50
        assert pick["readiness"].base.postclose_hold_steps == 10
        assert pick["readiness"].base.action_budget == 4483
        assert pick["readiness"].global_safety_cap == 5709
        assert pick["readiness"].measured_tcp_clearance_gate is True
        assert pick["artifact"].timebase.physics_dt == pytest.approx(0.002)
        assert pick["artifact"].timebase.control_substeps == 5

    assert pick_a["controller"].identity == pick_b["controller"].identity
    assert pick_a["solution_identity"] != pick_b["solution_identity"]
    assert pick_a["readiness"].base.posture_path_profile == "original"
    assert pick_b["readiness"].base.posture_path_profile == "world_x_roundtrip_v1"


def test_posture_ab_changes_only_orientation_and_preserves_measured_gates():
    pick_a = build_pickcube_reference(controller_profile=PROFILE_A)
    pick_b = build_pickcube_reference(controller_profile=PROFILE_B)
    observation = _reference_observation()
    plan_a = pick_a["solution"]._plan_move_above(observation, {})
    plan_b = pick_b["solution"]._plan_move_above(observation, {})

    np.testing.assert_array_equal(plan_a.target_pose, plan_b.target_pose)
    np.testing.assert_allclose(
        _compress_repeated_points(plan_a.actions[:, :3]),
        _compress_repeated_points(plan_b.actions[:, :3]),
        rtol=0.0,
        atol=1e-7,
    )
    assert np.allclose(plan_a.actions[:, 3:7], observation["state"]["ee_pose"][3:7])
    start_quaternion = observation["state"]["ee_pose"][3:7]
    angle_from_start = np.asarray([
        quat_angle_wxyz(quaternion, start_quaternion)
        for quaternion in plan_b.actions[:, 3:7]
    ])
    detour_rows = angle_from_start > 1e-5
    assert detour_rows.any()

    transit_position = plan_a.actions[
        plan_a.measured_tcp_gates[1].after_actions - 1, :3
    ]
    np.testing.assert_allclose(
        plan_b.actions[detour_rows, :3],
        np.broadcast_to(transit_position, (int(detour_rows.sum()), 3)),
        rtol=0.0,
        atol=1e-7,
    )
    assert np.max(angle_from_start) == pytest.approx(np.deg2rad(20.0), abs=2e-5)
    assert np.max([
        quat_angle_wxyz(left, right)
        for left, right in zip(plan_b.actions[:-1, 3:7], plan_b.actions[1:, 3:7])
    ]) <= pick_b["readiness"].base.planner.max_rotation_per_step + 1e-6
    np.testing.assert_allclose(
        plan_b.actions[-1, 3:7],
        normalize_quat_wxyz(start_quaternion),
        rtol=0.0,
        atol=1e-7,
    )

    for plan in (plan_a, plan_b):
        vertical, over_cube = plan.measured_tcp_gates
        assert vertical.name == "vertical_clearance"
        assert over_cube.name == "over_cube_before_descent"
        # R3 commands +90 mm above cube top and preserves 20 mm headroom plus
        # the 5 mm measurement tolerance, so its measured gate is +65 mm.
        assert vertical.minimum_height_above_cube_top_m == pytest.approx(0.065)
        assert over_cube.minimum_height_above_cube_top_m == pytest.approx(0.065)
        cube_top = float(observation["privileged_state"]["cube_v1_body_pose"][0, 2]) + 0.025
        assert plan.target_pose[2] - cube_top == pytest.approx(0.080, abs=1e-6)
        assert plan.actions[vertical.after_actions - 1, 2] - cube_top == pytest.approx(0.090, abs=1e-6)
        assert plan.actions[over_cube.after_actions - 1, 2] - cube_top == pytest.approx(0.090, abs=1e-6)
        assert 0.090 - vertical.minimum_height_above_cube_top_m == pytest.approx(0.020 + 0.005)
        assert over_cube.max_horizontal_error_m == pytest.approx(0.010)
        assert plan.actions[over_cube.after_actions - 1, 2] >= plan.target_pose[2]
        np.testing.assert_allclose(
            plan.actions[over_cube.after_actions - 1, 3:7],
            normalize_quat_wxyz(plan.target_pose[3:7]),
            rtol=0.0,
            atol=1e-7,
        )
        settle = pick_a["readiness"].base.planner.settle_steps
        assert np.allclose(
            plan.actions[vertical.after_actions - settle:vertical.after_actions],
            plan.actions[vertical.after_actions - 1],
            rtol=0.0,
            atol=0.0,
        )


def test_r3_route_uses_native_five_substep_binding_on_both_scalar_providers():
    assert make_reference_binding(
        controller_profile=PROFILE_A, interval_provider="mujoco"
    ).interval_mode == "native"
    assert make_reference_binding(
        controller_profile=PROFILE_B, interval_provider="mujoco"
    ).interval_mode == "native"
    assert make_reference_binding(
        controller_profile=PROFILE_A, interval_provider="geophys"
    ).interval_mode == "native"
    assert make_reference_binding(
        controller_profile=PROFILE_B, interval_provider="geophys"
    ).interval_mode == "native"
    assert make_reference_binding(
        controller_profile="r1", interval_provider="mujoco"
    ).interval_mode == "grouped"
    assert make_reference_binding(
        controller_profile="r1", interval_provider="geophys"
    ).interval_mode == "grouped"


def test_lift_uses_planner_length_instead_of_spending_remaining_solution_budget():
    pick = build_pickcube_reference(controller_profile=PROFILE_A)
    solution = pick["solution"]
    plan = solution._plan_lift(_reference_observation(), {})

    hold_steps = pick["readiness"].base.postclose_hold_steps
    start = solution._ee_pose(_reference_observation())
    expected_hold = solution._planner.hold_pose(
        pose=start, steps=hold_steps, gripper=-1.0,
    )
    target = start.copy()
    target[2] += 0.16
    expected_plan = solution._planner.plan_translation_only(
        current_pose=start, target_position=target[:3], gripper=-1.0,
    )
    assert hold_steps == 10
    assert len(plan.actions) == hold_steps + len(expected_plan)
    np.testing.assert_array_equal(plan.actions[:hold_steps], expected_hold)
    np.testing.assert_array_equal(plan.actions[hold_steps:], expected_plan)
    assert np.all(plan.actions[:, 7] == -1.0)
    assert len(plan.actions) < solution.config.action_budget
    settle = pick["readiness"].base.planner.settle_steps
    assert np.allclose(
        plan.actions[-settle:], plan.actions[-1], rtol=0.0, atol=0.0,
    )
