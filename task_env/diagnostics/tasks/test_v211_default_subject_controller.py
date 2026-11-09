"""Default Controller ownership and source-bound command checks."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.diagnostics.tasks.test_v211_controlled_subjects import _fixture
from task_env.robots.panda import PandaAgent
from task_env.robots.assembled_panda import AssembledPandaAgent
from task_env.robots.pendulum import PendulumEntity
from task_env.robots.two_wheel_balance import TwoWheelBalanceEntity
from task_env.artifacts import FrameReference


@pytest.mark.parametrize('subject_type', [PandaAgent, AssembledPandaAgent,
                                           PendulumEntity, TwoWheelBalanceEntity])
def test_each_subject_has_its_own_stable_unbound_default(subject_type):
    subject, other = subject_type(), subject_type()
    default = subject.default_controller
    assert default is subject.default_controller
    assert default is not other.default_controller
    assert not default.is_bound
    with pytest.raises(RuntimeError, match='source-bound'):
        default.compute([], object(), object())


def test_default_binds_once_and_preserves_declared_effort_semantics():
    execution, declaration, context = _fixture()
    channel = execution.compiled.binding.channels[0]
    default = PendulumEntity().default_controller
    with pytest.raises(ValueError, match='writer'):
        default.bind(declaration, execution.compiled.binding, writer_id='foreign', units=(channel.unit,))
    assert not default.is_bound
    with pytest.raises(ValueError, match='unit'):
        default.bind(declaration, execution.compiled.binding, writer_id='controller-a', units=('wrong',))
    assert not default.is_bound
    assert default.bind(declaration, execution.compiled.binding, writer_id='controller-a',
                        units=(channel.unit,)) is default
    state = SimpleNamespace(boundary=context.boundary, sample_clock=context.clock)
    default.reset_from_realized_state(state)
    result = default.compute([1.25], state, context)
    assert len(result.joint_efforts) == 1
    effort = result.joint_efforts[0]
    assert (effort.target_key, effort.unit, effort.value) == (channel.target_key, channel.unit, 1.25)
    with pytest.raises(ValueError, match='declared bounds'):
        default.compute([channel.effort_range[1] + 1], state, context)
    with pytest.raises(ValueError, match='stale or foreign'):
        default.compute([1.25], SimpleNamespace(boundary=None, sample_clock=context.clock), context)
    with pytest.raises(RuntimeError, match='already bound'):
        default.bind(declaration, execution.compiled.binding, writer_id='controller-a', units=(channel.unit,))


def test_nested_defaults_bind_atomically_as_distinct_existing_writers():
    execution, arm, context = _fixture()
    channel = execution.compiled.binding.channels[0]
    hand_channel = replace(channel, entity_id='hand', joint_id='finger',
                           component_path=('robot', 'finger'), owner_ids=('hand-writer',),
                           axis_frame=FrameReference('hand', 'base'),
                           native_actuator='hand-actuator', transmission_id='hand-transmission')
    binding = replace(execution.compiled.binding, channels=(channel, hand_channel))
    hand = replace(arm, subject_id='hand', entity_id='hand', root_frame=FrameReference('hand', 'base'),
                   channel_paths=(hand_channel.component_path,), controller_writers=('hand-writer',))
    default = AssembledPandaAgent().default_controller
    with pytest.raises(ValueError, match='writer'):
        default.bind_many(binding, ((arm, 'controller-a', (channel.unit,)),
                                    (hand, 'wrong', (hand_channel.unit,))))
    assert not default.is_bound
    children = default.bind_many(binding, ((arm, 'controller-a', (channel.unit,)),
                                           (hand, 'hand-writer', (hand_channel.unit,))))
    assert default.is_bound and default.controllers == children
    assert tuple(child.writer_id for child in children) == ('controller-a', 'hand-writer')
    state = SimpleNamespace(boundary=context.boundary, sample_clock=context.clock)
    for child in children:
        child.reset_from_realized_state(state)
    assert children[0].compute([1.25], state, context).joint_efforts[0].entity_id == 'arm'
    assert children[1].compute([.5], state, context).joint_efforts[0].entity_id == 'hand'
    with pytest.raises(RuntimeError, match='multi-controller compositor'):
        default.compute([], state, context)
