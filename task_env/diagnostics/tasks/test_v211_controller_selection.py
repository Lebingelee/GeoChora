"""Production-owner selection checks for generic subject effort Controllers."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.artifacts.state import (
    CanonicalStateViewV2, StateFieldRequirement, StateRequirements, TypedJointStateValue,
)
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.environment.configuration import resolve_task_env_config
from task_env.controllers.canonical.physical_controller import select_subject_effort_controller
from task_env.runtime.sessions.control import bind_selected_controller
from task_env.runtime.sessions.physical_control import (
    ControlledSubjectV1, PhysicalControlExecutionV1,
)
from task_env.artifacts import FrameReference


def _selection(profile_id, *, state_fields=True):
    compiled, context, _, _ = _case()
    subject = ControlledSubjectV1(
        'generic-rotor', 'arm', 'source-a', 'b' * 64, 'references_existing',
        'fixed', FrameReference('arm', 'base'), None,
        (('robot', 'arm-drive-joint'),), ('controller-a',),
        supported_controller_profiles=(
            'direct_joint_effort_v1', 'velocity_damped_joint_effort_v1'))
    controller = select_subject_effort_controller(
        subject, compiled.binding, profile_id=profile_id, writer_id='controller-a',
        units=('N*m',), cadence_s=.01)
    requirements = ()
    if state_fields:
        requirements = (
            StateFieldRequirement('state-field-requirement-v1', 'joint_position',
                'joint', 'arm', 'drive', 'required', 'evaluation_boundary',
                'joint-definition', 'joint_state_query'),
            StateFieldRequirement('state-field-requirement-v1', 'joint_velocity',
                'joint', 'arm', 'drive', 'required', 'evaluation_boundary',
                'joint-definition', 'joint_state_query'),
        )
    state_requirements = StateRequirements(
        'state-requirements-v1', 'controller', 'controller-a', requirements)
    execution = PhysicalControlExecutionV1(
        compiled, (controller,), compiled.scene, {'arm/drive': compiled.scene.articulations[0].joints[0]},
        {}, state_requirements, 1, (subject,))
    source = SimpleNamespace(source_id='source-a', source_closure_digest='b' * 64,
        joints={'arm/drive': 'drive'}, free_joints={}, bodies={}, frames={})
    artifact = SimpleNamespace(identity_hash='a' * 64,
        timebase=SimpleNamespace(control_dt=.01))
    value = {'controller': controller, 'physical_execution': execution,
        'selected_controller_profile_id': profile_id, 'artifact': artifact, 'source': source}
    return value, context, controller, subject


def test_subject_selects_direct_or_velocity_damped_effort_with_distinct_output():
    direct_value, context, direct, _ = _selection('direct_joint_effort_v1')
    damped_value, _, damped, _ = _selection('velocity_damped_joint_effort_v1')
    joint = TypedJointStateValue('typed-joint-state-v1', 'arm', 'drive', 'revolute',
        'radian', (0.,), 'radian_per_second', (2.,))
    state = CanonicalStateViewV2('canonical-state-v2', 'SI_right_handed_z_up_wxyz',
        context.boundary, context.clock, (joint,), (), ())
    direct.reset_from_realized_state(state)
    damped.reset_from_realized_state(state)
    command_direct = direct.compute({'torque': np.asarray([1.], dtype=np.float32)}, state, context)
    command_damped = damped.compute({'torque': np.asarray([1.], dtype=np.float32)}, state, context)
    assert direct_value['physical_execution'].controllers[0].profile_id == 'direct_joint_effort_v1'
    assert damped_value['physical_execution'].controllers[0].profile_id == 'velocity_damped_joint_effort_v1'
    assert command_direct.joint_efforts[0].value == pytest.approx(1.)
    assert command_damped.joint_efforts[0].value == pytest.approx(.5)
    assert damped.profile.model_requirement.source_closure_sha256 == 'b' * 64
    assert damped.profile.model_requirement.computation == 'pure_no_physics_step'
    assert np.array_equal(damped.last_action, np.asarray([1.], dtype=np.float32))
    assert damped.action_space.contains({'torque': np.asarray([1.], dtype=np.float32)})


def test_common_selection_owner_emits_source_bound_match_before_compute():
    value, _, controller, _ = _selection('velocity_damped_joint_effort_v1')
    calls = []
    original_compute = controller.compute
    controller.compute = lambda *args, **kwargs: (calls.append('compute'), original_compute(*args, **kwargs))[1]
    selected = bind_selected_controller(value, binding=SimpleNamespace(), provider='mujoco', backend='cpu')
    assert selected.physical_execution is value['physical_execution']
    match, = selected.selection_matches
    assert match.control_kind == 'joint_effort'
    assert match.selection_profile_id == 'velocity_damped_joint_effort_v1'
    assert match.subject_ids == ('generic-rotor',)
    assert match.channel_keys == ('arm/drive',)
    assert match.channel_units == ('N*m',)
    assert match.source_closure_sha256 == 'b' * 64
    assert match.cadence_s == .01
    assert calls == []


def test_selection_rejects_unsupported_profile_and_missing_model_state_before_compute():
    value, _, controller, _ = _selection('velocity_damped_joint_effort_v1')
    calls = []
    controller.compute = lambda *args, **kwargs: calls.append('compute')
    value['selected_controller_profile_id'] = 'unsupported_profile'
    with pytest.raises(ValueError, match='not declared by the controlled subject'):
        bind_selected_controller(value, binding=SimpleNamespace(), provider='mujoco', backend='cpu')
    assert calls == []

    value, _, controller, _ = _selection('velocity_damped_joint_effort_v1', state_fields=False)
    calls = []
    controller.compute = lambda *args, **kwargs: calls.append('compute')
    with pytest.raises(ValueError, match='lacks required state field joint_position'):
        bind_selected_controller(value, binding=SimpleNamespace(), provider='mujoco', backend='cpu')
    assert calls == []


def test_public_control_profile_is_task_scoped_and_explicit():
    from task_env.tasks.pendulum import PendulumEnv
    from task_env.tasks.two_wheel_balance import TwoWheelBalanceEnv

    default = resolve_task_env_config(PendulumEnv, None)
    explicit = resolve_task_env_config(PendulumEnv, {
        'execution': {'physics_provider': 'mujoco'}, 'controller': {'profile_id': 'velocity_damped_joint_effort_v1'}})
    direct = resolve_task_env_config(TwoWheelBalanceEnv, {
        'controller': {'profile_id': 'direct_joint_effort_v1'}})
    assert default.controller_profile == 'direct_joint_effort_v1'
    assert explicit.controller_profile == 'velocity_damped_joint_effort_v1'
    assert direct.controller_profile == 'direct_joint_effort_v1'
    with pytest.raises(ValueError, match='unsupported selected controller profile'):
        resolve_task_env_config(PendulumEnv, {'controller': {'profile_id': 'r3_continuous_v1'}})
