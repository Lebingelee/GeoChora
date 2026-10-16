"""Provider-free, measured-state oracles for the selected 100Hz outcome route.

The ideal tracking fixture executes real authored plans and native-sample guards;
it is a lifecycle/semantics test, never physical provider qualification.
"""
import numpy as np
import pytest
from dataclasses import replace

from task_env.tasks.nut_assembly.reference import build_reference, GUARDED_EXPERT, OUTCOME_COMPLETION
from task_env.tasks.nut_assembly.outcome_solution import NutAssemblyOutcomeSolutionV1
from task_env.tasks.nut_assembly.canonical_semantics import evaluate
from task_env.artifacts import CanonicalStateView, PoseWorld
from task_env.controllers.canonical.readiness import CanonicalControlReadiness, GripperReadiness
from task_env.utils.rotation import quat_multiply_wxyz, quat_wxyz_to_matrix

META = {'action_schema': {'controller_kind':'absolute_pose','reference':'world',
                          'rotation_representation':'quaternion_wxyz'}}


class Hold:
    locked = False
    def lock(self): self.locked = True


class Ideal:
    def __init__(self, *, residual=-.00022, release=True, authorize=True):
        value = build_reference(execution_policy=GUARDED_EXPERT)
        self.solution = NutAssemblyOutcomeSolutionV1(config=value['solution_config'],
            control_dt=.01, physics_dt_s=.002, arm_hold=Hold())
        self.ee = np.array([.5,-.075,.7,*value['solution_config'].grasp_quaternion_wxyz])
        self.nut = np.array([.5085,-.075,.473,0.,0.,0.,1.])
        self.peg = np.array([.58,.045,.5,1.,0.,0.,0.])
        self.opening=.08; self.residual=residual; self.release=release; self.authorize=authorize
        obs,info=self.boundary(0); self.solution.reset(obs,info,META)

    def boundary(self, step):
        poses={name:PoseWorld(tuple(map(float,p[:3])),tuple(map(float,p[3:]))) for name,p in
               [('panda-v1/ee',self.ee),('square-nut-v1',self.nut),('square-peg-v1',self.peg)]}
        joints={n:self.opening/2 for n in ['panda-v1/finger_joint1','panda-v1/finger_joint2']}
        state=CanonicalStateView('canonical-state-v0','SI_right_handed_z_up_wxyz',step,
            step*.01,joints,{n:0. for n in joints},poses)
        result=evaluate(state)
        obs={'state':{'ee_pose':self.ee.copy()},'privileged_state':{
            'square_nut_v1_body_pose':np.array([self.nut]),
            'square_peg_v1_body_pose':np.array([self.peg])}}
        return obs,{'is_success':result.success,'task_failure':False,
            'task_metrics':dict(result.metrics),'control_step':step,'simulation_time_s':step*.01}

    def step(self, mutate=None, terminated=False, truncated=False):
        s=self.solution; action=s.act(); stage=action.stage
        self.ee=np.array(action.action[:7],dtype=float)
        if stage=='descend_to_handle' and s._index>=len(s._actions):
            self.ee[2]=s._goal[2]-s.servo_height_compensation_m+self.residual
        if stage=='close_gripper': self.opening=.02
        if stage in s.capture_stages:
            self.nut[:3]=self.ee[:3]+quat_wxyz_to_matrix(self.ee[3:])@s._captured_position
            self.nut[3:]=quat_multiply_wxyz(self.ee[3:],s._captured_rotation)
        if stage in {'open_gripper','release_retreat'}:
            self.opening=.08 if self.release else .02
        obs,info=self.boundary(s._emitted)
        readiness=CanonicalControlReadiness('canonical-control-readiness-v1',s._emitted,
            s._emitted*.01,GripperReadiness('panda-v1/gripper',self.authorize,10.,10.,0.))
        samples=[]
        if stage=='close_gripper':
            for i in range(5):
                samples.append({'sample_time_s':(s._emitted-1)*.01+i*.002,'sample_duration_s':.002,
                    'conditions':{'controller_close_ready':self.authorize,
                        'measured_force_at_least_threshold':self.authorize,
                        'force_mode_active':self.authorize,'force_mode_initialized':self.authorize,
                        'grasped_nut':info['task_metrics']['grasped_nut'],'pose_ready':True},'values':{}})
        if mutate: mutate(obs,info)
        s.observe(obs,0.,terminated,truncated,info,readiness=readiness,transition_samples=samples)
        return stage,obs,info

    def until(self, stage):
        for _ in range(6100):
            if self.solution.stage==stage or self.solution.failed or self.solution.done:return
            self.step()
        raise AssertionError('unbounded fixture')


def test_warning_advances_without_diagnostic_override_and_retains_original_gate_measurements():
    f=Ideal(); f.until('close_gripper');s=f.solution
    assert s.stage=='close_gripper' and not s.failed and not s.outcome_complete
    warning,=s.readiness_warnings
    assert warning['reason']=='stable_height_mismatch'
    assert warning['height_residual_m']==pytest.approx(-.00022,abs=1e-12)
    assert warning['strict_tolerance_m']==.0001 and warning['sample_count']>=20
    assert s.original_expert_lifecycle_status['expert_failed']
    assert not s.original_expert_lifecycle_status['expert_complete']
    strict=build_reference(execution_policy=GUARDED_EXPERT)['solution']
    assert not strict._stable_height_ready(.5,.50022)


@pytest.mark.parametrize('residual',[-.00030001,.00030001])
def test_outside_height_warning_bound_still_fails(residual):
    f=Ideal(residual=residual);f.until('close_gripper')
    assert f.solution.failed and f.solution.failure_reason=='stable_height_mismatch'
    assert not f.solution.readiness_warnings


@pytest.mark.parametrize('reason',['preclose_motion_stability_timeout','close_gripper_authorization_deadline',
                                 'release_retreat_readiness_timeout','unknown_failure'])
def test_unapproved_failure_remains_fatal(reason):
    s=Ideal().solution;s._fail(reason)
    assert s.failed and s.failure_reason==reason and not s.outcome_complete


@pytest.mark.parametrize('field',['ee_nan','nut_inf','zero_quaternion','opening_nan',
                                'success_inconsistent','clock','string_nan_pose','string_predicate'])
def test_invalid_or_nonfinite_state_fails_closed(field):
    f=Ideal()
    def bad(obs,info):
        if field=='ee_nan':obs['state']['ee_pose'][0]=np.nan
        if field=='nut_inf':obs['privileged_state']['square_nut_v1_body_pose'][0,0]=np.inf
        if field=='zero_quaternion':obs['state']['ee_pose'][3:]=0
        if field=='opening_nan':info['task_metrics']['gripper_opening']=np.nan
        if field=='success_inconsistent':info['is_success']=True
        if field=='clock':info['simulation_time_s']+=.1
        if field=='string_nan_pose':obs['state']['ee_pose']=['nan',0.,0.,1.,0.,0.,0.]
        if field=='string_predicate':info['task_metrics']['released_nut']='False'
    f.step(bad)
    assert f.solution.failed and f.solution.failure_reason=='invalid_state_or_clock'


@pytest.mark.parametrize('flag',['terminated','truncated'])
def test_runtime_terminal_stops_before_warning_or_progression(flag):
    f=Ideal();f.step(**{flag:True})
    assert f.solution.failed and not f.solution.outcome_complete
    assert getattr(f.solution.lifecycle,'environment_'+flag)


def test_budget_and_runtime_error_and_task_failure_fail_closed():
    s=Ideal().solution;s._emitted=s._ticks(s.config.action_budget_s)
    with pytest.raises(RuntimeError):s.act()
    assert s.failure_reason=='canonical_solution_action_budget'
    s=Ideal().solution;s.abort('runtime_error')
    assert s.failed and not s.outcome_complete
    f=Ideal();f.step(lambda obs,info:info.update(task_failure=True))
    assert f.solution.failure_reason=='task_failure'


def test_guard_authorization_not_bypassed_by_height_warning():
    f=Ideal(authorize=False);f.until('verify_lift')
    assert f.solution.failed and f.solution.failure_reason=='close_gripper_authorization_deadline'


@pytest.mark.parametrize('violation',['translation','rotation'])
def test_capture_violation_hard_stops_during_transport(violation):
    f=Ideal();f.until('raise_for_transport')
    assert not f.solution.failed
    def bad(obs,info):
        p=obs['privileged_state']['square_nut_v1_body_pose'][0]
        if violation=='translation':p[0]+=.009
        else:p[3:]=quat_multiply_wxyz([np.cos(.1),np.sin(.1),0,0],p[3:])
    f.step(bad)
    assert f.solution.failed and f.solution.failure_reason=='capture_constraint_violation'


def test_full_authored_trajectory_measured_insertion_release_and_retreat_required():
    f=Ideal();f.until('release_retreat');s=f.solution
    assert not s.failed and not s.planned_trajectory_completed and not s.outcome_complete
    # Entering retreat, even with a successful task predicate, is insufficient.
    for _ in range(1000):
        if s.done or s.failed:break
        f.step()
    assert s.done and s.task_success and s.planned_trajectory_completed and s.outcome_complete
    receipt=s.outcome_report()['stage_execution_receipts'][-1]
    assert receipt['stage']=='release_retreat' and receipt['planned_actions_executed']==receipt['planned_actions']
    assert receipt['actions_executed']>=receipt['planned_actions']>0 and receipt['endpoint_pass']
    assert s.original_expert_lifecycle_status['expert_failed']
    # Late recording/runtime failure cannot leave the new outcome marked complete.
    s.abort('recording_error');assert not s.outcome_complete


def test_without_measured_release_task_cannot_complete():
    f=Ideal(release=False);f.until('release_retreat')
    assert f.solution.failed and not f.solution.task_success and not f.solution.outcome_complete


def test_default_and_source_policy_identity_and_complete_checkpoint_fields():
    v=build_reference();s=v['solution']
    assert isinstance(s,NutAssemblyOutcomeSolutionV1)
    assert v['execution_policy']['policy_id']==OUTCOME_COMPLETION and not v['diagnostic_shadow_mode']
    assert s.original_solution_identity=='15bfc3745c622ecb9eeb0b22248d2b12417ca3c40dbfd6b849ee06729b1dba2e'
    assert s.identity!=s.original_solution_identity
    assert v['source'].config.robot.gripper.force_limit_N==10.
    from task_env.diagnostics.phase1.integration.replay_preparation import _fields,_owner_version
    assert set(s.outcome_state_fields)<=set(_fields('coordinator',s))
    assert _owner_version('coordinator',s)=='coordinator-task-owned-outcome-v1'
    with pytest.raises(ValueError,match='only 100Hz'):build_reference(rate_hz=50)
    with pytest.raises(ValueError,match='unchanged physical limits'):
        NutAssemblyOutcomeSolutionV1(config=replace(s.config,capture_translation_slip_m=.009),
            control_dt=.01,physics_dt_s=.002,arm_hold=Hold())


@pytest.mark.parametrize('residual',[-.00029999,.00029999])
def test_admission_inside_explicit_height_bound(residual):
    f=Ideal(residual=residual);f.until('close_gripper')
    assert f.solution.stage=='close_gripper' and len(f.solution.readiness_warnings)==1


@pytest.mark.parametrize('fault',['pose_error','unstable'])
def test_original_pose_and_measured_stability_are_required(fault):
    f=Ideal();f.until('descend_to_handle')
    def bad(obs,info):
        if f.solution._index>=len(f.solution._actions):
            obs['state']['ee_pose'][0]+=(.01 if fault=='pose_error' else .001*(-1)**f.solution._emitted)
    for _ in range(1000):
        if f.solution.failed or f.solution.stage!='descend_to_handle':break
        f.step(bad)
    assert f.solution.failed and not f.solution.readiness_warnings


def test_repeat_warning_or_warning_at_another_stage_is_not_admitted():
    f=Ideal();f.until('close_gripper');s=f.solution
    s._observing=True
    assert not s._stable_height_ready(.5,.50022)
    s._stage_index=1
    assert not s._stable_height_ready(.5,.50022)
    assert len(s.readiness_warnings)==1


def test_historical_measured_opening_overshoot_is_not_a_new_command_range_gate():
    # Fresh failure/S1.5 matching boundary280: a command cap is not a measured
    # hard-stop threshold. Finite state, force cap and original predicates stay.
    f=Ideal();f.opening=.08000223711133003
    f.step()
    assert not f.solution.failed


@pytest.mark.parametrize('fault',['success_lost','retreat_pose'])
def test_final_success_and_retreat_gate_cannot_be_replaced_by_stage_entry(fault):
    f=Ideal();f.until('release_retreat');s=f.solution
    if fault=='success_lost':f.release=False
    for _ in range(1000):
        if s.done or s.failed:break
        f.step((lambda obs,info:obs['state']['ee_pose'].__setitem__(0,obs['state']['ee_pose'][0]+.02))
               if fault=='retreat_pose' else None)
    assert s.failed and not s.outcome_complete
    assert s.failure_reason==('final_task_success_not_valid' if fault=='success_lost'
                             else 'release_retreat_readiness_timeout')
