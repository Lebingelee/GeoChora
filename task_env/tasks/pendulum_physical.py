"""Pendulum's source-bound declaration for the shared physical RuntimeSession."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..artifacts import (ActionIntent, EntityDefinition, InitializationContract,
    SemanticDefinition, Timebase)
from ..artifacts.execution import ResetSampleV1, ResetPlanV1
from ..environment.task_source import TaskSourceV1, TaskArtifactDeclarationV1
from ..environment.types import TaskCompositionSpec, RuntimeSnapshot
from ..environment.reference_binding import ReferenceTaskBinding, observe_task_definition
from ..environment.gym_compat import Box, Dict
from ..robots.pendulum import PENDULUM_MJCF_XML, PendulumEntity, PENDULUM_ACTION_CONTRACT
from ..runtime.sessions.physical_control import build_existing_subject_effort
from ..runtime.sessions.declared_effort_source import (
    declared_effort_scene, compile_declared_effort_source,
)
from ..runtime.sessions.isaac_g05 import (
    G05_ISAAC_EFFORT_PROFILE, build_g05_isaac_runtime_source,
    ensure_g05_isaac_app_open, load_g05_isaac_delivery,
)
from .pendulum import (PENDULUM_TASK_UID, PENDULUM_SCENE_UID,
                       PENDULUM_SUCCESS_DEFINITION, PendulumTaskDefinition,
                       PendulumObservationBuilder, PENDULUM_TASK_SEMANTICS)

ENTITY = 'pendulum-v1'
JOINT = f'{ENTITY}/pendulum_hinge'



def _declaration(scene):
    entity = EntityDefinition(ENTITY, 'embodiment', 'inline://task-env/pendulum',
        ('pendulum-v1/pendulum_anchor', 'pendulum-v1/pendulum_link'), (JOINT,),
        'source_owned', 'source_owned', {})
    init = InitializationContract('initialization-v0', {}, {JOINT: 0.}, (), 'clear', 'source', 0)
    semantics = SemanticDefinition('semantics-v0', 'pendulum-task-definition-v1', (), (JOINT,),
                                   {}, PENDULUM_SUCCESS_DEFINITION)
    decl = TaskArtifactDeclarationV1('pendulum-physical-v1', PENDULUM_TASK_UID, 'v1', (entity,),
        ActionIntent('direct_joint_effort', None, 'none', 'joint_effort'), ('joint_state',),
        init, semantics, Timebase(.002, 25, .05), ('articulated_robot', 'joint_state_query'))
    source = TaskSourceV1(PENDULUM_TASK_UID, 'v1', scene.scene_id, (), None)
    artifact = decl.compile_v1(source, scene)
    return source, artifact


def _reset_plan(artifact, source, seed, sampled=None):
    angle, speed = (PENDULUM_TASK_SEMANTICS.sample_reset(np.random.default_rng(seed))
                    if sampled is None else sampled)
    row = json.dumps([float(angle), float(speed)], separators=(',', ':')).encode()
    sample = ResetSampleV1.create(schema_version='reset-sample-v1',
        task_artifact_hash=artifact.identity_hash, source_id=source.source_id,
        source_closure_digest=source.source_closure_digest,
        sampler_id='pendulum-uniform-angle-velocity', sampler_version='v1', task_seed=seed,
        init_row_index=0, init_row_sha256=hashlib.sha256(row).hexdigest(),
        joint_position={JOINT: float(angle)}, joint_velocity={JOINT: float(speed)},
        sampled_poses_world={}, poses_world={}, free_joint_velocity={},
        free_joint_velocity_frame='mujoco_world_linear_local_angular_v1', fixture_pose_world={},
        simulation_time_s=0., velocity_policy='named_qvel_and_free_joint_qvel_v1',
        control_policy='named_physical_effort_by_source_v1', initialization_order=(
            'sample_source_properties', 'native_preprocess', 'sample_task_placements',
            'restore_source_bound_state', 'forward_derived_state'), settle_steps=0)
    return ResetPlanV1('reset-plan-v1', sample, 'task_episode')


def _build(config, seed, sampled=None, *, provider='geophys', source_delivery_manifest=None):
    robot = PendulumEntity()
    scene = declared_effort_scene(robot, provider=provider,
        source_delivery_manifest=source_delivery_manifest)
    task_source, artifact = _declaration(scene)
    composition = TaskCompositionSpec(PENDULUM_TASK_UID, PENDULUM_SCENE_UID,
                                      success_definition=PENDULUM_SUCCESS_DEFINITION)
    source, execution_spec, closure = compile_declared_effort_source(
        robot=robot, scene=scene, artifact=artifact, task_source=task_source,
        composition=composition, config=config, provider=provider,
        source_delivery_manifest=source_delivery_manifest, seed=seed,
        base_dir=Path(__file__).resolve().parent)
    selected_profile_id = config.control.profile_id or 'direct_joint_effort_v1'
    physical = build_existing_subject_effort(robot, scene=scene, artifact=artifact,
        source=source, profile_id=selected_profile_id)
    controller = physical.controllers[0]
    return {'artifact': artifact, 'task_source': task_source, 'source': source,
        'controller': controller, 'solution': None, 'physical_execution': physical,
        'reset_plan': _reset_plan(artifact, source, seed, sampled), 'construction_id': 'pendulum-shared-physical-v1',
        'source_revision': scene.assets[0].source_revision or 'pendulum-inline-v1',
        'execution_spec_v1': execution_spec,
        'selected_controller_profile_id': selected_profile_id,
        'source_sha256': {'original': hashlib.sha256(
            PENDULUM_MJCF_XML.encode()).hexdigest(), 'projected_closure': closure},
        'resolved_configuration': {'physics_dt': .002, 'control_substeps': 25}}


def _observation_spaces(_env):
    return {'state': Dict({'proprioception': Box(-np.inf, np.inf, (3,), dtype=np.float32)})}


def _task_state(state):
    q = np.asarray([state.joint_position[JOINT]], dtype=np.float32)
    v = np.asarray([state.joint_velocity[JOINT]], dtype=np.float32)
    snapshot = RuntimeSnapshot(qpos=q, qvel=v, simulation_time=state.simulation_time)
    return snapshot


def reset_metadata(sample):
    return {'profile': 'pendulum_uniform_angle_velocity_v1',
        'angle_range_rad': [-np.pi, np.pi], 'angular_velocity_range_rad_s': [-1., 1.],
        'theta_rad': sample.joint_position[JOINT],
        'theta_dot_rad_s': sample.joint_velocity[JOINT]}


def task_binding(config, *, provider, backend, source_delivery_manifest=None):
    """Declare Pendulum semantics and source construction; Env owns lifecycle."""
    def build_seeded(_provider, _backend, seed, _horizon):
        return _build(config, seed, provider=provider,
                      source_delivery_manifest=source_delivery_manifest)
    def build_sampled(_provider, _backend, seed, _horizon, sampled):
        return _build(config, seed, sampled, provider=provider,
                      source_delivery_manifest=source_delivery_manifest)
    def reset_seed(seed):
        if type(seed) is not int or seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        return seed
    def space():
        return Dict({'torque': Box(-2., 2., (1,), dtype=np.float32)})
    sample_reset = PENDULUM_TASK_SEMANTICS.sample_reset
    task_definition = lambda _artifact: PendulumTaskDefinition(qpos_id=0, qvel_id=0)
    observation_schema = PendulumObservationBuilder(qpos_id=0, qvel_id=0).schema
    return ReferenceTaskBinding(build=lambda _provider: _build(
        config, 31, provider=provider, source_delivery_manifest=source_delivery_manifest),
        build_seeded=build_seeded, build_sampled=build_sampled,
        task_reset_sampler=sample_reset, task_reset_metadata=reset_metadata,
        task_definition_factory=task_definition, task_state_projection=_task_state,
        task_observation_schema=observation_schema,
        external_action_contract=PENDULUM_ACTION_CONTRACT,
        reset_sample=lambda _artifact, _seed: None, evaluate=lambda _state, _semantics: None,
        object_poses=(), external_actions=True, interval_mode='grouped', recorder_mode='execution',
        reset_seed=reset_seed, action_schema={'schema_id': 'task-env.pendulum.torque.v1',
            'schema_version': 'task-env-action-v1', 'mode': 'direct_torque',
            'components': ['torque'], 'low': -2., 'high': 2., 'unit': 'N*m'},
        action_space_factory=space, prepare_action=lambda value: value,
        observation_space_factory=_observation_spaces, observation_projection=observe_task_definition,
        physical_control_profile=lambda env: env.value['physical_execution'],
        physical_direct_effort_feedback=(config.control.profile_id in (None, 'direct_joint_effort_v1')),
        physical_terminate_on_success=True,
        physical_ignore_done=config.episode.ignore_done)
