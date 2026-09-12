"""Resolved robot-facing handles owned by a built TaskEnv runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..assembly import AgentReferences
from ..environment import ActionModeSpec, RuntimeSnapshot
from .gripper import PandaGripperController


@dataclass(frozen=True)
class RobotFrameReference:
    """A declared robot reference resolved against the compiled scene."""

    name: str
    frame_type: str
    index: int | None
    source_name: str

    def __post_init__(self) -> None:
        if self.name not in {"world", "base", "ee"}:
            raise ValueError("robot frame name must be world, base, or ee")
        if self.frame_type not in {"world", "body", "site"}:
            raise ValueError("robot frame type must be world, body, or site")
        if self.frame_type == "world" and self.index is not None:
            raise ValueError("world reference cannot have a compiled index")
        if self.frame_type != "world" and (self.index is None or self.index < 0):
            raise ValueError("body/site reference requires a non-negative compiled index")


class RobotControllerHandle:
    """The robot-owned public controller facade.

    Stage 10b delegates to the already-verified adapters while making ownership
    explicit.  Stage 10c/10d replace the legacy adapter implementations without
    changing this ``env.robot.controller`` boundary.
    """

    def __init__(
        self,
        *,
        adapter: Any,
        kind: str,
        reference: str | None,
        action_spec: ActionModeSpec | None,
    ) -> None:
        self._adapter = adapter
        self.kind = str(kind)
        self.reference = reference
        self.action_spec = action_spec
        self.rotation_representation = (
            None if action_spec is None else action_spec.rotation_representation
        )

    @property
    def action_space(self):
        return self._adapter.action_space

    @property
    def resolved_pose_target(self):
        """Latest world pose target when the selected controller resolves one."""

        return getattr(self._adapter, "resolved_pose_target", None)

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        self._adapter.reset(snapshot)

    def convert(self, action, snapshot: RuntimeSnapshot):
        return self._adapter.convert(action, snapshot)


@dataclass(frozen=True)
class RobotRuntime:
    """Single robot runtime view exposed as ``env.robot``."""

    uid: str
    references: AgentReferences
    controller: RobotControllerHandle
    gripper: PandaGripperController
    base: RobotFrameReference
    ee: RobotFrameReference
    world: RobotFrameReference

    @property
    def arm_joint_order(self) -> tuple[str, ...]:
        return self.references.arm_joint_names


__all__ = ["RobotControllerHandle", "RobotFrameReference", "RobotRuntime"]
