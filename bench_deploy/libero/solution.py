"""Source-bound task Solution for the pinned LIBERO bowl-to-plate task.

The policy consumes only the public SelectedReferenceEnv observation, info and
episode metadata. It issues incremental arm-joint targets and aggregate finger
opening through the existing mixed-control owner; it never steps physics or
reads a RuntimeSession/provider object.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

import numpy as np

from task_env.controllers.canonical.contracts import digest
from task_env.controllers.canonical.kinematics import (
    PandaKinematics,
    derive_panda_tcp_profile_v2,
)
from task_env.planners.contracts import ExpertAction

from .task_contracts import TASK_1


SOLUTION_SCHEMA = "libero-bowl-to-plate-solution-v1"
TCP_ID = "libero-mounted-panda-v1/gripper0-grip-site-v1"
HAND_FRAME_ID = "robot0_right_hand"
SITE_NAME = "gripper0_grip_site"
BASE_BODY_ID = "robot0_link0"
_JOINT_LIMITS = np.asarray((
    (-2.8973, 2.8973), (-1.7628, 1.7628), (-2.8973, 2.8973),
    (-3.0718, -0.0698), (-2.8973, 2.8973), (-0.0175, 3.7525),
    (-2.8973, 2.8973),
), dtype=np.float64)
_OPENING_BY_STAGE = {
    # Leave 10 mm per finger inside the signed source joint limits. Native
    # attempts measured roughly 5 mm overshoot near the open stop; the physical
    # monitor correctly rejects even small source-range crossings.
    "approach": 0.06,
    "descend": 0.06,
    "grasp": 0.045,
    "lift": 0.045,
    "carry": 0.045,
    "place": 0.045,
    "release": 0.06,
}


def solution_identity_v1(source_xml_sha256: str) -> str:
    """Return the exact task/profile identity bound to one composed MJCF."""
    if (type(source_xml_sha256) is not str or len(source_xml_sha256) != 64
            or any(character not in "0123456789abcdef" for character in source_xml_sha256)):
        raise ValueError("LIBERO Solution identity requires a lowercase source XML SHA-256")
    return digest({
        "schema_version": SOLUTION_SCHEMA,
        "task_uid": TASK_1,
        "source_xml_sha256": source_xml_sha256,
        "controller_profile_id": "libero-spatial-bowl-to-plate-joint-space-pd-v1",
        "tcp_id": TCP_ID,
        "algorithm": "public-observation-damped-jacobian-waypoints-v1",
        "waypoints_m": {
            "approach_z": 0.15, "grasp_z": 0.05,
            "lift_z": 0.20, "place_tcp_z_above_plate": 0.085,
        },
        "opening_m": _OPENING_BY_STAGE,
    })


def _body_position(observation: Mapping[str, object], key: str) -> np.ndarray:
    try:
        value = np.asarray(observation["privileged_state"][key], dtype=np.float64)[0, :3]
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"public LIBERO observation is missing {key}") from exc
    if value.shape != (3,) or not np.isfinite(value).all():
        raise ValueError(f"public LIBERO body pose {key} must contain a finite world position")
    return value.copy()


def _state_vector(observation: Mapping[str, object]) -> tuple[np.ndarray, np.ndarray]:
    try:
        state = observation["state"]
        joints = np.asarray(state["joint_position"], dtype=np.float64)
        ee_pose = np.asarray(state["ee_pose"], dtype=np.float64)
    except (KeyError, TypeError) as exc:
        raise ValueError("public LIBERO observation is missing state fields") from exc
    if joints.shape != (9,) or not np.isfinite(joints).all():
        raise ValueError("public LIBERO joint_position must contain seven arm and two finger values")
    if ee_pose.shape != (7,) or not np.isfinite(ee_pose).all():
        raise ValueError("public LIBERO ee_pose must be a finite world pose")
    return joints[:7].copy(), ee_pose[:3].copy()


def _boundary_identity(info: Mapping[str, object]) -> tuple[str, str, str, str, str, int, float]:
    try:
        identity = (
            str(info["source_id"]), str(info["source_closure_digest"]),
            str(info["provider_materialization_id"]), str(info["episode_id"]),
            str(info["reset_sample_id"]), int(info["control_step"]),
            float(info["simulation_time_s"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("public LIBERO info is missing its source and boundary identity") from exc
    if (any(not value for value in identity[:5]) or identity[5] < 0
            or not math.isfinite(identity[6]) or identity[6] < 0):
        raise ValueError("public LIBERO boundary identity is invalid")
    context = info.get("boundary_context_v1")
    if isinstance(context, Mapping):
        expected = (
            context.get("source_id"), context.get("source_closure_digest"),
            context.get("provider_materialization_id"), context.get("episode_id"),
            context.get("reset_sample_id"), context.get("control_step"),
            context.get("simulation_time_s"),
        )
        if expected != identity:
            raise ValueError("public LIBERO info and boundary context identities disagree")
    return identity


@dataclass(frozen=True)
class LiberoPickPlaceSolutionConfigV1:
    position_tolerance_m: float = 0.012
    max_cartesian_increment_m: float = 0.008
    max_joint_increment_rad: float = 0.055
    grasp_dwell_steps: int = 8
    release_dwell_steps: int = 12
    release_timeout_steps: int = 50
    max_episode_steps: int = 1000

    def validate(self) -> None:
        numeric = (
            self.position_tolerance_m,
            self.max_cartesian_increment_m,
            self.max_joint_increment_rad,
        )
        if any(not math.isfinite(float(value)) or value <= 0 for value in numeric):
            raise ValueError("LIBERO Solution motion tolerances must be positive and finite")
        if (type(self.grasp_dwell_steps) is not int or self.grasp_dwell_steps < 1
                or type(self.release_dwell_steps) is not int or self.release_dwell_steps < 1
                or type(self.release_timeout_steps) is not int
                or self.release_timeout_steps < self.release_dwell_steps
                or type(self.max_episode_steps) is not int
                or not 1 <= self.max_episode_steps <= 1000):
            raise ValueError("LIBERO Solution step limits are invalid")


class LiberoPickPlaceSolutionV1:
    """Public-interface-only pick/place expert for the exact task #1 source."""

    task_uid = TASK_1

    def __init__(self, source_xml: bytes | str,
                 config: LiberoPickPlaceSolutionConfigV1 | None = None):
        raw = source_xml.encode("utf-8") if isinstance(source_xml, str) else bytes(source_xml)
        if not raw:
            raise ValueError("LIBERO Solution requires nonempty composed source MJCF bytes")
        self.source_xml_sha256 = hashlib.sha256(raw).hexdigest()
        self.tcp_profile = derive_panda_tcp_profile_v2(
            raw, tcp_id=TCP_ID, hand_frame_id=HAND_FRAME_ID, site_name=SITE_NAME,
        )
        self.kinematics = PandaKinematics(
            raw, tcp_profile=self.tcp_profile, native_prefix="robot0_",
            base_body_id=BASE_BODY_ID,
        )
        self.config = config or LiberoPickPlaceSolutionConfigV1()
        self.config.validate()
        self.identity = solution_identity_v1(self.source_xml_sha256)
        self._reset_state()

    def _reset_state(self) -> None:
        self.stage = "uninitialized"
        self.done = False
        self.failed = False
        self.failure_reason = None
        self._episode_identity = None
        self._last_boundary_step = None
        self._pending_action = False
        self._stage_steps = 0
        self._actions = 0
        self._initial_bowl = None
        self._plate = None
        self._last_observation = None

    def reset(self, observation, info: Mapping[str, object], metadata, **_kwargs) -> None:
        self._reset_state()
        if not isinstance(metadata, Mapping):
            raise TypeError("LIBERO Solution requires the public SelectedReferenceEnv metadata mapping")
        artifact_hash = metadata.get("task_artifact_hash")
        if type(artifact_hash) is not str or not artifact_hash:
            raise ValueError("LIBERO Solution received invalid task Artifact identity")
        if metadata.get("solution_identity") != self.identity:
            raise ValueError("SelectedReferenceEnv metadata names a different caller-owned Solution")
        if metadata.get("source_xml_sha256") != self.source_xml_sha256:
            raise ValueError("LIBERO Solution MJCF differs from the selected episode source")
        if metadata.get("source_closure_digest") != info.get("source_closure_digest"):
            raise ValueError("LIBERO Solution source closure differs from the selected episode")
        action_schema = metadata.get("action_schema")
        if (not isinstance(action_schema, Mapping)
                or action_schema.get("schema_id") != "libero-joint-space-absolute-v1"
                or action_schema.get("dimension") != 8):
            raise ValueError("LIBERO Solution action schema differs from its selected task route")
        if (metadata.get("provider") != "mujoco" or metadata.get("backend") != "cpu"):
            raise ValueError("LIBERO task #1 Solution is currently enabled only for MuJoCo CPU")
        identity = _boundary_identity(info)
        if identity[5] != 0 or identity[6] != 0.0:
            raise ValueError("LIBERO Solution must initialize at the reset boundary")
        if info.get("provider") != "mujoco":
            raise ValueError("LIBERO Solution reset info names an unsupported provider")
        if info.get("source_xml_sha256") != self.source_xml_sha256:
            raise ValueError("LIBERO reset info source MJCF differs from the Solution")
        sample = info.get("reset_sample_v1")
        if (not isinstance(sample, Mapping) or sample.get("sample_id") != identity[4]
                or sample.get("task_artifact_hash") != artifact_hash):
            raise ValueError("LIBERO reset sample identity is missing or mismatched")
        self._episode_identity = identity[:5]
        self._last_boundary_step = 0
        self._initial_bowl = _body_position(observation, "bowl_body_pose")
        self._plate = _body_position(observation, "plate_body_pose")
        _state_vector(observation)
        self.stage = "approach"
        self._last_observation = observation

    def _validate_boundary(self, observation, info: Mapping[str, object], *, next_step: bool) -> tuple[np.ndarray, np.ndarray]:
        if self._episode_identity is None or self._last_boundary_step is None:
            raise RuntimeError("LIBERO Solution must be reset before execution")
        identity = _boundary_identity(info)
        if identity[:5] != self._episode_identity:
            raise ValueError("LIBERO Solution observed a different source, materialization, episode or reset")
        expected_step = self._last_boundary_step + (1 if next_step else 0)
        if identity[5] != expected_step:
            raise ValueError("LIBERO Solution observed a skipped, stale or repeated control boundary")
        if next_step and self._pending_action is not True:
            raise RuntimeError("LIBERO Solution received an unrequested post-step observation")
        if not next_step and self._pending_action:
            raise RuntimeError("LIBERO Solution requires observe() after each action")
        expected_time = identity[5] * 0.05
        if abs(identity[6] - expected_time) > 1e-6:
            raise ValueError("LIBERO Solution observed a boundary outside the frozen 20 Hz timebase")
        joints, ee_position = _state_vector(observation)
        obs_digest = np.asarray(observation["state"].get("boundary_identity_sha256"), dtype=np.uint8)
        expected_digest = info.get("state_boundary_identity_sha256")
        if (obs_digest.shape != (32,) or type(expected_digest) is not str
                or obs_digest.tobytes().hex() != expected_digest):
            raise ValueError("LIBERO Solution observation and info boundary identities disagree")
        return joints, ee_position

    def _target(self) -> np.ndarray:
        if self._initial_bowl is None or self._plate is None:
            raise RuntimeError("LIBERO Solution reset geometry is unavailable")
        bowl = self._initial_bowl
        plate = self._plate
        if self.stage == "approach":
            return bowl + np.asarray((0.0, 0.0, 0.15))
        if self.stage in {"descend", "grasp"}:
            return bowl + np.asarray((0.0, 0.0, 0.05))
        if self.stage == "lift":
            return bowl + np.asarray((0.0, 0.0, 0.20))
        if self.stage == "carry":
            return np.asarray((plate[0], plate[1], bowl[2] + 0.20))
        if self.stage in {"place", "release"}:
            return plate + np.asarray((0.0, 0.0, 0.085))
        raise RuntimeError(f"LIBERO Solution has no target in stage {self.stage!r}")

    def act(self, observation, info: Mapping[str, object]) -> ExpertAction:
        joints, _ee_position = self._validate_boundary(observation, info, next_step=False)
        if self.done or self.failed:
            raise RuntimeError("LIBERO Solution has already stopped")
        target = self._target()
        transform, jacobian = self.kinematics.fk_jacobian(joints)
        current_position = transform[:3, 3]
        error = target - current_position
        distance = float(np.linalg.norm(error))
        step = error if distance <= self.config.max_cartesian_increment_m else (
            error * (self.config.max_cartesian_increment_m / distance)
        )
        position_jacobian = jacobian[:3, :]
        damping = 0.025
        system = position_jacobian @ position_jacobian.T + damping * damping * np.eye(3)
        delta_q = position_jacobian.T @ np.linalg.solve(system, step)
        largest = float(np.max(np.abs(delta_q)))
        if largest > self.config.max_joint_increment_rad:
            delta_q *= self.config.max_joint_increment_rad / largest
        desired = joints + delta_q
        if np.any(desired < _JOINT_LIMITS[:, 0]) or np.any(desired > _JOINT_LIMITS[:, 1]):
            raise ValueError("LIBERO Solution waypoint would leave the exact Panda joint ranges")
        opening = _OPENING_BY_STAGE.get(self.stage)
        if opening is None:
            raise RuntimeError(f"LIBERO Solution has no gripper policy in stage {self.stage!r}")
        self._pending_action = True
        self._actions += 1
        return ExpertAction(
            action=np.asarray((*desired, opening), dtype=np.float32),
            stage=self.stage,
            diagnostics={
                "waypoint_distance_m": distance,
                "cartesian_increment_m": float(np.linalg.norm(step)),
                "stage_step": self._stage_steps,
                "source_fk_position_m": tuple(float(value) for value in current_position),
            },
        )

    def observe(self, observation, reward: float, terminated: bool, truncated: bool,
                info: Mapping[str, object], **_kwargs) -> None:
        _joints, ee_position = self._validate_boundary(observation, info, next_step=True)
        self._pending_action = False
        identity = _boundary_identity(info)
        self._last_boundary_step = identity[5]
        self._last_observation = observation
        self._stage_steps += 1
        target = self._target()
        target_error = float(np.linalg.norm(target - ee_position))
        tolerance = self.config.position_tolerance_m

        if self.stage == "approach" and target_error <= tolerance:
            self.stage, self._stage_steps = "descend", 0
        elif self.stage == "descend" and target_error <= tolerance:
            self.stage, self._stage_steps = "grasp", 0
        elif self.stage == "grasp" and self._stage_steps >= self.config.grasp_dwell_steps:
            self.stage, self._stage_steps = "lift", 0
        elif self.stage == "lift" and target_error <= tolerance:
            bowl_now = _body_position(observation, "bowl_body_pose")
            if bowl_now[2] >= self._initial_bowl[2] + 0.035:
                self.stage, self._stage_steps = "carry", 0
            elif self._stage_steps >= 60:
                self.failed = True
                self.failure_reason = "bowl_not_lifted_after_grasp"
        elif self.stage == "carry" and np.linalg.norm(target[:2] - ee_position[:2]) <= tolerance:
            self.stage, self._stage_steps = "place", 0
        elif self.stage == "place" and target_error <= tolerance:
            self.stage, self._stage_steps = "release", 0
        elif self.stage == "release":
            predicate = info.get("predicate_v1", {}).get("on_bowl_plate", {})
            success = info.get("is_success")
            if type(success) is not bool or predicate.get("status") not in {"available", "unavailable"}:
                raise ValueError("LIBERO Solution post-step info omits the typed On predicate result")
            if predicate.get("status") == "available" and predicate.get("value") is not success:
                raise ValueError("LIBERO task success and typed On predicate disagree")
            if (self._stage_steps >= self.config.release_dwell_steps
                    and success is True and predicate.get("status") == "available"):
                self.done = True
                self.stage = "complete"
            elif self._stage_steps >= self.config.release_timeout_steps:
                self.failed = True
                self.failure_reason = "released_bowl_did_not_satisfy_source_on_predicate"
        if truncated and not self.done:
            self.failed = True
            self.failure_reason = "horizon_truncated_before_source_task_success"
        if terminated and not self.done:
            self.failed = True
            self.failure_reason = "task_terminated_before_solution_completion"

    def outcome_report(self) -> dict[str, object]:
        return {
            "solution_schema_version": SOLUTION_SCHEMA,
            "solution_identity": self.identity,
            "solution_stage": self.stage,
            "solution_actions": self._actions,
            "solution_done": bool(self.done),
            "solution_failed": bool(self.failed),
            "solution_failure_reason": self.failure_reason,
        }

    def abort(self, reason: str) -> None:
        if self.done:
            raise RuntimeError("completed LIBERO Solution cannot be aborted")
        self.failed = True
        self.failure_reason = str(reason)


__all__ = [
    "SOLUTION_SCHEMA", "LiberoPickPlaceSolutionConfigV1",
    "LiberoPickPlaceSolutionV1", "solution_identity_v1",
]
