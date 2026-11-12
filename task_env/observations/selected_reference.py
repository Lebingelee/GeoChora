"""Observation and task-evaluation projection for selected scalar routes."""

from collections import OrderedDict
from collections.abc import Mapping

import numpy as np
from ..environment.gym_compat import Box, Dict

from ..artifacts import CanonicalStateView
from ..environment.reference_binding import evaluate_task_definition


def switch_observation_space():
    """The opt-in, provider-independent PickCube state projection."""
    return Dict({
        'state': Dict({
            'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
            'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
            'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
            'boundary_identity_sha256': Box(0, 255, (32,), dtype=np.uint8),
        }),
        'privileged_state': Dict({'cube_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32)}),
    })


def selected_reference_observation_spaces(env):
    """Build the existing Panda reference projection; mixed tasks own their spaces."""
    keys = [key for _, key in env.binding.object_poses]
    state_spaces = {'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32)}
    if env.position_profile:
        state_spaces.update({
            'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
            'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
            'boundary_identity_sha256': Box(0, 255, (32,), dtype=np.uint8),
        })
        if env.dual_entity_position:
            state_spaces['entities'] = Dict({
                profile.entity_id: Dict({
                    'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
                    'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                })
                for profile in env.position_profiles
            })
    observation_spaces = OrderedDict((
        ('state', Dict(state_spaces)),
        ('privileged_state', Dict({
            k + '_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32)
            for k in keys
        })),
    ))
    return observation_spaces


def selected_reference_observation_schema(env, observation=None):
    """Describe the exact selected Env projection and any fixed task camera."""
    from ..environment.types import ObservationFieldSpec, ObservationSchema

    spaces = env.observation_space.spaces
    fields = []
    declared_only = object()
    root_names = list(observation.keys()) if isinstance(observation, Mapping) else list(spaces)
    if getattr(env, '_task_rgb_config', None) is not None and 'task_rgb' not in root_names:
        root_names.append('task_rgb')
    if set(root_names) != set(spaces):
        raise ValueError('selected observation projection differs from its declared top-level space')

    def visit(path, value, space):
        nested = getattr(space, 'spaces', None)
        if isinstance(value, Mapping):
            if nested is None or set(value) != set(nested):
                raise ValueError(f'selected observation mapping {path!r} differs from its declared space')
            for name, item in value.items():
                visit(f'{path}.{name}' if path else str(name), item, nested[name])
            return
        if nested is not None and value is not declared_only:
            raise ValueError(f'selected observation leaf {path!r} is missing its declared mapping')
        if not hasattr(space, 'shape') or not hasattr(space, 'dtype'):
            raise TypeError(f'selected observation space leaf {path!r} has no typed shape/dtype')
        if value is not declared_only:
            array = np.asarray(value)
            if array.shape != tuple(space.shape) or np.dtype(array.dtype) != np.dtype(space.dtype):
                raise ValueError(f'selected observation leaf {path!r} differs from its declared shape/dtype')
        if path == 'task_rgb':
            semantic, unit, frame = ('synchronized task RGB image', 'normalized RGB [0,1]', 'camera pixel grid')
        elif path.endswith('ee_pose') or path.endswith('hand_pose'):
            semantic, unit, frame = ('measured pose [x,y,z,qw,qx,qy,qz]', 'm + unit quaternion', 'world')
        elif path.endswith('boundary_identity_sha256'):
            semantic, unit, frame = ('state boundary identity digest', 'uint8[0,255]', 'identity')
        else:
            semantic, unit, frame = (f'task-declared observation leaf {path}', 'task-defined', 'task-defined')
        fields.append(ObservationFieldSpec(
            path, tuple(space.shape), str(np.dtype(space.dtype)), semantic, unit, frame,
        ))

    for group in root_names:
        value = observation[group] if isinstance(observation, Mapping) and group in observation else declared_only
        visit(str(group), value, spaces[group])
    return ObservationSchema('selected-reference-observation-v1', tuple(fields),
                             groups=tuple(str(name) for name in root_names))


def selected_observation_binding():
    """Expose the existing selected observation space and state projection."""
    return {'observation_space_factory': selected_reference_observation_spaces,
            'observation_projection': build_selected_observation}


def _position_task_evaluation_state(state, adapted):
    """Merge Position publication fields into the existing v0 task-state contract."""
    return CanonicalStateView(
        schema_version='canonical-state-v0',
        convention=state.convention,
        control_step=state.control_step,
        simulation_time=state.simulation_time,
        joint_position={**state.joint_position, **adapted.joint_position},
        joint_velocity={**state.joint_velocity, **adapted.joint_velocity},
        pose_world={**state.pose_world, **adapted.pose_world},
    )


def build_selected_observation(self, state):
    if getattr(self, 'position_profile', False):
        adapted = self.position_profiles[0]._adapt_publication(self.typed_state)
        evaluation_state = _position_task_evaluation_state(state, adapted)
        evaluation = evaluate_task_definition(self, evaluation_state)
        ee = adapted.pose_world['panda-v1/ee']
    else:
        evaluation = evaluate_task_definition(self, state)
        ee = state.pose_world['panda-v1/ee']
    state_obs = {'ee_pose': np.array((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)}
    obs = {'state': state_obs, 'privileged_state': {}}
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
    for semantic, key in self.binding.object_poses:
        pose = state.pose_world[semantic]
        obs['privileged_state'][key + '_body_pose'] = np.array(
            [(*pose.position, *pose.quaternion_wxyz)], dtype=np.float32)
    info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
        'task_metrics': dict(evaluation.metrics), 'control_step': int(state.control_step),
        'simulation_time_s': float(state.simulation_time)}
    if getattr(self, 'position_profile', False):
        boundary = self.typed_state.view.boundary
        info['state_boundary_identity'] = boundary.to_mapping()
        info['state_boundary_id'] = boundary.boundary_id
        info['state_sample_clock'] = self.typed_state.view.sample_clock.to_mapping()
        if self.value.get('f06_pickcube_isaac_input') is not None:
            # The admitted USD route exposes the Core-owned typed
            # publication used by observations and Position control.
            info['canonical_state_view_v1'] = self.typed_state.view.to_mapping()
    if getattr(getattr(self, 'resolved_public_config', None), 'reset_profile', None) == 'pickcube-state-only-switch-v1':
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
