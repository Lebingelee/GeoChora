"""R1 production gripper ownership, shared source-derived arm lowering.

One compute per observed control boundary; reset owns/reseeds persistent state.
No provider, legacy RuntimeSnapshot, native IDs, or native controller delegation.
"""
from dataclasses import asdict
import numpy as np
from ...environment import GripperConfig
from .contracts import CanonicalControlTarget, GripperControlTarget, digest
from .controller import CanonicalPandaController
from .feedback import CanonicalControlFeedback, CanonicalGripperMemory
from .kinematics import ARM, FINGERS


class ProductionCanonicalPandaController:
    def __init__(self, model, *, artifact_hash, config, gripper_config: GripperConfig,
                 gripper_semantic_id='panda-v1/gripper'):
        if not isinstance(gripper_config, GripperConfig):
            raise TypeError('resolved RobotConfig.gripper required')
        if gripper_config.kind != 'experimental_rate_limited':
            raise ValueError('R1 implements the resolved experimental gripper profile only')
        # Projection discards opening-direction force. For this envelope, both
        # legacy and canonical branches adjust when that force is present.
        if gripper_config.force_deadband_N >= gripper_config.force_limit_N:
            raise ValueError('closing-magnitude feedback requires deadband below force limit')
        self.config = config
        self.gripper_config = gripper_config
        self.gripper_semantic_id = gripper_semantic_id
        self._arm = CanonicalPandaController(model, artifact_hash=artifact_hash, config=config)
        self.identity = digest({'schema': 'panda-production-control-r1',
            'arm_profile': self._arm.identity, 'gripper_profile': asdict(gripper_config),
            'opening_range_m': config.gripper_opening_range_m,
            'position_stiffness_N_per_m': config.gripper_position_stiffness_N_per_m,
            'feedback': 'nonnegative_closing_magnitude_completed_interval'})
        self._expected_step = None

    @classmethod
    def from_source(cls, artifact, source):
        """Production construction: gripper authority is the resolved robot owner."""
        from .kinematics import PandaKinematics
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError('source/Artifact mismatch')
        return cls(PandaKinematics(source.scene_source.xml), artifact_hash=artifact.identity_hash,
            config=source.config.action, gripper_config=source.config.robot.gripper)

    def _feedback(self, state, feedback):
        if not isinstance(feedback, CanonicalControlFeedback):
            raise TypeError('CanonicalControlFeedback required')
        feedback.require_state(state, self.gripper_semantic_id, FINGERS)

    def reset(self, state, feedback):
        self._feedback(state, feedback)
        self._commanded = float(np.clip(feedback.gripper.opening_m, 0, self.config.gripper_opening_range_m))
        self._desired = self._commanded
        self._force_mode = False
        self._force_initialized = False
        self._expected_step = state.control_step

    def memory(self):
        if self._expected_step is None:
            raise RuntimeError('controller reset required')
        return CanonicalGripperMemory(self._desired, self._commanded,
            self.gripper_config.force_limit_N, self._force_mode, self._force_initialized)

    def readiness(self, state, feedback):
        """Read-only projection at reset or the completed compute/step boundary."""
        from .readiness import CanonicalControlReadiness, GripperReadiness
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step:
            raise ValueError('readiness requires current observed controller boundary')
        force = feedback.gripper.closing_force_N
        error = self.gripper_config.force_limit_N - force
        ready = self._force_mode and self._force_initialized and error <= self.gripper_config.force_deadband_N
        return CanonicalControlReadiness('canonical-control-readiness-v1',
            state.control_step, state.simulation_time,
            GripperReadiness(self.gripper_semantic_id, bool(ready), force,
                self.gripper_config.force_limit_N, error))

    def compute(self, state, feedback, requested):
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError('reset then compute exactly once per control boundary')
        # Validate/lower first; invalid public actions never advance gripper state.
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
            if cfg.force_limit_N - measured > cfg.force_deadband_N:
                self._commanded = float(max(0., self._commanded - cfg.force_adjust_step_m))
        elif not self._force_mode:
            self._commanded = float(np.clip(self._commanded + np.clip(delta,
                -cfg.opening_step_m, cfg.opening_step_m), 0, self.config.gripper_opening_range_m))
        self._desired = opening
        target = CanonicalControlTarget('canonical-control-v0', self._arm.artifact_hash,
            self.identity, ARM, dict(zip(ARM, map(float, desired_arm))),
            dict(zip(ARM, map(float, servo_arm))),
            GripperControlTarget(self.gripper_semantic_id, opening, cfg.force_limit_N, self._commanded))
        self._expected_step += 1
        return canonical, target
