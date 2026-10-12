"""Deterministic mock-feedback preparation checks; never claims physical success."""
import argparse
from copy import deepcopy
from dataclasses import replace
import json
import traceback

import numpy as np

from .stable_grasp import context
from .replay_preparation import snapshot, restore, interval_record, decode_interval, clock_bound
from ....artifacts import CanonicalStateView, PoseWorld
from ....artifacts.execution import RealizedInitialState
from ....controllers.canonical.contracts import RequestedAction, AppliedCanonicalControl, digest
from ....controllers.canonical.feedback import CanonicalControlFeedback, CanonicalGripperFeedback
from ....controllers.canonical.kinematics import ARM, FINGERS
from ....controllers.canonical.execution import BoundaryWait
from ....tasks.nut_assembly.canonical_reset import sample_reset
from ....trajectory.canonical import EpisodeMetadata, BoundaryRecord, TransitionRecord, CanonicalRecorder, save, load
from ..nutassembly.common import observation, METADATA
from ..p1_2_runtime import execution


def fixture(v, step=0, force=0., opening=.03):
    sample = sample_reset(v['artifact'], 19)
    joints = dict(sample.joint_position)
    joints.update({n: opening / 2 for n in FINGERS})
    ee = v['controller'].hold.controller._arm.model.pose([joints[n] for n in ARM])
    poses = dict(sample.poses_world)
    poses.update({'panda-v1/ee': ee, 'panda-v1/base': PoseWorld((0., 0., 0.), (1., 0., 0., 0.)),
                  'square-peg-v1': PoseWorld((.6, 0., .5), (1., 0., 0., 0.))})
    state = CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz', step,
        step * v['artifact'].timebase.control_dt, joints, {n: 0. for n in joints}, poses)
    feedback = CanonicalControlFeedback('canonical-control-feedback-v0', step, state.simulation_time,
        CanonicalGripperFeedback('panda-v1/gripper', opening, force))
    return state, feedback


def initialize(v, state, feedback):
    v['controller'].reset(state, feedback)
    obs, info, _ = observation(state, v['artifact'])
    v['solution'].reset(obs, info, METADATA)


def ack(t):
    return AppliedCanonicalControl('applied-canonical-control-v0', t.identity_hash, 'mujoco',
        dict(t.arm_servo_position), t.gripper.servo_opening_m, t.gripper.force_limit_N, False, 'synthetic_exact')


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=__import__('pathlib').Path, required=True)
    args = p.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    tests = {}; negative = {}; first = None
    def check(name, predicate):
        if not predicate:
            raise AssertionError(name)
        tests[name] = True
    def rejects(name, fn):
        try:
            fn()
        except (ValueError, KeyError, RuntimeError, TypeError):
            negative[name] = True
        else:
            raise AssertionError('negative accepted: ' + name)
    try:
        for hz in (500, 100, 50):
            a, b = context(hz), context(hz)
            s, f = fixture(a); initialize(a, s, f); initialize(b, s, f)
            check(f'reset_exact_{hz}', snapshot(a,s,'mujoco') == snapshot(b,s,'mujoco'))
            dt = a['artifact'].timebase.control_dt
            all_intervals = []
            # Complete prefix, mock force-mode acquisition, locked hold and resume.
            for k in range(70):
                s, f = fixture(a,k, force=9.5 if k >= 2 else 0.)
                if k == 4:
                    a['controller'].hold.lock(); b['controller'].hold.lock()
                if k == 60:
                    a['controller'].hold.locked=False; b['controller'].hold.locked=False
                pose=s.pose_world['panda-v1/ee']; arr=np.array([*pose.position,*pose.quaternion_wxyz])
                for v in (a,b):
                    v['solution']._stability.is_stable(s.simulation_time,arr,
                        minimum_wait_s=.5,window_s=.2,minimum_samples=v['solution']._ticks(.2),axis_span_m=.0001,speed_m_s=.002)
                # Small moving world reference exercises feedforward and nonzero
                # persistent lead; actual state remains explicitly mock feedback.
                from ....utils.rotation import quat_multiply_wxyz
                arr = arr.copy(); arr[2] += .002 * k / 70
                yaw = .001 * k / 70
                arr[3:] = quat_multiply_wxyz(np.array([np.cos(yaw/2),0.,0.,np.sin(yaw/2)]),arr[3:])
                request=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,[*arr,-1.])))
                ca, ta=a['controller'].compute(s,f,request); cb,tb=b['controller'].compute(s,f,request)
                check(f'prefix_target_{hz}_{k}',ta.to_mapping()==tb.to_mapping())
                targets=[];acks=[];updates=[]
                for sub in range(a['artifact'].timebase.control_substeps):
                    ss=replace(s,simulation_time=s.simulation_time+sub*.002)
                    ff=replace(f,simulation_time=ss.simulation_time)
                    ga,da=a['controller'].inner_gripper_step(ss,ff);gb,db=b['controller'].inner_gripper_step(ss,ff)
                    check(f'inner_exact_{hz}_{k}_{sub}',ga==gb and da==db)
                    t=replace(ta,gripper=ga);targets.append(t);acks.append(ack(t));updates.append(da['inner_update_performed'])
                ir=interval_record(targets,acks,updates,step=k,physics_dt=.002,
                     substeps=len(targets),provider='mujoco')
                check(f'interval_decode_{hz}_{k}',[t.to_mapping() for t in decode_interval(ir,physics_dt=.002,substeps=len(targets),provider='mujoco')]==ir['targets'])
                all_intervals.append(ir)
                next_s,next_f=fixture(a,k+1,force=9.5)
                snap=snapshot(a,next_s,'mujoco')
                check(f'prefix_memory_{hz}_{k}',snap==snapshot(b,next_s,'mujoco'))
                # Independent fresh construction restores only explicit canonical owner memory.
                c=context(hz);initialize(c,next_s,next_f)
                encoded=json.loads(json.dumps(snap,allow_nan=False))
                restore(c,next_s,'mujoco',encoded)
                check(f'owner_roundtrip_{hz}_{k}',snapshot(c,next_s,'mujoco')==snap)
                probe=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,[*arr,-1.])))
                d=context(hz);initialize(d,next_s,next_f);restore(d,next_s,'mujoco',snap)
                check(f'restored_next_target_{hz}_{k}',c['controller'].compute(next_s,next_f,probe)[1]==d['controller'].compute(next_s,next_f,probe)[1])
            (args.output/f'intervals_tb{hz}.json').write_text(json.dumps(all_intervals))
            check(f'force_mode_restored_{hz}',a['controller']._force_mode and a['controller']._force_initialized)
            check(f'no_qref_reset_{hz}',a['controller']._q_ref_reset_events==1)
            check(f'prefix_vs_restored_next_target_{hz}',a['controller'].compute(next_s,next_f,probe)[1]==b['controller'].compute(next_s,next_f,probe)[1]==c['controller'].hold.last_target)
            if hz == 100:
                bad=deepcopy(snap);del bad['owners']['arm_gripper']['fields']['_previous_reference']
                bad['integrity_hash']=digest({k:v for k,v in bad.items() if k!='integrity_hash'})
                rejects('missing_history',lambda:restore(c,next_s,'mujoco',bad))
                bad=deepcopy(snap);bad['version']='incompatible';bad['integrity_hash']=digest({k:v for k,v in bad.items() if k!='integrity_hash'})
                rejects('wrong_snapshot_version',lambda:restore(c,next_s,'mujoco',bad))
                rejects('wrong_provider',lambda:restore(c,next_s,'geophys',snap))
                for name, mutation in [('missing_substep',lambda r:r['targets'].pop()),
                    ('duplicate_update',lambda r:r['updates'].__setitem__(1,True)),
                    ('wrong_timebase',lambda r:r.__setitem__('physics_dt',.003)),
                    ('corrupted_target_identity',lambda r:r['target_hashes'].__setitem__(0,'0'*64))]:
                    r=deepcopy(ir);mutation(r)
                    rejects(name,lambda:decode_interval(r,physics_dt=.002,substeps=5,provider='mujoco'))
        # Real coordinator close authorization counting / hold / capture restore.
        v=context(100);s,f=fixture(v,force=9.5);initialize(v,s,f)
        sol=v['solution'];obs,info,_=observation(s,v['artifact']);info['task_metrics']['grasped_nut']=True
        sol._stage_index=sol.STAGES.index('close_gripper');sol._grasp_pose=sol._ee(obs).copy();sol._plan(obs)
        sol._index=len(sol._actions);sol.arm_hold.fixed={n:s.joint_position[n] for n in ARM};sol.arm_hold.locked=True
        from ....controllers.canonical.readiness import CanonicalControlReadiness, GripperReadiness
        for k in range(1,11):
            sol._emitted=k
            ready=CanonicalControlReadiness('canonical-control-readiness-v1',k,k*.01,
                GripperReadiness('panda-v1/gripper',True,9.5,10.,.5))
            sol.observe(obs,0.,False,False,info,readiness=ready)
            if k == 5:
                v['controller'].hold.controller._expected_step=k
                checkpoint_state,checkpoint_feedback=fixture(v,k,force=9.5)
                partial=snapshot(v,checkpoint_state,'mujoco')
                resumed=context(100);initialize(resumed,checkpoint_state,checkpoint_feedback)
                restore(resumed,checkpoint_state,'mujoco',partial)
            elif k > 5:
                resumed['solution']._emitted=k
                resumed['solution'].observe(obs,0.,False,False,info,readiness=ready)
                check(f'partial_readiness_window_restore_{k}',resumed['solution']._stable_ticks==sol._stable_ticks and resumed['solution'].stage==sol.stage)
        check('readiness_0p1_window',sol.stage=='verify_lift' and sol.events[-2]['event']=='controller_close_authorized')
        baseline=sol._captured_position.copy();rotation=sol._captured_rotation.copy()
        v['controller'].hold.controller._expected_step=10;s,f=fixture(v,10,force=9.5)
        snap=snapshot(v,s,'mujoco');w=context(100);initialize(w,s,f);restore(w,s,'mujoco',snap)
        check('deadline_and_posthold_restored',w['solution']._close_gate.start_s==sol._close_gate.start_s and w['solution']._postclose_hold_ticks==10)
        check('capture_baseline_persistent',np.array_equal(w['solution']._captured_position,baseline) and np.array_equal(w['solution']._captured_rotation,rotation))
        for i in range(11):
            check(f'coordinator_hold_action_{i}',np.array_equal(sol.act().action,w['solution'].act().action))
        check('arm_unlock_after_hold',not sol.arm_hold.locked and not w['solution'].arm_hold.locked)
        bad=deepcopy(snap);bad['owners']['coordinator']['fields']['_captured_position']['value']['values'][0]+=.001
        rejects('changed_capture_baseline',lambda:restore(w,s,'mujoco',bad))
        check('expired_deadline_rejected',BoundaryWait(0.,1.5).wait_until(1.51,True)=='timeout')
        negative['expired_close_authorization']=tests['expired_deadline_rejected']
        # Clock count is independently exact; representation bound is not a physics tolerance.
        t=0.
        for n in range(1,10001):
            t+=.002
            check(f'clock_accumulation_{n}',abs(t-n*.002)<=clock_bound(n,.002))
        # Exercise the existing v0 recorder and H5 reader on genuine typed synthetic contracts.
        v=context(500);s,f=fixture(v);initialize(v,s,f);sample=sample_reset(v['artifact'],19)
        initial=RealizedInitialState('realized-initial-state-v0',sample.sample_id,'mujoco',s,0)
        meta=EpisodeMetadata('canonical-trajectory-metadata-v0',v['artifact'].identity_hash,sample,initial,
            execution('mujoco'),{'mode':'synthetic_no_physics'},{'source':'frozen_candidate'},v['artifact'].timebase,
            v['controller_identity'],v['solution_identity'],'1'*64,'2'*64,19,'regression')
        def boundary(s,f):return BoundaryRecord(s.control_step,s.simulation_time,s,f,v['controller'].readiness(s,f),{},False,False)
        recorder=CanonicalRecorder(meta,boundary(s,f))
        for k in range(8):
            pose=s.pose_world['panda-v1/ee'];r=RequestedAction('absolute_pose','world','quaternion_wxyz',(*pose.position,*pose.quaternion_wxyz,-1.))
            ca,t=v['controller'].compute(s,f,r)
            s,f=fixture(v,k+1)
            recorder.append(TransitionRecord(r,ca,t,ack(t),0.,False,False,'synthetic_track',{},True,False),boundary(s,f))
        trajectory=recorder.freeze('synthetic_endpoint');save(args.output/'synthetic_v0.h5',trajectory)
        check('v0_T_plus_1_roundtrip',load(args.output/'synthetic_v0.h5').to_mapping()==trajectory.to_mapping())
    except Exception:
        first=traceback.format_exc()
    result={'synthetic_only':True,'formal_D0_D1_D2_executed':False,'pass':first is None,
        'positive_checks':len(tests),'checks':{k:v for k,v in tests.items() if not k.startswith(('clock_accumulation','prefix_','inner_','interval_decode','owner_roundtrip','restored_next_target'))},
        'negative_cases':negative,'first_divergence':first,
        'limitations':['Opt-in diagnostics ABI; not promoted public schema',
            'No live coordinator/interval recorder wiring or checkpointed provider state replay',
            'Mock feedback does not establish mechanical competence']}
    (args.output/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['pass'] else 1)

if __name__=='__main__':main()
