"""Identity and ownership negatives for independently computed Position owners."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.controllers.canonical.contracts import CanonicalControlTarget, GripperControlTarget
from task_env.controllers.canonical.kinematics import ARM
from task_env.controllers.canonical.split_panda_position import (
    ARM_WRITER, HAND_WRITER, SplitPositionBundleV1, split_identity,
)


def test_split_outputs_require_exact_component_owners_and_native_target():
    arm_identity, hand_identity = 'a' * 64, 'b' * 64
    gripper = GripperControlTarget('panda-v1/gripper', .04, 10., .03)
    desired, servo = tuple(float(x) for x in range(7)), tuple(float(x)/2 for x in range(7))
    target = CanonicalControlTarget('canonical-control-v0', 'c' * 64,
        split_identity(arm_identity, hand_identity), ARM,
        dict(zip(ARM, desired, strict=True)), dict(zip(ARM, servo, strict=True)), gripper)
    bundle = SplitPositionBundleV1(arm_identity, hand_identity, desired, servo, gripper, target.identity_hash)
    plan = SimpleNamespace(controller_bindings=(
        SimpleNamespace(writer_id=ARM_WRITER, controller_identity=arm_identity),
        SimpleNamespace(writer_id=HAND_WRITER, controller_identity=hand_identity)))
    bundle.validate_target(target, plan)
    assert bundle.arm_hash != bundle.hand_hash and len(bundle.arm_hash) == len(bundle.hand_hash) == 64
    with pytest.raises(ValueError, match='source-bound plan'):
        replace(bundle, hand_identity='d' * 64).validate_target(target, plan)
    with pytest.raises(ValueError, match='native target'):
        replace(bundle, arm_servo_position=(0.,) * 7).validate_target(target, plan)
    with pytest.raises(ValueError, match='native target'):
        replace(bundle, gripper=replace(gripper, servo_opening_m=.02)).validate_target(target, plan)
    with pytest.raises(ValueError, match='source-bound plan'):
        bundle.validate_target(target, SimpleNamespace(controller_bindings=(
            SimpleNamespace(writer_id=ARM_WRITER, controller_identity=arm_identity),
            SimpleNamespace(writer_id='foreign-writer', controller_identity=hand_identity))))


def test_split_profile_rejects_missing_or_unadmitted_robot_before_source_build():
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    with pytest.raises(ValueError, match='explicitly selected Robot'):
        PickCubeReferenceEnv.selected_binding(SimpleNamespace(controller_profile='r1_split', robot_uid=None))
    with pytest.raises(ValueError, match='does not declare this Controller profile'):
        PickCubeReferenceEnv.selected_binding(SimpleNamespace(controller_profile='r1_split', robot_uid='panda-v1'))


def test_split_hand_preserves_existing_r1_gripper_law_across_force_modes():
    import numpy as np
    from task_env.environment.config import ActionConfig, GripperConfig
    from task_env.controllers.canonical.feedback import CanonicalControlFeedback, CanonicalGripperFeedback
    from task_env.controllers.canonical.production import ProductionCanonicalPandaController
    from task_env.controllers.canonical.split_panda_position import PandaHandPositionControllerV1
    from task_env.controllers.canonical.kinematics import FINGERS

    config, gripper_config = ActionConfig(), GripperConfig()
    model = SimpleNamespace(limits=np.asarray([[-3., 3.]] * 7), source_sha256='e' * 64)
    original = ProductionCanonicalPandaController(model, artifact_hash='c' * 64,
                                                   config=config, gripper_config=gripper_config)
    hand = PandaHandPositionControllerV1(config, gripper_config, 'c' * 64)
    current = SimpleNamespace(interpreted_values=(0.,) * 7 + (-1.,))
    original._arm._compute_arm = lambda *_: (current, np.zeros(7), np.zeros(7))

    def boundary(step, opening, force):
        state = SimpleNamespace(control_step=step, simulation_time=step * .01,
                                joint_position={FINGERS[0]: opening/2, FINGERS[1]: opening/2})
        feedback = CanonicalControlFeedback('canonical-control-feedback-v0', step, step * .01,
            CanonicalGripperFeedback('panda-v1/gripper', opening, force))
        return state, feedback

    state, feedback = boundary(0, .08, 0.)
    original.reset(state, feedback); hand.reset(state, feedback)
    for step, opening, force, scalar, expected, ready in (
            (0, .08, 0., -1., .078, False), (1, .078, 4., -1., .0659, False),
            (2, .076, 29.5, -1., .0659, True), (3, .075, 5., 1., .0679, False)):
        state, feedback = boundary(step, opening, force)
        current = SimpleNamespace(interpreted_values=(0.,) * 7 + (scalar,))
        _, old_target = original.compute(state, feedback, None)
        new_target = hand.compute(state, feedback, current)
        assert new_target == old_target.gripper
        assert new_target.servo_opening_m == pytest.approx(expected, abs=1e-12)
        assert hand.readiness(*boundary(step + 1, opening, force)).gripper.close_ready is ready
        assert hand.readiness(*boundary(step + 1, opening, force)).gripper == original.readiness(
            *boundary(step + 1, opening, force)).gripper


def test_split_preflights_both_owner_boundaries_before_computation():
    from task_env.controllers.canonical.split_panda_position import SplitPandaPositionControllerV1
    owner = object.__new__(SplitPandaPositionControllerV1)
    writes = []
    owner.arm = SimpleNamespace(_expected_step=0, compute=lambda *_: writes.append('arm'))
    owner.hand = SimpleNamespace(_expected_step=1, _feedback=lambda *_: None)
    with pytest.raises(RuntimeError, match='one current reset boundary'):
        owner.compute(SimpleNamespace(control_step=0), object(), object())
    assert writes == []
    owner.hand._expected_step = 0
    def stale(*_):
        raise ValueError('stale feedback')
    owner.hand._feedback = stale
    with pytest.raises(ValueError, match='stale feedback'):
        owner.compute(SimpleNamespace(control_step=0), object(), object())
    assert writes == []
