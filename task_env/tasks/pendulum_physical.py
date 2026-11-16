"""Pendulum's source-bound declaration for the shared physical RuntimeSession."""
from __future__ import annotations

import numpy as np

from ..artifacts import Timebase
from ..environment.task_source import compile_existing_subject_effort_task, compile_named_effort_joint_reset_plan
from ..environment.types import TaskCompositionSpec, RuntimeSnapshot
from ..environment.reference_binding import ExistingSubjectEffortTask

from .pendulum import (PENDULUM_TASK_UID, PENDULUM_SCENE_UID,
                       PENDULUM_SUCCESS_DEFINITION, PendulumTaskDefinition,
                       PendulumObservationBuilder, PENDULUM_TASK_SEMANTICS,
                       PENDULUM_PHYSICS_DT, PENDULUM_CONTROL_SUBSTEPS)

ENTITY = 'pendulum-v1'
JOINT = f'{ENTITY}/pendulum_hinge'



def _declaration(scene, robot):
    return compile_existing_subject_effort_task(scene=scene, robot=robot, task_id=PENDULUM_TASK_UID,
        artifact_id='pendulum-physical-v1', semantic_id='pendulum-task-definition-v1',
        success_definition=PENDULUM_SUCCESS_DEFINITION,
        timebase=Timebase(PENDULUM_PHYSICS_DT, PENDULUM_CONTROL_SUBSTEPS,
                          PENDULUM_PHYSICS_DT * PENDULUM_CONTROL_SUBSTEPS))


def _reset_plan(artifact, source, seed, sampled=None):
    angle, speed = (PENDULUM_TASK_SEMANTICS.sample_reset(np.random.default_rng(seed))
                    if sampled is None else sampled)
    return compile_named_effort_joint_reset_plan(artifact=artifact, source=source, task_seed=seed,
        sampler_id='pendulum-uniform-angle-velocity', sampled_values=(angle, speed),
        joint_position={JOINT: float(angle)}, joint_velocity={JOINT: float(speed)})


def _observation_spaces(_env):
    return dict(PendulumObservationBuilder(qpos_id=0, qvel_id=0).observation_space.spaces)


def _task_state(state):
    q = np.asarray([state.joint_position[JOINT]], dtype=np.float32)
    v = np.asarray([state.joint_velocity[JOINT]], dtype=np.float32)
    snapshot = RuntimeSnapshot(qpos=q, qvel=v, simulation_time=state.simulation_time)
    return snapshot


def reset_metadata(sample):
    return {'profile': 'pendulum_uniform_angle_velocity_v1',
        'angle_range_rad': list(PENDULUM_TASK_SEMANTICS.reset_angle_range),
        'angular_velocity_range_rad_s': list(PENDULUM_TASK_SEMANTICS.reset_velocity_range),
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
        observation_space_factory=_observation_spaces)
    return task.bind(config, source_delivery_manifest=source_delivery_manifest)
