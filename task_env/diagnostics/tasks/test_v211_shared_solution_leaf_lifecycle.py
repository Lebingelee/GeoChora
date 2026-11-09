"""Provider-free checks for Solution and nested leaf common submission."""
from types import SimpleNamespace

import pytest

from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.planners.contracts import ExpertAction
from task_env.runtime.sessions.control_lifecycle import ControlLifecycleDispatchV1
from task_env.runtime.sessions.leaf_control import dispatch_leaf_control_interval
from task_env.diagnostics.tasks.test_phase_ii_01_r02b_leaf_execution import (
    _actions, _case, _receipt, _publication, _SyntheticRuntime, _request,
)


def _leaf_runtime(*, fault_mode=None):
    scene, _, _, _, plan = _case(split=True)
    receipt = _receipt(plan)
    publication = _publication(scene, receipt, plan=plan)
    runtime = _SyntheticRuntime(scene, receipt, publication, plan=plan, fault_mode=fault_mode)
    boundary = publication.view.boundary
    runtime._control_lifecycle_dispatch = ControlLifecycleDispatchV1(
        'control-lifecycle-dispatch-v1', 'position-target', 'synthetic-source',
        plan.source_closure_sha256, 'b' * 64, boundary.episode_id,
        boundary.boundary_id, boundary.control_step, 0,
        tuple(sorted(entry.binding.identity_hash for entry in plan.leaves)),
        'prepared',
    )
    return scene, plan, receipt, publication, runtime


def test_two_leaf_writes_use_one_common_receipt_before_step():
    scene, plan, receipt, publication, runtime = _leaf_runtime()
    result = dispatch_leaf_control_interval(
        plan, _request(plan, receipt, publication), scene=scene, runtime=runtime)
    assert result.interval_completed and runtime.step_calls == 1
    assert runtime.apply_calls == 2
    assert runtime._control_lifecycle_dispatch.stage == 'committed'
    common = runtime._last_control_submission
    assert common['status'] == 'acknowledged'
    assert common['writer_ids'] == ('arm-writer', 'hand-writer')
    assert set(common['resource_ids']) == {
        f'{entity}/{actuator}' for entity, actuator, _ in plan.resource_writers}
    assert common['attempted_writer_ids'] == common['completed_writer_ids'] == common['writer_ids']
    outer = runtime._last_scene_control_submission
    assert outer['status'] == 'acknowledged'
    assert outer['inner_submission_id'] == common['submission_id']
    assert outer['inner_command_sha256'] == common['command_sha256']
    assert len(outer['contribution_command_sha256']) == 2
    assert outer['interval']['row'] is None
    assert all(item['controller_generation'] is None for item in outer['interval']['contributions'])
    assert {(item['start_substep'], item['end_substep'])
            for item in outer['interval']['contributions']} == {(0, plan.control_substeps)}


def test_selected_leaf_binding_without_position_profiles_installs_lifecycle():
    from task_env.controllers.canonical.leaf_actions import LeafPositionActionSetV1
    from task_env.runtime.sessions.control_lifecycle import prepare_selected_control_action

    scene, _, _, _, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt, plan=plan)
    runtime = _SyntheticRuntime(scene, receipt, publication, plan=plan)
    runtime.state_boundary_identity = lambda: runtime.clock.boundary
    arm, hand = _actions(plan=plan)
    action = LeafPositionActionSetV1('leaf-position-action-set-v1', scene.identity_hash,
                                     plan.identity_sha256, arm.action, hand.action)
    env = SimpleNamespace(
        _stopped=False, session=runtime, binding=SimpleNamespace(physical_control_profile=None),
        mixed_control_profile=False, leaf_position_profile=True,
        fixed_attachment_leaf_position_profile=False, leaf_plan=plan,
        position_profiles=(), position_plan=None, position_scene=scene,
        state=SimpleNamespace(control_step=0), horizon=4,
        value={'source': SimpleNamespace(source_id='synthetic',
                                         source_closure_digest=plan.source_closure_sha256)},
        artifact=SimpleNamespace(identity_hash='b' * 64),
        _prepare_leaf_position=lambda _action: lambda: dispatch_leaf_control_interval(
            plan, _request(plan, receipt, publication), scene=scene, runtime=runtime),
    )
    execute = prepare_selected_control_action(env, action)
    assert runtime._control_lifecycle_dispatch.stage == 'prepared'
    assert execute().interval_completed
    assert runtime._control_lifecycle_dispatch.stage == 'committed'


def test_leaf_failure_is_latched_without_step_or_replay():
    scene, plan, receipt, publication, runtime = _leaf_runtime(fault_mode='hand_write_then_raise')
    with pytest.raises(RuntimeError, match='second writer'):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication), scene=scene, runtime=runtime)
    assert runtime.step_calls == 0
    assert runtime._control_lifecycle_dispatch.stage == 'failed'
    assert runtime._last_control_submission['status'] == 'failed_partial'
    assert runtime._last_scene_control_submission['status'] == 'failed_partial'
    assert (runtime._last_scene_control_submission['inner_submission_id'] ==
            runtime._last_control_submission['submission_id'])
    assert runtime.fault is not None
    with pytest.raises(RuntimeError, match='fault-latched'):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication), scene=scene, runtime=runtime)


def test_leaf_rejects_wrong_shared_controller_before_any_write():
    from dataclasses import replace
    scene, plan, receipt, publication, runtime = _leaf_runtime()
    runtime._control_lifecycle_dispatch = replace(
        runtime._control_lifecycle_dispatch, controller_identities=('wrong-controller',))
    with pytest.raises(ValueError, match='shared lifecycle'):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication), scene=scene, runtime=runtime)
    assert runtime.begin_calls == runtime.apply_calls == runtime.step_calls == 0


def test_scene_interval_tamper_rejected_before_writer_or_boundary(monkeypatch):
    from dataclasses import replace
    from task_env.runtime.sessions import control_submission
    scene, plan, receipt, publication, runtime = _leaf_runtime()
    original = control_submission.prepare_leaf_scene_interval
    calls = []
    def tamper_first(**kwargs):
        value = original(**kwargs)
        calls.append(True)
        return replace(value, artifact_sha256='f' * 64) if len(calls) == 1 else value
    monkeypatch.setattr(control_submission, 'prepare_leaf_scene_interval', tamper_first)
    with pytest.raises(ValueError, match='differs from its bound inner commands'):
        dispatch_leaf_control_interval(plan, _request(plan, receipt, publication), scene=scene, runtime=runtime)
    assert runtime.begin_calls == runtime.apply_calls == runtime.step_calls == 0
    assert not hasattr(runtime, '_control_submission_consumed')


def test_caller_solution_enters_declared_common_lifecycle():
    from task_env.diagnostics.tasks.test_v211_control_lifecycle_capability import _DeclaredController
    from task_env.diagnostics.tasks.test_v211_control_submission_contract import _Session

    class Episode:
        def require_step(self, **_kwargs):
            pass

    session = _Session()
    boundary = {'episode_id': 'episode-1', 'control_step': 0}
    captured = {}
    def prepare(action, **kwargs):
        captured.update(kwargs)
        return action
    env = SimpleNamespace(
        _episode_execution_state=lambda: Episode(),
        binding=SimpleNamespace(external_solution_actions=True, control_request_required=False,
                                physical_control_profile=None),
        _episode_mode=None, solution=None, _external_solution_owner=None, _stopped=False,
        session=session, position_profiles=(), position_plan=None, mixed_control_profile=False,
        _require_published_execution_info=lambda: None,
        info={'expert_execution_boundary_v1': boundary},
        value={'solution_identity': 'solution', 'source': SimpleNamespace(
            source_id='task', source_closure_digest='a' * 64)},
        artifact=SimpleNamespace(identity_hash='b' * 64), controller=_DeclaredController(),
        _prepare_reference_step=prepare,
    )
    proposal = ExpertAction([.1] * 8, 'go', request_boundary=boundary,
                            solution_identity='solution')
    SelectedReferenceEnv._prepare_selected_step(env, proposal)
    assert captured['proposal'] is proposal and captured['caller_driven']
    assert session._control_lifecycle_dispatch.stage == 'prepared'


def test_solution_step_preserves_context_through_shared_dispatch():
    from task_env.diagnostics.tasks.test_v211_control_lifecycle_capability import _DeclaredController
    from task_env.diagnostics.tasks.test_v211_control_submission_contract import _Session

    session = _Session()
    owner = object()
    proposal = ExpertAction([.1] * 8, 'go')
    captured = {}
    def prepare(action, **kwargs):
        captured.update(kwargs)
        return {'action': action}
    env = SimpleNamespace(
        _stopped=False, session=session,
        binding=SimpleNamespace(physical_control_profile=None),
        mixed_control_profile=False, leaf_position_profile=False,
        position_profiles=(), position_plan=None,
        value={'source': SimpleNamespace(source_id='task', source_closure_digest='a' * 64)},
        artifact=SimpleNamespace(identity_hash='b' * 64), controller=_DeclaredController(),
        _prepare_reference_step=prepare,
        _episode_execution_state=lambda: SimpleNamespace(execute_interval=lambda **ops: ops),
    )
    SelectedReferenceEnv._step(env, proposal.action, proposal=proposal, observer_solution=owner)
    assert captured == {'proposal': proposal, 'observer_solution': owner}
    assert session._control_lifecycle_dispatch.stage == 'prepared'


def test_external_solution_converts_action_for_typed_position_profile(monkeypatch):
    from task_env.runtime.sessions import control

    class Episode:
        def require_step(self, **_kwargs):
            pass

    proposal = ExpertAction([.1] * 8, 'go')
    solution = SimpleNamespace(done=False, failed=False, act=lambda *_args: proposal)
    captured = {}
    request = object()
    monkeypatch.setattr(control, 'single_position_action_request',
                        lambda action, **kwargs: captured.update(action=action, **kwargs) or request)
    env = SimpleNamespace(
        _episode_execution_state=lambda: Episode(), _external_solution_owner=solution,
        _validate_external_solution=lambda _solution: None, _stopped=False,
        session=object(), _episode_mode=None, _physical_reset_selection=None,
        mixed_control_profile=False, _require_published_execution_info=lambda: None,
        obs={}, info={}, position_profile=True, position_scene=object(),
        position_plan=object(), position_profiles=(object(),),
        _step_position_profile=lambda value, **kwargs: (value, kwargs),
    )
    result, context = SelectedReferenceEnv.step_with_solution(env, solution)
    assert result is request and context == {'proposal': proposal, 'observer_solution': solution}
    assert captured['profile'] is env.position_profiles[0]
