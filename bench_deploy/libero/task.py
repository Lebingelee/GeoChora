"""Pinned task identity and source-level task semantics."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from task_env.environment.task_definition import (
    TaskDefinitionBase,
    TaskEvaluationContextV1,
    TaskPredicateEvaluationV1,
    TaskPredicateResultV1,
)
from task_env.controllers.mounted_panda_mixed import (
    MountedPandaControlMapV1,
    MountedPandaMixedActuatorAdapter,
    MountedPandaServoConfigV1,
)


PILOT_SOURCE_ID = (
    "libero-pilot-candidate:"
    "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"
)
PILOT_ACTIVE_SCENE_XML_SHA256 = (
    "bb118118e3e02a0f23295c072d77c5a7c6b44cc773032dc79c17070b4e133f86"
)


@dataclass(frozen=True)
class LiberoPilotControlHookV1(TaskDefinitionBase):
    """TaskDefinition extension candidate bound to the composed candidate MJCF.

    It is not a registered public Env or provider-admission route. Physical
    identity and unqualified gains remain explicit.
    """

    source_id: str
    source_xml_sha256: str
    agent_uid: str
    servo_config: MountedPandaServoConfigV1
    requires_contact_summary = True

    def __post_init__(self) -> None:
        if self.source_id != PILOT_SOURCE_ID:
            raise ValueError("LIBERO candidate source id differs from the frozen pilot manifest")
        if (type(self.source_xml_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self.source_xml_sha256) is None):
            raise ValueError("LIBERO candidate composed MJCF identity must be a SHA-256")
        if self.agent_uid != "libero-mounted-panda-v1":
            raise ValueError("LIBERO candidate requires the fixed MountedPanda Agent identity")

    def create_action_adapter(self, compiled_scene: Any):
        references = getattr(compiled_scene, "references", None)
        if references is None:
            raise TypeError("LIBERO candidate action hook requires compiled TaskReferences")
        mapping = MountedPandaControlMapV1.from_task_references(
            references,
            agent_uid=self.agent_uid,
            source_id=self.source_id,
            source_xml_sha256=self.source_xml_sha256,
        )
        return MountedPandaMixedActuatorAdapter(
            mapping=mapping,
            config=self.servo_config,
        )

    def evaluate_predicates(self, context: TaskEvaluationContextV1):
        if not isinstance(context, TaskEvaluationContextV1):
            raise TypeError("LIBERO pilot predicate evaluation requires TaskEvaluationContextV1")
        contact = context.state.contact_summary
        reason = (
            contact.reason
            if contact is not None and contact.status == "unavailable"
            else "public_object_pose_mapping_unavailable"
        )
        return TaskPredicateEvaluationV1.available({
            "on_bowl_plate": TaskPredicateResultV1.unavailable(reason)
        })


def build_task(manifest: dict) -> dict:
    task = manifest["task"]
    predicate = next(
        (row for row in manifest["source_code_references"]
         if row["repository"] == "libero" and row["path"] == "libero/libero/envs/predicates/base_predicates.py"),
        None,
    )
    if predicate is None:
        raise ValueError("pinned LIBERO predicate implementation reference is missing")
    return {
        "uid": task["task_uid"],
        "suite": task["suite"],
        "native_filename": task["native_filename"],
        "language": task["language"],
        "bddl": task["bddl"],
        "objects": task["objects_instance_to_type"],
        "fixtures": task["fixtures_instance_to_type"],
        "native_goal_semantics": {
            "expression": task["bddl"]["goal_expression"],
            "predicate_source": predicate,
            "required_meaning": "object-object On requires geom-group contact, vertical ordering, and strict XY body-centre distance < 0.03 m",
            "core_evaluator_status": "NOT_ADMITTED",
        },
        "native_initialization": {
            "selected_source": task["selected_pruned_init"],
            "loader_policy": "Pinned LIBERO loader selects this .pruned_init; this package verifies and copies bytes only.",
            "unpickle_or_torch_load": False,
            "reset_realization": "NOT_RUN",
            "flat_state_order": "UNKNOWN_NOT_INFERRED",
        },
    }
