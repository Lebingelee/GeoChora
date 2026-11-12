"""Provider-neutral, source-bound joint-reference effort using a fixed local mass model."""
from __future__ import annotations

import math
import numpy as np

from .contracts import digest
from .physical_commands import ContributionPolicyV1, JointEffortV1, PhysicalCommandBatchV1, PhysicalCommandContextV1, PhysicalControlBindingV1


class MassMatrixEffortControllerV1:
    """Map named reference acceleration through an injected 8-DOF mass matrix.

    Seven arm coordinates and one equal-finger coordinate are used. The mass
    matrix is a bounded nominal model, not a live provider object or a force
    measurement. The fixed model's source and allowed state neighborhood are
    part of controller identity; admission must verify native drive isolation.
    """
    def __init__(self, binding, *, matrix, nominal_position, max_abs_deviation,
                 model_sha256, cadence_s, kp=20., kd=2., selection_profile_id=None):
        if type(binding) is not PhysicalControlBindingV1:
            raise TypeError('mass effort controller requires a typed physical binding')
        names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
        channels = tuple(binding.channels)
        if (len(channels) != 9 or tuple(c.joint_id for c in channels) != names
                or len({c.entity_id for c in channels}) != 1
                or any(c.native_drive != 'disabled' or c.owner_ids != channels[0].owner_ids for c in channels)
                or len(channels[0].owner_ids) != 1):
            raise ValueError('mass effort controller requires isolated named Panda channels and one owner')
        M = np.asarray(matrix, dtype=np.float64)
        q0 = np.asarray(nominal_position, dtype=np.float64)
        radius = np.asarray(max_abs_deviation, dtype=np.float64)
        if (M.shape != (8, 8) or q0.shape != (8,) or radius.shape != (8,)
                or not np.isfinite(M).all() or not np.isfinite(q0).all() or not np.isfinite(radius).all()
                or not np.allclose(M, M.T, rtol=0., atol=1e-6)
                or np.min(np.linalg.eigvalsh((M+M.T)*.5)) <= 0. or np.any(radius <= 0.)):
            raise ValueError('nominal reduced mass model must be finite, symmetric and positive definite')
        if (not isinstance(model_sha256, str) or len(model_sha256) != 64
                or any(c not in '0123456789abcdef' for c in model_sha256)
                or not all(math.isfinite(float(x)) and float(x) > 0 for x in (cadence_s, kp, kd))):
            raise ValueError('mass model identity, cadence and gains must be valid')
        self.binding, self.writer_id = binding, channels[0].owner_ids[0]
        self._channels, self._matrix = channels, M.copy()
        self._nominal, self._radius = q0.copy(), radius.copy()
        self._cadence, self._kp, self._kd = float(cadence_s), float(kp), float(kd)
        self.profile_id = selection_profile_id
        identity = {'schema':'mass-matrix-effort-controller-v1','binding':binding.identity_hash,
            'model_sha256':model_sha256,'matrix':M.tolist(),'nominal':q0.tolist(),'radius':radius.tolist(),
            'cadence_s':self._cadence,'kp_s-2':self._kp,'kd_s-1':self._kd,
            'pair_projection':'equal-coordinate-half-effort'}
        if selection_profile_id is not None:
            from ...artifacts.contracts import _name
            _name(selection_profile_id)
            identity['selection_profile_id'] = selection_profile_id
        self.identity = digest(identity)

    @property
    def action_shape(self):
        return (8,)

    def compute(self, action, state, context):
        if type(context) is not PhysicalCommandContextV1:
            raise TypeError('mass effort controller requires a typed interval context')
        if (state.boundary != context.boundary or state.sample_clock != context.clock
                or (context.source_id,context.source_closure_sha256,context.artifact_sha256) !=
                   (self.binding.source_id,self.binding.source_closure_sha256,self.binding.artifact_sha256)
                or not math.isclose(context.cadence_s,self._cadence,rel_tol=0.,abs_tol=1e-12)):
            raise ValueError('mass effort state, source, or cadence is stale or foreign')
        raw=np.asarray(action)
        if raw.shape != (8,) or raw.dtype.kind not in {'i','u','f'} or not np.isfinite(raw).all():
            raise ValueError('mass effort reference needs eight finite real values')
        refs=np.asarray(raw,dtype=np.float64).copy();refs[7]*=.5
        if not 0. <= refs[7] <= .04:
            raise ValueError('paired opening reference is outside the declared range')
        entity=self._channels[0].entity_id
        joints={x.joint_id:x for x in state.joints if x.entity_id==entity}
        if set(joints)!={c.joint_id for c in self._channels}:
            raise ValueError('mass effort state does not contain the exact named Panda joints')
        q=np.array([float(joints[c.joint_id].position[0]) for c in self._channels]);v=np.array([float(joints[c.joint_id].velocity[0]) for c in self._channels])
        reduced_q=np.r_[q[:7],.5*(q[7]+q[8])];reduced_v=np.r_[v[:7],.5*(v[7]+v[8])]
        if not np.isfinite(q).all() or not np.isfinite(v).all() or np.any(np.abs(reduced_q-self._nominal)>self._radius):
            raise ValueError('mass effort state exceeds the bounded nominal model neighborhood')
        with np.errstate(over='ignore', invalid='ignore'):
            acceleration=self._kp*(refs-reduced_q)-self._kd*reduced_v
            force=self._matrix@acceleration
        if not np.isfinite(acceleration).all() or not np.isfinite(force).all():
            raise ValueError('mass effort controller produced nonfinite effort')
        values=np.r_[force[:7],.5*force[7],.5*force[7]]
        efforts=[]
        for i,channel in enumerate(self._channels):
            policy=ContributionPolicyV1('physical-contribution-policy-v1',f'{self.writer_id}/channel-{i}',
                f'{self.writer_id}/effect-{i}',self.writer_id,'exclusive','reject_outside','one_interval')
            efforts.append(JointEffortV1('joint-effort-v1',context,policy,channel.entity_id,channel.joint_id,
                channel.dof_id,channel.kind,channel.axis,channel.axis_frame,channel.sign,channel.unit,
                float(values[i]),channel.effort_range,'explicit_full_pd'))
        return PhysicalCommandBatchV1('physical-command-batch-v1',context,tuple(efforts),(),())


def build_mass_effort_execution(direct_execution, *, matrix, nominal_position, max_abs_deviation,
                                model_sha256, use_pose_reference=False, r3_reference=None,
                                end_frame_id='ee', selection_profile_id=None):
    """Compose a source-admitted mass servo into an existing physical execution."""
    from dataclasses import replace
    from ...artifacts.state import StateFieldRequirement, StateRequirements
    from .r3_effort import R3ReferenceEffortControllerV1

    binding = direct_execution.compiled.binding
    cadence = direct_execution.controllers[0].model.requirement.cadence_s
    servo = MassMatrixEffortControllerV1(binding, matrix=matrix,
        nominal_position=nominal_position, max_abs_deviation=max_abs_deviation,
        model_sha256=model_sha256, cadence_s=cadence, selection_profile_id=selection_profile_id)
    requirements = direct_execution.requirements
    if use_pose_reference:
        from .production_r3 import _ProductionR3ArmReference
        if not isinstance(r3_reference, _ProductionR3ArmReference):
            raise TypeError('mass pose control requires the existing production R3 reference')
        entity = binding.channels[0].entity_id
        field = StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world', 'frame', entity,
            end_frame_id, 'required', 'evaluation_boundary', 'meter+quaternion_wxyz', 'frame_pose_query')
        requirements = StateRequirements('state-requirements-v1', 'controller', servo.writer_id,
                                          (*requirements.requirements, field))
        controller = R3ReferenceEffortControllerV1(r3_reference, servo, entity_id=entity,
            end_frame_id=end_frame_id, opening_range_m=.08, selection_profile_id=selection_profile_id)
    else:
        controller = servo
    return replace(direct_execution, controllers=(controller,), requirements=requirements)
