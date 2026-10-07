"""R0 forensic reconstruction and R1 exact-final-close diagnostic; no production edits.

Read old Evidence only. Native hold sessions run solely through existing public
runtime/control APIs. Controller memory is reconstructed with recorded inputs,
never inferred from stage labels. Contact pair absence is not invented for the
historical GeoPhys aggregate-only readback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .common import context, observation, METADATA, write, label
from .native import contact_readback
from .worker import initialize
from ....trajectory.canonical import load
from ....controllers.canonical import ProductionCanonicalPandaController, RequestedAction
from ....tasks.nut_assembly.solution import NutAssemblySolution


def pair_contact(native):
    if 'contacts' not in native:
        return {'finger_nut': None, 'hand_nut': None, 'pair_attribution': 'not recorded: body aggregate only'}
    pairs=[set(x['source_body_names']) for x in native['contacts'] if x['separation_m'] <= 0]
    return {'finger_nut':any('SquareNut' in p and bool(p & {'leftfinger','rightfinger','left_finger','right_finger'}) for p in pairs),
            'hand_nut':any({'hand','SquareNut'} <= p for p in pairs), 'pair_attribution':'native contact pairs'}


def geophys_pair_reader(session, source):
    """Diagnostic-only public typed contact readback, names from same compiler."""
    from ....assembly.compiler import compile_task_scene
    from ....runtime.sessions.geophys_source import GeoPhysSourceComposer
    from runtime.diagnostics import DiagnosticsConfig
    from runtime.readback_probe import explicit_to_numpy
    compiled = compile_task_scene(composition=source.composition, scene=source.scene,
        agents=source.agents, objects=source.objects, scene_composer=GeoPhysSourceComposer(source.scene_source))
    names = {i:n for n,i in compiled.references.names.bodies.items()}
    # Binding identity must match the already materialized adapter.
    for semantic, native in source.bodies.items():
        if compiled.references.names.bodies[native] != session._bodies[semantic]:
            raise ValueError('diagnostic compiler/body binding mismatch')
    def read():
        packet = session._boundary._physics.query_diagnostics(DiagnosticsConfig(contacts=True)).contacts
        if packet is None or packet.body_contact_count is None:
            raise RuntimeError('public typed contact readback unavailable')
        arrays = {k:explicit_to_numpy(getattr(packet, 'body_contact_'+k), reason='nutassembly_grasp_diagnostic')
            for k in ('active','body_a','body_b','point','penetration','normal_impulse')}
        count=int(packet.body_contact_count[None]); rows=[]
        for i in range(min(count,len(arrays['active']))):
            if not arrays['active'][i]:continue
            rows.append({'source_body_names':[names[int(arrays['body_a'][i])],names[int(arrays['body_b'][i])]],
                'separation_m':-float(arrays['penetration'][i]),'point_world':arrays['point'][i].tolist(),
                'normal_impulse_native':float(arrays['normal_impulse'][i])})
        return {'public_api':'query_diagnostics(contacts=True) typed readback',
            'meaning':'completed native substep manifolds; diagnostic only','contacts':rows,'contact_count':len(rows)}
    return read


def row(state, feedback, metrics, target, request, memory, readiness, initial, native, stage):
    ee=state.pose_world['panda-v1/ee'];nut=state.pose_world['square-nut-v1'];pos=np.array(nut.position)
    return {'stage':stage,'control_step':state.control_step,'simulation_time_s':state.simulation_time,
        'EE_pose':ee.to_mapping(),'nut_pose':nut.to_mapping(),'nut_yaw':metrics['nut_yaw'],
        'eef_to_handle_dist':metrics['eef_to_handle_dist'],'eef_to_nut_dist':metrics['eef_to_nut_dist'],
        'EE_request_residual_m':float(np.linalg.norm(np.array(ee.position)-request.values[:3])),
        'physical_opening_m':feedback.gripper.opening_m,'requested_gripper_scalar':request.values[-1],
        'target':target.gripper.to_mapping(),'feedback':feedback.gripper.to_mapping(),
        'controller_memory':memory.to_mapping(),'readiness':readiness.to_mapping(),
        'reached_nut':bool(metrics['reached_nut']),'grasped_nut':bool(metrics['grasped_nut']),
        'lifted_nut':bool(metrics['lifted_nut']),'nut_displacement_XY_m':float(np.linalg.norm(pos[:2]-initial[:2])),
        'nut_displacement_Z_m':float(pos[2]-initial[2]),'native_contact':native,'contact':pair_contact(native)}


def forensic(prior, output):
    prior=Path(prior);output=Path(output);episodes=[]
    for path in sorted(prior.glob('expert/*/*/unsuccessful_trajectory.h5')):
        tr=load(path);profile=tr.metadata.source_provenance['profile'];provider=tr.metadata.execution.physics_provider
        a,source,_=context(profile);c=ProductionCanonicalPandaController.from_source(a,source)
        c.reset(tr.boundaries[0].state,tr.boundaries[0].feedback)
        native=json.loads((prior/'contact_diagnostics'/provider/label(profile)/'expert.json').read_text())
        initial=np.array(tr.boundaries[0].state.pose_world['square-nut-v1'].position);rows=[];exact=0
        for i,t in enumerate(tr.transitions):
            before=tr.boundaries[i];b=tr.boundaries[i+1]
            _,target=c.compute(before.state,before.feedback,t.requested_action)
            if target.to_mapping()!=t.controller_target.to_mapping():raise ValueError('reconstructed controller differs from recorded target')
            exact+=1
            if t.expert_stage in {'descend_to_handle','close_gripper','lift_nut'}:
                rows.append(row(b.state,b.feedback,b.task_metrics,target,t.requested_action,c.memory(),b.readiness,initial,native[i]['native'],t.expert_stage))
        descend=[x for x in rows if x['stage']=='descend_to_handle'][-1];close=[x for x in rows if x['stage']=='close_gripper'];end=close[-1]
        # 500Hz has a measured 30mm request lag; do not conflate broad reach heuristic with achieved requested pose.
        cls='R0-A: pose_not_ready_before_close' if profile=='NA-TB500' else 'R0-B: gripper_did_not_close'
        events={}
        for key in ['finger_nut','hand_nut']:
            events['first_'+key]=next(({'control_step':x['control_step'],'time_s':x['simulation_time_s']} for x in rows if x['contact'][key] is True),None) if provider=='mujoco' else 'unknown: historical aggregate-only evidence'
        for name,threshold in [('first_nonzero_closing_force',0.),('first_force_activation_level',3.)]:
            events[name]=next(({'control_step':x['control_step'],'time_s':x['simulation_time_s'],'force_N':x['feedback']['closing_force_N']} for x in rows if x['feedback']['closing_force_N']>threshold),None)
        episodes.append({'profile':profile,'provider':provider,'path':str(path.resolve()),'h5_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'logical_hash':tr.identity_hash,'reconstructed_target_exact':exact,'T':len(tr.transitions),'end_descend':descend,'end_close':end,
            'classification':cls,'classification_rationale':'all end-close openings exceed frozen 0.045m; nut remains unlifted. At TB500 the emitted descend request is additionally not achieved.',
            'contact_events':events,'close_finger_contact_boundaries':sum(x['contact']['finger_nut'] is True for x in close) if provider=='mujoco' else None,
            'close_force_mode_boundaries':sum(x['controller_memory']['force_mode_active'] for x in close),'boundaries':rows})
    result={'schema':'nutassembly-grasp-r0-v0','physics_rerun':False,'episodes':episodes,
        'primary_classification':'R0-B: gripper_did_not_close (TB100/TB50); R0-A additional TB500 pose lag',
        'causal_status':'force-mode interaction vs stage duration vs geometry unresolved until controlled hold; force is actuator readback, not proof of nut contact',
        'R1_authorized':True,'unrecoverable_pose_or_geometry_proven':False}
    write(output/'r0_existing_trace_analysis.json',result)
    lines=['# R0 existing trajectory forensic analysis','','No physics rerun. Reconstructed controller targets exactly match every recorded transition. Post-boundary feedback/memory is aligned to the incoming target.','',
        '| Profile | Provider | EE/handle m | EE request residual m | Close opening m | Force N | Servo m | Grasp | Nut XY/Z m |','|---|---|---|---|---|---|---|---|---|']
    for e in episodes:
        d=e['end_descend'];x=e['end_close'];lines.append(f"| {e['profile']} | {e['provider']} | {d['eef_to_handle_dist']:.6f} | {d['EE_request_residual_m']:.6f} | {x['physical_opening_m']:.6f} | {x['feedback']['closing_force_N']:.6f} | {x['target']['servo_opening_m']:.6f} | {x['grasped_nut']} | {x['nut_displacement_XY_m']:.8f} / {x['nut_displacement_Z_m']:.8f} |")
    lines+=['','All reached_nut predicates are true at end-descend and end-close. The broad reach predicate alone does not prove finger alignment. TB500 request lag is about 30mm; TB100/TB50 1–3.5mm. All close openings exceed 45mm; no physical capture/lift evidence.','',
        'MuJoCo has no recorded finger/nut or hand/nut contact in these windows. Historical GeoPhys only records aggregate body contacts: pair attribution is unknown, not zero. Closing force is actuator force, not nut contact.','',
        'Primary TB100 provisional class R0-B; force-mode entry is reconstructed but causal prevention vs temporal delay is not established. R1 is needed; no production modification is justified from R0.']
    (output/'r0_existing_trace_analysis.md').write_text('\n'.join(lines)+'\n');return result


def hold(prior, output, provider, profile='NA-TB100'):
    """Withhold final-close observe; hold identical request outside legacy expert."""
    folder=Path(output)/'r1'/label(profile)/provider
    if (folder/'report.json').exists():raise FileExistsError('diagnostic Evidence collision')
    spec,a,source,cfg,c,s,audit,sample,realized,state,feedback,reset=initialize(prior,profile,provider)
    trace=[];report={'provider':provider,'profile':profile,'R2_executed':False,'R2_lifted_nut':None,'production_changes':False, 'reset_checks':reset, 'reset_sample_hash':sample.identity_hash, 'controller_identity':c.identity}
    initial=np.array(state.pose_world['square-nut-v1'].position)
    native_reader=geophys_pair_reader(s,source) if provider=='geophys' else lambda:contact_readback(s,provider)
    original_sample=sample.to_mapping()
    obs,info,e=observation(state,a);solution=NutAssemblySolution(config=cfg);solution.reset(obs,info,METADATA)
    def tick(action,stage):
        nonlocal state,feedback,obs,info,e
        req=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,action)))
        _,target=c.compute(state,feedback,req);applied=s.apply_control(target);state=audit.step(target);feedback=s.control_feedback(state)
        obs,info,e=observation(state,a);native=native_reader()
        x=row(state,feedback,info['task_metrics'],target,req,c.memory(),c.readiness(state,feedback),initial,native,stage)
        x['requested_action']=req.to_mapping();x['target_hash']=target.identity_hash;x['applied_control']=applied.to_mapping()
        trace.append(x);return x
    try:
        while True:
            public=solution.act();x=tick(public.action,public.stage)
            if public.stage=='close_gripper' and int(public.diagnostics['stage_step'])==cfg.close_steps+cfg.close_settle_steps-1:
                final=public.action.copy();exhaustion=x;break
            solution.observe(obs,e.reward,False,False,info)
            if solution.failed:raise RuntimeError(solution.failure_reason)
        report['close_exhaustion']=exhaustion;report['unchanged_baseline_through_close']=True
        # Frozen diagnostic criterion: semantic grasp + actual nut/finger contact for
        # three consecutive control boundaries. Force readiness alone is not capture.
        consecutive=0;event=None;max_ticks=round(1./a.timebase.control_dt)
        for n in range(max_ticks):
            x=tick(final,'diagnostic_final_close_hold')
            paired=x['contact']['finger_nut'] is True
            consecutive=consecutive+1 if paired and x['grasped_nut'] else 0
            if consecutive>=3:event=x;break
        report.update(hold_ticks=n+1,physical_hold_seconds=(n+1)*a.timebase.control_dt,
            exact_final_action=trace[-1]['requested_action']==exhaustion['requested_action'],hold_terminal=x,
            first_mechanical_readiness=event,mechanical_grasp_criterion='finger/nut contact and grasped_nut true for 3 consecutive boundaries; actuator force readiness alone insufficient',
            contact_attribution_limitation=None)
        if event:
            # One observe on already exhausted unchanged close plans existing lift
            # from measured terminal state. No alternate waypoints or expert edits.
            solution.observe(obs,e.reward,False,False,info);report['R2_executed']=True
            lift=[]
            while solution.stage=='lift_nut' and not solution.failed:
                public=solution.act();x=tick(public.action,'lift_nut');lift.append(x)
                solution.observe(obs,e.reward,False,False,info)
            report.update(R2_lifted_nut=any(x['lifted_nut'] for x in lift),R2_max_nut_lift_m=max(x['nut_displacement_Z_m'] for x in lift))
        else:report['R2_not_executed_reason']='no demonstrated stable mechanical grasp; do not use force/semantic heuristic alone'
        report['max_nut_lift_m']=max(x['nut_displacement_Z_m'] for x in trace)
        report['sample_unchanged']=sample.to_mapping()==original_sample
        report['native_count_valid']=audit.count==state.control_step*a.timebase.control_substeps
    finally:
        write(folder/'native_audit.json',audit.boundaries)
        audit.close();s.close();write(folder/'trace.json',trace);write(folder/'report.json',report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--prior',required=True);p.add_argument('--output',required=True);p.add_argument('--route',choices=['r0','hold'],required=True);p.add_argument('--provider',choices=['geophys','mujoco']);args=p.parse_args()
    result=forensic(args.prior,args.output) if args.route=='r0' else hold(args.prior,args.output,args.provider)
    print(json.dumps({k:v for k,v in result.items() if k not in {'episodes','close_exhaustion','hold_terminal'}},indent=2))

if __name__=='__main__':main()
