"""Provider-free S1 for versioned Arm/Hand leaf contracts (R02a only)."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import (
    ActuatorReference,
    ActuatorResourceDefinition,
    ArticulationDefinition,
    AssetDefinition,
    ControlGroup,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    JointReference,
    LogicalAssemblyControlGroupReferenceV1,
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblyScenePinV1,
    LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
    PoseWorld,
    RobotInstance,
    SceneDefinition,
    resolve_logical_assembly,
)
from task_env.controllers.canonical.contracts import RequestedAction
from task_env.controllers.canonical.leaf_profiles import (
    ARM_POSITION_ACTION_SCHEMA,
    ARM_POSITION_PROFILE_ID,
    HAND_FORCE_AWARE_ACTION_SCHEMA,
    HAND_FORCE_AWARE_PROFILE_ID,
    HAND_POSITION_ACTION_SCHEMA,
    HAND_POSITION_PROFILE_ID,
    PANDA_ARM_JOINT_LIMITS_RAD,
    PANDA_ARM_JOINT_IDS,
    PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M,
    PANDA_HAND_FINGER_JOINT_IDS,
    PANDA_HAND_FINGER_LIMITS_M,
    PANDA_HAND_TENDON_COEFFICIENTS,
    PANDA_HAND_TENDON_IDENTITY,
    PANDA_HAND_EQUALITY_IDENTITY,
    PANDA_HAND_ACTUATOR_GAINPRM,
    PANDA_HAND_ACTUATOR_BIASPRM,
    ArmPositionActionV1,
    ArmPositionTargetV1,
    HandPositionActionV1,
    HandPositionTargetV1,
    LeafApplicationAckV1,
    LeafJointActuatorBindingV1,
    LeafProfileBindingV1,
    decode_force_aware_dependency,
    decode_leaf_action,
    decode_leaf_application_ack,
    decode_leaf_profile_binding,
    decode_leaf_target,
    leaf_profile_catalog_v1,
    panda_arm_required_state,
    panda_hand_force_aware_dependency,
    panda_hand_required_state,
    validate_leaf_binding,
    validate_leaf_bindings,
    validate_leaf_target_ack,
)
from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock


_HASH = "a" * 64
_IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))


def _scene(*, separate_entities=False):
    if separate_entities:
        entity_asset = (("arm", "arm-asset"), ("hand", "hand-asset"))
    else:
        entity_asset = (("panda", "panda-asset"),)
    assets = tuple(
        AssetDefinition("asset-definition-v1", asset, "v1", f"test:{asset}", "fixture-v1", _HASH, "apache-2.0")
        for _, asset in entity_asset
    )
    entities = tuple(
        EntityInstance("entity-instance-v1", entity, asset, "v1")
        for entity, asset in entity_asset
    )
    frames = []
    articulations = []
    robots = []
    actuator_resources = []
    control_groups = []

    for entity, _asset in entity_asset:
        arm_joints = tuple(f"{entity}/joint{i}" for i in range(8))
        finger_joints = tuple(f"{entity}/{name}" for name in PANDA_HAND_FINGER_JOINT_IDS)
        link_ids = tuple(f"link{i}" for i in range(8))
        local_frames = list(link_ids)
        if not separate_entities:
            local_frames.extend(("hand", "finger1", "finger2"))
        elif entity == "hand":
            local_frames = ["hand", "finger1", "finger2"]
        elif entity == "arm":
            local_frames = list(link_ids)
        frames.extend(
            FrameDefinition("frame-definition-v1", entity, frame, "runtime", None, None)
            for frame in local_frames
        )

        joints = []
        if not separate_entities or entity == "arm":
            for index, joint_id in enumerate(PANDA_ARM_JOINT_IDS, 1):
                joints.append(JointDefinition(
                    "joint-definition-v1", joint_id,
                    FrameReference(entity, f"link{index - 1}"), FrameReference(entity, f"link{index}"),
                    _IDENTITY, _IDENTITY, "revolute", (0.0, 0.0, 1.0),
                    "radian", "radian_per_second", 1, 1,
                ))
        if not separate_entities or entity == "hand":
            parent = "hand" if separate_entities else "link7"
            child_prefix = "finger"
            if not separate_entities:
                # Keep the fixed hand body in the kinematic tree before the fingers.
                joints.append(JointDefinition(
                    "joint-definition-v1", "hand_mount",
                    FrameReference(entity, "link7"), FrameReference(entity, "hand"),
                    _IDENTITY, _IDENTITY, "fixed", None, "none", "none", 0, 0,
                ))
            for index, joint_id in enumerate(PANDA_HAND_FINGER_JOINT_IDS, 1):
                joints.append(JointDefinition(
                    "joint-definition-v1", joint_id,
                    FrameReference(entity, parent), FrameReference(entity, f"{child_prefix}{index}"),
                    _IDENTITY, _IDENTITY, "prismatic", (0.0, 1.0, 0.0),
                    "meter", "meter_per_second", 1, 1,
                ))
        root = "link0" if entity != "hand" else "hand"
        frame_order = tuple(local_frames)
        articulations.append(ArticulationDefinition(
            "articulation-definition-v1", entity, root, frame_order, tuple(joints),
        ))
        robots.append(RobotInstance("robot-instance-v1", entity, (FrameReference(entity, root),)))

        if not separate_entities and entity == "panda":
            arm_actuator_ids = tuple(f"actuator{i}" for i in range(1, 8))
            hand_actuator_ids = ("actuator8",)
            for actuator_id in (*arm_actuator_ids, *hand_actuator_ids):
                actuator_resources.append(ActuatorResourceDefinition("actuator-resource-v1", entity, actuator_id))
            control_groups.extend((
                ControlGroup("control-group-v1", entity, "arm-control", tuple(
                    ActuatorReference(entity, actuator_id) for actuator_id in arm_actuator_ids
                )),
                ControlGroup("control-group-v1", entity, "hand-control", tuple(
                    ActuatorReference(entity, actuator_id) for actuator_id in hand_actuator_ids
                )),
            ))
        elif separate_entities:
            actuator_ids = tuple(f"actuator{i}" for i in range(1, 8)) if entity == "arm" else ("actuator8",)
            for actuator_id in actuator_ids:
                actuator_resources.append(ActuatorResourceDefinition("actuator-resource-v1", entity, actuator_id))
            control_groups.append(ControlGroup(
                "control-group-v1", entity, "arm-control" if entity == "arm" else "hand-control",
                tuple(ActuatorReference(entity, actuator_id) for actuator_id in actuator_ids),
            ))

    return SceneDefinition(
        "scene-definition-v3", "leaf-test-scene", assets, entities,
        tuple(frames), tuple(articulations), tuple(robots),
        tuple(actuator_resources), tuple(control_groups),
    )


def _assembly(scene, *, separate_entities=False):
    pin = LogicalAssemblyScenePinV1(
        "logical-assembly-scene-pin-v1", scene.scene_id, scene.schema_version, scene.identity_hash,
    )
    if separate_entities:
        members = (
            LogicalAssemblyEntityMemberV1("entity_member", ("arm",), "arm", "arm-asset", "v1"),
            LogicalAssemblyEntityMemberV1("entity_member", ("hand",), "hand", "hand-asset", "v1"),
        )
        assembly_id = "separate-panda"
    else:
        members = (
            LogicalAssemblyEntityMemberV1("entity_member", ("panda",), "panda", "panda-asset", "v1"),
            LogicalAssemblySubcomponentReferenceV1(
                "existing_entity_subcomponent_ref", ("arm",), "control_group",
                LogicalAssemblyControlGroupReferenceV1("panda", "arm-control"),
            ),
            LogicalAssemblySubcomponentReferenceV1(
                "existing_entity_subcomponent_ref", ("hand",), "control_group",
                LogicalAssemblyControlGroupReferenceV1("panda", "hand-control"),
            ),
        )
        assembly_id = "whole-panda"
    root = LogicalAssemblyV1("logical-assembly-v1", assembly_id, "r1", pin, members)
    resolved = resolve_logical_assembly(root, scene, {})
    return root, resolved


def _binding(scene, resolved, kind, *, entity=None, whole_panda=False, writer=None):
    arm = kind == "arm_position"
    if whole_panda:
        entity = "panda"
        asset = "panda-asset"
        path = ("arm",) if arm else ("hand",)
        member_kind, target_kind, target_id = "existing_entity_subcomponent_ref", "control_group", (
            "arm-control" if arm else "hand-control"
        )
        assembly = resolved
    else:
        entity = entity or ("arm" if arm else "hand")
        asset = "arm-asset" if entity == "arm" else "hand-asset"
        path = ("arm",) if arm else ("hand",)
        member_kind, target_kind, target_id = "entity_member", "entity", entity
        assembly = resolved
    group = "arm-control" if arm else "hand-control"
    joint_ids = PANDA_ARM_JOINT_IDS if arm else PANDA_HAND_FINGER_JOINT_IDS
    limits = PANDA_ARM_JOINT_LIMITS_RAD if arm else PANDA_HAND_FINGER_LIMITS_M
    actuator_ids = tuple(f"actuator{i}" for i in range(1, 8)) if arm else ("actuator8",)
    tcp_frame = FrameReference(entity, "link7" if arm else "hand")
    profile_id = ARM_POSITION_PROFILE_ID if arm else HAND_POSITION_PROFILE_ID
    action_schema = ARM_POSITION_ACTION_SCHEMA if arm else HAND_POSITION_ACTION_SCHEMA
    required_state = panda_arm_required_state(entity, tcp_frame) if arm else panda_hand_required_state(entity, tcp_frame)
    return LeafProfileBindingV1(
        "leaf-profile-binding-v1", "synthetic_fixture", kind, profile_id, action_schema,
        scene.identity_hash, assembly.root_assembly_id, assembly.root_revision,
        assembly.root_logical_content_sha256, path, member_kind, target_kind, target_id,
        entity, asset, "v1", "b" * 64, "canonical-joint-position-v1", "c" * 64,
        writer or f"{entity}/{kind}-writer", group, "synthetic-provider", "fixture-v1",
        "d" * 64, "cpu", 0.002, 5,
        tuple(JointReference(entity, joint_id) for joint_id in joint_ids),
        "radian" if arm else "meter", tuple(limits),
        tuple(ActuatorReference(entity, actuator_id) for actuator_id in actuator_ids),
        tuple(
            LeafJointActuatorBindingV1("leaf-joint-actuator-binding-v1", joint, actuator)
            for joint, actuator in zip(
                tuple(JointReference(entity, joint_id) for joint_id in joint_ids),
                tuple(ActuatorReference(entity, actuator_id) for actuator_id in actuator_ids),
                strict=True,
            )
        ) if arm else (),
        tcp_frame, "T_parent_from_tcp", _IDENTITY, required_state,
        None if arm else PANDA_HAND_TENDON_IDENTITY,
        () if arm else PANDA_HAND_TENDON_COEFFICIENTS,
        None if arm else PANDA_HAND_EQUALITY_IDENTITY,
        None if arm else PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M,
        None if arm else "opening_m = finger_joint1_q_m + finger_joint2_q_m",
        None if arm else "ctrl = 3187.5 * opening_m",
        None if arm else (0.0, 255.0),
        () if arm else PANDA_HAND_ACTUATOR_GAINPRM,
        () if arm else PANDA_HAND_ACTUATOR_BIASPRM,
    )


def _boundary(scene, step=0, *, revision=0):
    return StateBoundaryIdentity(
        "state-boundary-identity-v1", "episode-1", "reset-" + "1" * 64,
        scene.identity_hash, "scene-instance-1", "materialization-1", step, revision,
    )


def _clock(step=0, time=0.0):
    return StateSampleClock("state-sample-clock-v1", "evaluation_boundary", step, time)


def _target_ack(binding):
    source = _boundary(_scene())
    clock = _clock()
    if binding.profile_kind == "arm_position":
        action = ArmPositionActionV1(
            ARM_POSITION_ACTION_SCHEMA, binding.joint_order, (0.0, -0.5, 0.0, -1.5, 0.0, 1.0, 0.5),
        )
        target = ArmPositionTargetV1(
            "arm-position-target-v1", binding.profile_id, binding.action_schema_id,
            binding.writer_id, binding.identity_hash, binding.source_closure_sha256,
            binding.scene_identity_hash, binding.joint_order, binding.actuator_order,
            source, clock, action,
        )
    else:
        target = HandPositionTargetV1(
            "hand-position-target-v1", binding.profile_id, binding.action_schema_id,
            binding.writer_id, binding.identity_hash, binding.source_closure_sha256,
            binding.scene_identity_hash, binding.joint_order, binding.actuator_order,
            source, clock, HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, 0.04),
        )
    ack = LeafApplicationAckV1(
        "leaf-application-ack-v1", binding.profile_kind, binding.profile_id,
        binding.action_schema_id,
        target.identity_hash, binding.writer_id, binding.identity_hash,
        binding.source_closure_sha256, binding.scene_identity_hash,
        binding.joint_order, binding.actuator_order, source, clock, source, clock,
    )
    return source, clock, target, ack


def test_whole_panda_reference_only_groups_and_separate_entity_owners_bind_independently():
    whole_scene = _scene()
    _root, whole_resolved = _assembly(whole_scene)
    whole_bindings = (
        _binding(whole_scene, whole_resolved, "arm_position", whole_panda=True),
        _binding(whole_scene, whole_resolved, "hand_position", whole_panda=True),
    )
    assert [value.member_kind for value in whole_bindings] == [
        "existing_entity_subcomponent_ref", "existing_entity_subcomponent_ref",
    ]
    assert validate_leaf_bindings(whole_scene, whole_bindings, whole_resolved) == whole_bindings

    separate_scene = _scene(separate_entities=True)
    _root, separate_resolved = _assembly(separate_scene, separate_entities=True)
    separate_bindings = (
        _binding(separate_scene, separate_resolved, "arm_position", entity="arm"),
        _binding(separate_scene, separate_resolved, "hand_position", entity="hand"),
    )
    assert [value.member_kind for value in separate_bindings] == ["entity_member", "entity_member"]
    assert validate_leaf_bindings(separate_scene, separate_bindings, separate_resolved) == separate_bindings


def test_scene_binding_rejects_wrong_assembly_path_asset_group_or_scene():
    scene = _scene()
    _root, resolved = _assembly(scene)
    good = _binding(scene, resolved, "arm_position", whole_panda=True)
    validate_leaf_binding(scene, good, resolved)
    with pytest.raises(ValueError, match="typed ControlGroup view"):
        validate_leaf_binding(scene, replace(good, member_path=("hand",)), resolved)
    with pytest.raises(ValueError, match="Asset/Entity identity"):
        validate_leaf_binding(scene, replace(good, asset_version="v2"), resolved)
    with pytest.raises(ValueError, match="Scene identity"):
        validate_leaf_binding(scene, replace(good, scene_identity_hash="e" * 64), resolved)


def test_joint_order_limits_units_tendon_and_equality_are_explicit():
    scene = _scene()
    _root, resolved = _assembly(scene)
    arm = _binding(scene, resolved, "arm_position", whole_panda=True)
    hand = _binding(scene, resolved, "hand_position", whole_panda=True)
    assert tuple(ref.joint_id for ref in arm.joint_order) == PANDA_ARM_JOINT_IDS
    assert arm.joint_position_unit == "radian"
    assert arm.joint_position_limits == PANDA_ARM_JOINT_LIMITS_RAD
    assert tuple((pair.joint.joint_id, pair.actuator.actuator_id) for pair in arm.joint_actuator_bindings) == tuple(
        (f"joint{i}", f"actuator{i}") for i in range(1, 8)
    )
    assert tuple(ref.joint_id for ref in hand.joint_order) == PANDA_HAND_FINGER_JOINT_IDS
    assert hand.joint_position_limits == PANDA_HAND_FINGER_LIMITS_M
    assert hand.tendon_coefficients == (0.5, 0.5)
    assert hand.tendon_identity and hand.equality_identity
    assert hand.actuator_order == (ActuatorReference("panda", "actuator8"),)
    assert hand.actuator_command_scale_ctrl_per_opening_m == 3187.5
    assert hand.native_ctrlrange == (0.0, 255.0)
    assert hand.actuator_gainprm == (0.01568627451, 0.0, 0.0)
    assert hand.actuator_biasprm == (0.0, -100.0, -10.0)
    with pytest.raises(ValueError, match="Panda order"):
        replace(arm, joint_position_limits=((0.0, 1.0),) * 7)
    with pytest.raises(ValueError, match="one coupled tendon actuator"):
        replace(hand, actuator_order=(ActuatorReference("panda", "actuator7"),))
    with pytest.raises(ValueError, match="one coupled tendon actuator"):
        replace(hand, tendon_coefficients=(1.0, 0.0))
    with pytest.raises(ValueError, match="exact canonical order"):
        replace(arm, joint_actuator_bindings=tuple(reversed(arm.joint_actuator_bindings)))


def test_position_actions_are_strict_ordered_and_finite():
    scene = _scene()
    _root, resolved = _assembly(scene)
    binding = _binding(scene, resolved, "arm_position", whole_panda=True)
    order = binding.joint_order
    decoded = decode_leaf_action({
        "schema_version": ARM_POSITION_ACTION_SCHEMA,
        "joint_order": [ref.to_mapping() for ref in order],
        "position_rad": [0.0, -0.5, 0.0, -1.5, 0.0, 1.0, 0.5],
    })
    assert decoded == ArmPositionActionV1(ARM_POSITION_ACTION_SCHEMA, order, (0.0, -0.5, 0.0, -1.5, 0.0, 1.0, 0.5))
    with pytest.raises(ValueError, match="unknown"):
        ArmPositionActionV1.from_mapping({
            "schema_version": ARM_POSITION_ACTION_SCHEMA, "joint_order": order,
            "position_rad": (0.0,) * 7, "future_field": 1,
        })
    with pytest.raises(ValueError, match="seven ordered"):
        ArmPositionActionV1(ARM_POSITION_ACTION_SCHEMA, order, (0.0,) * 6)
    with pytest.raises(ValueError):
        ArmPositionActionV1(ARM_POSITION_ACTION_SCHEMA, order, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, float("nan")))
    with pytest.raises((TypeError, ValueError)):
        ArmPositionActionV1(ARM_POSITION_ACTION_SCHEMA, order, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False))
    with pytest.raises(ValueError, match="unknown"):
        decode_leaf_action({"schema_version": HAND_POSITION_ACTION_SCHEMA, "opening_m": 0.04, "position_rad": []})
    with pytest.raises(ValueError, match="unsupported leaf Action"):
        decode_leaf_action({"schema_version": "arm-position-action-v2", "position_rad": [0.0] * 7})


@pytest.mark.parametrize("value", [-0.001, 0.080001, float("inf"), float("nan"), True, False])
def test_hand_metre_action_rejects_invalid_or_out_of_range_values(value):
    with pytest.raises((TypeError, ValueError)):
        HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, value)


def test_hand_normalized_mapping_is_explicit_and_never_silently_clips():
    assert HandPositionActionV1.from_normalized_signed_scalar(-1.0).opening_m == 0.0
    assert HandPositionActionV1.from_normalized_signed_scalar(0.0).opening_m == 0.04
    assert HandPositionActionV1.from_normalized_signed_scalar(1.0).opening_m == 0.08
    with pytest.raises(ValueError):
        HandPositionActionV1.from_normalized_signed_scalar(1.01)
    with pytest.raises(ValueError):
        HandPositionActionV1.from_normalized_signed_scalar(False)
    with pytest.raises(ValueError, match="mapping"):
        HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, 0.04, "normalized_signed_scalar_v1", 0.5)
    with pytest.raises((TypeError, ValueError)):
        HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, 0.04, "normalized_signed_scalar_v1", False)
    with pytest.raises(ValueError, match="unknown Hand Position input"):
        HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, 0.04, "unspecified")


@pytest.mark.parametrize("profile_kind", ["arm_position", "hand_position"])
def test_target_ack_cross_checks_identity_context_and_resource_order(profile_kind):
    scene = _scene()
    _root, resolved = _assembly(scene)
    binding = _binding(scene, resolved, profile_kind, whole_panda=True)
    source, clock, target, ack = _target_ack(binding)
    assert validate_leaf_target_ack(
        binding, target, ack,
        expected_source_boundary=source, expected_source_clock=clock,
        expected_application_boundary=source, expected_application_clock=clock,
    ) == ack

    with pytest.raises(ValueError, match="exact Target identity"):
        validate_leaf_target_ack(
            binding, target, replace(ack, target_identity_hash="e" * 64),
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="Target profile/source/writer"):
        bad_target = replace(target, writer_id="wrong-writer")
        validate_leaf_target_ack(
            binding, bad_target, ack,
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="Target profile/source/writer"):
        bad_target = replace(target, source_closure_sha256="e" * 64)
        validate_leaf_target_ack(
            binding, bad_target, ack,
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="source boundary/clock"):
        bad_target = replace(target, sample_clock=_clock(0, 0.01))
        validate_leaf_target_ack(
            binding, bad_target, replace(ack, target_identity_hash=bad_target.identity_hash),
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="ordered resources"):
        wrong_order = (ActuatorReference(binding.entity_id, "actuator7"),) if profile_kind == "hand_position" else tuple(reversed(binding.actuator_order))
        wrong_ack = replace(ack, actuator_order=wrong_order)
        validate_leaf_target_ack(
            binding, target, wrong_ack,
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    wrong_boundary = replace(source, state_revision=1)
    with pytest.raises(ValueError, match="explicit context"):
        validate_leaf_target_ack(
            binding, target, ack,
            expected_source_boundary=wrong_boundary, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="application boundary/clock"):
        validate_leaf_target_ack(
            binding, target, ack,
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=wrong_boundary, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="Ack profile/source/writer"):
        validate_leaf_target_ack(
            binding, target, replace(ack, writer_id="wrong-writer"),
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="same evaluation boundary"):
        validate_leaf_target_ack(
            binding, target, replace(ack, application_sample_clock=_clock(0, 0.01)),
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )
    with pytest.raises(ValueError, match="binding"):
        bad_target = replace(target, binding_identity_hash="e" * 64)
        validate_leaf_target_ack(
            binding, bad_target, ack,
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )


def test_target_decoders_reject_cross_kind_unknown_and_wrong_version_payloads():
    scene = _scene()
    _root, resolved = _assembly(scene)
    binding = _binding(scene, resolved, "hand_position", whole_panda=True)
    source, clock, target, ack = _target_ack(binding)
    decoded_target = decode_leaf_target(target.to_mapping())
    assert decoded_target == target
    assert decode_leaf_application_ack(ack.to_mapping()) == ack
    with pytest.raises(ValueError, match="unsupported leaf Target"):
        decode_leaf_target({"schema_version": "hand-position-target-v99"})
    with pytest.raises(ValueError, match="unknown"):
        decode_leaf_application_ack({**ack.to_mapping(), "unchecked": True})


def test_target_arm_limits_checked_against_binding():
    scene = _scene()
    _root, resolved = _assembly(scene)
    binding = _binding(scene, resolved, "arm_position", whole_panda=True)
    source, clock, target, ack = _target_ack(binding)
    action = replace(target.action, position_rad=(3.0, -0.5, 0.0, -1.5, 0.0, 1.0, 0.5))
    bad_target = replace(target, action=action)
    bad_ack = replace(ack, target_identity_hash=bad_target.identity_hash)
    with pytest.raises(ValueError, match="joint limits"):
        validate_leaf_target_ack(
            binding, bad_target, bad_ack,
            expected_source_boundary=source, expected_source_clock=clock,
            expected_application_boundary=source, expected_application_clock=clock,
        )


def test_duplicate_writer_or_actuator_across_static_bindings_is_rejected():
    scene = _scene()
    _root, resolved = _assembly(scene)
    arm = _binding(scene, resolved, "arm_position", whole_panda=True)
    hand = _binding(scene, resolved, "hand_position", whole_panda=True)
    with pytest.raises(ValueError, match="duplicate leaf writer"):
        validate_leaf_bindings(scene, (arm, replace(hand, writer_id=arm.writer_id)), resolved)
    with pytest.raises(ValueError, match="overlap an owned Actuator"):
        validate_leaf_bindings(scene, (hand, replace(hand, writer_id="panda/other-hand-writer")), resolved)


def test_position_required_state_is_force_free_and_force_aware_is_independently_refused():
    arm_state = panda_arm_required_state("panda", FrameReference("panda", "link7"))
    hand_state = panda_hand_required_state("panda", FrameReference("panda", "hand"))
    assert not any(item.field_name == "actuator_force" for item in arm_state.state_requirements.requirements)
    assert not any(item.field_name == "actuator_force" for item in hand_state.state_requirements.requirements)
    force = panda_hand_force_aware_dependency("panda", FrameReference("panda", "hand"))
    decoded = decode_force_aware_dependency(force.to_mapping())
    assert decoded.admission_status == "NOT_ADMITTED"
    assert decoded.sign_mapping_status == "NOT_AUDITED"
    assert decoded.sample_phase_status == "NOT_AUDITED"
    assert decoded.position_profiles_independent is True
    assert [item.field_name for item in decoded.required_state.state_requirements.requirements].count("actuator_force") == 1
    with pytest.raises(ValueError, match="must remain NOT_ADMITTED"):
        replace(force, admission_status="ADMITTED")
    with pytest.raises(ValueError, match="not an executable Action"):
        decode_leaf_action({"schema_version": HAND_FORCE_AWARE_ACTION_SCHEMA})


def test_catalog_is_finite_read_only_contract_only_not_admission():
    catalog = leaf_profile_catalog_v1()
    assert tuple(item.profile_id for item in catalog) == (
        ARM_POSITION_PROFILE_ID, HAND_POSITION_PROFILE_ID, HAND_FORCE_AWARE_PROFILE_ID,
    )
    assert all(item.contract_status == "CONTRACT_ONLY" for item in catalog)
    assert all(item.admission_status == "NOT_ADMITTED" for item in catalog)
    assert all(item.execution_status == "NOT_RUN" for item in catalog)
    assert catalog[0].force_feedback_required is False
    assert catalog[1].force_feedback_required is False
    assert catalog[2].force_feedback_required is True
    with pytest.raises((AttributeError, TypeError)):
        catalog[0].profile_id = "changed"


@pytest.mark.parametrize("profile_kind", ["arm_position", "hand_position"])
@pytest.mark.parametrize("mutation", ["optional", "unbound_joint", "foreign_frame"])
def test_required_state_cannot_weaken_or_expand_bound_leaf_resources(profile_kind, mutation):
    from task_env.artifacts import StateFieldRequirement

    scene = _scene()
    _root, resolved = _assembly(scene)
    binding = _binding(scene, resolved, profile_kind, whole_panda=True)
    requirements = binding.required_state.state_requirements.requirements
    if mutation == "optional":
        requirements = tuple(replace(item, requiredness="optional") for item in requirements)
    elif mutation == "unbound_joint":
        requirements = (*requirements, StateFieldRequirement(
            "state-field-requirement-v1", "joint_position", "joint", binding.entity_id,
            "finger_joint1" if profile_kind == "arm_position" else "joint1",
            "required", "evaluation_boundary", "joint-definition", "joint_state_query",
        ))
    else:
        requirements = (*requirements, StateFieldRequirement(
            "state-field-requirement-v1", "frame_pose_world", "frame", "another-entity", "tcp",
            "required", "evaluation_boundary", "meter+quaternion_wxyz", "frame_pose_query",
        ))
    with pytest.raises(ValueError, match="Required State"):
        state = replace(binding.required_state, state_requirements=replace(
            binding.required_state.state_requirements, requirements=requirements,
        ))
        validate_leaf_binding(scene, replace(binding, required_state=state), resolved)
    assert validate_leaf_binding(scene, binding, resolved) == binding


def test_force_dependency_cannot_mark_required_feedback_optional():
    force = panda_hand_force_aware_dependency("panda", FrameReference("panda", "hand"))
    requirements = tuple(replace(item, requiredness="optional")
                         for item in force.required_state.state_requirements.requirements)
    with pytest.raises(ValueError, match="Required State"):
        replace(force.required_state, state_requirements=replace(
            force.required_state.state_requirements, requirements=requirements,
        ))
    assert force.admission_status == "NOT_ADMITTED"


def test_binding_codec_hash_and_mapping_snapshots_are_strict_and_detached():
    scene = _scene()
    _root, resolved = _assembly(scene)
    binding = _binding(scene, resolved, "arm_position", whole_panda=True)
    encoded = binding.to_mapping()
    decoded = decode_leaf_profile_binding(encoded)
    assert decoded == binding
    assert replace(binding, provider_name="mujoco", provider_version="3.8.1").provider_version == "3.8.1"
    first_hash = binding.identity_hash
    encoded["joint_order"][0]["joint_id"] = "tampered"
    assert binding.identity_hash == first_hash
    assert binding.joint_order[0].joint_id == "joint1"
    with pytest.raises(ValueError, match="unknown"):
        decode_leaf_profile_binding({**binding.to_mapping(), "future_field": True})
    with pytest.raises(ValueError, match="unsupported leaf binding"):
        decode_leaf_profile_binding({**binding.to_mapping(), "schema_version": "leaf-profile-binding-v2"})
    with pytest.raises(ValueError):
        replace(binding, source_closure_sha256="not-a-hash")


def test_old_complete_panda_action_contract_stays_eight_dimensional():
    legacy = RequestedAction("absolute_joint", None, "none", (0.0,) * 8)
    legacy.validate()
    with pytest.raises(ValueError, match="shape"):
        RequestedAction("absolute_joint", None, "none", (0.0,) * 7).validate()


def test_documented_minimal_example_runs_as_a_pure_value_contract():
    from task_env.controllers.canonical import (
        HAND_POSITION_ACTION_SCHEMA as EXPORTED_HAND_POSITION_ACTION_SCHEMA,
        HandPositionActionV1 as ExportedHandPositionActionV1,
        leaf_profile_catalog_v1 as exported_leaf_profile_catalog_v1,
    )

    action = ExportedHandPositionActionV1(EXPORTED_HAND_POSITION_ACTION_SCHEMA, 0.038)
    assert action.to_mapping() == {
        "schema_version": EXPORTED_HAND_POSITION_ACTION_SCHEMA,
        "opening_m": 0.038,
        "input_representation": "opening_m",
        "requested_normalized": None,
    }
    assert all(entry.admission_status == "NOT_ADMITTED" for entry in exported_leaf_profile_catalog_v1())


def test_import_and_provider_free_call_do_not_load_provider_or_native_modules():
    code = """
import sys
from task_env.controllers.canonical.leaf_profiles import (
    HandPositionActionV1, HAND_POSITION_ACTION_SCHEMA, leaf_profile_catalog_v1,
)
action = HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, 0.038)
assert action.opening_m == 0.038
assert all(entry.admission_status == 'NOT_ADMITTED' for entry in leaf_profile_catalog_v1())
assert not any(name == 'mujoco' or name.startswith('mujoco.') for name in sys.modules)
assert not any(name == 'taichi' or name.startswith('taichi.') for name in sys.modules)
assert not any(name == 'GeoPhys' or name.startswith('GeoPhys.') for name in sys.modules)
"""
    root = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(root), str(root / "GeoPhys/src")))
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=root, env=env,
        text=True, capture_output=True, check=False, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
