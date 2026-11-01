"""Task-local LIBERO joint and operational-space controllers; no physics stepping."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from task_env.artifacts import PoseWorld
from task_env.controllers.canonical.contracts import (
    CanonicalArmResolutionV1, MixedActuatorCommandV1,
)
from task_env.utils.rotation import quat_wxyz_to_matrix, rotation_vector_error

from .source_gravity import (
    SOURCE_OPERATIONAL_SPACE_PROFILE_V1, SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
)


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


@dataclass(frozen=True)
class LiberoOperationalSpaceConfigV1:
    """Fixed, task-local OSC_POSE gains and source-model boundary cadence."""

    position_kp_N_per_m: float = 150.0
    orientation_kp_Nm_per_rad: float = 150.0
    damping_ratio: float = 1.0
    nullspace_kp_per_s2: float = 10.0
    control_frequency_hz: int = 20
    physics_dt_s: float = 0.002
    control_substeps: int = 25
    hold_policy: str = 'torque_zero_order_hold_per_outer_step_v1'

    def validate(self):
        for value in (self.position_kp_N_per_m, self.orientation_kp_Nm_per_rad,
                      self.damping_ratio, self.nullspace_kp_per_s2):
            if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
                raise ValueError('LIBERO OSC gains must be finite and positive')
        if (self.control_frequency_hz, self.physics_dt_s, self.control_substeps) != (20, 0.002, 25):
            raise ValueError('LIBERO source OSC profile is fixed to 20 Hz and 2 ms x 25')
        if self.hold_policy != 'torque_zero_order_hold_per_outer_step_v1':
            raise ValueError('unsupported LIBERO source OSC torque hold policy')


class LiberoMixedControllerV3(LiberoMixedControllerV2):
    """Task-local source-bound OSC_POSE using only public boundary feedback."""

    profile_id = 'libero-spatial-bowl-to-plate-robosuite-osc-pose-source-v1'

    def __init__(self, operational_config: LiberoOperationalSpaceConfigV1 | None = None,
                 gravity_bias_model=None, *, arm_resolver_identity: str | None = None):
        # Keep the frozen V1 timebase validation and shared named channel map;
        # OSC gains and control law are separately versioned below.
        super().__init__(gravity_bias_model=gravity_bias_model)
        self.operational_config = operational_config or LiberoOperationalSpaceConfigV1()
        self.operational_config.validate()
        if (arm_resolver_identity is not None
                and (type(arm_resolver_identity) is not str or len(arm_resolver_identity) != 64
                     or any(char not in '0123456789abcdef' for char in arm_resolver_identity))):
            raise ValueError('OSC Controller arm resolver identity must be a lowercase SHA-256')
        self.arm_resolver_identity = arm_resolver_identity
        self._arm_joint_semantics = tuple(f'panda-v1/joint{i}' for i in range(1, 8))
        self.control_joint_order = tuple(f'joint{i}' for i in range(1, 8))
        self.last_control_receipt = None
        payload = {
            'schema_version': 'libero-mixed-controller-identity-v3',
            'profile_id': self.profile_id,
            'action_encoding': 'absolute_world_xyz_m_quaternion_wxyz_plus_normalized_gripper_v1',
            'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_nullspace_v1',
            'reference': {
                'repository': 'robosuite',
                'commit': 'fbee5844ff5632f5b5698e204ec5357ca50be0df',
                'implementation': 'OperationalSpaceController.run_controller',
            },
            'source_state_profile_id': SOURCE_OPERATIONAL_SPACE_PROFILE_V1,
            'tcp_site_name': 'gripper0_grip_site',
            'arm_resolver_identity': self.arm_resolver_identity,
            'arm_joint_order': list(self._arm_joint_semantics),
            'position_kp_N_per_m': self.operational_config.position_kp_N_per_m,
            'orientation_kp_Nm_per_rad': self.operational_config.orientation_kp_Nm_per_rad,
            'damping_ratio': self.operational_config.damping_ratio,
            'nullspace_kp_per_s2': self.operational_config.nullspace_kp_per_s2,
            'control_frequency_hz': self.operational_config.control_frequency_hz,
            'physics_dt_s': self.operational_config.physics_dt_s,
            'control_substeps': self.operational_config.control_substeps,
            'hold_policy': self.operational_config.hold_policy,
            'torque_limits_Nm': dict(_TORQUE_LIMITS),
            'qualification': 'diagnostic_only_source_bound_20hz_OSC',
        }
        self.identity = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()

    def set_source_gravity_model(self, model, *, source_xml_sha256: str,
                                 source_closure_digest: str):
        if not callable(getattr(model, 'operational_space_state_v1', None)):
            raise TypeError('OSC Controller requires the source-bound operational-space state owner')
        super().set_source_gravity_model(
            model, source_xml_sha256=source_xml_sha256,
            source_closure_digest=source_closure_digest,
        )

    def _source_operational_space_state(self, model, q, qdot):
        return model.operational_space_state_v1(q, qdot)

    def _source_state_contract(self):
        return ('libero-source-operational-space-state-v1', SOURCE_OPERATIONAL_SPACE_PROFILE_V1)

    def map_arm_target_to_control_order(self, arm_target):
        from task_env.controllers.canonical.contracts import CanonicalArmTargetV1

        if not isinstance(arm_target, CanonicalArmTargetV1):
            raise TypeError('OSC Controller requires the typed canonical Panda arm target')
        arm_target.validate()
        if (self.arm_resolver_identity is None
                or arm_target.controller_identity != self.arm_resolver_identity
                or arm_target.arm_joint_order != self._arm_joint_semantics):
            raise ValueError('OSC arm target resolver identity or named joint order differs from its binding')
        named = dict(zip(arm_target.arm_joint_order, arm_target.joint_position_rad, strict=True))
        return tuple(float(named[semantic]) for semantic in self._arm_joint_semantics)

    def compute_target(self, *args, **kwargs):
        raise TypeError(
            'OSC Controller requires a typed CanonicalArmResolutionV1 and absolute world-pose target'
        )

    def compute_pose_target(
        self, resolution: CanonicalArmResolutionV1, opening_m: float, state, *,
        task_artifact_hash, source_id, source_closure_digest,
        provider_materialization_id, episode_id, reset_sample_id, state_revision,
        desired_tcp_twist_world=None,
    ):
        if not isinstance(resolution, CanonicalArmResolutionV1):
            raise TypeError('OSC Controller requires a typed iterative canonical arm resolution')
        resolution.validate()
        if (not resolution.diagnostics.converged
                and not getattr(self, '_allow_unconverged_arm_resolution', False)):
            raise ValueError('OSC Controller refuses an unconverged canonical world-pose target')
        arm_target = resolution.target
        q_reference = np.asarray(self.map_arm_target_to_control_order(arm_target), dtype=np.float64)
        target_pose = arm_target.canonical_action.resolved_world_pose
        if not isinstance(target_pose, PoseWorld):
            raise TypeError('OSC Controller requires a typed absolute world-pose target')
        if (type(opening_m) not in (int, float) or not math.isfinite(float(opening_m))
                or not 0.0 <= float(opening_m) <= 0.08):
            raise ValueError('OSC Controller aggregate gripper opening must lie in [0, 0.08] m')
        model = self.gravity_bias_model
        if (model is None or model.source_xml_sha256 != self.source_xml_sha256
                or model.source_closure_digest != self.source_closure_digest
                or arm_target.source_xml_sha256 != self.source_xml_sha256
                or source_closure_digest != self.source_closure_digest):
            raise ValueError('OSC source model, target and selected RuntimeSource identities differ')

        q = np.asarray([float(state.joint_position[name]) for name in _JOINTS], dtype=np.float64)
        qdot = np.asarray([float(state.joint_velocity[name]) for name in _JOINTS], dtype=np.float64)
        if any(value.shape != (7,) or not np.isfinite(value).all()
               for value in (q, qdot, q_reference)):
            raise ValueError('OSC Controller requires finite named seven-joint feedback and reference')
        q_reference, q_reference_source = self._nullspace_reference(q, q_reference)
        if q_reference.shape != (7,) or not np.isfinite(q_reference).all():
            raise ValueError('OSC nullspace reference must be a finite named seven-joint vector')
        source_state = self._source_operational_space_state(model, q, qdot)
        expected_state_schema, expected_state_profile = self._source_state_contract()
        if (source_state.get('schema_version') != expected_state_schema
                or source_state.get('profile_id') != expected_state_profile
                or source_state.get('source_xml_sha256') != self.source_xml_sha256
                or source_state.get('source_closure_digest') != self.source_closure_digest
                or source_state.get('tcp_site_name') != 'gripper0_grip_site'):
            raise ValueError('source OSC state is not bound to the selected task XML/closure/TCP')

        current_position = np.asarray(source_state['site_position_world_m'], dtype=np.float64)
        current_rotation = np.asarray(source_state['site_rotation_world'], dtype=np.float64)
        public_pose = state.pose_world.get('panda-v1/ee')
        if not isinstance(public_pose, PoseWorld):
            raise TypeError('OSC Controller requires the public typed Panda TCP pose')
        public_position = np.asarray(public_pose.position, dtype=np.float64)
        public_rotation = quat_wxyz_to_matrix(np.asarray(public_pose.quaternion_wxyz, dtype=np.float64))
        public_pose_gap_m = float(np.linalg.norm(public_position - current_position))
        public_orientation_gap_rad = float(np.linalg.norm(rotation_vector_error(
            current_rotation, public_rotation,
        )))
        if public_pose_gap_m > 0.003 or public_orientation_gap_rad > 0.03:
            raise ValueError('public TCP feedback differs from the pinned source OSC FK state')

        target_position = np.asarray(target_pose.position, dtype=np.float64)
        target_rotation = quat_wxyz_to_matrix(np.asarray(target_pose.quaternion_wxyz, dtype=np.float64))
        position_error = target_position - current_position
        orientation_error = 0.5 * sum(
            (np.cross(current_rotation[:, axis], target_rotation[:, axis]) for axis in range(3)),
            start=np.zeros(3, dtype=np.float64),
        )
        jacobian = np.asarray(source_state['jacobian_world'], dtype=np.float64)
        mass = np.asarray(source_state['mass_matrix_arm'], dtype=np.float64)
        bias = self._source_feedforward_torque(source_state)
        if (jacobian.shape != (6, 7) or mass.shape != (7, 7) or bias.shape != (7,)
                or any(not np.isfinite(value).all() for value in (jacobian, mass, bias))):
            raise ValueError('source OSC dynamics have invalid dimensions or non-finite values')
        desired_twist = (np.zeros(6, dtype=np.float64) if desired_tcp_twist_world is None
                         else np.asarray(desired_tcp_twist_world, dtype=np.float64))
        if desired_twist.shape != (6,) or not np.isfinite(desired_twist).all():
            raise ValueError('OSC desired TCP twist must contain six finite world-frame values')
        mass_inv = np.linalg.inv(mass)
        j_pos, j_ori = jacobian[:3], jacobian[3:]
        lambda_full_inv = jacobian @ mass_inv @ jacobian.T
        lambda_pos_inv = j_pos @ mass_inv @ j_pos.T
        lambda_ori_inv = j_ori @ mass_inv @ j_ori.T
        lambda_full = np.linalg.pinv(lambda_full_inv)
        lambda_pos = np.linalg.pinv(lambda_pos_inv)
        lambda_ori = np.linalg.pinv(lambda_ori_inv)
        j_bar = mass_inv @ jacobian.T @ lambda_full
        nullspace = np.eye(7, dtype=np.float64) - j_bar @ jacobian

        config = self.operational_config
        kp_pos = float(config.position_kp_N_per_m)
        kp_ori = float(config.orientation_kp_Nm_per_rad)
        kd_pos = 2.0 * math.sqrt(kp_pos) * config.damping_ratio
        kd_ori = 2.0 * math.sqrt(kp_ori) * config.damping_ratio
        ee_velocity = jacobian @ qdot
        desired_force = kp_pos * position_error + kd_pos * (desired_twist[:3] - ee_velocity[:3])
        desired_moment = kp_ori * orientation_error + kd_ori * (desired_twist[3:] - ee_velocity[3:])
        decoupled_wrench = np.concatenate((lambda_pos @ desired_force, lambda_ori @ desired_moment))
        task_torque = jacobian.T @ decoupled_wrench

        kp_null = float(config.nullspace_kp_per_s2)
        kd_null = 2.0 * math.sqrt(kp_null)
        nullspace_pose_torque = mass @ (kp_null * (q_reference - q) - kd_null * qdot)
        nullspace_torque = nullspace.T @ nullspace_pose_torque
        raw_torque = task_torque + nullspace_torque + bias
        applied_torque = np.asarray([
            np.clip(value, -_TORQUE_LIMITS[name], _TORQUE_LIMITS[name])
            for name, value in zip(_JOINTS, raw_torque, strict=True)
        ], dtype=np.float64)
        clipped = np.abs(raw_torque - applied_torque) > 1e-12
        values = {name: float(value) for name, value in zip(_JOINTS, applied_torque, strict=True)}
        self.last_control_receipt = {
            'schema_version': 'libero-mixed-control-receipt-v3',
            'controller_identity': self.identity,
            'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_nullspace_v1',
            'source_state_profile_id': source_state['profile_id'],
            'source_model_identity_sha256': source_state['model_identity_sha256'],
            'source_xml_sha256': self.source_xml_sha256,
            'source_closure_digest': self.source_closure_digest,
            'tcp_site_name': source_state['tcp_site_name'],
            'canonical_arm_resolution': resolution.diagnostics.to_mapping(),
            'target_world_pose': {
                'position_m': list(target_pose.position),
                'quaternion_wxyz': list(target_pose.quaternion_wxyz),
            },
            'current_world_pose': {
                'position_m': current_position.tolist(),
                'rotation_matrix': current_rotation.tolist(),
            },
            'q_rad': q.tolist(),
            'qdot_rad_s': qdot.tolist(),
            'q_reference_rad': q_reference.tolist(),
            'q_reference_source': q_reference_source,
            'public_to_source_tcp_gap_m': public_pose_gap_m,
            'public_to_source_tcp_gap_rad': public_orientation_gap_rad,
            'position_error_m': position_error.tolist(),
            'orientation_error_rad_vector': orientation_error.tolist(),
            'ee_velocity': ee_velocity.tolist(),
            'desired_tcp_twist_world': desired_twist.tolist(),
            'mass_matrix_arm': mass.tolist(),
            'jacobian_world': jacobian.tolist(),
            'task_torque_Nm': task_torque.tolist(),
            'nullspace_torque_Nm': nullspace_torque.tolist(),
            'bias_minus_passive_Nm': bias.tolist(),
            'raw_torque_Nm': raw_torque.tolist(),
            'applied_torque_Nm': applied_torque.tolist(),
            'torque_clipped': clipped.tolist(),
            'torque_clip_any': bool(clipped.any()),
            'opening_m': float(opening_m),
            'channel_order': list(_JOINTS),
            'hold_policy': config.hold_policy,
        }
        controller_values = {
            **values,
            'finger_joint1': float(opening_m) / 2.0,
            'finger_joint2': -float(opening_m) / 2.0,
        }
        return MixedActuatorCommandV1(
            'mixed-actuator-command-v1', self.plan_identity_hash,
            task_artifact_hash, source_id, source_closure_digest, self.identity,
            provider_materialization_id, episode_id, reset_sample_id,
            int(state.control_step), int(state_revision), float(state.simulation_time),
            controller_values,
            {**{name: 'N*m' for name in values},
             'finger_joint1': 'm', 'finger_joint2': 'm'},
        )

    def _source_feedforward_torque(self, source_state):
        """Return the legacy V3-V5 source torque compensation vector."""
        return np.asarray(source_state['bias_minus_passive_arm_Nm'], dtype=np.float64)

    def _nullspace_reference(self, current_q, resolved_target_q):
        """Return this profile's named OSC posture reference and its provenance."""
        return np.asarray(resolved_target_q, dtype=np.float64), 'resolved_pose_target_v1'

    def identity_mapping(self):
        config = self.operational_config
        return {
            'schema_version': 'libero-mixed-controller-identity-v3',
            'profile_id': self.profile_id,
            'identity_sha256': self.identity,
            'action_encoding': 'absolute_world_xyz_m_quaternion_wxyz_plus_normalized_gripper_v1',
            'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_nullspace_v1',
            'reference': {
                'repository': 'robosuite',
                'commit': 'fbee5844ff5632f5b5698e204ec5357ca50be0df',
                'implementation': 'OperationalSpaceController.run_controller',
            },
            'source_state_profile_id': SOURCE_OPERATIONAL_SPACE_PROFILE_V1,
            'tcp_site_name': 'gripper0_grip_site',
            'arm_resolver_identity': self.arm_resolver_identity,
            'arm_joint_order': list(self._arm_joint_semantics),
            'position_kp_N_per_m': config.position_kp_N_per_m,
            'orientation_kp_Nm_per_rad': config.orientation_kp_Nm_per_rad,
            'damping_ratio': config.damping_ratio,
            'nullspace_kp_per_s2': config.nullspace_kp_per_s2,
            'control_frequency_hz': config.control_frequency_hz,
            'physics_dt_s': config.physics_dt_s,
            'control_substeps': config.control_substeps,
            'hold_policy': config.hold_policy,
            'torque_limits_Nm': dict(_TORQUE_LIMITS),
            'qualification': 'diagnostic_only_source_bound_20hz_OSC',
        }


@dataclass(frozen=True)
class LiberoOperationalSpaceConfigV2:
    """Source OSC gains with torque recomputation at every 2 ms substep."""

    position_kp_N_per_m: float = 150.0
    orientation_kp_Nm_per_rad: float = 150.0
    damping_ratio: float = 1.0
    nullspace_kp_per_s2: float = 10.0
    control_frequency_hz: int = 20
    physics_dt_s: float = 0.002
    control_substeps: int = 25
    hold_policy: str = 'torque_recomputed_each_physics_substep_v1'

    def validate(self):
        for value in (self.position_kp_N_per_m, self.orientation_kp_Nm_per_rad,
                      self.damping_ratio, self.nullspace_kp_per_s2):
            if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
                raise ValueError('LIBERO OSC gains must be finite and positive')
        if (self.control_frequency_hz, self.physics_dt_s, self.control_substeps) != (20, 0.002, 25):
            raise ValueError('LIBERO source OSC profile is fixed to 20 Hz and 2 ms x 25')
        if self.hold_policy != 'torque_recomputed_each_physics_substep_v1':
            raise ValueError('unsupported LIBERO physics-rate OSC recomputation policy')


class LiberoMixedControllerV4(LiberoMixedControllerV3):
    """Physics-rate OSC with the reset-captured robosuite nullspace reference."""

    profile_id = 'libero-spatial-bowl-to-plate-robosuite-osc-pose-source-v2'

    def __init__(self, operational_config: LiberoOperationalSpaceConfigV2 | None = None,
                 gravity_bias_model=None, *, arm_resolver_identity: str | None = None,
                 nullspace_reference_joint_position_rad=None,
                 allow_unconverged_arm_resolution: bool = False):
        super().__init__(
            operational_config=operational_config or LiberoOperationalSpaceConfigV2(),
            gravity_bias_model=gravity_bias_model,
            arm_resolver_identity=arm_resolver_identity,
        )
        if type(allow_unconverged_arm_resolution) is not bool:
            raise TypeError('unconverged arm-resolution policy must be bool')
        self._allow_unconverged_arm_resolution = allow_unconverged_arm_resolution
        configured_reference = None
        if nullspace_reference_joint_position_rad is not None:
            configured_reference = np.asarray(
                nullspace_reference_joint_position_rad, dtype=np.float64,
            )
            if configured_reference.shape != (7,) or not np.isfinite(configured_reference).all():
                raise ValueError('configured robosuite nullspace reference must contain seven finite joint values')
            configured_reference = configured_reference.copy()
            self.profile_id = 'libero-spatial-bowl-to-plate-robosuite-osc-pose-official-reference-v1'
        self._configured_nullspace_reference = configured_reference
        self._initial_joint_reference = None
        payload = self.identity_mapping()
        payload.pop('identity_sha256', None)
        if self._configured_nullspace_reference is None:
            payload.update({
                'schema_version': 'libero-mixed-controller-identity-v4',
                'profile_id': self.profile_id,
                'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_reset_nullspace_v2',
                'nullspace_reference_policy': 'initial_joint_position_captured_at_reset_v1',
                'hold_policy': self.operational_config.hold_policy,
            })
        else:
            payload.update({
                'schema_version': 'libero-mixed-controller-identity-v5',
                'profile_id': self.profile_id,
                'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_official_initial_joint_reference_v1',
                'nullspace_reference_policy': 'robosuite_controller_initial_joint_after_set_init_state_v1',
                'nullspace_reference_joint_position_rad': self._configured_nullspace_reference.tolist(),
                'hold_policy': self.operational_config.hold_policy,
            })
        self.identity = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()

    def reset(self, state):
        super().reset(state)
        initial = np.asarray([float(state.joint_position[name]) for name in _JOINTS], dtype=np.float64)
        if initial.shape != (7,) or not np.isfinite(initial).all():
            raise ValueError('physics-rate OSC reset requires finite named initial arm feedback')
        self._initial_joint_reference = (
            initial.copy() if self._configured_nullspace_reference is None
            else self._configured_nullspace_reference.copy()
        )

    def _nullspace_reference(self, current_q, resolved_target_q):
        if self._initial_joint_reference is None:
            raise RuntimeError('physics-rate OSC requires reset-captured initial_joint before stepping')
        if self._initial_joint_reference.shape != (7,):
            raise RuntimeError('physics-rate OSC initial_joint reference has an invalid shape')
        reference_profile = (
            'reset_initial_joint_v1' if self._configured_nullspace_reference is None
            else 'robosuite_controller_initial_joint_after_set_init_state_v1'
        )
        return self._initial_joint_reference.copy(), reference_profile

    def compute_pose_target(self, *args, **kwargs):
        target = super().compute_pose_target(*args, **kwargs)
        resolution = args[0] if args else kwargs.get('resolution')
        self.last_control_receipt.update({
            'schema_version': (
                'libero-mixed-control-receipt-v4'
                if self._configured_nullspace_reference is None
                else 'libero-mixed-control-receipt-v5'
            ),
            'algorithm': (
                'robosuite_osc_pose_uncoupled_lambda_and_reset_nullspace_v2'
                if self._configured_nullspace_reference is None else
                'robosuite_osc_pose_uncoupled_lambda_and_official_initial_joint_reference_v1'
            ),
            'nullspace_reference_policy': (
                'initial_joint_position_captured_at_reset_v1'
                if self._configured_nullspace_reference is None else
                'robosuite_controller_initial_joint_after_set_init_state_v1'
            ),
            'nullspace_reference_joint_position_rad': (
                None if self._configured_nullspace_reference is None
                else self._configured_nullspace_reference.tolist()
            ),
            'hold_policy': self.operational_config.hold_policy,
            'arm_resolution_diagnostics': (
                None if resolution is None else resolution.diagnostics.to_mapping()
            ),
            'allow_unconverged_arm_resolution': self._allow_unconverged_arm_resolution,
        })
        return target

    def identity_mapping(self):
        payload = super().identity_mapping()
        if self._configured_nullspace_reference is None:
            payload.update({
                'schema_version': 'libero-mixed-controller-identity-v4',
                'profile_id': self.profile_id,
                'identity_sha256': self.identity,
                'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_reset_nullspace_v2',
                'nullspace_reference_policy': 'initial_joint_position_captured_at_reset_v1',
                'hold_policy': self.operational_config.hold_policy,
            })
        else:
            payload.update({
                'schema_version': 'libero-mixed-controller-identity-v5',
                'profile_id': self.profile_id,
                'identity_sha256': self.identity,
                'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_official_initial_joint_reference_v1',
                'nullspace_reference_policy': 'robosuite_controller_initial_joint_after_set_init_state_v1',
                'nullspace_reference_joint_position_rad': self._configured_nullspace_reference.tolist(),
                'hold_policy': self.operational_config.hold_policy,
            })
        if self._allow_unconverged_arm_resolution:
            payload['arm_resolution_policy'] = (
                'allow_unconverged_ik_auxiliary_target_for_absolute_pose_osc_a_replay_v1'
            )
        return payload


class LiberoMixedControllerV5(LiberoMixedControllerV4):
    """V4 OSC with bounded planner-velocity feed-forward per outer boundary."""

    profile_id = 'libero-spatial-bowl-to-plate-osc-pose-velocity-feedforward-v1'

    def __init__(self, operational_config: LiberoOperationalSpaceConfigV2 | None = None,
                 gravity_bias_model=None, *, arm_resolver_identity: str | None = None,
                 allow_unconverged_arm_resolution: bool = False):
        super().__init__(
            operational_config=operational_config,
            gravity_bias_model=gravity_bias_model,
            arm_resolver_identity=arm_resolver_identity,
            allow_unconverged_arm_resolution=allow_unconverged_arm_resolution,
        )
        self._last_target_control_step = None
        self._last_target_position = None
        self._last_target_rotation = None
        self._desired_tcp_twist_world = np.zeros(6, dtype=np.float64)
        payload = self.identity_mapping()
        payload.pop('identity_sha256', None)
        payload.update({
            'schema_version': 'libero-mixed-controller-identity-v5',
            'profile_id': self.profile_id,
            'algorithm': 'source_osc_pose_pd_with_bounded_planner_twist_feedforward_v1',
            'desired_twist_source': 'successive_absolute_planner_targets_at_20hz_v1',
            'desired_twist_limits': {'linear_m_s': 0.05, 'angular_rad_s': 0.5},
            'hold_policy': self.operational_config.hold_policy,
        })
        self.identity = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()

    def reset(self, state):
        super().reset(state)
        self._last_target_control_step = None
        self._last_target_position = None
        self._last_target_rotation = None
        self._desired_tcp_twist_world = np.zeros(6, dtype=np.float64)

    @staticmethod
    def _bound_vector(value, maximum):
        magnitude = float(np.linalg.norm(value))
        return value if magnitude <= maximum or magnitude == 0.0 else value * (maximum / magnitude)

    def compute_pose_target(self, resolution, opening_m, state, **kwargs):
        if not isinstance(resolution, CanonicalArmResolutionV1):
            raise TypeError('velocity-feedforward OSC requires a typed canonical arm resolution')
        target_pose = resolution.target.canonical_action.resolved_world_pose
        if not isinstance(target_pose, PoseWorld):
            raise TypeError('velocity-feedforward OSC requires an absolute world pose target')
        step = int(state.control_step)
        position = np.asarray(target_pose.position, dtype=np.float64)
        rotation = quat_wxyz_to_matrix(np.asarray(target_pose.quaternion_wxyz, dtype=np.float64))
        if self._last_target_control_step is None:
            self._last_target_control_step = step
            self._last_target_position = position.copy()
            self._last_target_rotation = rotation.copy()
        elif step > self._last_target_control_step:
            elapsed = (step - self._last_target_control_step) / self.operational_config.control_frequency_hz
            linear = self._bound_vector(
                (position - self._last_target_position) / elapsed, 0.05,
            )
            angular = self._bound_vector(
                rotation_vector_error(self._last_target_rotation, rotation) / elapsed, 0.5,
            )
            self._desired_tcp_twist_world = np.concatenate((linear, angular))
            self._last_target_control_step = step
            self._last_target_position = position.copy()
            self._last_target_rotation = rotation.copy()
        elif step < self._last_target_control_step:
            raise ValueError('velocity-feedforward OSC observed a stale control boundary')
        target = super().compute_pose_target(
            resolution, opening_m, state,
            desired_tcp_twist_world=self._desired_tcp_twist_world,
            **kwargs,
        )
        self.last_control_receipt.update({
            'schema_version': 'libero-mixed-control-receipt-v5',
            'algorithm': 'source_osc_pose_pd_with_bounded_planner_twist_feedforward_v1',
            'desired_twist_source': 'successive_absolute_planner_targets_at_20hz_v1',
            'desired_twist_limits': {'linear_m_s': 0.05, 'angular_rad_s': 0.5},
            'desired_tcp_twist_world': self._desired_tcp_twist_world.tolist(),
        })
        return target

    def identity_mapping(self):
        payload = super().identity_mapping()
        payload.update({
            'schema_version': 'libero-mixed-controller-identity-v5',
            'profile_id': self.profile_id,
            'identity_sha256': self.identity,
            'algorithm': 'source_osc_pose_pd_with_bounded_planner_twist_feedforward_v1',
            'desired_twist_source': 'successive_absolute_planner_targets_at_20hz_v1',
            'desired_twist_limits': {'linear_m_s': 0.05, 'angular_rad_s': 0.5},
        })
        return payload


class LiberoMixedControllerV6(LiberoMixedControllerV4):
    """Robosuite-aligned OSC compensation using the source model's qfrc_bias."""

    profile_id = 'libero-spatial-bowl-to-plate-robosuite-osc-pose-qfrc-bias-v1'
    OFFICIAL_REFERENCE_PROFILE_ID = (
        'libero-spatial-bowl-to-plate-robosuite-osc-pose-official-reference-qfrc-bias-v1'
    )

    def __init__(self, operational_config: LiberoOperationalSpaceConfigV2 | None = None,
                 gravity_bias_model=None, *, arm_resolver_identity: str | None = None,
                 nullspace_reference_joint_position_rad=None):
        super().__init__(
            operational_config=operational_config,
            gravity_bias_model=gravity_bias_model,
            arm_resolver_identity=arm_resolver_identity,
            nullspace_reference_joint_position_rad=nullspace_reference_joint_position_rad,
        )
        self.profile_id = (
            self.OFFICIAL_REFERENCE_PROFILE_ID
            if self._configured_nullspace_reference is not None
            else type(self).profile_id
        )
        payload = self.identity_mapping()
        payload.pop('identity_sha256', None)
        self.identity = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()

    def _source_feedforward_torque(self, source_state):
        return np.asarray(source_state['qfrc_bias_arm_Nm'], dtype=np.float64)

    def set_source_gravity_model(self, model, *, source_xml_sha256: str,
                                 source_closure_digest: str):
        if not callable(getattr(model, 'operational_space_state_v2', None)):
            raise TypeError('qfrc_bias OSC Controller requires source operational-space state v2')
        super().set_source_gravity_model(
            model, source_xml_sha256=source_xml_sha256,
            source_closure_digest=source_closure_digest,
        )

    def _source_operational_space_state(self, model, q, qdot):
        return model.operational_space_state_v2(q, qdot)

    def _source_state_contract(self):
        return ('libero-source-operational-space-state-v2', SOURCE_OPERATIONAL_SPACE_PROFILE_V2)

    def compute_pose_target(self, *args, **kwargs):
        target = super().compute_pose_target(*args, **kwargs)
        receipt = self.last_control_receipt
        receipt['gravity_feedforward_Nm'] = receipt.pop('bias_minus_passive_Nm')
        receipt.update({
            'schema_version': 'libero-mixed-control-receipt-v6',
            'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_qfrc_bias_v1',
            'gravity_feedforward_source': 'qfrc_bias_arm_Nm',
        })
        return target

    def identity_mapping(self):
        payload = super().identity_mapping()
        profile = (
            self.OFFICIAL_REFERENCE_PROFILE_ID
            if getattr(self, '_configured_nullspace_reference', None) is not None
            else type(self).profile_id
        )
        payload.update({
            'schema_version': 'libero-mixed-controller-identity-v6',
            'profile_id': profile,
            'identity_sha256': self.identity,
            'algorithm': 'robosuite_osc_pose_uncoupled_lambda_and_qfrc_bias_v1',
            'source_state_profile_id': SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
            'gravity_feedforward_source': 'qfrc_bias_arm_Nm',
            'gravity_feedforward_receipt_field': 'gravity_feedforward_Nm',
            'gravity_feedforward_semantics': 'robosuite_qfrc_bias_without_qfrc_passive_v1',
        })
        return payload


class LiberoMixedControllerV7(LiberoMixedControllerV5):
    """Rim-path OSC with planner twist feed-forward and robosuite qfrc_bias."""

    profile_id = 'libero-spatial-bowl-to-plate-osc-pose-velocity-feedforward-qfrc-bias-v1'

    def __init__(self, operational_config: LiberoOperationalSpaceConfigV2 | None = None,
                 gravity_bias_model=None, *, arm_resolver_identity: str | None = None,
                 allow_unconverged_arm_resolution: bool = False):
        super().__init__(
            operational_config=operational_config,
            gravity_bias_model=gravity_bias_model,
            arm_resolver_identity=arm_resolver_identity,
            allow_unconverged_arm_resolution=allow_unconverged_arm_resolution,
        )
        self.profile_id = type(self).profile_id
        payload = self.identity_mapping()
        payload.pop('identity_sha256', None)
        self.identity = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()

    def _source_feedforward_torque(self, source_state):
        return np.asarray(source_state['qfrc_bias_arm_Nm'], dtype=np.float64)

    def set_source_gravity_model(self, model, *, source_xml_sha256: str,
                                 source_closure_digest: str):
        if not callable(getattr(model, 'operational_space_state_v2', None)):
            raise TypeError('qfrc_bias OSC Controller requires source operational-space state v2')
        super().set_source_gravity_model(
            model, source_xml_sha256=source_xml_sha256,
            source_closure_digest=source_closure_digest,
        )

    def _source_operational_space_state(self, model, q, qdot):
        return model.operational_space_state_v2(q, qdot)

    def _source_state_contract(self):
        return ('libero-source-operational-space-state-v2', SOURCE_OPERATIONAL_SPACE_PROFILE_V2)

    def compute_pose_target(self, *args, **kwargs):
        target = super().compute_pose_target(*args, **kwargs)
        receipt = self.last_control_receipt
        receipt['gravity_feedforward_Nm'] = receipt.pop('bias_minus_passive_Nm')
        receipt.update({
            'schema_version': 'libero-mixed-control-receipt-v7',
            'algorithm': 'source_osc_pose_pd_with_bounded_planner_twist_feedforward_qfrc_bias_v1',
            'gravity_feedforward_source': 'qfrc_bias_arm_Nm',
        })
        return target

    def identity_mapping(self):
        payload = super().identity_mapping()
        payload.update({
            'schema_version': 'libero-mixed-controller-identity-v7',
            'profile_id': type(self).profile_id,
            'identity_sha256': self.identity,
            'algorithm': 'source_osc_pose_pd_with_bounded_planner_twist_feedforward_qfrc_bias_v1',
            'source_state_profile_id': SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
            'gravity_feedforward_source': 'qfrc_bias_arm_Nm',
            'gravity_feedforward_receipt_field': 'gravity_feedforward_Nm',
            'gravity_feedforward_semantics': 'robosuite_qfrc_bias_without_qfrc_passive_v1',
        })
        return payload


__all__ = ['LiberoMixedControlConfigV1', 'LiberoMixedControllerV1',
           'LiberoMixedControllerV2', 'LiberoMixedControllerV3', 'LiberoMixedControllerV4',
           'LiberoMixedControllerV5', 'LiberoMixedControllerV6', 'LiberoMixedControllerV7',
           'LiberoOperationalSpaceConfigV1', 'LiberoOperationalSpaceConfigV2',
           'legacy_v2_controller_identity_mapping',
           'build_controller']
