"""Absolute Panda joint-position target action adapter."""

from __future__ import annotations

import numpy as np
from gymnasium.spaces import Box

from ..environment import ActionConfig, ControlCommand, RuntimeSnapshot
from ..robots.gripper import PandaGripperController
from ..assembly import AgentReferences
from .contracts import JointTarget
from .joint_position import JointPositionServoBackend


class AbsoluteJointPositionActionAdapter:
    """Translate one 8D absolute joint target into one position-servo command.

    Public action layout is ``[q1, ..., q7, gripper]``.  The first seven values
    are desired absolute arm joint coordinates; the final normalized scalar is
    independently mapped to the gripper actuator command.
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
        self._joint_backend = JointPositionServoBackend(
            references=references,
            config=config,
            gripper=gripper,
        )
        low = np.concatenate(
            [
                np.full(7, -np.inf, dtype=np.float32),
                np.array([-1.0], dtype=np.float32),
            ]
        )
        high = np.concatenate(
            [
                np.full(7, np.inf, dtype=np.float32),
                np.array([1.0], dtype=np.float32),
            ]
        )
        self._action_space = Box(low=low, high=high, dtype=np.float32)

    @property
    def action_space(self) -> Box:
        return self._action_space

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        self._validate_snapshot(snapshot)

    @staticmethod
    def _validate_snapshot(snapshot: RuntimeSnapshot) -> None:
        if snapshot.ctrl is None or snapshot.qpos is None:
            raise ValueError("absolute-joint control requires snapshot ctrl and qpos")

    def convert(
        self,
        action: np.ndarray,
        snapshot: RuntimeSnapshot,
    ) -> ControlCommand:
        self._validate_snapshot(snapshot)
        requested = np.asarray(action, dtype=np.float32).reshape(-1).copy()
        if requested.shape != (8,):
            raise ValueError(f"action shape must be {(8,)}, got {requested.shape}")
        if not np.isfinite(requested).all():
            raise ValueError("action must contain only finite values")
        interpreted = requested.copy()
        interpreted[7] = np.float32(np.clip(interpreted[7], -1.0, 1.0))
        command = self._joint_backend.compile(
            snapshot=snapshot,
            joint_target=JointTarget(
                positions=interpreted[:7],
                provenance="absolute",
            ),
            gripper_command=float(interpreted[7]),
        )
        return self._joint_backend.to_control_command(
            command,
            requested_action=requested,
            external_action=interpreted,
            universal_action=command.joint_target.positions.tolist() + [float(interpreted[7])],
            mode="absolute_joint",
            action_clipped=not np.array_equal(requested, interpreted),
        )


__all__ = ["AbsoluteJointPositionActionAdapter"]
