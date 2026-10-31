"""Source-bound task Solution for the pinned LIBERO bowl-to-plate task.

The policy consumes only the public SelectedReferenceEnv observation, info and
episode metadata. Historical profiles issue arm-joint targets; the current
pose profile issues absolute world-pose and aggregate-finger intents through
the existing mixed-control owner. It never steps physics or reads a
RuntimeSession/provider object.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

import numpy as np

from task_env.controllers.canonical.contracts import digest
from task_env.controllers.canonical.kinematics import (
    PandaKinematics,
    derive_panda_tcp_profile_v2,
)
from task_env.planners.contracts import ExpertAction
from task_env.planners.cartesian import CartesianPosePlanner, CartesianPosePlannerConfig
from task_env.utils.rotation import (
    normalize_quat_wxyz, quat_angle_wxyz, quat_multiply_wxyz,
    rotate_vector_wxyz,
)

from .controller import (
    LiberoMixedControlConfigV1, LiberoMixedControllerV3,
    LiberoMixedControllerV4, LiberoMixedControllerV5, LiberoOperationalSpaceConfigV1,
    LiberoOperationalSpaceConfigV2,
)
from .source_gravity import SOURCE_GRAVITY_PROFILE_V1
from .task_contracts import TASK_1


SOLUTION_SCHEMA = "libero-bowl-to-plate-solution-v1"
SOLUTION_SCHEMA_V2 = "libero-bowl-to-plate-solution-v2"
SOLUTION_SCHEMA_V3 = "libero-bowl-to-plate-solution-v3"
SOLUTION_SCHEMA_V4 = "libero-bowl-to-plate-solution-v4"
SOLUTION_SCHEMA_V5 = "libero-bowl-to-plate-solution-v5"
SOLUTION_SCHEMA_V6 = "libero-bowl-to-plate-solution-v6"
SOLUTION_SCHEMA_V7 = "libero-bowl-to-plate-solution-v7"
POSE_ACTION_SCHEMA_V1 = "libero-world-pose-wxyz-absolute-v1"
TCP_ID = "libero-mounted-panda-v1/gripper0-grip-site-v1"
HAND_FRAME_ID = "robot0_right_hand"
SITE_NAME = "gripper0_grip_site"
BASE_BODY_ID = "robot0_link0"
_JOINT_LIMITS = np.asarray((
    (-2.8973, 2.8973), (-1.7628, 1.7628), (-2.8973, 2.8973),
    (-3.0718, -0.0698), (-2.8973, 2.8973), (-0.0175, 3.7525),
    (-2.8973, 2.8973),
), dtype=np.float64)
_JOINT_NAMES = tuple(f"joint{index}" for index in range(1, 8))
_POSITION_LIMITS = {
    name: (float(limits[0]), float(limits[1]))
    for name, limits in zip(_JOINT_NAMES, _JOINT_LIMITS, strict=True)
}
_OPENING_BY_STAGE = {
    # Leave 10 mm per finger inside the signed source joint limits. Native
    # attempts measured roughly 5 mm overshoot near the open stop; the physical
    # monitor correctly rejects even small source-range crossings.
    "approach": 0.06,
    "descend": 0.06,
    "grasp": 0.045,
    "lift": 0.045,
    "carry": 0.045,
    "place": 0.045,
    "release": 0.06,
}


def solution_identity_v1(
    source_xml_sha256: str,
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
) -> str:
    """Return the exact task/profile identity bound to one composed MJCF."""
    if (type(source_xml_sha256) is not str or len(source_xml_sha256) != 64
            or any(character not in "0123456789abcdef" for character in source_xml_sha256)):
        raise ValueError("LIBERO Solution identity requires a lowercase source XML SHA-256")
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    return digest({
        "schema_version": SOLUTION_SCHEMA,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "controller_profile_id": "libero-spatial-bowl-to-plate-joint-space-pd-v3",
        "tcp_id": TCP_ID,
        "algorithm": "public-observation-damped-jacobian-waypoints-v2",
        "waypoints_m": {
            "approach_z": 0.15, "grasp_z": 0.05,
            "lift_z": 0.20, "place_tcp_z_above_plate": 0.085,
        },
        "opening_m": _OPENING_BY_STAGE,
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "max_cartesian_increment_m": selected_config.max_cartesian_increment_m,
            "max_joint_increment_rad": selected_config.max_joint_increment_rad,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


def solution_identity_v2(
    source_xml_sha256: str,
    source_closure_digest: str,
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
) -> str:
    """Bind task #1's public-observation plan and source gravity primitive."""
    for value, label in ((source_xml_sha256, "source XML"),
                         (source_closure_digest, "source closure")):
        if (type(value) is not str or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError(f"LIBERO Solution v2 requires a lowercase {label} SHA-256")
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    controller = LiberoMixedControlConfigV1()
    controller.validate()
    return digest({
        "schema_version": SOLUTION_SCHEMA_V2,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "source_closure_digest": source_closure_digest,
        "controller_profile_id": "libero-spatial-bowl-to-plate-joint-space-pd-v6",
        "tcp_id": TCP_ID,
        "algorithm": "public-observation-damped-jacobian-waypoints-v2",
        "gravity_compensation": {
            "profile_id": SOURCE_GRAVITY_PROFILE_V1,
            "model": "same-source-closure-independent-mujoco-static-bias-v1",
            "torque_formula": "qfrc_bias-minus-qfrc_passive-at-zero-joint-velocity",
            "position_target_encoding": "planner-target-plus-gravity-torque-over-controller-kp",
            "controller_kp_Nm_per_rad": list(controller.kp_Nm_per_rad),
            "controller_kd_Nm_s_per_rad": list(controller.kd_Nm_s_per_rad),
            "joint_limits_rad": {key: list(value) for key, value in _POSITION_LIMITS.items()},
            "no_extra_physics_step": True,
        },
        "waypoints_m": {
            "approach_z": 0.15, "grasp_z": 0.05,
            "lift_z": 0.20, "place_tcp_z_above_plate": 0.085,
        },
        "opening_m": _OPENING_BY_STAGE,
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "max_cartesian_increment_m": selected_config.max_cartesian_increment_m,
            "max_joint_increment_rad": selected_config.max_joint_increment_rad,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


def solution_identity_v2_frozen(
    source_xml_sha256: str,
    source_closure_digest: str,
    recorded_controller: Mapping[str, object],
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
) -> str:
    """Recompute a historical v2 identity from its frozen controller profile."""
    from .controller import legacy_v2_controller_identity_mapping

    expected_controller = legacy_v2_controller_identity_mapping(
        recorded_controller.get("profile_id"),
    )
    if dict(recorded_controller) != expected_controller:
        raise ValueError("historical v2 Controller record differs from its frozen version manifest")
    for value, label in ((source_xml_sha256, "source XML"),
                         (source_closure_digest, "source closure")):
        if (type(value) is not str or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError(f"LIBERO Solution v2 requires a lowercase {label} SHA-256")
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    return digest({
        "schema_version": SOLUTION_SCHEMA_V2,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "source_closure_digest": source_closure_digest,
        "controller_profile_id": expected_controller["profile_id"],
        "tcp_id": TCP_ID,
        "algorithm": "public-observation-damped-jacobian-waypoints-v2",
        "gravity_compensation": {
            "profile_id": SOURCE_GRAVITY_PROFILE_V1,
            "model": "same-source-closure-independent-mujoco-static-bias-v1",
            "torque_formula": "qfrc_bias-minus-qfrc_passive-at-zero-joint-velocity",
            "position_target_encoding": "planner-target-plus-gravity-torque-over-controller-kp",
            "controller_kp_Nm_per_rad": expected_controller["kp_Nm_per_rad"],
            "controller_kd_Nm_s_per_rad": expected_controller["kd_Nm_s_per_rad"],
            "joint_limits_rad": {key: list(value) for key, value in _POSITION_LIMITS.items()},
            "no_extra_physics_step": True,
        },
        "waypoints_m": {
            "approach_z": 0.15, "grasp_z": 0.05,
            "lift_z": 0.20, "place_tcp_z_above_plate": 0.085,
        },
        "opening_m": _OPENING_BY_STAGE,
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "max_cartesian_increment_m": selected_config.max_cartesian_increment_m,
            "max_joint_increment_rad": selected_config.max_joint_increment_rad,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


def solution_identity_v3(
    source_xml_sha256: str,
    source_closure_digest: str,
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
    planner_config: CartesianPosePlannerConfig | None = None,
) -> str:
    """Bind task #1's explicit world-pose path, shared resolver and mixed law."""
    for value, label in ((source_xml_sha256, "source XML"),
                         (source_closure_digest, "source closure")):
        if (type(value) is not str or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError(f"LIBERO Solution v3 requires a lowercase {label} SHA-256")
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    selected_planner = planner_config or CartesianPosePlannerConfig(
        max_translation_per_step=0.012,
        max_translation_acceleration_per_step=0.004,
        max_rotation_per_step=0.08,
        max_rotation_acceleration_per_step=0.04,
        settle_steps=0,
        max_steps=200,
    )
    from .controller import LiberoMixedControllerV2
    return digest({
        "schema_version": SOLUTION_SCHEMA_V3,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "source_closure_digest": source_closure_digest,
        "tcp_id": TCP_ID,
        "action_schema_id": POSE_ACTION_SCHEMA_V1,
        "action_semantics": {
            "mode": "absolute_pose", "reference": "world",
            "rotation_representation": "quaternion_wxyz",
            "gripper_scalar": "normalized_minus1_to1_to_aggregate_opening_m_0p04_times_u_plus_1",
        },
        "grasp_orientation_source": "reset_public_source_bound_tcp_world_quaternion_wxyz_v1",
        "bowl_reference": "live_public_bowl_pose_until_grasp_then_frozen_v1",
        "planner": {
            "owner": "task_env.planners.cartesian.CartesianPosePlanner.plan_to_pose",
            "gripper_transition_owner": "task_env.planners.cartesian.CartesianPosePlanner.plan_gripper_transition",
            "config": {
                "max_translation_per_step": selected_planner.max_translation_per_step,
                "max_translation_acceleration_per_step": selected_planner.max_translation_acceleration_per_step,
                "max_rotation_per_step": selected_planner.max_rotation_per_step,
                "max_rotation_acceleration_per_step": selected_planner.max_rotation_acceleration_per_step,
                "settle_steps": selected_planner.settle_steps,
                "max_steps": selected_planner.max_steps,
            },
        },
        "arm_resolution_owner": "CanonicalPandaController.resolve_world_pose_target_v1",
        "mixed_controller": LiberoMixedControllerV2().identity_mapping(),
        "waypoints_m": {
            "approach_z": 0.15, "grasp_z": 0.05,
            "lift_z": 0.20, "place_tcp_z_above_plate": 0.085,
        },
        "opening_m": _OPENING_BY_STAGE,
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


_OPENING_BY_STAGE_V4 = {
    # Insert narrow fingers inside the bowl, then spread outward against both
    # inner walls. Keep the spread command during lift/carry/place.
    "approach": 0.045,
    "descend": 0.045,
    "grasp": 0.08,
    "lift": 0.08,
    "carry": 0.08,
    "place": 0.08,
    "release": 0.045,
}
_OPENING_BY_STAGE_V5 = {
    **_OPENING_BY_STAGE_V4,
    # Native rows 0/1/2 confirm bilateral rim contact near 0.0555 m, but
    # opening to 0.060 m loses both contacts within 5-7 lift boundaries.
    # Hold just below the measured contact aperture to keep a slight closing
    # preload while the shared Cartesian planner advances the lift path.
    "lift": 0.055,
    "carry": 0.055,
    "place": 0.055,
}
_OPENING_BY_STAGE_V6 = {
    # Match the measured LIBERO demonstration pinch: enter with an open jaw,
    # close across the rim wall, and preserve that aperture through lift/carry.
    "approach": 0.042,
    "descend": 0.042,
    "grasp": 0.010,
    "lift": 0.008,
    "carry": 0.008,
    "place": 0.008,
    "release": 0.042,
}
_OPENING_BY_STAGE_V7 = {
    # Use the demonstrated pre-lift pinch aperture from the same replay
    # analysis that supplies the first-bilateral-contact pose.
    **_OPENING_BY_STAGE_V6,
    "grasp": 0.008,
}
_DEMO_TCP_BOWL_LOCAL_M = np.asarray(
    (-0.04555440076829924, 0.002120461738427656, 0.03321187804063996),
    dtype=np.float64,
)
_DEMO_FIRST_BILATERAL_TCP_BOWL_LOCAL_M = np.asarray(
    (-0.04490935541611755, 0.004212145868712052, 0.0312549937079468),
    dtype=np.float64,
)
_DEMO_DATASET_SHA256 = "ff6f26121653c77280eb40a38773a74141c11a8509f3466058cb56dd2cc60ead"
_DEMO_DATASET_REVISION = "e434c228d52f21e37c6f45046a6476a8fa362b8d"
_STAGE_TIMEOUTS_V4 = {
    "approach": 180, "descend": 120, "grasp": 60,
    "lift": 180, "carry": 180, "place": 120,
}
_WAYPOINT_POSITION_TOLERANCE_V4_M = 0.006
_WAYPOINT_ORIENTATION_TOLERANCE_V4_RAD = 0.03
_GRASP_TCP_HEIGHT_V4_M = 0.035
_GRASP_CONTACT_DWELL_V4 = 2


def solution_identity_v4(
    source_xml_sha256: str, source_closure_digest: str,
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
    planner_config: CartesianPosePlannerConfig | None = None,
) -> str:
    """Bind the OSC, convergence-gated planner and bilateral inner-wall grasp."""
    for value, label in ((source_xml_sha256, "source XML"),
                         (source_closure_digest, "source closure")):
        if (type(value) is not str or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError(f"LIBERO Solution v4 requires a lowercase {label} SHA-256")
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    selected_planner = planner_config or CartesianPosePlannerConfig(
        max_translation_per_step=0.0055,
        max_translation_acceleration_per_step=0.002,
        max_rotation_per_step=0.08,
        max_rotation_acceleration_per_step=0.04,
        settle_steps=0,
        max_steps=200,
    )
    osc = LiberoMixedControllerV3(
        operational_config=LiberoOperationalSpaceConfigV1(),
    )
    return digest({
        "schema_version": SOLUTION_SCHEMA_V4,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "source_closure_digest": source_closure_digest,
        "tcp_id": TCP_ID,
        "action_schema_id": POSE_ACTION_SCHEMA_V1,
        "action_semantics": {
            "mode": "absolute_pose", "reference": "world",
            "rotation_representation": "quaternion_wxyz",
            "gripper_scalar": "normalized_minus1_to1_to_aggregate_opening_m_0p04_times_u_plus_1",
        },
        "grasp_orientation_source": "reset_public_source_bound_tcp_world_quaternion_wxyz_v1",
        "bowl_reference": "live_public_bowl_pose_until_grasp_then_frozen_v1",
        "planner": {
            "owner": "task_env.planners.cartesian.CartesianPosePlanner.plan_to_pose",
            "gripper_transition_owner": "task_env.planners.cartesian.CartesianPosePlanner.plan_gripper_transition",
            "advancement": "current_public_TCP_waypoint_convergence_gated_v1",
            "position_tolerance_m": _WAYPOINT_POSITION_TOLERANCE_V4_M,
            "orientation_tolerance_rad": _WAYPOINT_ORIENTATION_TOLERANCE_V4_RAD,
            "config": {
                "max_translation_per_step": selected_planner.max_translation_per_step,
                "max_translation_acceleration_per_step": selected_planner.max_translation_acceleration_per_step,
                "max_rotation_per_step": selected_planner.max_rotation_per_step,
                "max_rotation_acceleration_per_step": selected_planner.max_rotation_acceleration_per_step,
                "settle_steps": selected_planner.settle_steps,
                "max_steps": selected_planner.max_steps,
            },
        },
        "arm_resolution_owner": "CanonicalPandaController.resolve_world_pose_target_iterative_v1",
        "mixed_controller": osc.identity_mapping(),
        "grasp": {
            "strategy": "insert_narrow_fingers_below_rim_then_open_outward_v1",
            "tcp_height_above_bowl_center_m": _GRASP_TCP_HEIGHT_V4_M,
            "approach_opening_m": _OPENING_BY_STAGE_V4["approach"],
            "grasp_opening_target_m": _OPENING_BY_STAGE_V4["grasp"],
            "required_contact_groups": [
                "panda-v1/finger-left", "panda-v1/finger-right",
                "akita_black_bowl_1",
            ],
            "contact_dwell_boundaries": _GRASP_CONTACT_DWELL_V4,
        },
        "opening_m": _OPENING_BY_STAGE_V4,
        "stage_timeouts": _STAGE_TIMEOUTS_V4,
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


def solution_identity_v5(
    source_xml_sha256: str, source_closure_digest: str, *, arm_resolver_identity: str,
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
    planner_config: CartesianPosePlannerConfig | None = None,
) -> str:
    """Bind the physics-rate OSC posture policy to the source and shared resolver."""
    for value, label in ((source_xml_sha256, "source XML"),
                         (source_closure_digest, "source closure"),
                         (arm_resolver_identity, "arm resolver")):
        if (type(value) is not str or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError(f"LIBERO Solution v5 requires a lowercase {label} SHA-256")
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    selected_planner = planner_config or CartesianPosePlannerConfig(
        max_translation_per_step=0.0055,
        max_translation_acceleration_per_step=0.002,
        max_rotation_per_step=0.08,
        max_rotation_acceleration_per_step=0.04,
        settle_steps=0,
        max_steps=200,
    )
    osc = LiberoMixedControllerV4(
        operational_config=LiberoOperationalSpaceConfigV2(),
        arm_resolver_identity=arm_resolver_identity,
    )
    return digest({
        "schema_version": SOLUTION_SCHEMA_V5,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "source_closure_digest": source_closure_digest,
        "tcp_id": TCP_ID,
        "action_schema_id": POSE_ACTION_SCHEMA_V1,
        "action_semantics": {
            "mode": "absolute_pose", "reference": "world",
            "rotation_representation": "quaternion_wxyz",
            "gripper_scalar": "normalized_minus1_to1_to_aggregate_opening_m_0p04_times_u_plus_1",
        },
        "grasp_orientation_source": "reset_public_source_bound_tcp_world_quaternion_wxyz_v1",
        "bowl_reference": "live_public_bowl_pose_until_grasp_then_frozen_v1",
        "planner": {
            "owner": "task_env.planners.cartesian.CartesianPosePlanner.plan_to_pose",
            "gripper_transition_owner": "task_env.planners.cartesian.CartesianPosePlanner.plan_gripper_transition",
            "advancement": "current_public_TCP_waypoint_convergence_gated_v1",
            "position_tolerance_m": _WAYPOINT_POSITION_TOLERANCE_V4_M,
            "orientation_tolerance_rad": _WAYPOINT_ORIENTATION_TOLERANCE_V4_RAD,
            "config": {
                "max_translation_per_step": selected_planner.max_translation_per_step,
                "max_translation_acceleration_per_step": selected_planner.max_translation_acceleration_per_step,
                "max_rotation_per_step": selected_planner.max_rotation_per_step,
                "max_rotation_acceleration_per_step": selected_planner.max_rotation_acceleration_per_step,
                "settle_steps": selected_planner.settle_steps,
                "max_steps": selected_planner.max_steps,
            },
        },
        "arm_resolution_owner": "CanonicalPandaController.resolve_world_pose_target_iterative_v1",
        "arm_resolver_identity": arm_resolver_identity,
        "mixed_controller": osc.identity_mapping(),
        "grasp": {
            "strategy": "insert_narrow_fingers_below_rim_then_hold_contact_aperture_v2",
            "tcp_height_above_bowl_center_m": _GRASP_TCP_HEIGHT_V4_M,
            "approach_opening_m": _OPENING_BY_STAGE_V4["approach"],
            "grasp_opening_target_m": _OPENING_BY_STAGE_V4["grasp"],
            "grasp_hold_opening_m": _OPENING_BY_STAGE_V5["lift"],
            "required_contact_groups": [
                "panda-v1/finger-left", "panda-v1/finger-right",
                "akita_black_bowl_1",
            ],
            "contact_dwell_boundaries": _GRASP_CONTACT_DWELL_V4,
        },
        "opening_m": _OPENING_BY_STAGE_V5,
        "stage_timeouts": _STAGE_TIMEOUTS_V4,
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


def solution_identity_v6(
    source_xml_sha256: str, source_closure_digest: str, *, arm_resolver_identity: str,
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
    planner_config: CartesianPosePlannerConfig | None = None,
) -> str:
    """Bind a demonstration-grounded rim grasp and conservative pose path."""
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    selected_planner = planner_config or CartesianPosePlannerConfig(
        max_translation_per_step=0.0025,
        max_translation_acceleration_per_step=0.001,
        max_rotation_per_step=0.04,
        max_rotation_acceleration_per_step=0.02,
        settle_steps=0,
        max_steps=200,
    )
    controller_identity = LiberoMixedControllerV5(
        arm_resolver_identity=arm_resolver_identity,
    ).identity
    return digest({
        "schema_version": SOLUTION_SCHEMA_V6,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "source_closure_digest": source_closure_digest,
        "arm_resolver_identity": arm_resolver_identity,
        "controller_identity": controller_identity,
        "parent_profile_identity": solution_identity_v5(
            source_xml_sha256, source_closure_digest,
            arm_resolver_identity=arm_resolver_identity,
            config=selected_config, planner_config=selected_planner,
        ),
        "grasp_frame": {
            "reference": "public_bowl_and_plate_body_pose_world_wxyz_live_until_grasp_v1",
            "tcp_offset_bowl_local_m": _DEMO_TCP_BOWL_LOCAL_M.tolist(),
            "offset_source": "LIBERO task-0 demonstrated pre-lift median",
            "dataset_revision": _DEMO_DATASET_REVISION,
            "dataset_file_sha256": _DEMO_DATASET_SHA256,
            "jaw_orientation": "reset_tcp_orientation_relative_to_bowl_v1",
            "plate_reference": "follow_public_plate_pose_until_grasp_then_freeze_v1",
            "approach_height_above_bowl_origin_m": 0.15,
        },
        "opening_m": _OPENING_BY_STAGE_V6,
        "contact_policy": "bilateral_source_finger_contact_two_boundaries_then_retain_pinch_v2",
        "planner": {
            "owner": "task_env.planners.cartesian.CartesianPosePlanner",
            "max_translation_per_step_m": selected_planner.max_translation_per_step,
            "max_translation_acceleration_per_step_m": selected_planner.max_translation_acceleration_per_step,
            "max_rotation_per_step_rad": selected_planner.max_rotation_per_step,
            "max_rotation_acceleration_per_step_rad": selected_planner.max_rotation_acceleration_per_step,
            "position_tolerance_m": _WAYPOINT_POSITION_TOLERANCE_V4_M,
            "orientation_tolerance_rad": _WAYPOINT_ORIENTATION_TOLERANCE_V4_RAD,
        },
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


def solution_identity_v7(
    source_xml_sha256: str, source_closure_digest: str, *, arm_resolver_identity: str,
    config: "LiberoPickPlaceSolutionConfigV1 | None" = None,
    planner_config: CartesianPosePlannerConfig | None = None,
) -> str:
    """Bind the demonstrated first-bilateral-contact rim pose and pinch aperture."""
    selected_config = config or LiberoPickPlaceSolutionConfigV1()
    selected_config.validate()
    selected_planner = planner_config or CartesianPosePlannerConfig(
        max_translation_per_step=0.0025,
        max_translation_acceleration_per_step=0.001,
        max_rotation_per_step=0.04,
        max_rotation_acceleration_per_step=0.02,
        settle_steps=0,
        max_steps=200,
    )
    return digest({
        "schema_version": SOLUTION_SCHEMA_V7,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "source_closure_digest": source_closure_digest,
        "arm_resolver_identity": arm_resolver_identity,
        "parent_profile_identity": solution_identity_v6(
            source_xml_sha256, source_closure_digest,
            arm_resolver_identity=arm_resolver_identity,
            config=selected_config, planner_config=selected_planner,
        ),
        "grasp_frame": {
            "reference": "public_bowl_and_plate_body_pose_world_wxyz_live_until_grasp_v1",
            "tcp_offset_bowl_local_m": _DEMO_FIRST_BILATERAL_TCP_BOWL_LOCAL_M.tolist(),
            "offset_source": "LIBERO task-0 reconstructed first-bilateral-contact median",
            "dataset_revision": _DEMO_DATASET_REVISION,
            "dataset_file_sha256": _DEMO_DATASET_SHA256,
            "jaw_orientation": "reset_tcp_orientation_relative_to_bowl_v1",
            "plate_reference": "follow_public_plate_pose_until_grasp_then_freeze_v1",
            "approach_height_above_bowl_origin_m": 0.15,
        },
        "opening_m": _OPENING_BY_STAGE_V7,
        "contact_policy": "bilateral_source_finger_contact_two_boundaries_then_retain_pinch_v2",
        "planner": {
            "owner": "task_env.planners.cartesian.CartesianPosePlanner",
            "max_translation_per_step_m": selected_planner.max_translation_per_step,
            "max_translation_acceleration_per_step_m": selected_planner.max_translation_acceleration_per_step,
            "max_rotation_per_step_rad": selected_planner.max_rotation_per_step,
            "max_rotation_acceleration_per_step_rad": selected_planner.max_rotation_acceleration_per_step,
            "position_tolerance_m": _WAYPOINT_POSITION_TOLERANCE_V4_M,
            "orientation_tolerance_rad": _WAYPOINT_ORIENTATION_TOLERANCE_V4_RAD,
        },
        "motion_config": {
            "position_tolerance_m": selected_config.position_tolerance_m,
            "grasp_dwell_steps": selected_config.grasp_dwell_steps,
            "release_dwell_steps": selected_config.release_dwell_steps,
            "release_timeout_steps": selected_config.release_timeout_steps,
            "max_episode_steps": selected_config.max_episode_steps,
        },
    })


def _body_position(observation: Mapping[str, object], key: str) -> np.ndarray:
    try:
        value = np.asarray(observation["privileged_state"][key], dtype=np.float64)[0, :3]
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"public LIBERO observation is missing {key}") from exc
    if value.shape != (3,) or not np.isfinite(value).all():
        raise ValueError(f"public LIBERO body pose {key} must contain a finite world position")
    return value.copy()


def _body_pose(observation: Mapping[str, object], key: str) -> np.ndarray:
    """Return a validated public world position/quaternion body pose."""
    try:
        value = np.asarray(observation["privileged_state"][key], dtype=np.float64)[0]
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"public LIBERO observation is missing {key}") from exc
    if value.shape != (7,) or not np.isfinite(value).all():
        raise ValueError(f"public LIBERO body pose {key} must contain a finite world pose")
    return np.concatenate((value[:3], normalize_quat_wxyz(value[3:7])))


def _state_vector(observation: Mapping[str, object]) -> tuple[np.ndarray, np.ndarray]:
    try:
        state = observation["state"]
        joints = np.asarray(state["joint_position"], dtype=np.float64)
        ee_pose = np.asarray(state["ee_pose"], dtype=np.float64)
    except (KeyError, TypeError) as exc:
        raise ValueError("public LIBERO observation is missing state fields") from exc
    if joints.shape != (9,) or not np.isfinite(joints).all():
        raise ValueError("public LIBERO joint_position must contain seven arm and two finger values")
    if ee_pose.shape != (7,) or not np.isfinite(ee_pose).all():
        raise ValueError("public LIBERO ee_pose must be a finite world pose")
    return joints[:7].copy(), ee_pose[:3].copy()


def _boundary_identity(info: Mapping[str, object]) -> tuple[str, str, str, str, str, int, float]:
    try:
        identity = (
            str(info["source_id"]), str(info["source_closure_digest"]),
            str(info["provider_materialization_id"]), str(info["episode_id"]),
            str(info["reset_sample_id"]), int(info["control_step"]),
            float(info["simulation_time_s"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("public LIBERO info is missing its source and boundary identity") from exc
    if (any(not value for value in identity[:5]) or identity[5] < 0
            or not math.isfinite(identity[6]) or identity[6] < 0):
        raise ValueError("public LIBERO boundary identity is invalid")
    context = info.get("boundary_context_v1")
    if isinstance(context, Mapping):
        expected = (
            context.get("source_id"), context.get("source_closure_digest"),
            context.get("provider_materialization_id"), context.get("episode_id"),
            context.get("reset_sample_id"), context.get("control_step"),
            context.get("simulation_time_s"),
        )
        if expected != identity:
            raise ValueError("public LIBERO info and boundary context identities disagree")
    return identity


@dataclass(frozen=True)
class LiberoPickPlaceSolutionConfigV1:
    position_tolerance_m: float = 0.012
    max_cartesian_increment_m: float = 0.002
    max_joint_increment_rad: float = 0.01
    grasp_dwell_steps: int = 8
    release_dwell_steps: int = 12
    release_timeout_steps: int = 50
    max_episode_steps: int = 1000

    def validate(self) -> None:
        numeric = (
            self.position_tolerance_m,
            self.max_cartesian_increment_m,
            self.max_joint_increment_rad,
        )
        if any(not math.isfinite(float(value)) or value <= 0 for value in numeric):
            raise ValueError("LIBERO Solution motion tolerances must be positive and finite")
        if (type(self.grasp_dwell_steps) is not int or self.grasp_dwell_steps < 1
                or type(self.release_dwell_steps) is not int or self.release_dwell_steps < 1
                or type(self.release_timeout_steps) is not int
                or self.release_timeout_steps < self.release_dwell_steps
                or type(self.max_episode_steps) is not int
                or not 1 <= self.max_episode_steps <= 1000):
            raise ValueError("LIBERO Solution step limits are invalid")


class LiberoPickPlaceSolutionV1:
    """Public-interface-only pick/place expert for the exact task #1 source."""

    task_uid = TASK_1
    action_schema_id = "libero-joint-space-absolute-v1"
    solution_schema_version = SOLUTION_SCHEMA

    def __init__(self, source_xml: bytes | str,
                 config: LiberoPickPlaceSolutionConfigV1 | None = None):
        raw = source_xml.encode("utf-8") if isinstance(source_xml, str) else bytes(source_xml)
        if not raw:
            raise ValueError("LIBERO Solution requires nonempty composed source MJCF bytes")
        self.source_xml_sha256 = hashlib.sha256(raw).hexdigest()
        self.tcp_profile = derive_panda_tcp_profile_v2(
            raw, tcp_id=TCP_ID, hand_frame_id=HAND_FRAME_ID, site_name=SITE_NAME,
        )
        self.kinematics = PandaKinematics(
            raw, tcp_profile=self.tcp_profile, native_prefix="robot0_",
            base_body_id=BASE_BODY_ID,
        )
        self.config = config or LiberoPickPlaceSolutionConfigV1()
        self.config.validate()
        self.identity = solution_identity_v1(self.source_xml_sha256, self.config)
        self._reset_state()

    def _reset_state(self) -> None:
        self.stage = "uninitialized"
        self.done = False
        self.failed = False
        self.failure_reason = None
        self._episode_identity = None
        self._last_boundary_step = None
        self._pending_action = False
        self._stage_steps = 0
        self._actions = 0
        self._initial_bowl = None
        self._plate = None
        self._last_observation = None
        self._last_action_receipt = None

    def reset(self, observation, info: Mapping[str, object], metadata, **_kwargs) -> None:
        self._reset_state()
        if not isinstance(metadata, Mapping):
            raise TypeError("LIBERO Solution requires the public SelectedReferenceEnv metadata mapping")
        artifact_hash = metadata.get("task_artifact_hash")
        if type(artifact_hash) is not str or not artifact_hash:
            raise ValueError("LIBERO Solution received invalid task Artifact identity")
        if metadata.get("solution_identity") != self.identity:
            raise ValueError("SelectedReferenceEnv metadata names a different caller-owned Solution")
        if metadata.get("source_xml_sha256") != self.source_xml_sha256:
            raise ValueError("LIBERO Solution MJCF differs from the selected episode source")
        if metadata.get("source_closure_digest") != info.get("source_closure_digest"):
            raise ValueError("LIBERO Solution source closure differs from the selected episode")
        action_schema = metadata.get("action_schema")
        if (not isinstance(action_schema, Mapping)
                or action_schema.get("schema_id") != self.action_schema_id
                or action_schema.get("dimension") != 8):
            raise ValueError("LIBERO Solution action schema differs from its selected task route")
        if self.action_schema_id == POSE_ACTION_SCHEMA_V1 and (
                action_schema.get("controller_kind") != "absolute_pose"
                or action_schema.get("reference") != "world"
                or action_schema.get("rotation_representation") != "quaternion_wxyz"):
            raise ValueError("LIBERO Solution pose action schema must be explicit world/quaternion_wxyz")
        if (metadata.get("provider") != "mujoco" or metadata.get("backend") != "cpu"):
            raise ValueError("LIBERO task #1 Solution is currently enabled only for MuJoCo CPU")
        identity = _boundary_identity(info)
        if identity[5] != 0 or identity[6] != 0.0:
            raise ValueError("LIBERO Solution must initialize at the reset boundary")
        if info.get("provider") != "mujoco":
            raise ValueError("LIBERO Solution reset info names an unsupported provider")
        if info.get("source_xml_sha256") != self.source_xml_sha256:
            raise ValueError("LIBERO reset info source MJCF differs from the Solution")
        sample = info.get("reset_sample_v1")
        if (not isinstance(sample, Mapping) or sample.get("sample_id") != identity[4]
                or sample.get("task_artifact_hash") != artifact_hash):
            raise ValueError("LIBERO reset sample identity is missing or mismatched")
        self._episode_identity = identity[:5]
        self._last_boundary_step = 0
        self._initial_bowl = _body_position(observation, "bowl_body_pose")
        self._plate = _body_position(observation, "plate_body_pose")
        _state_vector(observation)
        self.stage = "approach"
        self._last_observation = observation

    def _validate_boundary(self, observation, info: Mapping[str, object], *, next_step: bool) -> tuple[np.ndarray, np.ndarray]:
        if self._episode_identity is None or self._last_boundary_step is None:
            raise RuntimeError("LIBERO Solution must be reset before execution")
        identity = _boundary_identity(info)
        if identity[:5] != self._episode_identity:
            raise ValueError("LIBERO Solution observed a different source, materialization, episode or reset")
        expected_step = self._last_boundary_step + (1 if next_step else 0)
        if identity[5] != expected_step:
            raise ValueError("LIBERO Solution observed a skipped, stale or repeated control boundary")
        if next_step and self._pending_action is not True:
            raise RuntimeError("LIBERO Solution received an unrequested post-step observation")
        if not next_step and self._pending_action:
            raise RuntimeError("LIBERO Solution requires observe() after each action")
        expected_time = identity[5] * 0.05
        if abs(identity[6] - expected_time) > 1e-6:
            raise ValueError("LIBERO Solution observed a boundary outside the frozen 20 Hz timebase")
        joints, ee_position = _state_vector(observation)
        obs_digest = np.asarray(observation["state"].get("boundary_identity_sha256"), dtype=np.uint8)
        expected_digest = info.get("state_boundary_identity_sha256")
        if (obs_digest.shape != (32,) or type(expected_digest) is not str
                or obs_digest.tobytes().hex() != expected_digest):
            raise ValueError("LIBERO Solution observation and info boundary identities disagree")
        return joints, ee_position

    def _target(self) -> np.ndarray:
        if self._initial_bowl is None or self._plate is None:
            raise RuntimeError("LIBERO Solution reset geometry is unavailable")
        bowl = self._initial_bowl
        plate = self._plate
        if self.stage == "approach":
            return bowl + np.asarray((0.0, 0.0, 0.15))
        if self.stage in {"descend", "grasp"}:
            return bowl + np.asarray((0.0, 0.0, 0.05))
        if self.stage == "lift":
            return bowl + np.asarray((0.0, 0.0, 0.20))
        if self.stage == "carry":
            return np.asarray((plate[0], plate[1], bowl[2] + 0.20))
        if self.stage in {"place", "release"}:
            return plate + np.asarray((0.0, 0.0, 0.085))
        raise RuntimeError(f"LIBERO Solution has no target in stage {self.stage!r}")

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction:
        joints, _ee_position = self._validate_boundary(observation, info, next_step=False)
        if self.done or self.failed:
            raise RuntimeError("LIBERO Solution has already stopped")
        target = self._target()
        transform, jacobian = self.kinematics.fk_jacobian(joints)
        current_position = transform[:3, 3]
        error = target - current_position
        distance = float(np.linalg.norm(error))
        step = error if distance <= self.config.max_cartesian_increment_m else (
            error * (self.config.max_cartesian_increment_m / distance)
        )
        position_jacobian = jacobian[:3, :]
        damping = 0.025
        system = position_jacobian @ position_jacobian.T + damping * damping * np.eye(3)
        delta_q = position_jacobian.T @ np.linalg.solve(system, step)
        largest = float(np.max(np.abs(delta_q)))
        if largest > self.config.max_joint_increment_rad:
            delta_q *= self.config.max_joint_increment_rad / largest
        desired = joints + delta_q
        if np.any(desired < _JOINT_LIMITS[:, 0]) or np.any(desired > _JOINT_LIMITS[:, 1]):
            raise ValueError("LIBERO Solution waypoint would leave the exact Panda joint ranges")
        opening = _OPENING_BY_STAGE.get(self.stage)
        if opening is None:
            raise RuntimeError(f"LIBERO Solution has no gripper policy in stage {self.stage!r}")
        action = np.asarray((*desired, opening), dtype=np.float32)
        self._last_action_receipt = {
            "stage": self.stage,
            "action": [float(value) for value in action],
            "target_position_m": [float(value) for value in target],
            "target_error_m": [float(value) for value in error],
            "diagnostics": {
                "waypoint_distance_m": distance,
                "cartesian_increment_m": float(np.linalg.norm(step)),
                "stage_step": self._stage_steps,
                "source_fk_position_m": [float(value) for value in current_position],
            },
        }
        self._pending_action = True
        self._actions += 1
        return ExpertAction(
            action=action,
            stage=self.stage,
            diagnostics=dict(self._last_action_receipt["diagnostics"]),
        )

    def observe(self, observation, reward: float, terminated: bool, truncated: bool,
                info: Mapping[str, object], **_kwargs) -> None:
        _joints, ee_position = self._validate_boundary(observation, info, next_step=True)
        self._pending_action = False
        identity = _boundary_identity(info)
        self._last_boundary_step = identity[5]
        self._last_observation = observation
        self._stage_steps += 1
        target = self._target()
        target_error = float(np.linalg.norm(target - ee_position))
        tolerance = self.config.position_tolerance_m

        if self.stage == "approach" and target_error <= tolerance:
            self.stage, self._stage_steps = "descend", 0
        elif self.stage == "descend" and target_error <= tolerance:
            self.stage, self._stage_steps = "grasp", 0
        elif self.stage == "grasp" and self._stage_steps >= self.config.grasp_dwell_steps:
            self.stage, self._stage_steps = "lift", 0
        elif self.stage == "lift" and target_error <= tolerance:
            bowl_now = _body_position(observation, "bowl_body_pose")
            if bowl_now[2] >= self._initial_bowl[2] + 0.035:
                self.stage, self._stage_steps = "carry", 0
            elif self._stage_steps >= 60:
                self.failed = True
                self.failure_reason = "bowl_not_lifted_after_grasp"
        elif self.stage == "carry" and np.linalg.norm(target[:2] - ee_position[:2]) <= tolerance:
            self.stage, self._stage_steps = "place", 0
        elif self.stage == "place" and target_error <= tolerance:
            self.stage, self._stage_steps = "release", 0
        elif self.stage == "release":
            predicate = info.get("predicate_v1", {}).get("on_bowl_plate", {})
            success = info.get("is_success")
            if type(success) is not bool or predicate.get("status") not in {"available", "unavailable"}:
                raise ValueError("LIBERO Solution post-step info omits the typed On predicate result")
            if predicate.get("status") == "available" and predicate.get("value") is not success:
                raise ValueError("LIBERO task success and typed On predicate disagree")
            if (self._stage_steps >= self.config.release_dwell_steps
                    and success is True and predicate.get("status") == "available"):
                self.done = True
                self.stage = "complete"
            elif self._stage_steps >= self.config.release_timeout_steps:
                self.failed = True
                self.failure_reason = "released_bowl_did_not_satisfy_source_on_predicate"
        if truncated and not self.done:
            self.failed = True
            self.failure_reason = "horizon_truncated_before_source_task_success"
        if terminated and not self.done:
            self.failed = True
            self.failure_reason = "task_terminated_before_solution_completion"

    def outcome_report(self) -> dict[str, object]:
        return {
            "solution_schema_version": SOLUTION_SCHEMA,
            "solution_identity": self.identity,
            "solution_stage": self.stage,
            "solution_actions": self._actions,
            "last_action_receipt": self._last_action_receipt,
            "solution_done": bool(self.done),
            "solution_failed": bool(self.failed),
            "solution_failure_reason": self.failure_reason,
        }

    def abort(self, reason: str) -> None:
        if self.done:
            raise RuntimeError("completed LIBERO Solution cannot be aborted")
        self.failed = True
        self.failure_reason = str(reason)


class LiberoPickPlaceSolutionV2(LiberoPickPlaceSolutionV1):
    """Task #1 public-observation Solution with source-bound gravity bias."""

    solution_schema_version = SOLUTION_SCHEMA_V2

    def __init__(self, source_xml: bytes | str, *, source_closure_digest: str,
                 gravity_bias_model, config: LiberoPickPlaceSolutionConfigV1 | None = None):
        super().__init__(source_xml, config=config)
        if getattr(gravity_bias_model, "profile_id", None) != SOURCE_GRAVITY_PROFILE_V1:
            raise TypeError("LIBERO Solution v2 requires the source MJCF gravity-bias primitive")
        if (getattr(gravity_bias_model, "source_xml_sha256", None) != self.source_xml_sha256
                or getattr(gravity_bias_model, "source_closure_digest", None) != source_closure_digest):
            raise ValueError("LIBERO Solution v2 gravity model differs from its source XML/closure")
        self.source_closure_digest = source_closure_digest
        self.gravity_bias_model = gravity_bias_model
        self.identity = solution_identity_v2(
            self.source_xml_sha256, self.source_closure_digest, self.config,
        )
        self._gravity_queries = 0

    def reset(self, observation, info: Mapping[str, object], metadata, **kwargs) -> None:
        super().reset(observation, info, metadata, **kwargs)
        if info.get("source_closure_digest") != self.source_closure_digest:
            raise ValueError("LIBERO Solution v2 reset closure differs from its gravity model")
        self._gravity_queries = 0

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction:
        planned = super().act(observation, info)
        joints, _ee_position = _state_vector(observation)
        gravity = np.asarray(self.gravity_bias_model.gravity_torque(joints), dtype=np.float64)
        controller = LiberoMixedControlConfigV1()
        controller.validate()
        kp = np.asarray(controller.kp_Nm_per_rad, dtype=np.float64)
        if gravity.shape != (7,) or not np.isfinite(gravity).all():
            raise ValueError("LIBERO source gravity primitive must return seven finite N*m values")
        planner_target = np.asarray(planned.action[:7], dtype=np.float64)
        correction = gravity / kp
        compensated_target = planner_target + correction
        for index, name in enumerate(_JOINT_NAMES):
            low, high = _POSITION_LIMITS[name]
            if not low <= compensated_target[index] <= high:
                raise ValueError(f"gravity-compensated target would leave the source range: {name}")
        action_values = np.asarray((*compensated_target, float(planned.action[7])), dtype=np.float32)
        diagnostics = dict(planned.diagnostics)
        diagnostics.update({
            "gravity_compensation_profile_id": SOURCE_GRAVITY_PROFILE_V1,
            "gravity_bias_Nm": [float(value) for value in gravity],
            "gravity_target_offset_rad": [float(value) for value in correction],
            "planner_joint_target_rad": [float(value) for value in planner_target],
            "gravity_compensated_joint_target_rad": [float(value) for value in compensated_target],
            "gravity_source_model_identity_sha256": self.gravity_bias_model.model_identity_sha256,
        })
        self._gravity_queries += 1
        self._last_action_receipt.update({
            "planner_action": [float(value) for value in planned.action],
            "gravity_bias_Nm": [float(value) for value in gravity],
            "gravity_target_offset_rad": [float(value) for value in correction],
            "gravity_compensated_action": [float(value) for value in action_values],
            "gravity_source_model_identity_sha256": self.gravity_bias_model.model_identity_sha256,
            "diagnostics": diagnostics,
        })
        return ExpertAction(action=action_values, stage=planned.stage, diagnostics=diagnostics)

    def outcome_report(self) -> dict[str, object]:
        report = super().outcome_report()
        return {
            **report,
            "solution_schema_version": SOLUTION_SCHEMA_V2,
            "source_closure_digest": self.source_closure_digest,
            "gravity_compensation": self.gravity_compensation_receipt(),
        }

    def gravity_compensation_receipt(self) -> dict[str, object]:
        return {
            **self.gravity_bias_model.identity_mapping(),
            "episode_query_count": self._gravity_queries,
        }


class LiberoPickPlaceSolutionV3(LiberoPickPlaceSolutionV1):
    """Task #1 world-pose Solution using the shared planner and arm resolver."""

    action_schema_id = POSE_ACTION_SCHEMA_V1
    solution_schema_version = SOLUTION_SCHEMA_V3

    def __init__(self, source_xml: bytes | str,
                 source_closure_digest: str,
                 config: LiberoPickPlaceSolutionConfigV1 | None = None,
                 planner_config: CartesianPosePlannerConfig | None = None):
        super().__init__(source_xml, config=config)
        self.source_closure_digest = source_closure_digest
        if (type(source_closure_digest) is not str or len(source_closure_digest) != 64
                or any(character not in "0123456789abcdef" for character in source_closure_digest)):
            raise ValueError("LIBERO Solution v3 requires a lowercase source closure SHA-256")
        self.planner_config = planner_config or CartesianPosePlannerConfig(
            max_translation_per_step=0.012,
            max_translation_acceleration_per_step=0.004,
            max_rotation_per_step=0.08,
            max_rotation_acceleration_per_step=0.04,
            settle_steps=0,
            max_steps=200,
        )
        self.pose_planner = CartesianPosePlanner(self.planner_config)
        self.identity = solution_identity_v3(
            self.source_xml_sha256, self.source_closure_digest,
            self.config, self.planner_config,
        )
        self._grasp_quaternion_wxyz = None
        self._pose_plan = None
        self._pose_plan_index = 0
        self._pose_plan_stage = None

    def _refresh_bowl_reference_from_public_pose(self, observation) -> bool:
        """Track bowl settling while approaching, then freeze its grasp reference."""
        if self.stage not in {"approach", "descend"}:
            return False
        current = _body_position(observation, "bowl_body_pose")
        if self._initial_bowl is None or np.linalg.norm(current - self._initial_bowl) > 1e-6:
            self._initial_bowl = current
            self._pose_plan = None
            self._pose_plan_index = 0
            self._pose_plan_stage = None
            return True
        return False

    def reset(self, observation, info: Mapping[str, object], metadata, **kwargs) -> None:
        super().reset(observation, info, metadata, **kwargs)
        if info.get("source_closure_digest") != self.source_closure_digest:
            raise ValueError("LIBERO Solution v3 reset closure differs from its selected source")
        current_pose = np.asarray(observation["state"].get("ee_pose"), dtype=np.float64)
        if current_pose.shape != (7,) or not np.isfinite(current_pose).all():
            raise ValueError("LIBERO Solution v3 requires the typed source TCP world pose at reset")
        self._grasp_quaternion_wxyz = normalize_quat_wxyz(current_pose[3:7])
        self._pose_plan = None
        self._pose_plan_index = 0
        self._pose_plan_stage = None

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction:
        _joints, current_position = self._validate_boundary(observation, info, next_step=False)
        if self.done or self.failed:
            raise RuntimeError("LIBERO Solution has already stopped")
        if self._grasp_quaternion_wxyz is None:
            raise RuntimeError("LIBERO Solution v3 has no source-derived grasp orientation")
        current_pose = np.asarray(observation["state"].get("ee_pose"), dtype=np.float64)
        if current_pose.shape != (7,) or not np.isfinite(current_pose).all():
            raise ValueError("LIBERO Solution v3 requires a finite world TCP pose")
        current_pose = current_pose.copy()
        current_pose[3:7] = normalize_quat_wxyz(current_pose[3:7])
        target_position = self._target()
        target_pose = np.asarray((*target_position, *self._grasp_quaternion_wxyz), dtype=np.float64)
        opening_m = _OPENING_BY_STAGE.get(self.stage)
        if opening_m is None:
            raise RuntimeError(f"LIBERO Solution has no gripper policy in stage {self.stage!r}")
        gripper_scalar = float(opening_m / 0.04 - 1.0)
        if not -1.0 <= gripper_scalar <= 1.0:
            raise ValueError("aggregate finger opening does not map to the normalized planner gripper range")
        if (self._pose_plan is None or self._pose_plan_stage != self.stage
                or self._pose_plan_index >= len(self._pose_plan)):
            if self.stage == "grasp":
                finger_positions = np.asarray(
                    observation["state"].get("joint_position"), dtype=np.float64,
                )
                if finger_positions.shape != (9,) or not np.isfinite(finger_positions).all():
                    raise ValueError("LIBERO Solution v3 requires public signed finger positions")
                actual_opening = float(finger_positions[7] - finger_positions[8])
                current_gripper = float(np.clip(actual_opening / 0.04 - 1.0, -1.0, 1.0))
                self._pose_plan = self.pose_planner.plan_gripper_transition(
                    pose=target_pose,
                    start_gripper=current_gripper,
                    goal_gripper=gripper_scalar,
                    steps=max(4, self.config.grasp_dwell_steps),
                    settle_steps=0,
                )
            else:
                self._pose_plan = self.pose_planner.plan_to_pose(
                    current_pose=current_pose,
                    goal_pose=target_pose,
                    gripper=gripper_scalar,
                    settle_steps=0,
                )
            self._pose_plan_index = 0
            self._pose_plan_stage = self.stage
        action = np.asarray(self._pose_plan[self._pose_plan_index], dtype=np.float32)
        if action.shape != (8,) or not np.isfinite(action).all():
            raise ValueError("CartesianPosePlanner returned an invalid absolute world-pose action")
        action_pose = np.asarray(action[:7], dtype=np.float64)
        self._last_action_receipt = {
            "solution_schema_version": SOLUTION_SCHEMA_V3,
            "action_schema_id": POSE_ACTION_SCHEMA_V1,
            "stage": self.stage,
            "action": [float(value) for value in action],
            "current_world_pose": [float(value) for value in current_pose],
            "target_world_pose": [float(value) for value in target_pose],
            "planner_world_pose": [float(value) for value in action_pose],
            "source_grasp_quaternion_wxyz": [float(value) for value in self._grasp_quaternion_wxyz],
            "source_tcp_profile_identity_sha256": self.tcp_profile.identity_hash,
            "aggregate_opening_m": float(opening_m),
            "normalized_gripper_scalar": float(action[7]),
            "diagnostics": {
                "waypoint_distance_m": float(np.linalg.norm(target_position - current_position)),
            "planner_step_translation_m": float(np.linalg.norm(action_pose[:3] - current_pose[:3])),
            "planner_step_rotation_rad": float(quat_angle_wxyz(action_pose[3:7], current_pose[3:7])),
            "planner_path_index": int(self._pose_plan_index),
            "planner_path_length": int(len(self._pose_plan)),
            "stage_step": self._stage_steps,
            "planner_owner": (
                "CartesianPosePlanner.plan_gripper_transition"
                if self.stage == "grasp" else "CartesianPosePlanner.plan_to_pose"
            ),
            "source_pose_observation_used": True,
            },
        }
        self._pending_action = True
        self._actions += 1
        return ExpertAction(
            action=action,
            stage=self.stage,
            diagnostics=dict(self._last_action_receipt["diagnostics"]),
        )

    def observe(self, observation, reward: float, terminated: bool, truncated: bool,
                info: Mapping[str, object], **_kwargs) -> None:
        """Advance only from current public pose, finger and task feedback."""
        joints, ee_position = self._validate_boundary(observation, info, next_step=True)
        # The source reset row places the bowl above its settled support pose.
        # Follow its live public pose during approach/descent so the planner
        # does not close the gripper around the stale reset height. Freeze the
        # reference once grasp begins, so later object motion remains evidence
        # for the lift predicate instead of moving the goal with the object.
        self._refresh_bowl_reference_from_public_pose(observation)
        self._pending_action = False
        identity = _boundary_identity(info)
        self._last_boundary_step = identity[5]
        self._last_observation = observation
        self._stage_steps += 1
        if self._pose_plan is not None and self._pose_plan_stage == self.stage:
            self._pose_plan_index += 1
        target = self._target()
        target_error = float(np.linalg.norm(target - ee_position))
        current_pose = np.asarray(observation["state"].get("ee_pose"), dtype=np.float64)
        if current_pose.shape != (7,) or not np.isfinite(current_pose).all():
            raise ValueError("LIBERO Solution v3 post-step observation omits its world TCP pose")
        orientation_error = float(quat_angle_wxyz(
            normalize_quat_wxyz(current_pose[3:7]), self._grasp_quaternion_wxyz,
        ))
        pose_reached = (
            target_error <= self.config.position_tolerance_m
            and orientation_error <= 0.12
        )
        stage_before = self.stage
        planned_pose = np.asarray(
            (self._last_action_receipt or {}).get("planner_world_pose", current_pose),
            dtype=np.float64,
        )
        tracking_position_error = float(np.linalg.norm(planned_pose[:3] - current_pose[:3]))
        tracking_orientation_error = float(quat_angle_wxyz(
            planned_pose[3:7], normalize_quat_wxyz(current_pose[3:7]),
        ))
        if tracking_position_error > 0.025 or tracking_orientation_error > 0.25:
            self._pose_plan = None
            self._pose_plan_index = 0
            self._pose_plan_stage = None
        if stage_before == "approach" and pose_reached:
            self.stage, self._stage_steps = "descend", 0
        elif stage_before == "descend" and pose_reached:
            self.stage, self._stage_steps = "grasp", 0
        elif stage_before == "grasp":
            # Confirm the signed fingers actually moved to the requested
            # aggregate aperture before beginning the lift.
            finger_positions = np.asarray(
                observation["state"].get("joint_position"), dtype=np.float64,
            )
            if finger_positions.shape != (9,) or not np.isfinite(finger_positions).all():
                raise ValueError("LIBERO Solution v3 requires public signed finger positions")
            actual_opening = float(finger_positions[7] - finger_positions[8])
            requested_opening = _OPENING_BY_STAGE["grasp"]
            if (self._stage_steps >= 2
                    and actual_opening <= requested_opening + 0.003):
                self.stage, self._stage_steps = "lift", 0
        elif stage_before == "lift" and pose_reached:
            bowl_now = _body_position(observation, "bowl_body_pose")
            if bowl_now[2] >= self._initial_bowl[2] + 0.035:
                self.stage, self._stage_steps = "carry", 0
            elif self._stage_steps >= 60:
                self.failed = True
                self.failure_reason = "bowl_not_lifted_after_public_grasp_feedback"
        elif stage_before == "carry" and np.linalg.norm(target[:2] - ee_position[:2]) <= self.config.position_tolerance_m:
            self.stage, self._stage_steps = "place", 0
        elif stage_before == "place" and pose_reached:
            self.stage, self._stage_steps = "release", 0
        elif stage_before == "release":
            predicate = info.get("predicate_v1", {}).get("on_bowl_plate", {})
            success = info.get("is_success")
            if type(success) is not bool or predicate.get("status") not in {"available", "unavailable"}:
                raise ValueError("LIBERO Solution post-step info omits the typed On predicate result")
            if predicate.get("status") == "available" and predicate.get("value") is not success:
                raise ValueError("LIBERO task success and typed On predicate disagree")
            if (self._stage_steps >= self.config.release_dwell_steps
                    and success is True and predicate.get("status") == "available"):
                self.done = True
                self.stage = "complete"
            elif self._stage_steps >= self.config.release_timeout_steps:
                self.failed = True
                self.failure_reason = "released_bowl_did_not_satisfy_source_on_predicate"
        if self.stage != stage_before:
            self._pose_plan = None
            self._pose_plan_index = 0
            self._pose_plan_stage = None
        self._last_action_receipt = {
            **(self._last_action_receipt or {}),
            "post_step_feedback": {
                "stage_before": stage_before,
                "stage_after": self.stage,
                "tcp_position_error_m": target_error,
                "tcp_orientation_error_rad": orientation_error,
                "planner_tracking_position_error_m": tracking_position_error,
                "planner_tracking_orientation_error_rad": tracking_orientation_error,
                "aggregate_finger_opening_m": float(
                    np.asarray(observation["state"]["joint_position"], dtype=np.float64)[7]
                    - np.asarray(observation["state"]["joint_position"], dtype=np.float64)[8]
                ),
                "bowl_world_z_m": float(_body_position(observation, "bowl_body_pose")[2]),
                "task_success": info.get("is_success"),
                "stage_step": self._stage_steps,
            },
        }
        if truncated and not self.done:
            self.failed = True
            self.failure_reason = "horizon_truncated_before_source_task_success"
        if terminated and not self.done:
            self.failed = True
            self.failure_reason = "task_terminated_before_solution_completion"

    def outcome_report(self) -> dict[str, object]:
        return {
            "solution_schema_version": SOLUTION_SCHEMA_V3,
            "solution_identity": self.identity,
            "solution_stage": self.stage,
            "solution_actions": self._actions,
            "last_action_receipt": self._last_action_receipt,
            "solution_done": bool(self.done),
            "solution_failed": bool(self.failed),
            "solution_failure_reason": self.failure_reason,
            "source_closure_digest": self.source_closure_digest,
            "action_schema_id": POSE_ACTION_SCHEMA_V1,
            "source_grasp_quaternion_wxyz": (
                None if self._grasp_quaternion_wxyz is None
                else [float(value) for value in self._grasp_quaternion_wxyz]
            ),
        }


class LiberoPickPlaceSolutionV4(LiberoPickPlaceSolutionV3):
    """Convergence-gated OSC task plan with public bilateral finger feedback."""

    solution_schema_version = SOLUTION_SCHEMA_V4

    def __init__(self, source_xml: bytes | str, source_closure_digest: str,
                 config: LiberoPickPlaceSolutionConfigV1 | None = None,
                 planner_config: CartesianPosePlannerConfig | None = None):
        selected_planner = planner_config or CartesianPosePlannerConfig(
            max_translation_per_step=0.0055,
            max_translation_acceleration_per_step=0.002,
            max_rotation_per_step=0.08,
            max_rotation_acceleration_per_step=0.04,
            settle_steps=0,
            max_steps=200,
        )
        super().__init__(
            source_xml, source_closure_digest, config=config,
            planner_config=selected_planner,
        )
        self.identity = solution_identity_v4(
            self.source_xml_sha256, self.source_closure_digest,
            self.config, self.planner_config,
        )
        self._grasp_contact_streak = 0
        self._lift_contact_loss_streak = 0
        self._grasp_confirmed = False

    def reset(self, observation, info: Mapping[str, object], metadata, **kwargs) -> None:
        super().reset(observation, info, metadata, **kwargs)
        self._grasp_contact_streak = 0
        self._lift_contact_loss_streak = 0
        self._grasp_confirmed = False

    def _opening_for_stage(self):
        return _OPENING_BY_STAGE_V4.get(self.stage)

    def _target(self) -> np.ndarray:
        if self._initial_bowl is None or self._plate is None:
            raise RuntimeError("LIBERO Solution reset geometry is unavailable")
        bowl = self._initial_bowl
        plate = self._plate
        if self.stage == "approach":
            return bowl + np.asarray((0.0, 0.0, 0.15))
        if self.stage in {"descend", "grasp"}:
            return bowl + np.asarray((0.0, 0.0, _GRASP_TCP_HEIGHT_V4_M))
        if self.stage == "lift":
            return bowl + np.asarray((0.0, 0.0, 0.20))
        if self.stage == "carry":
            return np.asarray((plate[0], plate[1], bowl[2] + 0.20))
        if self.stage in {"place", "release"}:
            return plate + np.asarray((0.0, 0.0, 0.085))
        raise RuntimeError(f"LIBERO Solution v4 has no target in stage {self.stage!r}")

    @staticmethod
    def _bilateral_finger_contact(info: Mapping[str, object]):
        contact = info.get("contact_summary_v2")
        if not isinstance(contact, Mapping):
            return None, None, "contact_summary_missing"
        context = info.get("boundary_context_v1")
        if not isinstance(context, Mapping):
            return None, None, "boundary_context_missing"
        identity_fields = (
            "source_id", "source_closure_digest", "provider_materialization_id",
            "episode_id", "reset_sample_id", "control_step", "state_revision",
            "simulation_time_s",
        )
        for name in identity_fields:
            expected = context.get(name)
            if name != "state_revision" and info.get(name) != expected:
                return None, None, "boundary_context_mismatch"
            if contact.get(name) != expected:
                return None, None, "contact_summary_stale_or_wrong_boundary"
        if contact.get("schema_version") != "task-contact-summary-v2":
            return None, None, "contact_summary_schema_mismatch"
        required_pairs = tuple(sorted((
            tuple(sorted(("panda-v1/finger-left", "akita_black_bowl_1"))),
            tuple(sorted(("panda-v1/finger-right", "akita_black_bowl_1"))),
        )))
        requested = tuple(tuple(pair) for pair in contact.get("requested_pairs", ()))
        covered = tuple(tuple(pair) for pair in contact.get("covered_pairs", ()))
        if contact.get("status") != "available":
            return None, None, str(contact.get("reason") or "contact_summary_unavailable")
        if not set(required_pairs) <= set(requested) or not set(required_pairs) <= set(covered):
            return None, None, "bilateral_finger_contact_query_not_covered"
        counts = contact.get("pair_counts")
        if not isinstance(counts, Mapping):
            return None, None, "contact_pair_counts_missing"
        keys = tuple("/".join(pair) for pair in required_pairs)
        values = tuple(counts.get(key) for key in keys)
        if any(type(value) is not int or value < 0 for value in values):
            return None, None, "bilateral_finger_pair_count_invalid"
        return values[0] > 0 and values[1] > 0, values, "available"

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction:
        joints, _ = self._validate_boundary(observation, info, next_step=False)
        if self.done or self.failed:
            raise RuntimeError("LIBERO Solution has already stopped")
        if self._grasp_quaternion_wxyz is None:
            raise RuntimeError("LIBERO Solution v4 has no source-derived grasp orientation")
        current_pose = np.asarray(observation["state"].get("ee_pose"), dtype=np.float64)
        if current_pose.shape != (7,) or not np.isfinite(current_pose).all():
            raise ValueError("LIBERO Solution v4 requires a finite world TCP pose")
        current_pose[3:7] = normalize_quat_wxyz(current_pose[3:7])
        target_position = self._target()
        target_pose = np.asarray((*target_position, *self._grasp_quaternion_wxyz), dtype=np.float64)
        opening_m = self._opening_for_stage()
        if opening_m is None:
            raise RuntimeError(f"LIBERO Solution v4 has no gripper policy in stage {self.stage!r}")
        gripper_scalar = float(opening_m / 0.04 - 1.0)
        if not -1.0 <= gripper_scalar <= 1.0:
            raise ValueError("stage opening does not map to the normalized planner range")

        if (self._pose_plan is None or self._pose_plan_stage != self.stage
                or self._pose_plan_index >= len(self._pose_plan)):
            if self.stage in {"grasp", "release"}:
                finger_positions = np.asarray(
                    observation["state"].get("joint_position"), dtype=np.float64,
                )
                if finger_positions.shape != (9,) or not np.isfinite(finger_positions).all():
                    raise ValueError("LIBERO Solution v4 requires public signed finger positions")
                actual_opening = float(finger_positions[7] - finger_positions[8])
                current_gripper = float(np.clip(actual_opening / 0.04 - 1.0, -1.0, 1.0))
                steps = (max(4, self.config.grasp_dwell_steps) if self.stage == "grasp"
                         else max(4, self.config.release_dwell_steps))
                self._pose_plan = self.pose_planner.plan_gripper_transition(
                    pose=target_pose, start_gripper=current_gripper,
                    goal_gripper=gripper_scalar, steps=steps, settle_steps=0,
                )
            else:
                self._pose_plan = self.pose_planner.plan_to_pose(
                    current_pose=current_pose, goal_pose=target_pose,
                    gripper=gripper_scalar, settle_steps=0,
                )
            self._pose_plan_index = 0
            self._pose_plan_stage = self.stage

        action = np.asarray(self._pose_plan[self._pose_plan_index], dtype=np.float32)
        if action.shape != (8,) or not np.isfinite(action).all():
            raise ValueError("CartesianPosePlanner returned an invalid v4 world-pose action")
        self._last_action_receipt = {
            "solution_schema_version": SOLUTION_SCHEMA_V4,
            "solution_identity": self.identity,
            "action_schema_id": POSE_ACTION_SCHEMA_V1,
            "stage": self.stage,
            "action": [float(value) for value in action],
            "current_world_pose": [float(value) for value in current_pose],
            "target_world_pose": [float(value) for value in target_pose],
            "planner_world_pose": [float(value) for value in action[:7]],
            "source_grasp_quaternion_wxyz": [float(value) for value in self._grasp_quaternion_wxyz],
            "source_tcp_profile_identity_sha256": self.tcp_profile.identity_hash,
            "aggregate_opening_m": float(opening_m),
            "normalized_gripper_scalar": float(action[7]),
            "grasp_strategy": (
                "insert_narrow_fingers_below_rim_then_hold_contact_aperture_v2"
                if self.solution_schema_version == SOLUTION_SCHEMA_V5
                else "insert_narrow_fingers_below_rim_then_open_outward_v1"
            ),
            "diagnostics": {
                "waypoint_distance_m": float(np.linalg.norm(target_position - current_pose[:3])),
                "planner_step_translation_m": float(np.linalg.norm(action[:3] - current_pose[:3])),
                "planner_step_rotation_rad": float(quat_angle_wxyz(action[3:7], current_pose[3:7])),
                "planner_path_index": int(self._pose_plan_index),
                "planner_path_length": int(len(self._pose_plan)),
                "stage_step": self._stage_steps,
                "planner_owner": (
                    "CartesianPosePlanner.plan_gripper_transition"
                    if self.stage in {"grasp", "release"}
                    else "CartesianPosePlanner.plan_to_pose"
                ),
                "advancement_policy": "public_TCP_waypoint_convergence_gated_v1",
                "source_pose_observation_used": True,
            },
        }
        self._pending_action = True
        self._actions += 1
        return ExpertAction(action=action, stage=self.stage,
                            diagnostics=dict(self._last_action_receipt["diagnostics"]))

    def observe(self, observation, reward: float, terminated: bool, truncated: bool,
                info: Mapping[str, object], **_kwargs) -> None:
        joints, ee_position = self._validate_boundary(observation, info, next_step=True)
        self._refresh_bowl_reference_from_public_pose(observation)
        self._pending_action = False
        identity = _boundary_identity(info)
        self._last_boundary_step = identity[5]
        self._last_observation = observation
        self._stage_steps += 1
        current_pose = np.asarray(observation["state"].get("ee_pose"), dtype=np.float64)
        if current_pose.shape != (7,) or not np.isfinite(current_pose).all():
            raise ValueError("LIBERO Solution v4 post-step observation omits its TCP world pose")
        current_pose[3:7] = normalize_quat_wxyz(current_pose[3:7])
        bilateral, contact_counts, contact_status = self._bilateral_finger_contact(info)
        planned_pose = np.asarray(
            (self._last_action_receipt or {}).get("planner_world_pose", current_pose),
            dtype=np.float64,
        )
        tracking_position_error = float(np.linalg.norm(planned_pose[:3] - current_pose[:3]))
        tracking_orientation_error = float(quat_angle_wxyz(planned_pose[3:7], current_pose[3:7]))
        planned_action = np.asarray((self._last_action_receipt or {}).get("action", ()), dtype=np.float64)
        finger_positions = np.asarray(observation["state"].get("joint_position"), dtype=np.float64)
        if planned_action.shape != (8,) or finger_positions.shape != (9,):
            raise ValueError("LIBERO Solution v4 lost its planned action or signed gripper feedback")
        actual_opening = float(finger_positions[7] - finger_positions[8])
        planned_opening = 0.04 * (float(planned_action[7]) + 1.0)
        gripper_tracking_error = abs(actual_opening - planned_opening)
        stage_before = self.stage
        target = self._target()
        target_error = float(np.linalg.norm(target - ee_position))
        orientation_error = float(quat_angle_wxyz(current_pose[3:7], self._grasp_quaternion_wxyz))
        pose_reached = target_error <= self.config.position_tolerance_m and orientation_error <= 0.12

        if tracking_position_error > 0.025 or tracking_orientation_error > 0.25:
            self._pose_plan = None
            self._pose_plan_index = 0
            self._pose_plan_stage = None
            waypoint_advanced = False
        else:
            position_converged = tracking_position_error <= _WAYPOINT_POSITION_TOLERANCE_V4_M
            orientation_converged = tracking_orientation_error <= _WAYPOINT_ORIENTATION_TOLERANCE_V4_RAD
            gripper_converged = gripper_tracking_error <= 0.006
            waypoint_advanced = False
            if (self._pose_plan is not None and self._pose_plan_stage == self.stage
                    and position_converged and orientation_converged and gripper_converged):
                self._pose_plan_index += 1
                waypoint_advanced = True

        if stage_before == "approach" and pose_reached:
            self.stage, self._stage_steps = "descend", 0
        elif stage_before == "descend" and pose_reached:
            self.stage, self._stage_steps = "grasp", 0
            self._grasp_contact_streak = 0
        elif stage_before == "grasp":
            self._grasp_contact_streak = self._grasp_contact_streak + 1 if bilateral is True else 0
            if self._grasp_contact_streak >= _GRASP_CONTACT_DWELL_V4:
                self._grasp_confirmed = True
                self.stage, self._stage_steps = "lift", 0
                self._lift_contact_loss_streak = 0
            elif self._stage_steps >= _STAGE_TIMEOUTS_V4["grasp"]:
                self.failed = True
                self.failure_reason = (
                    "bilateral_finger_contact_unavailable" if bilateral is None
                    else "bowl_rim_not_bilaterally_contacted"
                )
        elif stage_before == "lift":
            self._lift_contact_loss_streak = (
                self._lift_contact_loss_streak + 1 if bilateral is False else 0
            )
            bowl_now = _body_position(observation, "bowl_body_pose")
            if bowl_now[2] >= self._initial_bowl[2] + 0.035:
                self.stage, self._stage_steps = "carry", 0
            elif (self._lift_contact_loss_streak >= 3
                  and self._stage_steps >= self._lift_contact_loss_streak):
                self.failed = True
                self.failure_reason = "bilateral_grasp_lost_during_lift"
            elif self._stage_steps >= _STAGE_TIMEOUTS_V4["lift"]:
                self.failed = True
                self.failure_reason = "bowl_not_lifted_after_bilateral_grasp"
        elif stage_before == "carry":
            bowl_now = _body_position(observation, "bowl_body_pose")
            if bowl_now[2] < self._initial_bowl[2] + 0.025:
                self.failed = True
                self.failure_reason = "bowl_dropped_during_carry"
            elif np.linalg.norm(target[:2] - ee_position[:2]) <= self.config.position_tolerance_m:
                self.stage, self._stage_steps = "place", 0
            elif self._stage_steps >= _STAGE_TIMEOUTS_V4["carry"]:
                self.failed = True
                self.failure_reason = "plate_transfer_stage_timeout"
        elif stage_before == "place" and pose_reached:
            self.stage, self._stage_steps = "release", 0
        elif stage_before == "release":
            predicate = info.get("predicate_v1", {}).get("on_bowl_plate", {})
            success = info.get("is_success")
            if type(success) is not bool or predicate.get("status") not in {"available", "unavailable"}:
                raise ValueError("LIBERO Solution post-step info omits its typed On predicate")
            if predicate.get("status") == "available" and predicate.get("value") is not success:
                raise ValueError("LIBERO task success and typed On predicate disagree")
            released = bilateral is False and actual_opening <= _OPENING_BY_STAGE_V4["release"] + 0.008
            if (self._stage_steps >= self.config.release_dwell_steps and success is True
                    and predicate.get("status") == "available" and released):
                self.done = True
                self.stage = "complete"
            elif self._stage_steps >= self.config.release_timeout_steps:
                self.failed = True
                self.failure_reason = (
                    "finger_contact_remained_after_release" if bilateral is True
                    else "released_bowl_did_not_satisfy_source_on_predicate"
                )

        if (self.stage == stage_before and not self.done and not self.failed
                and stage_before in _STAGE_TIMEOUTS_V4
                and self._stage_steps >= _STAGE_TIMEOUTS_V4[stage_before]):
            self.failed = True
            self.failure_reason = f"stage_timeout:{stage_before}"
        if self.stage != stage_before:
            self._pose_plan = None
            self._pose_plan_index = 0
            self._pose_plan_stage = None
        self._last_action_receipt = {
            **(self._last_action_receipt or {}),
            "post_step_feedback": {
                "stage_before": stage_before,
                "stage_after": self.stage,
                "tcp_target_position_error_m": target_error,
                "tcp_target_orientation_error_rad": orientation_error,
                "planner_tracking_position_error_m": tracking_position_error,
                "planner_tracking_orientation_error_rad": tracking_orientation_error,
                "waypoint_advanced": waypoint_advanced,
                "actual_opening_m": actual_opening,
                "planned_opening_m": planned_opening,
                "gripper_tracking_error_m": gripper_tracking_error,
                "bilateral_finger_contact": bilateral,
                "bilateral_contact_counts": contact_counts,
                "contact_feedback_status": contact_status,
                "grasp_confirmed": self._grasp_confirmed,
                "bowl_world_z_m": float(_body_position(observation, "bowl_body_pose")[2]),
                "task_success": info.get("is_success"),
                "stage_step": self._stage_steps,
            },
        }
        if truncated and not self.done:
            self.failed = True
            self.failure_reason = "horizon_truncated_before_source_task_success"
        if terminated and not self.done:
            self.failed = True
            self.failure_reason = "task_terminated_before_solution_completion"

    def outcome_report(self) -> dict[str, object]:
        return {
            "solution_schema_version": SOLUTION_SCHEMA_V4,
            "solution_identity": self.identity,
            "solution_stage": self.stage,
            "solution_actions": self._actions,
            "last_action_receipt": self._last_action_receipt,
            "solution_done": bool(self.done),
            "solution_failed": bool(self.failed),
            "solution_failure_reason": self.failure_reason,
            "source_closure_digest": self.source_closure_digest,
            "action_schema_id": POSE_ACTION_SCHEMA_V1,
            "source_grasp_quaternion_wxyz": (
                None if self._grasp_quaternion_wxyz is None
                else [float(value) for value in self._grasp_quaternion_wxyz]
            ),
            "grasp_confirmed_by_bilateral_contact": self._grasp_confirmed,
        }


class LiberoPickPlaceSolutionV5(LiberoPickPlaceSolutionV4):
    """V4 task behavior bound to the physics-rate, reset-reference OSC profile."""

    solution_schema_version = SOLUTION_SCHEMA_V5

    def _opening_for_stage(self):
        return _OPENING_BY_STAGE_V5.get(self.stage)

    def __init__(self, source_xml: bytes | str, source_closure_digest: str, *,
                 arm_resolver_identity: str,
                 config: LiberoPickPlaceSolutionConfigV1 | None = None,
                 planner_config: CartesianPosePlannerConfig | None = None):
        super().__init__(
            source_xml, source_closure_digest, config=config,
            planner_config=planner_config,
        )
        self.arm_resolver_identity = arm_resolver_identity
        self.identity = solution_identity_v5(
            self.source_xml_sha256, self.source_closure_digest,
            arm_resolver_identity=arm_resolver_identity,
            config=self.config, planner_config=self.planner_config,
        )

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction:
        proposal = super().act(observation, info)
        self._last_action_receipt = {
            **(self._last_action_receipt or {}),
            'solution_schema_version': SOLUTION_SCHEMA_V5,
        }
        return ExpertAction(
            action=proposal.action, stage=proposal.stage,
            diagnostics=dict(proposal.diagnostics),
        )

    def outcome_report(self) -> dict[str, object]:
        report = super().outcome_report()
        report['solution_schema_version'] = SOLUTION_SCHEMA_V5
        return report


class LiberoPickPlaceSolutionV6(LiberoPickPlaceSolutionV5):
    """Demonstration-grounded radial rim pinch using the public bowl pose."""

    solution_schema_version = SOLUTION_SCHEMA_V6
    grasp_strategy_id = "demonstration_grounded_bowl_local_radial_rim_pinch_v1"
    grasp_offset_source = "LIBERO task-0 demonstrated pre-lift median"

    def __init__(self, source_xml: bytes | str, source_closure_digest: str, *,
                 arm_resolver_identity: str,
                 config: LiberoPickPlaceSolutionConfigV1 | None = None,
                 planner_config: CartesianPosePlannerConfig | None = None):
        selected_planner = planner_config or CartesianPosePlannerConfig(
            max_translation_per_step=0.0025,
            max_translation_acceleration_per_step=0.001,
            max_rotation_per_step=0.04,
            max_rotation_acceleration_per_step=0.02,
            settle_steps=0,
            max_steps=200,
        )
        super().__init__(
            source_xml, source_closure_digest,
            arm_resolver_identity=arm_resolver_identity,
            config=config, planner_config=selected_planner,
        )
        self._bowl_reference_pose = None
        self._plate_reference_pose = None
        self._tcp_quaternion_in_bowl = None
        self.identity = solution_identity_v6(
            self.source_xml_sha256, self.source_closure_digest,
            arm_resolver_identity=self.arm_resolver_identity,
            config=self.config, planner_config=self.planner_config,
        )

    def reset(self, observation, info: Mapping[str, object], metadata, **kwargs) -> None:
        super().reset(observation, info, metadata, **kwargs)
        self._bowl_reference_pose = _body_pose(observation, "bowl_body_pose")
        self._plate_reference_pose = _body_pose(observation, "plate_body_pose")
        self._plate = self._plate_reference_pose[:3].copy()
        current_pose = np.asarray(observation["state"].get("ee_pose"), dtype=np.float64)
        if current_pose.shape != (7,) or not np.isfinite(current_pose).all():
            raise ValueError("LIBERO Solution v6 requires the public TCP world pose at reset")
        bowl_inverse = self._bowl_reference_pose[3:7].copy()
        bowl_inverse[1:] *= -1.0
        self._tcp_quaternion_in_bowl = quat_multiply_wxyz(
            bowl_inverse, normalize_quat_wxyz(current_pose[3:7]),
        )

    def _opening_for_stage(self):
        return self._opening_profile().get(self.stage)

    def _opening_profile(self):
        return _OPENING_BY_STAGE_V6

    def _bowl_local_grasp_offset_m(self):
        return _DEMO_TCP_BOWL_LOCAL_M

    def _refresh_bowl_reference_from_public_pose(self, observation) -> bool:
        if self.stage not in {"approach", "descend"}:
            return False
        current_bowl = _body_pose(observation, "bowl_body_pose")
        current_plate = _body_pose(observation, "plate_body_pose")
        previous_bowl = self._bowl_reference_pose
        previous_plate = self._plate_reference_pose
        changed = any((
            previous is None
            or float(np.linalg.norm(current[:3] - previous[:3])) > 1e-6
            or quat_angle_wxyz(current[3:7], previous[3:7]) > 1e-6
        ) for current, previous in (
            (current_bowl, previous_bowl), (current_plate, previous_plate),
        ))
        if changed:
            self._bowl_reference_pose = current_bowl
            self._plate_reference_pose = current_plate
            self._initial_bowl = current_bowl[:3].copy()
            self._plate = current_plate[:3].copy()
            self._pose_plan = None
            self._pose_plan_index = 0
            self._pose_plan_stage = None
        return changed

    def _target(self) -> np.ndarray:
        if self._bowl_reference_pose is None or self._plate_reference_pose is None:
            raise RuntimeError("LIBERO Solution v6 reset geometry is unavailable")
        bowl = self._bowl_reference_pose
        plate = self._plate_reference_pose
        bowl_quaternion = normalize_quat_wxyz(bowl[3:7])
        local_offset = self._bowl_local_grasp_offset_m()
        offset_world = rotate_vector_wxyz(bowl_quaternion, local_offset)
        self._grasp_quaternion_wxyz = quat_multiply_wxyz(
            bowl_quaternion, self._tcp_quaternion_in_bowl,
        )
        if self.stage == "approach":
            local_approach = local_offset.copy()
            local_approach[2] = 0.15
            return bowl[:3] + rotate_vector_wxyz(bowl_quaternion, local_approach)
        if self.stage in {"descend", "grasp"}:
            return bowl[:3] + offset_world
        if self.stage == "lift":
            return bowl[:3] + offset_world + np.asarray((0.0, 0.0, 0.20))
        if self.stage == "carry":
            return np.asarray((plate[0], plate[1], bowl[2] + 0.20)) + offset_world
        if self.stage in {"place", "release"}:
            return plate[:3] + np.asarray((0.0, 0.0, 0.085)) + offset_world
        raise RuntimeError(f"LIBERO Solution v6 has no target in stage {self.stage!r}")

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction:
        proposal = super().act(observation, info)
        self._last_action_receipt.update({
            "solution_schema_version": self.solution_schema_version,
            "grasp_strategy": self.grasp_strategy_id,
            "grasp_frame": {
                "bowl_local_tcp_offset_m": self._bowl_local_grasp_offset_m().tolist(),
                "offset_source": self.grasp_offset_source,
                "bowl_reference_pose_world_wxyz": self._bowl_reference_pose.tolist(),
                "plate_reference_pose_world_wxyz": self._plate_reference_pose.tolist(),
                "tcp_quaternion_in_bowl_wxyz": self._tcp_quaternion_in_bowl.tolist(),
                "dataset_revision": _DEMO_DATASET_REVISION,
                "dataset_file_sha256": _DEMO_DATASET_SHA256,
            },
            "opening_target_m": float(self._opening_for_stage()),
        })
        return ExpertAction(
            action=proposal.action, stage=proposal.stage,
            diagnostics=dict(self._last_action_receipt["diagnostics"]),
        )

    def outcome_report(self) -> dict[str, object]:
        report = super().outcome_report()
        report["solution_schema_version"] = self.solution_schema_version
        report["solution_profile"] = {
            "grasp_strategy": self.grasp_strategy_id,
            "grasp_offset_source": self.grasp_offset_source,
            "bowl_local_tcp_offset_m": self._bowl_local_grasp_offset_m().tolist(),
            "opening_by_stage_m": self._opening_profile(),
            "dataset_revision": _DEMO_DATASET_REVISION,
            "dataset_file_sha256": _DEMO_DATASET_SHA256,
        }
        return report


class LiberoPickPlaceSolutionV7(LiberoPickPlaceSolutionV6):
    """First-contact median rim pose with demo-scale closing aperture."""

    solution_schema_version = SOLUTION_SCHEMA_V7
    grasp_strategy_id = "demonstration_first_bilateral_contact_radial_rim_pinch_v1"
    grasp_offset_source = "LIBERO task-0 reconstructed first-bilateral-contact median"

    def __init__(self, source_xml: bytes | str, source_closure_digest: str, *,
                 arm_resolver_identity: str,
                 config: LiberoPickPlaceSolutionConfigV1 | None = None,
                 planner_config: CartesianPosePlannerConfig | None = None):
        super().__init__(
            source_xml, source_closure_digest,
            arm_resolver_identity=arm_resolver_identity,
            config=config, planner_config=planner_config,
        )
        self.identity = solution_identity_v7(
            self.source_xml_sha256, self.source_closure_digest,
            arm_resolver_identity=self.arm_resolver_identity,
            config=self.config, planner_config=self.planner_config,
        )

    def _opening_profile(self):
        return _OPENING_BY_STAGE_V7

    def _bowl_local_grasp_offset_m(self):
        return _DEMO_FIRST_BILATERAL_TCP_BOWL_LOCAL_M


__all__ = [
    "SOLUTION_SCHEMA", "SOLUTION_SCHEMA_V2", "SOLUTION_SCHEMA_V3", "SOLUTION_SCHEMA_V4",
    "SOLUTION_SCHEMA_V5", "SOLUTION_SCHEMA_V6", "SOLUTION_SCHEMA_V7",
    "POSE_ACTION_SCHEMA_V1",
    "LiberoPickPlaceSolutionConfigV1", "LiberoPickPlaceSolutionV1",
    "LiberoPickPlaceSolutionV2", "LiberoPickPlaceSolutionV3", "LiberoPickPlaceSolutionV4",
    "LiberoPickPlaceSolutionV5", "LiberoPickPlaceSolutionV6", "LiberoPickPlaceSolutionV7",
    "solution_identity_v1", "solution_identity_v2", "solution_identity_v2_frozen",
    "solution_identity_v3", "solution_identity_v4", "solution_identity_v5", "solution_identity_v6",
    "solution_identity_v7",
]
