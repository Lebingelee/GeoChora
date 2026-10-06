"""Shared stateless action interpretation/DLS, no provider inputs/imports."""
from dataclasses import asdict
import numpy as np
from ...artifacts import PoseWorld
from ...environment import ActionConfig
from ...utils.rotation import quat_wxyz_to_matrix,matrix_to_quat_wxyz,rotvec_to_matrix,matrix_to_rotvec,rotation_vector_error
from .contracts import CanonicalAction,CanonicalControlTarget,GripperControlTarget,digest
from .kinematics import ARM,FINGERS


class CanonicalPandaController:
    def __init__(self,model,*,artifact_hash,config=None):
        self.model=model;self.artifact_hash=artifact_hash;self.config=config or ActionConfig()
        self.identity=digest({'schema':'panda-shared-dls-v0','config':asdict(self.config),'source_sha256':model.source_sha256,
            'target_basis':'achieved_joint_state_one_DLS_increment','gripper':'legacy_physical_force_limited_servo_v0'})

    def _compute_arm(self,state,requested):
        cfg=self.config;values=np.array(requested.values,dtype=float);original=values.copy()
        values[-1]=np.clip(values[-1],-1,1);q=np.array([state.joint_position[n] for n in ARM])
        current=state.pose_world['panda-v1/ee'];world_pose=None
        if requested.mode=='absolute_joint':desired=np.clip(values[:7],self.model.limits[:,0],self.model.limits[:,1]);values[:7]=desired
        else:
            if requested.rotation_representation=='quaternion_wxyz':
                norm=np.linalg.norm(values[3:7])
                if norm<1e-8:raise ValueError('zero action quaternion')
                values[3:7]/=norm;rotation=quat_wxyz_to_matrix(values[3:7])
            else:rotation=rotvec_to_matrix(values[3:6])
            position=values[:3].copy();base=self.model.base_transform
            if requested.mode=='absolute_pose':
                if requested.reference=='base':position=base[:3,3]+base[:3,:3]@position;rotation=base[:3,:3]@rotation
            else:
                values[:3]=np.clip(values[:3],-.03,.03);position=values[:3].copy()
                rv=matrix_to_rotvec(rotation);angle=np.linalg.norm(rv)
                if angle>.2:
                    rv*=.2/angle;rotation=rotvec_to_matrix(rv)
                    values[3:7 if requested.rotation_representation=='quaternion_wxyz' else 6]=(matrix_to_quat_wxyz(rotation) if requested.rotation_representation=='quaternion_wxyz' else rv)
                current_rotation=quat_wxyz_to_matrix(current.quaternion_wxyz)
                if requested.reference=='ee':position=current_rotation@position;rotation=current_rotation@rotation
                elif requested.reference=='base':position=base[:3,:3]@position;rotation=base[:3,:3]@rotation@base[:3,:3].T@current_rotation
                else:rotation=rotation@current_rotation
                position+=current.position
            world_pose=PoseWorld(tuple(float(v) for v in position),tuple(float(v) for v in matrix_to_quat_wxyz(rotation)))
            position_error=position-np.array(current.position);rotation_error=rotation_vector_error(quat_wxyz_to_matrix(current.quaternion_wxyz),rotation)
            _,J=self.model.fk_jacobian(q)
            if np.linalg.norm(position_error)<=cfg.ik_position_deadband and np.linalg.norm(rotation_error)<=cfg.ik_rotation_deadband:desired=q.copy()
            else:
                for error,bound in ((position_error,cfg.cartesian_max_position_step),(rotation_error,cfg.cartesian_max_rotation_step)):
                    length=np.linalg.norm(error)
                    if length>bound:error*=bound/length
                J=J.copy();J[3:]*=cfg.ik_rotation_row_weight
                error=np.r_[position_error,cfg.ik_rotation_row_weight*cfg.ik_rotation_gain*rotation_error]
                dq=J.T@np.linalg.solve(J@J.T+cfg.ik_damping**2*np.eye(6),error)
                desired=np.clip(q+cfg.ik_position_gain*np.clip(dq,-cfg.ik_max_delta_q,cfg.ik_max_delta_q),self.model.limits[:,0],self.model.limits[:,1])
        servo=np.clip(desired+cfg.joint_position_correction_gain*(desired-q),self.model.limits[:,0],self.model.limits[:,1])
        canonical=CanonicalAction('canonical-action-v0',requested,tuple(float(v) for v in values),not np.array_equal(original,values),world_pose)
        return canonical,desired,servo

    def compute(self,state,requested):
        # Frozen-v0 compatibility only; production R1 owns its resolved gripper profile.
        cfg=self.config
        canonical,desired,servo=self._compute_arm(state,requested)
        values=canonical.interpreted_values
        opening=.5*(values[-1]+1)*cfg.gripper_opening_range_m
        achieved=float(sum(state.joint_position[n] for n in FINGERS))
        correction=cfg.gripper_default_force_N/cfg.gripper_position_stiffness_N_per_m
        servo_opening=float(np.clip(achieved+np.clip(opening-achieved,-correction,correction),0,cfg.gripper_opening_range_m))
        target=CanonicalControlTarget('canonical-control-v0',self.artifact_hash,self.identity,ARM,dict(zip(ARM,map(float,desired))),dict(zip(ARM,map(float,servo))),
            GripperControlTarget('panda-v1/gripper',float(opening),cfg.gripper_default_force_N,servo_opening))
        return canonical,target
