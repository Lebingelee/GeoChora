"""LIBERO pilot's task-local joint-space controller; no physics stepping."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from task_env.controllers.canonical.contracts import MixedActuatorCommandV1


_JOINTS = tuple(f'joint{i}' for i in range(1, 8))
_TORQUE_LIMITS = {**{f'joint{i}': 80.0 for i in range(1, 6)}, 'joint6': 12.0, 'joint7': 12.0}
_POSITION_LIMITS = {
    'joint1': (-2.8973, 2.8973), 'joint2': (-1.7628, 1.7628),
    'joint3': (-2.8973, 2.8973), 'joint4': (-3.0718, -0.0698),
    'joint5': (-2.8973, 2.8973), 'joint6': (-0.0175, 3.7525),
    'joint7': (-2.8973, 2.8973),
}
_GAIN_SOURCE = (
    'R07 task #1 failure-driven unqualified 20 Hz sample-and-hold experiment; '
    'not copied from or equivalent to upstream OSC_POSE'
)
_GAIN_STABILITY_RATIONALE = (
    'Native task #1 controller_tracking_001 used source gravity feed-forward with Kp=40/Kd=8 (joint2 Kd=16) '
    'and a four-segment unloaded joint-space setpoint sequence. Public TCP endpoint error stayed below the '
    'existing 12 mm waypoint tolerance, but independent H5 readback found 26 joint7 torque commands at its '
    'compiled +/-12 Nm limit and 0.112 rad maximum joint7 position error after the joint3 perturbation. '
    'Earlier native task1 run010 used Kp=20/Kd=4 (joint2 Kd=8), remained within source limits and emitted no '
    'MuJoCo warnings, but the task Solution entered descend near boundary900 and horizon-truncated. This '
    'unqualified v6 restores those lower gains so the same unloaded point-tracking probe can determine '
    'whether they avoid sustained joint7 saturation while meeting the point tolerance. The 20 Hz outer loop, '
    '2 ms x 25 hold, source motor ctrlranges, and source joint limits remain unchanged. This experiment is '
    'not a stability proof or controller qualification.'
)

_LEGACY_V2_PROFILE_RECORDS = {
    'libero-spatial-bowl-to-plate-joint-space-pd-v3': {
        'kp': (100.0,) * 7,
        'kd': (20.0, 40.0, 20.0, 20.0, 20.0, 20.0, 20.0),
        'rationale': (
            'Native R07 task #1 attempt006 reached 148 successful boundaries before joint2 crossed its source upper limit; '
            'attempt007 showed uniform Kp=200/Kd=40 saturated all seven torque channels and drove joint4 across its lower '
            'range within 10 boundaries. This unqualified follow-up restores uniform Kp=100 and Kd=20, raising Kd to 40 '
            'only for joint2, whose attempt006 public trace retained outward velocity while its target had already reversed. '
            'The source motor ctrlrange and joint limits remain unchanged; every torque remains clamped to the compiled '
            'source ctrlrange. This is a bounded control-parameter experiment, not a proof for the coupled 20 Hz '
            'sample-and-hold system or a controller qualification; native motion and fault gates remain required.'
        ),
    },
    'libero-spatial-bowl-to-plate-joint-space-pd-v4': {
        'kp': (20.0,) * 7,
        'kd': (4.0, 8.0, 4.0, 4.0, 4.0, 4.0, 4.0),
        'rationale': (
            'Native R07 task #1 run009 with source gravity feed-forward and Kp=100/Kd=20 (joint2 Kd=40) crossed '
            'joint3 by 0.004751 rad at boundary25 after several joints began oscillating and saturating. The prior '
            'v3 run008 without feed-forward reached boundary196 before joint2 crossed its upper source limit by '
            '0.002073 rad. This unqualified follow-up scales the gains fivefold down to Kp=20/Kd=4 (joint2 Kd=8) '
            'to test lower closed-loop bandwidth under the fixed 20 Hz outer loop and 2 ms x 25 hold. Source motor '
            'ctrlranges and joint limits remain unchanged; every torque remains clamped to the compiled source '
            'ctrlrange. This is an experiment, not a stability proof or controller qualification.'
        ),
    },
    'libero-spatial-bowl-to-plate-joint-space-pd-v5': {
        'kp': (40.0,) * 7,
        'kd': (8.0, 16.0, 8.0, 8.0, 8.0, 8.0, 8.0),
        'rationale': (
            'Native R07 task #1 run009 with source gravity feed-forward and Kp=100/Kd=20 (joint2 Kd=40) crossed '
            'joint3 by 0.004751 rad at boundary25 after several joints began oscillating and saturating. The prior '
            'v3 run008 without feed-forward reached boundary196 before joint2 crossed its upper source limit by '
            '0.002073 rad. Run010 with source gravity feed-forward and Kp=20/Kd=4 (joint2 Kd=8) remained within '
            'source limits and emitted no MuJoCo warnings, but all three episodes entered the descend stage only '
            'near boundary900 and horizon-truncated before task success. This unqualified follow-up doubles the '
            'gains to Kp=40/Kd=8 (joint2 Kd=16) while preserving the 20 Hz outer loop, 2 ms x 25 hold, and '
            '2 mm/10 mrad per-boundary motion caps to test reference tracking. Source motor ctrlranges and joint '
            'limits remain unchanged; every torque remains clamped to the compiled source ctrlrange. This is an '
            'experiment, not a stability proof or controller qualification.'
        ),
    },
    'libero-spatial-bowl-to-plate-joint-space-pd-v6': {
        'kp': (20.0,) * 7,
        'kd': (4.0, 8.0, 4.0, 4.0, 4.0, 4.0, 4.0),
        'rationale': _GAIN_STABILITY_RATIONALE,
    },
}


def legacy_v2_controller_identity_mapping(profile_id: str) -> dict:
    """Reconstruct only the frozen v2 controller identities emitted by v3-v6."""
    if type(profile_id) is not str or profile_id not in _LEGACY_V2_PROFILE_RECORDS:
        raise ValueError('legacy v2 Controller profile is not in the frozen v3-v6 allowlist')
    row = _LEGACY_V2_PROFILE_RECORDS[profile_id]
    kp, kd = tuple(row['kp']), tuple(row['kd'])
    rationale = row['rationale']
    material = {
        'schema_version': 'libero-mixed-controller-identity-v1',
        'profile_id': profile_id,
        'kp_Nm_per_rad': kp,
        'kd_Nm_s_per_rad': kd,
        'limits': {
            'arm_position_rad': _POSITION_LIMITS,
            'arm_torque_Nm': _TORQUE_LIMITS,
            'finger_position_m': {'finger_joint1': [0.0, 0.04],
                                  'finger_joint2': [-0.04, 0.0]},
        },
        'hold_policy': 'joint_torque_zero_order_hold_per_outer_step_v1',
        'gain_source': _GAIN_SOURCE,
        'gain_stability_rationale': rationale,
    }
    identity = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode()).hexdigest()
    return {
        'schema_version': 'libero-mixed-controller-identity-v1',
        'profile_id': profile_id,
        'identity_sha256': identity,
        'kp_Nm_per_rad': list(kp),
        'kd_Nm_s_per_rad': list(kd),
        'torque_limits_Nm': dict(_TORQUE_LIMITS),
        'position_limits_rad': {key: list(value) for key, value in _POSITION_LIMITS.items()},
        'hold_policy': 'joint_torque_zero_order_hold_per_outer_step_v1',
        'qualification': 'diagnostic_only_unqualified_gains',
        'gain_source': _GAIN_SOURCE,
        'gain_stability_rationale': rationale,
    }


@dataclass(frozen=True)
class LiberoMixedControlConfigV1:
    kp_Nm_per_rad: tuple[float, ...] = (20.0,) * 7
    kd_Nm_s_per_rad: tuple[float, ...] = (4.0, 8.0, 4.0, 4.0, 4.0, 4.0, 4.0)
    control_frequency_hz: int = 20
    physics_dt_s: float = 0.002
    control_substeps: int = 25
    hold_policy: str = 'joint_torque_zero_order_hold_per_outer_step_v1'
    gain_status: str = 'diagnostic_unqualified_PD_20Hz_kp20_kd4_8_v6'

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

    profile_id = 'libero-spatial-bowl-to-plate-joint-space-pd-v6'

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
        torques = self._compute_torques(positions, state)
        return MixedActuatorCommandV1(
            'mixed-actuator-command-v1', self.plan_identity_hash, task_artifact_hash,
            source_id, source_closure_digest, self.identity, provider_materialization_id,
            episode_id, reset_sample_id, int(state.control_step), int(state_revision),
            float(state.simulation_time),
            {**torques, 'finger_joint1': opening / 2.0, 'finger_joint2': -opening / 2.0},
            {**{name: 'N*m' for name in torques}, 'finger_joint1': 'm', 'finger_joint2': 'm'},
        )

    def _compute_torques(self, positions, state):
        """Shared task-owned torque hook; v1 retains its frozen PD-only law."""
        torques = {}
        for index, name in enumerate(_JOINTS):
            error = positions[index] - float(state.joint_position[name])
            velocity = float(state.joint_velocity[name])
            raw = self.config.kp_Nm_per_rad[index] * error - self.config.kd_Nm_s_per_rad[index] * velocity
            torques[name] = float(np.clip(raw, -_TORQUE_LIMITS[name], _TORQUE_LIMITS[name]))
        return torques

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


class LiberoMixedControllerV2(LiberoMixedControllerV1):
    """Versioned mixed controller with separate source gravity torque feed-forward."""

    profile_id = 'libero-spatial-bowl-to-plate-joint-space-pd-gravity-ff-v7'

    def __init__(self, config: LiberoMixedControlConfigV1 | None = None,
                 gravity_bias_model=None):
        super().__init__(config)
        self.gravity_bias_model = None
        self.last_control_receipt = None
        self.source_xml_sha256 = None
        self.source_closure_digest = None
        payload = super().identity_mapping()
        payload.pop('identity_sha256', None)
        payload.update({
            'schema_version': 'libero-mixed-controller-identity-v2',
            'profile_id': self.profile_id,
            'torque_law': 'kp_times_qdesired_minus_q_minus_kd_times_qdot_plus_source_gravity_ff_v1',
            'gravity_feedforward_profile_id': 'libero-source-mjcf-gravity-bias-v1',
            'position_target_encoding': 'absolute_qdesired_only_v1',
        })
        self.identity = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()
        if gravity_bias_model is not None:
            self.set_source_gravity_model(
                gravity_bias_model,
                source_xml_sha256=gravity_bias_model.source_xml_sha256,
                source_closure_digest=gravity_bias_model.source_closure_digest,
            )

    def set_source_gravity_model(self, model, *, source_xml_sha256: str,
                                 source_closure_digest: str):
        if self.gravity_bias_model is not None:
            raise RuntimeError('source gravity model may be attached only once')
        if (getattr(model, 'profile_id', None) != 'libero-source-mjcf-gravity-bias-v1'
                or not callable(getattr(model, 'gravity_torque', None))):
            raise TypeError('mixed controller requires the versioned source MJCF gravity primitive')
        if (getattr(model, 'source_xml_sha256', None) != source_xml_sha256
                or getattr(model, 'source_closure_digest', None) != source_closure_digest
                or type(source_xml_sha256) is not str or len(source_xml_sha256) != 64
                or type(source_closure_digest) is not str or len(source_closure_digest) != 64):
            raise ValueError('mixed controller source gravity model differs from its selected XML/closure')
        self.gravity_bias_model = model
        self.source_xml_sha256 = source_xml_sha256
        self.source_closure_digest = source_closure_digest

    def _compute_torques(self, positions, state):
        model = self.gravity_bias_model
        if model is None:
            raise RuntimeError('v2 mixed Controller requires its source gravity model before stepping')
        if (model.source_xml_sha256 != self.source_xml_sha256
                or model.source_closure_digest != self.source_closure_digest):
            raise ValueError('v2 mixed Controller source gravity identity changed after attachment')
        q = np.asarray([float(state.joint_position[name]) for name in _JOINTS], dtype=np.float64)
        qdot = np.asarray([float(state.joint_velocity[name]) for name in _JOINTS], dtype=np.float64)
        qdesired = np.asarray(positions, dtype=np.float64)
        bias = np.asarray(model.gravity_torque(q), dtype=np.float64)
        if any(value.shape != (7,) or not np.isfinite(value).all()
               for value in (q, qdot, qdesired, bias)):
            raise ValueError('v2 mixed Controller requires finite seven-joint q, qdot, qdesired and gravity bias')
        kp = np.asarray(self.config.kp_Nm_per_rad, dtype=np.float64)
        kd = np.asarray(self.config.kd_Nm_s_per_rad, dtype=np.float64)
        raw = kp * (qdesired - q) - kd * qdot + bias
        applied = np.asarray([
            np.clip(value, -_TORQUE_LIMITS[name], _TORQUE_LIMITS[name])
            for name, value in zip(_JOINTS, raw, strict=True)
        ], dtype=np.float64)
        clipped = np.abs(raw - applied) > 1e-12
        self.last_control_receipt = {
            'schema_version': 'libero-mixed-control-receipt-v2',
            'controller_identity': self.identity,
            'gravity_profile_id': model.profile_id,
            'gravity_model_identity_sha256': model.model_identity_sha256,
            'source_xml_sha256': self.source_xml_sha256,
            'source_closure_digest': self.source_closure_digest,
            'qdesired_rad': qdesired.tolist(),
            'q_rad': q.tolist(),
            'qdot_rad_s': qdot.tolist(),
            'gravity_feedforward_Nm': bias.tolist(),
            'raw_torque_Nm': raw.tolist(),
            'applied_torque_Nm': applied.tolist(),
            'torque_clipped': clipped.tolist(),
            'torque_clip_any': bool(clipped.any()),
            'channel_order': list(_JOINTS),
        }
        return {name: float(value) for name, value in zip(_JOINTS, applied, strict=True)}

    def identity_mapping(self):
        payload = super().identity_mapping()
        payload.pop('identity_sha256', None)
        payload.update({
            'schema_version': 'libero-mixed-controller-identity-v2',
            'profile_id': self.profile_id,
            'identity_sha256': self.identity,
            'torque_law': 'kp_times_qdesired_minus_q_minus_kd_times_qdot_plus_source_gravity_ff_v1',
            'gravity_feedforward_profile_id': 'libero-source-mjcf-gravity-bias-v1',
            'position_target_encoding': 'absolute_qdesired_only_v1',
        })
        return payload

    def close_resources(self):
        model = self.gravity_bias_model
        if model is None:
            return {
                'schema_version': 'libero-source-gravity-model-close-v1',
                'profile_id': 'libero-source-mjcf-gravity-bias-v1',
                'model_created': False, 'forward_call_count': 0,
                'mj_step_call_count': 0, 'closed': True,
                'model_released': True, 'data_released': True,
            }
        receipt = model.close()
        self.gravity_bias_model = None
        self.source_xml_sha256 = None
        self.source_closure_digest = None
        return receipt


__all__ = ['LiberoMixedControlConfigV1', 'LiberoMixedControllerV1',
           'LiberoMixedControllerV2', 'legacy_v2_controller_identity_mapping',
           'build_controller']
