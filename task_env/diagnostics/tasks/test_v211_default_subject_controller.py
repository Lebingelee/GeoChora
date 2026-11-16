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


@pytest.mark.parametrize('uid', ['pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'])
def test_assembled_default_binds_declared_channels_against_actual_native_source(uid):
    """Bind the real Robot declaration and check the independent compiled transmission."""
    import mujoco
    from task_env import make_env

    env = make_env(uid, config={
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
        'robot': {'uid': 'panda-arm-hand-v1'}, 'controller': {'profile_id': 'r3_continuous_v1'},
    })
    try:
        env.reset(seed=19 if uid.startswith('nut-') else 31)
        robot = env.binding.robot
        default = robot.default_controller
        assert default is robot.default_controller and not default.is_bound
        assert env.controller is not default
        declaration = env.value['source'].composition_runtime_input.fixed_declaration
        plan, model = declaration.attachment_plan, env.session._model
        names = [plan.native_actuator_names[f'panda-arm/actuator{i}'] for i in range(1, 8)]
        names.append(plan.native_actuator_names['panda-hand/actuator8'])
        ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) for name in names]
        assert min(ids) >= 0
        ranges = tuple(tuple(map(float, model.actuator_forcerange[i])) for i in ids)
        compiled, subjects, _ = robot.compile_effort_subjects(declaration,
            artifact_sha256=env.artifact.identity_hash, source_id=declaration.parent_source.source_id,
            native_ranges=ranges, native_drive='position')
        with pytest.raises(ValueError, match='source id'):
            robot.compile_effort_subjects(declaration, artifact_sha256=env.artifact.identity_hash,
                source_id='foreign', native_ranges=ranges, native_drive='position')
        with pytest.raises(ValueError, match='unit'):
            default.bind_many(compiled.binding, ((subjects[0], 'panda-arm-effort', ('wrong',) * 7),
                                                 (subjects[1], 'panda-hand-effort', ('N', 'N'))))
        assert not default.is_bound
        children = default.bind_many(compiled.binding, (
            (subjects[0], 'panda-arm-effort', ('N*m',) * 7),
            (subjects[1], 'panda-hand-effort', ('N', 'N'))))
        assert tuple(child.writer_id for child in children) == ('panda-arm-effort', 'panda-hand-effort')
        channels = compiled.binding.channels
        assert tuple(channel.native_actuator for channel in channels[:7]) == tuple(names[:7])
        assert tuple(channel.native_actuator for channel in channels[7:]) == (names[7], names[7])
        assert tuple(channel.transmission_coefficient for channel in channels[7:]) == (.5, .5)
        for i, actuator in enumerate(ids[:7], 1):
            joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT,
                env.value['source'].joints[f'panda-v1/joint{i}'])
            assert model.actuator_trntype[actuator] == mujoco.mjtTrn.mjTRN_JOINT
            assert model.actuator_trnid[actuator, 0] == joint
        assert model.actuator_trntype[ids[7]] == mujoco.mjtTrn.mjTRN_TENDON
        tendon = int(model.actuator_trnid[ids[7], 0])
        start, count = int(model.tendon_adr[tendon]), int(model.tendon_num[tendon])
        assert count == 2
        actual_joints = tuple(int(v) for v in model.wrap_objid[start:start + count])
        expected_joints = tuple(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT,
            env.value['source'].joints[f'panda-v1/finger_joint{i}']) for i in (1, 2))
        assert actual_joints == expected_joints
        assert tuple(model.wrap_prm[start:start + count]) == pytest.approx((.5, .5))
        # The selected Position task does not publish a physical-effort state;
        # exercise the real source-bound defaults with an explicit synthetic
        # physical boundary, without claiming a native effort submission.
        from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
        from task_env.controllers.canonical.physical_commands import PhysicalCommandContextV1
        boundary = StateBoundaryIdentity('state-boundary-identity-v1', 'test-episode',
            'reset-' + 'a' * 64, compiled.binding.scene_sha256, 'test-scene', 'test-materialization', 0, 0)
        clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.)
        context = PhysicalCommandContextV1('physical-command-context-v1', compiled.binding.source_id,
            compiled.binding.source_closure_sha256, compiled.binding.artifact_sha256,
            boundary, clock, 0, 0, .01, .01)
        state = SimpleNamespace(boundary=boundary, sample_clock=clock)
        for child, size, effort in zip(children, (7, 2), (1.25, .5), strict=True):
            child.reset_from_realized_state(state)
            commands = child.compute([effort] * size, state, context)
            assert len(commands.joint_efforts) == size
            assert all(command.value == effort for command in commands.joint_efforts)
    finally:
        env.close()
