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
        elif env.fixed_attachment_leaf_position_profile and env.leaf_plan is not None:
            state_spaces['entities'] = Dict({
                'panda-arm': Dict({
                    'joint_position': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                    'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                }),
                'panda-hand': Dict({
                    'joint_position': Box(-np.inf, np.inf, (2,), dtype=np.float32),
                    'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                }),
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


def position_camera_observation_declaration(binding, config):
    """Declare the existing single-Panda Position camera observation leaves."""
    from ..environment.types import ObservationFieldSpec, ObservationSchema
    from .state import camera_observation_field_specs

    camera_fields = camera_observation_field_specs(config)
    groups = OrderedDict((name, OrderedDict()) for name in ('rgb', 'depth', 'entity_mask'))
    for field in camera_fields:
        group, camera_id = field.name.split('.', 1)
        if group == 'rgb':
            space = Box(0.0, 1.0, field.shape, dtype=np.float32)
        elif group == 'depth':
            space = Box(0.0, np.inf, field.shape, dtype=np.float32)
        else:
            space = Box(0, np.iinfo(np.uint32).max, field.shape, dtype=np.uint32)
        groups[group][camera_id] = space
    fields = [
        ObservationFieldSpec('state.ee_pose', (7,), 'float32', 'hand-origin TCP pose',
                             'm + unit quaternion', 'world'),
        ObservationFieldSpec('state.joint_position', (9,), 'float32',
                             'required Panda joint positions', 'rad + m', 'canonical joint coordinates'),
        ObservationFieldSpec('state.hand_pose', (7,), 'float32',
                             'provider-measured Panda hand pose', 'm + unit quaternion', 'world'),
        ObservationFieldSpec('state.boundary_identity_sha256', (32,), 'uint8',
                             'state boundary identity digest', 'uint8[0,255]', 'identity'),
    ]
    fields.extend(
        ObservationFieldSpec(
            f'privileged_state.{key}_body_pose', (1, 7), 'float32',
            f'{key} measured world pose', 'm + unit quaternion', 'world',
        ) for _, key in binding.object_poses
    )
    fields.extend(camera_fields)
    schema = ObservationSchema(
        'position-camera-observation-v1', tuple(fields),
        groups=('state', 'privileged_state', 'rgb', 'depth', 'entity_mask'),
    )
    return OrderedDict((name, Dict(values)) for name, values in groups.items()), schema


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
    if getattr(self, 'mixed_control_profile', False):
        result = self.binding.observe_mixed_control(self, state)
        if not isinstance(result, tuple) or len(result) != 3:
            raise TypeError('mixed-control observation hook must return observation, info, evaluation')
        obs, info, evaluation = result
        from ..environment.types import TaskEvaluation
        if not isinstance(obs, Mapping) or not isinstance(info, Mapping) or not isinstance(evaluation, TaskEvaluation):
            raise TypeError('mixed-control observation hook returned untyped values')
        contact = info.get('contact_summary_v2')
        if contact is not None:
            if not isinstance(contact, Mapping):
                raise TypeError('RuntimeSession contact summary must remain a mapping')
            source = self.value['source']
            expected = (
                source.scene_source.source_id, source.source_closure_digest,
                self.session.provider_materialization_id, self.session.episode_id,
                self.sample.sample_id, int(state.control_step),
                int(self.session.state_revision), float(state.simulation_time),
            )
            observed = (
                contact.get('source_id'), contact.get('source_closure_digest'),
                contact.get('provider_materialization_id'), contact.get('episode_id'),
                contact.get('reset_sample_id'), contact.get('control_step'),
                contact.get('state_revision'), contact.get('simulation_time_s'),
            )
            if observed != expected:
                raise ValueError('RuntimeSession contact summary is stale or belongs to another state revision')
        return dict(obs), dict(info), evaluation
    if getattr(self, 'position_profile', False):
        if getattr(self, 'leaf_position_profile', False):
            evaluation = evaluate_task_definition(self, state)
            frame_values = {
                (item.frame.entity_id, item.frame.frame_id): item
                for item in self.typed_state.view.frames
            }
            ee_key = (('panda-arm', 'link7')
                      if self.fixed_attachment_leaf_position_profile
                      else ('panda-main', 'link7'))
            ee_value = frame_values[ee_key].pose_world
            ee = ee_value
        else:
            adapted = self.controller._adapt_publication(self.typed_state)
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
        if getattr(self, 'leaf_position_profile', False):
            if self.fixed_attachment_leaf_position_profile:
                arm_joints = {value.joint_id: value for value in view.joints
                              if value.entity_id == 'panda-arm'}
                hand_joints = {value.joint_id: value for value in view.joints
                               if value.entity_id == 'panda-hand'}
                arm_pose = frame_values[('panda-arm', 'link7')].pose_world
                hand_pose = frame_values[('panda-hand', 'hand')].pose_world
                entity_states['panda-arm'] = {
                    'joint_position': np.asarray([
                        arm_joints[name].position[0] for name in (
                            'joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6', 'joint7',
                        )
                    ], dtype=np.float32),
                    'hand_pose': np.asarray((*arm_pose.position, *arm_pose.quaternion_wxyz), dtype=np.float32),
                }
                entity_states['panda-hand'] = {
                    'joint_position': np.asarray([
                        hand_joints[name].position[0] for name in ('finger_joint1', 'finger_joint2')
                    ], dtype=np.float32),
                    'hand_pose': np.asarray((*hand_pose.position, *hand_pose.quaternion_wxyz), dtype=np.float32),
                }
            else:
                entity_id = 'panda-main'
                joints = {value.joint_id: value for value in view.joints if value.entity_id == entity_id}
                hand = frame_values[(entity_id, 'hand')]
                entity_states[entity_id] = {
                    'joint_position': np.asarray([
                        *(joints[name].position[0] for name in (
                            'joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6', 'joint7',
                        )),
                        joints['finger_joint1'].position[0], joints['finger_joint2'].position[0],
                    ], dtype=np.float32),
                    'hand_pose': np.asarray(
                        (*hand.pose_world.position, *hand.pose_world.quaternion_wxyz), dtype=np.float32,
                    ),
                }
        else:
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
        primary_entity = (
            'panda-arm' if self.fixed_attachment_leaf_position_profile else 'panda-main'
        ) if self.leaf_position_profile else self.position_profiles[0].entity_id
        identity_hex = boundary.boundary_id.removeprefix('state-boundary-')
        if self.fixed_attachment_leaf_position_profile:
            state_obs['joint_position'] = np.concatenate((
                entity_states['panda-arm']['joint_position'],
                entity_states['panda-hand']['joint_position'],
            )).astype(np.float32, copy=False)
            state_obs['hand_pose'] = entity_states['panda-hand']['hand_pose']
            state_obs['entities'] = entity_states
        else:
            state_obs.update({
                'joint_position': entity_states[primary_entity]['joint_position'],
                'hand_pose': entity_states[primary_entity]['hand_pose'],
            })
        state_obs['boundary_identity_sha256'] = np.frombuffer(
            bytes.fromhex(identity_hex), dtype=np.uint8,
        ).copy()
        if self.dual_entity_position and not self.fixed_attachment_leaf_position_profile:
            state_obs['entities'] = entity_states
    for semantic, key in self.binding.object_poses:
        pose = state.pose_world[semantic]
        obs['privileged_state'][key + '_body_pose'] = np.array(
            [(*pose.position, *pose.quaternion_wxyz)], dtype=np.float32)
    info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
        'task_metrics': dict(evaluation.metrics), 'control_step': int(state.control_step),
        'simulation_time_s': float(state.simulation_time)}
    if getattr(self, 'position_profile', False):
        from ..environment.reference_binding import position_input_kind
        input_kind = position_input_kind(self.binding, self.value.get('versioned_position_input'))
        if input_kind == 'dg02_geophys':
            info.update({
                'task_success_semantics': 'raw_predicate_only',
                'raw_task_predicate': bool(evaluation.success),
                'lifecycle_valid_success': None,
                'lifecycle_valid_success_assessed': False,
                'lifecycle_terminated': bool(evaluation.failure),
            })
        boundary = self.typed_state.view.boundary
        info['state_boundary_identity'] = boundary.to_mapping()
        info['state_boundary_id'] = boundary.boundary_id
        info['state_sample_clock'] = self.typed_state.view.sample_clock.to_mapping()
        if self.value.get('f06_pickcube_isaac_input') is not None or input_kind in (
            'f04', 'f05', 'f05_native', 'dg02_geophys', 'dg04_isaac_native',
        ):
            # Versioned USD state-only routes expose the Core-owned typed
            # publication used by observations and Position control.
            info['canonical_state_view_v1'] = self.typed_state.view.to_mapping()
        if self.camera_observation_config is not None:
            from .capture import DynamicCameraObservationConsumerV1

            if self._camera_consumer is None:
                self._camera_consumer = DynamicCameraObservationConsumerV1(
                    config=self.camera_observation_config,
                    task_artifact_hash=self.artifact.identity_hash,
                    runtime_source=self.value['source'],
                    horizon=self.horizon,
                    session_factory=self._camera_session_factory,
                )
            leaves, capture_boundary = self._camera_consumer.capture(self.typed_state.view)
            obs.update(leaves)
            info['camera_observation_v1'] = capture_boundary.to_mapping()
            self.camera_observation_schema.validate(obs)
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
