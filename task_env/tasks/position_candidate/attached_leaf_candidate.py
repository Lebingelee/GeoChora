"""R03c task-owned two-Entity attached leaf candidate."""
from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace
import hashlib
import json

from ...artifacts import (
    ActuatorReference, FrameReference, JointReference, PoseWorld,
)
from ...controllers.canonical.contracts import (
    ControlGroupActionV1, StructuredActionRequestV1, digest,
)
from ...controllers.canonical.leaf_profiles import (
    ARM_POSITION_ACTION_SCHEMA, ARM_POSITION_PROFILE_ID,
    HAND_POSITION_ACTION_SCHEMA, HAND_POSITION_PROFILE_ID,
    PANDA_ARM_JOINT_IDS, PANDA_ARM_JOINT_LIMITS_RAD,
    PANDA_HAND_FINGER_JOINT_IDS, PANDA_HAND_FINGER_LIMITS_M,
    PANDA_HAND_TENDON_IDENTITY, PANDA_HAND_TENDON_COEFFICIENTS,
    PANDA_HAND_EQUALITY_IDENTITY, PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M,
    PANDA_HAND_ACTUATOR_GAINPRM, PANDA_HAND_ACTUATOR_BIASPRM,
    ArmPositionActionV1, HandPositionActionV1, LeafJointActuatorBindingV1,
    LeafProfileBindingV1, panda_arm_required_state, panda_hand_required_state,
)
from ...controllers.canonical.leaf_plan import (
    LeafControlPresetV1, LeafProfileOverrideV1, LeafProfileSectionV1,
    compile_effective_leaf_plan, default_leaf_profile_section,
)
from ...environment import compile_task_artifact_v1, sample_episode_reset_plan
from ...environment.configuration import resolve_env_config
from ...environment.task_source import TaskInitializationV1
from ...runtime.sessions.provenance import provider_build_identity
from ...runtime.sessions.source import RuntimeSource
from .fixed_attachment_candidate import build_fixed_attachment_candidate


R03C_TASK_ID = "phase-ii-r03c-attached-leaf-position"
R03C_TASK_VERSION = "candidate-v1"
R03C_SEED = 31
ARM_WRITER_ID = "panda-arm/arm-position-leaf"
HAND_WRITER_ID = "panda-hand/hand-position-leaf"
ARM_HOME = (0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853)


@dataclass(frozen=True)
class AttachedLeafActionSetV1:
    schema_version: str
    scene_identity_sha256: str
    plan_identity_sha256: str
    arm: ArmPositionActionV1
    hand: HandPositionActionV1

    def __post_init__(self):
        if self.schema_version != "r03c-attached-leaf-action-set-v1":
            raise ValueError("unsupported R03c attached leaf action-set schema")
        if type(self.arm) is not ArmPositionActionV1 or type(self.hand) is not HandPositionActionV1:
            raise TypeError("R03c action-set requires typed Arm and Hand values")
        self.arm.validate(); self.hand.validate()
        for value in (self.scene_identity_sha256, self.plan_identity_sha256):
            if type(value) is not str or len(value) != 64:
                raise ValueError("R03c action-set requires SHA-256 Scene and plan identities")

    def structured_request(self, scene, plan):
        if (scene.identity_hash, plan.identity_sha256) != (
                self.scene_identity_sha256, self.plan_identity_sha256):
            raise ValueError("R03c action-set belongs to another Scene/effective plan")
        actions = {
            ARM_WRITER_ID: (self.arm, tuple(self.arm.position_rad)),
            HAND_WRITER_ID: (self.hand, (float(self.hand.opening_m),)),
        }
        groups = []
        for entry in plan.leaves:
            typed, values = actions[entry.binding.writer_id]
            groups.append(ControlGroupActionV1(
                "control-group-action-v1", entry.binding.entity_id,
                entry.binding.control_group_id, entry.binding.action_schema_id, values,
            ))
        request = StructuredActionRequestV1(
            "structured-action-request-v1", scene.identity_hash,
            plan.identity_sha256, tuple(sorted(groups, key=lambda item: (item.entity_id, item.group_id))),
        )
        request.validate()
        return request


@dataclass(frozen=True)
class AttachedLeafCandidate:
    env: object
    scene: object
    task_source: object
    artifact: object
    reset_plan: object
    source: RuntimeSource
    assembly: object
    attachment_plan: object
    bindings: tuple[LeafProfileBindingV1, ...]
    preset: LeafControlPresetV1
    overrides: tuple[LeafProfileOverrideV1, ...]
    plan: object
    provider_build_identity: dict[str, object]
    source_inventory: dict[str, object]
    arm_gain: float
    hand_stiffness_N_per_m: float
    episode_id: str
    arm_active: bool
    hand_active: bool


def _bindings(candidate, provider_version, build_sha):
    scene = candidate.scene
    assembly = candidate.assembly
    asset_by_entity = {item.entity_id: item for item in scene.entities}
    assets = {(item.asset_id, item.asset_version): item for item in scene.assets}
    identity_pose = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    records = []
    for is_arm in (True, False):
        entity_id = "panda-arm" if is_arm else "panda-hand"
        path = ("arm",) if is_arm else ("hand",)
        kind = "arm_position" if is_arm else "hand_position"
        group = "arm-position" if is_arm else "hand-position"
        joints = PANDA_ARM_JOINT_IDS if is_arm else PANDA_HAND_FINGER_JOINT_IDS
        limits = PANDA_ARM_JOINT_LIMITS_RAD if is_arm else PANDA_HAND_FINGER_LIMITS_M
        actuators = tuple(f"actuator{i}" for i in range(1, 8)) if is_arm else ("actuator8",)
        tcp = FrameReference(entity_id, "link7" if is_arm else "hand")
        asset_instance = asset_by_entity[entity_id]
        asset = assets[(asset_instance.asset_id, asset_instance.asset_version)]
        binding = LeafProfileBindingV1(
            "leaf-profile-binding-v1", "declared", kind,
            ARM_POSITION_PROFILE_ID if is_arm else HAND_POSITION_PROFILE_ID,
            ARM_POSITION_ACTION_SCHEMA if is_arm else HAND_POSITION_ACTION_SCHEMA,
            scene.identity_hash, assembly.assembly_id, assembly.revision,
            assembly.logical_content_sha256, path, "entity_member", "entity", entity_id,
            entity_id, asset.asset_id, asset.asset_version,
            candidate.runtime_source.source_closure_digest, "canonical-joint-position-v1", "0" * 64,
            ARM_WRITER_ID if is_arm else HAND_WRITER_ID, group,
            "mujoco", provider_version, build_sha, "cpu", 0.002, 5,
            tuple(JointReference(entity_id, item) for item in joints),
            "radian" if is_arm else "meter", tuple(limits),
            tuple(ActuatorReference(entity_id, item) for item in actuators),
            tuple(LeafJointActuatorBindingV1(
                "leaf-joint-actuator-binding-v1", JointReference(entity_id, joint),
                ActuatorReference(entity_id, actuator),
            ) for joint, actuator in zip(joints, actuators, strict=True)) if is_arm else (),
            tcp, "T_parent_from_tcp", identity_pose,
            panda_arm_required_state(entity_id, tcp) if is_arm else panda_hand_required_state(entity_id, tcp),
            None if is_arm else PANDA_HAND_TENDON_IDENTITY,
            () if is_arm else PANDA_HAND_TENDON_COEFFICIENTS,
            None if is_arm else PANDA_HAND_EQUALITY_IDENTITY,
            None if is_arm else PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M,
            None if is_arm else "opening_m = finger_joint1_q_m + finger_joint2_q_m",
            None if is_arm else "ctrl = 3187.5 * opening_m",
            None if is_arm else (0.0, 255.0),
            () if is_arm else PANDA_HAND_ACTUATOR_GAINPRM,
            () if is_arm else PANDA_HAND_ACTUATOR_BIASPRM,
        )
        records.append(binding)
    defaults = tuple(sorted((default_leaf_profile_section(item) for item in records),
                             key=lambda item: item.member_path))
    bindings = tuple(sorted((replace(item, configuration_identity_sha256=next(
        section.configuration_identity_sha256 for section in defaults
        if section.member_path == item.member_path
    )) for item in records), key=lambda item: item.member_path))
    return bindings, defaults


def build_attached_leaf_candidate(*, environment_type, arm_gain=2.5,
                                  hand_stiffness_N_per_m=50.0, provider="mujoco", horizon=64,
                                  episode_id="E3", arm_active=True, hand_active=True):
    if provider != "mujoco" or arm_gain not in (2.5, 3.0) or hand_stiffness_N_per_m != 50.0:
        raise ValueError("R03c admits MuJoCo CPU, Arm gain 2.5/3.0, and the fixed Hand50 section")
    fixed = build_fixed_attachment_candidate()
    scene, assembly = fixed.scene, fixed.assembly
    task_id, version = R03C_TASK_ID, R03C_TASK_VERSION
    task_source = replace(
        fixed.task_source, task_id=task_id, version=version,
        initialization=TaskInitializationV1(
            "r03c-fixed-reset", "frozen-authored-v0", "training",
            "zero_named_joint_and_entity_velocities",
            "arm_targets_at_initial_joints_gripper_open",
        ),
    )
    legacy = replace(
        fixed.source_artifact, artifact_id="phase-ii-r03c-attached-leaf-v0",
        task_id=task_id, artifact_version=version,
        initialization=replace(fixed.source_artifact.initialization, reset_validity="r03c-fixed-reset"),
        semantics=replace(fixed.source_artifact.semantics,
                          evaluator="r03c_attached_leaf_oracle",
                          success_definition="fixed_attachment_motion_only"),
    )
    frame_bindings = {name: FrameReference(*name.split("/", 1))
                      for name in legacy.semantics.required_poses}
    joint_bindings = {name: JointReference(*name.split("/", 1))
                      for name in legacy.semantics.required_joints}
    artifact = compile_task_artifact_v1(
        task_source, scene, legacy, frame_bindings=frame_bindings,
        joint_bindings=joint_bindings,
    )
    reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=R03C_SEED)
    config = resolve_env_config(
        task_uid=task_id, scene_uid=scene.scene_id,
        runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 5, "prewarm": False},
        render={"camera_obs": False},
    )
    source = replace(
        fixed.runtime_source, task_artifact_hash=artifact.identity_hash,
        composition=replace(fixed.runtime_source.composition, task_uid=task_id),
        config=config,
    )
    build_info = provider_build_identity("mujoco")
    build_sha = hashlib.sha256(json.dumps(
        build_info, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    bindings, defaults = _bindings(fixed, str(build_info["package_version"]), build_sha)
    preset = LeafControlPresetV1("leaf-control-preset-v1", "r03c-attached-default", "r1", defaults)
    overrides = []
    arm_default = next(item for item in defaults if item.member_path == ("arm",))
    if arm_gain == 3.0:
        overrides.append(LeafProfileOverrideV1(
            "leaf-profile-override-v1", ("arm",),
            replace(arm_default, configuration=(("joint_position_correction_gain", 3.0),)),
        ))
    hand_default = next(item for item in defaults if item.member_path == ("hand",))
    overrides.append(LeafProfileOverrideV1(
        "leaf-profile-override-v1", ("hand",),
        replace(hand_default, configuration=tuple(
            (key, 50.0 if key == "gripper_position_stiffness_N_per_m" else value)
            for key, value in hand_default.configuration
        )),
    ))
    overrides = tuple(overrides)
    plan = compile_effective_leaf_plan(
        scene, assembly, (), bindings, preset, overrides,
        source_closure_sha256=source.source_closure_digest,
        fixed_attachment_plan_identity_sha256=fixed.attachment_plan.identity_hash,
    )

    def build(_provider):
        return {
            "artifact": artifact, "task_source": task_source, "solution": None,
            "source": source, "reset_plan": reset_plan, "leaf_plan": plan,
            "logical_assembly": assembly, "fixed_attachment_plan": fixed.attachment_plan,
            "leaf_bindings": bindings, "leaf_preset": preset, "leaf_overrides": overrides,
            "provider_build_identity": build_info,
            "construction_id": digest({"artifact": artifact.identity_hash,
                                        "source": source.source_closure_digest,
                                        "plan": plan.identity_sha256}),
            "resolved_configuration": {"provider": _provider, "backend": "cpu",
                                        "effective_leaf_plan": plan.identity_sha256,
                                        "episode_id": episode_id,
                                        "arm_active": bool(arm_active),
                                        "hand_active": bool(hand_active)},
            "source_revision": "R03c-attached-entity-position-leaves-v1",
            "source_sha256": {"source_closure": source.source_closure_digest},
        }

    def fixed_seed(seed):
        if type(seed) is not int or seed != R03C_SEED:
            raise ValueError(f"R03c fixed ResetPlan requires seed {R03C_SEED}")
        return seed

    from ..reference_env import ReferenceTaskBinding
    binding = ReferenceTaskBinding(
        build=build, reset_sample=lambda _artifact, _seed: reset_plan.reset_sample,
        evaluate=lambda _state, _semantics: SimpleNamespace(
            reward=0.0, success=False, failure=False, metrics={},
        ),
        object_poses=(("panda-arm/link0", "arm_root"),), external_actions=True,
        interval_mode="grouped", recorder_mode="execution", reset_seed=fixed_seed,
    )
    env = environment_type.from_leaf_position_candidate(
        binding, provider=provider, backend="cpu", horizon=horizon,
        fixed_attachment=True,
    )
    return AttachedLeafCandidate(
        env, scene, task_source, artifact, reset_plan, source, assembly,
        fixed.attachment_plan, bindings, preset, overrides, plan, build_info,
        fixed.source_inventory, float(arm_gain), float(hand_stiffness_N_per_m), episode_id,
        bool(arm_active), bool(hand_active),
    )


def action_for_interval(candidate, interval, *, arm_active, hand_active):
    if type(interval) is not int or not 1 <= interval <= 64:
        raise ValueError("R03c curve interval must be in [1,64]")
    if arm_active and interval <= 16:
        arm_values = (0.1 * interval / 16.0,) + ARM_HOME[1:]
    elif arm_active and interval <= 32:
        arm_values = (0.1,) + ARM_HOME[1:]
    elif arm_active and interval <= 48:
        arm_values = (0.1 * (48 - interval) / 16.0,) + ARM_HOME[1:]
    else:
        arm_values = ARM_HOME
    if not hand_active or interval > 48:
        opening = 0.076
    elif interval <= 16:
        opening = 0.076 - 0.072 * interval / 16.0
    elif interval <= 32:
        opening = 0.004
    else:
        opening = 0.004 + 0.072 * (interval - 32) / 16.0
    arm_binding = next(item for item in candidate.bindings if item.profile_kind == "arm_position")
    arm = ArmPositionActionV1(ARM_POSITION_ACTION_SCHEMA, arm_binding.joint_order, tuple(arm_values))
    hand = HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, float(opening))
    return AttachedLeafActionSetV1(
        "r03c-attached-leaf-action-set-v1", candidate.scene.identity_hash,
        candidate.plan.identity_sha256, arm, hand,
    )


__all__ = [
    "AttachedLeafActionSetV1", "AttachedLeafCandidate", "build_attached_leaf_candidate",
    "action_for_interval", "R03C_TASK_ID", "ARM_WRITER_ID", "HAND_WRITER_ID",
]
