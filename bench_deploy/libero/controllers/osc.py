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

from bench_deploy.libero.controllers.source_gravity import (
    SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
)


_JOINTS = tuple(f'joint{i}' for i in range(1, 8))
_TORQUE_LIMITS = {**{f'joint{i}': 80.0 for i in range(1, 6)}, 'joint6': 12.0, 'joint7': 12.0}
class _SourceOSCController:
    """Shared source-bound OSC math and lifecycle for final task profiles."""

    profile_id = 'libero-spatial-bowl-to-plate-robosuite-osc-pose-source-v1'

    def __init__(self, operational_config: LiberoOperationalSpaceConfigV2,
                 gravity_bias_model=None, *, arm_resolver_identity: str | None = None):
        self.gravity_bias_model = None
        self.source_xml_sha256 = None
        self.source_closure_digest = None
        if gravity_bias_model is not None:
            self.set_source_gravity_model(
                gravity_bias_model,
                source_xml_sha256=gravity_bias_model.source_xml_sha256,
                source_closure_digest=gravity_bias_model.source_closure_digest,
            )
        if operational_config is None:
            raise TypeError('source OSC base requires an explicit physics-rate operational-space config')
        self.operational_config = operational_config
        self.operational_config.validate()
        if (arm_resolver_identity is not None
                and (type(arm_resolver_identity) is not str or len(arm_resolver_identity) != 64
                     or any(char not in '0123456789abcdef' for char in arm_resolver_identity))):
            raise ValueError('OSC Controller arm resolver identity must be a lowercase SHA-256')
        self.arm_resolver_identity = arm_resolver_identity
        self._arm_joint_semantics = tuple(f'panda-v1/joint{i}' for i in range(1, 8))
        self.control_joint_order = tuple(f'joint{i}' for i in range(1, 8))
        self.last_control_receipt = None
        self.identity = ''

    def _refresh_identity(self):
        payload = self.identity_mapping()
        payload.pop('identity_sha256', None)
        self.identity = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()

    def set_source_gravity_model(self, model, *, source_xml_sha256: str,
                                 source_closure_digest: str):
        if not callable(getattr(model, 'operational_space_state_v2', None)):
            raise TypeError('OSC Controller requires the source-bound operational-space state owner')
        if self.gravity_bias_model is not None:
            raise RuntimeError('source gravity model may be attached only once')
        if getattr(model, 'profile_id', None) != 'libero-source-mjcf-gravity-bias-v1':
            raise TypeError('mixed controller requires the versioned source MJCF gravity primitive')
        if (getattr(model, 'source_xml_sha256', None) != source_xml_sha256
                or getattr(model, 'source_closure_digest', None) != source_closure_digest
                or type(source_xml_sha256) is not str or len(source_xml_sha256) != 64
                or type(source_closure_digest) is not str or len(source_closure_digest) != 64):
            raise ValueError('mixed controller source gravity model differs from its selected XML/closure')
        self.gravity_bias_model = model
        self.source_xml_sha256 = source_xml_sha256
        self.source_closure_digest = source_closure_digest

    def reset(self, state):
        if set(_JOINTS) - set(state.joint_position) or set(_JOINTS) - set(state.joint_velocity):
            raise ValueError('LIBERO controller reset state omits named Panda arm feedback')

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
        source_state = model.operational_space_state_v2(q, qdot)
        if (source_state.get('schema_version') != 'libero-source-operational-space-state-v2'
                or source_state.get('profile_id') != SOURCE_OPERATIONAL_SPACE_PROFILE_V2
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

    def _nullspace_reference(self, current_q, resolved_target_q):
        """Return this profile's named OSC posture reference and its provenance."""
        return np.asarray(resolved_target_q, dtype=np.float64), 'resolved_pose_target_v1'

    def _source_feedforward_torque(self, source_state):
        return np.asarray(source_state['qfrc_bias_arm_Nm'], dtype=np.float64)

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
            'source_state_profile_id': SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
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


class _PhysicsRateOSCController(_SourceOSCController):
    """Physics-rate OSC base with reset-captured robosuite nullspace state."""

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
        # V6/V7 rebuild the final identity after selecting their profile. This
        # intermediate physics-rate identity is never consumed.
        self.identity = ''

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


class LiberoMixedControllerV6(_PhysicsRateOSCController):
    """Robosuite-aligned OSC compensation using the source model's qfrc_bias."""

    profile_id = 'libero-spatial-bowl-to-plate-robosuite-osc-pose-qfrc-bias-v1'
    OFFICIAL_REFERENCE_PROFILE_ID = (
        'libero-spatial-bowl-to-plate-robosuite-osc-pose-official-reference-qfrc-bias-v1'
    )

    def __init__(self, operational_config: LiberoOperationalSpaceConfigV2 | None = None,
                 gravity_bias_model=None, *, arm_resolver_identity: str | None = None,
                 nullspace_reference_joint_position_rad=None,
                 allow_unconverged_arm_resolution: bool = False):
        super().__init__(
            operational_config=operational_config,
            gravity_bias_model=gravity_bias_model,
            arm_resolver_identity=arm_resolver_identity,
            nullspace_reference_joint_position_rad=nullspace_reference_joint_position_rad,
            allow_unconverged_arm_resolution=allow_unconverged_arm_resolution,
        )
        self.profile_id = (
            self.OFFICIAL_REFERENCE_PROFILE_ID
            if self._configured_nullspace_reference is not None
            else type(self).profile_id
        )
        self._refresh_identity()

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


class LiberoMixedControllerV7(LiberoMixedControllerV6):
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
        self._last_target_control_step = None
        self._last_target_position = None
        self._last_target_rotation = None
        self._desired_tcp_twist_world = np.zeros(6, dtype=np.float64)
        self._refresh_identity()

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
            linear = self._bound_vector((position - self._last_target_position) / elapsed, 0.05)
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
        receipt = self.last_control_receipt
        receipt.update({
            'schema_version': 'libero-mixed-control-receipt-v7',
            'algorithm': 'source_osc_pose_pd_with_bounded_planner_twist_feedforward_qfrc_bias_v1',
            'desired_twist_source': 'successive_absolute_planner_targets_at_20hz_v1',
            'desired_twist_limits': {'linear_m_s': 0.05, 'angular_rad_s': 0.5},
            'desired_tcp_twist_world': self._desired_tcp_twist_world.tolist(),
        })
        return target

    def identity_mapping(self):
        payload = super().identity_mapping()
        payload.update({
            'schema_version': 'libero-mixed-controller-identity-v7',
            'profile_id': type(self).profile_id,
            'identity_sha256': self.identity,
            'algorithm': 'source_osc_pose_pd_with_bounded_planner_twist_feedforward_qfrc_bias_v1',
            'desired_twist_source': 'successive_absolute_planner_targets_at_20hz_v1',
            'desired_twist_limits': {'linear_m_s': 0.05, 'angular_rad_s': 0.5},
        })
        return payload


__all__ = [
    'LiberoMixedControllerV6', 'LiberoMixedControllerV7',
    'LiberoOperationalSpaceConfigV2',
]
