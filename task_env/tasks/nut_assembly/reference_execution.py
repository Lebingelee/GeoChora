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


class ReferenceArmSchedule:
    """Selected V2 public-ack interpolation; runtime owns native stepping."""
    version = 'linear-native-ramp-after-lift-v2-public-ack-memory'

    def __init__(self, solution, memory):
        self.solution, self.memory = solution, memory

    def begin(self, target):
        self.active = bool(self.solution._lift_released)
        if self.active and self.memory.last_applied_arm is None:
            raise ValueError('arm ramp requires a preceding public applied acknowledgement')
        self.initial = dict(self.memory.last_applied_arm or target.arm_servo_position)

    def target(self, target, index, count):
        from dataclasses import replace
        if not self.active:
            return target
        fraction = (index + 1) / count
        arm = {k: self.initial[k] + fraction * (v - self.initial[k])
               for k, v in target.arm_servo_position.items()}
        return replace(target, arm_position=arm, arm_servo_position=arm)

    def applied(self, acknowledgement):
        self.memory.last_applied_arm = dict(acknowledgement.arm_servo_position)
