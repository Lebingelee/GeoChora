"""Narrow regression coverage for the shared R3 execution owners."""

import pytest

from task_env.controllers.canonical.execution import (
    ReferenceExecutionController, StableArmTargetHold,
)
from task_env.controllers.canonical.gripper_execution import NativeRateGripperServo
from task_env.planners import AbsolutePosePlannerConfig
from task_env.tasks.nut_assembly.specialization import build_reference as build_nutassembly_reference
from task_env.tasks.pick_cube.specialization import build_reference as build_pickcube_reference


def test_si_rate_conversion_and_zero_settle_preserve_tick_contract():
    config = AbsolutePosePlannerConfig.from_si_rates(
        control_dt_s=0.01,
        translation_speed_m_s=0.06,
        translation_acceleration_m_s2=0.45,
        rotation_speed_rad_s=3.0,
        rotation_acceleration_rad_s2=27.0,
        settle_duration_s=0.27,
        max_plan_duration_s=6.0,
    )
    assert config.max_translation_per_step == pytest.approx(0.0006)
    assert config.max_translation_acceleration_per_step == pytest.approx(0.000045)
    assert config.max_rotation_per_step == pytest.approx(0.03)
    assert config.max_rotation_acceleration_per_step == pytest.approx(0.0027)
    assert config.settle_steps == 27
    assert config.max_steps == 600

    zero_settle = AbsolutePosePlannerConfig.from_si_rates(
        control_dt_s=0.01,
        translation_speed_m_s=0.06,
        translation_acceleration_m_s2=0.45,
        rotation_speed_rad_s=3.0,
        rotation_acceleration_rad_s2=27.0,
        settle_duration_s=0.0,
        max_plan_duration_s=6.0,
    )
    assert zero_settle.settle_steps == 0
    assert AbsolutePosePlannerConfig().settle_steps == 16


def test_pickcube_and_nutassembly_resolve_the_shared_r3_execution_owners():
    pick = build_pickcube_reference(controller_profile="r3_continuous_v1")
    nut = build_nutassembly_reference(provider="mujoco", include_solution=True)

    for reference in (pick, nut):
        controller = reference["controller"]
        assert isinstance(controller, ReferenceExecutionController)
        assert isinstance(controller.hold, StableArmTargetHold)
        assert isinstance(controller.inner, NativeRateGripperServo)
        assert controller.gripper_rate_hz == 500
        assert controller.inner.controller.inner_physics_dt_s == pytest.approx(0.002)

    assert pick["controller"].rate_profile_mapping() == nut["controller"].rate_profile_mapping()
    assert pick["controller"].rate_profile_mapping()["joint_velocity_limit_rad_s"] == pytest.approx(2.0)
    assert pick["controller"].gripper_config.force_limit_N == pytest.approx(10.0)
    assert pick["readiness"].base.planner == nut["solution"]._planner.config
