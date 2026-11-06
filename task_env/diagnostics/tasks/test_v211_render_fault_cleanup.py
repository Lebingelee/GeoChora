"""Guarded renderer fault/rollback semantics; no native engine or source parsing."""
from types import SimpleNamespace as N
from unittest.mock import patch
import numpy as np
import pytest
from task_env.render.camera.mujoco import MuJoCoDynamicCameraSession


def _fixture(version, *, rollback='ok', close_fails=False):
    s=object.__new__(MuJoCoDynamicCameraSession)
    s._closed=False;s._faulted=False;s._close_status='open';s._close_error=None
    s._source=N(identity_hash='src',geometry_version='geo',schema_version=version)
    s._last_projection=None;s._last_sync=None;s._materialization_identity=('scene','material')
    s._active_episode_key=('ep','reset');s._seen_episode_keys={('ep','reset')}
    s._joint_qpos_addresses={('entity','joint'):0};s._free_qpos_addresses={};s._body_ids={('entity','frame'):0}
    s._data=N(qpos=np.array([0.]),time=0.,xpos=np.array([[0.,0.,0.]]),xquat=np.array([[1.,0.,0.,0.]]));s._model=object()
    s._consumer_id='consumer';s._geometry_build_count=1;s._visual_instance_bindings=()
    calls=[];close=[]
    def kinematics(model,data):
        calls.append(float(data.qpos[0]))
        if len(calls)==2:
            data.xpos[0]=[99.,0.,0.]
            raise RuntimeError('primary update')
        if len(calls)==3 and rollback=='fail':
            data.xpos[0]=[77.,0.,0.]
            raise RuntimeError('secondary rollback')
        data.xpos[0]=[55.,0.,0.] if len(calls)==3 and rollback=='wrong_pose' else [float(data.qpos[0]),0.,0.]
    def release():
        close.append('attempted')
        if close_fails:raise RuntimeError('secondary close')
    s._mj=N(mj_kinematics=kinematics);s._renderer=N(close=release)
    def projection(step):
        b=N(scene_instance_id='scene',provider_materialization_id='material',episode_id='ep',reset_sample_id='reset',control_step=step,state_revision=step)
        return N(source_identity_hash='src',geometry_version='geo',state_boundary=b,publication_version=f'p{step}',transform_version=f't{step}',sample_clock=N(simulation_time_s=float(step)),joint_positions=(('entity','joint','native',float(step)),),frame_poses=(('entity','frame','body',(float(step),0.,0.),(1.,0.,0.,0.)),))
    p0,p1=projection(0),projection(1)
    first=s._consume_projection(p0)
    assert s.last_sync is first and s.visual_body_pose('entity','frame')[0]==(0.,0.,0.)
    return s,p1,calls,close


@pytest.mark.parametrize('version',['camera-dynamic-source-v1','camera-dynamic-source-v2'])
@pytest.mark.parametrize('rollback',['fail','wrong_pose'])
@pytest.mark.parametrize('close_fails',[False,True])
def test_failed_or_unverifiable_restoration_faults_and_preserves_errors(version,rollback,close_fails):
    s,p,calls,closed=_fixture(version,rollback=rollback,close_fails=close_fails)
    with pytest.raises(RuntimeError,match='primary update') as caught:
        s._consume_projection(p)
    assert len(calls)==3 and closed==['attempted']
    notes=' '.join(getattr(caught.value,'__notes__',[]))
    assert 'restoration also failed' in notes
    if close_fails:
        assert 'secondary close' in notes and s.close_status['status']=='close_failed_unknown_release'
    else: assert s.close_status['status']=='closed'
    assert s._closed and s._faulted
    for operation in (lambda:s.visual_body_pose('entity','frame'),lambda:s.visual_model_info(),
                      lambda:s.sync_state(object()),lambda:s.capture(object()),lambda:s.last_sync,
                      lambda:s.last_consumed_publication_version,lambda:s.last_consumed_transform_version):
        with pytest.raises(RuntimeError):operation()
    s.close();assert closed==['attempted']


@pytest.mark.parametrize('version',['camera-dynamic-source-v1','camera-dynamic-source-v2'])
def test_restored_frame_poses_still_require_rebuild(version):
    s,p,calls,closed=_fixture(version)
    with pytest.raises(RuntimeError,match='primary update') as error:
        s._consume_projection(p)
    assert any('requires rebuild' in note for note in error.value.__notes__)
    assert s._closed and s._faulted and closed==['attempted']
    with pytest.raises(RuntimeError): _=s.last_sync
    with pytest.raises(RuntimeError): s.visual_body_pose('entity','frame')
    s.close();s.close();assert closed==['attempted'] and s.close_status['status']=='closed'


def test_faulted_renderer_does_not_close_sibling_or_physics():
    broken,p,_,closed=_fixture('camera-dynamic-source-v2',rollback='fail')
    sibling,_,_,sibling_closed=_fixture('camera-dynamic-source-v2')
    physics=N(closed=False)
    with pytest.raises(RuntimeError,match='primary update'):broken._consume_projection(p)
    assert closed==['attempted'] and not sibling_closed and not physics.closed
    assert sibling.visual_body_pose('entity','frame')[0]==(0.,0.,0.)
    sibling.close()


def test_partial_constructor_failure_preserves_primary_and_cleanup_error():
    import builtins
    import xml.etree.ElementTree as ET
    from task_env.runtime.sessions import source as source_module
    import task_env.render.camera.mujoco as camera_module
    attempts=[]; captured=[]
    def release():
        attempts.append('close')
        raise RuntimeError('secondary close')
    renderer=N(close=release)
    model=N(camera=lambda _name:N(id=0))
    fake=N(MjModel=N(from_xml_string=lambda *_a,**_k:model), MjData=lambda _model:object(),
           Renderer=lambda *_a,**_k:renderer)
    real_import=builtins.__import__
    def guarded_import(name,*args,**kwargs):
        return fake if name=='mujoco' else real_import(name,*args,**kwargs)
    root=ET.Element('mujoco');ET.SubElement(root,'worldbody')
    source=N(scene_source=object(),scene_definition=object(),source_closure_digest='closure',
             schema_version='camera-dynamic-source-v1',geometry_version='geo')
    boundary=N(episode_id='ep',reset_sample_id='reset',scene_instance_id='scene',provider_materialization_id='material')
    projection=N(state_boundary=boundary,geometry_version='geo')
    camera=N(width=32,height=24,fov_y=1.,depth=False)
    original_close=MuJoCoDynamicCameraSession.close
    def tracked_close(session):
        captured.append(session)
        return original_close(session)
    with patch.object(builtins,'__import__',guarded_import), \
         patch.object(source_module,'lower_mujoco_scene_source',return_value=('ignored',{})), \
         patch.object(camera_module.ET,'fromstring',return_value=root), \
         patch.object(MuJoCoDynamicCameraSession,'_resolve_joint_addresses',return_value={}), \
         patch.object(MuJoCoDynamicCameraSession,'_resolve_body_ids',return_value={}), \
         patch.object(MuJoCoDynamicCameraSession,'_resolve_free_addresses',return_value={}), \
         patch.object(MuJoCoDynamicCameraSession,'_resolve_visual_instances',return_value=()), \
         patch.object(MuJoCoDynamicCameraSession,'_consume_projection',side_effect=ValueError('primary build')), \
         patch.object(MuJoCoDynamicCameraSession,'close',tracked_close):
        with pytest.raises(ValueError,match='primary build') as error:
            MuJoCoDynamicCameraSession(camera,source,projection,execution=object(),manifest=object())
    assert attempts==['close'] and any('secondary close' in note for note in error.value.__notes__)
    assert captured[0].close_status['status']=='close_failed_unknown_release'
    captured[0].close();assert attempts==['close']


def test_env_reports_fault_and_cleanup_without_touching_physics():
    from task_env.environment.reference_env import SelectedReferenceEnv
    s,p,_,closed=_fixture('camera-dynamic-source-v2',rollback='fail',close_fails=True)
    env=object.__new__(SelectedReferenceEnv)
    env._visual_state_session=s;env._camera_consumer=None
    with pytest.raises(RuntimeError,match='primary update'):s._consume_projection(p)
    status=env.visual_binding_status()
    assert status['faulted'] and not status['bound']
    assert status['close']['status']=='close_failed_unknown_release'
    env._close_camera_consumer()
    status=env.visual_binding_status()
    assert not status['bound'] and status['faulted'] and status['close']['status']=='close_failed_unknown_release'
    assert closed==['attempted']


def test_env_close_preserves_first_error_and_renderer_cleanup_outcome():
    from task_env.environment.reference_env import SelectedReferenceEnv
    env=object.__new__(SelectedReferenceEnv)
    def first():raise RuntimeError('consumer first')
    def second():raise RuntimeError('renderer second')
    visual=N(close=second,close_status={'status':'close_failed_unknown_release','error':'renderer second'})
    env._camera_consumer=N(close=first);env._visual_state_session=visual
    with pytest.raises(RuntimeError,match='consumer first') as error:env._close_camera_consumer()
    assert any('renderer second' in note for note in error.value.__notes__)
    assert env.visual_binding_status()['close']['status']=='close_failed_unknown_release'
