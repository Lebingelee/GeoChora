"""Execute unchanged official legacy planning loop; passive native trace only.

Invoke this file from the exact historical worktree, without adding source there.
"""
import argparse
from collections.abc import Mapping
from collections import Counter
from dataclasses import asdict, is_dataclass, fields
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np


def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if is_dataclass(value):return {f.name:plain(getattr(value,f.name)) for f in fields(value)}
    if isinstance(value,Mapping):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def contact_reader(boundary,names):
    from runtime.diagnostics import DiagnosticsConfig
    from runtime.readback_probe import explicit_to_numpy
    packet=boundary._physics.query_diagnostics(DiagnosticsConfig(contacts=True)).contacts
    arrays={k:explicit_to_numpy(getattr(packet,'body_contact_'+k),reason='historical_nutassembly_passive_trace') for k in ('active','body_a','body_b','point','penetration','normal_impulse')}
    count=int(packet.body_contact_count[None]);result=[]
    inverse={i:n for n,i in names.bodies.items()}
    for i in range(min(count,len(arrays['active']))):
        if arrays['active'][i]:result.append({'source_body_names':[inverse[int(arrays['body_a'][i])],inverse[int(arrays['body_b'][i])]],'point_world':arrays['point'][i].tolist(),'separation_m':-float(arrays['penetration'][i]),'normal_impulse_native':float(arrays['normal_impulse'][i])})
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--backend',default='cpu');args=p.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    if (folder/'reproduction.json').exists():raise FileExistsError('historical Evidence collision')
    from task_env import make_env
    from task_env.script.trajectory._task_plans import _build_plan
    from task_env.script.trajectory.planning._common import rollout_solution
    from task_env.environment import SnapshotRequest
    config,solution=_build_plan('nut-assembly-square-v1',args.backend,600,camera_obs=False,force_limit_N=30.,camera_size=32)
    env=make_env('nut-assembly-square-v1',config=config);trace=[];actions=[]
    def capture(obs,info,stage,action=None):
        snap=env._runtime.read_snapshot(SnapshotRequest(qacc=False,actuator_force=True,simulation_time=True))
        refs=env._runtime_assembly.compiled_scene.references;agent=refs.agents['panda-v1'];g=env._robot.gripper
        row={'control_step':len(trace),'simulation_time_s':float(snap.simulation_time),'stage':stage,'observation':plain(obs),'info':plain({k:v for k,v in info.items() if k in {'is_success','task_failure','task_metrics','elapsed_steps'}}),
            'qpos_native':plain(snap.qpos),'qvel_native':plain(snap.qvel),'ctrl_native':plain(snap.ctrl),'actuator_force_native':plain(snap.actuator_force),
            'body_pose_native':{'position':plain(snap.body_xpos),'quaternion_wxyz':plain(snap.body_xquat)},'body_names':dict(refs.names.bodies),
            'finger_position':plain(snap.qpos[agent.gripper_qpos_ids]),'public_action':plain(action),
            'gripper_memory':{'commanded_opening_m':g._commanded_opening_m,'force_mode':g._force_mode_active,'force_initialized':g._force_mode_initialized},
            'native_contacts':contact_reader(env._runtime,refs.names)}
        json.dumps(plain(row))  # Validate passive record before proceeding.
        trace.append(row)
    class Observed:
        metadata=env.metadata
        def reset(self,**kw):
            obs,info=env.reset(**kw);capture(obs,info,'reset');return obs,info
        def step(self,action):
            result=env.step(action);capture(result[0],result[4],solution.stage,action);return result
    try:
        result=rollout_solution(Observed(),solution,horizon=600,seed=19)
        metrics=result['task_metrics'];report={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'backend':args.backend,'seed':19,'success':result['success'],'transitions':result['transitions'],'stage_counts':dict(Counter(result['stages'])),'task_metrics':metrics,'failure_reason':result['failure_reason'],'runtime_config':asdict(env.config.runtime),'gripper_config':asdict(env.config.robot.gripper),'action_config':asdict(env.config.action),'controller_config':asdict(env.config.robot.controller),'official_loop':'rollout_solution + _build_plan; passive wrapper only','source_solution_sha256':hashlib.sha256(Path('task_env/tasks/nut_assembly/solution.py').read_bytes()).hexdigest()}
        report['expected_success_match']=report['success'] and report['transitions']==354 and all(metrics[n] for n in ['inserted_on_peg','released_nut','task_success'])
        (folder/'reproduction.json').write_text(json.dumps(plain(report),indent=2)+'\n');print(json.dumps(plain(report),indent=2))
    finally:
        env.close();(folder/'stage_trace.json').write_text(json.dumps(plain(trace),indent=2)+'\n')

if __name__=='__main__':main()
