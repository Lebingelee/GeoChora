"""Bounded public factory, isolated MuJoCo worker, one control interval."""
from pathlib import Path
import fcntl, json, resource, sys, time, traceback
plan=json.loads(Path(sys.argv[1]).read_text())
case=sys.argv[2] if len(sys.argv)>2 else 'pickcube'
if case not in {'pickcube','nut'}:
 raise ValueError('case must be pickcube or nut')
provider=sys.argv[3] if len(sys.argv)>3 else 'mujoco'
if provider not in {'mujoco','geophys'}:
 raise ValueError('provider must be mujoco or geophys')
resource.setrlimit(resource.RLIMIT_AS,(plan['rss_address_space_limit_bytes'],)*2)
resource.setrlimit(resource.RLIMIT_CPU,(120,125))
row={'status':'RUNNING','observed_native_substeps':None,'conservative_substep_charge':50}; locks=[]; env=None; start=time.monotonic()
try:
 for path in plan['locks_in_order']:
  fd=open(path,'r+'); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); locks.append(fd)
 import numpy as np
 from task_env import make_env
 config={'execution':{'physics_provider':provider,'deployment':'isolated_worker','interpreter':sys.executable},'episode':{'horizon':8}}
 env=make_env('nut-assembly-outcome-reference-v1' if case=='nut' else 'pick-cube-p16-reference-v1',config=config)
 binding=env.value['source'].position_subject_binding
 assert binding is not None and env.robot.subjects == binding.subjects
 row['robot_binding']=binding.identity_hash
 if case=='nut':
  solution=env.value['solution_factory']()
  obs,info=env.reset_for_solution(solution,seed=19)
 else:
  obs,info=env.reset(seed=31)
 row['reset_boundary']={'episode_id':env.session.episode_id, 'control_step':env.state.control_step, 'simulation_time':env.state.simulation_time}
 row['source']=env.value['source'].source_id
 action=np.asarray([.4,0.,.4,1.,0.,0.,0.,1.],np.float32)
 result=env.step_with_solution(solution) if case=='nut' else env.step(action)
 if case=='nut': assert not solution.failed
 row['step_boundary']={'episode_id':env.session.episode_id, 'control_step':env.state.control_step, 'simulation_time':env.state.simulation_time}
 assert row['step_boundary']['control_step']==row['reset_boundary']['control_step']+1
 assert row['step_boundary']['episode_id']==row['reset_boundary']['episode_id']
 env.reset(seed=19 if case=='nut' else 31)
 row['second_reset_boundary']={'episode_id':env.session.episode_id, 'control_step':env.state.control_step, 'simulation_time':env.state.simulation_time}
 assert row['second_reset_boundary']['episode_id']!=row['reset_boundary']['episode_id']
 env.close(); env.close(); row['status']='PASS'
except BaseException as error:
 row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
finally:
 if env is not None:
  try: env.close()
  except BaseException as error: row.update(status='FAIL',cleanup_error=repr(error))
 for fd in reversed(locks): fcntl.flock(fd,fcntl.LOCK_UN); fd.close()
 row.update(locks_released=True,wall_s=time.monotonic()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
 Path('result.json').write_text(json.dumps(row,indent=2)+'\n')
 print(json.dumps({k:row.get(k) for k in ('status','error','wall_s','conservative_substep_charge')}),flush=True)
raise SystemExit(0 if row['status']=='PASS' else 1)
