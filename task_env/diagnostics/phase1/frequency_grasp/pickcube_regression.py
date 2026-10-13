"""Fresh frozen R1/PickCube regression; not historical qualification replay."""
import argparse,hashlib,json,time,subprocess,traceback
from pathlib import Path
import numpy as np
from ..control.spec import context
from ..control.worker import observation
from ..p1_2_runtime import execution
from ..p1_5_readiness import execution_info
from ....tasks.pick_cube.reset import sample_reset
from ....tasks.pick_cube.readiness_solution import PickCubeReadinessConfig,PickCubeReadinessSolution
from ....controllers.canonical import ProductionCanonicalPandaController,RequestedAction
from ....runtime.sessions.control import materialize_control,ControlBinding

def run(provider,seed,output):
    output.mkdir(parents=True,exist_ok=False)
    artifact,source,_,_=context();sample=sample_reset(artifact,seed)
    controller=ProductionCanonicalPandaController.from_source(artifact,source)
    cfg=PickCubeReadinessConfig.from_source(artifact,source)
    launch={'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'provider':provider,'seed':seed,'qualification':False,'purpose':'unchanged frozen R1/PickCube diagnostic regression','artifact':artifact.to_mapping(),'reset_sample':sample.to_mapping(),'controller_identity':controller.identity,'expert_config_identity':cfg.identity,'source_xml_sha256':hashlib.sha256(source.scene_source.xml.encode()).hexdigest()}
    (output/'launch.json').write_text(json.dumps(launch,indent=2)+'\n')
    session=None;trace=[];result={'pass':False,'qualification':False};start=time.monotonic()
    try:
        session=materialize_control(artifact,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',source.config.action.gripper_opening_range_m))
        session.reset(sample);state=session.snapshot();feedback=session.control_feedback(state);controller.reset(state,feedback)
        expert=PickCubeReadinessSolution(config=cfg);obs,info,_=observation(state,artifact)
        expert.reset(obs,info,{'action_schema':{'controller_kind':'absolute_pose','reference':'world','rotation_representation':'quaternion_wxyz','dimension':8}},execution_info=execution_info(controller,state,feedback))
        while not expert.done and not expert.failed:
            public=expert.act();request=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
            canonical,target=controller.compute(state,feedback,request);applied=session.apply_control(target);before=state;state=session.step()
            if state.simulation_time<=before.simulation_time:raise ValueError('nonmonotonic native time')
            if provider=='mujoco' and (any(session._data.warning.number) or not np.isfinite(session._data.qpos).all()):raise ValueError('native instability')
            feedback=session.control_feedback(state);obs,info,_=observation(state,artifact)
            expert.observe(obs,0.,False,False,info,execution_info=execution_info(controller,state,feedback))
            trace.append({'state':state.to_mapping(),'target':target.to_mapping(),'applied':applied.to_mapping(),'stage':public.stage,'task_info':info})
        ready={e['stage'] for e in expert.completion_events}
        result.update(pass_=expert.done and bool(info['is_success']) and {'move_above_cube','descend_vertical','close_gripper'}<=ready,endpoint=expert.done,task_success=bool(info['is_success']),completion_events=expert.completion_events,failure_reason=expert.failure_reason)
        result['pass']=result.pop('pass_')
    except Exception as exc:result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:
        if session is not None:session.close()
    result.update(wall_time_s=time.monotonic()-start,boundaries=len(trace),provider=provider,seed=seed)
    (output/'trace.json').write_text(json.dumps(trace)+'\n');(output/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    return result['pass']
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--provider',choices=['mujoco','geophys'],required=True);p.add_argument('--seed',type=int,choices=[31,73],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raise SystemExit(0 if run(a.provider,a.seed,a.output) else 1)
