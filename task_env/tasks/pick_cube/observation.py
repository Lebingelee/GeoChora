"""PickCube's opt-in state-only compatibility observation."""

from collections import OrderedDict

import numpy as np

from ...environment.gym_compat import Box, Dict
from ...observations.selected_reference import build_selected_observation


def switch_observation_space():
    """The opt-in, provider-independent PickCube state projection."""
    return Dict(OrderedDict((
        ('state', Dict(OrderedDict((
            ('ee_pose', Box(-np.inf, np.inf, (7,), dtype=np.float32)),
            ('joint_position', Box(-np.inf, np.inf, (9,), dtype=np.float32)),
            ('hand_pose', Box(-np.inf, np.inf, (7,), dtype=np.float32)),
            ('boundary_identity_sha256', Box(0, 255, (32,), dtype=np.uint8)),
        )))),
        ('privileged_state', Dict(OrderedDict((
            ('cube_body_pose', Box(-np.inf, np.inf, (1, 7), dtype=np.float32)),
        )))),
    )))


def build_switch_observation(self, state):
    obs, info, evaluation = build_selected_observation(self, state)
    state_obs = obs['state']
    names = tuple(f'panda-v1/joint{i}' for i in range(1, 8)) + (
        'panda-v1/finger_joint1', 'panda-v1/finger_joint2')
    if self.position_profile:
        joint_positions = state_obs['joint_position'].copy()
        boundary = self.typed_state.view.boundary
        velocities = {f'{j.entity_id}/{j.joint_id}': j.velocity[0]
                      for j in self.typed_state.view.joints}
    else:
        joint_positions = np.asarray([state.joint_position[name] for name in names], dtype=np.float32)
        velocities = state.joint_velocity
        boundary = self.session.state_boundary_identity()
    ee_pose = state_obs['ee_pose'].copy()
    obs = {'state': {'ee_pose': ee_pose, 'joint_position': joint_positions,
                     'hand_pose': ee_pose.copy(),
                     'boundary_identity_sha256': np.frombuffer(
                         bytes.fromhex(boundary.boundary_id.removeprefix('state-boundary-')),
                         dtype=np.uint8).copy()},
           'privileged_state': {'cube_body_pose': obs['privileged_state']['cube_v1_body_pose'].copy()}}
    info['state_boundary_identity'] = boundary.to_mapping()
    info['state_boundary_id'] = boundary.boundary_id
    info['measured_joint_velocity'] = [float(velocities[name]) for name in names]
    info['measured_joint_velocity_units'] = ['rad/s'] * 7 + ['m/s'] * 2
    info['observation_schema'] = 'pickcube-state-only-switch-v1'
    return obs, info, evaluation
