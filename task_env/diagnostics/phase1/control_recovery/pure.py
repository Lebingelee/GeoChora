"""Provider-free state-machine, identity and strict feedback probes."""
from dataclasses import asdict,replace
import json,os,subprocess,sys
import yaml
from ....controllers.canonical import (ProductionCanonicalPandaController,
    CanonicalControlFeedback,CanonicalGripperFeedback,RequestedAction)
from ....controllers.canonical.kinematics import ARM,FINGERS
from ..control.spec import context,virtual_state
from ....artifacts.execution import ResetSample


def setup():
    a,s,m,_=context();old=yaml.safe_load(open('workspace/qualification/phase1/p1_5_expert/control_oracle.yaml'))
    state=virtual_state(a,m,ResetSample.from_mapping(old['samples'][0]));c=ProductionCanonicalPandaController.from_source(a,s)
    return a,s,m,state,c


def feedback(state,force):
    return CanonicalControlFeedback('canonical-control-feedback-v0',state.control_step,state.simulation_time,
        CanonicalGripperFeedback('panda-v1/gripper',max(0.,sum(state.joint_position[n] for n in FINGERS)),force))


def at(state,tick,opening):
    q=dict(state.joint_position);q.update({n:opening/2 for n in FINGERS})
    return replace(state,control_step=tick,simulation_time=tick*.002,joint_position=q)


def checks():
    a,s,m,initial,c=setup();cfg=s.config.robot.gripper;stiff=s.config.action.gripper_position_stiffness_N_per_m
    request=lambda scalar:RequestedAction('absolute_joint',None,'none',tuple(initial.joint_position[n] for n in ARM)+(scalar,))
    f0=feedback(initial,0.);c.reset(initial,f0);clone=ProductionCanonicalPandaController.from_source(a,s);clone.reset(initial,f0)
    out=c.compute(initial,f0,request(-1.));repeat=clone.compute(initial,f0,request(-1.));memory=c.memory();checks={
        'resolved_profile_identity':out[1].gripper.force_limit_N==cfg.force_limit_N,
        'identical_history_target':out==repeat,'rate_limit':abs(memory.commanded_opening_m-(.08-cfg.opening_step_m))<1e-12,
        'initial_no_force_mode':not memory.force_mode_active}
    state=at(initial,1,.079);f=feedback(state,max(.5,.1*cfg.force_limit_N)+1)
    c.compute(state,f,request(-1.));expected=.079-cfg.force_limit_N/stiff-cfg.force_adjust_step_m
    checks['first_force_initialization']=c.memory().force_mode_active and c.memory().force_mode_initialized and abs(c.memory().commanded_opening_m-expected)<1e-12
    state=at(initial,2,.06);c.compute(state,feedback(state,cfg.force_limit_N-.5*cfg.force_deadband_N),request(-1.))
    checks['deadband_holds_persistent_command']=abs(c.memory().commanded_opening_m-expected)<1e-12
    state=at(initial,3,.055);c.compute(state,feedback(state,cfg.force_limit_N-2*cfg.force_deadband_N),request(-1.))
    checks['insufficient_force_adjusts_without_reseeding']=abs(c.memory().commanded_opening_m-(expected-cfg.force_adjust_step_m))<1e-12
    state=at(initial,4,.05);c.compute(state,feedback(state,0.),request(1.))
    checks['explicit_open_resets_force_cycle']=not c.memory().force_mode_active and not c.memory().force_mode_initialized
    c.reset(initial,f0);checks['reset_reseed_deterministic']=c.compute(initial,f0,request(-1.))==repeat
    try:c.compute(initial,f0,request(-1.))
    except RuntimeError:checks['duplicate_compute_rejected']=True
    else:checks['duplicate_compute_rejected']=False
    c.reset(initial,f0)
    try:c.compute(initial,replace(f0,control_step=1),request(-1.))
    except ValueError:checks['stale_boundary_rejected']=True
    else:checks['stale_boundary_rejected']=False
    c.reset(initial,f0)
    try:c.compute(initial,replace(f0,gripper=replace(f0.gripper,opening_m=.07)),request(-1.))
    except ValueError:checks['opening_coherence_rejected']=True
    else:checks['opening_coherence_rejected']=False
    for codec,value in [('json',json.loads(json.dumps(f.to_mapping()))),('yaml',yaml.safe_load(yaml.safe_dump(f.to_mapping())))]:
        checks[codec+'_feedback_roundtrip']=CanonicalControlFeedback.from_mapping(value)==f
    for name in ('kind','force_limit_N','opening_step_m','force_deadband_N','force_adjust_step_m'):
        if name=='kind':
            try:ProductionCanonicalPandaController(m,artifact_hash=a.identity_hash,config=s.config.action,gripper_config=replace(cfg,kind='legacy'))
            except ValueError:checks['unsupported_kind_fail_closed']=True
        else:
            changed=replace(cfg,**{name:getattr(cfg,name)*1.1})
            other=ProductionCanonicalPandaController(m,artifact_hash=a.identity_hash,config=s.config.action,gripper_config=changed)
            checks[name+'_changes_identity']=other.identity!=c.identity
    # Same shared pose lowering, with explicit reset of the gripper lifecycle.
    request_pose=RequestedAction('absolute_pose','world','quaternion_wxyz',tuple(initial.pose_world['panda-v1/ee'].position)+tuple(initial.pose_world['panda-v1/ee'].quaternion_wxyz)+(1.,))
    c.reset(initial,f0);clone.reset(initial,f0);checks['shared_pose_target_deterministic']=c.compute(initial,f0,request_pose)==clone.compute(initial,f0,request_pose)
    code="from task_env.diagnostics.phase1.control_recovery.pure import setup,feedback; from task_env.controllers.canonical import RequestedAction; from task_env.controllers.canonical.kinematics import ARM; import sys; a,s,m,state,c=setup(); f=feedback(state,0.); c.reset(state,f); c.compute(state,f,RequestedAction('absolute_joint',None,'none',tuple(state.joint_position[n] for n in ARM)+(1.,))); bad=[n for n in sys.modules if n.split('.')[0] in {'geophys','mujoco','sapien','genesis','taichi'}]; assert not bad,bad; print('PASS provider-free R1 computation')"
    guard=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,env=os.environ.copy())
    checks['fresh_provider_free_computation']=guard.returncode==0
    return {'pass':all(checks.values()),'checks':checks,'guard':{'stdout':guard.stdout,'stderr':guard.stderr},'profile':asdict(cfg),'controller_identity':c.identity}
