"""Formal selected control must enter a declared submission capability."""

from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.control_lifecycle import prepare_selected_control_action


def test_undeclared_controller_cannot_bypass_the_submission_owner():
    calls = []
    env = SimpleNamespace(_stopped=False, session=object(), position_profiles=(),
        controller=object(), _physical_execution=lambda: None,
        _prepare_reference_step=lambda *args, **kwargs: calls.append('legacy'))
    with pytest.raises(TypeError, match='common control submission capability'):
        prepare_selected_control_action(env, [0.0])
    assert calls == []


def test_position_sequence_is_not_reinterpreted_as_a_pose_action():
    from task_env.controllers.canonical.contracts import RequestedAction
    from task_env.controllers.canonical.position_sequence import PositionActionSequenceV1, PositionActionSliceV1

    def reject_projection(*args, **kwargs):
        pytest.fail('a typed Position sequence must not be projected as a pose action')

    profile = SimpleNamespace(identity='controller', prepare_action_request=reject_projection)
    boundary = SimpleNamespace(episode_id='episode', boundary_id='boundary', control_step=0)
    session = SimpleNamespace(episode_id='episode', state_boundary_identity=lambda: boundary)
    source = SimpleNamespace(source_id='source', source_closure_digest='closure')
    artifact = SimpleNamespace(identity_hash='artifact', timebase=SimpleNamespace(control_substeps=5))
    env = SimpleNamespace(_stopped=False, session=session, position_profiles=(profile,),
        position_plan=object(), _physical_execution=lambda: None, state=SimpleNamespace(control_step=0),
        horizon=8, binding=SimpleNamespace(external_actions=True), value={'source': source},
        artifact=artifact, _prepare_position_profile=lambda action, **kwargs: action)
    action = RequestedAction('absolute_joint', None, 'none', (0., 0., 0., -1., 0., 1., 0., 0.))
    sequence = PositionActionSequenceV1((PositionActionSliceV1(0, 5, action),))
    assert prepare_selected_control_action(env, sequence) is sequence
    assert session._control_lifecycle_dispatch.stage == 'prepared'
