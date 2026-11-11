"""Bounded public-factory CPU check; SDK step counting is external instrumentation."""
from pathlib import Path
import argparse,datetime,fcntl,json,os,resource,sys,time,traceback
parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);parser.add_argument('--plan',required=True);args=parser.parse_args()
plan=json.loads(Path(args.plan).read_text())
started=time.monotonic();locks=[];env=None;result={'case':args.case,'status':'RUNNING','steps':[],'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_substeps':0}
resource.setrlimit(resource.RLIMIT_AS,(plan['rss_address_space_limit_bytes'],)*2)
resource.setrlimit(resource.RLIMIT_CPU,(120,125))
try:
    for path in plan['locks_in_order']:
        handle=open(path,'r+');fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(handle)
    result['locks_acquired']=True
    import numpy as np
    import mujoco
    original_step=mujoco.mj_step
    def counted_step(*params,**kwargs):
        count=kwargs.get('nstep',params[2] if len(params)>2 else 1)
        if result['native_substeps']+int(count)>plan['per_run_reserved_physics_substeps']:
            raise RuntimeError('reserved physics substep limit exhausted')
        result['native_substeps']+=int(count)
        return original_step(*params,**kwargs)
    mujoco.mj_step=counted_step
    from task_env import make_env
    if args.case in {'panda-r3','panda-gravity','assembled-unreset','assembled-live','nut'}:
        config={'execution':{'physics_provider':'mujoco','physics_backend':'cpu','physics_device':'cpu','deployment':'in_process','interpreter':sys.executable},'episode':{'horizon':8}}
        if args.case=='panda-gravity':config['controller']={'gravity_compensation':True}
        if args.case.startswith('assembled'):config.update(robot={'uid':'panda-arm-hand-v1'},task={'controller_profile':'r1_split'})
        uid='nut-assembly-outcome-reference-v1' if args.case=='nut' else 'pick-cube-p16-reference-v1'
        env=make_env(uid,config=config)
        action=np.asarray([.4,0.,.4,1.,0.,0.,0.,1.],dtype=np.float32)
    else:
        uid='pendulum-v1' if args.case=='pendulum' else 'two-wheel-balance-v1'
        env=make_env(uid,config={'execution':{'physics_provider':'mujoco','physics_backend':'cpu','physics_device':'cpu'},'episode':{'horizon':8}})
        action={'torque':np.asarray([.25]if args.case=='pendulum'else[.25,-.2],dtype=np.float32)}
    result['uid']=env.uid
    result['constructed']=True
    robot=env.robot
    result['robot']={'uid':robot.uid,'subjects':[s.subject_id for s in robot.subjects],
        'parents':[s.parent_subject_id for s in robot.subjects],
        'controller_identities':[str(c.identity) for c in robot.controllers]}
    assert robot.controller is env.controller
    subject_binding=getattr(env.value['source'],'position_subject_binding',None)
    if args.case in {'nut','panda-r3','assembled-live'}:
        assert subject_binding is not None and robot.subjects == subject_binding.subjects
        result['robot']['binding_identity']=subject_binding.identity_hash
        result['robot']['resource_writers']=list(subject_binding.plan.resource_writers)

    receipt=getattr(env.value['source'],'execution_source_receipt',None)
    snapshot=None if receipt is None else str(receipt.snapshot_root)
    result['source_snapshot']=snapshot
    if args.case!='assembled-unreset':
        if args.case=='nut':
            solution=env.value['solution_factory']()
            observation,info=env.reset_for_solution(solution,seed=19)
        else:
            observation,info=env.reset(seed=31)
        first=env.session.state_boundary_identity().to_mapping()
        if subject_binding is not None:
            live_binding=env.session._source.position_subject_binding
            assert live_binding.identity_hash==env.value['source'].position_subject_binding.identity_hash
        if args.case in {'pendulum','two-wheel'}:
            first_reset_parameters=dict(info['reset_parameters'])
            first_observation=np.asarray(observation['state']['proprioception']).copy()

        time_before=float(env.state.simulation_time)
        stepped=env.step_with_solution(solution) if args.case=='nut' else env.step(action)
        if args.case=='nut':
            assert not solution.failed
        second=env.session.state_boundary_identity().to_mapping()
        time_after=float(env.state.simulation_time)
        result['steps'].append({'before':first,'after':second,'time_before':time_before,'time_after':time_after,'reward':float(stepped[1]),'terminated':bool(stepped[2]),'truncated':bool(stepped[3])})
        assert time_after>time_before
        assert abs(time_after-time_before-env.artifact.timebase.control_dt)<1e-9
        observation,info=env.reset(seed=19 if args.case=='nut' else 31)
        reset=env.session.state_boundary_identity().to_mapping()
        assert reset['episode_id']!=first['episode_id']
        result['second_reset']=reset
        assert env.robot is not robot and env.robot.controller is env.controller
        result['robot_rebound_after_reset']=True
        if args.case in {'pendulum','two-wheel'}:
            assert info['reset_parameters']==first_reset_parameters
            np.testing.assert_allclose(observation['state']['proprioception'],first_observation,atol=1e-6)
            observation,info=env.reset(seed=None)
            rng=np.random.default_rng(31)
            limits=([(-np.pi,np.pi),(-1.,1.)] if args.case=='pendulum' else
                    [(-.08,.08),(-.20,.20),(-.02,.02),(-.02,.02),(-.30,.30),(-.30,.30)])
            tuple(rng.uniform(a,b) for a,b in limits)
            expected=tuple(float(rng.uniform(a,b)) for a,b in limits)
            if args.case=='pendulum':expected=tuple(float(np.float32(x)) for x in expected)
            sample=env.value['reset_plan'].reset_sample
            if args.case=='pendulum':
                joints=('pendulum-v1/pendulum_hinge',)
                actual=(sample.joint_position[joints[0]],sample.joint_velocity[joints[0]])
            else:
                joints=tuple('two-wheel-balance-v1/'+n for n in ('chassis_pitch','left_wheel_hinge','right_wheel_hinge'))
                actual=(sample.joint_position[joints[0]],sample.joint_velocity[joints[0]],
                        sample.joint_position[joints[1]],sample.joint_position[joints[2]],
                        sample.joint_velocity[joints[1]],sample.joint_velocity[joints[2]])
            np.testing.assert_allclose(actual,expected,atol=0,rtol=0)
            np.testing.assert_allclose([env.state.joint_position[j] for j in joints],
                                      [sample.joint_position[j] for j in joints],atol=1e-6,rtol=0)
            result['rng_sequence']={'seed':31,'seed_none_after_repeat':list(actual),
                'independent_expected':list(expected),'info_seed':info['seed'],
                'reset_parameters':info['reset_parameters']}

    current_receipt=getattr(env.value['source'],'execution_source_receipt',None)
    current_snapshot=None if current_receipt is None else str(current_receipt.snapshot_root)
    result['current_source_snapshot_before_close']=current_snapshot
    env.close();env.close();result['repeated_close_completed']=True
    result['current_source_snapshot_exists_after_close']=None if current_snapshot is None else Path(current_snapshot).exists()
    result['source_snapshot_exists_after_close']=None if snapshot is None else Path(snapshot).exists()
    result['status']='PASS'
except BaseException as error:
    result['status']='FAIL';result['error']={'type':type(error).__name__,'message':str(error),
        'receipt':getattr(error,'receipt',None)};traceback.print_exc()
finally:
    if env is not None:
        try:env.close()
        except BaseException as error:result['cleanup_error']={'type':type(error).__name__,'message':str(error)};result['status']='FAIL'
    result['wall_s']=time.monotonic()-started;result['max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for handle in reversed(locks):fcntl.flock(handle,fcntl.LOCK_UN);handle.close()
    result['locks_released']=True
    Path('result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'case':args.case,'status':result['status'],'native_substeps':result['native_substeps'],'wall_s':result['wall_s']}))
raise SystemExit(0 if result['status']=='PASS'else 1)
