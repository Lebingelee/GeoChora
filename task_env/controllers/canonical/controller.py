"""Shared stateless action interpretation/DLS, no provider inputs/imports."""
from dataclasses import asdict
import math
from types import SimpleNamespace
import numpy as np
from ...artifacts import PoseWorld
from ...environment import ActionConfig
from ...utils.rotation import quat_wxyz_to_matrix,matrix_to_quat_wxyz,rotvec_to_matrix,matrix_to_rotvec,rotation_vector_error
from .contracts import (CanonicalAction,CanonicalArmResolutionDiagnosticsV1,
                        CanonicalArmResolutionV1,CanonicalArmTargetV1,
                        CanonicalControlTarget,GripperControlTarget,RequestedAction,digest)
from .kinematics import ARM,FINGERS


class CanonicalPandaController:
    def __init__(self,model,*,artifact_hash,config=None,nullspace_reference_gain=0.0,
                 pose_target_method='achieved_state_dls_v1',arm_target_limits=None,
                 arm_target_limit_source='kinematics_model_v1'):
        if (isinstance(nullspace_reference_gain, bool)
                or not np.isfinite(nullspace_reference_gain)
                or nullspace_reference_gain < 0.0
                or nullspace_reference_gain > 1.0):
            raise ValueError('nullspace reference gain must be finite and in [0, 1]')
        if not isinstance(pose_target_method, str) or pose_target_method not in {
                'achieved_state_dls_v1',
                'accumulated_dls_target_until_settled_v1',
        }:
            raise ValueError('unsupported Panda pose target method')
        if not isinstance(arm_target_limit_source, str) or arm_target_limit_source not in {
                'kinematics_model_v1',
                'kinematics_and_geophys_receipt_intersection_v1',
        }:
            raise ValueError('unsupported Panda arm target limit source')
        self.model=model;self.artifact_hash=artifact_hash;self.config=config or ActionConfig()
        self.nullspace_reference_gain=float(nullspace_reference_gain)
        self.pose_target_method=pose_target_method
        self.arm_target_limit_source=arm_target_limit_source
        self.arm_target_limits=np.asarray(
            model.limits if arm_target_limits is None else arm_target_limits,
            dtype=np.float64,
        )
        if (self.arm_target_limits.shape!=(7,2)
                or not np.isfinite(self.arm_target_limits).all()
                or np.any(self.arm_target_limits[:,0]>=self.arm_target_limits[:,1])
                or np.any(self.arm_target_limits[:,0]<np.asarray(model.limits)[:,0]-1e-12)
                or np.any(self.arm_target_limits[:,1]>np.asarray(model.limits)[:,1]+1e-12)):
            raise ValueError('Panda arm target limits must be a valid subset of its kinematic limits')
        if ((arm_target_limits is None) != (arm_target_limit_source=='kinematics_model_v1')):
            raise ValueError('Panda arm target limit source must match its bound limits')
        self._nullspace_reference=None
        self._arm_target=None
        self._last_pose_target=None
        self._last_pose_error_norm=None
        self._pose_target_settled=False
        legacy_default = (
            self.nullspace_reference_gain == 0.0
            and pose_target_method == 'achieved_state_dls_v1'
            and arm_target_limits is None
        )
        if legacy_default:
            # Keep every existing default caller on the accepted v0 identity.
            # Opt-in target semantics, nullspace behavior, or native limit
            # intersections remain explicitly versioned below.
            identity_payload = {
                'schema': 'panda-shared-dls-v0',
                'config': asdict(self.config),
                'source_sha256': model.source_sha256,
                'target_basis': 'achieved_joint_state_one_DLS_increment',
                'gripper': 'legacy_physical_force_limited_servo_v0',
            }
        else:
            identity_payload={'schema':'panda-shared-dls-v1','config':asdict(self.config),'source_sha256':model.source_sha256,
                'target_basis':('achieved_joint_state_one_DLS_increment'
                                if pose_target_method == 'achieved_state_dls_v1'
                                else 'accumulated_dls_target_until_settled_v1'),
                'nullspace_reference':{
                    'gain':self.nullspace_reference_gain,
                    'source':'reset_typed_joint_position' if self.nullspace_reference_gain else 'disabled',
                    'projector':'svd_right_nullspace_v1' if self.nullspace_reference_gain else 'none',
                },
                'gripper':'legacy_physical_force_limited_servo_v0'}
            if arm_target_limits is not None:
                identity_payload['arm_target_limits']={
                    'source':arm_target_limit_source,
                    'lower_upper':self.arm_target_limits.tolist(),
                }
        self.identity=digest(identity_payload)

    def reset_pose_target_memory(self, joint_position):
        """Seed opt-in pose target memory from a complete reset/switch boundary."""
        if self.pose_target_method != 'accumulated_dls_target_until_settled_v1':
            return
        target=np.asarray(joint_position,dtype=np.float64)
        if target.shape!=(7,) or not np.isfinite(target).all():
            raise ValueError('pose target memory requires seven finite arm joint positions')
        self._arm_target=target.copy()
        self._last_pose_target=None
        self._last_pose_error_norm=None
        self._pose_target_settled=False

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

    def iterative_resolution_identity_v1(
        self, *, max_iterations=12, position_tolerance_m=0.006,
        orientation_tolerance_rad=0.03, model_position_tolerance_m=0.003,
        model_orientation_tolerance_rad=0.03,
    ):
        """Identify one bounded iterative resolver profile without changing legacy identity."""
        values = (position_tolerance_m, orientation_tolerance_rad,
                  model_position_tolerance_m, model_orientation_tolerance_rad)
        if (type(max_iterations) is not int or not 1 <= max_iterations <= 64
                or any(isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0
                       for value in values)):
            raise ValueError('iterative resolver identity bounds are invalid')
        return digest({
            'schema_version': 'canonical-panda-iterative-resolver-identity-v1',
            'base_controller_identity': self.identity,
            'source_xml_sha256': self.model.source_sha256,
            'method_id': 'shared_canonical_dls_iterative_v1',
            'max_iterations': max_iterations,
            'position_tolerance_m': float(position_tolerance_m),
            'orientation_tolerance_rad': float(orientation_tolerance_rad),
            'model_position_tolerance_m': float(model_position_tolerance_m),
            'model_orientation_tolerance_rad': float(model_orientation_tolerance_rad),
        })

    def _compute_arm(self,state,requested):
        cfg=self.config;values=np.array(requested.values,dtype=float);original=values.copy()
        values[-1]=np.clip(values[-1],-1,1);q=np.array([state.joint_position[n] for n in ARM])
        current=state.pose_world['panda-v1/ee'];world_pose=None
        accumulated_pose_target=(
            self.pose_target_method == 'accumulated_dls_target_until_settled_v1'
            and requested.mode == 'absolute_pose'
        )
        if (self.pose_target_method == 'accumulated_dls_target_until_settled_v1'
                and not accumulated_pose_target):
            self.reset_pose_target_memory(q)
        if requested.mode=='absolute_joint':desired=np.clip(values[:7],self.arm_target_limits[:,0],self.arm_target_limits[:,1]);values[:7]=desired
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
            position_error_norm=float(np.linalg.norm(position_error))
            rotation_error_norm=float(np.linalg.norm(rotation_error))
            if accumulated_pose_target:
                if self._arm_target is None:
                    self.reset_pose_target_memory(q)
                target_position=np.asarray(world_pose.position,dtype=np.float64)
                target_quaternion=np.asarray(world_pose.quaternion_wxyz,dtype=np.float64)
                previous_position,previous_quaternion=(
                    (None,None) if self._last_pose_target is None
                    else self._last_pose_target
                )
                same_target=(
                    previous_position is not None
                    and np.allclose(target_position,previous_position,atol=1e-8,rtol=0.0)
                    and abs(float(np.dot(target_quaternion,previous_quaternion))) >= 1.0-1e-8
                )
                settled=(position_error_norm<=cfg.ik_position_deadband
                         and rotation_error_norm<=cfg.ik_rotation_deadband)
                error_grew=(
                    same_target and self._last_pose_error_norm is not None
                    and position_error_norm > self._last_pose_error_norm + cfg.cartesian_error_growth_margin
                )
                if not same_target:
                    self._pose_target_settled=False
                elif settled and not error_grew:
                    self._pose_target_settled=True
                elif not settled:
                    self._pose_target_settled=False
                if not self._pose_target_settled and not error_grew:
                    for error,bound in ((position_error,cfg.cartesian_max_position_step),
                                        (rotation_error,cfg.cartesian_max_rotation_step)):
                        length=np.linalg.norm(error)
                        if length>bound:error*=bound/length
                    J=J.copy();J[3:]*=cfg.ik_rotation_row_weight
                    error=np.r_[position_error,cfg.ik_rotation_row_weight*cfg.ik_rotation_gain*rotation_error]
                    task_dq=J.T@np.linalg.solve(J@J.T+cfg.ik_damping**2*np.eye(6),error)
                self._last_pose_target=(target_position.copy(),target_quaternion.copy())
                self._last_pose_error_norm=position_error_norm
            elif not (position_error_norm<=cfg.ik_position_deadband
                      and rotation_error_norm<=cfg.ik_rotation_deadband):
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
            if accumulated_pose_target:
                self._arm_target=np.clip(
                    self._arm_target+cfg.ik_position_gain*np.clip(task_dq,-cfg.ik_max_delta_q,cfg.ik_max_delta_q),
                    self.arm_target_limits[:,0],self.arm_target_limits[:,1],
                )
                desired=self._arm_target.copy()
            else:
                desired=np.clip(q+cfg.ik_position_gain*np.clip(task_dq,-cfg.ik_max_delta_q,cfg.ik_max_delta_q),self.arm_target_limits[:,0],self.arm_target_limits[:,1])
        _resolved, servo = absolute_joint_position_servo(
            desired, q, self.arm_target_limits, cfg.joint_position_correction_gain,
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

    def resolve_world_pose_target_iterative_v1(
        self, *, current_joint_position_rad, current_pose_world: PoseWorld,
        target_pose_world, gripper_scalar: float, max_iterations: int = 12,
        position_tolerance_m: float = 0.006,
        orientation_tolerance_rad: float = 0.03,
        model_position_tolerance_m: float = 0.003,
        model_orientation_tolerance_rad: float = 0.03,
    ) -> CanonicalArmResolutionV1:
        """Iterate the existing shared DLS owner to a measured FK residual.

        Each iteration resolves the same typed absolute world pose from the
        previous joint target and that target's source FK pose. The operation
        is bounded, stateless, and provider-free. The historical single-step
        resolver above is unchanged.
        """
        if not isinstance(current_pose_world, PoseWorld):
            raise TypeError('iterative world-pose resolution requires a typed PoseWorld current pose')
        q = np.asarray(current_joint_position_rad, dtype=np.float64)
        pose = np.asarray(target_pose_world, dtype=np.float64)
        if (q.shape != (7,) or pose.shape != (7,)
                or not np.isfinite(q).all() or not np.isfinite(pose).all()
                or isinstance(gripper_scalar, bool) or not np.isfinite(gripper_scalar)):
            raise ValueError('iterative world-pose resolution requires finite seven-joint and seven-pose values')
        if (type(max_iterations) is not int or not 1 <= max_iterations <= 64
                or isinstance(position_tolerance_m, bool)
                or not np.isfinite(position_tolerance_m) or position_tolerance_m <= 0.0
                or isinstance(orientation_tolerance_rad, bool)
                or not np.isfinite(orientation_tolerance_rad) or orientation_tolerance_rad <= 0.0
                or isinstance(model_position_tolerance_m, bool)
                or not np.isfinite(model_position_tolerance_m) or model_position_tolerance_m <= 0.0
                or isinstance(model_orientation_tolerance_rad, bool)
                or not np.isfinite(model_orientation_tolerance_rad)
                or model_orientation_tolerance_rad <= 0.0):
            raise ValueError('iterative world-pose resolution bounds are invalid')
        requested = RequestedAction(
            'absolute_pose', 'world', 'quaternion_wxyz',
            tuple(float(value) for value in (*pose, float(gripper_scalar))),
        )
        requested.validate()
        original_q = q.copy()
        state_pose = np.asarray((*current_pose_world.position,
                                 *current_pose_world.quaternion_wxyz), dtype=np.float64)
        transform, _ = self.model.fk_jacobian(q)
        model_pose = PoseWorld(
            tuple(float(value) for value in transform[:3, 3]),
            tuple(float(value) for value in matrix_to_quat_wxyz(transform[:3, :3])),
        )
        initial_position_gap = float(np.linalg.norm(state_pose[:3] - np.asarray(model_pose.position)))
        initial_orientation_gap = float(np.linalg.norm(rotation_vector_error(
            quat_wxyz_to_matrix(state_pose[3:7]),
            quat_wxyz_to_matrix(np.asarray(model_pose.quaternion_wxyz)),
        )))
        if (initial_position_gap > model_position_tolerance_m
                or initial_orientation_gap > model_orientation_tolerance_rad):
            raise ValueError('public current TCP pose differs from the pinned source FK model')

        q_iter = q.copy()
        canonical = None
        desired = q_iter.copy()
        servo = q_iter.copy()
        position_residual = math.inf
        orientation_residual = math.inf
        iterations = 0
        for iterations in range(1, max_iterations + 1):
            transform, _ = self.model.fk_jacobian(q_iter)
            current_pose = PoseWorld(
                tuple(float(value) for value in transform[:3, 3]),
                tuple(float(value) for value in matrix_to_quat_wxyz(transform[:3, :3])),
            )
            state = SimpleNamespace(
                joint_position=dict(zip(ARM, map(float, q_iter), strict=True)),
                pose_world={'panda-v1/ee': current_pose},
            )
            canonical, desired, _intermediate_servo = self._compute_arm(state, requested)
            next_transform, _ = self.model.fk_jacobian(desired)
            next_pose = PoseWorld(
                tuple(float(value) for value in next_transform[:3, 3]),
                tuple(float(value) for value in matrix_to_quat_wxyz(next_transform[:3, :3])),
            )
            position_residual = float(np.linalg.norm(
                np.asarray(target_pose_world, dtype=np.float64)[:3]
                - np.asarray(next_pose.position, dtype=np.float64)
            ))
            orientation_residual = float(np.linalg.norm(rotation_vector_error(
                quat_wxyz_to_matrix(np.asarray(next_pose.quaternion_wxyz, dtype=np.float64)),
                quat_wxyz_to_matrix(np.asarray(target_pose_world, dtype=np.float64)[3:7]),
            )))
            q_iter = np.asarray(desired, dtype=np.float64).copy()
            if (position_residual <= position_tolerance_m
                    and orientation_residual <= orientation_tolerance_rad):
                break
            if np.linalg.norm(q_iter - q) <= 1e-12:
                break
            q = q_iter.copy()

        final_desired, final_servo = absolute_joint_position_servo(
            q_iter, original_q, self.model.limits, self.config.joint_position_correction_gain,
        )
        target = CanonicalArmTargetV1(
            'canonical-arm-target-v1', self.model.source_sha256,
            self.iterative_resolution_identity_v1(
                max_iterations=max_iterations,
                position_tolerance_m=position_tolerance_m,
                orientation_tolerance_rad=orientation_tolerance_rad,
                model_position_tolerance_m=model_position_tolerance_m,
                model_orientation_tolerance_rad=model_orientation_tolerance_rad,
            ),
            canonical, ARM, tuple(map(float, final_desired)), tuple(map(float, final_servo)),
        )
        target.validate()
        diagnostics = CanonicalArmResolutionDiagnosticsV1(
            'canonical-arm-resolution-diagnostics-v1',
            'shared_canonical_dls_iterative_v1', iterations, max_iterations,
            position_residual, orientation_residual, float(position_tolerance_m),
            float(orientation_tolerance_rad),
            position_residual <= position_tolerance_m
            and orientation_residual <= orientation_tolerance_rad,
            initial_position_gap, initial_orientation_gap,
            float(model_position_tolerance_m), float(model_orientation_tolerance_rad),
        )
        diagnostics.validate()
        result = CanonicalArmResolutionV1('canonical-arm-resolution-v1', target, diagnostics)
        result.validate()
        return result

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
