"""Pendulum's source-bound declaration for the shared physical RuntimeSession."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..artifacts import (ActionIntent, EntityDefinition, InitializationContract,
    SemanticDefinition, Timebase)
from ..artifacts.execution import ResetSampleV1, ResetPlanV1
from ..artifacts import ExecutionSpecV1, RendererSelectionV1
from ..assembly.assets import _source_closure_digest
from ..assembly.compiler import compile_reference_source
from ..assembly.source import TaskSceneSource
from ..environment.task_source import TaskSourceV1, TaskArtifactDeclarationV1
from ..environment.types import TaskCompositionSpec, RuntimeSnapshot
from ..environment.reference_binding import ReferenceTaskBinding, observe_task_definition
from ..environment.gym_compat import Box, Dict
from ..robots.pendulum import PENDULUM_MJCF_XML, PendulumEntity, PENDULUM_ACTION_CONTRACT
from ..runtime.sessions.physical_control import build_existing_subject_effort
from ..runtime.sessions.source import project_scene_definition_v3_to_mjcf, source_asset_bytes
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
    import xml.etree.ElementTree as ET
    isaac_loaded = None
    if provider == 'isaacsim':
        if source_delivery_manifest is None:
            raise ValueError('Pendulum Isaac requires its explicit source_delivery_manifest')
        ensure_g05_isaac_app_open()
        isaac_loaded = load_g05_isaac_delivery(source_delivery_manifest)
        source_revision = isaac_loaded.delivery.asset_definition.source_revision
    else:
        source_revision = None
    robot = PendulumEntity()
    scene = robot.scene_definition(source_revision=source_revision)
    task_source, artifact = _declaration(scene)
    # Validate exact source motor semantics before creating any provider.
    root_xml = ET.fromstring(PENDULUM_MJCF_XML)
    motors = root_xml.findall('./actuator/motor')
    actuator_section = root_xml.find('./actuator')
    if (actuator_section is None or len(actuator_section) != 1 or len(motors) != 1
            or motors[0].get('name') != 'pendulum_torque'
            or motors[0].get('joint') != 'pendulum_hinge'
            or motors[0].get('gear') != '1' or motors[0].get('ctrllimited') != 'true'
            or motors[0].get('ctrlrange') != '-2 2'):
        raise ValueError('source does not declare the expected single unit-gear motor')
    base = Path(__file__).resolve().parent
    projected = project_scene_definition_v3_to_mjcf(PENDULUM_MJCF_XML, scene)
    closure = _source_closure_digest({'scene.xml': projected.encode(), **source_asset_bytes(base, projected)})
    composition = TaskCompositionSpec(PENDULUM_TASK_UID, PENDULUM_SCENE_UID,
                                      success_definition=PENDULUM_SUCCESS_DEFINITION)
    if provider == 'isaacsim':
        source = build_g05_isaac_runtime_source(
            manifest_path=source_delivery_manifest, artifact=artifact, scene=scene,
            task_source_identity_sha256=task_source.identity_hash,
            joints={JOINT: 'pendulum_hinge'},
            bodies={'pendulum-v1/pendulum_anchor': 'Geometry/pendulum_anchor',
                    'pendulum-v1/pendulum_link': 'Geometry/pendulum_anchor/pendulum_link'},
            frames={}, free_joints={}, joint_targets={JOINT: 'pendulum_hinge'},
        )
        closure = source.source_closure_digest
        execution_spec = ExecutionSpecV1(
            'execution-spec-v1', 'isaacsim', 'cuda', G05_ISAAC_EFFORT_PROFILE,
            seed, 'best_effort',
            RendererSelectionV1('renderer-selection-v1', 'none', 'cpu', 'none', None),
            physics_device='cuda:0', camera_overrides=(),
        )
    else:
        source = compile_reference_source(artifact=artifact,
            scene_source=TaskSceneSource(PENDULUM_MJCF_XML, base, f'scene-definition-v3:{scene.identity_hash}'),
            composition=composition, config=config, joints={JOINT: 'pendulum_hinge'},
            bodies={'pendulum-v1/pendulum_anchor': 'pendulum_anchor',
                    'pendulum-v1/pendulum_link': 'pendulum_link'}, frames={},
            free_joints={}, joint_targets={}, open_actuators=(), scene_definition=scene,
            source_closure_digest=closure, torque_actuators={JOINT: 'pendulum_torque'},
            actuator_units={'pendulum_torque': 'N*m'})
        execution_spec = None
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
