"""Shared NutAssembly task identity consumed by active and legacy adapters."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NutAssemblyVariantSpec:
    env_id: str
    task_uid: str
    variant: str
    scene_uid: str
    agent_uids: tuple[str, ...]
    object_uids: tuple[str, ...]
    success_definition: str
    scene_profile: str
    sensor_profile: str
    reset_profile: str
    expert_profile: str
    reward_profile: str
    language_templates: tuple[str, ...] = ()


NUT_ASSEMBLY_SQUARE_SPEC = NutAssemblyVariantSpec(
    env_id="nut-assembly-square-v1", task_uid="nut-assembly-square-v1", variant="square",
    scene_uid="tabletop-v1", agent_uids=("panda-v1",),
    object_uids=("square-nut-v1", "square-peg-v1", "round-peg-v1"),
    success_definition="nut_on_square_peg_v1",
    scene_profile="tabletop_panda_square_nut_pegs_v1",
    sensor_profile="state_privileged_optional_base_hand_camera_v1",
    reset_profile="deterministic_hand_above_square_nut_handle_v1",
    expert_profile="public_delta_pose_stage_machine_v1",
    reward_profile="nut_on_square_peg_release_shaping_v1",
    language_templates=("assemble the square nut onto the square peg",),
)

NUT_ASSEMBLY_ENV_ID = NUT_ASSEMBLY_SQUARE_SPEC.env_id
NUT_ASSEMBLY_TASK_UID = NUT_ASSEMBLY_SQUARE_SPEC.task_uid
NUT_ASSEMBLY_VARIANT = NUT_ASSEMBLY_SQUARE_SPEC.variant
NUT_ASSEMBLY_SUCCESS_DEFINITION = NUT_ASSEMBLY_SQUARE_SPEC.success_definition
NUT_ASSEMBLY_SCENE_UID = NUT_ASSEMBLY_SQUARE_SPEC.scene_uid
NUT_ASSEMBLY_AGENT_UIDS = NUT_ASSEMBLY_SQUARE_SPEC.agent_uids
NUT_ASSEMBLY_OBJECT_UIDS = NUT_ASSEMBLY_SQUARE_SPEC.object_uids
NUT_ASSEMBLY_EXPERT_PROFILE = NUT_ASSEMBLY_SQUARE_SPEC.expert_profile
NUT_ASSEMBLY_RESET_PROFILE = NUT_ASSEMBLY_SQUARE_SPEC.reset_profile
NUT_ASSEMBLY_SENSOR_PROFILE = NUT_ASSEMBLY_SQUARE_SPEC.sensor_profile


__all__ = [
    "NUT_ASSEMBLY_AGENT_UIDS", "NUT_ASSEMBLY_ENV_ID", "NUT_ASSEMBLY_EXPERT_PROFILE",
    "NUT_ASSEMBLY_OBJECT_UIDS", "NUT_ASSEMBLY_RESET_PROFILE", "NUT_ASSEMBLY_SCENE_UID",
    "NUT_ASSEMBLY_SENSOR_PROFILE", "NUT_ASSEMBLY_SQUARE_SPEC",
    "NUT_ASSEMBLY_SUCCESS_DEFINITION", "NUT_ASSEMBLY_TASK_UID", "NUT_ASSEMBLY_VARIANT",
    "NutAssemblyVariantSpec",
]
