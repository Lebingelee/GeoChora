"""S1 analytical wrench-reference oracle, independent of runtime outcomes."""
import numpy as np
from .native import wrench_at

def test_gravity_force_moments_about_distinct_points():
    # A 1 N downward force at x=1m: moment +1Nm about origin, +0.5Nm about COM.
    f=np.array([0.,0.,-1.]);point=np.array([1.,0.,0.]);zero=np.zeros(3)
    np.testing.assert_allclose(wrench_at(f,zero,point,zero),[0.,1.,0.],atol=1e-14)
    np.testing.assert_allclose(wrench_at(f,zero,point,np.array([.5,0.,0.])),[0.,.5,0.],atol=1e-14)

def test_wrench_reference_translation_identity():
    f=np.array([2.,3.,5.]);tau=np.array([.1,.2,.3]);p=np.array([.7,.8,.9]);a=np.array([.2,.3,.1]);b=np.array([.4,.2,.5])
    np.testing.assert_allclose(wrench_at(f,tau,p,a)-wrench_at(f,tau,p,b),np.cross(b-a,f),atol=1e-14)

def test_observer_preserves_native_step_and_reads_preintegration_state():
    import mujoco
    from .native import AppliedStepObserver
    from types import SimpleNamespace
    model=mujoco.MjModel.from_xml_string('<mujoco><option timestep="0.002" integrator="implicitfast"/><worldbody><body pos="0 0 1"><freejoint/><geom type="sphere" size="0.1" mass="1"/></body></worldbody></mujoco>')
    reference=mujoco.MjData(model);observed=mujoco.MjData(model)
    mujoco.mj_forward(model,reference);mujoco.mj_forward(model,observed)
    start_qpos=observed.qpos.copy();start_qvel=observed.qvel.copy()
    samples=[]
    class Recorder:
        errors=[]
        def capture(self,session,stage,pre):
            samples.append((stage,pre,session._data.time));return {'available':True}
    wrapped=AppliedStepObserver(mujoco,SimpleNamespace(_data=observed),Recorder(),lambda:'hold')
    mujoco.mj_step(model,reference);wrapped.mj_step(model,observed)
    np.testing.assert_array_equal(reference.qpos,observed.qpos)
    np.testing.assert_array_equal(reference.qvel,observed.qvel)
    assert len(samples)==1 and samples[0][0]=='hold'
    assert samples[0][1]['time_s']==0 and samples[0][2]==.002
    np.testing.assert_array_equal(samples[0][1]['qpos'],start_qpos)
    np.testing.assert_array_equal(samples[0][1]['qvel'],start_qvel)

def test_ramp_audit_rejects_off_schedule_before_physics():
    import pytest
    from types import SimpleNamespace
    from .arm_schedule import RampedArmAudit
    audit=RampedArmAudit.__new__(RampedArmAudit)
    audit.timebase=SimpleNamespace(control_substeps=25)
    audit._diagnostic_plan=({'joint':0.},{'joint':1.},True)
    audit._ramp_verified_count=0
    target=SimpleNamespace(arm_position={'joint':.041},arm_servo_position={'joint':.04})
    with pytest.raises(ValueError,match='diagnostic_arm_ramp_schedule_mismatch'):
        audit.execute_inner_substep(target,lambda:pytest.fail('invalid schedule advanced physics'))

def test_armature_intervention_updates_effective_inertia_without_live_reset():
    import mujoco
    from .mechanics import set_freejoint_armature
    m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><body pos="0 0 1"><joint type="free" armature=".03"/><geom type="sphere" size=".1" mass=".1"/></body></worldbody></mujoco>')
    d=mujoco.MjData(m);d.time=.75;d.qpos[:3]=[.2,.3,1.2];d.qvel[:]=np.arange(6)*.01;d.qacc_warmstart[:]=np.arange(6)*.1
    mujoco.mj_forward(m,d);q=d.qpos.copy();v=d.qvel.copy();warm=d.qacc_warmstart.copy()
    before=np.zeros((6,6));mujoco.mj_fullM(m,before,d.qM)
    proof=set_freejoint_armature(m,d,0,0.)
    assert proof['live_integration_state_exact'] and d.time==.75
    np.testing.assert_array_equal(d.qpos,q);np.testing.assert_array_equal(d.qvel,v);np.testing.assert_array_equal(d.qacc_warmstart,warm)
    mujoco.mj_forward(m,d);after=np.zeros((6,6));mujoco.mj_fullM(m,after,d.qM)
    np.testing.assert_allclose(before-after,.03*np.eye(6),rtol=0,atol=1e-14)

def test_native_gripper_intervention_does_not_enable_model_switch():
    from .run import NATIVE_GRIP_CASES,LIFT_INTERVENTION_CASES,ARM_RAMP_CASES
    assert NATIVE_GRIP_CASES.isdisjoint(LIFT_INTERVENTION_CASES)
    assert NATIVE_GRIP_CASES & ARM_RAMP_CASES == {'arm_ramp_native_grip'}

def test_freebody_damping_changes_realized_passive_force():
    import mujoco
    m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><joint type="free" damping="2" armature=".03"/><geom type="sphere" size=".1" mass=".1"/></body></worldbody></mujoco>')
    d=mujoco.MjData(m);d.qvel[:]=[.1,-.2,.3,.4,-.5,.6]
    mujoco.mj_forward(m,d);np.testing.assert_allclose(d.qfrc_passive,-2*d.qvel,atol=1e-14)
    q=d.qpos.copy();v=d.qvel.copy();m.dof_damping[:]=0
    mujoco.mj_forward(m,d);np.testing.assert_array_equal(d.qfrc_passive,np.zeros(6))
    np.testing.assert_array_equal(d.qpos,q);np.testing.assert_array_equal(d.qvel,v)
