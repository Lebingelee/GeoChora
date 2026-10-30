"""Shared stateless action interpretation/DLS, no provider inputs/imports."""
from dataclasses import asdict
from types import SimpleNamespace
import numpy as np
from ...artifacts import PoseWorld
from ...environment import ActionConfig
from ...utils.rotation import quat_wxyz_to_matrix,matrix_to_quat_wxyz,rotvec_to_matrix,matrix_to_rotvec,rotation_vector_error
from .contracts import CanonicalAction,CanonicalArmTargetV1,CanonicalControlTarget,GripperControlTarget,RequestedAction,digest
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
        _resolved, servo = absolute_joint_position_servo(
            desired, q, self.model.limits, cfg.joint_position_correction_gain,
        )
        canonical=CanonicalAction('canonical-action-v0',requested,tuple(float(v) for v in values),not np.array_equal(original,values),world_pose)
        return canonical,desired,servo

    def resolve_world_pose_target_v1(self, *, current_joint_position_rad,
                                    current_pose_world: PoseWorld,
                                    target_pose_world, gripper_scalar: float) -> CanonicalArmTargetV1:
        """Resolve one absolute world pose through the shared canonical arm DLS owner.

        This advanced stateless route shares the exact arm calculation used by
        the legacy Controller. It consumes typed world pose plus named-order
        arm feedback; it does not advance the environment or touch a Provider.
        """
        if not isinstance(current_pose_world, PoseWorld):
            raise TypeError('world-pose resolution requires a typed PoseWorld current pose')
        q = np.asarray(current_joint_position_rad, dtype=np.float64)
        pose = np.asarray(target_pose_world, dtype=np.float64)
        if (q.shape != (7,) or pose.shape != (7,)
                or not np.isfinite(q).all() or not np.isfinite(pose).all()
                or isinstance(gripper_scalar, bool) or not np.isfinite(gripper_scalar)):
            raise ValueError('world-pose resolution requires seven finite joints, pose values and a finite gripper scalar')
        requested = RequestedAction(
            'absolute_pose', 'world', 'quaternion_wxyz',
            tuple(float(value) for value in (*pose, float(gripper_scalar))),
        )
        requested.validate()
        state = SimpleNamespace(
            joint_position=dict(zip(ARM, map(float, q), strict=True)),
            pose_world={'panda-v1/ee': current_pose_world},
        )
        canonical, desired, servo = self._compute_arm(state, requested)
        target = CanonicalArmTargetV1(
            'canonical-arm-target-v1', self.model.source_sha256, self.identity,
            canonical, ARM, tuple(map(float, desired)), tuple(map(float, servo)),
        )
        target.validate()
        return target

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
