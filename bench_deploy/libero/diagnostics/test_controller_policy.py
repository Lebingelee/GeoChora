"""Regression checks for the accepted reference and optional rim controller."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from bench_deploy.libero.controllers.osc import (
    LiberoMixedControllerV6,
    LiberoMixedControllerV7,
)
from bench_deploy.libero.controllers.source_gravity import (
    SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
)
from bench_deploy.libero.environment.selected_reference import (
    PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID,
    PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID,
    _a_upstream_pose_replay_joint_limit_tolerances,
    _make_candidate_controller,
    _panda_gripper_aggregate_opening_m,
)
from bench_deploy.libero.artifacts.contracts import TASK_2, TASK_3


def _assert_identity_hash(controller):
    mapping = controller.identity_mapping()
    material = {key: value for key, value in mapping.items() if key != "identity_sha256"}
    expected = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    assert mapping["identity_sha256"] == expected == controller.identity


def test_v6_uses_qfrc_bias_and_versions_the_source_and_controller_profiles():
    controller = LiberoMixedControllerV6()
    passive_adjusted = np.arange(7, dtype=np.float64)
    upstream_bias = passive_adjusted + 0.25
    identity = controller.identity_mapping()

    assert np.array_equal(controller._source_feedforward_torque({
        "bias_minus_passive_arm_Nm": passive_adjusted,
        "qfrc_bias_arm_Nm": upstream_bias,
    }), upstream_bias)
    assert controller._source_state_contract() == (
        "libero-source-operational-space-state-v2", SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
    )
    assert identity["schema_version"] == "libero-mixed-controller-identity-v6"
    assert identity["gravity_feedforward_source"] == "qfrc_bias_arm_Nm"
    assert identity["gravity_feedforward_receipt_field"] == "gravity_feedforward_Nm"
    _assert_identity_hash(controller)


def test_v6_official_reference_and_v7_rim_profiles_have_distinct_identities():
    official_reference = LiberoMixedControllerV6(
        nullspace_reference_joint_position_rad=np.arange(7, dtype=np.float64),
    )
    rim = LiberoMixedControllerV7()
    official_identity = official_reference.identity_mapping()
    rim_identity = rim.identity_mapping()

    assert official_identity["profile_id"] == LiberoMixedControllerV6.OFFICIAL_REFERENCE_PROFILE_ID
    assert official_identity["nullspace_reference_policy"] == (
        "robosuite_controller_initial_joint_after_set_init_state_v1"
    )
    assert rim_identity["schema_version"] == "libero-mixed-controller-identity-v7"
    assert rim_identity["gravity_feedforward_source"] == "qfrc_bias_arm_Nm"
    assert rim._source_state_contract() == (
        "libero-source-operational-space-state-v2", SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
    )
    assert rim_identity["source_state_profile_id"] == SOURCE_OPERATIONAL_SPACE_PROFILE_V2
    _assert_identity_hash(official_reference)
    _assert_identity_hash(rim)


def test_task23_upstream_replay_uses_reference_v6_osc_without_planner_twist():
    controller = _make_candidate_controller(
        execution_profile="a-reference",
        task_uid=TASK_3,
        arm_resolver_identity=None,
    )
    initial_joint_position = {f"joint{i}": i / 10 for i in range(1, 8)}
    controller.reset(SimpleNamespace(
        joint_position=initial_joint_position,
        joint_velocity={name: 0.0 for name in initial_joint_position},
        control_step=0,
        simulation_time=0.0,
    ))
    identity = controller.identity_mapping()
    reference, provenance = controller._nullspace_reference(
        np.zeros(7), np.ones(7),
    )

    assert isinstance(controller, LiberoMixedControllerV6)
    assert not isinstance(controller, LiberoMixedControllerV7)
    assert identity["algorithm"] == "robosuite_osc_pose_uncoupled_lambda_and_qfrc_bias_v1"
    assert identity["gravity_feedforward_source"] == "qfrc_bias_arm_Nm"
    assert "desired_twist_source" not in identity
    assert identity["control_frequency_hz"] == 20
    assert identity["physics_dt_s"] == 0.002
    assert identity["control_substeps"] == 25
    assert identity["hold_policy"] == "torque_recomputed_each_physics_substep_v1"
    assert provenance == "reset_initial_joint_v1"
    assert np.array_equal(reference, np.asarray(list(initial_joint_position.values())))
    assert controller._allow_unconverged_arm_resolution is True
    _assert_identity_hash(controller)


def test_panda_gripper_replay_v1_preserves_exact_endpoints_and_v2_is_opt_in():
    assert PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID == "robosuite-panda-gripper-delta-v1"
    assert PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID == (
        "robosuite-panda-gripper-delta-endpoint-guard-v2"
    )
    assert PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID != PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID
    assert _panda_gripper_aggregate_opening_m(-1.0) == 0.0
    assert _panda_gripper_aggregate_opening_m(1.0) == 0.08
    assert _panda_gripper_aggregate_opening_m(
        -1.0, PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID,
    ) == 0.0005
    assert _panda_gripper_aggregate_opening_m(
        1.0, PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID,
    ) == 0.0795


def test_task_local_limit_monitor_allowance_is_scoped_to_approved_a_replay():
    task2 = _a_upstream_pose_replay_joint_limit_tolerances("mujoco", TASK_2, True)
    task3 = _a_upstream_pose_replay_joint_limit_tolerances("mujoco", TASK_3, True)
    assert task2["finger_joint1"] == task2["finger_joint2"] == 50.0e-6
    assert task3["finger_joint1"] == task3["finger_joint2"] == 500.0e-6
    assert all(task2[f"joint{i}"] == task3[f"joint{i}"] == 4.0e-3 for i in range(1, 8))
    assert _a_upstream_pose_replay_joint_limit_tolerances("geophys", TASK_3, True) == {}
    assert _a_upstream_pose_replay_joint_limit_tolerances("mujoco", TASK_3, False) == {}


def test_factory_rejects_a_non_versioned_solution_selector():
    from bench_deploy.libero.environment.selected_reference import build_libero_selected_candidate

    with pytest.raises(TypeError, match="named A-reference or V8"):
        build_libero_selected_candidate(_execution_profile=True)
