"""Successful source trajectories and provider-free exact action reconstruction.

No learner, inference, policy or Flow imports. Existing production controller,
readiness expert and canonical H5 contracts are consumed without modification.
"""
from dataclasses import replace, asdict
import hashlib
import json
from pathlib import Path
from ....assembly.source import TaskSceneSource
from ....tasks.pick_cube.candidate import build_candidate
from ....tasks.pick_cube.runtime_source import build_runtime_source
from ....tasks.pick_cube.reset import sample_reset
from ....tasks.pick_cube.readiness_solution import PickCubeReadinessConfig, PickCubeReadinessSolution
from ....controllers.canonical import ProductionCanonicalPandaController, RequestedAction
from ....controllers.canonical.contracts import digest
from ....controllers.canonical.kinematics import ARM
from ....runtime.sessions.control import materialize_control, ControlBinding
from ....runtime.sessions.provenance import provider_build_identity
from ....trajectory.canonical import EpisodeMetadata, BoundaryRecord, TransitionRecord, CanonicalRecorder, save, load
from ....planners.completion import ExpertExecutionInfo
from ..control.worker import observation
from ..p1_2_runtime import execution


def context(root):
    artifact = build_candidate(); source = build_runtime_source(artifact)
    xml = (Path(root) / 'approved_shared_source.xml').read_text()
    source = replace(source, scene_source=TaskSceneSource(xml, source.scene_source.base_dir, source.scene_source.source_id))
    cfg = PickCubeReadinessConfig.from_source(artifact, source)
    return artifact, source, cfg


def identities(root):
    artifact, source, cfg = context(root)
    return {'task_artifact': artifact.identity_hash,
        'controller': ProductionCanonicalPandaController.from_source(artifact, source).identity,
        'expert': PickCubeReadinessSolution(config=cfg).identity,
        'readiness': digest({'schema': 'canonical-control-readiness-v1', 'policies': [p.to_mapping() for p in cfg.policies],
            'profile_identity': cfg.profile_identity, 'config_identity': cfg.identity,
            'contract_source_sha256': hashlib.sha256(Path('task_env/controllers/canonical/readiness.py').read_bytes()).hexdigest()})}


def boundary(controller, state, feedback, info):
    return BoundaryRecord(state.control_step, state.simulation_time, state, feedback, controller.readiness(state, feedback),
        {k: float(v) for k,v in info['task_metrics'].items()}, bool(info['is_success']), bool(info['task_failure']))


def collect(root, seed, provider='geophys'):
    root = Path(root); artifact, source, cfg = context(root); ids = identities(root)
    sample = sample_reset(artifact, seed)
    folder = root / 'golden_trajectories' / provider / f'seed{seed}'
    folder.mkdir(parents=True, exist_ok=True)
    session = materialize_control(artifact, execution(provider), source=source, binding=ControlBinding('panda-v1/gripper', .08))
    try:
        realized = session.reset(sample); state = session.snapshot(); feedback = session.control_feedback(state)
        controller = ProductionCanonicalPandaController.from_source(artifact, source); controller.reset(state, feedback)
        obs, info, evaluation = observation(state, artifact)
        metadata = EpisodeMetadata('canonical-trajectory-metadata-v0', artifact.identity_hash, sample, realized, execution(provider),
            {k: json.dumps(v, sort_keys=True) for k,v in provider_build_identity(provider).items()},
            {'source_sha256': hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
             'recipe_json': json.dumps(asdict(source.config), sort_keys=True),
             'bindings_json': json.dumps({k:dict(getattr(source,k)) for k in ('joints','bodies','frames','free_joints','joint_targets')}, sort_keys=True)},
            artifact.timebase, ids['controller'], ids['expert'], ids['readiness'], cfg.identity, seed, 'regression')
        recorder = CanonicalRecorder(metadata, boundary(controller, state, feedback, info))
        expert = PickCubeReadinessSolution(config=cfg)
        expert.reset(obs, info, {'action_schema': {'controller_kind':'absolute_pose','reference':'world','rotation_representation':'quaternion_wxyz','dimension':8}},
            execution_info=ExpertExecutionInfo('expert-execution-info-v1', 0, 0., controller.readiness(state, feedback)))
        while not expert.done and not expert.failed:
            public = expert.act()
            request = RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,public.action)))
            canonical, target = controller.compute(state,feedback,request)
            applied = session.apply_control(target); state = session.step(); feedback = session.control_feedback(state)
            obs, info, evaluation = observation(state, artifact)
            after = boundary(controller,state,feedback,info)
            expert.observe(obs,evaluation.reward,False,False,info,execution_info=ExpertExecutionInfo('expert-execution-info-v1',state.control_step,state.simulation_time,after.readiness))
            hold = bool(public.diagnostics['readiness_hold'])
            recorder.append(TransitionRecord(request,canonical,target,applied,float(evaluation.reward),False,False,public.stage,
                {k:json.dumps(v,sort_keys=True) for k,v in public.diagnostics.items()},not hold,hold), after)
        trajectory = recorder.freeze('expert_endpoint' if expert.done else expert.failure_reason)
        path = folder / 'trajectory.h5'; save(path,trajectory); loaded = load(path)
        report = {'provider':provider,'seed':seed,'pass':bool(expert.done and loaded.boundaries[-1].is_success and loaded.boundaries[-1].task_metrics['cube_lift']>=.105),
            'path':str(path.resolve()),'h5_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'logical_hash':loaded.identity_hash,
            'reset_sample_hash':sample.identity_hash,'T':len(loaded.transitions),'holds':loaded.hold_count,
            'roundtrip_exact':loaded.to_mapping()==trajectory.to_mapping(),'identities':ids,
            'final_lift':loaded.boundaries[-1].task_metrics['cube_lift'],'expert_failure':expert.failure_reason}
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        if provider == 'geophys':
            (root/'golden_trajectories'/f'seed{seed}_ref.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    finally:
        session.close()


def d0(root, seed):
    root = Path(root)
    ref = json.loads((root/'golden_trajectories'/f'seed{seed}_ref.json').read_text())
    trajectory = load(ref['path']); artifact,source,_ = context(root)
    if not ref['pass'] or trajectory.identity_hash!=ref['logical_hash']:
        raise ValueError('invalid golden reference')
    controller = ProductionCanonicalPandaController.from_source(artifact,source)
    controller.reset(trajectory.boundaries[0].state,trajectory.boundaries[0].feedback)
    actions=[]; mismatches=[]
    for i,t in enumerate(trajectory.transitions):
        recorded=t.controller_target
        action=RequestedAction('absolute_joint',None,'none',tuple([recorded.arm_position[n] for n in ARM]+[2.*recorded.gripper.opening_m/.08-1.]))
        _,target=controller.compute(trajectory.boundaries[i].state,trajectory.boundaries[i].feedback,action)
        if target.to_mapping()!=recorded.to_mapping() or target.identity_hash!=recorded.identity_hash:
            mismatches.append({'transition':i,'stored':recorded.to_mapping(),'recomputed':target.to_mapping()})
        actions.append(action.to_mapping())
    out=root/'d0'/f'seed{seed}';out.mkdir(parents=True,exist_ok=True)
    (out/'actions.json').write_text(json.dumps(actions,sort_keys=True,separators=(',',':'))+'\n')
    report={'seed':seed,'T':len(actions),'exact_target_matches':len(actions)-len(mismatches), 'pass':not mismatches,
        'action_sequence_identity':digest(actions),'trajectory_logical_hash':trajectory.identity_hash,'controller_identity':controller.identity,'mismatches':mismatches}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report
