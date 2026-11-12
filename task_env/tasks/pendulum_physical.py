"""Pendulum's source-bound declaration for the shared physical RuntimeSession."""
from __future__ import annotations

import numpy as np

from ..artifacts import Timebase
from ..environment.task_source import compile_existing_subject_effort_task, compile_named_effort_joint_reset_plan
from ..environment.types import TaskCompositionSpec, RuntimeSnapshot
from ..environment.reference_binding import ExistingSubjectEffortTask
from ..environment.gym_compat import Box, Dict
from ..robots.pendulum import PENDULUM_ACTION_CONTRACT

from .pendulum import (PENDULUM_TASK_UID, PENDULUM_SCENE_UID,
                       PENDULUM_SUCCESS_DEFINITION, PendulumTaskDefinition,
                       PendulumObservationBuilder, PENDULUM_TASK_SEMANTICS)

ENTITY = 'pendulum-v1'
JOINT = f'{ENTITY}/pendulum_hinge'



def _declaration(scene, robot):
    return compile_existing_subject_effort_task(scene=scene, robot=robot, task_id=PENDULUM_TASK_UID,
        artifact_id='pendulum-physical-v1', semantic_id='pendulum-task-definition-v1',
        success_definition=PENDULUM_SUCCESS_DEFINITION, timebase=Timebase(.002, 25, .05))


def _reset_plan(artifact, source, seed, sampled=None):
    angle, speed = (PENDULUM_TASK_SEMANTICS.sample_reset(np.random.default_rng(seed))
                    if sampled is None else sampled)
    return compile_named_effort_joint_reset_plan(artifact=artifact, source=source, task_seed=seed,
        sampler_id='pendulum-uniform-angle-velocity', sampled_values=(angle, speed),
        joint_position={JOINT: float(angle)}, joint_velocity={JOINT: float(speed)})


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


def task_binding(config, *, robot, source_delivery_manifest=None):
    """Declare Pendulum semantics for the common Robot construction path."""
    task = ExistingSubjectEffortTask(
        robot=robot, compile_declaration=_declaration, reset_plan=_reset_plan,
        composition=TaskCompositionSpec(PENDULUM_TASK_UID, PENDULUM_SCENE_UID, (robot.uid,), (),
                                        success_definition=PENDULUM_SUCCESS_DEFINITION),
        construction_id='pendulum-shared-physical-v1', source_revision='pendulum-inline-v1',
        reset_sampler=PENDULUM_TASK_SEMANTICS.sample_reset,
        reset_metadata=reset_metadata, definition_factory=lambda _artifact: PendulumTaskDefinition(qpos_id=0, qvel_id=0),
        state_projection=_task_state, observation_schema=PendulumObservationBuilder(qpos_id=0, qvel_id=0).schema,
        observation_space_factory=_observation_spaces, action_contract=PENDULUM_ACTION_CONTRACT)
    return task.bind(config, source_delivery_manifest=source_delivery_manifest)
