"""Selected construction support; no session stepping or diagnostic imports.

NativeRateGripperServo follows the historical frequency_grasp/cadence owner.
Its new source identity is recorded separately; the old module remains intact.
"""
from dataclasses import dataclass
from ...controllers.canonical.gripper_execution import EqualRateGripperServo


@dataclass
class ArmRampMemory:
    last_applied_arm: dict | None = None


class NativeRateGripperServo(EqualRateGripperServo):
    version = 'native-gripper-500hz-v1'

    def inner_gripper_step(self, state, feedback):
        if abs(self.controller.inner_physics_dt_s - .002) > 1e-12:
            raise ValueError('Native-rate gripper requires2ms physics clock')
        target, diag = self._update(state, feedback)
        self._last_control_step = state.control_step
        self._last_target = target
        self._last_diagnostics = dict(diag)
        self.update_count += 1
        return target, {**diag, 'inner_update_performed': True,
                        'inner_update_period_s': .002, 'configured_inner_rate_hz': 500}


class ReferenceExecutionController:
    def __init__(self, hold, control_dt):
        self.hold = hold
        self.inner = NativeRateGripperServo(hold.controller, 500, control_dt)

    def __getattr__(self, name):
        return getattr(self.hold, name)

    def compute(self, *args):
        return self.hold.compute(*args)

    def inner_gripper_step(self, *args):
        return self.inner.inner_gripper_step(*args)
