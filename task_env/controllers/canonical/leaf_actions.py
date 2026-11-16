"""Typed leaf action sets consumed by the selected control route."""
from dataclasses import dataclass

from .contracts import ControlGroupActionV1, StructuredActionRequestV1
from .leaf_profiles import (
    ARM_POSITION_ACTION_SCHEMA, HAND_POSITION_ACTION_SCHEMA,
    ArmPositionActionV1, HandPositionActionV1,
)

ARM_WRITER_ID = "panda-arm/arm-position-leaf"
HAND_WRITER_ID = "panda-hand/hand-position-leaf"
MAIN_ARM_WRITER_ID = "panda-main/arm-position-leaf"
MAIN_HAND_WRITER_ID = "panda-main/hand-position-leaf"


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


@dataclass(frozen=True)
class AttachedLeafActionSetV1:
    schema_version: str
    scene_identity_sha256: str
    plan_identity_sha256: str
    arm: ArmPositionActionV1
    hand: HandPositionActionV1

    def __post_init__(self):
        if self.schema_version != "r03c-attached-leaf-action-set-v1":
            raise ValueError("unsupported R03c attached leaf action-set schema")
        if type(self.arm) is not ArmPositionActionV1 or type(self.hand) is not HandPositionActionV1:
            raise TypeError("R03c action-set requires typed Arm and Hand values")
        self.arm.validate(); self.hand.validate()
        for value in (self.scene_identity_sha256, self.plan_identity_sha256):
            if type(value) is not str or len(value) != 64:
                raise ValueError("R03c action-set requires SHA-256 Scene and plan identities")

    def structured_request(self, scene, plan):
        if (scene.identity_hash, plan.identity_sha256) != (
                self.scene_identity_sha256, self.plan_identity_sha256):
            raise ValueError("R03c action-set belongs to another Scene/effective plan")
        actions = {
            ARM_WRITER_ID: (self.arm, tuple(self.arm.position_rad)),
            HAND_WRITER_ID: (self.hand, (float(self.hand.opening_m),)),
        }
        groups = []
        for entry in plan.leaves:
            typed, values = actions[entry.binding.writer_id]
            groups.append(ControlGroupActionV1(
                "control-group-action-v1", entry.binding.entity_id,
                entry.binding.control_group_id, entry.binding.action_schema_id, values,
            ))
        request = StructuredActionRequestV1(
            "structured-action-request-v1", scene.identity_hash,
            plan.identity_sha256, tuple(sorted(groups, key=lambda item: (item.entity_id, item.group_id))),
        )
        request.validate()
        return request
