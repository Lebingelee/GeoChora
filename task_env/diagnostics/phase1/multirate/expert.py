"""Gate E: unchanged expert/controller, explicit profile, physical-time records."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
import traceback
import numpy as np
from .common import context,identities,label,verify,write,NativeAudit
from ..multi_backend_replay.golden import boundary
from ..control.worker import observation
from ..p1_2_runtime import execution
from ....runtime.sessions.control import materialize_control,ControlBinding
from ....runtime.sessions.provenance import provider_build_identity
from ....tasks.pick_cube.reset import sample_reset
from ....tasks.pick_cube.readiness_solution import PickCubeReadinessSolution
from ....controllers.canonical import ProductionCanonicalPandaController,RequestedAction
from ....trajectory.canonical import EpisodeMetadata,CanonicalRecorder,TransitionRecord,save,load
from ....planners.completion import ExpertExecutionInfo
from ....utils.rotation import quat_wxyz_to_matrix,rotation_vector_error


def run(root,profile,seed):
    root=Path(root);verify(root);a,source,cfg=context(root,profile);ids=identities(root,profile)
    folder=root/'expert'/label(profile)/f'seed{seed}'
    if (folder/'report.json').exists():raise FileExistsError('expert Evidence collision')
    report={'profile':profile,'seed':seed,'provider':'geophys','success':False,'failure_boundary':None,'first_success_control_step':None,'first_success_simulation_time_s':None};session=None;audit=None;recorder=None;raw=[]
    try:
        sample=sample_reset(a,seed);session=materialize_control(a,execution('geophys'),source=source,binding=ControlBinding('panda-v1/gripper',.08))
        audit=NativeAudit(session,'geophys',a.timebase);realized=session.reset(sample)
        if audit.count:raise ValueError('hidden reset settle')
        state=session.snapshot();feedback=session.control_feedback(state)
        controller=ProductionCanonicalPandaController.from_source(a,source);controller.reset(state,feedback)
        obs,info,evaluation=observation(state,a)
        metadata=EpisodeMetadata('canonical-trajectory-metadata-v0',a.identity_hash,sample,realized,execution('geophys'),
            {k:json.dumps(v,sort_keys=True) for k,v in provider_build_identity('geophys').items()},
            {'source_sha256':hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),'recipe_json':json.dumps(asdict(source.config),sort_keys=True),'profile':profile},
            a.timebase,ids['controller'],ids['expert'],ids['readiness'],cfg.identity,seed,'evaluation')
        recorder=CanonicalRecorder(metadata,boundary(controller,state,feedback,info));expert=PickCubeReadinessSolution(config=cfg)
        expert.reset(obs,info,{'action_schema':{'controller_kind':'absolute_pose','reference':'world','rotation_representation':'quaternion_wxyz','dimension':8}},execution_info=ExpertExecutionInfo('expert-execution-info-v1',0,0.,controller.readiness(state,feedback)))
        while not expert.done and not expert.failed:
            public=expert.act();request=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
            canonical,target=controller.compute(state,feedback,request);applied=session.apply_control(target);state=audit.step(target);feedback=session.control_feedback(state)
            obs,info,evaluation=observation(state,a);after=boundary(controller,state,feedback,info)
            plan=expert._segments[expert._segment_index].plan
            ee=np.asarray((*state.pose_world['panda-v1/ee'].position,*state.pose_world['panda-v1/ee'].quaternion_wxyz));goal=np.asarray(plan.target_pose)
            residual={'position_m':float(np.linalg.norm(ee[:3]-goal[:3])),'rotation_rad':float(np.linalg.norm(rotation_vector_error(quat_wxyz_to_matrix(ee[3:]),quat_wxyz_to_matrix(goal[3:]))))}
            expert.observe(obs,evaluation.reward,False,False,info,execution_info=ExpertExecutionInfo('expert-execution-info-v1',state.control_step,state.simulation_time,after.readiness))
            hold=bool(public.diagnostics['readiness_hold']);recorder.append(TransitionRecord(request,canonical,target,applied,float(evaluation.reward),False,False,public.stage,{k:json.dumps(v,sort_keys=True) for k,v in public.diagnostics.items()},not hold,hold),after)
            raw.append({'stage':public.stage,'control_step':state.control_step,'simulation_time_s':state.simulation_time,'readiness_hold':hold,'pose_residual':residual,'readiness':after.readiness.to_mapping(),'cube_lift':after.task_metrics['cube_lift']})
            if after.is_success and report['first_success_control_step'] is None:report.update(first_success_control_step=state.control_step,first_success_simulation_time_s=state.simulation_time)
        trajectory=recorder.freeze('expert_endpoint' if expert.done else expert.failure_reason)
        success=bool(expert.done and trajectory.boundaries[-1].is_success and trajectory.boundaries[-1].task_metrics['cube_lift']>=cfg.policies[-1].collection_endpoint_m)
        path=(root/'golden'/label(profile)/f'seed{seed}'/'trajectory.h5') if success else folder/'unsuccessful_trajectory.h5'
        path.parent.mkdir(parents=True,exist_ok=True);save(path,trajectory);loaded=load(path)
        if loaded.to_mapping()!=trajectory.to_mapping():raise ValueError('strict H5 logical roundtrip mismatch')
        report.update(success=success,expert_failure=expert.failure_reason,T=len(trajectory.transitions),holds=trajectory.hold_count,planned=len(trajectory.transitions)-trajectory.hold_count,
            control_dt=a.timebase.control_dt,control_substeps=a.timebase.control_substeps,total_duration_s=len(trajectory.transitions)*a.timebase.control_dt,hold_duration_s=trajectory.hold_count*a.timebase.control_dt,
            planned_duration_s=(len(trajectory.transitions)-trajectory.hold_count)*a.timebase.control_dt,endpoint_control_step=state.control_step if success else None,endpoint_simulation_time_s=state.simulation_time if success else None,
            path=str(path.resolve()),logical_hash=loaded.identity_hash,h5_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),reset_sample_hash=sample.identity_hash,identities=ids,roundtrip_exact=True,
            global_safety_cap=cfg.global_safety_cap,completion_events=expert.completion_events)
        if not success:report['failure_boundary']='expert_'+str(expert.failure_reason)
        if success:write(path.parent/'reference.json',report)
    except Exception as e:report.update(failure_boundary=str(e),error=str(e),traceback=traceback.format_exc())
    finally:
        if audit:write(folder/'native_audit.json',audit.boundaries);audit.close()
        if session:session.close()
        write(folder/'stage_trace.json',raw);write(folder/'report.json',report);verify(root)
    return report
