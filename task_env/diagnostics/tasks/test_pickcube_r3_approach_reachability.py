"""Kinematic R3 regression: measured gates, not native physics qualification."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.controllers.canonical.contracts import RequestedAction
from task_env.controllers.canonical.kinematics import (
    ARM, PANDA_PICKCUBE_EE_TCP_V1, PandaKinematics,
)
from task_env.controllers.canonical.production_r3 import (
    ProductionCanonicalPandaControllerR3, load_r3_dynamic_profile,
)
from task_env.environment import ActionConfig
from task_env.tasks.pick_cube.solution import (
    PickCubePositionExecutionInfoV1, PickCubeReadinessSolution,
)
from task_env.tasks.pick_cube.specialization import build_reference
from task_env.utils.rotation import quat_angle_wxyz


ROOT = Path(__file__).resolve().parents[3]
Q0 = np.array([-0.17, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853])


@pytest.mark.parametrize("seed", [0, 2, 4, 10, 14, 17, 19])
def test_r3_safe_approach_reaches_both_measured_gates(seed):
    """Fixed narrow reset; exact kinematic servo; original 10 mm/215 mm gates."""
    model = PandaKinematics(
        (ROOT / "asset/external/mujoco_menagerie/franka_emika_panda/panda.xml").read_text(),
        tcp_profile=PANDA_PICKCUBE_EE_TCP_V1,
    )
    value = build_reference(include_solution=False, controller_profile="r3_continuous_v1")
    solution = PickCubeReadinessSolution(config=value["readiness"])
    controller = ProductionCanonicalPandaControllerR3.create_arm_reference(
        model, artifact_hash="a" * 64, config=ActionConfig(), control_dt=0.01,
        profile=load_r3_dynamic_profile(), joint_velocity_limit_rad_s=4.0,
    )
    q = Q0.copy()
    cube = np.r_[np.random.default_rng(seed).uniform([.5295, -.025], [.5795, .025]), .488]

    def observation():
        pose = model.pose(q)
        return {
            "state": {"ee_pose": np.array((*pose.position, *pose.quaternion_wxyz), dtype=np.float32)},
            "privileged_state": {"cube_v1_body_pose": np.array([[*cube, 1., 0., 0., 0.]])},
        }

    info = {"is_success": False, "task_failure": False, "task_metrics": {"cube_lift": 0.0}}
    metadata = {"action_schema": {
        "controller_kind": "absolute_pose", "reference": "world",
        "rotation_representation": "quaternion_wxyz", "dimension": 8,
    }}

    def execution(step):
        return PickCubePositionExecutionInfoV1(
            "pickcube-position-execution-info-v1", step, step * .01, .08, 0., .08, False,
        )

    initial = observation()
    solution.reset(initial, info, metadata, execution_info=execution(0))
    plan = solution._segments[0].plan
    gate = plan.measured_tcp_gates[1]
    assert gate.max_horizontal_error_m == .010
    assert gate.minimum_height_above_cube_top_m == pytest.approx(.215)
    # No downward motion is requested until after the second measured gate.
    assert np.all(plan.actions[:gate.after_actions, 2] >= initial["state"]["ee_pose"][2] - 1e-6)
    assert np.allclose(plan.target_pose[3:], initial["state"]["ee_pose"][3:], atol=1e-6)
    rotations = np.vstack((initial["state"]["ee_pose"][3:], plan.actions[:, 3:7]))
    assert max(quat_angle_wxyz(a, b) for a, b in zip(rotations, rotations[1:])) <= .10 + 1e-6
    controller.reset(SimpleNamespace(control_step=0, joint_position=dict(zip(ARM, q))))
    step = 0
    while solution.stage == "move_above_cube" and not solution.failed:
        action = solution.act().action
        state = SimpleNamespace(control_step=step, simulation_time=step * .01,
            joint_position=dict(zip(ARM, q)), pose_world={"panda-v1/ee": model.pose(q)})
        _, target = controller.compute(state, RequestedAction(
            "absolute_pose", "world", "quaternion_wxyz", tuple(map(float, action)),
        ))
        q = np.array([target[name] for name in ARM])
        step += 1
        solution.observe(observation(), 0., False, False, info, execution_info=execution(step))
        assert step < solution.readiness_config.global_safety_cap
    assert not solution.failed, solution.failure_reason
    assert solution.stage == "descend_vertical"
    measured = [event for event in solution.completion_events if event["kind"] == "measured_tcp_clearance"]
    assert [event["gate"] for event in measured] == ["vertical_clearance", "over_cube_before_descent"]
    assert measured[-1]["horizontal_error_m"] <= .010
    assert measured[-1]["height_above_cube_top_m"] >= .215
