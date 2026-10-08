"""Additive physical-time-aware production controller profile (R2).

R1 remains untouched. R2 derives the boundary-sized limits from one shared
physical profile and the TaskArtifact control interval.
"""
from dataclasses import asdict, replace
import hashlib
import math
from pathlib import Path

import numpy as np

from ...environment import ActionConfig, GripperConfig
from .contracts import CanonicalControlTarget, GripperControlTarget, digest
from .kinematics import ARM, PandaKinematics
from .production import ProductionCanonicalPandaController


class ProductionCanonicalPandaControllerR2(ProductionCanonicalPandaController):
    """Production canonical controller with physical-time-derived rate caps."""

    PROFILE_SCHEMA = "canonical-panda-production-r2-physical-profile-v5"

    def __init__(
        self,
        model,
        *,
        artifact_hash,
        config: ActionConfig,
        gripper_config: GripperConfig,
        control_dt: float,
        profile,
        gripper_semantic_id="panda-v1/gripper",
    ):
        if not isinstance(config, ActionConfig):
            raise TypeError("resolved ActionConfig required")
        if not isinstance(gripper_config, GripperConfig):
            raise TypeError("resolved GripperConfig required")
        dt = float(control_dt)
        if not math.isfinite(dt) or dt <= 0.0:
            raise ValueError("positive finite control_dt required")
        controller = dict(profile["controller"])
        gripper = dict(profile["gripper"])
        required_controller = {
            "max_cartesian_translation_rate_m_s",
            "max_cartesian_rotation_rate_rad_s",
            "max_joint_increment_rate_rad_s",
            "ik_damping",
            "ik_position_gain",
            "ik_rotation_gain",
            "ik_rotation_row_weight",
            "position_deadband_m",
            "rotation_deadband_rad",
            "joint_position_correction_rate_s",
            "joint_position_correction_max_gain",
        }
        required_gripper = {
            "opening_rate_m_s",
            "force_adjust_rate_m_s",
            "force_adjust_error_exponent",
        }
        if set(controller) != required_controller:
            raise ValueError("R2 controller profile keys differ from its versioned contract")
        if set(gripper) != required_gripper:
            raise ValueError("R2 gripper profile keys differ from its versioned contract")
        for name, value in {**controller, **gripper}.items():
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"R2 rate/gain must be finite and positive: {name}")

        derived_action = replace(
            config,
            ik_damping=float(controller["ik_damping"]),
            ik_position_gain=float(controller["ik_position_gain"]),
            ik_rotation_gain=float(controller["ik_rotation_gain"]),
            ik_rotation_row_weight=float(controller["ik_rotation_row_weight"]),
            ik_max_delta_q=float(controller["max_joint_increment_rate_rad_s"]) * dt,
            ik_position_deadband=float(controller["position_deadband_m"]),
            ik_rotation_deadband=float(controller["rotation_deadband_rad"]),
            cartesian_max_position_step=float(controller["max_cartesian_translation_rate_m_s"]) * dt,
            cartesian_max_rotation_step=float(controller["max_cartesian_rotation_rate_rad_s"]) * dt,
            # R1's correction is a per-boundary extrapolation factor. In R2,
            # interpret it as a physical rate so the same elapsed time gives
            # the same correction at every control frequency.
            joint_position_correction_gain=min(
                float(controller["joint_position_correction_rate_s"]) * dt,
                float(controller["joint_position_correction_max_gain"]),
            ),
        )
        derived_gripper = replace(
            gripper_config,
            opening_step_m=float(gripper["opening_rate_m_s"]) * dt,
            force_adjust_step_m=float(gripper["force_adjust_rate_m_s"]) * dt,
        )
        super().__init__(
            model,
            artifact_hash=artifact_hash,
            config=derived_action,
            gripper_config=derived_gripper,
            gripper_semantic_id=gripper_semantic_id,
        )
        self.control_dt = dt
        self.physical_profile = {
            "schema_version": self.PROFILE_SCHEMA,
            "controller": controller,
            "gripper": gripper,
        }
        self.controller_source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity = digest({
            "schema": "panda-production-control-r2",
            "controller_source_sha256": self.controller_source_sha256,
            "physical_profile": self.physical_profile,
            "control_dt_s": dt,
            "derived_action_config": asdict(derived_action),
            "derived_gripper_config": asdict(derived_gripper),
            "arm_profile_identity": self._arm.identity,
            "source_sha256": model.source_sha256,
            "readiness": "R1-compatible-completed-boundary-force-readiness",
            "control": "R1-canonical-DLS-with-physical-time-derived-rate-caps-and-servo-correction",
            "gripper_force_adjust_law": "physical-rate-times-normalized-force-error-power-v1",
        })

    def compute(self, state, feedback, requested):
        """Lower the R1 action contract with R2 physical-time gripper dynamics.

        The configured force-adjust rate is the maximum physical closing rate.
        Scale it by a shared normalized-force-error exponent so the
        zero-order-held gripper target decelerates near the force window.
        This keeps stable fallback and close-ready observations resolvable at
        each shared control frequency.
        """
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError("reset then compute exactly once per control boundary")
        canonical, desired_arm, servo_arm = self._arm._compute_arm(state, requested)
        cfg = self.gripper_config
        opening = float(.5 * (canonical.interpreted_values[-1] + 1) * self.config.gripper_opening_range_m)
        delta = opening - self._commanded
        if delta > 1e-12:
            self._force_mode = False
            self._force_initialized = False
        closing = delta < -1e-12
        measured = feedback.gripper.closing_force_N
        activation = max(.5, .1 * cfg.force_limit_N)
        if closing and not self._force_mode and measured >= activation:
            self._force_mode = True
        if closing and self._force_mode:
            if not self._force_initialized:
                self._commanded = float(np.clip(
                    feedback.gripper.opening_m - cfg.force_limit_N / self.config.gripper_position_stiffness_N_per_m,
                    0, self.config.gripper_opening_range_m))
                self._force_initialized = True
            force_error = max(0.0, cfg.force_limit_N - measured)
            if force_error > cfg.force_deadband_N:
                normalized_error = float(np.clip(force_error / cfg.force_limit_N, 0.0, 1.0))
                exponent = float(self.physical_profile["gripper"]["force_adjust_error_exponent"])
                step = cfg.force_adjust_step_m * normalized_error**exponent
                self._commanded = float(max(0.0, self._commanded - step))
        elif not self._force_mode:
            self._commanded = float(np.clip(self._commanded + np.clip(
                delta, -cfg.opening_step_m, cfg.opening_step_m), 0, self.config.gripper_opening_range_m))
        self._desired = opening
        target = CanonicalControlTarget(
            "canonical-control-v0", self._arm.artifact_hash, self.identity, ARM,
            dict(zip(ARM, map(float, desired_arm))),
            dict(zip(ARM, map(float, servo_arm))),
            GripperControlTarget(self.gripper_semantic_id, opening, cfg.force_limit_N, self._commanded),
        )
        self._expected_step += 1
        return canonical, target

    @classmethod
    def from_source(cls, artifact, source, *, profile):
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError("source/Artifact mismatch")
        return cls(
            PandaKinematics(source.scene_source.xml),
            artifact_hash=artifact.identity_hash,
            config=source.config.action,
            gripper_config=source.config.robot.gripper,
            control_dt=artifact.timebase.control_dt,
            profile=profile,
        )

    def rate_profile_mapping(self):
        """Return the shared physical profile and mechanical per-boundary values."""
        return {
            "schema_version": self.PROFILE_SCHEMA,
            "control_dt_s": self.control_dt,
            "controller_source_sha256": self.controller_source_sha256,
            "physical_profile": self.physical_profile,
            "derived_action_config": asdict(self.config),
            "derived_gripper_config": asdict(self.gripper_config),
        }


__all__ = ["ProductionCanonicalPandaControllerR2"]
