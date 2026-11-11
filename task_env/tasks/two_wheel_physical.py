"""Source-bound two-wheel declarations for the shared physical RuntimeSession."""
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
from ..robots.two_wheel_balance import TWO_WHEEL_BALANCE_MJCF_XML, TwoWheelBalanceEntity, TWO_WHEEL_ACTION_CONTRACT
from ..runtime.sessions.physical_control import build_existing_subject_effort
from ..runtime.sessions.declared_effort_source import (
    declared_effort_scene, compile_declared_effort_source,
)
from ..runtime.sessions.isaac_g05 import (
    G05_ISAAC_EFFORT_PROFILE, build_g05_isaac_runtime_source,
    ensure_g05_isaac_app_open, load_g05_isaac_delivery,
)
from .two_wheel_balance import (TWO_WHEEL_BALANCE_TASK_UID,
    TWO_WHEEL_BALANCE_SCENE_UID, TWO_WHEEL_BALANCE_SUCCESS_DEFINITION,
    TwoWheelBalanceTaskDefinition, TwoWheelBalanceObservationBuilder)

ENTITY = 'two-wheel-balance-v1'
NAMES = ('chassis_pitch', 'left_wheel_hinge', 'right_wheel_hinge')
JOINTS = tuple(f'{ENTITY}/{name}' for name in NAMES)
FRAMES = ('balance_anchor', 'balance_chassis', 'left_wheel', 'right_wheel')
ACTUATORS = ('left_wheel_torque', 'right_wheel_torque')



def _declaration(scene):
    entity = EntityDefinition(ENTITY, 'embodiment', 'inline://task-env/two-wheel-balance',
        tuple(f'{ENTITY}/{f}' for f in FRAMES), JOINTS, 'source_owned', 'source_owned', {})
    init = InitializationContract('initialization-v0', {}, {j: 0. for j in JOINTS}, (), 'clear', 'source', 0)
    semantics = SemanticDefinition('semantics-v0', 'two-wheel-task-definition-v1', (), JOINTS,
                                   {}, TWO_WHEEL_BALANCE_SUCCESS_DEFINITION)
    decl = TaskArtifactDeclarationV1('two-wheel-physical-v1', TWO_WHEEL_BALANCE_TASK_UID, 'v1', (entity,),
        ActionIntent('direct_joint_effort', None, 'none', 'joint_effort'), ('joint_state',), init, semantics,
        Timebase(.002, 25, .05), ('articulated_robot', 'joint_state_query'))
    task_source = TaskSourceV1(TWO_WHEEL_BALANCE_TASK_UID, 'v1', scene.scene_id, (), None)
    return task_source, decl.compile_v1(task_source, scene)


def sample_reset(rng):
    return (float(rng.uniform(-.08, .08)), float(rng.uniform(-.20, .20)),
            float(rng.uniform(-.02, .02)), float(rng.uniform(-.02, .02)),
            float(rng.uniform(-.30, .30)), float(rng.uniform(-.30, .30)))


def _reset_plan(artifact, source, seed, sampled):
    pitch, pitch_rate, left, right, left_rate, right_rate = sampled
    row = json.dumps([float(x) for x in sampled], separators=(',', ':')).encode()
    sample = ResetSampleV1.create(schema_version='reset-sample-v1', task_artifact_hash=artifact.identity_hash,
        source_id=source.source_id, source_closure_digest=source.source_closure_digest,
        sampler_id='two-wheel-uniform-perturbation', sampler_version='v1', task_seed=seed,
        init_row_index=0, init_row_sha256=hashlib.sha256(row).hexdigest(),
        joint_position=dict(zip(JOINTS, (pitch, left, right), strict=True)),
        joint_velocity=dict(zip(JOINTS, (pitch_rate, left_rate, right_rate), strict=True)),
        sampled_poses_world={}, poses_world={}, free_joint_velocity={},
        free_joint_velocity_frame='mujoco_world_linear_local_angular_v1', fixture_pose_world={},
        simulation_time_s=0., velocity_policy='named_qvel_and_free_joint_qvel_v1',
        control_policy='named_physical_effort_by_source_v1', initialization_order=(
            'sample_source_properties', 'native_preprocess', 'sample_task_placements',
            'restore_source_bound_state', 'forward_derived_state'), settle_steps=0)
    return ResetPlanV1('reset-plan-v1', sample, 'task_episode')


def _build(config, seed, sampled=None, *, provider='geophys', source_delivery_manifest=None):
    robot = TwoWheelBalanceEntity()
    scene = declared_effort_scene(robot, provider=provider,
        source_delivery_manifest=source_delivery_manifest)
    task_source, artifact = _declaration(scene)
    composition = TaskCompositionSpec(TWO_WHEEL_BALANCE_TASK_UID, TWO_WHEEL_BALANCE_SCENE_UID,
                                      success_definition=TWO_WHEEL_BALANCE_SUCCESS_DEFINITION)
    source, execution_spec, closure = compile_declared_effort_source(
        robot=robot, scene=scene, artifact=artifact, task_source=task_source,
        composition=composition, config=config, provider=provider,
        source_delivery_manifest=source_delivery_manifest, seed=seed,
        base_dir=Path(__file__).resolve().parent)
    selected_profile_id = config.control.profile_id or 'direct_joint_effort_v1'
    physical = build_existing_subject_effort(robot, scene=scene, artifact=artifact,
        source=source, profile_id=selected_profile_id)
    controller = physical.controllers[0]
    return {'artifact': artifact, 'task_source': task_source, 'source': source, 'controller': controller,
        'solution': None, 'physical_execution': physical,
        'reset_plan': _reset_plan(artifact, source, seed, sampled if sampled is not None else sample_reset(np.random.default_rng(seed))),
        'construction_id': 'two-wheel-shared-physical-v1',
        'source_revision': scene.assets[0].source_revision or 'two-wheel-inline-v1',
        'execution_spec_v1': execution_spec,
        'selected_controller_profile_id': selected_profile_id,
        'source_sha256': {'original': hashlib.sha256(TWO_WHEEL_BALANCE_MJCF_XML.encode()).hexdigest(),
                          'projected_closure': closure},
        'resolved_configuration': {'physics_dt': .002, 'control_substeps': 25}}


def _observation_spaces(_env):
    return {'state': Dict({'proprioception': Box(-np.inf, np.inf, (7,), dtype=np.float32)})}


def _task_state(state):
    snapshot = RuntimeSnapshot(qpos=np.asarray([state.joint_position[j] for j in JOINTS], dtype=np.float32),
        qvel=np.asarray([state.joint_velocity[j] for j in JOINTS], dtype=np.float32), simulation_time=state.simulation_time)
    return snapshot


def reset_metadata(sample):
    return {'profile': 'two_wheel_balance_uniform_perturbation_v1',
        'pitch_rad': sample.joint_position[JOINTS[0]],
        'pitch_rate_rad_s': sample.joint_velocity[JOINTS[0]],
        'left_wheel_position_rad': sample.joint_position[JOINTS[1]],
        'right_wheel_position_rad': sample.joint_position[JOINTS[2]],
        'left_wheel_rate_rad_s': sample.joint_velocity[JOINTS[1]],
        'right_wheel_rate_rad_s': sample.joint_velocity[JOINTS[2]],
        'pitch_range_rad': [-.08, .08], 'pitch_rate_range_rad_s': [-.20, .20],
        'wheel_position_range_rad': [-.02, .02], 'wheel_rate_range_rad_s': [-.30, .30]}


def task_binding(config, *, provider, backend, source_delivery_manifest=None):
    """Declare wheel/task semantics and source construction; Env owns lifecycle."""
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
    task_definition = lambda _artifact: TwoWheelBalanceTaskDefinition(0, 0, 1, 1, 2, 2)
    observation_schema = TwoWheelBalanceObservationBuilder(
        joint_ids={'pitch': (0, 0), 'left': (1, 1), 'right': (2, 2)}).schema
    return ReferenceTaskBinding(build=lambda _provider: _build(
        config, 31, provider=provider, source_delivery_manifest=source_delivery_manifest),
        build_seeded=build_seeded, build_sampled=build_sampled,
        task_reset_sampler=sample_reset, task_reset_metadata=reset_metadata,
        task_definition_factory=task_definition, task_state_projection=_task_state,
        task_observation_schema=observation_schema,
        external_action_contract=TWO_WHEEL_ACTION_CONTRACT,
        reset_sample=lambda _artifact, _seed: None, evaluate=lambda _state, _semantics: None,
        object_poses=(), external_actions=True, interval_mode='grouped', recorder_mode='execution',
        reset_seed=reset_seed, action_schema={'schema_id': 'task-env.two-wheel-balance.wheel-torque.v1',
            'schema_version': 'task-env-action-v1', 'mode': 'direct_wheel_torque',
            'components': ['left_wheel_torque', 'right_wheel_torque'], 'low': -1.5, 'high': 1.5, 'unit': 'N*m'},
        action_space_factory=lambda: Dict({'torque': Box(-1.5, 1.5, (2,), dtype=np.float32)}),
        prepare_action=lambda value: value, observation_space_factory=_observation_spaces, observation_projection=observe_task_definition,
        physical_control_profile=lambda env: env.value['physical_execution'],
        physical_direct_effort_feedback=(config.control.profile_id in (None, 'direct_joint_effort_v1')),
        physical_terminate_on_success=True,
        physical_ignore_done=config.episode.ignore_done)
