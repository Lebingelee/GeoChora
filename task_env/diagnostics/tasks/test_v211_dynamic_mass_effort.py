"""Pure checks for source dynamics injection and clipping policy."""
from dataclasses import replace
import numpy as np
import pytest
from task_env.controllers.canonical.dynamic_mass_effort import DynamicMassEffortControllerV1
from task_env.diagnostics.tasks.test_v211_mass_matrix_effort import _fixture


def test_dynamic_model_injected_at_matching_state_without_stepping():
    binding,context,state,matrix=_fixture()
    servo=DynamicMassEffortControllerV1(binding,cadence_s=.01,kp=10.,kd=2.,finger_kp=100.,finger_kd=4.)
    class Model:
        source_closure_sha256=binding.source_closure_sha256
        calls=[]
        def evaluate(self,q,qd,boundary):
            self.calls.append((q.copy(),qd.copy(),boundary))
            return {'mass_matrix':matrix,'bias':np.arange(8,dtype=float),'boundary':boundary,'physics_steps':0}
    model=Model();servo.bind_model(model)
    batch=servo.compute([.1,0,0,0,0,0,0,.04],state,context)
    assert [x.value for x in batch.joint_efforts] == pytest.approx([1.,1.1,2.,3.,4.,5.,6.,3.5,3.5])
    assert all(x.contribution.limit_order=='clip_after_sum' for x in batch.joint_efforts)
    assert len(model.calls)==1 and model.calls[0][2]==state.boundary
    with pytest.raises(ValueError,match='stale or foreign'):
        servo.compute([0.]*8,state,replace(context,boundary=replace(context.boundary,state_revision=1)))
    model.source_closure_sha256='c'*64
    with pytest.raises(ValueError,match='selected source'):
        servo.bind_model(model)


def test_mujoco_source_model_uses_scratch_state_without_physics_advance():
    from types import SimpleNamespace
    from task_env.runtime.sessions.mujoco_dynamics import MuJoCoSourceDynamicsV1
    _,context,_,_=_fixture()
    class Model:
        nv=9
        jnt_qposadr=np.arange(9)
        jnt_dofadr=np.arange(9)
    class Data:
        def __init__(self, model):
            self.qpos=np.zeros(9);self.qvel=np.zeros(9);self.qM=np.zeros(1);self.qfrc_bias=np.arange(9,dtype=float)
    class MJ:
        mjtObj=SimpleNamespace(mjOBJ_JOINT=0)
        MjData=Data
        forwards=0
        def mj_name2id(self,model,kind,name):
            return int(name[5:])-1 if name.startswith('joint') else (7 if name=='finger_joint1' else 8)
        def mj_forward(self,model,data):self.forwards+=1
        def mj_fullM(self,model,full,qM):full[:]=np.eye(9)
    api=MJ();model=Model();live=Data(model)
    session=SimpleNamespace(_require_reset=lambda:None,_mj=api,_model=model,_data=live,
        _source=SimpleNamespace(source_closure_digest='b'*64),
        provider_materialization_id=context.boundary.provider_materialization_id,
        state_boundary_identity=lambda:context.boundary)
    dynamics=MuJoCoSourceDynamicsV1(session)
    q=np.arange(9,dtype=float)*.01;result=dynamics.evaluate(q,np.zeros(9),context.boundary)
    assert result['physics_steps']==0 and api.forwards==1
    assert result['mass_matrix'][7,7]==2. and result['bias'][7]==15.
    np.testing.assert_array_equal(live.qpos,np.zeros(9))
    with pytest.raises(ValueError,match='foreign episode'):
        dynamics.evaluate(q,np.zeros(9),replace(context.boundary,episode_id='foreign'))
