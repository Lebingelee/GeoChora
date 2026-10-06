"""Provider-free sequence/sample construction, lock before governed execution."""
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import numpy as np
import yaml
from ....artifacts import CanonicalStateView
from ....controllers.canonical import PandaKinematics,CanonicalPandaController,RequestedAction
from ....controllers.canonical.kinematics import ARM
from ....tasks.pick_cube.candidate import build_candidate
from ....tasks.pick_cube.runtime_source import build_runtime_source
from ....tasks.pick_cube.reset import sample_reset
from ....tasks.pick_cube.solution import PickCubeSolutionConfig
from ....runtime.sessions.provenance import provider_build_identity

BASELINE='d983d31c107bead06e3f0f22a0bc2085044d08d8'
GEOPHYS='c665ce5028a12bb4d2afe49f05e015fa9b684a39'


def identities():
    git=lambda *a:subprocess.check_output(['git',*a],text=True).strip()
    path=Path('workspace/qualification/phase1/p1_4_camera/phase_decision.yaml');d=yaml.safe_load(path.read_text())
    providers={p:provider_build_identity(p) for p in ('geophys','mujoco')}
    if (d.get('decision')!='approve' or d.get('judge',{}).get('type')!='human' or d.get('implementation_commit',{}).get('geochora')!=BASELINE
        or d.get('provider_baseline')!={'geophys':GEOPHYS,'mujoco':'3.8.1'} or git('ls-tree','HEAD','GeoPhys').split()[2]!=GEOPHYS
        or git('-C','GeoPhys','rev-parse','HEAD')!=GEOPHYS or git('-C','GeoPhys','status','--porcelain')
        or providers['geophys']['repository_revision']!=GEOPHYS or providers['geophys']['dirty_build_sha256']
        or providers['mujoco']['package_version']!='3.8.1' or subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'HEAD']).returncode):raise ValueError('P1.4 approved provenance mismatch')
    return {'head':git('rev-parse','HEAD'),'geophys_gitlink':GEOPHYS,'geophys_checkout':git('-C','GeoPhys','rev-parse','HEAD'),'providers':providers,
        'decision_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'public_main':git('rev-parse','public/main'),
        'main_contains_approved':subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'public/main']).returncode==0}


def context():
    artifact=build_candidate();source=build_runtime_source(artifact);model=PandaKinematics(source.scene_source.xml)
    controller=CanonicalPandaController(model,artifact_hash=artifact.identity_hash,config=source.config.action)
    return artifact,source,model,controller


def virtual_state(artifact,model,sample,joints=None):
    positions=dict(sample.joint_position)
    if joints is not None:positions.update(dict(zip(ARM,map(float,joints))))
    ee=model.pose([positions[n] for n in ARM]);poses=dict(sample.poses_world);poses['panda-v1/ee']=ee
    return CanonicalStateView('canonical-state-v0','SI_right_handed_z_up_wxyz',0,0.,positions,{n:0. for n in positions},poses)


def free_space_source(source):
    root=ET.fromstring(source.scene_source.xml)
    for geom in root.iter('geom'):geom.set('contype','0');geom.set('conaffinity','0')
    for body in root.iter('body'):
        if body.get('name')=='PickCube':body.set('pos','0.5 0 -2')
    return replace(source,scene_source=replace(source.scene_source,xml=ET.tostring(root,encoding='unicode')),
        config=replace(source.config,runtime=replace(source.config.runtime,enable_ground_contact=False,enable_domain_boundary_contact=False)))


def specification():
    artifact,source,model,controller=context();samples=[sample_reset(artifact,s) for s in (31,73)];initial=virtual_state(artifact,model,samples[0])
    q0=np.array([initial.joint_position[n] for n in ARM]);sequence_a=[]
    for tick in range(40):
        alpha=(tick+1)/40;alpha=3*alpha**2-2*alpha**3;q=q0.copy();q[[0,1,2]]+=[.02*alpha,-.015*alpha,.01*alpha]
        # Freeze servo setpoint equal to smooth position target for replay; feedback correction is a separate shared-controller concern.
        _,target=controller.compute(initial,RequestedAction('absolute_joint',None,'none',tuple(map(float,np.r_[q,1]))))
        target=replace(target,arm_servo_position=target.arm_position);sequence_a.append(target.to_mapping())
    cube=np.array(samples[0].poses_world['cube-v1'].position);start=np.array(initial.pose_world['panda-v1/ee'].position)
    full_goal=cube+np.array([0,0,.145]);goal=start+.25*(full_goal-start);sequence_b=[];q=q0.copy()
    for tick in range(40):
        desired=start+(tick+1)/40*(goal-start);state=virtual_state(artifact,model,samples[0],q)
        request=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(map(float,np.r_[desired,initial.pose_world['panda-v1/ee'].quaternion_wxyz,1])))
        _,target=controller.compute(state,request);sequence_b.append(target.to_mapping());q=np.array([target.arm_position[n] for n in ARM])
    return {'schema':'p1_5-control-oracle-v0','artifact_hash':artifact.identity_hash,'source_sha256':model.source_sha256,
        'free_space_source_sha256':hashlib.sha256(free_space_source(source).scene_source.xml.encode()).hexdigest(),
        'controller_identity':controller.identity,'controller_config':asdict(controller.config),'controller_profile':'stateless_one_DLS_increment_achieved_basis_v0',
        'expert_identity':'unchanged_PickCubeSolution','expert_source_sha256':hashlib.sha256(Path('task_env/tasks/pick_cube/solution.py').read_bytes()).hexdigest(),
        'expert_config':asdict(PickCubeSolutionConfig()),'samples':[s.to_mapping() for s in samples],
        'C1_A':sequence_a,'C1_B':sequence_b,'C1_B_goal_world':goal.tolist(),
        'bounds':{'C1_A_joint_error':.03,'C1_A_pairwise_joint':.03,'C1_B_joint_error':.05,'C1_B_pairwise_joint':.05,'C1_B_pairwise_EE_m':.02,
            'joint_limit_slack':1e-5,'FK_position_m':1e-5,'FK_rotation':1e-5,'gripper_open_min_m':.07,'gripper_close_max_m':.01},
        'gripper_smoke':{'open_ticks':160,'close_ticks':160,'reopen_ticks':160,'force_limit_N':5.,'opening_range_m':.08},
        'success':'cube_lift>=0.10m','expert_endpoint':'cube_lift>=0.105m only collection endpoint','action_budget':120,
        'rationale':'User ceilings for bounded arm replay; gripper physical full-open/full-close millimeter slack. Source FK numerical representation 1e-5. C1-B quarter approach is pre-contact only; no success gate.'}


def prepare(root):
    root=Path(root);path=root/'control_oracle.yaml'
    if path.exists() or (root/'control_oracle_lock.json').exists():raise ValueError('unsafe Evidence collision')
    provenance=identities();spec=specification();path.write_text(yaml.safe_dump(json.loads(json.dumps(spec)),sort_keys=False))
    lock={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'timestamp':datetime.now(timezone.utc).isoformat(),'provenance':provenance}
    (root/'control_oracle_lock.json').write_text(json.dumps(lock,indent=2)+'\n');return lock


def verify(path):
    path=Path(path);lock=json.loads((path.parent/'control_oracle_lock.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=lock['sha256']:raise ValueError('oracle lock mismatch')
    spec=yaml.safe_load(path.read_text())
    if spec!=json.loads(json.dumps(specification())):raise ValueError('locked config/source/sample/sequence changed')
    return spec,lock
