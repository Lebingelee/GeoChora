"""Pinned task predicate facts and provider-free candidate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any

import numpy as np

from task_env.environment import (
    TaskEvaluationContextV1,
    TaskPredicateEvaluationV1,
    TaskPredicateResultV1,
)


PILOT_TASK_UID = (
    "libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_"
    "and_place_it_on_the_plate"
)
ON_THRESHOLD_M = 0.03


def _position(value: Any, name: str) -> tuple[float, float, float] | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a finite world position with shape (3,)")
    return tuple(float(item) for item in array)


@dataclass(frozen=True)
class OnBowlPlateEvidenceV1:
    """Explicit synthetic/public evidence consumed by the pinned ``On`` rule.

    ``contact`` must be a public geom-group contact result. ``None`` means the
    provider did not publish it; it is never coerced to false. Positions are
    body centers in the named frame and SI meters.
    """

    task_uid: str
    source_manifest_sha256: str
    frame_id: str
    bowl_center_m: tuple[float, float, float] | None
    plate_center_m: tuple[float, float, float] | None
    geom_group_contact: bool | None
    schema_version: str = "libero-on-bowl-plate-evidence-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "libero-on-bowl-plate-evidence-v1":
            raise ValueError("unsupported LIBERO On evidence schema")
        if self.task_uid != PILOT_TASK_UID:
            raise ValueError("On evidence task identity differs from the fixed pilot")
        if (type(self.source_manifest_sha256) is not str
                or len(self.source_manifest_sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.source_manifest_sha256)):
            raise ValueError("On evidence requires a source-manifest SHA-256")
        if type(self.frame_id) is not str or not self.frame_id:
            raise ValueError("On evidence requires an explicit coordinate frame")
        if self.geom_group_contact is not None and type(self.geom_group_contact) is not bool:
            raise TypeError("geom_group_contact must be bool or None")
        object.__setattr__(self, "bowl_center_m", _position(self.bowl_center_m, "bowl_center_m"))
        object.__setattr__(self, "plate_center_m", _position(self.plate_center_m, "plate_center_m"))


def evaluate_on_bowl_plate_v1(
    evidence: OnBowlPlateEvidenceV1 | None,
    *,
    expected_source_manifest_sha256: str,
) -> TaskPredicateResultV1:
    """Evaluate the fixed source semantics without inventing missing evidence."""

    if evidence is None:
        return TaskPredicateResultV1.unavailable("public_on_evidence_unavailable")
    if not isinstance(evidence, OnBowlPlateEvidenceV1):
        raise TypeError("On evaluator requires OnBowlPlateEvidenceV1")
    if evidence.source_manifest_sha256 != expected_source_manifest_sha256:
        return TaskPredicateResultV1.unavailable("source_manifest_identity_mismatch")
    if evidence.frame_id != "world":
        return TaskPredicateResultV1.unavailable("body_center_frame_mismatch")
    if evidence.geom_group_contact is None:
        return TaskPredicateResultV1.unavailable("geom_group_contact_unavailable")
    if not evidence.geom_group_contact:
        return TaskPredicateResultV1.available(False)
    if evidence.bowl_center_m is None or evidence.plate_center_m is None:
        return TaskPredicateResultV1.unavailable("body_center_pose_unavailable")
    bowl = evidence.bowl_center_m
    plate = evidence.plate_center_m
    if bowl[2] < plate[2]:
        return TaskPredicateResultV1.available(False)
    xy_distance = math.hypot(bowl[0] - plate[0], bowl[1] - plate[1])
    return TaskPredicateResultV1.available(xy_distance < ON_THRESHOLD_M)


def build_evaluation(task_input: dict, manifest: dict) -> dict:
    semantics = task_input["semantics"]
    return {
        "source_goal": manifest["task"]["bddl"]["goal_expression"],
        "native_predicate_owner": "LIBERO object state and predicate sources",
        "required_contact": semantics["contact_evidence"],
        "required_xy_threshold_m": semantics["goal_threshold_m"],
        "required_evidence": semantics["required_evidence"],
        "unavailable_is_not_false": semantics["unavailable_is_not_false"],
        "core_evaluator_owner": "task_env/environment/task_definition.py::TaskDefinitionBase.evaluate_predicates",
        "candidate_evaluator": "evaluate_on_bowl_plate_v1",
        "candidate_evaluator_scope": "provider-free explicit-evidence fixture only; no current Core public contact publisher is connected",
        "status": "NOT_ADMITTED_CONTACT_PUBLICATION_UNAVAILABLE",
    }


__all__ = [
    "ON_THRESHOLD_M",
    "PILOT_TASK_UID",
    "OnBowlPlateEvidenceV1",
    "build_evaluation",
    "evaluate_on_bowl_plate_v1",
]
