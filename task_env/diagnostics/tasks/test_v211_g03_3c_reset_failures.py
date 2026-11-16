"""Production reset consumer with synthetic terminal failures; no physics."""
from types import SimpleNamespace
import sys
import pytest

from task_env import make_env


def make_selected():
    return make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider':'mujoco', 'physics_backend':'cpu',
                      'physics_device':'cpu', 'deployment':'in_process',
                      'interpreter':sys.executable,
                      'reset_profile':'pickcube-state-only-switch-v1'},
        'controller': {'profile_id':'r3_continuous_v1'},
        'episode': {'horizon':32},
    })


def test_pure_preflight_rejects_without_closing_session_or_consuming_rng(monkeypatch):
    from task_env.environment.reset_switch import prepare_switch_reset
    env = make_selected()
    events=[]
    old = SimpleNamespace(close=lambda: events.append('close'))
    env.session = old
    seed = prepare_switch_reset(type(env), env.resolved_public_config, 31, None, None)
    env._switch_rng_state = seed.rng_state
    old_value, old_binding, old_rng = env.value, env.binding, env._switch_rng_state
    try:
        with pytest.raises(ValueError):
            env.reset(options={'execution': {'physics_provider':'geophys', 'engine':'not-real'}})
        assert env.session is old and env.value is old_value and env.binding is old_binding
        assert env._switch_rng_state == old_rng and events == []
    finally:
        env.session=None
        env.close()


def test_materialization_failure_after_release_faults_and_no_normal_publication(monkeypatch):
    env=make_selected()
    events=[]
    old=SimpleNamespace(close=lambda: events.append('close'))
    env.session=old
    def fail(*args, **kwargs):
        events.append('materialize')
        raise RuntimeError('synthetic materializer failure')
    monkeypatch.setattr('task_env.environment.reference_env.materialize_control', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic materializer failure'):
            env.reset(seed=31)
        assert events == ['close','materialize'] and env.session is None
        assert env.execution_fault is not None
        assert env._published_position_state is None
        with pytest.raises(RuntimeError, match='fault'):
            env.step([0.] * 8)
    finally:
        env.close()


def test_synthetic_partial_advance_fault_blocks_step_and_preserves_record(monkeypatch, tmp_path):
    import numpy as np
    from task_env.diagnostics.tasks.test_selected_consumers import FakeSession, _expose_fake_physics_clock
    from task_env.runtime.sessions import provenance
    monkeypatch.setattr('task_env.environment.reference_env.materialize_control', FakeSession)
    monkeypatch.setattr(FakeSession, 'build_layout_facts', property(lambda self: {}))
    monkeypatch.setattr(provenance, 'bind_selected_build_checks', lambda *a, **k: None)
    monkeypatch.setattr(provenance, 'provider_build_identity', lambda p: {'synthetic_provider':p})
    env=make_selected()
    try:
        obs, info = env.reset(seed=31)
        env.start_recording(tmp_path/'partial.h5')
        tcp=env.state.pose_world['panda-v1/ee']
        opening=sum(env.state.joint_position[f'panda-v1/finger_joint{i}'] for i in (1,2))
        limit=env.resolved_public_config.environment.action.gripper_opening_range_m
        action=np.array([*tcp.position,*tcp.quaternion_wxyz,2*opening/limit-1],dtype=np.float32)
        native=env.session._step_physics_once
        count=0
        def partial():
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('synthetic partial advance')
            native()
        env.session._step_physics_once=partial
        _expose_fake_physics_clock(env)
        with pytest.raises(RuntimeError, match='synthetic partial advance'):
            env.step(action)
        assert env.execution_fault.physical_progress == 'partially_advanced'
        assert env.execution_fault.simulation_time_before_s == 0.0
        assert env.execution_fault.simulation_time_after_s == pytest.approx(0.002)
        assert env.execution_fault.transition_status in {'incomplete', 'not_recorded'}
        assert not env.recorder.transitions
        with pytest.raises(RuntimeError, match='fault'):
            env.step(action)
        assert not (tmp_path/'partial.h5').exists()
    finally:
        env.close()


def test_source_preflight_consumer_rejection_preserves_live_session(monkeypatch):
    from task_env.runtime.sessions import provenance
    from task_env.environment.reset_switch import prepare_switch_reset
    env=make_selected()
    effects=[]
    old=SimpleNamespace(close=lambda: effects.append('old closed'))
    env.session=old
    candidate=prepare_switch_reset(type(env),env.resolved_public_config,31,None,None)
    env._switch_rng_state=candidate.rng_state
    old_rng=env._switch_rng_state
    seen=[]
    def reject(selection, **kwargs):
        seen.append((selection.physics_provider,kwargs['source'].scene_source.source_id,
                     kwargs['binding'],kwargs['value']))
        raise RuntimeError('synthetic required source dependency unavailable')
    monkeypatch.setattr(provenance,'preflight_selected_deployment',reject)
    try:
        with pytest.raises(RuntimeError,match='source dependency unavailable'):
            env.reset(options={'execution':{'physics_provider':'geophys',
                                            'deployment':'in_process','interpreter':sys.executable}})
        assert len(seen)==1 and seen[0][0]=='geophys'
        assert env.session is old and env._switch_rng_state == old_rng and effects == []
    finally:
        env.session=None
        env.close()


def test_bound_old_command_rejected_and_owned_observation_retained(monkeypatch):
    import numpy as np
    from copy import deepcopy
    from task_env.diagnostics.tasks.test_selected_consumers import FakeSession
    from task_env.runtime.sessions import provenance
    from task_env.planners.contracts import ExpertAction
    monkeypatch.setattr('task_env.environment.reference_env.materialize_control', FakeSession)
    monkeypatch.setattr(FakeSession, 'build_layout_facts', property(lambda self: {}))
    monkeypatch.setattr(provenance, 'bind_selected_build_checks', lambda *a, **k: None)
    monkeypatch.setattr(provenance, 'provider_build_identity', lambda p: {'synthetic_provider':p})
    env=make_selected()
    try:
        old_obs,info=env.reset(seed=31)
        assert info['reset_switch_v1']['configuration_generation'] == 1
        assert info['reset_switch_v1']['topology_generation'] == 1
        old_bytes={k:v.copy() for k,v in old_obs['state'].items()}
        old_boundary=deepcopy(info['expert_execution_boundary_v1'])
        old_identity=old_boundary['solution_identity']
        old_action=ExpertAction(np.zeros(8,dtype=np.float32),'hold',
                                request_boundary=old_boundary,solution_identity=old_identity)
        _, second_info = env.reset(seed=31)
        assert second_info['reset_switch_v1']['configuration_generation'] == 2
        assert second_info['reset_switch_v1']['topology_generation'] == 1
        assert second_info['execution_configuration_v1']['reset_switch_v1']['configuration_generation'] == 2
        assert all(np.array_equal(old_obs['state'][k],v) for k,v in old_bytes.items())
        assert env.info['expert_execution_boundary_v1'] != old_boundary
        with pytest.raises(ValueError,match='stale or mismatched'):
            env.step(old_action)
    finally:
        env.close()


def test_partial_reset_write_failure_reports_fault_and_releases_session(monkeypatch):
    from task_env.diagnostics.tasks.test_selected_consumers import FakeSession
    from task_env.runtime.sessions import provenance
    events=[]
    class FailedReset(FakeSession):
        def reset(self, sample):
            events.append('partial write')
            raise RuntimeError('synthetic partial reset write')
        def close(self):
            events.append('new session close')
            super().close()
    monkeypatch.setattr(FailedReset, 'build_layout_facts', property(lambda self: {}))
    monkeypatch.setattr('task_env.environment.reference_env.materialize_control', FailedReset)
    monkeypatch.setattr(provenance,'bind_selected_build_checks',lambda *a,**k:None)
    env=make_selected()
    env.session=SimpleNamespace(close=lambda:events.append('old session close'))
    try:
        with pytest.raises(RuntimeError,match='synthetic partial reset write'):
            env.reset(seed=31)
        assert events == ['old session close','partial write','new session close']
        assert env.session is None and env.execution_fault.phase == 'runtime_reset'
        assert env.execution_fault.physical_progress == 'not_advanced'
        assert env.reset_failure_receipt['previous_session_close_completed']
        assert env.reset_failure_receipt['replacement_session_close_completed']
        assert env.reset_failure_receipt['reset_write_attempted']
        assert env.reset_failure_receipt['reset_write_status'] == 'unknown'
        assert env._published_position_state is None
        with pytest.raises(RuntimeError,match='fault'):
            env.step([0.]*8)
    finally:
        env.close()


@pytest.mark.parametrize('provider', ['mujoco','geophys','isaacsim'])
def test_each_target_source_reaches_selected_preflight_without_mutation(monkeypatch,provider):
    from task_env.runtime.sessions import provenance
    env=make_selected()
    old=SimpleNamespace(close=lambda:pytest.fail('old session closed during preflight'))
    env.session=old
    routes={
        'mujoco': {'physics_provider':'mujoco','physics_backend':'cpu','physics_device':'cpu','deployment':'in_process','interpreter':sys.executable},
        'geophys': {'physics_provider':'geophys','physics_backend':'cpu','physics_device':'cpu','deployment':'in_process','interpreter':sys.executable},
        'isaacsim': {'physics_provider':'isaacsim','physics_backend':'cuda','physics_device':'cuda:0','deployment':'isolated_worker',
                     'interpreter':'/home/lly/Program_Files/Geochora/workspace/environments/isaacsim-6.2.0/bin/python',
                     'source_delivery_manifest':'/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json'},
    }
    seen=[]
    # Simulate failure at the selected deployment terminal, after production
    # config, real target source construction, binding and candidate plan.
    def reject(selection, **kwargs):
        source=kwargs['source'];value=kwargs['value']
        seen.append((selection.physics_provider,source.scene_source.source_id,
                     source.source_closure_digest,value['artifact'].identity_hash,kwargs['seed']))
        raise RuntimeError('synthetic selected terminal unavailable')
    monkeypatch.setattr(provenance,'preflight_selected_deployment',reject)
    try:
        with pytest.raises(RuntimeError,match='synthetic selected terminal unavailable'):
            env.reset(seed=31,options={'execution':routes[provider]})
        assert env.session is old and len(seen)==1 and seen[0][0]==provider
        assert len(seen[0][2])==64 and len(seen[0][3])==64 and seen[0][4]==31
        assert not hasattr(env,'_switch_rng_state')
    finally:
        env.session=None
        env.close()


@pytest.mark.parametrize('provider', ['mujoco','geophys','isaacsim'])
def test_each_real_source_reaches_its_production_materializer_boundary(monkeypatch,provider):
    from task_env.runtime.sessions import transport
    env=make_selected()
    events=[]
    env.session=SimpleNamespace(close=lambda:events.append('old closed'))
    routes={
        'mujoco': {'physics_provider':'mujoco','physics_backend':'cpu','physics_device':'cpu','deployment':'in_process','interpreter':sys.executable},
        'geophys': {'physics_provider':'geophys','physics_backend':'cpu','physics_device':'cpu','deployment':'in_process','interpreter':sys.executable},
        'isaacsim': {'physics_provider':'isaacsim','physics_backend':'cuda','physics_device':'cuda:0','deployment':'isolated_worker',
                     'interpreter':'/home/lly/Program_Files/Geochora/workspace/environments/isaacsim-6.2.0/bin/python',
                     'source_delivery_manifest':'/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json'},
    }
    observed=[]
    def reject_materializer(artifact,execution,**kwargs):
        observed.append((execution.physics_provider,artifact.identity_hash,kwargs['source'].source_closure_digest))
        raise RuntimeError('synthetic materializer terminal failure')
    def reject_worker(*args,**kwargs):
        payload = kwargs.get('payload', args[1] if len(args)>1 else None)
        observed.append(('isaacsim',payload['facts']['artifact_identity'],payload['facts']['source_closure']))
        raise RuntimeError('synthetic worker terminal failure')
    monkeypatch.setattr('task_env.environment.reference_env.materialize_control',reject_materializer)
    monkeypatch.setattr(transport,'start_selected_worker',reject_worker)
    try:
        with pytest.raises(RuntimeError,match='synthetic .* terminal failure'):
            env.reset(seed=31,options={'execution':routes[provider]})
        assert events==['old closed'] and len(observed)==1 and observed[0][0]==provider
        assert len(observed[0][1])==len(observed[0][2])==64
        assert env.execution_fault.phase=='session_materialization'
        assert env.reset_failure_receipt['previous_session_close_completed']
        assert env.reset_failure_receipt['replacement_materialization_attempted']
        assert not env.reset_failure_receipt['reset_write_attempted']
    finally:
        env.close()


@pytest.mark.parametrize('position_profile', [True, False])
def test_failed_old_position_stop_releases_candidate_source(monkeypatch, position_profile):
    from task_env.runtime.sessions import provenance
    env=make_selected()
    old=SimpleNamespace(close=lambda:pytest.fail('old session must not be closed'))
    env.session=old
    # Published state, not this legacy classification flag, requires stop.
    env.position_profile=position_profile
    env._selected_reset_stop_capability=True
    env._published_position_typed_state=object()
    seen=[]
    original=provenance.preflight_selected_deployment
    def capture(*args,**kwargs):
        seen.append(kwargs['source'].execution_source_receipt)
        return original(*args,**kwargs)
    monkeypatch.setattr(provenance,'preflight_selected_deployment',capture)
    monkeypatch.setattr(env,'stop',lambda reason: (_ for _ in ()).throw(RuntimeError('synthetic stop failure')))
    try:
        with pytest.raises(RuntimeError,match='synthetic stop failure'):
            env.reset(seed=31)
        assert env.session is old and len(seen)==1
        assert not seen[0].snapshot_root.exists()
        assert not hasattr(env,'_switch_rng_state')
    finally:
        env.session=None
        env._published_position_typed_state=None
        env._published_position_state=None
        env.close()
