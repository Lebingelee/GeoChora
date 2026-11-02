"""Resolved-rate Panda tracker with persistent joint-reference state.

This same-branch R5 continuation replaces the rejected achieved-state rebase
with a bounded, persistent q_ref. The public action and position-target
contracts remain unchanged.
"""
import hashlib
import math
from pathlib import Path

import numpy as np

from ...utils.rotation import quat_wxyz_to_matrix, matrix_to_rotvec
from .contracts import CanonicalArmReferenceV1, CanonicalControlTarget, GripperControlTarget, digest
from .controller import CanonicalPandaController
from .kinematics import ARM
from .production_r2 import ProductionCanonicalPandaControllerR2



R3_PROFILE_PATH = Path(__file__).with_name("production_r3_profile.yaml")

def load_r3_dynamic_profile():
    """Return a fresh copy of the shared, versioned production profile."""
    import yaml

    profile = yaml.safe_load(R3_PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or set(profile) != {"controller", "gripper", "planner"}:
        raise ValueError("invalid production R3 dynamic profile")
    return profile

def _limit_joint_velocity_direction_preserving(qdot_raw, limit_rad_s):
    """Uniformly limit a joint-velocity vector without changing its direction."""
    velocity = np.asarray(qdot_raw, dtype=float)
    limit = float(limit_rad_s)
    if velocity.ndim != 1 or not np.isfinite(velocity).all():
        raise ValueError("R3 joint velocity must be a finite one-dimensional vector")
    if not math.isfinite(limit) or limit <= 0.0:
        raise ValueError("R3 joint velocity limit must be finite and positive")
    peak = float(np.max(np.abs(velocity))) if velocity.size else 0.0
    if peak <= limit:
        return velocity.copy()
    return velocity * (limit / peak)


class _ProductionR3ArmReference:
    """Shared R3 arm law and memory used by full and arm-only callers."""

    def __init__(self, arm, *, control_dt, feedforward_gain,
                 position_feedback_s, rotation_feedback_s,
                 joint_velocity_limit_rad_s, reference_lead_limit_rad,
                 dls_damping, rotation_row_weight):
        self._arm = arm
        self.control_dt = float(control_dt)
        self.feedforward_gain = float(feedforward_gain)
        self.position_feedback_s = float(position_feedback_s)
        self.rotation_feedback_s = float(rotation_feedback_s)
        self.joint_velocity_limit_rad_s = float(joint_velocity_limit_rad_s)
        self.reference_lead_limit_rad = float(reference_lead_limit_rad)
        self.dls_damping = float(dls_damping)
        self.rotation_row_weight = float(rotation_row_weight)
        self._previous_reference = None
        self._previous_reference_step = None
        self._joint_reference = None
        self._expected_step = None
        self._q_ref_reset_events = 0
        self._lead_clamp_events = 0
        self._joint_velocity_clip_events = 0
        self._reference_reset_event_pending = False
        self.last_diagnostics = {}
        self.identity = digest({
            "schema": "canonical-panda-production-r3-arm-reference-v1",
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "arm_controller_identity": arm.identity,
            "control_dt_s": self.control_dt,
            "feedforward_gain": self.feedforward_gain,
            "position_feedback_s": self.position_feedback_s,
            "rotation_feedback_s": self.rotation_feedback_s,
            "joint_velocity_limit_rad_s": self.joint_velocity_limit_rad_s,
            "reference_lead_limit_rad": self.reference_lead_limit_rad,
            "dls_damping": self.dls_damping,
            "rotation_row_weight": self.rotation_row_weight,
            "law": "world_twist_DLS_integrated_into_persistent_bounded_joint_position_reference",
        })

    def reset(self, state):
        step = getattr(state, "control_step", None)
        if type(step) is not int or step < 0:
            raise ValueError("R3 arm reset requires a nonnegative control boundary")
        q = np.asarray([state.joint_position[name] for name in ARM], dtype=float)
        if q.shape != (7,) or not np.isfinite(q).all():
            raise ValueError("R3 arm reset requires seven finite typed joint positions")
        self._previous_reference = None
        self._previous_reference_step = None
        self._joint_reference = q
        self._expected_step = step
        self._q_ref_reset_events = 1
        self._lead_clamp_events = 0
        self._joint_velocity_clip_events = 0
        self._reference_reset_event_pending = True
        self.last_diagnostics = {}

    def persistent_state_mapping(self):
        reference = self._previous_reference
        return {
            "schema_version": "canonical-panda-production-r3-arm-reference-v1/state-v1",
            "joint_reference_rad": None if self._joint_reference is None else self._joint_reference.tolist(),
            "joint_reference_lead_limit_rad": self.reference_lead_limit_rad,
            "previous_requested_position_m": None if reference is None else reference[0].tolist(),
            "previous_requested_rotation_matrix_world": None if reference is None else reference[1].tolist(),
            "previous_reference_control_step": self._previous_reference_step,
            "expected_control_step": self._expected_step,
            "q_ref_reset_events": self._q_ref_reset_events,
            "reference_lead_clamp_events": self._lead_clamp_events,
            "joint_velocity_clip_events": self._joint_velocity_clip_events,
        }

    def compute(self, state, requested):
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError("reset then compute exactly once per R3 arm control boundary")
        canonical, _legacy_desired, _legacy_servo = self._arm._compute_arm(state, requested)
        goal = canonical.resolved_world_pose
        if goal is None:
            raise ValueError("R3 prototype requires the existing absolute-pose action contract")
        goal_position = np.asarray(goal.position, dtype=float)
        goal_rotation = quat_wxyz_to_matrix(goal.quaternion_wxyz)
        actual = state.pose_world["panda-v1/ee"]
        actual_position = np.asarray(actual.position, dtype=float)
        actual_rotation = quat_wxyz_to_matrix(actual.quaternion_wxyz)

        twist_reset_reason = None
        if (self._previous_reference is not None and
                self._previous_reference_step != state.control_step - 1):
            self._previous_reference = None
            twist_reset_reason = "control_step_discontinuity"
        if self._previous_reference is not None:
            prior_position, prior_rotation = self._previous_reference
            translation_jump = float(np.linalg.norm(goal_position - prior_position))
            rotation_jump = float(np.linalg.norm(matrix_to_rotvec(goal_rotation @ prior_rotation.T)))
            if translation_jump > 0.05 or rotation_jump > 0.5:
                self._previous_reference = None
                twist_reset_reason = "reference_pose_discontinuity"

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
        position_feedback = self.position_feedback_s * e_p
        rotation_feedback = self.rotation_feedback_s * e_r
        v_cmd = self.feedforward_gain * v_ff + position_feedback
        omega_cmd = self.feedforward_gain * omega_ff + rotation_feedback

        q_actual = np.asarray([state.joint_position[name] for name in ARM], dtype=float)
        if self._joint_reference is None:
            self._joint_reference = q_actual.copy()
            self._q_ref_reset_events += 1
            self._reference_reset_event_pending = True
            q_ref_init_reason = "uninitialized_reference_initialized_from_actual"
        else:
            q_ref_init_reason = None
        q_ref_previous = self._joint_reference.copy()

        _transform, jacobian = self._arm.model.fk_jacobian(q_actual)
        weight = self.rotation_row_weight
        weighted_jacobian = np.asarray(jacobian, dtype=float).copy()
        weighted_jacobian[3:] *= weight
        weighted_twist = np.concatenate((v_cmd, weight * omega_cmd))
        system = weighted_jacobian @ weighted_jacobian.T + self.dls_damping**2 * np.eye(6)
        qdot_raw = weighted_jacobian.T @ np.linalg.solve(system, weighted_twist)
        qdot = _limit_joint_velocity_direction_preserving(
            qdot_raw, self.joint_velocity_limit_rad_s,
        )
        velocity_clipped = bool(np.any(np.abs(qdot_raw - qdot) > 1e-12))
        if velocity_clipped:
            self._joint_velocity_clip_events += 1

        q_ref_integrated = q_ref_previous + qdot * self.control_dt
        joint_limits = self._arm.model.limits
        q_ref_joint_limited = np.clip(q_ref_integrated, joint_limits[:, 0], joint_limits[:, 1])
        joint_limit_clipped = bool(np.any(np.abs(q_ref_joint_limited - q_ref_integrated) > 1e-12))
        lead_before_clamp = q_ref_joint_limited - q_actual
        lead_clipped = bool(np.any(np.abs(lead_before_clamp) > self.reference_lead_limit_rad))
        if lead_clipped:
            self._lead_clamp_events += 1
        bounded_lead = np.clip(lead_before_clamp, -self.reference_lead_limit_rad,
                               self.reference_lead_limit_rad)
        q_ref_next = q_actual + bounded_lead
        self._joint_reference = q_ref_next.copy()

        self.last_diagnostics = {
            "q_actual_rad": q_actual.tolist(),
            "q_ref_previous_rad": q_ref_previous.tolist(),
            "q_ref_integrated_rad": q_ref_integrated.tolist(),
            "q_ref_next_rad": q_ref_next.tolist(),
            "q_ref_minus_q_actual_rad": (q_ref_next - q_actual).tolist(),
            "qdot_raw_rad_s": qdot_raw.tolist(),
            "qdot_cmd_rad_s": qdot.tolist(),
            "joint_velocity_clipped": velocity_clipped,
            "joint_velocity_limit_rad_s": self.joint_velocity_limit_rad_s,
            "joint_position_limit_clipped": joint_limit_clipped,
            "reference_lead_clipped": lead_clipped,
            "reference_lead_limit_rad": self.reference_lead_limit_rad,
            "reference_lead_clamp_events_total": self._lead_clamp_events,
            "joint_velocity_clip_events_total": self._joint_velocity_clip_events,
            "q_ref_reset_event": self._reference_reset_event_pending,
            "q_ref_reset_events_total": self._q_ref_reset_events,
            "q_ref_init_reason": q_ref_init_reason,
            "v_ff_m_s": v_ff.tolist(),
            "omega_ff_rad_s": omega_ff.tolist(),
            "position_feedback_m_s": position_feedback.tolist(),
            "rotation_feedback_rad_s": rotation_feedback.tolist(),
            "v_cmd_m_s": v_cmd.tolist(),
            "omega_cmd_rad_s": omega_cmd.tolist(),
            "position_error_m": e_p.tolist(),
            "rotation_error_rad": e_r.tolist(),
            "reference_twist_reset_reason": twist_reset_reason,
            "reference_twist_reset_event": twist_reset_reason is not None,
        }
        self._reference_reset_event_pending = False
        self._expected_step += 1
        return canonical, dict(zip(ARM, map(float, q_ref_next)))

    def compute_reference(self, state, requested, *, controller_identity=None):
        canonical, arm_position = self.compute(state, requested)
        result = CanonicalArmReferenceV1(
            "canonical-arm-reference-v1",
            self.identity if controller_identity is None else controller_identity,
            canonical, ARM, arm_position,
        )
        result.validate()
        return result


class ProductionCanonicalPandaControllerR3(ProductionCanonicalPandaControllerR2):
    """Provider-neutral resolved-rate arm tracker and optional gripper inner loop."""

    PROFILE_SCHEMA = "canonical-panda-production-r3-persistent-reference-v1"

    @classmethod
    def create_arm_reference(cls, model, *, artifact_hash, config, control_dt,
                              profile, feedforward_gain=1.0,
                              position_feedback_s=4.0, rotation_feedback_s=4.0,
                              joint_velocity_limit_rad_s=2.0,
                              reference_lead_limit_rad=0.15,
                              inner_physics_dt_s=0.002):
        """Build the existing R3 arm sub-contract without gripper configuration or feedback."""
        values = (feedforward_gain, position_feedback_s, rotation_feedback_s,
                  joint_velocity_limit_rad_s, reference_lead_limit_rad,
                  inner_physics_dt_s)
        if any(not math.isfinite(float(value)) or float(value) <= 0.0 for value in values):
            raise ValueError("R3 physical gains/rates must be finite and positive")
        if float(inner_physics_dt_s) != 0.002:
            raise ValueError("R3 arm profile requires the shared 2 ms physics interval")
        resolved_config = ProductionCanonicalPandaControllerR2.derive_action_config(
            config, profile["controller"], control_dt,
        )
        arm = CanonicalPandaController(
            model, artifact_hash=artifact_hash, config=resolved_config,
        )
        controller = dict(profile["controller"])
        return _ProductionR3ArmReference(
            arm, control_dt=control_dt,
            feedforward_gain=feedforward_gain,
            position_feedback_s=position_feedback_s,
            rotation_feedback_s=rotation_feedback_s,
            joint_velocity_limit_rad_s=joint_velocity_limit_rad_s,
            reference_lead_limit_rad=reference_lead_limit_rad,
            dls_damping=float(controller["ik_damping"]),
            rotation_row_weight=float(controller["ik_rotation_row_weight"]),
        )

    def __init__(self, model, *, artifact_hash, config, gripper_config, control_dt,
                 profile, feedforward_gain=1.0, position_feedback_s=4.0,
                 rotation_feedback_s=4.0, joint_velocity_limit_rad_s=2.0,
                 reference_lead_limit_rad=0.15, inner_physics_dt_s=0.002):
        super().__init__(model, artifact_hash=artifact_hash, config=config,
                         gripper_config=gripper_config, control_dt=control_dt,
                         profile=profile)
        values = (feedforward_gain, position_feedback_s, rotation_feedback_s,
                  joint_velocity_limit_rad_s, reference_lead_limit_rad,
                  inner_physics_dt_s)
        if any(not math.isfinite(float(v)) or float(v) <= 0.0 for v in values):
            raise ValueError("R3 physical gains/rates must be finite and positive")
        self.feedforward_gain = float(feedforward_gain)
        self.position_feedback_s = float(position_feedback_s)
        self.rotation_feedback_s = float(rotation_feedback_s)
        self.joint_velocity_limit_rad_s = float(joint_velocity_limit_rad_s)
        self.reference_lead_limit_rad = float(reference_lead_limit_rad)
        self.inner_physics_dt_s = float(inner_physics_dt_s)
        self.dls_damping = float(profile["controller"]["ik_damping"])
        self.rotation_row_weight = float(profile["controller"]["ik_rotation_row_weight"])
        if self.inner_physics_dt_s != 0.002:
            raise ValueError("R5 fixed gripper inner servo requires physics_dt=0.002 s")
        self._arm_reference = _ProductionR3ArmReference(
            self._arm, control_dt=self.control_dt,
            feedforward_gain=self.feedforward_gain,
            position_feedback_s=self.position_feedback_s,
            rotation_feedback_s=self.rotation_feedback_s,
            joint_velocity_limit_rad_s=self.joint_velocity_limit_rad_s,
            reference_lead_limit_rad=self.reference_lead_limit_rad,
            dls_damping=self.dls_damping,
            rotation_row_weight=self.rotation_row_weight,
        )
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
            "reference_lead_limit_rad": self.reference_lead_limit_rad,
            "inner_physics_dt_s": self.inner_physics_dt_s,
            "row_weight": self.rotation_row_weight,
            "law": "world_twist_DLS_integrated_into_persistent_bounded_joint_position_reference",
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
        self.reset_arm_reference(state)

    def reset_arm_reference(self, state):
        """Reset only R3's arm memory from a complete typed arm/hand boundary."""
        self._arm_reference.reset(state)
        self._expected_step = state.control_step
        self.last_arm_diagnostics = {}

    @staticmethod
    def _reference_from_arm_helper(helper, state, requested, identity):
        return helper.compute_reference(
            state, requested, controller_identity=identity,
        )

    def persistent_state_mapping(self):
        """Canonical controller state needed to replay this R3 sequence."""
        reference = self._arm_reference._previous_reference
        return {
            "schema_version": self.PROFILE_SCHEMA + "/state-v1",
            "joint_reference_rad": (None if self._arm_reference._joint_reference is None
                                     else self._arm_reference._joint_reference.tolist()),
            "joint_reference_lead_limit_rad": self.reference_lead_limit_rad,
            "previous_requested_position_m": None if reference is None else reference[0].tolist(),
            "previous_requested_rotation_matrix_world": None if reference is None else reference[1].tolist(),
            "previous_reference_control_step": self._arm_reference._previous_reference_step,
            "expected_control_step": self._expected_step,
            "q_ref_reset_events": self._arm_reference._q_ref_reset_events,
            "reference_lead_clamp_events": self._arm_reference._lead_clamp_events,
            "joint_velocity_clip_events": self._arm_reference._joint_velocity_clip_events,
            "gripper_memory": self.memory().to_mapping() if self._expected_step is not None else None,
        }

    def compute_arm_reference(self, state, requested):
        """Compute the public force-free arm sub-contract for a typed state boundary.

        This entry point does not consume or synthesize gripper feedback. Full
        Production R3 execution continues to use ``compute`` and its complete
        canonical gripper feedback contract.
        """
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError("reset then compute exactly once per R3 arm control boundary")
        result = self._reference_from_arm_helper(
            self._arm_reference, state, requested, self.identity,
        )
        self._expected_step += 1
        self.last_arm_diagnostics = self._arm_reference.last_diagnostics
        return result

    def compute(self, state, feedback, requested):
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError("reset then compute exactly once per outer control boundary")

        arm_reference = self._arm_reference.compute(state, requested)
        canonical, arm = arm_reference
        self.last_arm_diagnostics = self._arm_reference.last_diagnostics

        opening = float(np.clip(.5 * (canonical.interpreted_values[-1] + 1.0) *
                                self.config.gripper_opening_range_m, 0.0,
                                self.config.gripper_opening_range_m))
        if opening > self._commanded + 1e-12:
            self._force_mode = False
            self._force_initialized = False
        self._desired = opening
        target = CanonicalControlTarget(
            "canonical-control-v0", self._arm.artifact_hash, self.identity, ARM,
            arm, dict(arm),
            GripperControlTarget(self.gripper_semantic_id, opening,
                                 self.gripper_config.force_limit_N, self._commanded),
        )
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
            "reference_lead_limit_rad": self.reference_lead_limit_rad,
            "dls_damping": self.dls_damping,
        }


__all__ = ["ProductionCanonicalPandaControllerR3"]
