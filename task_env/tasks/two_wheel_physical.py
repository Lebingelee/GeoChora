"""Source-bound two-wheel declarations for the shared physical RuntimeSession."""
from __future__ import annotations

import numpy as np

from ..artifacts import Timebase
from ..environment.task_source import compile_existing_subject_effort_task, compile_named_effort_joint_reset_plan
from ..environment.types import TaskCompositionSpec, RuntimeSnapshot
from ..environment.reference_binding import ExistingSubjectEffortTask
from ..environment.gym_compat import Box, Dict

from .two_wheel_balance import (TWO_WHEEL_BALANCE_TASK_UID,
    TWO_WHEEL_BALANCE_SCENE_UID, TWO_WHEEL_BALANCE_SUCCESS_DEFINITION,
    TWO_WHEEL_BALANCE_PHYSICS_DT, TWO_WHEEL_BALANCE_CONTROL_SUBSTEPS,
    TwoWheelBalanceTaskDefinition, TwoWheelBalanceObservationBuilder)

ENTITY = 'two-wheel-balance-v1'
NAMES = ('chassis_pitch', 'left_wheel_hinge', 'right_wheel_hinge')
JOINTS = tuple(f'{ENTITY}/{name}' for name in NAMES)



def _declaration(scene, robot):
    return compile_existing_subject_effort_task(scene=scene, robot=robot, task_id=TWO_WHEEL_BALANCE_TASK_UID,
        artifact_id='two-wheel-physical-v1', semantic_id='two-wheel-task-definition-v1',
        success_definition=TWO_WHEEL_BALANCE_SUCCESS_DEFINITION,
        timebase=Timebase(TWO_WHEEL_BALANCE_PHYSICS_DT, TWO_WHEEL_BALANCE_CONTROL_SUBSTEPS,
                          TWO_WHEEL_BALANCE_PHYSICS_DT * TWO_WHEEL_BALANCE_CONTROL_SUBSTEPS))


def sample_reset(rng):
    return (float(rng.uniform(-.08, .08)), float(rng.uniform(-.20, .20)),
            float(rng.uniform(-.02, .02)), float(rng.uniform(-.02, .02)),
            float(rng.uniform(-.30, .30)), float(rng.uniform(-.30, .30)))


def _reset_plan(artifact, source, seed, sampled=None):
    if sampled is None:
        sampled = sample_reset(np.random.default_rng(seed))
    pitch, pitch_rate, left, right, left_rate, right_rate = sampled
    return compile_named_effort_joint_reset_plan(artifact=artifact, source=source, task_seed=seed,
        sampler_id='two-wheel-uniform-perturbation', sampled_values=sampled,
        joint_position=dict(zip(JOINTS, (pitch, left, right), strict=True)),
        joint_velocity=dict(zip(JOINTS, (pitch_rate, left_rate, right_rate), strict=True)))


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


def task_binding(config, *, robot, source_delivery_manifest=None):
    """Declare balance-task semantics for the common Robot construction path."""
    task = ExistingSubjectEffortTask(
        robot=robot, compile_declaration=_declaration, reset_plan=_reset_plan,
        composition=TaskCompositionSpec(TWO_WHEEL_BALANCE_TASK_UID, TWO_WHEEL_BALANCE_SCENE_UID, (robot.uid,), (),
                                        success_definition=TWO_WHEEL_BALANCE_SUCCESS_DEFINITION),
        construction_id='two-wheel-shared-physical-v1', source_revision='two-wheel-inline-v1',
        reset_sampler=sample_reset,
        reset_metadata=reset_metadata, definition_factory=lambda _artifact: TwoWheelBalanceTaskDefinition(0, 0, 1, 1, 2, 2),
        state_projection=_task_state, observation_schema=TwoWheelBalanceObservationBuilder(
            joint_ids={'pitch': (0, 0), 'left': (1, 1), 'right': (2, 2)}).schema,
        observation_space_factory=_observation_spaces)
    return task.bind(config, source_delivery_manifest=source_delivery_manifest)
