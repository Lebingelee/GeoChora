"""Provider-free S1 for R02b effective leaf plans, adapters and dispatch."""
from __future__ import annotations

from dataclasses import replace
import math

import pytest

from task_env.artifacts.contracts import (
    ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityInstance, FrameDefinition,
    FrameReference, JointDefinition, JointReference, PoseWorld, RobotInstance,
    SceneDefinition,
)
from task_env.artifacts.logical_assembly import (
    LogicalAssemblyControlGroupReferenceV1, LogicalAssemblyEntityMemberV1,
    LogicalAssemblyScenePinV1, LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
)
from task_env.artifacts.logical_assembly_resolution import resolve_logical_assembly
from task_env.artifacts.state import (
    CanonicalStatePublicationV1, CanonicalStateViewV1, StateBoundaryIdentity,
    StateFieldRequirement, StateSampleClock, StateViewLifetime,
    TypedFrameStateValue, TypedJointStateValue,
)
from task_env.controllers.canonical.contracts import RequestedAction
from task_env.controllers.canonical.controller import CanonicalPandaController
from task_env.controllers.canonical.leaf_profiles import (
    ARM_POSITION_ACTION_SCHEMA, ARM_POSITION_PROFILE_ID,
    HAND_POSITION_ACTION_SCHEMA, HAND_POSITION_PROFILE_ID,
    PANDA_ARM_JOINT_IDS, PANDA_ARM_JOINT_LIMITS_RAD,
    PANDA_HAND_ACTUATOR_BIASPRM, PANDA_HAND_ACTUATOR_GAINPRM,
    PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M, PANDA_HAND_EQUALITY_IDENTITY,
    PANDA_HAND_FINGER_JOINT_IDS, PANDA_HAND_FINGER_LIMITS_M,
    PANDA_HAND_TENDON_COEFFICIENTS, PANDA_HAND_TENDON_IDENTITY,
    ArmPositionActionV1, ArmPositionTargetV1, HandPositionActionV1, LeafApplicationAckV1,
    LeafJointActuatorBindingV1, LeafProfileBindingV1,
    panda_arm_required_state, panda_hand_required_state,
)
from task_env.controllers.canonical.leaf_plan import (
    EffectiveLeafPlanV1, LeafControlPresetV1, LeafProfileOverrideV1,
    LeafProfileSectionV1, compile_effective_leaf_plan,
    decode_leaf_control_preset, decode_leaf_profile_override,
    decode_leaf_profile_section, default_leaf_profile_section,
)
from task_env.environment import ActionConfig
from task_env.environment.types import ExecutionFaultV1
from task_env.robots.gripper import (
    GripperTarget, PandaGripperController, position_gripper_ctrl_for_opening,
    position_gripper_servo_opening,
)
from task_env.runtime.sessions.leaf_control import (
    LeafActuatorPatchV1, LeafActuatorSlotValueV1, LeafApplyResultV1,
    LeafControlIntervalRequestV1, LeafDispatchProgressV1,
    LeafMaterializationReceiptV1, LeafNativeActuatorMappingV1,
    LeafNativeFrameMappingV1, LeafNativeJointMappingV1, LeafNativeTendonMappingV1,
    LeafRuntimeClockV1,
    LeafActionRequestV1, dispatch_leaf_control_interval, prepare_leaf_command,
    preflight_leaf_control_interval,
)


_HASH = "a" * 64
_IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
_ARM_CURRENT = (0.0, -0.4, 0.0, -1.8, 0.0, 1.2, 0.3)
_ARM_TARGET = (0.1, -0.3, 0.1, -1.7, 0.1, 1.3, 0.4)
_SOURCE_CLOSURE = "b" * 64


def _scene():
    entity, asset = "panda", "panda-asset"
    assets = (AssetDefinition("asset-definition-v1", asset, "v1", "test:panda", "fixture-v1", _HASH, "apache-2.0"),)
    entities = (EntityInstance("entity-instance-v1", entity, asset, "v1"),)
    frame_ids = tuple(f"link{i}" for i in range(8)) + ("hand", "finger1", "finger2")
    frames = tuple(FrameDefinition("frame-definition-v1", entity, frame, "runtime", None, None)
                   for frame in frame_ids)
    joints = []
    for index, joint_id in enumerate(PANDA_ARM_JOINT_IDS, 1):
        joints.append(JointDefinition(
            "joint-definition-v1", joint_id,
            FrameReference(entity, f"link{index - 1}"), FrameReference(entity, f"link{index}"),
            _IDENTITY, _IDENTITY, "revolute", (0.0, 0.0, 1.0),
            "radian", "radian_per_second", 1, 1,
        ))
    joints.append(JointDefinition(
        "joint-definition-v1", "hand_mount", FrameReference(entity, "link7"),
        FrameReference(entity, "hand"), _IDENTITY, _IDENTITY,
        "fixed", None, "none", "none", 0, 0,
    ))
    for index, joint_id in enumerate(PANDA_HAND_FINGER_JOINT_IDS, 1):
        joints.append(JointDefinition(
            "joint-definition-v1", joint_id, FrameReference(entity, "hand"),
            FrameReference(entity, f"finger{index}"), _IDENTITY, _IDENTITY,
            "prismatic", (0.0, 1.0, 0.0), "meter", "meter_per_second", 1, 1,
        ))
    articulation = ArticulationDefinition(
        "articulation-definition-v1", entity, "link0", frame_ids, tuple(joints),
    )
    robot = RobotInstance("robot-instance-v1", entity, (FrameReference(entity, "link0"),))
    actuator_ids = tuple(f"actuator{i}" for i in range(1, 9))
    resources = tuple(ActuatorResourceDefinition("actuator-resource-v1", entity, actuator)
                      for actuator in actuator_ids)
    groups = (
        ControlGroup("control-group-v1", entity, "arm-control", tuple(
            ActuatorReference(entity, f"actuator{i}") for i in range(1, 8)
        )),
        ControlGroup("control-group-v1", entity, "hand-control", (
            ActuatorReference(entity, "actuator8"),
        )),
    )
    return SceneDefinition(
        "scene-definition-v3", "r02b-synthetic-panda", assets, entities, frames,
        (articulation,), (robot,), resources, groups,
    )


def _split_scene():
    """Small two-Entity declaration fixture with disjoint Arm/Hand owners."""
    assets = (
        AssetDefinition("asset-definition-v1", "arm-asset", "v1", "test:panda-arm", "fixture-v1", _HASH, "apache-2.0"),
        AssetDefinition("asset-definition-v1", "hand-asset", "v1", "test:panda-hand", "fixture-v1", _HASH, "apache-2.0"),
    )
    entities = (
        EntityInstance("entity-instance-v1", "panda-arm", "arm-asset", "v1"),
        EntityInstance("entity-instance-v1", "panda-hand", "hand-asset", "v1"),
    )
    arm_frames = tuple(f"link{i}" for i in range(8))
    hand_frames = ("hand", "finger1", "finger2")
    frames = tuple(
        FrameDefinition("frame-definition-v1", "panda-arm", name, "runtime", None, None)
        for name in arm_frames
    ) + tuple(
        FrameDefinition("frame-definition-v1", "panda-hand", name, "runtime", None, None)
        for name in hand_frames
    )
    arm_joints = tuple(JointDefinition(
        "joint-definition-v1", joint_id,
        FrameReference("panda-arm", f"link{index - 1}"),
        FrameReference("panda-arm", f"link{index}"), _IDENTITY, _IDENTITY,
        "revolute", (0.0, 0.0, 1.0), "radian", "radian_per_second", 1, 1,
    ) for index, joint_id in enumerate(PANDA_ARM_JOINT_IDS, 1))
    hand_joints = tuple(JointDefinition(
        "joint-definition-v1", joint_id, FrameReference("panda-hand", "hand"),
        FrameReference("panda-hand", f"finger{index}"), _IDENTITY, _IDENTITY,
        "prismatic", (0.0, 1.0, 0.0), "meter", "meter_per_second", 1, 1,
    ) for index, joint_id in enumerate(PANDA_HAND_FINGER_JOINT_IDS, 1))
    articulations = (
        ArticulationDefinition("articulation-definition-v1", "panda-arm", "link0", arm_frames, arm_joints),
        ArticulationDefinition("articulation-definition-v1", "panda-hand", "hand", hand_frames, hand_joints),
    )
    robots = (
        RobotInstance("robot-instance-v1", "panda-arm", (FrameReference("panda-arm", "link0"),)),
        RobotInstance("robot-instance-v1", "panda-hand", (FrameReference("panda-hand", "hand"),)),
    )
    resources = tuple(ActuatorResourceDefinition("actuator-resource-v1", "panda-arm", f"actuator{i}")
                      for i in range(1, 8)) + (
        ActuatorResourceDefinition("actuator-resource-v1", "panda-hand", "actuator8"),
    )
    groups = (
        ControlGroup("control-group-v1", "panda-arm", "arm-control", tuple(
            ActuatorReference("panda-arm", f"actuator{i}") for i in range(1, 8)
        )),
        ControlGroup("control-group-v1", "panda-hand", "hand-control", (
            ActuatorReference("panda-hand", "actuator8"),
        )),
    )
    return SceneDefinition(
        "scene-definition-v3", "r02b-split-arm-hand", assets, entities,
        frames, articulations, robots, resources, groups,
    )


def _assembly(scene, *, split=False):
    pin = LogicalAssemblyScenePinV1(
        "logical-assembly-scene-pin-v1", scene.scene_id, scene.schema_version,
        scene.identity_hash,
    )
    if split:
        members = (
            LogicalAssemblyEntityMemberV1("entity_member", ("arm-entity",), "panda-arm", "arm-asset", "v1"),
            LogicalAssemblyEntityMemberV1("entity_member", ("hand-entity",), "panda-hand", "hand-asset", "v1"),
            LogicalAssemblySubcomponentReferenceV1(
                "existing_entity_subcomponent_ref", ("arm",), "control_group",
                LogicalAssemblyControlGroupReferenceV1("panda-arm", "arm-control"),
            ),
            LogicalAssemblySubcomponentReferenceV1(
                "existing_entity_subcomponent_ref", ("hand",), "control_group",
                LogicalAssemblyControlGroupReferenceV1("panda-hand", "hand-control"),
            ),
        )
    else:
        members = (
            LogicalAssemblyEntityMemberV1(
                "entity_member", ("panda",), "panda", "panda-asset", "v1",
            ),
            LogicalAssemblySubcomponentReferenceV1(
                "existing_entity_subcomponent_ref", ("arm",), "control_group",
                LogicalAssemblyControlGroupReferenceV1("panda", "arm-control"),
            ),
            LogicalAssemblySubcomponentReferenceV1(
                "existing_entity_subcomponent_ref", ("hand",), "control_group",
                LogicalAssemblyControlGroupReferenceV1("panda", "hand-control"),
            ),
        )
    return LogicalAssemblyV1(
        "logical-assembly-v1", "r02b-assembly", "r1", pin,
        members,
    )


def _binding(scene, resolved, *, arm, split=False):
    entity = ("panda-arm" if arm else "panda-hand") if split else "panda"
    asset = ("arm-asset" if arm else "hand-asset") if split else "panda-asset"
    profile_kind = "arm_position" if arm else "hand_position"
    profile_id = ARM_POSITION_PROFILE_ID if arm else HAND_POSITION_PROFILE_ID
    action_schema = ARM_POSITION_ACTION_SCHEMA if arm else HAND_POSITION_ACTION_SCHEMA
    joint_ids = PANDA_ARM_JOINT_IDS if arm else PANDA_HAND_FINGER_JOINT_IDS
    limits = PANDA_ARM_JOINT_LIMITS_RAD if arm else PANDA_HAND_FINGER_LIMITS_M
    actuator_ids = tuple(f"actuator{i}" for i in range(1, 8)) if arm else ("actuator8",)
    tcp = FrameReference(entity, "link7" if arm else "hand")
    required = panda_arm_required_state(entity, tcp) if arm else panda_hand_required_state(entity, tcp)
    return LeafProfileBindingV1(
        "leaf-profile-binding-v1", "synthetic_fixture", profile_kind, profile_id,
        action_schema, scene.identity_hash, resolved.root_assembly_id,
        resolved.root_revision, resolved.root_logical_content_sha256,
        ("arm",) if arm else ("hand",), "existing_entity_subcomponent_ref",
        "control_group", "arm-control" if arm else "hand-control", entity,
        asset, "v1", _SOURCE_CLOSURE, "canonical-joint-position-v1",
        "c" * 64, "arm-writer" if arm else "hand-writer",
        "arm-control" if arm else "hand-control", "synthetic-provider",
        "fixture-v1", "d" * 64, "cpu", 0.002, 5,
        tuple(JointReference(entity, joint_id) for joint_id in joint_ids),
        "radian" if arm else "meter", tuple(limits),
        tuple(ActuatorReference(entity, actuator) for actuator in actuator_ids),
        tuple(LeafJointActuatorBindingV1(
            "leaf-joint-actuator-binding-v1", JointReference(entity, joint),
            ActuatorReference(entity, actuator),
        ) for joint, actuator in zip(PANDA_ARM_JOINT_IDS, actuator_ids, strict=True)) if arm else (),
        tcp, "T_parent_from_tcp", _IDENTITY, required,
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


def _case(*, split=False):
    scene = _split_scene() if split else _scene()
    root = _assembly(scene, split=split)
    resolved = resolve_logical_assembly(root, scene, {})
    initial = tuple(_binding(scene, resolved, arm=arm, split=split) for arm in (True, False))
    base_sections = tuple(sorted(
        (default_leaf_profile_section(binding) for binding in initial),
        key=lambda section: section.member_path,
    ))
    bindings = tuple(sorted((
        replace(binding, configuration_identity_sha256=next(
            section.configuration_identity_sha256 for section in base_sections
            if section.member_path == binding.member_path
        )) for binding in initial
    ), key=lambda binding: binding.member_path))
    preset = LeafControlPresetV1(
        "leaf-control-preset-v1", "r02b-default-preset", "r1", base_sections,
    )
    plan = compile_effective_leaf_plan(
        scene, root, {}, bindings, preset, source_closure_sha256=_SOURCE_CLOSURE,
    )
    return scene, root, bindings, preset, plan


def _receipt(plan, *, materialization_id="materialization-1", configuration_revision="config-r1",
             slot_alias=False, swap_transmission=False, swap_hand_tendon_target=False,
             omit_tendon=False, omit_equality=False):
    joints = []
    actuators = []
    frames = []
    tendons = []
    equalities = []
    for entry in plan.leaves:
        binding = entry.binding
        if binding.profile_kind == "arm_position":
            for index, ref in enumerate(binding.joint_order):
                joints.append(LeafNativeJointMappingV1(
                    "leaf-native-joint-mapping-v1", ref, f"native_arm_joint_{index + 1}",
                    index, index, index, "radian",
                ))
            for index, (joint, actuator) in enumerate(zip(
                binding.joint_order, binding.actuator_order, strict=True,
            )):
                target_id = f"native_arm_joint_{index + 1}"
                if swap_transmission and index == 0:
                    target_id = f"native_arm_joint_{index + 2}"
                actuators.append(LeafNativeActuatorMappingV1(
                    "leaf-native-actuator-mapping-v1", actuator,
                    f"native_arm_actuator_{index + 1}", index, index,
                    tuple(binding.joint_position_limits[index]), "radian", "joint", target_id,
                ))
            frames.append(LeafNativeFrameMappingV1(
                "leaf-native-frame-mapping-v1", binding.tcp_frame, "native_link7", 7,
            ))
        else:
            for index, ref in enumerate(binding.joint_order, 7):
                joints.append(LeafNativeJointMappingV1(
                    "leaf-native-joint-mapping-v1", ref, f"native_hand_joint_{index - 6}",
                    index, index, index, "meter",
                ))
            actuators.append(LeafNativeActuatorMappingV1(
                "leaf-native-actuator-mapping-v1", binding.actuator_order[0],
                "native_hand_actuator_8", 7, 0 if slot_alias else 7, (0.0, 255.0),
                "native_ctrl", "tendon",
                "wrong_native_tendon" if swap_hand_tendon_target else "native_hand_tendon",
            ))
            tendons.append(LeafNativeTendonMappingV1(
                "leaf-native-tendon-mapping-v1", binding.tendon_identity, "native_hand_tendon",
            ))
            equalities.append(binding.equality_identity)
            frames.append(LeafNativeFrameMappingV1(
                "leaf-native-frame-mapping-v1", binding.tcp_frame, "native_hand", 8,
            ))
    return LeafMaterializationReceiptV1(
        "leaf-materialization-receipt-v1", "synthetic_fixture",
        plan.scene_identity_sha256, plan.source_closure_sha256,
        plan.identity_sha256, plan.provider_name, plan.provider_version,
        plan.provider_build_sha256, plan.backend, materialization_id,
        configuration_revision, 9, 9, 8, 9, 9, 1, 1,
        tuple(reversed(joints)), tuple(reversed(actuators)), tuple(reversed(frames)),
        () if omit_tendon else tuple(tendons),
        () if omit_equality else tuple(equalities),
    )


def _publication(scene, receipt, *, step=0, time_s=0.0, revision=3,
                 episode="episode-1", reset_id="reset-" + "1" * 64,
                 scene_instance="scene-instance-1", include_arm=True, include_hand=True,
                 plan=None):
    boundary = StateBoundaryIdentity(
        "state-boundary-identity-v1", episode, reset_id, scene.identity_hash,
        scene_instance, receipt.materialization_id, step, revision,
    )
    clock = StateSampleClock("state-sample-clock-v1", "evaluation_boundary", step, time_s)
    joints = []
    frames = []
    if plan is None:
        bindings = (("arm_position", "panda", tuple(JointReference("panda", name) for name in PANDA_ARM_JOINT_IDS), FrameReference("panda", "link7")),
                    ("hand_position", "panda", tuple(JointReference("panda", name) for name in PANDA_HAND_FINGER_JOINT_IDS), FrameReference("panda", "hand")))
    else:
        bindings = tuple((entry.binding.profile_kind, entry.binding.entity_id,
                          entry.binding.joint_order, entry.binding.tcp_frame)
                         for entry in plan.leaves)
    for kind, entity, joint_refs, tcp in bindings:
        if (kind == "arm_position" and not include_arm) or (kind == "hand_position" and not include_hand):
            continue
        for ref in joint_refs:
            if kind == "arm_position":
                index = PANDA_ARM_JOINT_IDS.index(ref.joint_id)
                position, joint_kind, unit, velocity_unit = _ARM_CURRENT[index], "revolute", "radian", "radian_per_second"
            else:
                position, joint_kind, unit, velocity_unit = 0.02, "prismatic", "meter", "meter_per_second"
            joints.append(TypedJointStateValue(
                "typed-joint-state-v1", entity, ref.joint_id, joint_kind, unit,
                (position,), velocity_unit, (0.0,),
            ))
        frames.append(TypedFrameStateValue(
            "typed-frame-state-v1", tcp,
            PoseWorld((0.45, 0.0, 0.5 if kind == "arm_position" else 0.4), (1.0, 0.0, 0.0, 0.0)),
        ))
    view = CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", boundary, clock,
        tuple(joints), tuple(frames), (),
    )
    lifetime = StateViewLifetime(
        "state-view-lifetime-v1", receipt.materialization_id, boundary,
        revision, "owned_snapshot", "retained",
    )
    return CanonicalStatePublicationV1("canonical-state-publication-v1", view, lifetime)


def _actions(*, arm_action=None, hand_action=None, plan=None):
    if plan is None:
        arm_entity, arm_writer, arm_order = "panda", "arm-writer", tuple(JointReference("panda", name) for name in PANDA_ARM_JOINT_IDS)
        hand_writer = "hand-writer"
    else:
        arm_binding = next(entry.binding for entry in plan.leaves if entry.binding.profile_kind == "arm_position")
        hand_binding = next(entry.binding for entry in plan.leaves if entry.binding.profile_kind == "hand_position")
        arm_entity, arm_writer, arm_order = arm_binding.entity_id, arm_binding.writer_id, arm_binding.joint_order
        hand_writer = hand_binding.writer_id
    return (
        LeafActionRequestV1(
            "leaf-action-request-v1", arm_writer,
            arm_action or ArmPositionActionV1(
                ARM_POSITION_ACTION_SCHEMA, arm_order, _ARM_TARGET,
            ),
        ),
        LeafActionRequestV1(
            "leaf-action-request-v1", hand_writer,
            hand_action or HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, 0.08),
        ),
    )


def _request(plan, receipt, publication, *, actions=None):
    return LeafControlIntervalRequestV1(
        "leaf-control-interval-request-v1", plan.identity_sha256, receipt,
        publication, receipt.configuration_revision,
        _actions(plan=plan) if actions is None else actions,
    )


class _SyntheticRuntime:
    """Synthetic IO only; every command still passes through production dispatch."""

    def __init__(self, scene, receipt, publication, *, fault_mode=None, plan=None):
        self.scene = scene
        self.receipt = receipt
        self.publication = publication
        self.plan = plan if plan is not None else _case()[4]
        self.clock = LeafRuntimeClockV1(
            "leaf-runtime-clock-v1", publication.view.boundary,
            publication.view.sample_clock, receipt.configuration_revision,
        )
        self.fault_mode = fault_mode
        self.fault = None
        self.active_plan = None
        self.consumed = set()
        self.begin_calls = 0
        self.apply_calls = 0
        self.step_calls = 0
        self.publish_calls = 0
        self.latch_calls = 0
        self.ctrl = {}
        self.applied_patches = []
        self.closed = False
        self.close_calls = 0

    @property
    def leaf_control_fault(self):
        return self.fault

    @property
    def active_leaf_plan_identity(self):
        return self.active_plan

    def read_leaf_runtime_clock(self):
        if self.fault_mode == "readback_after_apply" and self.apply_calls:
            raise OSError("synthetic public clock readback unavailable")
        return self.clock

    def validate_leaf_materialization(self, receipt, plan):
        assert receipt.provenance_kind == "synthetic_fixture"
        assert receipt.identity_sha256 == self.receipt.identity_sha256
        receipt.validate_against_plan(plan)

    def validate_leaf_writer_available(self, writer_id, actuator_refs, receipt):
        assert writer_id in {entry.binding.writer_id for entry in self.plan.leaves}
        assert actuator_refs
        assert receipt.identity_sha256 == self.receipt.identity_sha256

    def begin_leaf_control_interval(self, plan_identity, boundary_id):
        if self.fault is not None:
            raise RuntimeError("synthetic runtime is faulted")
        if boundary_id in self.consumed:
            raise RuntimeError("synthetic boundary already consumed")
        if self.active_plan not in (None, plan_identity):
            raise RuntimeError("synthetic plan switch refused")
        self.active_plan = plan_identity
        self.consumed.add(boundary_id)
        self.begin_calls += 1

    def apply_leaf_actuator_patch(self, patch):
        self.apply_calls += 1
        self.applied_patches.append(patch)
        for value in patch.slot_values:
            self.ctrl[value.ctrl_slot] = value.value
        if self.fault_mode == "hand_write_then_raise" and patch.writer_id == "hand-writer":
            raise RuntimeError("synthetic second writer wrote before raising")
        target = patch.target
        profile_kind = "arm_position" if type(target) is ArmPositionTargetV1 else "hand_position"
        clock = self.clock
        ack = LeafApplicationAckV1(
            "leaf-application-ack-v1", profile_kind, target.profile_id,
            target.action_schema_id, target.identity_hash, target.writer_id,
            target.binding_identity_hash, target.source_closure_sha256,
            target.scene_identity_hash, target.joint_order, target.actuator_order,
            target.source_boundary, target.sample_clock,
            clock.boundary, clock.sample_clock,
        )
        if self.fault_mode == "hand_wrong_ack" and patch.writer_id == "hand-writer":
            ack = replace(ack, target_identity_hash="f" * 64)
        return LeafApplyResultV1(
            "leaf-apply-result-v1", patch.writer_id,
            patch.command_identity_sha256, patch.materialization_identity_sha256,
            tuple(item.ctrl_slot for item in patch.slot_values), ack,
        )

    def step_leaf_control_interval(self, *, substeps):
        self.step_calls += 1
        assert substeps == 5
        if self.fault_mode == "step_raise_partial":
            self._advance(time_delta=0.004)
            raise RuntimeError("synthetic step failed after partial public progress")
        self._advance(time_delta=0.01)
        if self.fault_mode == "step_raise_after_advance":
            raise RuntimeError("synthetic step raised after advancing the public clock")

    def _advance(self, *, time_delta):
        before = self.clock
        step = before.boundary.control_step + 1
        boundary = replace(before.boundary, control_step=step, state_revision=before.boundary.state_revision + 1)
        clock = StateSampleClock("state-sample-clock-v1", "evaluation_boundary", step,
                                 before.sample_clock.simulation_time_s + time_delta)
        self.clock = LeafRuntimeClockV1(
            "leaf-runtime-clock-v1", boundary, clock, before.configuration_revision,
        )

    def publish_leaf_state(self, scene, requirements):
        self.publish_calls += 1
        source = self.publication.view.boundary
        return _publication(
            scene, self.receipt, step=self.clock.boundary.control_step,
            time_s=self.clock.sample_clock.simulation_time_s,
            revision=self.clock.boundary.state_revision,
            episode=source.episode_id, reset_id=source.reset_sample_id,
            scene_instance=source.scene_instance_id,
            plan=self.plan,
        )

    def latch_leaf_control_fault(self, progress, error):
        assert type(progress) is LeafDispatchProgressV1
        assert type(progress.fault) is ExecutionFaultV1
        self.fault = progress
        self.latch_calls += 1

    def reset(self, receipt, publication):
        assert (receipt.materialization_id, publication.view.boundary.episode_id,
                publication.view.boundary.reset_sample_id,
                publication.view.boundary.scene_instance_id) != (
                self.receipt.materialization_id,
                self.publication.view.boundary.episode_id,
                self.publication.view.boundary.reset_sample_id,
                self.publication.view.boundary.scene_instance_id,
        )
        self.receipt, self.publication = receipt, publication
        self.clock = LeafRuntimeClockV1(
            "leaf-runtime-clock-v1", publication.view.boundary,
            publication.view.sample_clock, receipt.configuration_revision,
        )
        self.fault = None
        self.active_plan = None
        self.consumed.clear()
        self.ctrl.clear()

    def close(self):
        if not self.closed:
            self.closed = True
            self.close_calls += 1


def test_effective_plan_is_deterministic_strict_and_derives_override_status():
    scene, root, bindings, preset, plan = _case()
    assert plan.profile_status == "preset"
    repeated = compile_effective_leaf_plan(
        scene, root, {}, tuple(reversed(bindings)), preset,
        source_closure_sha256=_SOURCE_CLOSURE,
    )
    assert repeated.identity_sha256 == plan.identity_sha256

    arm = preset.sections[0]
    changed_arm = replace(arm, configuration=(("joint_position_correction_gain", 3.0),))
    override = LeafProfileOverrideV1("leaf-profile-override-v1", arm.member_path, changed_arm)
    partial = compile_effective_leaf_plan(
        scene, root, {}, bindings, preset, (override,),
        source_closure_sha256=_SOURCE_CLOSURE,
    )
    assert partial.profile_status == "partially_overridden"
    assert partial.identity_sha256 != plan.identity_sha256
    unchanged = LeafProfileOverrideV1("leaf-profile-override-v1", arm.member_path, arm)
    no_effect = compile_effective_leaf_plan(
        scene, root, {}, bindings, preset, (unchanged,),
        source_closure_sha256=_SOURCE_CLOSURE,
    )
    assert no_effect.profile_status == "preset"
    assert no_effect.leaves[0].effective_configuration_identity_sha256 == plan.leaves[0].effective_configuration_identity_sha256
    assert no_effect.identity_sha256 == plan.identity_sha256

    assert decode_leaf_profile_section(arm.to_mapping()) == arm
    assert decode_leaf_control_preset(preset.to_mapping()) == preset
    assert decode_leaf_profile_override(unchanged.to_mapping()) == unchanged
    malformed = arm.to_mapping()
    malformed["member_path"] = "arm"
    with pytest.raises(TypeError, match="member_path"):
        decode_leaf_profile_section(malformed)

    hand = preset.sections[1]
    changed_hand = replace(hand, configuration=tuple(
        (key, 7.5 if key == "gripper_default_force_N" else value)
        for key, value in hand.configuration
    ))
    custom = compile_effective_leaf_plan(
        scene, root, {}, bindings, preset,
        (override, LeafProfileOverrideV1("leaf-profile-override-v1", hand.member_path, changed_hand)),
        source_closure_sha256=_SOURCE_CLOSURE,
    )
    assert custom.profile_status == "custom"
    snapshot = custom.to_mapping()
    snapshot["leaves"][0]["section"]["configuration"][0][1] = 999.0
    assert custom.leaves[0].section.configuration[0][1] != 999.0

    with pytest.raises(ValueError, match="duplicate local override"):
        compile_effective_leaf_plan(
            scene, root, {}, bindings, preset, (override, override),
            source_closure_sha256=_SOURCE_CLOSURE,
        )
    with pytest.raises(ValueError, match="unknown or ambiguous"):
        compile_effective_leaf_plan(
            scene, root, {}, bindings, preset,
            (LeafProfileOverrideV1("leaf-profile-override-v1", ("missing",),
                                    replace(arm, member_path=("missing",))),),
            source_closure_sha256=_SOURCE_CLOSURE,
        )
    with pytest.raises(ValueError, match="cannot switch"):
        compile_effective_leaf_plan(
            scene, root, {}, bindings, preset,
            (LeafProfileOverrideV1("leaf-profile-override-v1", arm.member_path,
                                    replace(hand, member_path=arm.member_path)),),
            source_closure_sha256=_SOURCE_CLOSURE,
        )
    with pytest.raises(ValueError, match="Force-aware"):
        replace(hand, profile_kind="hand_force_aware")


def test_compiler_reresolves_current_scene_and_requires_unique_complete_coverage():
    scene, root, bindings, preset, _ = _case()
    changed_scene = replace(scene, scene_id="different-scene")
    with pytest.raises(ValueError):
        compile_effective_leaf_plan(
            changed_scene, root, {}, bindings, preset,
            source_closure_sha256=_SOURCE_CLOSURE,
        )
    with pytest.raises(ValueError, match="uniquely cover"):
        compile_effective_leaf_plan(
            scene, root, {}, bindings[:1], LeafControlPresetV1(
                "leaf-control-preset-v1", "arm-only", "r1", (preset.sections[0],),
            ), source_closure_sha256=_SOURCE_CLOSURE,
        )
    with pytest.raises(ValueError, match="source closure"):
        compile_effective_leaf_plan(
            scene, root, {}, bindings, preset, source_closure_sha256="e" * 64,
        )


def test_native_mapping_uses_explicit_relationships_and_rejects_aliases_or_missing_hand_sources():
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    receipt.validate_against_plan(plan)
    assert receipt.provenance_kind == "synthetic_fixture"
    assert [item.ctrl_slot for item in receipt.actuators] != sorted(item.ctrl_slot for item in receipt.actuators)
    for invalid in (
        _receipt(plan, slot_alias=True),
        _receipt(plan, swap_transmission=True),
        _receipt(plan, swap_hand_tendon_target=True),
        _receipt(plan, omit_tendon=True),
        _receipt(plan, omit_equality=True),
    ):
        with pytest.raises(ValueError):
            invalid.validate_against_plan(plan)


def test_arm_and_hand_adapters_need_only_their_own_typed_leaf_state():
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    arm_publication = _publication(scene, receipt, include_arm=True, include_hand=False)
    hand_publication = _publication(scene, receipt, include_arm=False, include_hand=True)
    arm = prepare_leaf_command(
        plan, "arm-writer", _actions()[0].action, arm_publication,
        receipt, receipt.configuration_revision, scene=scene,
    )
    hand = prepare_leaf_command(
        plan, "hand-writer", _actions()[1].action, hand_publication,
        receipt, receipt.configuration_revision, scene=scene,
    )
    assert type(arm.target).__name__ == "ArmPositionTargetV1"
    assert type(hand.target).__name__ == "HandPositionTargetV1"
    assert len(arm.slot_values) == 7 and len(hand.slot_values) == 1
    assert hand.requested_opening_m == 0.08
    assert hand.servo_opening_m == pytest.approx(0.042)
    assert hand.native_ctrl == pytest.approx(133.875)
    assert hand.native_ctrl != hand.requested_opening_m


def test_adapter_algorithms_share_legacy_numeric_owners_without_behavior_drift():
    cfg = ActionConfig()
    class _Kinematics:
        limits = __import__("numpy").asarray(PANDA_ARM_JOINT_LIMITS_RAD)
        base_transform = __import__("numpy").eye(4)
        source_sha256 = _HASH
    class _State:
        joint_position = {
            **{f"panda-v1/{name}": value for name, value in zip(PANDA_ARM_JOINT_IDS, _ARM_CURRENT, strict=True)},
            "panda-v1/finger_joint1": 0.02,
            "panda-v1/finger_joint2": 0.02,
        }
        pose_world = {"panda-v1/ee": PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))}
    requested = RequestedAction("absolute_joint", None, "none", (*_ARM_TARGET, 0.0))
    controller = CanonicalPandaController(_Kinematics(), artifact_hash=_HASH, config=cfg)
    _canonical, target = controller.compute(_State(), requested)
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    arm_publication = _publication(scene, receipt, include_arm=True, include_hand=False)
    arm_command = prepare_leaf_command(
        plan, "arm-writer", _actions()[0].action, arm_publication,
        receipt, receipt.configuration_revision, scene=scene,
    )
    for native, legacy in zip(arm_command.slot_values, target.arm_servo_position.values(), strict=True):
        assert native.value == pytest.approx(legacy)

    refs = type("Refs", (), {
        "gripper_qpos_ids": __import__("numpy").asarray((0, 1)),
        "gripper_actuator_ids": __import__("numpy").asarray((0,)),
    })()
    gripper = PandaGripperController(references=refs, config=cfg)
    snapshot = type("Snapshot", (), {"qpos": __import__("numpy").asarray((0.02, 0.02))})()
    legacy_ctrl = gripper.ctrl_for_target(snapshot=snapshot, target=GripperTarget(0.08, 5.0))
    leaf_hand = prepare_leaf_command(
        plan, "hand-writer", _actions()[1].action,
        _publication(scene, receipt, include_arm=False, include_hand=True),
        receipt, receipt.configuration_revision, scene=scene,
    )
    assert leaf_hand.native_ctrl == pytest.approx(legacy_ctrl)
    assert position_gripper_ctrl_for_opening(
        leaf_hand.servo_opening_m, cfg.gripper_opening_range_m,
        cfg.gripper_close_ctrl, cfg.gripper_open_ctrl,
    ) == pytest.approx(legacy_ctrl)


def test_full_dispatch_preflights_all_writers_then_applies_acknowledges_and_steps_once():
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt)
    runtime = _SyntheticRuntime(scene, receipt, publication)
    result = dispatch_leaf_control_interval(
        plan, _request(plan, receipt, publication), scene=scene, runtime=runtime,
    )
    assert result.interval_completed is True
    assert len(result.prepared_commands) == len(result.apply_results) == 2
    assert {slot for command in result.prepared_commands for slot in
            (item.ctrl_slot for item in command.slot_values)} == set(range(8))
    assert [item.writer_id for item in result.apply_results] == ["arm-writer", "hand-writer"]
    assert runtime.step_calls == runtime.publish_calls == 1
    assert result.next_publication.view.boundary.control_step == 1


def test_separate_arm_and_hand_entities_each_dispatch_through_the_same_production_owner():
    scene, _root, _bindings, _preset, plan = _case(split=True)
    assert {entry.binding.entity_id for entry in plan.leaves} == {"panda-arm", "panda-hand"}
    receipt = _receipt(plan)
    publication = _publication(scene, receipt, plan=plan)
    runtime = _SyntheticRuntime(scene, receipt, publication, plan=plan)
    result = dispatch_leaf_control_interval(
        plan, _request(plan, receipt, publication), scene=scene, runtime=runtime,
    )
    assert result.interval_completed is True
    assert {value.actuator.entity_id for command in result.prepared_commands
            for value in command.slot_values} == {"panda-arm", "panda-hand"}
    assert runtime.apply_calls == 2 and runtime.step_calls == 1
    assert len(runtime.consumed) == 1
    assert result.prepared_commands[1].requested_opening_m == 0.08
    assert result.prepared_commands[1].servo_opening_m == pytest.approx(0.042)
    assert result.prepared_commands[1].native_ctrl == pytest.approx(133.875)
    runtime.close()
    runtime.close()
    assert runtime.close_calls == 1


def test_last_leaf_invalid_is_rejected_before_any_compute_or_runtime_mutation(monkeypatch):
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt)
    runtime = _SyntheticRuntime(scene, receipt, publication)
    bad_hand = object.__new__(HandPositionActionV1)
    object.__setattr__(bad_hand, "schema_version", HAND_POSITION_ACTION_SCHEMA)
    object.__setattr__(bad_hand, "opening_m", False)
    object.__setattr__(bad_hand, "input_representation", "opening_m")
    object.__setattr__(bad_hand, "requested_normalized", None)
    bad_request = _request(plan, receipt, publication,
                           actions=_actions(hand_action=bad_hand))
    import task_env.runtime.sessions.leaf_control as leaf_control
    monkeypatch.setattr(leaf_control, "absolute_joint_position_servo",
                        lambda *args: pytest.fail("adapter compute ran before full preflight"))
    with pytest.raises(ValueError, match="finite total opening"):
        dispatch_leaf_control_interval(plan, bad_request, scene=scene, runtime=runtime)
    assert (runtime.begin_calls, runtime.apply_calls, runtime.step_calls,
            len(runtime.consumed), runtime.fault) == (0, 0, 0, 0, None)


def test_wrong_ack_and_write_then_raise_preserve_partial_facts_and_latch():
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt)
    for mode, expected_applied, expected_unknown, expected_acknowledged in (
        ("hand_wrong_ack", ("arm-writer", "hand-writer"), (), ("arm-writer",)),
        ("hand_write_then_raise", ("arm-writer",), ("hand-writer",), ("arm-writer",)),
    ):
        runtime = _SyntheticRuntime(scene, receipt, publication, fault_mode=mode)
        with pytest.raises((ValueError, RuntimeError)) as caught:
            dispatch_leaf_control_interval(
                plan, _request(plan, receipt, publication), scene=scene, runtime=runtime,
            )
        progress = caught.value.leaf_dispatch_progress
        assert progress.attempted_writers == ("arm-writer", "hand-writer")
        assert progress.applied_writers == expected_applied
        assert progress.unknown_writers == expected_unknown
        assert progress.acknowledged_writers == expected_acknowledged
        assert progress.failed_writer == "hand-writer"
        assert progress.fault.physical_progress == "not_advanced"
        assert [item.writer_id for item in progress.prepared_commands] == ["arm-writer", "hand-writer"]
        expected_returned = ("arm-writer", "hand-writer") if mode == "hand_wrong_ack" else ("arm-writer",)
        assert tuple(item.writer_id for item in progress.returned_apply_results) == expected_returned
        assert progress.returned_apply_results[0].ack.target_identity_hash == progress.prepared_commands[0].target.identity_hash
        if mode == "hand_wrong_ack":
            assert progress.returned_apply_results[1].ack.target_identity_hash != progress.prepared_commands[1].target.identity_hash
        assert runtime.step_calls == 0 and runtime.latch_calls == 1
        with pytest.raises(RuntimeError, match="fault-latched"):
            preflight_leaf_control_interval(
                plan, _request(plan, receipt, publication), scene=scene, runtime=runtime,
            )


def test_clock_readback_and_step_failures_report_actual_unknown_or_partial_progress():
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt)
    runtime = _SyntheticRuntime(scene, receipt, publication, fault_mode="readback_after_apply")
    with pytest.raises(OSError) as caught:
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                       scene=scene, runtime=runtime)
    assert caught.value.leaf_dispatch_progress.fault.physical_progress == "unknown", caught.value.leaf_dispatch_progress.fault.to_mapping()
    assert caught.value.leaf_dispatch_progress.fault.readback_error
    assert runtime.step_calls == 0

    runtime = _SyntheticRuntime(scene, receipt, publication, fault_mode="step_raise_partial")
    with pytest.raises(RuntimeError) as caught:
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                       scene=scene, runtime=runtime)
    fault = caught.value.execution_fault
    assert fault.physical_progress == "unknown"
    assert fault.transition_status == "incomplete"
    assert runtime.step_calls == 1 and runtime.publish_calls == 0


def test_reset_requires_new_episode_reset_and_materialization_context_to_clear_fault():
    scene, _root, _bindings, _preset, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt)
    runtime = _SyntheticRuntime(scene, receipt, publication, fault_mode="hand_write_then_raise")
    with pytest.raises(RuntimeError):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                       scene=scene, runtime=runtime)
    new_receipt = _receipt(plan, materialization_id="materialization-2", configuration_revision="config-r2")
    new_publication = _publication(
        scene, new_receipt, episode="episode-2", reset_id="reset-" + "2" * 64,
        scene_instance="scene-instance-2", revision=0,
    )
    runtime.fault_mode = None
    runtime.reset(new_receipt, new_publication)
    result = dispatch_leaf_control_interval(
        plan, _request(plan, new_receipt, new_publication), scene=scene, runtime=runtime,
    )
    assert result.interval_completed
    assert runtime.latch_calls == 1


def test_switch_repeat_stale_source_and_identity_mismatch_fail_before_apply():
    scene, _root, _bindings, preset, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt)
    runtime = _SyntheticRuntime(scene, receipt, publication)
    dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                   scene=scene, runtime=runtime)
    apply_calls = runtime.apply_calls
    with pytest.raises(ValueError, match="stale"):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                       scene=scene, runtime=runtime)
    assert runtime.apply_calls == apply_calls

    arm = preset.sections[0]
    changed = replace(arm, configuration=(("joint_position_correction_gain", 3.5),))
    switched = compile_effective_leaf_plan(
        scene, _assembly(scene), {}, tuple(entry.binding for entry in plan.leaves), preset,
        (LeafProfileOverrideV1("leaf-profile-override-v1", arm.member_path, changed),),
        source_closure_sha256=_SOURCE_CLOSURE,
    )
    switched_receipt = _receipt(switched)
    switched_pub = _publication(scene, switched_receipt)
    switch_runtime = _SyntheticRuntime(scene, receipt, publication)
    dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                   scene=scene, runtime=switch_runtime)
    with pytest.raises(ValueError, match="cannot be switched"):
        preflight_leaf_control_interval(
            switched, _request(switched, switched_receipt, switched_pub),
            scene=scene, runtime=switch_runtime,
        )
    assert switch_runtime.apply_calls == 2

    # Move the public fixture clock back to the exact already-consumed source
    # boundary to exercise the replay guard after full static preflight.
    runtime.clock = LeafRuntimeClockV1(
        "leaf-runtime-clock-v1", publication.view.boundary,
        publication.view.sample_clock, receipt.configuration_revision,
    )
    with pytest.raises(RuntimeError, match="already consumed"):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                       scene=scene, runtime=runtime)
    assert runtime.apply_calls == apply_calls
    with pytest.raises(RuntimeError, match="fault-latched"):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication),
                                       scene=scene, runtime=runtime)

    uncompiled = replace(plan)
    with pytest.raises(TypeError, match="effective plan"):
        preflight_leaf_control_interval(
            uncompiled, _request(uncompiled, receipt, publication),
            scene=scene, runtime=runtime,
        )
    assert runtime.apply_calls == apply_calls


def test_force_aware_and_hand_config_outside_source_contract_remain_refused():
    scene, root, bindings, preset, _plan = _case()
    hand = preset.sections[1]
    with pytest.raises(ValueError, match="0.08 m"):
        invalid = replace(hand, configuration=tuple(
            (key, 0.07 if key == "gripper_opening_range_m" else value)
            for key, value in hand.configuration
        ))
        compile_effective_leaf_plan(
            scene, root, {}, bindings, preset,
            (LeafProfileOverrideV1("leaf-profile-override-v1", hand.member_path, invalid),),
            source_closure_sha256=_SOURCE_CLOSURE,
        )
