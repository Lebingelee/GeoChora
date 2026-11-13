"""Provider-free joint-reference effort servo and drive-conflict checks."""
from dataclasses import replace
import pytest
from task_env.artifacts.state import CanonicalStateViewV2, TypedJointStateValue
from task_env.controllers.canonical.effort_servo import JointReferenceEffortControllerV1, JointReferenceEffortProfileV1
from task_env.controllers.canonical.model import AffineJointBiasModelV1, ControllerModelRequirementV1
from task_env.runtime.sessions.physical_control import compile_physical_control_binding, prepare_physical_command_batch
from task_env.diagnostics.tasks.physical_contract_fixtures import _case, _joint_receipt


def make_case():
    plan, context, _, assessment = _case()
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1', 'servo-example',
        'geochora', 'v1', 'stdlib', 'source-a', 'b'*64, ('arm/drive',), ('rad',),
        'joint_bias', ('N*m',), 'joint-axis', 'evaluation_boundary', .01, 0.,
        'pure_no_physics_step', 'controller-a', 'none', 'required')
    profile = JointReferenceEffortProfileV1('joint-reference-effort-profile-v1', 'controller-a',
        ('joint-reference',), ('arm/drive',), ((1.,),), (4.,), (3.,), requirement)
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement, (.5,), (-4.,), (-3.,))
    joint = TypedJointStateValue('typed-joint-state-v1', 'arm', 'drive', 'revolute',
        'radian', (.1,), 'radian_per_second', (.2,))
    state = CanonicalStateViewV2('canonical-state-v2', 'SI_right_handed_z_up_wxyz',
        context.boundary, context.clock, (joint,), (), ())
    return plan, context, assessment, profile, model, state


def test_servo_uses_named_reference_state_bias_and_explicit_pd():
    plan, context, assessment, profile, model, state = make_case()
    controller = JointReferenceEffortControllerV1(profile, plan.binding, model)
    command = controller.compute((.25,), state, context)
    assert command.joint_efforts[0].controller_law == 'explicit_full_pd'
    assert command.joint_efforts[0].value == pytest.approx(4*(.25-.1)-3*.2+.5)
    result = prepare_physical_command_batch(plan, command, expected_context=context,
        assessment=assessment('joint_effort'), joint_build_receipt=_joint_receipt(plan, context))
    assert result.joints[0].value == pytest.approx(.5)
    with pytest.raises(ValueError, match='state is stale'):
        controller.compute((.25,), state, replace(context, boundary=replace(context.boundary, state_revision=1)))
    with pytest.raises(ValueError, match='negative PD'):
        JointReferenceEffortControllerV1(profile, plan.binding, replace(model, velocity_coefficients=(3.,)))


def test_servo_refuses_uncoordinated_position_drive():
    plan, context, assessment, profile, model, state = make_case()
    binding = replace(plan.binding, channels=(replace(plan.binding.channels[0], native_drive='position'),))
    driven = compile_physical_control_binding(plan.scene, plan.root, plan.children, binding)
    command = JointReferenceEffortControllerV1(profile, binding, model).compute((.25,), state, context)
    old = assessment('joint_effort')
    capability = replace(old, request_identity=binding.identity_hash,
        rows=tuple(replace(row, object_ref=f'binding:{binding.identity_hash}') for row in old.rows))
    with pytest.raises(ValueError, match='uncoordinated native drive'):
        prepare_physical_command_batch(driven, command, expected_context=context,
            assessment=capability, joint_build_receipt=_joint_receipt(driven, context))
