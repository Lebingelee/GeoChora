"""Provider-free contract checks for versioned visual state projection."""
from dataclasses import replace
from pathlib import Path

import pytest

from task_env.artifacts import (ArticulationDefinition, CanonicalStateViewV1, FrameDefinition,
    FrameReference, PoseWorld, StateBoundaryIdentity, StateSampleClock,
    TypedFrameStateValue, TypedJointStateValue)
from task_env.assembly.source import TaskSceneSource
from task_env.diagnostics.tasks.test_phase_ii_d02a_state_contracts import _joint, _scene
from task_env.render.camera import (DynamicCameraRenderSourceV1, DynamicCameraRenderSourceV2,
    DynamicRenderFrameBindingV1, DynamicRenderJointBindingV1, project_render_state_v1)


def _values():
    scalar = _joint()
    free = replace(_joint('floating', joint_id='free'), child_frame=FrameReference('robot', 'floating'))
    original = _scene(scalar)
    frames = (*original.frames, FrameDefinition('frame-definition-v1', 'robot', 'floating', 'runtime', None, None))
    articulation = ArticulationDefinition('articulation-definition-v1', 'robot', 'base',
                                          ('base', 'link', 'floating'), (scalar, free))
    scene = replace(original, schema_version='scene-definition-v3', frames=frames,
                    articulations=(articulation,), robots=(), actuator_resources=(), control_groups=())
    source_id = 'scene-definition-v3:' + scene.identity_hash
    source = DynamicCameraRenderSourceV2('camera-dynamic-source-v2', 'a'*64, scene.identity_hash,
        source_id, 'b'*64, TaskSceneSource('', Path('.'), source_id), scene,
        (DynamicRenderJointBindingV1('robot','joint1','hinge'),),
        (DynamicRenderFrameBindingV1('robot','link','link'),
         DynamicRenderFrameBindingV1('robot','floating','floating')),
        (('robot','free','free_joint','robot','floating'),),
        (('robot','link'),('robot','floating')))
    pose = PoseWorld((0.1,0.2,0.3), (1.,0.,0.,0.))
    frame = FrameReference('robot','floating')
    joints=(TypedJointStateValue('typed-joint-state-v1','robot','joint1','revolute','radian',(0.2,),
              'radian_per_second',(0.,)),
            TypedJointStateValue('typed-joint-state-v1','robot','free','floating',free.position_representation,
              (*pose.position,*pose.quaternion_wxyz),free.velocity_representation,(0.,)*6,frame,frame))
    state=CanonicalStateViewV1('canonical-state-v1','SI_right_handed_z_up_wxyz',
        StateBoundaryIdentity('state-boundary-identity-v1','episode','reset-'+'c'*64,scene.identity_hash,
                              'scene-instance','materialization',0,0),
        StateSampleClock('state-sample-clock-v1','evaluation_boundary',0,0.), joints,
        (TypedFrameStateValue('typed-frame-state-v1',FrameReference('robot','link'),pose),
         TypedFrameStateValue('typed-frame-state-v1',frame,pose)))
    return source,state


def test_v2_free_pose_identity_and_rejections():
    source,state=_values()
    projection=project_render_state_v1(source,state)
    assert len(projection.joint_positions)==1 and len(projection.frame_poses)==2
    assert source.identity_hash != DynamicCameraRenderSourceV1(
        'camera-dynamic-source-v1',source.task_artifact_hash,source.scene_identity_hash,
        source.source_identity,source.source_closure_digest,source.scene_source,source.scene_definition,
        source.joint_bindings,source.frame_bindings).identity_hash
    with pytest.raises(ValueError,match='Frame identities'):
        project_render_state_v1(source,replace(state,frames=state.frames[:-1]))
    with pytest.raises(ValueError,match='duplicate'):
        project_render_state_v1(source,replace(state,frames=state.frames+(state.frames[0],)))
    with pytest.raises(ValueError,match='Scene identity'):
        project_render_state_v1(source,replace(state,boundary=replace(state.boundary,scene_identity_hash='f'*64)))
    free=next(v for v in state.joints if v.kind=='floating')
    bad=replace(free,position=(0.9,*free.position[1:]))
    with pytest.raises(ValueError,match='body-origin'):
        project_render_state_v1(source,replace(state,joints=tuple(bad if v is free else v for v in state.joints)))
    with pytest.raises(ValueError,match='unique'):
        replace(source,free_bindings=source.free_bindings*2).validate()
    negative=replace(free,position=(*free.position[:3],*(-x for x in free.position[3:])))
    project_render_state_v1(source,replace(state,joints=tuple(negative if v is free else v for v in state.joints)))


def test_v1_scalar_projection_and_identity_remain_stable():
    import hashlib
    import json
    v2,state=_values()
    source=DynamicCameraRenderSourceV1('camera-dynamic-source-v1',v2.task_artifact_hash,
        v2.scene_identity_hash,v2.source_identity,v2.source_closure_digest,v2.scene_source,
        v2.scene_definition,v2.joint_bindings,v2.frame_bindings)
    scalar_state=replace(state,joints=tuple(v for v in state.joints if v.kind!='floating'))
    payload={'schema_version':'camera-dynamic-source-v1','task_artifact_hash':source.task_artifact_hash,
             'scene_identity_hash':source.scene_identity_hash,'source_identity':source.source_identity,
             'source_closure_digest':source.source_closure_digest,
             'joint_bindings':tuple(v.to_mapping() for v in source.joint_bindings),
             'frame_bindings':tuple(v.to_mapping() for v in source.frame_bindings)}
    assert source.identity_hash == hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()).hexdigest()
    assert project_render_state_v1(source,scalar_state).joint_positions[0][-1]==0.2
    with pytest.raises(ValueError,match='Joint identities'):
        project_render_state_v1(source,state)


def test_v2_unproven_mapping_is_rejected_before_native_admission():
    from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.observations.canonical_camera.contracts import IDENTITY
    from task_env.render.camera import V211_DYNAMIC_PROFILE, V211_PHYSICS_PROFILE, admit_dynamic_camera
    source,_=_values()
    camera=CameraGeometry('camera-observation-v0',source.task_artifact_hash,'cam','world',
                          IDENTITY,IDENTITY,32,24,1.,.01,10.,True,False)
    selection=RendererSelectionV1('renderer-selection-v1','mujoco','native-opengl',V211_DYNAMIC_PROFILE,None)
    execution=ExecutionSpecV1('execution-spec-v1','mujoco','cpu',V211_PHYSICS_PROFILE,31,
                              'best_effort',selection,physics_device='cpu')
    with pytest.raises(TypeError,match='RuntimeSource and TaskArtifactV1'):
        admit_dynamic_camera(camera,execution,source=source)


def test_nonfinite_and_free_joint_frame_disagreement_are_rejected():
    source,state=_values()
    scalar=next(v for v in state.joints if v.kind=='revolute')
    with pytest.raises(ValueError):
        invalid=replace(scalar,position=(float('nan'),))
        project_render_state_v1(source,replace(state,joints=tuple(invalid if v is scalar else v for v in state.joints)))
    with pytest.raises(ValueError):
        PoseWorld((float('inf'),0.,0.),(1.,0.,0.,0.))


def test_v1_scalar_session_sync_and_stale_rejection_without_sdk():
    import numpy as np
    from types import SimpleNamespace
    from task_env.render.camera.mujoco import MuJoCoDynamicCameraSession
    v2,state=_values()
    source=DynamicCameraRenderSourceV1('camera-dynamic-source-v1',v2.task_artifact_hash,
        v2.scene_identity_hash,v2.source_identity,v2.source_closure_digest,v2.scene_source,
        v2.scene_definition,v2.joint_bindings,v2.frame_bindings)
    state=replace(state,joints=tuple(v for v in state.joints if v.kind!='floating'))
    session=object.__new__(MuJoCoDynamicCameraSession)
    session._closed=False;session._source=source;session._last_projection=None;session._last_sync=None
    session._consumer_id='scalar-test';session._geometry_build_count=1;session._visual_instance_bindings=()
    b=state.boundary;session._active_episode_key=(b.episode_id,b.reset_sample_id)
    session._seen_episode_keys={session._active_episode_key};session._materialization_identity=(b.scene_instance_id,b.provider_materialization_id)
    session._joint_qpos_addresses={('robot','joint1'):0};session._free_qpos_addresses={}
    session._body_ids={('robot','link'):0,('robot','floating'):1}
    session._data=SimpleNamespace(qpos=np.zeros(1),time=0.,xpos=np.array([[.1,.2,.3],[.1,.2,.3]]),xquat=np.array([[1.,0.,0.,0.],[1.,0.,0.,0.]]))
    session._model=object();session._mj=SimpleNamespace(mj_kinematics=lambda *_:None)
    first=session.sync_state(state)
    assert first.schema_version=='render-state-sync-receipt-v1' and first.transforms_updated
    moved=replace(state,boundary=replace(b,control_step=1,state_revision=1),
                  sample_clock=replace(state.sample_clock,sample_index=1,simulation_time_s=.01),
                  joints=(replace(state.joints[0],position=(.3,)),))
    assert session.sync_state(moved).publication_updated
    with pytest.raises(ValueError,match='stale'):
        session.sync_state(state)


def test_v2_named_mapping_with_extra_nested_link_and_joint():
    """A second, nested joint is mapped by names, not by the PickCube shape."""
    source, state = _values()
    new_joint = replace(_joint('prismatic', joint_id='slide_b'),
                        parent_frame=FrameReference('robot', 'link'),
                        child_frame=FrameReference('robot', 'tool_b'))
    art = source.scene_definition.articulations[0]
    scene = replace(source.scene_definition,
                    frames=source.scene_definition.frames +
                        (FrameDefinition('frame-definition-v1', 'robot', 'tool_b', 'runtime', None, None),),
                    articulations=(replace(art, link_frame_ids=art.link_frame_ids + ('tool_b',), joints=art.joints + (new_joint,)),))
    source_id = 'scene-definition-v3:' + scene.identity_hash
    expanded = replace(source, scene_definition=scene, scene_identity_hash=scene.identity_hash,
        source_identity=source_id, scene_source=TaskSceneSource('', Path('.'), source_id),
        joint_bindings=source.joint_bindings + (DynamicRenderJointBindingV1('robot', 'slide_b', 'native_slide_b'),),
        frame_bindings=source.frame_bindings + (DynamicRenderFrameBindingV1('robot', 'tool_b', 'native_tool_b'),),
        published_frame_keys=source.published_frame_keys + (('robot', 'tool_b'),))
    added = TypedJointStateValue('typed-joint-state-v1', 'robot', 'slide_b', 'prismatic',
                                 'meter', (.08,), 'meter_per_second', (0.,))
    frame = TypedFrameStateValue('typed-frame-state-v1', FrameReference('robot', 'tool_b'),
                                 PoseWorld((.2, .3, .4), (1., 0., 0., 0.)))
    state2 = replace(state, boundary=replace(state.boundary, scene_identity_hash=scene.identity_hash),
                     joints=state.joints + (added,), frames=state.frames + (frame,))
    projection = project_render_state_v1(expanded, state2)
    assert len(projection.joint_positions) == 2 and len(projection.frame_poses) == 3
    with pytest.raises(ValueError, match='Joint identities'):
        project_render_state_v1(expanded, replace(state2, joints=state2.joints[:-1]))
    with pytest.raises(ValueError, match='duplicate'):
        project_render_state_v1(expanded, replace(state2, frames=state2.frames + (frame,)))
