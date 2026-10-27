"""Task-owned construction and typed action values for the R02c leaf candidate."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json

from ...artifacts import (
    ActuatorReference, FrameReference, JointReference, PoseWorld, Timebase,
)
from ...artifacts.logical_assembly import (
    LogicalAssemblyControlGroupReferenceV1, LogicalAssemblyEntityMemberV1,
    LogicalAssemblyScenePinV1, LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1,
)
from ...artifacts.logical_assembly_resolution import resolve_logical_assembly
from ...assembly.logical_source import project_logical_assembly_source
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
from ...controllers.canonical.contracts import StructuredActionRequestV1, ControlGroupActionV1, digest
from ...runtime.sessions.provenance import provider_build_identity
from .source import _a05_scene, _artifact_and_sample, _source_input, _task_source
from ...environment import compile_task_artifact_v1, sample_episode_reset_plan


LEAF_CANDIDATE_TASK_ID = "phase-ii-r02c-independent-position-leaves"
LEAF_CANDIDATE_VERSION = "candidate-v1"
LEAF_CANDIDATE_SEED = 31
ARM_WRITER_ID = "panda-main/arm-position-leaf"
HAND_WRITER_ID = "panda-main/hand-position-leaf"
_ARM_HOME = (0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853)


@dataclass(frozen=True)
class LeafPositionActionSetV1:
    """One complete, typed two-writer request; the Hand value is total opening in metres."""

    schema_version: str
    scene_identity_sha256: str
    plan_identity_sha256: str
    arm: ArmPositionActionV1
    hand: HandPositionActionV1

    def __post_init__(self):
        if self.schema_version != "leaf-position-action-set-v1":
            raise ValueError("unsupported leaf Position action-set schema")
        if type(self.arm) is not ArmPositionActionV1 or type(self.hand) is not HandPositionActionV1:
            raise TypeError("leaf action-set requires typed Arm and Hand actions")
        self.arm.validate(); self.hand.validate()
        for name, value in (("Scene", self.scene_identity_sha256), ("plan", self.plan_identity_sha256)):
            if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"leaf action-set {name} identity must be SHA-256")

    def structured_request(self, scene, plan):
        if scene.identity_hash != self.scene_identity_sha256 or plan.identity_sha256 != self.plan_identity_sha256:
            raise ValueError("leaf action-set belongs to another Scene/effective plan")
        groups = (
            ControlGroupActionV1("control-group-action-v1", "panda-main", "arm",
                                 ARM_POSITION_ACTION_SCHEMA, tuple(self.arm.position_rad)),
            ControlGroupActionV1("control-group-action-v1", "panda-main", "gripper",
                                 HAND_POSITION_ACTION_SCHEMA, (float(self.hand.opening_m),)),
        )
        request = StructuredActionRequestV1(
            "structured-action-request-v1", scene.identity_hash, plan.identity_sha256, groups,
        )
        request.validate()
        return request


def _provider_build_sha256():
    value = provider_build_identity("mujoco")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(canonical).hexdigest(), value


def _logical_root(scene):
    entity = next(item for item in scene.entities if item.entity_id == "panda-main")
    pin = LogicalAssemblyScenePinV1(
        "logical-assembly-scene-pin-v1", scene.scene_id, scene.schema_version, scene.identity_hash,
    )
    members = (
        LogicalAssemblyEntityMemberV1(
            "entity_member", ("panda",), entity.entity_id, entity.asset_id, entity.asset_version,
        ),
        LogicalAssemblySubcomponentReferenceV1(
            "existing_entity_subcomponent_ref", ("arm",), "control_group",
            LogicalAssemblyControlGroupReferenceV1("panda-main", "arm"),
        ),
        LogicalAssemblySubcomponentReferenceV1(
            "existing_entity_subcomponent_ref", ("hand",), "control_group",
            LogicalAssemblyControlGroupReferenceV1("panda-main", "gripper"),
        ),
    )
    return LogicalAssemblyV1("logical-assembly-v1", "r02c-panda-leaf-plan", "r1", pin, members)


def _leaf_bindings(scene, resolved, source_digest, provider_build_sha, provider_version):
    asset = next(item for item in scene.assets if item.asset_id == "panda-v1")
    identity_pose = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    values = []
    for is_arm in (True, False):
        kind = "arm_position" if is_arm else "hand_position"
        group_id = "arm" if is_arm else "gripper"
        path = ("arm",) if is_arm else ("hand",)
        joints = PANDA_ARM_JOINT_IDS if is_arm else PANDA_HAND_FINGER_JOINT_IDS
        limits = PANDA_ARM_JOINT_LIMITS_RAD if is_arm else PANDA_HAND_FINGER_LIMITS_M
        tcp = FrameReference("panda-main", "link7" if is_arm else "hand")
        actuators = tuple(f"actuator{i}" for i in range(1, 8)) if is_arm else ("actuator8",)
        profile_id = ARM_POSITION_PROFILE_ID if is_arm else HAND_POSITION_PROFILE_ID
        schema_id = ARM_POSITION_ACTION_SCHEMA if is_arm else HAND_POSITION_ACTION_SCHEMA
        required = panda_arm_required_state("panda-main", tcp) if is_arm else panda_hand_required_state("panda-main", tcp)
        # The real R02b defaults own the complete versioned configuration.
        from ...controllers.canonical.leaf_profiles import LeafProfileBindingV1 as _Binding
        # Construct once with a syntactically valid configuration identity, then replace it
        # with the default section's exact hash below.
        binding = _Binding(
            "leaf-profile-binding-v1", "declared", kind, profile_id, schema_id,
            scene.identity_hash, resolved.root_assembly_id, resolved.root_revision,
            resolved.root_logical_content_sha256, path,
            "existing_entity_subcomponent_ref", "control_group", group_id,
            "panda-main", asset.asset_id, asset.asset_version, source_digest,
            "canonical-joint-position-v1", "0" * 64,
            ARM_WRITER_ID if is_arm else HAND_WRITER_ID, group_id,
            "mujoco", provider_version, provider_build_sha, "cpu", 0.002, 5,
            tuple(JointReference("panda-main", item) for item in joints),
            "radian" if is_arm else "meter", tuple(limits),
            tuple(ActuatorReference("panda-main", item) for item in actuators),
            tuple(LeafJointActuatorBindingV1(
                "leaf-joint-actuator-binding-v1", JointReference("panda-main", joint),
                ActuatorReference("panda-main", actuator),
            ) for joint, actuator in zip(joints, actuators, strict=True)) if is_arm else (),
            tcp, "T_parent_from_tcp", identity_pose, required,
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
        values.append(binding)
    defaults = tuple(sorted((default_leaf_profile_section(item) for item in values), key=lambda item: item.member_path))
    bound = tuple(sorted((replace(item, configuration_identity_sha256=next(
        section.configuration_identity_sha256 for section in defaults if section.member_path == item.member_path
    )) for item in values), key=lambda item: item.member_path))
    return bound, defaults


def build_leaf_position_candidate(workspace: Path | str, *, environment_type, arm_gain=2.5,
                                  hand_stiffness_N_per_m=2500.0, provider="mujoco", horizon=64):
    """Build R02c leaves, optionally selecting the source-derived Hand50 case.

    The opt-in replaces a complete Hand section through the existing override
    owner. It leaves the legacy preset/defaults and the shared Position law intact.
    This parameter bounds command offset; it does not impose a physical force cap.
    """
    import importlib
    if provider != "mujoco" or type(arm_gain) not in (int, float) or arm_gain not in (2.5, 3.0):
        raise ValueError("R02c candidate admits MuJoCo CPU and the two fixed Arm sections only")
    if (type(hand_stiffness_N_per_m) not in (int, float)
            or hand_stiffness_N_per_m not in (2500.0, 50.0)):
        raise ValueError("R02c Hand stiffness must select legacy2500 or source-derived50 N/m")
    root_dir = Path(workspace).resolve()
    root_dir.mkdir(parents=True, exist_ok=True)
    scene = _a05_scene()
    legacy, _ = _artifact_and_sample(scene)
    init_positions = dict(legacy.initialization.joint_position)
    init_positions.update({f"panda-main/{name}": value for name, value in zip(PANDA_ARM_JOINT_IDS, _ARM_HOME, strict=True)})
    init_positions.update({"panda-main/finger_joint1": 0.038, "panda-main/finger_joint2": 0.038})
    legacy = replace(
        legacy, artifact_id="phase-ii-r02c-position-leaves-v1",
        task_id=LEAF_CANDIDATE_TASK_ID, artifact_version=LEAF_CANDIDATE_VERSION,
        timebase=Timebase(0.002, 5, 0.01),
        initialization=replace(legacy.initialization, joint_position=init_positions),
    )
    task_source = replace(_task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version)
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=LEAF_CANDIDATE_SEED)
    source, imported, closure_digest, panda_digest, panda_file_count = _source_input(
        importlib.import_module("scene"), root_dir / "source-closure", scene, legacy,
    )
    if imported is None or len(closure_digest) != 64 or panda_digest == "":
        raise ValueError("R02c source importer did not produce bounded source closure evidence")
    source_config = replace(source.config, runtime=replace(source.config.runtime, control_substeps=5))
    source = replace(
        source, task_artifact_hash=artifact.identity_hash,
        joint_targets={f"panda-main/{name}": f"actuator{i}" for i, name in enumerate(PANDA_ARM_JOINT_IDS, 1)},
        open_actuators=("actuator8",), config=source_config,
        source_closure_digest=closure_digest,
    )
    root = _logical_root(scene)
    resolved = resolve_logical_assembly(root, scene, {})
    projection = project_logical_assembly_source(root, scene, {})
    if projection.root_logical_content_sha256 != resolved.root_logical_content_sha256:
        raise ValueError("R02c logical assembly resolution/source projection disagree")
    build_sha, build_info = _provider_build_sha256()
    provider_version = str(build_info["package_version"])
    bindings, sections = _leaf_bindings(scene, resolved, closure_digest, build_sha, provider_version)
    preset = LeafControlPresetV1("leaf-control-preset-v1", "r02c-default", "r1", sections)
    overrides = []
    if arm_gain == 3.0:
        base_arm = next(item for item in sections if item.member_path == ("arm",))
        replacement = LeafProfileSectionV1(
            base_arm.schema_version, base_arm.member_path, base_arm.profile_kind,
            base_arm.profile_id, base_arm.action_schema_id, base_arm.algorithm_id,
            (("joint_position_correction_gain", 3.0),),
        )
        overrides.append(LeafProfileOverrideV1("leaf-profile-override-v1", ("arm",), replacement))
    if hand_stiffness_N_per_m == 50.0:
        base_hand = next(item for item in sections if item.member_path == ("hand",))
        replacement = replace(base_hand, configuration=tuple(
            (key, 50.0 if key == "gripper_position_stiffness_N_per_m" else value)
            for key, value in base_hand.configuration
        ))
        overrides.append(LeafProfileOverrideV1("leaf-profile-override-v1", ("hand",), replacement))
    overrides = tuple(overrides)
    plan = compile_effective_leaf_plan(
        scene, root, {}, bindings, preset, overrides,
        source_closure_sha256=closure_digest,
    )

    case_id = ("SOURCE_CALIBRATED_HAND_50_V1" if hand_stiffness_N_per_m == 50.0
               else "LEGACY_HAND_2500")

    def build(_provider):
        resolved_configuration = {"provider": _provider, "backend": "cpu",
                                  "effective_leaf_plan": plan.identity_sha256}
        if hand_stiffness_N_per_m == 50.0:
            resolved_configuration["hand_position_case"] = case_id
        return {
            "artifact": artifact, "task_source": task_source, "solution": None,
            "source": source, "reset_plan": reset_plan,
            "leaf_plan": plan, "logical_assembly": root, "leaf_bindings": bindings,
            "leaf_preset": preset, "leaf_overrides": overrides,
            "provider_build_identity": build_info,
            "construction_id": digest({"artifact": artifact.identity_hash,
                                        "source": closure_digest, "plan": plan.identity_sha256}),
            "resolved_configuration": resolved_configuration,
            "source_revision": "R02c-independent-position-leaves-v1",
            "source_sha256": {"source_closure": closure_digest, "panda_closure": panda_digest},
        }

    def fixed_seed(seed):
        if type(seed) is not int or seed != reset_plan.reset_sample.task_seed:
            raise ValueError(f"R02c fixed ResetPlan requires seed {reset_plan.reset_sample.task_seed}")
        return seed

    from ..reference_env import ReferenceTaskBinding
    binding = ReferenceTaskBinding(
        build=build, reset_sample=lambda _artifact, _seed: reset_plan.reset_sample,
        evaluate=lambda _state, _semantics: SimpleNamespace(reward=0.0, success=False, failure=False, metrics={}),
        object_poses=(("square-peg-instance/peg1", "target"),), external_actions=True,
        interval_mode="grouped", recorder_mode="execution", reset_seed=fixed_seed,
    )
    env = environment_type.from_leaf_position_candidate(binding, provider=provider, backend="cpu", horizon=horizon)
    return SimpleNamespace(
        env=env, scene=scene, task_source=task_source, artifact=artifact,
        reset_plan=reset_plan, source=source, logical_assembly=root,
        leaf_bindings=bindings, preset=preset, plan=plan, provider_build_identity=build_info,
        panda_closure_digest=panda_digest, panda_file_count=panda_file_count,
        provider=provider, arm_gain=float(arm_gain),
        hand_stiffness_N_per_m=float(hand_stiffness_N_per_m), case_id=case_id,
    )


def action_for_interval(scene, plan, interval, *, arm_active, hand_active):
    if type(interval) is not int or not 1 <= interval <= 64:
        raise ValueError("R02c curve interval must be in [1,64]")
    start = (0.0,) + _ARM_HOME[1:]
    if not arm_active or interval > 48:
        arm_values = _ARM_HOME
    elif interval <= 16:
        arm_values = (0.1 * interval / 16.0,) + _ARM_HOME[1:]
    elif interval <= 32:
        arm_values = (0.1,) + _ARM_HOME[1:]
    else:
        arm_values = (0.1 * (48 - interval) / 16.0,) + _ARM_HOME[1:]
    if not hand_active or interval > 48:
        opening = 0.076
    elif interval <= 16:
        opening = 0.076 + (0.004 - 0.076) * interval / 16.0
    elif interval <= 32:
        opening = 0.004
    else:
        opening = 0.004 + (0.076 - 0.004) * (interval - 32) / 16.0
    arm = ArmPositionActionV1(ARM_POSITION_ACTION_SCHEMA,
        tuple(JointReference("panda-main", item) for item in PANDA_ARM_JOINT_IDS), tuple(arm_values))
    hand = HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, float(opening))
    return LeafPositionActionSetV1("leaf-position-action-set-v1", scene.identity_hash, plan.identity_sha256, arm, hand)
