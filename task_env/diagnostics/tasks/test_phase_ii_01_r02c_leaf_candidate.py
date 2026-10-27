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


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), 0.0, 51.0, "50"])
def test_hand_case_rejects_unknown_configuration_before_creating_source(tmp_path, value):
    workspace = tmp_path / "invalid"
    with pytest.raises(ValueError, match="Hand stiffness"):
        build_leaf_position_candidate(
            workspace, environment_type=SelectedReferenceEnv, hand_stiffness_N_per_m=value,
        )
    assert not workspace.exists()


def _calibrated_contract():
    return {
        "configuration_case": {
            "hand_config_identity_sha256": "5ff6243924c53fe31569a9047aa8787862c01e91d31d5b092b2c931050b313cd",
        },
        "plans": {
            "default_identity_sha256": "31150ec4397ff8f94555376ca35bffb0fd0ab0e0b0415d6fe4b3ca2beb7c59ff",
            "override_identity_sha256": "2c595164c9bded911799f5923fe51bb4f9d6e6804d156189fc81cf14ea4513cd",
        },
    }


def test_hand50_complete_override_preserves_defaults_and_prepares_requested_opening(candidate, tmp_path):
    from task_env.diagnostics.tasks.test_phase_ii_01_r02b_leaf_execution import _publication
    from task_env.runtime.sessions.leaf_control import prepare_leaf_command
    from task_env.diagnostics.tasks.r02c_leaf_position_probe import _validate_case_candidate
    calibrated = build_leaf_position_candidate(
        tmp_path / "hand50", environment_type=SelectedReferenceEnv, hand_stiffness_N_per_m=50.0,
    )
    variant = None
    try:
        assert candidate.plan.identity_sha256 == "71743daa095df274bdb59162ad29c6b6027260d62221ce755c725cee69ebf1c7"
        assert calibrated.preset == candidate.preset
        assert calibrated.leaf_bindings == candidate.leaf_bindings
        assert calibrated.source.source_closure_digest == candidate.source.source_closure_digest
        _validate_case_candidate(calibrated, _calibrated_contract(), arm_gain=2.5)
        with pytest.raises(RuntimeError, match="complete frozen Hand50"):
            _validate_case_candidate(candidate, _calibrated_contract(), arm_gain=2.5)
        hand = next(entry for entry in calibrated.plan.leaves if entry.binding.profile_kind == "hand_position")
        old_hand = next(entry for entry in candidate.plan.leaves if entry.binding.profile_kind == "hand_position")
        assert hand.section.values() == {**old_hand.section.values(), "gripper_position_stiffness_N_per_m": 50.0}
        assert old_hand.section.values()["gripper_position_stiffness_N_per_m"] == 2500.0
        receipt = _receipt_with_panda_general_ranges(calibrated.plan)
        publication = _publication(calibrated.scene, receipt, plan=calibrated.plan)
        for interval, expected_opening, expected_ctrl in ((16, 0.004, 12.75), (64, 0.076, 242.25)):
            action = action_for_interval(calibrated.scene, calibrated.plan, interval,
                                         arm_active=True, hand_active=True)
            command = prepare_leaf_command(
                calibrated.plan, HAND_WRITER_ID, action.hand, publication, receipt,
                receipt.configuration_revision, scene=calibrated.scene,
            )
            assert command.servo_opening_m == pytest.approx(expected_opening, abs=1e-15)
            assert command.native_ctrl == pytest.approx(expected_ctrl, abs=1e-12)
        variant = build_leaf_position_candidate(
            tmp_path / "hand50-arm3", environment_type=SelectedReferenceEnv,
            arm_gain=3.0, hand_stiffness_N_per_m=50.0,
        )
        _validate_case_candidate(variant, _calibrated_contract(), arm_gain=3.0)
        assert next(entry.section for entry in variant.plan.leaves
                    if entry.binding.profile_kind == "hand_position") == hand.section
        assert "mujoco" not in sys.modules and "taichi" not in sys.modules
    finally:
        if variant is not None:
            variant.env.close()
        calibrated.env.close()


def test_actual_static_probe_validates_both_hand50_plans_without_native(candidate, tmp_path, monkeypatch):
    import hashlib
    from task_env.diagnostics.tasks import r02c_leaf_position_probe as probe
    contract = _calibrated_contract()
    xml, assets = lower_mujoco_scene_source(
        candidate.source.scene_source, candidate.scene, candidate.source.source_closure_digest,
    )
    contract["source"] = {
        "closure_sha256": candidate.source.source_closure_digest,
        "lowered_xml_sha256": hashlib.sha256(xml.encode()).hexdigest(),
        "assets_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in assets.items()},
    }
    monkeypatch.setattr(probe, "ATTEMPT_ROOT", tmp_path / "probe")
    result = probe._static_candidate_checks(contract)
    assert result["configuration_case"] == "SOURCE_CALIBRATED_HAND_50_V1"
    assert result["default_plan_identity_sha256"] == contract["plans"]["default_identity_sha256"]
    assert result["override_plan_identity_sha256"] == contract["plans"]["override_identity_sha256"]
    assert result["hand_configuration"]["gripper_position_stiffness_N_per_m"] == 50.0
    assert result["native_provider_imported"] is False
