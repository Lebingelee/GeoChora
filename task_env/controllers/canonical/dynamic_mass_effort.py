"""Provider-neutral reference effort using an injected source dynamics model."""
from __future__ import annotations
import math
import numpy as np
from .contracts import digest
from .physical_commands import ContributionPolicyV1, JointEffortV1, PhysicalCommandBatchV1, PhysicalCommandContextV1, PhysicalControlBindingV1


class DynamicMassEffortControllerV1:
    """Source-bound inverse dynamics with an injected model and constrained pair.

    The model is supplied after actual reset by the selected runtime and must
    compute from supplied state without advancing physics. Output is explicitly
    clipped at the typed command admission boundary; it is not measured force.
    """
    def __init__(self, binding, *, cadence_s, kp=120., kd=22., finger_kp=1200., finger_kd=35.):
        if type(binding) is not PhysicalControlBindingV1:
            raise TypeError('dynamic effort requires a typed binding')
        channels = tuple(binding.channels)
        names = tuple(f'joint{i}' for i in range(1,8)) + ('finger_joint1','finger_joint2')
        if (len(channels)!=9 or tuple(c.joint_id for c in channels)!=names
                or len({c.entity_id for c in channels})!=1
                or any(c.native_drive!='disabled' or c.owner_ids!=channels[0].owner_ids for c in channels)
                or len(channels[0].owner_ids)!=1):
            raise ValueError('dynamic effort requires nine isolated named Panda channels')
        gains = (cadence_s,kp,kd,finger_kp,finger_kd)
        if not all(math.isfinite(float(x)) and float(x)>0 for x in gains):
            raise ValueError('dynamic effort gains and cadence must be positive and finite')
        self.binding, self._channels, self.writer_id = binding, channels, channels[0].owner_ids[0]
        self._cadence,self._kp,self._kd,self._finger_kp,self._finger_kd = map(float,gains)
        self._model = None
        self.identity = digest({'schema':'dynamic-mass-effort-v1','binding':binding.identity_hash,
            'cadence_s':self._cadence,'kp':self._kp,'kd':self._kd,'finger_kp':self._finger_kp,
            'finger_kd':self._finger_kd,'model':'source-bound-live-state-no-step-v1',
            'limit_order':'clip_after_sum','finger_projection':'equal-pair-half-effort'})

    @property
    def action_shape(self): return (8,)

    def bind_model(self, model):
        if (not callable(getattr(model,'evaluate',None)) or
                getattr(model,'source_closure_sha256',None)!=self.binding.source_closure_sha256):
            raise ValueError('dynamic model is missing or differs from the selected source')
        self._model = model

    def compute(self, action, state, context):
        if type(context) is not PhysicalCommandContextV1:
            raise TypeError('dynamic effort requires a typed interval context')
        if (state.boundary!=context.boundary or state.sample_clock!=context.clock or
            (context.source_id,context.source_closure_sha256,context.artifact_sha256)!=
            (self.binding.source_id,self.binding.source_closure_sha256,self.binding.artifact_sha256) or
            not math.isclose(context.cadence_s,self._cadence,rel_tol=0.,abs_tol=1e-12)):
            raise ValueError('dynamic effort state, source or cadence is stale or foreign')
        raw=np.asarray(action)
        if raw.shape!=(8,) or raw.dtype.kind not in 'iuf' or not np.isfinite(raw).all():
            raise ValueError('dynamic effort requires eight finite reference values')
        refs=np.asarray(raw,dtype=np.float64).copy();refs[7]*=.5
        if not 0.<=refs[7]<=.04: raise ValueError('paired opening reference outside declared range')
        entity=self._channels[0].entity_id
        joints={j.joint_id:j for j in state.joints if j.entity_id==entity}
        if set(joints)!={c.joint_id for c in self._channels}:
            raise ValueError('dynamic effort requires the exact named Panda state')
        q=np.array([float(joints[c.joint_id].position[0]) for c in self._channels])
        velocity=np.array([float(joints[c.joint_id].velocity[0]) for c in self._channels])
        if not np.isfinite(q).all() or not np.isfinite(velocity).all() or self._model is None:
            raise ValueError('dynamic effort requires finite state and a bound source model')
        model=self._model.evaluate(q,velocity,state.boundary)
        matrix=np.asarray(model['mass_matrix'],dtype=np.float64);bias=np.asarray(model['bias'],dtype=np.float64)
        if (matrix.shape!=(8,8) or bias.shape!=(8,) or not np.isfinite(matrix).all() or not np.isfinite(bias).all()
                or model.get('boundary')!=state.boundary or model.get('physics_steps')!=0):
            raise ValueError('dynamic source model returned invalid or stale facts')
        reduced_q=np.r_[q[:7],.5*(q[7]+q[8])];reduced_v=np.r_[velocity[:7],.5*(velocity[7]+velocity[8])]
        acceleration=self._kp*(refs-reduced_q)-self._kd*reduced_v
        force=matrix@acceleration+bias
        # The pair is controlled in its single independent coordinate. The
        # finger term provides the specified contact effort inside source limits.
        force[7]=self._finger_kp*(refs[7]-reduced_q[7])-self._finger_kd*reduced_v[7]+bias[7]
        if not np.isfinite(force).all():raise ValueError('dynamic effort produced nonfinite values')
        values=np.r_[force[:7],.5*force[7],.5*force[7]]
        commands=[]
        for i,c in enumerate(self._channels):
            policy=ContributionPolicyV1('physical-contribution-policy-v1',f'{self.writer_id}/channel-{i}',
                f'{self.writer_id}/effect-{i}',self.writer_id,'exclusive','clip_after_sum','one_interval')
            commands.append(JointEffortV1('joint-effort-v1',context,policy,c.entity_id,c.joint_id,c.dof_id,
                c.kind,c.axis,c.axis_frame,c.sign,c.unit,float(values[i]),c.effort_range,'explicit_full_pd'))
        return PhysicalCommandBatchV1('physical-command-batch-v1',context,tuple(commands),(),())
