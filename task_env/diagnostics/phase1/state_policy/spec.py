"""Authority, frozen lower-layer source and P1.6 evaluation lock."""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib,json,re,subprocess,importlib.metadata
import yaml
from ....tasks.pick_cube.candidate import build_candidate
from ....tasks.pick_cube.runtime_source import build_runtime_source
from ....tasks.pick_cube.reset import sample_reset
from ....tasks.pick_cube.readiness_solution import PickCubeReadinessConfig,PickCubeReadinessSolution
from ....controllers.canonical import ProductionCanonicalPandaController
from ....controllers.canonical.contracts import digest
from ....runtime.sessions.provenance import provider_build_identity
from ....alg.state_bc.features import FEATURE_CONTRACT,ACTION_CONTRACT

BASELINE='9c5fcc26fa1164baccd72bfca450d79187b27470'
GP='c665ce5028a12bb4d2afe49f05e015fa9b684a39'
LEARNER={'schema':'state-bc-v0','input_dim':33,'output_dim':8,'hidden':[128,128],'activation':'ReLU','optimizer':'Adam','lr':.001,'batch_size':256,'epochs':200,'seed':2026,'normalization_epsilon':1e-6,'checkpoint_selection':'minimum_fixed_validation_loss'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def context():
    artifact=build_candidate();source=build_runtime_source(artifact);cfg=PickCubeReadinessConfig.from_source(artifact,source)
    return artifact,source,cfg


def identities():
    artifact,source,cfg=context()
    return {'task_artifact':artifact.identity_hash,'controller':ProductionCanonicalPandaController.from_source(artifact,source).identity,
        'expert':PickCubeReadinessSolution(config=cfg).identity,'readiness':digest({'schema':'canonical-control-readiness-v1','policies':[p.to_mapping() for p in cfg.policies],
            'profile_identity':cfg.profile_identity,'config_identity':cfg.identity,'contract_source_sha256':sha('task_env/controllers/canonical/readiness.py')})}


def verify_authority(provenance):
    d=yaml.safe_load(Path('workspace/qualification/phase1/p1_5_expert/phase_decision.yaml').read_text());f=d['frozen_identities']
    expected={'task_artifact':f['task_artifact'],'controller':f['controller'],'expert':f['expert']['identity'],'readiness':f['readiness_contract']['identity']}
    if d.get('decision')!='approve' or d.get('judge',{}).get('type')!='human' or d['implementation_commit']['geochora']!=BASELINE:raise ValueError('human_approval_mismatch')
    ids=identities();goal=Path('docs/module/task_env/goal/P1.6_4h_trajectory_state_policy_goal.md').read_text()
    if ids!=expected or ids!=provenance['identities'] or not all(v in goal and re.fullmatch('[0-9a-f]{64}',v) for v in ids.values()):raise ValueError('goal_or_decision_identity_mismatch')
    if subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'HEAD']).returncode:raise ValueError('approved_baseline_unavailable')
    if subprocess.check_output(['git','-C','GeoPhys','rev-parse','HEAD'],text=True).strip()!=GP or subprocess.check_output(['git','ls-tree','HEAD','GeoPhys'],text=True).split()[2]!=GP or subprocess.check_output(['git','-C','GeoPhys','status','--porcelain'],text=True) or importlib.metadata.version('mujoco')!='3.8.1':raise ValueError('provider_baseline_mismatch')
    for path,value in provenance['frozen_source_sha256'].items():
        if sha(path)!=value:raise ValueError('lower_phase_recovery_required: '+path)
    return ids


def prepare(root):
    root=Path(root);path=root/'p1_6_spec.yaml';provenance=json.loads((root/'provenance.json').read_text());verify_authority(provenance)
    if path.exists() or (root/'p1_6_spec_lock.json').exists():raise FileExistsError('unsafe spec collision')
    artifact,source,cfg=context();samples={str(seed):sample_reset(artifact,seed).to_mapping() for seed in (11,17,23,47,31,73)}
    spec={'schema':'p1_6-spec-v0','identities':identities(),'expert_config_identity':cfg.identity,'source_xml_sha256':hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
        'source_bindings':{'joints':dict(source.joints),'bodies':dict(source.bodies),'frames':dict(source.frames),'actuators':dict(source.joint_targets),'free_joints':dict(source.free_joints)},
        'source_config':asdict(source.config),'timebase':artifact.timebase.to_mapping(),'trajectory_schema':'canonical-trajectory-v0','file_schema':'task-env-canonical-trajectory-v0',
        'sample_sets':{'train':[11,17,23],'validation':[47],'evaluation':[31,73]},'samples':samples,'sample_hashes':{k:v['sample_id'].removeprefix('reset-') for k,v in samples.items()},
        'replay_slice':{'training_seed':11,'source_provider':'geophys','start':0,'stop_exclusive':20,'require_stage':'move_above_cube','require_pre_contact':True},
        'feature_contract':FEATURE_CONTRACT,'action_contract':ACTION_CONTRACT,'learner':LEARNER,'all_holds':'equal_weight_preserved',
        'policy_eval_horizon':2500,'success_threshold_m':.10,'collection_endpoint_m':.105,'checkpoint_parity_max_abs':1e-7,
        'providers':{p:provider_build_identity(p) for p in ('geophys','mujoco')},'lower_source_sha256':provenance['frozen_source_sha256']}
    path.write_text(yaml.safe_dump(json.loads(json.dumps(spec)),sort_keys=False));lock={'sha256':sha(path),'locked_at':datetime.now(timezone.utc).isoformat(),'goal_sha256':sha('docs/module/task_env/goal/P1.6_4h_trajectory_state_policy_goal.md'),'decision_sha256':sha('workspace/qualification/phase1/p1_5_expert/phase_decision.yaml')}
    (root/'p1_6_spec_lock.json').write_text(json.dumps(lock,indent=2)+'\n');return spec,lock


def verify(path):
    path=Path(path);root=path.parent;lock=json.loads((root/'p1_6_spec_lock.json').read_text())
    if sha(path)!=lock['sha256']:raise ValueError('spec lock mismatch')
    spec=yaml.safe_load(path.read_text());verify_authority(json.loads((root/'provenance.json').read_text()))
    if spec['identities']!=identities() or spec['learner']!=LEARNER or spec['feature_contract']!=FEATURE_CONTRACT or spec['action_contract']!=ACTION_CONTRACT:raise ValueError('frozen lower/learner contract changed')
    artifact,source,cfg=context()
    if spec['source_xml_sha256']!=hashlib.sha256(source.scene_source.xml.encode()).hexdigest() or spec['expert_config_identity']!=cfg.identity:raise ValueError('source/expert config changed')
    return spec,lock
