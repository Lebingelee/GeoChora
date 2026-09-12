"""Joint-position actuator command backend for TaskEnv controllers."""

from __future__ import annotations

import numpy as np

from ..environment import ActionConfig, ControlCommand, RuntimeSnapshot
from ..robots.gripper import GripperTarget, PandaGripperController
from ..assembly import AgentReferences
from .contracts import ActuatorCommand, JointTarget, PoseTarget


class JointPositionServoBackend:
    """Compile a resolved arm joint target into one position-actuator command.

    The backend resolves a desired joint position to the next ``ctrl`` vector.
    It owns the small outer position-error correction shared by Cartesian IK
    and absolute-joint public actions.  Actuator stiffness and velocity damping
    remain actuator/solver responsibilities.
    """

    def __init__(
        self,
        *,
        references: AgentReferences,
        config: ActionConfig,
        gripper: PandaGripperController,
    ) -> None:
        self.references = references
        self.config = config
        self._gripper_controller = gripper

    def move_gripper_m(
        self,
        value: float = 0.0,
        force: float | None = None,
    ) -> GripperTarget:
        """Create a force-limited physical gripper request for this backend."""
        return self._gripper_controller.move_gripper_m(value=value, force=force)

    def compile(
        self,
        *,
        snapshot: RuntimeSnapshot,
        joint_target: JointTarget,
        gripper_command: float,
        gripper_target: GripperTarget | None = None,
        pose_target: PoseTarget | None = None,
    ) -> ActuatorCommand:
        if snapshot.ctrl is None or snapshot.qpos is None:
            raise ValueError("joint-position control requires snapshot ctrl and qpos")
        refs = self.references
        arm_ids = refs.arm_actuator_ids
        if joint_target.positions.shape != (arm_ids.size,):
            raise ValueError(
                "joint target size must equal the number of arm actuators: "
                f"{joint_target.positions.shape} vs {(arm_ids.size,)}"
            )
        ctrl = np.asarray(snapshot.ctrl, dtype=np.float32).copy()
        if ctrl.ndim != 1:
            raise ValueError("snapshot ctrl must be one-dimensional")
        if arm_ids.size and int(np.max(arm_ids)) >= ctrl.size:
            raise ValueError("arm actuator ids exceed snapshot ctrl size")
        if refs.gripper_actuator_ids.size and int(np.max(refs.gripper_actuator_ids)) >= ctrl.size:
            raise ValueError("gripper actuator ids exceed snapshot ctrl size")

        desired_target = np.asarray(joint_target.positions, dtype=np.float32).copy()
        limits = np.asarray(refs.ctrl_range[arm_ids], dtype=np.float32)
        limited = limits[:, 1] > limits[:, 0] + 1.0e-8
        desired_target[limited] = np.clip(
            desired_target[limited],
            limits[limited, 0],
            limits[limited, 1],
        )
        resolved_joint_target = JointTarget(
            positions=desired_target,
            provenance=joint_target.provenance,
        )
        current_positions = np.asarray(
            snapshot.qpos[refs.arm_qpos_ids], dtype=np.float32
        )
        if current_positions.shape != resolved_joint_target.positions.shape:
            raise ValueError("arm qpos ids must match arm actuator count")
        corrected_ctrl = resolved_joint_target.positions + np.float32(
            self.config.joint_position_correction_gain
        ) * (resolved_joint_target.positions - current_positions)
        corrected_ctrl[limited] = np.clip(
            corrected_ctrl[limited], limits[limited, 0], limits[limited, 1]
        )
        ctrl[arm_ids] = corrected_ctrl

        resolved_gripper_target = (
            self._gripper_controller.normalized_target(gripper_command)
            if gripper_target is None
            else gripper_target
        )
        gripper_ctrl = self._gripper_controller.ctrl_for_target(
            snapshot=snapshot,
            target=resolved_gripper_target,
        )
        ctrl[refs.gripper_actuator_ids] = np.float32(gripper_ctrl)
        return ActuatorCommand(
            actuator_ctrl=ctrl,
            control_mode="position",
            joint_target=resolved_joint_target,
            pose_target=pose_target,
        )

    @staticmethod
    def to_control_command(
        command: ActuatorCommand,
        *,
        requested_action: np.ndarray,
        external_action: np.ndarray,
        universal_action: np.ndarray,
        mode: str,
        action_clipped: bool = False,
    ) -> ControlCommand:
        """Adapt the backend command to the frozen RuntimeBoundary contract."""
        return ControlCommand(
            actuator_ctrl=command.actuator_ctrl,
            external_action=external_action,
            requested_action=requested_action,
            controller_target=command.actuator_ctrl,
            universal_action=universal_action,
            mode=mode,
            action_clipped=action_clipped,
        )


__all__ = ["JointPositionServoBackend"]
