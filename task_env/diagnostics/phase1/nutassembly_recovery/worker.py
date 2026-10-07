"""Additive recovery driver. Frozen controller/provider/task; solution selectable."""
from dataclasses import replace,asdict
import argparse,json,hashlib,traceback
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from ....artifacts import Timebase
from ....artifacts.execution import ResetSample
from ....assembly.source import TaskSceneSource
from ....tasks.nut_assembly.canonical_artifact import build_candidate
from ....tasks.nut_assembly.canonical_source import build_runtime_source
from ....tasks.nut_assembly.canonical_reset import sample_reset
from ....tasks.nut_assembly.solution import NutAssemblySolution,NutAssemblySolutionConfig
from ....controllers.canonical import ProductionCanonicalPandaController,RequestedAction
from ....controllers.canonical.contracts import digest
from ....runtime.sessions.control import materialize_control,ControlBinding
from ....runtime.sessions.provenance import provider_build_identity
from ....trajectory.canonical import EpisodeMetadata,CanonicalRecorder,TransitionRecord,save,load
from ..nutassembly.common import observation,METADATA,empty_events,events_update,NativeAudit,write
from ..nutassembly.native import contact_readback
from ..multi_backend_replay.golden import boundary
from ..p1_2_runtime import execution


def context(root,profile):
    a=build_candidate('NA-TB100' if profile=='NA-TB30-REF' else profile);source=build_runtime_source(a)
    xml=(Path(root)/'shared_source.xml').read_text()
    if profile=='NA-TB30-REF':
        a=replace(a,artifact_version='ver_p1_8_er2_tb30_diagnostic',timebase=Timebase(1./600.,20,1./30.))
        tree=ET.fromstring(xml);tree.find('option').set('timestep',repr(1./600.));xml=ET.tostring(tree,encoding='unicode')
        source=replace(source,task_artifact_hash=a.identity_hash,config=replace(source.config,runtime=replace(source.config.runtime,physics_dt=1./600.,control_substeps=20)))
        base=sample_reset(build_candidate('NA-TB100')).to_mapping();base.pop('sample_id');base['task_artifact_hash']=a.identity_hash;sample=ResetSample.create(**base)
    else:sample=sample_reset(a)
    source=replace(source,scene_source=TaskSceneSource(xml,source.scene_source.base_dir,source.scene_source.source_id))
    return a,source,sample


def run(root,folder,profile,provider,solution_kind,config_path=None,scope="full"):
    root=Path(root);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    if (folder/'report.json').exists():raise FileExistsError('recovery Evidence collision')
    report={'profile':profile,'provider':provider,'success':False,'solution_kind':solution_kind,'scope':scope};session=audit=None;trace=[];contacts=[];events=empty_events();phase='materialization'
    try:
        a,source,sample=context(root,profile);c=ProductionCanonicalPandaController.from_source(a,source)
        if solution_kind=='legacy':
            solution=NutAssemblySolution();sid=digest({'legacy_source_sha256':hashlib.sha256(Path('task_env/tasks/nut_assembly/solution.py').read_bytes()).hexdigest(),'config':asdict(solution.config)})
        else:
            from ....tasks.nut_assembly.canonical_solution import NutAssemblyCanonicalSolutionV1,CanonicalNutAssemblyConfig
            cfg=CanonicalNutAssemblyConfig(**json.loads(Path(config_path).read_text())) if config_path else CanonicalNutAssemblyConfig()
            solution=NutAssemblyCanonicalSolutionV1(config=cfg,control_dt=a.timebase.control_dt);sid=solution.identity
        session=materialize_control(a,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08));audit=NativeAudit(session,provider,a.timebase)
        realized=session.reset(sample);state=session.snapshot();feedback=session.control_feedback(state);c.reset(state,feedback)
        obs,info,e=observation(state,a);solution.reset(obs,info,METADATA)
        metadata=EpisodeMetadata('canonical-trajectory-metadata-v0',a.identity_hash,sample,realized,execution(provider),
            {k:json.dumps(v,sort_keys=True) for k,v in provider_build_identity(provider).items()},
            {'source_xml_sha256':hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),'profile':profile},a.timebase,c.identity,sid,digest({'readiness':'canonical-control-readiness-v1'}),digest({'expert':sid}),19,'evaluation')
        rec=CanonicalRecorder(metadata,boundary(c,state,feedback,info));initial=np.array(state.pose_world['square-nut-v1'].position);phase='expert'
        while not solution.done and not solution.failed:
            public=solution.act();req=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
            canonical,target=c.compute(state,feedback,req);applied=session.apply_control(target);state=audit.step(target);feedback=session.control_feedback(state);obs,info,e=observation(state,a)
            if solution_kind=='legacy':solution.observe(obs,e.reward,False,False,info)
            else:solution.observe(obs,e.reward,False,False,info,readiness=c.readiness(state,feedback))
            after=boundary(c,state,feedback,info);planned=not bool(public.diagnostics.get('readiness_hold',False))
            rec.append(TransitionRecord(req,canonical,target,applied,float(e.reward),False,False,public.stage,{k:json.dumps(v,sort_keys=True) for k,v in public.diagnostics.items()},planned,not planned),after)
            events_update(events,state,info['task_metrics']);trace.append({'stage':public.stage,'state':state.to_mapping(),'feedback':feedback.to_mapping(),'controller_target':target.to_mapping(),'applied_control':applied.to_mapping(),'controller_memory':c.memory().to_mapping(),'metrics':dict(info['task_metrics']),'requested_action':req.to_mapping(),'expert_diagnostics':dict(public.diagnostics),'readiness':c.readiness(state,feedback).to_mapping()})
            contacts.append({'stage':public.stage,'control_step':state.control_step,'simulation_time_s':state.simulation_time,'native':contact_readback(session,provider)})
            if scope=='grasp_lift' and public.stage=='verify_lift' and solution.stage=='raise_for_transport':
                report['grasp_lift_gate_passed']=True;break
        phase='trajectory_roundtrip';trajectory=rec.freeze('bounded_grasp_lift_complete' if report.get('grasp_lift_gate_passed') else 'success' if e.success and solution.done else solution.failure_reason or 'failed');path=folder/'trajectory.h5';save(path,trajectory);loaded=load(path);assert loaded.to_mapping()==trajectory.to_mapping()
        report.update(success=bool(e.success and solution.done and not solution.failed),T=len(trace),duration_s=state.simulation_time,events=events,final_metrics=dict(info['task_metrics']),failure_reason=solution.failure_reason,stage=solution.stage,holds=trajectory.hold_count,roundtrip_exact=True,artifact_hash=a.identity_hash,reset_sample_hash=sample.identity_hash,source_xml_sha256=hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),controller_identity=c.identity,expert_identity=sid,logical_hash=loaded.identity_hash,h5_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),path=str(path.resolve()),max_nut_lift_m=max((x['metrics']['nut_z']-initial[2] for x in trace),default=0.))
    except Exception as error:
        if 'rec' in locals() and trace:
            try:
                partial=rec.freeze('provider_exception');path=folder/'partial_trajectory.h5';save(path,partial);loaded=load(path);assert loaded.to_mapping()==partial.to_mapping()
                report.update(partial_roundtrip_exact=True,partial_T=len(trace),partial_logical_hash=loaded.identity_hash,partial_h5_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            except Exception as serialization_error:report['partial_serialization_error']=str(serialization_error)
        report.update(failure_boundary=phase,error=str(error),traceback=traceback.format_exc(),completed_transitions=len(trace),last_state=trace[-1]['state'] if trace else None)
        if session is not None and provider=='mujoco':
            report['native_failure_audit']={'native_time_s':float(session._data.time),'native_steps':session._native_steps,'control_step':session._control_step,'clock_audit':getattr(session,'_native_time_audit',None),'warning_counts':session._data.warning.number.tolist()}
    finally:
        if audit:write(folder/'native_audit.json',audit.boundaries);audit.close()
        if session:session.close()
        write(folder/'trace.json',trace);write(folder/'contacts.json',contacts);write(folder/'report.json',report)
    print(json.dumps(report,indent=2));return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--folder',required=True);p.add_argument('--profile',required=True);p.add_argument('--provider',choices=['geophys','mujoco'],required=True);p.add_argument('--solution',choices=['legacy','canonical'],default='canonical');p.add_argument('--config');p.add_argument('--scope',choices=['full','grasp_lift'],default='full');args=p.parse_args();run(args.root,args.folder,args.profile,args.provider,args.solution,args.config,args.scope)

if __name__=='__main__':main()
