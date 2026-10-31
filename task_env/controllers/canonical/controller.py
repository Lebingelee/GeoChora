"""Shared stateless action interpretation/DLS, no provider inputs/imports."""
from dataclasses import asdict
import numpy as np
from ...artifacts import PoseWorld
from ...environment import ActionConfig
from ...utils.rotation import quat_wxyz_to_matrix,matrix_to_quat_wxyz,rotvec_to_matrix,matrix_to_rotvec,rotation_vector_error
from .contracts import CanonicalAction,CanonicalControlTarget,GripperControlTarget,digest
from .kinematics import ARM,FINGERS


class CanonicalPandaController:
    def __init__(self,model,*,artifact_hash,config=None,nullspace_reference_gain=0.0):
        if (isinstance(nullspace_reference_gain, bool)
                or not np.isfinite(nullspace_reference_gain)
                or nullspace_reference_gain < 0.0
                or nullspace_reference_gain > 1.0):
            raise ValueError('nullspace reference gain must be finite and in [0, 1]')
        self.model=model;self.artifact_hash=artifact_hash;self.config=config or ActionConfig()
        self.nullspace_reference_gain=float(nullspace_reference_gain)
        self._nullspace_reference=None
        self.identity=digest({'schema':'panda-shared-dls-v1','config':asdict(self.config),'source_sha256':model.source_sha256,
            'target_basis':'achieved_joint_state_one_DLS_increment',
            'nullspace_reference':{
                'gain':self.nullspace_reference_gain,
                'source':'reset_typed_joint_position' if self.nullspace_reference_gain else 'disabled',
                'projector':'svd_right_nullspace_v1' if self.nullspace_reference_gain else 'none',
            },
            'gripper':'legacy_physical_force_limited_servo_v0'})

    def set_nullspace_reference(self, joint_position):
        reference=np.asarray(joint_position,dtype=np.float64)
        if reference.shape!=(7,) or not np.isfinite(reference).all():
            raise ValueError('nullspace reference requires seven finite arm joint positions')
        self._nullspace_reference=reference.copy()

    @staticmethod
    def _right_nullspace_projector(jacobian):
        jacobian=np.asarray(jacobian,dtype=np.float64)
        if jacobian.ndim!=2 or jacobian.shape[1]!=7 or not np.isfinite(jacobian).all():
            raise ValueError('Panda task Jacobian must be a finite matrix with seven columns')
        _u,singular_values,vh=np.linalg.svd(jacobian,full_matrices=True)
        if singular_values.size==0 or singular_values[0]<=0.0:
            return np.eye(7,dtype=np.float64)
        rank=int(np.count_nonzero(singular_values>singular_values[0]*1e-8))
        basis=vh[rank:].T
        return basis@basis.T if basis.size else np.zeros((7,7),dtype=np.float64)

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
            task_dq=np.zeros(7,dtype=np.float64)
            if not (np.linalg.norm(position_error)<=cfg.ik_position_deadband
                    and np.linalg.norm(rotation_error)<=cfg.ik_rotation_deadband):
                for error,bound in ((position_error,cfg.cartesian_max_position_step),(rotation_error,cfg.cartesian_max_rotation_step)):
                    length=np.linalg.norm(error)
                    if length>bound:error*=bound/length
                J=J.copy();J[3:]*=cfg.ik_rotation_row_weight
                error=np.r_[position_error,cfg.ik_rotation_row_weight*cfg.ik_rotation_gain*rotation_error]
                task_dq=J.T@np.linalg.solve(J@J.T+cfg.ik_damping**2*np.eye(6),error)
            if self.nullspace_reference_gain:
                if self._nullspace_reference is None:
                    raise RuntimeError('Panda nullspace reference was not initialized at reset')
                task_dq += self.nullspace_reference_gain * (
                    self._right_nullspace_projector(J)
                    @ (self._nullspace_reference-q)
                )
            desired=np.clip(q+cfg.ik_position_gain*np.clip(task_dq,-cfg.ik_max_delta_q,cfg.ik_max_delta_q),self.model.limits[:,0],self.model.limits[:,1])
        _resolved, servo = absolute_joint_position_servo(
            desired, q, self.model.limits, cfg.joint_position_correction_gain,
        )
        canonical=CanonicalAction('canonical-action-v0',requested,tuple(float(v) for v in values),not np.array_equal(original,values),world_pose)
        return canonical,desired,servo

    def compute(self,state,requested):
        # Frozen-v0 compatibility only; production R1 owns its resolved gripper profile.
        from ...robots.gripper import position_gripper_servo_opening
        cfg=self.config
        canonical,desired,servo=self._compute_arm(state,requested)
        values=canonical.interpreted_values
        opening=.5*(values[-1]+1)*cfg.gripper_opening_range_m
        achieved=float(sum(state.joint_position[n] for n in FINGERS))
        servo_opening=position_gripper_servo_opening(
            opening, achieved, cfg.gripper_default_force_N,
            cfg.gripper_position_stiffness_N_per_m, cfg.gripper_opening_range_m,
            error_deadband_m=0.0,
        )
        servo_opening=float(np.clip(servo_opening,0,cfg.gripper_opening_range_m))
        target=CanonicalControlTarget('canonical-control-v0',self.artifact_hash,self.identity,ARM,dict(zip(ARM,map(float,desired))),dict(zip(ARM,map(float,servo))),
            GripperControlTarget('panda-v1/gripper',float(opening),cfg.gripper_default_force_N,servo_opening))
        return canonical,target


def absolute_joint_position_servo(requested, current, limits, correction_gain):
    """Apply the shared absolute-joint clipping and position-error correction.

    This stateless operation is also used by the versioned Arm leaf adapter,
    which deliberately has no Panda FK/hand state.  Keeping the historical
    controller on the same function preserves its numerical rule.
    """
    requested = np.asarray(requested, dtype=float)
    current = np.asarray(current, dtype=float)
    limits = np.asarray(limits, dtype=float)
    if (requested.ndim != 1 or current.shape != requested.shape
            or limits.shape != (requested.size, 2)):
        raise ValueError('absolute-joint servo inputs have inconsistent dimensions')
    if not np.isfinite(requested).all() or not np.isfinite(current).all() or not np.isfinite(limits).all():
        raise ValueError('absolute-joint servo inputs must be finite')
    if np.any(limits[:, 0] >= limits[:, 1]):
        raise ValueError('absolute-joint servo limits must be strictly ordered')
    if isinstance(correction_gain, bool) or not np.isfinite(correction_gain) or correction_gain <= 0:
        raise ValueError('absolute-joint correction gain must be finite and positive')
    desired = np.clip(requested, limits[:, 0], limits[:, 1])
    servo = np.clip(
        desired + float(correction_gain) * (desired - current),
        limits[:, 0], limits[:, 1],
    )
    return desired, servo
