"""Resolved-rate Panda trajectory tracking and fixed-physics-rate gripper servo.

R3 is additive. It consumes the existing absolute-pose action contract and
produces the existing canonical joint-position target. Gripper state may be
advanced by the optional shared runtime inner-servo interval contract.
"""
from dataclasses import asdict
import hashlib
import math
from pathlib import Path

import numpy as np

from ...artifacts import PoseWorld
from .contracts import CanonicalAction, CanonicalControlTarget, GripperControlTarget, digest
from .feedback import CanonicalControlFeedback
from .kinematics import ARM
from .production_r2 import ProductionCanonicalPandaControllerR2
from ...utils.rotation import quat_wxyz_to_matrix, matrix_to_rotvec


class ProductionCanonicalPandaControllerR3(ProductionCanonicalPandaControllerR2):
    """Provider-neutral resolved-rate arm tracker with an optional inner gripper loop."""

    PROFILE_SCHEMA = "canonical-panda-production-r3-resolved-rate-v1"

    def __init__(self, model, *, artifact_hash, config, gripper_config, control_dt,
                 profile, feedforward_gain=1.0, position_feedback_s=4.0,
                 rotation_feedback_s=4.0, joint_velocity_limit_rad_s=2.0,
                 inner_physics_dt_s=0.002):
        super().__init__(model, artifact_hash=artifact_hash, config=config,
                         gripper_config=gripper_config, control_dt=control_dt,
                         profile=profile)
        values = (feedforward_gain, position_feedback_s, rotation_feedback_s,
                  joint_velocity_limit_rad_s, inner_physics_dt_s)
        if any(not math.isfinite(float(v)) or float(v) <= 0.0 for v in values):
            raise ValueError("R3 physical gains/rates must be finite and positive")
        self.feedforward_gain = float(feedforward_gain)
        self.position_feedback_s = float(position_feedback_s)
        self.rotation_feedback_s = float(rotation_feedback_s)
        self.joint_velocity_limit_rad_s = float(joint_velocity_limit_rad_s)
        self.inner_physics_dt_s = float(inner_physics_dt_s)
        self.dls_damping = float(profile["controller"]["ik_damping"])
        self.rotation_row_weight = float(profile["controller"]["ik_rotation_row_weight"])
        if self.inner_physics_dt_s != 0.002:
            raise ValueError("R5 fixed gripper inner servo requires physics_dt=0.002 s")
        self._previous_reference = None
        self._previous_reference_step = None
        self.last_arm_diagnostics = {}
        self.controller_source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity = digest({
            "schema": self.PROFILE_SCHEMA,
            "source_sha256": self.controller_source_sha256,
            "r2_source_sha256": self._arm.model.source_sha256,
            "physical_profile": self.physical_profile,
            "control_dt_s": self.control_dt,
            "feedforward_gain": self.feedforward_gain,
            "position_feedback_s": self.position_feedback_s,
            "rotation_feedback_s": self.rotation_feedback_s,
            "joint_velocity_limit_rad_s": self.joint_velocity_limit_rad_s,
            "inner_physics_dt_s": self.inner_physics_dt_s,
            "row_weight": self.rotation_row_weight,
            "law": "world_twist_feedforward_plus_pose_error_DLS_integrated_to_joint_position",
        })

    @classmethod
    def from_source(cls, artifact, source, *, profile, **kwargs):
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError("source/Artifact mismatch")
        from .kinematics import PandaKinematics
        return cls(PandaKinematics(source.scene_source.xml), artifact_hash=artifact.identity_hash,
                   config=source.config.action, gripper_config=source.config.robot.gripper,
                   control_dt=artifact.timebase.control_dt, profile=profile, **kwargs)

    def reset(self, state, feedback):
        super().reset(state, feedback)
        self._previous_reference = None
        self._previous_reference_step = None
        self.last_arm_diagnostics = {}

    def compute(self, state, feedback, requested):
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError("reset then compute exactly once per outer control boundary")

        # Reuse the frozen R1 action interpreter for canonical clipping and world-pose
        # resolution; R3 deliberately ignores its waypoint-regulation joint targets.
        canonical, _legacy_desired, _legacy_servo = self._arm._compute_arm(state, requested)
        goal = canonical.resolved_world_pose
        if goal is None:
            raise ValueError("R3 prototype requires the existing absolute-pose action contract")
        goal_position = np.asarray(goal.position, dtype=float)
        goal_rotation = quat_wxyz_to_matrix(goal.quaternion_wxyz)
        actual = state.pose_world["panda-v1/ee"]
        actual_position = np.asarray(actual.position, dtype=float)
        actual_rotation = quat_wxyz_to_matrix(actual.quaternion_wxyz)

        reset_reason = None
        if (self._previous_reference is not None and
                self._previous_reference_step != state.control_step - 1):
            self._previous_reference = None
            reset_reason = "control_step_discontinuity"
        if self._previous_reference is not None:
            prior_position, prior_rotation = self._previous_reference
            translation_jump = float(np.linalg.norm(goal_position - prior_position))
            rotation_jump = float(np.linalg.norm(matrix_to_rotvec(goal_rotation @ prior_rotation.T)))
            if translation_jump > 0.05 or rotation_jump > 0.5:
                self._previous_reference = None
                reset_reason = "reference_pose_discontinuity"

        if self._previous_reference is None:
            v_ff = np.zeros(3, dtype=float)
            omega_ff = np.zeros(3, dtype=float)
        else:
            prior_position, prior_rotation = self._previous_reference
            v_ff = (goal_position - prior_position) / self.control_dt
            omega_ff = matrix_to_rotvec(goal_rotation @ prior_rotation.T) / self.control_dt
        self._previous_reference = (goal_position.copy(), goal_rotation.copy())
        self._previous_reference_step = state.control_step

        e_p = goal_position - actual_position
        e_r = matrix_to_rotvec(goal_rotation @ actual_rotation.T)
        v_cmd = self.feedforward_gain * v_ff + self.position_feedback_s * e_p
        omega_cmd = self.feedforward_gain * omega_ff + self.rotation_feedback_s * e_r
        q = np.asarray([state.joint_position[name] for name in ARM], dtype=float)
        _transform, jacobian = self._arm.model.fk_jacobian(q)
        weight = self.rotation_row_weight
        weighted_jacobian = np.asarray(jacobian, dtype=float).copy()
        weighted_jacobian[3:] *= weight
        weighted_twist = np.concatenate((v_cmd, weight * omega_cmd))
        system = weighted_jacobian @ weighted_jacobian.T + self.dls_damping**2 * np.eye(6)
        qdot = weighted_jacobian.T @ np.linalg.solve(system, weighted_twist)
        qdot = np.clip(qdot, -self.joint_velocity_limit_rad_s, self.joint_velocity_limit_rad_s)
        q_reference = np.clip(q + qdot * self.control_dt,
                              self._arm.model.limits[:, 0], self._arm.model.limits[:, 1])

        opening = float(np.clip(.5 * (canonical.interpreted_values[-1] + 1.0) *
                                self.config.gripper_opening_range_m, 0.0,
                                self.config.gripper_opening_range_m))
        if opening > self._commanded + 1e-12:
            self._force_mode = False
            self._force_initialized = False
        self._desired = opening
        arm = dict(zip(ARM, map(float, q_reference)))
        target = CanonicalControlTarget(
            "canonical-control-v0", self._arm.artifact_hash, self.identity, ARM,
            arm, dict(arm),
            GripperControlTarget(self.gripper_semantic_id, opening,
                                 self.gripper_config.force_limit_N, self._commanded),
        )
        self.last_arm_diagnostics = {
            "v_ff_m_s": v_ff.tolist(), "omega_ff_rad_s": omega_ff.tolist(),
            "v_cmd_m_s": v_cmd.tolist(), "omega_cmd_rad_s": omega_cmd.tolist(),
            "position_error_m": e_p.tolist(), "rotation_error_rad": e_r.tolist(),
            "joint_velocity_rad_s": qdot.tolist(),
            "reference_history_reset_reason": reset_reason,
            "joint_velocity_limit_rad_s": self.joint_velocity_limit_rad_s,
        }
        self._expected_step += 1
        return canonical, target

    def inner_gripper_step(self, state, feedback):
        """Advance only gripper state at one fixed physics boundary (2 ms)."""
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step - 1:
            raise RuntimeError("gripper inner update must stay within the current outer interval")
        cfg = self.gripper_config
        dt = self.inner_physics_dt_s
        delta = self._desired - self._commanded
        if delta > 1e-12:
            self._force_mode = False
            self._force_initialized = False
        closing = delta < -1e-12
        measured_force = float(feedback.gripper.closing_force_N)
        activation = max(.5, .1 * cfg.force_limit_N)
        if closing and not self._force_mode and measured_force >= activation:
            self._force_mode = True
        if closing and self._force_mode:
            if not self._force_initialized:
                self._commanded = float(np.clip(
                    feedback.gripper.opening_m - cfg.force_limit_N /
                    self.config.gripper_position_stiffness_N_per_m,
                    0.0, self.config.gripper_opening_range_m))
                self._force_initialized = True
            force_error = max(0.0, cfg.force_limit_N - measured_force)
            if force_error > cfg.force_deadband_N:
                normalized = float(np.clip(force_error / cfg.force_limit_N, 0.0, 1.0))
                exponent = float(self.physical_profile["gripper"]["force_adjust_error_exponent"])
                self._commanded = max(0.0, self._commanded -
                                      float(self.physical_profile["gripper"]["force_adjust_rate_m_s"]) *
                                      dt * normalized**exponent)
        elif not self._force_mode:
            max_step = float(self.physical_profile["gripper"]["opening_rate_m_s"]) * dt
            self._commanded = float(np.clip(self._commanded +
                                            np.clip(delta, -max_step, max_step),
                                            0.0, self.config.gripper_opening_range_m))
        target = GripperControlTarget(self.gripper_semantic_id, self._desired,
                                      cfg.force_limit_N, self._commanded)
        return target, {
            "measured_opening_m": float(feedback.gripper.opening_m),
            "commanded_opening_m": float(self._commanded),
            "desired_opening_m": float(self._desired),
            "closing_force_N": measured_force,
            "force_mode_active": bool(self._force_mode),
            "force_mode_initialized": bool(self._force_initialized),
            "command_saturated_at_zero": self._commanded <= 1e-12,
            "controller_close_ready": bool(self._force_mode and self._force_initialized and
                                             cfg.force_limit_N - measured_force <= cfg.force_deadband_N),
        }

    def rate_profile_mapping(self):
        return {
            "schema_version": self.PROFILE_SCHEMA,
            "control_dt_s": self.control_dt,
            "inner_physics_dt_s": self.inner_physics_dt_s,
            "source_sha256": self.controller_source_sha256,
            "physical_profile": self.physical_profile,
            "feedforward_gain": self.feedforward_gain,
            "position_feedback_s": self.position_feedback_s,
            "rotation_feedback_s": self.rotation_feedback_s,
            "joint_velocity_limit_rad_s": self.joint_velocity_limit_rad_s,
            "dls_damping": self.dls_damping,
        }


__all__ = ["ProductionCanonicalPandaControllerR3"]
