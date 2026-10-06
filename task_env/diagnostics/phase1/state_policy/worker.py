"""Isolated canonical expert collection and learned public-action rollout."""
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
import json,traceback,hashlib
import numpy as np
from ....trajectory.canonical import EpisodeMetadata,BoundaryRecord,TransitionRecord,CanonicalRecorder,save,load
from ....controllers.canonical import ProductionCanonicalPandaController,RequestedAction
from ....tasks.pick_cube.readiness_solution import PickCubeReadinessSolution
from ....runtime.sessions.control import materialize_control,ControlBinding
from ....runtime.sessions.provenance import provider_build_identity
from ....artifacts.execution import ResetSample
from ....planners.completion import ExpertExecutionInfo
from ..control.worker import observation
from ..p1_2_runtime import execution,write_json
from .spec import verify,context


def boundary(controller,state,feedback,info):
    return BoundaryRecord(state.control_step,state.simulation_time,state,feedback,controller.readiness(state,feedback),
        {k:float(v) for k,v in info['task_metrics'].items()},bool(info['is_success']),bool(info['task_failure']))


def metadata(provider,role,sample,realized,spec,artifact,source,cfg):
    return EpisodeMetadata('canonical-trajectory-metadata-v0',artifact.identity_hash,sample,realized,execution(provider),
        {k:json.dumps(v,sort_keys=True) for k,v in provider_build_identity(provider).items()},
        {'source_xml_sha256':spec['source_xml_sha256'],'bindings_json':json.dumps(spec['source_bindings'],sort_keys=True),'execution_recipe_json':json.dumps(spec['source_config'],sort_keys=True)},
        artifact.timebase,spec['identities']['controller'],spec['identities']['expert'],spec['identities']['readiness'],cfg.identity,sample.task_seed,role)


def collect(provider,seed,role,oracle,output):
    spec,lock=verify(oracle);artifact,source,cfg=context();sample=ResetSample.from_mapping(spec['samples'][str(seed)]);before=sample.to_mapping()
    report={'provider':provider,'seed':seed,'role':role,'sample_hash':sample.identity_hash,'oracle_sha256':lock['sha256'],'started_at':datetime.now(timezone.utc).isoformat(),'pass':False,'first_boundary':None};session=None;recorder=None;stage='materialization'
    try:
        session=materialize_control(artifact,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08))
        realized=session.reset(sample);state=session.snapshot();feedback=session.control_feedback(state)
        controller=ProductionCanonicalPandaController.from_source(artifact,source);controller.reset(state,feedback)
        obs,info,e=observation(state,artifact);first=boundary(controller,state,feedback,info)
        recorder=CanonicalRecorder(metadata(provider,role,sample,realized,spec,artifact,source,cfg),first)
        expert=PickCubeReadinessSolution(config=cfg);action_metadata={'action_schema':{'controller_kind':'absolute_pose','reference':'world','rotation_representation':'quaternion_wxyz','dimension':8}}
        expert.reset(obs,info,action_metadata,execution_info=ExpertExecutionInfo('expert-execution-info-v1',0,0.,first.readiness))
        stage='expert_data_collection';max_lift=info['task_metrics']['cube_lift']
        while not expert.done and not expert.failed:
            public=expert.act();request=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
            canonical,target=controller.compute(state,feedback,request);applied=session.apply_control(target);state=session.step();feedback=session.control_feedback(state)
            obs,info,e=observation(state,artifact);after=boundary(controller,state,feedback,info)
            expert.observe(obs,e.reward,False,False,info,execution_info=ExpertExecutionInfo('expert-execution-info-v1',state.control_step,state.simulation_time,after.readiness))
            hold=bool(public.diagnostics['readiness_hold'])
            transition=TransitionRecord(request,canonical,target,applied,float(e.reward),False,False,public.stage,
                {k:json.dumps(v,sort_keys=True) for k,v in public.diagnostics.items()},not hold,hold)
            recorder.append(transition,after);max_lift=max(max_lift,info['task_metrics']['cube_lift'])
        stage='trajectory_schema';trajectory=recorder.freeze('expert_endpoint' if expert.done else expert.failure_reason or 'expert_failed')
        stage='serialization_roundtrip';file=output.parent/'trajectory.h5';save(file,trajectory);loaded=load(file)
        exact=loaded.to_mapping()==trajectory.to_mapping();report.update(file=str(file),file_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),logical_hash=loaded.identity_hash,
            T=len(loaded.transitions),boundary_count=len(loaded.boundaries),holds=loaded.hold_count,planned=expert.planned_actions_emitted,
            roundtrip=exact,expert_stage_sequence=[t.expert_stage for t in loaded.transitions],success=bool(info['is_success']),endpoint=expert.done,max_cube_lift=float(max_lift),
            failure_reason=expert.failure_reason,completion_events=expert.completion_events,sample_unchanged=sample.to_mapping()==before)
        if not expert.done:report['first_boundary']='expert_data_collection'
        elif not exact:report['first_boundary']='serialization_roundtrip'
        report['pass']=bool(expert.done and info['is_success'] and exact and sample.to_mapping()==before and loaded.boundaries[-1].task_metrics['cube_lift']>=.105)
    except Exception as error:
        report.update(first_boundary=stage,error=str(error),traceback=traceback.format_exc())
        if recorder is not None:
            # Preserve all observations/transitions even when validation itself failed.
            write_json(output.parent/'partial_records.json',{'boundaries':[b.to_mapping() for b in recorder.boundaries],'transitions':[t.to_mapping() for t in recorder.transitions]})
    finally:
        if session is not None:session.close()
    write_json(output,report);return report


def replay(provider,oracle,trajectory_path,output):
    spec,lock=verify(oracle);artifact,source,cfg=context();trajectory=load(trajectory_path);slice_spec=spec['replay_slice'];targets=trajectory.transitions[slice_spec['start']:slice_spec['stop_exclusive']]
    if len(targets)!=20 or any(t.expert_stage!=slice_spec['require_stage'] for t in targets):raise ValueError('replay_contract: frozen pre-contact slice not available')
    session=None;report={'pass':False,'provider':provider,'oracle_sha256':lock['sha256'],'slice':slice_spec};rows=[]
    try:
        session=materialize_control(artifact,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08));session.reset(trajectory.metadata.reset_sample);last=session.snapshot().simulation_time
        for transition in targets:
            target=transition.controller_target;before=target.identity_hash;applied=session.apply_control(target);state=session.step()
            if applied.target_hash!=before or target.identity_hash!=before or state.simulation_time<=last:raise ValueError('replay linkage/time mismatch')
            last=state.simulation_time;rows.append({'state':state.to_mapping(),'target_hash':before,'applied':applied.to_mapping()})
        report.update(pass_result=True,target_hashes=[r['target_hash'] for r in rows],states=rows,final_state=state.to_mapping(),sample_hash=trajectory.metadata.reset_sample.identity_hash);report['pass']=True
    except Exception as error:report.update(error=str(error),traceback=traceback.format_exc())
    finally:
        if session is not None:session.close()
    write_json(output,report);return report


def evaluate_policy(provider,seed,oracle,checkpoint,output):
    from ....alg.state_bc.learner import load_checkpoint
    from ....alg.state_bc.features import features,requested_action
    import torch
    torch.set_num_threads(1)
    spec,lock=verify(oracle);artifact,source,cfg=context();sample=ResetSample.from_mapping(spec['samples'][str(seed)]);original=sample.to_mapping()
    checkpoint_hash=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest();policy=load_checkpoint(checkpoint)
    report={'provider':provider,'seed':seed,'checkpoint_sha256':checkpoint_hash,'sample_hash':sample.identity_hash,'oracle_sha256':lock['sha256'],
        'started_at':datetime.now(timezone.utc).isoformat(),'success':False,'steps_to_success':None,'terminated':False,'truncated':False,'clipping_count':0,'actions_issued':0,'pass':False};session=None;trace=[];max_lift=None
    try:
        session=materialize_control(artifact,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08));session.reset(sample)
        state=session.snapshot();feedback=session.control_feedback(state);controller=ProductionCanonicalPandaController.from_source(artifact,source);controller.reset(state,feedback)
        _,info,e=observation(state,artifact);max_lift=float(info['task_metrics']['cube_lift'])
        for _ in range(spec['policy_eval_horizon']):
            # Only current public state/feedback enter inference; no expert is constructed.
            values=policy(features(state,feedback));request=requested_action(values);canonical,target=controller.compute(state,feedback,request)
            report['clipping_count']+=int(canonical.clipped);report['actions_issued']+=1
            applied=session.apply_control(target);before=state;state=session.step()
            if state.control_step!=before.control_step+1 or state.simulation_time<=before.simulation_time:
                report['invalid_timebase']={'before_step':before.control_step,'after_step':state.control_step,'time_before':before.simulation_time,'time_after':state.simulation_time}
                raise ValueError('canonical_timebase_regression: native reset/rollback during learned rollout')
            feedback=session.control_feedback(state);_,info,e=observation(state,artifact)
            max_lift=max(max_lift,float(info['task_metrics']['cube_lift']))
            trace.append({'state':state.to_mapping(),'feedback':feedback.to_mapping(),'requested':request.to_mapping(),'canonical':canonical.to_mapping(),'target':target.to_mapping(),'applied':applied.to_mapping(),'task_metrics':info['task_metrics'],'is_success':info['is_success']})
            if info['is_success']:report.update(success=True,steps_to_success=state.control_step);break
        report.update(steps=len(trace),max_cube_lift=max_lift,clip_rate=report['clipping_count']/max(1,len(trace)),horizon_reached=len(trace)==spec['policy_eval_horizon'],sample_unchanged=sample.to_mapping()==original,
            checkpoint_unchanged=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest()==checkpoint_hash)
        report['pass']=report['success'] and report['sample_unchanged'] and report['checkpoint_unchanged']
        report['first_boundary']=None if report['pass'] else 'cross_provider_policy_behavior'
    except Exception as error:report.update(first_boundary='runner_action_boundary',error=str(error),traceback=traceback.format_exc(),steps=len(trace),attempted_steps=report['actions_issued'],max_cube_lift=max_lift,clip_rate=report['clipping_count']/max(1,report['actions_issued']),checkpoint_unchanged=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest()==checkpoint_hash,sample_unchanged=sample.to_mapping()==original)
    finally:
        if session is not None:session.close()
    write_json(output.parent/'trace.json',trace);write_json(output,report);return report
