"""Diagnostic native-clock owner; frozen EqualRateGripperServo stays untouched.

Same R3 physical-time law at500Hz independent of arm policy rate. This mode has
its own strict recorder admission; it is never labeled outer-equal-rate.
"""
from ....controllers.canonical.gripper_execution import EqualRateGripperServo

class NativeRateGripperServo(EqualRateGripperServo):
    version='native-gripper-500hz-v1'
    def inner_gripper_step(self,state,feedback):
        if abs(self.controller.inner_physics_dt_s-.002)>1e-12:
            raise ValueError('Native-rate gripper requires2ms physics clock')
        target,diag=self._update(state,feedback)
        self._last_control_step=state.control_step;self._last_target=target
        self._last_diagnostics=dict(diag);self.update_count+=1
        return target,{**diag,'inner_update_performed':True,'inner_update_period_s':.002,
                       'configured_inner_rate_hz':500}


def validate_native_cadence(recording):
    if recording['recipe']['cadence']!='fixed-native-500hz-v1':
        raise ValueError('Incorrect native-clock recording label')
    for transition in recording['transitions']:
        interval=transition['interval']
        if interval['physics_dt']!=.002 or len(interval['substeps'])!=interval['control_substeps']:
            raise ValueError('Native-clock interval mismatch')
        if not all(s['updated'] is True for s in interval['substeps']):
            raise ValueError('Native-clock command update missing')
