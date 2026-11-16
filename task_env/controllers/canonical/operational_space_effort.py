"""Source-bound operational-space pose control through typed effort channels."""
from __future__ import annotations
import math
import numpy as np
from gymnasium.spaces import Box
from .contracts import digest
from .model import ControllerModelRequirementV1
from .physical_commands import ContributionPolicyV1, JointEffortV1, PhysicalCommandBatchV1, PhysicalCommandContextV1
from ...utils.rotation import quat_wxyz_to_matrix


class OperationalSpaceEffortControllerV1:
    """World TCP pose to seven named efforts at the external control cadence."""
    profile_id = 'source_osc_pose_v1'

    def __init__(self, binding, *, tcp_frame, cadence_s, kp=150., damping_ratio=.9, nullspace_kp=10.):
        channels = tuple(binding.channels)
        if (len(channels) != 7 or any(c.kind != 'revolute' or c.unit != 'N*m'
                or c.native_drive != 'disabled' for c in channels)
                or len({c.entity_id for c in channels}) != 1
                or any(c.owner_ids != channels[0].owner_ids for c in channels)
                or len(channels[0].owner_ids) != 1):
            raise ValueError('operational-space controller needs seven isolated arm channels')
        if any(not math.isfinite(float(x)) or float(x) <= 0 for x in (cadence_s, kp, damping_ratio, nullspace_kp)):
            raise ValueError('operational-space gains and cadence must be positive and finite')
        self.binding, self._channels = binding, channels
        from ...artifacts import FrameReference
        if type(tcp_frame) is not FrameReference or tcp_frame.entity_id != channels[0].entity_id:
            raise ValueError('operational-space TCP must be a declared subject frame')
        self.tcp_frame = tcp_frame
        self.writer_id = channels[0].owner_ids[0]
        self.cadence_s, self.kp, self.damping_ratio, self.nullspace_kp = map(
            float, (cadence_s, kp, damping_ratio, nullspace_kp))
        self.model_requirement = ControllerModelRequirementV1(
            'controller-model-requirement-v1', self.profile_id, 'mujoco-source-dynamics', 'v1',
            'named-arm-and-tcp-v1', binding.source_id, binding.source_closure_sha256,
            tuple(f'{c.entity_id}/{c.joint_id}' for c in channels), ('rad',) * 7,
            'operational_space_dynamics', ('N*m',) * 7, 'world', 'evaluation_boundary',
            self.cadence_s, 0., 'pure_no_physics_step', 'runtime-session', 'runtime-session', 'required')
        self.model_requirement.validate()
        self.identity = digest({'profile': self.profile_id, 'binding': binding.identity_hash,
            'model_requirement': self.model_requirement.identity_hash, 'kp': self.kp,
            'damping_ratio': self.damping_ratio, 'nullspace_kp': self.nullspace_kp,
            'tcp_frame': tcp_frame.to_mapping(), 'law': 'uncoupled-operational-inertia-qfrc-bias-zoh-v1'})
        self.action_space = Box(-np.inf, np.inf, (7,), dtype=np.float64)
        self._model = None
        self._episode = None
        self._reference = None
        self.last_action = None

    @property
    def action_shape(self):
        return (7,)

    def bind_model(self, model):
        if (not callable(getattr(model, 'evaluate', None))
                or model.source_id != self.binding.source_id
                or model.source_closure_sha256 != self.binding.source_closure_sha256
                or model.tcp_frame != self.tcp_frame):
            raise ValueError('operational-space model differs from selected source')
        if self._model is not None:
            raise RuntimeError('operational-space model is already bound')
        self._model = model

    def release_model(self):
        self._model = None
        self._episode = None
        self._reference = None

    def _state(self, state):
        joints = {(j.entity_id, j.joint_id): j for j in state.joints}
        keys = [(c.entity_id, c.joint_id) for c in self._channels]
        if any(key not in joints for key in keys):
            raise ValueError('operational-space state lacks a declared arm joint')
        q = np.asarray([joints[key].position[0] for key in keys], dtype=np.float64)
        qd = np.asarray([joints[key].velocity[0] for key in keys], dtype=np.float64)
        if not np.isfinite(q).all() or not np.isfinite(qd).all():
            raise ValueError('operational-space joint state is not finite')
        return q, qd

    def reset_from_realized_state(self, state):
        if state.boundary.scene_identity_hash != self.binding.scene_sha256 or self._model is None:
            raise ValueError('operational-space reset requires its bound Scene and model')
        self._reference, _ = self._state(state)
        self._episode = state.boundary.episode_id
        self.last_action = None

    def validate_action(self, action):
        target = np.asarray(action, dtype=np.float64)
        if target.shape != (7,) or not np.isfinite(target).all() or np.linalg.norm(target[3:]) < 1e-12:
            raise ValueError('operational-space input requires a finite world pose quaternion')
        return target

    def compute(self, action, state, context):
        if (type(context) is not PhysicalCommandContextV1 or state.boundary != context.boundary
                or state.sample_clock != context.clock or context.boundary.episode_id != self._episode
                or (context.source_id, context.source_closure_sha256, context.artifact_sha256) !=
                   (self.binding.source_id, self.binding.source_closure_sha256, self.binding.artifact_sha256)
                or not math.isclose(context.cadence_s, self.cadence_s, rel_tol=0, abs_tol=1e-12)):
            raise ValueError('operational-space command has stale or foreign state')
        target = self.validate_action(action)
        rotation = quat_wxyz_to_matrix(target[3:] / np.linalg.norm(target[3:]))
        q, qd = self._state(state)
        values = self._model.evaluate(q, qd, state.boundary)
        if values['boundary'] != state.boundary or values['physics_steps'] != 0:
            raise ValueError('operational-space model returned stale or advancing state')
        mass, jac = np.asarray(values['mass']), np.asarray(values['jacobian'])
        bias, current = np.asarray(values['bias']), np.asarray(values['rotation'])
        position = np.asarray(values['position'])
        if (mass.shape != (7, 7) or jac.shape != (6, 7) or bias.shape != (7,)
                or current.shape != (3, 3) or position.shape != (3,)
                or any(not np.isfinite(v).all() for v in (mass, jac, bias, current, position))):
            raise ValueError('operational-space dynamics are malformed')
        frames = [item for item in state.frames if item.frame == self.tcp_frame]
        if len(frames) != 1:
            raise ValueError('operational-space state requires the declared TCP frame')
        actual = frames[0].pose_world
        public_rotation = quat_wxyz_to_matrix(np.asarray(actual.quaternion_wxyz, dtype=np.float64))
        if (np.linalg.norm(np.asarray(actual.position) - position) > .003
                or np.linalg.norm(public_rotation - current) > .05):
            raise ValueError('operational-space model TCP differs from public state')
        position_error = target[:3] - position
        rotation_error = .5 * sum((np.cross(current[:, i], rotation[:, i]) for i in range(3)), start=np.zeros(3))
        inv = np.linalg.inv(mass)
        jpos, jrot = jac[:3], jac[3:]
        full = np.linalg.pinv(jac @ inv @ jac.T)
        null = np.eye(7) - inv @ jac.T @ full @ jac
        velocity = jac @ qd
        kd = 2. * math.sqrt(self.kp) * self.damping_ratio
        force = np.r_[np.linalg.pinv(jpos @ inv @ jpos.T) @ (self.kp * position_error - kd * velocity[:3]),
                      np.linalg.pinv(jrot @ inv @ jrot.T) @ (self.kp * rotation_error - kd * velocity[3:])]
        null_torque = null.T @ mass @ (self.nullspace_kp * (self._reference - q)
                                      - 2. * math.sqrt(self.nullspace_kp) * qd)
        torque = jac.T @ force + null_torque + bias
        if not np.isfinite(torque).all():
            raise ValueError('operational-space controller produced nonfinite effort')
        self.last_action = target.copy()
        efforts = []
        for index, (channel, value) in enumerate(zip(self._channels, torque, strict=True)):
            policy = ContributionPolicyV1('physical-contribution-policy-v1', f'{self.writer_id}/channel-{index}',
                f'{self.writer_id}/effect-{index}', self.writer_id, 'exclusive', 'clip_after_sum', 'one_interval')
            efforts.append(JointEffortV1('joint-effort-v1', context, policy, channel.entity_id,
                channel.joint_id, channel.dof_id, channel.kind, channel.axis, channel.axis_frame,
                channel.sign, channel.unit, float(value), channel.effort_range, 'explicit_full_pd'))
        return PhysicalCommandBatchV1('physical-command-batch-v1', context, tuple(efforts), (), ())
