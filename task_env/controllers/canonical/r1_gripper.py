"""Shared outer-boundary R1 gripper state update, independent of Provider IO."""
import numpy as np

from .contracts import GripperControlTarget


def advance_r1_gripper(owner, feedback, gripper_scalar):
    """Advance an already validated R1 gripper owner and return its target."""
    cfg = owner.gripper_config
    opening = float(.5 * (gripper_scalar + 1) * owner.config.gripper_opening_range_m)
    delta = opening - owner._commanded
    if delta > 1e-12:
        owner._force_mode = False
        owner._force_initialized = False
    closing = delta < -1e-12
    measured = feedback.gripper.closing_force_N
    if closing and not owner._force_mode and measured >= max(.5, .1 * cfg.force_limit_N):
        owner._force_mode = True
    if closing and owner._force_mode:
        if not owner._force_initialized:
            owner._commanded = float(np.clip(feedback.gripper.opening_m
                - cfg.force_limit_N / owner.config.gripper_position_stiffness_N_per_m,
                0, owner.config.gripper_opening_range_m))
            owner._force_initialized = True
        if cfg.force_limit_N - measured > cfg.force_deadband_N:
            owner._commanded = float(max(0., owner._commanded - cfg.force_adjust_step_m))
    elif not owner._force_mode:
        owner._commanded = float(np.clip(owner._commanded + np.clip(delta,
            -cfg.opening_step_m, cfg.opening_step_m), 0, owner.config.gripper_opening_range_m))
    owner._desired = opening
    return GripperControlTarget(owner.gripper_semantic_id, opening, cfg.force_limit_N, owner._commanded)
