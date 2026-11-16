"""Pure contract checks for bounded Position sequences."""
from dataclasses import replace
import pytest
from task_env.controllers.canonical.contracts import RequestedAction
from task_env.controllers.canonical.position_sequence import PositionActionSequenceV1, PositionActionSliceV1


def test_position_slices_are_immutable_contiguous_absolute_joint_requests():
    action = RequestedAction('absolute_joint', None, 'none', (0., -.2, 0., -1.5, 0., 1.5, -.7, .5))
    first = PositionActionSliceV1(0, 2, action)
    second = PositionActionSliceV1(2, 5, action)
    sequence = PositionActionSequenceV1((first, second))
    sequence.validate(substeps=5)
    assert sequence.identity_hash != replace(sequence, slices=(first, replace(second, end_substep=4))).identity_hash
    for start in (1, 3, 2.0):
        with pytest.raises(ValueError):
            replace(sequence, slices=(first, replace(second, start_substep=start))).validate(substeps=5)
    with pytest.raises(ValueError, match='complete'):
        replace(sequence, slices=(first, replace(second, end_substep=4))).validate(substeps=5)
    pose = RequestedAction('absolute_pose', 'world', 'quaternion_wxyz', (0., 0., 0., 1., 0., 0., 0., 0.))
    with pytest.raises(ValueError, match='absolute-joint'):
        replace(sequence, slices=(first, replace(second, request=pose))).validate(substeps=5)


def test_position_sequence_rejects_mutable_or_boolean_action_values():
    request = RequestedAction('absolute_joint', None, 'none', (0., 0., 0., -1., 0., 1., 0., 0.))
    sequence = PositionActionSequenceV1((PositionActionSliceV1(0, 5, request),))
    for values in (list(request.values), (True, *request.values[1:])):
        tampered = replace(request)
        object.__setattr__(tampered, 'values', values)
        with pytest.raises(ValueError, match='immutable finite'):
            replace(sequence, slices=(replace(sequence.slices[0], request=tampered),)).validate(substeps=5)


def test_position_physical_action_requires_actual_controller_set():
    from task_env import PositionPhysicalActionV1
    request = RequestedAction('absolute_joint', None, 'none', (0., 0., 0., -1., 0., 1., 0., 0.))
    position = PositionActionSequenceV1((PositionActionSliceV1(0, 5, request),))
    action = PositionPhysicalActionV1(position, (('a'*64, (0., 0., 1., 0., 0., 0.)),))
    action.validate(substeps=5, controller_identities=('a'*64,))
    with pytest.raises(ValueError, match='cover each bound Controller'):
        action.validate(substeps=5, controller_identities=('b'*64,))
    with pytest.raises(ValueError, match='finite immutable'):
        replace(action, physical_actions=(('a'*64, (True,)),)).validate(substeps=5, controller_identities=('a'*64,))


def test_v2_scene_associates_each_contribution_with_its_real_binding():
    from task_env.runtime.sessions.control_submission import (SceneCommandIntervalV2,
        SceneCommandContributionV1, _validate_scene_contributions)
    physical = SceneCommandContributionV1('robot-controller','body-wrench',('N','N*m'),
        'exclusive','effect','wrench','a'*64,2,'c'*64,('body:probe',),0,5)
    position = SceneCommandContributionV1('robot-controller','position-target',('rad','m'),
        'exclusive',None,'position','b'*64,7,'d'*64,('panda/actuator1',),0,5)
    interval = SceneCommandIntervalV2('scene-command-interval-v2','source','e'*64,'f'*64,
        None,None,(('physical','1'*64),('position','2'*64)),('1'*64,'2'*64),0,.002,5,(physical,position))
    _validate_scene_contributions(interval)
    with pytest.raises(ValueError,match='foreign binding'):
        _validate_scene_contributions(replace(interval,contribution_binding_sha256=('2'*64,'1'*64)))
    with pytest.raises(ValueError,match='distinct actual binding'):
        _validate_scene_contributions(replace(interval,binding_authorities=(('physical','1'*64),('position','1'*64))))


def test_mixed_preparation_is_cleared_if_dispatch_fails_before_compute(monkeypatch):
    from types import SimpleNamespace
    import task_env.runtime.sessions.control_lifecycle as lifecycle
    import task_env.runtime.sessions.physical_control as physical
    import task_env.runtime.sessions.position_physical as mixed_owner
    from task_env import PositionPhysicalActionV1
    class Execution:
        controllers = (SimpleNamespace(identity='a'*64),)
        generation = 1
    execution = Execution()
    monkeypatch.setattr(physical, 'PhysicalControlExecutionV1', Execution)
    session = SimpleNamespace(_prepared_position_sequence=None, _prepared_mixed_position=None)
    env = SimpleNamespace(_stopped=False, session=session, state=object(),
        binding=SimpleNamespace(physical_control_profile=lambda _env: execution),
        _physical_reset_selection=None)
    def prepare(_env, _action):
        session._prepared_position_sequence=object()
        return object()
    monkeypatch.setattr(mixed_owner, 'prepare_mixed_position', prepare)
    def fail_dispatch(*_args): raise ValueError('injected dispatch preflight')
    monkeypatch.setattr(lifecycle, '_dispatch_record', fail_dispatch)
    request = RequestedAction('absolute_joint', None, 'none', (0., 0., 0., -1., 0., 1., 0., 0.))
    action = PositionPhysicalActionV1(PositionActionSequenceV1((PositionActionSliceV1(0,5,request),)),
                                      (('a'*64, (1.,)),))
    with pytest.raises(ValueError, match='injected dispatch preflight'):
        lifecycle.prepare_selected_control_action(env, action)
    assert session._prepared_mixed_position is None and session._prepared_position_sequence is None


def test_v2_explicit_verified_native_body_sum_and_source_authority():
    from task_env.runtime.sessions.control_submission import (SceneCommandIntervalV2,
        SceneCommandContributionV1, _validate_scene_contributions)
    body = SceneCommandContributionV1('robot-controller','body-wrench',('N','N*m'),
        'sum','body-effect','body','a'*64,7,'c'*64,('body:probe',),0,5)
    caller = SceneCommandContributionV1('caller','body-com-wrench',('N','N*m'),
        'sum','caller-effect','caller',None,None,'d'*64,('body:probe',),0,5)
    pos = SceneCommandContributionV1('robot-controller','position-target',('rad','m'),
        'exclusive',None,'position','b'*64,3,'e'*64,('panda/actuator1',),0,5)
    interval = SceneCommandIntervalV2('scene-command-interval-v2','source','f'*64,'9'*64,
        None,None,(('physical','1'*64),('position','2'*64),('scene-load','f'*64)),
        ('1'*64,'f'*64,'2'*64),0,.002,5,(body,caller,pos))
    with pytest.raises(ValueError,match='matching command kinds'):
        _validate_scene_contributions(interval)
    _validate_scene_contributions(interval,verified_body_sums=frozenset({'body:probe'}))
    with pytest.raises(ValueError,match='foreign binding'):
        _validate_scene_contributions(replace(interval,contribution_binding_sha256=('1'*64,'1'*64,'2'*64)),verified_body_sums=frozenset({'body:probe'}))
    with pytest.raises(ValueError,match='repeats a physical effect'):
        _validate_scene_contributions(replace(interval,contributions=(body,replace(caller,physical_effect_id='body-effect'),pos)),verified_body_sums=frozenset({'body:probe'}))


def test_v2_task_contribution_requires_real_task_source_and_construction_authority():
    from task_env.runtime.sessions.control_submission import (SceneCommandIntervalV2,
        SceneCommandContributionV1, _validate_scene_contributions)
    body=SceneCommandContributionV1('robot-controller','body-wrench',('N','N*m'),
        'sum','physical','body','a'*64,7,'b'*64,('body:probe',),0,5)
    task=SceneCommandContributionV1('task','body-com-wrench',('N','N*m'),
        'sum','task-effect','task-writer',None,None,'c'*64,('body:probe',),0,5)
    pos=SceneCommandContributionV1('robot-controller','position-target',('rad','m'),
        'exclusive',None,'position','d'*64,3,'e'*64,('panda/actuator1',),0,5)
    interval=SceneCommandIntervalV2('scene-command-interval-v2','source','f'*64,'9'*64,
        None,None,(('physical','1'*64),('position','2'*64),('task','3'*64)),
        ('1'*64,'3'*64,'2'*64),0,.002,5,(body,task,pos),'4'*64)
    _validate_scene_contributions(interval,verified_body_sums=frozenset({'body:probe'}))
    with pytest.raises(ValueError,match='foreign binding'):
        _validate_scene_contributions(replace(interval,contribution_binding_sha256=('1'*64,'1'*64,'2'*64)),verified_body_sums=frozenset({'body:probe'}))
    with pytest.raises(ValueError,match='mixed Task source'):
        _validate_scene_contributions(replace(interval,task_source_sha256=None),verified_body_sums=frozenset({'body:probe'}))
