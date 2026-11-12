"""Observation and task-evaluation projection for selected scalar routes."""

from collections import OrderedDict
from collections.abc import Mapping

import numpy as np
from ..environment.gym_compat import Box, Dict

from ..artifacts import CanonicalStateView
from ..environment.reference_binding import evaluate_task_definition


def selected_reference_observation_spaces(env, *, include_robot_state=False):
    """Compose the selected Robot projection with Task object spaces."""
    keys = [key for _, key in env.binding.object_poses]
    state_spaces = env.binding.robot.reference_observation_spaces(
        env, include_robot_state=include_robot_state)
    observation_spaces = OrderedDict((
        ('state', Dict(OrderedDict(state_spaces))),
        ('privileged_state', Dict(OrderedDict(
            (k + '_body_pose', Box(-np.inf, np.inf, (1, 7), dtype=np.float32))
            for k in keys
        ))),
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

    binding = getattr(env, 'binding', None)
    robot = getattr(binding, 'robot', None)
    describe_robot = getattr(robot, 'reference_observation_field_metadata', None)
    metadata = dict(describe_robot(env)) if callable(describe_robot) else {}
    for _semantic, key in getattr(binding, 'object_poses', ()):
        metadata[f'privileged_state.{key}_body_pose'] = (
            'task object pose [x,y,z,qw,qx,qy,qz]', 'm + unit quaternion', 'world')
    metadata.update((getattr(binding, 'observation_metadata', None) or {}).get('field_metadata', {}))
    metadata['task_rgb'] = ('synchronized task RGB image', 'normalized RGB [0,1]', 'camera pixel grid')

    def visit(path, value, space):
        nested = getattr(space, 'spaces', None)
        if nested is not None and value is declared_only:
            for name, child in nested.items():
                visit(f'{path}.{name}' if path else str(name), declared_only, child)
            return
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
        semantic, unit, frame = metadata.get(
            path, (f'task-declared observation leaf {path}', 'task-defined', 'task-defined'))
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
    else:
        evaluation = evaluate_task_definition(self, state)
        adapted = state
    state_obs = self.binding.robot.reference_observation_state(self, adapted)
    obs = {'state': state_obs, 'privileged_state': {}}
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
        if self.value.get('session_admission_input') is not None:
            # The admitted USD route exposes the Core-owned typed
            # publication used by observations and Position control.
            info['canonical_state_view_v1'] = self.typed_state.view.to_mapping()
    return obs, info, evaluation
