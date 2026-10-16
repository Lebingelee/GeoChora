"""Shared PickCube task identifiers and authored success parameters.

The selected reference builder and the historical Gym adapter consume these
same task-owned values; neither route redefines the task identity.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PickCubeVariantSpec:
    """Stable identifiers and profiles for the registered PickCube variant."""

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


PICK_CUBE_SPEC = PickCubeVariantSpec(
    env_id="pick-cube-v1",
    task_uid="pick-cube-v1",
    variant="default",
    scene_uid="tabletop-v1",
    agent_uids=("panda-v1",),
    object_uids=("cube-v1",),
    success_definition="cube_lifted_v1",
    scene_profile="tabletop_panda_cube_v1",
    sensor_profile="state_privileged_optional_base_hand_camera_v1",
    reset_profile="uniform_table_center_xy_v1",
    expert_profile="cartesian_pose_primitive_sequence_v1",
    reward_profile="cube_lift_height_10cm_v2",
    language_templates=("pick up the cube",),
)

PICK_CUBE_ENV_ID = PICK_CUBE_SPEC.env_id
PICK_CUBE_TASK_UID = PICK_CUBE_SPEC.task_uid
PICK_CUBE_VARIANT = PICK_CUBE_SPEC.variant
PICK_CUBE_SUCCESS_DEFINITION = PICK_CUBE_SPEC.success_definition
PICK_CUBE_SCENE_UID = PICK_CUBE_SPEC.scene_uid
PICK_CUBE_AGENT_UIDS = PICK_CUBE_SPEC.agent_uids
PICK_CUBE_OBJECT_UIDS = PICK_CUBE_SPEC.object_uids
PICK_CUBE_EXPERT_PROFILE = PICK_CUBE_SPEC.expert_profile
PICK_CUBE_RESET_PROFILE = PICK_CUBE_SPEC.reset_profile
PICK_CUBE_SENSOR_PROFILE = PICK_CUBE_SPEC.sensor_profile

PICK_CUBE_P16_ARTIFACT_ID = "pick-cube-v1/p1_6_experimental_100hz"
PICK_CUBE_P16_ARTIFACT_VERSION = "ver_p1_6_experimental_100hz"
PICK_CUBE_P16_ARTIFACT_SHA256 = "fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4"

PANDA_UID = "panda-v1"
CUBE_UID = "cube-v1"
LIFT_HEIGHT_M = 0.100
REACH_DISTANCE_M = 0.090
# Grasp is a diagnostic/reward heuristic; measured cube lift remains success.
GRIPPER_CLOSED_OPENING_M = 0.045


__all__ = [
    "CUBE_UID", "GRIPPER_CLOSED_OPENING_M", "LIFT_HEIGHT_M", "PANDA_UID",
    "PICK_CUBE_AGENT_UIDS", "PICK_CUBE_ENV_ID", "PICK_CUBE_EXPERT_PROFILE",
    "PICK_CUBE_OBJECT_UIDS", "PICK_CUBE_P16_ARTIFACT_ID",
    "PICK_CUBE_P16_ARTIFACT_SHA256", "PICK_CUBE_P16_ARTIFACT_VERSION",
    "PICK_CUBE_RESET_PROFILE", "PICK_CUBE_SCENE_UID", "PICK_CUBE_SENSOR_PROFILE",
    "PICK_CUBE_SPEC", "PICK_CUBE_SUCCESS_DEFINITION", "PICK_CUBE_TASK_UID",
    "PICK_CUBE_VARIANT", "PickCubeVariantSpec", "REACH_DISTANCE_M",
]
