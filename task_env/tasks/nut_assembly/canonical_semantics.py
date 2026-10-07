"""Additive state-only NutAssembly semantics; legacy command shortcut is untouched."""
import math
import numpy as np

from ...artifacts import CanonicalStateView, SemanticDefinition
from ...environment import TaskEvaluation
from ...utils.rotation import quat_wxyz_to_matrix
from .assets import NUT_HALF_HEIGHT, NUT_CONTACT_MARGIN, NUT_HANDLE_LOCAL_X, PEG_HALF_HEIGHT, TABLE_TOP_Z

NUT = 'square-nut-v1'
PEG = 'square-peg-v1'
EEF = 'panda-v1/ee'
FINGERS = ('panda-v1/finger_joint1', 'panda-v1/finger_joint2')
SUCCESS = 'nut_on_square_peg_canonical_state_v0'


def semantic_definition():
    return SemanticDefinition('semantics-v0', 'nut_assembly_state_v0', (NUT, PEG, EEF), FINGERS,
        {'insert_xy_tolerance': .030, 'insert_yaw_tolerance': .35,
         'lift_height': .050, 'hover_xy_tolerance': .050, 'grasp_distance': .090,
         'gripper_closed_opening': .045, 'gripper_release_opening': .065,
         'release_distance': .055, 'table_top_z': TABLE_TOP_Z,
         'nut_half_height': NUT_HALF_HEIGHT, 'nut_contact_margin': NUT_CONTACT_MARGIN,
         'nut_handle_local_x': NUT_HANDLE_LOCAL_X, 'peg_half_height': PEG_HALF_HEIGHT}, SUCCESS)


def evaluate(state: CanonicalStateView, semantics=None):
    expected = semantic_definition()
    semantics = expected if semantics is None else semantics
    if not isinstance(state, CanonicalStateView) or semantics != expected:
        raise ValueError('unsupported canonical NutAssembly state/semantics')
    semantics.require_state(state)
    p = semantics.parameters_si
    nut = state.pose_world[NUT]; peg = state.pose_world[PEG]
    pos = np.asarray(nut.position); ee = np.asarray(state.pose_world[EEF].position)
    rotation = quat_wxyz_to_matrix(nut.quaternion_wxyz)
    handle = pos + rotation @ np.array([p['nut_handle_local_x'], 0., 0.])
    yaw = float(math.atan2(rotation[1, 0], rotation[0, 0]))
    period = .5 * math.pi
    yaw_error = abs((yaw + .5 * period) % period - .5 * period)
    xy_error = float(np.linalg.norm(pos[:2] - np.asarray(peg.position[:2])))
    seated_z = p['table_top_z'] + p['nut_half_height'] + p['nut_contact_margin']
    z_error = float(pos[2] - seated_z)
    ee_distance = float(np.linalg.norm(ee - pos))
    handle_distance = float(np.linalg.norm(ee - handle))
    opening = sum(state.joint_position[n] for n in FINGERS)
    reached = handle_distance <= p['grasp_distance']
    grasped = reached and opening <= p['gripper_closed_opening']
    lifted = pos[2] >= p['table_top_z'] + p['nut_half_height'] + p['lift_height']
    hover = lifted and xy_error <= p['hover_xy_tolerance']
    aligned = xy_error <= p['insert_xy_tolerance'] and yaw_error <= p['insert_yaw_tolerance']
    passed = pos[2] <= peg.position[2] + p['peg_half_height'] - p['nut_contact_margin']
    returned = pos[2] <= p['table_top_z'] + 3 * p['nut_half_height']
    inserted = aligned and passed and returned
    gripper_released = opening >= p['gripper_release_opening']
    released = inserted and gripper_released and ee_distance >= p['release_distance']
    success = inserted and released
    metrics = {
        'reached_nut': bool(reached), 'grasped_nut': bool(grasped), 'lifted_nut': bool(lifted),
        'hovered_over_peg': bool(hover), 'aligned_with_peg': bool(aligned),
        'peg_passed_through_nut_center': bool(passed), 'nut_returned_to_table': bool(returned),
        'inserted_on_peg': bool(inserted), 'gripper_released': bool(gripper_released),
        'released_nut': bool(released), 'task_success': bool(success),
        'nut_x': float(pos[0]), 'nut_y': float(pos[1]), 'nut_z': float(pos[2]), 'nut_yaw': yaw,
        'table_seated_nut_max_z': p['table_top_z'] + 3 * p['nut_half_height'],
        'peg_xy_error': xy_error, 'peg_z_error': z_error, 'yaw_error': yaw_error,
        'eef_to_nut_dist': ee_distance, 'eef_to_handle_dist': handle_distance,
        'gripper_opening': opening, 'success_definition': True,
    }
    terms = {'reach': .10 * (1. - math.tanh(10. * handle_distance)), 'grasp': .25 if grasped else 0.,
             'lift': .25 if lifted else 0., 'hover': .15 if hover else 0., 'insert': .15 if inserted else 0.,
             'release': .10 if released else 0., 'success': 1. if success else 0.}
    return TaskEvaluation(reward=sum(terms.values()), success=bool(success), failure=False,
                          metrics=metrics, reward_terms=terms)
