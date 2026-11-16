"""F06 existing Recorder/H5 stores measured typed velocity boundaries."""
import json
import h5py
import numpy as np
import pytest
from task_env.artifacts import PoseWorld, FrameReference
from task_env.artifacts.state import (CanonicalStateViewV1,StateBoundaryIdentity,StateSampleClock,
                                      TypedFrameStateValue,TypedJointStateValue)
from task_env.recorders import RecorderConfig,TransitionRecorder,load_structured_control_records_h5
from task_env.diagnostics.tasks.test_phase_ii_c05a_structured_recording import _control,_outcome,COMPONENTS,ACTION_SCHEMA


def view(index):
    boundary=StateBoundaryIdentity('state-boundary-identity-v1','episode','reset-'+'1'*64,'2'*64,'scene','materialization',index,index)
    clock=StateSampleClock('state-sample-clock-v1','evaluation_boundary',index,index*.01)
    joints=[]
    for i in range(1,10):
        finger=i>7;name=('finger_joint'+str(i-7)) if finger else ('joint'+str(i))
        joints.append(TypedJointStateValue('typed-joint-state-v1','panda-v1',name,
            'prismatic' if finger else 'revolute','meter' if finger else 'radian',(0.01*i,),
            'meter_per_second' if finger else 'radian_per_second',(0.001*i*(index+1),)))
    frame=TypedFrameStateValue('typed-frame-state-v1',FrameReference('panda-v1','ee'),PoseWorld((0,0,1),(1,0,0,0)))
    return CanonicalStateViewV1('canonical-state-v1','SI_right_handed_z_up_wxyz',boundary,clock,tuple(joints),(frame,)).to_mapping()


def record(tmp_path, *, missing=False):
    profile={'typed_state_h5_witness_schema_version':'f06-public-typed-state-witness-v1',
      'source_closure_digest':'3'*64,'request_identity_sha256':'4'*64,
      'materialization_identity':'materialization','reset_sample_id':'reset-'+'1'*64,'scene_identity_hash':'2'*64}
    metadata={'env_metadata':{'env_name':'fixture','task_name':'fixture','task_version':'1','scene_uid':'scene',
      'agent_uids':('panda',),'action_schema':{'schema_id':ACTION_SCHEMA,'schema_version':'panda-action-v1',
      'controller_kind':'absolute_pose','reference':'world','components':COMPONENTS},
      'observation_schema':{'leaf_specs':[{'path':'state.ee_pose','semantic':'state'}]},'reference_profile':profile},
      'universal_action_schema':{'version':'panda-universal-action-v1','dimension':8,'components':COMPONENTS}}
    state0=view(0);state1=view(1)
    if missing:state1['joints']=[j for j in state1['joints'] if j['joint_id']!='joint4']
    recorder=TransitionRecorder(RecorderConfig(schema_version='v3',max_transitions=1))
    def info(state):
        return {'canonical_state_view_v1':state,'state_boundary_identity':state['boundary'],
                'state_sample_clock':state['sample_clock']}
    def observation(state):
        b=StateBoundaryIdentity.from_mapping(state['boundary'])
        return {'state':{'joint_position':np.asarray([0.01*i for i in range(1,10)],dtype=np.float32),
          'ee_pose':np.asarray([0,0,1,1,0,0,0],dtype=np.float32),
          'hand_pose':np.asarray([0,0,1,1,0,0,0],dtype=np.float32),
          'boundary_identity_sha256':np.frombuffer(bytes.fromhex(b.boundary_id.removeprefix('state-boundary-')),dtype=np.uint8).copy()}}
    recorder.begin_episode(observation(state0),info(state0),metadata)
    values=(0.1,0.2,0.3,1.,0.,0.,0.,0.5)
    recorder.append_transition(np.array(values,dtype=np.float32),np.array(values,dtype=np.float32),
        observation(state1),0.,False,False,False,info(state1),structured_control=_control(values))
    recorder.end_episode('expert_endpoint',outcome=_outcome('episode',1,'expert_endpoint',truncated=True))
    return recorder.save_h5(tmp_path,'witness.h5')


def test_real_recorder_and_reader_preserve_measured_velocity(tmp_path):
    path=record(tmp_path);result=load_structured_control_records_h5(path)
    witness=result['f06_typed_state_witness'];assert len(witness['rows'])==2
    joints=witness['rows'][1]['canonical_state_view_v1']['joints']
    joint=next(j for j in joints if j['joint_id']=='joint4')
    assert joint['velocity']==[0.008] and joint['velocity_representation']=='radian_per_second'


def test_missing_required_joint_velocity_rejected(tmp_path):
    with pytest.raises(ValueError,match='all nine named joint velocities'):
        record(tmp_path,missing=True)


def test_independent_reader_rejects_missing_velocity_and_wrong_frame(tmp_path):
    path=record(tmp_path)
    with h5py.File(path,'r+') as root:
        dataset=root['meta/f06_public_typed_state_witness_v1_json']
        value=json.loads(dataset[()].decode())
        value['rows'][1]['canonical_state_view_v1']['joints']=[j for j in value['rows'][1]['canonical_state_view_v1']['joints'] if j['joint_id']!='joint4']
        dataset[()]=json.dumps(value)
    with pytest.raises(ValueError,match='all nine named joint velocities'):
        load_structured_control_records_h5(path)

    path.unlink();path=record(tmp_path)
    with h5py.File(path,'r+') as root:
        root['obs/state/hand_pose'][1,2]+=0.1
    with pytest.raises(ValueError,match='observation or frame'):
        load_structured_control_records_h5(path)
