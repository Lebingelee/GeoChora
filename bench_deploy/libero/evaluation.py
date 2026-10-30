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
from task_env.environment.types import TaskEvaluation
from task_env.controllers.canonical.contracts import digest


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


def observe_selected_reference_v1(env, state):
    """Build this task's observation and predicate from public runtime values."""
    source = env.value['source']
    pair = ('akita_black_bowl_1', 'plate_1')
    contact = env.session.read_contact_summary_v2((pair,))
    requested = (pair,)
    if contact.status == 'available' and (
            contact.requested_pairs != requested or contact.covered_pairs != requested):
        predicate = TaskPredicateResultV1.unavailable('contact_query_coverage_mismatch')
    elif contact.status == 'unavailable':
        predicate = TaskPredicateResultV1.unavailable(contact.reason or 'contact_unavailable')
    else:
        count = contact.pair_counts.get('akita_black_bowl_1/plate_1')
        if type(count) is not int or count < 0:
            raise ValueError('contact summary omitted the exact covered pair count')
        evidence = OnBowlPlateEvidenceV1(
            task_uid=env.artifact.task_id,
            source_manifest_sha256=env.value['source_manifest_sha256'],
            frame_id='world',
            bowl_center_m=tuple(state.pose_world['akita_black_bowl_1'].position),
            plate_center_m=tuple(state.pose_world['plate_1'].position),
            geom_group_contact=bool(count),
        )
        predicate = env.binding.evaluate(evidence, env.artifact.semantics)
    if not isinstance(predicate, TaskPredicateResultV1):
        raise TypeError('task observation callback must return TaskPredicateResultV1')
    success = bool(predicate.value) if predicate.status == 'available' else False
    evaluation = TaskEvaluation(
        reward=1.0 if success else 0.0, success=success,
        metrics={'on_bowl_plate_available': predicate.status == 'available',
                 'on_bowl_plate': success},
    )
    boundary_identity = {
        'source_id': source.scene_source.source_id,
        'source_closure_digest': source.source_closure_digest,
        'provider_materialization_id': env.session.provider_materialization_id,
        'episode_id': env.session.episode_id,
        'reset_sample_id': env.sample.sample_id,
        'control_step': int(state.control_step),
        'state_revision': int(env.session.state_revision),
        'simulation_time_s': float(state.simulation_time),
    }
    boundary_digest = digest(boundary_identity)
    ee = state.pose_world['panda-v1/ee']
    obs = {
        'state': {
            'ee_pose': np.asarray((*ee.position, *ee.quaternion_wxyz), dtype=np.float32),
            'joint_position': np.asarray(
                [state.joint_position[f'joint{i}'] for i in range(1, 8)]
                + [state.joint_position['finger_joint1'], state.joint_position['finger_joint2']],
                dtype=np.float32,
            ),
            'boundary_identity_sha256': np.frombuffer(bytes.fromhex(boundary_digest), dtype=np.uint8).copy(),
        },
        'privileged_state': {
            key + '_body_pose': np.asarray(
                [(*state.pose_world[semantic].position, *state.pose_world[semantic].quaternion_wxyz)],
                dtype=np.float32,
            ) for semantic, key in env.binding.object_poses
        },
    }
    contact_mapping = {
        'schema_version': contact.schema_version,
        'source_id': contact.source_id,
        'source_closure_digest': contact.source_closure_digest,
        'provider_materialization_id': contact.provider_materialization_id,
        'episode_id': contact.episode_id,
        'reset_sample_id': contact.reset_sample_id,
        'control_step': contact.control_step,
        'state_revision': contact.state_revision,
        'simulation_time_s': contact.simulation_time_s,
        'requested_pairs': [list(item) for item in contact.requested_pairs],
        'covered_pairs': [list(item) for item in contact.covered_pairs],
        'pair_counts': dict(contact.pair_counts),
        'geom_groups': {key: list(value) for key, value in contact.geom_groups.items()},
        'status': contact.status, 'reason': contact.reason,
    }
    predicate_mapping = {
        'status': predicate.status, 'value': predicate.value, 'reason': predicate.reason,
    }
    info = {
        'is_success': success, 'task_failure': False,
        'task_metrics': dict(evaluation.metrics),
        'control_step': int(state.control_step),
        'simulation_time_s': float(state.simulation_time),
        'predicate_v1': {'on_bowl_plate': predicate_mapping},
        'contact_summary_v2': contact_mapping,
        'source_id': source.scene_source.source_id,
        'source_xml_sha256': source.execution_source_receipt.canonical_xml_sha256,
        'source_closure_digest': source.source_closure_digest,
        'provider_materialization_id': env.session.provider_materialization_id,
        'episode_id': env.session.episode_id,
        'reset_sample_id': env.sample.sample_id,
        'state_boundary_identity_sha256': boundary_digest,
        'boundary_context_v1': {
            'schema_version': 'task-observation-context-v1',
            **boundary_identity,
            'state_boundary_identity_sha256': boundary_digest,
            'contact_summary_v2': contact_mapping,
            'predicate_v1': predicate_mapping,
        },
    }
    return obs, info, evaluation


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
    "observe_selected_reference_v1",
]
