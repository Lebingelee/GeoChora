"""LIBERO pilot's task-local joint-space controller; no physics stepping."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from task_env.controllers.canonical.contracts import MixedActuatorTargetV1


_JOINTS = tuple(f'joint{i}' for i in range(1, 8))
_TORQUE_LIMITS = {**{f'joint{i}': 80.0 for i in range(1, 6)}, 'joint6': 12.0, 'joint7': 12.0}
_POSITION_LIMITS = {
    'joint1': (-2.8973, 2.8973), 'joint2': (-1.7628, 1.7628),
    'joint3': (-2.8973, 2.8973), 'joint4': (-3.0718, -0.0698),
    'joint5': (-2.8973, 2.8973), 'joint6': (-0.0175, 3.7525),
    'joint7': (-2.8973, 2.8973),
}
_GAIN_SOURCE = (
    'explicit D01 bounded diagnostic choice; not copied from or equivalent to the upstream OSC_POSE controller'
)
_GAIN_STABILITY_RATIONALE = (
    'The unsaturated continuous joint-space error model has positive diagonal Kp and Kd; with a positive-definite '
    'Panda mass matrix its linearized second-order dynamics are dissipative and asymptotically stable. A planned '
    '0.08 rad setpoint change gives a 1.6 Nm proportional component at the source-state baseline, below the smallest '
    '12 Nm source motor limit; actual tracking error may differ, and the adapter clamps every torque to the compiled '
    'source ctrlrange. This is a bounded engineering rationale, not a proof for the saturated coupled 20 Hz '
    'sample-and-hold system or a controller qualification; native motion and fault gates remain required.'
)


@dataclass(frozen=True)
class LiberoMixedControlConfigV1:
    kp_Nm_per_rad: tuple[float, ...] = (20.0,) * 7
    kd_Nm_s_per_rad: tuple[float, ...] = (4.0,) * 7
    control_frequency_hz: int = 20
    physics_dt_s: float = 0.002
    control_substeps: int = 25
    hold_policy: str = 'joint_torque_zero_order_hold_per_outer_step_v1'
    gain_status: str = 'diagnostic_unqualified_PD_20Hz'

    def validate(self):
        if (len(self.kp_Nm_per_rad), len(self.kd_Nm_s_per_rad)) != (7, 7):
            raise ValueError('LIBERO mixed controller requires seven named PD gains')
        if any(not math.isfinite(float(value)) or value <= 0
               for value in (*self.kp_Nm_per_rad, *self.kd_Nm_s_per_rad)):
            raise ValueError('LIBERO mixed controller gains must be positive and finite')
        if (self.control_frequency_hz, self.physics_dt_s, self.control_substeps) != (20, 0.002, 25):
            raise ValueError('LIBERO mixed controller is fixed to 20 Hz and 2 ms x 25')
        if self.hold_policy != 'joint_torque_zero_order_hold_per_outer_step_v1':
            raise ValueError('unsupported LIBERO mixed torque hold policy')


class LiberoMixedControllerV1:
    """Map absolute joint targets to seven torques and two signed finger positions."""

    profile_id = 'libero-spatial-bowl-to-plate-joint-space-pd-v1'

    def __init__(self, config: LiberoMixedControlConfigV1 | None = None):
        self.config = config or LiberoMixedControlConfigV1()
        self.config.validate()
        material = {
            'schema_version': 'libero-mixed-controller-identity-v1',
            'profile_id': self.profile_id,
            'kp_Nm_per_rad': self.config.kp_Nm_per_rad,
            'kd_Nm_s_per_rad': self.config.kd_Nm_s_per_rad,
            'limits': {'arm_position_rad': _POSITION_LIMITS,
                       'arm_torque_Nm': _TORQUE_LIMITS,
                       'finger_position_m': {'finger_joint1': [0.0, 0.04],
                                             'finger_joint2': [-0.04, 0.0]}},
            'hold_policy': self.config.hold_policy,
            'gain_source': _GAIN_SOURCE,
            'gain_stability_rationale': _GAIN_STABILITY_RATIONALE,
        }
        self.identity = hashlib.sha256(json.dumps(
            material, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()
        self._last_boundary = None

    def reset(self, state):
        if set(_JOINTS) - set(state.joint_position) or set(_JOINTS) - set(state.joint_velocity):
            raise ValueError('LIBERO controller reset state omits named Panda arm feedback')
        self._last_boundary = (int(state.control_step), float(state.simulation_time))

    def compute_target(self, action, state, *, task_artifact_hash, source_id,
                       source_closure_digest, provider_materialization_id,
                       episode_id, reset_sample_id, state_revision):
        values = np.asarray(action, dtype=np.float64)
        if values.shape != (8,) or not np.isfinite(values).all():
            raise ValueError('LIBERO mixed action must contain eight finite joint/opening values')
        positions = tuple(float(values[index]) for index in range(7))
        opening = float(values[7])
        if not 0.0 <= opening <= 0.08:
            raise ValueError('aggregate finger opening must lie in [0, 0.08] m')
        for name, target in zip(_JOINTS, positions, strict=True):
            low, high = _POSITION_LIMITS[name]
            if not low <= target <= high:
                raise ValueError(f'joint target is outside the named source limit: {name}')
        torques = {}
        for index, name in enumerate(_JOINTS):
            error = positions[index] - float(state.joint_position[name])
            velocity = float(state.joint_velocity[name])
            raw = self.config.kp_Nm_per_rad[index] * error - self.config.kd_Nm_s_per_rad[index] * velocity
            torques[name] = float(np.clip(raw, -_TORQUE_LIMITS[name], _TORQUE_LIMITS[name]))
        return MixedActuatorTargetV1(
            'mixed-actuator-target-v1', task_artifact_hash, source_id,
            source_closure_digest, self.identity, provider_materialization_id,
            episode_id, reset_sample_id, int(state.control_step), int(state_revision),
            float(state.simulation_time), torques,
            {'finger_joint1': opening / 2.0, 'finger_joint2': -opening / 2.0},
        )

    def identity_mapping(self):
        return {
            'schema_version': 'libero-mixed-controller-identity-v1',
            'profile_id': self.profile_id,
            'identity_sha256': self.identity,
            'kp_Nm_per_rad': list(self.config.kp_Nm_per_rad),
            'kd_Nm_s_per_rad': list(self.config.kd_Nm_s_per_rad),
            'torque_limits_Nm': dict(_TORQUE_LIMITS),
            'position_limits_rad': {key: list(value) for key, value in _POSITION_LIMITS.items()},
            'hold_policy': self.config.hold_policy,
            'qualification': 'diagnostic_only_unqualified_gains',
            'gain_source': _GAIN_SOURCE,
            'gain_stability_rationale': _GAIN_STABILITY_RATIONALE,
        }


def build_controller(task_input: dict) -> dict:
    native = task_input['native_reference']['controller']
    config = LiberoMixedControlConfigV1()
    config.validate()
    return {
        'schema_version': 'libero-mixed-control-plan-v1',
        'control_frequency_hz': 20,
        'control_timestep_seconds': 0.05,
        'physics_dt_s': 0.002,
        'control_substeps': 25,
        'control_mode': 'absolute_joint_target_to_seven_torque_motors_plus_two_signed_finger_position_actuators',
        'hold_policy': config.hold_policy,
        'kp_Nm_per_rad': list(config.kp_Nm_per_rad),
        'kd_Nm_s_per_rad': list(config.kd_Nm_s_per_rad),
        'gain_status': config.gain_status,
        'gain_source': _GAIN_SOURCE,
        'gain_stability_rationale': _GAIN_STABILITY_RATIONALE,
        'native_reference': native,
        'core_equivalence': 'diagnostic joint-space profile; not OSC_POSE equivalence',
    }


__all__ = ['LiberoMixedControlConfigV1', 'LiberoMixedControllerV1', 'build_controller']
