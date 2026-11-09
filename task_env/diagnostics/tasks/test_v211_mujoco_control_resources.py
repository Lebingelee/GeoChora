"""Native DOF conflict-domain checks; synthetic model, no native steps."""
from types import SimpleNamespace
import numpy as np
import pytest

from task_env.runtime.sessions.mujoco_control_resources import position_native_dofs


def _fixture():
    mj = SimpleNamespace(mjtJoint=SimpleNamespace(mjJNT_HINGE=1, mjJNT_SLIDE=2),
        mjtTrn=SimpleNamespace(mjTRN_JOINT=3, mjTRN_TENDON=4),
        mjtWrap=SimpleNamespace(mjWRAP_JOINT=5), mjtEq=SimpleNamespace(mjEQ_JOINT=6))
    model = SimpleNamespace(nu=2, ntendon=1, njnt=4, nv=4, neq=1,
        actuator=lambda name: SimpleNamespace(id={'actuator1':0, 'actuator8':1}[name]),
        joint=lambda name: SimpleNamespace(id={'joint1':0}[name]),
        actuator_trntype=[3,4], actuator_trnid=[[0,0],[0,0]],
        tendon_adr=[0], tendon_num=[2], wrap_type=[5,5], wrap_objid=[1,2],
        jnt_type=[1,2,2,1], jnt_dofadr=[0,1,2,3],
        eq_type=[6], eq_obj1id=[2], eq_obj2id=[3])
    source=SimpleNamespace(joint_targets={'panda/joint1':'actuator1'},
        joints={'panda/joint1':'joint1'}, open_actuators=('actuator8',))
    profile=SimpleNamespace(entity_id='panda',writer_id='writer',
        _target_bindings={'panda/joint1':'actuator1'},open_actuator='actuator8')
    plan=SimpleNamespace(resource_writers=(('panda','actuator1','writer'),('panda','actuator8','writer')))
    return SimpleNamespace(_model=model,_mj=mj,_source=source,_data=SimpleNamespace(eq_active=np.array([1]))), profile, plan


def test_native_dof_footprint_includes_tendon_and_live_equality():
    session, profile, plan = _fixture()
    assert position_native_dofs(session,profile,plan)==frozenset({0,1,2,3})
    session._data.eq_active[0]=0
    assert position_native_dofs(session,profile,plan)==frozenset({0,1,2})


def test_native_dof_footprint_rejects_foreign_resource_or_unknown_topology():
    session, profile, plan = _fixture()
    session._source.joint_targets['panda/joint1']='other'
    with pytest.raises(ValueError,match='bound native source'):
        position_native_dofs(session,profile,plan)
    session._source.joint_targets['panda/joint1']='actuator1'
    session._model.wrap_type[1]=9
    with pytest.raises(ValueError,match='joint-only'):
        position_native_dofs(session,profile,plan)
    session._model.wrap_type[1]=5
    session._model.eq_type[0]=9
    with pytest.raises(ValueError,match='non-joint'):
        position_native_dofs(session,profile,plan)
