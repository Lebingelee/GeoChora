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
    references: AgentReferences | None = None
    controller: object | None = None
    gripper: PandaGripperController | None = None
    base: object | None = None
    ee: RobotFrameReference | None = None
    world: RobotFrameReference | None = None
    subjects: tuple = ()
    controllers: tuple = ()

    @classmethod
    def from_selected(cls, value, selected):
        """Expose the admitted subjects and their actual Controller owners.

        No native resource, state copy, or Controller is created by this view.
        Component-only Panda conveniences remain optional capabilities.
        """
        source = value['source']
        physical = selected.physical_execution or value.get('physical_execution')
        if physical is not None:
            subjects, controllers = physical.subjects, physical.controllers
        else:
            binding = getattr(source, 'position_subject_binding', None)
            subjects = () if binding is None else binding.subjects
            declare = getattr(selected.controller, 'position_binding_requirements', None)
            controllers = (tuple(row[0] for row in declare()) if callable(declare)
                           else (selected.controller,))
        if not subjects:
            return None
        roots = tuple(subject for subject in subjects if subject.parent_subject_id is None)
        request = getattr(source, 'source_composition_request', None)
        uid = request.robot_uid if request is not None else subjects[0].entity_id
        return cls(uid=uid, controller=selected.controller, subjects=subjects,
                   controllers=controllers, base=roots[0].root_frame if len(roots) == 1 else None,
                   world=RobotFrameReference('world', 'world', None, 'world'))

    @property
    def root_frames(self):
        """Source-owned root Frames, retaining nested subject identities."""
        return tuple(subject.root_frame for subject in self.subjects)

    @property
    def arm_joint_order(self) -> tuple[str, ...]:
        if self.references is None:
            raise AttributeError('this Robot does not declare a legacy arm joint projection')
        return self.references.arm_joint_names


__all__ = ["RobotControllerHandle", "RobotFrameReference", "RobotRuntime"]
