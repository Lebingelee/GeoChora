"""Provider-free S1 for the R02c independent Arm/Hand Position leaves."""
from __future__ import annotations

import sys

import pytest

from task_env.runtime.sessions.leaf_control import (
    LeafMaterializationReceiptV1, LeafNativeActuatorMappingV1,
    LeafNativeFrameMappingV1, LeafNativeJointMappingV1,
    LeafNativeTendonMappingV1,
)
from task_env.runtime.sessions.source import lower_mujoco_scene_source
from task_env.tasks.position_candidate.leaf_candidate import (
    ARM_WRITER_ID, HAND_WRITER_ID, action_for_interval,
    build_leaf_position_candidate,
)
from task_env.tasks.reference_env import SelectedReferenceEnv


@pytest.fixture
def candidate(tmp_path):
    value = build_leaf_position_candidate(
        tmp_path / "candidate", environment_type=SelectedReferenceEnv,
    )
    try:
        yield value
    finally:
        value.env.close()


def _receipt_with_panda_general_ranges(plan):
    joints = []
    actuators = []
    frames = []
    tendons = []
    equalities = []
    joint_native_name_by_ref = {}
    for entry in plan.leaves:
        for ref, unit in zip(
            entry.binding.joint_order,
            (entry.binding.joint_position_unit,) * len(entry.binding.joint_order),
            strict=True,
        ):
            native_id = len(joints)
            native_name = f"native_joint_{native_id}"
            joint_native_name_by_ref[ref] = native_name
            joints.append(LeafNativeJointMappingV1(
                "leaf-native-joint-mapping-v1", ref, native_name,
                native_id, native_id, native_id, unit,
            ))
        if entry.binding.profile_kind == "arm_position":
            for ref in entry.binding.actuator_order:
                joint_ref = next(
                    pair.joint for pair in entry.binding.joint_actuator_bindings
                    if pair.actuator == ref
                )
                # Panda's inherited <general> range differs from several
                # authored Joint limits; the receipt must preserve both facts.
                limits = (-2.8973, 2.8973)
                actuators.append(LeafNativeActuatorMappingV1(
                    "leaf-native-actuator-mapping-v1", ref, ref.actuator_id,
                    len(actuators), len(actuators), limits, "radian", "joint",
                    joint_native_name_by_ref[joint_ref],
                ))
            frames.append(LeafNativeFrameMappingV1(
                "leaf-native-frame-mapping-v1", entry.binding.tcp_frame,
                entry.binding.tcp_frame.frame_id, 8,
            ))
        else:
            for ref in entry.binding.actuator_order:
                actuators.append(LeafNativeActuatorMappingV1(
                    "leaf-native-actuator-mapping-v1", ref, ref.actuator_id,
                    len(actuators), len(actuators), tuple(entry.binding.native_ctrlrange),
                    "native_ctrl", "tendon", "split",
                ))
            frames.append(LeafNativeFrameMappingV1(
                "leaf-native-frame-mapping-v1", entry.binding.tcp_frame,
                entry.binding.tcp_frame.frame_id, 9,
            ))
            tendons.append(LeafNativeTendonMappingV1(
                "leaf-native-tendon-mapping-v1", entry.binding.tendon_identity, "split",
            ))
            equalities.append(entry.binding.equality_identity)
    return LeafMaterializationReceiptV1(
        "leaf-materialization-receipt-v1", "synthetic_fixture",
        plan.scene_identity_sha256, plan.source_closure_sha256, plan.identity_sha256,
        plan.provider_name, plan.provider_version, plan.provider_build_sha256,
        plan.backend, "s1-native-map", "s1-config-revision",
        9, 9, 8, 9, 10, 1, 1,
        tuple(joints), tuple(actuators), tuple(frames), tuple(tendons), tuple(equalities),
    )


def test_candidate_uses_existing_selected_env_and_two_same_entity_position_leaves(candidate):
    assert candidate.env.leaf_position_profile is True
    assert candidate.env.position_profile is True
    assert candidate.env.position_profiles == ()
    assert candidate.scene.identity_hash == candidate.plan.scene_identity_sha256
    assert len(candidate.plan.leaves) == 2
    by_kind = {entry.binding.profile_kind: entry for entry in candidate.plan.leaves}
    arm, hand = by_kind["arm_position"], by_kind["hand_position"]
    assert (arm.binding.writer_id, arm.binding.entity_id, arm.binding.member_path,
            arm.binding.control_group_id) == (ARM_WRITER_ID, "panda-main", ("arm",), "arm")
    assert (hand.binding.writer_id, hand.binding.entity_id, hand.binding.member_path,
            hand.binding.control_group_id) == (HAND_WRITER_ID, "panda-main", ("hand",), "gripper")
    assert tuple(ref.joint_id for ref in arm.binding.joint_order) == (
        "joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7",
    )
    assert tuple(ref.joint_id for ref in hand.binding.joint_order) == (
        "finger_joint1", "finger_joint2",
    )
    assert tuple(ref.actuator_id for ref in hand.binding.actuator_order) == ("actuator8",)
    assert "mujoco" not in sys.modules


def test_action_curve_preserves_arm_radians_and_hand_total_opening_m(candidate):
    command = action_for_interval(
        candidate.scene, candidate.plan, 16, arm_active=True, hand_active=True,
    )
    assert command.arm.position_rad == pytest.approx((0.1, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853))
    assert command.hand.opening_m == pytest.approx(0.004)
    request = command.structured_request(candidate.scene, candidate.plan)
    assert {(item.entity_id, item.group_id) for item in request.groups} == {
        ("panda-main", "arm"), ("panda-main", "gripper"),
    }
    arm_only = action_for_interval(
        candidate.scene, candidate.plan, 16, arm_active=True, hand_active=False,
    )
    hand_only = action_for_interval(
        candidate.scene, candidate.plan, 16, arm_active=False, hand_active=True,
    )
    assert arm_only.hand.opening_m == pytest.approx(0.076)
    assert hand_only.arm.position_rad == pytest.approx(
        (0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853)
    )


def test_full_arm_override_changes_only_arm_section(candidate, tmp_path):
    variant = build_leaf_position_candidate(
        tmp_path / "gain-three", environment_type=SelectedReferenceEnv, arm_gain=3.0,
    )
    try:
        base = {entry.binding.profile_kind: entry for entry in candidate.plan.leaves}
        changed = {entry.binding.profile_kind: entry for entry in variant.plan.leaves}
        assert changed["arm_position"].section.values()["joint_position_correction_gain"] == 3.0
        assert base["arm_position"].section.values()["joint_position_correction_gain"] == 2.5
        assert changed["hand_position"].section == base["hand_position"].section
        assert variant.plan.identity_sha256 != candidate.plan.identity_sha256
        assert variant.env.leaf_position_profile is True
        assert "mujoco" not in sys.modules
    finally:
        variant.env.close()


def test_shared_lowerer_validates_exact_candidate_source_closure(candidate):
    # The lowerer validates the authored projected XML and consumed assets
    # before its runtime-only freejoint/keyframe normalization.
    xml, assets = lower_mujoco_scene_source(
        candidate.source.scene_source, candidate.scene,
        candidate.source.source_closure_digest,
    )
    assert xml and len(assets) >= 1
    assert "mujoco" not in sys.modules


def test_joint_limits_and_native_actuator_ranges_are_independent_contracts(candidate):
    receipt = _receipt_with_panda_general_ranges(candidate.plan)
    receipt.validate_against_plan(candidate.plan)
    arm = next(entry for entry in candidate.plan.leaves
               if entry.binding.profile_kind == "arm_position")
    by_actuator = {item.canonical_actuator: item for item in receipt.actuators}
    assert any(
        by_actuator[pair.actuator].ctrlrange != arm.binding.joint_position_limits[index]
        for index, pair in enumerate(arm.binding.joint_actuator_bindings)
    )
