"""Versioned provider-free 33D state features / 8D public joint action."""
import numpy as np
from ...controllers.canonical.kinematics import ARM,FINGERS
from ...controllers.canonical import RequestedAction
from ...utils.rotation import quat_wxyz_to_matrix

FEATURE_CONTRACT={'schema':'pick-cube-state-policy-v0','dtype':'float32','shape':[33],
    'field_order':['arm_position7','arm_velocity7','gripper_opening_m1','EE_position3','EE_rotation_column0_then_column1_6','cube_position3','cube_rotation_column0_then_column1_6'],'arm_order':list(ARM)}
ACTION_CONTRACT={'schema':'pick-cube-state-policy-action-v0','dtype':'float32','shape':[8],'mode':'absolute_joint','reference':None,'rotation_representation':'none','arm_order':list(ARM),'opening_range_m':.08}


def features(state,feedback):
    feedback.require_state(state,'panda-v1/gripper',FINGERS)
    def pose(p):
        rotation=quat_wxyz_to_matrix(p.quaternion_wxyz)
        return [*p.position,*rotation[:,0],*rotation[:,1]]
    out=np.array([*[state.joint_position[n] for n in ARM],*[state.joint_velocity[n] for n in ARM],feedback.gripper.opening_m,
        *pose(state.pose_world['panda-v1/ee']),*pose(state.pose_world['cube-v1'])],dtype=np.float32)
    if out.shape!=(33,) or not np.isfinite(out).all():raise ValueError('invalid canonical policy features')
    return out


def action_target(target):
    if target.arm_joint_order!=ARM:raise ValueError('action joint order mismatch')
    out=np.array([*[target.arm_position[n] for n in ARM],2*target.gripper.opening_m/.08-1],dtype=np.float32)
    if out.shape!=(8,) or not np.isfinite(out).all():raise ValueError('invalid public target action')
    return out


def requested_action(values):
    values=np.asarray(values)
    if values.shape!=(8,) or not np.isfinite(values).all():raise ValueError('policy must emit finite public action [8]')
    return RequestedAction('absolute_joint',None,'none',tuple(map(float,values)))


def examples(trajectory):
    if not trajectory.transitions:raise ValueError('empty dataset trajectory')
    x=np.stack([features(b.state,b.feedback) for b in trajectory.boundaries[:-1]])
    y=np.stack([action_target(t.controller_target) for t in trajectory.transitions])
    return x,y
