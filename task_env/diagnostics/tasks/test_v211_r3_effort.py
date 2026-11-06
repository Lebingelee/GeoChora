"""Provider-free checks for R3 reference to shared effort-servo composition."""
from types import SimpleNamespace
import pytest

from task_env.artifacts import FrameReference, PoseWorld
from task_env.artifacts.state import CanonicalStateViewV2, TypedJointStateValue, TypedFrameStateValue
from task_env.controllers.canonical.effort_servo import JointReferenceEffortControllerV1
from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1
from task_env.controllers.canonical.r3_effort import R3ReferenceEffortControllerV1
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case


def test_r3_pose_reference_flows_to_named_servo_once_per_boundary():
    plan, context, effort, _ = _case()
    names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
    joints = tuple(TypedJointStateValue('typed-joint-state-v1', 'panda-v1', name,
        'revolute' if i < 7 else 'prismatic', 'radian' if i < 7 else 'meter',
        (.01*i,), 'radian_per_second' if i < 7 else 'meter_per_second', (0.,))
        for i, name in enumerate(names))
    frame = TypedFrameStateValue('typed-frame-state-v1', FrameReference('panda-v1', 'ee'),
                                 PoseWorld((.5, 0., .6), (1., 0., 0., 0.)))
    state = CanonicalStateViewV2('canonical-state-v2', 'SI_right_handed_z_up_wxyz',
                                  context.boundary, context.clock, joints, (frame,), ())
    calls = []
    class R3:
        identity = 'a'*64
        def reset(self, adapted): calls.append(('reset', adapted.control_step))
        def compute_reference(self, adapted, requested):
            calls.append(('reference', requested.mode, adapted.pose_world['panda-v1/ee']))
            return SimpleNamespace(arm_position={f'panda-v1/joint{i}': .1*i for i in range(1, 8)},
                                   canonical_action=SimpleNamespace(interpreted_values=(*requested.values[:7], 0.)))
    class Linear:
        action_shape = (8,)
        def compute(self, action, observed, actual_context):
            calls.append(('servo', action, observed.boundary))
            return PhysicalCommandBatchV1('physical-command-batch-v1', actual_context, (effort('test-effort', .1),), (), ())
    servo = object.__new__(JointReferenceEffortControllerV1)
    servo._linear, servo.binding, servo.writer_id, servo.identity = Linear(), plan.binding, 'controller-a', 'b'*64
    controller = R3ReferenceEffortControllerV1(R3(), servo, entity_id='panda-v1', end_frame_id='ee', opening_range_m=.08)
    result = controller.compute((.5, 0., .6, 1., 0., 0., 0., 0.), state, context)
    assert result.context == context
    assert calls[0] == ('reset', 0)
    assert calls[1][0:2] == ('reference', 'absolute_pose')
    assert calls[2][1] == pytest.approx((.1, .2, .3, .4, .5, .6, .7, .04))
    with pytest.raises(ValueError, match='duplicated or out of order'):
        controller.compute((.5, 0., .6, 1., 0., 0., 0., 0.), state, context)


def test_unequal_finger_pd_outputs_project_to_equal_constraint_effort():
    from dataclasses import replace
    from task_env.controllers.canonical.r3_effort import ConstrainedPairEffortControllerV1
    plan, context, effort, _ = _case()
    one = replace(effort('finger-one', .4), entity_id='panda-v1', joint_id='finger_joint1',
                  joint_kind='prismatic', unit='N', axis_frame=FrameReference('panda-v1', 'hand'))
    two = replace(effort('finger-two', .2), entity_id='panda-v1', joint_id='finger_joint2',
                  joint_kind='prismatic', unit='N', axis_frame=FrameReference('panda-v1', 'hand'))
    class Linear:
        action_shape = (8,)
        def compute(self, action, state, actual_context):
            return PhysicalCommandBatchV1('physical-command-batch-v1', actual_context, (one, two), (), ())
    servo = object.__new__(JointReferenceEffortControllerV1)
    servo._linear, servo.binding, servo.writer_id, servo.identity = Linear(), plan.binding, 'controller-a', 'b'*64
    controller = ConstrainedPairEffortControllerV1(servo)
    result = controller.compute((0.,)*8, None, context)
    assert tuple(item.value for item in result.joint_efforts) == pytest.approx((.3, .3))
    assert sum(item.value for item in result.joint_efforts) == pytest.approx(.6)
    assert all(item.controller_law == 'explicit_full_pd' for item in result.joint_efforts)
