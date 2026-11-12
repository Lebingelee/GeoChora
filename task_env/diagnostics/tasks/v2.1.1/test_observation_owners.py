"""Selected observation composition and declared schema contracts."""
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.environment.gym_compat import Box, Dict
from task_env.observations import selected_reference


def test_schema_is_available_before_a_sample_and_checks_nested_values():
    space = Dict({'state': Dict({'angle': Box(-1, 1, (2,), dtype=np.float32)}),
                  'privileged_state': Dict({})})
    env = SimpleNamespace(observation_space=space, _task_rgb_config=None)
    declaration = selected_reference.selected_reference_observation_schema(env)
    sample = {'state': {'angle': np.array([0, 1], dtype=np.float32)}, 'privileged_state': {}}
    actual_schema = selected_reference.selected_reference_observation_schema(env, sample)
    assert set(declaration.fields) == set(actual_schema.fields)
    actual_schema.validate(sample)
    assert declaration.fields[0].name == 'state.angle'
    with pytest.raises(ValueError, match='shape/dtype'):
        selected_reference.selected_reference_observation_schema(
            env, {'state': {'angle': np.array([0, 1], dtype=np.float64)}, 'privileged_state': {}})
    with pytest.raises(ValueError, match='mapping'):
        selected_reference.selected_reference_observation_schema(env, {'state': {}, 'privileged_state': {}})


def test_selected_composition_uses_robot_projection_without_panda_fields(monkeypatch):
    class Robot:
        def reference_observation_spaces(self, env, *, include_robot_state=False):
            return {'angle': Box(-1, 1, (1,), dtype=np.float32)}
        def reference_observation_state(self, env, state):
            return {'angle': np.array([0.5], dtype=np.float32)}

    binding = SimpleNamespace(robot=Robot(), object_poses=())
    env = SimpleNamespace(binding=binding, position_profile=False)
    state = SimpleNamespace(control_step=3, simulation_time=0.03)
    evaluation = SimpleNamespace(success=False, failure=False, metrics={})
    monkeypatch.setattr(selected_reference, 'evaluate_task_definition', lambda *_: evaluation)
    spaces = selected_reference.selected_reference_observation_spaces(env)
    observation, info, actual = selected_reference.build_selected_observation(env, state)
    assert set(spaces['state'].spaces) == set(observation['state']) == {'angle'}
    assert observation['state']['angle'].dtype == np.float32
    assert info['control_step'] == 3 and actual is evaluation


def test_pickcube_switch_keeps_compatibility_alias_and_boundary(monkeypatch):
    from task_env.tasks.pick_cube import observation as pick_observation

    identity = 'ab' * 32
    boundary = SimpleNamespace(boundary_id='state-boundary-' + identity,
                               to_mapping=lambda: {'boundary_id': identity})
    names = tuple(f'panda-v1/joint{i}' for i in range(1, 8)) + (
        'panda-v1/finger_joint1', 'panda-v1/finger_joint2')
    state = SimpleNamespace(joint_position={name: float(i) for i, name in enumerate(names)},
                            joint_velocity={name: float(i) / 10 for i, name in enumerate(names)})
    original = {'state': {'ee_pose': np.arange(7, dtype=np.float32)},
                'privileged_state': {'cube_v1_body_pose': np.ones((1, 7), dtype=np.float32)}}
    evaluation = object()
    monkeypatch.setattr(pick_observation, 'build_selected_observation',
                        lambda *_: (original, {}, evaluation))
    env = SimpleNamespace(position_profile=False,
                          session=SimpleNamespace(state_boundary_identity=lambda: boundary))
    obs, info, actual = pick_observation.build_switch_observation(env, state)
    assert pick_observation.switch_observation_space().contains(obs)
    np.testing.assert_array_equal(obs['privileged_state']['cube_body_pose'],
                                  original['privileged_state']['cube_v1_body_pose'])
    assert not np.shares_memory(obs['privileged_state']['cube_body_pose'],
                                original['privileged_state']['cube_v1_body_pose'])
    assert info['measured_joint_velocity_units'] == ['rad/s'] * 7 + ['m/s'] * 2
    assert info['state_boundary_id'] == boundary.boundary_id and actual is evaluation


def test_panda_and_task_field_declarations_match_space_and_schema():
    from task_env.robots.panda import PandaAgent

    binding = SimpleNamespace(robot=PandaAgent(), object_poses=(('cube-v1', 'cube_v1'),),
                              observation_metadata=None)
    env = SimpleNamespace(binding=binding, position_profile=False, position_profiles=(),
                          dual_entity_position=False, _task_rgb_config=None)
    env.observation_space = Dict(selected_reference.selected_reference_observation_spaces(env))
    obs = {'state': {'ee_pose': np.zeros(7, dtype=np.float32)},
           'privileged_state': {'cube_v1_body_pose': np.zeros((1, 7), dtype=np.float32)}}
    declared = selected_reference.selected_reference_observation_schema(env)
    sampled = selected_reference.selected_reference_observation_schema(env, obs)
    assert declared == sampled
    declared.validate(obs)
    fields = {f.name: f for f in declared.fields}
    assert fields['state.ee_pose'].frame == fields['privileged_state.cube_v1_body_pose'].frame == 'world'
    assert fields['privileged_state.cube_v1_body_pose'].unit == 'm + unit quaternion'


def test_renderer_publication_keeps_controller_state_and_rejects_stale(monkeypatch):
    from task_env import artifacts
    from task_env.environment.reference_env import SelectedReferenceEnv

    class Publication:
        def __init__(self, boundary):
            self.view = SimpleNamespace(boundary=boundary,
                sample_clock=SimpleNamespace(simulation_time_s=0.0),
                validate_against_scene=lambda _: None, validate_requirements=lambda _: None)
            self.lifetime = SimpleNamespace(may_be_retained=True)

    monkeypatch.setattr(artifacts, 'CanonicalStatePublicationV1', Publication)
    boundary = SimpleNamespace(control_step=0)
    publication = Publication(boundary)
    source = SimpleNamespace(scene_definition=object())
    env = object.__new__(SelectedReferenceEnv)
    env.artifact = SimpleNamespace(identity_hash='a' * 64,
        timebase=SimpleNamespace(control_dt=.01, physics_dt=.002, control_substeps=5))
    env.value = {'source': source}
    env.session = SimpleNamespace(state_boundary_identity=lambda: boundary,
                                  snapshot_v1=lambda **_: publication)
    env.state = SimpleNamespace(control_step=0, simulation_time=0.0)
    env._task_rgb_state_binding = (source, env.artifact.identity_hash,
                                   source.scene_definition, {}, {}, object(), None)
    controller_publication = env.typed_state = object()
    assert env._publish_task_rgb_typed_state(env.state) is publication
    assert env.typed_state is controller_publication
    with pytest.raises(ValueError, match='stale or differs from Runtime readback'):
        env._publish_task_rgb_typed_state(SimpleNamespace(control_step=1, simulation_time=0.0))
    assert env.typed_state is controller_publication and env._task_rgb_typed_state is None
