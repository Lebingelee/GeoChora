"""Stage 10 physical delta EE-pose controller with explicit frame composition."""

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
    matrix_to_rotvec,
    quat_wxyz_to_matrix,
    rotation_vector_error,
    rotvec_to_matrix,
)
from .contracts import JointTarget, PoseTarget
from .joint_position import JointPositionServoBackend


class DeltaPoseActionController:
    """Resolve one physical delta against the current achieved EE snapshot.

    This controller does not retain an EE target between calls.  Each action is
    composed from the same pre-action ``RuntimeSnapshot`` later used for the
    IK solve, which prevents controller-target drift from changing delta
    semantics.
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
        if controller_config.kind != "delta_pose":
            raise ValueError("DeltaPoseActionController requires delta_pose config")
        if action_spec.controller_kind != "delta_pose":
            raise ValueError("DeltaPoseActionController requires delta_pose ActionModeSpec")
        self.references = references
        self.config = config
        self.controller_config = controller_config
        self.action_spec = action_spec
        self._joint_backend = JointPositionServoBackend(
            references=references,
            config=config,
            gripper=gripper,
        )
        self._resolved_pose_target: PoseTarget | None = None
        self._arm_target: np.ndarray | None = None
        self._last_world_pose_target: np.ndarray | None = None
        self._last_position_error_norm: float | None = None
        self._last_gripper_command: float | None = None
        self._gripper_hold_pose_target: np.ndarray | None = None
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
        return self._resolved_pose_target

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        self._validate_snapshot(snapshot)
        self._resolved_pose_target = None
        self._arm_target = np.asarray(
            snapshot.ctrl[self.references.arm_actuator_ids], dtype=np.float64
        ).copy()
        self._last_world_pose_target = None
        self._last_position_error_norm = None
        self._last_gripper_command = None
        self._gripper_hold_pose_target = None

    def _validate_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        if (
            snapshot.ctrl is None
            or snapshot.qpos is None
            or snapshot.site_xpos is None
            or snapshot.site_xquat is None
            or snapshot.site_jacp is None
            or snapshot.site_jacr is None
        ):
            raise ValueError("delta-pose control requires ctrl, qpos, site pose, and Jacobians")
        if self.controller_config.reference == "base" and (
            snapshot.body_xpos is None or snapshot.body_xquat is None
        ):
            raise ValueError("delta_pose(base) requires base body pose in snapshot")

    def _decode_delta(self, action: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
        requested = np.asarray(action, dtype=np.float32).reshape(-1).copy()
        if requested.shape != (self.action_spec.dimension,):
            raise ValueError(
                f"action shape must be {(self.action_spec.dimension,)}, got {requested.shape}"
            )
        if not np.isfinite(requested).all():
            raise ValueError("action must contain only finite values")
        interpreted = requested.copy()
        maximum_translation = float(self.controller_config.max_translation_delta_m)
        interpreted[:3] = np.clip(interpreted[:3], -maximum_translation, maximum_translation)
        if self.controller_config.rotation_representation == "quaternion_wxyz":
            quaternion = np.asarray(interpreted[3:7], dtype=np.float64)
            norm = float(np.linalg.norm(quaternion))
            if norm <= 1.0e-8:
                raise ValueError("delta_pose quaternion cannot be zero")
            delta_rotation = quat_wxyz_to_matrix(quaternion)
            rotvec = matrix_to_rotvec(delta_rotation)
            angle = float(np.linalg.norm(rotvec))
            maximum_rotation = float(self.controller_config.max_rotation_delta_rad)
            if angle > maximum_rotation:
                rotvec *= maximum_rotation / angle
                delta_rotation = rotvec_to_matrix(rotvec)
                interpreted[3:7] = matrix_to_quat_wxyz(delta_rotation).astype(np.float32)
            else:
                interpreted[3:7] = (quaternion / norm).astype(np.float32)
        else:
            rotvec = np.asarray(interpreted[3:6], dtype=np.float64)
            angle = float(np.linalg.norm(rotvec))
            maximum_rotation = float(self.controller_config.max_rotation_delta_rad)
            if angle > maximum_rotation:
                interpreted[3:6] = (rotvec * (maximum_rotation / angle)).astype(np.float32)
            delta_rotation = rotvec_to_matrix(interpreted[3:6])
        interpreted[-1] = np.float32(np.clip(float(interpreted[-1]), -1.0, 1.0))
        return requested, interpreted, delta_rotation, not np.array_equal(requested, interpreted)

    def _compose_world_target(
        self,
        *,
        translation: np.ndarray,
        delta_rotation: np.ndarray,
        snapshot: RuntimeSnapshot,
    ) -> tuple[np.ndarray, np.ndarray]:
        site_id = int(self.references.eef_site_id)
        current_position = np.asarray(snapshot.site_xpos[site_id], dtype=np.float64)
        current_rotation = quat_wxyz_to_matrix(snapshot.site_xquat[site_id])
        reference = self.controller_config.reference
        if reference == "world":
            # ΔT_world · T_WE: left multiplication in world coordinates.
            return translation + delta_rotation @ current_position, delta_rotation @ current_rotation
        if reference == "ee":
            # T_WE · ΔT_ee: right multiplication in the achieved EE frame.
            return current_position + current_rotation @ translation, current_rotation @ delta_rotation
        base_id = int(self.references.base_body_id)
        base_position = np.asarray(snapshot.body_xpos[base_id], dtype=np.float64)
        base_rotation = quat_wxyz_to_matrix(snapshot.body_xquat[base_id])
        world_delta_rotation = base_rotation @ delta_rotation @ base_rotation.T
        world_delta_translation = base_position + base_rotation @ translation
        # T_WB · ΔT_base · inv(T_WB) · T_WE.
        return (
            world_delta_translation + world_delta_rotation @ (current_position - base_position),
            world_delta_rotation @ current_rotation,
        )

    def convert(self, action: np.ndarray, snapshot: RuntimeSnapshot) -> ControlCommand:
        self._validate_snapshot(snapshot)
        requested, interpreted, delta_rotation, action_clipped = self._decode_delta(action)
        target_position, target_rotation = self._compose_world_target(
            translation=np.asarray(interpreted[:3], dtype=np.float64),
            delta_rotation=delta_rotation,
            snapshot=snapshot,
        )
        target_quaternion = matrix_to_quat_wxyz(target_rotation).astype(np.float32)
        world_pose_target = np.concatenate([target_position, target_quaternion])
        pose_target = PoseTarget(
            position=target_position,
            quaternion_wxyz=target_quaternion,
            provenance="delta_from_achieved",
        )

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
            and position_error_norm > self._last_position_error_norm + float(cfg.cartesian_error_growth_margin)
        )
        if self._arm_target is None:
            self._arm_target = np.asarray(
                snapshot.ctrl[refs.arm_actuator_ids], dtype=np.float64
            ).copy()
        if gripper_hold_active or (settled and not error_grew):
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
            arm_target = self._arm_target + cfg.ik_position_gain * delta_q
        actuator_command = self._joint_backend.compile(
            snapshot=snapshot,
            joint_target=JointTarget(positions=arm_target, provenance="delta_from_achieved"),
            pose_target=pose_target,
            gripper_command=float(interpreted[-1]),
        )
        self._resolved_pose_target = pose_target
        # 将 IK 目标跨 tick 累积，保持 source absolute pose 与 delta replay
        # 在同一 public control tick 上的驱动强度一致；frame 组合本身仍以
        # 当前 achieved snapshot 为唯一起点。
        self._arm_target = np.asarray(arm_target, dtype=np.float64).copy()
        self._last_world_pose_target = world_pose_target.copy()
        self._last_position_error_norm = position_error_norm
        self._last_gripper_command = float(interpreted[-1])
        # Preserve the corrected actuator command emitted by the shared joint
        # servo backend.  Replacing it with the raw joint target would make
        # delta-pose replay physically diverge from absolute-pose source
        # trajectories even when universal_action matches exactly.
        controller_target = np.asarray(actuator_command.actuator_ctrl, dtype=np.float32).copy()
        return ControlCommand(
            actuator_ctrl=controller_target,
            external_action=interpreted,
            requested_action=requested,
            controller_target=controller_target,
            universal_action=np.concatenate([actuator_command.joint_target.positions, interpreted[-1:]]),
            mode="delta_pose",
            action_clipped=bool(action_clipped),
        )


__all__ = ["DeltaPoseActionController"]
