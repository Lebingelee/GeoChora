"""Frozen D1/D2 worker over accepted public session/control boundaries."""
import hashlib
import json
from pathlib import Path
import traceback
import yaml
from ....trajectory.canonical import load
from ....controllers.canonical import ProductionCanonicalPandaController, RequestedAction
from ....controllers.canonical.contracts import digest
from ....runtime.sessions.control import materialize_control, ControlBinding
from ....tasks.pick_cube.canonical_semantics import evaluate
from ..p1_2_runtime import execution
from .golden import context


def verify(root):
    root=Path(root); path=root/'provider_spec.yaml'
    lock=json.loads((root/'provider_spec_lock.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=lock['sha256']:
        raise ValueError('provider spec lock mismatch')
    spec=yaml.safe_load(path.read_text())
    for path,value in spec['adapter_source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=value:
            raise ValueError('adapter source changed after replay lock: '+path)
    for path,value in spec['frozen_sources'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=value:
            raise ValueError('accepted source changed: '+path)
    return spec


def run(root, route, provider, seed):
    root=Path(root);spec=verify(root)
    ref=spec['golden'][str(seed)];trajectory=load(ref['path'])
    actions=json.loads((root/'d0'/f'seed{seed}'/'actions.json').read_text())
    if (trajectory.identity_hash!=ref['logical_hash'] or hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['h5_sha256']
        or digest(actions)!=spec['d0'][str(seed)]['action_sequence_identity']):
        raise ValueError('golden/action identity changed')
    folder=root/route.lower()/provider/f'seed{seed}';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'report.json').exists():raise FileExistsError('replay Evidence collision')
    artifact,source,_=context(root);session=None;trace=[]
    report={'route':route,'provider':provider,'seed':seed,'execution_valid':False,'task_valid':False,'first_success':None,
        'final_lift':None,'max_lift':None,'first_boundary':None,'sample_hash':trajectory.metadata.reset_sample.identity_hash,
        'trajectory_logical_hash':trajectory.identity_hash,'action_sequence_identity':digest(actions)}
    stage='materialization'
    try:
        session=materialize_control(artifact,execution(provider),source=source,binding=ControlBinding('panda-v1/gripper',.08))
        stage='reset';sample=trajectory.metadata.reset_sample;before=sample.to_mapping();session.reset(sample);state=session.snapshot()
        controller=None
        if route=='D2':
            controller=ProductionCanonicalPandaController.from_source(artifact,source)
            if controller.identity!=spec['identities']['controller']:raise ValueError('controller identity mismatch')
            controller.reset(state,session.control_feedback(state))
        report['max_lift']=float(evaluate(state,artifact.semantics).metrics['cube_lift'])
        stage='replay'
        for i,transition in enumerate(trajectory.transitions):
            stored=transition.controller_target
            if route=='D1':target=stored;canonical=None;request=None
            else:
                request=RequestedAction.from_mapping(actions[i]);feedback=session.control_feedback(state)
                canonical,target=controller.compute(state,feedback,request)
            old_hash=target.identity_hash;applied=session.apply_control(target);old=state;state=session.step()
            if target.identity_hash!=old_hash or applied.target_hash!=old_hash:raise ValueError('target linkage changed')
            if state.control_step!=old.control_step+1 or state.simulation_time<=old.simulation_time:raise ValueError('time not monotonic')
            if set(state.joint_position)!=set(old.joint_position) or set(state.pose_world)!=set(old.pose_world):raise ValueError('semantic field set changed')
            e=evaluate(state,artifact.semantics);lift=float(e.metrics['cube_lift'])
            report['max_lift']=max(report['max_lift'],lift)
            if e.success and report['first_success'] is None:report['first_success']=state.control_step
            trace.append({'state':state.to_mapping(),'target':target.to_mapping(),'applied':applied.to_mapping(),
                'requested':request.to_mapping() if request else None,'canonical':canonical.to_mapping() if canonical else None,
                'is_success':e.success,'cube_lift':lift,'stored_target_hash':stored.identity_hash,
                'target_matches_source':old_hash==stored.identity_hash})
        report.update(execution_valid=sample.to_mapping()==before,task_valid=bool(e.success and report['first_success'] is not None),
            final_lift=lift,steps=len(trace),target_match_count=sum(t['target_matches_source'] for t in trace),
            sample_unchanged=sample.to_mapping()==before)
        report['first_boundary']=None if report['task_valid'] else 'provider_replay_task_behavior'
    except Exception as error:
        report.update(first_boundary=stage,error=str(error),traceback=traceback.format_exc(),steps=len(trace))
    finally:
        if session is not None:session.close()
        verify(root)
        (folder/'trace.json').write_text(json.dumps(trace,allow_nan=False)+'\n')
        (folder/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
