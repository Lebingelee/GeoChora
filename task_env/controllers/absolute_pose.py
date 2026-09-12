"""Stage 10 absolute EE-pose controller with explicit world/base references."""

from __future__ import annotations

import numpy as np
from gymnasium.spaces import Box

from ..assembly import AgentReferences
from ..environment import (
    ActionConfig,
    ActionModeSpec,
    ControlCommand,
    RobotControllerConfig,
    RuntimeSnapshot,
)
from ..robots.gripper import PandaGripperController
from ..utils.rotation import (
    matrix_to_quat_wxyz,
    quat_wxyz_to_matrix,
    rotation_vector_error,
    rotvec_to_matrix,
)
from .contracts import JointTarget, PoseTarget
from .joint_position import JointPositionServoBackend


class AbsolutePoseActionAdapter:
    """Convert one absolute EE pose in world/base coordinates into actuator ctrl.

    The public target is decoded only once.  IK always sees the resulting world
    EE target, and the backend still receives one resolved joint position target
    for the following ``env.step`` tick.
    """

    def __init__(
        self,
        *,
        references: AgentReferences,
        config: ActionConfig,
        controller_config: RobotControllerConfig,
        action_spec: ActionModeSpec,
        gripper: PandaGripperController,
    ) -> None:
        if controller_config.kind != "absolute_pose":
            raise ValueError("AbsolutePoseActionAdapter requires absolute_pose config")
        if action_spec.controller_kind != "absolute_pose":
            raise ValueError("AbsolutePoseActionAdapter requires absolute_pose ActionModeSpec")
        self.references = references
        self.config = config
        self.controller_config = controller_config
        self.action_spec = action_spec
        self._joint_backend = JointPositionServoBackend(
            references=references,
            config=config,
            gripper=gripper,
        )
        self._arm_target: np.ndarray | None = None
        self._last_world_pose_target: np.ndarray | None = None
        self._last_position_error_norm: float | None = None
        self._last_gripper_command: float | None = None
        self._gripper_hold_pose_target: np.ndarray | None = None
        self._resolved_pose_target: PoseTarget | None = None
        self._action_space = Box(
            low=np.asarray(action_spec.low, dtype=np.float32),
            high=np.asarray(action_spec.high, dtype=np.float32),
            dtype=np.float32,
        )

    @property
    def action_space(self) -> Box:
        return self._action_space

    @property
    def resolved_pose_target(self) -> PoseTarget | None:
        """Latest decoded world EE target; useful for public diagnostics only."""

        return self._resolved_pose_target

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        self._validate_snapshot(snapshot)
        self._arm_target = np.asarray(
            snapshot.ctrl[self.references.arm_actuator_ids], dtype=np.float64
        ).copy()
        self._last_world_pose_target = None
        self._last_position_error_norm = None
        self._last_gripper_command = None
        self._gripper_hold_pose_target = None
        self._resolved_pose_target = None

    def _validate_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        if (
            snapshot.ctrl is None
            or snapshot.site_xpos is None
            or snapshot.site_xquat is None
            or snapshot.site_jacp is None
            or snapshot.site_jacr is None
        ):
            raise ValueError("absolute-pose control requires ctrl, site pose, and Jacobians")
        if self.controller_config.reference == "base" and (
            snapshot.body_xpos is None or snapshot.body_xquat is None
        ):
            raise ValueError("absolute_pose(base) requires base body pose in snapshot")

    def _decode_world_target(self, action: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
        requested = np.asarray(action, dtype=np.float32).reshape(-1).copy()
        if requested.shape != (self.action_spec.dimension,):
            raise ValueError(
                f"action shape must be {(self.action_spec.dimension,)}, got {requested.shape}"
            )
        if not np.isfinite(requested).all():
            raise ValueError("action must contain only finite values")
        interpreted = requested.copy()
        if self.controller_config.rotation_representation == "quaternion_wxyz":
            quaternion = np.asarray(interpreted[3:7], dtype=np.float64)
            norm = float(np.linalg.norm(quaternion))
            if norm <= 1.0e-8:
                raise ValueError("absolute_pose quaternion cannot be zero")
            interpreted[3:7] = (quaternion / norm).astype(np.float32)
            action_rotation = quat_wxyz_to_matrix(interpreted[3:7])
        else:
            rotvec = np.asarray(interpreted[3:6], dtype=np.float64)
            angle = float(np.linalg.norm(rotvec))
            maximum = float(self.controller_config.max_absolute_rotvec_angle_rad)
            if angle > maximum:
                interpreted[3:6] = (rotvec * (maximum / angle)).astype(np.float32)
            action_rotation = rotvec_to_matrix(interpreted[3:6])
        interpreted[-1] = np.float32(np.clip(float(interpreted[-1]), -1.0, 1.0))
        clipped = not np.array_equal(requested, interpreted)
        return requested, interpreted, clipped

    def _world_pose_from_action(self, interpreted: np.ndarray, snapshot: RuntimeSnapshot) -> tuple[np.ndarray, np.ndarray]:
        if self.controller_config.rotation_representation == "quaternion_wxyz":
            action_rotation = quat_wxyz_to_matrix(interpreted[3:7])
        else:
            action_rotation = rotvec_to_matrix(interpreted[3:6])
        position = np.asarray(interpreted[:3], dtype=np.float64)
        if self.controller_config.reference == "world":
            return position, action_rotation
        base_id = int(self.references.base_body_id)
        base_position = np.asarray(snapshot.body_xpos[base_id], dtype=np.float64)
        base_rotation = quat_wxyz_to_matrix(snapshot.body_xquat[base_id])
        return base_position + base_rotation @ position, base_rotation @ action_rotation

    def convert(self, action: np.ndarray, snapshot: RuntimeSnapshot) -> ControlCommand:
        self._validate_snapshot(snapshot)
        requested, interpreted, action_clipped = self._decode_world_target(action)
        target_position, target_rotation = self._world_pose_from_action(interpreted, snapshot)
        target_quaternion = matrix_to_quat_wxyz(target_rotation).astype(np.float32)
        world_pose_target = np.concatenate([target_position, target_quaternion])

        refs = self.references
        cfg = self.config
        site_id = int(refs.eef_site_id)
        current_position = np.asarray(snapshot.site_xpos[site_id], dtype=np.float64)
        current_rotation = quat_wxyz_to_matrix(snapshot.site_xquat[site_id])
        jacp = np.asarray(snapshot.site_jacp[site_id, refs.arm_dof_ids], dtype=np.float64).T
        jacr = np.asarray(snapshot.site_jacr[site_id, refs.arm_dof_ids], dtype=np.float64).T
        position_error = target_position - current_position
        rotation_error = rotation_vector_error(current_rotation, target_rotation)
        position_error_norm = float(np.linalg.norm(position_error))
        rotation_error_norm = float(np.linalg.norm(rotation_error))
        settled = (
            position_error_norm <= float(cfg.ik_position_deadband)
            and rotation_error_norm <= float(cfg.ik_rotation_deadband)
        )
        repeated_target = (
            self._last_world_pose_target is not None
            and float(np.linalg.norm(world_pose_target - self._last_world_pose_target)) <= 1.0e-5
        )
        gripper_changed = (
            self._last_gripper_command is not None
            and abs(float(interpreted[-1]) - self._last_gripper_command) > 1.0e-5
        )
        if self._gripper_hold_pose_target is not None and float(
            np.linalg.norm(world_pose_target - self._gripper_hold_pose_target)
        ) > 1.0e-5:
            self._gripper_hold_pose_target = None
        if repeated_target and gripper_changed and self._arm_target is not None:
            self._gripper_hold_pose_target = world_pose_target.copy()
        gripper_hold_active = (
            self._gripper_hold_pose_target is not None
            and float(np.linalg.norm(world_pose_target - self._gripper_hold_pose_target)) <= 1.0e-5
        )
        error_grew = (
            repeated_target
            and self._last_position_error_norm is not None
            and position_error_norm
            > self._last_position_error_norm + float(cfg.cartesian_error_growth_margin)
        )
        if gripper_hold_active and self._arm_target is not None:
            arm_target = self._arm_target.copy()
        elif settled and not error_grew and self._arm_target is not None:
            arm_target = self._arm_target.copy()
        else:
            if position_error_norm > float(cfg.cartesian_max_position_step):
                position_error *= float(cfg.cartesian_max_position_step) / position_error_norm
            if rotation_error_norm > float(cfg.cartesian_max_rotation_step):
                rotation_error *= float(cfg.cartesian_max_rotation_step) / rotation_error_norm
            jacobian = np.vstack([jacp, cfg.ik_rotation_row_weight * jacr])
            error = np.concatenate(
                [
                    position_error,
                    cfg.ik_rotation_row_weight * cfg.ik_rotation_gain * rotation_error,
                ]
            )
            system = jacobian @ jacobian.T + (cfg.ik_damping * cfg.ik_damping) * np.eye(6, dtype=np.float64)
            delta_q = jacobian.T @ np.linalg.solve(system, error)
            delta_q = np.clip(delta_q, -cfg.ik_max_delta_q, cfg.ik_max_delta_q)
            if self._arm_target is None:
                self._arm_target = np.asarray(snapshot.ctrl[refs.arm_actuator_ids], dtype=np.float64).copy()
            arm_target = self._arm_target + cfg.ik_position_gain * delta_q

        pose_target = PoseTarget(
            position=target_position,
            quaternion_wxyz=target_quaternion,
            provenance="absolute",
        )
        actuator_command = self._joint_backend.compile(
            snapshot=snapshot,
            joint_target=JointTarget(positions=arm_target, provenance="ik_solution"),
            pose_target=pose_target,
            gripper_command=float(interpreted[-1]),
        )
        self._arm_target = np.asarray(arm_target, dtype=np.float64).copy()
        self._last_world_pose_target = world_pose_target.copy()
        self._last_position_error_norm = position_error_norm
        self._last_gripper_command = float(interpreted[-1])
        self._resolved_pose_target = pose_target
        return self._joint_backend.to_control_command(
            actuator_command,
            requested_action=requested,
            external_action=interpreted,
            universal_action=np.concatenate([actuator_command.joint_target.positions, interpreted[-1:]]),
            mode="absolute_pose",
            action_clipped=bool(action_clipped),
        )


__all__ = [
    "AbsolutePoseActionAdapter",
    "matrix_to_quat_wxyz",
    "quat_wxyz_to_matrix",
    "rotvec_to_matrix",
]
