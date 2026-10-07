"""Locked unchanged NutAssembly expert plus symmetric frozen D0/D1/D2."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
from .common import context, label, observation, verify, write, NativeAudit, METADATA, empty_events, events_update
from .native import legacy_metrics, contact_readback
from ..multi_backend_replay.golden import boundary
from ..p1_2_runtime import execution
from ....tasks.nut_assembly.canonical_reset import sample_reset
from ....tasks.nut_assembly.solution import NutAssemblySolution
from ....controllers.canonical import ProductionCanonicalPandaController, RequestedAction
from ....controllers.canonical.kinematics import ARM
from ....controllers.canonical.contracts import digest
from ....runtime.sessions.control import materialize_control, ControlBinding
from ....runtime.sessions.provenance import provider_build_identity
from ....trajectory.canonical import EpisodeMetadata, CanonicalRecorder, TransitionRecord, save, load


def initialize(root, profile, provider):
    spec = verify(root); artifact, source, cfg = context(profile)
    profile_spec = spec['profiles'][profile]
    controller = ProductionCanonicalPandaController.from_source(artifact, source)
    if artifact.identity_hash != profile_spec['artifact_hash'] or controller.identity != profile_spec['controller_identity']:
        raise ValueError('Artifact/controller identity changed')
    if hashlib.sha256(source.scene_source.xml.encode()).hexdigest() != spec['source_xml_sha256']:
        raise ValueError('source XML changed')
    session = materialize_control(artifact, execution(provider), source=source,
                                  binding=ControlBinding('panda-v1/gripper', .08))
    audit = NativeAudit(session, provider, artifact.timebase)
    sample = sample_reset(artifact); realized = session.reset(sample); state = session.snapshot()
    if audit.count or state.control_step or state.simulation_time:
        raise ValueError('hidden reset steps or reset clock mismatch')
    max_joint = max(abs(state.joint_position[n] - v) for n,v in sample.joint_position.items())
    requested = sample.poses_world['square-nut-v1']; measured = state.pose_world['square-nut-v1']
    position_error = max(abs(x-y) for x,y in zip(requested.position, measured.position))
    quaternion_error = max(abs(x-y) for x,y in zip(requested.quaternion_wxyz, measured.quaternion_wxyz))
    velocity_error = max(abs(v) for v in state.joint_velocity.values())
    bound = spec['reset_representation_bound']
    if max(max_joint, position_error, quaternion_error, velocity_error) > bound:
        raise ValueError('reset realization outside locked representation bound')
    repeat = session.reset(sample).measured_state
    if repeat.to_mapping() != state.to_mapping():
        raise ValueError('repeat reset changed measured canonical state')
    feedback = session.control_feedback(state); controller.reset(state, feedback)
    return spec, artifact, source, cfg, controller, session, audit, sample, realized, state, feedback, {
        'joint_max_abs': max_joint, 'position_max_abs': position_error,
        'quaternion_max_abs': quaternion_error, 'velocity_max_abs': velocity_error,
        'repeat_exact': True, 'hidden_settle_steps': audit.count}


def expert(root, profile, provider):
    root = Path(root); folder = root/'expert'/label(profile)/provider
    if (folder/'report.json').exists():
        raise FileExistsError('expert Evidence collision')
    report = {'profile':profile, 'provider':provider, 'success':False, 'failure_boundary':None}
    session = audit = recorder = None; trace = []; contacts = []; events = empty_events(); stage = 'materialization'
    try:
        spec,a,source,cfg,c,session,audit,sample,realized,state,feedback,reset = initialize(root, profile, provider)
        original_sample = sample.to_mapping(); obs,info,e = observation(state,a)
        metadata = EpisodeMetadata('canonical-trajectory-metadata-v0',a.identity_hash,sample,realized,execution(provider),
            {k:json.dumps(v,sort_keys=True) for k,v in provider_build_identity(provider).items()},
            {'source_xml_sha256':spec['source_xml_sha256'],'bindings_json':json.dumps(spec['semantic_bindings'],sort_keys=True),'profile':profile},
            a.timebase,c.identity,spec['expert_identity'],spec['readiness_identity'],spec['expert_config_hash'],19,'evaluation')
        recorder = CanonicalRecorder(metadata,boundary(c,state,feedback,info))
        solution = NutAssemblySolution(config=cfg); solution.reset(obs,info,METADATA)
        initial_legacy = legacy_metrics(session, provider)
        stage = 'closed_loop_expert'
        while not solution.done and not solution.failed:
            public = solution.act(); request = RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
            canonical,target = c.compute(state,feedback,request); target_hash = target.identity_hash
            applied = session.apply_control(target); state = audit.step(target); feedback = session.control_feedback(state)
            obs,info,e = observation(state,a); after = boundary(c,state,feedback,info)
            solution.observe(obs,e.reward,False,False,info)
            recorder.append(TransitionRecord(request,canonical,target,applied,float(e.reward),False,False,
                public.stage,{k:json.dumps(v,sort_keys=True) for k,v in public.diagnostics.items()},True,False),after)
            if target.identity_hash != target_hash or applied.target_hash != target_hash:
                raise ValueError('target mutation/linkage mismatch')
            events_update(events,state,info['task_metrics'])
            # The emitted pose is the per-tick public request, not an assumed final stage goal.
            ee = state.pose_world['panda-v1/ee']
            residual = float(np.linalg.norm(np.array(ee.position)-public.action[:3]))
            trace.append({'stage':public.stage,'control_step':state.control_step,'simulation_time_s':state.simulation_time,
                'planned_transition':True,'EE_request_position_error_m':residual,'state':state.to_mapping(),
                'metrics':info['task_metrics'],'expert_diagnostics':dict(public.diagnostics)})
            contacts.append({'stage':public.stage,'control_step':state.control_step,'simulation_time_s':state.simulation_time,
                             'native':contact_readback(session,provider)})
        stage = 'trajectory_roundtrip'
        success = bool(solution.done and not solution.failed and e.success)
        trajectory = recorder.freeze('expert_success' if success else solution.failure_reason or 'no_canonical_success')
        path = root/'golden'/label(profile)/provider/'trajectory.h5' if success else folder/'unsuccessful_trajectory.h5'
        path.parent.mkdir(parents=True,exist_ok=True); save(path,trajectory); loaded = load(path)
        if loaded.to_mapping() != trajectory.to_mapping():
            raise ValueError('strict trajectory logical roundtrip mismatch')
        final_legacy = legacy_metrics(session,provider)
        comparisons = {k:{'legacy':final_legacy[k],'canonical':info['task_metrics'][k]} for k in info['task_metrics'] if k in final_legacy}
        report.update(success=success,expert_done=solution.done,expert_failed=solution.failed,
            expert_failure=solution.failure_reason,failure_stage=trace[-1]['stage'] if not success and trace else None,
            failure_boundary=None if success else 'closed_loop_expert',T=len(trajectory.transitions),holds=trajectory.hold_count,
            duration_s=len(trajectory.transitions)*a.timebase.control_dt,events=events,final_metrics=info['task_metrics'],
            reset_checks=reset,reset_sample_hash=sample.identity_hash,sample_unchanged=sample.to_mapping()==original_sample,
            native_substep_count_valid=audit.count==len(trajectory.transitions)*a.timebase.control_substeps,
            path=str(path.resolve()),logical_hash=loaded.identity_hash,h5_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            roundtrip_exact=True,controller_identity=c.identity,expert_identity=spec['expert_identity'],
            semantic_identity=spec['semantic_identity'],legacy_initial_metrics=initial_legacy,
            legacy_endpoint_metrics=final_legacy,legacy_canonical_endpoint_comparison=comparisons)
        if final_legacy['task_success'] and not e.success and final_legacy['gripper_ctrl']>=200 and info['task_metrics']['gripper_opening']<.065:
            report['failure_boundary']='nutassembly_canonical_semantics_migration'
        if success:
            write(path.parent/'reference.json',report)
    except Exception as error:
        report.update(failure_boundary=stage,error=str(error),traceback=traceback.format_exc())
    finally:
        if audit:
            write(folder/'native_audit.json',audit.boundaries); audit.close()
        if session:
            session.close()
        write(folder/'stage_trace.json',trace); write(folder/'report.json',report)
        write(root/'contact_diagnostics'/provider/label(profile)/'expert.json',contacts)
        verify(root)
    return report


def golden(root,profile,source_provider):
    folder=Path(root)/'golden'/label(profile)/source_provider
    ref=json.loads((folder/'reference.json').read_text()); tr=load(ref['path'])
    if not ref['success'] or tr.identity_hash!=ref['logical_hash'] or hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['h5_sha256']:
        raise ValueError('golden identity mismatch')
    return ref,tr


def d0(root,profile,source_provider):
    root=Path(root);verify(root);ref,tr=golden(root,profile,source_provider);a,source,_=context(profile)
    c=ProductionCanonicalPandaController.from_source(a,source);c.reset(tr.boundaries[0].state,tr.boundaries[0].feedback)
    actions=[];mismatches=[]
    for i,t in enumerate(tr.transitions):
        target=t.controller_target
        request=RequestedAction('absolute_joint',None,'none',tuple([target.arm_position[n] for n in ARM]+[2*target.gripper.opening_m/.08-1]))
        _,new=c.compute(tr.boundaries[i].state,tr.boundaries[i].feedback,request)
        if new.to_mapping()!=target.to_mapping() or new.identity_hash!=target.identity_hash:
            mismatches.append(i)
        actions.append(request.to_mapping())
    folder=root/'d0'/label(profile)/source_provider
    if (folder/'report.json').exists():raise FileExistsError('D0 collision')
    result={'profile':profile,'source_provider':source_provider,'pass':not mismatches,'exact_matches':len(actions)-len(mismatches),
        'T':len(actions),'mismatches':mismatches,'action_sequence_identity':digest(actions),'golden_logical_hash':tr.identity_hash}
    write(folder/'actions.json',actions);write(folder/'report.json',result);return result


def replay(root,profile,source_provider,provider,route):
    root=Path(root);verify(root);ref,tr=golden(root,profile,source_provider)
    folder=root/route.lower()/label(profile)/source_provider/provider
    if (folder/'report.json').exists():raise FileExistsError('replay collision')
    d0folder=root/'d0'/label(profile)/source_provider;actions=json.loads((d0folder/'actions.json').read_text());d0ref=json.loads((d0folder/'report.json').read_text())
    if not d0ref['pass'] or digest(actions)!=d0ref['action_sequence_identity']:raise ValueError('D0 sequence mismatch')
    report={'profile':profile,'source_provider':source_provider,'provider':provider,'route':route,'execution_valid':False,'task_valid':False}
    session=audit=None;trace=[];contacts=[];events=empty_events();stage='materialization'
    try:
        spec,a,source,cfg,c,session,audit,sample,realized,state,feedback,reset=initialize(root,profile,provider)
        if sample.to_mapping()!=tr.metadata.reset_sample.to_mapping():raise ValueError('replay reset mismatch')
        original_sample=sample.to_mapping();stage='replay'
        for i,t in enumerate(tr.transitions):
            stored=t.controller_target
            if route=='D1':target=stored;request=canonical=None
            elif route=='D2':
                request=RequestedAction.from_mapping(actions[i]);canonical,target=c.compute(state,feedback,request)
            else:raise ValueError('unsupported replay route')
            hash_before=target.identity_hash;applied=session.apply_control(target);before=state;state=audit.step(target);feedback=session.control_feedback(state)
            if hash_before!=target.identity_hash or applied.target_hash!=hash_before:raise ValueError('target mutation/linkage')
            if set(state.joint_position)!=set(before.joint_position) or set(state.pose_world)!=set(before.pose_world):raise ValueError('semantic field change')
            _,info,e=observation(state,a);events_update(events,state,info['task_metrics']);reference=tr.boundaries[i+1].state
            divergence={'arm_joint_max_abs':max(abs(state.joint_position[n]-reference.joint_position[n]) for n in ARM),
                'EE_position_norm_m':float(np.linalg.norm(np.array(state.pose_world['panda-v1/ee'].position)-reference.pose_world['panda-v1/ee'].position)),
                'nut_position_norm_m':float(np.linalg.norm(np.array(state.pose_world['square-nut-v1'].position)-reference.pose_world['square-nut-v1'].position)),
                'nut_quaternion_max_abs':max(abs(x-y) for x,y in zip(state.pose_world['square-nut-v1'].quaternion_wxyz,reference.pose_world['square-nut-v1'].quaternion_wxyz)),
                'arm_desired_max_abs':max(abs(target.arm_position[n]-stored.arm_position[n]) for n in ARM),
                'arm_servo_max_abs':max(abs(target.arm_servo_position[n]-stored.arm_servo_position[n]) for n in ARM),
                'gripper_desired_delta_m':abs(target.gripper.opening_m-stored.gripper.opening_m),
                'gripper_servo_delta_m':abs(target.gripper.servo_opening_m-stored.gripper.servo_opening_m)}
            trace.append({'state':state.to_mapping(),'metrics':info['task_metrics'],'controller_target':target.to_mapping(),
                'applied_control':applied.to_mapping(),'requested_action':request.to_mapping() if request else None,
                'canonical_action':canonical.to_mapping() if canonical else None,'divergence':divergence})
            contacts.append({'source_expert_stage':t.expert_stage,'control_step':state.control_step,'simulation_time_s':state.simulation_time,
                             'native':contact_readback(session,provider)})
        report.update(execution_valid=sample.to_mapping()==original_sample,task_valid=bool(e.success and events['success']),
            failure_boundary=None if e.success else ('nutassembly_cross_provider_target_replay' if route=='D1' else 'nutassembly_feedback_controller_interaction'),
            T=len(tr.transitions),duration_s=len(tr.transitions)*a.timebase.control_dt,events=events,final_metrics=info['task_metrics'],
            minimum_peg_xy_error=min(x['metrics']['peg_xy_error'] for x in trace),minimum_yaw_error=min(x['metrics']['yaw_error'] for x in trace),
            reset_checks=reset,sample_unchanged=sample.to_mapping()==original_sample,native_substep_count_valid=audit.count==len(tr.transitions)*a.timebase.control_substeps,
            golden_logical_hash=ref['logical_hash'],action_sequence_identity=d0ref['action_sequence_identity'],controller_identity=c.identity,
            final_divergence=trace[-1]['divergence'],maximum_divergence={k:max(x['divergence'][k] for x in trace) for k in trace[-1]['divergence']})
    except Exception as error:
        report.update(failure_boundary=stage,error=str(error),traceback=traceback.format_exc())
    finally:
        if audit:write(folder/'native_audit.json',audit.boundaries);audit.close()
        if session:session.close()
        write(folder/'trace.json',trace);write(folder/'report.json',report)
        write(root/'contact_diagnostics'/provider/label(profile)/(route.lower()+'_'+source_provider+'.json'),contacts)
        verify(root)
    return report
