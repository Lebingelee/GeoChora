"""Panda reference observation fields and their typed state projection."""

from collections import OrderedDict

import numpy as np

from ..environment.gym_compat import Box, Dict


def reference_observation_spaces(env, *, include_robot_state=False):
    state_spaces = {'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32)}
    if env.position_profile or include_robot_state:
        state_spaces.update({
            'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
            'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
            'boundary_identity_sha256': Box(0, 255, (32,), dtype=np.uint8),
        })
        if env.dual_entity_position:
            state_spaces['entities'] = Dict(OrderedDict(
                (profile.entity_id, Dict(OrderedDict((
                    ('joint_position', Box(-np.inf, np.inf, (9,), dtype=np.float32)),
                    ('hand_pose', Box(-np.inf, np.inf, (7,), dtype=np.float32)),
                )))) for profile in env.position_profiles
            ))
    return state_spaces


def reference_observation_field_metadata(env):
    """Describe units and frames for the Robot's declared reference fields."""
    pose = ('measured pose [x,y,z,qw,qx,qy,qz]', 'm + unit quaternion', 'world')
    joints = ('measured joint positions', 'rad (arm), m (fingers)', 'joint coordinates')
    digest = ('state boundary identity digest', 'uint8[0,255]', 'identity')
    fields = {'state.ee_pose': pose, 'state.joint_position': joints,
              'state.hand_pose': pose, 'state.boundary_identity_sha256': digest}
    for profile in getattr(env, 'position_profiles', ()):
        prefix = f'state.entities.{profile.entity_id}'
        fields[f'{prefix}.joint_position'] = joints
        fields[f'{prefix}.hand_pose'] = pose
    return fields


def reference_observation_state(self, adapted):
    ee = adapted.pose_world['panda-v1/ee']
    state_obs = {'ee_pose': np.array((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)}
    if getattr(self, 'position_profile', False):
        view = self.typed_state.view
        boundary = view.boundary
        entity_states = {}
        for profile in self.position_profiles:
            joints = {
                value.joint_id: value for value in view.joints
                if value.entity_id == profile.entity_id
            }
            hand = next(
                value for value in view.frames
                if value.frame.entity_id == profile.entity_id
                and value.frame.frame_id == profile.hand_frame_id
            )
            entity_states[profile.entity_id] = {
                'joint_position': np.asarray([
                    joints[name].position[0]
                    for name in (*profile.joint_ids, *profile.finger_joint_ids)
                ], dtype=np.float32),
                'hand_pose': np.asarray(
                    (*hand.pose_world.position, *hand.pose_world.quaternion_wxyz),
                    dtype=np.float32,
                ),
            }
        primary_entity = self.position_profiles[0].entity_id
        identity_hex = boundary.boundary_id.removeprefix('state-boundary-')
        state_obs.update({
            'joint_position': entity_states[primary_entity]['joint_position'],
            'hand_pose': entity_states[primary_entity]['hand_pose'],
        })
        state_obs['boundary_identity_sha256'] = np.frombuffer(
            bytes.fromhex(identity_hex), dtype=np.uint8,
        ).copy()
        if self.dual_entity_position:
            state_obs['entities'] = entity_states
    return state_obs


def physical_reference_observation(robot, env, state, *, hand_frame_id):
    """Project the declared physical Panda without a Position Controller."""
    from ..artifacts import CanonicalStateView

    view = env.typed_state.view
    entity = robot.uid
    joints = {v.joint_id: v for v in view.joints if v.entity_id == entity}
    names = robot.physical_joint_names()
    if any(name not in joints for name in names):
        raise ValueError('Panda observation requires its named joints')
    hands = [v for v in view.frames if v.frame.entity_id == entity and v.frame.frame_id == hand_frame_id]
    if len(hands) != 1:
        raise ValueError('Panda observation requires one hand frame')
    hand = hands[0].pose_world
    adapted = CanonicalStateView(
        schema_version='canonical-state-v0', convention=state.convention,
        control_step=state.control_step, simulation_time=state.simulation_time,
        joint_position={**state.joint_position, **{f'{entity}/{n}': float(joints[n].position[0]) for n in names}},
        joint_velocity={**state.joint_velocity, **{f'{entity}/{n}': float(joints[n].velocity[0]) for n in names}},
        pose_world=dict(state.pose_world),
    )
    site = state.pose_world[f'{entity}/ee']
    boundary = view.boundary
    subject = {'ee_pose': np.asarray((*site.position, *site.quaternion_wxyz), dtype=np.float32),
               'joint_position': np.asarray([joints[n].position[0] for n in names], dtype=np.float32),
               'hand_pose': np.asarray((*hand.position, *hand.quaternion_wxyz), dtype=np.float32),
               'boundary_identity_sha256': np.frombuffer(bytes.fromhex(
                   boundary.boundary_id.removeprefix('state-boundary-')), dtype=np.uint8).copy()}
    info = {'state_boundary_identity': boundary.to_mapping(), 'state_boundary_id': boundary.boundary_id,
            'state_sample_clock': view.sample_clock.to_mapping()}
    return adapted, subject, info
