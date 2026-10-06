"""Provider-free strict synthetic trajectory, corruption and feature tests."""
from dataclasses import replace
from pathlib import Path
import json,os,subprocess,sys
import numpy as np
from ....trajectory.canonical import EpisodeMetadata,BoundaryRecord,TransitionRecord,CanonicalTrajectory,CanonicalRecorder,save,load
from ....artifacts.execution import RealizedInitialState
from ....controllers.canonical import ProductionCanonicalPandaController,RequestedAction
from ....controllers.canonical.feedback import CanonicalControlFeedback,CanonicalGripperFeedback
from ....controllers.canonical.contracts import AppliedCanonicalControl
from ....alg.state_bc.features import features,examples
from ..control.spec import virtual_state
from ..p1_2_runtime import execution,write_json
from .spec import context,identities
from ....tasks.pick_cube.reset import sample_reset


def run(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);a,s,cfg=context();ids=identities();sample=sample_reset(a,11);state=virtual_state(a,ProductionCanonicalPandaController.from_source(a,s)._arm.model,sample)
    feedback=CanonicalControlFeedback('canonical-control-feedback-v0',0,0.,CanonicalGripperFeedback('panda-v1/gripper',.08,0.));controller=ProductionCanonicalPandaController.from_source(a,s);controller.reset(state,feedback)
    readiness=controller.readiness(state,feedback);b0=BoundaryRecord(0,0.,state,feedback,readiness,{'cube_lift':.001},False,False)
    meta=EpisodeMetadata('canonical-trajectory-metadata-v0',a.identity_hash,sample,RealizedInitialState('realized-initial-state-v0',sample.sample_id,'geophys',state,0),execution('geophys'),{'kind':'synthetic_not_native'},{'kind':'provider-free_fixture'},a.timebase,ids['controller'],ids['expert'],ids['readiness'],cfg.identity,11,'train')
    recorder=CanonicalRecorder(meta,b0)
    for tick in range(2):
        request=RequestedAction('absolute_joint',None,'none',tuple(state.joint_position[n] for n in __import__('task_env.controllers.canonical.kinematics',fromlist=['ARM']).ARM)+(1.,))
        canonical,target=controller.compute(state,feedback,request);applied=AppliedCanonicalControl('applied-canonical-control-v0',target.identity_hash,'geophys',target.arm_servo_position,target.gripper.servo_opening_m,target.gripper.force_limit_N,False,'synthetic_semantic_mapping')
        state=replace(state,control_step=tick+1,simulation_time=(tick+1)*a.timebase.control_dt);feedback=replace(feedback,control_step=state.control_step,simulation_time=state.simulation_time)
        b=BoundaryRecord(state.control_step,state.simulation_time,state,feedback,controller.readiness(state,feedback),{'cube_lift':.001},False,False)
        recorder.append(TransitionRecord(request,canonical,target,applied,0.,False,False,'move_above_cube',{'readiness_hold':json.dumps(bool(tick))},not bool(tick),bool(tick)),b)
    trajectory=recorder.freeze('synthetic');path=root/'synthetic.h5';save(path,trajectory);loaded=load(path);x,y=examples(loaded)
    result={'checks':{'T_plus_1_T':len(loaded.boundaries)==3 and len(loaded.transitions)==2,'logical_roundtrip':loaded==trajectory,'hold_count':loaded.hold_count==1,'data_replay':np.array_equal(examples(trajectory)[0],x) and np.array_equal(examples(trajectory)[1],y),
        'feature_shape_dtype':x.shape==(2,33) and x.dtype==np.float32 and y.shape==(2,8) and y.dtype==np.float32,
        'deterministic_feature':np.array_equal(features(b0.state,b0.feedback),features(b0.state,b0.feedback))}}
    for name,operation in [('missing_boundary',lambda:replace(trajectory,boundaries=trajectory.boundaries[:-1])),('unknown_field',lambda:CanonicalTrajectory.from_mapping({**trajectory.to_mapping(),'native_id':3})),('target_hash',lambda:replace(trajectory.transitions[0].applied_control,target_hash='0'*64))]:
        try:
            value=operation()
            if name=='target_hash':replace(trajectory.transitions[0],applied_control=value)
        except (ValueError,TypeError):result['checks']['reject_'+name]=True
        else:result['checks']['reject_'+name]=False
    import h5py
    corrupt=root/'corrupt.h5';corrupt.write_bytes(path.read_bytes())
    with h5py.File(corrupt,'r+') as h:
        data=h['numeric/reward'][:].astype(np.float32);del h['numeric/reward'];h['numeric'].create_dataset('reward',data=data)
    try:load(corrupt)
    except ValueError:result['checks']['reject_numeric_dtype_corruption']=True
    else:result['checks']['reject_numeric_dtype_corruption']=False
    command=[sys.executable,'-c',"import sys; from task_env.trajectory.canonical import load; from task_env.alg.state_bc.features import examples; x,y=examples(load(sys.argv[1])); forbidden=[n for n in sys.modules if n.split('.')[0] in {'geophys','mujoco','sapien','genesis','taichi'}]; assert not forbidden,forbidden; print(x.shape,y.shape,'PASS no simulator')",str(path)]
    guard=subprocess.run(command,capture_output=True,text=True,env=os.environ.copy());result['guard']={'returncode':guard.returncode,'stdout':guard.stdout,'stderr':guard.stderr};result['checks']['fresh_data_replay_guard']=guard.returncode==0
    result['pass']=all(result['checks'].values());write_json(root/'report.json',result);return result
