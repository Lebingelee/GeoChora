"""Pure PickCube evaluation over semantic names, never native references.

The existing production evaluator is retained. The Phase-I detector compares
its metrics/reward on synthetic fixtures; no simulator is needed.
"""
import math

from ...artifacts import CanonicalStateView, SemanticDefinition
from ...environment import TaskEvaluation
from .assets import TABLE_TOP_Z, CUBE_HALF_SIZE
from .task import (
    PICK_CUBE_SUCCESS_DEFINITION, _LIFT_HEIGHT, _REACH_DISTANCE,
    _GRIPPER_CLOSED_OPENING,
)

CUBE = 'cube-v1'
EEF = 'panda-v1/ee'
FINGERS = ('panda-v1/finger_joint1', 'panda-v1/finger_joint2')
EVALUATOR = 'pick_cube_lift_v0'
SUCCESS = PICK_CUBE_SUCCESS_DEFINITION


def semantic_definition() -> SemanticDefinition:
    return SemanticDefinition(
        schema_version='semantics-v0', evaluator=EVALUATOR,
        required_poses=(CUBE, EEF), required_joints=FINGERS,
        parameters_si={
            'rest_height': TABLE_TOP_Z + CUBE_HALF_SIZE,
            'lift_height': _LIFT_HEIGHT, 'reach_distance': _REACH_DISTANCE,
            'gripper_closed_opening': _GRIPPER_CLOSED_OPENING,
        }, success_definition=SUCCESS,
    )


def evaluate(state: CanonicalStateView, semantics: SemanticDefinition | None = None) -> TaskEvaluation:
    """Lift is the sole success gate; grasp remains a reward diagnostic."""
    if not isinstance(state, CanonicalStateView):
        raise TypeError('PickCube evaluation requires CanonicalStateView')
    expected = semantic_definition()
    semantics = expected if semantics is None else semantics
    if semantics != expected:
        raise ValueError('unsupported PickCube semantic definition')
    semantics.require_state(state)
    p = semantics.parameters_si
    cube_pos = state.pose_world[CUBE].position
    eef_pos = state.pose_world[EEF].position
    gripper_opening = sum(state.joint_position[n] for n in FINGERS)
    cube_lift = cube_pos[2] - p['rest_height']
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(eef_pos, cube_pos, strict=True)))
    reached = distance <= p['reach_distance']
    grasped = bool(reached and gripper_opening <= p['gripper_closed_opening'])
    lifted = bool(cube_lift >= p['lift_height'])
    terms = {
        'reach': .10 * (1.0 - math.tanh(10.0 * distance)),
        'grasp': .25 if grasped else 0.0,
        'lift': min(.40, max(0.0, cube_lift / p['lift_height']) * .40),
        'success': 1.0 if lifted else 0.0,
    }
    metrics = {
        'reached_cube': bool(reached), 'grasped_cube': grasped,
        'lifted_cube': lifted, 'task_success': lifted,
        'cube_x': cube_pos[0], 'cube_y': cube_pos[1], 'cube_z': cube_pos[2],
        'cube_lift': cube_lift, 'eef_to_cube_dist': distance,
        'gripper_opening': gripper_opening, 'success_definition': True,
    }
    return TaskEvaluation(reward=sum(terms.values()), success=lifted, failure=False,
                          metrics=metrics, reward_terms=terms)
